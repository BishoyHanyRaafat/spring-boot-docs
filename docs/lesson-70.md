---
title: Lesson 70: Reliable RabbitMQ Confirms, Retries, DLQ, and Idempotency
sidebar_position: 70
---

Now we move from **“RabbitMQ works”** to **“RabbitMQ failures are handled deliberately.”**

Spring AMQP 4.1.1 currently supports correlated publisher confirms and returned messages, while RabbitMQ 4.2 documents publisher confirms and consumer acknowledgements as separate reliability mechanisms.  

Our target:

```text
Post + Outbox
      ↓
   Publisher
      ↓
 RabbitMQ
      ↓
   Consumer
      ↓
 Idempotency
      ↓
 Business work
      ↓
     ACK
```

with failures handled rather than ignored.

---

## **1. First: the most important distinction**

There are **two acknowledgements** in our system.

### **Publisher confirm**

```text
ProjectHub ───────→ RabbitMQ
             confirm ←
```

This answers:

Did RabbitMQ accept responsibility for this published message?

### **Consumer ACK**

```text
RabbitMQ ─────────→ Worker
             ACK ←
```

This answers:

Did the consumer successfully process this delivery?

RabbitMQ explicitly says these mechanisms are independent; publisher confirms don’t know whether consumers processed anything, and consumer acknowledgements don’t know how the message was originally published.  

This distinction is fundamental.

---

# **2. Publisher failure scenario**

Imagine our outbox contains:

```text
event_id = abc
status = PROCESSING
```

Publisher sends:

```text
PostCreated
```

Then the network disappears.

Our application doesn’t know whether RabbitMQ received it.

So we **cannot safely assume**:

```text
PUBLISHED
```

Instead:

```text
PROCESSING
     ↓
uncertain
     ↓
retry
```

Potentially:

```text
PostCreated
PostCreated
```

gets published.

That’s okay.

Why?

Because we’re deliberately choosing:

**possible duplication rather than silent event loss.**

---

# **3. Publisher confirms**

RabbitMQ publisher confirms are designed specifically for this problem. A publisher cannot assume that writing a message to its socket means the broker successfully processed it.  

Spring AMQP configures correlated confirms through `CachingConnectionFactory` using:

```java
ConfirmType.CORRELATED
```

and returned messages through:

```java
publisherReturns = true
```

Conceptually:

```java
connectionFactory.setPublisherConfirmType(
        ConfirmType.CORRELATED
);

connectionFactory.setPublisherReturns(true);
```

The important word is **correlated**.

---

# **4. Why correlation matters**

Suppose we’re publishing:

```text
event A
event B
event C
```

We need to know which confirmation corresponds to which event.

So:

```text
Outbox A
   ↓
CorrelationData(A)
   ↓
RabbitMQ
   ↓
confirmation(A)
```

and:

```text
Outbox B
   ↓
CorrelationData(B)
   ↓
RabbitMQ
   ↓
confirmation(B)
```

Now our publisher can update the correct outbox row.

---

# **5. A confirmation is not the same as routing**

This is subtle.

Imagine:

```text
Exchange:
projecthub.events

Routing key:
post.created

Queues:
NONE
```

The broker can accept the publication but have nowhere to route it.

RabbitMQ supports the `mandatory` mechanism so unroutable messages can be returned to the publisher; Spring AMQP exposes this through `ReturnsCallback`.  

So we care about:

```text
confirm
+
return
```

not merely:

```text
send() returned normally
```

---

# **6. The publisher state machine**

Let’s formalize our outbox.

```text
             ┌──────────────┐
             │    PENDING   │
             └──────┬───────┘
                    │
                  claim
                    ↓
             ┌──────────────┐
             │  PROCESSING  │
             └──────┬───────┘
                    │
                 publish
                    │
          ┌─────────┴─────────┐
          ↓                   ↓
       confirmed            failure
          │                   │
          ↓                   ↓
      PUBLISHED            PENDING
```

And:

```text
PROCESSING
     ↓
publisher crashes
     ↓
lease expires
     ↓
PENDING
```

This is the reason our outbox state machine exists.

---

# 

# 

# **7. Why**

**`PROCESSING`**

**needs recovery**

Imagine Pod 1 claims:

```text
event 123
```

and changes:

```text
PENDING → PROCESSING
```

Then:

```text
Pod 1 crashes
```

If nothing recovers that record, it is stuck forever.

So we periodically recover stale records:

```sql
UPDATE outbox_events
SET status = 'PENDING'
WHERE status = 'PROCESSING'
  AND last_attempt_at <
      CURRENT_TIMESTAMP - INTERVAL '5 minutes';
```

The five minutes is just an example.

In production, the lease duration should reflect the expected publishing behavior.

---

# **8. Don’t hold the DB transaction during RabbitMQ publishing**

Remember this:

### **Bad**

```text
BEGIN
   claim event
   publish RabbitMQ
   wait for network
   mark published
COMMIT
```

### **Better**

```text
Transaction
    ↓
claim event
    ↓
COMMIT

publish to RabbitMQ
    ↓
confirm

Transaction
    ↓
mark PUBLISHED
    ↓
COMMIT
```

This keeps database transactions short.

---

# **9. Now the consumer side**

Suppose RabbitMQ delivers:

```text
PostCreated(eventId=abc)
```

Our consumer does:

```text
receive
   ↓
process
   ↓
ACK
```

RabbitMQ’s manual acknowledgement mode is designed so the broker retains responsibility until the consumer explicitly acknowledges the delivery. Unacknowledged messages can be requeued when a consumer connection/channel disappears.  

---

# **10. Consumer crash**

Consider:

```text
RabbitMQ
   ↓
PostCreated
   ↓
NotificationConsumer
   ↓
send notification
   ↓
CRASH
```

No ACK happened.

RabbitMQ can redeliver it.

That’s good.

But now:

```text
send notification
```

may have already happened.

So:

```text
PostCreated
```

might be processed twice.

And this brings us to one of the most important rules:

**Consumers must tolerate redelivery.**

RabbitMQ itself recommends designing consumers with idempotence in mind when manual acknowledgements are used.  

---

# **11. Idempotency**

Suppose:

```text
eventId = 123
```

arrives twice.

Without idempotency:

```text
123 → send email
123 → send email
```

With idempotency:

```text
123 → send email
123 → already processed → skip
```

We need a durable record of processed event IDs.

---

# 

# **12.**

**`processed_events`**

For a consumer backed by PostgreSQL:

```sql
CREATE TABLE processed_events (
    event_id UUID PRIMARY KEY,
    processed_at TIMESTAMP WITH TIME ZONE NOT NULL
);
```

The primary key is important.

It means the database itself enforces:

```text
eventId must be unique
```

rather than relying on:

```java
if (!alreadyProcessed()) {
    ...
}
```

alone.

---

# **13. Why the database constraint matters**

Suppose two consumer threads somehow process:

```text
eventId = abc
```

simultaneously.

Both might execute:

```text
SELECT ...
```

and both see:

```text
not processed
```

Then both perform the business operation.

A unique constraint gives us a final safety barrier:

```text
eventId UUID PRIMARY KEY
```

The database decides that only one record can exist.

---

# **14. But idempotency isn’t magic**

There’s an important problem:

```text
BEGIN
    perform external side effect
    INSERT processed_events
COMMIT
```

Suppose:

```text
external side effect succeeds
        ↓
database crashes
        ↓
processed_events isn't committed
```

The message gets retried.

The external side effect happens again.

So a local `processed_events` table cannot magically make arbitrary external systems exactly-once.

---

# **15. External side effects need idempotency too**

For example, suppose the consumer calls:

```text
Payment Service
```

We should ideally send:

```text
Idempotency-Key: eventId
```

Then the payment service can guarantee:

```text
same idempotency key
       ↓
same logical operation
```

This gives us:

```text
RabbitMQ at-least-once
        +
consumer idempotency
        +
external API idempotency
```

That’s much stronger.

---

# **16. What if the business operation is local?**

Suppose the notification consumer updates its own database:

```text
notification.status = SENT
```

Then we can often put:

```text
business change
+
processed_events
```

in the **same database transaction**.

Conceptually:

```text
BEGIN

    perform business change

    INSERT processed_events(eventId)

COMMIT
```

Now those two local changes succeed or fail together.

That’s much easier to make reliable.

---

# **17. Duplicate delivery**

Imagine:

```text
Event abc
```

arrives.

First delivery:

```text
abc
 ↓
not processed
 ↓
business operation
 ↓
INSERT abc
 ↓
COMMIT
 ↓
ACK
```

Second delivery:

```text
abc
 ↓
already processed
 ↓
skip business operation
 ↓
ACK
```

Perfect.

The duplicate is harmless.

---

# **18. Now retries**

Let’s say the consumer encounters:

```text
Notification API timeout
```

We don’t want:

```text
NACK + requeue forever
```

RabbitMQ supports negative acknowledgements with `requeue=true` or `false`; with `false`, the message can be routed to a configured DLX, otherwise discarded.  

So conceptually:

```text
temporary failure
       ↓
retry
```

and eventually:

```text
permanent / repeated failure
       ↓
DLQ
```

---

# **19. Retry isn’t the same as DLQ**

Think of them as two different mechanisms.

### **Retry**

Answers:

Maybe the next attempt will succeed.

### **DLQ**

Answers:

We’ve decided this message shouldn’t continue blocking the normal queue.

So:

```text
Message
   ↓
attempt 1
   ↓ failure
attempt 2
   ↓ failure
attempt 3
   ↓ failure
DLQ
```

---

# **20. Why infinite requeue is dangerous**

Suppose we have:

```text
post.created
```

and the consumer has a deterministic bug:

```text
NullPointerException
```

If we endlessly requeue:

```text
queue
 ↓
consumer
 ↓
exception
 ↓
queue
 ↓
consumer
 ↓
exception
 ↓
...
```

we can create a hot failure loop.

This consumes:

- CPU
- network
- database connections
- logs
- broker resources

while making no progress.

---

# **21. Dead-letter topology**

Let’s add:

```text
projecthub.notifications.dlx
```

and:

```text
projecthub.notifications.dlq
```

So:

```text
notifications queue
        │
        │ reject / expire / policy
        ↓
notifications.dlx
        │
        ↓
notifications.dlq
```

RabbitMQ supports dead-letter exchanges for messages that are rejected or expire, among other cases.  

---

# **22. Important DLQ caveat**

Don’t think:

“DLQ means absolutely nothing can ever be lost.”

Dead-lettering itself has delivery semantics.

RabbitMQ’s quorum queues, for example, support an opt-in at-least-once dead-lettering strategy, while the default strategy has different guarantees and tradeoffs.  

For ProjectHub, the main lesson is:

**A DLQ is an operational isolation mechanism, not a magical guarantee of exactly-once recovery.**

---

# **23. Retry count**

We need to know how many times we’ve tried.

There are several ways to implement this.

For example, a message header:

```text
x-retry-count = 3
```

or a retry queue/state system.

Conceptually:

```text
attempt = 1
attempt = 2
attempt = 3
attempt = 4
```

Then:

```text
attempt > MAX_RETRIES
       ↓
DLQ
```

Don’t blindly retry forever.

---

# **24. Exponential backoff**

Imagine RabbitMQ is temporarily unavailable downstream.

Instead of:

```text
retry immediately
retry immediately
retry immediately
retry immediately
```

use:

```text
1 second
2 seconds
4 seconds
8 seconds
16 seconds
```

with a maximum:

```text
30 seconds
```

or:

```text
60 seconds
```

This is exponential backoff.

It reduces pressure on an unhealthy dependency.

---

# **25. The complete consumer state machine**

Conceptually:

```text
              ┌────────────┐
              │  MESSAGE   │
              └─────┬──────┘
                    │
                 process
                    │
           ┌────────┴────────┐
           ↓                 ↓
        success            failure
           │                 │
           ↓                 ↓
          ACK              retry
                             │
                    ┌────────┴────────┐
                    ↓                 ↓
                 success         max retries
                    │                 │
                    ↓                 ↓
                   ACK               DLQ
```

That’s much safer than simply:

```text
exception → requeue
```

---

# **26. Prefetch**

Now let’s talk about throughput.

RabbitMQ’s prefetch count limits how many unacknowledged deliveries can be outstanding. With manual acknowledgements, this prevents consumers from accumulating an unbounded number of in-flight messages.  

Imagine:

```text
prefetch = 1
```

Then:

```text
receive 1
 ↓
process
 ↓
ACK
 ↓
receive next
```

Very conservative.

---

# **27. Higher prefetch**

With:

```text
prefetch = 100
```

a consumer can have many messages outstanding.

That can improve throughput, especially when processing is fast.

But it can also mean:

```text
consumer
  ↓
100 unprocessed messages
  ↓
large memory usage
```

and uneven distribution when processing times vary.

RabbitMQ’s current documentation notes that appropriate prefetch depends on workload and that larger values can improve throughput but increase the amount of work held in flight.  

---

# **28. Scaling with Kubernetes**

Suppose we have:

```text
3 Pods
```

and:

```text
5 consumers / Pod
```

That’s potentially:

```text
15 consumers
```

Now HPA scales to:

```text
10 Pods
```

We potentially have:

```text
50 consumers
```

If PostgreSQL can only comfortably support 15 concurrent database-heavy operations, we’ve just created a bottleneck.

So our architecture has:

```text
Kubernetes scaling
        +
RabbitMQ consumer concurrency
        +
prefetch
```

all affecting throughput.

---

# **29. Don’t optimize these independently**

This:

```text
Pods ↑
threads ↑
prefetch ↑
```

doesn’t automatically mean:

```text
throughput ↑↑↑
```

You need to consider:

```text
RabbitMQ
   ↓
Consumer
   ↓
Database
   ↓
External API
```

The slowest dependency often determines sustainable throughput.

---

# **30. Let’s examine a real failure**

Suppose:

```text
PostCreated(eventId=ABC)
```

gets published.

Publisher receives:

```text
CONFIRM
```

So:

```text
Outbox = PUBLISHED
```

Then RabbitMQ delivers it.

Consumer:

```text
receive ABC
```

Then:

```text
database update succeeds
```

But before ACK:

```text
CRASH
```

RabbitMQ redelivers:

```text
ABC
```

Consumer sees:

```text
processed_events contains ABC
```

and does:

```text
skip business operation
ACK
```

Result:

```text
business operation = once
message delivery = twice
```

This is exactly the behavior we want.

---

# **31. Another failure**

Now:

```text
Outbox event ABC
      ↓
RabbitMQ accepts
      ↓
application crashes
      ↓
outbox still PROCESSING
```

Recovery eventually changes:

```text
PROCESSING → PENDING
```

Then publishes ABC again.

Consumer sees:

```text
ABC
```

twice.

Again:

```text
processed_events
```

protects us.

This demonstrates why the **outbox + idempotent consumer** combination is so powerful.

---

# **32. One thing we should NOT promise**

Don’t say:

“Our system has exactly-once delivery.”

It doesn’t.

The realistic statement is:

**ProjectHub uses at-least-once delivery with idempotent processing.**

That’s a much more accurate distributed-systems design.

---

# **33. Our reliability model**

Here’s the whole thing:

```text
                PostgreSQL
                    │
              ┌─────┴─────┐
              │ Post+Outbox│
              └─────┬─────┘
                    │
                 COMMIT
                    │
                    ▼
             Outbox Publisher
                    │
             publish + confirm
                    │
          ┌─────────┴─────────┐
          │                   │
       success              failure
          │                   │
          ▼                   ▼
      PUBLISHED             retry
          │
          ▼
       RabbitMQ
          │
          ▼
       Consumer
          │
      idempotency
          │
     ┌────┴────┐
     │         │
 success     failure
     │         │
     ↓         ↓
    ACK      retry
                │
              max?
             /    \
           no      yes
           ↓        ↓
         retry     DLQ
```

---

# **34. What we’ve accomplished**

At this point ProjectHub has a proper asynchronous architecture:

### **Synchronous path**

```text
HTTP
 ↓
Authentication
 ↓
Authorization
 ↓
Business transaction
 ↓
Post + Outbox
 ↓
HTTP response
```

### **Asynchronous path**

```text
Outbox
 ↓
RabbitMQ
 ↓
Consumers
 ↓
Retries
 ↓
Idempotency
 ↓
ACK
 ↓
DLQ when necessary
```

And the two paths are deliberately separated.

---

# **35. Your implementation task**

Now I want you to implement the **reliability layer** on top of the happy path from Lesson 69.

Do these in order.

### **Part A — Publisher confirms**

Configure:

```text
ConfirmType.CORRELATED
publisherReturns = true
```

Then make your publisher distinguish:

```text
confirmed
nacked
returned
```

Don’t immediately solve all retry logic.

---

### **Part B — Outbox recovery**

Implement:

```text
PROCESSING
    ↓
stale
    ↓
PENDING
```

using a lease/timeout.

---

### **Part C — Consumer idempotency**

Create:

```sql
processed_events
```

with:

```text
event_id PRIMARY KEY
processed_at
```

Then make:

```text
PostCreated(eventId=ABC)
```

safe to process twice.

---

### **Part D — DLQ**

Create:

```text
projecthub.notifications.dlx
projecthub.notifications.dlq
```

and configure the notification queue so permanently rejected messages can reach the DLQ.

---

### **Part E — Failure test**

This is the important part.

Intentionally make your consumer throw an exception.

Observe:

```text
message
 ↓
failure
 ↓
retry
 ↓
failure
 ↓
DLQ
```

Then restart the consumer and verify that normal messages continue processing.

---

## **Final mental model**

If you remember only one diagram from this lesson, remember this:

```text
       DATABASE
          │
     Post + Outbox
          │
       COMMIT
          │
          ▼
      PUBLISHER
          │
    Confirm / Return
          │
          ▼
      RABBITMQ
          │
          ▼
      CONSUMER
          │
     Idempotency
          │
    ┌─────┴─────┐
    │           │
 success      failure
    │           │
   ACK        retry
                │
             exhausted
                │
               DLQ
```

This is the point where RabbitMQ stops being merely **“a queue we put messages into”** and becomes a deliberate reliability component of the architecture.

Next, we’ll take the same architecture and tackle a particularly nasty problem: **ordering, duplicate events, concurrent consumers, and why** **`post.created → post.updated → post.deleted`** **can arrive in ways your application may not expect.**