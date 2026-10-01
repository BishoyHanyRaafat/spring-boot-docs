---
title: Lesson 76: Kafka Partitioning, Concurrency, Ordering & Retry
sidebar_position: 76
---

This is the lesson where Kafka’s most important concepts finally connect:

```text
partitions
   +
consumer groups
   +
concurrency
   +
ordering
   +
retries
```

The dangerous misconception is:

“Kafka gives me ordering, so my application is ordered.”

It doesn’t.

Kafka gives you **ordering within a partition**. Your application architecture determines whether that ordering survives processing, retries, concurrency, and failures. Spring Kafka’s current documentation specifically warns that non-blocking retry topics lose the original topic’s ordering guarantees.  

---

# **1. Start with the simplest case**

Suppose:

```text
projecthub.events
```

has:

```text
Partition 0
Partition 1
Partition 2
Partition 3
```

And our key is:

```text
postId
```

So:

```text
Post 42 → Partition 2
Post 43 → Partition 0
Post 44 → Partition 1
```

Within Partition 2:

```text
offset 100 → PostCreated(42)
offset 101 → PostUpdated(42)
offset 102 → PostUpdated(42)
offset 103 → PostDeleted(42)
```

Kafka preserves the order of records within that partition.

That’s our foundation.

---

# **2. Now add consumers**

Suppose:

```text
notifications
```

is our consumer group.

We have:

```text
Consumer A
Consumer B
Consumer C
Consumer D
```

Kafka can assign:

```text
P0 → A
P1 → B
P2 → C
P3 → D
```

Spring’s `@KafkaListener` containers participate in Kafka’s consumer-group partition assignment when subscribed to topics.  

Now:

```text
Post 42
   ↓
P2
   ↓
Consumer C
```

So events for Post 42 can be handled by the same consumer while that assignment remains stable.

---

# **3. More consumers than partitions**

Suppose:

```text
4 partitions
10 consumers
```

You cannot get:

```text
10 partitions of work
```

from those four partitions.

Conceptually:

```text
P0 → Consumer 1
P1 → Consumer 2
P2 → Consumer 3
P3 → Consumer 4

Consumer 5 → idle
Consumer 6 → idle
...
```

For a traditional Kafka consumer group, partitions are the unit that gets distributed among consumers.

Therefore:

**Partition count limits consumer-group parallelism.**

---

# **4. Now Kubernetes enters the picture**

Imagine:

```text
ProjectHub Pod A
ProjectHub Pod B
ProjectHub Pod C
```

Each Pod runs:

```text
@KafkaListener
```

with:

```text
groupId = notifications
```

Kafka treats them as members of the same consumer group.

So scaling:

```text
1 Pod → 3 Pods
```

can increase consumption parallelism **if enough partitions exist**.

But:

```text
4 partitions
3 Pods
```

doesn’t automatically mean each Pod gets multiple partitions in a useful way.

And:

```text
4 partitions
20 Pods
```

cannot produce 20-way partition parallelism.

---

# **5. Listener concurrency**

Spring Kafka also lets a listener container use multiple consumer threads.

For example:

```java
@KafkaListener(
    topics = "projecthub.events",
    groupId = "notifications",
    concurrency = "3"
)
public void consume(PostCreatedEvent event) {
    ...
}
```

Conceptually:

```text
one application instance

listener thread 1
listener thread 2
listener thread 3
```

Those consumers participate in the same consumer group.

Spring explicitly notes that listener instances are invoked across consumer threads, so listener code must be thread-safe; stateless listeners are preferable.  

---

# **6. Don’t blindly maximize concurrency**

Suppose:

```text
10 Pods
×
10 Kafka consumer threads
=
100 consumers
```

But:

```text
Kafka → PostgreSQL
```

can only handle:

```text
20 concurrent database operations
```

You’ve created a bottleneck.

Your architecture becomes:

```text
100 consumers
      ↓
20 DB connections
      ↓
80 waiting
```

Or worse, you overload the database.

So concurrency must be designed around the **whole pipeline**:

```text
Kafka
 ↓
consumer threads
 ↓
CPU
 ↓
DB pool
 ↓
external APIs
```

---

# **7. Now the interesting part: failure**

Suppose Partition 2 contains:

```text
100 → PostCreated(42)
101 → PostUpdated(42)
102 → PostDeleted(42)
```

And:

```text
PostCreated(42)
```

fails.

What should happen?

There are two fundamentally different strategies.

---

# **8. Strategy A — Blocking retry**

Conceptually:

```text
P2:

100 PostCreated
     ↓
    FAIL
     ↓
   retry
     ↓
   retry
     ↓
 success
     ↓
101 PostUpdated
     ↓
102 PostDeleted
```

The failed record is retried before moving forward.

This is useful when:

**The order of processing matters.**

For example, imagine a materialized database state:

```text
PostCreated
PostUpdated
PostDeleted
```

Processing `PostUpdated` before `PostCreated` could make no sense.

---

# **9. Strategy B — Non-blocking retry**

Now imagine:

```text
100 → PostCreated
```

fails.

We send it to a retry topic:

```text
projecthub.events
        ↓
projecthub.events-retry
```

Meanwhile the main partition can continue processing:

```text
101 → PostUpdated
102 → PostDeleted
```

Conceptually:

```text
main
 │
 ├── 100 → retry topic
 │
 ├── 101 → process
 │
 └── 102 → process
```

This is much better when later events don’t depend on the failed one.

Spring Kafka’s `@RetryableTopic` implements this kind of non-blocking retry by creating retry topics and forwarding failed records through them.  

---

# **10. But now ordering is broken**

Imagine:

```text
100 PostCreated
101 PostUpdated
```

Event 100 fails.

It goes to:

```text
retry topic
```

Event 101 succeeds.

Now:

```text
101 completed
100 still waiting
```

So the original ordering:

```text
Created → Updated
```

has effectively become:

```text
Updated → Created
```

Spring’s documentation explicitly states that non-blocking retry loses the original topic’s ordering guarantees.  

This is one of the most important facts in this lesson.

---

# **11. Therefore: retry strategy depends on business semantics**

Ask:

**Does this consumer actually require ordering?**

### **Notifications**

Maybe:

```text
PostCreated
PostUpdated
```

doesn’t require strict processing order.

Perhaps both ultimately generate notifications.

Non-blocking retries can be useful.

### **Search indexing**

Often:

```text
PostUpdated
```

can simply index the latest state.

Ordering may be less important if the consumer reads current state from the database.

### **State machine**

Suppose:

```text
OrderCreated
OrderPaid
OrderShipped
OrderDelivered
```

Order matters.

You probably don’t want:

```text
OrderShipped
```

processed before:

```text
OrderPaid
```

That consumer needs much stronger ordering discipline.

---

# **12. Financial ledger**

Imagine:

```text
Debit 100
Credit 50
Debit 25
```

The sequence can be part of the business meaning.

This is very different from:

```text
send notification
```

So don’t create one universal retry strategy for every Kafka topic.

---

# **13. A useful ProjectHub classification**

We can think about our consumers like this:

```text
Notifications
→ ordering often not critical

Analytics
→ ordering often not critical

Search indexing
→ depends on design

Post state projection
→ ordering may matter

Financial ledger
→ ordering can be critical
```

This isn’t a universal classification; it’s something you determine from the actual business requirements.

---

# **14. Per-aggregate ordering**

Remember our key:

```text
postId
```

Suppose:

```text
Post 42 → P2
Post 43 → P1
Post 44 → P3
```

Then:

```text
P2:
42 Created
42 Updated
42 Deleted

P1:
43 Created
43 Updated

P3:
44 Created
44 Updated
```

Different posts can progress independently.

That’s usually much more useful than requiring:

```text
ALL ProjectHub events
```

to be globally ordered.

---

# **15. Global ordering is expensive**

Imagine:

```text
1 partition
```

Then:

```text
Post 1
Post 2
Post 3
Post 4
...
```

have one global sequence.

But you’ve sacrificed partition-level parallelism.

You can’t distribute those records across many partitions while maintaining a single global order.

So:

**Global ordering and high parallelism naturally pull in opposite directions.**

---

# **16. Per-key ordering is usually the better abstraction**

Instead of saying:

“All ProjectHub events must be ordered.”

say:

“Events belonging to the same aggregate must be ordered.”

For example:

```text
postId = 42
```

must preserve:

```text
Created
Updated
Deleted
```

while:

```text
postId = 43
```

can proceed independently.

That gives us:

```text
ordering where needed
+
parallelism where possible
```

---

# **17. But the key alone isn’t enough**

Suppose our events contain:

```json
{
  "aggregateId": "42",
  "version": 18
}
```

and:

```json
{
  "aggregateId": "42",
  "version": 17
}
```

Even if they normally use the same partition, failures, retries, replay, or other architectural behavior can expose stale events.

So consumers should often understand versions.

---

# **18. Version checking**

Imagine the consumer has already processed:

```text
version = 18
```

Then it receives:

```text
version = 17
```

It can recognize:

```text
17 < 18
```

and treat the event as stale according to the consumer’s business rules.

This is different from duplicate detection.

---

# **19. Event ID vs version**

Keep these three concepts separate:

### **Event ID**

```text
eventId = UUID
```

Answers:

“Have I seen this exact event before?”

### **Aggregate ID**

```text
aggregateId = 42
```

Answers:

“Which entity does this event belong to?”

### **Version**

```text
version = 18
```

Answers:

“Which state transition/version of this entity is this?”

So:

```text
eventId     → identity
aggregateId → grouping
version     → sequence/state
```

---

# **20. Now consider a retry topic**

Suppose:

```text
Post 42
version 17
```

fails and moves to:

```text
projecthub.events-retry
```

while:

```text
version 18
```

is processed successfully.

Now the consumer may see:

```text
18
17
```

That’s why **retry topology and ordering cannot be designed independently**.

Spring’s documentation explicitly highlights this tradeoff for non-blocking retries.  

---

# **21. What if ordering is critical?**

Then a safer strategy is often:

```text
main partition
     ↓
blocking retry
     ↓
recover/DLT
```

rather than immediately sending the record to a separate retry topic.

The idea is:

```text
v17
 ↓
retry
 ↓
retry
 ↓
success / DLT
 ↓
v18
```

This keeps the partition’s processing sequence intact.

---

# **22. But what if the failure lasts 30 minutes?**

Now you have a tradeoff.

Blocking the partition for 30 minutes could prevent other events in that partition from progressing.

So you must decide:

```text
strict ordering
        vs
availability/progress
```

There isn’t a magic framework setting that eliminates this business tradeoff.

---

# **23. Partition design becomes important**

Suppose we have:

```text
100 partitions
```

and:

```text
key = postId
```

Then:

```text
Post 42 → partition 7
Post 43 → partition 81
Post 44 → partition 13
```

Different posts can process concurrently.

But:

```text
Post 42
```

stays associated with one partitioning lane.

This is why choosing the Kafka key is an architectural decision, not just a parameter.

---

# **24. Bad key choice**

Suppose we use:

```text
key = "ProjectHub"
```

for every event.

Then:

```text
EVERY EVENT
    ↓
same partition
```

You’ve accidentally created a bottleneck.

You might have:

```text
100 partitions
```

but only one is heavily used.

So your partition count doesn’t help.

---

# **25. Another bad choice: random key**

Suppose we use:

```text
UUID.randomUUID()
```

as the Kafka key for every event.

Now events for:

```text
Post 42
```

could go:

```text
P1
P7
P3
P9
```

You’ve lost your per-post ordering relationship.

Random distribution can improve balancing, but it destroys the key-based grouping we wanted.

Again:

The right key depends on the business ordering requirement.

---

# **26. Consumer concurrency and ordering**

Suppose one partition contains:

```text
A
B
C
```

A normal blocking listener processes:

```text
A
 ↓
B
 ↓
C
```

in sequence.

But if you introduce asynchronous listener processing, later records can have their listener bodies complete before earlier records. Spring’s current documentation warns that asynchronous processing does not preserve per-partition processing order; if correctness depends on per-key ordering, a blocking listener is the appropriate model.  

So don’t assume:

```text
Kafka delivered A then B
```

means:

```text
business side effects completed A then B
```

---

# **27. This is a subtle but critical distinction**

There are actually several orders:

```text
1. Producer order
2. Kafka partition order
3. Consumer delivery order
4. Listener execution order
5. Business side-effect completion order
```

They are not automatically identical.

For strict ordering, you need to reason about all five.

---

# **28. Producer order**

Suppose three different application Pods publish:

```text
Pod A → PostCreated
Pod B → PostUpdated
Pod C → PostDeleted
```

Even if the outbox rows have:

```text
100
101
102
```

that doesn’t automatically mean Kafka receives them in that exact sequence.

The publisher architecture matters.

---

# **29. Kafka order**

Once records are in the same partition:

```text
offset 100
offset 101
offset 102
```

Kafka provides the ordered log.

That’s the strongest ordering guarantee we’re relying on.

---

# **30. Consumer order**

The consumer can receive records according to partition order.

But then:

```text
listener concurrency
async processing
retry
external calls
```

can affect when the actual business effects complete.

Therefore:

```text
Kafka order ≠ business completion order
```

---

# **31. A practical ProjectHub rule**

For our application, I’d design around:

```text
at-least-once
+
idempotency
+
aggregate-based key
+
versioned events
+
ordering only where business logic requires it
```

And avoid:

```text
global event ordering
```

unless a concrete requirement demands it.

---

# **32. Retry policy by consumer**

Instead of:

```text
ALL consumers
   ↓
same retry strategy
```

think:

```text
Notifications
   → non-blocking retry may be fine

Analytics
   → non-blocking retry may be fine

Post projection
   → preserve ordering

Ledger
   → preserve ordering very carefully
```

The Spring Kafka framework supports combining blocking and non-blocking retry approaches, including choosing specific exception classes for blocking retries before moving to retry topics.  

---

# **33. A useful hybrid**

Suppose a temporary database failure occurs:

```text
DatabaseAccessException
```

We might do:

```text
main topic
   ↓
short blocking retries
   ↓
still failing?
   ↓
retry topic
   ↓
DLT
```

Spring Kafka supports combining blocking and non-blocking retry strategies in this way.  

This can be useful when you want a few quick retries for transient blips without holding the main processing path indefinitely.

---

# **34. But don’t over-engineer immediately**

For ProjectHub, I’d start with:

```text
Consumer
   ↓
DefaultErrorHandler
   ↓
small blocking retry
   ↓
DLT
```

for consumers where ordering matters.

For consumers where ordering doesn’t matter:

```text
@RetryableTopic
```

can be a good fit.

Spring Kafka’s current docs describe `@RetryableTopic` as the convenient mechanism for bootstrapping non-blocking retry/DLT infrastructure.  

---

# **35. One more important detail: DLT partitioning**

Suppose:

```text
projecthub.events
```

has:

```text
4 partitions
```

and:

```text
Post 42
```

is on partition 2.

Your DLT design should preserve enough metadata to understand:

```text
original topic
original partition
original offset
```

Spring’s `DeadLetterPublishingRecoverer` adds exception and original-record metadata to DLT records, which is useful for diagnosis and recovery.  

---

# **36. Monitoring**

Now imagine production.

You should be able to answer:

```text
How many messages are failing?
How many are retrying?
How many are in DLT?
Which partitions are lagging?
Which consumer groups are behind?
How old is the oldest unprocessed event?
```

Kafka gives you the concept of consumer lag:

```text
latest available offset
        -
consumer's processed/committed position
        =
lag
```

High lag can indicate:

```text
too few consumers
slow processing
database bottleneck
external API bottleneck
partition imbalance
retry problems
```

---

# **37. Don’t automatically scale on lag alone**

Suppose:

```text
lag = high
```

You add 50 Pods.

But:

```text
topic = 10 partitions
```

Only 10 consumers can actively own those partitions in the traditional consumer-group model.

Or perhaps:

```text
Kafka → PostgreSQL
```

is already saturated.

Adding consumers could make the database problem worse.

So:

```text
lag
 ↓
investigate bottleneck
 ↓
then scale appropriately
```

is better than:

```text
lag high → add Pods blindly
```

---

# **38. Our complete Kafka architecture now**

```text
                           PostgreSQL
                               │
                      ┌────────┴────────┐
                      │                 │
                   domain            outbox
                    data              events
                      │                 │
                      └────── COMMIT ───┘
                                        │
                                multi-Pod publisher
                                        │
                                 claim + lease
                                        │
                                        ▼
                              Kafka: projecthub.events
                                        │
                              key = aggregateId
                                        │
                  ┌─────────────────────┼─────────────────────┐
                  ↓                     ↓                     ↓
              partition 0           partition 1          partition 2
                  │                     │                     │
                  └──────────────┬──────┴──────────────┬──────┘
                                 │                     │
                           consumer group        consumer group
                           notifications           analytics
                                 │
                         retry / idempotency
                                 │
                       ┌─────────┴─────────┐
                       ↓                   ↓
                    success               DLT
```

At this point, you have the architecture vocabulary to reason about fairly serious Kafka systems.

---

# **39. The four rules I want you to remember**

If you forget everything else from this lesson, remember these:

### **Rule 1**

**Ordering is per partition.**

```text
same partition → ordered
different partitions → no global order
```

### **Rule 2**

**The Kafka key determines grouping/partitioning.**

For ProjectHub:

```text
key = aggregateId
```

can provide per-aggregate ordering.

### **Rule 3**

**Retry topology can change ordering.**

Non-blocking retry topics can let later records proceed before earlier failed records, so Spring Kafka documents that the original topic’s ordering guarantee is lost.  

### **Rule 4**

**At-least-once means idempotency matters.**

```text
eventId
+
database uniqueness
+
transactional business processing
```

is one of our main defenses.

---

# **40. Exercise 76**

Let’s make this one architectural rather than code-heavy.

### **Scenario 1**

You have:

```text
PostCreated
PostUpdated
PostDeleted
```

for the same post.

`PostUpdated` must never be applied before `PostCreated`.

**Question:** Would you use blocking or non-blocking retries? Why?

---

### **Scenario 2**

You have:

```text
EmailNotification
```

A failure means:

```text
SMTP temporarily unavailable
```

The notification doesn’t affect the state of the Post.

**Question:** Does strict ordering necessarily matter here?

---

### **Scenario 3**

You have:

```text
PostUpdated v18
PostUpdated v19
```

but `v18` is delayed while `v19` succeeds.

What could the consumer use to recognize that:

```text
v18
```

is stale?

---

### **Scenario 4**

You have:

```text
100 Kafka partitions
```

but every message uses:

```text
key = "projecthub"
```

Why might the application still behave as though it has only one useful processing lane?

---

### **Scenario 5**

You have:

```text
8 Kafka partitions
20 Kubernetes Pods
```

all using the same consumer group.

Can all 20 Pods simultaneously own one partition each?

Explain why or why not.

---

### **Scenario 6 — the big one**

Explain the difference between:

```text
eventId
aggregateId
version
Kafka partition
Kafka offset
consumer group
```

in one example involving:

```text
Post 42
```

If you can explain those six concepts cleanly, you’ve crossed a pretty important Kafka milestone.

---

## **Where we go next**

We’ve now finished the core **RabbitMQ + Kafka reliability foundations**.

The next logical step is **Lesson 77 — Kafka vs RabbitMQ in the actual ProjectHub architecture**: we’ll make a concrete architectural decision for each kind of workload—commands, notifications, analytics, search, audit history, and long-running jobs—and then move into **Kafka Schema Evolution**, where we’ll tackle a problem every real event-driven system eventually encounters:

```text
Producer deploys v2
        ↓
Consumer is still running v1
        ↓
How do both survive?
```

That leads into event versioning, backward/forward compatibility, schema contracts, and eventually Avro/Protobuf + Schema Registry.