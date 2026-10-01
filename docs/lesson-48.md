---
title: "Lesson 48: Kubernetes Fundamentals"
sidebar_position: 48
---

This is a big one.

We’ve gone from:

```text
Java
 ↓
Spring Boot
 ↓
PostgreSQL
 ↓
Redis
 ↓
RabbitMQ
 ↓
Docker
```

Now we’re going to learn how large systems **run and manage many containers**.

That is where Kubernetes comes in.

---

# **1. Why isn’t Docker enough?**

Suppose ProjectHub has one container:

```text
ProjectHub
```

Easy.

But production might need:

```text
ProjectHub #1
ProjectHub #2
ProjectHub #3
ProjectHub #4
```

Why?

Because traffic is high.

Now imagine:

```text
ProjectHub #2 crashes
```

Someone needs to:

1. detect the failure
2. start another container
3. connect it to the network
4. route traffic to it
5. remove the broken container

Doing that manually doesn’t scale.

Kubernetes automates this kind of orchestration.

---

# **2. What is Kubernetes?**

Kubernetes is a platform for managing containerized workloads.

Think of Docker as:

“Run this container.”

Kubernetes as:

“Keep my application running according to this desired state.”

For example:

```text
I want:

3 ProjectHub instances
```

Kubernetes continuously works toward that state.

---

# **3. The basic architecture**

At a very high level:

```text
                    Kubernetes Cluster

                           |
              +------------+------------+
              |                         |
              v                         v

        Control Plane                 Nodes

                                      |
                         +------------+------------+
                         |            |            |
                         v            v            v

                       Pod          Pod          Pod
```

The **control plane** manages the cluster.

The **worker nodes** run workloads.

---

# **4. What is a Pod?**

The smallest deployable unit in Kubernetes is generally a **Pod**.

A Pod contains one or more containers.

For a normal Spring Boot service:

```text
Pod
 |
 +-- Spring Boot Container
```

You usually don’t think:

“Kubernetes runs my Docker container directly.”

You think:

“Kubernetes runs my container inside a Pod.”

---

# **5. Why Pods exist**

A Pod provides a shared environment for its containers.

Containers in the same Pod can share:

- network namespace
- localhost
- storage volumes

But most Spring Boot applications will use:

```text
1 Pod
 |
 +-- 1 application container
```

You don’t need multiple containers in every Pod.

---

# **6. Pods are disposable**

This is extremely important.

Don’t think:

```text
Pod = permanent server
```

Think:

```text
Pod = temporary application instance
```

Example:

```text
Pod A
```

dies.

Kubernetes can create:

```text
Pod B
```

Your application should therefore **not depend on the local Pod’s identity or filesystem for durable state**.

Database data belongs in persistent storage, not inside the application Pod.

---

# **7. Deployment**

Now suppose we want:

```text
3 ProjectHub Pods
```

We create a:

```text
Deployment
```

Conceptually:

```text
Deployment

desired replicas = 3

       |
       v

+------+------+------+
|      |      |      |
v      v      v

Pod   Pod    Pod
```

The Deployment manages the desired number of Pods through ReplicaSets.

---

# **8. Example Deployment**

A simplified Kubernetes manifest:

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
          image: projecthub:1.0
          ports:
            - containerPort: 8080
```

Don’t memorize this yet.

Understand the model.

---

# 

# **9.**

**`replicas: 3`**

This:

```yaml
replicas: 3
```

means:

I want three instances of this workload.

So:

```text
Deployment
    |
    +--- Pod 1
    |
    +--- Pod 2
    |
    +--- Pod 3
```

If one dies:

```text
Pod 1
Pod 2
Pod 3  X
```

Kubernetes can create another:

```text
Pod 1
Pod 2
Pod 4
```

The desired state remains:

```text
3 Pods
```

---

# **10. Labels**

You’ll see this everywhere in Kubernetes.

Example:

```yaml
labels:
  app: projecthub
```

Labels are metadata used to identify and select objects.

Think:

```text
app=projecthub
```

as a tag.

---

# **11. Selectors**

A selector says:

Find objects having these labels.

Example:

```yaml
selector:
  matchLabels:
    app: projecthub
```

Meaning:

```text
Find Pods where:

app = projecthub
```

This is how Kubernetes resources connect to one another.

---

# **12. The problem with Pod IP addresses**

Suppose:

```text
Pod A
IP = 10.0.0.10
```

Then it dies.

New Pod:

```text
Pod B
IP = 10.0.0.25
```

So clients shouldn’t directly depend on:

```text
10.0.0.10
```

We need a stable abstraction.

Enter:

# **Service**

---

# **13. Kubernetes Service**

A Service provides a stable network endpoint for a set of Pods.

Architecture:

```text
              ProjectHub Service

                      |
          +-----------+-----------+
          |           |           |
          v           v           v

        Pod 1       Pod 2       Pod 3
```

Clients talk to the Service.

Not individual Pods.

---

# **14. Example Service**

```yaml
apiVersion: v1
kind: Service

metadata:
  name: projecthub

spec:
  selector:
    app: projecthub

  ports:
    - port: 80
      targetPort: 8080
```

Now:

```text
projecthub:80
```

can route to:

```text
Pod:8080
```

---

# **15. Service discovery**

Suppose we have:

```text
project-service
notification-service
```

Inside Kubernetes, services can communicate using stable service names.

Conceptually:

```text
Project Service

    |
    v

notification-service
```

Instead of remembering changing Pod IPs.

---

# **16. The complete flow**

Now:

```text
                    Client
                       |
                       v
                Load Balancer
                       |
                       v
                Kubernetes Service
                       |
             +---------+---------+
             |         |         |
             v         v         v
           Pod 1     Pod 2     Pod 3
             |         |         |
             +---------+---------+
                       |
                       v
                 Spring Boot
```

---

# **17. Kubernetes Services have different purposes**

You’ll commonly encounter:

### **ClusterIP**

Internal access.

```text
Service
   |
   v
inside cluster
```

Good for:

```text
Project Service
    ↓
Notification Service
```

---

### **NodePort**

Exposes a service through a node port.

Useful for some scenarios, but generally not how you’d design a polished public production entry point.

---

### **LoadBalancer**

Requests an external load balancer from the environment/cloud integration.

Conceptually:

```text
Internet
   |
   v
Load Balancer
   |
   v
Kubernetes Service
```

---

# **18. Ingress**

For HTTP applications, you may also use an Ingress mechanism.

Conceptually:

```text
                    Internet

                       |
                       v

                    Ingress

                /             \

               /               \

              v                 v

       project.example     auth.example

              |                 |

              v                 v

       Project Service     Auth Service
```

The important idea:

One HTTP entry point can route traffic to different services.

---

# **19. Kubernetes health checks**

This connects directly to our observability lesson.

Kubernetes needs to know:

Is this Pod healthy?

Spring Boot has built-in support for liveness and readiness states, and Actuator exposes dedicated health endpoints such as `/actuator/health/liveness` and `/actuator/health/readiness`.  

---

# **20. Liveness probe**

Liveness asks:

Is this application alive enough that restarting it may help?

If liveness fails repeatedly, Kubernetes can restart the container.

Example:

```yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
```

---

# **21. Readiness probe**

Readiness asks:

Should this Pod receive traffic right now?

This is different.

Imagine:

```text
Pod starts
   |
   v
Spring Boot starting
   |
   v
Database initialization
   |
   v
Application ready
```

Before it’s ready:

```text
Traffic → ❌
```

After:

```text
Traffic → ✅
```

This prevents Kubernetes from sending requests to an application that isn’t ready yet.

---

# **22. Don’t confuse liveness and readiness**

This is a common interview question.

### **Liveness**

```text
Should Kubernetes restart me?
```

### **Readiness**

```text
Should Kubernetes send traffic to me?
```

Spring Boot explicitly distinguishes these application availability states.  

---

# **23. Configuration**

You shouldn’t put environment-specific configuration directly into the image.

Example:

```text
Production DB
Staging DB
Development DB
```

The same application image should ideally be deployable into different environments with different configuration.

Kubernetes provides:

```text
ConfigMap
Secret
```

---

# **24. ConfigMap**

For non-sensitive configuration.

Example:

```yaml
apiVersion: v1
kind: ConfigMap

metadata:
  name: projecthub-config

data:
  SPRING_PROFILES_ACTIVE: "prod"
  APP_JWT_ISSUER: "projecthub"
```

---

# **25. Secret**

For sensitive values.

Example:

```yaml
apiVersion: v1
kind: Secret

metadata:
  name: projecthub-secrets

stringData:
  DB_USERNAME: projecthub
  DB_PASSWORD: some-password
```

But important:

Kubernetes Secrets are not automatically equivalent to a dedicated production secret-management system.

They are Kubernetes resources for sensitive configuration; production environments may additionally integrate external secret managers.

---

# **26. Resource requests and limits**

A container needs resources.

Example:

```yaml
resources:

  requests:
    cpu: "250m"
    memory: "512Mi"

  limits:
    cpu: "1"
    memory: "1Gi"
```

Think:

```text
requests = resources the scheduler should reserve for the Pod

limits = upper boundary for container resource usage
```

This becomes important for scheduling and autoscaling.

---

# **27. Horizontal scaling**

Suppose traffic increases:

```text
10 requests/sec
```

Then:

```text
1,000 requests/sec
```

We might need more Pods.

Manually:

```bash
kubectl scale deployment projecthub --replicas=10
```

Now:

```text
ProjectHub

+--- Pod
+--- Pod
+--- Pod
+--- Pod
+--- Pod
+--- ...
```

---

# **28. Horizontal Pod Autoscaler**

Kubernetes has:

```text
HorizontalPodAutoscaler
```

It can automatically adjust the number of Pods based on observed metrics such as CPU, memory, or custom metrics.  

Conceptually:

```text
Low traffic

3 Pods
```

then:

```text
High traffic

10 Pods
```

then:

```text
Traffic falls

4 Pods
```

---

# **29. Example HPA**

A simplified modern HPA uses:

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

The important part:

```text
minimum = 3

maximum = 10

target CPU = 60%
```

---

# **30. Rolling deployments**

Suppose production currently runs:

```text
ProjectHub 1.0

Pod 1
Pod 2
Pod 3
```

You build:

```text
ProjectHub 1.1
```

You don’t want:

```text
STOP EVERYTHING

install 1.1

START EVERYTHING
```

That causes downtime.

Instead:

```text
1.0  1.0  1.0

 ↓

1.1  1.0  1.0

 ↓

1.1  1.1  1.0

 ↓

1.1  1.1  1.1
```

That’s a rolling update.

Kubernetes Deployments use `RollingUpdate` by default and gradually replace old Pods with new ones.  

---

# **31. Rollback**

What if version 1.1 is broken?

Kubernetes can roll back to a previous Deployment revision.

Conceptually:

```text
1.0 → 1.1

1.1 broken

      ↓

rollback

      ↓

1.0
```

That’s one of the reasons Deployments are so useful.

---

# **32. Spring Boot + Kubernetes**

Our ProjectHub application now looks like:

```text
                         Internet
                            |
                            v
                       Load Balancer
                            |
                            v
                         Ingress
                            |
                            v
                    ProjectHub Service
                            |
             +--------------+--------------+
             |              |              |
             v              v              v
           Pod 1          Pod 2          Pod 3
             |              |              |
             +--------------+--------------+
                            |
                            v
                         Redis
                            |
                            v
                       PostgreSQL
```

And separately:

```text
Project Service
      |
      v
RabbitMQ
      |
      v
Notification Service
```

---

# **33. Very important architecture rule**

Don’t put your PostgreSQL database inside ordinary application Pods just because Kubernetes can run containers.

Your application is usually stateless:

```text
Pod 1
Pod 2
Pod 3
```

The database has very different requirements:

```text
durability
storage
backup
replication
failover
```

In production, databases are commonly managed separately or through dedicated stateful infrastructure.

---

# **34. Kubernetes does NOT replace everything**

A common beginner misconception:

“Kubernetes is a database.”

No.

Kubernetes manages workloads.

It doesn’t magically make:

```text
PostgreSQL
Redis
Kafka
```

safe, durable, and correctly configured.

Those systems still need their own architecture.

---

# **35. What Kubernetes actually gives us**

Think:

```text
Docker
  ↓
Container

Kubernetes
  ↓
Orchestration
```

Kubernetes helps with:

✅ scheduling  
✅ restarting failed workloads  
✅ service discovery  
✅ rolling deployments  
✅ scaling  
✅ health checks  
✅ configuration  
✅ traffic routing

---

# **36. ProjectHub production architecture**

We’re getting somewhere serious now:

```text
                         INTERNET
                            |
                            v
                     Load Balancer
                            |
                            v
                         Ingress
                            |
                            v
                    +-------+-------+
                    |               |
                    v               v
              Auth Service    Project Service
                    |               |
                 Pods x3          Pods x5
                                    |
                         +----------+----------+
                         |                     |
                         v                     v
                       Redis              PostgreSQL
                                             |
                                             v
                                           Backup

Project Service
       |
       v
   RabbitMQ
       |
       +--------> Notification Service
       |
       +--------> Analytics Service

All services
       |
       +----> Logs
       +----> Metrics
       +----> Traces
```

That is starting to look like a real production platform.

---

# **37. One final mental model**

Remember this hierarchy:

```text
Container
   ↓
Pod
   ↓
Deployment
   ↓
Service
   ↓
Ingress / Load Balancer
```

And:

```text
Deployment
   ↓
replicas
   ↓
Pods
```

And:

```text
HPA
   ↓
changes replicas
   ↓
Deployment
```

And:

```text
Readiness
   ↓
controls whether traffic should reach Pod
```

This mental model is more important than memorizing YAML.

---

# **Lesson 48 Summary**

You’ve learned:

✅ Why Kubernetes exists  
✅ Cluster/control plane/nodes  
✅ Pods  
✅ Deployments  
✅ Replica counts  
✅ Labels/selectors  
✅ Services  
✅ Service discovery  
✅ Ingress concept  
✅ Liveness probes  
✅ Readiness probes  
✅ ConfigMaps  
✅ Secrets  
✅ Resource requests/limits  
✅ Horizontal scaling  
✅ HPA  
✅ Rolling updates  
✅ Rollbacks  
✅ Stateless application architecture

Spring Boot has built-in support for Kubernetes-oriented liveness/readiness availability states, and Actuator exposes them for probes.  

Spring Boot also supports container images through Dockerfiles or Cloud Native Buildpacks, so the container image we created in the previous lesson can become the artifact Kubernetes deploys.  

---

# **Exercise 48**

Don’t write Kubernetes YAML yet. First make sure the architecture is clear.

### **1.**

What’s the difference between:

```text
Pod
```

and:

```text
Deployment
```

---

### **2.**

Why shouldn’t clients communicate directly with Pod IPs?

---

### **3.**

What’s the difference between:

```text
Liveness
```

and:

```text
Readiness
```

---

### **4.**

Suppose ProjectHub has:

```text
3 Pods
```

and one crashes.

What should happen?

---

### **5.**

Traffic suddenly increases from:

```text
100 requests/sec
```

to:

```text
10,000 requests/sec
```

What Kubernetes component could automatically increase the number of ProjectHub Pods?

---

### **6. Architecture challenge**

Complete this:

```text
Internet
   |
   v
   ?
   |
   v
ProjectHub Service
   |
   +--------+--------+
   |        |        |
   v        v        v
  Pod      Pod      Pod
```

What should `?` be, and why?

---

## **Next: Lesson 49 — CI/CD**

Now that we have:

```text
Spring Boot
Docker
Kubernetes
```

the next question is:

How does new code automatically get from Git to production?

We’ll build the pipeline:

```text
Developer
   |
   v
Git
   |
   v
CI Pipeline
   |
   +--> Compile
   +--> Test
   +--> Security checks
   |
   v
Docker Image
   |
   v
Container Registry
   |
   v
Kubernetes
   |
   v
Production
```

That’s where we’ll connect **software development → testing → Docker → Kubernetes → deployment**.