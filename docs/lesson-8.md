---
title: "Lesson 8: DTOs, Validation & Clean API Design"
sidebar_position: 8
---


Now we’re going to fix a common beginner mistake:

**Using the same Java object everywhere.**

In a real backend, your HTTP API, business logic, and database should not all be forced to use the same class.

We’ll introduce **DTOs** and **validation**, then connect them to our ProjectHub API.

---

# **1. What’s a DTO?**

DTO = **Data Transfer Object**.

A DTO is simply an object designed to transfer data between boundaries.

For example:

```java
public record CreatePostRequest(
        String title,
        String content
) {
}
```

This isn’t necessarily a database entity.

It’s specifically:

“The data that my API accepts when creating a post.”

Similarly:

```java
public record PostResponse(
        Long id,
        String title,
        String content
) {
}
```

means:

“The data my API exposes when returning a post.”

So we might have:

```text
HTTP request
      ↓
CreatePostRequest
      ↓
Service
      ↓
Post entity
      ↓
Database

Database
      ↓
Post entity
      ↓
PostResponse
      ↓
HTTP response
```

That’s a very useful separation.

---

# 2. Why not just use `Post` everywhere?**

Imagine our database entity eventually looks like:

```java
@Entity
public class Post {

    private Long id;

    private String title;

    private String content;

    private User author;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;

    private boolean deleted;

    // ...
}
```

Now imagine returning that directly from:

```http
GET /posts/1
```

You might accidentally expose:

```json
{
  "id": 1,
  "title": "...",
  "content": "...",
  "author": {
    "id": 42,
    "email": "..."
  },
  "createdAt": "...",
  "updatedAt": "...",
  "deleted": false
}
```

Maybe you don’t want clients seeing:

```text
deleted
```

Maybe you don’t want to expose the user’s email.

Maybe tomorrow you change the database structure.

Your API shouldn’t necessarily change just because your database changed.

That’s one of the biggest reasons DTOs exist.

---

# **3. Request DTO vs Response DTO**

These are often different.

### **Request**

```java
public record CreatePostRequest(
        String title,
        String content
) {
}
```

### **Response**

```java
public record PostResponse(
        Long id,
        String title,
        String content
) {
}
```

Why different?

Because the client sends:

```text
title
content
```

but the server generates:

```text
id
createdAt
author
```

The client shouldn’t be allowed to send:

```json
{
  "id": 999999,
  "createdAt": "2099-01-01"
}
```

and decide what those values are.

---

# **4. PATCH needs a different mindset**

Suppose we have:

```http
PATCH /posts/42
```

and want to update only the title.

The request might be:

```json
{
  "title": "New title"
}
```

You might create:

```java
public record UpdatePostRequest(
        String title,
        String content
) {
}
```

But now you need to decide what `null` means.

Does:

```json
{
  "title": null
}
```

mean:

```text
Set title to null
```

or:

```text
Don't change title
```

This is one reason partial-update APIs require more thought than simple create requests.

We’ll revisit this when we implement PATCH properly.

---

# **5. Now: validation**

Currently our API accepts:

```json
{
  "title": "",
  "content": ""
}
```

That’s probably not acceptable.

We need rules.

For example:

```text
title:
  required
  3–100 characters

content:
  required
  maximum 10,000 characters
```

Jakarta Bean Validation gives us annotations for these constraints.

---

# **6. Add validation annotations**

Our request DTO can become:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreatePostRequest(

        @NotBlank
        @Size(min = 3, max = 100)
        String title,

        @NotBlank
        @Size(max = 10_000)
        String content

) {
}
```

Now we’ve described the rules directly on the input model.

---

# 7. What does `@NotBlank` mean?

Consider:

```java
@NotBlank
String title
```

It rejects values that are:

```text
null
""
"   "
```

That’s generally more appropriate for text fields than merely:

```java
@NotNull
```

because `@NotNull` allows:

```text
""
"   "
```

---

# 8. What does `@Size` do?

This:

```java
@Size(min = 3, max = 100)
String title
```

means:

```text
minimum length = 3
maximum length = 100
```

So:

```text
"Hi"
```

fails.

While:

```text
"Hello Spring"
```

passes.

---

# **9. Triggering validation**

Now our controller:

```java
@PostMapping
public ResponseEntity<PostResponse> createPost(
        @Valid @RequestBody CreatePostRequest request
) {
    PostResponse response =
            postService.createPost(request);

    return ResponseEntity
            .status(HttpStatus.CREATED)
            .body(response);
}
```

The important part is:

```java
@Valid
```

So the flow becomes:

```text
JSON
 ↓
CreatePostRequest
 ↓
Validation
 ↓
Valid?
 ├── NO → validation error
 │
 └── YES
       ↓
    Controller
       ↓
    Service
```

Spring MVC integrates with Jakarta Bean Validation when validation support is configured.

---

# **10. What happens with invalid JSON?**

Suppose the client sends:

```json
{
  "title": "",
  "content": ""
}
```

Validation detects the violations.

The request should not reach:

```java
postService.createPost(request);
```

That’s exactly what we want.

Why?

Because the service shouldn’t have to repeatedly check basic input rules:

```java
if (title == null) ...
if (title.isBlank()) ...
if (title.length() > 100) ...
```

The validation layer handles these boundary checks.

---

# **11. Dependency**

In a Spring Boot project, you normally add the validation starter.

For Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

This brings in the relevant Jakarta Validation infrastructure.

The exact dependency details can vary with the Spring Boot generation, so use the starter rather than manually assembling validation libraries.

---

# **12. Validation belongs at the boundary**

This is a subtle architectural point.

Imagine:

```text
HTTP
 ↓
Controller
 ↓
Service
```

The HTTP request is an **external input**.

You should validate it when it enters your system.

So:

```text
External world
      ↓
   VALIDATE
      ↓
 Your application
```

But validation isn’t only about controllers.

Your **business rules** belong in the appropriate application/domain layer.

For example:

### **Input validation**

```text
title must not be blank
```

Good candidate for DTO validation.

### **Business rule**

```text
A user cannot delete a post belonging to another user.
```

That’s not merely input validation.

That’s authorization/business logic.

This distinction becomes extremely important once we implement security.

---

# **13. Validation vs authorization**

Don’t mix these up.

### **Validation**

Is this input structurally valid?

Example:

```text
title = ""
```

Invalid.

### **Authorization**

Is this user allowed to perform this operation?

Example:

```text
User A attempts to delete User B's post.
```

The request may be perfectly valid structurally:

```json
{
  "id": 42
}
```

but the operation may not be authorized.

We’ll later have:

```text
Validation
    ↓
Authorization
    ↓
Business logic
```

---

# **14. Validation vs business rules**

Another important distinction.

Suppose:

```text
title must be 3–100 characters
```

That’s a straightforward validation constraint.

But:

```text
A project cannot be archived while it has active deployments.
```

That’s a **business rule**.

Don’t try to solve everything with:

```java
@SomeAnnotation
```

Business rules generally belong in your service/domain logic.

---

# **15. Custom validation**

Sometimes standard annotations aren’t enough.

Suppose ProjectHub has:

```text
username must contain only letters, numbers, '.', '_'
```

You could create a custom validation annotation.

Conceptually:

```java
@ValidUsername
String username
```

with a custom validator behind it.

We’ll cover custom validators later after we’ve learned the standard validation system properly.

---

# **16. Nested DTOs**

DTOs can contain other DTOs.

For example:

```java
public record CreateProjectRequest(
        @NotBlank
        @Size(max = 100)
        String name,

        @Valid
        ProjectSettingsRequest settings
) {
}
```

and:

```java
public record ProjectSettingsRequest(
        @NotNull
        Boolean publicProject
) {
}
```

Notice:

```java
@Valid
ProjectSettingsRequest settings
```

That tells validation to continue into the nested object.

---

# **17. Validation errors**

Eventually, if someone sends:

```json
{
  "title": "",
  "content": ""
}
```

we don’t want to return some ugly framework-generated response and call it done.

We want something predictable.

For example:

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

This leads us to a very important Spring concept:

# **`@ControllerAdvice`**

We’ll properly learn it in the next lesson.

It allows us to centralize exception/error handling instead of writing this in every controller.

---

# **18. A clean ProjectHub structure**

Our project is beginning to look like:

```text
com.projecthub
│
├── ProjectHubApplication
│
├── post
│   ├── PostController
│   ├── PostService
│   ├── Post
│   ├── CreatePostRequest
│   ├── UpdatePostRequest
│   └── PostResponse
│
├── user
│   ├── UserController
│   ├── UserService
│   ├── User
│   └── UserResponse
│
└── ...
```

This is just one possible organization.

Later we’ll discuss **package-by-feature vs package-by-layer**, because that becomes an architectural decision worth understanding.

---

# **19. The complete request flow now**

We have enough pieces to make our pipeline much richer:

```text
                  HTTP Request
                       │
                       ▼
                ┌─────────────┐
                │ Controller  │
                └──────┬──────┘
                       │
                       ▼
                 Deserialize
                       │
                       ▼
                  Validate
                       │
                  ┌────┴────┐
                  │         │
                FAIL       PASS
                  │         │
                  ▼         ▼
                400       Service
                            │
                            ▼
                         Business
                           logic
                            │
                            ▼
                        Repository
```

Later:

```text
HTTP
 ↓
Security
 ↓
Controller
 ↓
Validation
 ↓
Service
 ↓
Transaction
 ↓
Repository
 ↓
Database
```

We’re building this piece by piece.

---

# **20. A complete example**

Here’s what I’d currently consider a reasonable beginner-level endpoint:

```java
public record CreatePostRequest(

        @NotBlank
        @Size(min = 3, max = 100)
        String title,

        @NotBlank
        @Size(max = 10_000)
        String content

) {
}
```

```java
public record PostResponse(
        Long id,
        String title,
        String content
) {
}
```

```java
@RestController
@RequestMapping("/posts")
public class PostController {

    private final PostService postService;

    public PostController(PostService postService) {
        this.postService = postService;
    }

    @PostMapping
    public ResponseEntity<PostResponse> createPost(
            @Valid @RequestBody CreatePostRequest request
    ) {
        PostResponse response =
                postService.createPost(request);

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(response);
    }
}
```

Notice how clean the controller is.

It isn’t doing:

```text
SQL
validation logic
JSON parsing
business rules
database operations
```

It’s coordinating the HTTP boundary.

---

# **🧠 The architectural idea I want you to remember**

There are three different representations:

```text
                External API
                     │
                     ▼
             CreatePostRequest
                     │
                     ▼
                  Service
                     │
                     ▼
                  Post
                     │
                     ▼
                 Database
```

and coming back:

```text
Database
   ↓
Post
   ↓
Service
   ↓
PostResponse
   ↓
JSON
   ↓
Client
```

Don’t think:

“DTOs are just annoying extra classes.”

Think:

**DTOs define the contract between your application and the outside world.**

That distinction becomes incredibly valuable as applications grow.

---
