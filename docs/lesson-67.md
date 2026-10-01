---
title: Lesson 67: RabbitMQ in ProjectHub
sidebar_position: 67
---

Now we connect our outbox to the message broker.

The current Spring AMQP reference is 4.1.1. Spring AMQP provides `RabbitTemplate` for sending messages and `@RabbitListener` for receiving them.  

Our architecture becomes:

```text
PostgreSQL
    │
    │ outbox
    ↓
Outbox Publisher
    │
    │ publish
    ↓
RabbitMQ Exchange
    │
    ├───────────────┐
    ↓               ↓
Notification     Analytics
 Queue             Queue
    │               │
    ↓               ↓
Worker            Worker
```

---

## **1. First: understand RabbitMQ’s vocabulary**

There are four concepts you need to separate:

```text
Producer
Exchange
Queue
Consumer
```

### **Producer**

Our ProjectHub outbox publisher.

```text
Outbox → Producer
```

It sends a message.

### **Exchange**

Receives the message and decides where it should go.

### **Queue**

Stores messages waiting for consumers.

### **Consumer**

Reads messages from a queue and processes them.

So:

```text
Producer
   ↓
Exchange
   ↓
Queue
   ↓
Consumer
```

---

# **2. Exchange vs queue**

This is one of the most important RabbitMQ concepts.

Don’t think:

```text
publisher → queue
```

Think:

```text
publisher → exchange → queue
```

The exchange is responsible for routing.

For example:

```text
                    projecthub.events
                           │
              ┌────────────┴────────────┐
              ↓                         ↓
      notification.queue         analytics.queue
              ↓                         ↓
       NotificationWorker        AnalyticsWorker
```

The same event can therefore reach multiple consumers.

---

# **3. Why this is useful for ProjectHub**

Suppose:

```text
PostCreated
```

happens.

We might want:

```text
NotificationService
```

to send notifications.

But also:

```text
AnalyticsService
```

to record analytics.

We don’t want the PostService to know about either one.

Instead:

```text
PostService
    ↓
Outbox
    ↓
RabbitMQ exchange
   /        \
  ↓          ↓
notification analytics
```

This is loose coupling.

---

# **4. Exchange types**

RabbitMQ has several exchange types.

The important ones initially are:

```text
direct
topic
fanout
```

### **Direct**

Routes based on an exact routing key.

```text
post.created
```

### **Topic**

Routes using routing-key patterns.

For example:

```text
post.created
post.deleted
comment.created
```

and consumers can subscribe to patterns such as:

```text
post.*
```

### **Fanout**

Broadcasts to bound queues.

```text
             exchange
            /    |    \
           ↓     ↓     ↓
          Q1    Q2    Q3
```

For ProjectHub events, **topic exchange** is a useful mental model.

---

# **5. Routing keys**

Suppose our exchange is:

```text
projecthub.events
```

and our message has:

```text
routing key = post.created
```

Then:

```text
projecthub.events
        |
        | post.created
        ↓
notification.queue
```

If analytics is interested in all post events:

```text
post.*
```

it can have a binding that matches that pattern.

---

# **6. Spring configuration**

We can declare the infrastructure with Spring beans.

Conceptually:

```java
@Bean
TopicExchange projectHubExchange() {
    return new TopicExchange("projecthub.events");
}
```

Then:

```java
@Bean
Queue notificationQueue() {
    return QueueBuilder
            .durable("projecthub.notifications")
            .build();
}
```

And bind them:

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

The exact Spring AMQP APIs should be checked against the version you’re using; the current reference provides these exchange/queue/binding abstractions.  

---

# **7. Durable queues**

Notice:

```java
.durable("projecthub.notifications")
```

We want the queue to survive a RabbitMQ restart.

Likewise, important exchanges and messages should be configured with appropriate durability/persistence.

Don’t confuse:

```text
durable queue
```

with:

```text
message has been processed
```

They’re different concerns.

---

# 

# **8. Publishing with**

**`RabbitTemplate`**

Spring AMQP provides:

```java
RabbitTemplate
```

for sending messages.  

Conceptually:

```java
rabbitTemplate.convertAndSend(
    "projecthub.events",
    "post.created",
    event
);
```

So our outbox publisher becomes:

```text
OutboxEvent
    ↓
deserialize/prepare payload
    ↓
RabbitTemplate
    ↓
projecthub.events
    ↓
post.created
```

---

# **9. Why the outbox still matters**

You might ask:

Why not just call `RabbitTemplate` directly from `PostService`?

Because we would return to the dual-write problem.

Bad:

```text
DB transaction
   ↓
save Post
   ↓
publish RabbitMQ
   ↓
RabbitMQ fails
```

Now:

```text
Post exists
Event doesn't
```

The outbox solves this:

```text
DB transaction
   ↓
save Post
   ↓
save OutboxEvent
   ↓
COMMIT
```

Then:

```text
Outbox
   ↓
RabbitMQ
```

---

# **10. Publisher confirms**

There’s another important problem.

Suppose:

```text
RabbitTemplate.convertAndSend(...)
```

returns without an obvious exception.

Can we immediately say:

“The broker definitely accepted my message”?

For reliable publishing, RabbitMQ publisher confirms are important.

Spring AMQP supports publisher confirms through `RabbitTemplate` and `CachingConnectionFactory`; confirms can report an acknowledgement or negative acknowledgement.  

Conceptually:

```text
Publisher
   ↓
RabbitMQ
   ↓
CONFIRM
```

Only after appropriate confirmation should we consider the outbox event successfully published.

---

# **11. Return vs confirm**

There’s another subtle failure:

```text
message
 ↓
exchange
 ↓
no matching queue
```

A message can potentially be unroutable.

Spring AMQP supports returned-message callbacks for such cases, while publisher confirms provide broker confirmation.  

So reliable publishing involves thinking about both:

```text
Was the message accepted?
```

and:

```text
Was it routed as expected?
```

---

# **12. Our publisher now**

Conceptually:

```java
for (OutboxEvent event : events) {

    try {

        rabbitTemplate.convertAndSend(
            "projecthub.events",
            event.getRoutingKey(),
            event.getPayload()
        );

        markPublished(event);

    } catch (Exception ex) {

        retry(event, ex);
    }
}
```

But remember:

**real publisher-confirm handling is more nuanced than simply assuming** **`convertAndSend()`** **returning means end-to-end success.**

We’ll keep that distinction in mind as we implement it.

---

# **13. Now consumers**

Spring AMQP makes consumers pleasantly simple.

```java
@Component
public class NotificationConsumer {

    @RabbitListener(queues = "projecthub.notifications")
    public void handle(PostCreatedEvent event) {

        // process event
    }
}
```

Spring creates the listener infrastructure behind the scenes.  

The important conceptual transformation is:

```text
RabbitMQ
   ↓
listener container
   ↓
Java method
```

---

# **14. Acknowledgements**

Now we hit another critical concept.

Suppose RabbitMQ sends:

```text
PostCreated
```

to our consumer.

The consumer processes it.

How does RabbitMQ know:

“You successfully handled this message”?

Through an **acknowledgement**.

RabbitMQ supports explicit acknowledgements, and its documentation recommends considering manual acknowledgement when reliability matters.  

---

# **15. Why acknowledgement matters**

Imagine:

```text
RabbitMQ
   ↓
consumer receives message
   ↓
consumer crashes
```

If RabbitMQ already considered the message finished:

```text
message = gone
```

We may lose the event.

With appropriate acknowledgement semantics:

```text
message
   ↓
consumer
   ↓
processing
   ↓
ACK
```

the broker knows the message has been successfully handled.

If the consumer dies before acknowledging, the message can be redelivered according to the broker/container configuration.

---

# **16. The dangerous side**

Suppose:

```text
consumer receives
 ↓
ACK
 ↓
application crashes
 ↓
business operation never happened
```

Now the message is gone from the consumer’s perspective.

Therefore:

**Acknowledgement should happen only after the consumer has successfully completed the work it is responsible for.**

This is why acknowledgment and transaction boundaries matter so much.

---

# **17. Spring’s listener behavior**

With `@RabbitListener`, exceptions from the listener are handled by the listener container.

Depending on configuration, a failed message may be requeued, discarded, or routed to a dead-letter exchange.  

That means:

```java
@RabbitListener(queues = "projecthub.notifications")
public void handle(PostCreatedEvent event) {

    notificationService.send(event);

}
```

If:

```text
send()
```

throws, the listener container gets involved.

Exactly what happens next depends on the acknowledgment/error/requeue configuration.

---

# **18. Don’t blindly requeue forever**

Suppose:

```text
PostCreated
   ↓
consumer
   ↓
bug
   ↓
exception
   ↓
requeue
   ↓
consumer
   ↓
same bug
   ↓
requeue
   ↓
...
```

You can create an infinite poison-message loop.

So we need a retry policy.

---

# **19. Retry and DLQ**

A common architecture is:

```text
Main Queue
    ↓
processing fails
    ↓
retry
    ↓
retry
    ↓
retry
    ↓
too many failures
    ↓
Dead Letter Queue
```

RabbitMQ dead-lettering can route messages to a dead-letter exchange when they are rejected without requeue, expire, exceed queue limits, or hit certain delivery limits.  

---

# **20. What is a poison message?**

Imagine this event:

```json
{
  "eventType": "PostCreated",
  "postId": "NOT-A-NUMBER"
}
```

and your consumer expects:

```java
Long postId
```

Every attempt fails.

Retrying forever doesn’t fix it.

That’s a:

**poison message**

It should eventually be isolated.

---

# **21. Dead Letter Queue**

We might have:

```text
projecthub.notifications
        ↓
       retry
        ↓
       retry
        ↓
       retry
        ↓
projecthub.notifications.dlq
```

The DLQ lets operators inspect:

```text
event ID
event type
payload
failure reason
```

and decide what to do.

---

# **22. Publisher retry vs consumer retry**

These are **different failures**.

### **Publisher failure**

```text
ProjectHub
   ↓
RabbitMQ
```

Maybe RabbitMQ is unavailable.

The **outbox publisher** retries.

### **Consumer failure**

```text
RabbitMQ
   ↓
Notification Worker
```

Maybe the notification service has a bug.

The **consumer** retries / dead-letters.

Don’t mix the two.

---

# **23. RabbitMQ consumer concurrency**

Suppose:

```text
notification.queue
```

has one consumer.

You might process:

```text
100 messages/sec
```

but your traffic grows to:

```text
1,000 messages/sec
```

You can increase consumer concurrency.

Spring AMQP supports listener concurrency configuration; `@RabbitListener` can specify concurrency such as `"3"` or `"3-10"` depending on the listener container type.  

Conceptually:

```text
Queue
 │
 ├── Consumer 1
 ├── Consumer 2
 ├── Consumer 3
 └── Consumer 4
```

---

# **24. Kubernetes gives us another scaling layer**

We can also run:

```text
NotificationWorker
   Pod 1
   Pod 2
   Pod 3
```

all consuming the same queue.

Then RabbitMQ distributes messages among consumers.

So there are potentially two forms of concurrency:

```text
Kubernetes Pods
        +
Spring listener concurrency
```

Don’t blindly maximize both.

You can overwhelm:

```text
PostgreSQL
external APIs
RabbitMQ
CPU
memory
```

---

# **25. Prefetch**

RabbitMQ also has the concept of **prefetch**.

It controls how many unacknowledged messages can be delivered to a consumer.

Spring AMQP’s current documentation notes a default prefetch of 250 for its relevant listener container behavior, while also explaining cases where a lower value is appropriate, such as large/slow messages or strict ordering.  

Conceptually:

```text
prefetch = 1

Consumer:
  processing one
  ↓
  ACK
  ↓
  next
```

versus:

```text
prefetch = 100

Consumer:
  receives 100
  ↓
  processes them
```

---

# **26. Why high prefetch isn’t always better**

Imagine each message takes:

```text
5 seconds
```

and a consumer receives:

```text
250 messages
```

It may hold a large number of unprocessed deliveries.

Memory can grow, and distribution between consumers can become less even.

RabbitMQ’s documentation specifically notes the tradeoff between throughput and the number of outstanding unacknowledged deliveries.  

---

# **27. Ordering**

Suppose we have:

```text
PostCreated
PostUpdated
PostDeleted
```

If order matters, high concurrency can complicate things.

You need to determine:

Do these events need to be processed in order?

If yes, you need a messaging design that preserves the required ordering boundary.

For example:

```text
same post → same logical ordering key
```

Don’t simply add 20 consumers and assume order survives.

---

# **28. RabbitMQ architecture for ProjectHub**

Let’s make our event infrastructure concrete:

```text
Exchange:
projecthub.events
```

Queues:

```text
projecthub.notifications
projecthub.analytics
```

Bindings:

```text
post.* → notifications
post.* → analytics
```

Potentially later:

```text
project.* → notifications
comment.* → notifications
```

---

# 

# 

# **29. A complete**

**`PostCreated`**

**flow**

Now everything connects.

### **Step 1**

Alice sends:

```http
POST /projects/7/posts
```

### **Step 2**

Spring Security authenticates Alice.

### **Step 3**

Authorization checks:

```text
posts.create
+
Project 7 membership
```

### **Step 4**

Transaction:

```text
INSERT post
INSERT outbox_event
COMMIT
```

### **Step 5**

HTTP returns:

```http
201 Created
```

### **Step 6**

Outbox worker claims:

```text
PostCreated
```

### **Step 7**

Worker publishes:

```text
projecthub.events
routing key = post.created
```

### **Step 8**

RabbitMQ routes to:

```text
notification queue
analytics queue
```

### **Step 9**

Consumers process independently.

```text
NotificationWorker
AnalyticsWorker
```

---

# **30. Why this architecture is powerful**

The PostService doesn’t know:

```text
who receives the event
how many consumers exist
where analytics is deployed
whether notification is temporarily down
```

It only knows:

```text
Post was created
```

That’s the meaning of an event.

---

# **31. Commands vs events**

This is worth reinforcing.

### **Command**

```text
SendNotification
```

means:

Please do this.

### **Event**

```text
PostCreated
```

means:

This happened.

Our outbox is primarily publishing **events**.

```text
PostCreated
CommentCreated
ProjectCreated
MemberAdded
```

Consumers independently decide what to do with those facts.

---

# **32. Don’t put authorization into RabbitMQ**

This is an important ProjectHub rule.

Don’t do:

```text
PostCreated
 ↓
consumer decides whether Alice was allowed to create it
```

Authorization should have happened synchronously:

```text
HTTP
 ↓
authentication
 ↓
posts.create
 ↓
membership
 ↓
database transaction
```

The event represents a successful domain fact:

```text
PostCreated
```

not an authorization request.

---

# **33. Don’t make RabbitMQ your source of truth**

The source of truth for:

```text
Post
Project
User
Membership
Permissions
```

is still PostgreSQL.

RabbitMQ is transporting events.

If RabbitMQ disappears temporarily:

```text
Post data remains
Outbox data remains
```

and the publisher can catch up later.

That’s one of the core benefits of the outbox.

---

# **34. The final architecture**

ProjectHub is now becoming:

```text
                         Internet
                            │
                            ↓
                         Gateway
                            │
                            ↓
                    ProjectHub Service
                            │
                    ┌───────┴────────┐
                    ↓                ↓
                 Pod 1             Pod N
                    │                │
                    └───────┬────────┘
                            ↓
                       PostgreSQL
                      /           \
                 domain data     outbox
                                   │
                                   ↓
                            Outbox Publishers
                                   │
                                   ↓
                         projecthub.events
                                   │
                     ┌─────────────┴─────────────┐
                     ↓                           ↓
              notification queue          analytics queue
                     ↓                           ↓
              Notification                 Analytics
                Workers                    Workers
```

And:

```text
Metrics
Logs
Traces
Alerts
```

surround the system.

---

# **35. One more production detail: publisher confirms**

For the next implementation, don’t make this assumption:

```java
rabbitTemplate.convertAndSend(...);
markPublished();
```

and call it guaranteed.

The publisher should have a clear definition of:

“RabbitMQ accepted this publication.”

Spring AMQP supports publisher confirms through `RabbitTemplate`, including correlation data and confirm callbacks.  

This will matter when we implement the actual publisher.

---

# **Exercise 67**

Before we write the RabbitMQ configuration, design it.

### **1. Draw this**

```text
OutboxEvent
    ↓
RabbitMQ
    ↓
Exchange
    ↓
Notification Queue
    ↓
Notification Consumer
```

Label the role of each component.

---

### **2. Routing**

We have:

```text
PostCreated
PostDeleted
CommentCreated
ProjectCreated
```

Design routing keys for them.

Then explain why a topic exchange could be useful.

---

### **3. Queues**

Why should we have:

```text
notification.queue
analytics.queue
```

instead of one:

```text
projecthub.queue
```

if both notification and analytics need every `PostCreated` event?

---

### **4. Acknowledgement**

Explain this failure:

```text
RabbitMQ
   ↓
NotificationWorker
   ↓
send notification
   ↓
worker crashes
   ↓
ACK never happens
```

What should happen to the message?

Then explain the opposite:

```text
RabbitMQ
   ↓
NotificationWorker
   ↓
ACK
   ↓
worker crashes
   ↓
business operation wasn't actually completed
```

Why is that dangerous?

---

### **5. Poison message**

Suppose:

```text
PostCreated event
```

contains invalid JSON.

What happens if the consumer simply keeps requeueing it forever?

Design:

```text
retry
retry
retry
↓
DLQ
```

---

### **6. Scaling**

You have:

```text
notification.queue
```

and:

```text
NotificationWorker Pod 1
NotificationWorker Pod 2
NotificationWorker Pod 3
```

Explain how messages should be distributed.

Then explain what could happen if you simultaneously increase:

```text
Pods: 3 → 30
```

and:

```text
listener concurrency: 5 → 20
```

---

### **7. Hardest question**

Explain why this is **not** a complete reliable messaging architecture:

```text
PostService
   ↓
RabbitTemplate
   ↓
RabbitMQ
```

and why this is substantially stronger:

```text
PostService
   ↓
Post + Outbox
   ↓
COMMIT
   ↓
Outbox Publisher
   ↓
RabbitMQ
   ↓
Idempotent Consumer
   ↓
ACK
```

Once you understand this, we’ll move to **Lesson 68 — implementing RabbitMQ in ProjectHub**, including the exchange/queues/bindings, JSON message conversion, publisher confirms, `@RabbitListener`, acknowledgements, retries, and DLQ.