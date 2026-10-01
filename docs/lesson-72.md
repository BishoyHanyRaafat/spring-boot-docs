---
title: Lesson 72: Kafka vs RabbitMQ
sidebar_position: 72
---

We’ve now built a fairly serious RabbitMQ pipeline, so this is the right moment to learn **why Kafka exists and when its model is different**.

The key idea:

**RabbitMQ is primarily a message broker built around queues and routing. Kafka is primarily a distributed event-streaming platform built around durable, partitioned logs.**

Neither is simply “better.” They optimize for different workloads.

Apache Kafka’s current documentation organizes the system around concepts such as topics, partitions, consumer groups, Kafka Streams, Connect, and operational concerns; RabbitMQ’s current documentation centers on exchanges, queues, consumers, acknowledgements, routing, and also offers Streams as a separate data structure.  

---

# **1. Start with RabbitMQ**

Our ProjectHub architecture is:

```text
Producer
   ↓
Exchange
   ↓
Queue
   ↓
Consumer
```

For example:

```text
OutboxPublisher
      ↓
projecthub.events
      ↓
 ┌────┴─────┐
 ↓          ↓
notifications analytics
 queue        queue
 ↓            ↓
worker       worker
```

RabbitMQ routes messages into queues, and consumers receive messages from those queues.  

This is excellent for:

- background jobs
- commands
- asynchronous processing
- work distribution
- notifications
- task queues
- routing messages to different consumers

---

# **2. Now Kafka**

Kafka’s fundamental model is different.

Think:

```text
Producer
    ↓
   Topic
    ↓
 ┌───────┬───────┬───────┐
 │ Part 0│ Part 1│ Part 2│
 └───────┴───────┴───────┘
    ↓
Consumer groups
```

A Kafka topic is divided into **partitions**.

Each partition is an ordered log.

Conceptually:

```text
Partition 0

offset
  0    PostCreated
  1    PostUpdated
  2    CommentCreated
  3    PostUpdated
  4    PostDeleted
```

Kafka partitions are also the fundamental unit of parallelism. Apache’s documentation notes that partition count affects the maximum consumer parallelism.  

---

# **3. RabbitMQ queue vs Kafka partition**

This is the conceptual difference I want you to remember.

### **RabbitMQ**

```text
Queue
 ↓
consume
 ↓
message is acknowledged
 ↓
message can be removed
```

### **Kafka**

```text
Partition
 ↓
message remains in the log
 ↓
consumer tracks position
 ↓
consumer can later read it again
```

RabbitMQ queues are designed around message delivery to consumers; Kafka topics are durable logs from which consumers track their position. RabbitMQ itself also now provides Streams, which use an append-only, non-destructive model distinct from ordinary RabbitMQ queues.  

---

# **4. The biggest difference: replay**

Imagine we publish:

```text
PostCreated
PostUpdated
PostDeleted
```

A RabbitMQ queue consumer processes them.

Once successfully acknowledged, the messages can be removed from the queue.

Now imagine a new analytics service starts tomorrow.

With the ordinary queue model, it doesn’t automatically get last month’s messages.

Kafka’s log-oriented model is designed around retaining records and allowing consumers to track/read from positions in the log.

That’s extremely useful for:

```text
analytics
auditing
data pipelines
event sourcing
stream processing
```

---

# **5. Example**

Imagine ProjectHub has produced:

```text
10 million events
```

and tomorrow we build:

```text
Analytics Service
```

We want:

```text
Analytics Service
      ↓
read historical events
      ↓
rebuild analytics state
```

A retained event log is extremely useful here.

You don’t necessarily need the original consumers to have been online when the events were produced.

---

# **6. RabbitMQ’s natural model**

RabbitMQ is closer to:

“Here is work that needs to be delivered to a consumer.”

Kafka is closer to:

“Here is a durable stream of events. Consumers maintain their own position in that stream.”

That’s the mental distinction.

---

# **7. Consumer groups**

Kafka introduces an important concept:

```text
Consumer Group
```

Suppose:

```text
Topic: projecthub.events
```

has:

```text
Partition 0
Partition 1
Partition 2
Partition 3
```

Consumer group:

```text
analytics-group
```

might have:

```text
Consumer A → Partition 0
Consumer B → Partition 1
Consumer C → Partition 2
Consumer D → Partition 3
```

This allows parallel consumption.

---

# **8. Multiple consumer groups**

Now something interesting.

We can have:

```text
projecthub.events
       │
 ┌─────┼──────┐
 ↓     ↓      ↓
Analytics Notifications Search
 group      group       group
```

Each consumer group maintains its own position.

So:

```text
Analytics
```

can read:

```text
event 1
event 2
event 3
```

while:

```text
Search
```

independently reads:

```text
event 1
event 2
event 3
```

This is conceptually similar to our RabbitMQ:

```text
exchange
  ├── analytics queue
  ├── notification queue
  └── search queue
```

but the underlying mechanics are quite different.

---

# **9. RabbitMQ analogy**

Our RabbitMQ system:

```text
                  Exchange
                /    |     \
               ↓     ↓      ↓
          Analytics  Notifications Search
            Queue       Queue      Queue
```

Kafka:

```text
                 Topic
                   │
          ┌────────┼────────┐
          ↓        ↓        ↓
       Analytics Notifications Search
        Group       Group      Group
```

The outcome can look similar.

The storage and consumption model are different.

---

# **10. Partitions are extremely important**

Suppose we have:

```text
Topic: posts
```

with:

```text
Partition 0
Partition 1
Partition 2
Partition 3
```

When publishing an event, Kafka can assign it to a partition based on a key.

For example:

```text
key = postId
```

Then:

```text
Post 42 → Partition 2
Post 43 → Partition 0
Post 44 → Partition 1
```

All events for Post 42 can therefore be directed to the same partition.

That gives us a natural way to achieve **per-key ordering**.

---

# **11. This connects directly to our last lesson**

Remember our problem:

```text
Post 42:
Created → Updated → Deleted
```

We wanted:

```text
same post → same processing lane
```

Kafka’s partitioning model is particularly well suited to that.

For example:

```text
key = postId
```

could produce:

```text
Post 42 → Partition 2
Post 42 → Partition 2
Post 42 → Partition 2
```

while:

```text
Post 43 → Partition 1
Post 44 → Partition 3
```

can process independently.

This is one of Kafka’s most important architectural ideas.

---

# **12. But partition count limits parallelism**

Suppose:

```text
Topic
  ↓
4 partitions
```

and:

```text
20 consumers
```

in one consumer group.

You don’t get 20-way partition parallelism.

At most roughly:

```text
4 active partition consumers
```

can process those four partitions concurrently within that group.

Apache Kafka’s documentation explicitly describes partition count as affecting maximum consumer parallelism.  

So partition count is an architectural decision.

---

# **13. RabbitMQ scaling looks different**

RabbitMQ:

```text
Queue
 ├── Consumer A
 ├── Consumer B
 ├── Consumer C
 └── Consumer D
```

Consumers compete for messages.

Kafka:

```text
Topic
 ├── Partition 0 → Consumer A
 ├── Partition 1 → Consumer B
 ├── Partition 2 → Consumer C
 └── Partition 3 → Consumer D
```

The unit of parallelism is fundamentally different.

---

# **14. Ordering**

### **RabbitMQ queue**

A queue is an ordered collection and normally behaves FIFO, but multiple consumers, acknowledgements, requeueing, and other features can affect the ordering observed by consumers.  

### **Kafka partition**

Ordering is defined within a partition.

So:

```text
Partition 2

offset 100 → A
offset 101 → B
offset 102 → C
```

gives a clear ordered sequence.

But:

```text
Partition 0 → A
Partition 1 → B
```

doesn’t give you a global ordering between A and B.

This is a very important principle:

**Kafka provides ordering per partition, not globally across a topic.**

---

# **15. RabbitMQ isn’t “unordered”**

Don’t interpret this lesson as:

RabbitMQ doesn’t support ordering.

It does.

The difference is that Kafka makes **partitioned ordered logs** a central architectural concept.

RabbitMQ’s traditional queue model makes **message delivery and work distribution** central.

---

# **16. Retention**

This is another major difference.

With Kafka, you can configure retention so records remain available for some period even after consumers have processed them.

Conceptually:

```text
7 days
30 days
90 days
```

or based on log size.

This allows:

```text
Consumer A
    ↓
read today

Consumer B
    ↓
start next week
    ↓
read retained history
```

That is one reason Kafka is so useful for event-streaming architectures.

---

# **17. RabbitMQ can also retain/replay in other ways**

RabbitMQ isn’t limited to “message disappears forever.”

It now has Streams, which are persistent replicated append-only structures with non-destructive consumer semantics, allowing messages to be read repeatedly until they expire.  

So the comparison is not:

```text
RabbitMQ = no replay
Kafka = replay
```

That’s too simplistic.

The better comparison is:

```text
RabbitMQ queues
    vs
Kafka log

and separately:

RabbitMQ Streams
    vs
Kafka-style streaming workloads
```

---

# **18. RabbitMQ vs Kafka: mental model**

|**Concept**|**RabbitMQ Queue**|**Kafka**|
|---|---|---|
|Primary abstraction|Queue/message delivery|Partitioned event log|
|Routing|Exchanges + bindings|Topics + partitions|
|Consumption|Consumer receives delivery|Consumer tracks position|
|Parallelism|Competing consumers|Partitions + consumer groups|
|Ordering|Queue ordering with caveats|Per-partition ordering|
|Replay|Not the primary queue model|Core capability|
|Work queues|Excellent fit|Possible, but different model|
|Event streaming|Possible|Core use case|
|Routing patterns|Very rich|Usually topic/key based|
|Retained history|Not the core queue model|Core model|

---

# **19. When I’d naturally reach for RabbitMQ**

Imagine ProjectHub needs:

```text
POST /projects/7/reports
```

The API creates a report-generation job.

We want:

```text
API
 ↓
RabbitMQ
 ↓
Report Worker
```

The worker performs:

```text
generate PDF
upload file
send notification
```

This is a classic work-queue problem.

The conceptual question is:

“Who should do this job?”

RabbitMQ fits naturally.

---

# **20. When I’d naturally reach for Kafka**

Now imagine ProjectHub has:

```text
500 million events/day
```

and several independent systems need the event stream:

```text
ProjectHub
     ↓
Kafka
 ┌───┼────┬──────┐
 ↓   ↓    ↓      ↓
Analytics
Search
Data Lake
Fraud
ML
```

And tomorrow we add another consumer:

```text
Recommendation Engine
```

which wants to replay six months of history.

That’s a much more natural Kafka-shaped problem.

---

# **21. Don’t choose Kafka just because traffic is high**

This is a common beginner mistake:

“Kafka is for big systems, therefore if my application grows I should use Kafka.”

Not necessarily.

The architecture should follow the workload.

A system processing:

```text
10,000 messages/day
```

might legitimately need Kafka if it requires durable event streams and replay.

A system processing:

```text
10 million jobs/day
```

might still use RabbitMQ if its fundamental problem is work distribution.

Throughput alone isn’t the decision.

---

# **22. Kafka is not simply a better RabbitMQ**

This is probably the most important misconception to eliminate.

Think:

```text
RabbitMQ:
"Deliver this message."

Kafka:
"Store this event in this ordered partitioned log."
```

Those are different abstractions.

---

# **23. Example: notifications**

Suppose:

```text
PostCreated
```

should cause:

```text
Notification Service
```

to send a notification.

RabbitMQ:

```text
PostCreated
     ↓
notifications queue
     ↓
worker
```

This is very natural.

Kafka could also do:

```text
PostCreated
     ↓
Kafka topic
     ↓
notification consumer group
```

but now you’re using a log-based streaming system for a problem that may fundamentally be a work queue.

That’s not wrong.

It just introduces a different operational model.

---

# **24. Example: analytics**

Now:

```text
PostCreated
PostUpdated
CommentCreated
CommentDeleted
...
```

need to feed:

```text
real-time analytics
```

while also being:

```text
replayable
```

and perhaps consumed by:

```text
data warehouse pipeline
machine learning
search indexing
fraud detection
```

Kafka starts looking very natural.

---

# **25. Kafka Streams**

Kafka also has a stream-processing ecosystem.

For example:

```text
Kafka
 ↓
Kafka Streams
 ↓
aggregate events
 ↓
materialized state
```

Apache Kafka’s official documentation lists Kafka Streams as part of the Kafka ecosystem.  

This lets applications perform operations such as:

```text
count
aggregate
join
filter
window
transform
```

over event streams.

That’s a different programming model from a traditional RabbitMQ worker.

---

# **26. The “event log” mindset**

With RabbitMQ, you might think:

```text
message = task
```

With Kafka:

```text
record = fact/event in a stream
```

For example:

```text
UserRegistered
PostCreated
PostUpdated
CommentCreated
```

can form a historical stream of what happened.

Multiple consumers can derive their own views from that history.

---

# **27. Event sourcing connection**

This is where Kafka starts connecting to another architecture concept.

Imagine:

```text
AccountCreated
MoneyDeposited
MoneyWithdrawn
MoneyDeposited
```

Instead of storing only:

```text
balance = 750
```

we could maintain an event history.

Then:

```text
events
 ↓
replay
 ↓
derive current state
```

That’s event sourcing.

Kafka is often used as part of architectures involving event streams, though Kafka itself does **not** automatically make an application event-sourced.

Important distinction.

---

# **28. RabbitMQ can still be part of an event-driven system**

Don’t conclude:

```text
event-driven = Kafka
```

Our ProjectHub system is already event-driven:

```text
PostService
   ↓
Outbox
   ↓
RabbitMQ
   ↓
Notification
Analytics
```

RabbitMQ is perfectly capable of transporting domain events.

The choice depends on the required messaging semantics and workload.

---

# **29. What happens to our Outbox?**

Interestingly, the Outbox Pattern doesn’t disappear if we choose Kafka.

We still have the dual-write problem:

```text
PostgreSQL
    +
Kafka
```

We don’t want:

```text
DB COMMIT
   ↓
Kafka publish fails
```

So:

```text
Post + Outbox
       ↓
     COMMIT
       ↓
 Outbox Publisher
       ↓
     Kafka
```

is still a valid architecture.

The transport changes.

The transactional problem doesn’t.

---

# **30. ProjectHub with Kafka**

Our architecture would become:

```text
                       PostgreSQL
                           │
                     Post + Outbox
                           │
                         COMMIT
                           │
                           ▼
                    Kafka Producer
                           │
                           ▼
                  projecthub.events
                  ┌────┬────┬────┐
                  │    │    │    │
                  P0   P1   P2   P3
                  │    │    │    │
                  └────┴────┴────┘
                           │
                  ┌────────┼────────┐
                  ↓        ↓        ↓
              Analytics Search Notifications
                Group     Group      Group
```

This is a very different topology from our RabbitMQ queue topology.

---

# **31. Which would I use for ProjectHub?**

For the ProjectHub architecture we’ve been building, **RabbitMQ is a perfectly reasonable choice** for asynchronous commands, notifications, background jobs, and relatively straightforward domain-event delivery.

If ProjectHub later becomes primarily a high-volume event-streaming platform with many independent consumers, long retention/replay requirements, partition-key ordering, and stream processing, Kafka becomes much more compelling.

That’s an architectural comparison—not a universal winner.

---

# **32. One more interesting point: RabbitMQ Streams**

Modern RabbitMQ also supports Streams and Super Streams. Streams are persistent, replicated, append-only structures; Super Streams partition a stream.  

So modern RabbitMQ actually overlaps more with Kafka than the classic:

```text
RabbitMQ = queues
Kafka = streams
```

comparison suggests.

But the systems still have different APIs, operational models, ecosystems, and design philosophies.

---

# **33. What you should remember for interviews**

If someone asks:

“RabbitMQ or Kafka?”

Don’t answer:

“Kafka is faster.”

That’s an incomplete answer.

Instead discuss:

### **RabbitMQ**

```text
message broker
exchanges
queues
routing
acknowledgements
work distribution
```

### **Kafka**

```text
distributed event log
topics
partitions
consumer groups
offsets
retention
replay
stream processing
```

Then ask:

What does the application actually need?

That’s the senior-engineer answer.

---

# **34. The decision matrix**

|**Requirement**|**RabbitMQ Queue**|**Kafka**|
|---|---|---|
|Background jobs|Excellent fit|Possible|
|Complex routing|Strong|Simpler topic/key model|
|Competing workers|Natural|Consumer groups|
|Long event retention|Not primary|Core strength|
|Replay historical events|Not primary|Core strength|
|Per-key ordered stream|Possible with design|Natural via partition key|
|Many independent consumers|Possible|Natural via consumer groups|
|Traditional async commands|Natural|Possible|
|Stream processing|Possible via Streams|Core ecosystem|
|Event-driven architecture|Yes|Yes|

Again, this is about **fit**, not ranking.

---

# **35. Your next mental model**

You’ve now encountered three increasingly different concepts:

### **Queue**

```text
"Someone needs to process this."
```

### **Event**

```text
"Something happened."
```

### **Stream**

```text
"Here is the durable sequence of things that happened."
```

RabbitMQ can support all three patterns in different ways.

Kafka is particularly centered around the third.

---

# **Exercise 72**

Don’t write code yet.

### **1.**

Explain the difference between:

```text
RabbitMQ queue
```

and:

```text
Kafka partition
```

in your own words.

### **2.**

Suppose:

```text
PostCreated
```

must be consumed by:

```text
Notifications
Analytics
Search
Data Warehouse
```

Explain how you would model that with RabbitMQ and with Kafka.

### **3.**

Suppose Search starts today but wants to process **six months of existing events**.

Why does Kafka’s log model fit that requirement naturally?

### **4.**

Suppose ProjectHub has:

```text
100,000 background PDF-generation jobs
```

and each job should be processed by exactly one available worker.

Which messaging model naturally fits this requirement, and why?

### **5.**

Suppose events for the same `postId` must remain ordered, but different posts should process in parallel.

Explain how Kafka’s partition key can help.

### **6.**

Finally:

**Why doesn’t switching RabbitMQ → Kafka eliminate the need for the Outbox Pattern?**

This last question is particularly important. If you can answer it clearly, you’ve understood the distinction between **database consistency** and **message transport**.

---

After this, we’ll return to ProjectHub and build **Lesson 73 — Kafka fundamentals in practice**, where we’ll create a topic, partitions, producers, consumer groups, offsets, and then compare the actual Spring Boot code against the RabbitMQ code we’ve already written.