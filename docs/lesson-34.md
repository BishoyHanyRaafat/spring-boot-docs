---
title: "Lesson 34: Redis & Caching"
sidebar_position: 34
---

We’ve now got:

```text
ProjectHub
   ↓
PostgreSQL
```

PostgreSQL is our **source of truth**.

But imagine this endpoint:

```http
GET /projects/7
```

and Project 7 is requested **10,000 times per minute**.

Every request might do:

```text
HTTP
 ↓
Controller
 ↓
Service
 ↓
JPA
 ↓
PostgreSQL
 ↓
return project
```

That’s unnecessary work if the project changes rarely.

This is where **caching** comes in.

Spring Boot provides Spring’s cache abstraction, and Spring Data Redis provides Redis-backed caching through `RedisCacheManager`.  

---

# **1. What is a cache?**

A cache is a **faster temporary copy of data**.

Instead of:

```text
Every request
     ↓
PostgreSQL
```

we can have:

```text
Request
   ↓
Redis
   │
   ├── found → return immediately
   │
   └── missing
         ↓
      PostgreSQL
         ↓
       Redis
         ↓
       return
```

The database remains the source of truth.

Redis is the fast copy.

---

# **2. The fundamental rule**

Remember this:

**A cache is disposable.**

If Redis disappears:

```text
Redis ❌
```

we should still have:

```text
PostgreSQL ✅
```

The application might become slower, but it shouldn’t lose its actual data.

So:

```text
PostgreSQL
   ↓
authoritative data

Redis
   ↓
performance optimization
```

This distinction will become extremely important later.

---

# **3. What is Redis?**

Redis is an in-memory data store supporting key/value-style operations and several data structures, including strings, lists, sets, and sorted sets. Spring Data Redis provides both lower-level APIs such as `RedisTemplate` and higher-level integrations such as Redis-backed Spring caching.  

A simplistic Redis example is:

```text
key                 value
--------------------------------
project:7           {...}
project:8           {...}
project:9           {...}
```

You can think of it as:

```text
GET project:7
```

returning the cached value.

---

# **4. Why is Redis fast?**

The simplified explanation is:

```text
PostgreSQL
   ↓
disk-backed relational database
   ↓
queries, indexes, transactions...

Redis
   ↓
memory-oriented key/value store
   ↓
very fast simple lookups
```

Don’t interpret this as:

“Redis is always better than PostgreSQL.”

They’re designed for different purposes.

For ProjectHub:

```text
PostgreSQL
→ durable relational data

Redis
→ fast temporary data
```

---

# **5. A real ProjectHub example**

Suppose:

```http
GET /projects/7
```

returns:

```json
{
  "id": 7,
  "name": "ProjectHub",
  "description": "Our backend project"
}
```

Without caching:

```text
request 1 → PostgreSQL
request 2 → PostgreSQL
request 3 → PostgreSQL
...
request 10000 → PostgreSQL
```

With caching:

```text
request 1
   ↓
Redis miss
   ↓
PostgreSQL
   ↓
Redis

request 2
   ↓
Redis hit

request 3
   ↓
Redis hit

...

request 10000
   ↓
Redis hit
```

That’s the basic idea.

---

# **6. Cache hit vs cache miss**

These two terms are fundamental.

### **Cache hit**

The requested value is already cached.

```text
GET project:7
      ↓
Redis
      ↓
FOUND
      ↓
return
```

### **Cache miss**

The value isn’t cached.

```text
GET project:7
      ↓
Redis
      ↓
NOT FOUND
      ↓
PostgreSQL
```

Then we normally put the result into the cache.

---

# **7. Cache-aside pattern**

This is the caching pattern we’ll use first.

Also called:

**Lazy caching**

The application controls the cache.

Flow:

```text
              Request
                 │
                 ▼
              Redis
             /     \
          HIT       MISS
           │          │
           ▼          ▼
        return    PostgreSQL
                       │
                       ▼
                     Redis
                       │
                       ▼
                     return
```

This is simple and extremely common.

---

# **8. Why not cache everything?**

Because caching has costs.

Suppose we cache:

```text
GET /projects/7
```

Great.

But what about:

```text
GET /projects
```

returning 2 million projects?

Caching that entire result might be terrible.

Or:

```text
GET /posts/search?q=...
```

with millions of possible queries.

You could end up with:

```text
millions of cache entries
```

So the rule is:

Cache things where the performance benefit justifies the complexity and memory cost.

---

# **9. Good cache candidates**

ProjectHub examples:

```text
Project details
User profile
Permission metadata
Frequently accessed project summaries
Expensive read-only queries
External API responses
```

Potentially:

```text
GET /projects/7
GET /users/42
```

---

# **10. Bad cache candidates**

Be cautious with:

```text
Highly volatile data
Huge result sets
Rarely requested data
Sensitive data without a clear security design
Data where stale values are unacceptable
```

For example:

```text
Current account balance
```

might require very different consistency guarantees from:

```text
Project description
```

Never blindly cache because:

“Redis is fast.”

---

# **11. Spring’s cache abstraction**

Here’s where Spring becomes convenient.

Spring provides annotations such as:

```java
@Cacheable
@CachePut
@CacheEvict
```

The idea is:

```text
Your service
     ↓
Spring Cache abstraction
     ↓
CacheManager
     ↓
Redis
```

The application doesn’t have to manually write:

```java
redis.get(...)
redis.set(...)
```

for every cached method.

Spring’s cache abstraction applies caching transparently around methods, and Spring Boot can auto-configure a cache provider such as Redis when the necessary infrastructure is present.  

---

# 

# **12.**

**`@Cacheable`**

Imagine:

```java
@Cacheable("projects")
public ProjectResponse getProject(Long projectId) {
    return loadFromDatabase(projectId);
}
```

Conceptually:

```text
getProject(7)
      ↓
Spring checks cache
      ↓
  ┌───┴───┐
 HIT     MISS
  │        │
  │      method
  │        │
  │    PostgreSQL
  │        │
  └───┬────┘
      ▼
    result
```

The first call may execute the method.

Later calls can return the cached value.

---

# **13. Important: the method may not execute**

This is one of the key ideas behind `@Cacheable`.

Suppose:

```java
@Cacheable("projects")
public ProjectResponse getProject(Long projectId) {
    log.info("Loading project {} from database", projectId);
    return repository.findById(projectId)...
}
```

First request:

```text
Redis miss
 ↓
method executes
 ↓
database
```

Second request:

```text
Redis hit
 ↓
method may not execute
```

So:

```text
log.info(...)
```

may only appear on cache misses.

This is why understanding Spring’s proxy-based behavior matters.

---

# **14. Cache keys**

Suppose:

```java
@Cacheable("projects")
public ProjectResponse getProject(Long projectId)
```

and:

```text
projectId = 7
```

Spring needs a cache key.

Conceptually:

```text
projects::7
```

The exact key representation depends on configuration.

Spring Data Redis recommends keeping cache key prefixes enabled so different caches don’t accidentally overlap when they use the same key.  

So don’t think of:

```text
7
```

as globally unique.

Think:

```text
projects + 7
```

---

# **15. TTL — Time To Live**

Here’s the first major problem.

Suppose:

```text
Project 7
```

is cached.

Then someone changes the project:

```text
Project name:
"ProjectHub"
        ↓
"ProjectHub Backend"
```

But Redis still contains:

```text
"ProjectHub"
```

Now the cache is **stale**.

One solution is TTL.

TTL means:

How long should this cached value live?

For example:

```text
project cache TTL = 10 minutes
```

Then:

```text
cache created
     ↓
10 minutes
     ↓
expires
     ↓
next request → database
```

Spring Boot exposes Redis cache configuration including `spring.cache.redis.time-to-live`; the default TTL is no expiration unless configured otherwise.  

For many caches, explicitly choosing a TTL is safer than allowing entries to live forever.

---

# **16. TTL isn’t enough by itself**

Imagine:

```text
TTL = 1 hour
```

At:

```text
12:00
```

the project is cached.

At:

```text
12:05
```

someone changes the project.

The cache could still contain stale data until:

```text
13:00
```

So TTL gives us:

**eventual freshness**

not:

**immediate consistency**

---

# **17. Cache eviction**

That’s where:

```java
@CacheEvict
```

comes in.

Imagine:

```java
@CacheEvict(
    value = "projects",
    key = "#projectId"
)
public void updateProject(Long projectId, ...) {
    ...
}
```

The conceptual flow:

```text
UPDATE project
     ↓
PostgreSQL
     ↓
remove project from Redis
```

Then the next read:

```text
GET project/7
     ↓
cache miss
     ↓
PostgreSQL
     ↓
new value cached
```

This is a very common pattern.

---

# **18. Cache invalidation**

You’ve probably heard the famous joke:

There are only two hard things in Computer Science: cache invalidation and naming things.

There’s truth behind it.

Suppose Project 7 appears in:

```text
project cache
project list cache
project summary cache
project permissions cache
```

You update Project 7.

Which caches must be invalidated?

Now things get complicated.

---

# **19. Example of invalidation complexity**

Suppose:

```text
projects::7
projects::all
projects::owner::17
projects::active
```

You modify Project 7.

Deleting:

```text
projects::7
```

isn’t enough if:

```text
projects::all
```

still contains the old project.

So cache design must consider:

**What other cached representations become invalid when this data changes?**

This is why caching should be introduced deliberately.

---

# 

# **20.**

**`@CachePut`**

Another annotation is:

```java
@CachePut
```

Unlike `@Cacheable`, it generally **executes the method** and then updates the cache with the result.

Conceptually:

```text
updateProject()
      ↓
method executes
      ↓
PostgreSQL
      ↓
new result
      ↓
Redis updated
```

This can be useful when the returned value is the new authoritative representation.

But don’t automatically choose `@CachePut` over `@CacheEvict`.

The right strategy depends on your consistency requirements.

---

# **21. Three useful annotations**

Remember these:

```text
@Cacheable
    ↓
read through cache

@CachePut
    ↓
execute + update cache

@CacheEvict
    ↓
remove cache entry
```

For ProjectHub we’ll primarily start with:

```text
@Cacheable
@CacheEvict
```

---

# **22. Redis vs Spring Cache**

This distinction is important.

Redis itself is a data store.

Spring Cache is an **abstraction**.

Think:

```text
                    Spring Cache
                         │
             ┌───────────┼───────────┐
             ▼           ▼           ▼
           Redis       Caffeine     Other
```

Your application code can use:

```java
@Cacheable("projects")
```

without directly depending on Redis commands.

Spring Boot can auto-configure a `RedisCacheManager` when Redis is available/configured.  

---

# **23. But Redis can do more than caching**

This is important.

Redis isn’t merely:

```text
"the cache database"
```

It can also be used for things such as:

```text
distributed locks
rate limiting
session data
counters
leaderboards
pub/sub
streams
temporary state
```

Spring Data Redis provides support for Redis operations, repositories, caching, Pub/Sub, streams, and more.  

We’ll encounter some of these later.

---

# **24. Redis data structures**

Redis supports more than simple strings.

Conceptually:

```text
String
List
Set
Sorted Set
Hash
Streams
```

For example:

### **String**

```text
user:42:name → "Alice"
```

### **Set**

```text
project:7:members
    ↓
{17, 23, 91}
```

### **Sorted set**

Could represent:

```text
leaderboard
```

with scores.

### **Hash**

Could represent fields:

```text
user:42
    name → Alice
    role → ADMIN
```

We’re not going to use all of these yet.

---

# **25. Redis isn’t PostgreSQL replacement**

Consider our User:

```text
users
roles
permissions
projects
posts
comments
memberships
```

We want:

```text
PostgreSQL
```

because we need:

- relational modeling
- foreign keys
- transactions
- constraints
- joins
- durable source of truth

Redis is not a substitute for that architecture.

Our model remains:

```text
PostgreSQL = source of truth
Redis      = supporting infrastructure
```

---

# **26. Adding Redis to Docker Compose**

Our Compose architecture can now become:

```yaml
services:

  app:
    build: .
    ports:
      - "8080:8080"

    environment:
      SPRING_PROFILES_ACTIVE: docker
      DB_URL: jdbc:postgresql://postgres:5432/projecthub
      DB_USERNAME: projecthub
      DB_PASSWORD: projecthub
      REDIS_HOST: redis
      REDIS_PORT: 6379

    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  postgres:
    image: postgres:18

    # ...

  redis:
    image: redis:8

    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 10
```

The important new piece:

```text
REDIS_HOST=redis
```

Again:

```text
redis
```

is the Compose service name.

---

# **27. Spring configuration**

Our Docker profile might contain:

```yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT}
```

Then:

```text
ProjectHub
    ↓
REDIS_HOST=redis
    ↓
Docker DNS
    ↓
redis container
```

Spring Data Redis provides the connection infrastructure for Redis applications.  

---

# **28. Enable caching**

For Spring’s caching abstraction:

```java
@Configuration
@EnableCaching
public class CacheConfig {
}
```

Spring Boot’s caching support is enabled through `@EnableCaching`.  

One nuance from the official docs: putting `@EnableCaching` directly on the main application class can make caching mandatory even in tests, so a dedicated configuration class can be cleaner when you want flexibility across environments.  

---

# **29. Example ProjectHub service**

Imagine:

```java
@Service
public class ProjectService {

    @Cacheable(
        value = "projects",
        key = "#projectId"
    )
    @Transactional(readOnly = true)
    public ProjectResponse getProject(Long projectId) {

        return repository.findById(projectId)
                .map(mapper::toResponse)
                .orElseThrow();
    }
}
```

Conceptually:

```text
GET /projects/7
       ↓
ProjectService
       ↓
@Cacheable
       ↓
Redis?
   ┌───┴───┐
  YES      NO
   │        │
 return   PostgreSQL
            │
            ▼
          Redis
            │
            ▼
          return
```

---

# **30. Be careful with transactions**

Notice that caching and transactions are two different concerns.

```text
@Transactional
```

means:

Manage database transaction behavior.

```text
@Cacheable
```

means:

Manage cached method results.

They can interact, but don’t confuse them.

For example, you don’t want to cache data before you’re sure the database transaction has successfully committed.

This becomes particularly important for writes and cache invalidation.

We’ll revisit this when we discuss advanced transaction/caching patterns.

---

# **31. Cache only what you’re comfortable serving stale**

This is probably the most important practical rule from today’s lesson.

Ask:

“If this value is five minutes old, is that acceptable?”

For:

```text
Project description
```

maybe.

For:

```text
User's current permissions
```

be much more careful.

For:

```text
Password validation
```

definitely don’t casually introduce caching.

For:

```text
Financial balance
```

you need a completely different consistency strategy.

Caching is fundamentally a **data consistency decision**, not merely a performance trick.

---

# **32. Security + caching**

This deserves special attention for ProjectHub.

Suppose we cache:

```text
GET /projects/7
```

and the response differs depending on the current user.

For example:

```text
Alice → can see private fields
Bob   → cannot see private fields
```

If you cache incorrectly using only:

```text
projectId = 7
```

you could accidentally return Alice’s representation to Bob.

That’s a serious authorization bug.

So when cached results depend on identity or permissions, the cache key must reflect the relevant security context—or the data should not be cached at that layer.

This is one reason we’ll start with relatively simple, non-user-specific project data.

---

# **33. Cache keys should reflect the result’s inputs**

Suppose:

```text
GET /projects/7
```

depends only on:

```text
projectId
```

Then:

```text
projects::7
```

makes sense.

But suppose:

```text
GET /projects/7/posts?page=2&size=20
```

depends on:

```text
projectId
page
size
sort
filters
```

Then a key containing only:

```text
projects-posts::7
```

would be incorrect.

Different requests could overwrite each other.

So:

A cache key must identify the complete set of inputs that affect the cached result.

---

# **34. Cache stampede**

Here’s another production problem.

Suppose:

```text
project:7
```

expires at exactly 12:00.

At 12:00:

```text
10,000 requests
       ↓
Redis MISS
       ↓
10,000 PostgreSQL queries
```

Oops.

The cache protected the database for 59 minutes and then suddenly created a database spike.

This is sometimes called a:

**cache stampede**

or:

**cache avalanche**

There are techniques to mitigate it:

```text
request coalescing
locking
jittered TTLs
background refresh
stale-while-revalidate
```

We won’t implement these yet.

Just recognize the problem.

---

# **35. Cache invalidation strategies**

There are several broad approaches:

### **TTL only**

```text
cache
 ↓
wait
 ↓
expire
```

Simple, but potentially stale.

### **Explicit eviction**

```text
update DB
 ↓
evict cache
```

More consistent.

### **Update cache**

```text
update DB
 ↓
update cache
```

Potentially efficient, but more complicated.

### **Don’t cache**

Sometimes the best caching strategy is:

**No cache.**

If PostgreSQL can easily handle the query, adding Redis might only create unnecessary complexity.

---

# **36. ProjectHub’s first caching target**

Let’s keep our first implementation intentionally simple.

We’ll cache:

```text
GET /projects/{id}
```

with:

```text
cache name: projects
key: projectId
TTL: 10 minutes
```

And when a project changes:

```text
UPDATE project
    ↓
evict projects::{id}
```

So:

```text
READ
  ↓
@Cacheable

WRITE
  ↓
@CacheEvict
```

This is a very good learning example because it exposes the core concepts without immediately creating a distributed-cache monster.

---

# **37. The architecture**

Our ProjectHub stack is now:

```text
                         ProjectHub
                             │
                  ┌──────────┴──────────┐
                  │                     │
             PostgreSQL               Redis
                  │                     │
             source of truth        cache
                  │                     │
                  └──────────┬──────────┘
                             │
                           Service
                             │
                      Spring Cache
```

And the read flow:

```text
HTTP
 ↓
Controller
 ↓
ProjectService
 ↓
Redis
 ├── HIT → response
 │
 └── MISS
       ↓
   PostgreSQL
       ↓
     Redis
       ↓
   response
```

---

# **38. One final mental model**

Don’t think:

“Redis makes my application fast.”

Think:

“Redis can reduce expensive repeated work when the application’s consistency requirements allow cached data.”

That’s a much more mature way to think about caching.

---

# **Exercise 34**

Before implementing Redis, answer these.

### **1. Cache hit**

What happens here?

```text
GET /projects/7

Redis:
projects::7 → FOUND
```

Does PostgreSQL need to be queried?

---

### **2. Cache miss**

What happens here?

```text
GET /projects/7

Redis:
projects::7 → NOT FOUND
```

Describe the complete flow.

---

### **3. TTL**

If:

```text
TTL = 10 minutes
```

and a project changes 2 minutes after being cached, what could a reader see?

Why?

---

### **4. Invalidation**

Why would this be useful after updating Project 7?

```java
@CacheEvict(
    value = "projects",
    key = "#projectId"
)
```

---

### **5. Security**

Suppose Alice and Bob can receive different representations of Project 7.

Why could this be dangerous?

```java
@Cacheable(
    value = "projects",
    key = "#projectId"
)
```

---

### **6. Database vs Redis**

Explain why:

```text
PostgreSQL = source of truth
Redis      = cache
```

is a safer mental model than:

```text
PostgreSQL and Redis contain equally authoritative copies
```

---

### **7. Most important question**

Should **every** database query be cached?

Explain why or why not.

---

**Next: Lesson 35 — Redis Implementation in ProjectHub.**

We’ll actually add the Redis Compose service, Spring Data Redis dependencies, cache configuration, `@Cacheable`, `@CacheEvict`, TTL configuration, and then trace exactly what happens during a cache hit and miss.