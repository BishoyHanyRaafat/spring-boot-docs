---
title: "Lesson 35: Implementing Redis Caching in Spring Boot"
sidebar_position: 35
---

**Today** we move from **theory** into the actual ProjectHub implementation.

By the end of this lesson, ProjectHub will have:

```text
Client
  |
  v
Controller
  |
  v
Service
  |
  +------------+
  |            |
  v            v
 Redis       PostgreSQL
(cache)      (source of truth)
```

We will implement:

- Redis in Docker Compose
- Spring Data Redis
- Spring Cache
- `@Cacheable`
- `@CacheEvict`
- TTL configuration
- Cache testing
- Common mistakes

---

# **1. Add Redis to Docker Compose**

Our current architecture:

```text
docker-compose.yaml

ProjectHub
PostgreSQL
```

becomes:

```text
docker-compose.yaml

ProjectHub
PostgreSQL
Redis
```

Add:

```yaml
redis:
  image: redis:8

  ports:
    - "6379:6379"

  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 5s
    timeout: 5s
    retries: 10
```

Now:

```text
ProjectHub container
        |
        |
        v
 redis:6379
```

Remember:

Inside Docker:

```
redis
```

is the hostname.

Not:

```
localhost
```

---

# **2. Add Redis dependency**

For Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
```

What this gives us:

```text
Spring Boot
     |
     |
Spring Data Redis
     |
     |
Redis client
     |
     |
Redis server
```

Spring Data Redis provides Redis integration including templates, repositories, and cache support. (⁠[docs.spring.io](https://docs.spring.io/spring-data/redis/reference/redis.html?utm_source=chatgpt.com))

---

# **3. Configure Redis connection**

Create:

```
application-docker.yml
```

Add:

```yaml
spring:

  data:
    redis:
      host: redis
      port: 6379
```

Notice:

```yaml
host: redis
```

because Docker Compose gives us:

```
service name → hostname
```

Our flow:

```
Spring Boot
     |
     |
redis:6379
     |
     |
Redis container
```

---

# **4. Enable Spring caching**

Create:

```
CacheConfig.java
```

```java
@Configuration
@EnableCaching
public class CacheConfig {

}
```

This activates Spring’s cache infrastructure.

Now Spring understands:

```java
@Cacheable
@CacheEvict
@CachePut
```

---

# **5. Understand what Spring Cache does**

Before:

```java
public Project getProject(Long id){

    return repository.findById(id)
            .orElseThrow();

}
```

Every call:

```
request
   |
database
```

After:

```java
@Cacheable("projects")
public Project getProject(Long id){

    return repository.findById(id)
            .orElseThrow();

}
```

Now:

```
request
   |
cache?
   |
   +---- YES
   |       |
   |       return
   |
   +---- NO
           |
       database
           |
        cache
```

The method becomes cache-aware.

---

# **6. Our Project entity**

Imagine:

```java
@Entity
public class Project {

    @Id
    private Long id;

    private String name;

    private String description;

}
```

Repository:

```java
public interface ProjectRepository
        extends JpaRepository<Project, Long> {

}
```

Nothing changes here.

Redis does not replace JPA.

---

# **7. Add caching to the service**

Before:

```java
@Service
@RequiredArgsConstructor
public class ProjectService {


    private final ProjectRepository repository;


    public Project getProject(Long id){

        return repository.findById(id)
                .orElseThrow();

    }

}
```

After:

```java
@Service
@RequiredArgsConstructor
public class ProjectService {


    private final ProjectRepository repository;


    @Cacheable(
        value = "projects",
        key = "#id"
    )
    public Project getProject(Long id){

        System.out.println("Loading from database");

        return repository.findById(id)
                .orElseThrow();

    }

}
```

---

# **8. First request**

Call:

```
GET /projects/10
```

Sequence:

```
Controller
    |
ProjectService
    |
@Cacheable
    |
Redis
    |
MISS
    |
Repository
    |
PostgreSQL
    |
return project
    |
store in Redis
```

Console:

```
Loading from database
```

Redis now contains:

```
projects::10
```

---

# **9. Second request**

Same request:

```
GET /projects/10
```

Flow:

```
Controller
    |
ProjectService
    |
@Cacheable
    |
Redis
    |
HIT
    |
return
```

Database is never touched.

Console:

```
(no output)
```

Because:

```java
System.out.println("Loading from database");
```

never executed.

---

# **10. Important Spring proxy behavior**

This surprises beginners.

This works:

```java
controller
      |
      v
service method
```

because Spring creates a proxy:

```
Controller
    |
    v
Spring Proxy
    |
    v
Real Service
```

The proxy intercepts:

```java
@Cacheable
```

before calling your method.

---

But this may NOT work:

```java
@Service
public class ProjectService {


    public void methodA(){

        methodB();

    }


    @Cacheable("projects")
    public Project methodB(){

    }

}
```

Why?

Because:

```
methodA()
 |
 this.methodB()
 |
 bypasses proxy
```

Spring never sees the caching annotation.

This concept is extremely important.

---

# **11. Cache eviction on update**

Now imagine:

```
PUT /projects/10
```

We update:

```java
Project project =
repository.save(updated);
```

But Redis still has:

```
projects::10

old data
```

Problem.

Solution:

```java
@CacheEvict(
    value = "projects",
    key = "#id"
)
public Project updateProject(
        Long id,
        UpdateProjectRequest request){

    Project project =
        repository.findById(id)
        .orElseThrow();


    project.setName(request.name());


    return repository.save(project);
}
```

Flow:

```
update request
      |
PostgreSQL update
      |
remove Redis entry
      |
next GET
      |
reload fresh data
```

---

# **12. What about deleting?**

Same idea.

Before:

```
DELETE /projects/10

database removed
Redis still exists
```

Wrong.

Use:

```java
@CacheEvict(
    value="projects",
    key="#id"
)
public void deleteProject(Long id){

    repository.deleteById(id);

}
```

Now:

```
DELETE

PostgreSQL
     |
Redis eviction
```

---

# **13. Multiple cache entries**

Imagine:

```text
projects::10
```

but also:

```
projects:list
```

After update:

```
Project 10 changed
```

You might need:

```java
@CacheEvict(
    value="projects",
    allEntries=true
)
```

Example:

```java
@CacheEvict(
    value="projects",
    allEntries=true
)
public Project updateProject(...)
```

Meaning:

```
delete everything in projects cache
```

Simple but sometimes expensive.

---

# **14. Configure TTL**

Right now:

```
cache entry
     |
     |
never expires
```

Dangerous.

Configure:

```yaml
spring:

  cache:
    type: redis

  data:
    redis:
      host: redis
      port: 6379
```

Then:

```java
@Configuration
@EnableCaching
public class CacheConfig {


@Bean
RedisCacheConfiguration cacheConfiguration(){

    return RedisCacheConfiguration
            .defaultCacheConfig()
            .entryTtl(Duration.ofMinutes(10));

}

}
```

Now:

```
cache created
      |
      |
10 minutes
      |
      |
expired
```

---

# **15. Cache serialization**

A question:

How does Redis store:

```java
ProjectResponse
```

?

Redis stores bytes.

So Spring must serialize:

```
Java object

    |
    v

JSON / bytes

    |
    v

Redis
```

Example:

Java:

```java
ProjectResponse(
 id=10,
 name="ProjectHub"
)
```

Redis:

```json
{
"id":10,
"name":"ProjectHub"
}
```

Serialization strategy matters.

---

# **16. Cache DTOs, not entities**

A common mistake:

```java
@Cacheable("projects")
public Project getProject(Long id)
```

Caching JPA entities directly can create problems.

Why?

Entities contain:

- lazy relationships
- Hibernate proxies
- persistence context assumptions

Better:

```java
@Cacheable("projects")
public ProjectResponse getProject(Long id)
```

Flow:

```
Database entity
       |
       v
DTO
       |
       v
Redis
```

Cache what you actually return.

---

# **17. Example DTO**

```java
public record ProjectResponse(
        Long id,
        String name,
        String description
){

}
```

Service:

```java
@Cacheable(
    value="projects",
    key="#id"
)
public ProjectResponse getProject(Long id){

    Project project =
        repository.findById(id)
        .orElseThrow();


    return mapper.toResponse(project);

}
```

Now Redis stores:

```json
{
"id":10,
"name":"ProjectHub",
"description":"Backend"
}
```

Cleaner.

---

# **18. Checking Redis manually**

Enter Redis:

```bash
docker exec -it redis redis-cli
```

Then:

```bash
KEYS *
```

You may see:

```
projects::10
```

Check:

```bash
GET projects::10
```

Depending on serialization, the output may not be human-readable.

That’s normal.

---

# **19. Cache logging**

Add:

```yaml
logging:

  level:

    org.springframework.cache: TRACE
```

Now you can see:

```
Cache miss
Cache hit
Cache put
```

Useful while learning.

Usually you reduce this in production.

---

# **20. Testing caching**

Create a test:

First call:

```java
projectService.getProject(1L);
```

Expect:

```
database called
```

Second:

```java
projectService.getProject(1L);
```

Expect:

```
database NOT called
```

Mockito example:

```java
verify(repository, times(1))
.findById(1L);
```

Even though the service was called twice.

---

# **21. Common mistakes**

## **Mistake 1**

Caching everything.

Bad:

```java
@Cacheable("*")
```

Reality:

Some things should not be cached.

---

## **Mistake 2**

Caching sensitive data.

Example:

```text
User permissions
private documents
financial data
```

Need careful design.

---

## **Mistake 3**

No invalidation strategy.

Example:

```
cache forever
```

Then users see old data.

---

## **Mistake 4**

Using Redis as the database.

Bad:

```
Redis = primary storage
Postgres = backup
```

For our application:

```
Postgres = truth
Redis = acceleration
```

---

# **22. Our final ProjectHub caching flow**

Read:

```
GET /projects/10

Controller

    |
    v

Service

    |
    v

Redis

   HIT
    |
    v
 response


   MISS
    |
    v

PostgreSQL

    |
    v

Redis

    |
    v

response
```

Write:

```
PUT /projects/10

Controller

    |
    v

Service

    |
    v

PostgreSQL update

    |
    v

Redis eviction
```

---

# **23. Architecture after Lesson 35**

We now have:

```
                         Docker Compose

        +-------------------+----------------+
        |                   |                |
        v                   v                v

  Spring Boot          PostgreSQL          Redis

      |                   |                |
      |                   |                |
      +-------------------+----------------+

              Spring Cache Layer

                     |
                     |

             Project Services
```

---

# **Exercise 35**

Answer these:

### **1.**

First request:

```
GET /projects/5
```

Redis is empty.

Explain the full flow.

---

### **2.**

Second request:

```
GET /projects/5
```

Redis contains:

```
projects::5
```

What happens?

---

### **3.**

Why is this risky?

```java
@Cacheable(
 value="projects",
 key="#id"
)
public Project getProject(Long id)
```

if the response depends on the logged-in user?

---

### **4.**

Why do we prefer:

```java
ProjectResponse
```

over:

```java
Project entity
```

inside Redis?

---

### **5.**

Explain the difference:

```
@Cacheable
```

vs

```
@CacheEvict
```

---

### **6.**

Should Redis replace PostgreSQL in ProjectHub?

Explain.

---

Next lesson:

# **Lesson 36 — Messaging with RabbitMQ**

We will introduce asynchronous communication:

```
User creates a project
        |
        v
Project service
        |
        v
RabbitMQ message
        |
        v
Notification service
```

We’ll learn:

- why asynchronous systems exist
- queues vs topics
- producers and consumers
- RabbitMQ architecture
- Spring AMQP
- events in a real backend
- when NOT to use messaging

This is where ProjectHub starts moving from a simple backend into a distributed system.