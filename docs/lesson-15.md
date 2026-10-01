---
title: Lesson 15: Database Migrations with Flyway
sidebar_position: 15
---


We’ve now reached an important production concept.

So far, we’ve created database tables manually or conceptually through Hibernate:

```text
Entity
   ↓
Hibernate
   ↓
Database schema
```

That’s convenient for learning.

But imagine your application is already deployed and you need to add:

```text
posts.created_at
```

How do you safely change the database?

You don’t want every developer or server to manually run SQL.

This is what **database migrations** solve.

Spring Boot supports Flyway and Liquibase as higher-level database migration tools, and its documentation recommends using one schema-initialization mechanism rather than mixing Flyway with `schema.sql`/`data.sql`.  

---

# **1. What is a migration?**

A migration is a **versioned change to the database**.

For example:

```text
V1 → create users
V2 → create projects
V3 → create posts
V4 → create comments
V5 → add created_at to posts
```

Each change becomes a file.

```text
db/migration/
│
├── V1__create_users.sql
├── V2__create_projects.sql
├── V3__create_posts.sql
├── V4__create_comments.sql
└── V5__add_created_at_to_posts.sql
```

Flyway applies versioned migrations in order and records what has already been applied in its schema-history table. It also stores checksums so changes to already-applied migrations can be detected.  

---


# **2. Why not just use Hibernate `ddl-auto=update` ?

You may have seen:

```properties
spring.jpa.hibernate.ddl-auto=update
```

This can be useful during experimentation.

But think about production.

Suppose you deploy:

```text
Application v1
Database v1
```

Then six months later you need:

```text
Database v2
```

You want an explicit record:

```text
V7__add_post_status.sql
```

rather than:

“Hibernate looked at my entities and decided what database changes to make.”

With migrations, the database evolution is explicit and version-controlled.

Spring Boot’s documentation specifically notes that if you’re using Flyway or Liquibase, you should use that mechanism alone to initialize the schema.  

---

# **3. The migration history**

Imagine:

```text
V1__create_users.sql
V2__create_projects.sql
V3__create_posts.sql
```

First deployment:

```text
Database
    ↓
V1
    ↓
V2
    ↓
V3
```

Flyway records those migrations.

Later you add:

```text
V4__create_comments.sql
```

Next deployment:

```text
Already applied:
V1
V2
V3

Pending:
V4
```

So Flyway applies only:

```text
V4
```

That’s the key idea.

---

# **4. Migration files are source code**

This is an important mindset.

Your project now has two kinds of code:

```text
src/main/java/
    application code

src/main/resources/db/migration/
    database code
```

Both should be version controlled.

For example:

```text
Git
│
├── Java code
│
├── application configuration
│
└── database migrations
```

Flyway’s documentation describes migrations as SQL changes tracked in version control and used to deploy database changes consistently across environments.  

---

# **5. First migration**

Let’s create:

```text
V1__create_users.sql
```

Contents:

```sql
CREATE TABLE users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    username VARCHAR(50) NOT NULL UNIQUE,

    email VARCHAR(255) NOT NULL UNIQUE
);
```

Then:

```text
V2__create_projects.sql
```

```sql
CREATE TABLE projects (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    name VARCHAR(100) NOT NULL
);
```

Then:

```text
V3__create_posts.sql
```

```sql
CREATE TABLE posts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    title VARCHAR(100) NOT NULL,

    content TEXT NOT NULL,

    author_id BIGINT NOT NULL,

    project_id BIGINT NOT NULL,

    CONSTRAINT fk_posts_author
        FOREIGN KEY (author_id)
        REFERENCES users(id),

    CONSTRAINT fk_posts_project
        FOREIGN KEY (project_id)
        REFERENCES projects(id)
);
```

Notice something important:

**The SQL is now the explicit definition of our database schema.**

---

# **6. Adding comments**

Next:

```text
V4__create_comments.sql
```

```sql
CREATE TABLE comments (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    content TEXT NOT NULL,

    author_id BIGINT NOT NULL,

    post_id BIGINT NOT NULL,

    CONSTRAINT fk_comments_author
        FOREIGN KEY (author_id)
        REFERENCES users(id),

    CONSTRAINT fk_comments_post
        FOREIGN KEY (post_id)
        REFERENCES posts(id)
);
```

And:

```text
V5__create_project_memberships.sql
```

```sql
CREATE TABLE project_memberships (
    project_id BIGINT NOT NULL,

    user_id BIGINT NOT NULL,

    PRIMARY KEY (project_id, user_id),

    CONSTRAINT fk_membership_project
        FOREIGN KEY (project_id)
        REFERENCES projects(id),

    CONSTRAINT fk_membership_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
);
```

Now we have our initial schema.

---

# **7. Adding a column later**

Suppose our product requirement changes.

We need:

```text
posts.created_at
```

**Do not modify:**

```text
V3__create_posts.sql
```

if V3 has already been applied to a shared/permanent environment.

Instead create:

```text
V6__add_created_at_to_posts.sql
```

with:

```sql
ALTER TABLE posts
ADD COLUMN created_at TIMESTAMP WITH TIME ZONE NOT NULL;
```

Now the history is:

```text
V1
 ↓
V2
 ↓
V3
 ↓
V4
 ↓
V5
 ↓
V6
```

The database evolves forward.

Flyway recommends creating a new versioned migration rather than modifying an already-applied versioned migration; checksums help detect accidental modifications.  

---

# **8. Why modifying old migrations is dangerous**

Imagine developer A has:

```text
V3__create_posts.sql
```

and has already deployed it.

Developer B changes V3:

```text
V3__create_posts.sql
```

Now different environments might have effectively different meanings for “V3”.

That’s a disaster waiting to happen.

Instead:

```text
V3 = history
V6 = new change
```

The migration history remains deterministic.

---

# **9. Flyway + Spring Boot**

Spring Boot provides a Flyway starter.

For Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-flyway</artifactId>
</dependency>
```

The current Spring Boot documentation lists `spring-boot-starter-flyway` as the starter for Flyway database migrations.  

For PostgreSQL, Spring Boot’s documentation also notes that the PostgreSQL-specific Flyway database module is required for the PostgreSQL setup.  

So conceptually:

```text
Spring Boot
    │
    ├── PostgreSQL
    │
    └── Flyway
          ↓
      migrations
```

---

# **10. Where do migrations go?**

By default:

```text
src/main/resources/db/migration
```

So your project becomes:

```text
src/
└── main/
    ├── java/
    │   └── com/example/projecthub/
    │
    └── resources/
        ├── application.yaml
        │
        └── db/
            └── migration/
                ├── V1__create_users.sql
                ├── V2__create_projects.sql
                ├── V3__create_posts.sql
                ├── V4__create_comments.sql
                ├── V5__create_project_memberships.sql
                └── V6__add_created_at_to_posts.sql
```

Spring Boot documents `classpath:db/migration` as Flyway’s default migration location.  

---

# **11. What happens when the application starts?**

Conceptually:

```text
Spring Boot starts
      ↓
Flyway starts
      ↓
connect to PostgreSQL
      ↓
inspect migration history
      ↓
find pending migrations
      ↓
apply them
      ↓
JPA/Hibernate starts against the resulting schema
      ↓
application becomes ready
```

Spring Boot automatically invokes Flyway migration when Flyway is configured on the classpath.  

So you don’t need to manually execute:

```text
V1
V2
V3
...
```

every time.

---

# **12. The schema history table**

Flyway maintains a table to track migrations.

By default, the table is:

```text
flyway_schema_history
```

Spring Boot’s current configuration documentation lists that as Flyway’s default history-table name.  

Conceptually it contains information such as:

```text
version | description       | state
---------------------------------------
1       | create users      | SUCCESS
2       | create projects   | SUCCESS
3       | create posts      | SUCCESS
4       | create comments   | SUCCESS
```

The exact columns are more extensive.

This table is how Flyway knows:

“V1, V2, V3 and V4 have already been applied.”

---

# **13. What happens when a migration fails?**

Suppose:

```text
V1 ✅
V2 ✅
V3 ❌
```

Flyway reports the failure rather than silently pretending everything is okay.

Your application startup can therefore fail.

That’s desirable.

Imagine your Java application expects:

```text
posts.created_at
```

but the migration creating it failed.

You don’t want:

```text
Application says: "Everything is fine."
Database says: "No such column."
```

Failing startup early is much safer.

---

# **14. Migration + Entity must agree**

Now we have two representations:

### **Database**

```sql
CREATE TABLE posts (
    id BIGINT ...,
    title VARCHAR(100),
    content TEXT,
    author_id BIGINT,
    created_at TIMESTAMP WITH TIME ZONE
);
```

### **Java**

```java
@Entity
@Table(name = "posts")
public class Post {

    @Id
    private Long id;

    private String title;

    private String content;

    private Instant createdAt;

    @ManyToOne(fetch = FetchType.LAZY)
    private User author;
}
```

These need to agree.

But they have **different responsibilities**.

The migration defines:

What the database actually looks like.

The entity defines:

How Java maps to that database.

---


# 15. This is why `ddl-auto=validate` is useful

Once Flyway owns schema creation, we don’t want Hibernate modifying the schema.

A useful configuration is:

```yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
```

The idea is:

```text
Flyway
  ↓
creates/migrates schema

Hibernate
  ↓
checks that entity mappings match schema
```

Hibernate isn’t supposed to modify the database structure.

It’s essentially:

“Does the schema I found match what my entities expect?”

This creates a nice separation of responsibilities.

---

# **16. Avoid this combination**

Don’t build a production setup where:

```text
Flyway
   +
ddl-auto=update
   +
schema.sql
   +
data.sql
```

all compete to initialize or modify the same schema.

Spring Boot explicitly recommends using a single schema-generation mechanism and warns against mixing basic SQL initialization with Flyway/Liquibase.  

For our project we’ll use:

```text
Flyway → schema changes

Hibernate/JPA → ORM mapping

ddl-auto=validate → verify mapping
```

That’s a clean division.

---

# **17. What about seed data?**

Suppose we want default permissions:

```text
posts.read
posts.create
posts.delete
```

We could have a migration:

```text
V7__insert_default_permissions.sql
```

```sql
INSERT INTO permissions (name)
VALUES
    ('posts.read'),
    ('posts.create'),
    ('posts.delete');
```

That’s useful for **reference data** that should exist consistently across environments.

Flyway versioned migrations can contain data changes as well as schema changes.  

But don’t use migrations as a dumping ground for arbitrary user/test data.

---

# **18. Repeatable migrations**

Flyway also has **repeatable migrations**.

They use:

```text
R__something.sql
```

For example:

```text
R__create_post_summary_view.sql
```

Unlike versioned migrations, repeatable migrations are reapplied when their checksum changes. They’re commonly useful for objects such as views, procedures, and functions.  

You don’t need these yet.

For ProjectHub, our initial focus is:

```text
V1
V2
V3
...
```

---

# **19. A real development workflow**

Imagine you’re adding post editing.

### **Step 1 — Change database**

Create:

```text
V8__add_updated_at_to_posts.sql
```

```sql
ALTER TABLE posts
ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE;
```

### **Step 2 — Change entity**

```java
private Instant updatedAt;
```

### **Step 3 — Application code**

```java
post.setUpdatedAt(Instant.now());
```

### **Step 4 — Commit everything**

```text
Git commit
│
├── V8__add_updated_at_to_posts.sql
├── Post.java
└── PostService.java
```

Now someone else can clone the project and get the same database evolution.

---

# **20. Development → Test → Production**

This is where migrations become really valuable.

Imagine three environments:

```text
Developer DB
Test DB
Production DB
```

All use:

```text
V1
V2
V3
...
V8
```

So:

```text
Developer ──┐
Test ───────┼── same migration history
Production ─┘
```

The configuration may differ:

```text
database URL
credentials
connection pool
```

but the schema changes come from the same migration source.

That’s one of the major benefits of migration-based deployment. Flyway’s documentation explicitly describes using the same versioned migrations to bring multiple environments to the same schema version.  

---

# **21. A subtle but important deployment problem**

Suppose your new Java code expects:

```java
post.getUpdatedAt()
```

but production doesn’t have `updated_at` yet.

If you deploy Java first:

```text
New application
      ↓
expects new column
      ↓
old database
      ↓
💥
```

Migration ordering therefore matters.

For simple changes:

```text
1. Migration
2. Application
```

can work.

But for more complex zero-downtime deployments, you often use a **backward-compatible migration strategy**.

For example:

### **Deployment 1**

Add nullable column:

```sql
ALTER TABLE posts
ADD COLUMN new_title TEXT;
```

Old application still works.

### **Deployment 2**

New application starts using it.

### **Deployment 3**

Migrate existing data.

### **Deployment 4**

Eventually remove the old column.

This is often called an **expand-and-contract** style migration.

We’ll revisit this when we get to production deployment.

---

# **22. Our ProjectHub migration history**

Let’s establish a clean starting point:

```text
db/migration/

V1__create_users.sql
V2__create_projects.sql
V3__create_posts.sql
V4__create_comments.sql
V5__create_project_memberships.sql
V6__add_created_at_to_posts.sql
```

Later we might have:

```text
V7__create_permissions.sql
V8__create_roles.sql
V9__create_role_permissions.sql
V10__create_user_roles.sql
V11__add_post_status.sql
V12__add_indexes_for_post_search.sql
```

Notice how this gives us a **history of the application**.

You can look at the migrations six months later and understand how the database evolved.

---

# **23. The architecture is getting much more complete**

We’re now at:

```text
                         HTTP
                          │
                          ▼
                     Controller
                          │
                          ▼
                       Service
                    @Transactional
                          │
                          ▼
                     Repository
                          │
                          ▼
                  Spring Data JPA
                          │
                          ▼
                      Hibernate
                          │
                          ▼
                         SQL
                          │
                          ▼
                     PostgreSQL
                          ▲
                          │
                       Flyway
                          │
                    schema changes
```

Notice that Flyway doesn’t sit in the request path.

It’s responsible for:

```text
database evolution
```

while JPA is responsible for:

```text
runtime persistence
```

Those are different jobs.

---
