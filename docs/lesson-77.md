---
title: "Lesson 77: Kafka vs RabbitMQ in the Real ProjectHub Architecture"
sidebar_position: 77
---

We’ve now learned enough Kafka fundamentals to make an actual architecture decision.

The question isn’t:

“Is Kafka better than RabbitMQ?”

That’s the wrong question.

The useful question is:

**“Which messaging model fits this particular workload?”**

---

## **1. Start with the fundamental difference**

Think of RabbitMQ like this:

```text
Producer
   ↓
Exchange
   ↓
Queue
   ↓
Consumer
```

The queue is primarily about **delivering work to consumers**.

Kafka is different:

```text
Producer
   ↓
Topic
   ↓
Partitions
   ↓
Consumers
```

The topic is a **durable event log**. Consumers track their positions and can independently consume the same retained events.

That difference drives most of the architectural decisions we’ll make.

Spring Kafka 4.1.1 currently exposes the Kafka concerns we’ve been discussing—sending, receiving, partitions, seeking, serialization, error handling, transactions, and monitoring—as first-class parts of its API.  

---

# **2. Imagine ProjectHub**

Our application has:

```text
Users
Projects
Posts
Comments
Notifications
Search
Analytics
Audit history
```

And suppose a post is created:

```text
POST /projects/10/posts
```

The database transaction creates:

```text
Post
OutboxEvent
```

Then the outbox publisher produces:

```text
PostCreated
```

Now we have multiple consumers.

```text
                 Kafka
                   │
             PostCreated
                   │
       ┌───────────┼───────────┐
       ↓           ↓           ↓
 Notifications   Search     Analytics
```

This is where Kafka becomes particularly attractive.

---

# **3. One event, many independent consumers**

Suppose:

```text
PostCreated
```

is published once.

We can have:

```text
notifications group
search group
analytics group
```

Each group maintains its own consumption position.

Conceptually:

```text
Kafka topic
     │
     ├── notifications
     │
     ├── search
     │
     └── analytics
```

The notification service doesn’t “consume” the event away from search.

Each consumer group has its own view of the log.

That’s one of Kafka’s major architectural strengths.

---

# **4. What would RabbitMQ look like?**

With traditional RabbitMQ:

```text
PostCreated
      ↓
exchange
      │
 ┌────┴─────┐
 ↓          ↓
queue A    queue B
 ↓          ↓
notification search
```

This is also perfectly valid.

RabbitMQ’s routing model can be extremely good for:

```text
commands
tasks
work queues
notifications
background jobs
```

So both technologies can implement:

```text
PostCreated → notifications
PostCreated → search
```

The important difference is what happens **after delivery**.

---

# **5. Kafka’s replay model**

Suppose analytics accidentally has a bug.

It processed:

```text
offset 0
offset 1
offset 2
...
offset 800000
```

You deploy a fixed version.

With Kafka, the consumer can potentially reset/reposition its offset and process retained records again.

Conceptually:

```text
Kafka log

0
1
2
3
...
800000
```

The consumer can say:

```text
"Start me from offset 700000."
```

That’s fundamentally different from thinking of the message as simply “delivered and gone.”

This retained-log model is one reason Kafka works naturally for analytics and event-stream processing.

---

# **6. Example: rebuilding search**

Imagine our search index is accidentally deleted.

We still have:

```text
PostCreated
PostUpdated
PostDeleted
...
```

in Kafka according to the topic’s retention policy.

We can create a new search consumer group:

```text
search-rebuild-v2
```

and replay the relevant history.

Conceptually:

```text
Kafka
  ↓
search-rebuild-v2
  ↓
rebuild index
```

That’s extremely useful.

---

# **7. But don’t misunderstand retention**

Kafka isn’t an infinite database.

Events are retained according to topic configuration and Kafka’s retention/compaction mechanisms.

So:

```text
Kafka
```

isn’t automatically:

```text
permanent business history
```

If you require permanent audit history, you should deliberately store that history somewhere appropriate.

---

# **8. Where RabbitMQ fits better**

Imagine:

```text
GenerateMonthlyReport
```

You don’t necessarily need:

```text
10 different independent consumers
```

You might simply want:

```text
API
 ↓
RabbitMQ
 ↓
report queue
 ↓
worker
 ↓
generate PDF
```

That’s a very natural work-queue problem.

Similarly:

```text
SendPasswordResetEmail
GenerateThumbnail
ResizeImage
ProcessPaymentWebhook
```

can naturally fit a queue-oriented model.

---

# **9. Commands vs events**

This distinction is extremely useful.

### **Command**

A command says:

“Please do this.”

Example:

```text
GenerateProjectReport
```

Usually you want **one worker** to perform it.

### **Event**

An event says:

“This already happened.”

Example:

```text
ProjectCreated
```

Multiple independent systems may care.

So:

```text
Command
→ work distribution

Event
→ notification of something that happened
```

This isn’t an absolute rule, but it’s an excellent architectural starting point.

---

# **10. ProjectHub example**

### **Command**

```text
GenerateThumbnail
```

Could be:

```text
RabbitMQ
   ↓
thumbnail-worker
```

### **Event**

```text
PostCreated
```

Could be:

```text
Kafka
 ├── notifications
 ├── search
 ├── analytics
 └── audit
```

That’s a very reasonable split.

---

# **11. What about notifications?**

This is where either technology can work.

For example:

```text
PostCreated
   ↓
notification service
   ↓
send email
```

RabbitMQ is perfectly natural:

```text
notification queue
```

Kafka is also possible:

```text
notifications consumer group
```

The deciding factors become things like:

- Do we need replay?
- How many independent consumers?
- Is this primarily work distribution?
- How important is retained event history?
- Do we need stream processing?
- How much operational complexity are we willing to accept?

---

# **12. What about analytics?**

Kafka becomes particularly natural here.

Imagine:

```text
PostCreated
PostViewed
CommentCreated
UserLoggedIn
ProjectCreated
```

Millions of events accumulate.

Then:

```text
Kafka
 ↓
analytics consumer
 ↓
aggregation
 ↓
data warehouse / analytics DB
```

You may later add:

```text
Kafka
 ├── analytics-v1
 ├── analytics-v2
 └── fraud-detection
```

without changing the producers.

That retained event-stream model is a strong fit.

---

# **13. What about search?**

Search is interesting.

Suppose:

```text
PostCreated
PostUpdated
PostDeleted
```

go to:

```text
search consumer
```

The consumer updates Elasticsearch/OpenSearch.

Kafka works well because if the search system is rebuilt, you can replay events—or use another source of truth if the event history isn’t sufficient.

---

# **14. What about audit?**

Audit is another interesting case.

Suppose we publish:

```text
ProjectCreated
MemberAdded
MemberRemoved
PostDeleted
PermissionChanged
```

A dedicated:

```text
audit
```

consumer can persist those events.

Kafka can provide a convenient event stream, but remember:

If audit records are legally/business-critical historical records, don’t rely solely on Kafka retention as your permanent storage strategy.

Store the required audit history in durable business storage as appropriate.

---

# **15. Could we use both?**

Absolutely.

A mature architecture can look like:

```text
                 ProjectHub
                     │
        ┌────────────┴────────────┐
        │                         │
      RabbitMQ                  Kafka
        │                         │
        ↓                         ↓
    Commands                  Domain events
    Jobs                      Analytics
    Workers                   Search
                              Notifications
                              Event history
```

There’s nothing inherently wrong with having both.

The mistake would be introducing both without a clear reason.

---

# **16. Don’t create “Kafka everywhere”**

For example:

```text
HTTP request
   ↓
Kafka
   ↓
RabbitMQ
   ↓
Kafka
   ↓
service
```

just because the architecture diagram looks impressive.

Every broker adds:

```text
operations
monitoring
failure modes
security
deployment
debugging
serialization
retries
DLTs
```

Use messaging when it solves a real architectural problem.

---

# **17. Our ProjectHub decision**

For the course project, let’s make a deliberate choice.

### **Kafka**

We’ll use Kafka for:

```text
PostCreated
PostUpdated
PostDeleted
ProjectCreated
ProjectMemberChanged
```

because these are domain events that multiple independent consumers may care about.

Architecture:

```text
PostgreSQL
    ↓
Outbox
    ↓
Kafka
    ├── notifications
    ├── search
    ├── analytics
    └── audit
```

---

# **18. RabbitMQ**

We’ll use RabbitMQ for work that is more naturally command/task oriented.

For example:

```text
GenerateReport
SendEmail
GenerateThumbnail
RebuildSpecificProjection
```

Architecture:

```text
Service
   ↓
RabbitMQ
   ↓
worker queue
   ↓
worker
```

Again, this isn’t because RabbitMQ _can’t_ do events or Kafka _can’t_ do tasks.

It’s because the underlying models fit these workloads differently.

---

# **19. A very important architecture distinction**

Consider:

```text
GenerateReport
```

If the worker crashes after processing it, we probably want:

```text
retry
```

and eventually:

```text
DLQ
```

That’s a queue/work-processing problem.

Now consider:

```text
PostCreated
```

Maybe five systems independently care about it.

That’s a retained event-stream problem.

Thinking in terms of **work vs facts** is often more useful than thinking in terms of “which broker is more powerful?”

---

# **20. Now let’s move to our next major problem**

We’ve got:

```text
PostCreated
```

But six months later, the event changes.

Originally:

```json
{
  "eventId": "...",
  "postId": 42,
  "projectId": 10,
  "authorId": 7
}
```

Then someone says:

“We need the post title in the event.”

Version 2 becomes:

```json
{
  "eventId": "...",
  "postId": 42,
  "projectId": 10,
  "authorId": 7,
  "title": "Hello Kafka"
}
```

Looks harmless.

But production looks like:

```text
Producer v2
      ↓
Kafka
      ↓
Consumer A v1
Consumer B v2
Consumer C v1
```

Now we have a **schema evolution** problem.

---

# **21. Why deployments make this difficult**

In a real Kubernetes deployment, you rarely replace every component simultaneously.

You might have:

```text
10 notification Pods
```

and perform a rolling deployment:

```text
Pod 1 → v2
Pod 2 → v2
Pod 3 → v1
...
```

Meanwhile producers are already publishing the new event format.

So for a period of time:

```text
Producer v2
      ↓
Kafka
      ↓
Consumers v1 + v2
```

Your message format must tolerate this.

---

# **22. JSON gives us some flexibility**

Spring Kafka currently provides JSON serializers/deserializers and configurable type information, including behavior around unknown JSON properties. Its current 4.1.1 documentation notes that the enhanced Jackson mapper used by the JSON components disables `FAIL_ON_UNKNOWN_PROPERTIES`, which can help a consumer tolerate fields it doesn’t know about.  

So if v2 adds:

```json
"title": "Hello"
```

a suitably configured older consumer may simply ignore it.

That’s useful.

But don’t mistake that for a complete schema-evolution strategy.

---

# **23. Adding a field isn’t always safe**

Suppose v1:

```json
{
  "postId": 42
}
```

v2:

```json
{
  "postId": 42,
  "title": "Hello"
}
```

Potentially safe.

Now suppose v2 changes:

```json
"postId": 42
```

into:

```json
"postId": "42"
```

That’s a much more dangerous change.

Or:

```text
authorId
```

becomes:

```text
author
```

An old consumer may fail.

---

# **24. Think in compatibility categories**

When changing an event, ask:

### **Can old consumers read new events?**

That’s **backward compatibility** from the consumer perspective.

### **Can new consumers read old events?**

That’s **forward compatibility**.

And sometimes we need both.

A rolling deployment works much more safely when the new schema is compatible with records still being produced or retained under the old schema.

---

# **25. A safer evolution strategy**

Suppose we need:

```text
title
```

Instead of changing:

```text
PostCreated v1
```

destructively, create:

```text
PostCreated v2
```

or introduce a version field:

```json
{
  "eventId": "...",
  "eventType": "PostCreated",
  "version": 2,
  "postId": 42,
  "projectId": 10,
  "authorId": 7,
  "title": "Hello Kafka"
}
```

Now the consumer knows what contract it’s looking at.

---

# **26. But don’t version every tiny thing blindly**

You don’t necessarily need:

```text
PostCreatedV1
PostCreatedV2
PostCreatedV3
PostCreatedV4
...
```

as separate Java classes forever.

A good event contract should evolve intentionally.

For example:

```java
public record PostCreatedEvent(
    UUID eventId,
    long version,
    Instant occurredAt,
    Long postId,
    Long projectId,
    Long authorId,
    String title
) {}
```

Here:

```text
version
```

refers to the **event contract version**, not the aggregate version we discussed earlier.

Those are different concepts.

---

# **27. Important: two different versions**

We’ve now got:

### **Event schema version**

```text
version = 2
```

Means:

“This event follows contract version 2.”

### **Aggregate version**

```text
aggregateVersion = 18
```

Means:

“This is the 18th state transition/version of Post 42.”

Don’t mix them.

A richer envelope could therefore look like:

```java
public record EventEnvelope<T>(
    UUID eventId,
    String eventType,
    String aggregateType,
    String aggregateId,
    long schemaVersion,
    long aggregateVersion,
    Instant occurredAt,
    T data
) {}
```

That distinction becomes extremely valuable in production systems.

---

# **28. JSON vs Avro vs Protobuf**

We’re not implementing these yet, but you should know the landscape.

### **JSON**

```text
easy
human-readable
flexible
larger messages
less formal contract
```

Excellent for learning and many internal systems.

Spring Kafka has first-class JSON serialization/deserialization support.  

### **Avro**

```text
compact
schema-based
strong evolution tooling
common with Kafka ecosystems
```

### **Protobuf**

```text
compact
strongly typed
excellent cross-language contracts
excellent evolution model
```

The key concept isn’t the serialization format.

It’s:

**Your event schema is an API contract.**

---

# **29. This changes how you think about Kafka**

Before:

```text
Kafka = messaging system
```

Now:

```text
Kafka =
durable event log
+
consumer groups
+
partitioning
+
replay
+
event contracts
```

That’s why schema evolution matters so much.

---

# **30. Our next architectural layer**

Our ProjectHub pipeline is now:

```text
HTTP
 ↓
Service
 ↓
PostgreSQL transaction
 ├── business data
 └── outbox
       ↓
   Outbox publisher
       ↓
      Kafka
       ↓
   Event contract
       ↓
 ┌─────┼─────────┐
 ↓     ↓         ↓
search analytics notifications
```

And each consumer needs:

```text
deserialization
     ↓
validation
     ↓
idempotency
     ↓
business processing
     ↓
retry
     ↓
DLT
```

That’s a serious production-grade event pipeline.

---

# **31. One subtle thing about Spring Kafka**

Don’t tightly couple your Kafka contract to your Java package names.

Spring Kafka’s JSON support can put type information into Kafka headers and supports type mappings.  

But imagine:

```text
com.projecthub.events.PostCreatedEvent
```

becomes:

```text
com.projecthub.messaging.PostCreatedEvent
```

If consumers depend directly on Java class metadata, you’ve created an unnecessary coupling between services.

For independently deployed services, prefer a deliberate **wire contract**:

```text
eventType = "post.created"
schemaVersion = 1
```

rather than treating:

```text
Java package + Java class
```

as the public API.

---

# **32. Our mental model from now on**

Think of a Kafka event as:

```text
┌──────────────────────────────┐
│          Event               │
├──────────────────────────────┤
│ eventId                      │
│ eventType                    │
│ schemaVersion                │
│ aggregateType                │
│ aggregateId                  │
│ aggregateVersion             │
│ occurredAt                   │
│ data                         │
└──────────────────────────────┘
```

And remember:

```text
eventId
    ↓
deduplication

aggregateId
    ↓
partitioning / grouping

aggregateVersion
    ↓
ordering / stale-event detection

schemaVersion
    ↓
contract evolution
```

These four concepts solve four different problems.

---

# **33. Exercise 77**

Let’s make this one architectural.

### **Exercise A**

For each workload, choose **Kafka, RabbitMQ, or either**, and explain why:

```text
1. Generate PDF report
2. PostCreated event consumed by analytics
3. Send password reset email
4. Search index updates
5. Rebuild analytics from historical events
6. Resize uploaded image
7. Audit ProjectCreated / ProjectDeleted events
```

Don’t worry about giving the “perfect” answer. Explain your reasoning.

---

### **Exercise B**

We currently have:

```json
{
  "eventId": "123",
  "schemaVersion": 1,
  "postId": 42,
  "authorId": 7
}
```

We need to add:

```text
title
```

Would you consider this a potentially compatible change?

Then consider changing:

```text
authorId
```

from a number to a string.

Why is that more dangerous?

---

### **Exercise C — important**

Explain the difference between:

```text
schemaVersion
aggregateVersion
eventId
aggregateId
```

using:

```text
Post 42
```

as your example.

Once you can explain those four without mixing them together, you’re ready for the next step.

---

## **Next: Lesson 78**

We’ll turn this into actual code:

**Kafka Event Contracts + Schema Evolution in ProjectHub**

We’ll build a proper event envelope, discuss JSON compatibility, show how producer/consumer versions coexist during rolling deployments, and then introduce **Avro/Protobuf and Schema Registry**—including _why_ teams adopt them rather than simply adding more fields to JSON.

Spring Kafka 4.1.1’s current serialization layer supports JSON plus multiple serializer/deserializer approaches, so we’ll start with the simplest contract that teaches the underlying design before introducing schema-registry tooling.