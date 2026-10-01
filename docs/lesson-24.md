---
title: Lesson 24: Resource-Level Authorization
sidebar_position: 24
---

This is one of the most important lessons in the entire security section.

So far, we have learned how to answer:

**Does Alice have the** **`posts.delete`** **permission?**

But ProjectHub needs to answer a harder question:

**Does Alice have permission to delete this particular post?**

Those are different questions.

Spring Security supports method-level authorization specifically for fine-grained decisions involving method parameters and return values, and current Spring Security uses `AuthorizationManager` underneath these mechanisms.  

---

# **1. General permission vs resource authorization**

Suppose Alice has:

```text
posts.delete
```

That means:

```text
Alice is generally allowed to delete posts.
```

But imagine:

```text
Post 42 → authored by Bob
Post 57 → authored by Alice
```

Alice sends:

```http
DELETE /posts/42
```

Should that automatically succeed?

Not necessarily.

We may have a business rule:

```text
User can delete a post if:

    user has posts.delete
AND
    user owns the post
```

So authorization becomes:

```text
                    Alice
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
    posts.delete?             owns post?
          │                       │
          └───────────┬───────────┘
                      ▼
                  ALLOW/DENY
```

---

# **2. ProjectHub authorization rules**

Let’s define some rules for learning.

### **Read**

A user needs:

```text
posts.read
```

### **Create**

A user needs:

```text
posts.create
```

and must belong to the project.

### **Delete**

A user needs:

```text
posts.delete
```

and must either:

```text
own the post
```

or:

```text
be allowed to administer the project
```

This gives us two dimensions:

```text
Global permission
        +
Resource-specific rule
```

---

# **3. Why request-level authorization isn’t enough**

We could write:

```java
.requestMatchers(HttpMethod.DELETE, "/posts/**")
    .hasAuthority("posts.delete")
```

That’s useful.

But it can only answer:

```text
Does Authentication contain posts.delete?
```

It doesn’t naturally know:

```text
Who owns post 42?
Which project does post 42 belong to?
Is Alice a member of that project?
What role does Alice have in that project?
```

Spring Security’s method authorization is useful here because authorization decisions can use method parameters and return values.  

---

# **4. Method security**

First enable it:

```java
@Configuration
@EnableMethodSecurity
public class SecurityConfig {
}
```

`@EnableMethodSecurity` activates annotations such as `@PreAuthorize` and `@PostAuthorize`; method security isn’t enabled merely by adding the normal Spring Security starter.  

Now we can write:

```java
@PreAuthorize("hasAuthority('posts.delete')")
public void deletePost(Long postId) {
    ...
}
```

This protects the service method.

---

# **5. Why put authorization on the service?**

Imagine this endpoint:

```text
DELETE /posts/42
```

Today it is called by:

```text
REST Controller
```

But tomorrow perhaps:

```text
AdminController
ScheduledJob
MessageConsumer
GraphQL endpoint
```

could call the same service.

If authorization only exists in the HTTP layer:

```text
Controller
   ↓
security check
   ↓
Service
```

another caller might bypass that particular HTTP rule.

Putting important authorization at the service boundary gives us another layer of defense.

Spring Security explicitly identifies method security as useful for enforcing authorization at the service layer.  

---

# 

# 

# **6. But**

**`hasAuthority()`**

**still isn’t enough**

This:

```java
@PreAuthorize("hasAuthority('posts.delete')")
public void deletePost(Long postId) {
    ...
}
```

answers:

```text
Does the user have posts.delete?
```

It does **not** answer:

```text
Does the user own postId?
```

We need resource-aware authorization.

---

# **7. Method parameters can participate**

Spring Security method expressions can refer to method arguments.

For example:

```java
@PreAuthorize("#username == authentication.name")
public User getUser(String username) {
    ...
}
```

Here:

```text
#username
```

means:

```text
method parameter
```

and:

```text
authentication.name
```

means:

```text
currently authenticated user
```

So the decision can involve both:

```text
current Authentication
+
method arguments
```

That’s one reason method security is useful for fine-grained authorization.  

---

# **8. A simple ownership check**

Suppose we have:

```java
@PreAuthorize("#username == authentication.name")
public UserProfile getProfile(String username) {
    ...
}
```

Alice calls:

```text
getProfile("alice")
```

Then:

```text
#username
   ↓
alice

authentication.name
   ↓
alice
```

Result:

```text
ALLOW
```

But:

```text
getProfile("bob")
```

produces:

```text
bob != alice
```

Result:

```text
DENY
```

---

# **9. But don’t put huge business rules into SpEL**

You might be tempted to write something like:

```java
@PreAuthorize("""
    hasAuthority('posts.delete')
    and @postAuthorizationService.isOwner(#postId, authentication.name)
""")
```

This can work.

But imagine the rule becomes:

```text
has posts.delete
AND
is project member
AND
post belongs to project
AND
user is owner OR project admin
AND
project isn't archived
AND
post isn't locked
```

Now your annotation becomes a miniature programming language.

That’s not a good direction.

Spring Security’s current documentation itself cautions against unnecessarily complicated SpEL expressions and discusses moving authorization logic into granted authorities or custom authorization components where appropriate.  

---

# **10. Better: an authorization service**

Let’s create:

```java
@Component
public class PostAuthorizationService {

    public boolean canDelete(
            Long postId,
            Authentication authentication) {

        // domain authorization logic
    }
}
```

Then:

```java
@PreAuthorize(
    "hasAuthority('posts.delete') and " +
    "@postAuthorizationService.canDelete(#postId, authentication)"
)
public void deletePost(Long postId) {
    ...
}
```

Now the annotation says something understandable:

```text
must have posts.delete
AND
must satisfy post deletion rules
```

while the actual business logic lives in Java.

---

# **11. Even better: think in terms of policy**

Instead of asking:

```text
Can Alice delete post 42?
```

think:

```text
DeletePostPolicy
```

with rules:

```text
1. User must be authenticated.
2. User must have posts.delete.
3. Post must exist.
4. User must own post OR have appropriate project authority.
5. Project must permit deletion.
```

This makes authorization a real application concept rather than scattered `if` statements.

---

# **12. Ownership implementation**

Suppose `Post` has:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "author_id", nullable = false)
private User author;
```

We can query:

```java
public interface PostRepository
        extends JpaRepository<Post, Long> {

    boolean existsByIdAndAuthorUsername(
            Long postId,
            String username
    );
}
```

Now:

```java
@Component
public class PostAuthorizationService {

    private final PostRepository postRepository;

    public PostAuthorizationService(
            PostRepository postRepository) {
        this.postRepository = postRepository;
    }

    public boolean isOwner(
            Long postId,
            Authentication authentication) {

        return postRepository.existsByIdAndAuthorUsername(
                postId,
                authentication.getName()
        );
    }
}
```

This is nice because the database answers:

Does this post exist with this author?

without loading the entire `Post` entity.

---

# **13. Then protect deletion**

```java
@PreAuthorize(
    "hasAuthority('posts.delete') and " +
    "@postAuthorizationService.isOwner(#postId, authentication)"
)
@Transactional
public void deletePost(Long postId) {

    Post post = postRepository.findById(postId)
            .orElseThrow(() ->
                new PostNotFoundException(postId));

    postRepository.delete(post);
}
```

The flow becomes:

```text
DELETE /posts/42
       ↓
posts.delete?
       ↓
ownership?
       ↓
service method
       ↓
delete
```

---

# **14. What happens when authorization fails?**

Suppose Alice has:

```text
posts.delete
```

but doesn’t own post 42.

The method authorization check denies the invocation.

Spring Security’s method authorization infrastructure throws an authorization exception when the decision is denied; for HTTP requests this is ultimately translated into a 403 response.  

So:

```text
authenticated
+
has posts.delete
+
not owner
=
403 Forbidden
```

The important thing is that the service method itself never executes.

---

# **15. What if the post doesn’t exist?**

There’s an interesting question here.

Suppose:

```text
DELETE /posts/999
```

and post `999` doesn’t exist.

Should we first check:

```text
isOwner(999)?
```

The answer depends on how you’ve designed the authorization flow.

A simple implementation might query:

```text
existsByIdAndAuthorUsername
```

and return false.

That could produce:

```text
403
```

instead of:

```text
404
```

Whether that is desirable depends on your API’s information-disclosure policy.

Sometimes returning `404` for inaccessible resources helps avoid revealing whether the resource exists.

This is a **security/API design decision**, not something Spring automatically decides for you.

---

# **16. Project membership makes this more interesting**

Remember our schema:

```text
User
 │
 └── ProjectMembership
          │
          ▼
       Project
```

Suppose Alice wants to create:

```http
POST /projects/7/posts
```

Having:

```text
posts.create
```

is not necessarily enough.

We might require:

```text
Alice is a member of Project 7
```

So:

```text
posts.create
      AND
member(project=7)
```

---

# **17. Project authorization service**

Conceptually:

```java
@Component
public class ProjectAuthorizationService {

    public boolean isMember(
            Long projectId,
            Authentication authentication) {

        // query project membership
    }
}
```

Then:

```java
@PreAuthorize(
    "hasAuthority('posts.create') and " +
    "@projectAuthorizationService.isMember(" +
        "#projectId, authentication" +
    ")"
)
@Transactional
public PostResponse createPost(
        Long projectId,
        CreatePostRequest request) {

    ...
}
```

Now authorization is resource-aware.

---

# **18. Global role vs project role**

This is where our earlier distinction becomes extremely important.

Suppose:

```text
Alice
Global role: USER

Project A:
OWNER

Project B:
MEMBER
```

Alice might be allowed to:

```text
Project A → delete posts
Project B → create posts
```

depending on your project policies.

Her global role:

```text
USER
```

doesn’t tell us enough.

We need:

```text
User
 +
Project
 +
Membership
 +
Membership role
```

This is **resource-scoped authorization**.

---

# **19. Don’t put project membership into the JWT**

This is a common beginner mistake.

You might think:

```json
{
  "sub": "alice",
  "projects": {
      "7": "OWNER",
      "8": "MEMBER",
      "9": "MEMBER"
  }
}
```

Don’t do this for ProjectHub.

Why?

Because project memberships can change frequently.

Imagine Alice belongs to 200 projects.

Your JWT becomes huge.

And if Alice is removed from Project 7:

```text
database:
    Alice no longer member
```

but her old JWT might still say:

```text
Project 7 → OWNER
```

until it expires.

For resource-specific relationships, querying current state is usually more appropriate.

---

# **20. JWT vs database: what belongs where?**

This is a very useful architecture rule.

### **JWT**

Good for relatively stable authentication information:

```text
user identity
issuer
expiration
general authorities
```

### **Database**

Good for dynamic resource relationships:

```text
project membership
post ownership
project status
post status
team membership
resource-specific permissions
```

So:

```text
JWT
 ├── sub = alice
 └── posts.create

Database
 ├── Alice → Project 7 → OWNER
 └── Post 42 → Project 7 → Bob
```

Then the authorization decision combines both.

---

# **21. A complete create-post decision**

Alice sends:

```http
POST /projects/7/posts
Authorization: Bearer <JWT>
```

JWT contains:

```text
posts.create
```

Spring Security checks:

```text
hasAuthority("posts.create")
```

Pass.

Then ProjectHub checks:

```text
Is Alice a member of project 7?
```

Suppose:

```text
Alice → Project 7 → MEMBER
```

Pass.

Then:

```text
create post
author = Alice
project = 7
```

So:

```text
General permission
        +
resource authorization
        ↓
ALLOW
```

---

# **22. Defense in depth**

You might wonder:

Why check `posts.create` in Spring Security and membership in the service?

Because they’re different concerns.

Spring Security:

```text
Does this user have the general capability?
```

Application authorization:

```text
Does that capability apply to this particular resource?
```

That’s defense in depth.

Spring Security itself describes request-based and method-based authorization as complementary mechanisms for authorization.  

---

# 

# 

# **23.**

**`@PreAuthorize`**

**vs request authorization**

Think of these as two gates.

### **Gate 1**

```java
.requestMatchers(HttpMethod.DELETE, "/posts/**")
    .hasAuthority("posts.delete")
```

### **Gate 2**

```java
@PreAuthorize(
    "@postAuthorizationService.isOwner(#postId, authentication)"
)
```

So:

```text
HTTP request
     ↓
Gate 1: general permission
     ↓
Controller
     ↓
Service
     ↓
Gate 2: resource authorization
     ↓
Database operation
```

This is a very solid architecture for ProjectHub.

---

# **24. A subtle Spring AOP issue**

Method security works through Spring’s method interception/proxy infrastructure.  

That means this matters:

```java
@Service
public class PostService {

    public void publicMethod() {
        deletePost(42L);
    }

    @PreAuthorize("...")
    public void deletePost(Long id) {
        ...
    }
}
```

Calling:

```java
this.deletePost(42L);
```

inside the same class does not go through the Spring proxy in the normal proxy-based setup.

Therefore, you should not rely on self-invocation to trigger method-security interception.

This is conceptually similar to the `@Transactional` self-invocation issue we discussed earlier.

---

# 

# 

# **25. When**

**`@PreAuthorize`**

**becomes too complicated**

Suppose your expression becomes:

```java
@PreAuthorize("""
    hasAuthority('posts.delete')
    and @postAuthorizationService.isOwner(#id, authentication)
    and @projectAuthorizationService.isMember(#projectId, authentication)
    and @projectAuthorizationService.isActive(#projectId)
""")
```

That’s a warning sign.

At that point, a dedicated authorization component can make the policy easier to test and understand.

Current Spring Security uses the `AuthorizationManager` abstraction for authorization decisions, and custom `AuthorizationManager` implementations are supported.  

We’ll eventually build one.

---

# **26. The mental model I want you to remember**

ProjectHub authorization now looks like:

```text
                     REQUEST
                        │
                        ▼
                 Authentication
                        │
                        ▼
              General permissions
                        │
                        ▼
              Resource authorization
                        │
                        ▼
                 Business rules
                        │
                        ▼
                    Database
```

More concretely:

```text
                    Alice
                      │
                      ▼
              authenticated?
                      │
                     YES
                      │
                      ▼
             posts.delete?
                      │
                     YES
                      │
                      ▼
             owns post 42?
                      │
                     YES
                      │
                      ▼
                  DELETE
```

---

# **Exercise 24**

Now implement **authorization for deleting posts**.

Start with this repository method:

```java
boolean existsByIdAndAuthorUsername(
        Long postId,
        String username
);
```

Then create:

```text
PostAuthorizationService
```

with:

```java
boolean isOwner(
    Long postId,
    Authentication authentication
)
```

Then protect:

```java
deletePost(Long postId)
```

with:

```text
posts.delete
+
ownership
```

Finally test these four cases:

|**User**|**Permission**|**Owns Post**|**Result**|
|---|---|---|---|
|Alice|yes|yes|allowed|
|Alice|yes|no|403|
|Alice|no|yes|403|
|Alice|no|no|403|

Then we’ll do the more interesting case:

```text
Alice has posts.delete
BUT
Alice doesn't own the post
BUT
Alice is a PROJECT OWNER
```

That will lead us into **custom authorization policies and project-scoped permissions**, which is where ProjectHub’s authorization model becomes much closer to what you’d see in a real production application.