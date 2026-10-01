---
title: Lesson 44: Caching in Spring Boot Redis, Cache Strategies, and Performance
sidebar_position: 44
---

Welcome to one of the most important performance topics in backend engineering.

A system can be:

- correctly designed
- secure
- scalable

and still be slow.

Why?

Because every request hitting your database has a cost.

Today we learn how to make ProjectHub faster using caching.

---

# **1. The problem: databases are expensive**

Imagine:

```text
User

 |
 v

Project Service

 |
 v

PostgreSQL
```

Every request:

```http
GET /api/projects/10
```

causes:

```sql
SELECT *
FROM projects
WHERE id = 10;
```

The database must:

1. receive request
2. parse SQL
3. find data
4. read storage
5. return result

---

Now imagine:

```text
10,000 users

requesting:

GET /projects/10
```

The database does:

```text
SELECT project 10

SELECT project 10

SELECT project 10

SELECT project 10

...
```

The same work repeated thousands of times.

---

# **2. What is caching?**

Caching means:

Store frequently used data somewhere faster.

Instead of:

```text
Application
    |
    v
Database
```

we add:

```text
Application

    |
    v

Cache

    |
    v

Database
```

---

# **3. Cache example**

First request:

```text
GET /projects/10
```

Flow:

```text
Project Service

     |
     |
     v

 Redis

(empty)

     |
     v

 PostgreSQL
```

Database returns:

```json
{
"id":10,
"name":"ProjectHub"
}
```

Store it:

```text
Redis:

project:10

{
"id":10,
"name":"ProjectHub"
}
```

---

Second request:

```text
GET /projects/10
```

Now:

```text
Project Service

     |
     v

Redis

     |
     v

Return immediately
```

Database is not touched.

---

# **4. Why Redis?**

A popular cache database:

Redis

Redis stores data in memory.

Memory is much faster than disk.

Example:

Database:

```text
milliseconds
```

Redis:

```text
microseconds
```

---

# **5. Redis data model**

Redis stores:

```text
key -> value
```

Example:

```
user:100

{
"name":"Ahmed",
"role":"ADMIN"
}
```

Another:

```
project:10

{
"title":"Website"
}
```

---

# **6. Cache vs Database**

Database:

Designed for:

- permanent storage
- transactions
- complex queries

Example:

```text
PostgreSQL
```

---

Cache:

Designed for:

- speed
- temporary storage
- frequent reads

Example:

```text
Redis
```

---

# **7. What should we cache?**

Good candidates:

## **User profiles**

Example:

```http
GET /users/100
```

Many requests.

Rarely changes.

---

## **Project details**

Example:

```http
GET /projects/10
```

Frequently viewed.

---

## **Permissions**

Example:

```text
Does user have projects.delete?
```

Permission checks happen often.

---

## **Expensive calculations**

Example:

```text
Dashboard statistics
```

---

# **8. What should NOT be cached?**

Avoid caching:

## **Frequently changing data**

Example:

```text
Bank balance
```

---

## **Sensitive data without protection**

Example:

```text
Passwords
```

Never cache passwords.

---

## **Data requiring absolute consistency**

Example:

```text
Inventory count
```

---

# **9. Types of caching**

There are several levels.

---

## **Browser cache**

Client side:

```text
Browser

stores images/css
```

---

## **CDN cache**

Example:

```text
Images
Videos
Static files
```

---

## **Application cache**

Inside Spring Boot:

```text
Java memory
```

---

## **Distributed cache**

Example:

```text
Redis
```

For multiple servers.

---

# **10. Local cache problem**

Imagine:

```text
             Load Balancer

              /       \

             /         \


       Server A       Server B


       Cache A        Cache B
```

User updates data:

Server A:

```text
cache updated
```

Server B:

```text
old cache
```

Problem:

Different servers have different data.

---

# **11. Distributed caching**

Solution:

```text
             Servers


        Server A
             |
             |
        Server B

             |
             v

           Redis
```

Everyone uses the same cache.

---

# **12. Spring Cache abstraction**

Spring provides:

```java
@Cacheable
```

Instead of manually writing Redis code.

---

Add dependency:

```xml
<dependency>

<groupId>
org.springframework.boot
</groupId>

<artifactId>
spring-boot-starter-cache
</artifactId>

</dependency>
```

For Redis:

```xml
<dependency>

<groupId>
org.springframework.boot
</groupId>

<artifactId>
spring-boot-starter-data-redis
</artifactId>

</dependency>
```

---

# **13. Enable caching**

Main application:

```java
@SpringBootApplication
@EnableCaching
public class ProjectApplication {


public static void main(String[] args){

SpringApplication.run(
ProjectApplication.class,
args
);

}

}
```

---

# **14. Using @Cacheable**

Example:

```java
@Service
public class ProjectService {


@Cacheable(
value="projects",
key="#id"
)
public Project getProject(Long id){

return repository.findById(id)
        .orElseThrow();

}

}
```

---

First call:

```java
getProject(10)
```

Flow:

```text
Method executes

Database query

Store result in cache
```

---

Second call:

```java
getProject(10)
```

Flow:

```text
Cache hit

Method does NOT execute
```

---

# **15. Cache hit and cache miss**

Important terms.

## **Cache hit**

Data exists:

```text
Redis

project:10

FOUND
```

Fast response.

---

## **Cache miss**

Data missing:

```text
Redis

project:10

NOT FOUND
```

Then:

```text
Database query
```

---

# **16. Cache invalidation**

The hardest caching problem.

Example:

Cache:

```text
project:10

name="Old Name"
```

User updates:

```text
New Name
```

Database:

```text
New Name
```

Cache:

```text
Old Name
```

Now wrong data is returned.

---

# **17. @CacheEvict**

Remove old cache.

Example:

```java
@CacheEvict(
value="projects",
key="#id"
)
public void updateProject(
Long id,
ProjectRequest request
){

repository.update(id,request);

}
```

Flow:

```text
Update database

      |

Delete cache

      |

Next request reloads fresh data
```

---

# **18. @CachePut**

Sometimes you update the cache directly.

Example:

```java
@CachePut(
value="projects",
key="#project.id"
)
public Project update(Project project){

return repository.save(project);

}
```

Flow:

```text
Database updated

+

Cache updated
```

---

# **19. Cache strategies**

Now the important design patterns.

---

# **Strategy 1: Cache Aside**

Most common.

Flow:

```text
Application

   |
   v

Check Cache

   |
   |
 Found?
   |
   +---- Yes
   |
   v

Return


No:

   |
   v

Database

   |
   v

Save Cache
```

Spring’s:

```java
@Cacheable
```

uses this idea.

---

# **Strategy 2: Write Through**

When writing:

```text
Application

 |
 +---- Database

 |
 +---- Cache
```

Both updated together.

---

Advantages:

Cache always fresh.

Disadvantages:

Writes slower.

---

# **Strategy 3: Write Behind**

Application writes:

```text
Application

 |
 v

Cache

 |
 |
Later

 v

Database
```

Very fast writes.

But more complex.

---

# **20. TTL (Time To Live)**

Cache data should expire.

Example:

```text
project:10

expires:

5 minutes
```

After 5 minutes:

```text
Redis deletes it
```

---

Why?

Because data changes.

---

Example:

User profile:

```text
TTL = 1 hour
```

Permission:

```text
TTL = 5 minutes
```

---

# **21. Redis configuration**

application.yml:

```yaml
spring:

 redis:

  host: localhost

  port: 6379
```

---

# **22. Serialization problem**

Redis stores bytes.

Example:

Java object:

```java
Project
```

needs conversion:

```
Project

     |

 JSON

     |

Redis
```

Common choice:

JSON serialization.

---

# **23. Cache keys design**

Bad:

```
10
```

What is 10?

---

Better:

```
project:10
```

Even better:

```
project:v1:10
```

Why?

Versioning.

---

Example:

```
user:profile:100
permission:user:100
dashboard:admin
```

---

# **24. Cache permissions**

Remember our permission system:

```
projects.read
projects.create
projects.delete
```

Checking:

```java
hasPermission(
"projects.delete"
)
```

many times.

Instead:

Cache:

```
permissions:user:100
```

Value:

```json
[
"projects.read",
"projects.create"
]
```

---

Flow:

```text
Request

 |
 v

Security Check

 |
 v

Redis

 |
 v

Allow/Deny
```

---

# **25. Cache stampede problem**

Imagine:

Cache expires:

```
project:10
```

at the same moment.

1000 users request:

```
GET /projects/10
```

All see:

```
cache miss
```

All hit database:

```
1000 database queries
```

Problem:

Cache stampede.

---

Solutions:

## **Locking**

Only one request refreshes.

Others wait.

---

## **Random TTL**

Instead of:

```
TTL = 300 seconds
```

use:

```
300 + random seconds
```

Avoid synchronized expiration.

---

# **26. Cache penetration**

Problem:

User requests:

```
GET /projects/999999
```

Does not exist.

Every request:

```
Redis miss

Database query

Nothing found
```

Repeated forever.

---

Solution:

Cache empty results.

Example:

```
project:999999

NULL

TTL 60 seconds
```

---

# **27. Cache security**

Never cache:

```text
passwords
```

Be careful with:

```text
private user data
```

Example:

Wrong:

```
profile:100
```

shared globally.

Better:

```
profile:user:100
```

with access control.

---

# **28. ProjectHub caching architecture**

Final design:

```text
                    Client

                       |

                       v

                 API Gateway

                       |

                       v

              Project Service


                       |

             +---------+---------+

             |                   |

             v                   v


           Redis             PostgreSQL


             |
             |
       cached projects

       cached permissions

       cached users
```

---

# **29. Production cache rules**

Good caching:

✅ Read-heavy data  
✅ Expensive queries  
✅ Frequently accessed data  
✅ Data that can tolerate slight delay

Avoid:

❌ Passwords  
❌ Constantly changing values  
❌ Critical financial data without strategy

---

# **30. The performance equation**

Without cache:

```
Request
 |
Database
 |
Response
```

Cost:

```
Database load = 100%
```

---

With cache:

```
Request

 |
Cache

 |
Response
```

Most requests never reach database.

---

# **Lesson 44 Summary**

You learned:

✅ Why caching exists  
✅ Redis basics  
✅ Cache vs database  
✅ Spring Cache  
✅ @Cacheable  
✅ @CacheEvict  
✅ @CachePut  
✅ Cache strategies  
✅ TTL  
✅ Cache invalidation  
✅ Cache stampede  
✅ Cache penetration  
✅ Permission caching  
✅ Distributed cache architecture

---

# **Exercise 44**

Answer:

### **1.**

Why is Redis faster than PostgreSQL?

---

### **2.**

Explain:

```
Cache hit
```

and:

```
Cache miss
```

---

### **3.**

A project is updated.

Should you:

A)

```
Update database only
```

B)

```
Update database
+
invalidate cache
```

Why?

---

### **4.**

Would you cache:

```
User permissions
```

?

Explain.

---

### **5.**

Design a Redis key structure for:

- User profile
- Project details
- User permissions

Example:

```
?
```

---

Next lesson:

# **Lesson 45 — Database Scaling: Indexes, Read Replicas, Sharding, and High Traffic Design**

We will learn how companies handle millions of database operations:

- why queries become slow
- database indexes deeply
- read/write separation
- replicas
- partitioning
- sharding
- designing for huge traffic

This is where backend architecture moves toward large-scale systems.