---
title: Lesson 36: Messaging with RabbitMQ Building Asynchronous Systems
sidebar_position: 36
---


This lesson is indeed a fun one because we are moving from:

```text
Single application
```

into:

```text
Multiple components communicating with each other
```

This is the point where backend engineering starts feeling like **real production architecture**.

So far ProjectHub looks like:

```text
                 ProjectHub

Client
  |
  v
Spring Boot
  |
  v
PostgreSQL
  |
  v
Redis
```

Everything happens inside one request.

Example:

```http
POST /projects
```

Flow:

```text
Client
  |
  v
Controller
  |
  v
ProjectService
  |
  v
Save project
  |
  v
Return response
```

Simple.

But now imagine after creating a project we want to:

- send email notifications
- notify team members
- update analytics
- generate audit logs
- index search data
- trigger background jobs

Should the user wait for all of that?

Probably not.

---

# **1. The problem with synchronous systems**

Imagine:

```java
@PostMapping("/projects")
public ProjectResponse createProject(){

    Project project =
        projectService.create();


    emailService.sendEmail();

    analyticsService.record();

    notificationService.notifyUsers();

    searchService.index();


    return response;

}
```

The request becomes:

```text
Create project
      |
      |
      +--> Save database
      |
      +--> Send email
      |
      +--> Update analytics
      |
      +--> Update search
      |
      +--> Notify users
      |
      v
Return response
```

The user waits for everything.

Problems:

## **1. Slow response**

If email takes:

```text
3 seconds
```

your API takes:

```text
3 seconds longer
```

---

## **2. Failure coupling**

Suppose:

```text
Database ✅

Email service ❌
```

Should project creation fail?

Maybe not.

The project exists.

The email is a secondary action.

---

## **3. Hard scaling**

Imagine:

```text
100,000 project creations
```

and every creation triggers:

```text
emails
notifications
analytics
```

The main application becomes overloaded.

---

# **2. The asynchronous idea**

Instead of:

```text
Project Service
      |
      |
      v
Email Service
```

we do:

```text
Project Service
      |
      |
      v
Message Broker
      |
      |
      v
Email Service
```

The Project Service says:

“A project was created.”

It doesn’t care who listens.

---

# **3. Enter RabbitMQ**

RabbitMQ is a **message broker**.

Its job:

```text
Receive messages

Store messages

Deliver messages
```

Think of it as a mailbox.

Architecture:

```text
Producer
    |
    |
    v
RabbitMQ
    |
    |
    v
Consumer
```

---

# **4. Terminology**

These words are important.

## **Producer**

The application that sends messages.

Example:

```text
Project Service
```

creates:

```json
{
 "event":"PROJECT_CREATED",
 "projectId":10
}
```

---

## **Consumer**

The application that receives messages.

Example:

```text
Notification Service
```

receives:

```json
{
 "event":"PROJECT_CREATED",
 "projectId":10
}
```

and sends notifications.

---

## **Queue**

A queue stores messages.

Example:

```
project-events-queue
```

Messages wait there until consumed.

Visual:

```text
RabbitMQ

Queue:

[message1]
[message2]
[message3]
```

---

# **5. Real ProjectHub example**

User creates a project:

```http
POST /projects
```

The API does:

```text
Create project
      |
      v
Save PostgreSQL
      |
      v
Publish event
      |
      v
Return HTTP 201
```

Meanwhile:

```text
RabbitMQ

PROJECT_CREATED
        |
        |
        v

Notification Service

        |
        v

Send emails
```

The user doesn’t wait.

---

# **6. Events**

The message usually represents something that happened.

Example:

```json
{
    "eventType": "PROJECT_CREATED",
    "projectId": 42,
    "createdBy": 7,
    "timestamp": "2026-01-01T10:00:00"
}
```

Notice the wording:

Not:

```
CREATE_PROJECT
```

but:

```
PROJECT_CREATED
```

Why?

Because events describe facts.

Something already happened.

---

Compare:

Command:

```
CreateProject
```

means:

Please do this.

Event:

```
ProjectCreated
```

means:

This already happened.

Important distinction.

---

# **7. RabbitMQ architecture**

The simplified RabbitMQ model:

```text
              Producer

                 |
                 |
                 v

             Exchange

                 |
                 |
                 v

              Queue

                 |
                 |
                 v

             Consumer
```

There are four important pieces:

1. Producer
2. Exchange
3. Queue
4. Consumer

---

# **8. Why do we need an Exchange?**

A beginner question:

Why not:

```text
Producer
    |
    v
Queue
    |
    v
Consumer
```

Why add:

```text
Exchange
```

?

Because RabbitMQ allows flexible routing.

Example:

One event:

```
PROJECT_CREATED
```

might go to:

```
Notification Service

Analytics Service

Search Service
```

The exchange decides where it goes.

---

# **9. Types of exchanges**

RabbitMQ has several exchange types.

## **Direct exchange**

Routes by exact key.

Example:

```
routing key:

project.created
```

Queue:

```
project-created-queue
```

---

## **Topic exchange**

Routes by patterns.

Example:

Events:

```
project.created
project.deleted
user.created
```

Consumer:

```
project.*
```

receives:

```
project.created
project.deleted
```

but not:

```
user.created
```

---

## **Fanout exchange**

Broadcast.

One message:

```
PROJECT_CREATED
```

goes everywhere.

Example:

```text
             Exchange

          /     |      \

Notification Analytics Search
```

---

# **10. Our ProjectHub design**

Let’s imagine:

```text
                 Project Service

                       |
                       |
                       v

              project.events.exchange


                 /          |          \


                v           v           v


        Notification    Analytics     Search
          Queue          Queue        Queue
```

One event.

Multiple consumers.

---

# **11. Adding RabbitMQ to Docker Compose**

Our infrastructure becomes:

```text
Docker Compose

Spring Boot
PostgreSQL
Redis
RabbitMQ
```

Add:

```yaml
rabbitmq:

  image: rabbitmq:4-management

  ports:
    - "5672:5672"
    - "15672:15672"
```

Two ports:

## **5672**

Application communication.

```text
Spring Boot
     |
     v
RabbitMQ
```

---

## **15672**

Management UI.

Browser:

```
localhost:15672
```

You can see:

- queues
- exchanges
- messages
- connections

Very useful for learning.

---

# **12. Spring AMQP**

Spring’s RabbitMQ integration is called:

```
Spring AMQP
```

Add dependency:

```xml
<dependency>
    <groupId>
        org.springframework.boot
    </groupId>

    <artifactId>
        spring-boot-starter-amqp
    </artifactId>
</dependency>
```

Architecture:

```text
Spring Boot

    |
    |
Spring AMQP

    |
    |
RabbitMQ Client

    |
    |
RabbitMQ Server
```

---

# **13. Configuration**

application-docker.yml:

```yaml
spring:

  rabbitmq:

    host: rabbitmq

    port: 5672

    username: guest

    password: guest
```

Again:

```yaml
host: rabbitmq
```

because Docker Compose gives us:

```
service name = hostname
```

---

# **14. Creating an event class**

Example:

```java
public record ProjectCreatedEvent(

    Long projectId,

    Long createdBy

){

}
```

This represents:

A project was created.

---

# **15. Publishing an event**

After saving:

```java
@Service
@RequiredArgsConstructor
public class ProjectService {


private final RabbitTemplate rabbitTemplate;


public Project createProject(CreateProjectRequest request){

    Project project =
        repository.save(...);


    ProjectCreatedEvent event =
        new ProjectCreatedEvent(
            project.getId(),
            project.getOwnerId()
        );


    rabbitTemplate.convertAndSend(
        "project.exchange",
        "project.created",
        event
    );


    return project;

}

}
```

Flow:

```text
Save database

      |

Create event

      |

RabbitTemplate

      |

RabbitMQ
```

---

# **16. Consuming messages**

Another component:

```java
@Component
public class NotificationConsumer {


@RabbitListener(
 queues="project.notification.queue"
)
public void handle(
    ProjectCreatedEvent event
){

    System.out.println(
        "Send notification for "
        + event.projectId()
    );

}

}
```

Now:

```text
RabbitMQ

PROJECT_CREATED

        |

        v

NotificationConsumer

        |

        v

Send notification
```

---

# **17. What if the consumer crashes?**

This is where messaging becomes powerful.

Imagine:

```text
Project created

RabbitMQ
     |
     |
Notification service crashes
```

The message can remain:

```text
Queue:

[PROJECT_CREATED]
```

When the service returns:

```text
Consumer starts

      |

Consumes message
```

No lost work.

---

# **18. But messages can fail**

Example:

```java
sendEmail()
```

throws:

```
SMTP error
```

What happens?

We need strategies:

## **Retry**

Try again.

Example:

```
Attempt 1
Attempt 2
Attempt 3
```

---

## **Dead Letter Queue**

If it keeps failing:

```
Main Queue

      |

      X

Dead Letter Queue
```

The message is stored for investigation.

---

# **19. Messaging does NOT replace transactions**

Important.

This:

```text
Save project

Send message
```

has a tricky problem.

What if:

```
Database save ✅

Message publish ❌
```

Now:

```
Project exists

No event
```

How do we solve that?

This leads to:

# **The Outbox Pattern**

Very important production concept.

---

# **20. Outbox pattern preview**

Instead of:

```
Database
    |
    |
RabbitMQ
```

we do:

```
Database

projects table

outbox_events table


        |

background publisher


        |

RabbitMQ
```

Same transaction:

```text
Insert project

Insert event

COMMIT
```

Then:

```
Publisher reads outbox

publishes message
```

Now database and events stay consistent.

We will study this deeply later.

---

# **21. When should we use RabbitMQ?**

Good cases:

✅ Email sending

```
User registered

→ send email
```

---

✅ Notifications

```
Project created

→ notify team
```

---

✅ Background processing

```
Generate report

→ worker handles it
```

---

✅ Integration between services

```
Order service

→ Payment service
```

---

# **22. When should we NOT use RabbitMQ?**

Don’t use it just because it sounds advanced.

Avoid:

```
Simple CRUD operation
```

Example:

```
GET /projects/10
```

No queue needed.

Also avoid:

```
Need immediate response
```

Example:

```
Check password
```

You need the result now.

---

# **23. Our architecture evolution**

Before:

```
                ProjectHub

Client
  |
  |
Spring Boot
  |
  |
PostgreSQL
  |
Redis
```

After:

```
                  ProjectHub


Client
  |
  v
Spring Boot
  |
  +----------+
             |
             v
        RabbitMQ
             |
     +-------+-------+
     |       |       |
     v       v       v

Notifications Analytics Search
```

This is the beginning of event-driven architecture.

---

# **24. The important mental shift**

Old thinking:

“My service calls another service.”

New thinking:

“My service publishes facts. Other services react.”

This reduces coupling.

The producer doesn’t need to know:

```
Who listens?
How many listeners?
What they do?
```

It only announces:

```
ProjectCreated
```

---

# **Exercise 36**

Answer these:

### **1.**

Why is this bad?

```
Create Project

↓

Send Email

↓

Update Analytics

↓

Return response
```

---

### **2.**

Explain the difference:

```
Command:

CreateProject
```

vs

```
Event:

ProjectCreated
```

---

### **3.**

What are the roles of:

```
Producer
Exchange
Queue
Consumer
```

?

---

### **4.**

Why is RabbitMQ useful if a consumer crashes?

---

### **5.**

Why could this happen?

```
Database save succeeds

RabbitMQ publish fails
```

---

### **6.**

Why does an event usually use past tense?

Example:

```
ProjectCreated
```

instead of:

```
CreateProject
```

---

Next lesson:

# **Lesson 37 — RabbitMQ Deep Dive + Building the ProjectHub Event System**

We will implement:

- exchanges
- queues
- bindings
- routing keys
- `RabbitTemplate`
- `@RabbitListener`
- message serialization
- retries
- dead-letter queues
- the Outbox Pattern

This is where ProjectHub starts looking like a real production backend.