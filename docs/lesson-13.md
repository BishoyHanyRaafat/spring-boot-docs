---
title: Lesson 13: Transactions & the Persistence Context
sidebar_position: 13
---


This lesson connects several things we’ve already seen:

```text
@Transactional
Persistence Context
EntityManager
Managed entities
Dirty checking
Flush
Commit / Rollback
```

These concepts are the difference between **“I know some JPA annotations”** and actually understanding how JPA behaves.

Spring’s current documentation describes `@Transactional` as declarative transaction management, implemented through Spring’s transaction infrastructure/AOP.  

---

## **1. First: what is a transaction?**

A transaction is a group of database operations treated as one logical unit.

Imagine creating a post and recording an audit entry:

```text
Create Post
    +
Create Audit Record
```

We don’t want:

```text
Post created       ✅
Audit failed       ❌
```

if those two operations are supposed to succeed or fail together.

Instead:

```text
BEGIN
    create post
    create audit
COMMIT
```

or:

```text
BEGIN
    create post
    create audit
    something fails
ROLLBACK
```

So the mental model is:

```text
Transaction
    │
    ├── operation 1
    ├── operation 2
    ├── operation 3
    │
    └── COMMIT
```

---


# **2. `@Transactional`**

In Spring, we can write:

```java
@Transactional
public void createPost(...) {
    // database operations
}
```

Spring wraps the method with transaction behavior.

Conceptually:

```text
Call createPost()
       ↓
Spring transaction interceptor
       ↓
BEGIN TRANSACTION
       ↓
your method
       ↓
COMMIT
```

If the transaction is rolled back:

```text
Call createPost()
       ↓
BEGIN
       ↓
your method
       ↓
exception
       ↓
ROLLBACK
```

Spring’s default `@Transactional` behavior uses `PROPAGATION_REQUIRED`, defaults to the database’s default isolation level, is read-write, and rolls back for `RuntimeException` and `Error` by default.  

---


# **3. Where should** `@Transactional`go?

Usually, put transaction boundaries around **service operations**.

For example:

```java
@Service
public class PostService {

    private final PostRepository postRepository;

    public PostService(PostRepository postRepository) {
        this.postRepository = postRepository;
    }

    @Transactional
    public Post createPost(...) {
        // business operation
    }
}
```

Why the service?

Because the service represents the **business operation**.

For example:

```text
createPost()
    ├── validate user
    ├── load project
    ├── create post
    ├── save post
    └── create audit record
```

We want all of those database operations to participate in the same transaction.

---

# **4. What exactly is the Persistence Context?**

This is the big concept.

JPA maintains a **Persistence Context**.

Think of it as a tracking environment for entities.

```text
Persistence Context
┌─────────────────────────────┐
│                             │
│   User #1                   │
│   Post #10                  │
│   Project #3                │
│                             │
│   Hibernate tracks them     │
│                             │
└─────────────────────────────┘
```

An entity inside this context is called **managed**.

Hibernate knows:

“I’m currently responsible for tracking this object.”

---

# **5. The EntityManager**

JPA provides an `EntityManager` abstraction for interacting with the persistence context.

Conceptually:

```text
EntityManager
      │
      ▼
Persistence Context
      │
      ├── User
      ├── Post
      └── Project
```

You don’t need to manually use `EntityManager` for most normal Spring Data operations.

Spring Data JPA sits on top of it.

But understanding that it exists explains a lot of JPA behavior.

---

# **6. Managed entities**

Suppose:

```java
@Transactional
public void updateTitle(Long postId) {

    Post post = postRepository.findById(postId)
            .orElseThrow();

    post.setTitle("New title");
}
```

Notice something strange:

We didn’t write:

```java
postRepository.save(post);
```

So how does the database know the title changed?

Because `post` is a **managed entity** inside the persistence context.

Hibernate remembers its state.

---

# **7. Dirty checking**

Suppose the entity initially looks like:

```text
Post #10

title = "Old title"
content = "Hello"
```

Hibernate loads it and tracks its state.

Then:

```java
post.setTitle("New title");
```

Now:

```text
Original state:
title = "Old title"

Current state:
title = "New title"
```

Hibernate detects the difference.

That’s called:

**Dirty checking**

At flush time, Hibernate can generate:

```sql
UPDATE posts
SET title = 'New title'
WHERE id = 10;
```

So this:

```java
post.setTitle("New title");
```

can result in a database update without an explicit `save()` call.

---

# **8. This is the answer to the famous JPA question**

Why does changing an entity sometimes save it automatically?

Because:

```text
Entity
   ↓
managed by persistence context
   ↓
entity changes
   ↓
dirty checking
   ↓
flush
   ↓
SQL UPDATE
```

That’s one of the most important JPA mental models.

---


# **9. So is `save()`unnecessary?**

There’s an important nuance.

Spring Data’s documentation explicitly notes that `save()` isn’t strictly necessary from a JPA perspective when modifying an already-managed entity, although keeping it can be consistent with the repository abstraction.  

For example:

```java
@Transactional
public void renamePost(Long id, String title) {

    Post post = postRepository.findById(id)
            .orElseThrow();

    post.setTitle(title);
}
```

is perfectly legitimate.

You don’t necessarily need:

```java
postRepository.save(post);
```

after the setter.

But when creating a new entity:

```java
Post post = new Post();
```

you generally need to persist it, commonly through:

```java
postRepository.save(post);
```

---

# **10. Four entity states**

JPA commonly describes entities using four states.

## **1. Transient**

Just a normal new Java object:

```java
Post post = new Post();
```

It’s not associated with the persistence context.

```text
Java object
   │
   └── not managed
```

---

## **2. Managed**

The entity is being tracked.

For example:

```java
Post post = postRepository.findById(id)
        .orElseThrow();
```

inside a transaction.

Conceptually:

```text
Persistence Context
       │
       └── Post #10
```

Changes can be detected automatically.

---

## **3. Detached**

The entity used to be managed, but is no longer associated with the current persistence context.

For example, after the transaction/persistence context ends:

```text
Transaction ends
      ↓
Persistence context closes
      ↓
entity becomes detached
```

A detached object is still a Java object.

It’s just no longer being tracked by that persistence context.

---

## **4. Removed**

The entity has been marked for deletion.

For example:

```java
postRepository.delete(post);
```

The entity is scheduled for removal from the database.

---

# **11. Flush vs commit**

These are **not the same thing**.

This distinction causes a lot of confusion.

### **Flush**

Means roughly:

Synchronize the persistence context’s changes with the database.

Hibernate may send:

```sql
UPDATE ...
INSERT ...
DELETE ...
```

to the database.

### **Commit**

Means:

Successfully complete the database transaction.

Think:

```text
Persistence Context
       │
       │ flush
       ▼
Database statements
       │
       │ commit
       ▼
Transaction completed
```

A flush does **not** necessarily mean the transaction is committed.

---

# **12. Example**

Consider:

```java
@Transactional
public void updatePost(Long id) {

    Post post = postRepository.findById(id)
            .orElseThrow();

    post.setTitle("New title");

    // more work...

    throw new RuntimeException("Oops");
}
```

Potential sequence:

```text
BEGIN
  ↓
SELECT post
  ↓
modify managed entity
  ↓
Hibernate detects modification
  ↓
flush
  ↓
UPDATE posts ...
  ↓
exception
  ↓
ROLLBACK
```

Even though the `UPDATE` may have been sent to the database during the transaction, the transaction is rolled back.

Final database state:

```text
Old title
```

That’s the power of transactions.

---

# **13. Why transactions matter for multiple repositories**

Suppose we have:

```java
@Transactional
public void createProject(...) {

    Project project = projectRepository.save(...);

    ProjectMembership membership =
        membershipRepository.save(...);

    auditRepository.save(...);
}
```

All three operations participate in the same transaction.

Conceptually:

```text
                    Transaction
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
 projectRepository membershipRepository auditRepository
        │               │               │
        └───────────────┼───────────────┘
                        ▼
                      COMMIT
```

If the membership operation fails:

```text
project INSERT     ──┐
membership INSERT  ──┼── ROLLBACK
audit INSERT        ──┘
```

You don’t end up with half a project creation.

---

# **14. Repository transactions vs service transactions**

Spring Data JPA repository CRUD methods already have transactional configuration by default. Read operations inherited from the standard repository are configured as read-only, while other CRUD operations use normal transactions.  

So you might wonder:

“Why put `@Transactional` on my service if repositories already use transactions?”

Because a **business operation may involve multiple repository calls**.

Imagine:

```java
public void transferPost(...) {

    postRepository.findById(...);

    projectRepository.findById(...);

    membershipRepository.save(...);

    auditRepository.save(...);
}
```

You want one transaction around the **whole operation**, not independent transaction boundaries around individual repository operations.

That’s why service-level transaction boundaries are so useful.

---

# **15. Read-only transactions**

You may see:

```java
@Transactional(readOnly = true)
public PostResponse getPost(Long id) {
    ...
}
```

This communicates:

This transaction is intended for reading.

It’s useful for expressing intent and can allow some optimizations depending on the transaction manager/database/provider.

For example:

```java
@Transactional(readOnly = true)
public List<Post> getPosts() {
    return postRepository.findAll();
}
```

Then:

```java
@Transactional
public void createPost(...) {
    ...
}
```

Don’t think of `readOnly = true` as a magical security mechanism that physically makes every database modification impossible. It’s primarily transaction configuration/intent.

---

# **16. Rollback rules**

A common example:

```java
@Transactional
public void createPost(...) {

    // database work

    throw new RuntimeException();
}
```

By default, Spring rolls the transaction back for `RuntimeException` and `Error`. Checked exceptions don’t trigger rollback by default.  

You can explicitly configure rollback rules:

```java
@Transactional(rollbackFor = MyCheckedException.class)
```

Don’t memorize every option yet.

Just remember:

Transaction rollback behavior is configurable.

---

# **17. The self-invocation trap**

This is a subtle but important Spring concept.

Suppose:

```java
@Service
public class PostService {

    public void outerMethod() {
        innerMethod();
    }

    @Transactional
    public void innerMethod() {
        // ...
    }
}
```

You might expect:

```text
outerMethod()
    ↓
transaction starts
    ↓
innerMethod()
```

But Spring’s default transaction management works through proxies, and local calls within the same class don’t pass through that proxy. Therefore the `@Transactional` on `innerMethod()` isn’t necessarily applied when called this way.  

The usual solution is to put the transaction boundary on the externally invoked service method:

```java
@Transactional
public void outerMethod() {
    innerMethod();
}
```

This is a classic Spring gotcha.

---

# **18. Why controllers shouldn’t normally own transactions**

You could technically do:

```java
@RestController
@Transactional
public class PostController {
}
```

But that’s usually the wrong abstraction.

Consider:

```text
HTTP
 ↓
Controller
 ↓
Service
 ↓
Repository
```

The controller understands:

```text
HTTP
JSON
status codes
headers
```

The service understands:

```text
business operation
transaction boundary
```

So:

```java
@Transactional
public void createPost(...)
```

belongs naturally around the business operation.

---

# **19. A real ProjectHub example**

Let’s say creating a post requires:

1. Find the author.
2. Find the project.
3. Check membership.
4. Create the post.
5. Save it.
6. Record an audit event.

We want:

```java
@Transactional
public Post createPost(
        Long userId,
        Long projectId,
        CreatePostRequest request) {

    User user = userRepository.findById(userId)
            .orElseThrow(...);

    Project project = projectRepository.findById(projectId)
            .orElseThrow(...);

    membershipRepository
            .findByUserIdAndProjectId(userId, projectId)
            .orElseThrow(...);

    Post post = new Post();

    post.setAuthor(user);
    post.setProject(project);
    post.setTitle(request.title());
    post.setContent(request.content());

    return postRepository.save(post);
}
```

The transaction protects the **whole operation**.

---

# **20. And now security will eventually fit here**

Remember your permission model:

```text
posts.read
posts.create
posts.delete
```

Eventually our flow will look something like:

```text
HTTP request
    ↓
Authentication
    ↓
Authorization
    ↓
Controller
    ↓
@Transactional Service
    ↓
JPA
    ↓
PostgreSQL
```

For example:

```java
@PreAuthorize("hasAuthority('posts.create')")
@Transactional
public Post createPost(...) {
    ...
}
```

The security check answers:

**May this user perform this operation?**

The transaction answers:

**How should the database changes for this operation succeed or fail together?**

Different concerns, working together.

---

# **21. The complete mental model**

This is the diagram I want you to remember:

```text
                    HTTP Request
                         │
                         ▼
                    Controller
                         │
                         ▼
                    Service
                 @Transactional
                         │
              ┌──────────┴──────────┐
              │                     │
              ▼                     ▼
        Repository A          Repository B
              │                     │
              └──────────┬──────────┘
                         ▼
                  Persistence Context
                         │
                  ┌──────┴──────┐
                  │             │
               Entity A      Entity B
                  │             │
                  └──────┬──────┘
                         │
                   Dirty Checking
                         │
                        Flush
                         │
                         ▼
                      SQL
                         │
                         ▼
                    PostgreSQL
                         │
                       Commit
```

That’s the architecture you should have in your head.

---
