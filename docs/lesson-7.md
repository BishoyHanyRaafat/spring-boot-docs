---
title: Lesson 7: Building REST APIs with Spring Boot
sidebar_position: 7
---



Now we get to the part where Spring Boot starts feeling like a backend framework.

We’ll learn how this:

```text
HTTP request
     ↓
Spring Boot
     ↓
Controller
     ↓
Service
     ↓
Repository
     ↓
Database
```

actually works.

For now, we’ll stop at the service layer and use in-memory data. We’ll introduce PostgreSQL and JPA later.

---

## **1. What is an HTTP request?**

When a client calls:

```http
GET /users
```

it’s making an HTTP request to your server.

A request contains things like:

```text
HTTP method
URL
Headers
Query parameters
Body
```

For example:

```http
GET /users?page=2&size=20
Authorization: Bearer ...
```

Spring’s job is to take that HTTP request and route it to the appropriate Java method.

---

# **2. The Controller**

You’ve already seen:

```java
@RestController
public class UserController {
}
```

A controller is responsible for handling HTTP requests.

For example:

```java
@RestController
public class UserController {

    @GetMapping("/users")
    public String getUsers() {
        return "users";
    }
}
```

Now:

```http
GET /users
```

gets routed to:

```java
getUsers()
```

The flow is:

```text
GET /users
     ↓
UserController
     ↓
getUsers()
     ↓
"users"
```

---



# 3. Why `@RestController` ?

There are two related annotations:

```java
@Controller
```

and:

```java
@RestController
```

`@RestController` is designed for HTTP APIs where your methods return data, commonly JSON.

Conceptually:

```java
@RestController
```

is equivalent to:

```java
@Controller
@ResponseBody
```

So when you write:

```java
@GetMapping("/users")
public User getUser() {
    return user;
}
```

Spring treats the returned object as the HTTP response body rather than looking for a server-side HTML view.

---

# **4. HTTP methods**

The most important methods for our API are:

|**HTTP method**|**Typical meaning**|
|---|---|
|`GET`|Read|
|`POST`|Create|
|`PUT`|Replace/update|
|`PATCH`|Partially update|
|`DELETE`|Delete|

For example:

```text
GET    /posts
POST   /posts
GET    /posts/42
PATCH  /posts/42
DELETE /posts/42
```

This is the foundation of a REST-style API.

---

# **5. `@GetMapping`**

Simple:

```java
@GetMapping("/posts")
public String getPosts() {
    return "posts";
}
```

Request:

```http
GET /posts
```

calls the method.

---

# 

# **6. `@PostMapping`**

Now suppose we want to create a post:

```java
@PostMapping("/posts")
public String createPost() {
    return "created";
}
```

Request:

```http
POST /posts
```

calls:

```java
createPost()
```

The method is different from:

```http
GET /posts
```

even though the URL is identical.

That’s important.

The combination of:

```text
HTTP method + path
```

determines the endpoint.

---

# **7. Path variables**

Suppose we want:

```http
GET /posts/42
```

where `42` is the post ID.

We can write:

```java
@GetMapping("/posts/{id}")
public String getPost(@PathVariable Long id) {
    return "Post " + id;
}
```

Request:

```http
GET /posts/42
```

produces:

```text
Post 42
```

Spring extracts:

```text
42
```

from the URL and passes it into:

```java
Long id
```

---

# **8. Path variables are part of the resource identity**

Compare:

```text
GET /posts/42
```

with:

```text
GET /posts/43
```

They’re the same endpoint structure, but referring to different resources.

Conceptually:

```text
/posts/{id}
        ↑
   path variable
```

This will become extremely common.

---

# **9. Query parameters**

Now consider:

```http
GET /posts?page=2&size=20
```

These aren’t part of the resource identity.

They’re parameters modifying the request.

You can access them using:

```java
@GetMapping("/posts")
public String getPosts(
        @RequestParam int page,
        @RequestParam int size
) {
    return "page=" + page + ", size=" + size;
}
```

So:

```http
GET /posts?page=2&size=20
```

becomes:

```text
page = 2
size = 20
```

---

# **10. Optional query parameters**

You can provide a default:

```java
@GetMapping("/posts")
public String getPosts(
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size
) {
    return "page=" + page + ", size=" + size;
}
```

Now:

```http
GET /posts
```

means:

```text
page = 0
size = 20
```

while:

```http
GET /posts?page=3&size=50
```

means:

```text
page = 3
size = 50
```

We’ll later build proper pagination around this.

---

# **11. Request bodies**

Here’s where things become more interesting.

Suppose the client wants to create:

```text
Title: Hello Spring
Content: Learning Spring Boot
```

It can send JSON:

```json
{
  "title": "Hello Spring",
  "content": "Learning Spring Boot"
}
```

Spring can convert that JSON into a Java object.

---

# **12. Create a request DTO**

Don’t immediately use your database entity as the request object.

We’ll discuss why later.

For now:

```java
public record CreatePostRequest(
        String title,
        String content
) {
}
```

Then:

```java
@PostMapping("/posts")
public String createPost(
        @RequestBody CreatePostRequest request
) {
    return request.title();
}
```

The client sends:

```json
{
  "title": "Hello Spring",
  "content": "Learning Spring Boot"
}
```

Spring effectively performs:

```text
JSON
 ↓
Jackson
 ↓
CreatePostRequest
 ↓
Controller method
```

Spring Boot’s web stack includes JSON support so that Java objects can be serialized/deserialized for HTTP APIs.

---

# **13. The full request lifecycle**

This is extremely important.

Suppose the client sends:

```http
POST /posts
Content-Type: application/json
```

with:

```json
{
  "title": "Hello",
  "content": "World"
}
```

Conceptually:

```text
Client
  │
  │ HTTP request
  ↓
Embedded server
  │
  ↓
Spring MVC
  │
  ↓
Find matching controller method
  │
  ↓
Deserialize JSON
  │
  ↓
CreatePostRequest
  │
  ↓
Controller
  │
  ↓
Service
  │
  ↓
Repository
  │
  ↓
Database
```

We’ll eventually add:

```text
Security
Validation
Transactions
Exception handling
```

into that pipeline.

---

# **14. Controller → Service**

Here’s where our earlier lessons become important.

Don’t put all your business logic inside the controller.

Bad:

```java
@PostMapping("/posts")
public Post createPost(@RequestBody CreatePostRequest request) {

    // validate everything
    // check permissions
    // create entity
    // save to database
    // send notification
    // etc...

}
```

Instead:

```java
@RestController
@RequestMapping("/posts")
public class PostController {

    private final PostService postService;

    public PostController(PostService postService) {
        this.postService = postService;
    }

    @PostMapping
    public PostResponse createPost(
            @RequestBody CreatePostRequest request
    ) {
        return postService.createPost(request);
    }
}
```

Now:

```text
Controller
   ↓
Service
```

The controller’s job is primarily HTTP concerns.

The service handles application/business logic.

---

# 

# **15. `@RequestMapping`**

Notice:

```java
@RequestMapping("/posts")
public class PostController {
```

Then we can write:

```java
@GetMapping
```

instead of:

```java
@GetMapping("/posts")
```

and:

```java
@PostMapping
```

instead of:

```java
@PostMapping("/posts")
```

So:

```java
@RestController
@RequestMapping("/posts")
public class PostController {

    @GetMapping
    public ... getPosts() {
    }

    @GetMapping("/{id}")
    public ... getPost(@PathVariable Long id) {
    }

    @PostMapping
    public ... createPost(...) {
    }

    @DeleteMapping("/{id}")
    public ... deletePost(@PathVariable Long id) {
    }
}
```

This gives us a clean resource-oriented controller.

---

# **16. Returning objects**

Instead of:

```java
@GetMapping("/{id}")
public String getPost(...) {
    return "hello";
}
```

we can return a Java object:

```java
public record PostResponse(
        Long id,
        String title,
        String content
) {
}
```

Then:

```java
@GetMapping("/{id}")
public PostResponse getPost(@PathVariable Long id) {

    return new PostResponse(
            id,
            "Hello Spring",
            "Learning Spring Boot"
    );
}
```

The client receives JSON roughly like:

```json
{
  "id": 42,
  "title": "Hello Spring",
  "content": "Learning Spring Boot"
}
```

This is one of the major conveniences of Spring Boot’s HTTP stack.

---

# **17. HTTP status codes**

We shouldn’t always return:

```text
200 OK
```

Different operations have different appropriate statuses.

Common ones:

```text
200 OK
201 Created
204 No Content
400 Bad Request
401 Unauthorized
403 Forbidden
404 Not Found
409 Conflict
500 Internal Server Error
```

For example, creating a resource commonly uses:

```text
201 Created
```

Deleting something successfully might use:

```text
204 No Content
```

We’ll learn proper response handling shortly.

---

# 18. `ResponseEntity`**

One way to control the response:

```java
@PostMapping
public ResponseEntity<PostResponse> createPost(
        @RequestBody CreatePostRequest request
) {

    PostResponse response = postService.createPost(request);

    return ResponseEntity
            .status(HttpStatus.CREATED)
            .body(response);
}
```

Now Spring sends:

```text
HTTP/1.1 201 Created
```

with the response body.

Don’t overuse `ResponseEntity` everywhere, though.

Often a controller can simply return an object and let Spring handle the normal response.

---

# **19. Our ProjectHub API**

We’re finally starting to shape the real project.

Eventually we’ll have:

```text
/users
/projects
/posts
/comments
```

For posts:

```text
GET    /posts
GET    /posts/{id}
POST   /posts
PATCH  /posts/{id}
DELETE /posts/{id}
```

Later, security will map nicely onto these:

```text
posts.read
posts.create
posts.update
posts.delete
```

For example:

```java
@PreAuthorize("hasAuthority('posts.delete')")
@DeleteMapping("/{id}")
public ResponseEntity<Void> deletePost(
        @PathVariable Long id
) {
    ...
}
```

We’re not implementing security yet—the point is to see how the pieces will eventually fit.

---

# **20. A complete small example**

Here’s a deliberately simple controller:

```java
@RestController
@RequestMapping("/posts")
public class PostController {

    private final PostService postService;

    public PostController(PostService postService) {
        this.postService = postService;
    }

    @GetMapping("/{id}")
    public PostResponse getPost(@PathVariable Long id) {
        return postService.getPost(id);
    }

    @PostMapping
    public ResponseEntity<PostResponse> createPost(
            @RequestBody CreatePostRequest request
    ) {
        PostResponse response =
                postService.createPost(request);

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(response);
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> deletePost(
            @PathVariable Long id
    ) {
        postService.deletePost(id);

        return ResponseEntity.noContent().build();
    }
}
```

Notice what the controller **doesn’t** know about:

```text
SQL
PostgreSQL
JPA
passwords
JWT
database transactions
```

That’s intentional.

---

# **21. The architecture we’re building**

Our project is beginning to look like:

```text
                 HTTP
                  │
                  ▼
           ┌──────────────┐
           │  Controller  │
           └──────┬───────┘
                  │
                  ▼
           ┌──────────────┐
           │   Service    │
           └──────┬───────┘
                  │
                  ▼
           ┌──────────────┐
           │  Repository  │
           └──────┬───────┘
                  │
                  ▼
              Database
```

Later:

```text
HTTP
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
 ▼
Service
 │
 ▼
Repository
 │
 ▼
PostgreSQL
```

And that’s the architecture we’ll gradually implement rather than trying to learn all of it at once.

---

# **🧠 Important distinction**

Remember these three things:

### **Path variable**

```http
GET /posts/42
```

```java
@PathVariable Long id
```

**Identifies something in the URL.**

### **Query parameter**

```http
GET /posts?page=2&size=20
```

```java
@RequestParam int page
```

**Modifies/filter/sorts the request.**

### **Request body**

```json
{
  "title": "Hello"
}
```

```java
@RequestBody CreatePostRequest request
```

**Carries structured data to the server.**

That’s a very important distinction for API design.

---

# **📝 Exercise**

Build this without looking back if possible.

Create:

```text
PostController
PostService
CreatePostRequest
PostResponse
```

Your API should support:

### **`GET /posts/{id}`**

Return:

```json
{
  "id": 1,
  "title": "Spring Boot",
  "content": "Learning Spring"
}
```

### **`POST /posts`**

Accept:

```json
{
  "title": "Spring Security",
  "content": "Learning authorization"
}
```

and return a `201 Created`.

### **`DELETE /posts/{id}`**

Return:

```text
204 No Content
```

You don’t need a database yet. Your service can simply return hardcoded data.

---