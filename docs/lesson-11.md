---
title: "Lesson 11: JPA, Hibernate & Spring Data JPA"
sidebar_position: 11
---

Now we’re at one of the most important parts of Spring Boot backend development.

You already understand:

```text
Controller
   ↓
Service
   ↓
Repository
   ↓
PostgreSQL
```

Today we’re going to replace the vague idea of “repository talks to the database” with a concrete understanding of **JPA, Hibernate, and Spring Data JPA**.

---

## **1. The problem JPA solves**

Suppose PostgreSQL has:

```text
posts
--------------------------------
id | title       | author_id
--------------------------------
1  | Spring      | 10
2  | PostgreSQL  | 10
3  | Java        | 20
```

In Java, we’d like to work with:

```java
Post post;
```

rather than manually doing:

```java
ResultSet resultSet = statement.executeQuery(...);
```

and converting every database row ourselves.

Without an ORM, you’d have to repeatedly translate:

```text
Database row
     ↓
Java object
```

and:

```text
Java object
     ↓
SQL INSERT/UPDATE
```

That’s a lot of repetitive code.

**JPA** gives Java a standard way to describe this mapping.

**Hibernate** is a very common implementation of JPA.

And **Spring Data JPA** gives us a convenient repository abstraction on top.

So:

```text
JPA
│
├── specification/API
│
└── defines concepts such as entities, relationships, persistence

Hibernate
│
└── implements JPA

Spring Data JPA
│
└── provides repositories and integrates JPA with Spring
```

That’s the distinction I want you to remember.

---

# **2. ORM**

ORM means:

Object-Relational Mapping.

It maps:

```text
Java                         Database

User                         users
---------------------------------------
id            <----------->  id
username      <----------->  username
email         <----------->  email
```

And:

```text
Post                         posts
---------------------------------------
id            <----------->  id
title         <----------->  title
content       <----------->  content
author        <----------->  author_id
```

So instead of thinking primarily in SQL rows, your application can work with Java objects.

---

# **3. Your first Entity**

Let’s create our `User`.

```java
@Entity
@Table(name = "users")
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String username;

    @Column(nullable = false, unique = true)
    private String email;

    // constructors, getters, setters
}
```

Let’s break this down.

---

## **`@Entity`**

```java
@Entity
```

means:

Hibernate, this Java class represents persistent database data.

So:

```java
public class User
```

becomes conceptually:

```text
Java User
     ↕
database users
```

---

## **`@Table`**

```java
@Table(name = "users")
```

explicitly tells Hibernate which table this entity maps to.

We could potentially let naming conventions handle it, but being explicit is often useful when learning and when database naming conventions matter.

---

# **4. `@Id`**

```java
@Id
private Long id;
```

This tells JPA:

This field is the entity’s primary key.

It corresponds to:

```sql
PRIMARY KEY
```

from our previous lesson.

---

# 5. `@GeneratedValue`

```java
@GeneratedValue(strategy = GenerationType.IDENTITY)
```

means the database generates the ID.

Conceptually:

```text
Java:
new User("alice", "...")

        ↓

Database generates:

id = 1
```

Then Hibernate knows the generated ID.

---


# **6. `@Column`**

```java
@Column(nullable = false, unique = true)
private String username;
```

This corresponds roughly to:

```sql
username VARCHAR(...)
NOT NULL
UNIQUE
```

Again, JPA annotations describe the database mapping.

---

# **7. Entity vs DTO**

This distinction is **extremely important**.

Don’t confuse:

```java
@Entity
public class User
```

with:

```java
public record UserResponse(...) {}
```

They have different purposes.

### **Entity**

Represents persistence/domain data:

```text
User entity
    ↓
database
```

### **DTO**

Represents your API contract:

```text
HTTP request/response
    ↓
DTO
```

For example:

```java
public record UserResponse(
        Long id,
        String username,
        String email
) {}
```

The client receives:

```json
{
  "id": 1,
  "username": "alice",
  "email": "alice@example.com"
}
```

not necessarily the entire entity.

This separation becomes particularly important once we introduce passwords, permissions, relationships, and security.

---

# **8. Our Post entity**

Now let’s map the `posts` table.

```java
@Entity
@Table(name = "posts")
public class Post {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 100)
    private String title;

    @Column(nullable = false)
    private String content;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "author_id", nullable = false)
    private User author;

    // constructors, getters, setters
}
```

And here’s where things get interesting.

---

# **9. `@ManyToOne`**

Remember our SQL:

```text
posts
---------------------------
id | title | author_id
```

Many posts can belong to one user.

Therefore:

```java
@ManyToOne
private User author;
```

means:

```text
Many Post
     │
     ▼
 One User
```

For example:

```text
Alice
 │
 ├── Post 1
 ├── Post 2
 └── Post 3
```

---

# **10. `@JoinColumn`**

This:

```java
@JoinColumn(name = "author_id")
```

says:

The relationship is stored using the `author_id` column in the `posts` table.

So Hibernate understands:

```text
Post.author
     ↕
posts.author_id
     ↕
users.id
```

That’s the bridge between our Java relationship and our SQL foreign key.

---

# **11. What does Hibernate actually do?**

Suppose we write:

```java
Post post = postRepository.findById(1L)
        .orElseThrow();
```

We’re not explicitly writing:

```sql
SELECT ...
FROM posts
WHERE id = 1;
```

Hibernate generates SQL for us.

Conceptually:

```text
postRepository.findById(1)
            ↓
Spring Data JPA
            ↓
Hibernate
            ↓
SQL
            ↓
PostgreSQL
            ↓
row
            ↓
Hibernate
            ↓
Post object
```

This is the magic of ORM.

But remember:

**Hibernate doesn’t eliminate SQL.**

It generates SQL.

That’s why the SQL lesson mattered.

---

# **12. Spring Data JPA**

Now we get to the really convenient part.

Instead of writing a repository implementation ourselves:

```java
@Repository
public class PostRepository {

    // JDBC code...
    // SQL...
    // ResultSet...
    // mapping...
}
```

we can write:

```java
public interface PostRepository
        extends JpaRepository<Post, Long> {
}
```

That’s it.

Spring Data creates the implementation for us.

---

# **13. What does**

**`JpaRepository<Post, Long>`**

**mean?**

The first type:

```java
Post
```

is the entity.

The second:

```java
Long
```

is the ID type.

So:

```java
JpaRepository<Post, Long>
```

means:

Repository for `Post` entities whose primary key is `Long`.

---

# **14. What do we get for free?**

A `JpaRepository` gives us methods such as:

```java
postRepository.findAll();
```

```java
postRepository.findById(id);
```

```java
postRepository.save(post);
```

```java
postRepository.delete(post);
```

```java
postRepository.existsById(id);
```

You didn’t implement those methods.

Spring Data did.

---

# **15. The architecture now looks like this**

We started with:

```text
Controller
   ↓
Service
   ↓
Repository
```

Now we can make it concrete:

```text
HTTP
 ↓
PostController
 ↓
PostService
 ↓
PostRepository
 ↓
Spring Data JPA
 ↓
Hibernate
 ↓
SQL
 ↓
PostgreSQL
```

This is a huge milestone.

---

# **16. Repository → Service**

Our repository:

```java
public interface PostRepository
        extends JpaRepository<Post, Long> {
}
```

Our service:

```java
@Service
public class PostService {

    private final PostRepository postRepository;

    public PostService(PostRepository postRepository) {
        this.postRepository = postRepository;
    }

    public Post getPost(Long id) {
        return postRepository.findById(id)
                .orElseThrow(() -> new PostNotFoundException(id));
    }
}
```

Notice something important.

The service doesn’t know how PostgreSQL works.

It simply says:

```java
postRepository.findById(id)
```

The infrastructure underneath handles the database interaction.

---

# **17. Derived query methods**

Spring Data can also derive queries from method names.

Suppose we want:

Find all posts written by a particular user.

We can write:

```java
List<Post> findByAuthorId(Long authorId);
```

Spring Data interprets the method name.

Conceptually:

```text
findByAuthorId
      ↓
WHERE author_id = ?
```

Another:

```java
List<Post> findByTitle(String title);
```

roughly corresponds to:

```sql
WHERE title = ?
```

This is one of Spring Data’s nicest features.

---

# **18. But don’t go crazy with method names**

You could theoretically write:

```java
findByAuthorIdAndTitleContainingIgnoreCaseAndProjectIdOrderByCreatedAtDesc(...)
```

And Spring Data can derive complex queries from method names.

But at some point:

**the method name becomes worse than writing an explicit query.**

We’ll later learn:

```java
@Query(...)
```

JPQL, specifications, projections, and eventually more advanced querying.

The rule is:

Use derived queries when they’re simple and readable. Use explicit queries when the query becomes complex.

---

# **19. The database schema vs Hibernate schema generation**

There’s another important concept.

During development, Spring Boot/Hibernate can potentially create or modify tables from your entities.

For example, configuration can tell Hibernate to create/update the schema.

This is convenient while learning.

But for a serious application, we generally don’t want:

```text
Application starts
      ↓
Hibernate changes production database schema
```

Instead, we’ll eventually use **database migrations**, such as Flyway.

That gives us controlled changes like:

```text
V1__create_users.sql
V2__create_posts.sql
V3__add_projects.sql
V4__add_permissions.sql
```

We’ll get to that later.

For now, focus on understanding the mapping.

---

# **20. One important trap: entity relationships**

Consider:

```java
@ManyToOne
private User author;
```

It is tempting to think:

“Every time I load a Post, Java immediately loads the entire User.”

That’s not necessarily true.

That’s why we have:

```java
fetch = FetchType.LAZY
```

With:

```java
@ManyToOne(fetch = FetchType.LAZY)
```

Hibernate can initially load the `Post` without immediately loading all the `User` data.

Conceptually:

```text
find Post
   ↓
Post loaded

User?
   ↓
not necessarily loaded yet
```

When you actually access:

```java
post.getAuthor()
```

Hibernate may need to fetch the user.

This leads to a very important problem called the **N+1 query problem**.

We’ll study it carefully later rather than trying to solve it prematurely.

---

# **21. Why JPA can be dangerous if you don’t understand SQL**

Imagine:

```java
List<Post> posts = postRepository.findAll();

for (Post post : posts) {
    System.out.println(post.getAuthor().getUsername());
}
```

You might think:

```text
1 query → posts
```

But depending on mapping/fetching and the persistence context, you could end up with something conceptually like:

```text
SELECT posts...

SELECT user for post 1
SELECT user for post 2
SELECT user for post 3
SELECT user for post 4
...
```

That’s the famous:

**N+1 problem**

We’ll eventually learn how to diagnose and solve it with joins, fetch joins, entity graphs, projections, and appropriate query design.

This is exactly why I don’t want you to blindly use JPA annotations without understanding SQL.

---

# **22. One more important concept: Entity lifecycle**

JPA entities aren’t just ordinary objects as far as the persistence context is concerned.

An entity can be:

```text
Transient
   ↓
Managed
   ↓
Detached
   ↓
Removed
```

For example:

```java
Post post = new Post();
```

At this point, it’s just a Java object.

After persistence:

```java
postRepository.save(post);
```

the entity becomes associated with the persistence context.

Hibernate can then track changes.

This leads to a powerful concept called **dirty checking**.

---

# **23. Dirty checking**

Suppose:

```java
Post post = postRepository.findById(1L)
        .orElseThrow();

post.setTitle("New title");
```

You might expect:

```java
postRepository.save(post);
```

to be required.

But within a transaction, a managed JPA entity can be automatically detected as changed.

Conceptually:

```text
Load entity
     ↓
Hibernate tracks it
     ↓
Modify entity
     ↓
Hibernate detects change
     ↓
UPDATE generated
```

For example:

```sql
UPDATE posts
SET title = 'New title'
WHERE id = 1;
```

That’s **dirty checking**.

It’s extremely useful—but it’s also one reason you need to understand transactions and entity state.

---

# **24. The mental model I want you to keep**

Don’t memorize annotations yet.

Understand this:

```text
                     Spring Boot
                         │
                         ▼
                    PostService
                         │
                         ▼
                  PostRepository
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
```

And:

```text
Java class
    ↕
   @Entity
    ↕
Database table
```

And:

```text
Java relationship
    ↕
JPA relationship annotation
    ↕
Foreign key
```

For example:

```text
Post.author
    ↕
@ManyToOne
    ↕
posts.author_id
    ↕
users.id
```

If that makes sense, you’re understanding JPA rather than merely memorizing it.

---