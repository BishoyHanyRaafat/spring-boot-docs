---
title: "Lesson 46: Messaging Systems RabbitMQ, Kafka, Events, and Event-Driven Architecture"
sidebar_position: 46
---

Welcome to one of the most important concepts in distributed backend systems.

Until now, our services communicated like this:

```text
 id="directcall"

Project Service

       |
       |
       v

Identity Service
```

This is **synchronous communication**.

The problem:

If Identity Service is slow or down:

```text
Project Service
        |
        X
Identity Service
```

Project Service suffers.

Now we introduce:

# **Asynchronous communication**

A service sends a message and continues working.

```text
 id="async"

Project Service

       |
       v

 Message Broker

       |
       v

Notification Service
```

---

# **1. What is a message broker?**

A message broker is a system that receives messages from one service and delivers them to other services.

Think of it like a post office.

Sender:

```text
Project Service
```

sends:

```text
PROJECT_CREATED
```

Post office:

```text
RabbitMQ / Kafka
```

delivers it to:

```text
Notification Service
Analytics Service
Search Service
```

---

# **2. Why do we need messaging?**

Imagine creating a project.

Without messaging:

```text
 id="withoutmq"

User

 |
 v

Project Service

 |
 |
 +--> Save project
 |
 +--> Send email
 |
 +--> Update analytics
 |
 +--> Update search index
 |
 +--> Generate activity log

Return response
```

The user waits for everything.

---

With messaging:

```text
 id="withmq"

User

 |
 v

Project Service

 |
 |
 +--> Save project
 |
 |
 +--> Publish event
 |
 v

Return response


Later:


RabbitMQ

 |
 +--> Email
 |
 +--> Analytics
 |
 +--> Search
```

Much faster.

---

# **3. Event-driven architecture**

The idea:

Services communicate through events.

Example:

Project Service says:

A project was created.

It publishes:

```json
 id="event1"
{
 "event":"PROJECT_CREATED",
 "projectId":100,
 "ownerId":5,
 "createdAt":"2026-01-01"
}
```

It does NOT say:

“Send email.”

It only announces a fact.

---

# **4. Commands vs Events**

Very important distinction.

## **Command**

A request to do something.

Example:

```text
CreateProject
```

Meaning:

Please create a project.

---

## **Event**

Something already happened.

Example:

```text
ProjectCreated
```

Meaning:

A project has been created.

---

Comparison:

```text
Command:

"Do this"


Event:

"This happened"
```

---

# **5. RabbitMQ**

RabbitMQ is a message broker based on queues.

Architecture:

```text
 id="rabbit"

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

---

# **6. RabbitMQ components**

## **Producer**

Creates messages.

Example:

```text
Project Service
```

---

## **Exchange**

Receives messages and decides where they go.

---

## **Queue**

Stores messages.

Example:

```text
notification.queue
```

---

## **Consumer**

Processes messages.

Example:

```text
Notification Service
```

---

# **7. RabbitMQ example**

Project creation:

```text
 id="rabbitflow"

Project Service


publish:


PROJECT_CREATED


        |
        v


     Exchange


        |
        v


notification.queue


        |
        v


Notification Service
```

---

# **8. RabbitMQ routing**

RabbitMQ has routing rules.

Example:

Exchange:

```text
project.events
```

Events:

```text
PROJECT_CREATED
PROJECT_DELETED
```

Queues:

```text
notification.queue

analytics.queue
```

Routing:

```text
PROJECT_CREATED

       |
       +---- notification

       |
       +---- analytics
```

---

# **9. RabbitMQ message acknowledgment**

Important.

Imagine:

Notification Service receives:

```json
{
"event":"PROJECT_CREATED"
}
```

It sends email.

Success:

```text
 id="ack"

Process message

       |

ACK

       |

RabbitMQ removes message
```

---

Failure:

```text
 id="nack"

Process message

       X

Error

       |

NACK

       |

Message remains
```

---

# **10. Why acknowledgments matter**

Without acknowledgment:

RabbitMQ thinks:

```text
"Message delivered successfully"
```

and deletes it.

But the service crashed.

Message lost.

---

# **11. Consumer retries**

Example:

Email sending fails.

Retry:

```text
Attempt 1

X


Attempt 2

X


Attempt 3

OK
```

---

But be careful.

What if:

```text
Payment processed
```

then retry happens?

You might charge twice.

---

# **12. Idempotency**

Very important concept.

An operation is idempotent if:

Running it multiple times gives the same result.

Example:

Bad:

```text
Charge $100
```

Twice:

```text
-$100
-$100
```

Bad.

---

Good:

```text
Set user status = ACTIVE
```

Run:

```text
1 time
```

or:

```text
100 times
```

Result:

```text
ACTIVE
```

---

# **13. Dead Letter Queue (DLQ)**

What happens when a message always fails?

Example:

```text
Email Service

tries

10 times

still fails
```

Do not keep retrying forever.

Move it:

```text
 id="dlq"

Main Queue

      |
      X

      v

Dead Letter Queue
```

Later:

Developer investigates.

---

# **14. Kafka**

Apache Kafka is another messaging system.

But Kafka is designed differently.

RabbitMQ:

```text
Message delivery
```

Kafka:

```text
Event streaming
```

---

# **15. Kafka architecture**

Basic:

```text
 id="kafka"

Producer

    |
    v

 Kafka Topic

    |
    +------ Consumer A

    |
    +------ Consumer B
```

---

# **16. Kafka topics**

A topic is a stream of events.

Example:

```text
project-events
```

Contains:

```text
PROJECT_CREATED

PROJECT_UPDATED

PROJECT_DELETED
```

---

# **17. Kafka partitions**

Kafka topics are divided into partitions.

Example:

```text
 id="partition"

project-events


Partition 1

event1
event2


Partition 2

event3
event4
```

---

Why?

Performance.

Multiple consumers can process in parallel.

---

# **18. Kafka ordering**

Kafka guarantees ordering:

Inside one partition.

Example:

Partition 1:

```text
1. ProjectCreated

2. ProjectUpdated

3. ProjectDeleted
```

Order preserved.

---

Across partitions:

No global order.

---

# **19. Kafka consumer groups**

Example:

Three notification servers:

```text
 id="consumer"

Notification Service


Consumer Group:

notifications


Instance 1

Instance 2

Instance 3
```

Kafka distributes messages.

---

# **20. RabbitMQ vs Kafka**

Simple comparison:

||**RabbitMQ**|**Kafka**|
|---|---|---|
|Main idea|Message queue|Event streaming|
|Messages|Usually removed after processing|Stored for retention|
|Replay|Limited|Excellent|
|Ordering|Queue based|Partition based|
|High throughput|Good|Excellent|
|Common use|Tasks, commands|Events, analytics|

---

# **21. Which would ProjectHub use?**

Example:

## **Notifications**

Need:

```text
Send email once
```

RabbitMQ fits.

---

## **Analytics**

Need:

```text
Millions of events
Historical processing
```

Kafka fits.

---

Architecture:

```text
 id="projecthubmq"

                 Project Service


                       |

                 PROJECT_CREATED


                       |

             +---------+---------+

             |                   |

             v                   v


        RabbitMQ              Kafka


             |                   |

             v                   v


     Notification          Analytics
```

---

# **22. Event schema design**

Bad:

```json
{
"user":"Ahmed created something"
}
```

Hard to process.

---

Better:

```json
{
 "eventId":"abc-123",
 "eventType":"PROJECT_CREATED",
 "version":1,
 "timestamp":"2026-01-01T10:00:00",
 "data":{
    "projectId":10,
    "ownerId":5
 }
}
```

---

# **23. Why event versions matter**

Today:

```json
{
"projectId":10
}
```

Tomorrow:

```json
{
"projectId":10,
"teamId":20
}
```

Old consumers may break.

Use:

```json
{
"version":2
}
```

---

# **24. The Outbox Pattern**

A very important production pattern.

Problem:

You do:

```text
 id="dualwrite"

Save project

+

Publish event
```

Two operations.

What if:

Database succeeds:

```text
Project saved
```

but:

RabbitMQ fails:

```text
Event not published
```

Now inconsistent.

---

Solution:

Outbox pattern.

Architecture:

```text
 id="outbox"

Project Service


      |

      v


Database


projects table

+

outbox table


      |

      v


Message Publisher


      |

      v


RabbitMQ
```

---

Flow:

Transaction:

```sql
BEGIN;

INSERT project;

INSERT outbox_event;

COMMIT;
```

Now both are saved.

A background worker publishes:

```text
outbox_event

      |

      v

RabbitMQ
```

---

# **25. Event-driven ProjectHub design**

Final:

```text
 id="finalevent"

                     API Gateway


                          |


                   Project Service


                          |

                    PostgreSQL

                          |

                    Outbox Table

                          |

                          v


                    Message Broker


              +-----------+-----------+

              |                       |

              v                       v


       Notification              Analytics


       Service                   Service
```

---

# **26. Common messaging mistakes**

## **Mistake 1**

Using events for everything.

Bad:

```text
Need user name?

Publish event
```

No.

Use REST.

---

## **Mistake 2**

No retry strategy.

Messages fail.

You need:

- retry
- DLQ
- monitoring

---

## **Mistake 3**

Ignoring duplicate messages.

Consumers must handle:

```text
same event twice
```

---

## **Mistake 4**

Huge events.

Bad:

```json
{
"allProjects": [
100000 items
]
}
```

Events should be small.

---

# **27. ProjectHub communication decision**

Example:

Question:

```text
Is user allowed to edit project?
```

Use:

```text
REST
```

---

Question:

```text
Project was created.
Who cares?
```

Use:

```text
Event
```

---

Question:

```text
Need analytics history?
```

Use:

```text
Kafka
```

---

# **Lesson 46 Summary**

You learned:

✅ Message brokers  
✅ Event-driven architecture  
✅ RabbitMQ concepts  
✅ Producers and consumers  
✅ Queues and exchanges  
✅ Acknowledgments  
✅ Retries  
✅ Dead Letter Queues  
✅ Idempotency  
✅ Kafka basics  
✅ Topics and partitions  
✅ Consumer groups  
✅ RabbitMQ vs Kafka  
✅ Event schemas  
✅ Outbox pattern

---

# **Exercise 46**

Answer:

### **1.**

Project Service creates a project.

Should it:

A)

Call Notification Service directly

or

B)

Publish `PROJECT_CREATED`

Explain.

---

### **2.**

What is the difference between:

```
Command
```

and:

```
Event
```

---

### **3.**

Why do consumers need idempotency?

---

### **4.**

What problem does the Outbox Pattern solve?

---

### **5.**

For ProjectHub, choose:

```
Notifications:
?

Analytics:
?

Permission checks:
?
```

Use:

- REST
- RabbitMQ
- Kafka

Explain.

---

Next lesson:

# **Lesson 47 — Containers and Docker for Spring Boot Applications**

We will learn how production systems package and run applications:

- Docker images
- containers
- Dockerfile
- Docker Compose
- Spring Boot containers
- databases in containers
- preparing for Kubernetes

This is where we move from **writing backend code** to **running backend systems**.