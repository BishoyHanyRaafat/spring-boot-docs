---
title: Lesson 17: Spring Security Fundamentals
sidebar_position: 17
---

Now we enter one of the most important parts of Spring Boot:

**security.**

We’ll build this gradually. Don’t jump straight to JWT yet.

First, we need to understand the vocabulary and architecture.

The current Spring Security stable line is **7.1.1** according to the official documentation. Spring Security supports both request-based and method-based authorization.  

---

# **1. What problem does Spring Security solve?**

Suppose ProjectHub has:

```text
GET    /posts/10
POST   /projects/5/posts
DELETE /posts/10
```

Without security, anyone who can reach the server might be able to call them.

We need rules like:

```text
Anyone?
    GET /posts/10

Authenticated users?
    POST /projects/5/posts

Users with posts.delete?
    DELETE /posts/10
```

And eventually:

```text
Can Alice delete Bob's post?
```

That’s authorization.

But before authorization, we need authentication.

---

# **2. Authentication vs Authorization**

This distinction is fundamental.

### **Authentication**

**Who are you?**

For example:

```text
username: alice
password: ********
```

The system verifies Alice’s identity.

Result:

```text
Authenticated user = Alice
```

### **Authorization**

**What are you allowed to do?**

Alice might have:

```text
posts.read
posts.create
posts.delete
```

Bob might have:

```text
posts.read
posts.create
```

So:

```text
Authentication
     ↓
Who is Alice?

Authorization
     ↓
Can Alice perform this operation?
```

Spring Security provides both authentication and authorization functionality.  

---

# **3. A useful mental model**

Think of entering an office.

### **Authentication**

Security guard asks:

“Who are you?”

You show your ID.

### **Authorization**

The guard checks:

“What rooms can this person enter?”

You might have access to:

```text
Room A
Room B
```

but not:

```text
Room C
```

That’s exactly the distinction.

---

# **4. Spring Security sits in front of your controllers**

Earlier our request looked like:

```text
HTTP
 ↓
Controller
 ↓
Service
 ↓
Repository
```

Now:

```text
HTTP
 ↓
Spring Security
 ↓
Controller
 ↓
Service
 ↓
Repository
```

More accurately, Spring Security uses a filter chain around the request processing.

A simplified picture:

```text
Request
   │
   ▼
Security Filters
   │
   ├── Authentication
   │
   ├── Security Context
   │
   └── Authorization
   │
   ▼
Spring MVC
   │
   ▼
Controller
```

The official architecture documentation shows authentication-related filters occurring before the authorization filter in the security filter chain.  

---

# **5. SecurityFilterChain**

This is one of the first Spring Security concepts you’ll see.

Modern configuration looks roughly like:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        );

    return http.build();
}
```

Don’t worry about every piece yet.

The important part is:

```java
SecurityFilterChain
```

It defines security behavior for incoming requests.

Spring Security’s current API uses `SecurityFilterChain` together with `HttpSecurity` to configure request security.  

---

# 6. What does `authenticated()` mean?

This:

```java
.anyRequest().authenticated()
```

means:

Every request must come from an authenticated user.

So:

```text
GET /posts/10
```

without authentication:

```text
401 Unauthorized
```

With authentication:

```text
→ request continues
```

The important distinction:

### **401**

You aren’t authenticated.

### **403**

You are authenticated, but aren’t authorized.

For example:

```text
Alice is logged in
Alice doesn't have posts.delete
Alice calls DELETE /posts/10

→ 403 Forbidden
```

---

# **7. Public endpoints**

Not everything needs authentication.

For example:

```text
POST /auth/register
POST /auth/login
GET  /public/posts
```

could be public.

We can say:

```java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/auth/**").permitAll()
    .anyRequest().authenticated()
)
```

Conceptually:

```text
/auth/**       → public
everything else → authenticated
```

Spring Security’s request authorization API supports rules such as `permitAll`, `authenticated`, `hasAuthority`, and `hasRole`.  

---

# **8. Authorities**

Now we get to the part that directly connects to what you’ve already learned.

Spring Security represents permissions through:

```java
GrantedAuthority
```

For example:

```text
posts.read
posts.create
posts.delete
```

An authenticated user might have:

```text
Authentication
    │
    └── authorities
          ├── posts.read
          ├── posts.create
          └── posts.delete
```

Then we can write:

```java
.hasAuthority("posts.delete")
```

Meaning:

The authenticated user must have the `posts.delete` authority.

Spring Security’s request authorization API defines `hasAuthority` as requiring a matching `GrantedAuthority`.  

---

# **9. Roles**

Roles are another concept.

For example:

```text
ADMIN
USER
MODERATOR
```

You might give:

```text
ADMIN
 ├── posts.read
 ├── posts.create
 ├── posts.delete
 ├── users.read
 └── users.delete
```

while:

```text
USER
 ├── posts.read
 └── posts.create
```

A role is therefore often a **grouping of authorities/permissions**.

Spring Security provides:

```java
hasRole("ADMIN")
```

as a shortcut around role authorities with the configured role prefix.  

---

# **10. Roles vs permissions**

For ProjectHub, I want you to keep this distinction clear:

```text
Role
 ↓
group of permissions

Permission
 ↓
specific capability
```

Example:

```text
ADMIN
 ├── posts.read
 ├── posts.create
 ├── posts.delete
 ├── users.read
 └── users.delete
```

Then:

```text
MODERATOR
 ├── posts.read
 ├── posts.delete
 └── comments.delete
```

And:

```text
USER
 ├── posts.read
 └── posts.create
```

The permission is the more precise statement.

---

# **11. Your permission model**

Remember our ProjectHub design:

```text
posts.read
posts.create
posts.delete
```

I like this much more than inventing arbitrary numeric values as the source of truth.

For example:

```text
posts.read   → 1
posts.create → 2
posts.delete → 4
```

could theoretically be used internally as a bitmask.

But your actual business concept remains:

```text
posts.read
posts.create
posts.delete
```

Spring Security naturally works with named authorities.

So we’ll keep the names as our source of truth.

---

# **12. Request-level authorization**

We can authorize based on URL/method.

For example:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {

    http.authorizeHttpRequests(authorize -> authorize

        .requestMatchers(HttpMethod.GET, "/posts/**")
            .hasAuthority("posts.read")

        .requestMatchers(HttpMethod.POST, "/projects/*/posts")
            .hasAuthority("posts.create")

        .requestMatchers(HttpMethod.DELETE, "/posts/**")
            .hasAuthority("posts.delete")

        .anyRequest()
            .authenticated()
    );

    return http.build();
}
```

Conceptually:

```text
GET /posts/**
    ↓
posts.read

POST /projects/*/posts
    ↓
posts.create

DELETE /posts/**
    ↓
posts.delete
```

This is **request-level authorization**.

Spring Security explicitly supports this style through `authorizeHttpRequests`.  

---

# **13. But there’s a problem**

Suppose:

```text
Alice
 └── posts.delete
```

Alice sends:

```text
DELETE /posts/500
```

Spring Security can determine:

```text
Alice has posts.delete
```

But it doesn’t automatically know:

```text
Post 500 belongs to Bob
```

This is a **resource-level/business authorization** problem.

That’s why permissions alone aren’t enough for many real systems.

---

# **14. Method security**

Spring Security also allows authorization at the method level.

First:

```java
@EnableMethodSecurity
```

Then:

```java
@PreAuthorize("hasAuthority('posts.delete')")
public void deletePost(Long postId) {
    ...
}
```

Spring Security’s current documentation recommends method security for fine-grained authorization and supports annotations such as `@PreAuthorize` and `@PostAuthorize`.  

This gives us:

```text
HTTP
 ↓
request authorization
 ↓
Controller
 ↓
Service
 ↓
method authorization
 ↓
business logic
```

That’s defense in depth.

---

# **15. Why authorize at the service layer?**

Imagine today:

```text
REST Controller
```

calls:

```text
PostService
```

Tomorrow you add:

```text
Scheduled job
```

that calls:

```text
PostService
```

Or:

```text
Message consumer
```

calls:

```text
PostService
```

If authorization exists only in the HTTP controller, another caller might bypass it.

Method-level security can protect the service method itself.

Spring Security specifically documents method security as useful for enforcing authorization at the service layer.  

---
# 16. `@PreAuthorize`

For our permissions:

```java
@PreAuthorize("hasAuthority('posts.create')")
public PostResponse createPost(...) {
    ...
}
```

And:

```java
@PreAuthorize("hasAuthority('posts.delete')")
public void deletePost(...) {
    ...
}
```

Now the method won’t execute unless the authorization expression passes.

Conceptually:

```text
Caller
  ↓
Spring Security proxy
  ↓
Does user have posts.delete?
  │
  ├── No → AccessDeniedException
  │
  └── Yes
        ↓
     deletePost()
```

The current Spring Security documentation describes method authorization as being implemented through Spring AOP interceptors around the method invocation.  

---

#  17. `hasRole` vs `hasAuthority`

This is a common source of confusion.

```java
hasRole("ADMIN")
```

and:

```java
hasAuthority("ROLE_ADMIN")
```

are related.

By default, role checks use the `ROLE_` prefix.

So:

```java
hasRole("ADMIN")
```

conceptually checks:

```text
ROLE_ADMIN
```

Whereas:

```java
hasAuthority("posts.delete")
```

checks exactly:

```text
posts.delete
```

That’s another reason I want us to use:

```text
posts.read
posts.create
posts.delete
```

for permissions.

---

# **18. The `Authentication` object**

Once a user is authenticated, Spring Security has an:

```java
Authentication
```

object representing the current authentication.

Conceptually:

```text
Authentication
│
├── principal
│      ↓
│    User
│
├── authorities
│      ├── posts.read
│      ├── posts.create
│      └── posts.delete
│
└── authenticated
       ↓
      true
```

You can access the current authentication in Spring Security-aware code.

For example:

```java
Authentication authentication =
        SecurityContextHolder
            .getContext()
            .getAuthentication();
```

We’ll later make this much cleaner when we build our authenticated-user abstraction.

---

# **19. SecurityContext**

Where does the current authentication live?

Conceptually:

```text
SecurityContext
       │
       └── Authentication
```

Spring Security maintains a security context associated with the current execution.

So when your service asks:

```text
"Who is currently authenticated?"
```

Spring Security can provide the authentication.

This is one of the reasons you don’t want to pass:

```java
Long userId
```

through every single controller method manually once authentication is properly implemented.

---

# **20. Authentication mechanisms**

There are many ways a user can authenticate.

For example:

```text
Username + password
       ↓
session

Username + password
       ↓
JWT

OAuth2 / OpenID Connect
       ↓
external identity provider

API key
       ↓
application/client authentication
```

Spring Security supports many authentication mechanisms.

But these are separate from authorization.

That’s important.

You could authenticate someone using:

```text
JWT
```

and then authorize them using:

```text
posts.delete
```

The authorization model doesn’t fundamentally depend on JWT.

---

# **21. Our roadmap from here**

We’re going to build security in layers.

### **Lesson 17 — today**

```text
Authentication
Authorization
Roles
Authorities
Permissions
SecurityFilterChain
Method security
```

### **Lesson 18**

```text
Spring Security with username/password
UserDetails
UserDetailsService
PasswordEncoder
BCrypt/modern password hashing
```

### **Lesson 19**

```text
Database-backed users
Users
Roles
Permissions
Role ↔ Permission
User ↔ Role
```

### **Lesson 20**

```text
Login
AuthenticationManager
AuthenticationProvider
SecurityContext
```

### **Lesson 21**

```text
JWT
Access tokens
Claims
Expiration
Signing
```

### **Lesson 22+**

```text
Refresh tokens
Revocation
Ownership authorization
Custom AuthorizationManager
Multi-tenant authorization
Security testing
```

This gives us a much stronger foundation than jumping straight into copying a JWT tutorial.

---