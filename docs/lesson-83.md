---
title: "Lesson 83: Testing Spring Security"
sidebar_position: 83
---

This one is important because we spent a lot of time building ProjectHub’s authorization system.

We want tests that prove:

```text
anonymous          → 401
authenticated      → allowed when authorized
wrong permission   → 403
correct permission → allowed
```

Spring Security has dedicated testing support for MockMvc and method security.  

---

## **1. Test the actual permission, not just the role**

Remember our model:

```text
Role
  ↓
Permissions

ADMIN
 ├── posts.read
 ├── posts.create
 └── posts.delete
```

And our application might have:

```java
@PreAuthorize("hasAuthority('posts.delete')")
public void deletePost(Long postId) {
    // ...
}
```

Method security must be enabled with `@EnableMethodSecurity`.  

The test should therefore create a user with the **actual authority**:

```java
@WithMockUser(
    username = "alice",
    authorities = {
        "posts.read",
        "posts.create"
    }
)
```

`@WithMockUser(authorities = ...)` uses exactly the authorities you specify; unlike `roles`, Spring does **not** automatically add `ROLE_`.  

That’s particularly useful for our permission-based design.

---

# **2. The important test matrix**

For:

```java
@PreAuthorize("hasAuthority('posts.delete')")
```

we want at least:

|**User**|**Authority**|**Expected**|
|---|---|---|
|anonymous|none|`401`|
|Alice|`posts.read`|`403`|
|Bob|`posts.delete`|allowed|
|Admin|`posts.delete`|allowed|

That matrix is much more valuable than having one giant “security test.”

---

# **3. Controller-level security test**

With MockMvc, we can simulate the HTTP request:

```java
mockMvc.perform(
    delete("/posts/42")
        .with(user("alice")
            .authorities("posts.read"))
)
.andExpect(status().isForbidden());
```

Then:

```java
mockMvc.perform(
    delete("/posts/42")
        .with(user("bob")
            .authorities("posts.delete"))
)
.andExpect(status().isNoContent());
```

Spring Security provides the `user(...)` request post-processor specifically for this style of MockMvc testing.  

---

# 

# 

# **4.**

**`@WithMockUser`**

**is another option**

Instead of attaching the user to each request:

```java
@WithMockUser(
    username = "bob",
    authorities = "posts.delete"
)
@Test
void canDeletePost() {
    ...
}
```

Spring Security populates the test `SecurityContext` with that mocked authentication.  

For controller tests, I generally like:

```text
.with(user(...))
```

because the authorization is visible right beside the HTTP request.

For service/method-security tests:

```text
@WithMockUser(...)
```

is often cleaner.

---

# **5. Test method security directly**

Suppose:

```java
@Service
public class PostService {

    @PreAuthorize("hasAuthority('posts.delete')")
    public void deletePost(Long id) {
        // ...
    }
}
```

You can test the method itself:

```java
@Test
@WithMockUser(
    authorities = "posts.delete"
)
void userWithPermissionCanDelete() {
    service.deletePost(42L);
}
```

And:

```java
@Test
@WithMockUser(
    authorities = "posts.read"
)
void userWithoutPermissionCannotDelete() {
    assertThatThrownBy(
        () -> service.deletePost(42L)
    ).isInstanceOf(AccessDeniedException.class);
}
```

Spring Security’s documentation specifically demonstrates testing `@PreAuthorize` methods with `@WithMockUser`.  

---

# 

# 

# 

# **6. Don’t forget**

**`401`**

**vs**

**`403`**

This distinction should become automatic for you.

### **`401 Unauthorized`**

```text
No authentication
       ↓
protected endpoint
       ↓
401
```

### **`403 Forbidden`**

```text
Authenticated
       ↓
missing required authority
       ↓
403
```

So:

```text
401 → "Who are you?"

403 → "I know who you are,
       but you're not allowed."
```

---

# **7. One more important limitation**

`@WithMockUser` is excellent for MockMvc and method-security tests, but it isn’t pretending to perform your entire real JWT login flow.

For an actual end-to-end HTTP test, you eventually want:

```text
POST /auth/login
      ↓
real authentication
      ↓
JWT
      ↓
Authorization: Bearer ...
      ↓
protected endpoint
```

Spring Security’s documentation explicitly distinguishes mocked security contexts from full HTTP requests, where the request itself needs to carry authentication such as a bearer token.  

We’ll cover that when we do the integration tests.

---

# **What you’ve now learned**

Your security test strategy should look like:

```text
                 Security Tests
                       │
          ┌────────────┴────────────┐
          │                         │
     Method Security           HTTP Security
          │                         │
   @PreAuthorize              MockMvc
   @WithMockUser              user(...)
          │                         │
          └────────────┬────────────┘
                       │
                  JWT integration
                       │
                 Testcontainers
```

That’s enough security testing theory.

## **Next: Lesson 84 — Database integration tests**

We’ll move from mocked repositories to the **real PostgreSQL database**:

```text
Test
 ↓
Spring Boot
 ↓
JPA/Hibernate
 ↓
PostgreSQL
```

Then we’ll introduce **Testcontainers**, which is where backend testing starts feeling much more like production.