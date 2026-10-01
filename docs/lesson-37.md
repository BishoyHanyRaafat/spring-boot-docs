---
title: Lesson 37: RabbitMQ Deep Dive + Building the ProjectHub Event System
sidebar_position: 37
---


Today we stop talking about RabbitMQ as a concept and start designing a **real event-driven backend**.

By the end of this lesson, ProjectHub will have this architecture:

```text
                         ProjectHub

Client
  |
  v
Spring Boot API
  |
  |
  +----------------+
  |                |
  v                v

PostgreSQL       RabbitMQ
                    |
                    |
             Project Events
                    |
        +-----------+-----------+
        |           |           |
        v           v           v

 Notification   Analytics    Search
 Service        Service      Service
```

The important idea:

The Project service creates the event.

It does **not** care who consumes it.

---

# **1. The RabbitMQ mental model**

Let’s build the vocabulary first.

RabbitMQ has four main concepts:

```text
Producer
    |
    v
Exchange
    |
    v
Queue
    |
    v
Consumer
```

Let’s map this to ProjectHub.

---

## **Producer**

The application creating messages.

Example:

```text
Project Service
```

When a project is created:

```json
{
  "eventType": "PROJECT_CREATED",
  "projectId": 10
}
```

---

## **Exchange**

The router.

It receives messages and decides where they go.

Think:

```text
Airport

Incoming flights
       |
       v
Control tower
       |
       +---- Terminal A
       |
       +---- Terminal B
```

The exchange is the control tower.

---

## **Queue**

A waiting area for messages.

Example:

```
notification.queue
```

Messages wait there until processed.

---

## **Consumer**

The code reading from the queue.

Example:

```text
NotificationService
```

---

# **2. Why not send directly to queues?**

A beginner design:

```
ProjectService

    |
    v

notification.queue
```

Problem:

Tomorrow we add:

```
analytics.queue
search.queue
audit.queue
```

Now ProjectService knows everything:

```java
send(notification)
send(analytics)
send(search)
send(audit)
```

This creates tight coupling.

---

Better:

```
ProjectService

      |
      v

Project Exchange

      |
      +------ notification queue
      |
      +------ analytics queue
      |
      +------ search queue
```

The producer only knows:

```
Project Exchange exists
```

---

# **3. Exchange types**

RabbitMQ has different routing strategies.

---

# **Direct Exchange**

Exact match.

Example:

Message:

```
routing key:

project.created
```

Queue binding:

```
project.created
```

Result:

```
MATCH → deliver
```

---

# **Topic Exchange**

Pattern matching.

Example events:

```
project.created
project.deleted
project.updated

user.created
user.deleted
```

Binding:

```
project.*
```

Receives:

```
project.created
project.deleted
project.updated
```

Does not receive:

```
user.created
```

Very common for events.

---

# **Fanout Exchange**

Broadcast everything.

Example:

```
ProjectCreated
```

goes to:

```
Notification
Analytics
Search
Audit
```

No routing key.

---

# **4. Our ProjectHub event design**

Let’s design:

Exchange:

```
project.events.exchange
```

Type:

```
topic
```

Events:

```
project.created
project.updated
project.deleted
```

Queues:

```
notification.queue

analytics.queue

search.queue
```

Bindings:

```
notification.queue
       |
       |
project.*
```

or more specific:

```
project.created
```

---

# **5. Add RabbitMQ configuration**

Create:

```
RabbitMQConfig.java
```

```java
@Configuration
public class RabbitMQConfig {


    public static final String EXCHANGE =
            "project.events.exchange";


    public static final String PROJECT_CREATED =
            "project.created";


}
```

This gives us centralized names.

Avoid:

```java
rabbitTemplate.convertAndSend(
 "abc",
 "xyz",
 event
);
```

because six months later nobody knows what `"abc"` means.

---

# **6. Create the exchange**

```java
@Bean
TopicExchange projectExchange(){

    return new TopicExchange(
        RabbitMQConfig.EXCHANGE
    );

}
```

Now RabbitMQ has:

```
project.events.exchange
```

---

# **7. Create a queue**

Example:

Notification queue:

```java
@Bean
Queue notificationQueue(){

    return new Queue(
        "notification.queue"
    );

}
```

RabbitMQ now has:

```
Queue:

notification.queue
```

---

# **8. Create a binding**

Connect queue to exchange:

```java
@Bean
Binding notificationBinding(
        Queue notificationQueue,
        TopicExchange exchange
){

    return BindingBuilder
        .bind(notificationQueue)
        .to(exchange)
        .with("project.created");

}
```

Meaning:

```
Exchange

project.created

        |
        |
        v

notification.queue
```

---

# **9. The complete topology**

Now RabbitMQ looks like:

```
              project.events.exchange


                     |
        project.created routing key


          /              |              \


         v               v               v


notification      analytics          search
queue             queue              queue
```

---

# **10. Create the event object**

Events should be simple.

Example:

```java
public record ProjectCreatedEvent(

    Long projectId,

    Long ownerId,

    Instant createdAt

){

}
```

Important:

Events are contracts.

Changing them later affects consumers.

---

# **11. Publishing events**

Inside ProjectService:

```java
@Service
@RequiredArgsConstructor
public class ProjectService {


private final RabbitTemplate rabbitTemplate;


public Project createProject(
        CreateProjectRequest request
){

    Project project =
        repository.save(
            new Project(...)
        );


    ProjectCreatedEvent event =
        new ProjectCreatedEvent(
            project.getId(),
            project.getOwnerId(),
            Instant.now()
        );


    rabbitTemplate.convertAndSend(
        RabbitMQConfig.EXCHANGE,
        "project.created",
        event
    );


    return project;

}

}
```

Flow:

```
HTTP request

    |
    v

Save PostgreSQL

    |
    v

Create event

    |
    v

RabbitTemplate

    |
    v

RabbitMQ
```

---

# **12. Message serialization**

Question:

How does this:

```java
ProjectCreatedEvent
```

become:

```
JSON
```

?

Spring AMQP uses message converters.

Conceptually:

```
Java Object

      |
      |
      v

JSON Message

      |
      |
      v

RabbitMQ
```

Example:

```json
{
 "projectId":10,
 "ownerId":5,
 "createdAt":"2026-01-01T10:00:00Z"
}
```

---

# **13. Consuming messages**

Create:

```java
@Component
public class NotificationConsumer {


@RabbitListener(
    queues="notification.queue"
)
public void consume(
        ProjectCreatedEvent event
){

    System.out.println(
       "Sending notification for project "
       + event.projectId()
    );

}

}
```

Now:

```
RabbitMQ

project.created

      |

notification.queue

      |

@RabbitListener

      |

Java method
```

---

# **14. What happens after publishing?**

Let’s trace:

User:

```
POST /projects
```

Project service:

```
Save project
```

Creates:

```json
{
 "projectId":10
}
```

Publishes:

```
project.created
```

RabbitMQ:

```
project.events.exchange

        |
        |
        v

notification.queue
```

Consumer:

```
handle(event)
```

Done.

---

# **15. The hidden power: multiple consumers**

Tomorrow:

Add:

```
AnalyticsService
```

It creates:

```
analytics.queue
```

with:

```
project.*
```

binding.

Now:

```
             Exchange

                |
                |
        PROJECT_CREATED


        /        |          \


Notification Analytics Search
```

ProjectService code does not change.

This is the main benefit.

---

# **16. Reliability problem #1**

Let’s revisit:

```text
Save database

      ↓

Publish event
```

Imagine:

```
Database ✅

RabbitMQ ❌
```

Result:

```
Project exists

Nobody knows
```

We lost the event.

This is a serious production problem.

---

# **17. The Outbox Pattern**

The solution:

Store events in the database first.

Architecture:

```
                 PostgreSQL


projects table

outbox_events table


        |
        |
        v

Background Publisher

        |
        |
        v

RabbitMQ
```

---

# **18. How it works**

Transaction:

```text
BEGIN


Insert project


Insert event:

PROJECT_CREATED


COMMIT
```

Now both exist.

Either:

```
Both saved
```

or:

```
Neither saved
```

Database consistency is preserved.

---

# **19. Outbox table example**

```sql
CREATE TABLE outbox_events (

    id UUID PRIMARY KEY,

    event_type VARCHAR(100),

    payload JSONB,

    created_at TIMESTAMP,

    processed BOOLEAN

);
```

Example row:

```
id:
123

event_type:
PROJECT_CREATED

payload:
{
 "projectId":10
}
```

---

# **20. Publisher process**

A background job:

```
Every few seconds:

Find unprocessed events

      |

Publish to RabbitMQ

      |

Mark processed=true
```

Flow:

```
Outbox table

      |
      v

RabbitMQ

      |
      v

Consumers
```

This pattern is extremely common in serious systems.

---

# **21. Reliability problem #2**

What if:

```
Consumer receives message

     |

Application crashes

     |

Before finishing
```

Did it process?

Unknown.

Solution:

Acknowledgements.

---

# **22. Message acknowledgements**

RabbitMQ supports:

## **Auto acknowledge**

Meaning:

```
Receive message

Immediately delete
```

Danger:

```
Receive

Crash

Message lost
```

---

## **Manual acknowledge**

Meaning:

```
Receive message

Process successfully

Acknowledge

Delete message
```

Safer.

---

# **23. Consumer failure flow**

Example:

```
Queue:

[ProjectCreated]


Consumer receives


Processing...


Crash!


Message returns to queue


Retry later
```

---

# **24. Retry strategy**

Real systems need:

```
Attempt 1

failed

wait

Attempt 2

failed

wait

Attempt 3

failed
```

Then:

```
Dead Letter Queue
```

---

# **25. Dead Letter Queue**

A failed-message storage.

Architecture:

```
Main Queue

    |
    |
 failures

    |
    v

Dead Letter Queue
```

Example:

```
failed.notification.queue
```

Developers can inspect:

```
Why did this fail?
```

---

# **26. Event naming rules**

Good:

```
ProjectCreated
UserRegistered
PaymentCompleted
```

Bad:

```
CreateProject
SendEmail
UpdateSomething
```

Why?

Events are facts.

They happened.

---

# **27. Events should contain enough information**

Bad:

```json
{
 "projectId":10
}
```

Maybe consumer needs:

```
ownerId
createdAt
projectName
```

Good:

```json
{
 "projectId":10,
 "ownerId":5,
 "name":"ProjectHub",
 "createdAt":"..."
}
```

But don’t put everything.

Avoid huge events.

---

# **28. Events are contracts**

Imagine:

Version 1:

```json
{
"id":10
}
```

Consumers depend on it.

Then suddenly:

```json
{
"project_id":10
}
```

You broke everyone.

Event evolution needs discipline.

Later we’ll discuss:

- versioning
- backward compatibility
- schema evolution

---

# **29. ProjectHub after this lesson**

Our backend now looks like:

```
                       Client

                         |
                         v

                  Spring Boot API

                         |
          +--------------+--------------+

          v                             v

    PostgreSQL                    RabbitMQ


                                      |
                                      |

                 +--------------------+----------------+

                 v                    v                v


          Notification          Analytics          Search
```

This is no longer a simple CRUD application.

It is becoming a distributed system.

---

# **30. Key lessons today**

Remember these:

### **Exchange**

```
Routes messages
```

### **Queue**

```
Stores messages
```

### **Producer**

```
Creates messages
```

### **Consumer**

```
Processes messages
```

### **Event**

```
A fact that already happened
```

### **Outbox**

```
Makes database + messaging reliable
```

---

# **Exercise 37**

Answer these:

### **1.**

Why is this architecture better?

```
ProjectService
      |
      v
RabbitMQ
      |
      +---- Notification
      |
      +---- Analytics
      |
      +---- Search
```

compared with:

```
ProjectService
 |
 +--> NotificationService
 |
 +--> AnalyticsService
 |
 +--> SearchService
```

---

### **2.**

Explain:

```
Exchange
Queue
Binding
Routing Key
```

---

### **3.**

Why is:

```
ProjectCreated
```

better than:

```
CreateProject
```

as an event?

---

### **4.**

What problem does the Outbox Pattern solve?

---

### **5.**

A consumer crashes after receiving a message.

What should happen?

---

### **6.**

Should the Project service know that a Notification service exists?

Why?

---

Next lesson:

# **Lesson 38 — Building a Complete Event-Driven ProjectHub Feature**

We will implement a complete workflow:

```
User creates project

        |
        v

Database transaction

        |
        v

Outbox event

        |
        v

RabbitMQ

        |
        +---- Notification worker
        |
        +---- Audit worker
        |
        +---- Search indexing worker
```

We’ll also learn:

- transactional events
- idempotent consumers
- duplicate messages
- exactly-once vs at-least-once delivery
- production messaging patterns.