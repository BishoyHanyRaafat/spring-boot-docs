---
title: What is Next?
sidebar_position: 1000
---

# **Lesson 94 — Final Review & What Comes Next**

You’ve now reached the end of the original backend roadmap.

And there’s an important shift now:

**You don’t need another 50 tutorials. You need to build.**

The current stable Spring Boot line is **4.1.1**, and the current stable Spring Security line is **7.1.1**, so when you start your real implementation, use the current managed versions rather than copying old tutorials blindly.  

---

# **1. The whole journey in one map**

You started with:

```text
Java
```

and built upward:

```text
Java
 │
 ├── OOP
 ├── Collections
 ├── Generics
 ├── Exceptions
 ├── Streams
 └── Records
       │
       ▼
Spring
 │
 ├── IoC
 ├── DI
 ├── Beans
 ├── Configuration
 └── ApplicationContext
       │
       ▼
Spring Boot
 │
 ├── REST
 ├── Validation
 ├── Error handling
 └── Configuration
       │
       ▼
Database
 │
 ├── SQL
 ├── PostgreSQL
 ├── JPA/Hibernate
 ├── Relationships
 ├── Transactions
 ├── Queries
 └── Flyway
       │
       ▼
Security
 │
 ├── Authentication
 ├── Authorization
 ├── Password hashing
 ├── Roles
 ├── Permissions
 ├── JWT
 ├── Refresh tokens
 └── Resource ownership
       │
       ▼
Distributed systems
 │
 ├── Transactions
 ├── Events
 ├── Outbox
 ├── Kafka
 ├── RabbitMQ
 ├── Retries
 ├── DLT
 ├── Idempotency
 └── Ordering
       │
       ▼
Testing
 │
 ├── JUnit
 ├── Mockito
 ├── MockMvc
 ├── Test slices
 ├── Testcontainers
 └── Integration testing
       │
       ▼
Production
 │
 ├── Configuration
 ├── Logging
 ├── Metrics
 ├── Tracing
 ├── Performance
 ├── Docker
 ├── Kubernetes
 └── CI/CD
```

That’s a substantial backend foundation.

---

# **2. The five layers you should now see**

When you encounter a new backend system, mentally separate it into:

### **Application**

```text
Controllers
Services
Domain logic
Repositories
```

### **Data**

```text
PostgreSQL
Transactions
Indexes
Migrations
```

### **Security**

```text
Authentication
Authorization
Permissions
Resource ownership
```

### **Integration**

```text
Kafka
RabbitMQ
HTTP APIs
Outbox
Events
```

### **Infrastructure**

```text
Docker
Kubernetes
CI/CD
Observability
```

This mental model is more valuable than memorizing individual annotations.

---

# **3. What I want you to build now**

Don’t start another tutorial.

Build **ProjectHub yourself**.

Start with a smaller production-style version:

```text
Users
Projects
Posts
Comments
```

Then implement:

```text
POST   /auth/register
POST   /auth/login
POST   /auth/refresh
POST   /auth/logout

GET    /projects
POST   /projects

GET    /projects/{id}
PATCH  /projects/{id}
DELETE /projects/{id}

GET    /projects/{id}/posts
POST   /projects/{id}/posts

GET    /posts/{id}
PATCH  /posts/{id}
DELETE /posts/{id}
```

Don’t copy the implementation from the course.

Use the concepts.

---

# **4. Your authorization model**

Start with:

```text
Permissions
───────────

projects.read
projects.create
projects.update
projects.delete

posts.read
posts.create
posts.update
posts.delete
```

Then:

```text
ADMIN
 └── everything

PROJECT_MANAGER
 ├── projects.read
 ├── projects.update
 ├── posts.read
 ├── posts.create
 └── posts.update

MEMBER
 ├── projects.read
 ├── posts.read
 └── posts.create
```

And then add resource-level rules:

```text
has posts.delete
        AND
belongs to project
        AND
allowed to delete this post
```

This will force you to actually understand the difference between **RBAC and resource authorization**.

Spring Security explicitly supports both authentication and authorization, including method/service-layer security.  

---

# **5. Then make it asynchronous**

Once the basic application works:

```text
Post created
     │
     ▼
PostgreSQL
     │
     └── Outbox
            │
            ▼
          Kafka
            │
       ┌────┼────┐
       ▼    ▼    ▼
   Search Audit Notification
```

Then deliberately break things.

Test:

```text
Kafka unavailable
consumer crashes
duplicate event
malformed event
consumer too slow
publisher crashes
```

That’s where distributed-systems knowledge becomes real rather than theoretical.

---

# **6. Then containerize it**

Your local environment:

```text
Docker Compose
│
├── projecthub
├── postgres
├── kafka
├── rabbitmq
└── maybe redis
```

Don’t add Redis just because we studied it.

Add it when your application has a reason to cache something.

---

# **7. Then Kubernetes**

Move the application into:

```text
Kubernetes
│
├── Deployment
├── Service
├── ConfigMap
├── Secret
├── Gateway
└── probes
```

Kubernetes uses declarative API objects to represent desired cluster state, and Gateway API provides the current extensible model for traffic routing.  

Your production flow becomes:

```text
Git
 ↓
CI
 ↓
Docker image
 ↓
Registry
 ↓
Kubernetes
 ↓
ProjectHub
```

---

# **8. Then test the whole thing**

Your test pyramid should roughly look like:

```text
             /\
            /  \
           / E2E\
          /------\
         /Integration\
        /------------\
       / Slice tests  \
      /----------------\
     /   Unit tests     \
    /____________________\
```

Lots of:

```text
unit tests
```

Some:

```text
@WebMvcTest
@DataJpaTest
```

Real infrastructure where appropriate:

```text
Testcontainers
```

And fewer:

```text
@SpringBootTest
```

full-system tests.

---

# **9. Then performance-test it**

Don’t say:

“My API is fast.”

Measure it.

Test:

```text
100 concurrent users
500 concurrent users
1,000 concurrent users
```

Measure:

```text
p50
p95
p99
error rate
CPU
memory
database connections
database latency
Kafka lag
```

Then find the actual bottleneck.

---

# **10. Your next-level topics**

After ProjectHub, these are the areas I’d go deeper into.

### **Java**

```text
Concurrency
Virtual threads
JVM memory
Garbage collection
Advanced generics
Performance
```

### **Spring**

```text
Spring internals
AOP
Events
Caching
Scheduling
Async processing
Spring Modulith
```

Spring’s ecosystem currently includes projects such as Spring Data, Spring Kafka, Spring AMQP, Spring Cloud, Spring Modulith and others, so there’s a lot of depth available after the fundamentals.  

### **Databases**

```text
EXPLAIN ANALYZE
Advanced indexing
Locking
Isolation
Query optimization
Partitioning
Replication
```

### **Distributed systems**

This is probably your biggest next jump:

```text
Consensus
Consistency
CAP
Leader election
Distributed locks
Sagas
CQRS
Event sourcing
Backpressure
Rate limiting
Circuit breakers
```

You don’t need all of these immediately.

---

# **11. The thing I would NOT do**

Don’t spend six months learning:

```text
Kafka
Kubernetes
Redis
GraphQL
gRPC
AWS
Terraform
ArgoCD
Elasticsearch
Cassandra
```

without building anything.

You already know enough concepts to create something substantial.

The next stage should be:

```text
20% learning
80% building/debugging
```

---

# **12. Your practical roadmap**

Here’s the path I’d follow:

```text
PHASE 1
Build ProjectHub core
        ↓
PHASE 2
Authentication + authorization
        ↓
PHASE 3
Testing
        ↓
PHASE 4
Outbox + Kafka
        ↓
PHASE 5
RabbitMQ workers
        ↓
PHASE 6
Docker Compose
        ↓
PHASE 7
Kubernetes
        ↓
PHASE 8
CI/CD
        ↓
PHASE 9
Observability
        ↓
PHASE 10
Load testing + optimization
```

At the end, you won’t just be able to answer:

“What is Kafka?”

You’ll be able to explain:

“Why does this system use Kafka here, what happens if publishing fails, how duplicates are handled, how consumers recover, how the application is deployed, and how we’d know something went wrong.”

**That is the level we’re aiming for.**

---

# **13. One final mental model**

When you see a backend system, ask these questions:

```text
1. Where does the request enter?

2. How is the user authenticated?

3. How is authorization decided?

4. Where does business logic live?

5. Where is transactional state stored?

6. What happens when data changes?

7. What events are produced?

8. How are duplicate events handled?

9. What happens when dependencies fail?

10. How is the application tested?

11. How is it deployed?

12. How do we observe it?

13. How does it scale?

14. How does it recover?
```

If you can answer those questions, you can reason about a **real backend architecture**, not just write Spring controllers.

---

## **And one important correction to keep in mind**

Throughout the course we’ve intentionally used current APIs, but Spring moves quickly. Before starting your actual ProjectHub implementation, check the current official references rather than assuming an older tutorial is still correct. As of now, the official docs list **Spring Boot 4.1.1** and **Spring Security 7.1.1** as stable.  

### **You’ve finished the course roadmap. 🎯**

The next useful step isn’t another lecture.

It’s **building ProjectHub from an empty repository**, feature by feature, with you writing the code and me reviewing/debugging it with you.