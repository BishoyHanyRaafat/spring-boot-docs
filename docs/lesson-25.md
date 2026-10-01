---
title: "Lesson 25: Custom Authorization Policies & Project-Scoped Permissions"
sidebar_position: 25
---

Last lesson we reached an important problem:

Alice has `posts.delete`, but she doesn’t own the post. What if she’s the **owner of the project** containing that post?

This is where authorization starts becoming a real application architecture problem rather than just a few `hasAuthority(...)` checks.

Spring Security 7.1’s authorization model is built around `AuthorizationManager`, and Spring recommends this newer authorization API rather than the older `AccessDecisionManager`/`AccessDecisionVoter` model.  

---

## **1. Our ProjectHub rule**

Let’s define this clearly.

A user can delete a post when:

```text
posts.delete
AND
(
    user owns the post
    OR
    user is OWNER of the project
)
```

So:

```text
                    posts.delete?
                         │
                  ┌──────┴──────┐
                  NO            YES
                  │              │
                DENY       owns post?
                               │
                         ┌─────┴─────┐
                        YES          NO
                         │            │
                       ALLOW    project owner?
                                      │
                                ┌─────┴─────┐
                               YES          NO
                                │            │
                              ALLOW        DENY
```

This is a **policy**.

---

# **2. Why this shouldn’t be a giant annotation**

We could write:

```java
@PreAuthorize("""
    hasAuthority('posts.delete')
    and (
        @postAuthorizationService.isOwner(#postId, authentication)
        or
        @postAuthorizationService.isProjectOwner(#postId, authentication)
    )
""")
```

Technically, this is possible.

But imagine six months later:

```text
OWNER → can delete
ADMIN → can delete
AUTHOR → can delete
MODERATOR → can delete
ARCHIVED project → cannot delete
LOCKED post → cannot delete
```

The annotation becomes difficult to read and test.

Instead, make the policy explicit in Java.

---

# **3. Create a policy object**

Think:

```text
PostDeletionPolicy
```

Its job is simply:

Given a user and a post, can this user delete it?

For example:

```java
@Component
public class PostDeletionPolicy {

    public boolean canDelete(
            Authentication authentication,
            Long postId) {

        // determine whether deletion is allowed
    }
}
```

Then your service can use:

```java
@PreAuthorize(
    "hasAuthority('posts.delete') " +
    "and @postDeletionPolicy.canDelete(authentication, #postId)"
)
public void deletePost(Long postId) {
    ...
}
```

Now the annotation remains understandable.

---

# **4. The policy needs current database information**

The JWT might tell us:

```text
Alice
posts.delete
```

But it probably doesn’t tell us:

```text
Post 42 → Project 7
Alice → Project 7 → OWNER
```

Those are dynamic relationships.

So the policy can query the database.

For example:

```text
Post
 ├── id = 42
 ├── author = Bob
 └── project = 7

ProjectMembership
 ├── user = Alice
 ├── project = 7
 └── role = OWNER
```

The policy can determine:

```text
Alice owns post?
NO

Alice owns project?
YES

→ ALLOW
```

---

# **5. Important distinction: global vs resource-scoped permissions**

This distinction is worth memorizing.

### **Global authority**

```text
posts.delete
```

Means:

This user possesses the general capability of deleting posts.

### **Project membership**

```text
Project 7 → OWNER
```

Means:

This user has a particular relationship with Project 7.

Together:

```text
posts.delete
+
Project 7 OWNER
```

can produce:

```text
Can delete Post 42?
YES
```

Spring Security’s domain-object authorization documentation describes this general problem as authorization decisions that depend on the authenticated user **and the actual domain object**.  

---

# **6. Let’s design the repositories**

We want to avoid loading a giant object graph just to answer authorization questions.

For ownership:

```java
boolean existsByIdAndAuthorUsername(
    Long postId,
    String username
);
```

For the project:

```java
Optional<Long> findProjectIdByPostId(Long postId);
```

And for membership:

```java
boolean existsByProjectIdAndUserIdAndRole(
    Long projectId,
    Long userId,
    ProjectRole role
);
```

The exact queries can vary, but the principle is:

Ask the database the smallest question necessary for the authorization decision.

---

# **7. The policy**

Conceptually:

```java
@Component
public class PostDeletionPolicy {

    private final PostRepository postRepository;
    private final ProjectMembershipRepository membershipRepository;

    public PostDeletionPolicy(
            PostRepository postRepository,
            ProjectMembershipRepository membershipRepository) {

        this.postRepository = postRepository;
        this.membershipRepository = membershipRepository;
    }

    public boolean canDelete(
            Authentication authentication,
            Long postId) {

        String username = authentication.getName();

        if (postRepository.existsByIdAndAuthorUsername(
                postId, username)) {
            return true;
        }

        Long projectId =
                postRepository.findProjectIdByPostId(postId)
                        .orElse(null);

        if (projectId == null) {
            return false;
        }

        return membershipRepository
                .existsByProjectIdAndUsernameAndRole(
                        projectId,
                        username,
                        ProjectRole.OWNER
                );
    }
}
```

Don’t copy this blindly yet.

I want you to understand the architecture first.

---

# 

# **8. Why the policy doesn’t check**

**`posts.delete`**

Notice something.

The policy asks:

```text
Does Alice own this post?
OR
Is Alice the project owner?
```

It doesn’t ask:

```text
Does Alice have posts.delete?
```

Why?

Because we’ve separated responsibilities.

### **Spring Security expression**

```java
hasAuthority("posts.delete")
```

answers:

Does the user possess the general capability?

### **Policy**

```text
canDelete(postId)
```

answers:

Does that capability apply to this particular resource?

That’s much cleaner.

---

# **9. Service method**

Now the service becomes:

```java
@PreAuthorize(
    "hasAuthority('posts.delete') " +
    "and @postDeletionPolicy.canDelete(authentication, #postId)"
)
@Transactional
public void deletePost(Long postId) {

    Post post = postRepository.findById(postId)
            .orElseThrow(() ->
                    new PostNotFoundException(postId));

    postRepository.delete(post);
}
```

The security rule reads almost like English:

```text
Must have posts.delete
AND
must satisfy the post deletion policy
```

---

# **10. But there’s another problem**

Suppose Alice is:

```text
Project 7 → OWNER
```

and Bob is:

```text
Post 42 → author
```

Alice can delete Bob’s post.

That’s intentional.

But now imagine:

```text
Project 7 → ARCHIVED
```

Should Alice still be able to delete it?

Maybe not.

The policy can now evolve:

```text
posts.delete
AND
project is active
AND
(
    owns post
    OR
    project owner
)
```

This is exactly why we don’t want authorization rules scattered across controllers.

The policy gives us one place to reason about the rule.

---

# **11. Authorization is not the same as business validation**

This distinction is subtle.

### **Authorization**

```text
Can Alice perform this operation?
```

### **Validation**

```text
Is this request structurally valid?
```

### **Business rule**

```text
Is deleting a post allowed given the current state?
```

These can overlap.

For example:

```text
Authorization:
    Alice has posts.delete

Resource authorization:
    Alice owns the project

Business rule:
    project isn't archived

Validation:
    postId is a valid Long
```

A real application may enforce all four.

---

# 

# 

# **12. Where**

**`AuthorizationManager`**

**enters the picture**

So far we’ve used:

```java
@PreAuthorize(...)
```

Under the hood, Spring Security converts method-security annotations into authorization managers. For `@PreAuthorize`, the framework uses `PreAuthorizeAuthorizationManager`.  

Spring Security also lets you create your own `AuthorizationManager<T>`.

The interface conceptually looks like:

```java
AuthorizationResult authorize(
    Supplier<Authentication> authentication,
    T object
);
```

It receives:

```text
Authentication
+
object being authorized
```

and produces an authorization result.  

This is the modern extension point when authorization becomes more sophisticated.

---

# 

# 

# **13. When should we use a custom**

**`AuthorizationManager`**

**?**

Don’t reach for one immediately.

For ProjectHub:

### **Simple**

```java
@PreAuthorize("hasAuthority('posts.read')")
```

Excellent.

### **Moderate**

```java
@PreAuthorize(
    "hasAuthority('posts.delete') " +
    "and @postDeletionPolicy.canDelete(authentication, #postId)"
)
```

Still reasonable.

### **Very complex / reusable**

```text
PostDeletionAuthorizationManager
```

might make sense.

For example, if the exact same authorization policy is needed by:

```text
REST
GraphQL
message handlers
multiple services
```

a reusable authorization component can be valuable.

Spring Security explicitly supports custom `AuthorizationManager` implementations for application-specific authorization logic.  

---

# **14. Don’t confuse this with old Spring Security tutorials**

You will find older tutorials using:

```text
AccessDecisionManager
AccessDecisionVoter
```

For a new ProjectHub application, **don’t start there**.

Spring Security 7 moved those APIs into a legacy module and recommends the newer Authorization API for new applications.  

Your mental model should be:

```text
OLD:
AccessDecisionManager
AccessDecisionVoter

NEW:
AuthorizationManager
```

---

# **15. Project-scoped roles**

Let’s make our ProjectHub model more concrete.

Global roles:

```text
ADMIN
USER
```

Permissions:

```text
posts.read
posts.create
posts.delete
projects.read
projects.create
projects.update
```

Project membership:

```text
OWNER
MEMBER
```

Now consider:

|**User**|**Global**|**Project 7**|`posts.delete`|**Can delete Bob’s post?**|
|---|---|---|---|---|
|Alice|USER|OWNER|yes|Yes|
|Bob|USER|MEMBER|yes|Depends on ownership policy|
|Carol|USER|OWNER|no|No|
|Dave|ADMIN|MEMBER|yes|Depends on your global-admin policy|

Notice the last column is **not determined by the global role alone**.

That’s resource authorization.

---

# 

# 

# **16. What about**

**`ADMIN`**

**?**

We need to explicitly define our policy.

For example, we might decide:

```text
ADMIN + posts.delete → can delete any post
```

Then our policy becomes:

```text
if admin:
    allow

else if owner of post:
    allow

else if project owner:
    allow

else:
    deny
```

But remember:

**`ADMIN`** **automatically bypassing all resource checks is a business decision, not a Spring Security requirement.**

We define the rule.

---

# **17. Policy composition**

We’re now approaching a useful pattern:

```text
Permission
    ↓
Resource policy
    ↓
Business-state policy
```

For example:

```text
Can Alice delete Post 42?

    posts.delete?
       ↓
    project exists?
       ↓
    project active?
       ↓
    Alice owns post?
       OR
    Alice owns project?
       ↓
    ALLOW / DENY
```

This is much closer to real-world authorization systems.

---

# **18. One more important security principle**

**Never trust the client to tell you whether the user is allowed to do something.**

For example, don’t accept:

```json
{
  "projectId": 7,
  "role": "OWNER"
}
```

and then trust:

```text
role = OWNER
```

The client controls that request.

Instead:

```text
JWT → identity/authorities
Database → current membership
Policy → authorization decision
```

The server determines the truth.

---

# **19. ProjectHub’s evolving architecture**

We’re now at:

```text
                   HTTP Request
                        │
                        ▼
                  JWT validation
                        │
                        ▼
                  Authentication
                        │
                        ▼
               Global authorities
                        │
                        ▼
                Method security
                        │
                        ▼
              Resource policy
                        │
                        ▼
              Project membership
                        │
                        ▼
                 Business rules
                        │
                        ▼
                    Service
                        │
                        ▼
                  PostgreSQL
```

This is a very important milestone.

You’ve moved from:

```text
"Is the user logged in?"
```

to:

```text
"Is this authenticated user allowed to perform
this particular operation on this particular resource
given the current state of the system?"
```

---

# **Exercise 25**

Implement the following **without looking for a more complicated solution yet**.

### **Requirement**

Alice can delete a post if:

```text
posts.delete
AND
(
    Alice owns the post
    OR
    Alice is OWNER of the post's project
)
```

Create:

```text
PostDeletionPolicy
```

with:

```java
boolean canDelete(
    Authentication authentication,
    Long postId
)
```

Then protect:

```java
deletePost(Long postId)
```

with `@PreAuthorize`.

### **Test these cases**

```text
1. Alice has posts.delete
   Alice owns post
   → allowed

2. Alice has posts.delete
   Alice doesn't own post
   Alice is project OWNER
   → allowed

3. Alice has posts.delete
   Alice doesn't own post
   Alice is project MEMBER
   → denied

4. Alice doesn't have posts.delete
   Alice owns post
   → denied

5. Alice doesn't have posts.delete
   Alice is project OWNER
   → denied
```

**Don’t implement** **`AuthorizationManager`** **yet.** First get the policy working cleanly with `@PreAuthorize`.

Next we’ll take this one step further into **Lesson 26: testing security and authorization**—we’ll verify that these five scenarios actually produce the correct `200/204/403` behavior rather than trusting our code by inspection.