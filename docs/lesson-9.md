---
title: Lesson 9: Error Handling with @ControllerAdvice
sidebar_position: 9
---



So far, our API handles the **happy path**:

```text
Request
  ↓
Controller
  ↓
Service
  ↓
Response
```

Real applications also have:

```text
Post doesn't exist
Invalid input
User already exists
Not authorized
Database failure
Unexpected exception
```

We need a consistent way to turn those failures into useful HTTP responses.

---

# **1. The bad approach**

Imagine every controller does this:

```java
@GetMapping("/{id}")
public ResponseEntity<PostResponse> getPost(
        @PathVariable Long id
) {
    try {
        return ResponseEntity.ok(
                postService.getPost(id)
        );
    } catch (PostNotFoundException e) {
        return ResponseEntity.notFound().build();
    }
}
```

Then another controller:

```java
@GetMapping("/{id}")
public ResponseEntity<UserResponse> getUser(
        @PathVariable Long id
) {
    try {
        // ...
    } catch (UserNotFoundException e) {
        // ...
    }
}
```

And another.

Soon every controller contains error-handling code.

That’s not what we want.

---

# **2. Centralized exception handling**

Spring gives us:

```java
@RestControllerAdvice
```

Think of it as:

**A central place for handling exceptions thrown by your controllers.**

Conceptually:

```text
                    Controllers
                 /      |       \
                /       |        \
               ↓        ↓         ↓
          Controller Controller Controller
               \        |        /
                \       |       /
                 ↓      ↓      ↓
                 Exception
                      │
                      ▼
             @RestControllerAdvice
                      │
                      ▼
                HTTP response
```

This is a very useful separation.

---

# **3. Create an exception**

Suppose a post doesn’t exist.

Create:

```java
public class PostNotFoundException extends RuntimeException {

    public PostNotFoundException(Long id) {
        super("Post not found: " + id);
    }
}
```

Now our service can say:

```java
public PostResponse getPost(Long id) {

    // later we'll query the database

    throw new PostNotFoundException(id);
}
```

We’re deliberately throwing it for now.

---

# **4. Handle it centrally**

Create:

```java
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(PostNotFoundException.class)
    public ResponseEntity<String> handlePostNotFound(
            PostNotFoundException exception
    ) {
        return ResponseEntity
                .status(HttpStatus.NOT_FOUND)
                .body(exception.getMessage());
    }
}
```

Now when:

```java
postService.getPost(42);
```

throws:

```text
PostNotFoundException
```

Spring finds:

```java
@ExceptionHandler(PostNotFoundException.class)
```

and calls it.

The client receives:

```text
404 Not Found
```

instead of an unhandled exception.

---

# **5. The flow**

This is the important part:

```text
GET /posts/42
      ↓
PostController
      ↓
PostService
      ↓
PostNotFoundException
      ↓
@RestControllerAdvice
      ↓
@ExceptionHandler
      ↓
404 Not Found
```

The controller doesn’t need:

```java
try/catch
```

everywhere.

---

# **6. Don’t return random strings**

This:

```java
.body(exception.getMessage());
```

works, but production APIs usually want a consistent JSON error format.

For example:

```json
{
  "status": 404,
  "message": "Post not found",
  "path": "/posts/42"
}
```

Let’s create a proper response object.

---

# **7. Error response DTO**

```java
public record ErrorResponse(
        int status,
        String message,
        String path
) {
}
```

Then:

```java
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(PostNotFoundException.class)
    public ResponseEntity<ErrorResponse> handlePostNotFound(
            PostNotFoundException exception,
            HttpServletRequest request
    ) {

        ErrorResponse response = new ErrorResponse(
                404,
                exception.getMessage(),
                request.getRequestURI()
        );

        return ResponseEntity
                .status(HttpStatus.NOT_FOUND)
                .body(response);
    }
}
```

Now the client receives structured JSON.

---

# **8. Why the error DTO matters**

Imagine your frontend talks to your backend.

It shouldn’t have to guess:

```text
Sometimes the error is a string.
Sometimes it's JSON.
Sometimes it's HTML.
Sometimes it's some framework error.
```

Instead:

```text
All application errors
        ↓
Consistent format
        ↓
Client knows how to handle them
```

That’s part of designing a good API contract.

---

# **9. Multiple exceptions**

Our handler can deal with many exceptions:

```java
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(PostNotFoundException.class)
    public ResponseEntity<ErrorResponse> handlePostNotFound(...) {
        ...
    }

    @ExceptionHandler(UserNotFoundException.class)
    public ResponseEntity<ErrorResponse> handleUserNotFound(...) {
        ...
    }

    @ExceptionHandler(PostAlreadyExistsException.class)
    public ResponseEntity<ErrorResponse> handleConflict(...) {
        ...
    }
}
```

Each exception can map to an appropriate HTTP status.

For example:

```text
PostNotFoundException
        ↓
404 Not Found

UserAlreadyExistsException
        ↓
409 Conflict
```

---


# **10. `404` vs `400` vs`409`

These distinctions are important.

### **`400 Bad Request`**

The request itself is invalid.

Example:

```json
{
  "title": ""
}
```

when title is required.

---

### **`404 Not Found`**

The requested resource doesn’t exist.

```http
GET /posts/999999
```

when post `999999` doesn’t exist.

---

### **`409 Conflict`**

The request conflicts with the current state.

For example:

```http
POST /users
```

with:

```json
{
  "email": "already@exists.com"
}
```

when that email is already registered.

---

# **11. Validation errors**

Remember our previous lesson:

```java
@PostMapping
public ResponseEntity<PostResponse> createPost(
        @Valid @RequestBody CreatePostRequest request
) {
    ...
}
```

Suppose:

```json
{
  "title": "",
  "content": ""
}
```

is submitted.

Validation fails before your controller method executes.

Spring raises a validation-related exception.

We can handle that centrally too.

The exact exception types can vary depending on where validation occurs and the Spring MVC path involved, so don’t build your application around memorizing one class name. The important architectural idea is:

```text
Validation failure
        ↓
Exception
        ↓
Global handler
        ↓
400 response
```

---

# **12. Validation error response**

We could return something like:

```json
{
  "status": 400,
  "message": "Validation failed",
  "errors": {
    "title": [
      "must not be blank"
    ],
    "content": [
      "must not be blank"
    ]
  }
}
```

We could model this with:

```java
public record ValidationErrorResponse(
        int status,
        String message,
        Map<String, List<String>> errors
) {
}
```

Then our API has a predictable structure.

---

# **13. One important design decision**

Should every exception be exposed to the client?

**No.**

Suppose the database throws:

```text
SQLException
```

You probably don’t want to send:

```json
{
  "message": "ERROR: duplicate key violates constraint..."
}
```

or worse:

```json
{
  "message": "password authentication failed for user postgres"
}
```

That’s internal implementation detail.

Instead, the API might return:

```json
{
  "status": 500,
  "message": "An unexpected error occurred"
}
```

while the server logs the real exception.

---

# **14. Don’t blindly catch everything**

You might see:

```java
@ExceptionHandler(Exception.class)
public ResponseEntity<?> handleEverything(Exception e) {
    ...
}
```

A catch-all handler can be useful as a final safety net.

But don’t use it as an excuse to hide every programming bug.

For example:

```java
NullPointerException
```

could indicate a bug in your code.

The client shouldn’t see the stack trace, but developers absolutely need the exception logged.

So:

```text
Client
  ↓
Safe generic error

Developer
  ↓
Detailed logs / stack trace
```

Those are two different audiences.

---

# **15. A cleaner error model**

Our API can eventually standardize around:

```java
public record ApiError(
        int status,
        String code,
        String message,
        String path,
        Instant timestamp
) {
}
```

For example:

```json
{
  "status": 404,
  "code": "POST_NOT_FOUND",
  "message": "Post not found",
  "path": "/posts/42",
  "timestamp": "2026-09-30T20:45:00Z"
}
```

The `code` is particularly useful.

Your frontend can rely on:

```text
POST_NOT_FOUND
```

instead of trying to interpret human-readable text.

---

# **16. Exception hierarchy**

You can also design your application exceptions carefully.

For example:

```text
RuntimeException
      │
      └── ApiException
             │
             ├── PostNotFoundException
             ├── UserNotFoundException
             ├── UserAlreadyExistsException
             └── ProjectNotFoundException
```

But don’t create huge exception hierarchies just for the sake of architecture.

Start simple.

---

# **17. Where should exceptions be thrown?**

Generally, exceptions representing application/business outcomes can originate in the service layer.

For example:

```java
public PostResponse getPost(Long id) {

    Post post = repository.findById(id)
            .orElseThrow(() ->
                    new PostNotFoundException(id)
            );

    return mapper.toResponse(post);
}
```

The service says:

“This post doesn’t exist.”

It doesn’t decide how that becomes HTTP `404`.

That’s the responsibility of the HTTP layer.

So:

```text
Service
   ↓
PostNotFoundException
   ↓
HTTP exception handler
   ↓
404
```

This separation is very valuable.

---

# **18. Why this architecture scales**

Later we’ll have:

```text
Security
   ↓
Controller
   ↓
Validation
   ↓
Service
   ↓
Repository
```

Each layer can communicate failures without becoming tightly coupled to HTTP.

For example, your service shouldn’t have to do:

```java
return ResponseEntity
        .status(404)
        .body(...);
```

That would couple your business logic to HTTP.

Instead:

```java
throw new PostNotFoundException(id);
```

Then the web layer decides:

```text
PostNotFoundException
        ↓
HTTP 404
```

That’s a much cleaner boundary.

---

# **19. The complete ProjectHub flow**

We’re now at:

```text
                    HTTP Request
                         │
                         ▼
                    Security
                         │
                         ▼
                    Controller
                         │
                         ▼
                    Validation
                         │
                    ┌────┴────┐
                    │         │
                  invalid    valid
                    │         │
                    ▼         ▼
                   400      Service
                              │
                       ┌──────┴──────┐
                       │             │
                    success       exception
                       │             │
                       ▼             ▼
                   Response    @ControllerAdvice
                                     │
                                     ▼
                                Error response
```

We’re building a real backend architecture now.

---

# **20. One more modern Spring detail**

Spring Framework also provides a standardized error representation called **`ProblemDetail`**, based on RFC 9457.

Instead of inventing everything ourselves, we can eventually use:

```java
ProblemDetail
```

for HTTP API errors.

For example, conceptually:

```java
ProblemDetail problem =
        ProblemDetail.forStatus(HttpStatus.NOT_FOUND);

problem.setTitle("Post not found");
problem.setDetail("No post exists with id 42");
```

This is worth knowing because modern Spring applications can use `ProblemDetail` rather than inventing a completely custom error format.

We won’t switch the entire course to it yet; I want you to first understand the underlying exception-handling architecture.

---

# **🧠 The most important lesson**

Don’t think:

“`@ControllerAdvice` is just a convenient error handler.”

Think:

**It creates a boundary between application exceptions and HTTP responses.**

That distinction is important.

Your service knows:

```text
PostNotFoundException
```

Your HTTP layer knows:

```text
404 Not Found
```

The two don’t need to know about each other’s implementation details.

---

