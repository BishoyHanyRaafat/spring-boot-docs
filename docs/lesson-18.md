---
title: Lesson 18: Real Users, Password Hashing, UserDetails, and Authentication
sidebar_position: 18
---

Now we’re going to turn our abstract security model into a real authentication system.

By the end of this lesson, you should understand this entire flow:

```text
Username + password
        ↓
Authentication request
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
Authentication successful
        ↓
SecurityContext
```

This is the foundation we’ll later use for JWT.

The current Spring Security 7.1.1 documentation describes `DaoAuthenticationProvider` as the provider that retrieves a user through `UserDetailsService` and validates the supplied password using `PasswordEncoder`.  

---

# **1. First: never store passwords directly**

Suppose Alice registers:

```text
username = alice
password = MySecret123
```

**Never** store:

```text
password = MySecret123
```

in PostgreSQL.

If the database is compromised, the attackers immediately have everyone’s passwords.

Instead, store a password hash.

Conceptually:

```text
"MySecret123"
       ↓
 Password hashing
       ↓
"$2a$10$......"
```

The database contains the hash, not the original password.

Spring Security’s `PasswordEncoder` exists specifically for securely transforming passwords for storage and later comparison.  

---

# **2. Hashing is not encryption**

This distinction is extremely important.

### **Encryption**

```text
plaintext
   ↓
 encryption
   ↓
ciphertext
   ↓
decryption
   ↓
plaintext
```

You can recover the original value with the key.

### **Password hashing**

```text
password
   ↓
hash
   ↓
stored hash
```

There shouldn’t be a normal operation:

```text
hash → original password
```

That’s intentional.

A password hash is designed for **verification**, not recovery.

---

# **3. How do we verify a password?**

Suppose the database contains:

```text
username: alice
password_hash: $2a$10$...
```

Alice logs in:

```text
username: alice
password: MySecret123
```

We don’t do:

```text
decrypt(storedHash)
```

Instead:

```text
"MySecret123"
      ↓
PasswordEncoder.matches(...)
      ↓
Does it match stored hash?
      ↓
YES
```

Conceptually:

```java
passwordEncoder.matches(
    suppliedPassword,
    storedPasswordHash
);
```

That’s the fundamental password authentication operation.

---

# 

# **4.**

**`PasswordEncoder`**

Spring Security provides:

```java
PasswordEncoder
```

It’s an interface.

For example:

```java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
}
```

Spring Security’s current documentation describes `DelegatingPasswordEncoder` as a way to support current password-storage recommendations while also allowing migration between encoding schemes.  

You can also explicitly configure an encoder such as BCrypt.

The important architectural point is:

```text
Application
    ↓
PasswordEncoder interface
    ↓
actual hashing algorithm
```

Your service doesn’t need to know the hashing implementation.

---

# **5. Why not just use SHA-256?**

This is a common beginner question.

You might think:

```java
SHA-256(password)
```

would be enough.

It isn’t appropriate as a password-storage strategy by itself.

Passwords are generally low-entropy secrets. Attackers can try huge numbers of guesses against fast hashes.

Password hashing algorithms are intentionally designed to make guessing expensive.

Spring Security’s `PasswordEncoder` abstraction exists to use password-specific encoders and allow the strategy to evolve. Its documentation identifies BCrypt as a preferred implementation and also supports other password encoders.  

---

# **6. Registration flow**

Let’s start with registration.

Alice sends:

```http
POST /auth/register
```

```json
{
  "username": "alice",
  "email": "alice@example.com",
  "password": "MySecret123"
}
```

Our application should do:

```text
Request
   ↓
Validate
   ↓
Check username/email
   ↓
Hash password
   ↓
Create User
   ↓
Save User
```

The critical step:

```java
String hash = passwordEncoder.encode(request.password());
```

Then:

```java
user.setPasswordHash(hash);
```

The plaintext password should not be persisted.

---

# **7. Our User entity**

Let’s create something like:

```java
@Entity
@Table(name = "users")
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 50)
    private String username;

    @Column(nullable = false, unique = true)
    private String email;

    @Column(name = "password_hash", nullable = false)
    private String passwordHash;

    // getters/setters
}
```

Notice the name:

```java
passwordHash
```

rather than:

```java
password
```

That’s a small naming choice that communicates an important security property.

---

# **8. Registration service**

Conceptually:

```java
@Service
public class UserService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;

    public UserService(
            UserRepository userRepository,
            PasswordEncoder passwordEncoder) {

        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
    }

    @Transactional
    public User register(CreateUserRequest request) {

        String passwordHash =
                passwordEncoder.encode(request.password());

        User user = new User();

        user.setUsername(request.username());
        user.setEmail(request.email());
        user.setPasswordHash(passwordHash);

        return userRepository.save(user);
    }
}
```

The important relationship is:

```text
UserService
    │
    └── PasswordEncoder
```

The service doesn’t implement cryptography itself.

---

# **9. Now the interesting part: login**

Suppose Alice sends:

```http
POST /auth/login
```

```json
{
  "username": "alice",
  "password": "MySecret123"
}
```

Who actually checks the password?

You might initially think:

```java
userRepository.findByUsername(...)
passwordEncoder.matches(...)
```

inside your controller.

You **could** write such code, but Spring Security already provides an authentication architecture for this.

That’s where these concepts come in:

```text
AuthenticationManager
AuthenticationProvider
UserDetailsService
UserDetails
PasswordEncoder
```

---

# 

# **10.**

**`UserDetailsService`**

The name sounds complicated, but the idea is simple.

Spring Security asks:

“Give me the security-related information for this username.”

The interface is essentially:

```java
public interface UserDetailsService {

    UserDetails loadUserByUsername(String username);
}
```

That’s its core operation.  

So:

```text
Spring Security
      ↓
loadUserByUsername("alice")
      ↓
UserDetails
```

It doesn’t necessarily mean your database table has to be named `users`.

`UserDetailsService` is an abstraction over however you retrieve user security information.

Spring Security provides in-memory, JDBC, and custom `UserDetailsService` implementations.  

---

# 

# **11. Our database-backed**

**`UserDetailsService`**

We already have:

```java
UserRepository
```

So we can create:

```java
@Service
public class CustomUserDetailsService
        implements UserDetailsService {

    private final UserRepository userRepository;

    public CustomUserDetailsService(
            UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {

        User user = userRepository
                .findByUsername(username)
                .orElseThrow(() ->
                        new UsernameNotFoundException(
                                "User not found"));

        return ...;
    }
}
```

The missing part is:

```java
return ...;
```

That’s where `UserDetails` comes in.

---

# 

# 

# **12. What is**

**`UserDetails`**

**?**

`UserDetails` is Spring Security’s representation of the authenticated user’s security information.

Conceptually:

```text
UserDetails
│
├── username
├── password
├── authorities
├── enabled
├── accountNonExpired
├── accountNonLocked
└── credentialsNonExpired
```

Your domain entity:

```text
User
├── id
├── username
├── email
├── passwordHash
└── ...
```

is **not necessarily the same thing** as `UserDetails`.

That’s an important distinction.

---

# **13. Domain User vs Security User**

Think:

```text
Your application
      ↓
     User
```

and:

```text
Spring Security
      ↓
  UserDetails
```

The domain object answers:

What is a user in ProjectHub?

`UserDetails` answers:

What does Spring Security need to know about this user for authentication and authorization?

They can be related without being identical.

---

# **14. Mapping our User to UserDetails**

For now, we could use Spring Security’s `User` implementation:

```java
return org.springframework.security.core.userdetails.User
        .withUsername(user.getUsername())
        .password(user.getPasswordHash())
        .authorities("posts.read")
        .build();
```

Don’t worry about permissions yet.

We’re temporarily hardcoding one authority just to understand the authentication pipeline.

Later:

```text
Database
   ↓
User
   ↓
Roles
   ↓
Permissions
   ↓
UserDetails
   ↓
GrantedAuthority
```

We’ll build that properly in the next lessons.

---

# 

# **15.**

**`DaoAuthenticationProvider`**

Now the pieces connect.

Spring Security has:

```text
DaoAuthenticationProvider
```

“DAO” here basically means it gets user information from a data-access strategy.

Its job is approximately:

```text
username + password
       ↓
DaoAuthenticationProvider
       ↓
UserDetailsService
       ↓
find user
       ↓
UserDetails
       ↓
PasswordEncoder
       ↓
verify password
```

That’s exactly what the official Spring Security architecture describes.  

---

# **16. The complete authentication flow**

Let’s trace Alice.

### **Request**

```text
username = alice
password = MySecret123
```

### **Step 1**

Spring Security receives the authentication request.

### **Step 2**

It passes authentication to an `AuthenticationManager`.

### **Step 3**

The manager delegates to an appropriate `AuthenticationProvider`.

For username/password authentication, that’s commonly:

```text
DaoAuthenticationProvider
```

### **Step 4**

The provider calls:

```text
UserDetailsService
```

with:

```text
alice
```

### **Step 5**

Our service queries PostgreSQL:

```sql
SELECT *
FROM users
WHERE username = 'alice';
```

### **Step 6**

We return:

```text
UserDetails
```

containing the stored password hash.

### **Step 7**

`DaoAuthenticationProvider` uses:

```text
PasswordEncoder
```

to verify the supplied password against the stored hash.

### **Step 8**

If successful:

```text
Authentication
```

is created.

### **Step 9**

The authenticated result is associated with the:

```text
SecurityContext
```

Spring Security’s documentation describes this flow explicitly: the provider retrieves `UserDetails`, validates the password, and returns an authenticated `UsernamePasswordAuthenticationToken` whose principal is the loaded user details.  

---

# **17. The architecture**

Memorize this diagram:

```text
             username
                 +
             password
                 │
                 ▼
       ┌───────────────────┐
       │ Authentication    │
       │ Manager           │
       └─────────┬─────────┘
                 │
                 ▼
       ┌───────────────────┐
       │ DaoAuthentication │
       │ Provider          │
       └─────────┬─────────┘
                 │
          load user
                 │
                 ▼
       ┌───────────────────┐
       │ UserDetailsService│
       └─────────┬─────────┘
                 │
                 ▼
             Repository
                 │
                 ▼
             PostgreSQL
                 │
                 ▼
             UserDetails
                 │
                 ▼
          PasswordEncoder
                 │
                 ▼
       password matches?
            /       \
          no         yes
          │           │
          ▼           ▼
       failure    Authentication
                       │
                       ▼
                SecurityContext
```

If this diagram makes sense, you’ve understood the core of Spring Security username/password authentication.

---

# 

# 

# **18. Where does**

**`AuthenticationManager`**

**fit?**

`AuthenticationManager` is an abstraction:

```java
Authentication authenticate(Authentication authentication)
```

Its job is essentially:

Authenticate this authentication request.

A common implementation is:

```text
ProviderManager
```

which delegates to one or more:

```text
AuthenticationProvider
```

So:

```text
AuthenticationManager
        ↓
ProviderManager
        ↓
AuthenticationProvider
        ↓
DaoAuthenticationProvider
```

Spring Security supports multiple providers because applications can have different authentication mechanisms.

For example:

```text
AuthenticationManager
       │
       ├── DaoAuthenticationProvider
       │
       ├── OAuth provider
       │
       └── custom provider
```

You don’t need to implement these classes yourself in normal applications.

---

# **19. What happens when the password is wrong?**

Suppose Alice sends:

```text
password = WrongPassword
```

The database still contains:

```text
hash(MySecret123)
```

The encoder checks:

```text
WrongPassword
       ↓
doesn't match
       ↓
authentication failure
```

The user doesn’t become authenticated.

The controller shouldn’t manually decide:

```java
if (!matches) {
    return ...
}
```

Spring Security’s authentication machinery handles the authentication failure.

---

# **20. Very important: never compare hashes yourself**

Don’t do:

```java
passwordEncoder.encode(input)
    .equals(storedHash)
```

Password encoders such as BCrypt use a random salt, so encoding the same password twice can produce different encoded values.

Instead:

```java
passwordEncoder.matches(
    rawPassword,
    storedHash
);
```

That’s exactly why `PasswordEncoder` exposes separate encoding and matching operations.

---

# **21. Why two users with the same password can have different hashes**

Alice:

```text
password = Hello123
hash = $2a$10$AAA...
```

Bob:

```text
password = Hello123
hash = $2a$10$BBB...
```

That’s normal.

The salt makes the hashes different.

When Alice logs in:

```text
Hello123
   ↓
matches Alice's hash?
   ↓
yes
```

When Bob logs in:

```text
Hello123
   ↓
matches Bob's hash?
   ↓
yes
```

Same password doesn’t imply same stored hash.

---

# **22. What should the database actually contain?**

Something like:

```text
users
------------------------------------------------
id | username | email              | password_hash
------------------------------------------------
1  | alice    | alice@example.com  | {bcrypt}$2a$...
2  | bob      | bob@example.com    | {bcrypt}$2a$...
```

Never:

```text
password
----------------
MySecret123
password123
qwerty
```

And never log passwords:

```java
log.info("User password: {}", password); // NEVER
```

---

# **23. DelegatingPasswordEncoder**

You’ll often see hashes beginning with:

```text
{bcrypt}
```

For example:

```text
{bcrypt}$2a$10$...
```

That’s associated with Spring Security’s `DelegatingPasswordEncoder`.

The prefix identifies which encoder should be used to verify the stored password.

Conceptually:

```text
{bcrypt}........
   ↑
   algorithm identifier
```

This is useful because password-storage recommendations can evolve.

Spring Security documents `DelegatingPasswordEncoder` specifically as a mechanism for supporting current encodings while allowing older encodings to remain verifiable during migrations.  

---

# **24. Why this is better than hardcoding BCrypt everywhere**

Imagine today’s application uses:

```text
bcrypt
```

Years later you want to migrate to another password hashing strategy.

With a delegating format, the stored password can identify its algorithm.

Conceptually:

```text
{bcrypt}...
{argon2}...
{pbkdf2}...
```

Then the framework knows how to interpret the stored value.

You don’t have to suddenly invalidate every user’s password.

---

# **25. Where registration and authentication differ**

This is another important distinction.

### **Registration**

Your application calls:

```java
passwordEncoder.encode(...)
```

to create the stored hash.

```text
plaintext password
       ↓
PasswordEncoder
       ↓
hash
       ↓
database
```

### **Login**

Spring Security uses:

```java
passwordEncoder.matches(...)
```

to verify the supplied password.

```text
supplied password
       +
stored hash
       ↓
PasswordEncoder.matches()
       ↓
true / false
```

So:

```text
REGISTER → encode

LOGIN → matches
```

---

# **26. Where we’re heading**

Eventually our ProjectHub authentication will look like:

```text
POST /auth/register
       ↓
create User
       ↓
hash password
       ↓
save User


POST /auth/login
       ↓
AuthenticationManager
       ↓
UserDetailsService
       ↓
PostgreSQL
       ↓
PasswordEncoder
       ↓
Authentication
       ↓
JWT
```

And then:

```text
Authorization
       ↓
posts.read
posts.create
posts.delete
       ↓
resource ownership
       ↓
Project membership
```

That’s the security system we’re building.

---

# **Exercise**

Don’t implement JWT yet.

I want you to build the **username/password foundation** first.

### **Part 1 — Entity**

Create:

```java
User
```

with:

```text
id
username
email
passwordHash
```

### **Part 2 — Repository**

Create:

```java
UserRepository
```

with:

```java
Optional<User> findByUsername(String username);
```

### **Part 3 — Password encoder**

Create a Spring bean:

```java
PasswordEncoder
```

Use Spring Security’s delegating password encoder rather than storing plaintext passwords.  

### **Part 4 — UserDetailsService**

Create:

```java
CustomUserDetailsService
```

implementing:

```java
UserDetailsService
```

It should:

```text
username
   ↓
UserRepository
   ↓
User
   ↓
UserDetails
```

### **Part 5 — Registration**

Create:

```text
POST /auth/register
```

with:

```json
{
  "username": "alice",
  "email": "alice@example.com",
  "password": "MySecret123"
}
```

The database should contain the **hash**, not the plaintext password.

### **Part 6 — Security configuration**

Configure:

```text
/auth/register → public
everything else → authenticated
```

For now, you can use HTTP Basic authentication to demonstrate the username/password mechanism; Spring Security’s current documentation supports HTTP Basic and form login as username/password authentication mechanisms.  

---

## **One thing to understand before coding**

There are **three different users** in your head now:

```text
1. User entity
   ↓
   Your application's database representation


2. UserDetails
   ↓
   Spring Security's authentication representation


3. Authentication
   ↓
   The result of successfully authenticating someone
```

They’re related:

```text
Database User
      ↓
UserDetailsService
      ↓
UserDetails
      ↓
authentication succeeds
      ↓
Authentication
      ↓
SecurityContext
```

**Don’t collapse these concepts together.**

Once you build this exercise, send me your code. I’ll review the security configuration and authentication flow, then we’ll move to **Lesson 19 — Database-backed roles and permissions**, where your `posts.read`, `posts.create`, and `posts.delete` model becomes real.