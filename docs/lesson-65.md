---
title: Lesson 65: Implementing the Outbox Pattern
sidebar_position: 65
---



Now we actually build the ProjectHub outbox.

We’ll keep the first implementation deliberately understandable rather than jumping straight into a giant production framework.

Our target:

```text
POST /projects/7/posts
        ↓
PostService
        ↓
@Transactional
   ┌────┴────┐
   ↓         ↓
 Post      OutboxEvent
   └────┬────┘
        ↓
      COMMIT
        ↓
 Outbox Publisher
        ↓
    RabbitMQ
```

The current stable Spring Data JPA documentation is 4.1.1, and Spring’s current stable transaction documentation is 7.0.9.  

---

## **1. First: choose our outbox design**

There are two broad designs.

### **Simple**

```text
published_at IS NULL
```

Events are either:

```text
unpublished
published
```

### **More explicit**

```text
PENDING
PROCESSING
PUBLISHED
FAILED
```

For our **first ProjectHub implementation**, I want the simple model:

```text
published_at == null
        ↓
needs publishing

published_at != null
        ↓
published successfully
```

Why?

Because we already get a lot of reliability from:

```text
durable outbox
+
at-least-once publishing
+
idempotent consumers
```

We don’t need to make the first version unnecessarily complicated.

---

# **2. Flyway migration**

Create something like:

```text
V__create_outbox_events.sql
```

with:

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

CREATE INDEX idx_outbox_events_unpublished
    ON outbox_events (id)
    WHERE published_at IS NULL;
```

The partial index is useful because the publisher mostly cares about:

```sql
WHERE published_at IS NULL
```

So we’re indexing the work queue rather than every historical event.

---

# **3. Why keep old events?**

Notice that we aren’t deleting published events.

After:

```text
PostCreated
```

is published, we have:

```text
published_at = 2026-10-01T...
```

The event remains in the database.

That gives us an audit/history trail.

However, in a very high-volume system, keeping every outbox row forever can become expensive.

A production system may eventually archive or delete old published records.

That’s an operational decision—not something we need to solve immediately.

---

# **4. The JPA entity**

Now:

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

    // constructors/getters
}
```

The important thing isn’t the getters/setters.

It’s the model:

```text
OutboxEvent
 ├── identity
 ├── event type
 ├── aggregate
 ├── payload
 ├── creation time
 └── publication state
```

---

# **5. Don’t create relationships to every aggregate**

You might wonder:

Why not do `@ManyToOne Post post`?

Don’t.

An outbox should be relatively generic.

Instead:

```text
aggregateType = "Post"
aggregateId   = "42"
```

This lets the same table contain:

```text
PostCreated
CommentCreated
ProjectMemberAdded
ProjectDeleted
```

without having:

```text
@ManyToOne Post
@ManyToOne Project
@ManyToOne Comment
...
```

That would make the outbox tightly coupled to the entire domain model.

---

# **6. The event itself**

Let’s define:

```java
public record PostCreatedEvent(
        UUID eventId,
        Long postId,
        Long projectId,
        Long authorId
) {
}
```

And perhaps an envelope:

```java
public record EventEnvelope<T>(
        UUID eventId,
        String eventType,
        int version,
        Instant occurredAt,
        T data
) {
}
```

For example:

```json
{
  "eventId": "....",
  "eventType": "PostCreated",
  "version": 1,
  "occurredAt": "2026-10-01T12:00:00Z",
  "data": {
    "postId": 42,
    "projectId": 7,
    "authorId": 15
  }
}
```

This is a much better long-term event contract than dumping a JPA entity into JSON.

---

# **7. Don’t serialize JPA entities directly**

Avoid:

```java
objectMapper.writeValueAsString(post);
```

for your event contract.

Why?

Your entity may contain:

```text
lazy relationships
internal fields
password-related data
implementation details
huge object graphs
```

Instead create an explicit event DTO:

```text
Post
 ↓
PostCreatedEvent
 ↓
JSON
```

The event becomes a stable contract.

---

# **8. Repository**

Start simple:

```java
public interface OutboxEventRepository
        extends JpaRepository<OutboxEvent, Long> {

    List<OutboxEvent> findTop100ByPublishedAtIsNullOrderByIdAsc();
}
```

This gives us:

```text
top 100
unpublished
oldest first
```

It’s a fine starting point.

But there’s a problem.

---

# **9. Multiple Pods**

Imagine:

```text
Pod 1
Pod 2
Pod 3
```

All execute:

```java
findTop100ByPublishedAtIsNullOrderByIdAsc();
```

at approximately the same time.

They can all see:

```text
event 101
event 102
event 103
```

before any of them marks them published.

So:

```text
Pod 1 → event 101
Pod 2 → event 101
```

can happen.

We need coordination.

---

# **10. PostgreSQL gives us a useful tool**

PostgreSQL supports:

```sql
FOR UPDATE SKIP LOCKED
```

`FOR UPDATE` locks selected rows.

`SKIP LOCKED` tells PostgreSQL not to wait for rows another transaction already locked.

PostgreSQL specifically documents this pattern as useful for queue-like tables with multiple consumers.  

So conceptually:

```text
Pod 1
  ↓
locks 101,102,103

Pod 2
  ↓
skips 101,102,103
  ↓
gets 104,105,106
```

---

# **11. Native query**

Spring Data JPA supports locking metadata through `@Lock`.  

But `SKIP LOCKED` is PostgreSQL-specific, so a native query is reasonable here.

For example:

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
List<OutboxEvent> findBatchForUpdate(int limit);
```

However, **don’t implement the publisher by simply keeping this transaction open while publishing to RabbitMQ.**

That’s our next important problem.

---

# **12. The dangerous implementation**

Imagine:

```java
@Transactional
public void publishBatch() {

    List<OutboxEvent> events =
        repository.findBatchForUpdate(100);

    for (OutboxEvent event : events) {
        rabbit.publish(event);
        event.markPublished();
    }
}
```

Looks elegant.

But:

```text
BEGIN
 ↓
lock 100 DB rows
 ↓
RabbitMQ network calls
 ↓
more RabbitMQ calls
 ↓
UPDATE rows
 ↓
COMMIT
```

The database locks remain held during the external network operation.

If RabbitMQ is slow:

```text
DB locks
   ↓
held for seconds
```

That’s bad for throughput.

---

# **13. This is the same lesson as before**

We learned:

Don’t hold database locks while making slow external calls.

This applies here too.

The outbox is not an excuse to ignore transaction boundaries.

---

# **14. Separate claiming from publishing**

A stronger design is:

```text
Transaction 1:
    claim work
        ↓
    COMMIT

Then:

    publish to RabbitMQ

Then:

    mark published
```

Conceptually:

```text
DB
 ↓
claim
 ↓
commit
 ↓
RabbitMQ
 ↓
mark published
```

Now we’re not holding DB locks while talking to RabbitMQ.

But we need a way to represent:

“This event is currently being processed.”

That brings us back to a state column.

---

# **15. Evolve the table**

Let’s add:

```sql
ALTER TABLE outbox_events
ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'PENDING';

ALTER TABLE outbox_events
ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;

ALTER TABLE outbox_events
ADD COLUMN last_attempt_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE outbox_events
ADD COLUMN last_error TEXT;
```

Now:

```text
PENDING
PROCESSING
PUBLISHED
FAILED
```

becomes possible.

---

# **16. Why this is worth it**

Now we can claim:

```text
PENDING
   ↓
PROCESSING
```

and commit that change.

Then:

```text
PROCESSING
```

means:

A worker has claimed this event.

The database lock can be released.

---

# 

# **17. Claiming with**

**`SKIP LOCKED`**

Conceptually:

```sql
WITH next_events AS (
    SELECT id
    FROM outbox_events
    WHERE status = 'PENDING'
    ORDER BY id
    FOR UPDATE SKIP LOCKED
    LIMIT 100
)
UPDATE outbox_events e
SET status = 'PROCESSING',
    attempts = attempts + 1,
    last_attempt_at = now()
FROM next_events n
WHERE e.id = n.id
RETURNING e.*;
```

This does something powerful:

```text
find available work
       ↓
lock it
       ↓
change it to PROCESSING
       ↓
return it
```

inside one database transaction.

---

# **18. Why the transaction is short**

The claim transaction is:

```text
BEGIN
 ↓
select/lock rows
 ↓
update status
 ↓
COMMIT
```

No RabbitMQ call.

Excellent.

Then the locks disappear.

The worker owns the work logically through:

```text
status = PROCESSING
```

rather than through an open DB lock.

---

# **19. Now publish**

After claiming:

```text
event 101 = PROCESSING
```

the worker does:

```text
RabbitMQ publish
```

No database transaction needs to stay open.

That’s much healthier.

---

# **20. Success**

RabbitMQ accepts the event.

Then:

```text
UPDATE outbox_events
SET status = 'PUBLISHED',
    published_at = now()
WHERE id = ?
```

Now:

```text
PENDING
 ↓
PROCESSING
 ↓
PUBLISHED
```

Done.

---

# **21. Failure**

RabbitMQ is unavailable.

We don’t mark it published.

Instead:

```text
PROCESSING
 ↓
failure
```

We can return it to:

```text
PENDING
```

with:

```text
attempts = attempts + 1
last_error = ...
```

Then retry later.

---

# **22. But what if the worker crashes?**

This is the difficult case.

Suppose:

```text
PROCESSING
```

and then:

```text
worker dies
```

Nothing changes the row.

It stays:

```text
PROCESSING
```

forever unless we have recovery.

So we need:

```text
last_attempt_at
```

and a rule like:

```text
PROCESSING
AND
last_attempt_at < now() - 5 minutes
```

means:

The worker probably died; make this event available again.

This is a **lease timeout** concept.

---

# **23. Recovery**

A recovery query could conceptually do:

```sql
UPDATE outbox_events
SET status = 'PENDING'
WHERE status = 'PROCESSING'
  AND last_attempt_at < now() - interval '5 minutes';
```

Then:

```text
worker crashes
     ↓
PROCESSING
     ↓
5 minutes
     ↓
recovery
     ↓
PENDING
     ↓
another worker
```

The exact timeout should be based on your expected processing duration.

---

# **24. Why duplicates are still possible**

Suppose:

```text
PROCESSING
   ↓
RabbitMQ accepts event
   ↓
worker crashes
```

The DB still says:

```text
PROCESSING
```

Recovery eventually changes it to:

```text
PENDING
```

Then another worker publishes it.

So RabbitMQ receives:

```text
event 101
event 101
```

Again.

That’s okay.

We’re deliberately designing for:

```text
at-least-once
```

rather than pretending we have exactly-once delivery.

---

# **25. Consumer idempotency**

The consumer receives:

```text
eventId = 101
```

It needs to safely handle:

```text
101
101
101
```

without performing the business effect three times.

A common technique is:

```sql
CREATE TABLE processed_events (
    event_id UUID PRIMARY KEY,
    processed_at TIMESTAMP WITH TIME ZONE NOT NULL
);
```

Then the unique constraint protects:

```text
event 101 processed once
```

at the database level.

---

# **26. But remember the external-side-effect problem**

Suppose the consumer does:

```text
send email
insert processed_event
```

and crashes between them.

Then:

```text
email = sent
processed_events = missing
```

The event is retried.

Another email may be sent.

So:

**Idempotency must encompass the actual side effect.**

For external APIs, use their idempotency mechanism where available.

For local database state, unique constraints/transactions are extremely useful.

---

# **27. Retry policy**

Let’s say RabbitMQ is down.

We don’t want:

```text
retry immediately
retry immediately
retry immediately
retry immediately
```

Instead:

```text
attempt 1 → 1 second
attempt 2 → 2 seconds
attempt 3 → 4 seconds
attempt 4 → 8 seconds
attempt 5 → 16 seconds
```

with a maximum delay.

This is exponential backoff.

---

# **28. Failed events**

After, say:

```text
10 attempts
```

we might decide:

```text
PENDING
 ↓
...
 ↓
FAILED
```

Then operations can inspect:

```text
failed outbox events
```

and investigate.

Potentially we could later build:

```text
Admin retry event
```

which changes:

```text
FAILED → PENDING
```

---

# **29. Don’t confuse Outbox with DLQ**

They solve related but different problems.

### **Outbox**

Protects:

```text
Database change
+
event publication
```

### **Dead-letter queue**

Typically handles:

```text
message
 ↓
consumer repeatedly fails
 ↓
move message aside
```

So ProjectHub might eventually have:

```text
PostgreSQL outbox
        ↓
RabbitMQ
        ↓
consumer
        ↓
DLQ
```

There can be failure handling on both sides.

---

# **30. The publisher service**

Conceptually:

```java
@Service
public class OutboxPublisher {

    public void publishBatch() {

        List<OutboxEvent> events =
            claimEvents();

        for (OutboxEvent event : events) {
            try {
                publish(event);
                markPublished(event);
            }
            catch (Exception ex) {
                markFailedAttempt(event, ex);
            }
        }
    }
}
```

Notice the architecture:

```text
claimEvents()
```

is transactional.

But:

```text
publish(event)
```

doesn’t hold that transaction open.

That’s deliberate.

---

# **31. Scheduling**

We could periodically invoke:

```java
@Scheduled(fixedDelay = 1000)
public void publish() {
    ...
}
```

Conceptually:

```text
every second
    ↓
claim batch
    ↓
publish
```

But remember our Kubernetes architecture.

If we have:

```text
Pod 1
Pod 2
Pod 3
```

then all three may execute the scheduler.

That’s fine **if the claiming operation is concurrency-safe**.

That’s precisely why we designed:

```text
SKIP LOCKED
+
PROCESSING
```

---

# **32. The important connection**

Our previous lessons now connect:

### **Lesson 60**

Database concurrency.

### **Lesson 61**

JPA pessimistic locking.

### **Lesson 62**

Transaction boundaries.

### **Lesson 63**

Outbox architecture.

### **Lesson 64**

Outbox design.

### **Lesson 65**

Actual concurrency-safe implementation.

This is why learning these topics in sequence matters.

---

# 

# 

# **33. Where**

**`@Lock`**

**fits**

Spring Data JPA’s `@Lock` can attach a JPA `LockModeType` to repository query methods.  

For example:

```java
@Lock(LockModeType.PESSIMISTIC_WRITE)
Optional<Project> findById(Long id);
```

That’s excellent for:

```text
Project membership capacity
```

where we want to lock a specific Project row.

But our outbox worker wants:

```text
FOR UPDATE SKIP LOCKED
```

across a batch of queue rows.

That’s a different problem.

This is a good example of using the right abstraction for the job.

---

# **34. Why not lock the whole outbox?**

Never do:

```sql
LOCK TABLE outbox_events;
```

just because it’s easier.

That would effectively turn:

```text
3 publishers
```

into:

```text
1 publisher at a time
```

and destroy much of the concurrency benefit.

We want fine-grained row-level work claiming.

PostgreSQL’s locking documentation explicitly distinguishes row-level locks and explains `SKIP LOCKED` for queue-like workloads.  

---

# 

# 

# **35. What about**

**`@TransactionalEventListener`**

**?**

We should now clarify exactly where it fits.

For the durable outbox:

```text
Post
+
Outbox
```

should be written in the **same transaction**.

Therefore:

```java
@TransactionalEventListener
```

isn’t required to create the outbox row.

You could use it for:

```text
AFTER_COMMIT
 ↓
trigger some non-critical local action
```

Spring’s transaction-bound event support defaults `@TransactionalEventListener` to `AFTER_COMMIT`.  

But don’t accidentally make:

```text
Post commit
 ↓
AFTER_COMMIT
 ↓
create Outbox row
```

your durable outbox mechanism.

That defeats the main guarantee.

---

# **36. Final ProjectHub flow**

Our production-oriented flow now looks like:

```text
                 HTTP
                  ↓
            Spring Security
                  ↓
             Authorization
                  ↓
             PostService
                  ↓
            @Transactional
              /       \
             /         \
            ↓           ↓
          Post       OutboxEvent
            \           /
             \         /
                COMMIT
                  ↓
            HTTP 201 Created


        ───── asynchronous ─────


             Outbox Worker
                  ↓
          claim PENDING rows
                  ↓
              COMMIT
                  ↓
             PROCESSING
                  ↓
              RabbitMQ
               /     \
              ↓       ↓
       Notification  Analytics
          Worker       Worker
              ↓
        idempotency
```

---

# **37. What I want you to implement**

Don’t implement the entire RabbitMQ system yet.

We’ll do this incrementally.

### **Step 1**

Create:

```text
OutboxEvent
```

with:

```text
id
eventId
eventType
aggregateType
aggregateId
payload
createdAt
status
attempts
lastAttemptAt
lastError
publishedAt
```

### **Step 2**

Create the Flyway migration.

### **Step 3**

Create:

```text
OutboxEventRepository
```

### **Step 4**

Modify:

```text
PostService.createPost()
```

so one transaction writes:

```text
Post
+
OutboxEvent
```

### **Step 5**

Don’t build the publisher yet.

First make sure you understand the database state transitions.

---

# **Exercise 65 — Your turn**

Implement **Steps 1–4 only**.

I want to see:

### **A. Entity**

Your `OutboxEvent` entity.

### **B. Migration**

Your `V__...sql`.

### **C. Repository**

Your `OutboxEventRepository`.

### **D. Post service**

Your `createPost()` transaction that saves:

```text
Post
+
PostCreated outbox event
```

in the same transaction.

### **E. Explain this scenario**

```text
BEGIN
 ↓
INSERT post
 ↓
INSERT outbox
 ↓
exception
 ↓
ROLLBACK
```

What should be present in PostgreSQL afterward?

Then:

```text
BEGIN
 ↓
INSERT post
 ↓
INSERT outbox
 ↓
COMMIT
 ↓
RabbitMQ is completely down
```

What should be present afterward?

---

**Don’t implement** **`FOR UPDATE SKIP LOCKED`** **yet.** Once you send me your entity/migration/repository/service, I’ll review it and then we’ll build the multi-Pod publisher safely.