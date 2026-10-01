---
title: "Lesson 63: Transactions + Events + Outbox"
sidebar_position: 63
---

Now we’re going to connect several major pieces of ProjectHub:

```text
Transactions
      ↓
Domain events
      ↓
Outbox
      ↓
RabbitMQ
      ↓
Reliable asynchronous processing
```

This is where the backend starts looking like a real production system.

We’re using the current Spring Boot 4.1.1 / Spring Framework 7.0.x documentation as the API baseline.  

---

# **1. The problem we’re solving**

Suppose ProjectHub creates a post:

```text
POST /projects/7/posts
```

We want:

```text
1. Save Post
2. Notify subscribers
3. Send analytics event
4. Maybe send notification email
```

The naive approach is:

```java
@Transactional
public void createPost(...) {

    postRepository.save(post);

    rabbitTemplate.convertAndSend(...);

    emailService.send(...);
}
```

This looks reasonable.

It isn’t.

---

# **2. Why it’s dangerous**

Imagine:

```text
DB INSERT
    ↓
success
    ↓
RabbitMQ publish
    ↓
failure
```

Now:

```text
Post exists
RabbitMQ event doesn't
```

ProjectHub has inconsistent state.

Or:

```text
RabbitMQ publish
    ↓
success
    ↓
DB COMMIT
    ↓
failure
```

Now the message says:

```text
"Post created"
```

but the database says:

```text
post doesn't exist
```

We have a **dual-write problem**.

---

# **3. What is a dual write?**

You’re changing two independent systems:

```text
PostgreSQL
     +
RabbitMQ
```

There isn’t automatically one atomic transaction covering both.

So:

```text
DB success + MQ failure
```

and:

```text
MQ success + DB failure
```

are possible.

That’s why we need a better architecture.

---

# **4. First concept: application events**

Spring provides an application event mechanism.

Conceptually:

```java
applicationEventPublisher.publishEvent(
    new PostCreatedEvent(postId)
);
```

This means:

“Something happened inside the application.”

For example:

```java
public record PostCreatedEvent(
    Long postId,
    Long projectId,
    Long authorId
) {}
```

Then another component can listen.

---

# 

# **5. Regular**

**`@EventListener`**

You could write:

```java
@EventListener
public void handle(PostCreatedEvent event) {
    // ...
}
```

But there’s a problem.

A regular event listener isn’t automatically saying:

“Only run this after the database transaction successfully commits.”

That’s exactly the guarantee we sometimes need.

Spring provides `@TransactionalEventListener` specifically for transaction-bound events. Its default phase is `AFTER_COMMIT`.  

---

# 

# **6.**

**`@TransactionalEventListener`**

Now:

```java
@Component
public class PostEventHandler {

    @TransactionalEventListener
    public void handle(PostCreatedEvent event) {
        // ...
    }
}
```

The default behavior is:

```text
publish event
      ↓
transaction continues
      ↓
COMMIT
      ↓
listener executes
```

If the transaction rolls back:

```text
publish event
      ↓
ROLLBACK
      ↓
AFTER_COMMIT listener does not execute
```

That’s extremely useful.

Spring supports these phases:

```text
BEFORE_COMMIT
AFTER_COMMIT
AFTER_ROLLBACK
AFTER_COMPLETION
```

with `AFTER_COMMIT` as the default.  

---

# **7. This solves one problem**

Consider:

```text
@Transactional
createPost()
      |
      +-- save Post
      |
      +-- publish PostCreatedEvent
      |
      +-- COMMIT
                |
                v
        @TransactionalEventListener
```

Now the listener won’t run for a transaction that ultimately rolls back.

That’s better.

But…

---

# **8. It still isn’t the Outbox Pattern**

Suppose:

```text
DB transaction commits
      ↓
AFTER_COMMIT listener starts
      ↓
RabbitMQ publish
      ↓
RabbitMQ is unavailable
```

The database transaction already committed.

Your event listener failed.

Where is the event?

Gone.

So:

```text
@TransactionalEventListener
```

is useful, but **it is not a durable message guarantee**.

That’s an important distinction.

---

# **9. Enter the Outbox Pattern**

The Outbox Pattern changes the architecture.

Instead of:

```text
DB
 +
RabbitMQ
```

we do:

```text
DB transaction
       |
       +-- Post
       |
       +-- OutboxEvent
       |
      COMMIT
       |
       v
Outbox publisher
       |
       v
RabbitMQ
```

The critical insight is:

**The business change and the event record are stored in the same database transaction.**

---

# **10. The outbox table**

For ProjectHub:

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

The exact schema can evolve, but conceptually we need:

```text
event ID
event type
what entity it concerns
payload
when created
whether published
```

---

# **11. The important transaction**

Creating a post becomes:

```text
BEGIN
  |
  +-- INSERT post
  |
  +-- INSERT outbox event
  |
COMMIT
```

Now either:

```text
Post + event
```

both exist.

Or:

```text
neither exists
```

That’s the key guarantee.

---

# **12. Why this is powerful**

Suppose PostgreSQL crashes immediately after commit.

When it comes back:

```text
posts
   ↓
post exists

outbox_events
   ↓
event exists
```

The event hasn’t disappeared.

The publisher can continue from the outbox.

That’s fundamentally different from:

```text
DB commit
 ↓
RabbitMQ publish
 ↓
application crashes
```

where the event could simply vanish.

---

# **13. Outbox publisher**

Now we have a separate component:

```text
OutboxPublisher
```

Its job:

```text
1. Find unpublished events
2. Publish them to RabbitMQ
3. Mark them as published
```

Conceptually:

```text
PostgreSQL
    |
    | unpublished events
    v
Outbox Publisher
    |
    v
RabbitMQ
```

---

# **14. But there’s another race**

Suppose we have:

```text
Publisher A
Publisher B
```

Both query:

```text
WHERE published_at IS NULL
```

They could both find:

```text
event 123
```

Now both publish it.

That’s why an outbox system must also handle **duplicate publication**.

And this leads to one of the most important messaging concepts:

**At-least-once delivery means consumers must be idempotent.**

---

# **15. At-least-once delivery**

The publisher might do:

```text
publish event
     ↓
RabbitMQ accepts it
     ↓
publisher crashes
     ↓
published_at was never updated
```

When the publisher restarts:

```text
event still appears unpublished
```

So it publishes again.

Result:

```text
Event 123
Event 123
```

That’s not necessarily a bug.

It’s often the expected consequence of reliable delivery.

---

# **16. Therefore: idempotent consumers**

Suppose notification service receives:

```text
PostCreatedEvent
eventId = 123
```

It processes it.

Then receives:

```text
eventId = 123
```

again.

It needs to recognize:

```text
"I've already processed event 123."
```

and avoid performing the side effect twice.

---

# **17. Processed-events table**

One common strategy:

```sql
CREATE TABLE processed_events (
    event_id UUID PRIMARY KEY,
    processed_at TIMESTAMP WITH TIME ZONE NOT NULL
);
```

Consumer:

```text
BEGIN
  |
  +-- INSERT event_id into processed_events
  |
  +-- perform business change
  |
COMMIT
```

If the event already exists:

```text
duplicate
   ↓
skip
```

The unique constraint becomes part of the idempotency mechanism.

---

# **18. This gives us a complete pipeline**

Now:

```text
ProjectHub
    |
    | transaction
    v
PostgreSQL
    |
    +-- posts
    |
    +-- outbox_events
              |
              v
       Outbox Publisher
              |
              v
          RabbitMQ
              |
              v
      Notification Worker
              |
              v
      processed_events
```

That’s a real event-driven architecture.

---

# 

# 

# **19. Where does**

**`@TransactionalEventListener`**

**fit?**

Good question.

It can still be useful.

For example:

```java
@Transactional
public void createPost(...) {

    postRepository.save(post);

    publisher.publishEvent(
        new PostCreatedEvent(...)
    );
}
```

Then:

```java
@TransactionalEventListener
public void handle(PostCreatedEvent event) {

    outboxService.createOutboxEvent(event);
}
```

But there’s a subtle issue.

If the listener runs **after commit**, then inserting the outbox row in the listener is too late to be part of the original transaction.

So for the durable outbox itself, we usually want:

```text
Post
+
Outbox
```

written in the **same transaction**.

Don’t accidentally move the outbox write to `AFTER_COMMIT`.

---

# **20. Better approach**

The simplest reliable approach is often:

```java
@Transactional
public void createPost(...) {

    Post post = postRepository.save(...);

    outboxRepository.save(
        OutboxEvent.forPostCreated(post)
    );
}
```

Both writes occur in the same transaction.

No need for a transactional event listener for this particular step.

---

# **21. Then what are transaction-bound events useful for?**

They are excellent when you want:

“Do something only after this transaction successfully commits.”

For example:

```text
database commit
      ↓
send cache invalidation signal
```

or:

```text
database commit
      ↓
trigger some non-critical local processing
```

or:

```text
database rollback
      ↓
record/perform rollback-specific behavior
```

Spring explicitly supports those different transaction phases.  

---

# 

# 

# **22.**

**`AFTER_COMMIT`**

**has another subtlety**

Suppose:

```java
@TransactionalEventListener
public void handle(PostCreatedEvent event) {
    postRepository.save(...);
}
```

The original transaction has already committed.

You’re now doing database work after commit.

You shouldn’t mentally treat this as:

```text
"continuing the original transaction"
```

If you need a new transactional unit, make that explicit with an appropriate transaction boundary.

This is another place where understanding transaction propagation matters.

---

# **23. ProjectHub post creation**

Let’s design it properly.

Request:

```http
POST /projects/7/posts
```

Flow:

```text
Controller
    ↓
Authorization
    ↓
PostService.createPost()
    ↓
@Transactional
    |
    +-- validate project
    |
    +-- create Post
    |
    +-- create OutboxEvent
    |
    +-- COMMIT
```

Then separately:

```text
Outbox Publisher
    ↓
RabbitMQ
```

Then:

```text
Notification Consumer
    ↓
process event
```

---

# **24. Why not publish directly from the service?**

Because:

```java
@Transactional
public void createPost(...) {

    postRepository.save(post);

    rabbitTemplate.convertAndSend(...);
}
```

creates an unreliable relationship:

```text
DB transaction
      +
external broker operation
```

There’s no guarantee that both succeed together.

The outbox turns:

```text
DB + broker
```

into:

```text
DB transaction
      ↓
durable event
      ↓
eventual broker delivery
```

This is much easier to reason about.

---

# **25. Eventual consistency**

The outbox architecture means the broker may not receive the event immediately.

For example:

```text
12:00:00.000
Post created

12:00:00.020
DB committed

12:00:00.050
publisher discovers event

12:00:00.070
RabbitMQ receives event
```

For those 70 milliseconds, different components may see different states.

That’s:

**eventual consistency**

This is a deliberate tradeoff.

---

# **26. Not everything should become asynchronous**

Suppose:

```text
POST /projects/7/posts
```

requires:

```text
Does Alice have posts.create?
Is Alice a project member?
Does Project 7 exist?
```

Those authorization checks should remain synchronous.

You don’t want:

```text
create post
 ↓
event
 ↓
eventual authorization
```

That would be fundamentally wrong.

So:

```text
Security / authorization
        ↓
synchronous
```

while:

```text
notifications / analytics
        ↓
often asynchronous
```

---

# **27. Command vs event**

Remember our earlier lesson.

A command:

```text
SendPostNotification
```

means:

“Please do this.”

An event:

```text
PostCreated
```

means:

“This already happened.”

Our outbox should generally contain **facts about committed business changes**:

```text
PostCreated
ProjectMemberAdded
ProjectDeleted
CommentCreated
```

rather than arbitrary commands.

---

# **28. Event schema**

A useful event envelope:

```json
{
  "eventId": "8f7...",
  "eventType": "PostCreated",
  "version": 1,
  "occurredAt": "2026-10-01T12:00:00Z",
  "aggregateType": "Post",
  "aggregateId": "42",
  "data": {
    "projectId": 7,
    "authorId": 15
  }
}
```

Why include:

```text
eventId
```

?

Idempotency.

Why:

```text
version
```

?

Schema evolution.

Why:

```text
aggregateId
```

?

Consumers often need to know which business entity changed.

---

# **29. Event versioning**

Today:

```text
PostCreated v1
```

Later:

```text
PostCreated v2
```

Maybe v2 adds:

```text
authorDisplayName
```

Old consumers may still understand v1.

So events should be treated as contracts.

Don’t casually change:

```json
{
  "projectId": 7
}
```

into:

```json
{
  "project": {
    "id": 7
  }
}
```

without thinking about consumers.

---

# **30. Outbox polling**

The simplest publisher architecture is polling:

```text
every N milliseconds
       ↓
SELECT unpublished events
       ↓
publish
       ↓
mark published
```

Conceptually:

```java
@Scheduled(fixedDelay = 1000)
public void publishOutbox() {
    ...
}
```

But production implementations need to think carefully about:

```text
concurrency
batch size
locking
retries
duplicates
crashes
backpressure
```

The simple version is enough to understand the pattern.

---

# **31. Multiple publishers**

Imagine:

```text
Publisher A
Publisher B
Publisher C
```

all running because ProjectHub has multiple Pods.

Remember Kubernetes?

```text
ProjectHub Pod 1
ProjectHub Pod 2
ProjectHub Pod 3
```

If each Pod runs an outbox publisher:

```text
3 publishers
```

can compete for the same events.

This is where database claiming/locking becomes important.

For example, PostgreSQL can use row-locking strategies such as:

```sql
FOR UPDATE SKIP LOCKED
```

to allow workers to claim different rows without waiting on rows already claimed by another worker.

We’ll implement this later when we build the actual publisher.

---

# 

# 

# **32. Why**

**`SKIP LOCKED`**

**is interesting**

Imagine:

```text
events:
1
2
3
4
5
```

Publisher A locks:

```text
1
2
```

Publisher B asks for work.

Instead of waiting for:

```text
1
2
```

it can skip locked rows and get:

```text
3
4
```

So:

```text
Publisher A → 1,2
Publisher B → 3,4
Publisher C → 5
```

This can improve worker concurrency.

But again, this is a tool for a specific workload—not something you add automatically.

---

# **33. Failure scenario**

Let’s simulate:

```text
PostService
    ↓
INSERT post
INSERT outbox
    ↓
COMMIT
```

Everything succeeds.

Then:

```text
Outbox Publisher
    ↓
RabbitMQ unavailable
```

Publisher can’t deliver.

No problem yet.

The outbox row remains:

```text
published_at = NULL
```

Next attempt:

```text
RabbitMQ available
    ↓
publish
    ↓
mark published
```

This is the resilience benefit.

---

# **34. Another failure**

Publisher:

```text
publish event
```

RabbitMQ:

```text
SUCCESS
```

Then publisher crashes before:

```sql
UPDATE outbox_events
SET published_at = ...
```

On restart:

```text
event still unpublished
```

It publishes again.

So:

```text
at-least-once
```

means the consumer must be idempotent.

This is why:

```text
Outbox
```

and:

```text
Idempotent consumer
```

belong together.

---

# **35. Exactly-once is not your default assumption**

Don’t build ProjectHub assuming:

```text
"RabbitMQ guarantees this business operation happens exactly once."
```

Instead design for:

```text
possibly delivered multiple times
```

and make the business operation safe.

That’s a much stronger engineering model.

---

# **36. Example: notification**

Event:

```text
PostCreated
eventId = 123
```

Consumer:

```text
if event 123 already processed:
    return

send notification

mark 123 processed
```

But there’s still a subtle ordering problem:

```text
send notification
 ↓
crash
 ↓
mark processed never happens
```

Next delivery:

```text
send notification again
```

Now you may send duplicate emails.

True idempotency often requires the **side effect itself** to have an idempotency mechanism, or a design where duplicate effects are acceptable/controlled.

This is why distributed systems are hard.

---

# **37. The important lesson**

Idempotency isn’t simply:

```text
"check a database table."
```

You need to consider the entire side effect.

For example, an external payment API may support:

```text
Idempotency-Key: event-123
```

Then repeated requests with the same key don’t create multiple charges.

That’s much stronger.

---

# **38. ProjectHub event architecture**

Our evolving architecture is now:

```text
                       ┌───────────────┐
                       │  PostgreSQL   │
                       │               │
Request → Service ───→ │ Post          │
            │          │ Outbox        │
            │          └───────┬───────┘
            │                  │
            │                  v
            │          Outbox Publisher
            │                  │
            │                  v
            │             RabbitMQ
            │              /     \
            │             /       \
            │            v         v
            │       Notification  Analytics
            │          Worker       Worker
            │
            v
       synchronous
      authorization
```

That’s a major architectural milestone.

---

# **39. Where Redis fits**

Suppose we cache:

```text
project:7
```

After creating a post, we might need to invalidate:

```text
project:7:posts
```

This can be handled through an event:

```text
PostCreated
     ↓
cache invalidation consumer
```

But again:

```text
DB commit
```

must happen before the event represents a committed fact.

The outbox helps guarantee that relationship.

---

# **40. Where observability fits**

Remember our observability lesson?

Now we can monitor:

```text
outbox_events_pending
outbox_publish_latency
outbox_publish_failures
rabbitmq_queue_depth
consumer_processing_time
consumer_failures
dead_letter_queue_size
```

So our architecture isn’t just:

```text
make it work
```

but:

```text
make it observable
```

---

# **41. Where Kubernetes fits**

With three ProjectHub Pods:

```text
Pod 1
Pod 2
Pod 3
```

we might have:

```text
3 application instances
```

all producing outbox records.

We need to design the publisher so that:

```text
3 workers
```

can safely process:

```text
same outbox table
```

without creating uncontrolled duplication.

Again, this is why understanding database concurrency from Lessons 60–62 matters.

Everything is connecting.

---

# **42. The complete mental model**

You should now see:

```text
HTTP
 ↓
Spring Security
 ↓
Service
 ↓
@Transactional
 ↓
PostgreSQL
 ├── business data
 └── outbox event
       ↓
     COMMIT
       ↓
Outbox Publisher
       ↓
RabbitMQ
       ↓
Consumers
       ↓
Idempotent processing
```

This gives us:

```text
strong local consistency
+
durable event recording
+
eventual asynchronous processing
```

That’s the core of many production event-driven systems.

---

# **43. What not to do**

### **❌ Don’t do this**

```text
DB save
 ↓
RabbitMQ publish
 ↓
DB commit
```

### **❌ Don’t assume this solves durability**

```java
@TransactionalEventListener
```

It guarantees transaction-phase semantics, but an `AFTER_COMMIT` listener can still fail after the database commit.  

### **❌ Don’t assume events are delivered once**

Design consumers to tolerate duplicates.

### **❌ Don’t put authorization into asynchronous events**

Security decisions for the current request should happen synchronously.

### **❌ Don’t turn every method into an event**

Events are useful when asynchronous decoupling or independent consumers actually provide value.

---

# **44. Our ProjectHub rule**

For a business mutation:

```text
Post created
Project member added
Comment created
Project deleted
```

first make the database state correct.

Then make the fact that it happened durable:

```text
business row
+
outbox row
```

in one transaction.

Then:

```text
publish asynchronously
```

Then:

```text
consume idempotently
```

That’s our pattern.

---

# **Exercise 63**

### **1. Dual write**

Explain why this is unsafe:

```text
save Post
   ↓
publish RabbitMQ event
   ↓
commit DB
```

Give **two different failure scenarios**.

---

### **2. Transactional event listener**

Explain the difference between:

```java
@EventListener
```

and:

```java
@TransactionalEventListener
```

Then explain what the default `AFTER_COMMIT` phase means. Spring documents `AFTER_COMMIT` as the default phase and also supports `BEFORE_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`.  

---

### **3. Outbox**

Design an `outbox_events` table.

You should decide what fields you need for:

```text
event ID
event type
aggregate
payload
created time
publication state
```

---

### **4. Failure scenario**

Walk through:

```text
Post created
+
Outbox row created
+
DB committed
+
RabbitMQ is down for 5 minutes
```

What happens to the post?

What happens to the event?

What should the publisher do?

---

### **5. Duplicate delivery**

Explain this sequence:

```text
Publisher
   ↓
RabbitMQ accepts event
   ↓
Publisher crashes
   ↓
published_at was never updated
   ↓
Publisher restarts
   ↓
same event published again
```

Why is this acceptable in an at-least-once design?

What must the consumer do?

---

### **6. ProjectHub**

Design the complete flow for:

```http
POST /projects/7/posts
```

where:

```text
Alice has posts.create
Alice belongs to Project 7
Post is created
Notification must eventually be sent
Analytics must eventually receive the event
```

Draw:

```text
HTTP
 ↓
Security
 ↓
Service
 ↓
Transaction
 ↓
Post + Outbox
 ↓
Commit
 ↓
Publisher
 ↓
RabbitMQ
 ↓
Notification + Analytics
```

---

### **7. Architecture challenge**

Finally, answer this:

**Why is the Outbox Pattern more than “just another database table”?**

Explain what consistency problem it solves and why it works particularly well with the transaction concepts we’ve just learned.

**Next: Lesson 64 — Building the Outbox in ProjectHub: JPA entity, Flyway migration, publisher,** **`FOR UPDATE SKIP LOCKED`****, retries, failed events, and RabbitMQ integration.**