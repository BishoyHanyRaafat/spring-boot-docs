---
title: Lesson 51: Ingress & Gateway Getting Real HTTP Traffic into Kubernetes
sidebar_position: 51
---

Now we’re going to solve the missing piece from Lesson 50:

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

That `???` is where **Ingress/Gateway** comes in.

One important current Kubernetes detail: the Kubernetes project now recommends **Gateway API** for new work; the older Ingress API is stable but frozen.  

So we’ll learn both concepts, but use **Gateway API** as the modern direction.

---

# **1. What problem are we solving?**

Our ProjectHub Service currently looks like:

```text
ProjectHub Service
       |
       +---- Pod
       +---- Pod
       +---- Pod
```

But the Service is normally internal to the cluster.

A user on the Internet wants:

```text
https://api.projecthub.com/posts
```

We need to transform:

```text
Internet request
       ↓
api.projecthub.com
       ↓
Kubernetes
       ↓
ProjectHub Service
       ↓
Spring Boot Pod
```

---

# **2. DNS comes first**

Suppose we own:

```text
projecthub.com
```

We create:

```text
api.projecthub.com
```

DNS resolves that hostname to the public address of our Kubernetes gateway/load balancer.

Conceptually:

```text
api.projecthub.com
        |
        v
     DNS
        |
        v
Public IP
        |
        v
Kubernetes Gateway
```

DNS itself doesn’t know about your Pods.

It simply gets the client to the appropriate public entry point.

---

# **3. Gateway vs Service**

This distinction is critical.

### **Service**

Handles traffic **inside the Kubernetes networking model**:

```text
Service
   ↓
Pods
```

### **Gateway**

Handles traffic entering the cluster:

```text
Internet
   ↓
Gateway
   ↓
Service
   ↓
Pods
```

So:

```text
Gateway = external traffic entry/routing

Service = stable backend endpoint
```

---

# **4. Gateway API**

Gateway API defines resources such as:

```text
GatewayClass
Gateway
HTTPRoute
GRPCRoute
TLSRoute
```

`HTTPRoute` is used to route HTTP requests to Kubernetes Services based on things such as hostname and path.  

The conceptual hierarchy is:

```text
GatewayClass
      ↓
   Gateway
      ↓
  HTTPRoute
      ↓
   Service
      ↓
     Pods
```

---

# **5. GatewayClass**

A `GatewayClass` identifies the implementation that actually provides the Gateway.

Think:

```text
GatewayClass
    |
    v
"Which gateway/controller handles this?"
```

This is infrastructure-level configuration.

For example, a cloud provider or Gateway controller can implement it.

The exact `GatewayClass` name depends on the Gateway implementation you’re using.

That’s important:

Don’t blindly copy a `gatewayClassName` from an example and expect it to work in every cluster.

---

# **6. Gateway**

Conceptually:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway

metadata:
  name: projecthub-gateway

spec:
  gatewayClassName: example-gateway-class

  listeners:
    - name: https
      protocol: HTTPS
      port: 443
```

This says roughly:

“I want a gateway listening for HTTPS traffic.”

The actual controller behind the `GatewayClass` provisions/configures the networking infrastructure.

---

# **7. Why do we need a Gateway controller?**

This is an important Kubernetes concept.

Kubernetes API objects describe **desired state**.

Something needs to implement that desired state.

For Gateway API, you install/use a Gateway controller. The official Gateway API documentation describes Gateway API as specifications implemented by a wide range of controllers rather than something that provides the actual data plane by itself.  

So:

```text
Gateway YAML
     |
     v
Gateway Controller
     |
     v
Actual networking infrastructure
```

---

# **8. HTTPRoute**

Now comes the interesting part.

We want:

```text
api.projecthub.com
```

to go to:

```text
projecthub Service
```

We can express that with an `HTTPRoute`.

For example:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute

metadata:
  name: projecthub-route

spec:
  parentRefs:
    - name: projecthub-gateway

  hostnames:
    - api.projecthub.com

  rules:
    - backendRefs:
        - name: projecthub
          port: 80
```

Conceptually:

```text
Host:
api.projecthub.com

        ↓

Service:
projecthub:80
```

`HTTPRoute` supports hostname, path, header and other HTTP-level matching.  

---

# **9. The complete request**

A user requests:

```text
GET https://api.projecthub.com/posts
```

Here’s what happens:

```text
                    Internet
                       |
                       v
               api.projecthub.com
                       |
                       v
                      DNS
                       |
                       v
               Public Gateway
                       |
                       v
                  HTTPRoute
                       |
                       v
              ProjectHub Service
                       |
            +----------+----------+
            |          |          |
            v          v          v
          Pod 1      Pod 2      Pod 3
            |          |          |
            +----------+----------+
                       |
                       v
                Spring Boot
```

That is the architecture we’re building.

---

# **10. Host-based routing**

Here’s where Gateway becomes powerful.

Imagine ProjectHub has:

```text
api.projecthub.com
admin.projecthub.com
```

We could route:

```text
api.projecthub.com
        ↓
ProjectHub API Service
```

and:

```text
admin.projecthub.com
        ↓
Admin Service
```

Same Kubernetes cluster.

Different backend Services.

```text
                     Gateway
                        |
          +-------------+-------------+
          |                           |
          v                           v
api.projecthub.com          admin.projecthub.com
          |                           |
          v                           v
 ProjectHub API               Admin Service
```

Gateway API is specifically designed to support this kind of routing.  

---

# **11. Path-based routing**

We can also route based on paths.

For example:

```text
api.projecthub.com/api/*
        ↓
ProjectHub API
```

while:

```text
api.projecthub.com/notifications/*
        ↓
Notification Service
```

Conceptually:

```text
Request
  |
  +-- /api/* ------------> projecthub
  |
  +-- /notifications/* --> notifications
```

This is one reason Gateway/HTTP routing is more than simply “open a port.”

It becomes a traffic-routing layer.

---

# **12. HTTPS and TLS**

Now we need security.

We don’t want:

```text
http://api.projecthub.com
```

We want:

```text
https://api.projecthub.com
```

HTTPS uses TLS.

The Gateway can terminate TLS:

```text
Client
  |
  | HTTPS
  v
Gateway
  |
  | HTTP
  v
Service
```

The encrypted connection ends at the Gateway.

Gateway API defines TLS configuration on Gateway listeners, including HTTPS listeners with certificate references.  

---

# **13. TLS certificate**

Conceptually:

```yaml
listeners:
  - name: https
    protocol: HTTPS
    port: 443

    tls:
      mode: Terminate

      certificateRefs:
        - name: projecthub-tls
```

The certificate might be stored in a Kubernetes Secret:

```text
projecthub-tls
```

Conceptually:

```text
Secret
  |
  +-- TLS certificate
  +-- private key
```

The Gateway uses that certificate for HTTPS.

---

# **14. TLS termination**

Suppose Alice visits:

```text
https://api.projecthub.com/posts
```

The connection looks like:

```text
Alice
  |
  | encrypted HTTPS
  v
Gateway
  |
  | HTTP
  v
ProjectHub Service
  |
  v
Pod
```

This is called **TLS termination** at the Gateway.

---

# **15. Is HTTP between Gateway and Pod always okay?**

Not necessarily.

You might want:

```text
Client
   |
 HTTPS
   |
Gateway
   |
 HTTPS
   |
Service
   |
 HTTPS
   |
Pod
```

That’s encryption on both sides.

Gateway API supports configuration for TLS connections to backends as well; `BackendTLSPolicy` is the Gateway API mechanism for describing backend TLS settings.  

Whether you need this depends on your security architecture.

---

# **16. HTTP → HTTPS redirect**

Often you want:

```text
http://api.projecthub.com
```

to become:

```text
https://api.projecthub.com
```

Gateway API supports configuring HTTP and HTTPS listeners and redirecting HTTP traffic to HTTPS.  

Conceptually:

```text
HTTP :80
   |
   v
301/308 redirect
   |
   v
HTTPS :443
```

---

# **17. Gateway vs old Ingress**

You will still see examples like:

```yaml
kind: Ingress
```

Don’t panic.

Ingress is not obsolete in the sense of “it stopped working.”

It is a stable Kubernetes API.

But Kubernetes explicitly says the Ingress API is frozen and recommends Gateway instead for new development.  

So our learning direction is:

```text
Old/common:
Ingress

Modern Kubernetes direction:
Gateway API
```

You’ll still encounter Ingress extensively in existing projects.

---

# **18. Why Gateway API was introduced**

One of its important design goals is separation of responsibilities.

For example:

```text
Infrastructure team
        |
        v
   GatewayClass
```

Then:

```text
Platform team
        |
        v
      Gateway
```

Then:

```text
Application team
        |
        v
    HTTPRoute
```

Gateway API explicitly describes this role-oriented model.  

That’s useful in larger organizations.

---

# **19. ProjectHub example**

Imagine our company has one Kubernetes cluster.

We run:

```text
ProjectHub
Notification Service
Analytics Service
Admin Service
```

The Gateway might look conceptually like:

```text
                         Gateway
                            |
          +-----------------+-----------------+
          |                 |                 |
          v                 v                 v
    api.projecthub     admin.projecthub   events.projecthub
          |                 |                 |
          v                 v                 v
     API Service       Admin Service     Event Service
          |                 |                 |
         Pods              Pods              Pods
```

This is much cleaner than exposing every individual Pod or Service directly to the Internet.

---

# **20. Authentication still belongs to Spring Security**

Very important:

Gateway routing doesn’t replace our Spring Security architecture.

The flow remains:

```text
Internet
   |
Gateway
   |
ProjectHub Service
   |
Spring Security
   |
JWT validation
   |
Authorization
   |
Controller
   |
Service
```

The Gateway might perform infrastructure-level tasks such as:

```text
TLS
routing
load balancing
```

while ProjectHub still performs:

```text
authentication
authorization
business rules
resource ownership
```

For example:

```java
@PreAuthorize("hasAuthority('posts.delete')")
```

still belongs inside the application.

---

# **21. Gateway isn’t your authorization system**

Suppose:

```text
DELETE /posts/42
```

Gateway determines:

```text
"This request belongs to ProjectHub."
```

Spring Security determines:

```text
"Does this authenticated user have posts.delete?"
```

Then our policy determines:

```text
"Does this user own post 42 or have the appropriate project role?"
```

So:

```text
Gateway
   ↓
Routing

Spring Security
   ↓
Authentication / authorization

Application policy
   ↓
Resource-level authorization
```

Don’t collapse those responsibilities.

---

# **22. Rate limiting**

At some point you may also want:

```text
Client
   |
Gateway
   |
Rate limit
   |
ProjectHub
```

For example:

```text
100 requests / minute
```

But this gets into implementation-specific Gateway/controller features.

The important architectural idea is:

Traffic management can happen at the edge before requests reach the application.

Meanwhile, application-level security still remains necessary.

---

# **23. Observability at the Gateway**

Now our observability architecture gets bigger.

We can observe:

```text
Client
  |
Gateway
  |
Service
  |
Spring Boot
```

We may collect:

```text
request count
latency
status codes
TLS errors
routing errors
application errors
```

Then correlate them with our existing:

```text
logs
metrics
traces
```

This is where the observability lessons become useful.

---

# **24. The entire ProjectHub network**

We’re now approaching the production architecture:

```text
                         Internet
                            |
                            v
                          DNS
                            |
                            v
                    Load Balancer/Gateway
                            |
                  +---------+---------+
                  |                   |
                  v                   v
             HTTPRoute             HTTPRoute
                  |                   |
                  v                   v
           ProjectHub API       Admin Service
                  |
                  v
             Service
                  |
        +---------+---------+
        |         |         |
        v         v         v
      Pod       Pod       Pod
        |         |         |
        +---------+---------+
                  |
          +-------+-------+
          |       |       |
          v       v       v
       Postgres Redis  RabbitMQ
```

And surrounding everything:

```text
Metrics
Logs
Traces
Health checks
CI/CD
Security
```

---

# **25. The important mental model**

Don’t think:

“Gateway is just another Kubernetes object.”

Think in layers:

```text
Layer 1 — DNS
    "Where is api.projecthub.com?"

Layer 2 — Gateway
    "Where should this HTTP request go?"

Layer 3 — Service
    "Which Pods provide this application?"

Layer 4 — Pod
    "Run this container."

Layer 5 — Spring Boot
    "Handle the HTTP request."

Layer 6 — Spring Security
    "Is this caller authenticated/authorized?"

Layer 7 — Business logic
    "Is this operation actually allowed?"
```

That layered thinking is extremely valuable in backend engineering.

---

# **Exercise 51**

Try these before we move on.

### **1.**

What’s the difference between:

```text
Gateway
Service
Pod
```

in one sentence each?

---

### **2.**

A user requests:

```text
https://api.projecthub.com/posts/42
```

Walk through the request from:

```text
DNS
→ Gateway
→ HTTPRoute
→ Service
→ Pod
→ Spring Security
→ Controller
```

---

### **3.**

Why shouldn’t the Gateway replace:

```java
@PreAuthorize(...)
```

?

---

### **4.**

Suppose we have:

```text
api.projecthub.com
admin.projecthub.com
```

How could Gateway API route those to two different Services?

---

### **5.**

What does TLS termination mean?

Explain the difference between:

```text
Client --HTTPS--> Gateway --HTTP--> Pod
```

and:

```text
Client --HTTPS--> Gateway --HTTPS--> Pod
```

---

### **6. Architecture challenge**

Complete this:

```text
api.projecthub.com
        |
        v
       DNS
        |
        v
      ???
        |
        v
    HTTPRoute
        |
        v
    ProjectHub
     Service
        |
   +----+----+
   |    |    |
  Pod  Pod  Pod
```

And explain what each layer is responsible for.

---

**Next: Lesson 52 — Kubernetes Scaling & Reliability: HPA, resource requests/limits, rolling deployments, graceful shutdown, PodDisruptionBudgets, and what happens when production traffic suddenly jumps from 100 to 10,000 requests/sec.**