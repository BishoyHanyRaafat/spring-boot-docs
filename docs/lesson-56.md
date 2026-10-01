---
title: "Lesson 56: Kubernetes Observability"
sidebar_position: 56
---

We’ve built ProjectHub, secured it, containerized it, and deployed it to Kubernetes.

But there’s one huge problem:

**How do we know what’s actually happening in production?**

Suppose users report:

“ProjectHub is slow.”

Where do you look?

```text
Gateway?
   ↓
Kubernetes?
   ↓
Spring Boot?
   ↓
PostgreSQL?
   ↓
Redis?
   ↓
RabbitMQ?
```

This is where **observability** comes in.

Kubernetes describes observability around three primary signals: **metrics, logs, and traces**. Spring Boot uses the same three-pillar model and integrates metrics/tracing through Micrometer Observation.  

---

# **1. Monitoring vs observability**

These terms are related but not identical.

### **Monitoring**

You ask:

“Is CPU above 80%?”

or:

“Are requests returning 500?”

Monitoring usually focuses on known signals and known failure conditions.

### **Observability**

You ask:

“Why did request `abc123` take 4 seconds?”

and investigate:

```text
request
 ↓
Gateway
 ↓
Pod
 ↓
PostgreSQL
 ↓
Redis
```

Observability helps you understand internal system behavior from external outputs.

---

# **2. The three pillars**

Memorize:

```text
              Observability
                   |
       +-----------+-----------+
       |           |           |
       v           v           v
    Metrics      Logs       Traces
```

Each answers a different question.

### **Metrics**

**How much / how often?**

### **Logs**

**What happened?**

### **Traces**

**Where did this request spend its time?**

You generally want all three.

---

# **3. Metrics**

A metric is a numerical measurement over time.

Examples:

```text
HTTP requests/sec
CPU usage
memory usage
request duration
error count
database connections
queue depth
JVM heap
GC activity
```

Spring Boot Actuator integrates with Micrometer and provides metrics for many application and JVM components.  

---

# **4. Example: request rate**

Suppose ProjectHub receives:

```text
10:00 → 100 req/s
10:01 → 105 req/s
10:02 → 800 req/s
10:03 → 2,000 req/s
```

A graph immediately tells us:

```text
traffic
  ^
  |                 /
  |               /
  |            __/
  |___________/
  +------------------> time
```

That’s much more useful than:

“The server feels busy.”

---

# **5. Error rate**

Suppose:

```text
requests = 100,000
errors   = 2,000
```

Then:

```text
error rate = 2%
```

We can track this over time.

For example:

```text
10:00 → 0.2%
10:01 → 0.3%
10:02 → 0.4%
10:03 → 8.7%  ← 🚨
```

Now we know something changed around 10:03.

---

# **6. Latency**

Latency means how long an operation takes.

For an HTTP request:

```text
request
  |
  +----------------------+
                         |
                       250 ms
                         |
                         v
                      response
```

But averages can be misleading.

Imagine:

```text
99 requests → 10 ms
1 request   → 10 seconds
```

The average doesn’t tell the whole story.

That’s why we care about **percentiles**.

---

# **7. p50, p95, p99**

Suppose:

```text
p50 = 80 ms
p95 = 300 ms
p99 = 1.5 sec
```

Interpretation:

### **p50**

Half the requests are at or below roughly 80 ms.

### **p95**

95% are at or below roughly 300 ms.

### **p99**

99% are at or below roughly 1.5 seconds.

The remaining 1% could be much slower.

This helps reveal tail latency.

---

# **8. Why p99 matters**

Imagine your average is:

```text
120 ms
```

Sounds great.

But:

```text
p50 = 80 ms
p95 = 300 ms
p99 = 5 sec
```

Now you know a significant tail of requests is experiencing serious latency.

For production APIs, tail latency can matter enormously.

---

# **9. Prometheus**

A very common Kubernetes metrics architecture is:

```text
Spring Boot
     |
     | metrics
     v
Prometheus
     |
     v
time-series data
     |
     +------> dashboards
     |
     +------> alerts
```

Kubernetes itself documents Prometheus as a common component in a metrics pipeline that scrapes metrics endpoints and stores the samples as time-series data.  

---

# **10. Spring Boot + Prometheus**

Spring Boot can expose metrics in Prometheus format through:

```text
/actuator/prometheus
```

when the appropriate Prometheus registry is configured and the endpoint is exposed.  

Conceptually:

```text
ProjectHub Pod
     |
     | GET /actuator/prometheus
     |
     v
Prometheus
```

Prometheus periodically scrapes the endpoint.

---

# **11. Prometheus is not Grafana**

Another important distinction.

```text
Prometheus
   ↓
stores/queries metrics

Grafana
   ↓
visualizes data
```

So:

```text
Spring Boot
     ↓
Prometheus
     ↓
Grafana
```

A dashboard might show:

```text
HTTP request rate
HTTP error rate
p95 latency
CPU
memory
JVM heap
database connections
```

---

# **12. Kubernetes metrics**

We also need infrastructure metrics.

For example:

```text
Node CPU
Node memory
Pod CPU
Pod memory
Pod restarts
container state
API server health
scheduler behavior
```

Kubernetes components expose metrics, including the API server, scheduler, kubelet and other components; a typical metrics pipeline collects these for analysis and alerting.  

So we have two perspectives:

```text
Application metrics
       +
Kubernetes metrics
```

---

# **13. Application vs infrastructure metrics**

### **Application**

```text
HTTP latency
HTTP errors
posts.created
posts.deleted
DB query duration
RabbitMQ messages
```

### **Infrastructure**

```text
Pod CPU
Pod memory
Node CPU
Node memory
Pod restarts
network
disk
```

You need both.

---

# **14. Business metrics**

Don’t only monitor machines.

Monitor the business.

For ProjectHub:

```text
projects.created
posts.created
posts.deleted
users.registered
login.failures
project.members.added
```

Suppose infrastructure looks healthy:

```text
CPU      30%
Memory   40%
Errors   0.1%
```

but:

```text
projects.created
       ↓
       0
```

Something could still be seriously wrong.

---

# **15. Custom metrics**

Suppose we want:

```text
projecthub.posts.created
```

Micrometer provides the application metrics abstraction used by Spring Boot.

Conceptually:

```java
Counter counter = Counter.builder("projecthub.posts.created")
        .register(meterRegistry);

counter.increment();
```

We’ll eventually implement this in ProjectHub.

But there’s an important warning.

---

# **16. Cardinality**

Imagine creating a metric tag:

```text
userId=12345
```

Then:

```text
userId=12346
userId=12347
userId=12348
...
```

You could end up with millions of unique time series.

That’s **high cardinality**.

Bad metric labels include things like:

```text
userId
requestId
JWT
email
full URL
```

for large systems.

Spring Boot’s observability documentation distinguishes low-cardinality key/value pairs, which are suitable for metrics and traces, from high-cardinality values, which are kept to traces.  

---

# **17. Good vs bad metric tags**

Good:

```text
endpoint=/posts
method=GET
status=200
region=eu
```

Potentially dangerous:

```text
userId=847291
postId=918273
requestId=abc123...
```

Use traces/logs for individual identifiers.

Use metrics for aggregation.

---

# **18. Logs**

Metrics tell us:

“500 errors increased.”

Logs can tell us:

```text
2026-10-01T10:03:14
ERROR
PostRepository
database connection timeout
```

So:

```text
Metric
 ↓
"There is a problem."

Log
 ↓
"Here's an event associated with the problem."
```

---

# **19. Structured logging**

Instead of:

```text
Post 42 failed for user Alice
```

we want machine-readable information:

```json
{
  "level": "ERROR",
  "event": "post_delete_failed",
  "postId": 42,
  "userId": 123,
  "reason": "database_timeout"
}
```

Now log systems can search:

```text
event = "post_delete_failed"
```

or:

```text
reason = "database_timeout"
```

much more reliably.

---

# **20. Don’t put secrets in logs**

This deserves repeating.

Never log:

```text
password
JWT
refresh token
private key
DB password
```

A centralized logging system can contain logs from your entire production environment.

One careless log statement can turn a secure credential into a widely accessible credential.

---

# **21. Centralized logs**

If we have:

```text
Pod A
Pod B
Pod C
```

and each has local logs:

```text
Pod A → logs
Pod B → logs
Pod C → logs
```

that’s inconvenient.

Pods are disposable.

Instead:

```text
Pod A ──┐
Pod B ──┼──> Log collector ──> Log storage
Pod C ──┘
```

Now when Pod B disappears, its logs can still exist centrally.

---

# **22. Traces**

Now we reach the most powerful concept for distributed systems.

Suppose:

```text
POST /projects
```

takes 2.8 seconds.

Metrics tell you:

```text
p95 = 2.8 sec
```

Logs might say:

```text
Project creation succeeded
```

But why did it take 2.8 seconds?

A trace can show:

```text
POST /projects
│
├── Gateway                 20ms
│
├── ProjectHub              2.7s
│   │
│   ├── Authentication       5ms
│   ├── ProjectService      10ms
│   ├── PostgreSQL          2.6s
│   └── Event publishing    40ms
│
└── Response                30ms
```

Now we immediately suspect PostgreSQL.

---

# **23. Trace and span**

A **trace** represents the overall request journey.

A **span** represents one operation within that journey.

```text
Trace
 |
 +-- Span: HTTP request
 |
 +-- Span: authorization
 |
 +-- Span: database query
 |
 +-- Span: RabbitMQ publish
```

Think:

```text
Trace = entire story

Span = one chapter
```

---

# **24. Trace IDs**

Suppose a request gets:

```text
traceId = 7f31abc...
```

That ID can follow the request through multiple services.

Then you can search:

```text
traceId=7f31abc...
```

and find the entire request journey.

This becomes extremely useful when ProjectHub eventually has:

```text
Gateway
 ↓
ProjectHub
 ↓
RabbitMQ
 ↓
Notification Service
 ↓
Email provider
```

---

# **25. Spring Boot and tracing**

Spring Boot uses Micrometer Observation for metrics and tracing, and supports OpenTelemetry integration.  

The important architectural idea is:

```text
Application code
      ↓
Micrometer Observation
      ↓
metrics + traces
```

rather than sprinkling vendor-specific monitoring calls throughout your business logic.

Spring Boot’s current documentation also recommends using the Micrometer Observation/Tracing APIs rather than directly coupling application code to the OpenTelemetry API for these use cases.  

---

# **26. The three signals together**

Suppose users complain:

“Deleting posts is slow.”

### **Metrics**

```text
DELETE /posts
p95 = 2.4 sec
```

### **Trace**

```text
DELETE /posts
   |
   +-- auth       5ms
   +-- policy     8ms
   +-- PostgreSQL 2.3sec
```

### **Logs**

```text
database timeout
connection pool exhausted
```

Now we have:

```text
Metric → tells us WHEN/How much
Trace  → tells us WHERE
Log    → tells us WHAT happened
```

That’s the real power of observability.

---

# **27. Alerts**

Dashboards don’t wake engineers up.

Alerts do.

Suppose:

```text
error rate > 5%
```

for several minutes.

We can alert:

```text
🚨 ProjectHub high error rate
```

Or:

```text
p95 latency > 1 sec
```

Or:

```text
PostgreSQL connections > 90%
```

Or:

```text
RabbitMQ queue depth rapidly increasing
```

---

# **28. Don’t alert on everything**

A terrible monitoring system produces:

```text
🚨 CPU 81%
🚨 memory 72%
🚨 pod restarted
🚨 request count changed
🚨 GC increased
🚨 ...
```

Eventually engineers stop paying attention.

That’s **alert fatigue**.

Good alerts should indicate something that requires investigation or action.

---

# **29. Symptom vs cause**

Suppose:

```text
PostgreSQL
   ↓
slow
```

causes:

```text
API latency
   ↓
high
```

and:

```text
API errors
   ↓
high
```

Don’t necessarily create three independent paging alerts.

You may want:

```text
PRIMARY SYMPTOM
API availability/latency degraded
```

and then investigate:

```text
PostgreSQL
```

as the cause.

This is where good alert design matters.

---

# **30. SLI**

Now we’re approaching an important production concept.

An **SLI**, or Service Level Indicator, is a measurement of service behavior.

Examples:

```text
request success rate
request latency
availability
```

For ProjectHub:

```text
successful requests / total requests
```

could be an availability SLI.

---

# **31. SLO**

An **SLO**, or Service Level Objective, is a target for an SLI.

For example:

```text
99.9% of valid API requests succeed
```

or:

```text
99% of GET /posts requests complete
within 500ms
```

These are targets, not guarantees.

---

# **32. Error budget**

This is a powerful concept.

If your SLO is:

```text
99.9% availability
```

then the allowed failure budget is:

```text
0.1%
```

That is your **error budget**.

Instead of saying:

“We must never fail.”

you say:

“Our reliability target allows a small amount of failure.”

This helps engineering teams reason about reliability vs shipping changes.

---

# **33. Example**

Suppose ProjectHub handles:

```text
10,000,000 requests
```

with a 99.9% SLO.

Allowed unsuccessful requests:

```text
10,000,000 × 0.001
= 10,000
```

So the SLO translates an abstract percentage into an operational budget.

---

# **34. Why SLOs matter**

Without an explicit target:

```text
"Make it reliable."
```

is vague.

With an SLO:

```text
99.9% successful requests
```

we can ask:

```text
Are we meeting it?
How much budget remains?
What caused failures?
Is this release consuming too much budget?
```

This turns reliability into something measurable.

---

# **35. Kubernetes observability architecture**

Now let’s build the infrastructure:

```text
                 ProjectHub Pods
                 /      |      \
                /       |       \
               v        v        v
          Metrics     Logs     Traces
             |          |         |
             v          v         v
        Prometheus   Log Store  Trace Backend
             |          |         |
             +----------+---------+
                        |
                        v
                    Dashboards
                        |
                        v
                     Alerts
```

Kubernetes describes essentially this kind of signal pipeline: cluster components emit metrics, logs, and traces, which are collected into storage/analysis systems and consumed by operators and automation.  

---

# **36. ProjectHub production stack**

One possible stack is:

```text
Spring Boot
    |
    +-- Actuator
    +-- Micrometer
    +-- Micrometer Tracing
    |
    +----------+
               |
       +-------+-------+
       |       |       |
       v       v       v
  Prometheus  Logs   OpenTelemetry
       |               |
       v               v
    Grafana        Trace backend
```

The exact backend products can vary.

The architecture matters more than memorizing a particular vendor.

---

# **37. What should we monitor?**

For ProjectHub, start with four categories.

### **1. Traffic**

```text
requests/sec
```

### **2. Errors**

```text
4xx
5xx
authentication failures
```

### **3. Latency**

```text
p50
p95
p99
```

### **4. Saturation**

```text
CPU
memory
DB connections
queue depth
thread pools
```

This is closely related to the classic **RED** and **USE** approaches.

---

# **38. RED method**

For services:

```text
R = Rate
E = Errors
D = Duration
```

ProjectHub:

```text
Rate:
  1,500 req/s

Errors:
  1.2%

Duration:
  p95 = 240ms
```

This gives a quick health overview.

---

# **39. USE method**

For infrastructure:

```text
U = Utilization
S = Saturation
E = Errors
```

For PostgreSQL connections:

```text
Utilization:
80%

Saturation:
connection queue growing

Errors:
connection timeouts
```

Now we can reason about bottlenecks.

---

# **40. Observability and autoscaling**

Remember our HPA lesson?

We had:

```text
CPU → HPA → more Pods
```

But CPU isn’t always the best signal.

Suppose:

```text
CPU = 40%
```

yet:

```text
request latency = 3 sec
```

and:

```text
PostgreSQL connections = 100%
```

Adding more Pods might make things worse.

Observability helps us identify the actual bottleneck.

---

# **41. The bottleneck principle**

We’ve seen this before:

**Scale the bottleneck, not merely the easiest component.**

If:

```text
Spring Boot
   ↓
3 Pods → 10 Pods
   ↓
PostgreSQL
```

and PostgreSQL is already saturated, then:

```text
more Pods
   ↓
more DB connections
   ↓
more DB contention
   ↓
possibly worse performance
```

Metrics and traces reveal this.

---

# **42. Observability for RabbitMQ**

Suppose ProjectHub publishes:

```text
ProjectCreated
```

RabbitMQ receives the message.

But consumers fall behind.

You might see:

```text
queue depth:
100
500
2,000
10,000
```

That is a clear signal.

You can then investigate:

```text
consumer count
processing duration
consumer errors
retry rate
dead-letter queue
```

---

# **43. Observability for PostgreSQL**

Useful signals include:

```text
connection count
connection pool usage
query duration
slow queries
locks
transactions
deadlocks
disk usage
CPU
replication lag
```

Suppose traces say:

```text
DB query = 2 seconds
```

Then database metrics and database-level analysis help explain why.

---

# **44. Observability for Redis**

Potential signals:

```text
memory
evictions
hit rate
commands/sec
connections
latency
replication health
```

Imagine:

```text
cache hit rate
 ↓
95%
 ↓
60%
```

Suddenly PostgreSQL may receive dramatically more traffic.

Observability lets us connect those events:

```text
Redis degradation
       ↓
cache misses
       ↓
PostgreSQL load
       ↓
API latency
```

---

# **45. Correlation is the real superpower**

Imagine at 14:02:

```text
API latency ↑
```

At the same time:

```text
PostgreSQL latency ↑
```

and:

```text
DB connection pool saturation ↑
```

and traces show:

```text
HTTP
 ↓
DB query
 ↓
2.7 seconds
```

Now you can form a strong hypothesis:

```text
database saturation
        ↓
slow queries
        ↓
slow API requests
```

Without observability, you’re guessing.

---

# **46. Observability isn’t logging everything**

This is another important lesson.

You don’t want:

```text
log every method call
log every variable
log every request body
```

That creates:

```text
noise
cost
security risks
storage problems
```

Instead:

```text
Metrics → aggregate behavior
Logs    → meaningful events
Traces  → request journeys
```

Each signal has a job.

---

# **47. ProjectHub observability design**

Let’s put everything together:

```text
                         ProjectHub
                            |
                 +----------+----------+
                 |          |          |
                 v          v          v
              Metrics     Logs      Traces
                 |          |          |
                 v          v          v
            Prometheus   Collector   OTel/Tracing
                 |          |          |
                 +----------+----------+
                            |
                            v
                         Grafana
                            |
                   +--------+--------+
                   |                 |
                Dashboards         Alerts
```

And underneath:

```text
Kubernetes metrics
Pod metrics
Node metrics
PostgreSQL metrics
Redis metrics
RabbitMQ metrics
```

all contribute to the operational picture.

---

# **48. The production question changes**

When you’re a beginner, you ask:

“Does my API work?”

As you become a backend engineer, you ask:

“How do I know my API is working?”

Then:

“How do I know it’s working correctly under load?”

Then:

“How do I know which dependency caused the degradation?”

Then:

“How do I know before users report it?”

That’s the progression observability enables.

---

# **Lesson 56 Summary**

You’ve learned:

- Observability
- Metrics
- Logs
- Traces
- Prometheus
- Grafana’s role
- Micrometer
- OpenTelemetry
- p50/p95/p99
- Cardinality
- Structured logging
- Trace IDs and spans
- Alerts
- SLI
- SLO
- Error budgets
- RED
- USE
- Application vs infrastructure metrics
- Observability for PostgreSQL, Redis and RabbitMQ
- How observability interacts with Kubernetes autoscaling

The core model:

```text
                 Observability
                      |
        +-------------+-------------+
        |             |             |
        v             v             v
     Metrics        Logs         Traces
        |             |             |
        v             v             v
   "How much?"    "What?"       "Where?"
        |             |             |
        +-------------+-------------+
                      |
                      v
                  Dashboards
                      |
                      v
                    Alerts
```

Spring Boot’s current observability model is built around Micrometer Observation for metrics and traces, with Actuator providing application observability features and OpenTelemetry integration.  

---

# **Exercise 56**

### **1.**

Explain the difference between:

```text
Metric
Log
Trace
```

using this problem:

`DELETE /posts/42` takes 3 seconds.

---

### **2.**

You observe:

```text
p50 = 80ms
p95 = 300ms
p99 = 5s
```

What does this tell you that an average latency might hide?

---

### **3.**

Why is this a dangerous metric label?

```text
userId=123456
```

What would you use instead if you need to investigate one specific user’s request?

---

### **4.**

ProjectHub has:

```text
CPU: 35%
Memory: 40%
API p95: 4 seconds
PostgreSQL connection pool: 100%
```

Would simply increasing the API Pods necessarily solve the problem?

Explain why.

---

### **5.**

A RabbitMQ queue changes:

```text
100 messages
500
2,000
10,000
```

What does this suggest?

What additional metrics would you investigate?

---

### **6. Tracing challenge**

A trace shows:

```text
POST /projects                 2,500ms
 ├── authentication               5ms
 ├── ProjectService              15ms
 ├── PostgreSQL                2,300ms
 └── RabbitMQ publish            30ms
```

Where would you investigate first, and **why**?

---

### **7. Production challenge**

Design the minimum observability setup for ProjectHub.

Include:

```text
Spring Boot
Actuator
Micrometer
Prometheus
logs
traces
Grafana
alerts
```

and explain what information each component gives you.

**Next: Lesson 57 — Production Reliability: SLOs, SLIs, error budgets, incident response, graceful degradation, retries, timeouts, circuit breakers, and how to keep ProjectHub alive when dependencies start failing.**