---
title: "Lesson 78: Kafka Event Contracts & Schema Evolution"
sidebar_position: 78
---

This lesson is about treating Kafka messages as **APIs between independently deployed systems**.

So far we had:

```text
PostgreSQL
   ↓
Outbox
   ↓
Kafka
   ↓
notifications / search / analytics / audit
```

Now we need to answer:

What exactly is the contract of the message flowing through Kafka?

Spring Kafka 4.1.1 currently provides JSON serializers/deserializers, while schema-registry ecosystems commonly support Avro, Protobuf, and JSON Schema with compatibility checking.  

---

## **1. Your Kafka event is an API**

Suppose we publish:

```json
{
  "eventId": "8f...",
  "eventType": "post.created",
  "schemaVersion": 1,
  "aggregateId": "42",
  "aggregateVersion": 1,
  "occurredAt": "2026-10-01T10:00:00Z",
  "data": {
    "postId": 42,
    "projectId": 10,
    "authorId": 7,
    "title": "Hello Kafka"
  }
}
```

The important realization is:

```text
Kafka event
      ↓
API contract
```

It isn’t merely an internal Java object.

Your producer might be Java today.

Your consumer might be Python tomorrow.

Or another team might consume it.

Therefore this is dangerous:

```text
Producer Java class
        ↓
Consumer Java class
```

because you’ve accidentally made the Java implementation the contract.

Instead:

```text
Producer
   ↓
wire contract
   ↓
Kafka
   ↓
wire contract
   ↓
Consumer
```

---

# **2. Separate the envelope from the data**

I recommend thinking about events in two layers.

### **Envelope**

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

### **Payload**

```java
public record PostCreatedData(
    Long postId,
    Long projectId,
    Long authorId,
    String title
) {}
```

Then:

```java
EventEnvelope<PostCreatedData>
```

Conceptually:

```text
┌───────────────────────────────┐
│ EventEnvelope                 │
├───────────────────────────────┤
│ eventId                       │
│ eventType                     │
│ aggregateType                 │
│ aggregateId                   │
│ schemaVersion                 │
│ aggregateVersion              │
│ occurredAt                    │
├───────────────────────────────┤
│ data                          │
│   postId                      │
│   projectId                   │
│   authorId                    │
│   title                       │
└───────────────────────────────┘
```

This separation becomes extremely useful as the system grows.

---

# **3. Don’t confuse the versions**

We now have **two different kinds of version**.

### **Schema version**

```text
schemaVersion = 2
```

Means:

“What shape does this event contract have?”

### **Aggregate version**

```text
aggregateVersion = 18
```

Means:

“Which state transition of Post 42 is this?”

For example:

```text
Post 42

aggregateVersion 1
→ Created

aggregateVersion 2
→ TitleChanged

aggregateVersion 3
→ ContentChanged

...

aggregateVersion 18
→ Updated
```

Meanwhile the schema could remain:

```text
schemaVersion = 2
```

for all of them.

---

# **4. And eventId is something else again**

```text
eventId = 550e8400-...
```

means:

“What exact event is this?”

It’s primarily useful for idempotency.

So we now have:

|**Field**|**Question answered**|
|---|---|
|`eventId`|Have I processed this exact event?|
|`aggregateId`|Which entity does it belong to?|
|`aggregateVersion`|Which version/state transition is it?|
|`schemaVersion`|What contract shape does it use?|

These should **not** be collapsed into one concept.

---

# **5. Start simple: JSON**

For our ProjectHub learning system, we’ll initially use JSON.

Spring Kafka provides `JacksonJsonSerializer` and `JacksonJsonDeserializer` for converting Java objects to/from JSON. Its JSON components also support handling unknown properties and type mappings.  

That gives us something like:

```json
{
  "eventId": "...",
  "eventType": "post.created",
  "schemaVersion": 1,
  "aggregateType": "post",
  "aggregateId": "42",
  "aggregateVersion": 1,
  "occurredAt": "...",
  "data": {
    "postId": 42,
    "projectId": 10,
    "authorId": 7
  }
}
```

It’s easy to inspect:

```text
Kafka
 ↓
JSON
 ↓
logs
 ↓
debugging
```

For learning—and many internal systems—that simplicity is valuable.

---

# **6. The first schema change**

Imagine v1:

```json
{
  "postId": 42,
  "projectId": 10,
  "authorId": 7
}
```

We need:

```text
title
```

So v2 becomes:

```json
{
  "postId": 42,
  "projectId": 10,
  "authorId": 7,
  "title": "Hello Kafka"
}
```

This is an **additive change**.

Generally, additive changes are easier to make compatible than destructive changes.

An older consumer can potentially ignore the new field.

Spring’s enhanced JSON mapper disables Jackson’s `FAIL_ON_UNKNOWN_PROPERTIES` by default, which supports this style of tolerance when using its JSON components.  

---

# **7. But there’s a trap**

Suppose the consumer does this:

```java
public void consume(PostCreatedData event) {
    String title = event.title();
}
```

If the old event doesn’t have a title, what happens?

Potentially:

```text
null
```

That’s technically deserializable.

But semantically?

Maybe the application crashes later.

So:

**Serialization compatibility doesn’t automatically mean business compatibility.**

You still need sensible defaults and validation.

---

# **8. A much more dangerous change**

v1:

```json
{
  "authorId": 7
}
```

v2:

```json
{
  "authorId": "7"
}
```

You’ve changed:

```text
number → string
```

That’s a contract change.

Or:

```text
projectId
```

becomes:

```text
project
```

That’s even more obviously breaking.

Or:

```text
title
```

is removed entirely.

Existing consumers may break.

---

# **9. Another dangerous change: changing meaning**

This is particularly nasty.

Suppose v1 says:

```text
authorId = user who created the post
```

Then someone changes the meaning to:

```text
authorId = user who last modified the post
```

The JSON shape hasn’t changed.

Schema compatibility tooling might not save you.

But the **business contract** has changed.

So schema evolution has two dimensions:

```text
technical compatibility
        +
semantic compatibility
```

Both matter.

---

# **10. Rolling deployments make this real**

Suppose production has:

```text
Producer v1
Consumer v1
```

Then you deploy:

```text
Producer v2
```

before upgrading all consumers.

For a while:

```text
Producer v2
      ↓
    Kafka
      ↓
┌─────┴──────┐
↓            ↓
Consumer v1  Consumer v2
```

Therefore the new producer needs to produce events that old consumers can safely handle.

This is why **backward-compatible evolution** is so important.

---

# **11. Compatibility terminology**

There are several compatibility directions.

### **Backward compatibility**

New consumers can read old messages.

```text
old event
   ↓
new consumer
```

### **Forward compatibility**

Old consumers can read new messages.

```text
new event
   ↓
old consumer
```

### **Full compatibility**

Both directions work.

```text
old event ↔ new consumer
new event ↔ old consumer
```

Schema Registry systems define these compatibility modes explicitly; Confluent’s current documentation lists `BACKWARD`, `FORWARD`, `FULL`, and their transitive variants.  

---

# **12. What does BACKWARD mean in practice?**

Suppose:

```text
Schema 1
```

then:

```text
Schema 2
```

With backward compatibility:

```text
new consumer/schema 2
        ↓
can read
        ↓
old data/schema 1
```

This is particularly useful with Kafka because old records remain available according to topic retention.

A new consumer might need to process:

```text
2026-09-01 events
```

using the schema from:

```text
2026-10-01
```

So compatibility isn’t merely about rolling deployments.

It’s also about **replaying history**.

---

# **13. Why Kafka makes this especially important**

Imagine:

```text
Kafka
├── event from 3 months ago
├── event from 2 months ago
├── event from yesterday
└── event from today
```

Your new consumer might read all of them.

Therefore your new application version needs to understand historical event formats—or you need an explicit migration/versioning strategy.

That’s one reason schema contracts become increasingly important as event-driven systems mature.

---

# **14. Enter Schema Registry**

Now we introduce another component:

```text
Producer
   │
   ├──────────────→ Kafka
   │
   └──────────────→ Schema Registry
```

The registry stores schemas.

Conceptually:

```text
post-created-value
    │
    ├── v1
    ├── v2
    └── v3
```

When a new schema is registered, the registry can check whether it satisfies the configured compatibility rules before accepting it.  

---

# **15. What does the registry actually solve?**

Without a registry:

```text
Developer changes event
       ↓
compile
       ↓
deploy
       ↓
oops
```

With a compatibility check:

```text
Developer changes schema
       ↓
Schema Registry
       ↓
compatibility check
       ↓
allowed / rejected
```

That moves an important class of errors from:

```text
production runtime
```

toward:

```text
development / deployment
```

That’s a huge improvement.

---

# **16. Schema Registry isn’t Kafka**

Don’t confuse:

```text
Kafka
```

with:

```text
Schema Registry
```

Kafka stores the event records.

Schema Registry stores and manages schemas.

Conceptually:

```text
                 ┌───────────────┐
Producer ───────→│     Kafka     │
                 │   messages    │
                 └───────────────┘
                       ↑
                       │
                 schema reference
                       │
                 ┌───────────────┐
                 │Schema Registry│
                 │   contracts   │
                 └───────────────┘
```

---

# **17. Avro**

One popular Kafka ecosystem choice is **Avro**.

Instead of sending arbitrary JSON:

```json
{
  "postId": 42,
  "authorId": 7
}
```

you define a schema.

Conceptually:

```text
PostCreated
├── postId: long
├── projectId: long
├── authorId: long
└── title: string
```

The serializer/deserializer uses the schema to encode/decode the data.

Avro was designed with schema evolution in mind, and Schema Registry provides compatibility checks for it.  

---

# **18. Protobuf**

Another choice is:

```text
Protocol Buffers
```

You define a message contract such as:

```proto
message PostCreated {
    int64 post_id = 1;
    int64 project_id = 2;
    int64 author_id = 3;
    string title = 4;
}
```

The field numbers are important.

You don’t casually reuse them for unrelated fields.

Protobuf has its own compatibility rules, and current Confluent documentation recommends `BACKWARD_TRANSITIVE` in many Schema Registry Protobuf setups because adding new message types isn’t forward-compatible in the same way.  

---

# **19. JSON Schema**

There’s also:

```text
JSON Schema
```

which keeps JSON’s conceptual model while adding a formal schema.

So broadly:

```text
JSON
   → simple/flexible

JSON Schema
   → JSON + formal schema

Avro
   → schema-oriented binary format

Protobuf
   → strongly typed compact schema format
```

Schema Registry supports all three formats and applies format-specific compatibility rules.  

---

# **20. So which one should ProjectHub use?**

For **our learning project**, we’re going to do this in stages:

### **Stage 1**

```text
JSON
+
explicit event envelope
+
schemaVersion
+
good compatibility discipline
```

This teaches the architecture without introducing another infrastructure component too early.

### **Stage 2**

```text
Schema Registry
+
Avro or Protobuf
```

This teaches production-grade schema governance.

That’s deliberate.

Don’t introduce five technologies just because production systems sometimes use five technologies.

---

# **21. A subtle design choice: one topic or many?**

We currently have:

```text
projecthub.events
```

containing:

```text
PostCreated
PostUpdated
PostDeleted
ProjectCreated
...
```

That’s possible.

Another architecture is:

```text
projecthub.post-events
projecthub.project-events
projecthub.comment-events
```

Or even:

```text
projecthub.post.created
projecthub.post.updated
projecthub.post.deleted
```

There isn’t one universal answer.

Topic boundaries should reflect:

```text
consumer needs
retention requirements
partitioning
throughput
security
schema organization
operational ownership
```

---

# **22. Event type is still useful**

Even with schemas, I like an explicit event type:

```json
{
  "eventType": "post.created"
}
```

rather than making consumers infer everything from:

```text
Java class name
```

This makes the event contract understandable outside your Java codebase.

---

# **23. Don’t put JPA entities in Kafka**

This remains an important rule.

Bad:

```java
kafkaTemplate.send("events", postEntity);
```

where:

```java
@Entity
class Post { ... }
```

Why?

Because your database model is not your event contract.

JPA entities may contain:

```text
lazy relationships
internal fields
database implementation details
```

Instead:

```text
JPA entity
   ↓
explicit event DTO
   ↓
serializer
   ↓
Kafka
```

For example:

```java
public record PostCreatedData(
    Long postId,
    Long projectId,
    Long authorId,
    String title
) {}
```

That’s much more intentional.

---

# **24. Schema evolution rule #1**

Prefer:

```text
ADD
```

over:

```text
CHANGE
```

For example:

```text
Add:
title
```

is usually easier than:

```text
Rename:
authorId → creatorId
```

And:

```text
Add optional field
```

is generally easier than:

```text
Change integer → string
```

Compatibility rules are format-specific, but Schema Registry’s current documentation shows additive optional-field changes as commonly compatible under backward/full modes for Avro and Protobuf.  

---

# **25. Schema evolution rule #2**

Don’t reuse removed fields for a completely different meaning.

Bad:

```text
field 4 = title
```

then later:

```text
field 4 = email
```

An old consumer could interpret the new meaning incorrectly.

A safe schema evolution strategy treats historical field identities as part of the contract.

---

# **26. Schema evolution rule #3**

Prefer optional/defaulted additions.

Imagine v1:

```text
postId
authorId
```

v2:

```text
postId
authorId
title
```

If old events don’t contain `title`, the consumer needs a sensible interpretation.

For schema formats such as Avro, default values play an important role in compatibility when evolving fields.  

---

# **27. Schema evolution rule #4**

Don’t make a breaking change casually.

If you really need:

```text
authorId: number
```

to become:

```text
author: object
```

you might instead create:

```text
PostCreatedV2
```

or another explicit migration strategy.

The important thing is to make the incompatibility **intentional and visible**.

---

# **28. Our ProjectHub contract**

Let’s settle on:

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

And:

```java
public record PostCreatedData(
    Long postId,
    Long projectId,
    Long authorId,
    String title
) {}
```

Then:

```text
EventEnvelope<PostCreatedData>
```

is what goes to Kafka.

---

# **29. What happens during a deployment?**

Suppose:

```text
schemaVersion = 1
```

is currently deployed.

We introduce:

```text
schemaVersion = 2
```

with an optional `title`.

Deployment strategy:

```text
1. Make consumers tolerant of v2
2. Deploy consumers
3. Deploy producer that emits v2
```

The exact rollout order depends on the compatibility direction and tooling, but the central idea is:

**Never deploy a producer that immediately requires every consumer to have upgraded at exactly the same moment.**

Schema Registry documentation also describes rollout strategies where compatibility and serializer changes determine whether consumers or producers should be upgraded first.  

---

# **30. The architecture is becoming mature**

We now have:

```text
                 PostgreSQL
                     │
             ┌───────┴───────┐
             │               │
          business         outbox
             │               │
             └────── commit ─┘
                     │
                     ▼
              Outbox Publisher
                     │
                     ▼
                   Kafka
                     │
            explicit event contract
                     │
              schema evolution
                     │
        ┌────────────┼─────────────┐
        ↓            ↓             ↓
   notifications   search      analytics
        │            │             │
    idempotency   idempotency   idempotency
        │            │             │
      retry         retry         retry
        │            │             │
       DLT          DLT           DLT
```

That’s no longer a toy messaging setup.

---

# **31. One more concept: contract ownership**

Someone needs to own:

```text
post.created
```

Who decides:

```text
What does post.created mean?
Which fields exist?
What does each field mean?
What changes are allowed?
How long is the event supported?
```

In a small monolith:

```text
ProjectHub team
```

might own everything.

In a large organization:

```text
Posts team
```

might own the event contract while:

```text
Search team
Analytics team
Notifications team
```

consume it.

This is why event contracts eventually become an organizational concern, not merely a serialization concern.

---

# **32. Your mental model now**

You should now see Kafka events as:

```text
FACT
 │
 ├── identity → eventId
 │
 ├── entity → aggregateId
 │
 ├── sequence → aggregateVersion
 │
 ├── contract → schemaVersion
 │
 └── payload → data
```

And:

```text
Kafka
 │
 ├── partitioning
 ├── retention
 ├── replay
 └── consumer groups
```

while:

```text
Schema Registry
 │
 ├── schema storage
 ├── schema versions
 └── compatibility checks
```

Those are three separate concerns.

---

# **Exercise 78**

### **A — Design the event**

Create the Java records for:

```text
ProjectCreated
```

with:

```text
eventId
eventType
aggregateType
aggregateId
schemaVersion
aggregateVersion
occurredAt
data
```

and payload:

```text
projectId
ownerId
name
```

Don’t worry about Kafka configuration yet.

---

### **B — Schema evolution**

Starting with:

```text
ProjectCreated v1

projectId
ownerId
name
```

You need to add:

```text
description
```

Explain how you’d introduce it without breaking an older consumer.

---

### **C — Breaking change**

Now you need to change:

```text
ownerId: Long
```

to:

```text
owner: {
    id,
    displayName
}
```

Would you modify the existing contract directly, or introduce another contract/version?

Explain your reasoning.

---

### **D — The production question**

Imagine:

```text
Producer v2
Consumer A v1
Consumer B v2
```

and v2 adds:

```text
description
```

What properties must the new event have so that the rollout is safe?

---

## **Next lesson**

**Lesson 79 — Actually implementing the ProjectHub Kafka event contract.**

We’ll move from architecture into code:

```text
EventEnvelope<T>
       ↓
PostCreatedData
       ↓
KafkaTemplate
       ↓
JSON serialization
       ↓
@KafkaListener
       ↓
deserialization
       ↓
validation
       ↓
idempotency
```

Then we’ll deliberately break the contract and see what happens—because understanding failure is more valuable than merely seeing the happy path.