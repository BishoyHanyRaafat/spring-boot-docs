---
title: Lesson 58: Performance Engineering
sidebar_position: 58
---

Now we’re moving from:

**“Is ProjectHub reliable?”**

to:

**“How fast and how efficiently does ProjectHub operate?”**

This is where backend engineering becomes much more analytical.

A slow API doesn’t automatically mean:

```text
"Spring Boot is slow."
```

It could be:

```text
HTTP
 ↓
Spring Security
 ↓
Service
 ↓
JPA
 ↓
connection pool
 ↓
PostgreSQL
```

or:

```text
Redis
 ↓
cache miss
 ↓
PostgreSQL
```

or even:

```text
JVM
 ↓
GC pressure
 ↓
CPU
```

So our first principle is:

**Don’t optimize what you haven’t measured.**

---

# **1. Performance has multiple dimensions**

When we say “performance”, we usually mean several things:

```text
                 Performance
                     |
        +------------+------------+
        |            |            |
      Latency     Throughput    Resource use
        |            |            |
      ms/sec       req/sec       CPU/RAM/DB
```

### **Latency**

How long does one request take?

```text
GET /posts → 120 ms
```

### **Throughput**

How much work can the system perform?

```text
5,000 requests/sec
```

### **Resource efficiency**

How much infrastructure does that require?

```text
40% CPU
2 GB RAM
500 DB connections
```

A system can have good latency but poor resource efficiency, or high throughput but unacceptable latency.

---

# **2. Start with the request path**

Take:

```http
GET /projects/42/posts
```

ProjectHub might do:

```text
Client
  ↓
Gateway
  ↓
ProjectHub Pod
  ↓
Security
  ↓
Controller
  ↓
Service
  ↓
Redis?
  ↓
JPA
  ↓
PostgreSQL
  ↓
JSON serialization
  ↓
Response
```

If the request takes 800 ms, we need to discover **where those 800 ms went**.

That’s why traces from the previous lesson are so valuable.

---

# **3. Example trace**

Imagine:

```text
GET /projects/42/posts     800 ms
│
├── authentication           5 ms
├── authorization            8 ms
├── service                  2 ms
├── Redis                    3 ms
├── PostgreSQL             760 ms  ← 🚨
└── serialization           12 ms
```

Don’t optimize:

```text
authentication
```

because it isn’t the bottleneck.

Don’t optimize:

```text
JSON serialization
```

either.

The evidence points toward PostgreSQL.

---

# **4. The performance investigation loop**

Use this process:

```text
Measure
   ↓
Find bottleneck
   ↓
Form hypothesis
   ↓
Change one thing
   ↓
Measure again
   ↓
Keep or revert
```

Not:

```text
"Let's add Redis."
"Let's add threads."
"Let's increase CPU."
"Let's add indexes."
```

all at once.

Then you won’t know what actually helped.

---

# **5. Database performance**

One of the most common backend bottlenecks is the database.

Suppose:

```sql
SELECT *
FROM posts
WHERE project_id = 42;
```

If PostgreSQL scans a huge table every time:

```text
posts
 ↓
scan millions of rows
 ↓
find project_id = 42
```

that’s expensive.

An index can change the access path.

---

# **6. Indexes**

For:

```sql
WHERE project_id = ?
```

we might consider:

```sql
CREATE INDEX idx_posts_project_id
ON posts(project_id);
```

Then PostgreSQL has an indexed access path.

But:

**An index is not automatically good.**

Indexes consume storage and add work to writes.

Every insert/update affecting the indexed columns may need index maintenance.

So the question isn’t:

“Can I add an index?”

It’s:

“Does the workload justify this index?”

---

# **7. EXPLAIN**

PostgreSQL provides:

```sql
EXPLAIN
```

to inspect the query plan, and:

```sql
EXPLAIN ANALYZE
```

to execute the query and show actual execution information. PostgreSQL’s current documentation describes the plan as a tree of nodes such as sequential scans, index scans, joins, sorts, and aggregates.  

For example:

```sql
EXPLAIN ANALYZE
SELECT *
FROM posts
WHERE project_id = 42;
```

You might discover:

```text
Seq Scan
```

when you expected:

```text
Index Scan
```

That’s evidence worth investigating.

---

# **8. Don’t blindly chase index scans**

Important nuance:

A sequential scan isn’t inherently bad.

Suppose the table has only:

```text
100 rows
```

and you’re selecting:

```text
90 rows
```

A sequential scan may be perfectly reasonable.

The database optimizer chooses plans based on estimated costs and statistics.

So don’t learn:

“Seq Scan = bad.”

Learn:

**“Understand why PostgreSQL selected this plan and whether it meets the workload’s performance requirements.”**

---

# **9. N+1 queries**

This is especially important with JPA.

Imagine:

```java
List<Post> posts = postRepository.findByProjectId(projectId);
```

returns:

```text
100 posts
```

Then your mapping accesses:

```text
post.getAuthor().getUsername()
```

If author is lazy-loaded, you might accidentally create:

```text
1 query → posts

+ 100 queries → authors
```

Total:

```text
101 queries
```

That’s the classic **N+1 problem**.

---

# **10. The SQL shape matters**

What you intended:

```text
1 request
 ↓
1 query
```

What actually happens:

```text
1 request
 ↓
101 queries
```

Even if each query takes only:

```text
5 ms
```

that’s potentially:

```text
101 × 5ms = 505ms
```

before considering other work.

This is why database query count can matter just as much as individual query speed.

---

# **11. Fixing N+1**

Possible approaches include:

```text
JOIN FETCH
@EntityGraph
DTO projections
batch fetching
explicit queries
```

The correct choice depends on the use case.

For example:

```java
@Query("""
    select p
    from Post p
    join fetch p.author
    where p.project.id = :projectId
""")
List<Post> findPostsWithAuthors(Long projectId);
```

Now the database can retrieve the required relationship in a deliberate query.

But again:

Don’t turn every relationship into a giant fetch join.

That can create other problems.

---

# **12. Over-fetching**

Suppose your response only needs:

```json
{
  "id": 42,
  "title": "Hello",
  "authorName": "Alice"
}
```

But your query loads:

```text
Post
Author
Project
Project members
Comments
other relationships...
```

That’s unnecessary work.

This is **over-fetching**.

---

# **13. Projections**

A DTO projection can request only what the API needs.

Conceptually:

```text
Database
    |
    +-- id
    +-- title
    +-- author_name
```

instead of:

```text
entire entity graph
```

This can reduce:

```text
database work
memory usage
network transfer
JPA processing
serialization
```

Especially for read-heavy endpoints.

---

# **14. Pagination**

Never casually do:

```http
GET /posts
```

and return:

```text
5 million posts
```

Instead:

```http
GET /posts?page=0&size=50
```

or cursor-based pagination.

---

# **15. Offset pagination**

Traditional pagination:

```sql
SELECT *
FROM posts
ORDER BY id
LIMIT 50
OFFSET 100000;
```

At very large offsets, the database may need to process/skip many rows before returning the requested page.

That can become increasingly expensive.

---

# **16. Keyset pagination**

Instead, remember the last item:

```sql
SELECT *
FROM posts
WHERE id > 100000
ORDER BY id
LIMIT 50;
```

Conceptually:

```text
page 1
id 1 → 50

page 2
id > 50

page 3
id > 100
```

This is often called **keyset** or **cursor pagination**.

It becomes particularly attractive for large datasets.

---

# **17. Connection pools**

Now consider:

```text
ProjectHub
    |
    v
PostgreSQL
```

The application doesn’t usually open a brand-new physical database connection for every request.

It uses a connection pool.

Conceptually:

```text
       Connection Pool
      /      |      \
    DB1     DB2     DB3
      \      |      /
       PostgreSQL
```

A request borrows a connection:

```text
request
  ↓
borrow connection
  ↓
execute SQL
  ↓
return connection
```

---

# **18. Too few connections**

Suppose:

```text
100 concurrent requests
```

but:

```text
pool size = 5
```

Then many requests wait.

You might see:

```text
request
   ↓
waiting for DB connection
   ↓
waiting
   ↓
waiting
```

Latency increases.

---

# **19. Too many connections**

The opposite is also dangerous.

Suppose:

```text
20 Kubernetes Pods
```

and each has:

```text
maximumPoolSize = 50
```

Potential maximum:

```text
20 × 50 = 1,000 DB connections
```

Your PostgreSQL instance might not be able to handle that effectively.

So:

**Scaling application Pods can increase database pressure.**

We learned this with Kubernetes HPA, and now we’re seeing the performance mechanics behind it.

---

# **20. Connection pool sizing is a system problem**

Don’t think:

```text
"50 connections sounds good."
```

Think:

```text
How many Pods?
        ×
connections per Pod
        =
potential DB connections
```

Then compare that with:

```text
PostgreSQL capacity
```

and workload characteristics.

There isn’t one universal “correct” pool size.

---

# **21. Transactions and performance**

Long transactions are dangerous.

Imagine:

```text
@Transactional
public void createProject() {

    updateDatabase();

    callExternalApi();  // 5 seconds

    updateAnotherTable();
}
```

You may be holding database resources while waiting on an external system.

That is often a poor design.

Better architecture usually separates:

```text
database transaction
```

from:

```text
slow external work
```

using asynchronous processing where appropriate.

---

# **22. Don’t hold DB transactions across slow network calls**

Bad conceptual flow:

```text
BEGIN
 ↓
UPDATE DB
 ↓
call external API
 ↓
wait 4 seconds
 ↓
COMMIT
```

Better:

```text
BEGIN
 ↓
update DB
 ↓
write outbox
 ↓
COMMIT
 ↓
async worker
 ↓
external API
```

This connects our earlier lessons:

```text
transactions
+
outbox
+
messaging
```

can improve both reliability and resource efficiency.

---

# **23. JVM performance**

ProjectHub is a Java application.

So we also need to understand:

```text
Heap
Garbage collection
Threads
CPU
JIT
allocation
```

Modern JVMs already do a lot of optimization automatically. Oracle’s current Java 21 GC tuning guide recommends starting with JVM defaults before applying detailed tuning. On server-class machines, G1 is the default collector.  

This is important:

**Don’t start performance tuning by changing random JVM flags.**

Measure first.

---

# **24. Garbage collection**

Java applications allocate objects constantly:

```java
PostResponse response = new PostResponse(...);
```

Those objects eventually become unreachable.

The garbage collector reclaims memory.

Conceptually:

```text
Heap
 |
 +-- live objects
 |
 +-- garbage
```

GC:

```text
garbage
   ↓
collector
   ↓
reclaimed memory
```

---

# **25. GC can affect latency**

Suppose ProjectHub suddenly creates huge numbers of temporary objects.

```text
requests
   ↓
lots of allocations
   ↓
heap pressure
   ↓
more GC
   ↓
CPU usage
   ↓
latency
```

Your API might become slower even though your database is perfectly healthy.

That’s why JVM metrics matter.

Spring Boot Actuator automatically exposes JVM-related metrics, including memory, buffer pools, garbage collection, threads and JIT compilation.  

---

# **26. Memory leak vs high allocation**

These are different.

### **High allocation**

Your application creates lots of short-lived objects:

```text
allocate
allocate
allocate
GC
allocate
allocate
GC
```

### **Memory leak**

Objects remain reachable when they shouldn’t:

```text
application
 ↓
collection
 ↓
objects retained forever
 ↓
heap grows
```

Eventually:

```text
OutOfMemoryError
```

So don’t automatically blame GC.

Investigate:

```text
heap usage
allocation rate
GC frequency
GC pause time
object retention
```

---

# **27. CPU**

Suppose:

```text
CPU = 95%
```

Possible causes include:

```text
high traffic
expensive algorithms
serialization
compression
GC
cryptography
busy loops
too many threads
```

CPU itself isn’t the diagnosis.

It’s a symptom.

---

# **28. Thread pools**

A backend server processes many requests concurrently.

But resources are finite.

Suppose:

```text
1,000 requests
```

and:

```text
100 worker threads
```

Some requests wait.

If each request spends most of its time waiting on I/O, concurrency behavior becomes especially important.

But blindly increasing threads isn’t automatically good.

More threads can mean:

```text
context switching
memory overhead
contention
database pressure
```

---

# **29. Virtual threads**

Since we’re using modern Java, virtual threads are worth understanding.

Traditional platform threads are relatively heavyweight.

Virtual threads are lightweight threads designed for high-concurrency workloads, particularly where tasks spend substantial time waiting on I/O.

But:

Virtual threads don’t make PostgreSQL infinitely fast.

If you change:

```text
100 platform threads
```

to:

```text
10,000 virtual threads
```

and every request waits for PostgreSQL, you’ve potentially increased the number of simultaneous database operations dramatically.

So:

```text
more concurrency
≠
more capacity
```

This is one of the most important performance lessons.

---

# **30. The database bottleneck example**

Imagine:

```text
100 requests/sec
```

and PostgreSQL can comfortably handle:

```text
100 requests/sec
```

You increase ProjectHub from:

```text
3 Pods
```

to:

```text
20 Pods
```

Now you might generate:

```text
500 requests/sec
```

toward PostgreSQL.

Result:

```text
HPA scales
 ↓
more application Pods
 ↓
more DB connections
 ↓
DB saturates
 ↓
queries slow
 ↓
API latency increases
 ↓
HPA may scale again
```

You can accidentally create a feedback loop.

---

# **31. Caching**

Caching can dramatically reduce expensive repeated work.

Example:

```text
GET /projects/42
```

Without cache:

```text
API
 ↓
PostgreSQL
 ↓
result
```

With cache:

```text
API
 ↓
Redis
 ↓
result
```

The database may receive far fewer reads.

---

# **32. Cache hit vs miss**

```text
GET project 42
      |
      v
    Redis
    /   \
 hit     miss
 |        |
 v        v
return   PostgreSQL
          |
          v
        Redis
          |
          v
        return
```

This is called **cache-aside** or lazy caching.

It’s a very common pattern.

---

# **33. Cache invalidation**

Caching introduces a difficult question:

What happens when the underlying data changes?

Suppose:

```text
Post title = "Hello"
```

Redis contains:

```text
"Hello"
```

Then PostgreSQL changes:

```text
"Hello World"
```

but Redis still has:

```text
"Hello"
```

Now we have stale data.

---

# **34. Cache invalidation strategies**

Common approaches:

### **TTL**

```text
cache entry
 ↓
expires after 5 minutes
```

Simple, but stale data may exist until expiry.

### **Explicit invalidation**

When data changes:

```text
UPDATE DB
   ↓
DELETE Redis key
```

### **Write-through / other cache strategies**

Writes interact with cache and source of truth in a coordinated way.

Each has tradeoffs.

---

# **35. Cache what?**

Good cache candidates often include:

```text
frequently-read data
relatively expensive queries
data that tolerates some staleness
```

Potential ProjectHub examples:

```text
project summaries
public project metadata
permission metadata that isn't security-critical
```

Be careful caching:

```text
highly dynamic data
security-sensitive authorization decisions
user-specific data
```

unless the invalidation model is extremely clear.

---

# **36. Don’t use cache as the source of truth accidentally**

For ProjectHub:

```text
PostgreSQL
   ↓
source of truth
```

Redis:

```text
performance layer
```

If Redis disappears:

```text
Redis ❌
```

we should ideally still have:

```text
PostgreSQL ✅
```

for data that requires durability.

---

# **37. Serialization cost**

Performance isn’t only DB and CPU.

Suppose your endpoint returns:

```json
{
  "id": 42,
  "title": "...",
  "content": "...",
  "comments": [...],
  "members": [...],
  "project": {...}
}
```

Maybe the response is:

```text
4 MB
```

for one request.

That creates:

```text
DB work
+
JPA mapping
+
object allocation
+
JSON serialization
+
network transfer
```

Sometimes reducing the response size is a much better optimization than adding infrastructure.

---

# **38. Compression**

HTTP compression can reduce network transfer.

For example:

```text
JSON
 ↓
gzip/brotli
 ↓
smaller payload
```

But compression costs CPU.

So again:

```text
less network
+
more CPU
```

is a tradeoff.

Performance engineering is largely about understanding these tradeoffs.

---

# **39. Load testing**

You can’t confidently claim:

“ProjectHub handles 10,000 requests/sec.”

unless you’ve tested it.

Load testing might generate:

```text
100 req/s
500 req/s
1,000 req/s
2,000 req/s
...
```

while measuring:

```text
p50
p95
p99
error rate
CPU
memory
DB
Redis
RabbitMQ
```

---

# **40. Finding the saturation point**

Suppose:

```text
100 req/s  → p95 100ms
500 req/s  → p95 120ms
1,000 req/s → p95 180ms
2,000 req/s → p95 500ms
3,000 req/s → p95 3sec
```

We learned something important.

Around:

```text
2,000–3,000 req/s
```

the system begins approaching a bottleneck.

Now investigate what changed.

---

# **41. Performance curve**

You often see something like:

```text
latency
  ^
  |                       /
  |                     /
  |                   /
  |               ___/
  |          ____/
  |_________/
  +--------------------------> load
```

At first:

```text
more traffic
→
reasonable latency
```

Then:

```text
system saturation
→
latency increases sharply
```

That transition is extremely important operationally.

---

# **42. Don’t benchmark only the happy path**

Test:

```text
normal traffic
peak traffic
burst traffic
large payloads
slow DB
cache miss
high concurrency
dependency failure
```

For example:

```text
GET /posts
```

might be fast.

But:

```text
GET /projects/{id}/posts?includeComments=true
```

might expose N+1 queries and huge responses.

---

# **43. Performance testing layers**

A useful hierarchy:

```text
Unit benchmark
      ↓
Repository/query test
      ↓
Application load test
      ↓
Integration load test
      ↓
Production-like environment
```

Not every performance test needs the entire production environment.

---

# **44. Don’t optimize prematurely**

Suppose:

```text
endpoint = 20ms
```

and you spend three days reducing it to:

```text
18ms
```

while another endpoint is:

```text
4 seconds
```

You optimized the wrong thing.

Performance engineering is about **impact**.

---

# **45. A practical ProjectHub investigation**

Suppose users report:

“Project posts became slow.”

Start here:

### **Step 1 — Metrics**

```text
p50?
p95?
p99?
error rate?
traffic?
```

### **Step 2 — Traces**

Find:

```text
where is the time spent?
```

### **Step 3 — Database**

Check:

```text
query duration
query count
connection pool
locks
EXPLAIN
```

### **Step 4 — JVM**

Check:

```text
CPU
heap
GC
threads
```

### **Step 5 — Redis**

Check:

```text
hit rate
latency
memory
evictions
```

### **Step 6 — Kubernetes**

Check:

```text
Pod CPU
Pod memory
restarts
HPA
requests/limits
```

Now we’re investigating scientifically.

---

# **46. Example diagnosis**

Suppose we discover:

```text
p95 latency = 2.5s
```

Trace:

```text
Post endpoint = 2.4s
```

DB metrics:

```text
connection pool = 95%
```

SQL logs:

```text
101 queries/request
```

Then:

```text
N+1
 ↓
too many DB queries
 ↓
connection pressure
 ↓
latency
```

That’s a much stronger diagnosis than:

“We need more Pods.”

---

# **47. Fix**

Suppose we replace the N+1 query with a deliberate fetch/projection.

After deployment:

```text
queries/request:
101 → 2

p95:
2.5s → 180ms

DB connections:
95% → 35%
```

Now we have evidence that the optimization worked.

That’s performance engineering.

---

# **48. The optimization hierarchy**

When debugging ProjectHub, think roughly:

```text
1. Correct algorithm/query
        ↓
2. Correct database indexes
        ↓
3. Avoid unnecessary work
        ↓
4. Cache repeated expensive work
        ↓
5. Optimize serialization/network
        ↓
6. Tune JVM/resources
        ↓
7. Scale infrastructure
```

This isn’t an absolute ordering.

But it protects you from the common mistake:

**Throw more servers at an inefficient system.**

---

# **49. Performance and architecture**

At this point, notice how interconnected our lessons are:

```text
JPA
 ↓
N+1
 ↓
PostgreSQL
 ↓
indexes
 ↓
connection pool
 ↓
Redis
 ↓
Kubernetes scaling
 ↓
observability
```

Backend engineering isn’t a collection of isolated technologies.

It’s a system.

---

# **50. ProjectHub performance architecture**

Our target architecture now looks like:

```text
                        Internet
                           |
                        Gateway
                           |
                 +---------+---------+
                 |         |         |
               Pod       Pod       Pod
                 |         |         |
                 +---------+---------+
                           |
                    +------+------+
                    |             |
                  Redis       PostgreSQL
                    |             |
                    |        connection pool
                    |             |
                    +-------------+
```

And asynchronously:

```text
PostgreSQL
    |
  Outbox
    |
RabbitMQ
    |
Workers
```

With:

```text
Metrics
Logs
Traces
```

around everything.

---

# **51. One final principle**

When a system is slow, don’t ask:

“What technology should we add?”

Ask:

**“Where is the time going?”**

Then:

**“What resource is saturated?”**

Then:

**“What evidence proves the bottleneck?”**

Then:

**“What is the smallest change that addresses it?”**

That mindset is much more valuable than memorizing optimization tricks.

---

# **Lesson 58 Summary**

You now understand:

- Latency
- Throughput
- Resource utilization
- Performance bottlenecks
- Database indexes
- PostgreSQL `EXPLAIN`
- N+1 queries
- Projections
- Pagination
- Keyset pagination
- Connection pools
- Transaction duration
- JVM memory
- Garbage collection
- CPU
- Thread pools
- Virtual threads
- Caching
- Cache invalidation
- Serialization
- Compression
- Load testing
- Saturation
- Performance investigation

Spring Boot’s current Actuator/Micrometer integration exposes JVM, system, database and other application metrics, while PostgreSQL’s current documentation provides `EXPLAIN`/`EXPLAIN ANALYZE` specifically for understanding query plans and actual execution behavior.  

For Java 21 specifically, Oracle recommends beginning with JVM defaults before detailed GC tuning; G1 is the default collector on server-class machines.  

---

# **Exercise 58**

### **1. Bottleneck diagnosis**

You observe:

```text
p95 API latency:       2.8 sec
CPU:                   35%
Memory:                50%
DB connection pool:    98%
Redis hit rate:        92%
```

Where would you investigate first?

Why?

---

### **2. N+1**

A request loads:

```text
100 posts
```

and results in:

```text
101 SQL queries
```

Explain exactly why this can hurt performance.

Then give **two possible strategies** to fix it.

---

### **3. Connection pools**

You have:

```text
10 Kubernetes Pods
```

and:

```text
maximum DB connections per Pod = 20
```

What’s the potential maximum number of DB connections?

Why could blindly increasing the number of Pods make PostgreSQL slower?

---

### **4. Pagination**

Compare:

```sql
LIMIT 50 OFFSET 500000
```

with:

```sql
WHERE id > 500000
ORDER BY id
LIMIT 50
```

What problem is keyset pagination trying to solve?

---

### **5. JVM**

ProjectHub shows:

```text
CPU: 90%
GC activity: very high
heap: frequently near its limit
API p99: 4 seconds
```

Would you immediately switch garbage collectors?

Explain what you would investigate first.

---

### **6. Caching**

Suppose:

```text
GET /projects/42
```

is requested 10,000 times per minute.

PostgreSQL is doing the same expensive query repeatedly.

Design a cache-aside flow.

Then answer:

What happens when Project 42 is updated?

---

### **7. Load testing**

You run a load test:

```text
500 req/s  → p95 = 100ms
1000 req/s → p95 = 130ms
2000 req/s → p95 = 180ms
3000 req/s → p95 = 2.5s
```

What does this suggest?

What would you investigate next?

---

### **8. Final challenge**

ProjectHub’s:

```text
GET /projects/{id}/posts
```

suddenly becomes 10× slower.

You have access to:

```text
metrics
logs
traces
PostgreSQL
Redis
Kubernetes
```

Describe your **investigation sequence**, from the first thing you check through identifying the bottleneck.

Don’t jump directly to a fix.

The goal is to practice the engineer’s mindset:

```text
Measure
  ↓
Locate
  ↓
Hypothesize
  ↓
Change
  ↓
Measure again
```

**Next: Lesson 59 — Distributed Systems: consistency, replication, CAP, eventual consistency, distributed transactions, race conditions, and why scaling ProjectHub beyond one database changes the rules.**