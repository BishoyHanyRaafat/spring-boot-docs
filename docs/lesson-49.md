---
title: Lesson 49: CI CD From Git Commit to Production
sidebar_position: 49
---



Now we connect everything we’ve built.

Our journey is becoming:

```text
Java
 ↓
Spring Boot
 ↓
PostgreSQL
 ↓
Security
 ↓
Redis
 ↓
Messaging
 ↓
Docker
 ↓
Kubernetes
 ↓
CI/CD
```

The goal of this lesson is to understand how a developer can push code and have a system automatically:

```text
build → test → package → create image → deploy
```

GitHub’s current Actions documentation describes CI workflows that build and test Maven projects, and Kubernetes provides rollout commands for monitoring and rolling back deployments.  

---

# **1. The problem**

Imagine you finish a feature:

```text
feat: add project deletion
```

You push:

```bash
git push
```

Without CI/CD, someone might manually:

```text
pull code
 ↓
build
 ↓
run tests
 ↓
build Docker image
 ↓
push image
 ↓
SSH into server
 ↓
deploy
 ↓
restart application
```

That’s error-prone.

---

# **2. CI/CD**

CI/CD is a collection of practices for automatically building, testing, and delivering software.

### **CI**

**Continuous Integration**

Whenever code changes:

```text
Git push
   ↓
Build
   ↓
Tests
   ↓
Quality checks
```

---

### **CD**

**Continuous Delivery/Deployment**

After CI succeeds:

```text
Build
 ↓
Docker image
 ↓
Registry
 ↓
Deployment environment
```

Depending on the setup, deployment may be automatic or require approval.

---

# **3. The complete ProjectHub pipeline**

Our target:

```text
Developer
    |
    v
   Git
    |
    v
CI Pipeline
    |
    +---- Compile
    |
    +---- Unit tests
    |
    +---- Integration tests
    |
    +---- Security checks
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

That’s the big picture.

---

# **4. What is GitHub Actions?**

We’ll use GitHub Actions as our example CI/CD platform.

A workflow lives under:

```text
.github/workflows/
```

For example:

```text
.github/
└── workflows/
    └── ci.yml
```

A workflow defines:

- when it runs
- what machine runs it
- what jobs exist
- what steps each job performs

---

# **5. Workflow triggers**

You might want CI to run when:

```text
Pull Request
```

or:

```text
Push to main
```

Conceptually:

```yaml
on:
  pull_request:
  push:
    branches:
      - main
```

So:

```text
Developer
    |
    v
Pull Request
    |
    v
CI
```

and later:

```text
Merge
    |
    v
main
    |
    v
Deployment pipeline
```

---

# **6. Jobs**

A workflow contains jobs.

For example:

```text
CI Workflow

   |
   +---- build-and-test
   |
   +---- security
   |
   +---- package
```

Jobs can have dependencies.

Example:

```text
build-and-test
      |
      v
docker-build
      |
      v
deploy
```

You don’t want deployment to happen if tests fail.

---

# **7. A simple Maven CI workflow**

Here’s the basic idea:

```yaml
name: CI

on:
  pull_request:
  push:
    branches:
      - main

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v6

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Test
        run: ./mvnw verify
```

GitHub’s current documentation uses `actions/checkout@v6` and `actions/setup-java@v4` in its Maven examples, with Maven caching supported by `setup-java`.  

---

# **8. What happens?**

Suppose you push:

```text
commit abc123
```

GitHub starts a runner:

```text
Runner
  |
  +-- checkout repository
  |
  +-- install/setup Java
  |
  +-- run Maven
```

Then:

```bash
./mvnw verify
```

runs your build and tests.

---

# 

# 

# **9. Why**

**`verify`**

**?**

Earlier we used:

```bash
mvn test
```

That runs tests.

But:

```bash
mvn verify
```

takes the Maven lifecycle further and is often useful for CI because it can include additional verification configured by the project.

The exact lifecycle depends on your Maven plugins.

---

# **10. What should CI test?**

For ProjectHub:

```text
Compile
 ↓
Unit tests
 ↓
Spring tests
 ↓
Repository integration tests
 ↓
Security tests
 ↓
Architecture/quality checks
```

Remember our Testcontainers work?

This is where it becomes useful.

For example:

```text
CI runner
    |
    v
Testcontainers
    |
    +---- PostgreSQL
    |
    +---- Redis
    |
    +---- RabbitMQ
```

Then:

```text
ProjectHub tests
       |
       v
real infrastructure
```

---

# **11. CI catches problems before production**

Suppose someone changes:

```java
@PreAuthorize("hasAuthority('posts.delete')")
```

to:

```java
@PreAuthorize("hasAuthority('posts.delet')")
```

Typo.

Our authorization tests fail.

Pipeline:

```text
Push
 ↓
Tests
 ↓
❌ FAILED
 ↓
No deployment
```

Production stays untouched.

That’s the point.

---

# **12. Docker comes next**

After tests:

```text
Tests passed
      |
      v
Build Docker image
```

For example:

```text
projecthub:abc123
```

Notice something important.

Instead of:

```text
projecthub:latest
```

we can use an immutable version:

```text
projecthub:abc123
```

or:

```text
projecthub:1.7.0
```

---

# **13. Why image tags matter**

Suppose production is running:

```text
projecthub:1.6.0
```

We deploy:

```text
projecthub:1.7.0
```

Something breaks.

We know exactly what version is running.

We can roll back to:

```text
projecthub:1.6.0
```

Kubernetes supports Deployment rollout history and rollback commands such as `kubectl rollout undo`.  

---

# **14. Container Registry**

After building:

```text
Docker image
```

we need somewhere to store it.

For example:

```text
Container Registry

projecthub:abc123
projecthub:abc456
projecthub:1.7.0
```

Then Kubernetes can pull the image.

Architecture:

```text
CI
 |
 v
Build image
 |
 v
Registry
 |
 v
Kubernetes
```

---

# **15. Deployment**

Now CI/CD tells Kubernetes:

Deploy this image.

Conceptually:

```text
projecthub:1.7.0
```

becomes the image used by the Deployment.

Kubernetes creates new Pods and progressively replaces the old ones when using its default `RollingUpdate` strategy.  

---

# **16. The rollout**

Before:

```text
1.6.0

Pod A
Pod B
Pod C
```

Deploy:

```text
1.7.0
```

Kubernetes progressively changes the Pods:

```text
1.7.0   1.6.0   1.6.0

1.7.0   1.7.0   1.6.0

1.7.0   1.7.0   1.7.0
```

The exact behavior depends on the Deployment’s rollout settings such as `maxUnavailable` and `maxSurge`.  

---

# **17. Readiness becomes extremely important**

Remember:

```text
liveness
readiness
```

Suppose the new Pod starts:

```text
Pod 4

Spring Boot starting...
```

Kubernetes shouldn’t immediately send user traffic to it.

Instead:

```text
Pod 4
 |
 v
Readiness check
 |
 +--- ❌ not ready
 |
 v
Initialize
 |
 v
Ready
 |
 +--- ✅ traffic
```

This is one reason health probes and deployment strategies work together.

---

# **18. What if the new version is broken?**

Imagine:

```text
1.6.0 → 1.7.0
```

But 1.7.0 has:

```text
500 errors
```

You investigate:

```bash
kubectl rollout status deployment/projecthub
```

Kubernetes provides `kubectl rollout status` for monitoring the rollout.  

If necessary:

```bash
kubectl rollout undo deployment/projecthub
```

That rolls the Deployment back.  

---

# **19. CI vs CD**

This distinction is worth memorizing.

### **CI**

```text
"Is this code safe to merge/build?"
```

Pipeline:

```text
compile
test
verify
security checks
```

---

### **CD**

```text
"How do we deliver this validated version?"
```

Pipeline:

```text
build image
push image
deploy
verify rollout
```

---

# **20. A mature pipeline**

ProjectHub could eventually have:

```text
                    Git Push
                       |
                       v
                +-------------+
                |     CI      |
                +-------------+
                       |
             +---------+---------+
             |         |         |
             v         v         v
          Compile    Tests    Security
             |         |         |
             +---------+---------+
                       |
                       v
                 Docker Build
                       |
                       v
                 Image Scan
                       |
                       v
                Push Registry
                       |
                       v
                 Deploy Staging
                       |
                       v
                Smoke Tests
                       |
                       v
                 Production
```

That’s a real deployment pipeline.

---

# **21. Staging environment**

Don’t immediately deploy every commit directly to production.

A common flow is:

```text
Development
    |
    v
CI
    |
    v
Staging
    |
    v
Verification
    |
    v
Production
```

Staging should resemble production enough to expose important problems before release.

---

# **22. Database migrations are interesting**

Remember Flyway?

Suppose version 1.7.0 contains:

```text
V12__add_project_status.sql
```

Deployment needs to coordinate:

```text
Application
+
Database migration
```

This is where things become interesting.

You don’t want:

```text
Old application
      X
new database schema
```

to break production.

---

# **23. Backward-compatible migrations**

A safer migration often follows:

```text
Step 1

Add new column
```

without immediately deleting the old one.

Then:

```text
Step 2

Deploy application that understands both
```

Then:

```text
Step 3

Migrate data
```

Then:

```text
Step 4

Stop using old column
```

Then later:

```text
Step 5

Remove old column
```

This is sometimes called the **expand-and-contract** approach.

---

# **24. Secrets in CI/CD**

Very important.

Never do this:

```yaml
env:
  DB_PASSWORD: "super-secret-password"
```

inside a repository.

Instead use your CI/CD platform’s secret management and your deployment environment’s secret-management mechanism.

The pipeline should effectively say:

```text
"I need DB_PASSWORD"
```

without putting the actual secret into source control.

---

# **25. Pull requests**

A great workflow:

```text
Developer
   |
   v
Feature branch
   |
   v
Pull Request
   |
   v
CI
   |
   +---- tests
   +---- security
   +---- build
   |
   v
Code review
   |
   v
Merge main
```

Then:

```text
main
 |
 v
Docker
 |
 v
Staging
 |
 v
Production
```

---

# **26. Why this changes backend development**

Before CI/CD:

```text
"I wrote code."
```

After CI/CD:

```text
"I wrote code,
tested it,
packaged it,
and can reliably deliver it."
```

That’s a much more complete engineering skill.

---

# **27. ProjectHub’s complete journey**

We’ve now built almost the entire conceptual path:

```text
                         Developer
                             |
                             v
                           Git
                             |
                             v
                      GitHub Actions
                             |
              +--------------+--------------+
              |              |              |
              v              v              v
           Compile         Tests         Security
              |              |              |
              +--------------+--------------+
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
                 +-----------+-----------+
                 |           |           |
                 v           v           v
               Pod         Pod         Pod
                 |           |           |
                 +-----------+-----------+
                             |
                             v
                       ProjectHub
                             |
              +--------------+--------------+
              |              |              |
              v              v              v
          PostgreSQL       Redis         RabbitMQ
```

This is the architecture we’ve been building toward since the beginning.

---

# **28. One important distinction**

CI/CD does **not** mean:

“Deploy every commit to production no matter what.”

Good CI/CD means:

Automate the path from source code to a validated, controlled deployment.

You can have:

```text
automatic CI
+
manual production approval
```

or:

```text
automatic staging
+
automatic production
```

depending on the organization’s risk and release process.

---

# **Lesson 49 Summary**

You’ve learned:

✅ Continuous Integration  
✅ Continuous Delivery/Deployment  
✅ GitHub Actions workflows  
✅ Jobs and steps  
✅ Maven CI  
✅ Testcontainers in CI  
✅ Docker image creation  
✅ Image tagging  
✅ Container registries  
✅ Kubernetes deployment  
✅ Rolling updates  
✅ Rollbacks  
✅ Staging environments  
✅ Database migration concerns  
✅ Secrets in pipelines  
✅ Pull-request workflows

GitHub’s current documentation provides Maven workflows for building/testing Java projects, while Kubernetes documents rollout monitoring and rollback through `kubectl rollout`.  

---

# **Exercise 49**

Let’s make this practical.

### **1.**

What is the difference between:

```text
CI
```

and:

```text
CD
```

---

### **2.**

Why should a Docker image use:

```text
projecthub:abc123
```

instead of relying only on:

```text
projecthub:latest
```

?

---

### **3.**

Imagine this happens:

```text
Developer pushes code

      ↓

Tests fail
```

Should Docker build and deployment continue?

Why?

---

### **4.**

Why is this dangerous?

```text
Git
 ↓
Docker
 ↓
Production
```

with no automated tests?

---

### **5.**

ProjectHub version `2.0` requires a database migration.

How could deploying the application and database change simultaneously cause a problem?

---

### **6. The fun one 😄**

Design your complete ProjectHub pipeline:

```text
Developer
    |
    v
   Git
    |
    v
   ???
    |
    v
   ???
    |
    v
Docker
    |
    v
   ???
    |
    v
Kubernetes
    |
    v
Production
```

Fill in the missing pieces.

**Next lesson: Lesson 50 — Kubernetes in Practice: We’ll finally write actual Deployment + Service + ConfigMap manifests for ProjectHub and walk through what every line does.**