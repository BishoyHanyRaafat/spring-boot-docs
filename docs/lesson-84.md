---
title: "Lesson 84: Database Integration Tests"
sidebar_position: 84
---

Now we’re moving from:

```text
PostRepository
    ↓
Mockito mock
```

to:

```text
PostRepository
    ↓
real JPA/Hibernate
    ↓
real PostgreSQL
```

This is where you catch bugs that unit tests simply cannot see.

Spring Boot provides `@DataJpaTest` specifically for JPA tests. It configures JPA entities and repositories and, by default, runs each test transactionally and rolls it back afterward.  

---

## 

## **1.**

**`@DataJpaTest`**

Imagine:

```java
@Repository
public interface PostRepository
        extends JpaRepository<Post, Long> {

    List<Post> findByProjectId(Long projectId);
}
```

A repository unit test with Mockito doesn’t really prove that:

```text
findByProjectId()
```

generates the query you intended.

A JPA integration test does.

Conceptually:

```text
@DataJpaTest
      │
      ├── EntityManager
      ├── Hibernate
      ├── Spring Data
      └── PostRepository
              │
              ▼
          PostgreSQL
```

---

# 

# 

# **2. What**

**`@DataJpaTest`**

**gives you**

It focuses the Spring context on persistence-related components rather than loading your entire application. By default, it also uses an embedded database if one is available.  

For ProjectHub, however, we care about PostgreSQL-specific behavior.

Why?

Because this:

```text
H2
```

is not necessarily equivalent to:

```text
PostgreSQL
```

Things such as:

- SQL syntax
- indexes
- constraints
- JSONB
- PostgreSQL-specific types
- transaction behavior
- query plans

can differ.

So eventually we want **real PostgreSQL**.

---

# **3. Testcontainers**

This is where Testcontainers enters.

Instead of requiring every developer or CI server to manually install PostgreSQL:

```text
Developer machine
     ↓
install PostgreSQL
     ↓
configure database
     ↓
hope versions match
```

we can have the test start a PostgreSQL container:

```text
JUnit
  ↓
Testcontainers
  ↓
Docker
  ↓
PostgreSQL
```

Testcontainers is specifically designed to run real services in Docker containers during integration tests.  

That’s extremely useful for backend development.

---

# **4. The resulting test**

Eventually our test looks conceptually like:

```text
@Test
        │
        ▼
PostgreSQL container
        │
        ▼
Spring Data JPA
        │
        ▼
PostRepository
        │
        ▼
real database
```

Now we can test something meaningful:

```text
save Post
   ↓
query Post
   ↓
verify result
```

---

# **5. Transactions become important here**

Remember our previous transaction lessons.

`@DataJpaTest` tests are transactional by default and roll the transaction back after each test.  

So:

```text
Test 1
  INSERT post
  COMMIT? no
  ROLLBACK
       ↓
database clean

Test 2
  INSERT post
  ROLLBACK
       ↓
database clean
```

That’s extremely convenient for isolation.

But there is an important caveat:

**A test transaction isn’t necessarily the same thing as testing your production transaction boundary.**

For example, if your real service does:

```java
@Transactional
public void createPost(...) {
    ...
}
```

we eventually want a full integration test that exercises the service’s transaction rather than relying solely on the transaction created by the test framework.

That’s why we’ll have both:

```text
@DataJpaTest
```

and later:

```text
@SpringBootTest
```

---

# **6. What should we test?**

For a `PostRepository`, don’t test every trivial Spring Data method.

Instead test the things **you wrote or that are easy to get wrong**.

For example:

```text
findByProjectId()
findByAuthorId()
searchByTitle()
custom JPQL
native SQL
unique constraints
relationships
```

A test could conceptually be:

```text
Arrange:
  save 3 posts
    project 1 → post A
    project 1 → post B
    project 2 → post C

Act:
  findByProjectId(1)

Assert:
  A and B returned
  C not returned
```

That’s useful.

---

# **7. Don’t over-test Spring Data**

You don’t need:

```text
@Test
save_shouldCallJpaRepository()
```

That’s testing the framework.

Instead test:

```text
"My custom query returns the correct records."
```

Good tests verify **your behavior**.

---

# **8. The testing stack is becoming clear**

We’re building this:

```text
                 ProjectHub Tests
                       │
       ┌───────────────┼────────────────┐
       │               │                │
       ▼               ▼                ▼
     Unit             Web              JPA
   JUnit/Mockito     MockMvc       @DataJpaTest
       │               │                │
       │               │                ▼
       │               │           PostgreSQL
       │               │                │
       └───────────────┴────────────────┘
                       │
                       ▼
                Full integration
                  @SpringBootTest
```

And then:

```text
PostgreSQL
Kafka
RabbitMQ
```

can all be supplied by Testcontainers when we need real infrastructure. Spring Boot also provides dedicated Testcontainers integration.  

---

# **One important current-version note**

Since we’re using current APIs, Spring Boot **4.1.1 is currently the stable release**; 4.2 is still listed as preview/development in the official documentation.  

Also, in Boot 4, `@DataJpaTest` lives in the dedicated JPA test module, `spring-boot-data-jpa-test`.  

---

## **Next: Lesson 85 — Real PostgreSQL with Testcontainers**

This is the hands-on part:

```text
JUnit
 ↓
Testcontainers
 ↓
PostgreSQL Docker container
 ↓
Spring Boot
 ↓
JPA
 ↓
Repository
```

We’ll configure it once, run a real repository test, and then **move on quickly** rather than spending ten lessons on Testcontainers.