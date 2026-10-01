---
title: Lesson 52: Kubernetes Scaling & Reliability
sidebar_position: 52
---

Last lesson we got real traffic into ProjectHub:

```text
Internet
   ↓
Gateway
   ↓
Service
   ↓
Pods
   ↓
Spring Boot
```

Now imagine traffic suddenly goes from:

```text
100 requests/sec
```

to:

```text
10,000 requests/sec
```

Our three Pods may not be enough.

This lesson is about making the application **scale and survive failures**.

---

# **1. Horizontal vs Vertical Scaling**

There are two fundamental approaches.

### **Vertical scaling**

Make one machine/container bigger:

```text
Before:
1 CPU
2 GB RAM

After:
4 CPU
8 GB RAM
```

### **Horizontal scaling**

Add more instances:

```text
Before:

Pod
Pod
Pod


After:

Pod
Pod
Pod
Pod
Pod
Pod
Pod
```

Kubernetes is particularly powerful for horizontal scaling.

---

# **2. Kubernetes Deployment already gives us a foundation**

We currently have:

```yaml
spec:
  replicas: 3
```

Meaning:

```text
ProjectHub Deployment
        |
        +── Pod
        +── Pod
        +── Pod
```

We can manually scale:

```bash
kubectl scale deployment projecthub --replicas=6
```

Now:

```text
3 → 6 Pods
```

But manually deciding when to scale isn’t ideal.

That’s where HPA comes in.

---

# **3. Horizontal Pod Autoscaler**

**HPA = Horizontal Pod Autoscaler**

It automatically adjusts the replica count of a scalable workload based on configured metrics. The current stable API is `autoscaling/v2`.  

Conceptually:

```text
                  Metrics
                     |
                     v
                    HPA
                     |
             +-------+-------+
             |               |
          scale up         scale down
             |               |
             v               v
        more Pods        fewer Pods
```

---

# **4. Example HPA**

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler

metadata:
  name: projecthub

spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: projecthub

  minReplicas: 3
  maxReplicas: 10

  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 60
```

Let’s understand it instead of memorizing it.

---

# 

# **5.**

**`scaleTargetRef`**

```yaml
scaleTargetRef:
  kind: Deployment
  name: projecthub
```

We’re saying:

“HPA controls the replica count of the `projecthub` Deployment.”

So:

```text
HPA
 ↓
Deployment
 ↓
Replica count
 ↓
Pods
```

---

# **6. Minimum replicas**

```yaml
minReplicas: 3
```

Even when traffic is low:

```text
Pods = 3
```

We don’t want ProjectHub to disappear completely.

---

# **7. Maximum replicas**

```yaml
maxReplicas: 10
```

Even if traffic explodes:

```text
Pods ≤ 10
```

Why impose a maximum?

Because unlimited scaling can itself become dangerous.

Imagine:

```text
Traffic increases
 ↓
Pods increase
 ↓
Database connections increase
 ↓
PostgreSQL overwhelmed
 ↓
Requests slow down
 ↓
More Pods created
 ↓
Even more DB connections
```

You’ve created a **scaling feedback problem**.

Autoscaling must consider the entire system, not just the application Pods.

---

# **8. CPU target**

We said:

```yaml
averageUtilization: 60
```

Conceptually:

```text
CPU usage
   ↓
HPA observes
   ↓
average > 60%
   ↓
scale up
```

If utilization falls significantly:

```text
average < target
   ↓
scale down
```

For CPU/memory utilization, Kubernetes uses the Pods’ resource requests when calculating utilization.  

That’s why our earlier `resources.requests` matter.

---

# **9. Remember our Deployment?**

We had:

```yaml
resources:
  requests:
    cpu: "250m"
    memory: "512Mi"

  limits:
    cpu: "1"
    memory: "1Gi"
```

Suppose a Pod requests:

```text
250m CPU
```

and currently uses:

```text
200m CPU
```

Its CPU utilization relative to the request is roughly:

```text
200 / 250 = 80%
```

So an HPA target of 60% would consider that Pod above target.

---

# **10. Why requests matter**

This is an important Kubernetes lesson:

```text
resources.requests
```

aren’t merely documentation.

They influence scheduling and resource-utilization calculations used by resource-based HPA.  

So don’t blindly copy:

```yaml
cpu: "250m"
```

from tutorials.

You eventually measure your real workload.

---

# **11. What happens during traffic growth?**

Imagine:

```text
3 Pods
```

Traffic increases.

```text
CPU:
65%
70%
78%
```

HPA observes the configured metric.

It can increase the Deployment’s desired replicas:

```text
3
 ↓
4
 ↓
5
 ↓
6
```

The Deployment creates additional Pods.

Then the Service has more backends available.

```text
                 Service
                    |
       +------------+------------+
       |       |       |       |
      Pod     Pod     Pod     Pod
       |       |       |       |
       +-------+-------+-------+
```

---

# **12. HPA doesn’t magically create capacity**

This is a subtle but important point.

Suppose HPA says:

```text
Need 20 Pods
```

but your Kubernetes nodes don’t have enough CPU/memory.

Then:

```text
HPA
 ↓
20 desired Pods
 ↓
Cluster capacity insufficient
 ↓
Some Pods remain Pending
```

So there are actually multiple scaling layers:

```text
Application traffic
       ↓
HPA
       ↓
Pod count
       ↓
Cluster capacity
       ↓
Node autoscaling
```

Node autoscaling is a separate concern from HPA.

---

# **13. Application scaling vs database scaling**

Suppose we scale:

```text
3 Pods → 20 Pods
```

Each Pod opens database connections.

Now PostgreSQL might receive:

```text
20 × connection pool
```

instead of:

```text
3 × connection pool
```

So:

```text
Application scaling
        ≠
Database scaling
```

This is one of the most important production lessons.

Adding Pods doesn’t automatically make every dependency faster.

---

# **14. Redis can help**

Suppose every request performs an expensive database lookup:

```text
GET /projects/42

Spring Boot
    ↓
PostgreSQL
    ↓
response
```

Under heavy traffic:

```text
10,000 requests/sec
        ↓
10,000 DB operations/sec
```

Caching can change the architecture:

```text
Request
  ↓
Redis
  |
  +-- cache hit → response
  |
  +-- cache miss
          ↓
      PostgreSQL
```

That’s why our earlier Redis lesson matters now.

---

# **15. Messaging can absorb spikes**

Imagine users create thousands of notifications.

Instead of:

```text
HTTP request
 ↓
create notification
 ↓
send email
 ↓
return response
```

we can use:

```text
HTTP request
 ↓
save event
 ↓
RabbitMQ
 ↓
notification workers
 ↓
email
```

The queue absorbs bursts.

So ProjectHub’s scaling architecture becomes:

```text
HTTP traffic
    ↓
ProjectHub Pods
    ↓
RabbitMQ → workers

ProjectHub Pods
    ↓
Redis

ProjectHub Pods
    ↓
PostgreSQL
```

---

# **16. Scaling isn’t only about CPU**

CPU is easy to understand, but sometimes it’s the wrong metric.

Suppose ProjectHub is waiting on PostgreSQL.

CPU might be:

```text
20%
```

while requests are extremely slow.

CPU-based HPA might conclude:

“Everything is fine.”

But users experience:

```text
5 second latency
```

So production systems may scale based on application-specific metrics such as:

```text
requests/sec
queue depth
request latency
active connections
custom business metrics
```

Kubernetes HPA supports more than just CPU/memory, including other metric sources through its autoscaling APIs.  

---

# **17. Reliability is more than autoscaling**

Suppose we have:

```text
Pod A
Pod B
Pod C
```

Now Kubernetes needs to upgrade a node.

It may need to remove:

```text
Pod A
```

What happens?

```text
Pod A ❌

Pod B ✅
Pod C ✅
```

That’s called a **disruption**.

Kubernetes distinguishes voluntary disruptions, such as node draining or planned maintenance, from involuntary disruptions such as hardware/node failures.  

---

# **18. PodDisruptionBudget**

We can tell Kubernetes:

“Please don’t voluntarily take too many ProjectHub Pods down at once.”

For example:

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

With three replicas:

```text
3 Pods
```

we’re asking Kubernetes to maintain at least:

```text
2 available
```

during supported voluntary eviction operations.

PDBs are specifically designed to limit voluntary disruptions to replicated applications.  

---

# **19. PDB doesn’t make Pods immortal**

This is important.

A PDB does **not** mean:

“Kubernetes can never kill my Pod.”

It doesn’t protect against every failure.

For example:

```text
hardware failure
node crash
kernel panic
```

can still cause disruption.

Kubernetes explicitly notes that involuntary disruptions cannot be prevented by PDBs.  

Think:

```text
PDB
 ↓
protect against certain planned/voluntary disruptions
```

not:

```text
PDB
 ↓
guaranteed uptime
```

---

# **20. Pod placement matters**

Suppose we have three Pods:

```text
Node 1:
  Pod A
  Pod B
  Pod C
```

Node 1 dies.

Everything disappears.

Better:

```text
Node 1:
  Pod A

Node 2:
  Pod B

Node 3:
  Pod C
```

Now one node failure doesn’t remove every replica.

Kubernetes supports mechanisms such as topology spread constraints and affinity/anti-affinity to influence Pod placement.

The principle is:

Replication only improves availability if replicas aren’t all dependent on the same failure domain.

---

# **21. Graceful shutdown**

Now imagine Kubernetes wants to terminate:

```text
Pod A
```

We don’t want:

```text
Request arrives
       ↓
Pod killed
       ↓
500 error
```

We want:

```text
Pod receives termination
       ↓
stop accepting new work
       ↓
finish existing requests
       ↓
shutdown
```

Spring Boot currently enables graceful shutdown by default for its embedded web servers and provides `spring.lifecycle.timeout-per-shutdown-phase` to configure the shutdown grace period.  

---

# **22. Kubernetes termination**

Kubernetes has its own termination lifecycle.

The Pod enters:

```text
Terminating
```

The kubelet can execute a `preStop` hook if configured, then sends the container’s main process a `SIGTERM`, while the Service endpoints are updated so terminating Pods are no longer treated as normal in-service endpoints. The default termination grace period is 30 seconds unless configured otherwise.  

Conceptually:

```text
Pod
 ↓
Terminating
 ↓
remove from normal traffic
 ↓
SIGTERM
 ↓
Spring graceful shutdown
 ↓
finish requests
 ↓
process exits
```

This is why graceful shutdown matters.

---

# **23. Spring Boot configuration**

We can configure the shutdown timeout:

```yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
```

Spring Boot allows the timeout to define how long the graceful shutdown phase can wait for existing requests to complete.  

You need to choose this based on your application’s real request characteristics.

Don’t blindly choose 20 seconds.

---

# **24. Why readiness + graceful shutdown work together**

These two concepts complement each other.

### **Readiness**

Controls:

```text
"Should new traffic come here?"
```

### **Graceful shutdown**

Controls:

```text
"What happens to work already being processed?"
```

Together:

```text
Pod shutdown
     |
     +-- Readiness → stop receiving normal traffic
     |
     +-- Graceful shutdown → finish existing requests
     |
     v
   Exit
```

That’s a very important production pattern.

---

# **25. Rolling deployment**

Now combine:

```text
Deployment
+
readiness
+
graceful shutdown
+
multiple replicas
```

Suppose:

```text
Version 1
Pod A
Pod B
Pod C
```

We deploy Version 2.

Kubernetes gradually replaces Pods.

```text
V2    V1    V1
 ↓
V2    V2    V1
 ↓
V2    V2    V2
```

If readiness is correct, new Pods shouldn’t receive traffic until ready.

---

# **26. What if a Pod crashes?**

Suppose:

```text
Pod A ❌
```

The Deployment wants:

```text
replicas = 3
```

So Kubernetes creates a replacement:

```text
Pod D
```

Eventually:

```text
Pod B
Pod C
Pod D
```

This is the power of the **desired state model**.

You don’t normally tell Kubernetes:

“If Pod A crashes, create Pod D.”

You tell Kubernetes:

“I want three healthy replicas.”

The controllers work toward that desired state.

---

# **27. The full reliability architecture**

We’re now at:

```text
                         Internet
                            |
                         Gateway
                            |
                       Load Balancer
                            |
                       ProjectHub
                        Service
                            |
              +-------------+-------------+
              |             |             |
             Pod           Pod           Pod
              |             |             |
              +-------------+-------------+
                            |
                +-----------+-----------+
                |           |           |
                v           v           v
            PostgreSQL     Redis      RabbitMQ
```

And around ProjectHub:

```text
                 +----------------+
                 |      HPA       |
                 +-------+--------+
                         |
                         v
                    Pod count

                 +----------------+
                 |      PDB       |
                 +-------+--------+
                         |
                         v
                  disruption safety

                 +----------------+
                 | Readiness/Liveness |
                 +-------+--------+
                         |
                         v
                    Pod health
```

---

# **28. A production traffic spike**

Let’s walk through the scenario from the beginning.

Normal traffic:

```text
100 req/s
```

ProjectHub:

```text
3 Pods
```

Traffic increases:

```text
1,000 req/s
```

CPU rises:

```text
30% → 60%
```

HPA observes the target.

```text
3 Pods
   ↓
5 Pods
```

Traffic increases again:

```text
5,000 req/s
```

```text
5 Pods
   ↓
8 Pods
```

But now PostgreSQL starts becoming the bottleneck.

That’s when we need to think about:

```text
indexes
connection pools
caching
read replicas
query optimization
```

not simply:

```text
"Add 100 more Pods!"
```

---

# **29. This is why backend engineering is interconnected**

Notice how everything we’ve learned starts connecting:

```text
Spring Boot
    |
    +---- Database
    |
    +---- Redis
    |
    +---- Messaging
    |
    +---- Docker
    |
    +---- Kubernetes
            |
            +---- HPA
            +---- Service
            +---- Gateway
            +---- PDB
            +---- Health probes
```

You don’t learn these as isolated technologies.

You learn **how the system behaves as a whole**.

---

# **30. A critical lesson about scaling**

Never think:

“Kubernetes means infinite scalability.”

Instead:

```text
Load
 ↓
Application capacity
 ↓
Database capacity
 ↓
Cache capacity
 ↓
Queue capacity
 ↓
Network capacity
 ↓
Cluster capacity
```

Your actual system capacity is constrained by bottlenecks.

A useful mental model is:

**Scale the bottleneck, not the component that is easiest to scale.**

---

# **Exercise 52**

Let’s test whether you really understand this.

### **1.**

What’s the difference between:

```text
Vertical scaling
Horizontal scaling
```

---

### **2.**

Why does HPA need:

```yaml
resources:
  requests:
    cpu: ...
```

when using CPU utilization as its metric?

---

### **3.**

You have:

```text
minReplicas: 3
maxReplicas: 10
```

Traffic increases dramatically.

What component decides that more Pods are needed?

What component actually creates those Pods?

---

### **4.**

ProjectHub has 10 Pods, but PostgreSQL can only handle the database workload generated by 5 Pods.

Why can simply increasing the HPA maximum to 50 make things worse?

---

### **5.**

What’s the purpose of this?

```yaml
kind: PodDisruptionBudget

spec:
  minAvailable: 2
```

And what **doesn’t** it protect against?

---

### **6.**

Explain the difference between:

```text
Liveness
Readiness
Graceful shutdown
```

---

### **7. Production scenario**

You have:

```text
ProjectHub:
3 Pods

Pod A → Node 1
Pod B → Node 2
Pod C → Node 3
```

Node 2 suddenly crashes.

Walk me through what you expect Kubernetes to do.

---

### **8. Final architecture challenge**

Design what happens when ProjectHub receives **10× its normal traffic**:

```text
Internet
   ↓
Gateway
   ↓
Service
   ↓
Pods
   ↓
???
```

Include:

- HPA
- Redis
- PostgreSQL
- RabbitMQ
- readiness
- graceful shutdown

Don’t worry about YAML. **Explain the flow in your own words.**

**Next: Lesson 53 — Kubernetes Storage & Stateful Applications: why PostgreSQL/Redis/RabbitMQ are fundamentally different from our stateless Spring Boot Pods, StatefulSets, PersistentVolumes, StorageClasses, backups, and the stateful/stateless boundary.**