---
title: Lesson 23: Refresh Tokens, Logout, Revocation & Permission Changes
sidebar_position: 23
---



Now we tackle the biggest practical weakness of the JWT design from Lesson 22:

**What happens after the access token expires, or when the user’s permissions change while an old token is still valid?**

Spring Security supports OAuth 2.0 refresh-token flows when acting as an authorization server, and its Resource Server support is designed to validate bearer access tokens.  

For ProjectHub, we’ll first understand the architecture, then implement our own refresh-token mechanism.

---

## **1. Why do we need refresh tokens?**

Our access token might live for:

```text
15 minutes
```

That’s intentional.

If Alice’s access token is stolen, we want the window of usefulness to be limited.

But imagine Alice has to log in every 15 minutes:

```text
15 min → login
15 min → login
15 min → login
```

That’s terrible UX.

So we introduce a second token:

```text
Access Token
    ↓
short-lived

Refresh Token
    ↓
longer-lived
```

The basic flow becomes:

```text
LOGIN
  ↓
Access Token + Refresh Token
  ↓
use Access Token for API calls
  ↓
Access Token expires
  ↓
send Refresh Token
  ↓
receive new Access Token
```

---

# **2. Two tokens, two purposes**

### **Access token**

Used to access APIs:

```http
Authorization: Bearer <access-token>
```

Example lifetime:

```text
15 minutes
```

### **Refresh token**

Used only to obtain a new access token.

Example lifetime:

```text
7 days
```

It should **not** normally be sent to:

```text
GET /posts
DELETE /posts/42
POST /projects/1/posts
```

Instead:

```text
refresh token
    ↓
POST /auth/refresh
```

---

# **3. Why not make the access token live for 7 days?**

Because bearer tokens are powerful.

If someone steals:

```text
eyJhbGciOi...
```

they can potentially use it as the legitimate user until it expires.

Spring Security describes bearer tokens as usable by whoever possesses them; sender-constrained mechanisms such as DPoP exist specifically to reduce the impact of stolen bearer tokens.  

So we generally prefer:

```text
short access-token lifetime
```

and:

```text
longer refresh-token lifetime
```

rather than a seven-day access token.

---

# **4. The new login response**

Instead of:

```json
{
  "accessToken": "eyJ..."
}
```

we’ll eventually return:

```json
{
  "accessToken": "eyJ...",
  "refreshToken": "random-long-value",
  "tokenType": "Bearer",
  "expiresIn": 900
}
```

The important distinction:

```text
accessToken
    ↓
JWT

refreshToken
    ↓
random secret stored server-side
```

I recommend that our ProjectHub refresh token be **opaque**, rather than another JWT.

---

# **5. Why make the refresh token opaque?**

A refresh token doesn’t need to contain all the information that an access token contains.

We can simply generate a cryptographically random value:

```text
8d8e7f...very-long-random-value...
```

Store a hash of it in PostgreSQL:

```text
refresh_tokens

id
user_id
token_hash
expires_at
revoked_at
created_at
```

Then:

```text
Client
  ↓
refresh token
  ↓
hash
  ↓
database lookup
```

This gives us server-side control.

---

# **6. Why store a hash instead of the raw refresh token?**

Suppose our database contains:

```text
refresh_tokens
--------------------------
token = abc123...
```

and the database is compromised.

The attacker now has usable refresh tokens.

Instead:

```text
client:
    abc123...

database:
    SHA-256(abc123...)
```

If the database leaks, the attacker doesn’t immediately possess the actual refresh token.

The general principle is the same one we used with passwords:

Don’t store reusable authentication secrets in plaintext when you can avoid it.

There is an important difference, though: password hashing uses password-specific slow hashes; refresh-token hashes are typically high-entropy random secrets, so a cryptographic hash such as SHA-256 is appropriate.

---

# **7. Database table**

Let’s add:

```sql
CREATE TABLE refresh_tokens (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    user_id BIGINT NOT NULL
        REFERENCES users(id),

    token_hash VARCHAR(64) NOT NULL UNIQUE,

    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,

    created_at TIMESTAMP WITH TIME ZONE NOT NULL,

    revoked_at TIMESTAMP WITH TIME ZONE
);
```

Now our model is:

```text
User
 │
 └──────< RefreshToken
```

One user can have multiple refresh tokens.

For example:

```text
Alice
 ├── laptop refresh token
 ├── phone refresh token
 └── tablet refresh token
```

This becomes useful later when implementing:

“Log out this device”

versus:

“Log out everywhere.”

---

# **8. Refresh-token lifecycle**

A refresh token has a lifecycle:

```text
CREATED
   ↓
ACTIVE
   ↓
USED
   ↓
ROTATED / REVOKED
```

It can also become:

```text
EXPIRED
```

or:

```text
REVOKED
```

We should never accept a token simply because its hash exists.

We also check:

```text
not expired
AND
not revoked
```

---

# **9. Login flow with refresh tokens**

Let’s redesign login:

```text
POST /auth/login
       │
       ▼
AuthenticationManager
       │
       ▼
Authentication
       │
       ├───────────────┐
       ▼               ▼
 create JWT       create refresh token
       │               │
       │               ▼
       │            hash token
       │               │
       │               ▼
       │          PostgreSQL
       │
       ▼
LoginResponse
```

Response:

```json
{
  "accessToken": "...",
  "refreshToken": "...",
  "tokenType": "Bearer",
  "expiresIn": 900
}
```

---

# **10. Refresh flow**

After 15 minutes:

```http
POST /auth/refresh
Content-Type: application/json
```

```json
{
  "refreshToken": "abc123..."
}
```

Server:

```text
refresh token
      ↓
hash
      ↓
find database record
      ↓
exists?
      ↓
not revoked?
      ↓
not expired?
      ↓
load user
      ↓
load current roles/permissions
      ↓
create NEW access token
```

Notice something extremely important:

### **We can reload permissions here.**

That solves one of JWT’s biggest problems.

---

# **11. Permission changes**

Imagine Alice logs in at 10:00.

Her access token contains:

```text
posts.read
posts.create
```

At 10:05 an administrator removes:

```text
posts.create
```

from Alice’s role.

Her existing access token still says:

```text
posts.read
posts.create
```

because JWTs are self-contained.

Therefore, until that access token expires:

```text
Alice → posts.create
```

may still be authorized.

That’s the tradeoff.

---

# **12. Short-lived access tokens reduce the window**

Suppose:

```text
access token = 15 minutes
```

Alice’s permission changes at:

```text
10:05
```

Her old token could remain usable until approximately:

```text
10:15
```

assuming no additional revocation mechanism.

At refresh:

```text
10:15
```

we reload Alice’s current permissions:

```text
posts.read
```

and issue a new token without:

```text
posts.create
```

So:

```text
OLD TOKEN
posts.read
posts.create

        ↓ expires

NEW TOKEN
posts.read
```

This is one reason short-lived access tokens are useful.

---

# **13. But what if we need immediate revocation?**

Suppose Alice’s account is compromised.

Waiting 15 minutes might be unacceptable.

We need a way to invalidate credentials immediately.

There are several strategies.

### **Strategy A — revoke refresh tokens**

Set:

```text
revoked_at = NOW()
```

Then Alice cannot obtain new access tokens.

Simple and useful.

But:

Existing JWT access tokens remain valid until they expire.

### **Strategy B — access-token denylist**

Store revoked JWT identifiers (`jti`) somewhere such as Redis.

Then every request checks:

```text
jti revoked?
```

This makes JWT authentication less purely stateless.

### **Strategy C — token version**

Store something like:

```text
users.token_version
```

JWT contains:

```text
tokenVersion = 5
```

If we increment the user’s database value:

```text
tokenVersion = 6
```

all existing tokens containing version `5` become invalid.

But this requires checking the current version during requests, which again introduces state/database/cache access.

There isn’t a magic solution where you simultaneously get:

```text
completely stateless
+
instant revocation
+
no additional lookup
```

Those goals conflict.

---

# **14. Logout**

JWT logout is often misunderstood.

Suppose Alice has:

```text
access token
refresh token
```

She clicks:

Logout

What does the server actually do?

If the access token is a self-contained JWT and the server doesn’t maintain a denylist, simply deleting it from the client doesn’t invalidate it cryptographically.

The server doesn’t automatically know the client deleted it.

So our logout endpoint can revoke the refresh token:

```text
POST /auth/logout
       ↓
identify refresh token
       ↓
hash it
       ↓
database
       ↓
revoked_at = NOW()
```

Then:

```text
refresh → rejected
```

The current access token still works until it expires.

That’s why a short access-token lifetime matters.

---

# **15. Logout everywhere**

Now consider:

```text
Alice
 ├── laptop refresh token
 ├── phone refresh token
 └── tablet refresh token
```

If she chooses:

Log out everywhere

we can revoke all of them:

```sql
UPDATE refresh_tokens
SET revoked_at = CURRENT_TIMESTAMP
WHERE user_id = ? 
  AND revoked_at IS NULL;
```

Then:

```text
laptop → can't refresh
phone  → can't refresh
tablet → can't refresh
```

Again, existing access JWTs expire naturally unless we also implement access-token revocation.

---

# **16. Refresh token rotation**

There’s another important security technique:

**Refresh token rotation.**

Instead of allowing:

```text
refresh token A
    ↓
refresh token A
    ↓
refresh token A
```

we do:

```text
refresh token A
    ↓
use A
    ↓
revoke A
    ↓
create B
```

So:

```text
A → B → C → D
```

Each refresh token is intended for a single rotation step.

This makes replay detection possible.

For example:

```text
Alice legitimately uses A
       ↓
A revoked
       ↓
B issued
```

If someone later tries:

```text
A
```

again, we know something is wrong.

We can revoke the token family/session.

---

# **17. Token families**

We can make the database slightly more sophisticated:

```text
refresh_tokens

id
user_id
token_hash
family_id
expires_at
revoked_at
created_at
```

Then:

```text
family A
   │
   ├── token A
   ├── token B
   └── token C
```

If token reuse is detected:

```text
token A used twice
       ↓
possible replay
       ↓
revoke family A
```

This is an advanced topic, but it’s important to understand the idea before blindly copying refresh-token implementations from tutorials.

---

# **18. Why not make refresh tokens JWTs too?**

You can.

OAuth 2.0 systems can use different token formats, and Spring Authorization Server supports the refresh-token grant.  

But for our learning project, opaque refresh tokens are easier to reason about:

```text
Access token
    ↓
JWT
    ↓
stateless validation

Refresh token
    ↓
random opaque secret
    ↓
database-controlled lifecycle
```

That’s a useful separation.

---

# 

# 

# **19. A**

**`RefreshToken`**

**entity**

Conceptually:

```java
@Entity
@Table(name = "refresh_tokens")
public class RefreshToken {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @Column(name = "token_hash", nullable = false, unique = true)
    private String tokenHash;

    @Column(name = "expires_at", nullable = false)
    private Instant expiresAt;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "revoked_at")
    private Instant revokedAt;
}
```

Repository:

```java
public interface RefreshTokenRepository
        extends JpaRepository<RefreshToken, Long> {

    Optional<RefreshToken> findByTokenHash(String tokenHash);
}
```

---

# **20. Generating the refresh token**

We want cryptographically strong random bytes.

Conceptually:

```java
SecureRandom secureRandom = new SecureRandom();

byte[] bytes = new byte[32];
secureRandom.nextBytes(bytes);
```

Then encode them as a transport-safe string, such as Base64 URL encoding.

The client receives:

```text
random-secret
```

but the database stores:

```text
SHA-256(random-secret)
```

---

# **21. Hashing the refresh token**

Conceptually:

```java
MessageDigest digest =
        MessageDigest.getInstance("SHA-256");

byte[] hash =
        digest.digest(token.getBytes(StandardCharsets.UTF_8));
```

Then encode the hash for storage.

The important distinction:

```text
Client
    ↓
raw refresh token

Database
    ↓
hash(refresh token)
```

When the client refreshes:

```text
incoming token
    ↓
hash
    ↓
compare database value
```

---

# **22. The refresh service**

Conceptually:

```text
refresh(refreshToken)
       ↓
hash
       ↓
find token
       ↓
validate lifecycle
       ↓
load user
       ↓
authenticate current user state
       ↓
create new access JWT
       ↓
rotate refresh token
```

One subtle point:

We don’t necessarily need to run the user’s password authentication again.

The refresh token itself represents the server’s previously established authorization to obtain a new access token.

But we **do** need to validate the refresh token and its lifecycle carefully.

---

# **23. Refreshing should use current permissions**

This is the important connection to Lesson 19.

Suppose:

```text
10:00
Alice
USER
 ├── posts.read
 └── posts.create
```

Alice receives:

```text
Access JWT #1
```

Then:

```text
10:05
ADMIN removes posts.create
```

At:

```text
10:15
```

Alice refreshes.

The refresh service should load Alice’s **current** roles and permissions:

```text
USER
 └── posts.read
```

Then create:

```text
Access JWT #2
```

containing only:

```text
posts.read
```

This is a major reason to keep access tokens short-lived.

---

# **24. The complete lifecycle**

Now ProjectHub looks like:

```text
                         LOGIN
                           │
                           ▼
                  username + password
                           │
                           ▼
                 AuthenticationManager
                           │
                           ▼
                    Authentication
                      /         \
                     /           \
                    ▼             ▼
             Access JWT       Refresh Token
                15 min            7 days
                   │                 │
                   │                 ▼
                   │             PostgreSQL
                   │
                   ▼
              API requests
                   │
                   ▼
              JWT validation
                   │
                   ▼
              Authorization
```

When access expires:

```text
Refresh Token
      │
      ▼
POST /auth/refresh
      │
      ▼
load current user
      │
      ▼
load current permissions
      │
      ▼
new Access JWT
      │
      ▼
new Refresh Token
```

---

# **25. One more important architectural distinction**

At this point, ProjectHub has **three kinds of state**:

### **Database state**

```text
User
Role
Permission
RefreshToken
```

### **Access-token state**

```text
JWT
```

which is intentionally self-contained.

### **Refresh-token state**

```text
stored server-side
```

This gives us:

```text
JWT → fast request authorization
Refresh token → controlled session continuation
Database → source of truth
```

That’s a very useful mental model.

---

# **26. Where Redis will eventually fit**

Later in ProjectHub, we’ll introduce Redis.

A good use case is:

```text
JWT revocation
```

For example:

```text
revoked:jti:<token-id>
```

with an expiration matching the JWT.

Then:

```text
request
 ↓
JWT valid?
 ↓
Redis says revoked?
 ├── yes → reject
 └── no  → continue
```

We don’t need Redis yet.

I want you to understand **why** we’d introduce it before we introduce the technology.

---

# **27. What we’re deliberately not doing yet**

We are **not** implementing:

- OAuth login with Google/GitHub
- Authorization Code flow
- OpenID Connect
- DPoP
- multi-device session UI
- Redis revocation
- key rotation
- distributed authorization
- multi-tenant permissions

Those are later topics.

Spring Security’s current authorization-server implementation supports standards such as Authorization Code and Refresh Token grants, but ProjectHub’s custom username/password + JWT flow is intentionally being built first so you understand the mechanics.  

---

# **Exercise 23**

Before we move to advanced authorization, design these three endpoints:

```text
POST /auth/login
POST /auth/refresh
POST /auth/logout
```

And explain their behavior.

### **`/auth/login`**

Input:

```json
{
  "username": "alice",
  "password": "secret123"
}
```

Output:

```json
{
  "accessToken": "...",
  "refreshToken": "...",
  "tokenType": "Bearer",
  "expiresIn": 900
}
```

### **`/auth/refresh`**

Input:

```json
{
  "refreshToken": "..."
}
```

Explain:

1. How do we find the database record?
2. How do we determine whether it’s expired?
3. How do we determine whether it was revoked?
4. Why should we load Alice’s **current** permissions?
5. Why should the old refresh token be rotated?

### **`/auth/logout`**

Explain:

1. What should happen to the refresh token?
2. What happens to the already-issued access JWT?
3. Why doesn’t simply deleting the JWT from the client immediately invalidate it on the server?
4. How would “logout everywhere” differ from normal logout?

---

## **The most important thing to remember**

Don’t think:

“JWT is the authentication system.”

Think:

```text
Password authentication
        ↓
creates authentication
        ↓
access JWT represents that authentication
        ↓
refresh token extends the session
        ↓
database remains the source of truth
        ↓
authorization determines what the authenticated user may do
```

**Next lesson:** we’ll move into **resource-level authorization** — the difference between:

```text
posts.delete
```

and:

```text
Can Alice delete THIS specific post?
```

That’s where ProjectHub’s permissions, project memberships, ownership, and Spring Security method authorization really come together.