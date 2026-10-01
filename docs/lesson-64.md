---
title: Lesson 64: Building the Outbox in ProjectHub
sidebar_position: 64
---



Now we’re going from architecture to implementation.

The goal is to build this:

```text
POST /projects/7/posts
        ↓
PostService
        ↓
@Transactional
   ┌────┴────┐
   ↓         ↓
 Post     OutboxEvent
   └────┬────┘
        ↓
      COMMIT
        ↓
 Outbox Publisher
        ↓
    RabbitMQ
        ↓
 Consumers
```

The current stable Spring Data JPA line is 4.1.1, and its `@Lock` support allows repository query methods to specify a JPA lock mode. PostgreSQL 18 supports `FOR UPDATE ... SKIP LOCKED`, specifically useful for queue-like tables with multiple consumers.  

---

## **1. Start with the database**

Our outbox is just another table.

A useful first version:

```sql
CREATE TABLE outbox_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    event_id UUID NOT NULL UNIQUE,

    event_type VARCHAR(200) NOT NULL,

    aggregate_type VARCHAR(100) NOT NULL,

    aggregate_id VARCHAR(100) NOT NULL,

    payload JSONB NOT NULL,

    created_at TIMESTAMP WITH TIME ZONE NOT NULL,

    published_at TIMESTAMP WITH TIME ZONE
);
```

Think about each column:

|**Column**|**Purpose**|
|---|---|
|`id`|Database ordering/internal identifier|
|`event_id`|Globally unique event identity|
|`event_type`|`PostCreated`, `ProjectMemberAdded`, etc.|
|`aggregate_type`|`Post`, `Project`, etc.|
|`aggregate_id`|Which business object changed|
|`payload`|Event data|
|`created_at`|When event was created|
|`published_at`|`NULL` until successfully published|

The important state is:

```text
published_at IS NULL
```

meaning:

This event still needs publishing.

---

# 

# 

# **2. Why**

**`event_id`**

**needs a unique constraint**

Suppose a bug causes:

```text
event_id = abc123
```

to be inserted twice.

We don’t want that.

So:

```sql
event_id UUID NOT NULL UNIQUE
```

gives the database an invariant:

```text
one event ID
      ↓
one outbox record
```

This is another example of something we’ve repeatedly learned:

**Application code should enforce business rules, but the database should enforce important invariants too.**

---

# **3. JPA entity**

We can map it:

```java
@Entity
@Table(name = "outbox_events")
public class OutboxEvent {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private UUID eventId;

    @Column(nullable = false, length = 200)
    private String eventType;

    @Column(nullable = false, length = 100)
    private String aggregateType;

    @Column(nullable = false, length = 100)
    private String aggregateId;

    @Column(nullable = false, columnDefinition = "jsonb")
    private String payload;

    @Column(nullable = false)
    private Instant createdAt;

    private Instant publishedAt;
}
```

For now, notice that I’m using:

```java
String payload
```

rather than immediately introducing a sophisticated JSON mapping strategy.

That’s intentional.

We want to understand the architecture before adding infrastructure complexity.

---

# **4. Repository**

Initially:

```java
public interface OutboxEventRepository
        extends JpaRepository<OutboxEvent, Long> {

}
```

That’s enough to persist events.

Later we’ll add a query specifically for unpublished events.

---

# **5. The most important part: the service transaction**

Our post creation becomes:

```java
@Transactional
public Post createPost(...) {

    Post post = postRepository.save(...);

    OutboxEvent event =
        outboxEventFactory.postCreated(post);

    outboxEventRepository.save(event);

    return post;
}
```

The transaction contains:

```text
BEGIN
  |
  +-- INSERT post
  |
  +-- INSERT outbox event
  |
COMMIT
```

This is the heart of the pattern.

Spring’s transaction abstraction coordinates the database work within the transaction boundary.  

---

# **6. Why this is different from publishing RabbitMQ here**

We deliberately **don’t** do:

```java
postRepository.save(post);

rabbitTemplate.convertAndSend(...);

outboxEventRepository.save(event);
```

Instead:

```text
Post
 +
Outbox
 ↓
COMMIT
 ↓
Publisher
```

The transaction owns the durable database state.

The publisher handles communication with the outside world later.

---

# **7. Build the event**

Let’s define our event:

```java
public record PostCreatedEvent(
        UUID eventId,
        Long postId,
        Long projectId,
        Long authorId
) {
}
```

The event ID is generated once:

```java
UUID eventId = UUID.randomUUID();
```

Then we serialize the event into JSON for the outbox payload.

Conceptually:

```text
Java event
    ↓
JSON
    ↓
outbox_events.payload
```

For example:

```json
{
  "eventId": "....",
  "postId": 42,
  "projectId": 7,
  "authorId": 15
}
```

---

# **8. Don’t put everything in the event**

You might be tempted to do:

```json
{
  "postId": 42,
  "title": "...",
  "content": "...",
  "authorPassword": "...",
  "jwt": "...",
  "entireProject": "..."
}
```

Don’t.

Events should contain the information consumers actually need.

For example:

```json
{
  "eventId": "...",
  "eventType": "PostCreated",
  "version": 1,
  "postId": 42,
  "projectId": 7,
  "authorId": 15
}
```

Especially:

**never put passwords, access tokens, refresh tokens, or other secrets into events.**

---

# **9. Now the publisher**

We need something that periodically asks:

“Which events haven’t been published?”

Conceptually:

```text
OutboxPublisher
      ↓
SELECT unpublished events
      ↓
publish
      ↓
mark published
```

The simplest query is:

```sql
SELECT *
FROM outbox_events
WHERE published_at IS NULL
ORDER BY id
LIMIT 100;
```

But there is a problem.

---

# **10. Multiple ProjectHub Pods**

Remember Kubernetes:

```text
        Service
       /   |   \
      ↓    ↓    ↓
   Pod 1 Pod 2 Pod 3
```

If every Pod runs the publisher:

```text
Pod 1 → publisher
Pod 2 → publisher
Pod 3 → publisher
```

they could all select the same event.

For example:

```text
Pod 1 → event 42
Pod 2 → event 42
```

Both might publish it.

---

# 

# **11.**

**`FOR UPDATE SKIP LOCKED`**

PostgreSQL gives us a useful mechanism:

```sql
SELECT *
FROM outbox_events
WHERE published_at IS NULL
ORDER BY id
LIMIT 100
FOR UPDATE SKIP LOCKED;
```

`FOR UPDATE` locks selected rows.

`SKIP LOCKED` tells PostgreSQL:

If another worker already locked a row, skip it instead of waiting.

PostgreSQL explicitly documents `SKIP LOCKED` as useful for queue-like tables accessed by multiple consumers.  

So:

```text
Pod 1 locks:
42, 43, 44

Pod 2:
skips 42,43,44
gets 45,46,47
```

This is exactly the kind of concurrency problem we studied earlier.

---

# **12. But here’s a very important distinction**

`SKIP LOCKED` helps us **claim work**.

It does **not** magically guarantee exactly-once message delivery.

You can still have:

```text
lock event
   ↓
publish RabbitMQ
   ↓
RabbitMQ accepts
   ↓
application crashes
   ↓
database transaction never marks event published
```

When the event becomes available again:

```text
publish again
```

Therefore:

```text
SKIP LOCKED
+
idempotent consumers
```

is the important combination.

---

# **13. Why the transaction around publishing is tricky**

Imagine:

```text
BEGIN
 ↓
SELECT ... FOR UPDATE SKIP LOCKED
 ↓
publish RabbitMQ
 ↓
UPDATE published_at
 ↓
COMMIT
```

This means the database row remains locked while you’re communicating with RabbitMQ.

That’s potentially undesirable because network calls can be slow.

You don’t want:

```text
DB lock
    ↓
waiting 2 seconds for RabbitMQ
```

especially at high volume.

This is one of the places where production outbox implementations require careful design.

---

# **14. Claiming vs publishing**

A more scalable architecture often separates:

```text
1. Claim event
2. Publish event
3. Mark published
```

For example, the table can have a state:

```text
PENDING
PROCESSING
PUBLISHED
FAILED
```

Then workers atomically claim events.

But now we introduce another problem:

What happens if a worker claims an event and dies?

The event could remain:

```text
PROCESSING
```

forever.

So we need recovery.

---

# **15. Add retry metadata**

A more realistic table might contain:

```sql
attempts INTEGER NOT NULL DEFAULT 0,

last_attempt_at TIMESTAMP WITH TIME ZONE,

published_at TIMESTAMP WITH TIME ZONE,

failed_at TIMESTAMP WITH TIME ZONE,

last_error TEXT
```

Now we can understand event state.

For example:

```text
PENDING
   ↓
PROCESSING
   ↓
PUBLISHED
```

or:

```text
PENDING
   ↓
PROCESSING
   ↓
failure
   ↓
PENDING
   ↓
retry
```

Eventually:

```text
too many failures
   ↓
FAILED
```

---

# **16. Don’t retry forever**

Suppose RabbitMQ is permanently misconfigured.

Without limits:

```text
event
 ↓
retry
 ↓
retry
 ↓
retry
 ↓
retry
 ↓
retry
...
```

You can create a retry storm.

Instead:

```text
attempt 1
attempt 2
attempt 3
...
attempt 10
     ↓
FAILED / DLQ workflow
```

The exact policy depends on the system.

---

# **17. Exponential backoff**

Instead of:

```text
retry every 1 second
```

you might use:

```text
1s
2s
4s
8s
16s
...
```

with a maximum delay.

Why?

If RabbitMQ is down:

```text
100 workers
×
retry every second
```

can hammer an already unhealthy system.

Backoff gives the dependency time to recover.

---

# **18. Outbox state machine**

A useful mental model:

```text
             success
PENDING ----------------> PUBLISHED
   |
   | processing
   v
PROCESSING
   |
   | failure
   v
PENDING
   |
   | too many failures
   v
FAILED
```

Notice:

```text
PUBLISHED
```

is terminal.

```text
FAILED
```

may also be terminal until an operator/recovery process intervenes.

---

# 

# 

# **19. Do we actually need**

**`PROCESSING`**

**?**

Not necessarily.

A simpler design can use:

```text
published_at IS NULL
```

and tolerate duplicates.

That’s often attractive because:

```text
simple publisher
+
at-least-once
+
idempotent consumers
```

is easier to reason about.

Don’t add a state machine unless the operational requirements justify it.

---

# **20. Spring Data JPA locking**

Spring Data JPA supports:

```java
@Lock(LockModeType.PESSIMISTIC_WRITE)
```

on repository query methods.  

For our outbox, however, we’re reaching for PostgreSQL-specific:

```sql
FOR UPDATE SKIP LOCKED
```

because `SKIP LOCKED` is particularly useful for this queue-like workload.

This is a good example of a principle we’ve already learned:

JPA is useful, but sometimes the database’s native capabilities are exactly what the workload requires.

---

# **21. Native query**

A repository might eventually have something like:

```java
@Query(value = """
    SELECT *
    FROM outbox_events
    WHERE published_at IS NULL
    ORDER BY id
    LIMIT :limit
    FOR UPDATE SKIP LOCKED
    """,
    nativeQuery = true)
List<OutboxEvent> claimBatch(int limit);
```

But don’t rush to copy this into ProjectHub yet.

There are transaction and claiming semantics we need to design first.

---

# **22. The important transaction boundary**

If we use:

```text
SELECT ... FOR UPDATE SKIP LOCKED
```

the lock exists within the database transaction.

PostgreSQL’s row locks are held until the transaction ends.  

So:

```text
@Transactional
claimBatch()
```

might:

```text
BEGIN
 ↓
lock rows
 ↓
return rows
 ↓
COMMIT
```

At that point the locks disappear.

Therefore, the application needs a strategy for ensuring another worker doesn’t immediately claim the same events.

That’s why real outbox implementations often use explicit claiming/state transitions rather than simply locking and returning entities.

---

# **23. A practical claim design**

We could atomically change:

```text
PENDING
```

to:

```text
PROCESSING
```

inside the transaction.

Conceptually:

```sql
UPDATE outbox_events
SET status = 'PROCESSING',
    attempts = attempts + 1,
    last_attempt_at = now()
WHERE id IN (
    SELECT id
    FROM outbox_events
    WHERE status = 'PENDING'
    ORDER BY id
    FOR UPDATE SKIP LOCKED
    LIMIT 100
)
RETURNING *;
```

Now the transaction:

```text
BEGIN
 ↓
claim rows
 ↓
COMMIT
```

After commit:

```text
event = PROCESSING
```

The DB lock is gone, but ownership is represented by the state.

---

# **24. What if the worker crashes?**

Suppose:

```text
event = PROCESSING
```

Then:

```text
worker crashes
```

We need a recovery rule such as:

```text
PROCESSING
AND last_attempt_at < now() - timeout
```

becomes claimable again.

For example:

```text
PROCESSING for > 5 minutes
        ↓
assume worker died
        ↓
return to PENDING
```

This is called a lease/timeout-style approach.

The exact design depends on your reliability requirements.

---

# **25. This is distributed systems thinking**

Notice what’s happening.

We started with:

```text
"Save an event."
```

Now we’re discussing:

```text
concurrency
leases
crashes
retries
duplicate delivery
backoff
dead letters
idempotency
```

That’s because reliability isn’t achieved by one annotation.

It’s achieved by designing for failure.

---

# **26. Consumer side**

Now imagine RabbitMQ delivers:

```text
PostCreatedEvent
```

Our notification service receives it.

It should not simply do:

```java
sendEmail();
```

It should have an idempotency strategy.

For example:

```text
BEGIN
 ↓
record event as processed
 ↓
perform local DB operation
 ↓
COMMIT
```

But remember our earlier warning:

If the side effect is an external email API:

```text
DB
+
external email service
```

there can still be a dual-write problem.

So idempotency must extend to the external operation too.

---

# **27. A good idempotency key**

Suppose:

```text
eventId = 123
```

We can use:

```text
Idempotency-Key: 123
```

when calling an external service that supports idempotency keys.

Then:

```text
attempt 1 → key 123
attempt 2 → key 123
attempt 3 → key 123
```

The external system can recognize them as the same logical operation.

This is much safer than hoping retries won’t duplicate side effects.

---

# **28. What happens when RabbitMQ is down?**

Our desired behavior:

```text
Post creation
     ↓
DB + Outbox commit
     ↓
HTTP 201
```

The user shouldn’t necessarily receive:

```text
500 RabbitMQ unavailable
```

because the post itself succeeded.

Instead:

```text
Post = committed
Event = durable
Notification = pending
```

Later:

```text
RabbitMQ recovers
      ↓
publisher retries
      ↓
notification eventually happens
```

That’s eventual consistency in action.

---

# **29. But what if notification is mandatory?**

This is an important architectural question.

If the requirement is:

“The post must not be considered successful unless the email has been delivered.”

then asynchronous outbox processing may not satisfy that business requirement.

You need to define what success means.

For many systems:

```text
POST /posts
```

means:

“The post was successfully persisted.”

It does **not** mean:

“Every downstream system has finished processing all consequences.”

That distinction should be explicit.

---

# **30. Observability for our outbox**

Now add metrics.

I’d want:

```text
outbox.pending
outbox.processing
outbox.failed
outbox.publish.success
outbox.publish.failure
outbox.publish.duration
outbox.oldest.pending.age
```

Especially:

```text
oldest pending event age
```

because:

```text
pending = 5
```

doesn’t necessarily mean healthy.

If those five events have been waiting:

```text
2 hours
```

that’s very different from:

```text
50 milliseconds
```

---

# **31. Alerts**

A useful alert might be:

```text
oldest pending outbox event > 5 minutes
```

rather than:

```text
outbox has 100 events
```

because queue size alone isn’t always meaningful.

Again, this connects directly to our observability lessons.

---

# **32. ProjectHub’s evolving architecture**

We’re now at:

```text
                         Internet
                            ↓
                         Gateway
                            ↓
                         Service
                            ↓
                      ProjectHub Pods
                       /           \
                      /             \
             PostgreSQL           Redis
                |
          ┌─────┴─────┐
          |           |
        tables      outbox
                      |
                      ↓
              Outbox Publishers
                      |
                      ↓
                   RabbitMQ
                   /      \
                  /        \
                 ↓          ↓
          Notification   Analytics
             Worker        Worker
```

And around everything:

```text
Metrics
Logs
Traces
Alerts
```

---

# **33. One important design decision**

For ProjectHub, I want you to adopt this rule:

### **Synchronous**

Use synchronous processing for things required to determine whether the current request succeeds:

```text
authentication
authorization
ownership
membership
database invariants
```

### **Asynchronous**

Use asynchronous processing for independent consequences:

```text
notifications
analytics
search indexing
activity feeds
cache invalidation
webhooks
```

This isn’t an absolute law, but it’s a very useful architectural default.

---

# **34. Our final design**

For:

```http
POST /projects/7/posts
```

the implementation should conceptually be:

```text
Request
  ↓
Authenticate Alice
  ↓
Check posts.create
  ↓
Check Project 7 membership
  ↓
BEGIN TRANSACTION
  ↓
INSERT post
  ↓
INSERT PostCreated outbox event
  ↓
COMMIT
  ↓
HTTP 201
```

Then independently:

```text
Outbox Publisher
  ↓
claim event
  ↓
RabbitMQ
  ↓
Notification consumer
  ↓
idempotent processing
```

That’s the architecture I want you to understand before we write the production implementation.

---

# **Exercise 64**

Don’t code yet. **Design it first.**

### **1. Outbox entity**

Design the Java fields for:

```text
OutboxEvent
```

Include at least:

- database ID
- event ID
- event type
- aggregate type
- aggregate ID
- payload
- created timestamp
- published timestamp

Then decide whether you want:

```text
PENDING / PROCESSING / PUBLISHED / FAILED
```

or the simpler:

```text
published_at == null
```

model.

Explain your choice.

---

### **2. Post transaction**

Write the pseudocode for:

```text
createPost()
```

It must guarantee:

```text
Post saved
+
Outbox event saved
```

in the **same transaction**.

---

### **3. Multiple Pods**

Suppose:

```text
Pod 1 → publisher
Pod 2 → publisher
Pod 3 → publisher
```

Why can a simple:

```sql
SELECT *
FROM outbox_events
WHERE published_at IS NULL
LIMIT 100;
```

cause duplicate publication?

Then explain how:

```sql
FOR UPDATE SKIP LOCKED
```

helps.

---

### **4. Crash scenario**

Explain what happens here:

```text
Worker claims event
       ↓
publishes to RabbitMQ
       ↓
RabbitMQ accepts it
       ↓
Worker crashes
       ↓
published_at never updated
```

What happens next?

Why must the consumer be idempotent?

---

### **5. Recovery**

If you choose:

```text
PENDING
PROCESSING
PUBLISHED
FAILED
```

design a rule for recovering:

```text
PROCESSING
```

events after a worker crashes.

---

### **6. ProjectHub architecture**

Draw the full flow for:

```text
Alice creates Post 42
```

including:

```text
Spring Security
authorization
transaction
Post
Outbox
PostgreSQL
publisher
RabbitMQ
notification consumer
idempotency
```

---

### **7. The hardest question**

Why is this statement true?

**The Outbox Pattern does not give us exactly-once delivery. It gives us a durable path toward at-least-once delivery, after which idempotent consumers make repeated delivery safe.**

Explain that in your own words.

Once you’ve answered those, **Lesson 65** will be the implementation: we’ll build the actual `OutboxEvent` JPA entity + Flyway migration + publisher design and work through the concurrency details rather than just copying a finished implementation.