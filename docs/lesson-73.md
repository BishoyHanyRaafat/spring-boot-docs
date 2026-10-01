---
title: "Lesson 73: Kafka in Practice with Spring Boot"
sidebar_position: 73
---

Now we’re going to stop comparing Kafka and RabbitMQ and **actually build the Kafka side of ProjectHub**.

The current stable Spring for Apache Kafka release is **4.1.1**. With Spring Boot, the recommended dependency is `spring-boot-starter-kafka`; Spring Boot manages the compatible Spring Kafka version for you.  

Our goal is not to memorize configuration. It’s to understand the flow:

```text
ProjectHub
   ↓
KafkaTemplate
   ↓
Kafka topic
   ↓
partition
   ↓
consumer group
   ↓
@KafkaListener
```

---

## **1. First: what we’re building**

Let’s use the event we’ve already been using:

```java
public record PostCreatedEvent(
        UUID eventId,
        int version,
        Instant occurredAt,
        Long postId,
        Long projectId,
        Long authorId
) {}
```

We’ll publish it to:

```text
projecthub.events
```

and use:

```text
event key = postId
```

The key is important because it lets Kafka consistently associate events for the same post with the same partition.

Conceptually:

```text
Post 42 Created ──┐
Post 42 Updated ──┼──→ Partition 2
Post 42 Deleted ──┘

Post 43 Created ─────→ Partition 0
```

That gives us the possibility of **per-post ordering**.

---

# **2. Add Kafka to Spring Boot**

With Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-kafka</artifactId>
</dependency>
```

Notice that we don’t specify a Spring Kafka version ourselves when using the Spring Boot starter.

Spring’s current documentation explicitly recommends the starter and letting Spring Boot manage the compatible version.  

---

# **3. Run Kafka**

For local development, let’s use Docker Compose.

Conceptually:

```text
ProjectHub
    │
    │
    ▼
  Kafka
```

A modern Kafka deployment can be configured in several ways, so don’t treat a particular Docker image configuration as production architecture.

For this lesson, the important thing is simply:

```text
Kafka broker
    ↓
localhost:9092
```

Then Spring Boot needs:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
```

`bootstrap-servers` tells the Kafka client where it can initially connect to the cluster. Spring Kafka exposes producer and consumer factories around those Kafka clients.  

---

# **4. Our first topic**

We’ll use:

```text
projecthub.events
```

with, say:

```text
4 partitions
```

Conceptually:

```text
projecthub.events

Partition 0
Partition 1
Partition 2
Partition 3
```

Why four?

Not because four is magically correct.

It’s just enough for us to demonstrate partition-based parallelism.

In a real system, partition count is an architectural decision because it affects parallelism and ordering.

---

# **5. Creating the topic with Spring**

Spring Kafka provides `KafkaAdmin` and topic configuration support.  

We can declare:

```java
@Bean
NewTopic projectHubEventsTopic() {
    return TopicBuilder.name("projecthub.events")
            .partitions(4)
            .replicas(1)
            .build();
}
```

For local development:

```text
partitions = 4
replicas = 1
```

is fine.

For production, replication would be a separate availability decision.

---

# **6. Producer**

Spring Kafka gives us:

```text
KafkaTemplate
```

as the high-level abstraction for sending Kafka messages.  

So instead of dealing directly with Kafka’s low-level producer API:

```java
KafkaProducer
```

our application can use:

```java
KafkaTemplate
```

For example:

```java
@Service
public class ProjectHubEventPublisher {

    private final KafkaTemplate<String, PostCreatedEvent> kafkaTemplate;

    public ProjectHubEventPublisher(
            KafkaTemplate<String, PostCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(PostCreatedEvent event) {
        kafkaTemplate.send(
                "projecthub.events",
                event.postId().toString(),
                event
        );
    }
}
```

The important part is:

```java
event.postId().toString()
```

That’s our **Kafka key**.

---

# **7. Why the key matters**

Suppose:

```text
Post 42
```

produces:

```text
PostCreated
PostUpdated
PostUpdated
PostDeleted
```

We want:

```text
key = 42
```

for all of them.

Kafka can then place those records into the same partition.

Conceptually:

```text
             key = 42
                 ↓
        ┌────────────────┐
        │ partition 2    │
        ├────────────────┤
        │ Created        │
        │ Updated        │
        │ Updated        │
        │ Deleted        │
        └────────────────┘
```

Now another post can independently use another partition.

That’s the foundation of our per-post ordering strategy.

---

# **8. Don’t confuse key with event ID**

This is important.

We have:

```text
eventId
```

and:

```text
Kafka key
```

They solve different problems.

### **Event ID**

```text
eventId = 8d...
```

Identifies **this particular event**.

Useful for:

```text
deduplication
idempotency
tracing
```

### **Kafka key**

```text
key = postId
```

Determines **which logical stream/partition the event belongs to**.

Useful for:

```text
partitioning
per-aggregate ordering
parallelism
```

So:

```text
eventId ≠ Kafka key
```

---

# **9. JSON serialization**

We don’t want to send a Java object directly as some JVM-specific representation.

We want something like:

```json
{
  "eventId": "8d7...",
  "version": 1,
  "occurredAt": "2026-10-01T10:15:00Z",
  "postId": 42,
  "projectId": 7,
  "authorId": 12
}
```

Spring Kafka provides JSON serializers/deserializers and JSON message converters.  

So the conceptual pipeline is:

```text
Java record
    ↓
JSON serializer
    ↓
Kafka bytes
```

and on the consumer:

```text
Kafka bytes
    ↓
JSON deserializer/converter
    ↓
Java record
```

---

# **10. Consumer**

Now we create:

```java
@Component
public class PostEventConsumer {

    @KafkaListener(
            topics = "projecthub.events",
            groupId = "notifications"
    )
    public void consume(PostCreatedEvent event) {
        System.out.println(
                "Received post: " + event.postId()
        );
    }
}
```

`@KafkaListener` tells Spring to create a listener container that consumes records from Kafka.  

So:

```text
Kafka
 ↓
Spring listener container
 ↓
consume(...)
```

---

# **11. Consumer group**

This part is crucial.

We have:

```java
groupId = "notifications"
```

That means this consumer belongs to the:

```text
notifications
```

consumer group.

Suppose we have four partitions:

```text
P0
P1
P2
P3
```

and four consumer instances:

```text
Consumer A
Consumer B
Consumer C
Consumer D
```

Kafka can distribute partitions among those consumers.

Conceptually:

```text
P0 → A
P1 → B
P2 → C
P3 → D
```

Now suppose we deploy five application Pods.

There are still only four partitions.

So one consumer won’t have a partition assigned in that group.

This is why:

**Partitions determine the maximum useful parallelism of a consumer group.**

---

# **12. Two different consumer groups**

Now we create:

```text
notifications
analytics
```

So:

```text
                projecthub.events
                       │
              ┌────────┴────────┐
              ↓                 ↓
       notifications        analytics
          group                group
```

Both groups can independently consume the same events.

That’s one of Kafka’s most powerful concepts.

---

# **13. Compare this with RabbitMQ**

Our RabbitMQ design was:

```text
Exchange
   │
   ├── notifications queue
   │
   └── analytics queue
```

Kafka:

```text
Topic
   │
   ├── notifications group
   │
   └── analytics group
```

They look similar.

But remember the fundamental difference:

RabbitMQ’s queue is primarily about **delivery**.

Kafka’s partition is a **retained ordered log**, and each consumer group tracks its own position.

---

# **14. Offset**

Here’s another new Kafka concept.

Each record has an:

```text
offset
```

For example:

```text
Partition 2

offset 100 → PostCreated
offset 101 → PostUpdated
offset 102 → CommentCreated
offset 103 → PostDeleted
```

The consumer maintains its position.

Conceptually:

```text
Consumer
   ↓
"I processed through offset 102."
```

So if it restarts, it can resume from its stored position.

This is fundamentally different from RabbitMQ’s traditional “acknowledge this delivery” mental model.

---

# **15. This makes replay possible**

Suppose analytics has processed:

```text
offset 0 → 100000
```

Then we discover:

“Our analytics calculation was wrong.”

We can conceptually move the consumer’s position backward and process the records again.

That’s one of the major reasons Kafka is so useful for streaming/data-processing architectures.

Spring Kafka also provides support for seeking to specific offsets.  

---

# **16. But don’t think “offset = event ID”**

They’re different.

```text
eventId
```

is application-level identity.

```text
offset
```

is Kafka’s position within a particular partition.

For example:

```text
Partition 2:
offset 500 → eventId A
offset 501 → eventId B
```

If the event is copied into another topic, its offset there will be different.

The `eventId` remains the event’s identity.

---

# **17. Consumer acknowledgement vs offset**

This is another place where Kafka differs from RabbitMQ.

RabbitMQ:

```text
message delivered
      ↓
consumer ACK
      ↓
broker can remove message
```

Kafka:

```text
record consumed
      ↓
consumer position/offset committed
      ↓
consumer resumes from committed position
```

So Kafka’s fundamental recovery mechanism is based around **consumer offsets**, not destructive queue acknowledgement.

---

# **18. What happens if the consumer crashes?**

Suppose:

```text
offset 100
```

was processed.

Then the application crashes before committing its progress.

Kafka can deliver/process that record again after restart, depending on the consumer’s commit configuration.

Therefore:

**Kafka consumers must also be designed for duplicate processing.**

This connects directly to our previous RabbitMQ lesson.

Our:

```text
processed_events
```

idea remains valuable.

---

# **19. Kafka doesn’t magically give exactly-once business behavior**

This is another common misconception.

You might hear:

“Kafka supports exactly-once semantics.”

That’s a much more nuanced statement than:

“Your business operation happens exactly once.”

Kafka and Spring Kafka have transaction/exactly-once mechanisms for particular Kafka processing scenarios, but your external side effects still require careful design.

For example:

```text
Kafka event
   ↓
charge credit card
```

Kafka cannot magically make an external payment provider perform exactly one charge.

Your business operation needs its own idempotency strategy.

---

# **20. Our ProjectHub architecture**

Putting everything together:

```text
                     PostgreSQL
                         │
                 ┌───────┴───────┐
                 │               │
              Post row       Outbox row
                 │               │
                 └────── COMMIT ─┘
                         │
                         ▼
                 Outbox Publisher
                         │
                         ▼
                    Kafka topic
                projecthub.events
                         │
            ┌────────────┼────────────┐
            ↓            ↓            ↓
          P0/P1         P2/P3       ...
            │
      ┌─────┴─────┐
      ↓           ↓
notifications  analytics
   group         group
```

This is the Kafka version of the architecture we’ve already built.

---

# **21. Where does the Outbox publisher fit?**

Remember our previous design:

```text
PENDING
   ↓
PROCESSING
   ↓
PUBLISHED
```

The publisher now does:

```text
Outbox
   ↓
KafkaTemplate
   ↓
Kafka
```

The important principle remains:

```text
Post + Outbox
```

must be committed together.

Kafka doesn’t change that.

---

# **22. What I don’t want you to do yet**

Don’t immediately try to build:

```text
Kafka
+
Kafka Streams
+
Schema Registry
+
Avro
+
Debezium
+
Transactions
+
Exactly Once
+
Kubernetes
```

all at once.

That would turn a useful lesson into configuration memorization.

We’re going to build the concepts one at a time.

---

# **23. Our first minimal Kafka flow**

For now, reduce everything to:

```text
Producer
   ↓
Kafka topic
   ↓
Consumer
```

Specifically:

```text
PostCreatedEvent
       ↓
KafkaTemplate
       ↓
projecthub.events
       ↓
@KafkaListener
       ↓
log event
```

Once that works, we’ll add:

```text
partition keys
consumer groups
multiple consumers
offsets
retries
DLQ
idempotency
outbox integration
```

---

# **24. One subtle thing about Spring Boot**

Spring Kafka gives us a lot of infrastructure.

The application code can stay remarkably small:

```java
kafkaTemplate.send(...);
```

and:

```java
@KafkaListener(...)
public void consume(...) {
    ...
}
```

But underneath that, Spring is managing Kafka producers/consumers and listener containers. The current Spring Kafka reference explicitly describes `KafkaTemplate`, `ProducerFactory`, `ConsumerFactory`, and listener containers as the core infrastructure.  

That’s exactly why learning the underlying Kafka model first was important.

Otherwise these annotations look like magic.

---

# **25. Your exercise**

Before we add more code, I want you to implement this yourself.

### **Part A — Producer**

Create:

```text
PostCreatedEvent
```

and a:

```text
ProjectHubKafkaPublisher
```

that publishes to:

```text
projecthub.events
```

with:

```text
key = postId
```

---

### **Part B — Consumer**

Create:

```text
NotificationKafkaConsumer
```

with:

```text
groupId = notifications
```

and print:

```text
Received PostCreated: postId=42
```

---

### **Part C — Second consumer group**

Create:

```text
AnalyticsKafkaConsumer
```

with:

```text
groupId = analytics
```

Publish **one** event.

You should see both:

```text
notifications → receives event
analytics     → receives event
```

because they’re different consumer groups.

---

### **Part D — Experiment with the key**

Publish:

```text
postId = 42
postId = 42
postId = 42
```

and inspect which partition receives them.

Then publish:

```text
postId = 43
postId = 44
```

and observe the partition distribution.

Don’t worry if the exact distribution surprises you—the important thing is understanding **why the key is involved**.

---

### **Part E — Answer these before moving on**

1. What is a Kafka **topic**?
2. What is a **partition**?
3. What is a **consumer group**?
4. What is an **offset**?
5. Why are `eventId` and Kafka `key` different?
6. Why does using `postId` as the key help with per-post ordering?
7. Why can `notifications` and `analytics` both receive the same event?
8. If we have **4 partitions and 10 consumers in one consumer group**, why can’t all 10 consumers simultaneously consume one partition each?
9. Why can a Kafka consumer process the same event more than once?
10. Why does Kafka not eliminate our Outbox Pattern?

**Don’t worry about getting all 10 perfect.** Send me your implementation and/or answers, and I’ll review them like we did with the ProjectHub RabbitMQ work.

Next we’ll tackle **Kafka retries, error handling, dead-letter topics, and idempotent consumers**—which will let you compare the Kafka reliability model directly against the RabbitMQ reliability pipeline you just learned.