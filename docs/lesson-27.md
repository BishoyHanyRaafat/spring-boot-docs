---
title: "Lesson 27: Integration Testing with PostgreSQL & Testcontainers"
sidebar_position: 27
---

So far, we’ve mostly tested security behavior with mocked authentication and mocked dependencies.

That’s useful—but there’s a gap.

Our real authorization policy depends on things like:

```text
Post 42
   ↓
Project 7
   ↓
Alice → OWNER
```

That information lives in PostgreSQL.

So eventually we need a test that says:

Start a real PostgreSQL database, insert realistic ProjectHub data, make an HTTP request, and verify the actual result.

That’s where **Testcontainers** comes in.

Spring Boot’s current testing support integrates with Testcontainers, and `@ServiceConnection` can automatically provide connection details from a container to Spring Boot’s auto-configuration.  

---

## **1. Why not just use your development PostgreSQL?**

Imagine your tests connect to:

```text
localhost:5432/projecthub
```

Problems:

- Your database may contain old data.
- Tests can interfere with each other.
- Your schema may differ from CI.
- Another developer may have a different PostgreSQL version.
- Tests depend on someone’s machine configuration.

We want:

```text
Test
 ↓
fresh PostgreSQL
 ↓
run migrations
 ↓
insert test data
 ↓
run test
 ↓
throw database away
```

That’s much more reproducible.

---

# **2. What is Testcontainers?**

Testcontainers allows tests to start real infrastructure in containers.

For ProjectHub:

```text
JUnit
  │
  ├── Spring Boot
  │
  └── PostgreSQL container
          │
          └── real PostgreSQL
```

So we’re not pretending PostgreSQL exists.

We’re actually running PostgreSQL.

The Testcontainers JUnit integration supports both containers shared across a test class and containers restarted for individual test methods.  

---

# **3. The dependency**

For a Maven Spring Boot project, you’ll typically need:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-testcontainers</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
```

And of course your normal:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Spring Boot’s testing starter provides the general testing infrastructure, including JUnit Jupiter and assertion libraries.  

---

# **4. The PostgreSQL container**

Conceptually:

```java
@Testcontainers
@SpringBootTest
class PostIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:18");
}
```

There are several important things here.

### **`@Testcontainers`**

Tells the Testcontainers JUnit integration to manage container lifecycle.

### **`@Container`**

Identifies the actual container.

### **`static`**

Means the container can be shared by all tests in this class rather than recreated for every test method.

### **`@ServiceConnection`**

This is the really convenient Spring Boot part.

Spring Boot can automatically derive the connection details needed to connect to the container, rather than forcing us to manually configure host, port, username, password, etc.  

---

# **5. What happens during startup?**

Imagine running:

```text
mvn test
```

The rough flow is:

```text
JUnit starts
   ↓
Testcontainers starts PostgreSQL
   ↓
PostgreSQL becomes available
   ↓
Spring Boot starts
   ↓
@ServiceConnection provides DB connection details
   ↓
DataSource connects to container
   ↓
Flyway runs migrations
   ↓
JPA starts
   ↓
test executes
```

This is much closer to production than mocking your repository.

---

# **6. Why this is perfect for ProjectHub**

Remember our authorization rule:

```text
posts.delete
AND
(
    owns post
    OR
    project owner
)
```

We can create real data:

```text
users
────────────────
Alice
Bob
```

```text
projects
────────────────
Project 7
```

```text
project_memberships
────────────────────────
Alice → Project 7 → OWNER
Bob   → Project 7 → MEMBER
```

```text
posts
────────────────
Post 42 → Bob → Project 7
```

Then authenticate as Alice.

Our application has to actually query PostgreSQL to discover:

```text
Alice → OWNER → Project 7
```

There’s no mock pretending that relationship exists.

---

# **7. The test we’re aiming for**

Conceptually:

```java
@Test
void projectOwnerCanDeleteAnotherUsersPost() throws Exception {

    mvc.perform(
        delete("/posts/42")
            .with(jwt()
                .authorities(
                    new SimpleGrantedAuthority("posts.delete")
                )
            )
    )
    .andExpect(status().isNoContent());
}
```

But now:

```text
Post 42
    ↓
PostgreSQL
    ↓
Project 7
    ↓
Alice = OWNER
```

is real.

That’s a proper integration test.

---

# **8. Test the opposite**

Now change Alice:

```text
Alice → Project 7 → MEMBER
```

and don’t make her the post owner.

Run the exact same request:

```text
DELETE /posts/42
```

Expected:

```text
403 Forbidden
```

Now we’re testing the complete policy:

```text
JWT authority
      +
Post ownership
      +
Project membership
      +
PostgreSQL
      ↓
authorization decision
```

That’s significantly more valuable than a unit test that simply mocks:

```java
when(policy.canDelete(...))
    .thenReturn(false);
```

---

# **9. Unit tests still matter**

Don’t misunderstand this.

We are **not replacing unit tests with Testcontainers**.

We’re adding another layer.

### **Unit test**

Fast:

```text
PostDeletionPolicy
      ↓
mock repositories
      ↓
decision
```

### **Integration test**

Real:

```text
HTTP
 ↓
Spring Security
 ↓
Controller
 ↓
Service
 ↓
JPA
 ↓
Flyway
 ↓
PostgreSQL
```

You want both.

Spring Boot’s testing documentation explicitly distinguishes unit testing from integration testing with an actual Spring `ApplicationContext`.  

---

# **10. Flyway becomes especially important here**

Remember Lesson 15?

We decided:

```text
Flyway → owns schema
Hibernate → validates schema
```

That’s excellent for integration tests.

When the PostgreSQL container starts:

```text
empty PostgreSQL
       ↓
Flyway
       ↓
V1__create_users.sql
       ↓
V2__create_projects.sql
       ↓
V3__create_posts.sql
       ↓
...
```

Now your test database has the same schema construction process your application expects.

This catches problems like:

```text
Entity says:
author_id

Migration says:
user_id
```

A mock repository wouldn’t catch that.

---

# **11. Integration tests can catch real JPA problems**

For example, your authorization repository might contain:

```java
boolean existsByProjectIdAndUsernameAndRole(
    Long projectId,
    String username,
    ProjectRole role
);
```

Maybe you accidentally wrote:

```text
projectId
```

where the entity actually has:

```text
project.id
```

A unit test with a mocked repository won’t notice.

A real integration test can expose:

```text
JPA query failure
```

or:

```text
incorrect result
```

That’s exactly what we want.

---

# **12. Test data setup**

We need controlled test data.

A common pattern is:

```text
@BeforeEach
void setUp() {
    // create users
    // create project
    // create memberships
    // create posts
}
```

But there’s an important question:

Should we create everything through repositories or through SQL?

Both are useful.

### **Repositories**

Good when testing application behavior.

```java
userRepository.save(...)
projectRepository.save(...)
```

### **SQL**

Good when you need precise database state.

For example:

```sql
INSERT INTO project_memberships ...
```

We’ll learn better database test-fixture patterns as the project grows.

---

# **13. Don’t accidentally test your test setup**

Here’s a common mistake.

Suppose the test does:

```text
create Alice
create Project
make Alice OWNER
create Post
```

Then:

```text
call API
```

If the setup itself uses buggy application logic, your test can accidentally verify the wrong thing.

For important integration tests, it’s sometimes useful to establish state directly using repositories or SQL, then test the actual feature separately.

---

# **14. Transaction rollback isn’t a universal solution**

You may see:

```java
@Transactional
```

on tests.

It can be useful, but don’t assume:

Every test automatically gets a clean database because of rollback.

Why?

Because your application may perform operations in different transactions, and some behavior occurs outside the test transaction.

For Testcontainers integration tests, you should deliberately think about test isolation.

Later we’ll learn:

```text
transaction boundaries
test transactions
cleanup
database reset
```

rather than relying on magic.

---

# **15. Testcontainers doesn’t mean “one container per test”**

That would be unnecessarily expensive.

You can share a container across the tests in a class:

```text
Test class
 ├── Test 1
 ├── Test 2
 ├── Test 3
 └── Test 4

       ↓

   PostgreSQL
```

The Testcontainers JUnit integration supports static containers shared between test methods.  

But you still need to isolate the **data** between tests.

Container reuse and database-state isolation are two different things.

---

# **16. A good architecture for ProjectHub tests**

Eventually we’ll have something like:

```text
src/test
│
├── unit
│   ├── PostDeletionPolicyTest
│   └── JwtServiceTest
│
├── integration
│   ├── PostRepositoryTest
│   ├── ProjectMembershipTest
│   └── PostAuthorizationIntegrationTest
│
└── web
    ├── PostControllerTest
    └── AuthenticationControllerTest
```

The exact package structure isn’t important.

The distinction is.

---

# **17. Our security test matrix**

For the post deletion feature:

|**Scenario**|**JWT**|**Permission**|**Ownership/Membership**|**Expected**|
|---|---|---|---|---|
|Alice owns post|valid|delete|owner|204|
|Project owner|valid|delete|project OWNER|204|
|Project member|valid|delete|member only|403|
|No permission|valid|read|owner|403|
|Anonymous|none|—|—|401|

And now PostgreSQL is part of the test.

This is the point where your application starts getting **serious automated security coverage**.

---

# **18. One more thing: CI**

This is another major benefit.

Your local machine:

```text
Spring Boot
+
Testcontainers
+
PostgreSQL container
```

CI:

```text
Spring Boot
+
Testcontainers
+
PostgreSQL container
```

Same basic environment.

You aren’t saying:

“It works because my laptop happens to have PostgreSQL configured this way.”

You’re saying:

“The test creates the infrastructure it needs.”

That makes integration testing much more reproducible.

---

# **Your Exercise 27**

Don’t implement the entire security test suite yet.

Create **one integration test**:

### **Scenario**

```text
Alice:
    posts.delete

Project:
    Project 7

Membership:
    Alice → OWNER

Post:
    Post 42 → Bob → Project 7
```

Then execute:

```http
DELETE /posts/42
```

Expected:

```text
204 No Content
```

Your test should use:

```text
@SpringBootTest
@Testcontainers
@Container
@ServiceConnection
PostgreSQLContainer
MockMvc
jwt()
```

And let your normal **Flyway migrations** create the database schema.

The important architecture is:

```text
             Testcontainers
                  │
                  ▼
           Real PostgreSQL
                  │
                Flyway
                  │
                  ▼
            Spring Boot
                  │
             MockMvc
                  │
                  ▼
              JWT/User
                  │
                  ▼
          Authorization Policy
                  │
                  ▼
             DELETE post
```

Once you can make that test pass, **Lesson 28 will be database test isolation, test fixtures, and testing the entire ProjectHub authorization matrix**. After that, we’ll move beyond testing into the next major area: **production-ready application configuration and observability**.