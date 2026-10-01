---
title: Lesson 91: CI CD
sidebar_position: 91
---

Now we’re connecting development to production.

The goal is simple:

**Every change should be automatically built, tested, packaged, and safely deployable.**

For ProjectHub:

```text
Developer
   │
   ▼
Git push
   │
   ▼
CI pipeline
   │
   ├── Compile
   ├── Unit tests
   ├── Integration tests
   ├── Security checks
   │
   ▼
Build Docker image
   │
   ▼
Container registry
   │
   ▼
CD pipeline
   │
   ▼
Kubernetes
```

Spring Boot officially supports Maven and Gradle as its primary build systems, with dependency management designed to keep compatible versions together.  

---

## **1. CI vs CD**

### **CI — Continuous Integration**

Whenever code changes:

```text
git push
   ↓
build
   ↓
test
   ↓
quality/security checks
```

The goal is to catch problems **before they reach production**.

### **CD — Continuous Delivery/Deployment**

After CI succeeds:

```text
build artifact
   ↓
Docker image
   ↓
registry
   ↓
deployment
```

You can think of it as:

```text
CI = "Is this change safe to package?"

CD = "How do we deliver that package?"
```

---

# **2. The pipeline we want**

For ProjectHub:

```text
Pull Request
     │
     ▼
┌───────────────┐
│ Compile       │
│ Unit tests    │
│ Integration   │
│ tests         │
└───────┬───────┘
        │
      success
        │
        ▼
┌───────────────┐
│ Build JAR     │
│ Build image   │
└───────┬───────┘
        │
        ▼
 Container Registry
        │
        ▼
 Kubernetes
```

A pull request should generally prove the code is healthy before it can be merged.

---

# **3. Tests are part of deployment safety**

We’ve already built several testing layers:

```text
Unit tests
    ↓
@WebMvcTest
    ↓
@DataJpaTest
    ↓
Testcontainers
    ↓
@SpringBootTest
    ↓
Kafka/Outbox integration tests
```

CI simply automates running them.

For example:

```text
mvn test
```

might execute your normal test suite.

Then a more comprehensive pipeline can run the integration suite.

Spring Boot’s current documentation continues to support Maven/Gradle build plugins and executable JAR creation through those plugins.  

---

# **4. Build once**

This principle is extremely important:

**Build the application once; promote the same artifact through environments.**

Bad:

```text
dev  → build
test → build again
prod → build again
```

You could theoretically end up deploying three different binaries.

Better:

```text
Source
  ↓
Build
  ↓
Docker image: projecthub:abc123
  │
  ├── dev
  ├── staging
  └── production
```

The configuration changes.

The artifact doesn’t.

That’s exactly why we separated configuration from the application in Lesson 88.

---

# **5. Docker image tags**

Don’t rely exclusively on:

```text
projecthub:latest
```

Prefer an immutable identifier such as:

```text
projecthub:git-a81f92c
```

or:

```text
projecthub:2026-10-01-abc123
```

Now Kubernetes can tell exactly what version is running.

For example:

```text
Deployment
   ↓
image: registry/projecthub:a81f92c
```

---

# **6. Container registry**

The registry is basically:

**A Git repository for container images.**

Conceptually:

```text
CI
 ↓
docker build
 ↓
docker push
 ↓
Registry
```

Then Kubernetes pulls the image:

```text
Kubernetes
     ↓
registry/projecthub:a81f92c
```

---

# **7. Kubernetes deployment**

Suppose we update:

```text
a81f92c
```

to:

```text
b73c201
```

Kubernetes performs a Deployment rollout.

Conceptually:

```text
Old Pods
  ↓
┌─────┐ ┌─────┐ ┌─────┐
│ old │ │ old │ │ old │
└─────┘ └─────┘ └─────┘

        ↓ rollout

New Pods
  ↓
┌─────┐ ┌─────┐ ┌─────┐
│ new │ │ new │ │ new │
└─────┘ └─────┘ └─────┘
```

The exact rollout behavior depends on your Deployment strategy/configuration.

You can monitor a Kubernetes Deployment with:

```bash
kubectl rollout status deployment/projecthub
```

Kubernetes provides `kubectl rollout status` specifically for watching rollout progress.  

---

# **8. What if deployment fails?**

This is where CI/CD becomes really valuable.

Imagine:

```text
New version
    ↓
Kubernetes rollout
    ↓
Readiness checks fail
    ↓
new Pod doesn't receive traffic
```

Or perhaps the deployment completes but application errors appear.

You need:

```text
health checks
metrics
logs
deployment history
rollback capability
```

We already covered the first three.

So deployment isn’t isolated from observability.

They’re connected.

---

# **9. Secrets in CI/CD**

Never do this:

```yaml
password: my-real-production-password
```

inside your repository.

Instead:

```text
CI/CD secret store
        ↓
deployment
        ↓
Kubernetes Secret
        ↓
Spring configuration
```

And for cloud authentication, modern CI systems can use short-lived identity mechanisms such as OIDC rather than long-lived cloud credentials. GitHub’s deployment documentation specifically describes OIDC as a way to avoid storing long-lived cloud credentials.  

---

# **10. A realistic GitHub Actions pipeline**

For example, conceptually:

```yaml
name: ProjectHub CI

on:
  pull_request:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - checkout

      - setup Java

      - run: ./mvnw test
```

Then after merging:

```text
main
 ↓
test
 ↓
package
 ↓
docker build
 ↓
docker push
 ↓
deploy
```

I’m deliberately keeping the workflow conceptual here. The important thing is understanding **what each stage accomplishes**, rather than memorizing YAML.

---

# **11. CI/CD should have gates**

Think of each stage as a gate:

```text
                 ┌────────────┐
                 │ Source     │
                 └─────┬──────┘
                       ↓
                 ┌────────────┐
                 │ Compile    │
                 └─────┬──────┘
                       ↓
                 ┌────────────┐
                 │ Tests      │
                 └─────┬──────┘
                       ↓
                 ┌────────────┐
                 │ Security   │
                 └─────┬──────┘
                       ↓
                 ┌────────────┐
                 │ Image      │
                 └─────┬──────┘
                       ↓
                 ┌────────────┐
                 │ Deploy     │
                 └────────────┘
```

If tests fail:

```text
STOP
```

Don’t deploy.

---

# **12. The production feedback loop**

Now combine everything we’ve learned:

```text
Developer
   │
   ▼
Git
   │
   ▼
CI
   │
   ├── tests
   ├── security
   └── build
   │
   ▼
Docker Registry
   │
   ▼
Kubernetes
   │
   ├── readiness
   ├── liveness
   └── rollout
   │
   ▼
Production
   │
   ├── logs
   ├── metrics
   └── traces
   │
   ▼
Developer
```

That is the fundamental **software delivery feedback loop**.

---

# **13. ProjectHub’s final delivery architecture**

We’re getting very close to the complete picture:

```text
                    Git
                     │
                     ▼
                    CI
          ┌──────────┼──────────┐
          ▼          ▼          ▼
       Compile     Tests     Security
          │          │
          └────┬─────┘
               ▼
          Docker Image
               │
               ▼
       Container Registry
               │
               ▼
          Kubernetes
               │
       ┌───────┼────────┐
       ▼       ▼        ▼
     API     Workers   Consumers
       │       │        │
       └───────┼────────┘
               ▼
          PostgreSQL
               │
             Outbox
               │
          ┌────┴────┐
          ▼         ▼
        Kafka    RabbitMQ
          │         │
          ▼         ▼
      Consumers   Workers
```

And surrounding everything:

```text
Observability
Security
Configuration
Testing
CI/CD
```

---

# **The important lesson**

A professional backend isn’t just:

```text
Spring Boot + PostgreSQL
```

It’s:

```text
Application
+
Database
+
Messaging
+
Security
+
Testing
+
Configuration
+
Observability
+
Containers
+
Orchestration
+
CI/CD
```

You now have enough pieces to understand how those systems fit together.

---

## **Next: Lesson 92 — Production Deployment**

We’ll take the Kubernetes system we’ve built and walk through an actual production deployment:

```text
Docker image
      ↓
Registry
      ↓
Kubernetes Deployment
      ↓
Service
      ↓
Ingress
      ↓
TLS
      ↓
DNS
      ↓
Users
```

Then we’ll finish with **Lesson 93: the complete ProjectHub architecture**, where we put almost the entire course on one diagram.