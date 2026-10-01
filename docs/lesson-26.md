---
title: "Lesson 26: Testing Spring Security"
sidebar_position: 26
---

We’ve built authentication, JWTs, permissions, and resource-level authorization.

Now we need to prove that they actually work.

A security system that _looks_ correct isn’t enough. We need automated tests for cases like:

```text
authenticated + permission + owns resource     → allowed
authenticated + permission + doesn't own        → denied
authenticated + no permission                   → denied
anonymous                                       → denied
```

Spring Security 7.1.1 provides dedicated testing support for method security, MockMvc, authentication, JWTs, CSRF, and security assertions.  

---

## **1. The three levels of security testing**

For ProjectHub, we’ll eventually use three layers:

### **1. Unit test**

Test a policy directly:

```text
PostDeletionPolicy
        ↓
does Alice satisfy the rule?
```

Fast and isolated.

### **2. Method-security test**

Test:

```java
@PreAuthorize(...)
```

actually prevents unauthorized method calls.

### **3. HTTP integration test**

Test the whole path:

```text
HTTP
 ↓
SecurityFilterChain
 ↓
Controller
 ↓
Method security
 ↓
Service
 ↓
Database
```

This is where `MockMvc` becomes very useful.

---

# **2. Add Spring Security Test**

Your test dependencies should include Spring Security’s test module.

For Maven:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

Spring’s current documentation identifies `spring-security-test` as the module providing this testing support.  

---

# **3. Testing a secured service**

Suppose we have:

```java
@Service
public class PostService {

    @PreAuthorize("hasAuthority('posts.delete')")
    public void deletePost(Long postId) {
        // ...
    }
}
```

We need to test:

```text
posts.delete → allowed
no posts.delete → denied
```

Spring Security provides:

```java
@WithMockUser
```

which creates a mock authenticated user for the test.  

For example:

```java
@Test
@WithMockUser(
    username = "alice",
    authorities = "posts.delete"
)
void userWithDeletePermissionCanDelete() {

    postService.deletePost(42L);
}
```

The important thing is:

```java
authorities = "posts.delete"
```

not:

```java
roles = "posts.delete"
```

Remember our distinction:

```text
ROLE_ADMIN
```

is a role-style authority.

Whereas:

```text
posts.delete
```

is our actual permission authority.

Spring Security’s `@WithMockUser` supports explicitly supplying authorities without automatically adding the `ROLE_` prefix.  

---

# **4. Testing denial**

Now:

```java
@Test
@WithMockUser(
    username = "alice",
    authorities = "posts.read"
)
void userWithoutDeletePermissionCannotDelete() {

    assertThatThrownBy(() ->
        postService.deletePost(42L)
    );
}
```

Conceptually:

```text
Alice
 ↓
posts.read
 ↓
@PreAuthorize("hasAuthority('posts.delete')")
 ↓
DENIED
```

Spring Security’s method-security tests demonstrate that an unauthorized method invocation results in a security exception.  

---

# **5. The important part: test resource authorization**

Our real rule is more interesting:

```java
@PreAuthorize(
    "hasAuthority('posts.delete') " +
    "and @postDeletionPolicy.canDelete(authentication, #postId)"
)
```

Now we have two independent things to test.

### **Case A**

```text
Alice
posts.delete
owns post
```

→ allowed

### **Case B**

```text
Alice
posts.delete
doesn't own post
not project owner
```

→ denied

### **Case C**

```text
Alice
no posts.delete
owns post
```

→ denied

### **Case D**

```text
Alice
posts.delete
project owner
doesn't own post
```

→ allowed, according to our current policy.

These tests are much more valuable than simply testing whether the controller returns something.

---

# 

# 

# **6.**

**`@WithMockUser`**

**does not create a database user**

This is important.

If you write:

```java
@WithMockUser(username = "alice")
```

Spring does **not** insert Alice into PostgreSQL.

It creates a mock security context for the test.  

So:

```text
@WithMockUser
        ↓
SecurityContext
        ↓
Authentication
```

not:

```text
@WithMockUser
        ↓
PostgreSQL
        ↓
users table
```

This makes it excellent for testing security logic in isolation.

---

# **7. What if we need a real user?**

Spring Security also provides:

```java
@WithUserDetails("alice")
```

This uses your application’s `UserDetailsService` to load the user.  

That is useful when your authentication principal is custom or when you want the test to use the application’s actual user-loading logic.

So:

### **`@WithMockUser`**

Good for:

```text
"Give me an authenticated user with these authorities."
```

### **`@WithUserDetails`**

Good for:

```text
"Load this user through my real UserDetailsService."
```

---

# **8. Testing the HTTP layer with MockMvc**

Now let’s move outward.

Suppose:

```http
DELETE /posts/42
```

We want to test the actual HTTP response.

Spring Security integrates with Spring MVC’s `MockMvc`, and its testing support can install the security filter chain into the MockMvc instance.  

A typical setup is:

```java
@BeforeEach
void setUp() {
    mvc = MockMvcBuilders
            .webAppContextSetup(context)
            .apply(springSecurity())
            .build();
}
```

The important part is:

```java
.apply(springSecurity())
```

because that integrates Spring Security into the MockMvc request processing.  

---

# **9. Authenticate a MockMvc request**

Spring Security gives us request processors.

For example:

```java
mvc.perform(
    delete("/posts/42")
        .with(user("alice")
            .authorities(
                new SimpleGrantedAuthority("posts.delete")
            ))
);
```

This lets the request execute as Alice with the specified authority. Spring Security’s MockMvc support provides request post-processors for creating authenticated users.  

---

# **10. Testing a JWT endpoint**

This is particularly useful for our ProjectHub application.

Spring Security’s test support provides:

```java
.with(jwt())
```

which creates a mock `JwtAuthenticationToken` without requiring a real JWT to be generated and cryptographically validated for that particular test.  

For example:

```java
mvc.perform(
    delete("/posts/42")
        .with(jwt()
            .authorities(
                new SimpleGrantedAuthority("posts.delete")
            ))
);
```

Conceptually:

```text
MockMvc
 ↓
SecurityFilterChain
 ↓
mock JwtAuthenticationToken
 ↓
posts.delete
 ↓
Controller
```

This is extremely useful for testing resource authorization without making every test go through the real login/JWT-generation flow.

---

# **11. Why we don’t generate real JWTs in every test**

You could:

```text
login
 ↓
AuthenticationManager
 ↓
generate JWT
 ↓
send JWT
 ↓
decode JWT
 ↓
authorize
```

But then every authorization test becomes much more complicated.

Most tests don’t need to verify:

Does RSA signing work?

They need to verify:

Does Alice with `posts.delete` have permission to delete post 42?

So isolate the concerns.

### **JWT tests**

Verify:

```text
token creation
token validation
claims
expiration
authority mapping
```

### **Authorization tests**

Verify:

```text
permission
ownership
project membership
policy
```

### **End-to-end tests**

Verify that everything works together.

---

# **12. A useful testing pyramid**

Think:

```text
             ┌──────────────────┐
             │  End-to-end HTTP │
             │      tests       │
             └────────┬─────────┘
                      │
             ┌────────┴─────────┐
             │   MockMvc /      │
             │ integration      │
             └────────┬─────────┘
                      │
             ┌────────┴─────────┐
             │   Policy /       │
             │   service tests  │
             └──────────────────┘
```

The bottom should have many fast tests.

The top should have fewer tests because they’re more expensive.

---

# **13. Testing our five deletion scenarios**

Let’s translate our previous exercise into tests.

### **1. Permission + ownership**

```text
Alice
posts.delete
owns post
```

Expected:

```text
204 No Content
```

### **2. Permission + project ownership**

```text
Alice
posts.delete
doesn't own post
project owner
```

Expected:

```text
204
```

### **3. Permission but no resource access**

```text
Alice
posts.delete
doesn't own post
project member
```

Expected:

```text
403
```

### **4. No permission, owns post**

```text
Alice
posts.read
owns post
```

Expected:

```text
403
```

### **5. No permission, project owner**

```text
Alice
posts.read
project owner
```

Expected:

```text
403
```

That last one is important.

Being a project owner doesn’t magically grant every global permission unless **we explicitly define that policy**.

---

# **14. Testing anonymous requests**

We also need:

```text
no authentication
```

For example:

```java
@Test
void anonymousCannotDeletePost() throws Exception {

    mvc.perform(delete("/posts/42"))
        .andExpect(status().isUnauthorized());
}
```

The exact status depends on your security configuration and authentication mechanism, but the important distinction remains:

```text
401
```

means:

authentication is required but wasn’t successfully established.

While:

```text
403
```

means:

the request is authenticated, but the authenticated principal isn’t authorized.

---

# **15. CSRF: an important testing trap**

If your application uses cookie/session authentication with CSRF protection, non-safe methods such as:

```text
POST
PUT
PATCH
DELETE
```

may require a CSRF token in MockMvc tests. Spring Security’s testing support provides:

```java
.with(csrf())
```

for this purpose.  

For our ProjectHub JWT API, we’ll generally configure the API as stateless and handle CSRF according to that architecture.

The important lesson is:

Don’t randomly add `.with(csrf())` until a test passes. Understand whether your authentication architecture actually requires CSRF protection.

---

# **16. Don’t test implementation details**

Bad test:

```text
verify that PostService called
postRepository.findById()
exactly once
```

That can be useful in a narrow unit test, but it shouldn’t be the main security test.

Better:

```text
Alice with posts.delete
and ownership
→ DELETE succeeds
```

because that’s the behavior the user actually cares about.

---

# **17. Test the security boundary**

For our application, the most valuable test looks like:

```text
HTTP request
      ↓
Authentication
      ↓
Authorization
      ↓
Business operation
```

For example:

```java
mvc.perform(
    delete("/posts/42")
        .with(jwt()
            .authorities(
                new SimpleGrantedAuthority("posts.delete")
            ))
)
.andExpect(status().isNoContent());
```

The test doesn’t care whether your implementation uses:

```text
PostRepository A
```

or:

```text
PostRepository B
```

It cares that the authorization contract is correct.

---

# **18. One more subtlety: mock JWT authorities**

Our real JWT converter maps:

```json
{
  "authorities": [
    "posts.read",
    "posts.create",
    "posts.delete"
  ]
}
```

into:

```text
GrantedAuthority
```

When testing with:

```java
.with(jwt())
```

we can directly provide the authorities.

That means we’re intentionally skipping:

```text
JWT claim
 ↓
JwtGrantedAuthoritiesConverter
 ↓
GrantedAuthority
```

for an authorization-focused test.

That is okay.

Then we separately test the converter.

---

# **19. What we eventually need to test**

ProjectHub security will eventually have tests around:

### **Authentication**

```text
valid username/password
invalid password
unknown user
disabled user
```

### **JWT**

```text
valid signature
expired token
wrong issuer
invalid signature
authority mapping
```

### **Permissions**

```text
posts.read
posts.create
posts.delete
```

### **Resource authorization**

```text
owner
project owner
project member
unrelated user
```

### **Refresh tokens**

```text
valid refresh
expired refresh
revoked refresh
rotated refresh
reused refresh
```

### **HTTP**

```text
401
403
200
201
204
```

This is how security becomes something we can trust rather than something we merely assume works.

---

# **Exercise 26**

Don’t write all of these yet.

Start with **three tests** for our `deletePost` endpoint:

### **Test 1**

```text
Alice
posts.delete
owns post 42
```

Expected:

```text
204
```

### **Test 2**

```text
Alice
posts.delete
doesn't own post 42
not project owner
```

Expected:

```text
403
```

### **Test 3**

```text
Alice
posts.read
owns post 42
```

Expected:

```text
403
```

Use **MockMvc +** **`jwt()`** rather than generating a real JWT.

Once you’ve written those three tests, send them to me. I’ll review them and we’ll move to **Lesson 27 — Testing with PostgreSQL and Testcontainers**, where our authorization tests stop using fake repository state and start running against a real PostgreSQL database.