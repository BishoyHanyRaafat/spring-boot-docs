---
title: Lesson 79: Actually Implementing the ProjectHub Kafka Event Contract
sidebar_position: 79
---

Now we’re going to stop talking abstractly and build the contract we designed.

We’ll use **JSON first**. Spring Kafka 4.1.1 provides `JacksonJsonSerializer`/`JacksonJsonDeserializer`, and Spring Boot auto-configures Kafka support when using `spring-boot-starter-kafka`.  

The architecture will be:

```text
PostService
    ↓
PostgreSQL transaction
    ├── Post
    └── OutboxEvent
          ↓
    Outbox Publisher
          ↓
        Kafka
          ↓
    PostCreated event
          ↓
    @KafkaListener
          ↓
    Notification/Search/Analytics
```

---

# **1. First, define the event contract**

We don’t want:

```java
PostCreatedEvent {
    Post post;
}
```

because that couples the event to our JPA entity.

Instead:

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

So our actual event becomes:

```java
EventEnvelope<PostCreatedData>
```

---

# **2. Why use a generic envelope?**

Because eventually we’ll have:

```text
EventEnvelope<PostCreatedData>
EventEnvelope<PostUpdatedData>
EventEnvelope<PostDeletedData>
EventEnvelope<ProjectCreatedData>
```

The infrastructure stays consistent.

For example:

```text
EventEnvelope
 ├── eventId
 ├── eventType
 ├── aggregateType
 ├── aggregateId
 ├── schemaVersion
 ├── aggregateVersion
 ├── occurredAt
 └── data
       └── PostCreatedData
```

That’s much cleaner than inventing completely different metadata structures for every event.

---

# **3. Create the event**

For a newly created post:

```java
var event = new EventEnvelope<>(
    UUID.randomUUID(),
    "post.created",
    "post",
    post.getId().toString(),
    1,
    1,
    Instant.now(),
    new PostCreatedData(
        post.getId(),
        post.getProjectId(),
        post.getAuthorId(),
        post.getTitle()
    )
);
```

Notice something important:

```text
schemaVersion = 1
aggregateVersion = 1
```

They happen to both be `1` here.

That is coincidence.

They mean different things.

---

# **4. Let’s make that distinction concrete**

Suppose Post 42 has gone through:

```text
Post 42

aggregateVersion 1
→ created

aggregateVersion 2
→ title changed

aggregateVersion 3
→ content changed

aggregateVersion 4
→ archived
```

But the event contract hasn’t changed.

Therefore:

```text
schemaVersion = 1
```

could remain unchanged across all those events.

So:

```text
aggregateVersion
```

changes when the **business entity changes**.

While:

```text
schemaVersion
```

changes when the **wire contract changes**.

---

# **5. Configure the producer**

Assuming we have:

```text
spring-boot-starter-kafka
```

Spring Boot can auto-configure a `KafkaTemplate`. The current Spring Boot Kafka documentation shows `spring.kafka.*` as the configuration namespace and `KafkaTemplate` as the standard sending abstraction.  

Our configuration can start simply:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
```

Conceptually:

```text
String key
    ↓
StringSerializer

EventEnvelope
    ↓
JsonSerializer
    ↓
JSON bytes
```

---

# **6. Send the event**

Then:

```java
@Service
public class KafkaEventPublisher {

    private final KafkaTemplate<String, Object> kafkaTemplate;

    public KafkaEventPublisher(
            KafkaTemplate<String, Object> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(EventEnvelope<?> event) {

        kafkaTemplate.send(
            "projecthub.events",
            event.aggregateId(),
            event
        );
    }
}
```

Notice our Kafka key:

```java
event.aggregateId()
```

For Post 42:

```text
key = "42"
```

That gives us the partitioning relationship we discussed earlier.

---

# **7. Why not use eventId as the Kafka key?**

You could.

But consider:

```text
eventId = random UUID
```

Then:

```text
Post 42 event 1 → partition 3
Post 42 event 2 → partition 7
Post 42 event 3 → partition 1
```

That destroys our useful per-post partition affinity.

Instead:

```text
aggregateId = 42
```

gives us:

```text
Post 42
   ↓
same Kafka key
   ↓
same partition
```

assuming the partitioning configuration remains consistent.

---

# **8. Event ID still matters**

We’re not throwing away `eventId`.

It serves a different purpose:

```text
Kafka key
    ↓
partitioning/order grouping

eventId
    ↓
deduplication
```

For example, the same event might be published twice:

```text
eventId = abc-123
```

Consumer sees:

```text
abc-123
abc-123
```

The second occurrence can be recognized as a duplicate.

---

# **9. What does Kafka actually receive?**

Our Java object:

```java
EventEnvelope<PostCreatedData>
```

becomes JSON roughly like:

```json
{
  "eventId": "550e8400-e29b-41d4-a716-446655440000",
  "eventType": "post.created",
  "aggregateType": "post",
  "aggregateId": "42",
  "schemaVersion": 1,
  "aggregateVersion": 1,
  "occurredAt": "2026-10-01T10:15:00Z",
  "data": {
    "postId": 42,
    "projectId": 10,
    "authorId": 7,
    "title": "Hello Kafka"
  }
}
```

This is why explicit DTOs are so valuable.

You can look at the Kafka message and understand the contract without knowing anything about the JPA `Post` entity.

---

# **10. Now the consumer**

We can consume the event using `@KafkaListener`.

Spring Kafka’s current API supports `@KafkaListener` for registering a bean method as a listener.  

For a simple first version:

```java
@Component
public class NotificationConsumer {

    @KafkaListener(
        topics = "projecthub.events",
        groupId = "notifications"
    )
    public void consume(EventEnvelope<?> event) {

        System.out.println(
            "Received: " + event.eventType()
        );
    }
}
```

But there’s a problem.

What exactly is:

```text
EventEnvelope<?>
```

when deserializing JSON?

---

# **11. Generic types make serialization more interesting**

Our Java type is:

```text
EventEnvelope<PostCreatedData>
```

but JSON doesn’t inherently contain Java’s generic type information.

Spring Kafka’s JSON deserializer supports type information in headers and also supports explicitly configured target types/type-resolution strategies.  

For our learning project, however, I’d avoid making the first version unnecessarily clever.

We can instead start with a concrete event type.

---

# **12. Simple version**

Define:

```java
public record PostCreatedEvent(
    UUID eventId,
    String eventType,
    String aggregateType,
    String aggregateId,
    long schemaVersion,
    long aggregateVersion,
    Instant occurredAt,
    PostCreatedData data
) {}
```

Then:

```java
public record PostCreatedData(
    Long postId,
    Long projectId,
    Long authorId,
    String title
) {}
```

Now the consumer has a concrete target.

---

# **13. Consumer configuration**

Conceptually:

```yaml
spring:
  kafka:
    consumer:
      group-id: notifications
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.projecthub.events.PostCreatedEvent
        spring.json.trusted.packages: com.projecthub.events
```

The exact package should obviously match your project.

Spring Kafka’s JSON deserializer supports a default value type and trusted-package configuration, among other options.  

---

# **14. Why trusted packages exist**

JSON deserialization is not something you should blindly allow to instantiate arbitrary Java classes.

Spring Kafka’s `JsonDeserializer` has a `TRUSTED_PACKAGES` setting; by default only selected JDK packages are trusted, and applications can explicitly allow their own event packages.  

So don’t casually configure:

```text
trusted.packages = *
```

in a production system without understanding the consequences.

For our application:

```text
com.projecthub.events
```

is much more deliberate.

---

# **15. Now our listener can be concrete**

```java
@Component
public class NotificationConsumer {

    @KafkaListener(
        topics = "projecthub.events",
        groupId = "notifications"
    )
    public void consume(PostCreatedEvent event) {

        System.out.println(
            "Post created: " + event.data().postId()
        );
    }
}
```

Now the flow is:

```text
Kafka bytes
    ↓
JsonDeserializer
    ↓
PostCreatedEvent
    ↓
@KafkaListener
    ↓
business logic
```

---

# **16. But what about PostUpdated?**

Our topic contains:

```text
post.created
post.updated
post.deleted
```

A consumer needs to distinguish them.

There are several ways to design this.

One is separate topics:

```text
post.created
post.updated
post.deleted
```

Another is a shared event topic:

```text
projecthub.events
```

with:

```text
eventType
```

We chose the second approach for ProjectHub.

Therefore we need a strategy for multiple event types.

---

# **17. One option: different topics**

The simplest type-safe solution is:

```text
projecthub.post.created
projecthub.post.updated
projecthub.post.deleted
```

Then:

```java
@KafkaListener(topics = "projecthub.post.created")
```

always receives `PostCreatedEvent`.

Very simple.

But you now have more topics to operate and manage.

---

# **18. Another option: one topic + event type**

Our architecture currently uses:

```text
projecthub.events
```

with:

```json
{
  "eventType": "post.created"
}
```

Then consumers need to distinguish the payload type.

This is more flexible but introduces more serialization/deserialization complexity.

This is one reason mature event systems often introduce explicit schema contracts and schema registries.

---

# **19. For now, we’ll keep the teaching version simple**

We’ll create:

```text
projecthub.post-created
```

for the first implementation.

That lets us learn:

```text
producer
 ↓
JSON serializer
 ↓
Kafka
 ↓
JSON deserializer
 ↓
consumer
```

without simultaneously solving polymorphic event deserialization.

Once that works, we’ll evolve toward:

```text
projecthub.events
```

with proper event-type/schema handling.

This is an important engineering habit:

**Solve one complexity at a time.**

---

# **20. Now add validation**

Suppose Kafka contains:

```json
{
  "postId": null
}
```

Deserialization might succeed.

But our application should reject it.

That’s why:

```text
deserialization
```

and:

```text
validation
```

are separate steps.

Conceptually:

```text
Kafka bytes
    ↓
deserialize
    ↓
Java object
    ↓
validate
    ↓
business logic
```

Spring Kafka’s current `ErrorHandlingDeserializer` can also invoke a validator after successful deserialization, treating validation failure similarly to a deserialization failure for error handling.  

---

# **21. Don’t confuse validation with authorization**

A Kafka consumer isn’t an HTTP controller.

We’re not asking:

```text
"Is this user allowed?"
```

We’re asking:

```text
"Is this event structurally and semantically acceptable?"
```

For example:

```text
postId != null
projectId != null
authorId != null
schemaVersion supported
```

That’s event validation.

---

# **22. Now idempotency**

This is where our previous lessons return.

Suppose:

```text
eventId = abc
```

gets delivered.

Consumer:

```text
process abc
```

then crashes **before committing the Kafka offset**.

Kafka may deliver:

```text
abc
```

again.

So:

```text
abc
abc
```

is possible.

Our consumer must tolerate it.

---

# **23. Use the database**

We already introduced:

```sql
CREATE TABLE processed_events (
    event_id UUID PRIMARY KEY,
    processed_at TIMESTAMP WITH TIME ZONE NOT NULL
);
```

Now processing can conceptually be:

```text
BEGIN

INSERT processed_events(event_id)
VALUES ('abc')

apply business change

COMMIT
```

If:

```text
event_id = abc
```

already exists:

```text
PRIMARY KEY violation
```

tells us we’ve already processed it.

The database gives us the concurrency guarantee.

---

# **24. Why not do this?**

```java
if (!processedEvents.exists(eventId)) {
    processedEvents.save(eventId);
    process();
}
```

Because two consumers/threads could potentially do:

```text
Thread A → doesn't exist
Thread B → doesn't exist

Thread A → process
Thread B → process
```

That’s a race condition.

Database uniqueness is the important safety mechanism.

---

# **25. The complete consumer pipeline**

Our mature consumer now looks like:

```text
Kafka record
     ↓
deserialize
     ↓
validate
     ↓
identify eventId
     ↓
idempotency check
     ↓
business transaction
     ↓
commit DB transaction
     ↓
Kafka offset acknowledged
```

Failure anywhere before successful completion:

```text
        ↓
      retry
        ↓
      retry
        ↓
       DLT
```

That’s the pipeline we’ve been building across several lessons.

---

# **26. Deserialization failure is special**

Suppose somebody publishes:

```text
not-json-at-all
```

The consumer can’t even create:

```java
PostCreatedEvent
```

So your normal business code never runs.

That’s why Spring Kafka provides `ErrorHandlingDeserializer`: it can catch deserialization failures and expose the failure to the container’s error-handling machinery.  

This gives us:

```text
Kafka
 ↓
deserialization
 ↓
FAIL
 ↓
error handler
 ↓
retry/DLT
```

rather than:

```text
Kafka
 ↓
consumer crashes
```

---

# **27. There are therefore three different failure categories**

### **1. Deserialization failure**

```text
JSON is malformed
```

### **2. Validation failure**

```text
JSON is valid
but data violates contract
```

### **3. Business failure**

```text
event is valid
but processing fails
```

For example:

```text
Database unavailable
```

These failures happen at different layers.

---

# **28. Why this matters for DLT**

Imagine:

```text
bad JSON
```

Retrying it five times probably won’t magically turn it into valid JSON.

That’s likely a permanent failure.

Likewise:

```text
postId = null
```

isn’t likely to become valid through retries.

But:

```text
PostgreSQL temporarily unavailable
```

might succeed after a few seconds.

So:

```text
transient → retry
permanent → DLT
```

is still our central principle.

---

# **29. Now let’s connect it to the Outbox**

Our original transaction:

```text
BEGIN

INSERT post

INSERT outbox_event

COMMIT
```

creates the durable intent.

Then:

```text
outbox publisher
      ↓
Kafka
```

publishes it.

Then:

```text
Kafka consumer
      ↓
processed_events
      +
business change
```

handles it idempotently.

So the complete reliability chain becomes:

```text
DB transaction
   ↓
Outbox
   ↓
at-least-once publication
   ↓
Kafka
   ↓
at-least-once delivery
   ↓
idempotent consumer
   ↓
business transaction
```

This is the architecture you should keep in your head.

---

# **30. What Kafka does NOT guarantee**

Kafka does **not** magically guarantee:

```text
exactly-once business effects
```

just because we’re using Kafka.

For example:

```text
Kafka event
   ↓
send email
```

If the email provider accepts the email and your process crashes before acknowledging the Kafka record, the event can be delivered again.

You could send:

```text
email
email
```

Kafka can’t undo the first email.

That’s why external side effects need their own idempotency strategy.

---

# **31. Example: email idempotency**

Instead of:

```text
sendEmail()
```

blindly, you might maintain:

```text
notification_id
event_id
status
```

with a uniqueness constraint.

Then:

```text
event abc
   ↓
notification already sent?
   ↓
yes → don't send again
```

The exact implementation depends on the external provider and business requirements.

---

# **32. One important improvement**

Our earlier simple producer:

```java
kafkaTemplate.send(...)
```

is asynchronous.

The method returns before the broker necessarily confirms success.

That’s often exactly what you want for throughput.

But our outbox publisher must know whether publication succeeded before marking:

```text
PENDING → PUBLISHED
```

So the outbox publisher needs to handle the send result appropriately.

Conceptually:

```text
send
 ↓
Kafka acknowledgment
 ↓
success → mark PUBLISHED
failure → retry
```

That distinction is important.

---

# **33. Our event contract should also be immutable**

Records are excellent here:

```java
public record PostCreatedData(
    Long postId,
    Long projectId,
    Long authorId,
    String title
) {}
```

Once constructed:

```text
event
```

doesn’t mutate while traveling through the application.

That’s desirable for messages.

---

# **34. Where we’re going next**

We’ve now built the conceptual implementation:

```text
Post
 ↓
Outbox
 ↓
EventEnvelope
 ↓
JSON
 ↓
KafkaTemplate
 ↓
Kafka
 ↓
JsonDeserializer
 ↓
@KafkaListener
 ↓
validation
 ↓
idempotency
 ↓
business transaction
```

The next problem is much more interesting:

What happens when our topic contains **different event types and different schema versions simultaneously**?

For example:

```text
projecthub.events

offset 100 → PostCreated v1
offset 101 → ProjectCreated v2
offset 102 → PostUpdated v1
offset 103 → PostCreated v2
offset 104 → PostDeleted v1
```

We don’t want a giant:

```java
if (eventType.equals(...))
```

monster.

---

# **Exercise 79**

Before we move on, implement these three pieces in your project.

### **1. Event contract**

Create:

```java
EventEnvelope<T>
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

### **2. PostCreatedData**

Create:

```java
PostCreatedData
```

with:

```text
postId
projectId
authorId
title
```

### **3. Publisher**

Create a service that publishes:

```text
EventEnvelope<PostCreatedData>
```

to:

```text
projecthub.events
```

using:

```text
aggregateId
```

as the Kafka key.

**Don’t implement the consumer yet.**

Send me your three classes/configuration when you’re ready, and I’ll review them line by line.

Then we’ll build **Lesson 80 — Polymorphic Kafka Events + Schema Versions**, where we solve the `post.created` / `post.updated` / `project.created` problem properly.

Absolutely. Let’s **wrap up the Kafka section rather than stretching it indefinitely**.

We’ve gone far enough that you should now have the important production mental model.

## **The final ProjectHub messaging architecture**

```text
                    HTTP / REST
                        │
                        ▼
                 ProjectHub Service
                        │
                ┌───────┴────────┐
                │ PostgreSQL      │
                │ transaction     │
                ├─────────────────┤
                │ Post            │
                │ OutboxEvent     │
                └───────┬────────┘
                        │
                        ▼
                Outbox Publisher
                        │
                        ▼
                      Kafka
                        │
             key = aggregateId
                        │
        ┌───────────────┼────────────────┐
        ▼               ▼                ▼
 Notifications       Search          Analytics
 consumer group      consumer group   consumer group
        │               │                │
        └───────┬───────┴───────┬────────┘
                │               │
             retry           idempotency
                │               │
               DLT          business DB
```

Spring Kafka 4.1.1 currently provides the pieces we’ve been using: `KafkaTemplate`, `@KafkaListener`, JSON serialization/deserialization, listener containers, error handling, transactions, and monitoring.  

---

# **The 10 things I want you to remember**

### **1. Outbox solves DB → Kafka consistency**

```text
Post + Outbox
      ↓
same DB transaction
```

You don’t want:

```text
DB succeeds
Kafka fails
```

without a durable record of what needs publishing.

---

### **2. Kafka key controls partitioning**

For ProjectHub:

```text
key = postId
```

means events for the same post are routed consistently to the same partition under normal partitioning.

That gives us **per-post ordering**, rather than attempting global ordering.

---

### **3. Kafka ordering is per partition**

Not:

```text
all Kafka events globally ordered
```

but:

```text
Partition 0 → ordered
Partition 1 → ordered
Partition 2 → ordered
```

---

### **4. Consumer groups give independent consumers**

```text
Kafka
 ├── notifications
 ├── search
 └── analytics
```

Each group can independently consume the event stream.

---

### **5. At-least-once means duplicates are normal**

Therefore:

```text
eventId
    ↓
processed_events
    ↓
database uniqueness
```

is part of our design.

---

### **6. Retry isn’t automatically safe for ordering**

Blocking retry:

```text
failed event
   ↓
retry
   ↓
next event
```

preserves the processing sequence better.

Non-blocking retry:

```text
failed event → retry topic

next event → continues
```

can allow later events to overtake the failed one.

So retry strategy is a **business decision**, not merely configuration.

---

### **7. DLT is quarantine**

```text
temporary problem
     ↓
retry

permanent/exhausted problem
     ↓
DLT
```

DLT doesn’t mean:

“Throw it away.”

It means:

“Remove it from normal processing so the system can continue, while preserving the failure for investigation/recovery.”

---

### **8. Event contracts are APIs**

We ended up with:

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

That is much better than sending JPA entities through Kafka.

---

### **9. Keep the versions separate**

```text
eventId
    → identity

aggregateId
    → which entity?

aggregateVersion
    → which state transition?

schemaVersion
    → which message contract?
```

This distinction will save you a lot of confusion later.

---

### **10. Schema evolution must be intentional**

Prefer:

```text
add optional field
```

over:

```text
change meaning
rename fields
change types
remove required fields
```

As systems grow, schema registries and formats such as Avro, Protobuf, or JSON Schema can enforce compatibility rules rather than relying entirely on developer discipline.

---

# **Kafka vs RabbitMQ — final mental model**

Don’t memorize a simplistic:

Kafka good, RabbitMQ bad.

Instead:

|**Problem**|**Natural model**|
|---|---|
|Generate report|Queue/work|
|Resize image|Queue/work|
|Send email job|Queue/work|
|`PostCreated` → many consumers|Event stream|
|Analytics|Event stream|
|Replay historical events|Event stream|
|Search projection|Event stream|
|Long-lived event history|Event stream|

So for ProjectHub:

```text
RabbitMQ
→ commands / jobs / work distribution

Kafka
→ domain events / analytics / projections / replay
```

Both are useful; the workload determines the fit.

---

# **And that’s enough Kafka for now**

I don’t want to turn this course into:

```text
Kafka lesson 76
Kafka lesson 77
Kafka lesson 78
Kafka lesson 79
Kafka lesson 80
Kafka lesson 81
Kafka lesson 82
...
```

You’ve learned the important architecture.

We can come back to advanced Kafka when it becomes relevant.

## **Next major phase: Testing**

This is where I’d take the course next:

```text
Spring Boot
    ↓
REST API
    ↓
PostgreSQL
    ↓
Security
    ↓
Kafka/RabbitMQ
    ↓
        TEST EVERYTHING
```

We’ll cover:

1. **Unit testing with JUnit 5**
2. Mockito
3. Testing services
4. Testing controllers
5. `MockMvc`
6. Testing validation/errors
7. Testing Spring Security
8. Testing JWT authentication
9. PostgreSQL integration tests
10. **Testcontainers**
11. Testing Kafka consumers/producers
12. Testing transactions
13. Testing the Outbox
14. Integration-test architecture
15. Test fixtures/builders
16. Full end-to-end tests

And we’ll do it practically rather than spending 20 lessons on testing theory.

The current Spring Kafka documentation also explicitly includes testing, transactions, error handling, and listener infrastructure as part of its supported production concerns, so we’ll be able to test the messaging pieces rather than treating them as a black box.  

**Next up: Lesson 80 — Testing Spring Boot properly, starting with JUnit 5 and Mockito.**