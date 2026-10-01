---
title: "Lesson 93: The Complete ProjectHub Architecture"
sidebar_position: 93
---



This is the lesson where all the pieces finally become **one system**.

You’ve learned each component separately. Now stop thinking:

“Spring Security… Kafka… Kubernetes… JPA…”

as isolated technologies.

Instead, think:

**What happens when a user performs one business operation?**

We’ll use:

```text
POST /projects/42/posts
```

as the example.

The current stable Spring Boot release is **4.1.1**, so the architecture below is aligned with the current Spring Boot documentation.  

---

# **1. The complete architecture**

Here’s the big picture:

```text
                         INTERNET
                            │
                            ▼
                     DNS / HTTPS
                            │
                            ▼
                    Gateway / Ingress
                            │
                            ▼
                  ┌───────────────────┐
                  │ Kubernetes        │
                  │                   │
                  │  ProjectHub API   │
                  │                   │
                  │ ┌────┐ ┌────┐     │
                  │ │Pod │ │Pod │ ... │
                  │ └────┘ └────┘     │
                  └────────┬──────────┘
                           │
            ┌──────────────┼───────────────┐
            ▼              ▼               ▼
       PostgreSQL        Kafka          RabbitMQ
            │              │               │
         Outbox       Event consumers    Workers
            │              │               │
            └──────────────┼───────────────┘
                           │
                    External services
```

And surrounding everything:

```text
             ┌──────────────────────────────┐
             │ Security                      │
             │ Configuration                 │
             │ Testing                       │
             │ Observability                 │
             │ CI/CD                         │
             └──────────────────────────────┘
```

Kubernetes Services provide stable networking to the changing set of Pods, while Gateway API provides the modern Kubernetes model for external traffic routing.  

---

# **2. A user creates a post**

The request starts here:

```http
POST /projects/42/posts
Authorization: Bearer <JWT>
```

The request travels:

```text
User
 ↓
HTTPS
 ↓
Gateway
 ↓
Kubernetes Service
 ↓
ProjectHub Pod
 ↓
Spring Security
 ↓
Controller
 ↓
Service
 ↓
PostgreSQL
```

Let’s walk through it.

---

# **3. Step 1 — Security**

Spring Security examines the request.

Conceptually:

```text
JWT
 │
 ▼
Authentication
 │
 ▼
User identity
 │
 ▼
Authorities
```

Suppose the JWT represents:

```text
userId = 17

authorities:
    posts.read
    posts.create
```

Then:

```java
@PreAuthorize("hasAuthority('posts.create')")
```

allows the method to execute.

Spring Boot supports method-level security through `@EnableMethodSecurity`.  

Remember our distinction:

```text
Authentication
    ↓
"Who are you?"

Authorization
    ↓
"Are you allowed to do this?"
```

---

# **4. Step 2 — Controller**

The controller should be thin:

```text
HTTP
 ↓
DTO
 ↓
Service
```

Something conceptually like:

```java
@PostMapping
public PostResponse create(
        @PathVariable Long projectId,
        @Valid @RequestBody CreatePostRequest request) {

    return postService.create(projectId, request);
}
```

The controller shouldn’t contain:

```text
database logic
authorization business rules
Kafka publishing
transaction orchestration
```

Those belong elsewhere.

---

# **5. Step 3 — Service**

Now the business operation begins.

Conceptually:

```text
PostService.create()
       │
       ├── verify project
       ├── verify membership
       ├── create Post
       ├── create Outbox event
       └── commit transaction
```

The service represents the business operation.

---

# **6. Step 4 — PostgreSQL transaction**

This is the critical part.

We want:

```text
Post creation
+
Outbox event
```

to happen in **the same database transaction**.

Conceptually:

```text
BEGIN

INSERT INTO posts ...

INSERT INTO outbox_events ...

COMMIT
```

If the transaction fails:

```text
Post       ❌
Outbox     ❌
```

If it succeeds:

```text
Post       ✅
Outbox     ✅
```

That’s the fundamental reason we introduced the Outbox Pattern.

---

# **7. Why don’t we publish to Kafka inside that transaction?**

Because:

```text
PostgreSQL transaction
        +
Kafka transaction
```

are different systems.

If you do:

```text
DB commit
   ↓
Kafka publish
```

and Kafka fails:

```text
database = changed
Kafka    = not changed
```

Now your systems disagree.

Instead:

```text
DB transaction
   │
   ├── Post
   └── Outbox event
          │
          ▼
      COMMIT
          │
          ▼
   Outbox publisher
          │
          ▼
        Kafka
```

The database becomes the durable source of event intent.

---

# **8. Step 5 — Outbox publisher**

A separate publisher periodically finds:

```text
status = PENDING
```

events.

Then:

```text
Outbox
  ↓
claim
  ↓
publish Kafka
  ↓
mark PUBLISHED
```

With multiple Kubernetes Pods:

```text
Pod A ──┐
Pod B ──┼──> Outbox table
Pod C ──┘
```

we use database concurrency controls so two publishers don’t intentionally process the same row simultaneously.

But even then:

**Duplicates are still possible.**

For example:

```text
publish to Kafka
      ↓
Kafka accepts event
      ↓
publisher crashes
      ↓
database still says PENDING
```

The publisher retries.

Kafka receives the event again.

That’s why downstream consumers must be **idempotent**.

---

# **9. Step 6 — Kafka**

Our event might look conceptually like:

```json
{
  "eventId": "8c...",
  "eventType": "PostCreated",
  "aggregateType": "Post",
  "aggregateId": "123",
  "schemaVersion": 1,
  "aggregateVersion": 1,
  "occurredAt": "...",
  "data": {
    "postId": 123,
    "projectId": 42,
    "authorId": 17,
    "title": "My post"
  }
}
```

And:

```text
Kafka topic
projecthub.events
```

with:

```text
key = aggregateId
```

so events for the same aggregate can maintain partition ordering.

---

# **10. Multiple consumer groups**

This is one of Kafka’s most powerful concepts.

We might have:

```text
projecthub.events
        │
        ├── notifications group
        │
        ├── analytics group
        │
        ├── search group
        │
        └── audit group
```

Each group independently consumes the event stream.

So:

```text
PostCreated
    │
    ├── notification service
    ├── analytics service
    ├── search indexing
    └── audit
```

One event can therefore drive multiple independent business processes.

---

# **11. Consumer idempotency**

Suppose:

```text
eventId = abc123
```

arrives twice.

The consumer checks:

```text
processed_events
```

If:

```text
abc123
```

already exists:

```text
ignore duplicate
```

Otherwise:

```text
BEGIN

business change
+
INSERT processed_events(event_id)

COMMIT
```

The database unique constraint protects against concurrent duplicate processing.

So we have:

```text
Outbox
   ↓
durable event intent

processed_events
   ↓
consumer deduplication
```

Two different problems.

---

# **12. Kafka vs RabbitMQ**

Now our architecture uses both.

That isn’t automatically necessary in every application, but for ProjectHub we’ve given them different jobs.

### **Kafka**

```text
PostCreated
PostUpdated
PostDeleted
ProjectCreated
MemberChanged
```

These are **events**.

They describe something that happened.

### **RabbitMQ**

```text
SendEmail
GenerateReport
GenerateThumbnail
RebuildProjection
```

These are **tasks/commands**.

They tell some worker:

“Please perform this piece of work.”

So:

```text
Kafka
→ event stream

RabbitMQ
→ work distribution
```

---

# **13. What about failures?**

Suppose notification processing fails.

We don’t want:

```text
Kafka
 ↓
consumer
 ↓
failure
 ↓
entire system stops
```

Instead:

```text
Kafka
 ↓
Consumer
 ↓
retry
 ↓
retry
 ↓
still failing
 ↓
DLT
```

The failed event can then be investigated/reprocessed according to the operational policy.

This is separate from the Outbox:

```text
Outbox
→ protects DB → broker publishing

DLT
→ isolates broker → consumer failures
```

That distinction is extremely important.

---

# **14. Database architecture**

PostgreSQL contains our core state:

```text
users
roles
permissions
user_roles
role_permissions

projects
project_members

posts

refresh_tokens

outbox_events
processed_events
```

Potentially:

```text
audit records
```

as well.

The database is where transactional business state lives.

Kafka is **not** a replacement for the transactional database.

---

# **15. Authorization architecture**

Our permission model is:

```text
User
 │
 └── Roles
       │
       └── Permissions
             │
             ├── posts.read
             ├── posts.create
             ├── posts.update
             └── posts.delete
```

But some decisions are more complicated.

For example:

```text
Can user 17 delete post 123?
```

might require:

```text
has posts.delete
AND
user belongs to project
AND
user is allowed to delete this particular post
```

So authorization can be:

```text
Permission
    +
Resource ownership/membership
    +
Business policy
```

That’s why we studied custom authorization rather than stopping at roles.

---

# **16. Authentication architecture**

Our JWT flow looks like:

```text
Login
  ↓
AuthenticationManager
  ↓
verify password
  ↓
issue access token
  +
issue refresh token
```

Then:

```text
Access token
  ↓
API
  ↓
validate token
  ↓
SecurityContext
  ↓
authorities
```

Refresh tokens are handled separately and can be revoked/rotated according to our policy.

Passwords are never stored directly.

---

# **17. Configuration**

The same Docker image can run in:

```text
development
staging
production
```

with different configuration.

Conceptually:

```text
                    Same image
                        │
            ┌───────────┼───────────┐
            ▼           ▼           ▼
          Dev        Staging       Prod
            │           │           │
        config       config       config
```

Kubernetes supplies:

```text
ConfigMap
Secret
```

and Spring Boot binds those values into the application configuration.

So:

**Build once, configure per environment.**

---

# **18. Observability**

Every production component needs visibility.

Our Spring Boot application provides:

```text
logs
metrics
traces
health
```

Spring Boot’s current observability model uses logging, metrics, and traces as the three pillars, with Micrometer Observation providing the metrics/tracing observation API.  

So:

```text
                    ProjectHub
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
        Logs         Metrics      Traces
```

And Kubernetes gets:

```text
liveness
readiness
```

---

# **19. Testing architecture**

Before production:

```text
                 Tests
                   │
       ┌───────────┼───────────┐
       ▼           ▼           ▼
      Unit       Slice      Integration
       │           │           │
       ▼           ▼           ▼
    Mockito    MockMvc     PostgreSQL
                           Kafka
                           RabbitMQ
```

Then:

```text
@SpringBootTest
```

tests the complete application integration.

The goal isn’t to make every test a giant integration test.

Instead:

```text
many cheap tests
+
some realistic integration tests
+
few expensive end-to-end tests
```

---

# **20. CI/CD**

Every change goes through:

```text
Git
 ↓
CI
 ├── compile
 ├── unit tests
 ├── integration tests
 ├── security checks
 └── package
       ↓
Docker image
       ↓
Registry
       ↓
Kubernetes
       ↓
rolling deployment
```

If the new version isn’t healthy:

```text
deployment
   ↓
readiness fails
   ↓
investigate / rollback
```

---

# **21. The entire request lifecycle**

Let’s compress everything into one journey.

A user creates a post:

```text
1. User
   │
   ▼
2. HTTPS
   │
   ▼
3. Gateway
   │
   ▼
4. Kubernetes Service
   │
   ▼
5. Spring Boot Pod
   │
   ▼
6. JWT authentication
   │
   ▼
7. Permission authorization
   │
   ▼
8. Controller
   │
   ▼
9. Service
   │
   ▼
10. PostgreSQL transaction
       │
       ├── Post
       └── Outbox event
             │
             ▼
          COMMIT
             │
             ▼
11. Outbox publisher
             │
             ▼
12. Kafka
             │
       ┌─────┼──────┐
       ▼     ▼      ▼
 Notifications Search Analytics
       │
       ▼
13. External side effects
```

And throughout:

```text
logs
metrics
traces
health checks
```

---

# **22. The architecture in one final diagram**

```text
                              USERS
                                │
                                ▼
                         ┌────────────┐
                         │ DNS / TLS  │
                         └─────┬──────┘
                               │
                               ▼
                      ┌─────────────────┐
                      │ Gateway / LB    │
                      └────────┬────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Kubernetes           │
                    │                      │
                    │ ProjectHub Service   │
                    │          │           │
                    │    ┌─────┼─────┐     │
                    │    ▼     ▼     ▼     │
                    │   API    API   API   │
                    └─────┬─────┬─────┬────┘
                          │     │     │
                          └─────┼─────┘
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                 │
              ▼                 ▼                 ▼
        ┌───────────┐      ┌─────────┐      ┌──────────┐
        │ PostgreSQL│      │  Kafka  │      │ RabbitMQ │
        └─────┬─────┘      └────┬────┘      └────┬─────┘
              │                 │                 │
              │              Consumers          Workers
              │                 │                 │
              ▼                 ▼                 ▼
          ┌────────┐      Notifications      Email
          │ Outbox │      Analytics          Reports
          └────────┘      Search             Tasks
              │            Audit
              │
              ▼
       Outbox Publishers


     ┌─────────────────────────────────────────────┐
     │ Security                                    │
     │ JWT · Permissions · Ownership · CSRF/CORS  │
     ├─────────────────────────────────────────────┤
     │ Configuration                               │
     │ ConfigMap · Secrets · Profiles             │
     ├─────────────────────────────────────────────┤
     │ Observability                               │
     │ Logs · Metrics · Traces · Health            │
     ├─────────────────────────────────────────────┤
     │ Delivery                                    │
     │ Git · CI · Docker · Registry · Kubernetes  │
     └─────────────────────────────────────────────┘
```

---

# **23. What you’ve actually learned**

At the beginning, Spring Boot probably looked like:

```text
@SpringBootApplication
```

and a bunch of annotations.

Now you should see the deeper structure:

```text
Java
 ↓
Spring
 ↓
Spring Boot
 ↓
HTTP / REST
 ↓
PostgreSQL / JPA
 ↓
Transactions
 ↓
Security
 ↓
JWT
 ↓
Authorization
 ↓
Events
 ↓
Outbox
 ↓
Kafka / RabbitMQ
 ↓
Testing
 ↓
Docker
 ↓
Kubernetes
 ↓
Observability
 ↓
CI/CD
```

And, more importantly, you know **why each layer exists**.

---

# **24. The most important principles to keep**

If you forget individual APIs, remember these:

### **1. Keep business logic out of controllers**

```text
Controller → Service → Repository
```

### **2. Transactions protect business state**

```text
business change + outbox event
```

### **3. Don’t trust distributed systems to magically give you exactly-once business effects**

Use:

```text
idempotency
+
unique constraints
+
retries
+
DLTs
```

### **4. Authentication ≠ authorization**

```text
Who are you?
    ≠
What can you do?
```

### **5. Permissions are business concepts**

```text
posts.create
posts.delete
```

are usually easier to reason about than scattering role names everywhere.

### **6. Kafka ordering is partition-level**

```text
same key
→ same partition
→ ordered within that partition
```

not globally ordered.

### **7. Pods are disposable**

Don’t build critical state around one Pod.

### **8. Measure before optimizing**

```text
measure
→ identify bottleneck
→ change
→ measure again
```

### **9. Build once, configure differently**

```text
same artifact
+
different environment configuration
```

### **10. Production systems are designed for failure**

Assume:

```text
Pod crashes
DB becomes slow
Kafka consumer fails
network disappears
deployment goes wrong
messages duplicate
external API times out
```

The architecture should remain understandable and recoverable.

---

# **And that brings us to Lesson 94**

## **Final Review + What to Learn Next**

We’ll do a **compressed technical review of the entire course**:

```text
Java
Spring
REST
JPA
SQL
Transactions
Security
JWT
Authorization
Testing
Kafka
RabbitMQ
Outbox
Docker
Kubernetes
CI/CD
Observability
Performance
```

Then I’ll give you a **realistic next-stage roadmap**: what to build yourself, what skills to practice, and which topics are worth going deeper into versus leaving for later.