---
title: "Lesson 38: Building a Complete Event-Driven ProjectHub Feature"
sidebar_position: 38
---

Now we are going to build something that looks much closer to a **real production backend**.

Until now:

```text
User
 |
 v
Project Service
 |
 v
PostgreSQL
```

Then we added RabbitMQ:

```text
User
 |
 v
Project Service
 |
 +---- PostgreSQL
 |
 +---- RabbitMQ
```

But we discovered a problem:

```text
Save database
      |
      |
Publish event
```

What if the second step fails?

Today we solve that.

We will build:

```text
                 Project Creation

                       |
                       v

                PostgreSQL Transaction

                       |
          +------------+------------+
          |                         |
          v                         v

    projects table          outbox_events table


                       |
                       v

              Outbox Publisher


                       |
                       v

                  RabbitMQ


          +------------+------------+
          |                         |

          v                         v

 Notification Worker        Audit Worker
```

---

# **1. The reliability problem**

Imagine:

```java
public Project createProject(){

    Project project =
        projectRepository.save(project);


    rabbitTemplate.convertAndSend(
        "project.created",
        event
    );

    return project;
}
```

Looks fine.

But what happens here:

```text
Step 1:

Save project ✅


Step 2:

Publish event ❌
```

Now:

Database:

```
projects

ID: 10
Name: Website
```

RabbitMQ:

```
(no event)
```

Result:

The notification service never knows.

---

# **2. Why not reverse the order?**

Maybe:

```text
Publish event

      |

Save database
```

Problem:

```
RabbitMQ ✅

Database ❌
```

Now consumers receive an event about something that doesn’t exist.

Also bad.

---

# **3. The Outbox Pattern**

The idea:

Make the database the source of truth.

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

projects
outbox_events

      |
      |
Publisher

      |
      |
RabbitMQ
```

---

# **4. The outbox table**

Create:

```sql
CREATE TABLE outbox_events (

    id UUID PRIMARY KEY,

    event_type VARCHAR(100) NOT NULL,

    payload JSONB NOT NULL,

    created_at TIMESTAMP NOT NULL,

    published BOOLEAN DEFAULT FALSE

);
```

Example:

```
id:
550e8400


event_type:

PROJECT_CREATED


payload:

{
 "projectId":10,
 "ownerId":5
}


published:

false
```

---

# **5. The important transaction**

Now creating a project becomes:

```text
BEGIN TRANSACTION


Insert project


Insert outbox event


COMMIT
```

Both succeed.

Or both fail.

Database guarantees this.

---

# **6. Create the entity**

Java:

```java
@Entity
@Table(name="outbox_events")
public class OutboxEvent {


@Id
private UUID id;


private String eventType;


@Column(columnDefinition="jsonb")
private String payload;


private Instant createdAt;


private boolean published;

}
```

---

# **7. Outbox repository**

```java
public interface OutboxEventRepository
        extends JpaRepository<OutboxEvent, UUID> {


List<OutboxEvent> findByPublishedFalse();

}
```

We need unpublished events.

---

# **8. Creating the project with an event**

Service:

```java
@Transactional
public Project createProject(
        CreateProjectRequest request
){

    Project project =
        projectRepository.save(
            new Project(...)
        );


    ProjectCreatedEvent event =
        new ProjectCreatedEvent(
            project.getId(),
            project.getOwnerId()
        );


    OutboxEvent outbox =
        new OutboxEvent();


    outbox.setId(UUID.randomUUID());

    outbox.setEventType(
        "PROJECT_CREATED"
    );

    outbox.setPayload(
        objectMapper.writeValueAsString(event)
    );


    outboxRepository.save(outbox);


    return project;
}
```

Now:

Database:

```
projects

10 | Website
```

and:

```
outbox_events

abc | PROJECT_CREATED | false
```

exist together.

---

# **9. The publisher service**

Now we need something that moves events from:

```
outbox_events
```

to:

```
RabbitMQ
```

Example:

```java
@Service
@RequiredArgsConstructor
public class OutboxPublisher {


private final OutboxEventRepository repository;

private final RabbitTemplate rabbitTemplate;



@Scheduled(fixedDelay = 5000)
public void publishEvents(){


    List<OutboxEvent> events =
        repository.findByPublishedFalse();


    for(OutboxEvent event : events){

        rabbitTemplate.convertAndSend(
            "project.events.exchange",
            "project.created",
            event.getPayload()
        );


        event.setPublished(true);

        repository.save(event);
    }

}

}
```

Flow:

```
Every 5 seconds:

Find unpublished events

        |

Publish to RabbitMQ

        |

Mark published
```

---

# **10. Enable scheduling**

Add:

```java
@EnableScheduling
@SpringBootApplication
public class Application {

}
```

Now Spring runs:

```java
@Scheduled
```

methods.

---

# **11. But we have another problem**

Imagine:

Publisher:

```
Send message
      |
      X
Crash before:
published=true
```

Next run:

```
Find unpublished events
```

It sends again.

Now RabbitMQ has:

```
PROJECT_CREATED
PROJECT_CREATED
```

Duplicate messages.

---

# **12. The truth about distributed systems**

Many beginners think:

“A message is delivered exactly once.”

Reality:

Most systems use:

```
At least once delivery
```

Meaning:

The message will probably arrive.

But:

It may arrive multiple times.

---

# **13. Therefore consumers must be idempotent**

Idempotent means:

Running the same operation multiple times produces the same result.

Example:

Bad:

```java
sendMoney(100);
```

If executed twice:

```
-$100

-$100
```

Problem.

---

Good:

```java
markInvoicePaid(invoiceId);
```

First time:

```
PAID
```

Second time:

```
already PAID
```

No damage.

---

# **14. Making Notification Consumer idempotent**

Bad:

```java
@RabbitListener(
queues="notification.queue"
)
public void consume(
    ProjectCreatedEvent event
){

    emailService.send();

}
```

Duplicate message:

```
Email 1

Email 2
```

---

Better:

Create table:

```sql
processed_events

id UUID PRIMARY KEY

processed_at TIMESTAMP
```

Consumer:

```java
@Transactional
public void handle(Event event){

    if(processedEventRepository
       .existsById(event.id())){

        return;
    }


    emailService.send();


    processedEventRepository.save(
        new ProcessedEvent(event.id())
    );

}
```

Now:

First message:

```
Not found

Send email

Save processed
```

Second message:

```
Already exists

Ignore
```

---

# **15. Exactly once vs at least once**

Two concepts:

## **Exactly once**

Meaning:

```
Processed one time only
```

Sounds perfect.

Very hard in distributed systems.

---

## **At least once**

Meaning:

```
Message arrives one or more times
```

Most production systems use this.

Then they design:

```
duplicate-safe consumers
```

---

# **16. Event flow in our final system**

Let’s trace:

User:

```
POST /projects
```

---

Project Service:

```
BEGIN

Insert project

Insert outbox event

COMMIT
```

Database:

```
projects
---------
10 Website


outbox_events
-------------
abc PROJECT_CREATED
```

---

Publisher:

```
Reads abc
```

Publishes:

```json
{
 "event":"PROJECT_CREATED",
 "projectId":10
}
```

RabbitMQ:

```
project.events.exchange
```

---

Notification:

```
Receive event

Check processed_events

Send notification

Save processed
```

---

# **17. Adding an audit service**

Now imagine:

Requirement:

Every important action must be recorded.

Create:

```
audit.queue
```

Binding:

```
project.*
```

Consumer:

```java
@RabbitListener(
queues="audit.queue"
)
public void audit(
    ProjectCreatedEvent event
){

    auditRepository.save(
        new AuditLog(
            "PROJECT_CREATED",
            event.projectId()
        )
    );

}
```

No change to ProjectService.

This is the beauty of events.

---

# **18. Adding search indexing**

Another consumer:

```
search.queue
```

When:

```
PROJECT_CREATED
```

arrives:

```java
searchEngine.index(project);
```

Again:

ProjectService doesn’t know.

---

# **19. Event-driven architecture**

We now have:

```
                Events

                  |
                  |
                  v

              RabbitMQ


        /          |          \


       v           v           v


Notification    Audit       Search
```

Adding new behavior:

Before:

Change ProjectService.

Now:

Add a consumer.

---

# **20. The downside of events**

Events are powerful, but they introduce complexity.

You now have:

- eventual consistency
- retries
- duplicates
- monitoring
- failures
- ordering problems

Example:

Immediately after:

```
POST /projects
```

The project exists.

But:

```
Search index
```

might update 2 seconds later.

That is called:

## **Eventual consistency**

---

# **21. Strong consistency vs eventual consistency**

Strong:

```
Write

↓

Everything updated immediately
```

Example:

Bank balance.

---

Eventual:

```
Write

↓

Other systems update later
```

Example:

Analytics dashboard.

---

# **22. When ProjectHub should use events**

Good:

```
Project created
    |
    +--> Email
    +--> Audit
    +--> Analytics
    +--> Search
```

Bad:

```
Check user's password

    |
    v

RabbitMQ
```

Why?

Authentication needs immediate answers.

---

# **23. Production architecture**

Our current ProjectHub:

```
                         Client

                           |
                           v

                    Spring Boot API

                           |
              +------------+------------+

              v                         v

          PostgreSQL              Outbox


                                        |
                                        v

                                  Publisher


                                        |
                                        v

                                   RabbitMQ


                    +---------------+---------------+

                    v               v               v


             Notification       Analytics        Search
```

This is a real-world pattern.

---

# **Lesson 38 Summary**

You learned:

✅ Why direct service calls become problematic  
✅ Why RabbitMQ exists  
✅ Why the Outbox Pattern exists  
✅ How database transactions protect events  
✅ Why duplicate messages happen  
✅ Why consumers must be idempotent  
✅ Exactly-once vs at-least-once delivery  
✅ Eventual consistency  
✅ How multiple services react independently

---

# **Exercise 38**

Answer these:

### **1.**

Why does the Outbox Pattern store events in PostgreSQL first?

---

### **2.**

A message is delivered twice:

```
PROJECT_CREATED
PROJECT_CREATED
```

What design prevents double email?

---

### **3.**

Explain:

```
At least once delivery
```

---

### **4.**

Why can search indexing be eventually consistent?

---

### **5.**

Why should authentication usually not use RabbitMQ?

---

### **6.**

Draw the complete flow:

```
POST /projects

↓

?

↓

RabbitMQ

↓

Notification
Audit
Search
```

---

Next lesson:

# **Lesson 39 — Microservices Architecture: Splitting ProjectHub Properly**

We will discuss:

- Monolith vs Microservices
- when to split services
- service boundaries
- API Gateway
- service discovery
- communication patterns
- avoiding the “distributed monolith”

This is where we start designing systems like Netflix, Amazon, and large SaaS platforms.