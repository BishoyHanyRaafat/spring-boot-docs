---
title: "Lesson 39: Microservices Architecture Splitting ProjectHub Properly"
sidebar_position: 39
---

Welcome to one of the most misunderstood topics in backend engineering.

Many developers think:

“A big application = microservices.”

That is not true.

Microservices are not about having many services.

They are about **independent business capabilities**.

Today we will learn:

- Monolith vs Microservices
- When to split
- How to define service boundaries
- API Gateway
- Service communication
- The distributed monolith problem
- How ProjectHub could evolve

---

# **1. Where we are currently**

Our ProjectHub is currently a **modular monolith**.

Architecture:

```
                 ProjectHub

                    Spring Boot

        +-------------+-------------+
        |             |             |
        v             v             v

     Users        Projects      Notifications


                    |
                    v

               PostgreSQL


                    |
                    v

                RabbitMQ
```

Everything is:

- one deployment
- one application
- one codebase

But internally we have modules.

Example:

```
com.projecthub

├── users
│
├── projects
│
├── notifications
│
├── billing
│
└── audit
```

This is actually a very good starting point.

---

# **2. What is a monolith?**

A monolith means:

```
One application

+
One deployment unit
```

Example:

```
projecthub.jar
```

contains:

```
User logic
Project logic
Notification logic
Billing logic
```

You deploy:

```
java -jar projecthub.jar
```

Everything starts together.

---

# **3. Advantages of a monolith**

## **Simple deployment**

One artifact:

```
projecthub.jar
```

Deploy it.

Done.

---

## **Simple debugging**

A request:

```
GET /projects/10
```

stays inside:

```
Controller
 |
Service
 |
Repository
 |
Database
```

Easy tracing.

---

## **Simple transactions**

Example:

```java
@Transactional
createProject()
```

You can easily update:

```
projects table

+
project_members table
```

inside one transaction.

---

# **4. Problems when monoliths grow**

Imagine:

```
ProjectHub

500,000 lines

100 developers

50 modules
```

Now problems appear.

---

## **Problem 1: Deployment coupling**

Small change:

```
Fix notification bug
```

requires:

```
Build whole application

Deploy whole application
```

---

## **Problem 2: Scaling problems**

Imagine:

Projects:

```
100 requests/sec
```

Notifications:

```
10,000 requests/sec
```

With a monolith:

```
Scale everything
```

You cannot scale only notifications.

---

## **Problem 3: Team conflicts**

Developer A:

```
Changes user module
```

Developer B:

```
Changes billing module
```

Same codebase.

Merge conflicts.

---

# **5. What are microservices?**

Microservices mean:

```
Multiple independent applications
```

Example:

```
              ProjectHub Platform


+-----------+   +-----------+   +-------------+

 User       |   | Project   |   | Notification|

 Service    |   | Service   |   | Service     |


+-----------+   +-----------+   +-------------+
```

Each service:

- has its own code
- deploys independently
- owns its data

---

# **6. The biggest rule**

A microservice owns:

```
Business capability
```

Not:

```
Database table
```

Bad splitting:

```
UserTable Service

ProjectTable Service

CommentTable Service
```

Why?

Because databases are implementation details.

---

Good splitting:

```
Identity Service

Project Management Service

Notification Service

Billing Service
```

These represent business areas.

---

# **7. How to find service boundaries**

Ask:

## **Question 1:**

“Does this area have its own business rules?”

Example:

Users:

```
registration
login
password reset
permissions
```

Yes.

Possible service:

```
Identity Service
```

---

Projects:

```
create project
assign members
manage tasks
```

Yes.

Possible:

```
Project Service
```

---

Notifications:

```
email
push
SMS
templates
```

Yes.

Possible:

```
Notification Service
```

---

# **8. ProjectHub microservice design**

A possible future:

```
                         API Gateway

                              |
        +---------------------+---------------------+

        |                     |                     |

        v                     v                     v


 Identity Service      Project Service      Notification Service


        |                     |                     |

        v                     v                     v


 Identity DB          Project DB          Notification DB
```

Notice:

Each service owns its database.

---

# **9. Why separate databases?**

Imagine:

Project Service:

```
projects
tasks
members
```

Identity Service:

```
users
roles
permissions
```

Notification:

```
templates
messages
```

If Project Service directly edits:

```
users table
```

you have coupling.

---

Instead:

Project Service asks:

```
Who is user 10?
```

Identity Service answers.

---

# **10. Communication between services**

There are two major styles.

---

# **Style 1: Synchronous communication**

Service calls another service immediately.

Example:

```
Project Service

      |
      |
 HTTP

      |
      v

Identity Service
```

Example:

```http
GET /users/10
```

Response:

```json
{
"id":10,
"name":"Ahmed"
}
```

Technology:

- REST
- gRPC

---

# **Style 2: Asynchronous communication**

Using events:

```
Project Service

      |
      v

RabbitMQ

      |
      v

Notification Service
```

Example:

```
PROJECT_CREATED
```

---

# **11. When to use REST vs Events**

Use REST when:

You need an answer now.

Example:

```
Can this user access this project?
```

You need:

```
YES/NO
```

---

Use events when:

Something happened.

Example:

```
ProjectCreated
```

Other systems react.

---

# **12. API Gateway**

When you have many services:

Without gateway:

```
Client

 |
 +---- User Service
 |
 +---- Project Service
 |
 +---- Notification Service
```

The client knows everything.

Bad.

---

With gateway:

```
Client

 |
 v

API Gateway

 |
 +---- User Service
 |
 +---- Project Service
 |
 +---- Notification Service
```

The gateway is the front door.

---

# **13. What does an API Gateway do?**

Common responsibilities:

## **Authentication**

Example:

```
JWT validation
```

before reaching services.

---

## **Routing**

Example:

Request:

```
GET /api/projects
```

Gateway sends to:

```
Project Service
```

---

## **Rate limiting**

Example:

Prevent:

```
10,000 requests/sec
```

from one client.

---

## **Logging**

Central place for:

```
request ID
timing
errors
```

---

# **14. Example gateway routes**

```
/api/auth/**

        |
        v

Identity Service


/api/projects/**

        |
        v

Project Service


/api/notifications/**

        |
        v

Notification Service
```

---

# **15. Service discovery**

Problem:

Where is Project Service?

Today:

```
localhost:8081
```

Tomorrow:

```
server-192-168-1-55
```

Instances change.

---

Service discovery solves this.

Example:

```
Project Service

registers:

"I am project-service"
```

Registry:

```
project-service

instances:

10.0.0.5
10.0.0.6
```

Gateway asks:

```
Where is project-service?
```

Registry answers.

---

# **16. Load balancing**

Imagine:

Project Service:

```
Instance 1
Instance 2
Instance 3
```

Requests:

```
Request 1 ---> Instance 1

Request 2 ---> Instance 2

Request 3 ---> Instance 3
```

This distributes load.

---

# **17. The dangerous mistake: distributed monolith**

This is the worst situation.

You split into services:

```
User Service

Project Service

Task Service
```

But every request requires:

```
Project Service
 |
 v
User Service
 |
 v
Task Service
 |
 v
Permission Service
```

Now you have:

- network failures
- slow requests
- complicated debugging

But still tight coupling.

You created a distributed monolith.

---

# **18. Example of bad microservices**

Creating a project:

```
Project Service

calls

User Service

calls

Permission Service

calls

Notification Service

calls

Audit Service
```

Everything depends on everything.

---

Better:

```
Project Service

creates project

publishes:

PROJECT_CREATED


RabbitMQ:

Notification
Audit
Analytics
```

Loose coupling.

---

# **19. Database ownership**

Very important rule:

A service owns its data.

Example:

Identity Service:

```
users_db
```

Project Service:

```
projects_db
```

Notification:

```
notifications_db
```

Avoid:

```
Everyone uses one database
```

because then:

```
microservices
+
shared database
```

usually becomes a distributed monolith.

---

# **20. But should you always separate databases?**

Not necessarily.

A common evolution:

Stage 1:

```
Modular Monolith

One database
```

Stage 2:

```
Separate modules

Clear ownership
```

Stage 3:

```
Extract services

Separate databases
```

Do not start with 20 microservices.

---

# **21. ProjectHub evolution path**

A realistic journey:

## **Version 1**

```
Spring Boot Monolith

PostgreSQL
Redis
```

---

## **Version 2**

```
Modular Monolith

+
RabbitMQ
```

---

## **Version 3**

Extract:

```
Notification Service
```

because it is independent.

---

## **Version 4**

Extract:

```
Identity Service
```

because security is separate.

---

## **Version 5**

More services if needed.

---

# **22. Spring Boot technologies for microservices**

Later we will learn:

## **Spring Cloud Gateway**

API gateway.

---

## **OpenFeign**

Service-to-service REST calls.

Example:

```java
userClient.getUser(id);
```

---

## **Eureka / Consul**

Service discovery.

---

## **Resilience4j**

Fault tolerance:

- retries
- circuit breakers
- rate limits

---

## **Kafka/RabbitMQ**

Messaging.

---

# **23. The architecture we are aiming for**

Eventually:

```
                        Client

                          |
                          v

                    API Gateway

                          |

      +-------------------+-------------------+

      |                   |                   |

      v                   v                   v


 Identity            Project              Notification

 Service             Service              Service


      |                   |                   |

      v                   v                   v


Identity DB        Project DB        Notification DB


                          |

                          v

                       RabbitMQ
```

---

# **Lesson 39 Summary**

You learned:

✅ Monolith vs Microservices  
✅ Why splitting too early is dangerous  
✅ How to define service boundaries  
✅ API Gateway purpose  
✅ REST vs events  
✅ Service discovery  
✅ Load balancing  
✅ Database ownership  
✅ Distributed monolith problem  
✅ A realistic migration path

---

# **Exercise 39**

Answer these:

### **1.**

Why is this bad?

```
UserTable Service
ProjectTable Service
TaskTable Service
```

---

### **2.**

What is the difference between:

```
Modular Monolith
```

and:

```
Microservices
```

---

### **3.**

When would Project Service call Identity Service using REST?

---

### **4.**

When would Project Service publish an event instead?

---

### **5.**

Why is a shared database dangerous between microservices?

---

### **6.**

Design your own ProjectHub services.

Write:

```
Service name:
Responsibility:
Database:
Events:
```

for at least 3 services.

---

Next lesson:

# **Lesson 40 — API Gateway + Spring Cloud Gateway**

We will build the front door of ProjectHub:

```
Client

   |
   v

API Gateway

   |
   +---- Identity Service
   |
   +---- Project Service
   |
   +---- Notification Service
```

We will learn:

- Spring Cloud Gateway
- routing
- filters
- JWT authentication at gateway level
- rate limiting
- request tracing

This is where the architecture starts looking like a real SaaS platform.