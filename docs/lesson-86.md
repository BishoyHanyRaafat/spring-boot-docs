---
title: "Lesson 86: Full @SpringBootTestntegratioTest"
sidebar_position: 86
---

We’ve tested individual pieces. Now we connect the real application together.

Spring Boot’s `@SpringBootTest` loads the application’s `ApplicationContext`. By default it uses a mock web environment rather than starting a real server, and the context is cached between compatible tests.  

## **1. What we’re testing now**

Instead of:

```text
Controller → mock Service
```

or:

```text
Service → mock Repository
```

we want:

```text
              @SpringBootTest

HTTP
 ↓
Controller
 ↓
Security
 ↓
Service
 ↓
Transaction
 ↓
JPA
 ↓
PostgreSQL
 ↓
Outbox
```

This is where configuration and component wiring get tested together.

---

## **2. Basic structure**

Conceptually:

```java
@SpringBootTest
class PostIntegrationTest {

    @Test
    void shouldCreatePost() {
        // exercise the real application
    }
}
```

If we also want MockMvc:

```java
@SpringBootTest
@AutoConfigureMockMvc
class PostIntegrationTest {
}
```

`@SpringBootTest` does **not** start a real HTTP server by default, but it can work with MockMvc. If we specifically need a real server, `webEnvironment = RANDOM_PORT` starts one on a random port.  

---

# **3. Why this test is different**

Imagine:

```text
POST /posts
```

The request travels through:

```text
MockMvc
   ↓
SecurityFilterChain
   ↓
PostController
   ↓
PostService
   ↓
@Transactional
   ↓
PostRepository
   ↓
PostgreSQL
```

That’s a **real application path**.

You aren’t mocking your own application components.

That means this kind of test can catch:

- missing Spring beans
- incorrect dependency wiring
- security configuration problems
- transaction problems
- JPA mapping problems
- repository problems
- controller/service integration problems

Spring itself recommends moving to `ApplicationContext`-based integration testing when you need to verify components working together.  

---

# **4. Add Testcontainers**

For ProjectHub, combine this with our previous lesson:

```text
@SpringBootTest
       +
Testcontainers
       ↓
real PostgreSQL
```

So:

```text
JUnit
 ↓
Spring Boot
 ↓
PostgreSQL container
```

Now we’re very close to production behavior.

---

# **5. A realistic ProjectHub test**

Imagine the requirement:

A user with `posts.create` can create a post.

Our integration test should eventually verify:

```text
authenticate user
       ↓
POST /posts
       ↓
201 Created
       ↓
Post exists in PostgreSQL
       ↓
Outbox event exists
```

That’s an extremely valuable test.

Notice how much more it verifies than:

```java
verify(repository).save(...)
```

The latter only verifies that a mock was called.

The integration test verifies that the **system actually works**.

---

# **6. But don’t make every test this big**

This distinction is critical:

### **Unit**

```text
Does my business logic work?
```

### **Slice**

```text
Does my controller/repository layer work?
```

### **Integration**

```text
Do my application components work together?
```

### **End-to-end**

```text
Does the system work from the client's perspective?
```

Spring Boot supports focused test slices specifically so you don’t have to load the entire application for every test.  

---

# **7. One final distinction: MockMvc isn’t a real network test**

Even though MockMvc exercises Spring MVC, it doesn’t start a real HTTP server.  

So eventually we might have:

```text
@SpringBootTest
+ MockMvc
```

for most application integration tests.

And a **small number** of:

```text
@SpringBootTest(webEnvironment = RANDOM_PORT)
+ real HTTP client
```

for true end-to-end tests.

We don’t need hundreds of the latter.

---

# **8. Our testing pyramid is now complete**

```text
             E2E
              ▲
              │
        Full integration
              ▲
              │
      ┌───────┴───────┐
      │               │
     Web              JPA
   MockMvc       PostgreSQL
      │               │
      └───────┬───────┘
              ▲
              │
          Unit tests
        JUnit + Mockito
```

That’s enough testing theory.

---

# **Lesson 87 — Testing Kafka and the Outbox**

We’re going to make this one concise.

The critical flow is:

```text
DB transaction
     ↓
Post + Outbox
     ↓
Outbox publisher
     ↓
Kafka
     ↓
Consumer
```

We need to test **each boundary**.

### **Test 1 — Outbox transaction**

```text
create post
   ↓
Post exists
   ↓
Outbox exists
```

Both should be committed together.

### **Test 2 — Publisher**

```text
PENDING outbox
   ↓
Kafka publish
   ↓
PUBLISHED
```

### **Test 3 — Consumer**

```text
Kafka event
   ↓
consumer
   ↓
business change
```

### **Test 4 — Duplicate**

```text
same event twice
       ↓
business action once
```

That’s our idempotency guarantee.

### **Test 5 — Failure**

```text
consumer fails
     ↓
retry
     ↓
DLT
```

For these tests, Testcontainers can provide real Kafka when we want infrastructure-level confidence.

---

# **The key lesson**

Don’t test Kafka itself.

Test **your behavior around Kafka**.

Bad:

“Kafka successfully stores messages.”

Useful:

“When `PostCreated` is consumed, ProjectHub creates the expected notification.”

And:

“When the same `eventId` is delivered twice, the notification is created only once.”

That’s the level of testing that matters.

---

## **Testing phase: DONE ✅**

We’ve now covered:

```text
JUnit
Mockito
@WebMvcTest
MockMvc
Security tests
@DataJpaTest
PostgreSQL
Testcontainers
@SpringBootTest
Kafka/Outbox testing
```

So we’re moving on.

# **Lesson 88 — Production Configuration & Environment Management**

This is our last major phase.

We’ll cover:

```text
application.yaml
      ↓
profiles
      ↓
environment variables
      ↓
secrets
      ↓
Docker
      ↓
Kubernetes
      ↓
CI/CD
```

Then we’ll finish the series with **production architecture, observability, performance, and the final ProjectHub architecture**.