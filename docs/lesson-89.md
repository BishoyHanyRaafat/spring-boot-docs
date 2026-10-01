---
title: "Lesson 89: Production Logging & Observability"
sidebar_position: 89
---

This is one of the last important production topics.

When something breaks in production, you need to answer:

**What happened, where did it happen, and how bad is it?**

Spring Boot defines observability around three pillars:

```text
Logging
Metrics
Tracing
```

and uses Micrometer Observation for metrics/tracing integration.  

---

## **1. Logging**

Don’t do this:

```java
System.out.println("post created");
```

Use structured application logging.

Conceptually:

```java
log.info("Post created: postId={}", postId);
```

Different levels communicate different severity:

```text
DEBUG → detailed development information
INFO  → normal important events
WARN  → something unexpected
ERROR → failure requiring attention
```

Spring Boot’s logging infrastructure supports configurable logger levels, and Actuator can inspect/configure logger levels at runtime when exposed.  

---

## **2. What should we log?**

For ProjectHub:

```text
INFO
POST /posts
post created
user authenticated
outbox event published

WARN
retrying Kafka event
slow database operation
rate limit approaching

ERROR
unexpected exception
Kafka publishing failure
database failure
```

But **never casually log secrets**:

```text
❌ password
❌ JWT
❌ refresh token
❌ database credentials
❌ private keys
```

And be careful with personal/sensitive data.

---

# **3. Correlation IDs**

Imagine a request:

```text
POST /posts
```

causes:

```text
API
 ↓
PostgreSQL
 ↓
Outbox
 ↓
Kafka
 ↓
Notification consumer
 ↓
Email service
```

If something fails, you want to connect those events.

A correlation/request ID gives you:

```text
requestId=abc-123
```

across relevant logs.

Then you can search:

```text
abc-123
```

and reconstruct the request’s journey.

This becomes even more powerful when we introduce distributed tracing.

---

# **4. Metrics**

Logs answer:

**What happened?**

Metrics answer:

**How often/how much/how fast?**

Examples:

```text
HTTP request count
HTTP error rate
request latency
JVM memory
CPU
database connections
Kafka consumer lag
RabbitMQ queue depth
```

You might discover:

```text
p95 latency = 80ms
p99 latency = 2.4s
```

That tells you something very different from simply looking at logs.

---

# **5. Health checks**

Spring Boot Actuator exposes:

```text
/actuator/health
```

for application health information.  

A production deployment can use this to determine whether an instance is healthy.

For Kubernetes, Spring Boot provides:

```text
/actuator/health/liveness
/actuator/health/readiness
```

as dedicated probe endpoints.  

The distinction is important.

### **Liveness**

Is this application instance fundamentally alive?

### **Readiness**

Should this instance receive traffic right now?

---

# **6. A very important Kubernetes rule**

Don’t make liveness depend on every external dependency.

For example:

```text
Database is down
      ↓
liveness = DOWN
      ↓
Kubernetes restarts every pod
      ↓
more load / connection attempts
      ↓
possible cascading failure
```

Spring Boot’s documentation explicitly warns that liveness should not depend on external systems such as databases or external APIs.  

Readiness is where external availability can become relevant.

---

# **7. Actuator**

Actuator gives us production-management endpoints.

For example:

```text
/actuator/health
/actuator/info
/actuator/metrics
```

There are many other endpoints, but **don’t expose everything publicly**.

Spring Boot exposes only `health` over HTTP by default, and its documentation warns that actuator endpoints can contain sensitive information.  

So avoid:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
```

on a public application unless you’ve deliberately secured and evaluated every exposed endpoint.

---

# **8. Tracing**

Now imagine this:

```text
Request
  │
  ├── API: 20ms
  │
  ├── PostgreSQL: 40ms
  │
  ├── Kafka: 10ms
  │
  └── notification: 900ms
```

A distributed trace lets you see the request as a chain of operations.

That’s much easier than trying to reconstruct everything from logs.

Spring Boot’s current observability stack supports Micrometer Observation and OpenTelemetry integrations.  

---

# **9. The production picture**

Now we have:

```text
                    ProjectHub
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
       Logging       Metrics       Tracing
          │             │             │
          └─────────────┼─────────────┘
                        ▼
                 Observability
                        │
              ┌─────────┴─────────┐
              ▼                   ▼
           Alerts              Dashboards
```

And:

```text
Kubernetes
    │
    ├── liveness
    └── readiness
```

---

# **10. What happens when production breaks?**

A mature debugging process looks something like:

```text
Alert
 ↓
Check error rate
 ↓
Check latency
 ↓
Check affected pods
 ↓
Check logs
 ↓
Follow trace
 ↓
Check DB/Kafka/RabbitMQ metrics
 ↓
Identify bottleneck/failure
 ↓
Fix or rollback
```

Not:

```text
"Let's SSH into the server and look around."
```

😄

---

# **One configuration example**

A reasonable starting point is:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics

  endpoint:
    health:
      probes:
        enabled: true
```

Then secure the management endpoints appropriately for your deployment.

The exact exposure/security configuration should be treated as part of your production security design, not copied blindly.  

---

# **The key mental model**

Remember:

```text
Logs
"What happened?"

Metrics
"How much/how often/how fast?"

Traces
"Where did the request go?"

Health
"Can this instance serve traffic?"

Alerts
"Does somebody need to act?"
```

That’s observability.

---

## **We’re nearly done**

The compressed remaining path is now:

```text
89  Observability        ← NOW
90  Performance
91  CI/CD
92  Production deployment
93  Final ProjectHub architecture
94  Final review + next steps
```

**Next: Lesson 90 — Backend Performance: database queries, indexes, connection pools, caching, and avoiding premature optimization.**