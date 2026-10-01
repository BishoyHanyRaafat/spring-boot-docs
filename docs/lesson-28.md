---
title: Lesson 28: Test Isolation, Fixtures & the Full Authorization Matrix
sidebar_position: 28
---



We now have enough pieces to start testing ProjectHub like a real application.

The problem is no longer:

“How do I write one integration test?”

It’s:

**How do I make dozens or hundreds of integration tests reliable, isolated, and understandable?**

This is where test-data design becomes important.

---

## **1. The problem with shared test data**

Imagine five tests all use:

```text
Alice
Project 7
Post 42
```

Test 1 changes Alice’s membership.

Test 2 deletes Post 42.

Test 3 expects Post 42 to exist.

Now the result depends on test order.

That’s terrible.

Tests should ideally behave like:

```text
Test A
  ↓
fresh state
  ↓
result

Test B
  ↓
fresh state
  ↓
result
```

not:

```text
Test A
  ↓
changes database
  ↓
Test B inherits changes
  ↓
random failure
```

---

# **2. Three things must be isolated**

For our integration tests:

### **Application state**

Spring beans and application context.

### **Database state**

Users, projects, posts, memberships.

### **Security state**

The authenticated user/security context.

These are separate concerns.

---

# **3. Container lifetime vs database lifetime**

This is a very important distinction.

We can keep one PostgreSQL container running:

```text
PostgreSQL container
├── Test 1
├── Test 2
├── Test 3
└── Test 4
```

while resetting the **database contents** between tests.

That’s generally much cheaper than creating a new PostgreSQL container for every test.

Testcontainers supports static containers that can be shared across test methods. (⁠[java.testcontainers.org](https://java.testcontainers.org/test_framework_integration/junit_5/?utm_source=chatgpt.com))

Spring Boot’s `@ServiceConnection` can continue providing the container’s connection details to the application.  

So:

```text
Container lifecycle
        ≠
Test data lifecycle
```

---

# **4. A useful test lifecycle**

For ProjectHub, think:

```text
Start PostgreSQL
      ↓
Run Flyway
      ↓
Test begins
      ↓
Insert fixture
      ↓
Execute request
      ↓
Assert result
      ↓
Clean/reset data
      ↓
Next test
```

The database schema remains.

The test data changes.

---

# **5. What is a test fixture?**

A **fixture** is the known state required by a test.

For example:

```text
Alice
 └── OWNER of Project 7

Bob
 └── MEMBER of Project 7

Post 42
 └── authored by Bob
 └── belongs to Project 7
```

That’s a fixture for:

“Project owner can delete another member’s post.”

---

# **6. Don’t create giant fixtures**

A common beginner mistake is creating:

```text
10 users
20 projects
100 posts
50 memberships
```

before every test.

Then the test itself becomes difficult to understand.

Instead:

Create the smallest dataset necessary to prove the behavior.

For our deletion test:

```text
Alice
Bob
Project 7
Alice → OWNER
Bob → MEMBER
Post 42 → Bob
```

That’s enough.

---

# **7. A fixture factory**

As the project grows, we’ll have repetitive setup.

You might create a helper:

```java
public class ProjectHubFixtures {

    public User createUser(String username) {
        // ...
    }

    public Project createProject(String name) {
        // ...
    }

    public Post createPost(
            User author,
            Project project) {
        // ...
    }
}
```

Then a test becomes conceptually:

```java
User alice = fixtures.user("alice");
User bob = fixtures.user("bob");

Project project = fixtures.project("Project 7");

fixtures.owner(alice, project);
fixtures.member(bob, project);

Post post = fixtures.post(bob, project);
```

The test now describes the **scenario**, rather than drowning in persistence details.

---

# **8. Be careful with fixture abstractions**

Don’t create a giant:

```java
ProjectHubTestUtils
```

with 100 methods.

That’s just moving complexity somewhere else.

A good fixture API should make common scenarios easy:

```text
user()
project()
owner()
member()
post()
```

while unusual situations can still be created explicitly.

---

# **9. Test the authorization matrix**

Now let’s build something useful.

Our deletion rule is:

```text
posts.delete
AND
(
    owns post
    OR
    project owner
)
```

We can create a matrix:

|**Permission**|**Owns Post**|**Project Role**|**Expected**|
|---|---|---|---|
|yes|yes|MEMBER|204|
|yes|no|OWNER|204|
|yes|no|MEMBER|403|
|no|yes|OWNER|403|
|no|no|OWNER|403|
|no|no|MEMBER|403|

This is much better than testing random combinations.

We’re explicitly testing the **policy boundaries**.

---

# **10. Why boundary testing matters**

Consider this bug:

```java
return isOwner || isProjectOwner;
```

Looks correct.

But perhaps someone accidentally forgot:

```text
posts.delete
```

Then someone with:

```text
posts.read
```

might delete posts.

Our matrix catches it.

For example:

```text
permission = no
owner = yes
```

must still produce:

```text
403
```

That’s why security tests should test combinations, not just happy paths.

---

# **11. The “deny by default” principle**

This is one of the most important security principles.

If the policy doesn’t recognize a valid reason to allow an operation:

```text
DENY
```

For example:

```text
unknown project role
unknown membership
missing post
inactive membership
missing permission
```

shouldn’t accidentally fall through to:

```text
ALLOW
```

Conceptually:

```java
if (hasPermission && validRelationship) {
    return true;
}

return false;
```

not:

```java
if (someSpecialCase) {
    return false;
}

return true;
```

The latter is much easier to get wrong.

---

# **12. Test the negative cases aggressively**

For ordinary application features, developers often focus on:

```text
valid request → success
```

For security, you should spend substantial attention on:

```text
invalid authorization → denied
```

For ProjectHub:

```text
anonymous
wrong permission
wrong project
wrong membership
wrong role
wrong owner
revoked user
expired token
revoked refresh token
```

Security bugs frequently live in those boundaries.

---

# **13. Authentication and authorization should be tested separately**

Suppose Alice has:

```text
posts.delete
```

and the request gets:

```text
403
```

There are two very different possibilities:

### **Authentication problem**

Spring doesn’t recognize Alice correctly.

### **Authorization problem**

Spring knows Alice but correctly rejects the operation.

Your tests should make that distinction clear.

For example:

```text
No JWT
    → 401

Valid JWT + wrong authority
    → 403

Valid JWT + authority + failed resource policy
    → 403

Valid JWT + authority + policy passes
    → 204
```

That’s a very useful mental model.

---

# **14. Testing JWT mapping separately**

Remember our JWT contains:

```json
{
  "sub": "alice",
  "authorities": [
    "posts.read",
    "posts.delete"
  ]
}
```

We need a test that verifies:

```text
JWT claim
   ↓
JwtGrantedAuthoritiesConverter
   ↓
posts.delete
   ↓
GrantedAuthority
```

Then our authorization tests can assume:

```text
posts.delete
```

already exists.

This is separation of concerns.

---

# **15. Don’t make every test a full end-to-end test**

Imagine 300 tests.

If every test does:

```text
JWT generation
→ RSA signing
→ JWT decoding
→ database
→ HTTP
→ controller
→ service
→ repository
```

your test suite becomes slow.

Instead:

```text
Many unit tests
        ↓
Some Spring integration tests
        ↓
Some HTTP/security integration tests
        ↓
A smaller number of full end-to-end tests
```

This gives you both speed and confidence.

---

# **16. A practical ProjectHub test pyramid**

I’d aim for something like:

```text
                    E2E
                  /     \
                /         \
          HTTP integration
             /         \
           /             \
       Service / Security
        /                 \
      /                     \
    Unit / Policy / Domain
```

At the bottom:

```text
fast
many
isolated
```

At the top:

```text
slow
fewer
realistic
```

---

# **17. Database cleanup strategies**

There are several approaches.

### **Transaction rollback**

Useful when the operations being tested participate in the same transactional model.

### **Delete test data**

Explicit cleanup:

```text
DELETE posts
DELETE memberships
DELETE projects
DELETE users
```

Ordering matters because of foreign keys.

### **Recreate schema/database**

Very isolated, but potentially expensive.

### **Truncate tables**

Fast for many relational test suites, but requires care around foreign keys and sequences.

### **Dedicated fixture/schema tools**

Useful when the test suite becomes large.

For now, I recommend learning the concepts rather than building a complicated cleanup framework.

---

# **18. Don’t disable foreign keys just to make cleanup easy**

You might encounter advice like:

```text
disable constraints
delete everything
re-enable constraints
```

Avoid making that your normal strategy.

Foreign keys are valuable because they expose invalid test data.

Your tests should operate under constraints similar to production.

---

# **19. Test the real authorization queries**

Suppose your repository has:

```java
boolean existsByProjectIdAndUsernameAndRole(...)
```

A unit test can say:

```java
when(repository.exists(...))
    .thenReturn(true);
```

But it doesn’t prove your actual JPA query is correct.

An integration test does:

```text
real entity
   ↓
real repository
   ↓
real Hibernate
   ↓
real PostgreSQL
   ↓
real result
```

That’s why we want both.

---

# **20. Integration testing catches mapping problems**

Imagine:

```java
@ManyToOne
@JoinColumn(name = "project_id")
private Project project;
```

but your migration accidentally creates:

```sql
project_ref
```

A pure unit test might happily pass.

A real integration test will fail.

That’s good.

The test has discovered that:

```text
Java model
≠
database schema
```

before production does.

---

# **21. This is why Flyway + Testcontainers is powerful**

Our architecture now looks like:

```text
Testcontainers
      ↓
PostgreSQL
      ↓
Flyway migrations
      ↓
JPA mappings
      ↓
Repositories
      ↓
Services
      ↓
Security policies
      ↓
HTTP
```

You are testing a very large portion of the actual application.

And you’re doing it with infrastructure that can be reproduced locally and in CI.

---

# **22. A realistic test class**

Conceptually, we’re heading toward:

```java
@SpringBootTest
@AutoConfigureMockMvc
@Testcontainers
class PostAuthorizationIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:18");

    @Autowired
    MockMvc mvc;

    @Autowired
    UserRepository userRepository;

    @Autowired
    ProjectRepository projectRepository;

    @Autowired
    ProjectMembershipRepository membershipRepository;

    @Autowired
    PostRepository postRepository;

    @Test
    void projectOwnerCanDeleteAnotherUsersPost()
            throws Exception {

        // Arrange

        // Act

        // Assert
    }
}
```

Don’t worry about filling this in yet.

The important part is understanding the architecture.

---

# **23. One correction from our earlier lesson**

We previously used examples like:

```java
new PostgreSQLContainer<>("postgres:18")
```

Don’t treat the image version in an example as a permanent recommendation.

The important concept is:

```text
use a PostgreSQL version compatible with
your project's production environment
```

Your test database should resemble production rather than arbitrarily using whatever version happens to be newest.

Spring Boot’s Testcontainers integration supports service connections for containerized services, with connection details automatically supplied to auto-configuration.  

---

# **24. We’re now leaving the “security-only” world**

At this point we’ve covered a substantial security architecture:

```text
Authentication
    ↓
Password hashing
    ↓
UserDetails
    ↓
Roles
    ↓
Permissions
    ↓
Login
    ↓
JWT
    ↓
Refresh tokens
    ↓
Revocation
    ↓
Resource authorization
    ↓
Project-scoped authorization
    ↓
Security testing
    ↓
Integration testing
```

That’s a major milestone.

The next phase is **production readiness**.

And the first concept there is extremely important:

# **Lesson 29 — Production Configuration & Profiles**

We’ll learn how to separate:

```text
local development
test
staging
production
```

without ending up with:

```text
if (production) {
   ...
} else if (test) {
   ...
}
```

everywhere.

We’ll cover:

- Spring profiles
- `application.yml` vs `application-{profile}.yml`
- environment variables
- secrets
- configuration binding
- database configuration
- JWT keys
- externalized configuration
- what should **never** be committed to Git
- configuration validation at startup
- why production configuration should fail fast

Spring Boot’s current stable documentation is now on the 4.1.x line, and its observability stack uses Micrometer Observation for metrics/traces, which we’ll get to after configuration.