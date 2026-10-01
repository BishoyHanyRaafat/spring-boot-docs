---
title: Lesson 75: Kafka + Outbox
sidebar_position: 75
---

This is where the pieces finally connect.

We’ve learned:

- PostgreSQL transactions
- Outbox
- Kafka
- consumer groups
- retries
- DLTs
- idempotency
- ordering

Now we’re going to combine them into one reliable pipeline.

The key problem is still the same:

**How do we make a database change and publishing an event reliable when PostgreSQL and Kafka are separate systems?**

---

## **1. The dangerous code**

Imagine we do this:

```java
@Transactional
public void createPost(CreatePostRequest request) {

    Post post = postRepository.save(...);

    kafkaTemplate.send(
        "projecthub.events",
        post.getId().toString(),
        new PostCreatedEvent(...)
    );
}
```

Looks reasonable.

But there are failure windows.

### **Failure A**

```text
PostgreSQL
   ↓
COMMIT
   ↓
Kafka publish
   ↓
💥
```

The post exists.

The event doesn’t.

---

### **Failure B**

```text
Kafka
   ↓
event accepted
   ↓
💥
application crashes
   ↓
DB transaction rolls back
```

Now Kafka has an event for a post that doesn’t exist.

---

# **2. The Outbox solves the database/event boundary**

Instead:

```text
BEGIN

INSERT post

INSERT outbox_event

COMMIT
```

Then:

```text
Outbox Publisher
      ↓
Kafka
```

So the architecture becomes:

```text
                     PostgreSQL
                         │
                ┌────────┴────────┐
                ↓                 ↓
              posts          outbox_events
                │                 │
                └────── COMMIT ──┘
                                  │
                                  ↓
                           Outbox Publisher
                                  │
                                  ↓
                               Kafka
```

The critical property is:

**The post and its intent to publish the event are committed atomically in PostgreSQL.**

The publisher can fail and recover later because the event is still in the outbox.

---

# **3. What changes from our RabbitMQ implementation?**

Very little conceptually.

Previously:

```text
Outbox
   ↓
RabbitTemplate
   ↓
RabbitMQ
```

Now:

```text
Outbox
   ↓
KafkaTemplate
   ↓
Kafka
```

The Outbox pattern isn’t coupled to RabbitMQ.

That’s an important architectural lesson.

---

# **4. Our outbox table**

We’ll continue with something like:

```sql
CREATE TABLE outbox_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE,
    event_type VARCHAR(200) NOT NULL,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(30) NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMP WITH TIME ZONE,
    next_attempt_at TIMESTAMP WITH TIME ZONE,
    last_error TEXT,
    published_at TIMESTAMP WITH TIME ZONE
);
```

The important fields are:

```text
event_id
aggregate_id
payload
status
attempts
```

---

# **5. One database transaction**

Suppose:

```text
POST /posts
```

creates Post 42.

The service performs:

```text
BEGIN

INSERT INTO posts
    id = 42

INSERT INTO outbox_events
    event_id = A
    event_type = PostCreated
    aggregate_id = 42
    payload = {...}
    status = PENDING

COMMIT
```

Now we have:

```text
Post 42 exists
+
PostCreated event is guaranteed to be recorded
```

assuming the transaction committed successfully.

---

# **6. Kafka is deliberately outside that transaction**

Our publisher then finds:

```text
PENDING
```

and claims it:

```text
PENDING
   ↓
PROCESSING
```

Then:

```text
PROCESSING
   ↓
KafkaTemplate
   ↓
Kafka
```

Notice:

**We don’t keep the PostgreSQL transaction open while talking to Kafka.**

This is exactly the principle we learned with RabbitMQ.

---

# **7. Why not hold the DB transaction?**

Imagine:

```text
BEGIN PostgreSQL
   ↓
send Kafka message
   ↓
Kafka takes 2 seconds
   ↓
Kafka takes 10 seconds
   ↓
network timeout
   ↓
ROLLBACK
```

Now your database connection has been occupied throughout the network operation.

With many events:

```text
100 publishers
×
long Kafka calls
```

you can exhaust the connection pool.

So:

```text
DB transaction
    ↓
short
    ↓
claim event

Kafka network operation
    ↓
outside DB transaction
```

is much healthier.

---

# **8. The important failure window**

Now consider:

```text
PROCESSING
   ↓
Kafka accepts event
   ↓
💥 publisher crashes
```

The database still says:

```text
status = PROCESSING
```

while Kafka already has:

```text
PostCreated
```

This is unavoidable in a simple distributed workflow.

We don’t know whether:

```text
Kafka publish succeeded
```

if the process dies before recording the result.

---

# **9. Recovery**

That’s why we introduced:

```text
last_attempt_at
```

and/or a lease timeout.

For example:

```text
PROCESSING
last_attempt_at = 10:00
```

If it’s now:

```text
10:05
```

we can decide:

This processing lease is stale.

Then:

```sql
UPDATE outbox_events
SET status = 'PENDING'
WHERE status = 'PROCESSING'
  AND last_attempt_at <
      CURRENT_TIMESTAMP - INTERVAL '5 minutes';
```

Now another publisher can retry it.

---

# **10. But now we have a duplicate!**

Exactly.

Suppose Kafka accepted:

```text
eventId = A
```

Then our publisher crashed.

Recovery changes:

```text
PROCESSING → PENDING
```

and publishes again.

Kafka now has:

```text
eventId A
eventId A
```

Potentially twice.

This is why the Outbox pattern generally gives us:

**at-least-once publication**

rather than magically giving us exactly-once end-to-end business behavior.

---

# **11. This is where idempotency matters**

Our consumer receives:

```text
eventId = A
```

first time:

```text
process
↓
record eventId
```

Second time:

```text
eventId = A
↓
already processed
↓
skip
```

So the complete system becomes:

```text
Outbox
   ↓
at-least-once publish
   ↓
Kafka
   ↓
at-least-once consumption
   ↓
idempotent consumer
```

This is an extremely common and powerful distributed-systems pattern.

---

# **12. The complete lifecycle**

Let’s visualize one event:

```text
PENDING
   │
   │ claim
   ▼
PROCESSING
   │
   │ publish
   ▼
Kafka accepted
   │
   │ mark success
   ▼
PUBLISHED
```

Failure:

```text
PROCESSING
   │
   │ Kafka failure
   ▼
PENDING
```

Crash after successful Kafka publication:

```text
PROCESSING
   │
   │ Kafka accepted
   │
   X publisher crashes
```

Recovery:

```text
PROCESSING
   ↓
stale lease
   ↓
PENDING
   ↓
publish again
   ↓
duplicate possible
```

Consumer:

```text
eventId A
   ↓
business transaction
   +
processed_events(A)
   ↓
COMMIT
```

Second delivery:

```text
eventId A
   ↓
already processed
   ↓
ignore
```

That’s the whole reliability story.

---

# **13. Kafka producer acknowledgements**

Kafka itself has producer acknowledgement mechanisms.

At a high level, the producer can wait for broker acknowledgement before considering a send successful.

But remember the distinction:

```text
Kafka producer acknowledgement
        ≠
consumer processed event
```

A producer acknowledgement tells us something about Kafka accepting the record.

It does **not** mean:

```text
Notification Service
     ↓
successfully sent email
```

Those are different boundaries.

---

# 

# 

# **14.**

**`KafkaTemplate.send()`**

**is asynchronous**

Spring’s `KafkaTemplate` sends records asynchronously and returns a future-like result that can be used to observe the result of the send.

Conceptually:

```java
CompletableFuture<SendResult<String, Event>> future =
        kafkaTemplate.send(
                "projecthub.events",
                aggregateId,
                event
        );
```

Then you can observe:

```text
success
```

or:

```text
failure
```

Spring Kafka’s current documentation provides `KafkaTemplate` as the main high-level sending abstraction.  

---

# **15. Don’t do this blindly**

You might be tempted to write:

```java
kafkaTemplate.send(...).get();
```

for every event.

That makes the operation synchronous.

Sometimes that’s appropriate.

But if your outbox publisher does:

```text
100 events
↓
send
wait
send
wait
send
wait
```

you’ve unnecessarily serialized your publisher.

Instead, you can design controlled concurrency.

For our learning implementation, however, a simple synchronous confirmation is acceptable initially because **correctness comes before maximum throughput**.

Later we’ll optimize it.

---

# **16. A simple publisher**

Conceptually:

```java
@Component
public class OutboxKafkaPublisher {

    private final KafkaTemplate<String, EventEnvelope<?>> kafkaTemplate;

    public void publish(OutboxEvent event) {

        EventEnvelope<?> envelope =
                deserialize(event.getPayload());

        kafkaTemplate
                .send(
                    "projecthub.events",
                    event.getAggregateId(),
                    envelope
                )
                .whenComplete((result, error) -> {

                    if (error == null) {
                        markPublished(event.getId());
                    } else {
                        markFailed(event.getId(), error);
                    }
                });
    }
}
```

But there’s a major problem here.

Can you see it?

---

# **17. The race**

Suppose:

```text
send()
```

succeeds.

Then:

```text
markPublished()
```

fails.

Now:

```text
Kafka = event exists
DB = event still unpublished
```

The publisher will retry.

Again:

```text
duplicate
```

This is why we don’t try to pretend we have an atomic:

```text
PostgreSQL + Kafka
```

transaction unless we’re deliberately using a transaction model designed for that boundary.

---

# **18. Could Kafka transactions solve this?**

Spring Kafka does support Kafka transactions through `KafkaTransactionManager` and transactional `KafkaTemplate`. Current Spring Kafka documentation also supports transaction synchronization with other transaction managers.  

For example, Kafka can atomically coordinate:

```text
Kafka produce
+
Kafka offset commit
```

for Kafka-centric read → process → write workflows.

Spring’s documentation describes this as exactly-once semantics for a `read → process → write` sequence.  

But don’t jump to:

“Kafka transactions make PostgreSQL + Kafka atomic.”

That’s not the same thing.

---

# **19. Kafka EOS vs our Outbox**

Kafka transactions are excellent for:

```text
Kafka
 ↓
process
 ↓
Kafka
```

For example:

```text
input topic
   ↓
Kafka consumer
   ↓
transform
   ↓
output topic
```

Kafka can transactionally coordinate the output and offset progression.

But our architecture is:

```text
PostgreSQL
     ↓
Kafka
```

The PostgreSQL transaction and Kafka transaction are still two different systems.

The Outbox remains a useful solution for the database-to-event boundary.

---

# **20. This distinction is extremely important**

### **Kafka transaction**

Protects a Kafka-centric workflow:

```text
Kafka input
   ↓
processing
   ↓
Kafka output
+
offset
```

### **Outbox**

Protects:

```text
PostgreSQL business state
+
event intent
```

inside one PostgreSQL transaction.

Different problems.

---

# **21. What about Spring transaction synchronization?**

Spring Kafka can synchronize Kafka operations with other Spring transaction managers. The current documentation describes scenarios where a database transaction and Kafka transaction participate in coordinated transaction synchronization, while also noting the commit-order and failure implications.  

This can be useful in some architectures.

But for **our ProjectHub architecture**, we’re intentionally learning the Outbox pattern first because it makes the distributed failure modes explicit and gives us durable recovery.

Don’t hide the distributed-systems problem behind transaction configuration before understanding it.

---

# **22. Our final ProjectHub architecture**

We now have:

```text
                         HTTP
                          │
                          ▼
                   ProjectHub API
                          │
                          ▼
                   @Transactional
                          │
             ┌────────────┴────────────┐
             ↓                         ↓
        PostgreSQL Post             Outbox Event
             │                         │
             └────────── COMMIT ───────┘
                                       │
                                       ▼
                              Outbox Publisher
                                       │
                             ┌─────────┴─────────┐
                             │                   │
                         success              failure
                             │                   │
                             ▼                   ▼
                           Kafka              retry
                             │
                    projecthub.events
                             │
             ┌───────────────┼───────────────┐
             ↓               ↓               ↓
        notifications     analytics        search
          group             group            group
             │
             ↓
       idempotent consumer
             │
       ┌─────┴─────┐
       ↓           ↓
    success       failure
                    │
             ┌──────┴──────┐
             ↓             ↓
          retry           DLT
```

This is now a real event-driven architecture.

---

# **23. One thing we haven’t solved yet**

There is still a subtle issue:

```text
multiple Outbox publisher Pods
```

Suppose Kubernetes has:

```text
Publisher Pod A
Publisher Pod B
Publisher Pod C
```

all polling:

```text
PENDING
```

We don’t want:

```text
A claims event 42
B claims event 42
C claims event 42
```

So we need our database claiming strategy:

```sql
FOR UPDATE SKIP LOCKED
```

and our:

```text
PENDING → PROCESSING
```

state transition.

We’ve already learned this with RabbitMQ.

The same pattern works with Kafka.

---

# **24. And ordering gets another complication**

Suppose our outbox contains:

```text
id 100 → Post 42 Created
id 101 → Post 42 Updated
id 102 → Post 42 Deleted
```

Multiple publisher Pods may publish concurrently.

Therefore:

```text
outbox ID order
```

doesn’t automatically mean:

```text
Kafka processing order
```

We need:

```text
Kafka key = aggregateId
```

to keep events for the same aggregate associated with the same partition.

And we still need to think carefully about concurrent publishers and event creation order.

---

# **25. Why version numbers still matter**

Our event should carry:

```text
aggregateId
version
```

For example:

```json
{
  "eventId": "...",
  "eventType": "PostUpdated",
  "aggregateType": "Post",
  "aggregateId": "42",
  "version": 17,
  "occurredAt": "...",
  "data": {}
}
```

Now the consumer can reason:

```text
I've processed version 18.

This event is version 17.

→ stale event
```

That’s an additional defense.

Remember:

```text
eventId → duplicate detection

version → ordering/staleness detection
```

Different purposes.

---

# **26. The architecture we’re aiming for**

The mature version looks like:

```text
                    PostgreSQL
                        │
                ┌───────┴────────┐
                │                │
             Domain           Outbox
             tables            events
                │                │
                └────── COMMIT ──┘
                                 │
                         multi-Pod publisher
                                 │
                       claim with SKIP LOCKED
                                 │
                                 ▼
                              Kafka
                                 │
                         key = aggregateId
                                 │
                       ┌─────────┼─────────┐
                       ↓         ↓         ↓
                    Consumer  Consumer  Consumer
                       │
                  idempotency
                       │
                business transaction
                       │
                       ▼
                  processed_events
```

That is a very strong foundation.

---

# **27. Reliability guarantees**

Let’s be precise.

Our architecture aims for:

### **Database consistency**

```text
Post + Outbox
```

committed atomically.

### **Event publication**

```text
at least once
```

### **Kafka consumption**

Potentially:

```text
at least once
```

### **Business processing**

Made effectively idempotent through:

```text
eventId + database uniqueness
```

### **Ordering**

Potentially:

```text
per aggregate
```

when using the aggregate ID as Kafka key and designing the consumer topology appropriately.

### **Failure recovery**

Through:

```text
retry
DLT
outbox recovery
```

That’s a much more useful statement than:

“Our system is exactly once.”

---

# **28. Exercise 75**

This time I want you to reason about the failures.

### **Scenario A**

```text
Post INSERT succeeds
Outbox INSERT succeeds
COMMIT succeeds
Publisher crashes
```

What happens?

---

### **Scenario B**

```text
Publisher claims event
Kafka publish fails
```

What should happen to the outbox row?

---

### **Scenario C**

```text
Kafka accepts event
Publisher crashes
before marking PUBLISHED
```

What happens after recovery?

And most importantly:

**Why can the consumer receive the event twice?**

---

### **Scenario D**

Two publisher Pods run simultaneously.

Why doesn’t:

```text
SELECT ... WHERE status = 'PENDING'
```

by itself safely prevent both Pods from publishing the same row?

What does:

```sql
FOR UPDATE SKIP LOCKED
```

contribute?

---

### **Scenario E**

You receive:

```text
PostUpdated
postId = 42
version = 18
```

and later:

```text
PostUpdated
postId = 42
version = 17
```

What are the two different concepts involved in handling this?

Think:

```text
eventId
version
```

---

# **29. One final challenge**

Draw this architecture yourself:

```text
Post API
   ↓
PostgreSQL
   ↓
Outbox
   ↓
Publisher Pods
   ↓
Kafka
   ↓
Notifications Consumer
   ↓
PostgreSQL
```

Then annotate **every place where a crash can occur**.

For each crash, answer:

```text
Can the event be lost?
Can it be duplicated?
Can it be processed out of order?
How does the system recover?
```

That exercise is much more valuable than memorizing Spring annotations.

Once you’ve got that, **Lesson 76** will be the final reliability layer around this pipeline: **Kafka partitioning + consumer concurrency + ordering + retries together**, including the subtle case where retry topics can change ordering guarantees. Spring’s current documentation explicitly warns that non-blocking retry topics lose the original topic’s ordering guarantees, so we’ll design around that rather than accidentally breaking the ordering model we established earlier.