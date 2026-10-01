---
title: "Lesson 21: JWT Authentication"
sidebar_position: 21
---

This is a major milestone for ProjectHub.

So far, we have:

```text
username + password
        ↓
AuthenticationManager
        ↓
UserDetailsService
        ↓
PasswordEncoder
        ↓
Authentication
```

Now we’re going to turn successful authentication into a **JWT access token**, and then use that token to authenticate future API requests.

I’ve checked the current Spring Security documentation: the stable line is **7.1.1**, and Spring Security’s Resource Server support can validate custom JWT bearer tokens. Spring Security provides `JwtDecoder` for validation and `JwtEncoder` for creating JWTs, but it does **not** provide a ready-made token-minting endpoint—you build that part of your application.  

---

## **1. The problem JWT solves**

Imagine Alice logs in:

```http
POST /auth/login
```

with:

```json
{
  "username": "alice",
  "password": "secret123"
}
```

The server authenticates her.

But what happens when she subsequently sends:

```http
GET /posts
```

How does the server know it’s Alice?

With a traditional server-side session, the server can keep authentication state.

For our API, we’re going to use a **bearer access token**.

The flow becomes:

```text
LOGIN

username + password
        ↓
AuthenticationManager
        ↓
successful Authentication
        ↓
create JWT
        ↓
return JWT to client
```

Then:

```text
EVERY FUTURE REQUEST

Authorization: Bearer <JWT>
        ↓
Spring Security
        ↓
validate JWT
        ↓
Authentication
        ↓
authorization
        ↓
Controller
```

Spring Security’s Resource Server support processes bearer tokens from the `Authorization` header and, for JWTs, verifies the token before creating an authenticated `Authentication`.  

---

# **2. What is a JWT?**

JWT means **JSON Web Token**.

A JWT is a signed token containing claims.

Conceptually:

```text
header.payload.signature
```

For example:

```text
eyJhbGciOiJSUzI1NiJ9
.
eyJzdWIiOiJhbGljZSIsImV4cCI6MT...
.
signature...
```

Don’t worry about decoding the characters manually.

Think of it as:

```text
JWT
 ├── Header
 ├── Payload
 └── Signature
```

---

# **3. The header**

The header describes things such as the signing algorithm.

Conceptually:

```json
{
  "alg": "RS256",
  "typ": "JWT"
}
```

For learning purposes, the important field is:

```text
alg
```

which says which cryptographic algorithm was used.

---

# **4. The payload**

The payload contains **claims**.

For example:

```json
{
  "sub": "alice",
  "iss": "projecthub",
  "aud": "projecthub-api",
  "iat": 1790870400,
  "exp": 1790874000
}
```

Important claims:

### **`sub`**

Subject.

Usually identifies who the token represents.

```text
sub = alice
```

### **`iss`**

Issuer.

Who created the token?

```text
iss = projecthub
```

### **`aud`**

Audience.

Who is the token intended for?

```text
aud = projecthub-api
```

### **`iat`**

Issued-at time.

### **`exp`**

Expiration time.

Spring Security’s JWT Resource Server validates standard claims including `exp`, `nbf`, and `iss` when configured appropriately. It can also validate `aud`.  

---

# **5. The signature**

This is the security-critical part.

Conceptually:

```text
header + payload
       ↓
cryptographic signing
       ↓
signature
```

Someone can read the payload, but they shouldn’t be able to modify it and produce a valid signature.

For example, imagine the token says:

```json
{
  "sub": "alice",
  "role": "USER"
}
```

An attacker changes it to:

```json
{
  "sub": "alice",
  "role": "ADMIN"
}
```

The signature will no longer match.

The server rejects the token.

---

# **6. JWT is signed, not necessarily encrypted**

This is an extremely important concept.

JWT payloads are generally **not secret** merely because they’re inside a JWT.

Don’t put:

```text
password
password hash
credit card number
private information
```

into a normal signed JWT.

Think:

```text
JWT
=
tamper-resistant information
```

not:

```text
JWT
=
encrypted secret container
```

---

# **7. Access token vs password**

After login:

```text
password
   ↓
used to authenticate
   ↓
NOT sent on every API request
```

Instead:

```text
password
   ↓
successful authentication
   ↓
JWT access token
   ↓
future requests
```

The client sends:

```http
Authorization: Bearer eyJ...
```

rather than:

```http
Authorization: Basic ...
```

or the user’s password.

---

# **8. Our ProjectHub architecture**

We’re going to create this:

```text
                  LOGIN
                    │
                    ▼
             AuthenticationManager
                    │
                    ▼
             Authentication
                    │
                    ▼
                JwtEncoder
                    │
                    ▼
               Access JWT
                    │
                    ▼
                  Client
```

Then:

```text
                  REQUEST
                    │
                    ▼
          Authorization: Bearer JWT
                    │
                    ▼
       BearerTokenAuthenticationFilter
                    │
                    ▼
                JwtDecoder
                    │
                    ▼
             validate signature
             validate claims
                    │
                    ▼
            JwtAuthenticationToken
                    │
                    ▼
             SecurityContext
                    │
                    ▼
              Authorization
```

Spring Security’s JWT implementation uses a `JwtDecoder` to decode/verify JWTs and a `JwtAuthenticationConverter` to turn the JWT into an `Authentication`.  

---

# **9. Who creates the JWT?**

This is an important architectural distinction.

Spring Security can **validate** JWTs as a Resource Server.

But Spring Security doesn’t automatically give your application a `/login` endpoint that mints your application’s JWTs. The official documentation explicitly notes that Spring Security provides `JwtEncoder`, but not a token-minting endpoint.  

So our application will have something like:

```text
AuthenticationService
        ↓
AuthenticationManager
        ↓
JwtEncoder
        ↓
JWT
```

---

# 

# **10.**

**`JwtEncoder`**

Spring Security provides:

```java
JwtEncoder
```

for encoding/signing JWTs.

Conceptually:

```java
JwtClaimsSet claims = JwtClaimsSet.builder()
        .subject(authentication.getName())
        .issuer("projecthub")
        .issuedAt(...)
        .expiresAt(...)
        .build();

String token = jwtEncoder
        .encode(...)
        .getTokenValue();
```

We’re going to implement the details shortly.

The important mental model is:

```text
Authentication
      ↓
claims
      ↓
JwtEncoder
      ↓
signed JWT
```

---

# **11. Signing keys**

Now we reach an important cryptography concept.

Suppose we use RSA.

We have:

```text
PRIVATE KEY
    +
    ↓
sign JWT
```

and:

```text
PUBLIC KEY
    +
    ↓
verify JWT
```

So:

```text
Authorization side
      │
      │ private key
      ▼
   SIGN JWT
      │
      ▼
     JWT
      │
      ▼
Resource Server
      │
      │ public key
      ▼
 VERIFY JWT
```

This is one reason asymmetric signing is attractive for distributed systems.

The component creating tokens keeps the private key.

Services validating tokens only need the public key.

Spring Security’s Resource Server support can use a public key/JWK configuration to validate JWT signatures.  

---

# **12. Why not just use a secret string?**

You can use symmetric algorithms too:

```text
same secret
     ↓
sign
     ↓
JWT
```

and:

```text
same secret
     ↓
verify
```

But now every service that needs to verify tokens needs access to the secret.

With RSA:

```text
private key → token issuer
public key  → token consumers
```

That can be a cleaner architecture as systems grow.

For our learning project, we’ll use **RSA** so you understand the asymmetric model.

---

# **13. JWT authorities**

Here’s where our previous lessons connect beautifully.

Remember:

```text
User
 ↓
Role
 ↓
Permission
 ↓
GrantedAuthority
```

Suppose Alice has:

```text
posts.read
posts.create
```

We could put those authorities into the JWT:

```json
{
  "sub": "alice",
  "authorities": [
    "posts.read",
    "posts.create"
  ]
}
```

Then:

```text
JWT
 ↓
authorities claim
 ↓
GrantedAuthority
 ↓
hasAuthority("posts.create")
```

Spring Security supports customizing which JWT claim is converted into authorities. By default, Resource Server maps OAuth scopes to authorities prefixed with `SCOPE_`, but a custom claim such as `authorities` can be configured.  

For ProjectHub, we’ll eventually use our own `authorities` claim.

---

# **14. Why not query the database on every request?**

You might ask:

Why put permissions into the JWT? Why not load them from PostgreSQL every time?

You can.

But then every:

```http
GET /posts
```

might require:

```text
JWT
 ↓
user
 ↓
database
 ↓
roles
 ↓
permissions
```

That can become expensive.

With permissions inside a signed JWT:

```text
JWT
 ↓
verify signature
 ↓
read authorities
```

No database lookup is required just to establish those authorities.

That’s one of the main benefits of JWT-based stateless authentication.

But it introduces an important tradeoff:

If Alice’s permissions change, an already-issued token may still contain the old permissions until it expires or is otherwise invalidated.

We’ll address that later with **short-lived access tokens, refresh tokens, and revocation strategies**.

---

# **15. Access token expiration**

We should never create an access token that lives forever.

For example:

```text
access token
      ↓
expires in 15 minutes
```

After expiration:

```text
old JWT
  ↓
rejected
```

The client obtains a new access token through the refresh-token mechanism we’ll build later.

Think:

```text
Access token
= short-lived permission to access APIs
```

while:

```text
Refresh token
= mechanism for obtaining a new access token
```

We’ll cover refresh tokens in a dedicated lesson rather than mixing the concepts now.

---

# **16. The login flow we’re building**

Eventually:

```text
POST /auth/login
```

```json
{
  "username": "alice",
  "password": "secret123"
}
```

Server:

```text
AuthenticationManager
       ↓
authenticate username/password
       ↓
Authentication
       ↓
extract username + authorities
       ↓
build JWT claims
       ↓
JwtEncoder
       ↓
signed JWT
```

Response:

```json
{
  "accessToken": "eyJ...",
  "tokenType": "Bearer",
  "expiresIn": 900
}
```

Then the client calls:

```http
GET /posts
Authorization: Bearer eyJ...
```

---

# 

# 

# **17. What happens to**

**`/posts`**

**?**

The request enters Spring Security.

Spring Security sees:

```http
Authorization: Bearer eyJ...
```

The Resource Server support handles the bearer token. Its JWT provider validates the token using `JwtDecoder`, converts it to an authenticated token, and places that authentication into the `SecurityContext`.  

So:

```text
HTTP
 ↓
Bearer JWT
 ↓
JWT validation
 ↓
Authentication
 ↓
SecurityContext
 ↓
Authorization
 ↓
Controller
```

Our controller doesn’t need to manually parse:

```text
Authorization
```

or manually verify the JWT.

That’s Spring Security’s job.

---

# **18. Our SecurityFilterChain changes**

Eventually we’ll have something conceptually like:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/auth/**").permitAll()
            .requestMatchers(HttpMethod.GET, "/posts/**")
                .hasAuthority("posts.read")
            .requestMatchers(HttpMethod.POST, "/projects/*/posts")
                .hasAuthority("posts.create")
            .requestMatchers(HttpMethod.DELETE, "/posts/**")
                .hasAuthority("posts.delete")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults())
        );

    return http.build();
}
```

The important new piece is:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.jwt(Customizer.withDefaults())
)
```

That enables JWT bearer-token processing.  

---

# **19. But we’re not done yet**

There’s an important missing piece.

We said:

```text
JWT
 ↓
authorities
 ↓
posts.create
```

But Spring Security’s default JWT authority mapping is designed around scopes, which become authorities such as:

```text
SCOPE_read
SCOPE_write
```

Our ProjectHub permissions are:

```text
posts.read
posts.create
posts.delete
```

So we’ll need a custom JWT authority converter.

Spring Security explicitly supports replacing/customizing the `JwtAuthenticationConverter` for this purpose.  

That’s the next implementation step.

---

# **20. The big picture**

At this point ProjectHub will have:

```text
                   ┌──────────────┐
                   │  PostgreSQL  │
                   └──────┬───────┘
                          │
                    User / Roles
                    / Permissions
                          │
                          ▼
                   UserDetailsService
                          │
                          ▼
                   AuthenticationManager
                          │
                          ▼
                       LOGIN
                          │
                          ▼
                     JwtEncoder
                          │
                          ▼
                   ┌──────────────┐
                   │  Access JWT  │
                   └──────┬───────┘
                          │
                     Client stores
                          │
                          ▼
               Authorization: Bearer JWT
                          │
                          ▼
                 Spring Security
                          │
                          ▼
                    JwtDecoder
                          │
                          ▼
              JwtAuthenticationConverter
                          │
                          ▼
                    Authorities
                          │
                          ▼
                posts.create / etc.
                          │
                          ▼
                    Controller
```

That’s the architecture you should keep in your head.

---

# **Exercise 21**

Before writing the complete JWT implementation, answer these:

### **1.**

What is the difference between:

```text
JwtEncoder
```

and:

```text
JwtDecoder
```

### **2.**

Why should the client send:

```http
Authorization: Bearer <token>
```

instead of sending the username/password on every request?

### **3.**

What does this claim represent?

```json
{
  "sub": "alice"
}
```

### **4.**

Why should a JWT have an expiration time?

### **5.**

If Alice has:

```text
posts.read
posts.create
```

what would happen if we put these into:

```json
{
  "authorities": [
    "posts.read",
    "posts.create"
  ]
}
```

### **6.**

Most importantly:

Explain this entire flow in your own words:

```text
POST /auth/login
        ↓
username + password
        ↓
AuthenticationManager
        ↓
Authentication
        ↓
JwtEncoder
        ↓
JWT
        ↓
Authorization: Bearer JWT
        ↓
JwtDecoder
        ↓
Authentication
        ↓
hasAuthority("posts.create")
```

**Next lesson:** we’ll actually build the JWT implementation: RSA keys, `JwtEncoder`, `JwtDecoder`, the `/auth/login` response, and the custom authority converter that turns our `posts.*` permissions back into Spring Security authorities.