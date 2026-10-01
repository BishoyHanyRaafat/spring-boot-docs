---
title: Lesson 14: Querying with Spring Data JPA
sidebar_position: 14
---


Now we move from:

“How do I map Java objects to tables?”

to:

**“How do I efficiently retrieve exactly the data my application needs?”**

This is where Spring Data JPA becomes extremely powerful—and where blindly relying on it can get you into trouble.

Spring Data JPA currently supports several approaches: derived query methods, `@Query`, projections, pagination/sorting, specifications, native queries, and scrolling.  

---

# **1. The three levels of querying**

For ProjectHub, think of querying as three levels:

```text
Simple
  ↓
Derived query method

Moderate/complex
  ↓
@Query + JPQL

Database-specific / highly specialized
  ↓
Native SQL
```

We’ll learn them in that order.

---

# **2. Derived query methods**

We’ve already seen:

```java
List<Post> findByAuthorId(Long authorId);
```

Spring Data reads the method name and derives the query.

For example:

```java
List<Post> findByTitle(String title);
```

means approximately:

```sql
WHERE title = ?
```

And:

```java
List<Post> findByAuthorIdAndProjectId(
        Long authorId,
        Long projectId
);
```

means approximately:

```sql
WHERE author_id = ?
  AND project_id = ?
```

Spring Data supports a large collection of keywords for this, including `And`, `Or`, `Between`, `LessThan`, `GreaterThan`, `Containing`, `StartingWith`, `IsNull`, and more.  

---

# **3. More examples**

Suppose `Post` has:

```text
title
content
author
project
createdAt
```

We could write:

```java
List<Post> findByTitleContaining(String text);
```

Search for titles containing something.

Or:

```java
List<Post> findByTitleContainingIgnoreCase(String text);
```

Case-insensitive search.

Or:

```java
List<Post> findByCreatedAtAfter(Instant date);
```

Posts after a certain date.

Or:

```java
List<Post> findByProjectIdOrderByCreatedAtDesc(Long projectId);
```

Posts belonging to a project, newest first.

This is convenient because we haven’t written any SQL or JPQL.

---

# **4. But method names can become ridiculous**

Imagine:

```java
List<Post> findByProjectIdAndAuthorIdAndTitleContainingIgnoreCaseAndCreatedAtBetweenOrderByCreatedAtDesc(
    Long projectId,
    Long authorId,
    String title,
    Instant from,
    Instant to
);
```

Technically possible.

But ask yourself:

Is this readable?

Probably not.

Spring Data itself recommends declared queries when derived method names become unnecessarily ugly or can’t express what you need.  

That’s where `@Query` comes in.

---

# **5. JPQL**

Suppose we want:

Find posts belonging to a project and written by a particular user.

We can write:

```java
@Query("""
    SELECT p
    FROM Post p
    WHERE p.project.id = :projectId
      AND p.author.id = :authorId
""")
List<Post> findPosts(
        @Param("projectId") Long projectId,
        @Param("authorId") Long authorId
);
```

Notice something very important.

This is **not SQL**.

We wrote:

```text
FROM Post p
```

not:

```sql
FROM posts p
```

We wrote:

```text
p.author.id
```

not:

```sql
p.author_id
```

That’s because JPQL works with the **entity model**.

---

# **6. SQL vs JPQL**

### **SQL**

```sql
SELECT *
FROM posts
WHERE author_id = 10;
```

### **JPQL**

```java
SELECT p
FROM Post p
WHERE p.author.id = 10
```

SQL thinks in:

```text
tables
columns
rows
```

JPQL thinks in:

```text
entities
properties
relationships
```

That’s a major conceptual difference.

---

# **7. Why JPQL is useful**

Suppose our Java model says:

```java
Post.author
```

and our database says:

```text
posts.author_id
```

JPQL allows us to write:

```text
p.author.id
```

without directly caring about the physical foreign-key column.

Hibernate translates the JPQL into SQL appropriate for the database.

---

# **8. Named parameters**

Prefer:

```java
@Query("""
    SELECT p
    FROM Post p
    WHERE p.author.id = :authorId
""")
List<Post> findByAuthor(
        @Param("authorId") Long authorId
);
```

over:

```java
@Query("""
    SELECT p
    FROM Post p
    WHERE p.author.id = ?1
""")
List<Post> findByAuthor(Long authorId);
```

Both work, but named parameters are usually easier to read and maintain.

Spring Data JPA supports named parameter binding with `@Param`.  

---

# **9. JOINs in JPQL**

Remember our SQL:

```sql
SELECT p.id, p.title, u.username
FROM posts p
JOIN users u
    ON p.author_id = u.id;
```

In JPQL, we work with the relationship:

```java
SELECT p
FROM Post p
JOIN p.author a
```

Notice:

```text
p.author
```

That’s the Java relationship we defined earlier:

```java
@ManyToOne
private User author;
```

This is where understanding entity relationships pays off.

---
# **10. `JOIN FETCH`**

Now we get to something important.

Suppose:

```java
@Query("""
    SELECT p
    FROM Post p
    JOIN FETCH p.author
""")
List<Post> findAllWithAuthor();
```

`JOIN FETCH` means:

Retrieve the associated entity as part of this query and initialize it.

Conceptually:

```text
Post + Author
```

come back together.

This is one common tool for avoiding an N+1 query pattern.

---


# 11. Why normal `JOIN`and `JOIN FETCH`aren’t identical

Consider:

```java
SELECT p
FROM Post p
JOIN p.author a
```

The join can be used for filtering/query logic.

For example:

```java
SELECT p
FROM Post p
JOIN p.author a
WHERE a.username = :username
```

You’re saying:

Find posts whose author’s username matches.

But `JOIN FETCH` additionally tells the persistence provider to fetch the associated entity as part of the query result.

So:

```text
JOIN
```

and:

```text
JOIN FETCH
```

have different purposes.

---

# **12. Solving our N+1 problem**

Imagine:

```java
List<Post> posts = postRepository.findAll();

for (Post post : posts) {
    System.out.println(post.getAuthor().getUsername());
}
```

Potentially:

```text
SELECT posts...
SELECT user...
SELECT user...
SELECT user...
...
```

Instead:

```java
@Query("""
    SELECT p
    FROM Post p
    JOIN FETCH p.author
""")
List<Post> findAllWithAuthor();
```

Conceptually:

```text
SELECT posts
JOIN users
```

One appropriately designed query can retrieve the required data.

But there’s an important caveat:

**Don’t put** **`JOIN FETCH`** **everywhere.**

Fetch strategy should follow the use case.

---


# **13. `@EntityGraph`**

Another option is:

```java
@EntityGraph(attributePaths = "author")
List<Post> findAll();
```

This tells Spring Data which association should be fetched for that repository operation.

Spring Data JPA supports both named and ad-hoc entity graphs.  

So you have several tools:

```text
JOIN FETCH
@EntityGraph
projections
carefully designed queries
```

We’ll use each where appropriate.

---

# **14. Filtering through relationships**

Suppose:

Find all posts written by users with username `alice`.

Derived query:

```java
List<Post> findByAuthorUsername(String username);
```

That’s a nice example of Spring Data traversing nested properties.

Or JPQL:

```java
@Query("""
    SELECT p
    FROM Post p
    WHERE p.author.username = :username
""")
List<Post> findByAuthorUsername(
        @Param("username") String username
);
```

Notice how JPQL follows the object graph:

```text
Post
 ↓
author
 ↓
username
```

---

# **15. Projections**

Now imagine our API needs:

```json
{
  "id": 10,
  "title": "Spring Data JPA",
  "authorUsername": "alice"
}
```

Do we really need to load the entire:

```text
Post
User
Project
Comments
...
```

graph?

Not necessarily.

We can use a **projection**.

Spring Data JPA supports projections to retrieve more selective views of an entity’s data.  

For example:

```java
public interface PostSummary {

    Long getId();

    String getTitle();

    String getAuthorUsername();
}
```

Then:

```java
@Query("""
    SELECT
        p.id AS id,
        p.title AS title,
        p.author.username AS authorUsername
    FROM Post p
""")
List<PostSummary> findPostSummaries();
```

Now we’re asking for exactly the fields we need.

---

# **16. DTO projection**

We can also use a DTO/record.

For example:

```java
public record PostSummaryResponse(
        Long id,
        String title,
        String authorUsername
) {}
```

Then JPQL can construct that result:

```java
@Query("""
    SELECT new com.example.projecthub.PostSummaryResponse(
        p.id,
        p.title,
        p.author.username
    )
    FROM Post p
""")
List<PostSummaryResponse> findSummaries();
```

This is particularly useful for API read models.

---

# **17. Entity vs projection**

Think of it this way.

### **Entity query**

```text
Give me Post entities.
```

Useful when:

- you need to modify them
- business logic operates on them
- you need their entity relationships

### **Projection**

```text
Give me these specific pieces of data.
```

Useful for:

- list endpoints
- dashboards
- search results
- read-only views
- avoiding unnecessary entity loading

This becomes especially useful as our application grows.

---

# **18. Pagination**

This is essential for REST APIs.

Imagine:

```text
5 million posts
```

You don’t want:

```java
postRepository.findAll();
```

returning 5 million records.

Instead:

```text
page 0 → 20 posts
page 1 → 20 posts
page 2 → 20 posts
```

Spring Data supports pagination using `Pageable`, with repository methods returning `Page` or `Slice`.  

---

# 19.  `Pageable`

Our repository:

```java
Page<Post> findByProjectId(
        Long projectId,
        Pageable pageable
);
```

Then:

```java
Pageable pageable =
        PageRequest.of(
            0,
            20,
            Sort.by("createdAt").descending()
        );
```

And:

```java
Page<Post> page =
        postRepository.findByProjectId(
            projectId,
            pageable
        );
```

Now:

```text
page.getContent()
```

contains the current posts.

And `Page` also gives information such as:

```text
current page
page size
total elements
total pages
```

---


# 20. `Page` vs `Slice`

This distinction is useful.

### **`Page`**

Provides total-count information.

Conceptually:

```text
SELECT posts...
SELECT COUNT(...)
```

You get:

```text
total elements
total pages
```

### **`Slice`**

Focuses on:

Is there another chunk?

It doesn’t require the same total-count semantics.

For very large datasets, avoiding the total count can sometimes be useful.

Spring Data also provides scrolling approaches, including offset- and keyset-based scrolling for larger result sets.  

For our initial REST APIs, though, `Page` is perfectly fine.

---

# **21. Sorting**

You can do:

```java
PageRequest.of(
    0,
    20,
    Sort.by("createdAt").descending()
);
```

Or repository methods can encode ordering:

```java
List<Post> findByProjectIdOrderByCreatedAtDesc(
        Long projectId
);
```

Remember:

```text
Java property:
createdAt
```

is what Spring Data’s normal `Sort` operates against—not necessarily the raw database column name.  

---

# **22. Pagination + REST**

This connects directly to Lesson 7.

Request:

```http
GET /projects/5/posts?page=0&size=20
```

Controller:

```java
@GetMapping
public Page<PostResponse> getPosts(
        @PathVariable Long projectId,
        @PageableDefault(size = 20)
        Pageable pageable) {

    return postService.getPosts(projectId, pageable);
}
```

Service:

```java
@Transactional(readOnly = true)
public Page<PostResponse> getPosts(
        Long projectId,
        Pageable pageable) {

    return postRepository
            .findByProjectId(projectId, pageable)
            .map(this::toResponse);
}
```

This is the beginning of a realistic API.

---


# 23. A warning about exposing `Page`

**directly**

For learning, this is fine:

```java
Page<PostResponse>
```

But for a mature API, you may eventually want your own response format:

```java
public record PageResponse<T>(
        List<T> content,
        int page,
        int size,
        long totalElements,
        int totalPages
) {}
```

Why?

Because your API contract shouldn’t necessarily be dictated by Spring Data’s internal representation.

This is the same DTO principle we’ve been applying all along.

---

# **24. Native SQL**

Sometimes JPQL isn’t the right tool.

Spring Data JPA also supports native SQL queries. Current Spring Data JPA provides `@NativeQuery`, which is essentially a composed form of `@Query(nativeQuery = true)` with some additional support.  

For example:

```java
@NativeQuery("""
    SELECT *
    FROM posts
    WHERE author_id = :authorId
""")
List<Post> findPostsByAuthor(
        @Param("authorId") Long authorId
);
```

Now you’re writing actual PostgreSQL SQL.

Use this when you genuinely need database-specific SQL or a query that is awkward/impractical in JPQL.

Don’t use native SQL simply because JPQL looks unfamiliar.

---

# **25. A useful hierarchy**

When writing a query, ask:

### **Can a simple repository method express it?**

```java
findByAuthorId(...)
```

Use that.

### **Is it more complex?**

```java
@Query("""
    SELECT ...
""")
```

Use JPQL.

### **Need a specific database feature?**

```java
@NativeQuery("""
    SELECT ...
""")
```

Use native SQL.

This keeps the code understandable.

---

# **26. Querying our ProjectHub posts**

Let’s build a realistic repository.

```java
public interface PostRepository
        extends JpaRepository<Post, Long> {

    List<Post> findByAuthorId(Long authorId);

    Page<Post> findByProjectId(
            Long projectId,
            Pageable pageable
    );

    @Query("""
        SELECT p
        FROM Post p
        JOIN FETCH p.author
        WHERE p.project.id = :projectId
        ORDER BY p.createdAt DESC
    """)
    List<Post> findProjectPostsWithAuthor(
            @Param("projectId") Long projectId
    );

    @Query("""
        SELECT p
        FROM Post p
        WHERE p.author.username = :username
    """)
    List<Post> findByAuthorUsername(
            @Param("username") String username
    );
}
```

Notice how each technique has a purpose.

```text
findByAuthorId
    ↓
simple derived query

findByProjectId(Pageable)
    ↓
derived query + pagination

findProjectPostsWithAuthor
    ↓
custom JPQL + fetch join

findByAuthorUsername
    ↓
custom JPQL / could also be derived
```

---

# **27. Specifications**

There’s one more query mechanism you’ll encounter later:

```java
Specification<Post>
```

Imagine our search screen allows:

```text
project = 5
author = 10
title contains "spring"
created after = January
created before = March
```

You could potentially construct a giant method name.

Not ideal.

Specifications allow us to build dynamic criteria.

Spring Data JPA provides `Specification` support and fluent query operations including pagination, sorting, projections, `count`, `exists`, and scrolling.  

We’ll dedicate a later lesson to this rather than throwing it all at you now.

---

# **28. The most important lesson**

Don’t think:

“JPA means I don’t need to know SQL.”

Think:

```text
SQL
 ↓
understand database behavior

JPQL
 ↓
query through entity model

Spring Data
 ↓
reduce repository boilerplate
```

You should be comfortable moving between:

```text
Java
↕
JPQL
↕
SQL
```

For example:

### **Java relationship**

```java
p.author.username
```

### **JPQL**

```java
SELECT p
FROM Post p
WHERE p.author.username = :username
```

### **SQL conceptually**

```sql
SELECT ...
FROM posts p
JOIN users u
    ON p.author_id = u.id
WHERE u.username = ?;
```

That’s the skill we’re developing.

---

# **29. A query-design rule you’ll use constantly**

Before writing a query, ask:

**What data does this use case actually need?**

Suppose the endpoint is:

```http
GET /posts
```

and the UI needs:

```json
{
    "id": 1,
    "title": "Spring Boot",
    "authorUsername": "alice"
}
```

Don’t automatically load:

```text
Post
 ├── User
 │    ├── Posts
 │    └── Projects
 ├── Comments
 └── Project
      └── Members
```

You only need:

```text
Post
 ├── id
 ├── title
 └── author.username
```

That mindset leads naturally toward:

- projections
- DTO queries
- fetch joins
- deliberate pagination
- efficient SQL

rather than blindly loading entity graphs.

---
