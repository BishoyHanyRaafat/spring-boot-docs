---
title: Lesson 19: Database-Backed Roles & Permissions
sidebar_position: 19
---

Now we turn the permissions we discussed earlier into **real database-backed authorization**.

The goal is that ProjectHub can eventually answer:

“What is this user’s identity, and what is this user allowed to do?”

Spring Security represents permissions and roles as `GrantedAuthority` objects, which are then used by its authorization mechanisms.  

---

## **1. Why move permissions into the database?**

Previously we had something like:

```java
.authorities("posts.read")
```

That was useful for learning, but it is hardcoded.

Imagine we have:

```text
Alice → USER
Bob   → ADMIN
```

And:

```text
USER
 ├── posts.read
 └── posts.create

ADMIN
 ├── posts.read
 ├── posts.create
 └── posts.delete
```

We want the database to describe those relationships.

Then changing Bob from `ADMIN` to `USER` doesn’t require changing Java code.

---

# **2. Roles vs permissions**

This distinction is extremely important.

### **Permission**

A permission describes **one capability**:

```text
posts.read
posts.create
posts.delete
comments.create
projects.create
```

### **Role**

A role is a **collection of permissions**:

```text
USER
 ├── posts.read
 └── posts.create

ADMIN
 ├── posts.read
 ├── posts.create
 └── posts.delete
```

So:

```text
Role
  ↓
Permissions
```

And:

```text
User
  ↓
Roles
  ↓
Permissions
```

This gives us:

```text
User → Role → Permission
```

---

# **3. Database design**

For ProjectHub, we can start with four tables.

```text
users
roles
permissions
user_roles
role_permissions
```

Conceptually:

```text
users
  │
  │
  ▼
user_roles
  │
  ▼
roles
  │
  ▼
role_permissions
  │
  ▼
permissions
```

The SQL structure:

```sql
CREATE TABLE permissions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE roles (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE role_permissions (
    role_id BIGINT NOT NULL REFERENCES roles(id),
    permission_id BIGINT NOT NULL REFERENCES permissions(id),
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE user_roles (
    user_id BIGINT NOT NULL REFERENCES users(id),
    role_id BIGINT NOT NULL REFERENCES roles(id),
    PRIMARY KEY (user_id, role_id)
);
```

Notice something important:

There is **no direct** **`user_permissions`** **table**.

That’s because we’re saying:

Users receive permissions through roles.

---

# **4. ProjectHub example**

Suppose we have:

```text
permissions

posts.read
posts.create
posts.delete
```

And:

```text
roles

USER
ADMIN
```

Then:

```text
USER
 ├── posts.read
 └── posts.create

ADMIN
 ├── posts.read
 ├── posts.create
 └── posts.delete
```

And:

```text
Alice → USER
Bob   → ADMIN
```

Therefore:

```text
Alice
 ↓
USER
 ↓
posts.read
posts.create
```

while:

```text
Bob
 ↓
ADMIN
 ↓
posts.read
posts.create
posts.delete
```

This is **RBAC** — Role-Based Access Control.

---

# **5. Important distinction: global roles vs project roles**

ProjectHub will eventually have something like:

```text
Global application role:
ADMIN
USER
```

But we will also have:

```text
Project membership:
OWNER
MEMBER
```

These are **not necessarily the same thing**.

For example:

```text
Alice
Global role: USER

Project A:
OWNER

Project B:
MEMBER
```

Alice can be an ordinary application user but the owner of one particular project.

That means we shouldn’t put everything into one giant role system.

Later we’ll have:

```text
Global authorization
        +
Resource/project authorization
```

For now, we’re learning global roles and permissions.

---

# **6. JPA entities**

Let’s create a `Permission`.

```java
@Entity
@Table(name = "permissions")
public class Permission {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 100)
    private String name;
}
```

For example:

```text
Permission
----------------
id: 1
name: posts.read
```

Then `Role`:

```java
@Entity
@Table(name = "roles")
public class Role {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 50)
    private String name;

    @ManyToMany
    @JoinTable(
        name = "role_permissions",
        joinColumns = @JoinColumn(name = "role_id"),
        inverseJoinColumns = @JoinColumn(name = "permission_id")
    )
    private Set<Permission> permissions = new HashSet<>();
}
```

The important relationship is:

```text
Role ←→ Permission
```

through:

```text
role_permissions
```

---

# **7. Connecting User to Role**

Your `User` entity can have:

```java
@ManyToMany
@JoinTable(
    name = "user_roles",
    joinColumns = @JoinColumn(name = "user_id"),
    inverseJoinColumns = @JoinColumn(name = "role_id")
)
private Set<Role> roles = new HashSet<>();
```

Now the complete object relationship is:

```text
User
 │
 │ roles
 ▼
Role
 │
 │ permissions
 ▼
Permission
```

For example:

```text
user.roles
     ↓
   ADMIN
     ↓
permissions
     ↓
posts.read
posts.create
posts.delete
```

---

# **8. How does Spring Security see this?**

This is the key part.

Spring Security doesn’t care that your database happens to contain:

```text
User
Role
Permission
```

It ultimately wants:

```java
GrantedAuthority
```

The `GrantedAuthority` interface exposes an authority as a string, and `SimpleGrantedAuthority` is the standard implementation for string authorities.  

So we transform:

```text
Permission
    ↓
GrantedAuthority
```

For example:

```java
new SimpleGrantedAuthority("posts.read")
```

Then:

```java
new SimpleGrantedAuthority("posts.create")
```

and:

```java
new SimpleGrantedAuthority("posts.delete")
```

---

# **9. Updating UserDetailsService**

Previously we had something roughly like:

```java
return User.withUsername(user.getUsername())
        .password(user.getPasswordHash())
        .authorities("posts.read")
        .build();
```

Now we want to derive authorities from the database.

Conceptually:

```java
Set<GrantedAuthority> authorities =
        user.getRoles().stream()
                .flatMap(role -> role.getPermissions().stream())
                .map(permission ->
                        new SimpleGrantedAuthority(permission.getName()))
                .collect(Collectors.toSet());
```

Then:

```java
return User.withUsername(user.getUsername())
        .password(user.getPasswordHash())
        .authorities(authorities)
        .build();
```

Now there’s no hardcoded:

```text
posts.read
```

in our authentication code.

The database determines it.

`UserDetailsService` is specifically the Spring Security strategy for loading user-specific data and is used by `DaoAuthenticationProvider`.  

---

# **10. What happens during login?**

Eventually our authentication flow will look like this:

```text
username + password
        │
        ▼
AuthenticationManager
        │
        ▼
DaoAuthenticationProvider
        │
        ▼
UserDetailsService
        │
        ▼
Database
        │
        ├── User
        ├── Roles
        └── Permissions
        │
        ▼
UserDetails
        │
        ▼
PasswordEncoder
        │
        ▼
Authentication
        │
        ▼
SecurityContext
```

And the resulting `Authentication` contains authorities such as:

```text
posts.read
posts.create
posts.delete
```

Spring Security then uses those authorities during authorization.  

---

# **11. Then authorization becomes simple**

Our controller/security configuration can still say:

```java
.requestMatchers(HttpMethod.GET, "/posts/**")
    .hasAuthority("posts.read")

.requestMatchers(HttpMethod.POST, "/projects/*/posts")
    .hasAuthority("posts.create")

.requestMatchers(HttpMethod.DELETE, "/posts/**")
    .hasAuthority("posts.delete")
```

The important thing is that:

```java
hasAuthority("posts.delete")
```

doesn’t care **why** the user has the permission.

It only asks:

Does the current Authentication contain `posts.delete`?

That’s exactly the abstraction Spring Security provides.  

---

# 

# 

# **12. What about**

**`hasRole()`**

**?**

We can also expose roles as authorities.

For example:

```java
new SimpleGrantedAuthority("ROLE_ADMIN")
```

Then:

```java
.hasRole("ADMIN")
```

matches that authority.

Spring Security’s default role convention uses the `ROLE_` prefix.  

So you could have both:

```text
ROLE_ADMIN
posts.read
posts.create
posts.delete
```

in the `Authentication`.

However, for ProjectHub, I want you to think of:

```text
ROLE_ADMIN
```

as a **grouping concept**, while:

```text
posts.delete
```

is the actual capability.

That keeps permission-based authorization very explicit.

---

# **13. Why load the relationships during authentication?**

Here’s a subtle JPA problem.

Suppose:

```java
user.getRoles()
```

is lazy.

Then:

```java
user.getRoles()
    .stream()
    .flatMap(...)
```

might trigger lazy-loading.

If the persistence context is already closed, you can encounter:

```text
LazyInitializationException
```

So authentication needs to deliberately load the data it needs.

One approach is an entity graph.

Spring Data JPA supports `@EntityGraph` for configuring which relationships should be fetched for a repository query.  

For example, conceptually:

```java
@EntityGraph(attributePaths = {
    "roles",
    "roles.permissions"
})
Optional<User> findByUsername(String username);
```

Now when authentication loads the user, we explicitly request:

```text
User
 └── roles
      └── permissions
```

rather than relying on accidental lazy loading.

This is an important connection between what you learned in JPA and what you’re learning in Security.

---

# **14. Don’t let users assign themselves ADMIN**

This is a critical security rule.

Your registration request might contain:

```json
{
  "username": "alice",
  "email": "alice@example.com",
  "password": "secret"
}
```

It should **not** contain:

```json
{
  "role": "ADMIN"
}
```

and blindly trust it.

Otherwise someone could simply register:

```text
username = hacker
role = ADMIN
```

Instead, your application decides the initial role.

For example:

```text
New user
   ↓
USER
```

Later, an authorized administrative operation can change roles.

---

# **15. Flyway seed data**

Since we already learned Flyway, this is a perfect place to use it.

For example, a migration could create the initial permissions:

```sql
INSERT INTO permissions (name)
VALUES
    ('posts.read'),
    ('posts.create'),
    ('posts.delete');
```

And roles:

```sql
INSERT INTO roles (name)
VALUES
    ('USER'),
    ('ADMIN');
```

Then the join tables connect them.

Conceptually:

```text
USER
 ├── posts.read
 └── posts.create

ADMIN
 ├── posts.read
 ├── posts.create
 └── posts.delete
```

The exact migration SQL for retrieving generated IDs is something we’ll implement together rather than hiding it behind a giant script.

---

# **16. One very important architecture idea**

We now have three different layers of authorization.

### **Layer 1 — Authentication**

```text
Who are you?
```

Example:

```text
alice
```

### **Layer 2 — General permission**

```text
Are you allowed to delete posts?
```

Example:

```text
posts.delete
```

### **Layer 3 — Resource authorization**

```text
Are you allowed to delete THIS particular post?
```

For example:

```text
DELETE /posts/42
```

Alice may have:

```text
posts.delete
```

but perhaps post `42` belongs to Bob.

So:

```text
posts.delete
```

doesn’t automatically mean:

```text
Alice can delete every post.
```

This distinction is going to become **very important** in our next authorization lessons.

Spring Security’s own documentation distinguishes application-wide authorities from permissions specific to individual domain objects.  

---

# **Your exercise 🧠**

Don’t implement everything yet. I want to make sure the model is clear first.

### **Part A — Database**

Design these five tables:

```text
users
roles
permissions
user_roles
role_permissions
```

Then answer:

1. Why don’t we need `user_permissions` yet?
2. What does `role_permissions` represent?
3. What does `user_roles` represent?
4. Why should `Permission.name` be unique?
5. Why is `USER` → `posts.read` better than hardcoding `"posts.read"` inside `UserDetailsService`?

### **Part B — Java**

Create:

```text
Permission
Role
```

and add the role relationship to:

```text
User
```

Then explain this chain in your own words:

```text
User
 ↓
Role
 ↓
Permission
 ↓
GrantedAuthority
 ↓
Spring Security authorization
```

### **Part C — Security**

Explain what happens when Alice sends:

```http
DELETE /posts/42
```

and Alice has:

```text
USER
 ├── posts.read
 └── posts.create
```

but does **not** have:

```text
posts.delete
```

Then tell me what should happen if Alice _does_ have `posts.delete`, but post `42` belongs to Bob.

Don’t worry about JWT yet.

**Send me your entities + answers, and I’ll review them before we move on to login with** **`AuthenticationManager`****.**