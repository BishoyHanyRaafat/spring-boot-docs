---
title: "Lesson 71: Ordering, Duplicates, and Concurrent Consumers"
sidebar_position: 71
---

This is where RabbitMQ starts behaving like a **distributed system** rather than simply a queue.

The problem we’re solving is:

```text
PostCreated
PostUpdated
PostDeleted
```

What happens if they don’t arrive in that exact order?

RabbitMQ queues are FIFO, but ordering can be affected by multiple consumers, redeliveries, consumer priorities, and publishing across multiple channels/connections. Spring AMQP also specifically recommends low prefetch—typically `1`—when strict ordering is required.  

---

## **1. The naïve assumption**

Imagine ProjectHub does:

```text
PostCreated
    ↓
PostUpdated
    ↓
PostDeleted
```

You might assume the consumer sees:

```text
PostCreated
    ↓
PostUpdated
    ↓
PostDeleted
```

Sometimes it will.

But distributed systems require you to ask:

**What guarantees actually exist?**

---

# **2. One queue, one consumer**

Suppose:

```text
RabbitMQ Queue
      │
      ▼
Consumer A
```

and the publisher sends through one publishing channel:

```text
A → B → C
```

RabbitMQ queues preserve FIFO ordering for normal deliveries to a single consumer.  

So you can generally see:

```text
A
↓
B
↓
C
```

That’s the simplest ordering scenario.

---

# **3. Add two consumers**

Now:

```text
             Queue
            /     \
           ↓       ↓
     Consumer A  Consumer B
```

RabbitMQ can distribute deliveries among competing consumers.

So:

```text
A → Consumer A
B → Consumer B
C → Consumer A
```

Now there is no single consumer processing sequence:

```text
A → B → C
```

Instead, they may execute concurrently:

```text
Consumer A: A -------- C
Consumer B:      B --------
```

The queue still dequeues messages in FIFO order, but actual processing happens across multiple consumers.  

---

# **4. Why this matters**

Suppose our events are:

```text
post.created
post.updated
```

Consumer A receives:

```text
post.created
```

Consumer B receives:

```text
post.updated
```

If `post.updated` finishes first:

```text
updated
  ↓
created
```

your downstream system might temporarily observe an impossible state.

---

# **5. A more realistic example**

Imagine:

```text
PostCreated
title = "Hello"
```

followed immediately by:

```text
PostUpdated
title = "Hello World"
```

Two workers:

```text
Worker A → PostCreated → takes 500 ms

Worker B → PostUpdated → takes 50 ms
```

Actual completion:

```text
PostUpdated
     ↓
PostCreated
```

The broker didn’t necessarily violate FIFO delivery.

**Your workers created concurrent execution.**

That’s a crucial distinction.

---

# **6. Redelivery makes it even harder**

Now suppose:

```text
PostCreated
    ↓
Consumer
    ↓
processing
    ↓
CRASH
```

RabbitMQ redelivers it.

The `redelivered` flag can indicate that a delivery is a redelivery. RabbitMQ also documents that repeated deliveries can affect the original ordering because of acknowledgement and redelivery timing.  

So you might have:

```text
Created
Updated
Created (redelivery)
```

The application must therefore tolerate duplicates **and** possible ordering complications.

---

# **7. The first solution: don’t require ordering**

This is often the best architectural choice.

Instead of requiring:

```text
Created → Updated → Deleted
```

make every event independently meaningful.

For example:

```text
PostUpdated {
    postId: 42,
    version: 8,
    ...
}
```

Now the consumer can reason about:

```text
postId = 42
version = 8
```

rather than assuming:

“I must have seen every previous event.”

This is much more resilient.

---

# **8. Add a version**

Suppose the database changes:

```text
Post version 10
```

and emits:

```text
PostUpdated
version = 10
```

Then later:

```text
PostUpdated
version = 11
```

The consumer receives:

```text
version 11
version 10
```

It can recognize:

```text
10 < 11
```

and decide what to do.

---

# **9. Version-based protection**

Conceptually:

```java
if (event.version() <= currentVersion) {
    // stale or duplicate
    return;
}
```

So:

```text
current = 11
incoming = 10
```

means:

```text
ignore
```

while:

```text
current = 10
incoming = 11
```

means:

```text
apply
```

This is one of the strongest techniques for dealing with event ordering.

---

# **10. But there’s a catch**

Suppose the consumer receives:

```text
version 11
```

before:

```text
version 10
```

If it applies version 11 and then ignores version 10:

```text
11 → applied
10 → ignored
```

that’s fine **if version 11 contains enough information to establish the correct state**.

But if event 11 only says:

```text
"change title"
```

without the full state, skipping event 10 could leave the consumer incorrect.

Therefore:

Version numbers solve stale-event detection, but they don’t automatically solve missing-event recovery.

---

# **11. Event types matter**

There are two broad styles.

### **Delta event**

```json
{
  "eventType": "PostTitleChanged",
  "postId": 42,
  "newTitle": "Hello World"
}
```

It describes a change.

### **State event**

```json
{
  "eventType": "PostUpdated",
  "postId": 42,
  "version": 11,
  "title": "Hello World",
  "visibility": "TEAM"
}
```

It describes the resulting state.

State-oriented events can be easier for consumers to recover from out-of-order delivery, although they can carry more data.

---

# **12. Another solution: partition by aggregate**

Suppose we have:

```text
Post 42
Post 43
Post 44
```

Do we really need:

```text
42 event
43 event
44 event
```

to be globally ordered?

Probably not.

We usually care about ordering **within the same aggregate**.

So we want:

```text
Post 42:
Created → Updated → Deleted

Post 43:
Created → Updated

Post 44:
Created → Updated → Updated
```

while allowing:

```text
Post 42 event
Post 43 event
Post 44 event
```

to process concurrently.

This is a much more scalable requirement.

---

# **13. The key concept: ordering key**

Give each event:

```text
aggregateId
sequence
```

For example:

```json
{
  "eventId": "...",
  "eventType": "PostUpdated",
  "aggregateType": "Post",
  "aggregateId": "42",
  "sequence": 17
}
```

Now the consumer knows:

```text
Post 42
sequence 17
```

is part of one ordered stream.

---

# **14. RabbitMQ queues aren’t Kafka partitions**

This distinction is worth knowing.

RabbitMQ gives you:

```text
Queue
```

and multiple consumers can compete for messages.

RabbitMQ also has streams, which provide a different model and stronger replay/ordering-oriented capabilities.

For our current ProjectHub architecture, we’re deliberately using ordinary queues.

Therefore, if strict per-aggregate ordering becomes a core requirement, we need to design for it explicitly rather than assuming the queue provides it automatically.

---

# **15. One practical approach**

We can create separate queues by shard:

```text
notifications-0
notifications-1
notifications-2
notifications-3
```

Then calculate:

```text
hash(postId) % 4
```

So:

```text
Post 42 → queue 2
Post 43 → queue 3
Post 44 → queue 0
```

All events for Post 42 go to the same queue.

Now different posts can process concurrently.

---

# **16. Why this works**

Suppose:

```text
Post 42:
A → B → C

Post 43:
X → Y → Z
```

We can process:

```text
Queue 2:
A → B → C

Queue 3:
X → Y → Z
```

while both queues operate simultaneously.

We preserve:

```text
42: A → B → C
```

without requiring:

```text
42 + 43 + 44
```

to be globally sequential.

---

# **17. But hashing isn’t enough by itself**

Even if all Post 42 events go to the same queue:

```text
Queue 2
   ↓
Consumer A
Consumer B
```

you’ve still introduced competing consumers.

So if strict ordering is required, you need to control consumer concurrency too.

Spring AMQP explicitly notes that strict ordering is a case where prefetch should be reduced to 1.  

---

# **18. Strict ordering configuration**

Conceptually:

```text
prefetch = 1
concurrency = 1
```

for a particular ordered processing stream.

Then:

```text
A
 ↓
process
 ↓
ACK
 ↓
B
 ↓
process
 ↓
ACK
```

That’s much easier to reason about.

But it’s slower.

---

# **19. The tradeoff**

You now have:

### **Maximum parallelism**

```text
10 consumers
prefetch = 250
```

Potentially high throughput.

But ordering becomes difficult.

### **Strict ordering**

```text
1 consumer
prefetch = 1
```

Much easier ordering.

But lower throughput.

Neither is universally “better.”

The correct choice depends on the business requirement.

---

# **20. Ask the business question first**

Don’t start with:

“How do I guarantee ordering?”

Start with:

“Which events actually require ordering?”

For example:

### **Analytics**

Usually:

```text
ordering not critical
```

We can process lots of events concurrently.

### **Notifications**

Maybe:

```text
ordering occasionally important
```

### **Financial ledger**

Potentially:

```text
strict per-account ordering
```

Now architecture follows requirements rather than the other way around.

---

# **21. Duplicate events are a separate problem**

This is important.

You can have:

```text
perfect ordering
```

and still receive:

```text
event ABC
event ABC
```

Ordering doesn’t solve duplication.

Likewise:

```text
idempotency
```

doesn’t guarantee ordering.

They’re separate concerns:

```text
Ordering
   +
Idempotency
```

---

# **22. A robust event should carry identity**

Every ProjectHub event should have:

```text
eventId
aggregateType
aggregateId
version
occurredAt
eventType
```

For example:

```json
{
  "eventId": "7d...",
  "eventType": "PostUpdated",
  "version": 12,
  "aggregateType": "Post",
  "aggregateId": "42",
  "occurredAt": "2026-10-01T12:15:00Z"
}
```

Now consumers have enough metadata to reason about:

- duplicates
- stale events
- aggregate identity
- ordering
- debugging

---

# **23. Publisher ordering**

There’s another layer.

Suppose one publisher uses:

```text
Channel A
```

and publishes:

```text
A
B
C
```

RabbitMQ can enqueue those in publication order on that channel.  

But now suppose we have:

```text
Pod 1 → Channel A → A
Pod 2 → Channel B → B
Pod 3 → Channel C → C
```

Those publications can be concurrent.

Therefore, there may be no meaningful global:

```text
A → B → C
```

unless the application establishes one.

---

# **24. This matters for our multi-Pod outbox publisher**

Remember our architecture:

```text
Pod 1 ─┐
Pod 2 ─┼→ Outbox → RabbitMQ
Pod 3 ─┘
```

If Post 42 generates:

```text
event 10
event 11
event 12
```

different publisher Pods could potentially publish them concurrently.

So the database’s outbox ordering:

```text
10
11
12
```

doesn’t automatically imply broker processing order.

That’s an extremely important lesson.

---

# **25. If ordering really matters**

You need an explicit strategy.

For example:

```text
aggregateId = 42
sequence = 10
sequence = 11
sequence = 12
```

Then the consumer can enforce:

```text
expected = 10

receive 10 → process
expected = 11

receive 12 → hold/retry

receive 11 → process
expected = 12

process 12
```

This is considerably more complex.

Don’t build it unless the business actually needs it.

---

# **26. Another strategy: read current state**

Sometimes you don’t actually need event ordering.

Suppose:

```text
PostUpdated(version=12)
```

arrives.

The consumer can simply query the source of truth:

```text
Post 42 current state
```

and synchronize itself to that state.

Then the events become triggers:

“Something about Post 42 changed.”

rather than the complete source of truth.

This can dramatically simplify consumers.

---

# **27. But there’s a tradeoff**

Querying the source database from every consumer can create:

```text
RabbitMQ
   ↓
Consumer
   ↓
PostgreSQL
```

and potentially a huge database load.

So don’t blindly replace events with database queries.

The architectural question is:

Is the event carrying enough information for the consumer to process independently?

---

# **28. ProjectHub decision**

For our learning project, let’s choose:

```text
At-least-once delivery
+
idempotent consumers
+
versioned events
+
per-aggregate ordering only where necessary
```

We **do not** require global event ordering.

That’s a sensible default.

---

# **29. Our event becomes**

```java
public record EventEnvelope<T>(
        UUID eventId,
        String eventType,
        String aggregateType,
        String aggregateId,
        long version,
        Instant occurredAt,
        T data
) {}
```

Now:

```text
aggregateId = "42"
version = 17
```

gives the consumer meaningful ordering information.

---

# **30. Consumer logic**

Conceptually:

```text
receive event
      ↓
check eventId
      ↓
duplicate?
   /       \
 yes        no
 ↓           ↓
ACK       check version
             ↓
       stale version?
          /       \
        yes        no
         ↓          ↓
       ACK        process
                      ↓
                 record version
                      ↓
                     ACK
```

That is a strong consumer design.

---

# **31. One subtle problem**

Suppose we receive:

```text
version 17
```

but our consumer has only processed:

```text
version 15
```

What should happen?

We don’t necessarily know whether:

is missing.

So we have three choices:

### **Option A**

Process 17 anyway.

### **Option B**

Wait for 16.

### **Option C**

Fetch current state and reconcile.

Again, the correct choice depends on the business semantics.

---

# **32. Don’t overengineer the first version**

For ProjectHub:

```text
PostCreated
PostUpdated
PostDeleted
```

we’ll initially make consumers:

- idempotent
- version-aware
- tolerant of duplicates
- not dependent on global ordering

Then we’ll add strict per-project/per-post ordering only for a feature that genuinely requires it.

This is exactly the kind of architectural restraint you want in backend engineering.

---

# **33. The big picture**

We now have four independent concepts:

```text
                   Messaging
                      │
       ┌──────────────┼──────────────┐
       │              │              │
   Delivery       Ordering      Idempotency
       │              │              │
   at-least-once   per aggregate    eventId
       │              │              │
       └──────────────┼──────────────┘
                      │
                   Recovery
                      │
                  retry / DLQ
```

Don’t collapse these into one concept called “reliable messaging.”

Reliability is a collection of guarantees.

---

# **Exercise 71**

Now I want you to reason through these scenarios.

### **Scenario 1**

```text
PostCreated
PostUpdated
```

There are two consumers.

Can `PostUpdated` finish before `PostCreated`?

Explain why.

---

### **Scenario 2**

You receive:

```text
PostUpdated
version = 12
```

then:

```text
PostUpdated
version = 11
```

What information would allow the consumer to identify the second event as stale?

---

### **Scenario 3**

Why doesn’t:

```text
eventId uniqueness
```

solve ordering?

And why doesn’t:

```text
ordering
```

solve duplicate delivery?

---

### **Scenario 4**

ProjectHub has:

```text
100,000 posts
```

You want high throughput, but events for the **same post** must remain ordered.

Why would:

```text
100,000 independent consumers
```

be a terrible design?

What kind of partitioning/sharding strategy could give you:

```text
same post → same processing lane
different posts → parallel processing
```

---

### **Scenario 5**

Our outbox contains:

```text
Post 42 event 10
Post 42 event 11
Post 43 event 20
```

Three publisher Pods process them concurrently.

Why can’t we automatically conclude that RabbitMQ will process:

```text
42/10
42/11
43/20
```

in that order?

---

### **Scenario 6 — design question**

For ProjectHub, decide whether each requires strict ordering:

|**Event stream**|**Strict ordering?**|
|---|---|
|Analytics events|?|
|Post notifications|?|
|Post lifecycle (`created → updated → deleted`)|?|
|Financial ledger|?|

Don’t worry about giving the “official” answer. **Explain the reasoning behind each choice.**

---

Once you understand this, we’ve covered one of the hardest conceptual parts of messaging: **delivery guarantees, ordering guarantees, and processing guarantees are three different things.**

Next we’ll move into **Lesson 72 — Kafka vs RabbitMQ**, because now that you’ve built a serious RabbitMQ pipeline, you’re ready to understand why systems sometimes choose Kafka instead—and why Kafka is not simply “RabbitMQ but faster.”