---
title: "Lesson 57: Production Reliability"
sidebar_position: 57
---

We’ve reached an important transition.

So far we’ve learned how to **build** ProjectHub:

```text
Spring Boot
PostgreSQL
Redis
RabbitMQ
Docker
Kubernetes
```

And how to **observe** it:

```text
Metrics
Logs
Traces
Alerts
SLOs
```

Now we need to answer:

**What should ProjectHub do when something goes wrong?**

Because in production, failures aren’t exceptional.

```text
PostgreSQL slows down
Redis disappears
RabbitMQ is overloaded
network calls timeout
Pods restart
nodes disappear
third-party APIs fail
deployments go wrong
```

Reliable systems aren’t systems where nothing fails.

They’re systems that **fail in controlled ways**.

---

# **1. Reliability is about failure behavior**

Imagine ProjectHub depends on PostgreSQL:

```text
ProjectHub
    |
    v
PostgreSQL
```

PostgreSQL becomes unavailable.

A bad application might do:

```text
request
  ↓
wait
  ↓
wait
  ↓
wait
  ↓
wait
  ↓
timeout
```

Meanwhile 500 requests are doing the same thing.

Eventually:

```text
database failure
      ↓
request threads blocked
      ↓
connection pool exhausted
      ↓
API becomes unavailable
```

One dependency failure has become an application-wide failure.

We want to prevent that.

---

# **2. The reliability toolbox**

The major concepts we’ll learn today are:

```text
Timeouts
Retries
Exponential backoff
Jitter
Circuit breakers
Bulkheads
Graceful degradation
Idempotency
SLOs
Error budgets
Incident response
```

These aren’t independent tricks.

They work together.

---

# **3. First rule: every remote call needs a timeout**

Suppose ProjectHub calls:

```text
ProjectHub → Payment Service
```

If we don’t have a timeout:

```text
request
   |
   v
Payment Service
   |
   X
   |
  hangs
```

Our application might wait indefinitely.

Instead:

```text
request
   |
   v
Payment Service
   |
   | 2 seconds
   v
timeout
```

Then we can make a decision.

For example:

```text
Payment unavailable
       ↓
return controlled error
```

---

# **4. Why timeouts are so important**

Imagine 100 application threads.

Every request waits 30 seconds for a broken dependency.

You can end up with:

```text
100 threads
   ↓
100 waiting requests
   ↓
no capacity
```

This is sometimes called **resource exhaustion** or a cascading failure.

A timeout limits how long one operation can occupy resources.

---

# **5. Timeouts should exist at multiple layers**

For example:

```text
HTTP client timeout
Database connection timeout
Database query timeout
Redis timeout
RabbitMQ operation timeout
Gateway timeout
```

Don’t assume:

“The network will eventually tell me.”

Design explicit limits.

---

# **6. Timeout isn’t failure recovery**

Suppose:

```text
Redis
  ↓
timeout
```

What should we do?

Sometimes:

```text
retry
```

Sometimes:

```text
return fallback
```

Sometimes:

```text
fail immediately
```

It depends on the operation.

That’s where reliability design becomes interesting.

---

# **7. Retries**

Suppose a temporary network failure occurs:

```text
Request 1 → failure
Request 2 → success
```

A retry can help.

Conceptually:

```text
request
  ↓
failure
  ↓
wait
  ↓
retry
  ↓
success
```

This is useful for **transient failures**.

But retries can also make outages much worse.

---

# **8. The retry storm**

Imagine 1,000 requests hit a broken dependency.

Each request retries 3 times:

```text
1,000 original
+
3,000 retries
=
4,000 calls
```

Now the already-struggling dependency gets even more traffic.

This can create:

```text
failure
  ↓
retries
  ↓
more load
  ↓
more failure
  ↓
more retries
```

That’s a **retry storm**.

So:

Never add retries blindly.

---

# **9. Exponential backoff**

Instead of:

```text
retry immediately
retry immediately
retry immediately
```

we increase the delay:

```text
attempt 1 → immediate
attempt 2 → 100ms
attempt 3 → 200ms
attempt 4 → 400ms
```

Conceptually:

```text
delay = base × 2^attempt
```

The exact numbers depend on the system.

The important idea:

**Give the dependency time to recover.**

---

# **10. Jitter**

There’s another problem.

Suppose 10,000 requests fail simultaneously.

Without jitter:

```text
100ms → everyone retries
200ms → everyone retries
400ms → everyone retries
```

You get synchronized traffic spikes.

**Jitter** adds randomness:

```text
100ms + random
200ms + random
400ms + random
```

So requests spread out.

Conceptually:

```text
Backoff
   +
Jitter
   =
less synchronized retry traffic
```

---

# **11. Only retry retryable failures**

This is critical.

Suppose:

```http
POST /projects
```

returns:

```text
400 Bad Request
```

Should we retry?

Usually no.

The request itself is invalid.

Retrying doesn’t fix:

```text
title = ""
```

Similarly, don’t blindly retry:

```text
401
403
404
```

because those generally aren’t transient infrastructure failures.

---

# **12. Retry classification**

Think:

```text
                 Failure
                    |
        +-----------+-----------+
        |                       |
   potentially transient      permanent
        |                       |
        v                       v
     retry?                  don't retry
```

Examples of potentially transient failures:

```text
network interruption
temporary connection failure
some 5xx responses
temporary overload
```

Examples of permanent failures:

```text
400
401
403
invalid input
business rule violation
resource doesn't exist
```

The exact retry policy depends on the operation and protocol.

---

# **13. GET vs POST**

This becomes especially important with HTTP.

Consider:

```http
GET /projects/42
```

If it fails transiently, retrying is often straightforward because GET is intended to be safe.

Now:

```http
POST /payments
```

Suppose the server actually processed the request but the response was lost.

The client sees:

```text
timeout
```

If it blindly retries:

```text
POST /payments
```

the payment could potentially happen twice.

That’s a dangerous failure mode.

---

# **14. Idempotency**

This is where **idempotency** becomes essential.

An operation is idempotent when repeating the same operation produces the same intended result rather than creating repeated side effects.

For example:

```text
PUT /users/42
```

setting:

```json
{
  "name": "Alice"
}
```

multiple times should leave the resource in the same state.

But:

```text
POST /payments
```

could create multiple payments.

---

# **15. Idempotency keys**

For operations where retries are necessary but duplicate side effects are dangerous, clients can send an idempotency key:

```http
Idempotency-Key: 7f3c...
```

The server stores the result associated with that key.

Conceptually:

```text
POST payment
key = ABC123
       |
       v
   database
       |
       +-- ABC123 already processed?
       |
       +-- yes → return original result
       |
       +-- no → process + store result
```

Then:

```text
retry
 ↓
same key
 ↓
same result
```

This is extremely useful for payments, order creation, job submission and similar operations.

---

# **16. Circuit breakers**

Now suppose Redis is completely down.

Without a circuit breaker:

```text
Request
 ↓
Redis
 ↓
timeout
 ↓
Request
 ↓
Redis
 ↓
timeout
 ↓
Request
 ↓
Redis
 ↓
timeout
```

We’re wasting resources repeatedly calling something that is already known to be unavailable.

A **circuit breaker** changes behavior.

---

# **17. Circuit breaker states**

Typically:

```text
CLOSED
```

means normal operation.

```text
OPEN
```

means:

Stop calling the dependency temporarily.

And:

```text
HALF_OPEN
```

means:

Try a small number of requests to see whether the dependency recovered.

Conceptually:

```text
             failures
CLOSED ----------------→ OPEN
                           |
                           | wait
                           v
                      HALF_OPEN
                       /       \
                  success      failure
                    |             |
                    v             v
                 CLOSED         OPEN
```

---

# **18. Why circuit breakers help**

Suppose PostgreSQL is down.

Instead of:

```text
10,000 requests
   ↓
10,000 database attempts
```

we can eventually get:

```text
10,000 requests
   ↓
circuit OPEN
   ↓
fail quickly / fallback
```

This protects both:

```text
ProjectHub
```

and:

```text
the failing dependency
```

---

# **19. Circuit breaker ≠ retry**

These solve different problems.

### **Retry**

“This failure may be temporary. Try again.”

### **Circuit breaker**

“We’ve had enough failures. Stop making calls for a while.”

Together:

```text
request
  ↓
attempt
  ↓
temporary failure
  ↓
retry with backoff
  ↓
still failing
  ↓
circuit opens
  ↓
fail fast
```

---

# **20. Bulkheads**

Imagine ProjectHub has:

```text
HTTP requests
   |
   +---- PostgreSQL
   |
   +---- Redis
   |
   +---- external API
```

Suppose the external API becomes extremely slow.

If all application resources can be consumed waiting for it:

```text
external API
    ↓
slow
    ↓
threads/connections consumed
    ↓
ProjectHub
    ↓
everything becomes slow
```

A **bulkhead** limits how much of the system one dependency can consume.

Think of a ship:

```text
+-----------+-----------+-----------+
|           |           |           |
|   DB      |  Redis    | External  |
|           |           | API       |
|           |           |           |
+-----------+-----------+-----------+
```

If one compartment floods:

```text
+-----------+-----------+-----------+
|           |           |           |
|   DB      |  Redis    | FLOODED   |
|           |           |  X X X     |
|           |           |           |
+-----------+-----------+-----------+
```

the whole ship doesn’t necessarily sink.

---

# **21. Bulkheads in backend systems**

Possible isolation mechanisms include:

```text
separate connection pools
bounded thread pools
bounded queues
concurrency limits
separate worker pools
```

The exact implementation depends on your architecture.

The principle is:

**One dependency should not be able to consume all shared resources.**

---

# **22. Graceful degradation**

Now suppose Redis is down.

Does ProjectHub need to become completely unavailable?

Maybe not.

If Redis is being used as a cache:

```text
ProjectHub
   |
   v
Redis
   |
   X
```

we might do:

```text
cache miss / cache unavailable
       ↓
PostgreSQL
       ↓
return data
```

Performance may degrade.

But correctness remains.

That’s **graceful degradation**.

---

# **23. Cache failure example**

Normal:

```text
GET /projects/42
       |
       v
     Redis
       |
       v
    cached data
```

Redis fails:

```text
GET /projects/42
       |
       v
     Redis ❌
       |
       v
   PostgreSQL
       |
       v
     result
```

That’s much better than:

```text
Redis ❌
   ↓
API ❌
```

when Redis is only a performance optimization.

---

# **24. But not every dependency can degrade**

Suppose ProjectHub needs PostgreSQL to create a project.

You can’t realistically do:

```text
PostgreSQL ❌
      ↓
create project anyway
```

because PostgreSQL is the source of truth.

So we distinguish:

### **Optional dependency**

```text
Redis cache
```

Potentially degrade.

### **Required dependency**

```text
PostgreSQL
```

Usually fail safely.

This distinction should be explicit in your architecture.

---

# **25. RabbitMQ is different**

Suppose creating a project should send a notification.

We might have:

```text
Create project
     |
     v
PostgreSQL
     |
     v
ProjectCreated event
     |
     v
RabbitMQ
```

If RabbitMQ is temporarily unavailable, we have a problem.

Should we fail the entire project creation?

Maybe.

But often we want:

```text
database transaction
       +
outbox event
```

Then:

```text
Project created
       ↓
Outbox row stored
       ↓
publisher retries later
       ↓
RabbitMQ
```

This connects directly to the Outbox Pattern from our messaging lesson.

---

# **26. Reliability is connected to consistency**

Suppose we do:

```text
DB transaction
   ↓
commit
   ↓
RabbitMQ publish
   ↓
failure
```

Now:

```text
Database = project exists
RabbitMQ = event missing
```

That’s an inconsistent state.

The Outbox Pattern solves the dual-write problem:

```text
Transaction
   |
   +-- project
   |
   +-- outbox event
```

Both commit together.

Then:

```text
outbox
   ↓
publisher
   ↓
RabbitMQ
```

with retries.

---

# **27. Readiness vs liveness**

We covered this earlier, but reliability makes the distinction even more important.

### **Readiness**

Should this Pod receive traffic?

### **Liveness**

Should Kubernetes restart this container?

Kubernetes’ probe documentation explicitly distinguishes failed readiness from failed liveness: readiness removes the Pod from service traffic while liveness can trigger a restart.  

---

# **28. Don’t make liveness depend on PostgreSQL**

Imagine:

```text
PostgreSQL
   ↓
down
```

and:

```text
liveness = "Can I reach PostgreSQL?"
```

Every ProjectHub Pod says:

```text
UNHEALTHY
```

Kubernetes restarts them.

They start.

PostgreSQL is still down.

They fail.

Kubernetes restarts them again.

You’ve created:

```text
database failure
    ↓
pod restarts
    ↓
more connection attempts
    ↓
more load
```

That’s usually the wrong behavior.

Liveness should primarily answer whether the application process itself is stuck/unhealthy enough to restart.

---

# **29. Readiness can be dependency-aware**

Readiness is different.

If ProjectHub truly cannot serve requests without PostgreSQL, it may make sense for readiness to reflect that state.

Then:

```text
PostgreSQL unavailable
       ↓
Pod not ready
       ↓
Service stops sending traffic
```

The Pod isn’t necessarily restarted.

That’s an important distinction.

---

# **30. Graceful shutdown**

Now imagine Kubernetes wants to terminate a ProjectHub Pod.

We don’t want:

```text
request
  ↓
Pod suddenly dies
  ↓
client gets connection reset
```

Instead:

```text
Pod termination
      ↓
stop accepting new traffic
      ↓
finish in-flight requests
      ↓
shutdown
```

Spring Boot enables graceful shutdown by default for its supported embedded web servers, and `spring.lifecycle.timeout-per-shutdown-phase` controls the grace period.  

---

# **31. Kubernetes termination**

Kubernetes has its own termination process.

During graceful Pod termination, Kubernetes removes the terminating Pod from normal service endpoints and gives the container a termination grace period before forceful termination. API-initiated eviction also respects PodDisruptionBudgets and `terminationGracePeriodSeconds`.  

So our architecture becomes:

```text
Pod termination
      |
      v
Readiness changes / removed from traffic
      |
      v
existing requests finish
      |
      v
Spring graceful shutdown
      |
      v
process exits
```

This is a major reliability improvement during deployments and node maintenance.

---

# **32. Configure the grace period**

For example:

```yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
```

And Kubernetes might have:

```yaml
spec:
  terminationGracePeriodSeconds: 30
```

The values should be designed together.

You don’t want:

```text
Spring needs 20 sec
Kubernetes kills after 5 sec
```

because the application never gets enough time.

---

# **33. PodDisruptionBudget**

Suppose ProjectHub has:

```text
3 Pods
```

and Kubernetes wants to drain a node.

We don’t want all three disappearing simultaneously.

A PDB can say:

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget

metadata:
  name: projecthub

spec:
  minAvailable: 2

  selector:
    matchLabels:
      app: projecthub
```

This means voluntary disruption should preserve at least two available Pods.

Kubernetes documents PDBs as limiting simultaneous voluntary disruptions for replicated applications. They do **not** prevent involuntary failures such as hardware or node failures.  

---

# **34. PDB doesn’t make the application highly available**

Suppose:

```text
Node 1 → Pod A
Node 2 → Pod B
Node 3 → Pod C
```

A PDB protects against certain voluntary disruptions.

But if:

```text
Node 1
  ↓
hardware failure
```

Pod A is gone.

PDB can’t stop hardware from failing.

Kubernetes explicitly distinguishes voluntary and involuntary disruptions.  

This is why we also spread replicas across failure domains.

---

# **35. Reliability layers**

Now look at how many layers are cooperating:

```text
Replicas
   +
Readiness
   +
Graceful shutdown
   +
PDB
   +
timeouts
   +
retries
   +
circuit breakers
   +
bulkheads
   +
fallbacks
   +
observability
```

None alone is sufficient.

Together they make the system more resilient.

---

# **36. Incident response**

Eventually something will break.

You need a process.

A simple incident lifecycle:

```text
Detect
  ↓
Triage
  ↓
Mitigate
  ↓
Recover
  ↓
Investigate
  ↓
Learn
```

---

# **37. Detect**

An alert fires:

```text
🚨 ProjectHub 5xx rate > 5%
```

You look at:

```text
Grafana
metrics
logs
traces
```

---

# **38. Triage**

Ask:

```text
What changed?
When did it start?
Which endpoints?
Which users?
Which region?
Which Pods?
Which dependency?
```

For example:

```text
deployment at 14:02
errors at 14:04
```

That is a useful clue.

---

# **39. Mitigate**

During an incident, your first objective isn’t:

“Find the perfect root cause.”

It’s:

**Stop the damage.**

Possible mitigation:

```text
rollback deployment
disable feature
reduce traffic
increase capacity
disable optional dependency
switch to fallback
```

Then investigate.

---

# **40. Rollback**

Suppose version:

```text
projecthub:1.5.0
```

causes failures.

Kubernetes Deployment history can allow rollback to a previous revision.

Conceptually:

```text
1.4.2 → 1.5.0 → failures
                  ↓
               rollback
                  ↓
               1.4.2
```

This is one reason immutable image versions are useful.

---

# **41. Post-incident analysis**

After recovery:

Don’t just say:

“Developer X caused the outage.”

Instead ask:

```text
Why was the bad change deployed?
Why wasn't it detected?
Why didn't tests catch it?
Why didn't monitoring alert earlier?
Why was rollback difficult?
What control can prevent recurrence?
```

That’s how reliability improves.

---

# **42. SLI → SLO → error budget**

Now connect this lesson to Lesson 56.

Suppose:

```text
SLO:
99.9% successful requests
```

We monitor:

```text
SLI:
successful requests / total requests
```

If failures increase:

```text
error budget
   ↓
decreases
```

This tells us reliability isn’t merely:

“The server looks okay.”

It’s measurable.

---

# **43. Reliability is a tradeoff**

Suppose the team wants:

```text
100% uptime
```

and:

```text
deploy 20 times/day
```

and:

```text
ship features extremely quickly
```

These goals can conflict.

SLOs give us a framework for discussing that tradeoff.

For example:

```text
99.9% SLO
```

means we intentionally define a small amount of acceptable unreliability.

---

# **44. Error budget and releases**

Suppose we’ve consumed most of the error budget.

That could influence engineering decisions such as:

```text
slow down risky releases
invest in reliability
fix recurring failures
improve testing
```

If plenty of budget remains:

```text
experiment
ship features
```

may be more reasonable.

The important point is that the decision is based on measured reliability rather than vague feelings.

---

# **45. Reliability architecture for ProjectHub**

Let’s combine everything:

```text
                         Internet
                            |
                         Gateway
                            |
                     +------+------+
                     |             |
                    Pod           Pod
                     |             |
                     +------+------+
                            |
                       PostgreSQL
                            |
                     +------+------+
                     |             |
                   Redis        RabbitMQ
```

Around this:

```text
          Observability
          /     |      \
      Metrics  Logs   Traces
         |
      Alerts
```

And application resilience:

```text
Remote call
    |
 Timeout
    |
 Retry?
    |
 Backoff + Jitter
    |
 Still failing?
    |
 Circuit breaker
    |
 Fallback / controlled failure
```

And Kubernetes resilience:

```text
Deployment
   +
Replicas
   +
Readiness
   +
Graceful shutdown
   +
PDB
   +
multi-node/zone placement
```

---

# **46. The golden rule**

Here’s the mental model I want you to remember:

**Every dependency should have an explicit failure strategy.**

For each dependency ask:

```text
What happens if it's slow?
What happens if it's unavailable?
What happens if it returns errors?
Should we retry?
How many times?
Should we fail fast?
Can we degrade?
Can we cache?
Can we queue?
Can we recover automatically?
How will we know it's failing?
```

This is reliability engineering.

---

# **47. ProjectHub dependency table**

Start thinking like this:

|**Dependency**|**If slow**|**If unavailable**|**Recovery strategy**|
|---|---|---|---|
|PostgreSQL|timeout|controlled failure|retry carefully / recover DB|
|Redis|timeout|fallback to DB if cache|degrade|
|RabbitMQ|timeout|outbox/retry|asynchronous recovery|
|External API|timeout|fallback/error|timeout + retry + circuit breaker|
|Gateway|unavailable|API unavailable|redundant infrastructure|
|ProjectHub Pod|crash|traffic moves elsewhere|Deployment recreates|

Notice how every dependency has a different answer.

That’s the key.

---

# **Lesson 57 Summary**

You’ve learned:

- Reliability vs availability
- Timeouts
- Retries
- Exponential backoff
- Jitter
- Retry storms
- Idempotency
- Idempotency keys
- Circuit breakers
- Bulkheads
- Graceful degradation
- Required vs optional dependencies
- Outbox-based recovery
- Readiness vs liveness
- Graceful shutdown
- PodDisruptionBudgets
- Voluntary vs involuntary disruptions
- Incident response
- Rollbacks
- SLO/error-budget-driven reliability

The core failure-handling model:

```text
                 Remote dependency
                         |
                       timeout
                         |
                    transient?
                    /        \
                  yes         no
                  |            |
               retry        fail
                  |
            backoff+jitter
                  |
             still failing?
                  |
                 yes
                  |
          circuit breaker
                  |
          +-------+-------+
          |               |
       fallback      controlled error
```

And for Kubernetes:

```text
Deployment
    |
 replicas
    |
 readiness
    |
 graceful shutdown
    |
 PDB
    |
 failure-domain spreading
```

Kubernetes’ current disruption model explicitly separates voluntary disruptions, which PDBs can constrain, from involuntary failures that PDBs cannot prevent. Spring Boot’s current graceful-shutdown support lets existing requests complete during a configured shutdown grace period while new requests are rejected.  

---

# **Exercise 57**

### **1. Timeout**

Why is this dangerous?

```text
ProjectHub
    ↓
External API
    ↓
no timeout
```

Explain how this can eventually exhaust application resources.

---

### **2. Retry design**

A request fails with:

```text
503 Service Unavailable
```

Would you retry it?

If yes:

- How many times?
- Immediately or with backoff?
- Why add jitter?

Then compare that with:

```text
400 Bad Request
```

---

### **3. Circuit breaker**

Explain the three states:

```text
CLOSED
OPEN
HALF_OPEN
```

and what causes transitions between them.

---

### **4. Redis failure**

ProjectHub uses Redis **only as a cache**.

Redis goes down.

Design the request flow so that users can still retrieve projects.

---

### **5. PostgreSQL failure**

PostgreSQL goes down during:

```http
POST /projects
```

Should ProjectHub:

```text
A. retry forever
B. immediately crash the Pod
C. timeout and return a controlled error
D. create the project in memory
```

Choose the appropriate behavior and explain why.

---

### **6. Idempotency**

Suppose:

```http
POST /payments
```

takes 5 seconds.

The client times out after 3 seconds.

The server **actually processed the payment**.

The client retries.

Explain how an idempotency key prevents a duplicate payment.

---

### **7. Kubernetes**

ProjectHub has:

```text
3 Pods
```

and:

```yaml
minAvailable: 2
```

in its PDB.

What happens when Kubernetes tries a **voluntary eviction** of one Pod?

What about a node suddenly suffering a hardware failure?

---

### **8. Final architecture challenge**

Design failure behavior for:

```text
ProjectHub
   |
   +-- PostgreSQL
   +-- Redis
   +-- RabbitMQ
   +-- External Email API
```

For **each dependency**, specify:

```text
timeout
retry?
backoff?
circuit breaker?
fallback?
queue/outbox?
observability signal?
```

This exercise is particularly important: don’t just memorize resilience patterns. Learn to choose **which pattern belongs to which failure mode**.

**Next: Lesson 58 — Performance Engineering: JVM memory, connection pools, thread pools, database bottlenecks, caching strategy, N+1 queries, load testing, and how to find the real bottleneck instead of guessing.**