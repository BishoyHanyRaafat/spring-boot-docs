---
title: Lesson 20: Login with AuthenticationManager
sidebar_position: 20
---

Now we’re going to connect everything we’ve built:

```text
User
 ↓
Database
 ↓
UserDetailsService
 ↓
AuthenticationManager
 ↓
PasswordEncoder
 ↓
Authentication
 ↓
SecurityContext
```

This is the point where ProjectHub gets a **real username/password login flow**.

The current stable Spring Security line is **7.1.1** according to the official documentation. The architecture we’re using below is the current username/password authentication model.  

---

## **1. What exactly happens when someone logs in?**

Suppose Alice sends:

```http
POST /auth/login
Content-Type: application/json
```

```json
{
  "username": "alice",
  "password": "secret123"
}
```

We want:

```text
HTTP request
     ↓
AuthController
     ↓
AuthenticationManager
     ↓
DaoAuthenticationProvider
     ↓
UserDetailsService
     ↓
Database
     ↓
UserDetails
     ↓
PasswordEncoder
     ↓
Authentication
```

`DaoAuthenticationProvider` is specifically designed to authenticate username/password credentials using a `UserDetailsService` and `PasswordEncoder`.  

---

# **2. AuthenticationManager**

Think of `AuthenticationManager` as the **front door to authentication**.

Its job is essentially:

“Here are some credentials. Can you authenticate them?”

Conceptually:

```java
Authentication authentication =
        authenticationManager.authenticate(
            new UsernamePasswordAuthenticationToken(
                username,
                password
            )
        );
```

The important part is that your controller doesn’t manually do:

```java
findUser(...)
comparePasswords(...)
loadRoles(...)
```

Instead, it delegates authentication to Spring Security.

Spring Security defines `AuthenticationManager` as the API used by its authentication filters to perform authentication; `ProviderManager` is the most common implementation.  

---

# **3. Who actually checks the password?**

This is where `DaoAuthenticationProvider` comes in.

The flow is:

```text
AuthenticationManager
       ↓
DaoAuthenticationProvider
       ↓
UserDetailsService
       ↓
UserDetails
       ↓
PasswordEncoder
```

Suppose the database contains:

```text
username: alice
password_hash: {bcrypt}...
```

The `UserDetailsService` loads Alice:

```java
UserDetails userDetails =
        userDetailsService.loadUserByUsername("alice");
```

Then the provider uses the configured `PasswordEncoder` to validate the supplied password against the stored password representation.  

You **do not** write:

```java
if (password.equals(user.getPasswordHash()))
```

and you don’t manually implement the password comparison.

---

# **4. Your login DTO**

Let’s create:

```java
public record LoginRequest(
        @NotBlank
        String username,

        @NotBlank
        String password
) {}
```

And for now:

```java
public record LoginResponse(
        String username
) {}
```

We’re deliberately keeping the response simple.

**No JWT yet.**

JWT is the next major step.

---

# **5. AuthenticationController**

Conceptually:

```java
@RestController
@RequestMapping("/auth")
public class AuthenticationController {

    private final AuthenticationManager authenticationManager;

    public AuthenticationController(
            AuthenticationManager authenticationManager) {
        this.authenticationManager = authenticationManager;
    }

    @PostMapping("/login")
    public LoginResponse login(
            @Valid @RequestBody LoginRequest request) {

        Authentication authentication =
                authenticationManager.authenticate(
                    new UsernamePasswordAuthenticationToken(
                        request.username(),
                        request.password()
                    )
                );

        return new LoginResponse(authentication.getName());
    }
}
```

Notice how small this controller is.

It doesn’t know:

- how passwords are hashed
- how users are loaded
- how roles are loaded
- how permissions are loaded
- how authentication providers work

That’s exactly what we want.

---

# 

# 

# **6. What is**

**`UsernamePasswordAuthenticationToken`**

**?**

This class is basically the object we use to say:

“Here are the username and password that this person supplied.”

Before authentication, conceptually:

```text
UsernamePasswordAuthenticationToken

principal   = alice
credentials = secret123
authenticated = false
```

We give it to:

```java
authenticationManager.authenticate(...)
```

If authentication succeeds, Spring Security returns an authenticated `Authentication`.

The `Authentication` abstraction serves both as credentials supplied to an `AuthenticationManager` and, after successful authentication, as the representation of the currently authenticated user.  

---

# **7. Successful authentication**

Suppose Alice enters the correct password.

Spring Security returns something conceptually like:

```text
Authentication

principal:
    UserDetails(alice)

authorities:
    posts.read
    posts.create

authenticated:
    true
```

Those authorities came from the database-backed roles and permissions we built in Lesson 19.

So:

```text
Database
   ↓
Role
   ↓
Permission
   ↓
GrantedAuthority
   ↓
Authentication
```

That’s the connection you’ve been building toward.

---

# **8. Failed authentication**

Suppose Alice sends:

```json
{
  "username": "alice",
  "password": "wrong-password"
}
```

Authentication fails.

You should **not** respond with:

```text
"Your password was wrong."
```

as a detailed authentication diagnostic.

Generally, the login endpoint should expose a generic authentication failure response, while the server can log appropriate diagnostic information.

The important architectural point is:

```text
wrong password
      ↓
authentication fails
      ↓
no authenticated user
```

It does **not** mean:

```text
authentication succeeds
      ↓
authorization fails
```

Those are different stages.

---

# **9. Authentication vs authorization**

This distinction should now be crystal clear.

### **Authentication**

```text
POST /auth/login
```

Question:

Who are you?

Result:

```text
Alice successfully authenticated.
```

### **Authorization**

```text
DELETE /posts/42
```

Question:

Are you allowed to perform this operation?

Result might be:

```text
posts.delete → yes
```

or:

```text
posts.delete → no
```

So:

```text
AUTHENTICATION
     ↓
Who are you?
     ↓
AUTHORIZATION
     ↓
What can you do?
```

---

# **10. Where does the authenticated user go?**

After successful authentication, Spring Security associates the resulting `Authentication` with the `SecurityContext`.

The `SecurityContextHolder` is the central place Spring Security uses to hold the current `SecurityContext`, which contains the current `Authentication`.  

So later, inside your application, you can access:

```java
Authentication authentication =
        SecurityContextHolder
            .getContext()
            .getAuthentication();
```

Then:

```java
String username = authentication.getName();
```

And:

```java
authentication.getAuthorities();
```

might contain:

```text
posts.read
posts.create
```

---

# **11. Why this matters for ProjectHub**

Imagine:

```http
POST /projects/7/posts
```

We eventually want:

```text
Spring Security
       ↓
Is authenticated?
       ↓
Does Authentication contain posts.create?
       ↓
Controller
       ↓
PostService
       ↓
Does Alice belong to project 7?
       ↓
Create post
```

Notice that we now have **two authorization questions**:

### **General permission**

```text
posts.create
```

### **Resource authorization**

```text
Is Alice allowed to create a post in project 7?
```

The first can be handled by Spring Security authorities.

The second belongs to our ProjectHub domain rules.

---

# **12. Getting the current user**

Eventually our service shouldn’t require callers to manually pass a `User` around everywhere.

We can obtain the authenticated principal.

For example:

```java
Authentication authentication =
        SecurityContextHolder
            .getContext()
            .getAuthentication();

String username = authentication.getName();
```

Then:

```java
User user = userRepository
        .findByUsername(username)
        .orElseThrow(...);
```

This is one approach.

Later we’ll improve the design so we don’t repeatedly load users unnecessarily and so authorization logic has a clean boundary.

---

# 

# 

# **13. How does Spring know which**

**`UserDetailsService`**

**to use?**

Remember our custom implementation:

```java
@Service
public class CustomUserDetailsService
        implements UserDetailsService {

    @Override
    public UserDetails loadUserByUsername(String username) {
        ...
    }
}
```

Spring Security can use that `UserDetailsService` as part of username/password authentication. The official API describes `UserDetailsService` as the strategy for locating user-specific data, with `loadUserByUsername` as its core operation.  

The resulting architecture is:

```text
AuthenticationManager
       │
       ▼
DaoAuthenticationProvider
       │
       ├───────────────┐
       ▼               ▼
UserDetailsService  PasswordEncoder
       │
       ▼
   Database
```

---

# **14. PasswordEncoder remains important**

Our application should still expose a `PasswordEncoder` bean:

```java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
}
```

Spring Security integrates password storage through `PasswordEncoder`, which can be configured as a bean.  

Remember:

### **Registration**

```text
raw password
     ↓
passwordEncoder.encode(...)
     ↓
database
```

### **Login**

```text
raw password
     +
stored password hash
     ↓
passwordEncoder.matches(...)
```

You don’t manually perform either operation inside the controller.

---

# **15. What about the SecurityFilterChain?**

Our current security configuration might look like:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/auth/**").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());

    return http.build();
}
```

We’re temporarily keeping HTTP Basic around because it gives us an easy way to test authentication while we’re learning.

Spring Security’s username/password support includes HTTP Basic and form login, but we’re going to build our own `/auth/login` endpoint because ProjectHub will eventually use JWT-based API authentication.  

---

# 

# 

# **16. Important:**

**`/auth/login`**

**and HTTP Basic are different approaches**

This can be confusing.

HTTP Basic:

```text
Client
 ↓
Authorization: Basic ...
 ↓
Spring Security filter
 ↓
AuthenticationManager
```

Our custom login endpoint:

```text
Client
 ↓
POST /auth/login
 ↓
AuthenticationController
 ↓
AuthenticationManager
```

Both can ultimately use the same authentication infrastructure.

We’re using the second approach because later we’ll change:

```text
successful authentication
        ↓
return username
```

into:

```text
successful authentication
        ↓
create JWT access token
        ↓
return token
```

That’s our next major milestone.

---

# **17. The complete picture so far**

You’ve now built almost the entire authentication foundation:

```text
                    DATABASE
                       │
                       ▼
                   ┌────────┐
                   │  User  │
                   └────┬───┘
                        │
                        ▼
                     Roles
                        │
                        ▼
                   Permissions
                        │
                        ▼
                GrantedAuthority
                        │
                        ▼
HTTP ──→ AuthenticationManager
                        │
                        ▼
              DaoAuthenticationProvider
                        │
             ┌──────────┴──────────┐
             ▼                     ▼
    UserDetailsService       PasswordEncoder
             │                     │
             └──────────┬──────────┘
                        ▼
                  Authentication
                        │
                        ▼
                 SecurityContext
                        │
                        ▼
                 Authorization
```

That’s the architecture I want you to understand—not just memorize.

---

# **Exercise 20**

Before we jump to JWT, implement a basic login.

Create:

### **1. DTO**

```text
LoginRequest
```

with:

```text
username
password
```

### **2. Controller**

Create:

```text
POST /auth/login
```

and inject:

```text
AuthenticationManager
```

### **3. Authenticate**

Use:

```java
new UsernamePasswordAuthenticationToken(
    request.username(),
    request.password()
)
```

and pass it to:

```java
authenticationManager.authenticate(...)
```

### **4. Response**

For now return:

```json
{
  "username": "alice"
}
```

Don’t generate JWT yet.

---

## **The key question**

When this executes:

```java
authenticationManager.authenticate(
    new UsernamePasswordAuthenticationToken(
        request.username(),
        request.password()
    )
);
```

**explain the entire journey**:

```text
username/password
      ↓
?
      ↓
?
      ↓
?
      ↓
Authentication
```

Fill in the missing pieces:

1. Who loads the user from PostgreSQL?
2. Who checks the password?
3. Where do Alice’s `posts.read` / `posts.create` authorities come from?
4. Where is the successful authentication stored?
5. What is the difference between the `Authentication` supplied _to_ `authenticate()` and the `Authentication` returned _from_ it?

Once you’ve got that, **Lesson 21 will be JWT authentication**—where this successful `Authentication` becomes an access token that the client can send on subsequent API requests.