---
title: Lesson 85: Real PostgreSQL with Testcontainers
sidebar_position: 85
---

This is the last major database-testing concept we need. We’ll keep it practical.

Spring Boot currently supports Testcontainers through `@ServiceConnection`, which can automatically provide connection details from a container to the application. PostgreSQL containers are supported for JDBC/R2DBC connections.  

## **1. The goal**

Instead of:

```text
Test
 ↓
Mock Repository
```

or:

```text
Test
 ↓
H2
```

we want:

```text
JUnit
  ↓
Spring Boot
  ↓
JPA / Hibernate
  ↓
REAL PostgreSQL
  ↑
Docker/Testcontainers
```

That gives us much higher confidence that our persistence code works against the database we actually use.

---

## **2. Dependencies**

With Spring Boot, you’ll generally have the normal test starter plus Testcontainers/PostgreSQL test support.

Conceptually:

```text
spring-boot-starter-test
testcontainers-postgresql
spring-boot-testcontainers
```

The exact dependency coordinates depend on your Boot version/build setup, so use your Boot-managed dependency versions rather than manually mixing versions.

---

## **3. The modern Spring Boot approach**

The nice part is `@ServiceConnection`.

Conceptually:

```java
@Testcontainers
@SpringBootTest
class PostRepositoryIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:18");

}
```

The important pieces are:

```text
@Testcontainers
    ↓
Testcontainers manages lifecycle

@Container
    ↓
This is the PostgreSQL container

@ServiceConnection
    ↓
Spring Boot automatically gets connection information
```

Spring Boot’s service-connection mechanism means you don’t normally have to manually copy the dynamically assigned container URL, username, and password into `spring.datasource.*` properties.  

---

# **4. Then the test becomes surprisingly simple**

For example:

```java
@Test
void shouldFindPostsByProject() {

    Post first = new Post(...);
    Post second = new Post(...);

    repository.save(first);
    repository.save(second);

    List<Post> posts =
        repository.findByProjectId(projectId);

    assertThat(posts)
        .hasSize(2);
}
```

The important thing isn’t the syntax.

It’s this:

```text
repository.save()
       ↓
Hibernate
       ↓
JDBC
       ↓
PostgreSQL container
```

We’re testing the actual persistence stack.

---

# **5. Why this catches real bugs**

Suppose your query works against an in-memory database but fails against PostgreSQL.

A Testcontainers test catches it.

Suppose a migration creates:

```sql
UNIQUE (project_id, title)
```

and your application accidentally tries to insert duplicates.

A real PostgreSQL test catches it.

Suppose your JPA relationship is wrong.

A real database integration test can catch that too.

That’s why these tests are much more valuable than pretending a mocked repository is a database.

---

# **6. Flyway makes this even better**

Remember our Flyway lessons.

Ideally the integration test should start with:

```text
PostgreSQL container
       ↓
Flyway migrations
       ↓
real schema
       ↓
JPA
       ↓
test
```

That means your test isn’t secretly creating a different database schema from production.

You’re testing the **same migration-driven schema**.

This is a huge advantage.

---

# **7. The complete database testing strategy**

At this point:

```text
Unit
  ↓
Mockito
```

tests business logic.

```text
@DataJpaTest
  ↓
JPA + repository
```

tests persistence behavior.

```text
Testcontainers
  ↓
real PostgreSQL
```

tests the real database integration.

And:

```text
@SpringBootTest
  ↓
whole application
```

tests the components working together.

---

# **8. Don’t turn every test into Testcontainers**

This is important.

You don’t want:

```text
500 tests
    ↓
500 PostgreSQL containers
```

Instead, use layers:

```text
Many
 ↓
Unit tests

Some
 ↓
Web/JPA tests

Fewer
 ↓
Full integration tests

Very few
 ↓
End-to-end tests
```

The goal isn’t maximum realism everywhere.

The goal is **the cheapest test that gives you sufficient confidence**.

---

# **9. Our final testing architecture**

```text
                 ProjectHub Tests
                       │
        ┌──────────────┼───────────────┐
        ▼              ▼               ▼
      Unit            Web             JPA
   JUnit/Mockito    MockMvc       @DataJpaTest
        │              │               │
        │              │          PostgreSQL
        │              │               │
        └──────────────┼───────────────┘
                       ▼
                Integration
                @SpringBootTest
                       │
             ┌─────────┼─────────┐
             ▼         ▼         ▼
        PostgreSQL    Kafka    RabbitMQ
             │         │         │
             └─────────┼─────────┘
                       ▼
                 Testcontainers
```

That’s basically the testing foundation we need.

---

# **🚀 We’re moving on**

Rather than doing another five lessons about obscure testing techniques, we’ll finish the testing section with:

**Lesson 86 — Full** **`@SpringBootTest`** **integration test**

We’ll test a real flow:

```text
HTTP request
   ↓
Controller
   ↓
Security
   ↓
Service
   ↓
Transaction
   ↓
PostgreSQL
   ↓
Outbox
```

Then we’ll quickly finish:

```text
87 Kafka/Outbox testing
88 Testing strategy wrap-up
89 Production configuration
90 Logging + observability
91 Performance
92 CI/CD
93 Final ProjectHub production architecture
```

We’re getting close to the end of the series.