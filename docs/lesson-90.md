---
title: "Lesson 90: Backend Performance"
sidebar_position: 90
---

Performance is **not** “make everything faster.”

It is:

**Find the actual bottleneck, measure it, then improve that bottleneck.**

For ProjectHub, the usual chain is:

```text
HTTP request
    ↓
Controller
    ↓
Service
    ↓
Database ──────┐
    ↓          │
Kafka/RabbitMQ │
    ↓          │
External APIs ─┘
```

If the database takes 900 ms, making your Java method 20% faster doesn’t matter.

---

## **1. Start with measurement**

Before optimizing, measure:

```text
request latency
database query time
database connection usage
CPU
memory
Kafka lag
RabbitMQ queue depth
external API latency
```

Spring Boot exposes datasource pool metrics, including active, idle, maximum, and minimum connections; Hikari-specific metrics are also available.  

So instead of guessing:

“Maybe we need Redis.”

you first ask:

“Where is the time actually going?”

---

# **2. Database performance is usually critical**

Consider:

```sql
SELECT *
FROM posts
WHERE project_id = ?
ORDER BY created_at DESC;
```

If ProjectHub has:

```text
100 posts
```

almost anything works.

If it has:

```text
100,000,000 posts
```

the database needs help.

That’s where **indexes** matter.

For this query, you might investigate an index such as:

```sql
CREATE INDEX idx_posts_project_created
ON posts(project_id, created_at DESC);
```

The exact index should be based on real query patterns and PostgreSQL’s execution plan—not added automatically to every column.

---

# **3. N+1 queries**

This is one of the most important JPA performance problems.

Suppose:

```java
List<Post> posts = postRepository.findAll();
```

Then you access:

```java
post.getAuthor().getName();
```

for 100 posts.

You might accidentally produce:

```text
1 query → load posts

100 queries → load authors
---------------------------
101 queries
```

That’s the classic **N+1 problem**.

The application may look perfectly fine with 10 records and become painfully slow with 10,000.

Possible solutions include:

```text
fetch joins
@EntityGraph
projections
explicit queries
batch fetching
```

The right solution depends on what data the endpoint actually needs.

---

# **4. Don’t load entities when you only need a DTO**

Suppose your endpoint returns:

```json
{
  "id": 42,
  "title": "Spring Security",
  "authorName": "Alice"
}
```

You don’t necessarily need an enormous `Post` entity graph.

A projection/query can retrieve exactly what you need.

Spring Data JPA supports projections and explicit repository queries, including `@Query` and native queries.  

Think:

```text
Bad mental model:

Database
   ↓
Load everything
   ↓
Java filters it
   ↓
Return tiny DTO
```

Prefer:

```text
Database
   ↓
Query only required data
   ↓
Return required data
```

---

# **5. Pagination**

Never casually build:

```java
List<Post> findAll();
```

for an endpoint that could eventually contain millions of rows.

Instead:

```text
GET /posts?page=0&size=20
```

or use an appropriate scrolling/keyset strategy for large datasets.

Spring Data JPA supports paging and newer scrolling approaches; its documentation specifically describes keyset scrolling as a way to avoid shortcomings of offset-based retrieval and leverage indexes.  

---

## **Offset pagination**

```text
page 0 → rows 1–20
page 1 → rows 21–40
page 10000 → much farther into the dataset
```

At large offsets, the database may still need to walk through many preceding rows.

---

## **Keyset pagination**

Instead of:

```text
page=10000
```

you can conceptually say:

```text
give me the next 20 posts
after this post ID/timestamp
```

For example:

```text
GET /posts?after=98231&limit=20
```

This can work extremely well with the right index.

---

# 

# 

# 

# **6.**

**`Page`**

**vs**

**`Slice`**

This is a subtle Spring Data detail.

A `Page<T>` contains information such as:

```text
content
total elements
total pages
current page
```

Obtaining the total can require a count query.

A `Slice<T>` is lighter when you only need:

```text
content
is there another slice?
```

The Spring Data documentation explicitly notes this distinction.  

So if your UI only needs:

```text
[posts...]

Load more
```

you may not need an expensive total count.

---

# **7. Database connection pools**

Your application doesn’t normally open a brand-new database connection for every request.

It uses a connection pool:

```text
                ┌─ connection
                ├─ connection
Application ────┼─ connection
                ├─ connection
                └─ connection
                       ↓
                  PostgreSQL
```

Spring Boot prefers HikariCP when available, and the JPA/JDBC starters bring it in automatically.  

But bigger isn’t automatically better.

Suppose:

```text
10 pods
×
50 DB connections
=
500 connections
```

Your PostgreSQL server may not appreciate that.

This is why scaling application pods and database connections must be considered together.

---

# **8. Caching**

Imagine:

```text
GET /projects/123
```

gets requested 10,000 times per minute, while the project changes once.

Doing:

```text
10,000 database queries
```

may be unnecessary.

A cache can turn the flow into:

```text
Request
   ↓
Redis/cache
   ↓
hit → return
```

instead of:

```text
Request
   ↓
PostgreSQL
   ↓
return
```

But caching introduces difficult questions:

```text
When does cached data expire?
Who invalidates it?
What happens after an update?
What happens if Redis is unavailable?
Can stale data be tolerated?
```

So:

**Don’t add Redis merely because Redis is popular.**

Add caching when measurement shows that repeated reads justify the complexity.

---

# **9. The biggest performance trap: optimizing the wrong thing**

Imagine:

```text
Controller:       2 ms
Service:          1 ms
JSON serialization: 3 ms
Database query: 850 ms
```

You optimize JSON serialization from:

```text
3 ms → 1 ms
```

Congratulations.

Your request went from:

```text
856 ms → 854 ms
```

😂

The database was the bottleneck.

---

# **10. A practical performance hierarchy**

When debugging a slow endpoint, think in this order:

```text
1. Is the query correct?
        ↓
2. Is the database using the right index?
        ↓
3. Are we doing N+1 queries?
        ↓
4. Are we retrieving too much data?
        ↓
5. Are we paginating?
        ↓
6. Are connection pools saturated?
        ↓
7. Is an external service slow?
        ↓
8. Is caching appropriate?
        ↓
9. Only then optimize Java code
```

This is a much healthier approach than premature micro-optimization.

---

# **11. ProjectHub example**

Suppose:

```text
GET /projects/42/posts
```

is slow.

We investigate and discover:

```text
HTTP                    1.2 sec
  └── service           1.19 sec
       └── database     1.15 sec
            ├── posts      50 ms
            ├── authors   900 ms   ← N+1
            └── count     200 ms
```

Now we have concrete problems:

```text
N+1 author queries
        ↓
projection/fetch strategy

expensive count
        ↓
consider Slice/keyset pagination

missing/poor index
        ↓
inspect EXPLAIN ANALYZE
```

That’s real performance engineering.

---

# **12. The mental model to remember**

```text
                    PERFORMANCE
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
       Database        Network         JVM
          │              │              │
       indexes        APIs          CPU/memory
       N+1            Kafka         allocations
       pagination     RabbitMQ      threads
       connection     Redis         GC
       pool
```

And the golden rule:

**Measure → identify bottleneck → change one thing → measure again.**

---

## **ProjectHub performance checklist**

Before calling the system “production ready”:

```text
□ Database indexes reviewed
□ Slow queries measured
□ N+1 queries checked
□ Pagination implemented
□ Large result sets controlled
□ Connection pool sized
□ Kafka/RabbitMQ consumers monitored
□ External API timeouts configured
□ Caching added only where justified
□ Load testing performed
□ Metrics and alerts available
```

That gives us the foundation for the next step.

# **Lesson 91 — CI/CD**

We’ll connect everything we’ve built:

```text
Git push
   ↓
Build
   ↓
Tests
   ↓
Docker image
   ↓
Security checks
   ↓
Container registry
   ↓
Kubernetes deployment
   ↓
Health checks
   ↓
Rolling update
```

That is where ProjectHub starts looking like a **real production system**, rather than just a Spring Boot application.