---
title: "Lesson 82: Testing the Web Layer with"
sidebar_position: 82
---

**`@WebMvcTest`**

Let’s move quickly through testing and focus on the patterns you’ll actually use.

Spring Boot 4.1.1 provides `@WebMvcTest` specifically for testing MVC controllers. It auto-configures MVC and `MockMvc` while limiting the application slice instead of starting your entire application.  

## **1. What are we testing?**

Suppose:

```text
HTTP request
    ↓
PostController
    ↓
PostService
```

For a controller test, we don’t need:

```text
PostgreSQL
Kafka
RabbitMQ
```

We replace the service with a mock:

```text
Mock HTTP request
       ↓
PostController
       ↓
Mockito mock
   PostService
```

That lets us concentrate specifically on:

- URL mapping
- request parameters
- JSON serialization
- HTTP status codes
- validation
- controller error handling

---

## 

## **2.**

**`MockMvc`**

`MockMvc` lets us perform Spring MVC requests without starting a real HTTP server. It still exercises Spring MVC request handling.  

Conceptually:

```java
mockMvc.perform(
    get("/posts/42")
)
```

Then:

```java
.andExpect(status().isOk());
```

So we’re effectively saying:

Pretend a client sent `GET /posts/42`, then verify the response.

---

# **3. Example**

Imagine:

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

The test structure becomes:

```java
@WebMvcTest(PostController.class)
class PostControllerTest {

    // mock PostService

    // inject MockMvc

    @Test
    void shouldGetPost() throws Exception {
        // arrange

        // act

        // assert
    }
}
```

In current Spring Boot testing APIs, `@MockitoBean` is the appropriate mechanism for supplying mocked collaborators to the test slice.  

---

# **4. The three-part test**

Think:

```text
ARRANGE
   ↓
ACT
   ↓
ASSERT
```

For example:

```text
ARRANGE
service.getPost(42) → PostResponse

ACT
GET /posts/42

ASSERT
200 OK
JSON contains id=42
```

The controller isn’t responsible for actually retrieving anything.

That’s the service’s job.

---

# **5. Why this matters**

Suppose your controller accidentally changes:

```java
@GetMapping("/post/{id}")
```

instead of:

```java
@GetMapping("/{id}")
```

Your test catches it immediately.

Or perhaps the controller returns:

```text
201 Created
```

instead of:

```text
200 OK
```

Again, the test catches it.

Or validation accidentally accepts:

```json
{
    "title": ""
}
```

when it shouldn’t.

The test catches that too.

---

# **6. Security makes this especially useful**

This becomes **very valuable for ProjectHub**.

We can test:

```text
anonymous
    ↓
GET /posts
    ↓
401
```

Then:

```text
authenticated user
    ↓
GET /posts
    ↓
200
```

And:

```text
user WITHOUT posts.delete
    ↓
DELETE /posts/42
    ↓
403
```

And:

```text
user WITH posts.delete
    ↓
DELETE /posts/42
    ↓
success
```

Spring Security provides dedicated MockMvc support for supplying users and testing authentication/authorization.  

For example, Spring Security can run a request as a mocked user:

```java
mockMvc.perform(
    get("/posts")
        .with(user("alice").roles("USER"))
);
```

or:

```java
@WithMockUser(roles = "ADMIN")
```

This is exactly what we’ll use to test the permission system we built earlier.

---

# 

# 

# 

# 

# **7. Important: test**

**`401`**

**and**

**`403`**

**separately**

These are different.

```text
401 Unauthorized
    ↓
You haven't authenticated.

403 Forbidden
    ↓
You are authenticated,
but aren't allowed to perform this action.
```

So our security tests should explicitly cover both.

---

# **8. CSRF note**

If your application uses CSRF protection, Spring Security’s MockMvc support provides a `csrf()` request post-processor for non-safe methods such as POST/PUT/DELETE.  

For example:

```java
mockMvc.perform(
    post("/posts")
        .with(csrf())
);
```

Whether your JWT/stateless API needs CSRF enabled is a separate architectural decision—we already discussed that when building authentication.

---

# **9. Our testing strategy from here**

We’re going to move quickly:

```text
82  @WebMvcTest + MockMvc        ← NOW
83  Security testing
84  @DataJpaTest
85  Testcontainers + PostgreSQL
86  Full integration tests
87  Kafka / Outbox testing
88  Production testing strategy
```

Then we’ll leave testing and move on to:

```text
89  Production configuration
90  Logging + observability
91  Performance
92  CI/CD
93  Final ProjectHub production build
```

So we’re deliberately **compressing the remaining series** rather than spending dozens of lessons on edge cases.

### **Exercise**

Take one ProjectHub controller and write a `@WebMvcTest` containing:

1. a successful `GET`
2. a `404` case
3. an invalid `POST` returning `400`

Don’t worry about perfection. The goal is to get comfortable with:

```text
@WebMvcTest
@MockitoBean
MockMvc
perform()
andExpect()
```

Then we’ll jump directly into **Lesson 83: testing your Spring Security permission system**.