---
title: "Lesson 68: Implementing RabbitMQ in ProjectHub"
sidebar_position: 68
---

Now we wire the broker into the system we’ve designed.

The current Spring AMQP reference is **4.1.1**. It provides `RabbitTemplate` for publishing and `@RabbitListener` for consumers.  

Our goal:

```text
PostService
    ↓
Post + Outbox
    ↓
PostgreSQL COMMIT
    ↓
OutboxPublisher
    ↓
RabbitTemplate
    ↓
RabbitMQ Exchange
    ↓
┌───────────────┬──────────────┐
↓               ↓
Notification    Analytics
Queue           Queue
↓               ↓
Consumer        Consumer
```

---

## **1. Add Spring AMQP**

ProjectHub needs the RabbitMQ integration:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
```

This gives us Spring’s AMQP infrastructure and RabbitMQ integration.

---

# **2. Configure RabbitMQ**

For local Docker Compose development, we’d have something like:

```yaml
services:

  rabbitmq:
    image: rabbitmq:4-management
    ports:
      - "5672:5672"
      - "15672:15672"
```

The important distinction:

```text
5672
 ↓
AMQP application connection

15672
 ↓
RabbitMQ management UI
```

Inside Docker Compose, ProjectHub should connect to:

```text
rabbitmq:5672
```

not:

```text
localhost:5672
```

because `localhost` inside the ProjectHub container refers to the ProjectHub container itself.

---

# **3. Spring configuration**

For development:

```yaml
spring:
  rabbitmq:
    host: rabbitmq
    port: 5672
    username: projecthub
    password: projecthub
```

In production, credentials should come from your deployment secret mechanism rather than being committed to Git.

So eventually:

```text
Kubernetes Secret
       ↓
environment/config
       ↓
Spring Boot
       ↓
RabbitMQ connection
```

---

# **4. Define the exchange**

Let’s use a topic exchange:

```java
@Bean
TopicExchange projectHubExchange() {
    return new TopicExchange("projecthub.events");
}
```

Our architecture becomes:

```text
                    projecthub.events
                           ↑
                           │
                     Outbox Publisher
```

The exchange isn’t storing our business data.

It’s routing messages.

---

# **5. Notification queue**

```java
@Bean
Queue notificationQueue() {
    return QueueBuilder
            .durable("projecthub.notifications")
            .build();
}
```

Then bind it:

```java
@Bean
Binding notificationBinding(
        Queue notificationQueue,
        TopicExchange projectHubExchange) {

    return BindingBuilder
            .bind(notificationQueue)
            .to(projectHubExchange)
            .with("post.*");
}
```

Now:

```text
post.created
post.deleted
post.updated
```

can reach the notification queue.

---

# **6. Analytics queue**

Create another queue:

```java
@Bean
Queue analyticsQueue() {
    return QueueBuilder
            .durable("projecthub.analytics")
            .build();
}
```

And:

```java
@Bean
Binding analyticsBinding(
        Queue analyticsQueue,
        TopicExchange projectHubExchange) {

    return BindingBuilder
            .bind(analyticsQueue)
            .to(projectHubExchange)
            .with("post.*");
}
```

Now:

```text
                   projecthub.events
                       /       \
                      /         \
               notification   analytics
                  queue          queue
```

Both receive the event independently.

---

# **7. Why two queues?**

This is extremely important.

If we had:

```text
projecthub.queue
```

with two consumers:

```text
NotificationConsumer
AnalyticsConsumer
```

RabbitMQ would distribute messages between them.

That means:

```text
PostCreated
```

might go to:

```text
NotificationConsumer
```

but not:

```text
AnalyticsConsumer
```

That’s not what we want.

Separate queues mean:

```text
PostCreated
    ↓
notification queue → notification service

PostCreated
    ↓
analytics queue → analytics service
```

Each subscriber gets its own copy.

---

# **8. Routing keys**

Our first event:

```text
PostCreated
```

gets:

```text
post.created
```

For example:

```text
PostDeleted
    ↓
post.deleted
```

and:

```text
CommentCreated
    ↓
comment.created
```

This gives us a clean naming scheme:

```text
<aggregate>.<event>
```

---

# **9. The outbox contains the routing information**

Our outbox row could contain:

```text
eventType = PostCreated
```

Then our publisher maps:

```text
PostCreated
     ↓
post.created
```

You could store the routing key directly in the outbox too.

For example:

```text
event_type = PostCreated
routing_key = post.created
```

I prefer this when routing decisions may evolve independently of Java class names.

---

# **10. Message conversion**

Our outbox payload is JSON:

```json
{
  "eventId": "...",
  "eventType": "PostCreated",
  "version": 1,
  "occurredAt": "...",
  "data": {
    "postId": 42,
    "projectId": 7,
    "authorId": 15
  }
}
```

We don’t want RabbitMQ receiving a Java object tied to a particular JVM.

The message crossing the boundary should be:

```text
Java object
    ↓
JSON
    ↓
RabbitMQ
    ↓
JSON
    ↓
Java object
```

---

# **11. JSON converter**

Spring AMQP provides message converter support.

Conceptually:

```java
@Bean
JacksonJsonMessageConverter messageConverter(
        ObjectMapper objectMapper) {

    return new JacksonJsonMessageConverter(objectMapper);
}
```

Then configure the `RabbitTemplate` to use it.

The exact converter configuration should match your Spring AMQP version, but the architectural principle is more important:

**Messages crossing service boundaries should have an explicit serialization format.**

---

# **12. Don’t send JPA entities**

Never make:

```java
rabbitTemplate.convertAndSend(post);
```

your event contract.

A `Post` JPA entity is an internal persistence model.

Instead:

```text
Post entity
    ↓
PostCreatedEvent
    ↓
JSON
    ↓
RabbitMQ
```

This keeps persistence and messaging models independent.

---

# **13. Publishing from the outbox**

Our publisher eventually does:

```java
rabbitTemplate.convertAndSend(
        "projecthub.events",
        "post.created",
        event
);
```

Conceptually:

```text
OutboxEvent
   ↓
payload
   ↓
RabbitTemplate
   ↓
Exchange
   ↓
Routing key
   ↓
Queue
```

Spring AMQP’s `RabbitTemplate` supports publisher confirms and returned messages.  

---

# **14. Publisher confirms**

This is one of today’s most important concepts.

Calling:

```java
rabbitTemplate.convertAndSend(...);
```

doesn’t by itself mean:

RabbitMQ has durably accepted this message.

Publishing is asynchronous, and Spring AMQP supports correlated publisher confirms.  

RabbitMQ describes publisher confirms as the publisher-side mechanism for determining whether RabbitMQ has accepted responsibility for the published message.  

So our desired flow is:

```text
Outbox
  ↓
publish
  ↓
RabbitMQ
  ↓
CONFIRM
  ↓
mark outbox PUBLISHED
```

---

# **15. Confirm vs consumer ACK**

Don’t confuse these.

### **Publisher confirm**

```text
ProjectHub → RabbitMQ
```

means:

RabbitMQ accepted the publication.

### **Consumer acknowledgement**

```text
RabbitMQ → NotificationWorker
```

means:

The consumer successfully processed the delivery.

RabbitMQ explicitly describes these as separate mechanisms operating in opposite directions.  

So:

```text
ProjectHub
    │
    │ publisher confirm
    ↓
RabbitMQ
    │
    │ consumer ACK
    ↓
Worker
```

---

# **16. Returned messages**

There’s another failure case.

Suppose:

```text
projecthub.events
```

exists, but nobody has a queue bound for:

```text
post.created
```

The message might not reach a queue.

Spring AMQP supports returned-message handling when publishing is configured as mandatory.  

That’s why reliable publishing needs to think about:

```text
confirm
+
return
```

rather than only:

```text
no Java exception
```

---

# **17. Consumer**

Now our notification consumer:

```java
@Component
public class NotificationConsumer {

    @RabbitListener(queues = "projecthub.notifications")
    public void handle(PostCreatedEvent event) {

        notificationService.notifyProjectMembers(event);
    }
}
```

`@RabbitListener` creates the listener infrastructure that receives messages from the queue and invokes the method.  

---

# **18. The consumer lifecycle**

Think:

```text
RabbitMQ
   ↓
message
   ↓
listener container
   ↓
handle(...)
   ↓
business logic
   ↓
ACK
```

The crucial point:

```text
ACK
```

should happen only after successful processing.

RabbitMQ’s reliability documentation explicitly describes acknowledgements as the mechanism by which the consumer transfers responsibility for the delivery back to the broker.  

---

# **19. Failure before ACK**

Suppose:

```text
RabbitMQ
   ↓
PostCreated
   ↓
NotificationWorker
   ↓
send notification
   ↓
worker crashes
```

No successful ACK happened.

RabbitMQ can redeliver the message according to the configured acknowledgement/recovery behavior.

That’s desirable.

---

# **20. Failure after ACK**

Now:

```text
RabbitMQ
   ↓
message
   ↓
worker
   ↓
ACK
   ↓
worker crashes
   ↓
business operation wasn't actually completed
```

That’s dangerous.

The broker considers the message successfully handled.

Therefore:

**ACK must correspond to actual successful processing.**

RabbitMQ’s documentation makes the same distinction: acknowledgements tell the broker that the consumer has successfully processed the delivery.  

---

# **21. Automatic vs manual acknowledgement**

RabbitMQ supports automatic and manual acknowledgement modes.  

For reliability-sensitive ProjectHub consumers, I want you to understand **manual acknowledgement**.

Conceptually:

```text
receive
  ↓
process
  ↓
ACK
```

rather than:

```text
receive
  ↓
automatically ACK
  ↓
process
```

The latter can lose messages if processing fails after the automatic acknowledgement.

---

# **22. Spring listener configuration**

Conceptually:

```java
@Bean
SimpleRabbitListenerContainerFactory rabbitListenerContainerFactory(
        ConnectionFactory connectionFactory,
        MessageConverter messageConverter) {

    var factory = new SimpleRabbitListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setMessageConverter(messageConverter);

    factory.setAcknowledgeMode(AcknowledgeMode.MANUAL);

    return factory;
}
```

Then:

```java
@RabbitListener(
    queues = "projecthub.notifications",
    containerFactory = "rabbitListenerContainerFactory"
)
public void handle(
        PostCreatedEvent event,
        Channel channel,
        @Header(AmqpHeaders.DELIVERY_TAG) long tag) {

    // process

    channel.basicAck(tag, false);
}
```

This is intentionally lower-level.

We will eventually decide whether ProjectHub actually needs manual `Channel` management or whether container-managed acknowledgement is preferable for a particular consumer.

The important thing right now is understanding the lifecycle.

---

# **23. Failure path**

Conceptually:

```java
try {
    process(event);

    channel.basicAck(tag, false);

} catch (Exception ex) {

    channel.basicNack(
        tag,
        false,
        true
    );
}
```

The last argument:

```text
true
```

means:

requeue it.

RabbitMQ’s negative acknowledgement APIs can either requeue or dead-letter/discard a message depending on the configuration.  

---

# **24. But don’t requeue forever**

This is the poison-message problem again.

```text
message
 ↓
failure
 ↓
requeue
 ↓
failure
 ↓
requeue
 ↓
failure
 ↓
...
```

So ProjectHub needs a retry policy.

---

# **25. Retry architecture**

A conceptual topology:

```text
                    Main Queue
                        ↓
                    Consumer
                        ↓
                  processing fails
                        ↓
                    Retry Queue
                        ↓
                    Consumer
                        ↓
                    processing fails
                        ↓
                      DLQ
```

Or you can use broker/application retry mechanisms that implement delayed retries.

The key concept:

```text
temporary failure
       ↓
retry

permanent failure
       ↓
DLQ
```

---

# **26. Temporary vs permanent failure**

### **Temporary**

```text
Notification API timeout
RabbitMQ dependency unavailable
database temporarily unavailable
```

Retry may make sense.

### **Permanent**

```text
invalid event schema
unknown event version
required field missing
bug causing deterministic failure
```

Repeated retries probably won’t help.

That’s what the DLQ is for.

Spring AMQP supports error handling where listener failures can be requeued, discarded, or routed to a dead-letter exchange depending on configuration.  

---

# **27. Dead-letter exchange**

A conceptual setup:

```text
projecthub.notifications
          |
          | failure
          ↓
projecthub.dlx
          |
          ↓
projecthub.notifications.dlq
```

The DLQ becomes an operational safety net.

Operators can inspect:

```text
eventId
eventType
payload
exception
attempt history
```

and determine whether the event should be repaired/replayed.

RabbitMQ’s dead-lettering mechanism routes rejected/expired messages to a configured dead-letter exchange; with `requeue=false`, a negatively acknowledged message can be dead-lettered rather than requeued.  

---

# **28. One subtle RabbitMQ detail**

A DLQ isn’t automatically an exactly-once recovery mechanism.

RabbitMQ’s documentation distinguishes dead-lettering strategies, and in some configurations dead-letter transfer can have at-most-once behavior; quorum queues support an opt-in at-least-once dead-lettering strategy with additional guarantees and tradeoffs.  

For ProjectHub, don’t think:

“DLQ means data can never be lost.”

Think:

“DLQ gives us a controlled place to isolate messages that cannot currently be processed.”

---

# **29. Consumer concurrency**

Now suppose:

```text
projecthub.notifications
```

has:

```text
NotificationWorker Pod 1
NotificationWorker Pod 2
NotificationWorker Pod 3
```

RabbitMQ can distribute deliveries among consumers.

Inside one Pod, Spring AMQP can also use listener concurrency.

For example:

```text
Pod 1
 ├── Consumer A
 ├── Consumer B
 └── Consumer C
```

Spring AMQP supports listener concurrency configuration.  

But don’t maximize concurrency blindly.

---

# **30. The bottleneck problem**

Suppose:

```text
RabbitMQ
 ↓
30 consumer threads
 ↓
PostgreSQL
```

but PostgreSQL can safely handle only:

```text
10 concurrent operations
```

More consumers can make the entire system slower.

This is exactly the same principle we learned with Kubernetes:

**Scale the bottleneck, not merely the easiest component.**

---

# **31. Prefetch**

RabbitMQ limits the number of outstanding unacknowledged deliveries through prefetch.

Spring AMQP’s current default prefetch is 250, though its documentation notes that lower values can be appropriate for large/slow messages, strict ordering, or more even distribution across consumers.  

For learning, imagine:

```text
prefetch = 1
```

means:

```text
receive 1
 ↓
process
 ↓
ACK
 ↓
receive next
```

while:

```text
prefetch = 100
```

allows many messages to be outstanding.

---

# **32. Don’t use a giant prefetch automatically**

For a notification event that takes:

```text
2 ms
```

high prefetch might help throughput.

For a job that takes:

```text
30 seconds
```

a huge prefetch may mean one consumer holds many messages while other consumers sit idle.

The right value depends on:

```text
processing time
message size
ordering requirements
consumer count
available memory
```

---

# **33. Our first event contract**

Let’s make `PostCreated` explicit:

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

Why include:

```text
version
```

?

Because events live longer than today’s Java classes.

---

# **34. Event versioning**

Imagine version 1:

```json
{
  "version": 1,
  "postId": 42,
  "projectId": 7
}
```

Six months later:

```json
{
  "version": 2,
  "postId": 42,
  "projectId": 7,
  "visibility": "TEAM"
}
```

An old consumer might still understand version 1.

This is why events should be treated as contracts.

Don’t casually rename fields without considering existing consumers.

---

# **35. The event envelope**

I prefer:

```json
{
  "eventId": "...",
  "eventType": "PostCreated",
  "version": 1,
  "occurredAt": "...",
  "data": {
    "postId": 42,
    "projectId": 7,
    "authorId": 15
  }
}
```

This separates:

```text
metadata
```

from:

```text
business data
```

That becomes very useful later.

---

# **36. Correlation**

Eventually we may also include:

```text
correlationId
causationId
```

For example:

```text
HTTP request
   ↓
PostCreated
   ↓
NotificationSent
```

Then:

```text
correlationId
```

can connect the whole workflow.

That’s particularly useful with distributed tracing.

We don’t need to implement it today.

---

# **37. Complete publishing lifecycle**

Let’s put everything together.

```text
1. PostService creates Post
        ↓
2. Outbox row written
        ↓
3. DB COMMIT
        ↓
4. Outbox worker claims event
        ↓
5. status = PROCESSING
        ↓
6. RabbitTemplate publishes
        ↓
7. RabbitMQ confirms
        ↓
8. outbox = PUBLISHED
```

Then:

```text
9. RabbitMQ delivers
        ↓
10. NotificationConsumer
        ↓
11. business operation
        ↓
12. ACK
```

If step 7 fails:

```text
PROCESSING → retry
```

If step 11 fails:

```text
consumer retry
        ↓
eventually DLQ
```

---

# **38. The complete failure model**

This is the mental model I want you to remember:

```text
                 PostgreSQL
                    │
                 Outbox
                    │
             ┌──────┴──────┐
             │             │
          publish       crash
             │             │
             ↓             ↓
          RabbitMQ      retry/recover
             │
             ↓
          Consumer
             │
       ┌─────┴─────┐
       │           │
    success      failure
       │           │
       ↓           ↓
      ACK        retry
                    │
                    ↓
                   DLQ
```

There is no magical “never fails” path.

There are controlled failure paths.

---

# **39. One major architectural principle**

Our application now has **three different reliability boundaries**:

### **Database boundary**

```text
Post + Outbox
```

protected by one PostgreSQL transaction.

### **Broker boundary**

```text
Outbox → RabbitMQ
```

protected by publisher confirms/retry.

### **Consumer boundary**

```text
RabbitMQ → Worker
```

protected by acknowledgements/idempotency/retry/DLQ.

That separation is extremely important.

---

# **40. What I want you to build next**

Don’t implement everything at once.

For ProjectHub, implement in this order:

### **Step 1 — RabbitMQ infrastructure**

Create:

```text
projecthub.events
projecthub.notifications
projecthub.analytics
```

with:

```text
exchange
queues
bindings
```

### **Step 2 — Event DTO**

Create:

```java
PostCreatedEvent
```

with:

```text
eventId
version
occurredAt
postId
projectId
authorId
```

### **Step 3 — Publisher**

Connect:

```text
OutboxPublisher
        ↓
RabbitTemplate
        ↓
projecthub.events
```

### **Step 4 — Consumer**

Create:

```java
@RabbitListener
```

for:

```text
projecthub.notifications
```

### **Step 5 — Failure behavior**

Add:

```text
ACK
NACK
retry
DLQ
```

only after the happy path works.

---

# **Exercise 68**

Before we move on, I want you to reason through this.

### **1. Exchange**

Why does ProjectHub need:

```text
projecthub.events
```

instead of publishing directly to a queue?

---

### **2. Two queues**

Explain why:

```text
PostCreated
      ↓
Exchange
   /     \
  ↓       ↓
Notification  Analytics
Queue         Queue
```

allows both services to receive the same event.

---

### **3. Publisher confirmation**

What is wrong with:

```java
rabbitTemplate.convertAndSend(...);
outbox.markPublished();
```

if we haven’t established that RabbitMQ accepted the publication?

---

### **4. Consumer acknowledgement**

Explain why this ordering is safer:

```text
receive
  ↓
process
  ↓
ACK
```

than:

```text
receive
  ↓
ACK
  ↓
process
```

---

### **5. Poison message**

A consumer fails on the exact same event 50 times.

Why isn’t:

```text
NACK + requeue=true
```

a sufficient failure strategy?

---

### **6. Scaling**

You have:

```text
3 NotificationWorker Pods
```

and each has:

```text
10 listener threads
```

So there could be roughly:

```text
30 concurrent consumers
```

Why might increasing this to:

```text
30 Pods × 20 threads
```

make the system **less** reliable rather than more reliable?

---

### **7. Final design**

Draw this complete path:

```text
POST /projects/7/posts
       ↓
Post + Outbox
       ↓
PostgreSQL COMMIT
       ↓
Outbox Publisher
       ↓
RabbitMQ
       ↓
Exchange
       ↓
Notification Queue
       ↓
Notification Consumer
       ↓
Idempotency
       ↓
ACK
```

And mark where these can occur:

```text
retry
crash
duplicate
DLQ
```

After this, **Lesson 69** will put the whole thing together: we’ll build the actual ProjectHub RabbitMQ configuration and walk through a real `PostCreated` message from PostgreSQL all the way to an idempotent consumer.