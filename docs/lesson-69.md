---
title: Lesson 69: Building the RabbitMQ Pipeline in ProjectHub
sidebar_position: 69
---

Now let’s actually connect the pieces.

We’re going to build this:

```text
                    PostgreSQL
                       │
                ┌──────┴──────┐
                │   Outbox    │
                └──────┬──────┘
                       │
                OutboxPublisher
                       │
                 RabbitTemplate
                       │
                       ▼
              projecthub.events
                 Topic Exchange
                  /          \
                 /            \
                ▼              ▼
        notifications       analytics
           queue               queue
              │                  │
              ▼                  ▼
        Notification         Analytics
          Consumer            Consumer
```

Spring Boot currently provides RabbitMQ support through its AMQP starter, and Spring AMQP 4.1.1 provides `RabbitTemplate`, `@RabbitListener`, JSON conversion, publisher confirms, and listener infrastructure.  

---

## **1. Start with the infrastructure**

First, let’s separate **RabbitMQ configuration** from our business code.

Create something like:

```text
messaging/
├── RabbitMqConfig.java
├── OutboxPublisher.java
├── NotificationConsumer.java
└── event/
    ├── EventEnvelope.java
    └── PostCreatedEvent.java
```

Why?

Because RabbitMQ is infrastructure.

We don’t want `PostService` filled with broker-specific details.

---

# **2. RabbitMQ configuration**

We’ll define our exchange and queues in one configuration class.

Conceptually:

```java
@Configuration
public class RabbitMqConfig {

    public static final String EVENTS_EXCHANGE =
            "projecthub.events";

    public static final String NOTIFICATION_QUEUE =
            "projecthub.notifications";

    public static final String ANALYTICS_QUEUE =
            "projecthub.analytics";

    // exchange
    // queues
    // bindings
}
```

Notice something important:

We’re using constants rather than sprinkling:

```text
"projecthub.events"
```

throughout the application.

That’s a small thing, but it prevents configuration drift.

---

# **3. Exchange**

```java
@Bean
TopicExchange eventsExchange() {
    return new TopicExchange(EVENTS_EXCHANGE, true, false);
}
```

The important parameters are:

```text
name
durable
autoDelete
```

We want:

```text
durable = true
```

because this is infrastructure we expect to survive broker restarts.

---

# **4. Queues**

Notification:

```java
@Bean
Queue notificationQueue() {
    return QueueBuilder
            .durable(NOTIFICATION_QUEUE)
            .build();
}
```

Analytics:

```java
@Bean
Queue analyticsQueue() {
    return QueueBuilder
            .durable(ANALYTICS_QUEUE)
            .build();
}
```

Our topology is now:

```text
projecthub.events
      │
      ├── projecthub.notifications
      │
      └── projecthub.analytics
```

---

# **5. Bindings**

Notification:

```java
@Bean
Binding notificationBinding(
        Queue notificationQueue,
        TopicExchange eventsExchange) {

    return BindingBuilder
            .bind(notificationQueue)
            .to(eventsExchange)
            .with("post.*");
}
```

Analytics:

```java
@Bean
Binding analyticsBinding(
        Queue analyticsQueue,
        TopicExchange eventsExchange) {

    return BindingBuilder
            .bind(analyticsQueue)
            .to(eventsExchange)
            .with("post.*");
}
```

Now:

```text
post.created
post.updated
post.deleted
```

will match:

```text
post.*
```

and therefore reach both queues.

---

# **6. A subtle but important distinction**

The exchange doesn’t contain:

```text
PostCreated
```

The queue doesn’t contain:

```text
PostCreated
```

The **message** contains the event.

The routing key tells RabbitMQ where it should go:

```text
message
  │
  ├── event type: PostCreated
  │
  └── routing key: post.created
```

That’s two different concepts.

---

# **7. Our event contract**

Let’s create the actual event.

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

This is deliberately **not**:

```java
Post post
```

because the JPA entity belongs to the persistence layer.

Our event is a public internal contract.

---

# **8. Add an envelope**

I’d make the real message slightly richer:

```java
public record EventEnvelope<T>(
        UUID eventId,
        String eventType,
        int version,
        Instant occurredAt,
        T data
) {}
```

Then our message becomes conceptually:

```json
{
  "eventId": "7c...",
  "eventType": "PostCreated",
  "version": 1,
  "occurredAt": "2026-10-01T12:00:00Z",
  "data": {
    "postId": 42,
    "projectId": 7,
    "authorId": 15
  }
}
```

This is much more useful than simply serializing a Java object.

---

# **9. JSON conversion**

Spring AMQP’s current JSON converter is `JacksonJsonMessageConverter`; the older `Jackson2...` APIs are deprecated in favor of Jackson 3-based classes in the current 4.x line.  

So we’ll use:

```java
@Bean
JacksonJsonMessageConverter jsonMessageConverter() {
    return new JacksonJsonMessageConverter();
}
```

The purpose is:

```text
Java object
     ↓
Jackson
     ↓
JSON bytes
     ↓
RabbitMQ
```

and on the consumer:

```text
RabbitMQ
     ↓
JSON bytes
     ↓
Jackson
     ↓
Java object
```

---

# **10. Configure the listener**

Spring’s `@RabbitListener` infrastructure creates the listener container behind the scenes. The queue needs to exist and be bound, although Spring can declare resources automatically when a `RabbitAdmin` is present.  

For our learning project:

```java
@Bean
SimpleRabbitListenerContainerFactory rabbitListenerContainerFactory(
        ConnectionFactory connectionFactory,
        JacksonJsonMessageConverter converter) {

    var factory = new SimpleRabbitListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setMessageConverter(converter);

    return factory;
}
```

Now the listener knows how to turn JSON into our Java event.

---

# **11. Our consumer**

```java
@Component
public class NotificationConsumer {

    @RabbitListener(
        queues = RabbitMqConfig.NOTIFICATION_QUEUE
    )
    public void handle(PostCreatedEvent event) {

        System.out.println(
            "Post created: " + event.postId()
        );
    }
}
```

Spring AMQP invokes this method when a message arrives.  

At this point we have:

```text
RabbitMQ
   ↓
notification queue
   ↓
@RabbitListener
   ↓
PostCreatedEvent
```

That’s the basic happy path.

---

# **12. But there’s a problem**

Our consumer currently does:

```text
receive
 ↓
process
```

Where is the ACK?

With a reliable system, we need to carefully define:

```text
receive
 ↓
process successfully
 ↓
acknowledge
```

Otherwise failures become ambiguous.

---

# **13. Before implementing ACKs, let’s understand idempotency**

Suppose:

```text
PostCreated
```

arrives.

The consumer sends an email.

Then:

```text
email sent
     ↓
consumer crashes
     ↓
ACK never happens
```

RabbitMQ can deliver the message again.

Now:

```text
PostCreated
     ↓
email sent
```

happens **twice**.

That’s why:

**At-least-once delivery requires idempotent consumers.**

This is one of the most important distributed-systems lessons in the entire course.

---

# 

# **14. Create**

**`processed_events`**

Suppose our notification worker has a database.

We can create:

```sql
CREATE TABLE processed_events (
    event_id UUID PRIMARY KEY,
    processed_at TIMESTAMP WITH TIME ZONE NOT NULL
);
```

Now processing can conceptually be:

```text
event arrives
     ↓
have we processed eventId?
     │
   ┌─┴─┐
  yes  no
   │    │
   │    ↓
   │  process
   │    ↓
   │  insert eventId
   │
   ↓
 ACK
```

If the same message arrives twice:

```text
eventId = abc
```

the second attempt sees:

```text
abc already exists
```

and doesn’t perform the business operation again.

---

# **15. But there’s a transaction problem**

Don’t do this:

```text
send notification
     ↓
insert processed_events
```

without considering the transaction boundary.

What if:

```text
send notification
     ↓
database crashes
     ↓
processed_events wasn't saved
```

The message gets retried and the notification might be sent twice.

Exactly-once effects are much harder than exactly-once message delivery.

For external side effects such as email/payment/API calls, we need an idempotency strategy at the side-effect boundary too.

---

# **16. Back to the publisher**

Now let’s implement the other side.

Our outbox publisher has an `OutboxEvent`:

```text
id
eventId
eventType
payload
status
attempts
...
```

It publishes:

```java
rabbitTemplate.convertAndSend(
        RabbitMqConfig.EVENTS_EXCHANGE,
        "post.created",
        event
);
```

`RabbitTemplate` is Spring AMQP’s main abstraction for sending messages.  

---

# **17. The dangerous version**

Don’t do:

```java
rabbitTemplate.convertAndSend(...);

outboxEvent.markPublished();

repository.save(outboxEvent);
```

and assume success.

Publishing is asynchronous, and a successful method call doesn’t by itself mean the broker has accepted and routed the message. Spring AMQP specifically provides publisher confirms and returned-message handling for detecting these cases.  

---

# **18. Publisher confirms**

The current Spring AMQP configuration uses correlated publisher confirms:

```text
ConfirmType.CORRELATED
```

with a `ConfirmCallback`. Publisher returns require `publisherReturns=true` and a `ReturnsCallback`.  

Conceptually:

```text
Outbox
  ↓
RabbitTemplate
  ↓
RabbitMQ
  ↓
confirm
  ↓
Outbox = PUBLISHED
```

And:

```text
RabbitTemplate
  ↓
RabbitMQ
  ↓
NO_ROUTE
  ↓
returned message
  ↓
don't mark PUBLISHED
```

---

# **19. Configure confirms**

At the connection-factory level, the current API uses:

```java
factory.setPublisherConfirmType(
    ConfirmType.CORRELATED
);

factory.setPublisherReturns(true);
```

The important thing isn’t memorizing those two lines.

It’s understanding:

```text
publisher confirm
       =
RabbitMQ accepted publication
```

while:

```text
returned message
       =
RabbitMQ couldn't route the message
```

These solve different problems.  

---

# **20. Correlation**

When publishing, associate the message with its outbox event:

```text
OutboxEvent
   eventId = ABC
       ↓
CorrelationData
   eventId = ABC
       ↓
RabbitMQ
       ↓
confirm
   eventId = ABC
```

Now the confirmation tells us exactly which outbox record the broker responded to.

That is the reason for **correlated** confirms.

---

# **21. The publisher state machine**

Our outbox now has a useful lifecycle:

```text
PENDING
   ↓
PROCESSING
   ↓
publish
   │
   ├── confirmed ─────→ PUBLISHED
   │
   └── failed ────────→ PENDING
```

And:

```text
PROCESSING
     ↓
worker crashes
     ↓
lease timeout
     ↓
PENDING
```

That’s why we introduced `PROCESSING` in the previous lesson.

---

# **22. Don’t hold a DB transaction while publishing**

This is another important rule.

Avoid:

```text
BEGIN DB TRANSACTION
       ↓
claim event
       ↓
publish to RabbitMQ
       ↓
wait for network
       ↓
mark published
       ↓
COMMIT
```

Why?

Because you’re holding database resources while waiting on a network operation.

Instead:

```text
Transaction 1
    ↓
claim event
    ↓
COMMIT

RabbitMQ publish
    ↓
confirm

Transaction 2
    ↓
mark published
    ↓
COMMIT
```

Much healthier.

---

# **23. What if the process crashes?**

Suppose:

```text
PROCESSING
   ↓
RabbitMQ accepts message
   ↓
RabbitMQ confirms
   ↓
application crashes
   ↓
never marked PUBLISHED
```

After recovery:

```text
PROCESSING
   ↓
timeout
   ↓
PENDING
   ↓
publish again
```

Now RabbitMQ might receive the same event twice.

That’s okay **if consumers are idempotent**.

This is the fundamental tradeoff:

We prefer possible duplication over silently losing an event.

---

# **24. Why not delete the outbox row?**

You might ask:

Why not just delete the row after successful publishing?

You can eventually archive/delete old events.

But keeping published records for some retention period is often valuable for:

- auditing
- debugging
- replay
- operational investigation
- tracing event history

So:

```text
PUBLISHED
```

doesn’t necessarily mean:

```text
DELETE IMMEDIATELY
```

---

# **25. Retry and DLQ**

Now the consumer side.

Suppose:

```text
PostCreated
```

causes:

```text
Notification API timeout
```

We retry.

But suppose the payload is malformed:

```json
{
  "postId": "not-a-number"
}
```

Retrying 100 times won’t fix it.

So:

```text
temporary failure
      ↓
retry

permanent failure
      ↓
DLQ
```

That’s the purpose of a dead-letter queue.

---

# **26. Our topology becomes**

```text
                         projecthub.events
                               │
                         post.created
                               │
                    ┌──────────┴──────────┐
                    ↓                     ↓
              notifications            analytics
                  queue                   queue
                    │
                    ↓
                 Consumer
                    │
              ┌─────┴─────┐
              ↓           ↓
           success      failure
              │           │
             ACK        retry
                          │
                    ┌─────┴─────┐
                    ↓           ↓
                 success       DLQ
                    │
                   ACK
```

---

# **27. The three guarantees we are combining**

Our system is not “exactly once.”

Instead, we’re combining several mechanisms:

### **Database**

```text
Post + Outbox
```

gives atomicity.

### **Publisher**

```text
Confirm + retry
```

gives reliable broker publication.

### **Consumer**

```text
ACK + retry + idempotency
```

gives resilient processing.

Together they produce a robust **at-least-once event pipeline**.

---

# **28. What happens to our original POST?**

A user sends:

```http
POST /projects/7/posts
```

ProjectHub does:

```text
HTTP request
    ↓
PostController
    ↓
PostService
    ↓
@Transactional
    ├── INSERT post
    └── INSERT outbox_event
    ↓
COMMIT
```

The HTTP request can return successfully.

Then independently:

```text
OutboxPublisher
    ↓
RabbitTemplate
    ↓
projecthub.events
    ↓
post.created
```

Then:

```text
Notification Queue
    ↓
NotificationConsumer
    ↓
idempotency check
    ↓
send notification
    ↓
ACK
```

That’s the architecture we’ve been building toward.

---

# **29. One more important boundary**

Notice that authorization happened **before** the event.

For example:

```text
POST /projects/7/posts
        ↓
authenticate user
        ↓
authorize posts.create
        ↓
check project membership
        ↓
create Post
        ↓
create PostCreated event
```

RabbitMQ does **not** decide whether the user was allowed to create the post.

That’s already decided synchronously by ProjectHub.

RabbitMQ is transporting the fact:

“A post was created.”

This separation keeps authorization logic out of asynchronous consumers.

---

# **30. Final architecture**

We’ve now reached this:

```text
                       INTERNET
                           │
                           ▼
                       Gateway
                           │
                           ▼
                    ProjectHub API
                           │
                    ┌──────┴──────┐
                    │             │
                 Security       Services
                    │             │
                    └──────┬──────┘
                           │
                     PostgreSQL
                    ┌──────┴──────┐
                    │             │
                 Domain        Outbox
                  Data           │
                                 ▼
                         Outbox Publisher
                                 │
                          RabbitTemplate
                                 │
                                 ▼
                       ┌─────────────────┐
                       │ RabbitMQ        │
                       │ projecthub.events│
                       └────────┬────────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
              Notification               Analytics
                  Queue                    Queue
                    │                       │
                    ▼                       ▼
              Notification               Analytics
                Consumer                  Consumer
                    │
              Idempotency
                    │
               business work
                    │
                   ACK
```

That’s a real production-style architecture.

Not because RabbitMQ makes it automatically reliable—but because **every failure boundary has an explicit strategy**.

---

# **Your Lesson 69 exercise**

Implement the **happy path only** first.

Create:

### **1. RabbitMQ configuration**

```text
projecthub.events
projecthub.notifications
projecthub.analytics
```

with the appropriate topic bindings.

### **2. Event**

```java
PostCreatedEvent
```

containing:

```text
eventId
version
occurredAt
postId
projectId
authorId
```

### **3. JSON conversion**

Configure the current:

```text
JacksonJsonMessageConverter
```

### **4. Publisher**

Make an `OutboxPublisher` publish:

```text
exchange = projecthub.events
routing key = post.created
```

### **5. Consumer**

Create:

```java
@RabbitListener
```

for:

```text
projecthub.notifications
```

and have it receive a `PostCreatedEvent`.

**Don’t implement retries, DLQ, or idempotency yet.**

Get this first:

```text
OutboxEvent
     ↓
RabbitTemplate
     ↓
Exchange
     ↓
Notification Queue
     ↓
@RabbitListener
     ↓
PostCreatedEvent
```

Once that works, the next step is where things get really interesting: **Lesson 70 — reliable publishing + publisher confirms + retries + idempotent consumers + DLQ**, where we’ll deliberately crash components and reason through exactly what happens.