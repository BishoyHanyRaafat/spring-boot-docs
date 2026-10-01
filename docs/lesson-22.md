---
title: "Lesson 22: Actually Building JWT Authentication"
sidebar_position: 22
---

Now we’re going to turn the concepts from Lesson 21 into a working ProjectHub design.

One current-version detail first: Spring Security 7.1.1 provides `JwtEncoder`/`NimbusJwtEncoder` for creating JWTs and `JwtDecoder`/`NimbusJwtDecoder` for validating them. Its Resource Server support processes `Authorization: Bearer ...` requests and uses `JwtAuthenticationConverter` to turn a validated JWT into Spring Security authorities.  

Our architecture will be:

```text
POST /auth/login
       ↓
AuthenticationManager
       ↓
successful Authentication
       ↓
JwtEncoder
       ↓
Access Token
       ↓
Client
       ↓
Authorization: Bearer <token>
       ↓
Spring Security Resource Server
       ↓
JwtDecoder
       ↓
JwtAuthenticationConverter
       ↓
GrantedAuthorities
       ↓
Authorization
```

---

## **1. Dependencies**

For JWT Resource Server support, Spring Security needs both:

```text
spring-security-oauth2-resource-server
spring-security-oauth2-jose
```

The official documentation specifically notes that the JOSE module supplies JWT decoding/verifying support.  

With Spring Boot, use the corresponding Boot starter:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
```

Don’t manually specify Spring Security versions if Spring Boot is managing them for your project.

---

# **2. First: our JWT configuration**

Let’s define:

```yaml
app:
  jwt:
    issuer: projecthub
    access-token-expiration: 15m
```

The idea is:

```text
issuer
   ↓
Who issued this token?

expiration
   ↓
How long is this access token valid?
```

You’ve already learned why `@ConfigurationProperties` is useful for related configuration, so this is a good place to use it.

```java
@ConfigurationProperties(prefix = "app.jwt")
public record JwtProperties(
        String issuer,
        Duration accessTokenExpiration
) {
}
```

And enable configuration-property scanning as you learned earlier.

---

# **3. RSA keys**

For our learning implementation, we’ll use an RSA key pair:

```text
              RSA KEY PAIR

          ┌─────────────────┐
          │                 │
          │  Private Key    │
          │                 │
          └────────┬────────┘
                   │
                   ▼
                SIGN JWT


          ┌─────────────────┐
          │                 │
          │   Public Key    │
          │                 │
          └────────┬────────┘
                   │
                   ▼
              VERIFY JWT
```

The private key must remain secret.

The public key is safe to distribute to services that only need to verify tokens.

Spring Security’s `NimbusJwtDecoder.withPublicKey(...)` is specifically designed to validate JWTs using an RSA public key.  

---

# **4. A development key configuration**

For learning, we can generate an RSA key pair when the application starts:

```java
@Configuration
public class JwtKeyConfig {

    @Bean
    public KeyPair keyPair() throws NoSuchAlgorithmException {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");

        generator.initialize(2048);

        return generator.generateKeyPair();
    }
}
```

This is convenient for development.

### **But there’s an important warning**

Every time the application restarts:

```text
old private/public key
        ↓
gone
```

A token created before the restart can no longer be validated by the newly generated public key.

That’s **fine for learning**, but not for production.

Later we’ll move the keys into proper key management/secrets and discuss key rotation.

---

# 

# **5. Create the**

**`JwtEncoder`**

Now we have:

```text
KeyPair
 ├── private key
 └── public key
```

We need the private key for signing.

Spring Security’s `NimbusJwtEncoder` is the implementation we’ll use. Spring Security explicitly provides this encoder for application-side JWT creation.  

Conceptually:

```java
@Bean
JwtEncoder jwtEncoder(KeyPair keyPair) {
    // configure NimbusJwtEncoder with RSA private key
}
```

The current API also provides RSA key-pair builder support for `NimbusJwtEncoder`.  

For this course, the important concept is:

```text
JwtEncoder
      +
private key
      ↓
signed JWT
```

---

# 

# **6. Create the**

**`JwtDecoder`**

Now the other side:

```java
@Bean
JwtDecoder jwtDecoder(KeyPair keyPair) {
    return NimbusJwtDecoder
            .withPublicKey((RSAPublicKey) keyPair.getPublic())
            .build();
}
```

This is exactly the relationship we want:

```text
JwtEncoder
    ↓
private key
    ↓
SIGN


JwtDecoder
    ↓
public key
    ↓
VERIFY
```

`NimbusJwtDecoder` supports constructing a decoder directly from an RSA public key.  

---

# **7. Add JWT validation**

Signature validation isn’t the only thing we care about.

Suppose someone creates a perfectly validly signed JWT with:

```json
{
  "sub": "alice",
  "iss": "evil-service"
}
```

We don’t want to accept it merely because the signature is mathematically valid under some trusted key.

We also want claims such as:

```text
iss
exp
nbf
aud
```

to have the expected values.

Spring Security’s Resource Server JWT support validates standard timestamp/issuer claims, and audience validation can also be configured.  

So conceptually our decoder should enforce:

```text
signature valid?
       +
issuer correct?
       +
not expired?
       +
not before current time?
       +
audience correct?
```

Only then:

```text
VALID JWT
```

---

# **8. Now build the token service**

Let’s create:

```java
@Service
public class JwtService {

    private final JwtEncoder jwtEncoder;
    private final JwtProperties properties;

    public JwtService(
            JwtEncoder jwtEncoder,
            JwtProperties properties) {

        this.jwtEncoder = jwtEncoder;
        this.properties = properties;
    }
}
```

Its responsibility is simple:

Take a successful `Authentication` and create an access token.

It should **not** authenticate passwords.

That’s already the job of:

```text
AuthenticationManager
```

---

# **9. Creating JWT claims**

Inside the service, we’ll construct claims from the authenticated user.

Conceptually:

```java
Instant now = Instant.now();

JwtClaimsSet claims = JwtClaimsSet.builder()
        .issuer(properties.issuer())
        .subject(authentication.getName())
        .issuedAt(now)
        .expiresAt(now.plus(properties.accessTokenExpiration()))
        .claim("authorities", authorities)
        .build();
```

This gives us something conceptually like:

```json
{
  "iss": "projecthub",
  "sub": "alice",
  "iat": 1790870400,
  "exp": 1790871300,
  "authorities": [
    "posts.read",
    "posts.create"
  ]
}
```

---

# **10. Why put authorities in the token?**

Because we want the next request to be able to say:

```text
JWT
 ↓
authorities
 ↓
posts.create
```

without loading Alice’s roles from PostgreSQL on every request.

So:

```text
LOGIN
    ↓
DB
    ↓
roles
    ↓
permissions
    ↓
JWT
```

Then:

```text
SUBSEQUENT REQUEST
    ↓
JWT
    ↓
permissions
```

This is one of the important architectural tradeoffs of JWT.

---

# **11. Sign the token**

Now:

```java
JwsHeader header = JwsHeader.with(SignatureAlgorithm.RS256)
        .build();

JwtEncoderParameters parameters =
        JwtEncoderParameters.from(header, claims);

return jwtEncoder
        .encode(parameters)
        .getTokenValue();
```

The important concept is:

```text
claims
   ↓
JwtEncoder
   ↓
private RSA key
   ↓
signed JWT
```

We’re not manually implementing RSA.

Spring Security/Nimbus handles that cryptographic operation.

---

# **12. Our login service**

Now connect this to `AuthenticationManager`.

```java
@Service
public class AuthenticationService {

    private final AuthenticationManager authenticationManager;
    private final JwtService jwtService;

    public AuthenticationService(
            AuthenticationManager authenticationManager,
            JwtService jwtService) {

        this.authenticationManager = authenticationManager;
        this.jwtService = jwtService;
    }
}
```

And:

```java
public LoginResponse login(LoginRequest request) {

    Authentication authentication =
            authenticationManager.authenticate(
                    new UsernamePasswordAuthenticationToken(
                            request.username(),
                            request.password()
                    )
            );

    String accessToken =
            jwtService.generateToken(authentication);

    return new LoginResponse(
            accessToken,
            "Bearer"
    );
}
```

Now the responsibilities are beautifully separated:

```text
AuthenticationService
        │
        ├── AuthenticationManager
        │       ↓
        │   verify identity
        │
        └── JwtService
                ↓
            create token
```

---

# **13. Login controller**

The controller becomes very small:

```java
@RestController
@RequestMapping("/auth")
public class AuthenticationController {

    private final AuthenticationService authenticationService;

    public AuthenticationController(
            AuthenticationService authenticationService) {

        this.authenticationService = authenticationService;
    }

    @PostMapping("/login")
    public LoginResponse login(
            @Valid @RequestBody LoginRequest request) {

        return authenticationService.login(request);
    }
}
```

And:

```java
public record LoginResponse(
        String accessToken,
        String tokenType
) {
}
```

The request:

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

produces something like:

```json
{
  "accessToken": "eyJhbGciOiJSUzI1NiJ9...",
  "tokenType": "Bearer"
}
```

---

# **14. Now the really important part: reading the JWT**

Login creates the JWT.

But how does:

```http
GET /posts
Authorization: Bearer eyJ...
```

become an authenticated request?

That’s Resource Server functionality.

Configure:

```java
http.oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults())
);
```

When JWT bearer support is enabled, Spring Security installs `BearerTokenAuthenticationFilter`. The JWT authentication provider then uses `JwtDecoder` and `JwtAuthenticationConverter`.  

So:

```text
Authorization header
        ↓
BearerTokenAuthenticationFilter
        ↓
JwtAuthenticationProvider
        ↓
JwtDecoder
        ↓
validate JWT
        ↓
JwtAuthenticationConverter
        ↓
Authentication
```

---

# 

# 

# **15. The missing piece: our**

**`authorities`**

**claim**

By default, Spring Security commonly maps OAuth scopes into authorities prefixed with:

```text
SCOPE_
```

For example:

```json
{
  "scope": "posts.read posts.create"
}
```

becomes authorities like:

```text
SCOPE_posts.read
SCOPE_posts.create
```

But ProjectHub wants:

```text
posts.read
posts.create
```

Spring Security explicitly supports configuring a custom authorities claim name through `JwtGrantedAuthoritiesConverter`.  

So we configure:

```java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {

    JwtGrantedAuthoritiesConverter authoritiesConverter =
            new JwtGrantedAuthoritiesConverter();

    authoritiesConverter.setAuthoritiesClaimName("authorities");
    authoritiesConverter.setAuthorityPrefix("");

    JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();

    converter.setJwtGrantedAuthoritiesConverter(
            authoritiesConverter
    );

    return converter;
}
```

Two lines are especially important:

```java
authoritiesConverter.setAuthoritiesClaimName("authorities");
```

means:

Read authorities from our `authorities` claim.

And:

```java
authoritiesConverter.setAuthorityPrefix("");
```

means:

Don’t add `SCOPE_`.

So:

```json
"authorities": [
    "posts.read",
    "posts.create"
]
```

becomes:

```text
posts.read
posts.create
```

exactly what our authorization rules expect.  

---

# **16. Connect the converter**

Now:

```java
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
        oauth2.jwt(jwt ->
            jwt.jwtAuthenticationConverter(
                jwtAuthenticationConverter()
            )
        )
    );
```

Now the entire chain connects.

---

# **17. Let’s trace Alice**

Alice has:

```text
USER
 ├── posts.read
 └── posts.create
```

She logs in.

### **Step 1**

```text
POST /auth/login
```

### **Step 2**

```text
AuthenticationManager
```

authenticates her.

### **Step 3**

Her `Authentication` contains:

```text
posts.read
posts.create
```

### **Step 4**

`JwtService` creates:

```json
{
  "sub": "alice",
  "authorities": [
    "posts.read",
    "posts.create"
  ]
}
```

### **Step 5**

`JwtEncoder` signs it.

### **Step 6**

Alice receives:

```json
{
  "accessToken": "eyJ...",
  "tokenType": "Bearer"
}
```

---

# **18. Alice requests posts**

```http
GET /posts
Authorization: Bearer eyJ...
```

Spring Security:

```text
BearerTokenAuthenticationFilter
        ↓
JwtDecoder
        ↓
signature valid
        ↓
expiration valid
        ↓
issuer valid
        ↓
JwtAuthenticationConverter
        ↓
posts.read
posts.create
```

Then:

```java
.hasAuthority("posts.read")
```

succeeds.

The request reaches the controller.

---

# **19. Alice tries to delete**

```http
DELETE /posts/42
Authorization: Bearer eyJ...
```

Her authorities are:

```text
posts.read
posts.create
```

but the endpoint requires:

```text
posts.delete
```

Therefore:

```text
403 Forbidden
```

This is authorization failure.

She **is authenticated**.

She simply lacks the required authority.

---

# **20. What if the JWT is fake?**

Suppose an attacker creates:

```text
header.payload.fake-signature
```

The `JwtDecoder` verifies the JWT’s signature.

It fails.

Therefore:

```text
JWT validation failed
        ↓
authentication fails
        ↓
request rejected
```

The attacker cannot simply modify:

```json
"authorities": [
    "posts.delete"
]
```

and expect Spring Security to trust it.

That’s precisely why the signature matters.

---

# **21. What if the token expired?**

Suppose:

```json
{
  "exp": 1790871300
}
```

and the current time is later than that.

JWT validation fails.

So:

```text
expired JWT
    ↓
unauthenticated
    ↓
401 Unauthorized
```

This is different from Alice having a valid token without `posts.delete`.

Remember:

```text
Invalid/absent authentication → 401
Authenticated but insufficient authority → 403
```

---

# **22. One important problem with our development key**

Our current setup:

```java
KeyPairGenerator
       ↓
generate key pair on startup
```

means:

```text
Application restart
       ↓
new key pair
       ↓
old tokens invalid
```

That’s acceptable for our educational implementation.

In production, you would normally have stable private-key material managed outside ordinary source code and configuration, with an appropriate key rotation strategy.

Spring Security supports configurations where Resource Servers obtain public keys from a JWK Set endpoint, and it supports key rotation when the authorization server publishes new keys.  

We’ll eventually discuss proper key management rather than treating generated startup keys as production-ready.

---

# **23. Don’t put too much into the JWT**

It’s tempting to put:

```json
{
  "sub": "alice",
  "username": "alice",
  "email": "...",
  "roles": [...],
  "permissions": [...],
  "projects": [...],
  "everything": "..."
}
```

Don’t.

JWT payloads should contain the information needed by the authentication/authorization architecture.

For now:

```json
{
  "iss": "projecthub",
  "sub": "alice",
  "iat": "...",
  "exp": "...",
  "authorities": [
    "posts.read",
    "posts.create"
  ]
}
```

is enough for our learning project.

---

# **24. The complete ProjectHub authentication architecture**

You should now be able to visualize the whole thing:

```text
                    REGISTER
                       │
                       ▼
                 PasswordEncoder
                       │
                       ▼
                   PostgreSQL
                       │
                       │
                    LOGIN
                       │
                       ▼
              AuthenticationManager
                       │
                       ▼
              DaoAuthenticationProvider
                   /           \
                  /             \
                 ▼               ▼
       UserDetailsService    PasswordEncoder
                 │               │
                 ▼               │
             PostgreSQL           │
                 │               │
                 └───────┬───────┘
                         ▼
                  Authentication
                         │
                         ▼
                    JwtEncoder
                         │
                         ▼
                    ACCESS JWT
                         │
                         ▼
                       Client
                         │
                         │ Authorization: Bearer
                         ▼
              BearerTokenAuthenticationFilter
                         │
                         ▼
                    JwtDecoder
                         │
                         ▼
              JwtAuthenticationConverter
                         │
                         ▼
                   Authentication
                         │
                         ▼
                    Authorization
                         │
             ┌───────────┼────────────┐
             ▼           ▼            ▼
        posts.read  posts.create  posts.delete
```

This is a **huge conceptual milestone**.

---

# **Your exercise**

Don’t just copy the configuration. Implement it and make sure you understand each piece.

### **Part 1 — Configuration**

Create:

```text
JwtProperties
JwtKeyConfig
JwtEncoder bean
JwtDecoder bean
```

Use:

```text
issuer = projecthub
expiration = 15m
```

### **Part 2 — Token generation**

Create:

```text
JwtService
```

with:

```text
generateToken(Authentication authentication)
```

The token should contain:

```text
iss
sub
iat
exp
authorities
```

### **Part 3 — Login**

Create:

```text
POST /auth/login
```

that performs:

```text
LoginRequest
    ↓
AuthenticationManager
    ↓
Authentication
    ↓
JwtService
    ↓
LoginResponse
```

### **Part 4 — JWT validation**

Configure:

```text
oauth2ResourceServer
        ↓
jwt
        ↓
JwtAuthenticationConverter
```

and make sure:

```text
authorities
```

maps directly to:

```text
posts.read
posts.create
posts.delete
```

without the `SCOPE_` prefix. Spring Security officially supports this custom claim/prefix configuration.  

### **Part 5 — Test these four cases**

|**Request**|**Expected**|
|---|---|
|Login with correct password|Access token|
|`GET /posts` with `posts.read`|Allowed|
|`DELETE /posts/1` without `posts.delete`|403|
|Request with expired/invalid JWT|401|

**Next lesson:** we’ll tackle the most important JWT limitation: **refresh tokens, token expiration, logout/revocation, and what happens when a user’s permissions change while they still have a valid access token.**