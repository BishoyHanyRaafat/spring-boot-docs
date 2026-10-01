---
title: "Lesson 92: Production Deployment"
sidebar_position: 92
---

Now let’s take ProjectHub from:

```text
Docker image
```

to:

```text
https://api.projecthub.com
```

The important thing is understanding **how the pieces connect**.

---

# **1. The complete request path**

A production request might travel like this:

```text
                    Internet
                       │
                       ▼
                 DNS / Cloud LB
                       │
                       ▼
              Gateway / Ingress
                       │
                       ▼
                Kubernetes Service
                       │
             ┌─────────┼─────────┐
             ▼         ▼         ▼
           Pod       Pod       Pod
             │         │         │
             └─────────┼─────────┘
                       ▼
                  Spring Boot
                       │
             ┌─────────┼─────────┐
             ▼         ▼         ▼
        PostgreSQL    Kafka    RabbitMQ
```

A Kubernetes **Service** provides a stable abstraction over a changing set of Pods.  

---

# **2. Docker image**

CI produces something like:

```text
registry.example.com/projecthub:abc123
```

Spring Boot supports both Dockerfiles and Cloud Native Buildpacks for creating container images.  

For ProjectHub, the important principle is:

```text
Source code
    ↓
Build
    ↓
Immutable image
    ↓
Registry
```

Kubernetes should deploy **that image**, rather than rebuilding the application.

---

# **3. Kubernetes Deployment**

The Deployment describes the desired application state.

Conceptually:

```yaml
apiVersion: apps/v1
kind: Deployment

metadata:
  name: projecthub

spec:
  replicas: 3

  selector:
    matchLabels:
      app: projecthub

  template:
    metadata:
      labels:
        app: projecthub

    spec:
      containers:
        - name: projecthub
          image: registry.example.com/projecthub:abc123
```

The important pieces are:

```text
Deployment
   │
   ├── desired replicas = 3
   │
   └── Pod template
           │
           └── image
```

Kubernetes then works to make reality match that desired state.

---

# **4. Why three Pods?**

Suppose we have:

```text
Pod A
Pod B
Pod C
```

and Pod B crashes.

Kubernetes can create another Pod to restore the desired number.

More importantly, multiple Pods allow us to perform rolling deployments without taking the entire application offline.

Kubernetes Deployments use `RollingUpdate` by default, gradually replacing old Pods with new ones.  

---

# **5. Service**

Pods are disposable.

Their IP addresses can change.

So clients shouldn’t connect directly to:

```text
10.x.x.x
```

Instead:

```text
Client
  ↓
projecthub-service
  ↓
┌──────┬──────┬──────┐
Pod A  Pod B  Pod C
```

The Service selects the appropriate Pods.

This gives the application a stable internal network identity.  

---

# **6. External traffic**

Now we need to get traffic from the Internet into the cluster.

Historically:

```text
Internet
   ↓
Ingress
   ↓
Service
   ↓
Pods
```

Ingress can route HTTP/HTTPS traffic based on hosts and paths and can also handle things such as TLS termination and load balancing.  

However, there’s an important current Kubernetes detail:

**Ingress is stable, but its API is frozen; Kubernetes recommends Gateway API for new capabilities.**  

So for learning, you absolutely should understand Ingress.

For a new production architecture, you should also understand **Gateway API**.

---

# **7. DNS**

Suppose the user visits:

```text
api.projecthub.com
```

DNS resolves that hostname toward your external load-balancing entry point.

Conceptually:

```text
api.projecthub.com
        ↓
DNS
        ↓
Load Balancer
        ↓
Gateway / Ingress
        ↓
Service
        ↓
Pods
```

DNS itself doesn’t know about your Spring Boot application.

It simply helps the client find the network entry point.

---

# **8. HTTPS / TLS**

We don’t want:

```text
http://api.projecthub.com
```

for a production API.

We want:

```text
https://api.projecthub.com
```

TLS encrypts traffic between the client and the TLS termination point.

A common architecture is:

```text
Client
  │
 HTTPS
  ▼
Load Balancer / Gateway
  │
  ▼
Kubernetes Service
  │
  ▼
Spring Boot
```

Exactly where TLS terminates depends on your infrastructure.

---

# **9. Readiness is extremely important during deployment**

Suppose Kubernetes creates:

```text
projecthub-v2
```

but Spring Boot is still starting.

If Kubernetes sends production traffic immediately:

```text
User
 ↓
new Pod
 ↓
"Application isn't ready yet"
```

That’s bad.

Instead:

```text
New Pod
   ↓
startup
   ↓
readiness probe
   ↓
READY
   ↓
receive traffic
```

This is why we covered:

```text
/actuator/health/liveness
/actuator/health/readiness
```

earlier.

---

# **10. Rolling deployment**

Suppose we currently have:

```text
v1
v1
v1
```

We deploy:

```text
v2
```

Kubernetes can gradually transition:

```text
v1   v1   v1
 ↓
v2   v1   v1
 ↓
v2   v2   v1
 ↓
v2   v2   v2
```

The old Pods aren’t all killed simultaneously.

Kubernetes documents `maxUnavailable` and `maxSurge` as controls for how aggressively a rolling update replaces Pods.  

---

# **11. What if v2 is broken?**

This is where deployment safety becomes important.

You can inspect:

```bash
kubectl rollout status deployment/projecthub
```

and deployment history:

```bash
kubectl rollout history deployment/projecthub
```

If necessary, Kubernetes supports:

```bash
kubectl rollout undo deployment/projecthub
```

to roll back to an earlier revision.  

So:

```text
v1
 ↓
deploy v2
 ↓
problem
 ↓
rollback
 ↓
v1
```

This is one reason immutable image tags are useful.

---

# **12. Database migrations make deployment harder**

Here’s an important real-world problem.

Suppose version 1 has:

```sql
username
```

and version 2 wants:

```sql
display_name
```

You shouldn’t casually deploy:

```text
DB migration
     ↓
immediately deploy application
```

if old Pods still exist and expect the old schema.

During a rolling deployment:

```text
v1 Pods
+
v2 Pods
```

can temporarily coexist.

Therefore database migrations should generally be designed for **backward compatibility during the transition**.

For example:

```text
Step 1
Add new column

Step 2
Deploy code that can use old + new

Step 3
Migrate data

Step 4
Stop using old column

Step 5
Remove old column later
```

This is often called an **expand-and-contract** migration strategy.

This is a major production concept.

---

# **13. ProjectHub deployment architecture**

Putting the major pieces together:

```text
                         Internet
                            │
                            ▼
                       DNS / HTTPS
                            │
                            ▼
                     Gateway / Ingress
                            │
                            ▼
                  ┌───────────────────┐
                  │ Kubernetes        │
                  │                   │
                  │ ProjectHub Service│
                  │        │          │
                  │   ┌────┼────┐     │
                  │   ▼    ▼    ▼     │
                  │  Pod  Pod  Pod    │
                  └──┬────┬────┬──────┘
                     │    │    │
                     └────┼────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
          PostgreSQL     Kafka      RabbitMQ
              │
            Outbox
```

And beside it:

```text
CI/CD
  │
  ▼
Container Registry
  │
  ▼
Kubernetes Deployment
```

---

# **14. One more important production principle**

Your application should assume:

**Any individual Pod can disappear at any time.**

Therefore:

```text
❌ important state only in memory
❌ local filesystem as permanent storage
❌ session state tied to one Pod
❌ assuming a specific Pod IP
```

Instead:

```text
Database → persistent application state
Redis → shared temporary/cache state
Kafka → durable event stream
Object storage → files
Kubernetes → compute orchestration
```

This is the mindset shift from:

“I have a server.”

to:

**“I have disposable application instances.”**

---

# **15. What we have built**

At this point ProjectHub looks like a genuine production backend:

```text
                    USERS
                      │
                      ▼
                HTTPS / Gateway
                      │
                      ▼
                Kubernetes
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
        API          API          API
          │           │           │
          └───────────┼───────────┘
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
   PostgreSQL       Kafka        RabbitMQ
        │             │             │
      Outbox      Consumers       Workers
                      │
              Notifications
              Analytics
              Search
              Audit
```

Around all of it:

```text
Security
Configuration
Testing
Observability
CI/CD
```

And that brings us to the big finale.

---

# **Next — Lesson 93: Complete ProjectHub Architecture**

We’re going to take **everything you’ve learned**—Spring, REST, JPA, transactions, security, JWT, authorization, Outbox, Kafka, RabbitMQ, testing, Docker, Kubernetes, CI/CD, observability—and put it into **one coherent production architecture**.

That will be the most useful lesson for seeing how all these individual topics actually fit together.