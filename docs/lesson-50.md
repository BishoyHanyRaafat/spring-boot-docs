---
title: Lesson 50: Kubernetes in Practice Deploying ProjectHub
sidebar_position: 50
---

We’ve learned what Kubernetes concepts mean. Now we’re going to actually connect them.

Our goal is to take:

```text
ProjectHub Docker image
        ↓
Kubernetes Deployment
        ↓
Kubernetes Service
        ↓
ProjectHub Pods
```

A Kubernetes `Deployment` manages Pods/ReplicaSets and supports declarative updates; a `Service` gives a stable network endpoint for a changing set of Pods.  

---

# **1. The ProjectHub Kubernetes directory**

Let’s imagine:

```text
projecthub/
├── src/
├── pom.xml
├── Dockerfile
└── k8s/
    ├── deployment.yaml
    ├── service.yaml
    ├── configmap.yaml
    └── secret.yaml
```

Eventually we’ll also have things like:

```text
k8s/
├── deployment.yaml
├── service.yaml
├── configmap.yaml
├── secret.yaml
├── ingress.yaml
└── hpa.yaml
```

We’ll build these one at a time.

---

# **2. First: the Deployment**

Here’s our first real Deployment:

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
          image: projecthub:1.0.0

          ports:
            - containerPort: 8080
```

Don’t memorize this yet.

Let’s understand every part.

---

# 

# **3.**

**`apiVersion`**

```yaml
apiVersion: apps/v1
```

This tells Kubernetes which API version describes the object.

For a Deployment, `apps/v1` is the current stable API used in Kubernetes.  

---

# 

# **4.**

**`kind`**

```yaml
kind: Deployment
```

We’re saying:

“I want this Kubernetes object to be a Deployment.”

Kubernetes has many kinds:

```text
Deployment
Service
ConfigMap
Secret
Job
CronJob
Ingress
HorizontalPodAutoscaler
...
```

---

# 

# **5.**

**`metadata`**

```yaml
metadata:
  name: projecthub
```

This gives the object its name.

So Kubernetes knows it as:

```text
Deployment/projecthub
```

You can inspect it with:

```bash
kubectl get deployment projecthub
```

---

# 

# **6.**

**`replicas`**

```yaml
replicas: 3
```

We want:

```text
Pod 1
Pod 2
Pod 3
```

Why three?

Because one Pod isn’t a particularly good production availability strategy.

If one dies:

```text
Pod 1 ❌

Pod 2 ✅
Pod 3 ✅
```

The Deployment controller tries to maintain the desired number.

---

# **7. The selector**

Here’s one of the most important parts:

```yaml
selector:
  matchLabels:
    app: projecthub
```

We’re telling the Deployment:

“These are the Pods belonging to me.”

---

# **8. The Pod template**

Now:

```yaml
template:
  metadata:
    labels:
      app: projecthub
```

Notice:

```text
selector:
  app: projecthub
```

matches:

```text
labels:
  app: projecthub
```

That’s intentional.

Think:

```text
Deployment
    |
    | selector: app=projecthub
    |
    v
Pods
    |
    +-- label app=projecthub
    +-- label app=projecthub
    +-- label app=projecthub
```

Labels and selectors are fundamental to connecting Kubernetes resources.

---

# **9. The container**

Inside the Pod:

```yaml
containers:
  - name: projecthub
    image: projecthub:1.0.0
```

This means:

Start the ProjectHub container using this image.

The image might eventually be:

```text
ghcr.io/my-company/projecthub:abc123
```

rather than the simple local name.

---

# 

# **10.**

**`containerPort`**

```yaml
ports:
  - containerPort: 8080
```

Our Spring Boot application listens on:

```text
8080
```

So we document that the container exposes port 8080.

Important:

`containerPort` **doesn’t by itself make the application publicly accessible**.

That’s what the Service is for.

---

# **11. Deployment architecture so far**

We have:

```text
Deployment
    |
    +---- Pod
    |      └── ProjectHub container
    |
    +---- Pod
    |      └── ProjectHub container
    |
    +---- Pod
           └── ProjectHub container
```

But how does traffic reach these Pods?

Enter the Service.

---

# **12. ProjectHub Service**

Create:

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

A Service with no explicit type defaults to `ClusterIP`, which gives it a cluster-internal endpoint. It selects Pods using its selector.  

---

# 

# 

# **13.**

**`selector`**

**again**

We have:

```yaml
selector:
  app: projecthub
```

The Service searches for Pods with:

```yaml
labels:
  app: projecthub
```

So:

```text
Service
   |
   | selector
   v
app=projecthub
   |
   +---- Pod 1
   |
   +---- Pod 2
   |
   +---- Pod 3
```

The Pods can change over time.

The Service remains stable.

That’s one of its most important jobs.  

---

# 

# 

# 

# **14.**

**`port`**

**vs**

**`targetPort`**

This confuses almost everyone initially.

We have:

```yaml
ports:
  - port: 80
    targetPort: 8080
```

Think:

```text
Service
port 80
   |
   v
Pod
port 8080
```

So clients connect to:

```text
projecthub:80
```

and Kubernetes routes to:

```text
Pod:8080
```

---

# **15. Why not connect directly to Pod IPs?**

Suppose:

```text
Pod A
10.0.0.17

Pod B
10.0.0.21

Pod C
10.0.0.33
```

Tomorrow Kubernetes replaces them:

```text
Pod D
10.0.0.42

Pod E
10.0.0.51

Pod F
10.0.0.67
```

Pod IPs are not your application’s stable identity.

The Service provides that stable abstraction and tracks matching endpoints.  

---

# **16. Inside the cluster**

Other applications can communicate with:

```text
projecthub
```

using Kubernetes DNS.

For example:

```text
http://projecthub
```

or, across namespaces:

```text
http://projecthub.production
```

Kubernetes provides DNS-based Service discovery for Pods.  

---

# **17. Now configuration**

Our application shouldn’t have:

```yaml
spring:
  datasource:
    password: actual-production-password
```

inside the Deployment.

We want configuration separated from the application image.

That’s where `ConfigMap` comes in.

---

# **18. ConfigMap**

Example:

```yaml
apiVersion: v1
kind: ConfigMap

metadata:
  name: projecthub-config

data:
  SPRING_PROFILES_ACTIVE: "kubernetes"
  DB_URL: "jdbc:postgresql://postgres:5432/projecthub"
```

A ConfigMap is appropriate for **non-secret configuration**.

For example:

```text
application profile
database hostname
feature flags
log levels
```

Not:

```text
password
JWT private key
API secret
```

---

# **19. Secret**

For sensitive values:

```yaml
apiVersion: v1
kind: Secret

metadata:
  name: projecthub-secret

type: Opaque

stringData:
  DB_USERNAME: projecthub
  DB_PASSWORD: change-me
```

For learning, we’re showing the values directly.

In a real production cluster, you should think carefully about how secrets are provisioned and protected rather than treating a committed YAML file as a secure secret-management solution.

---

# **20. Connecting configuration to the Pod**

Now we modify our Deployment:

```yaml
containers:
  - name: projecthub
    image: projecthub:1.0.0

    envFrom:
      - configMapRef:
          name: projecthub-config

      - secretRef:
          name: projecthub-secret
```

Now Kubernetes injects those values as environment variables.

So the container receives something conceptually like:

```text
SPRING_PROFILES_ACTIVE=kubernetes
DB_URL=jdbc:postgresql://postgres:5432/projecthub
DB_USERNAME=projecthub
DB_PASSWORD=...
```

And Spring Boot can consume them through its external configuration system.

---

# **21. Complete Deployment**

Putting it together:

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
          image: projecthub:1.0.0

          ports:
            - containerPort: 8080

          envFrom:
            - configMapRef:
                name: projecthub-config

            - secretRef:
                name: projecthub-secret
```

That’s a legitimate starting point.

But production needs more.

---

# **22. Resource requests and limits**

Remember when we discussed Kubernetes scheduling?

We should tell Kubernetes how much CPU/memory the application expects.

For example:

```yaml
resources:
  requests:
    cpu: "250m"
    memory: "512Mi"

  limits:
    cpu: "1"
    memory: "1Gi"
```

Meaning approximately:

```text
Request:
CPU    0.25 core
Memory 512 MiB
```

and:

```text
Limit:
CPU    1 core
Memory 1 GiB
```

Requests help Kubernetes make scheduling decisions.

This becomes especially important when we introduce HPA.

---

# **23. Health checks**

Our Spring Boot application already has Actuator.

We can expose Kubernetes-oriented health endpoints such as:

```text
/actuator/health/liveness
/actuator/health/readiness
```

Spring Boot provides liveness and readiness health groups for this purpose.  

Now Kubernetes can ask:

```text
"Are you alive?"
```

and:

```text
"Are you ready for traffic?"
```

---

# **24. Liveness probe**

Example:

```yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  initialDelaySeconds: 30
  periodSeconds: 10
```

Conceptually:

```text
Kubernetes
    |
    | Are you alive?
    v
Spring Boot
    |
    +---- YES → continue
    |
    +---- NO → restart may occur
```

Liveness should generally answer whether the application itself is functioning, not whether every external dependency is available. Spring Boot specifically cautions against making liveness dependent on external systems.  

---

# **25. Readiness probe**

```yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  initialDelaySeconds: 30
  periodSeconds: 10
```

Conceptually:

```text
Kubernetes
    |
    | Can I send traffic?
    v
Spring Boot
    |
    +---- YES → Service may route traffic
    |
    +---- NO  → don't send traffic here
```

This is extremely important during deployments.

---

# **26. Why readiness matters during a rollout**

Suppose Kubernetes creates:

```text
Pod 4
```

The application is still starting:

```text
Spring Boot
    |
    +-- loading
    +-- connecting
    +-- initializing
```

Readiness:

```text
❌ NOT READY
```

So traffic stays away.

Then:

```text
Application started
       |
       v
READY
```

Now it can receive traffic.

This helps make rolling deployments much safer.

---

# **27. A more realistic Deployment**

Now our Deployment becomes:

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
          image: projecthub:1.0.0

          ports:
            - containerPort: 8080

          envFrom:
            - configMapRef:
                name: projecthub-config

            - secretRef:
                name: projecthub-secret

          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              cpu: "1"
              memory: "1Gi"

          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            initialDelaySeconds: 30
            periodSeconds: 10

          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            initialDelaySeconds: 30
            periodSeconds: 10
```

Don’t worry about memorizing this.

Understand the responsibilities:

```text
Deployment
 ├── number of Pods
 ├── image
 ├── configuration
 ├── resources
 └── health
```

---

# **28. Complete Service**

Our Service remains simple:

```yaml
apiVersion: v1
kind: Service

metadata:
  name: projecthub

spec:
  selector:
    app: projecthub

  ports:
    - name: http
      port: 80
      targetPort: 8080
```

Now:

```text
                 Service
              projecthub:80
                    |
        +-----------+-----------+
        |           |           |
        v           v           v
      Pod 1       Pod 2       Pod 3
       :8080       :8080       :8080
```

---

# **29. Applying the manifests**

Once we have:

```text
configmap.yaml
secret.yaml
deployment.yaml
service.yaml
```

we can apply them:

```bash
kubectl apply -f k8s/
```

Then inspect:

```bash
kubectl get pods
```

You might see:

```text
NAME                          READY   STATUS
projecthub-7f8...             1/1     Running
projecthub-7f8...             1/1     Running
projecthub-7f8...             1/1     Running
```

---

# **30. Inspect the Deployment**

```bash
kubectl get deployment projecthub
```

Something like:

```text
NAME         READY   UP-TO-DATE   AVAILABLE
projecthub   3/3     3            3
```

Meaning Kubernetes currently has the desired three replicas available.

---

# **31. Inspect the Service**

```bash
kubectl get service projecthub
```

You might see:

```text
NAME         TYPE        CLUSTER-IP      PORT(S)
projecthub   ClusterIP   10.x.x.x        80/TCP
```

That Service is internal to the cluster because `ClusterIP` is the default Service type.  

---

# **32. But how does the Internet reach ProjectHub?**

Currently:

```text
Internet
   X
   |
ProjectHub Service
```

Our Service is internal.

We eventually need something like:

```text
Internet
   |
   v
Load Balancer
   |
   v
Ingress / Gateway
   |
   v
ProjectHub Service
   |
   v
Pods
```

We’ll tackle external HTTP routing separately.

---

# **33. The complete mental model**

This is the important part:

```text
                   Kubernetes
                       |
                 Deployment
                       |
             desired replicas = 3
                       |
          +------------+------------+
          |            |            |
          v            v            v
        Pod          Pod          Pod
          |            |            |
       Spring       Spring       Spring
        Boot         Boot         Boot
          \            |            /
           \           |           /
            +----------+----------+
                       |
                    Service
                       |
                       v
                  stable endpoint
```

The Deployment manages **workload state**.

The Pods run **containers**.

The Service provides **stable networking**.

---

# **34. And where does CI/CD fit?**

Now connect Lesson 49:

```text
Developer
    |
    v
Git
    |
    v
CI
    |
    +-- compile
    +-- test
    +-- security
    |
    v
Docker image
    |
    v
Container Registry
    |
    v
Kubernetes Deployment
    |
    v
Pods
    |
    v
Service
    |
    v
Users
```

That’s the complete software delivery chain.

---

# **35. One important production correction**

Our example says:

```yaml
image: projecthub:1.0.0
```

In a real cluster, Kubernetes usually needs to pull the image from a registry, for example conceptually:

```yaml
image: registry.example.com/projecthub:1.0.0
```

And our CI/CD system is responsible for building and publishing that image.

So:

```text
CI
 |
 | build
 v
projecthub:abc123
 |
 | push
 v
Registry
 |
 | pull
 v
Kubernetes
```

This connects Docker, CI/CD and Kubernetes into one system.

---

# **36. Where PostgreSQL fits**

One more architectural point.

Don’t think:

```text
Kubernetes
  ├── ProjectHub
  └── PostgreSQL Pod
```

is automatically the production architecture.

PostgreSQL is stateful.

Our application Pods are deliberately disposable:

```text
Pod
  ↓
destroy
  ↓
new Pod
```

Database durability, backups, replication, failover and storage require a different operational model.

For ProjectHub, we’ll treat PostgreSQL as a separate managed/stateful infrastructure component for now.

Same general idea applies to Redis and messaging infrastructure.

---

# **Lesson 50 Summary**

You now understand how to create the core Kubernetes resources for ProjectHub:

### **Deployment**

Controls:

- replicas
- Pods
- container image
- resources
- configuration
- health probes

### **Service**

Provides:

- stable networking
- Pod discovery
- traffic routing

### **ConfigMap**

Stores:

- non-secret configuration

### **Secret**

Stores:

- sensitive configuration

### **Probes**

```text
Liveness  → should I restart you?
Readiness → should I send traffic?
```

And the architecture is:

```text
                 Internet
                    |
               Load Balancer
                    |
             Ingress / Gateway
                    |
             ProjectHub Service
                    |
        +-----------+-----------+
        |           |           |
       Pod         Pod         Pod
        |           |           |
     Spring      Spring      Spring
      Boot        Boot        Boot
        \           |           /
         +----------+----------+
                    |
          +---------+---------+
          |                   |
       PostgreSQL           Redis
                              |
                           RabbitMQ
```

Kubernetes Services intentionally decouple clients from ephemeral Pod IPs, while Deployments manage the desired set of Pods.  

---

# **Exercise 50**

Don’t copy the manifests yet. Try to reason through them.

### **1.**

Why does this need to match?

```yaml
selector:
  matchLabels:
    app: projecthub
```

and:

```yaml
labels:
  app: projecthub
```

---

### **2.**

Explain the difference:

```yaml
port: 80
targetPort: 8080
```

---

### **3.**

A ProjectHub Pod crashes.

Who is responsible for recreating it?

```text
Pod
Service
Deployment
Ingress
```

---

### **4.**

A new Pod starts but Spring Boot is still initializing.

Should it receive user traffic?

Which probe determines this?

---

### **5.**

Why is this a bad idea?

```yaml
livenessProbe:
  httpGet:
    path: /database-health
```

where `/database-health` fails whenever PostgreSQL has a temporary outage.

Think carefully about **liveness vs readiness**.

---

### **6. Architecture challenge**

Fill this in:

```text
Internet
   |
   v
   ???
   |
   v
ProjectHub Service
   |
   +---- Pod
   +---- Pod
   +---- Pod
```

Then explain why we don’t have the Internet connect directly to one Pod.

**Next: Lesson 51 — Ingress & Gateway: getting real HTTP/HTTPS traffic into Kubernetes, domains, TLS, routing, and how** **`api.projecthub.com`** **reaches the correct Spring Boot Service.**