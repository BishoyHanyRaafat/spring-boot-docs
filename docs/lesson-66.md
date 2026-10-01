---
title: Lesson 66: Building the Multi-Pod Outbox Publisher
sidebar_position: 66
---

Now we tackle the hardest part of the outbox:

**How can multiple ProjectHub Pods safely process the same outbox table without stepping on each other?**

This is where database concurrency, transactions, PostgreSQL locking, and messaging all meet.

PostgreSQL 18 explicitly supports `FOR UPDATE ... SKIP LOCKED` and documents it as useful for queue-like tables with multiple consumers.  

---

## **1. The problem**

Suppose Kubernetes gives us:

```text
             ProjectHub Service
               /      |      \
              ↓       ↓       ↓
           Pod 1    Pod 2    Pod 3
              |       |        |
              +-------+--------+
                      |
                 outbox_events
```

And our table contains:

```text
id   status
101  PENDING
102  PENDING
103  PENDING
104  PENDING
105  PENDING
```

If all three Pods simply execute:

```sql
SELECT *
FROM outbox_events
WHERE status = 'PENDING'
LIMIT 100;
```

they can all see the same rows.

That’s bad.

---

# **2. What we want**

Ideally:

```text
Pod 1 → 101, 102
Pod 2 → 103, 104
Pod 3 → 105
```

without:

```text
Pod 1 → 101
Pod 2 → 101
Pod 3 → 101
```

The database can help coordinate this.

---

# 

# **3.**

**`FOR UPDATE SKIP LOCKED`**

The key SQL is:

```sql
SELECT *
FROM outbox_events
WHERE status = 'PENDING'
ORDER BY id
LIMIT 100
FOR UPDATE SKIP LOCKED;
```

`FOR UPDATE` locks selected rows.

`SKIP LOCKED` means:

If another transaction already has a row locked, don’t wait for it; skip it.

PostgreSQL specifically notes that `SKIP LOCKED` can be useful when multiple consumers access a queue-like table.  

---

# **4. Example**

Suppose Pod 1 starts:

```text
BEGIN

SELECT 101,102
FOR UPDATE SKIP LOCKED
```

Now:

```text
101 🔒
102 🔒
103
104
105
```

Pod 2 starts at the same time:

```text
BEGIN

SELECT ...
FOR UPDATE SKIP LOCKED
```

It skips:

```text
101
102
```

and can take:

```text
103
104
105
```

depending on the limit.

That’s the basic work-distribution mechanism.

---

# **5. But locks aren’t ownership**

Here’s a critical distinction.

A database lock exists only while its transaction exists.

Suppose:

```text
BEGIN
 ↓
lock 101
 ↓
COMMIT
```

After the commit:

```text
101 🔓
```

So we can’t use the lock itself to mean:

“Pod 1 owns this event.”

That’s why we introduced:

```text
status
```

---

# **6. Claim the event**

We want:

```text
PENDING
   ↓
PROCESSING
```

to happen while the row is locked.

Conceptually:

```text
BEGIN
  ↓
find PENDING rows
  ↓
lock rows
  ↓
change them to PROCESSING
  ↓
COMMIT
```

After commit:

```text
101 = PROCESSING
```

The database lock is gone, but the state records that someone claimed it.

---

# **7. The SQL**

PostgreSQL gives us a very useful pattern:

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

Conceptually:

```text
Find work
   ↓
lock work
   ↓
claim work
   ↓
return claimed work
```

all as one database operation.

PostgreSQL’s documentation also demonstrates `FOR UPDATE` inside a CTE combined with an update for batch work, and notes that `SKIP LOCKED` can reduce contention between concurrent workers.  

---

# **8. Why the transaction is short**

Our claim transaction should look like:

```text
BEGIN
 ↓
claim 100 events
 ↓
COMMIT
```

Not:

```text
BEGIN
 ↓
claim 100 events
 ↓
publish to RabbitMQ
 ↓
wait for network
 ↓
publish another
 ↓
...
 ↓
COMMIT
```

The second design holds database locks/resources while communicating with another system.

We don’t want that.

---

# **9. The publisher architecture**

So our worker becomes:

```text
                    ┌───────────────┐
                    │ PostgreSQL    │
                    │               │
                    │ PENDING       │
                    └───────┬───────┘
                            │
                       claim batch
                            │
                            ↓
                    ┌───────────────┐
                    │ PROCESSING    │
                    └───────┬───────┘
                            │
                       COMMIT
                            │
                            ↓
                       RabbitMQ
```

Then:

```text
RabbitMQ success
       ↓
PROCESSING → PUBLISHED
```

or:

```text
RabbitMQ failure
       ↓
PROCESSING → PENDING
```

---

# **10. Repository design**

For the claim operation, I’d deliberately use a native query rather than pretending this is a generic JPA operation.

Something conceptually like:

```java
public interface OutboxEventRepository
        extends JpaRepository<OutboxEvent, Long> {

    @Modifying
    @Query(value = """
        WITH next_events AS (
            SELECT id
            FROM outbox_events
            WHERE status = 'PENDING'
            ORDER BY id
            FOR UPDATE SKIP LOCKED
            LIMIT :limit
        )
        UPDATE outbox_events e
        SET status = 'PROCESSING',
            attempts = attempts + 1,
            last_attempt_at = CURRENT_TIMESTAMP
        FROM next_events n
        WHERE e.id = n.id
        RETURNING e.*
        """,
        nativeQuery = true)
    List<OutboxEvent> claimBatch(int limit);
}
```

However, there is an important JPA detail here:

**`RETURNING`** **plus entity mapping is provider/database specific**, so I don’t want you to blindly copy this exact method into ProjectHub yet.

For this workload, a small custom repository implementation using `EntityManager` or JDBC can be cleaner.

That’s an important engineering lesson:

Don’t force a complicated native database operation through a repository abstraction just because you’re using JPA.

Spring Data JPA’s repository abstraction is designed to reduce data-access boilerplate, but native SQL remains appropriate when you need database-specific behavior.  

---

# **11. A cleaner custom repository**

I’d lean toward:

```java
public interface OutboxClaimRepository {

    List<OutboxEvent> claimBatch(int limit);
}
```

and:

```java
@Repository
public class OutboxClaimRepositoryImpl
        implements OutboxClaimRepository {

    // EntityManager/JdbcTemplate implementation
}
```

Then:

```java
public interface OutboxEventRepository
        extends JpaRepository<OutboxEvent, Long>,
                OutboxClaimRepository {
}
```

Now the responsibilities are clear:

```text
JpaRepository
     ↓
normal CRUD

OutboxClaimRepository
     ↓
PostgreSQL-specific queue claiming
```

That’s a good use of abstraction.

---

# **12. Claim service**

Now:

```java
@Service
public class OutboxClaimService {

    private final OutboxEventRepository repository;

    @Transactional
    public List<OutboxEvent> claimBatch(int limit) {
        return repository.claimBatch(limit);
    }
}
```

The transaction is deliberately tiny:

```text
BEGIN
 ↓
claim
 ↓
COMMIT
```

No RabbitMQ.

No HTTP.

No email.

No Redis.

---

# **13. Publisher**

Then:

```java
@Service
public class OutboxPublisher {

    private final OutboxClaimService claimService;

    public void publishBatch() {

        List<OutboxEvent> events =
            claimService.claimBatch(100);

        for (OutboxEvent event : events) {
            publishOne(event);
        }
    }
}
```

The actual publishing happens outside the claim transaction.

---

# **14. Publishing one event**

Conceptually:

```java
private void publishOne(OutboxEvent event) {
    try {
        rabbitPublisher.publish(event);

        markPublished(event.getId());

    } catch (Exception ex) {

        markFailedAttempt(
            event.getId(),
            ex.getMessage()
        );
    }
}
```

The state machine:

```text
PENDING
   ↓
PROCESSING
   ↓
   ├── success → PUBLISHED
   │
   └── failure → PENDING
```

---

# **15. Marking published**

This operation should be small:

```java
@Transactional
public void markPublished(Long eventId) {
    repository.markPublished(
        eventId,
        Instant.now()
    );
}
```

The SQL is conceptually:

```sql
UPDATE outbox_events
SET status = 'PUBLISHED',
    published_at = CURRENT_TIMESTAMP
WHERE id = ?
  AND status = 'PROCESSING';
```

That last condition is useful:

```sql
AND status = 'PROCESSING'
```

because we’re saying:

Only the worker that currently has this event in the expected state should mark it published.

---

# **16. What if the update affects zero rows?**

Suppose:

```text
Worker A
  ↓
event 101
```

but another recovery process has changed its state.

Then:

```sql
UPDATE ...
WHERE id = 101
AND status = 'PROCESSING'
```

could affect:

```text
0 rows
```

That’s valuable information.

It means:

The state wasn’t what I expected.

In concurrent systems, checking affected-row counts is often an important safety technique.

---

# **17. Failure handling**

Suppose RabbitMQ fails.

We could do:

```sql
UPDATE outbox_events
SET status = 'PENDING',
    last_error = ?,
    last_attempt_at = CURRENT_TIMESTAMP
WHERE id = ?
AND status = 'PROCESSING';
```

Then:

```text
PROCESSING
     ↓
PENDING
```

The event becomes available for another attempt.

---

# **18. But don’t retry instantly**

If our scheduler runs every second:

```text
RabbitMQ down
 ↓
event → PENDING
 ↓
1 second
 ↓
retry
 ↓
failure
 ↓
1 second
 ↓
retry
```

we could hammer RabbitMQ continuously.

Instead, add:

```text
next_attempt_at
```

to the table.

For example:

```sql
ALTER TABLE outbox_events
ADD COLUMN next_attempt_at TIMESTAMP WITH TIME ZONE;
```

Then:

```text
PENDING
+
next_attempt_at <= now()
```

means:

eligible for retry.

---

# **19. Exponential backoff**

For example:

```text
attempt 1 → 1 second
attempt 2 → 2 seconds
attempt 3 → 4 seconds
attempt 4 → 8 seconds
attempt 5 → 16 seconds
```

with a maximum.

The formula isn’t important.

The principle is:

**Give a failing dependency breathing room.**

---

# **20. Recovery of stuck events**

Now consider:

```text
PROCESSING
```

for too long.

Perhaps:

```text
last_attempt_at < now() - 5 minutes
```

Then a recovery job can do:

```sql
UPDATE outbox_events
SET status = 'PENDING'
WHERE status = 'PROCESSING'
  AND last_attempt_at < CURRENT_TIMESTAMP - INTERVAL '5 minutes';
```

Now:

```text
PROCESSING
     ↓
timeout
     ↓
PENDING
```

Another worker can claim it.

---

# **21. Why this doesn’t guarantee exactly once**

Here’s the unavoidable failure window:

```text
PROCESSING
   ↓
RabbitMQ accepts event
   ↓
worker crashes
   ↓
database still says PROCESSING
```

Recovery:

```text
PROCESSING
   ↓
PENDING
```

Then:

```text
publish again
```

RabbitMQ may see:

```text
event 42
event 42
```

So our publisher is **at least once**.

That’s okay.

---

# **22. The consumer is part of the design**

The architecture is not:

```text
Outbox = reliability
```

It’s:

```text
Outbox
   +
at-least-once delivery
   +
idempotent consumer
```

Together they create a robust system.

---

# **23. Consumer idempotency**

Suppose:

```text
NotificationService
```

receives:

```text
eventId = 123
```

We can have:

```sql
CREATE TABLE processed_events (
    event_id UUID PRIMARY KEY,
    processed_at TIMESTAMP WITH TIME ZONE NOT NULL
);
```

Then the consumer transaction can use the unique key to prevent duplicate processing of local database effects.

The database constraint is doing real concurrency work here.

---

# **24. But don’t mark processed too early**

Bad:

```text
INSERT processed_event
     ↓
send email
```

and then:

```text
send email fails
```

Now the system thinks:

```text
event processed
```

when the actual side effect didn’t happen.

Generally the idempotency record should be coordinated with the operation it protects.

For an external side effect, the external system’s own idempotency support can be essential.

---

# **25. Scheduling**

We can periodically trigger the publisher:

```java
@Scheduled(fixedDelay = 1000)
public void publishOutbox() {
    publisher.publishBatch();
}
```

But remember:

```text
Pod 1 → scheduler
Pod 2 → scheduler
Pod 3 → scheduler
```

This is **not a problem** if our claim query is concurrency-safe.

That’s one of the biggest advantages of making the database responsible for work claiming.

---

# **26. Kubernetes connection**

This architecture scales naturally:

```text
3 Pods
 ↓
3 outbox workers
 ↓
PostgreSQL
 ↓
SKIP LOCKED
```

Pod 1 doesn’t need to know Pod 2 exists.

The database coordinates the work.

This is a powerful distributed-systems pattern.

---

# **27. One concern: database load**

There is a tradeoff.

Now every ProjectHub Pod periodically queries:

```text
outbox_events
```

If you have:

```text
100 Pods
```

and every one polls every:

```text
100ms
```

you could create a significant amount of DB traffic.

Therefore production systems tune:

```text
poll interval
batch size
number of workers
connection pool
```

and often use adaptive polling/backoff.

---

# **28. Batch size matters**

Suppose:

```text
batch = 10
```

and there are:

```text
100,000 pending events
```

You need many iterations.

But:

```text
batch = 10,000
```

means:

- larger memory use
- longer processing
- more work held by a worker
- potentially greater recovery cost

So:

```text
batch size
```

is an operational tuning parameter.

Start modestly.

Measure.

Then tune.

---

# **29. Observability**

Now our outbox needs metrics.

I’d expose things such as:

```text
outbox.pending.count
outbox.processing.count
outbox.failed.count
outbox.publish.success
outbox.publish.failure
outbox.publish.duration
outbox.oldest.pending.age
```

Especially:

```text
oldest pending age
```

because it tells us whether events are actually getting stuck.

---

# **30. Example incident**

Suppose:

```text
outbox.pending.count = 50,000
```

That sounds bad.

But if:

```text
oldest.pending.age = 100ms
```

the system might simply be processing a large burst.

Now:

```text
pending = 100
oldest.pending.age = 2 hours
```

is much more concerning.

Metrics need context.

---

# **31. Logging**

When a publish fails, log something like:

```text
eventId=123
eventType=PostCreated
aggregateType=Post
aggregateId=42
attempt=4
error="connection refused"
```

But never log:

```text
password
JWT
refresh token
private key
```

Same security rule we’ve used throughout ProjectHub.

---

# **32. Trace propagation**

Later, when we integrate tracing, an event can carry correlation information.

Conceptually:

```text
HTTP request
 traceId=abc
      ↓
PostService
      ↓
Outbox
      ↓
RabbitMQ
      ↓
Notification Worker
 traceId/event correlation
```

This lets you investigate:

“Why did creating Post 42 take so long to produce its notification?”

That’s one reason observability matters in asynchronous architectures.

---

# **33. One more subtlety: ordering**

Suppose we have:

```text
PostCreated
PostDeleted
```

for the same Post.

We don’t want consumers to receive:

```text
PostDeleted
PostCreated
```

if ordering matters.

Outbox ordering isn’t automatically equivalent to global distributed ordering.

You need to decide what ordering guarantees the consumer actually requires.

Possible strategies include:

```text
same aggregate → same partition/key
```

when using a broker that supports partition-based ordering.

Don’t assume:

```text
id=101
id=102
```

automatically means every consumer sees them in that order.

---

# **34. Event ordering and retries**

Imagine:

```text
PostCreated
PostDeleted
```

Publisher sends:

```text
PostCreated → RabbitMQ
```

but it is delayed.

Then:

```text
PostDeleted → RabbitMQ
```

arrives first.

If the consumer requires strict ordering, this can cause problems.

So event-driven systems need an explicit answer to:

**What ordering guarantees does this business operation require?**

Sometimes:

```text
No ordering requirement
```

is perfectly fine.

Sometimes it isn’t.

---

# **35. The implementation we want**

For ProjectHub, our first serious design is:

```text
OutboxEvent
   |
   +-- PENDING
   +-- PROCESSING
   +-- PUBLISHED
   +-- FAILED
```

with:

```text
attempts
lastAttemptAt
nextAttemptAt
lastError
publishedAt
```

Then:

```text
@Transactional
claimBatch()
       ↓
FOR UPDATE SKIP LOCKED
       ↓
PENDING → PROCESSING
       ↓
COMMIT
       ↓
RabbitMQ
       ↓
success → PUBLISHED
failure → PENDING / FAILED
```

And:

```text
stuck PROCESSING
       ↓
recovery
       ↓
PENDING
```

---

# **36. One correction to our earlier simplified design**

Earlier we discussed a simple:

```text
published_at IS NULL
```

outbox.

That’s excellent for learning the core pattern.

But once we introduce:

```text
multiple Pods
claiming
recovery
backoff
```

a richer state model becomes much easier to operate safely.

That’s why production architecture often evolves:

```text
simple durable queue
       ↓
concurrency requirements
       ↓
explicit state machine
```

The important lesson is **not** that every outbox needs every column.

It’s:

Add complexity when a real failure mode requires it.

---

# **37. Your ProjectHub architecture now**

```text
                        Internet
                           ↓
                        Gateway
                           ↓
                    ProjectHub Service
                           ↓
                    ┌──────┴──────┐
                    ↓             ↓
                  Pod 1         Pod 2 ... Pod N
                    │             │
                    └──────┬──────┘
                           ↓
                      PostgreSQL
                     /           \
                business data    outbox
                                  |
                            SKIP LOCKED
                                  |
                             Publishers
                                  |
                              RabbitMQ
                             /       \
                            ↓         ↓
                     Notification  Analytics
                        Worker       Worker
```

And surrounding the whole thing:

```text
Metrics
Logs
Traces
Alerts
```

---

# **38. What you’ve learned**

At this point you should understand why these seemingly unrelated concepts connect:

```text
JPA
 ↓
Transactions
 ↓
PostgreSQL locks
 ↓
Concurrent workers
 ↓
Outbox
 ↓
RabbitMQ
 ↓
Idempotency
 ↓
Kubernetes scaling
 ↓
Observability
```

This is the point where backend engineering becomes less about memorizing annotations and more about understanding **failure and consistency**.

---

# **Exercise 66**

This time, I want you to reason about the actual implementation.

### **1. Explain this SQL**

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
    last_attempt_at = CURRENT_TIMESTAMP
FROM next_events n
WHERE e.id = n.id
RETURNING e.*;
```

Explain each part in plain English.

---

### **2. Two Pods**

Start with:

```text
101 PENDING
102 PENDING
103 PENDING
104 PENDING
```

Pod A claims 101 and 102.

At almost exactly the same time, Pod B claims a batch.

What should Pod B receive?

Why?

---

### **3. Crash**

Explain this sequence:

```text
PENDING
 ↓
PROCESSING
 ↓
RabbitMQ accepts message
 ↓
Pod crashes
```

What state is the database in?

What happens during recovery?

Why can the event be published twice?

---

### **4. Retry**

Design a retry strategy with:

```text
attempts
nextAttemptAt
lastError
```

For example, what happens after:

```text
attempt 1
attempt 2
attempt 3
```

and when should an event become `FAILED`?

---

### **5. Transaction boundaries**

Identify which of these should be transactional:

```text
A. claim outbox events
B. publish to RabbitMQ
C. mark event PUBLISHED
D. recover stale PROCESSING events
```

There may be more than one valid design; explain your reasoning.

---

### **6. Multi-Pod design**

Suppose ProjectHub scales from:

```text
3 Pods → 30 Pods
```

What prevents all 30 publishers from processing the same outbox row?

What new problems might appear at 30 Pods?

Think about:

```text
database load
connection pool
polling frequency
RabbitMQ capacity
batch size
```

---

### **7. Hardest question**

Why is this potentially dangerous?

```java
@Transactional
public void publishBatch() {

    List<OutboxEvent> events =
        repository.claimBatch();

    for (OutboxEvent event : events) {
        rabbitPublisher.publish(event);
    }

    markPublished(events);
}
```

Even though the code looks wonderfully simple, explain why holding the transaction open while publishing to RabbitMQ can become a production problem.

---

**Next: Lesson 67 — RabbitMQ in ProjectHub: exchanges, queues, routing keys, acknowledgments, retries, dead-letter queues, consumer concurrency, and how the outbox publisher actually hands events to RabbitMQ.**