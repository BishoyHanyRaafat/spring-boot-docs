---
title: "Lesson 81: Spring Integration Tests"
sidebar_position: 81
---

We’ve covered unit tests. Now let’s move one level up.

A unit test asks:

**Does this Java class behave correctly?**

An integration test asks:

**Do these Spring components actually work together?**

Spring Boot’s testing support is designed for both approaches, and `spring-boot-starter-test` includes Spring Test, JUnit, AssertJ, Mockito, and other testing tools.  

---

## **1. The difference**

### **Unit test**

```text
PostService
    ↓
Mockito mock
PostRepository
```

No Spring.

Very fast.

### **Integration test**

```text
Spring ApplicationContext
        ↓
Controller
        ↓
Service
        ↓
Repository
        ↓
Database / test infrastructure
```

Now we’re testing actual wiring and framework behavior.

---

# 

# **2.**

**`@SpringBootTest`**

The basic integration-test annotation is:

```java
@SpringBootTest
class PostIntegrationTest {
}
```

It tells Spring Boot to create the application context for the test.

So if your application normally has:

```text
PostController
     ↓
PostService
     ↓
PostRepository
```

Spring creates those beans just as it does when the application starts.

That’s extremely useful for catching things such as:

- missing beans
- incorrect dependency injection
- broken configuration
- incorrect Spring annotations
- components that don’t work together

Spring’s own documentation specifically describes `@SpringBootTest` as the way to move from isolated unit testing toward integration testing with an `ApplicationContext`.  

---

# **3. But don’t use it for everything**

Imagine you have 500 service tests.

If every test starts a whole Spring context, you’re making your test suite unnecessarily expensive.

Instead:

```text
                    Tests
                      │
          ┌───────────┴───────────┐
          │                       │
       Unit tests             Integration
          │                       │
      no Spring              Spring context
      Mockito                  real wiring
      very fast                slower
```

That’s why we use different levels of testing.

---

# **4. Controller testing**

There’s another extremely useful tool:

```java
@WebMvcTest
```

This focuses on the MVC/web layer instead of loading the entire application.

For example:

```text
@WebMvcTest
     ↓
Controller
     ↓
Mock Service
```

Spring Boot automatically configures `MockMvc` for this kind of test.  

So we can test:

```http
POST /posts
```

without needing:

- PostgreSQL
- Kafka
- RabbitMQ
- the entire application

---

# 

# 

# **5. What is**

**`MockMvc`**

**?**

This is an important concept.

Normally:

```text
HTTP client
    ↓
Tomcat
    ↓
Spring MVC
    ↓
Controller
```

With MockMvc:

```text
Mock HTTP request
       ↓
Spring MVC
       ↓
Controller
       ↓
Mock HTTP response
```

There isn’t a real network request or running servlet server.

But Spring MVC still processes the request.

That’s why it’s useful for controller tests.  

---

# **6. Example**

Suppose our controller is:

```java
@RestController
@RequestMapping("/posts")
public class PostController {

    private final PostService service;

    public PostController(PostService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public PostResponse getPost(@PathVariable Long id) {
        return service.getPost(id);
    }
}
```

We could test:

```text
GET /posts/42
```

and verify:

```text
HTTP 200
```

plus:

```json
{
  "id": 42,
  "title": "Hello"
}
```

without touching the database.

---

# **7. The testing layers we’re going to use**

For ProjectHub, we’ll eventually have:

```text
                     End-to-end
                         ▲
                         │
                ┌────────┴────────┐
                │                 │
          Integration        Integration
          PostgreSQL            Kafka
                ▲                 ▲
                │                 │
             Web/API          Messaging
                ▲
                │
           Unit tests
```

More concretely:

### **Unit**

```text
PostServiceTest
AuthorizationServiceTest
OutboxServiceTest
```

### **Web slice**

```text
PostControllerTest
AuthControllerTest
```

### **Database integration**

```text
PostRepositoryTest
PostTransactionTest
```

### **Full integration**

```text
API
 ↓
Service
 ↓
PostgreSQL
```

### **Messaging integration**

```text
Outbox
 ↓
Kafka
 ↓
Consumer
```

And eventually:

```text
Testcontainers
```

to run real PostgreSQL/Kafka containers during tests. Testcontainers is specifically designed to run real backend services in containers as part of integration tests.  

---

# **8. One important testing principle**

Don’t test Spring itself.

Bad:

```text
"Does @Service create a bean?"
```

unless you’re specifically testing application configuration.

Instead test your behavior:

```text
"Does creating a post save the correct post?"
```

or:

```text
"Does a user without posts.delete receive 403?"
```

or:

```text
"Does deleting a post create the correct outbox event?"
```

That’s where tests provide real value.

---

# **Exercise 81**

Let’s make this practical.

Take one of your existing ProjectHub controllers, for example:

```text
PostController
```

and create:

```java
@WebMvcTest(PostController.class)
class PostControllerTest {
}
```

Then we’ll test three things:

```text
GET /posts/{id}
       ↓
200 OK
```

```text
GET /posts/{id}
       ↓
post doesn't exist
       ↓
404
```

and later:

```text
POST /posts
       ↓
invalid request
       ↓
400
```

**Don’t implement those three yet if you want to keep following the course.**

Next we’ll build the first `@WebMvcTest` together, including `MockMvc`, Mockito, JSON, validation, and eventually Spring Security.

After that we’ll move into the really important part:

**real PostgreSQL integration tests with Testcontainers.**