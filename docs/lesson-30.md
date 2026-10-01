---
title: "Lesson 30: Actuator, Health Checks, Metrics & Observability"
sidebar_position: 30
---

**Now** we’re moving from:

**“Does ProjectHub work?”**

to:

**“How do I know ProjectHub is working correctly in production?”**

This is the beginning of **observability**.

Spring Boot’s production-ready features include health, metrics, auditing, and management capabilities through Actuator.  

---

## **1. What is observability?**

There are three major pillars:

```text
Observability
├── Logs
├── Metrics
└── Traces
```

Spring Boot uses **Micrometer Observation** as part of its observability infrastructure for metrics and traces.  

Think of them as three different questions.

### **Logs**

What happened?

```text
2026-10-01 14:32:10
User alice created post 42
```

### **Metrics**

How much / how often?

```text
HTTP requests: 125,432
Errors: 312
Average response time: 84ms
JVM memory: 512MB
```

### **Traces**

What happened during this particular request?

```text
HTTP request
    ↓
PostController
    ↓
PostService
    ↓
PostRepository
    ↓
PostgreSQL
```

Tracing becomes especially valuable when an application has multiple services.

---

# **2. Spring Boot Actuator**

Actuator adds production-oriented management endpoints.

The usual HTTP prefix is:

```text
/actuator
```

For example:

```text
/actuator/health
```

Spring Boot exposes enabled Actuator endpoints over HTTP using this `/actuator/{endpoint-id}` convention by default.  

---

# **3. Add Actuator**

For Maven, conceptually:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

After adding it, Spring Boot can provide endpoints such as:

```text
/actuator/health
/actuator/metrics
```

There are many others, but we don’t expose everything blindly.

That’s important.

---

# **4. Health checks**

The most fundamental endpoint is:

```text
GET /actuator/health
```

A healthy application might return something like:

```json
{
  "status": "UP"
}
```

Spring Boot can also include health information from components such as the database.  

Conceptually:

```text
Load balancer
      │
      │ GET /actuator/health
      ▼
ProjectHub
      │
      ├── Application → UP
      └── PostgreSQL  → UP
```

---

# **5. Why health checks matter**

Imagine you deploy ProjectHub:

```text
Server starts
       ↓
Application starts
       ↓
PostgreSQL connection fails
```

The process might technically still be running.

But the application isn’t actually healthy.

A health endpoint gives infrastructure a way to ask:

“Can this instance currently function?”

This becomes important for:

- Docker
- Kubernetes
- load balancers
- cloud platforms
- deployment systems

---

# **6. Liveness vs readiness**

This distinction is extremely important in production.

### **Liveness**

Should this application process continue running?

### **Readiness**

Is this application ready to receive traffic?

Imagine:

```text
Application starting
       ↓
JVM running
       ↓
Spring starting
       ↓
Database initialization
       ↓
Application ready
```

During startup, the process can be **alive** without being **ready**.

Conceptually:

```text
Liveness:
"I'm not dead."

Readiness:
"I'm ready to serve requests."
```

We’ll use this distinction later when we containerize ProjectHub.

---

# **7. Health isn’t just a URL**

Health is composed from **health indicators**.

For example:

```text
Health
├── db
├── diskSpace
└── ...
```

If PostgreSQL becomes unavailable, the database health indicator can reflect that.

You can also retrieve individual components such as:

```text
/actuator/health/db
```

Spring Boot’s current Actuator health API supports component-specific health information.  

---

# **8. Don’t expose everything publicly**

This is a major production rule.

You should not casually expose:

```text
/actuator/*
```

to the entire internet.

Some Actuator endpoints can reveal:

```text
configuration
environment information
beans
loggers
metrics
```

Some can even modify runtime behavior.

So think:

```text
Public API
    │
    ├── /api/...
    │
    └── limited health endpoint

Management interface
    │
    └── restricted access
```

Actuator endpoints can individually be exposed and access-controlled.  

---

# **9. Metrics**

Now we get to the second pillar.

A metric is a numerical measurement over time.

Examples:

```text
HTTP request count
HTTP request duration
JVM memory
CPU
database connection pool usage
garbage collection
application startup time
```

Spring Boot integrates with **Micrometer**, which provides a facade over different monitoring systems.  

---

# 

# **10.**

**`/actuator/metrics`**

You can inspect registered metrics through:

```text
GET /actuator/metrics
```

For example, you might see metric names related to:

```text
jvm.memory
jvm.gc
process
system
http.server.requests
```

The exact set depends on the application and dependencies.

The metrics endpoint is primarily a **diagnostic endpoint**. Spring’s documentation explicitly says it should not be used as the production metrics backend; an external monitoring system should collect/export the metrics.  

---

# **11. Think about metrics differently from logs**

Suppose you have:

```text
1,000,000 HTTP requests
```

You don’t want one million log messages just to know request volume.

A metric can represent:

```text
http requests = 1,000,000
```

Likewise:

```text
request duration
```

can tell you whether your application is getting slower.

Metrics are particularly useful for **trends and alerting**.

---

# **12. Example**

Imagine ProjectHub has:

```text
POST /projects/{id}/posts
```

During normal operation:

```text
Requests/minute: 500
Error rate: 0.4%
p95 latency: 120ms
```

Then something goes wrong:

```text
Requests/minute: 500
Error rate: 18%
p95 latency: 4.2s
```

You immediately know:

Something changed.

Logs can then help you investigate **why**.

---

# **13. Percentiles**

One metric you’ll hear constantly is:

```text
p50
p95
p99
```

Suppose 1,000 requests happen.

### **p50**

Half of requests are faster than this value.

### **p95**

95% are faster than this value.

### **p99**

99% are faster than this value.

For example:

```text
p50 = 80ms
p95 = 250ms
p99 = 900ms
```

This tells a more useful story than:

```text
average = 110ms
```

because averages can hide slow outliers.

---

# **14. Prometheus**

A very common architecture is:

```text
ProjectHub
    │
    │ metrics
    ▼
Prometheus
    │
    ▼
Grafana
```

Spring Boot can expose a Prometheus-formatted endpoint:

```text
/actuator/prometheus
```

when the appropriate Prometheus registry support is configured.  

Prometheus periodically scrapes the application.

So:

```text
Prometheus
     │
     │ GET /actuator/prometheus
     ▼
ProjectHub
```

Then Grafana can visualize the collected data.

We’ll build this later.

---

# **15. Logs**

The first observability pillar is the one you’ve already encountered.

Instead of:

```java
System.out.println("user created");
```

production applications should use a logging framework.

Conceptually:

```java
log.info("User {} created post {}", username, postId);
```

Different levels:

```text
TRACE
DEBUG
INFO
WARN
ERROR
```

A rough mental model:

```text
DEBUG → developer investigation
INFO  → normal important events
WARN  → unusual but recoverable
ERROR → failure requiring attention
```

---

# **16. Don’t log sensitive information**

Never casually log:

```text
password
JWT
refresh token
private key
credit card data
```

For authentication, don’t do:

```java
log.info("Login request: {}", request);
```

if `request` contains a password.

Instead:

```java
log.info("Login attempt for user {}", username);
```

Security and observability must work together.

---

# **17. Tracing**

Now the third pillar.

Suppose ProjectHub eventually becomes:

```text
Client
  ↓
API Gateway
  ↓
Project Service
  ↓
Post Service
  ↓
Notification Service
  ↓
RabbitMQ
```

A request might travel through several components.

Without tracing, debugging becomes painful.

Tracing gives the request an identity:

```text
traceId = abc123
```

and individual operations can have:

```text
spanId
```

So you can conceptually see:

```text
Trace abc123

Gateway       10ms
  └─ Project  30ms
      └─ Post 120ms
          └─ DB 110ms
```

Spring Boot provides Micrometer Tracing integration and supports OpenTelemetry/OTLP and Brave/Zipkin approaches.  

---

# **18. Logs + traces become powerful together**

Imagine a request:

```text
POST /projects/7/posts
```

and the log says:

```text
traceId=abc123
Creating post
```

Then another service logs:

```text
traceId=abc123
Publishing notification
```

You can follow the same request across components.

That’s much more powerful than isolated log files.

---

# **19. Custom business metrics**

You can also create metrics specific to ProjectHub.

For example:

```text
posts.created
projects.created
authentication.failures
authorization.denials
```

Imagine:

```text
posts.created = 12,450
```

and:

```text
authorization.denials = 37
```

Those can reveal application behavior that generic JVM metrics cannot.

Spring Boot’s observability infrastructure uses Micrometer Observation, and applications can create their own observations through `ObservationRegistry`.  

---

# **20. But don’t add metrics everywhere**

Don’t turn every variable into a metric.

Bad:

```text
userId
postId
email
requestId
```

as unrestricted metric labels.

Why?

Because metrics work best with **low-cardinality** dimensions.

For example:

```text
HTTP method = GET
status = 200
endpoint = /posts/{id}
```

are reasonable dimensions.

But:

```text
userId = 938472
```

could create enormous numbers of unique time series.

Spring’s observability model explicitly distinguishes low-cardinality key values, which can be used for metrics and traces, from high-cardinality values, which are intended for traces.  

---

# **21. ProjectHub observability architecture**

Eventually we’ll have:

```text
                    ProjectHub
                        │
          ┌─────────────┼─────────────┐
          │             │             │
        Logs         Metrics        Traces
          │             │             │
          ▼             ▼             ▼
       Log system    Prometheus    OpenTelemetry
          │             │             │
          └─────────────┼─────────────┘
                        │
                     Grafana
```

Don’t worry about installing all of this yet.

We’re learning the architecture first.

---

# **22. What I want you to understand**

You should now distinguish:

### **Health**

```text
"Is the application healthy?"
```

### **Metrics**

```text
"How is the application behaving numerically?"
```

### **Logs**

```text
"What happened?"
```

### **Traces**

```text
"Where did this request spend its time?"
```

Together:

```text
             Observability
                  │
       ┌──────────┼──────────┐
       │          │          │
      Logs      Metrics    Traces
       │          │          │
    events      numbers    requests
```

---

# **Exercise 30**

Before coding, answer these:

### **1.**

What’s the difference between:

```text
/actuator/health
```

and:

```text
/actuator/metrics
```

### **2.**

Why shouldn’t `/actuator/*` automatically be public?

### **3.**

A ProjectHub request takes 5 seconds.

Which observability tool would you use to investigate:

```text
"What happened during this specific request?"
```

### **4.**

Which is better as a metric label?

```text
endpoint=/posts/{id}
```

or:

```text
userId=847392
```

Why?

### **5.**

Suppose PostgreSQL is down but the Java process is still running.

Explain the difference between:

```text
process alive
```

and:

```text
application ready
```

### **6. Architecture**

Draw this in your own words:

```text
ProjectHub
   ↓
Actuator
   ├── Health
   ├── Metrics
   └── Observability
          ├── Logs
          ├── Metrics
          └── Traces
```

After this, we’ll move into **Lesson 31 — Production Logging**, where we’ll learn proper SLF4J logging, log levels, structured logs, correlation IDs, and how to avoid leaking sensitive information.