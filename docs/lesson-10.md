---
title: Lesson 10: PostgreSQL & SQL Fundamentals
sidebar_position: 10
---

Now we move from **Spring itself** to the thing that will eventually store our ProjectHub data.

The goal of this lesson is **not** to learn JPA yet. I want you to understand SQL and relational databases first, because JPA becomes much easier once you understand what it’s hiding.

PostgreSQL’s current documentation is on version 18, and its official tutorial covers exactly the progression we’re following: tables → rows → queries → joins → updates/deletes → foreign keys → transactions.  

---

## **1. Why do we need a database?**

So far, our application could do something like:

```java
List<Post> posts = new ArrayList<>();
```

That’s fine while the application is running.

But what happens when:

- the application restarts?
- 10,000 users create posts?
- we have multiple application instances?
- we need to search posts?
- we need relationships between users and posts?
- we need transactions?

We need **persistent storage**.

A relational database stores data in **tables**.

Think of it like this:

```text
Spring Boot application
        │
        │ SQL
        ▼
   PostgreSQL
        │
        ├── users
        ├── posts
        ├── comments
        └── projects
```

Our Java objects live in memory.

PostgreSQL stores the durable data.

Later, **JPA/Hibernate** will sit between the two:

```text
Java Objects
     ↕
JPA / Hibernate
     ↕
   SQL
     ↕
PostgreSQL
```

---

# **2. Database → table → row → column**

Suppose we have a `users` table:

|**id**|**username**|**email**|
|---|---|---|
|1|alice|alice@example.com|
|2|bob|bob@example.com|
|3|charlie|charlie@example.com|

The terminology is important:

### **Database**

The overall PostgreSQL database.

For example:

```text
projecthub
```

### **Table**

A collection of a particular type of data:

```text
users
posts
comments
projects
```

### **Row**

One record.

```text
1 | alice | alice@example.com
```

### **Column**

One property of each record:

```text
id
username
email
```

---

# **3. Creating a table**

Here’s our first SQL.

```sql
CREATE TABLE users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE
);
```

Let’s understand every part.

### **`id`**

```sql
id BIGINT
```

The column contains integer values.

### **`GENERATED ALWAYS AS IDENTITY`**

PostgreSQL generates the ID for us.

So we can insert:

```sql
INSERT INTO users (username, email)
VALUES ('alice', 'alice@example.com');
```

and PostgreSQL generates the ID.

### **`PRIMARY KEY`**

This identifies a row uniquely.

So:

```text
id = 1
```

can identify exactly one user.

A primary key must be unique and non-null; PostgreSQL automatically creates an index to enforce the primary-key constraint.  

### **`NOT NULL`**

Means:

This value is required.

So this isn’t allowed:

```sql
INSERT INTO users (username)
VALUES ('alice');
```

because `email` is required.

### **`UNIQUE`**

Means duplicate values aren’t allowed.

So this would fail if the email already exists:

```sql
INSERT INTO users (username, email)
VALUES ('anotherAlice', 'alice@example.com');
```

These constraints aren’t merely documentation. PostgreSQL actually prevents invalid data from being inserted.  

---

# **4. CRUD in SQL**

You already learned CRUD conceptually in our REST lesson.

SQL has the same four fundamental operations.

## **Create**

```sql
INSERT INTO users (username, email)
VALUES ('alice', 'alice@example.com');
```

Another:

```sql
INSERT INTO users (username, email)
VALUES ('bob', 'bob@example.com');
```

---

## **Read**

Get everything:

```sql
SELECT *
FROM users;
```

Get specific columns:

```sql
SELECT id, username
FROM users;
```

Filter:

```sql
SELECT id, username, email
FROM users
WHERE username = 'alice';
```

---

## **Update**

```sql
UPDATE users
SET email = 'alice@newdomain.com'
WHERE id = 1;
```

**Important:** notice the `WHERE`.

This:

```sql
UPDATE users
SET email = 'alice@newdomain.com';
```

means:

Change the email for EVERY user.

That’s a potentially nasty mistake.

---

## **Delete**

```sql
DELETE FROM users
WHERE id = 1;
```

Again, `WHERE` matters.

Without it:

```sql
DELETE FROM users;
```

means:

Delete every user.

---

# **5. Relationships**

This is where relational databases become really useful.

Our ProjectHub application needs something like:

```text
User
 │
 ├── creates ──> Posts
 │
 └── joins ────> Projects
                    │
                    └── contains Posts

Post
 │
 └── has ────────> Comments
```

Let’s start with users and posts.

---

# **6. One-to-many relationship**

One user can create many posts.

```text
User
  1
  │
  ├──── Post
  ├──── Post
  └──── Post
```

We represent this by putting the user’s ID into the `posts` table.

```sql
CREATE TABLE posts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    title VARCHAR(100) NOT NULL,

    content TEXT NOT NULL,

    author_id BIGINT NOT NULL,

    FOREIGN KEY (author_id)
        REFERENCES users(id)
);
```

Now imagine:

### **users**

|**id**|**username**|
|---|---|
|1|alice|
|2|bob|

### **posts**

|**id**|**title**|**author_id**|
|---|---|---|
|1|Spring Boot|1|
|2|PostgreSQL|1|
|3|Java Tips|2|

`author_id = 1` means:

This post belongs to Alice.

That’s a **foreign key**.

A foreign key requires the referenced value to exist in the referenced table, maintaining referential integrity.  

Therefore this should fail:

```sql
INSERT INTO posts (title, content, author_id)
VALUES ('Hello', 'My post', 999);
```

if user `999` doesn’t exist.

That’s the database protecting our data.

---

# **7. Why not just store the username?**

You might wonder:

Why not:

```sql
author_username VARCHAR(50)
```

instead of:

```sql
author_id BIGINT
```

Suppose Alice changes her username.

If 5,000 posts contain:

```text
alice
```

you now have to update 5,000 records.

With a foreign key:

```text
users
-----
id = 1
username = alice
```

and:

```text
posts
-----
author_id = 1
```

the relationship remains intact even if Alice changes her username.

This is one of the fundamental ideas behind relational modeling.

---

# **8. JOINs**

Now suppose we want:

Give me every post along with the author’s username.

The data is split across two tables, so we use a `JOIN`.

```sql
SELECT
    posts.id,
    posts.title,
    users.username
FROM posts
JOIN users
    ON posts.author_id = users.id;
```

Result:

|**id**|**title**|**username**|
|---|---|---|
|1|Spring Boot|alice|
|2|PostgreSQL|alice|
|3|Java Tips|bob|

This is extremely important.

You’ll eventually write something in Java like:

```java
postRepository.findSomething(...)
```

and Hibernate may generate SQL involving joins underneath.

So understanding this now will save you a lot of confusion later.

---

# **9. Many-to-many relationships**

Now consider:

A user can belong to many projects.

And:

A project can have many users.

That’s:

```text
User ─────── Project
  N             N
```

You don’t normally put:

```text
project_id
```

directly into `users`, because one user can belong to multiple projects.

Instead we create a **join table**.

```text
users
projects
project_members
```

For example:

```sql
CREATE TABLE projects (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);
```

Then:

```sql
CREATE TABLE project_members (
    project_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,

    PRIMARY KEY (project_id, user_id),

    FOREIGN KEY (project_id)
        REFERENCES projects(id),

    FOREIGN KEY (user_id)
        REFERENCES users(id)
);
```

Now:

|**project_id**|**user_id**|
|---|---|
|1|1|
|1|2|
|2|1|

means:

```text
Project 1
 ├── Alice
 └── Bob

Project 2
 └── Alice
```

The combination:

```text
(project_id, user_id)
```

is the primary key.

This is called a **composite primary key**.

---

# **10. Constraints are your database’s safety net**

You should become very comfortable with these:

|**Constraint**|**Meaning**|
|---|---|
|`PRIMARY KEY`|uniquely identifies a row|
|`FOREIGN KEY`|references another table|
|`NOT NULL`|value required|
|`UNIQUE`|duplicates forbidden|
|`CHECK`|value must satisfy a condition|

For example:

```sql
CREATE TABLE products (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    name VARCHAR(100) NOT NULL,

    price NUMERIC(10, 2) NOT NULL,

    CHECK (price >= 0)
);
```

Now the database itself prevents:

```text
price = -50
```

Constraints are an important part of database design, rather than something we should leave entirely to application code.  

---

# **11. Indexes**

Now imagine we have:

```text
10 rows
```

Searching all rows isn’t a big deal.

But imagine:

```text
10 million posts
```

and we frequently run:

```sql
SELECT *
FROM posts
WHERE author_id = 42;
```

An **index** can make searches like this much more efficient.

For example:

```sql
CREATE INDEX idx_posts_author_id
ON posts(author_id);
```

Conceptually:

```text
Without index:

posts
 ↓
scan lots of rows
 ↓
find author_id = 42
```

With index:

```text
index
 ↓
find rows associated with 42
 ↓
retrieve rows
```

But don’t think:

“Indexes make everything faster.”

They have costs too:

- consume storage
- must be maintained when data changes
- can slow writes
- aren’t useful for every query

Also, PostgreSQL automatically creates indexes for primary-key and unique constraints, so you don’t need to manually create those indexes.  

And importantly, PostgreSQL does **not** automatically create an index for every foreign-key column, so indexing frequently queried foreign keys can sometimes be appropriate.  

We’ll study query planning and indexes much more deeply later.

---

# **12. Transactions**

This is one of the most important database concepts you’ll learn.

Imagine transferring money:

```text
Alice:  $100
Bob:    $50
```

We want:

```text
Alice:  $70
Bob:    $80
```

That’s actually two operations:

```sql
UPDATE accounts
SET balance = balance - 30
WHERE id = 1;

UPDATE accounts
SET balance = balance + 30
WHERE id = 2;
```

But what if the first succeeds and the second fails?

We’d have:

```text
Alice: $70
Bob:   $50
```

$30 effectively disappeared.

A transaction allows us to treat the operations as one unit:

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 30
WHERE id = 1;

UPDATE accounts
SET balance = balance + 30
WHERE id = 2;

COMMIT;
```

If something goes wrong, we can roll back instead:

```sql
ROLLBACK;
```

The fundamental idea is:

```text
BEGIN
  operation 1
  operation 2
  operation 3
COMMIT
```

or:

```text
BEGIN
  operation 1
  operation 2
  ERROR
ROLLBACK
```

Later, when we learn Spring’s:

```java
@Transactional
```

you’ll understand exactly what problem it’s solving.

---

# **13. Our ProjectHub database**

Let’s put everything together.

At this stage, our conceptual model is:

```text
                    ┌──────────────┐
                    │    users     │
                    ├──────────────┤
                    │ id           │
                    │ username     │
                    │ email        │
                    └──────┬───────┘
                           │
                           │ 1:N
                           ▼
                    ┌──────────────┐
                    │    posts     │
                    ├──────────────┤
                    │ id           │
                    │ title        │
                    │ content      │
                    │ author_id    │
                    └──────┬───────┘
                           │
                           │ 1:N
                           ▼
                    ┌──────────────┐
                    │   comments   │
                    ├──────────────┤
                    │ id           │
                    │ content      │
                    │ author_id    │
                    │ post_id      │
                    └──────────────┘


       ┌──────────────┐
       │    users     │
       └──────┬───────┘
              │
              │ N:M
              │
       ┌──────▼───────────┐
       │ project_members  │
       └──────┬───────────┘
              │
              │ N:M
              │
       ┌──────▼───────┐
       │   projects   │
       └──────────────┘
```

This is the foundation for the application we’ll build.

---

# **14. One important design principle**

There’s a temptation when learning Spring to think:

“Spring Data JPA will handle all of this, so I don’t need SQL.”

Don’t fall into that trap.

You should understand:

```text
HTTP
 ↓
Controller
 ↓
Service
 ↓
Repository
 ↓
JPA/Hibernate
 ↓
SQL
 ↓
PostgreSQL
```

Because when something eventually goes wrong:

```text
Why is this query slow?

Why am I getting duplicate rows?

Why did this relationship load 500 times?

Why did deleting this entity fail?

Why did this transaction roll back?

Why did Hibernate generate this JOIN?
```

you need to understand the bottom half of the stack.

---

# **Exercise — Design ProjectHub’s database**

Don’t use JPA yet.

Write **SQL only**.

Create these five tables:

```text
users
projects
project_members
posts
comments
```

### **Requirements**

#### **`users`**

- `id`
- `username`
- `email`
- username required
- email required
- email unique

#### **`projects`**

- `id`
- `name`
- name required

#### **`project_members`**

- `project_id`
- `user_id`
- both foreign keys
- prevent the same user from joining the same project twice

#### **`posts`**

- `id`
- `title`
- `content`
- `author_id`
- `project_id`
- title required
- content required
- author must reference a user
- project must reference a project

#### **`comments`**

- `id`
- `content`
- `author_id`
- `post_id`
- content required
- author references a user
- post references a post

Then write these queries:

### **Query 1**

Find all posts written by user `1`.

### **Query 2**

Find all posts together with the author’s username.

### **Query 3**

Find all users belonging to project `1`.

### **Query 4**

Find all comments belonging to post `5`, including the comment author’s username.

---

### **One thing I want you to notice**

We haven’t written **one line of JPA** yet.

That’s intentional.

Once you can model this correctly in SQL, our next lesson becomes much more intuitive:

**Lesson 11 — JPA, Hibernate & Spring Data JPA**

We’ll take this:

```sql
posts.author_id
```

and learn how it becomes something like:

```java
@ManyToOne
private User author;
```

and then connect that to:

```java
JpaRepository<Post, Long>
```

That’s where Spring Boot starts talking to PostgreSQL through Java objects.