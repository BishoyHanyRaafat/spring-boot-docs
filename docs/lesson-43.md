---
title: Lesson 43: Observability Logs, Metrics, Tracing, and Debugging Microservices
sidebar_position: 43
---

Welcome to one of the most important lessons in real backend engineering.

A beginner thinks:

“If my code works, my job is done.”

A production engineer thinks:

“How do I know my system is working when thousands of users are using it?”

In a monolith:

```text
User

 |
 v

Application

 |
 v

Database
```

Debugging is simple.

You open logs:

```text
ERROR at ProjectService.java:50
```

Done.

---

But in microservices:

```text
User

 |
 v

Gateway

 |
 v

Project Service

 |
 v

Identity Service

 |
 v

Database

 |
 v

RabbitMQ

 |
 v

Notification Service
```

A request can travel through many systems.

Now the question becomes:

Where did it fail?

---

# **1. What is observability?**

Observability means:

Understanding the internal state of a system by looking at its external outputs.

The three pillars:

```text
1. Logs

2. Metrics

3. Traces
```

These are called:

## **The Three Pillars of Observability**

---

# **2. Logs**

Logs tell you:

What happened?

Example:

```text
2026-01-01 10:20:30

INFO

Project created successfully

projectId=10
userId=5
```

---

Another example:

```text
ERROR

Database connection failed

service=project-service
```

Logs are events.

---

# **3. Why normal logs are not enough**

Imagine:

User reports:

“Creating a project failed.”

You search:

```text
project-service.log
```

You find:

```text
Request received
```

Nothing else.

Why?

Maybe failure happened in:

```text
Identity Service
```

or:

```text
Database
```

or:

```text
RabbitMQ
```

---

We need correlation.

---

# **4. Correlation IDs**

A correlation ID is a unique identifier attached to a request.

Example:

```text
requestId:

abc-123
```

Flow:

```text
User Request

ID:
abc-123


        |
        v


Gateway

abc-123


        |
        v


Project Service

abc-123


        |
        v


Notification Service

abc-123
```

Now every log belongs to the same request.

---

# **5. Example logs without correlation ID**

Bad:

```text
Project created
```

Which user?

Which request?

Which service?

Unknown.

---

Better:

```json
{
 "service":"project-service",
 "requestId":"abc-123",
 "userId":5,
 "action":"PROJECT_CREATED"
}
```

Now searchable.

---

# **6. Structured logging**

Avoid:

```java
System.out.println(
"User created project"
);
```

Better:

```java
log.info(
"Project created id={} user={}",
projectId,
userId
);
```

Output:

```text
Project created id=10 user=5
```

---

Even better:

JSON logs:

```json
{
"time":"10:30",
"level":"INFO",
"service":"project-service",
"event":"PROJECT_CREATED",
"projectId":10
}
```

Tools can analyze these.

---

# **7. Centralized logging**

In microservices:

You don’t want:

```text
server-1
   |
   logs


server-2
   |
   logs


server-3
   |
   logs
```

You want:

```text
                Services

                    |
                    v

            Log Collector

                    |
                    v

            Log Storage

                    |
                    v

            Search Dashboard
```

Common stack:

```text
ELK

Elasticsearch
Logstash
Kibana
```

---

# **8. Metrics**

Logs answer:

What happened?

Metrics answer:

How much is happening?

Examples:

```text
Requests per second

CPU usage

Memory usage

Error rate

Response time
```

---

Example:

Project Service:

```text
Requests:

5000/minute


Average latency:

120ms


Errors:

0.5%
```

---

# **9. Important backend metrics**

## **Request count**

Example:

```text
HTTP requests:

10000/min
```

---

## **Error rate**

Example:

```text
500 errors:

2%
```

---

## **Latency**

Example:

```text
95% requests < 200ms
```

---

## **Database metrics**

Example:

```text
Active connections:

50
```

---

# **10. Prometheus**

A popular metrics system.

Architecture:

```text
Application

   |
   |
 exposes metrics

   |
   v

Prometheus

   |
   v

Grafana
```

---

Spring Boot provides:

```text
Spring Actuator
```

---

# **11. Spring Boot Actuator**

Dependency:

```xml
<dependency>

<groupId>
org.springframework.boot
</groupId>

<artifactId>
spring-boot-starter-actuator
</artifactId>

</dependency>
```

---

Now endpoints exist:

Example:

```http
GET /actuator/health
```

Response:

```json
{
"status":"UP"
}
```

---

Metrics:

```http
GET /actuator/metrics
```

Example:

```text
http.server.requests

jvm.memory.used

system.cpu.usage
```

---

# **12. Health checks**

Very important.

Gateway asks:

```text
Is Project Service alive?
```

Project Service:

```json
{
"status":"UP"
}
```

---

But healthy means more than alive.

Example:

Application:

```text
Running
```

Database:

```text
Disconnected
```

Not healthy.

---

Health:

```json
{
"status":"DOWN",

"database":"FAILED"
}
```

---

# **13. Kubernetes and health checks**

Later, Kubernetes uses:

## **Liveness probe**

Question:

Is the application alive?

If no:

Restart it.

---

## **Readiness probe**

Question:

Can it receive traffic?

If no:

Remove it from load balancing.

---

Example:

```text
Application starts

       |

Database unavailable

       |

Readiness = false

       |

No traffic sent
```

---

# **14. Distributed tracing**

Now the third pillar.

Tracing answers:

What path did this request take?

Example:

User request:

```text
GET /projects/10
```

Trace:

```text
Gateway
 |
 | 20ms
 |
Project Service
 |
 | 50ms
 |
Identity Service
 |
 | 100ms
 |
Database
```

---

# **15. Trace vs Log**

Log:

```text
Database query failed
```

Trace:

```text
This request spent:

Gateway:
10ms

Project:
50ms

Database:
900ms
```

Tracing finds bottlenecks.

---

# **16. OpenTelemetry**

Modern standard:

```text
OpenTelemetry
```

It provides:

- tracing
- metrics
- context propagation

Architecture:

```text
Application

 |
 v

OpenTelemetry Agent

 |
 v

Tracing Backend
```

---

# **17. Trace IDs**

Similar to correlation IDs.

Example:

```text
traceId:

xyz-999
```

Every service receives:

```text
traceId=xyz-999
```

---

Flow:

```text
Request

traceId=abc


Gateway

traceId=abc


Project Service

traceId=abc


Database

traceId=abc
```

---

# **18. Example ProjectHub trace**

User creates project:

```text
Trace ID: 555


Gateway

  |
  | 5ms
  v


Project Service

  |
  | 30ms
  v


PostgreSQL

  |
  | 10ms
  v


RabbitMQ Publish

  |
  | 2ms
  v


Notification Service

  |
  | 200ms
  v


Email Provider
```

Now we know:

Email provider was slow.

---

# **19. Logging + Metrics + Tracing together**

Imagine:

Alert:

```
Error rate increased
```

Metrics tells:

```text
Project Service
500 errors increased
```

Tracing tells:

```text
Database calls are slow
```

Logs tell:

```text
Connection timeout
```

Together:

You solve the problem.

---

# **20. Monitoring architecture**

Production setup:

```text
                 Applications


                      |
                      |

       +--------------+--------------+

       |              |              |

       v              v              v


     Logs          Metrics        Traces


       |              |              |

       v              v              v


 Elasticsearch   Prometheus    Jaeger/Tempo


                      |

                      v


                  Grafana
```

---

# **21. Grafana**

Grafana displays dashboards.

Example:

ProjectHub dashboard:

```
Requests/sec       5000

Error rate         0.2%

Average latency    120ms

Database CPU       60%

RabbitMQ messages  200
```

---

# **22. Alerts**

Monitoring without alerts is incomplete.

Example:

Rule:

```text
If error rate > 5%

for 5 minutes

send alert
```

---

Alert:

```text
🚨 Project Service errors increased
```

---

# **23. Common production alerts**

## **Application down**

```text
Service unavailable
```

---

## **High latency**

```text
95th percentile > 2 seconds
```

---

## **Database problems**

```text
Connection pool exhausted
```

---

## **Queue problems**

```text
RabbitMQ backlog growing
```

---

# **24. Debugging example**

User:

“Project creation is slow.”

Without observability:

Guessing.

---

With observability:

Metrics:

```text
Project API latency increased
```

Tracing:

```text
Database query takes 3 seconds
```

Logs:

```text
Slow query detected
```

Solution:

Optimize query.

---

# **25. Spring Boot production stack**

A common stack:

## **Application**

```text
Spring Boot
```

---

## **Logs**

```text
Logback
+
ELK
```

---

## **Metrics**

```text
Actuator
+
Prometheus
+
Grafana
```

---

## **Tracing**

```text
OpenTelemetry
+
Jaeger
```

---

# **26. ProjectHub final operational architecture**

```text
                       Users

                         |

                         v

                    API Gateway

                         |

        +----------------+----------------+

        |                |                |

        v                v                v


 Identity          Project          Notification


        \              |              /

         \             |             /

                  Observability


                       |

          +------------+------------+

          |            |            |

          v            v            v


        Logs       Metrics       Traces


          |            |            |

          v            v            v


          ELK      Prometheus    Jaeger


                       |

                       v

                    Grafana
```

---

# **27. Important production mindset**

A service is not complete when:

```text
Code works
```

It is complete when:

```text
Code works

+

You know when it fails

+

You know why it fails

+

You can debug it quickly
```

---

# **Lesson 43 Summary**

You learned:

✅ Observability concept  
✅ Logs  
✅ Structured logging  
✅ Correlation IDs  
✅ Centralized logging  
✅ Metrics  
✅ Spring Actuator  
✅ Prometheus  
✅ Grafana  
✅ Distributed tracing  
✅ OpenTelemetry  
✅ Health checks  
✅ Production debugging workflow

---

# **Exercise 43**

Answer:

### **1.**

A user reports:

“Creating projects is slow.”

Which pillar helps you find the exact slow service?

```
Logs
Metrics
Tracing
```

Explain.

---

### **2.**

Why do microservices need correlation IDs?

---

### **3.**

What is the difference between:

```
Liveness check
```

and:

```
Readiness check
```

---

### **4.**

Why is:

```text
System.out.println()
```

not enough for production?

---

### **5.**

Design a monitoring stack for ProjectHub:

```
Logs:
?

Metrics:
?

Tracing:
?

Dashboard:
?
```

---

Next lesson:

# **Lesson 44 — Caching in Spring Boot: Redis, Cache Strategies, and Performance**

We will learn:

- why databases become slow
- Redis architecture
- Spring Cache
- cache-aside pattern
- cache invalidation
- distributed caching
- when NOT to cache

This is where we start making ProjectHub fast under heavy traffic.