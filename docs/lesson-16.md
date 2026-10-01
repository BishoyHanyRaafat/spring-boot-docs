---
title: Lesson 16: Building a Real REST Feature with JPA
sidebar_position: 16
---


Now we’re going to stop learning the pieces independently and **connect them into one real feature**.

We’ll build:

```text
POST   /projects/{projectId}/posts
GET    /projects/{projectId}/posts
GET    /posts/{id}
DELETE /posts/{id}
```

using the architecture we’ve been building:

```text
HTTP
 ↓
Controller
 ↓
DTO + Validation
 ↓
Service
 ↓
Transaction
 ↓
Repository
 ↓
JPA/Hibernate
 ↓
PostgreSQL
```

This is the point where Spring Boot starts feeling like an actual backend framework rather than a collection of annotations.

Spring Data JPA’s current stable line is 4.1.1, and its repository abstraction is specifically intended to reduce persistence-layer boilerplate.  

---

# **1. The feature**

Let’s say a user wants to create a post inside a project.

The request:

```http
POST /projects/10/posts
Content-Type: application/json
```

```json
{
  "title": "Learning Spring Boot",
  "content": "Today I learned about transactions."
}
```

The application needs to answer several questions:

1. Does project `10` exist?
2. Is the user allowed to create a post there?
3. Is the request valid?
4. Which user becomes the author?
5. Should the database operations happen inside one transaction?
6. What should the response look like?

Notice how much more is happening than:

```java
repository.save(...)
```

That’s what the service layer is for.

---

# **2. Our entities**

Conceptually:

```text
User
 │
 ├── posts
 │
 └── memberships
          │
          ▼
       Project
          │
          └── posts
```

And:

```text
Post
 ├── author → User
 └── project → Project
```

Our `Post` entity might look like:

```java
@Entity
@Table(name = "posts")
public class Post {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 100)
    private String title;

    @Column(nullable = false)
    private String content;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "author_id", nullable = false)
    private User author;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "project_id", nullable = false)
    private Project project;

    // getters/setters
}
```

The important part is:

```java
private User author;
private Project project;
```

The database represents those relationships using:

```text
posts.author_id
posts.project_id
```

---

# **3. Don’t put HTTP logic in the service**

A common beginner mistake is something like:

```java
@Service
public class PostService {

    public ResponseEntity<?> createPost(...) {
        ...
    }
}
```

Don’t.

The service shouldn’t know that HTTP exists.

Instead:

```text
Controller
    knows HTTP
        ↓
Service
    knows business logic
        ↓
Repository
    knows persistence
```

This separation becomes extremely valuable as the application grows.

Spring MVC’s `@RestController` is specifically designed for controller methods whose return values are written to the HTTP response body.  

---

# **4. Request DTO**

We don’t want clients sending this:

```json
{
  "id": 999,
  "author": 123,
  "project": 456,
  "title": "...",
  "content": "..."
}
```

The server should determine:

```text
id       → database
author   → authenticated user
project  → URL
```

The client only supplies:

```java
public record CreatePostRequest(

        @NotBlank
        @Size(min = 3, max = 100)
        String title,

        @NotBlank
        @Size(max = 10_000)
        String content
) {}
```

Spring MVC supports Bean Validation on `@RequestBody` parameters using `@Valid`.  

So:

```java
@PostMapping
public ResponseEntity<PostResponse> createPost(
        @PathVariable Long projectId,
        @Valid @RequestBody CreatePostRequest request) {

    ...
}
```

Validation happens before the business operation proceeds.

---

# **5. Response DTO**

Our response shouldn’t expose the entire entity either.

Let’s create:

```java
public record PostResponse(
        Long id,
        String title,
        String content,
        Long authorId,
        String authorUsername,
        Long projectId,
        Instant createdAt
) {}
```

Now our API contract is explicit.

The entity can change internally without necessarily changing the API.

---

# **6. Repository layer**

We need:

```java
public interface PostRepository
        extends JpaRepository<Post, Long> {

    Page<Post> findByProjectId(
            Long projectId,
            Pageable pageable
    );
}
```

And:

```java
public interface ProjectRepository
        extends JpaRepository<Project, Long> {
}
```

That’s already enough for our first version.

Spring Data creates the implementation for us.

Conceptually:

```text
PostRepository
      ↓
Spring Data JPA
      ↓
Hibernate
      ↓
SQL
```

---

# **7. The service**

Now things become interesting.

```java
@Service
public class PostService {

    private final PostRepository postRepository;
    private final ProjectRepository projectRepository;

    public PostService(
            PostRepository postRepository,
            ProjectRepository projectRepository) {

        this.postRepository = postRepository;
        this.projectRepository = projectRepository;
    }
}
```

Why inject both?

Because creating a post requires more than one piece of data.

---

# **8. Creating the post**

The basic operation:

```java
@Transactional
public PostResponse createPost(
        Long projectId,
        CreatePostRequest request,
        User currentUser) {

    Project project = projectRepository.findById(projectId)
            .orElseThrow(() ->
                    new ProjectNotFoundException(projectId));

    Post post = new Post();

    post.setTitle(request.title());
    post.setContent(request.content());
    post.setAuthor(currentUser);
    post.setProject(project);

    Post saved = postRepository.save(post);

    return toResponse(saved);
}
```

There’s a lot to learn here.

---

# **9. Why check the project first?**

Suppose someone sends:

```http
POST /projects/999/posts
```

but project `999` doesn’t exist.

We don’t want:

```text
Post
 └── project_id = 999
```

if the database has a foreign-key constraint.

Instead:

```java
projectRepository.findById(projectId)
```

and:

```java
.orElseThrow(...)
```

gives us a clean application-level error:

```text
404 Project Not Found
```

rather than allowing the database to become the primary source of API semantics.

---


# 10. Why is `@Transactional`

**useful here?**

Imagine the operation eventually becomes:

```text
1. Find project
2. Check membership
3. Create post
4. Save post
5. Create audit record
6. Update project timestamp
```

Those operations form one business operation.

We want:

```text
BEGIN TRANSACTION

find project
check membership
insert post
insert audit
update project

COMMIT
```

If something fails:

```text
ROLLBACK
```

Spring’s transaction abstraction supports declarative transaction management and integrates with JPA/Hibernate.  

And `@Transactional` is implemented through Spring’s transaction infrastructure and AOP proxies.  

---

# **11. The controller**

Now the controller becomes surprisingly thin:

```java
@RestController
@RequestMapping("/projects/{projectId}/posts")
public class PostController {

    private final PostService postService;

    public PostController(PostService postService) {
        this.postService = postService;
    }

    @PostMapping
    public ResponseEntity<PostResponse> createPost(
            @PathVariable Long projectId,
            @Valid @RequestBody CreatePostRequest request) {

        PostResponse response =
                postService.createPost(
                        projectId,
                        request,
                        currentUser
                );

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(response);
    }
}
```

Don’t worry about `currentUser` yet.

We’ll introduce Spring Security shortly.

For now, imagine the controller gets the current user somehow.

The important architectural point is:

```text
Controller
 ├── receives HTTP
 ├── validates DTO
 └── calls service

Service
 ├── business rules
 ├── transaction
 └── persistence

Repository
 └── database access
```

---

# **12. Getting posts**

Now:

```http
GET /projects/10/posts?page=0&size=20
```

Repository:

```java
Page<Post> findByProjectId(
        Long projectId,
        Pageable pageable
);
```

Service:

```java
@Transactional(readOnly = true)
public Page<PostResponse> getPosts(
        Long projectId,
        Pageable pageable) {

    return postRepository
            .findByProjectId(projectId, pageable)
            .map(this::toResponse);
}
```

Controller:

```java
@GetMapping
public Page<PostResponse> getPosts(
        @PathVariable Long projectId,
        @PageableDefault(size = 20) Pageable pageable) {

    return postService.getPosts(projectId, pageable);
}
```

Notice how little the controller knows about SQL.

---

# **13. What SQL is roughly happening?**

For:

```java
findByProjectId(10, pageable)
```

Hibernate generates SQL conceptually similar to:

```sql
SELECT
    p.id,
    p.title,
    p.content,
    p.author_id,
    p.project_id
FROM posts p
WHERE p.project_id = ?
LIMIT ?
OFFSET ?;
```

This is why understanding SQL is still important even though you’re using JPA.

JPA doesn’t eliminate SQL.

It **generates SQL for you**.

---

# **14. Getting one post**

Repository:

```java
public interface PostRepository
        extends JpaRepository<Post, Long> {
}
```

We already inherit:

```java
findById(Long id)
```

Service:

```java
@Transactional(readOnly = true)
public PostResponse getPost(Long id) {

    Post post = postRepository.findById(id)
            .orElseThrow(() ->
                    new PostNotFoundException(id));

    return toResponse(post);
}
```

Controller:

```java
@GetMapping("/{postId}")
public PostResponse getPost(
        @PathVariable Long postId) {

    return postService.getPost(postId);
}
```

Simple.

---

# **15. Deleting a post**

Repository already provides:

```java
deleteById(...)
```

But again, business logic belongs in the service.

```java
@Transactional
public void deletePost(Long postId) {

    Post post = postRepository.findById(postId)
            .orElseThrow(() ->
                    new PostNotFoundException(postId));

    postRepository.delete(post);
}
```

Controller:

```java
@DeleteMapping("/{postId}")
@ResponseStatus(HttpStatus.NO_CONTENT)
public void deletePost(
        @PathVariable Long postId) {

    postService.deletePost(postId);
}
```

Eventually we’ll add:

```text
Can this user delete this post?
```

That’s authorization.

---

# **16. And this is where authorization gets interesting**

Imagine:

```text
Alice owns Post #10
Bob does not
```

Bob sends:

```http
DELETE /posts/10
```

Authentication answers:

Who is Bob?

Authorization answers:

Is Bob allowed to delete Post #10?

This isn’t merely:

```java
hasAuthority("posts.delete")
```

because perhaps Bob **has**:

```text
posts.delete
```

but only for posts belonging to projects where he’s a member.

So we eventually need:

```text
Authentication
      ↓
Permission
      ↓
Resource ownership / membership
      ↓
Decision
```

This is exactly why we’re building the architecture first.

---

# **17. A subtle architectural rule**

Don’t do this:

```java
if (user.isAdmin()) {
    ...
}
```

everywhere.

And don’t make controllers responsible for complicated authorization logic.

Eventually we want something more like:

```text
Controller
    ↓
Service
    ↓
Authorization rule
    ↓
Repository
```

or, with Spring Security method authorization:

```java
@PreAuthorize(...)
```

We’ll get there.

---

# **18. Mapping entity → DTO**

We need:

```java
private PostResponse toResponse(Post post) {

    return new PostResponse(
            post.getId(),
            post.getTitle(),
            post.getContent(),
            post.getAuthor().getId(),
            post.getAuthor().getUsername(),
            post.getProject().getId(),
            post.getCreatedAt()
    );
}
```

But now we hit an important JPA issue.

Remember:

```java
@ManyToOne(fetch = FetchType.LAZY)
private User author;
```

and:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Project project;
```

Accessing:

```java
post.getAuthor().getUsername()
```

may trigger another SQL query.

---

# **19. Potential N+1 problem**

Suppose we fetch:

```text
20 posts
```

Then mapping each:

```java
post.getAuthor().getUsername()
```

could result in:

```text
1 query → posts

20 queries → authors
```

Total:

```text
21 queries
```

That’s the N+1 problem we discussed earlier.

Instead, we might deliberately fetch the data we need.

For example:

```java
@Query("""
    SELECT p
    FROM Post p
    JOIN FETCH p.author
    JOIN FETCH p.project
    WHERE p.id = :id
""")
Optional<Post> findByIdWithAuthorAndProject(
        @Param("id") Long id
);
```

For list endpoints, projections can sometimes be even better.

Spring Data JPA supports projections specifically for retrieving selected portions of an aggregate instead of always loading the entire entity.  

---


# 20. Why not always use `JOIN FETCH` ?

Because optimization has trade-offs.

If the API only needs:

```text
id
title
author username
```

loading:

```text
Post
 + User
 + Project
 + Comments
 + ...
```

would be unnecessary.

That’s why the question shouldn’t be:

“How do I fetch my entities?”

Instead ask:

**“What data does this use case actually need?”**

Then choose:

```text
Entity
Fetch join
EntityGraph
Projection
DTO query
```

appropriately.

---

# **21. The complete request flow**

Let’s trace:

```http
POST /projects/10/posts
```

with:

```json
{
  "title": "Hello Spring",
  "content": "I'm learning JPA."
}
```

### **Step 1 — HTTP**

Spring MVC receives request.

### **Step 2 — DTO binding**

JSON becomes:

```java
CreatePostRequest
```

### **Step 3 — Validation**

```java
@Valid
```

checks:

```text
title
content
```

Spring MVC’s current validation infrastructure supports both argument validation and method validation, with different exceptions depending on the method signature.  

### **Step 4 — Controller**

Calls:

```java
postService.createPost(...)
```

### **Step 5 — Transaction begins**

```java
@Transactional
```

### **Step 6 — Service**

Checks project.

### **Step 7 — Business rules**

Eventually:

```text
Is current user a project member?
Does user have posts.create?
```

### **Step 8 — Entity creation**

```java
Post post = new Post();
```

### **Step 9 — Persistence**

```java
postRepository.save(post);
```

### **Step 10 — SQL**

Hibernate generates:

```sql
INSERT INTO posts (...)
VALUES (...);
```

### **Step 11 — Commit**

Transaction commits.

### **Step 12 — DTO**

Entity becomes:

```java
PostResponse
```

### **Step 13 — HTTP response**

```http
201 Created
```

```json
{
  "id": 42,
  "title": "Hello Spring",
  "content": "I'm learning JPA.",
  "authorId": 7,
  "authorUsername": "alice",
  "projectId": 10,
  "createdAt": "2026-10-01T12:00:00Z"
}
```

That’s a real Spring Boot backend flow.

---

# **22. The architecture we have now**

You should start seeing why we learned the concepts in this order:

```text
                    HTTP
                     │
                     ▼
              ┌─────────────┐
              │ Controller  │
              └──────┬──────┘
                     │
              DTO + Validation
                     │
                     ▼
              ┌─────────────┐
              │   Service   │
              └──────┬──────┘
                     │
              Business Rules
                     │
                Transaction
                     │
                     ▼
              ┌─────────────┐
              │ Repository  │
              └──────┬──────┘
                     │
                     ▼
                Spring Data
                     │
                     ▼
                  Hibernate
                     │
                     ▼
                PostgreSQL

Flyway ───────────────► Schema
```

This is the foundation we’ll build security on top of.

---
