---
title: "Lesson 32: Docker for Spring Boot"
sidebar_position: 32
---

We’ve built a fairly serious Spring Boot application:

```text
REST API
  ↓
Services
  ↓
JPA
  ↓
PostgreSQL
  ↓
Security
  ↓
JWT
  ↓
Authorization
  ↓
Tests
  ↓
Actuator
  ↓
Logging
```

Now we need to answer:

**How do we package ProjectHub so it can run consistently on another machine?**

That’s where **Docker** comes in.

Spring Boot officially supports container images through both Dockerfiles and Cloud Native Buildpacks.  

---

# **1. What problem does Docker solve?**

Without Docker, deploying ProjectHub might require:

```text
Install Java
Install correct Java version
Install PostgreSQL
Configure environment variables
Install dependencies
Configure networking
Configure startup
```

And then someone says:

“It works on my machine.”

Docker gives us a standardized runtime environment.

Conceptually:

```text
Your machine
      ↓
Docker image
      ↓
Container
      ↓
ProjectHub
```

The container carries the application runtime environment with it.

---

# **2. Image vs container**

This distinction is fundamental.

### **Image**

An **image** is a packaged, immutable template.

Think:

```text
Image = blueprint
```

For example:

```text
projecthub:1.0
```

### **Container**

A **container** is a running instance of an image.

```text
Image
  ↓
Container
```

You can create multiple containers from the same image:

```text
projecthub:1.0
      │
      ├── container A
      ├── container B
      └── container C
```

---

# **3. Dockerfile**

A `Dockerfile` describes how to build an image.

A very simple Java example:

```dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app

COPY target/projecthub.jar app.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "app.jar"]
```

Let’s understand every line before we worry about optimization.

---

# 

# **4.**

**`FROM`**

```dockerfile
FROM eclipse-temurin:21-jre
```

This chooses the base image.

We’re saying:

Start with an image containing a Java runtime.

The application doesn’t need the JDK merely to **run** a compiled JAR.

It needs the runtime.

---

# 

# **5.**

**`WORKDIR`**

```dockerfile
WORKDIR /app
```

This establishes the working directory inside the container.

Then:

```dockerfile
COPY target/projecthub.jar app.jar
```

means approximately:

```text
host:
target/projecthub.jar

        ↓

container:
/app/app.jar
```

---

# 

# **6.**

**`COPY`**

```dockerfile
COPY target/projecthub.jar app.jar
```

Copies something from the build context into the image.

The important mental model:

```text
Your computer
     │
     │ docker build
     ▼
Docker image
     │
     │ docker run
     ▼
Container
```

---

# 

# **7.**

**`EXPOSE`**

```dockerfile
EXPOSE 8080
```

This documents that the application listens on port 8080.

It does **not** by itself publish the port to your host.

That distinction matters.

---

# 

# **8.**

**`ENTRYPOINT`**

```dockerfile
ENTRYPOINT ["java", "-jar", "app.jar"]
```

This tells Docker:

When the container starts, run the Spring Boot application.

So:

```text
docker run
    ↓
container starts
    ↓
java -jar app.jar
    ↓
Spring Boot starts
    ↓
Tomcat starts
    ↓
ProjectHub listens on 8080
```

---

# **9. Building the image**

After building the Spring Boot JAR:

```bash
./mvnw clean package
```

you might have:

```text
target/
    projecthub-1.0.0.jar
```

Then:

```bash
docker build -t projecthub:1.0 .
```

Conceptually:

```text
Dockerfile
    +
JAR
    ↓
docker build
    ↓
projecthub:1.0
```

Docker’s build system creates the image from the Dockerfile. Multi-stage builds are recommended when you want to separate build tooling from the runtime image.  

---

# **10. Running the container**

Then:

```bash
docker run -p 8080:8080 projecthub:1.0
```

The two ports mean:

```text
-p HOST:CONTAINER
```

So:

```text
8080:8080
```

means:

```text
your computer:8080
       ↓
container:8080
```

Then:

```text
Browser
   ↓
localhost:8080
   ↓
Docker
   ↓
ProjectHub container:8080
```

---

# **11. Containers are isolated**

Imagine:

```text
Your machine
│
├── Java
├── PostgreSQL
├── Docker
│
└── ProjectHub container
      ├── Java runtime
      ├── application
      └── filesystem
```

The application runs in its own isolated environment.

This is one reason containers are useful for deployment.

---

# **12. But containers aren’t virtual machines**

A common beginner misconception:

“Docker is a lightweight virtual machine.”

Not exactly.

A VM generally contains:

```text
Virtual machine
 ├── virtual hardware
 ├── operating system
 ├── runtime
 └── application
```

A container generally shares the host kernel while isolating the process/filesystem/network environment.

Simplified:

```text
VM:
Host
 └── VM
      └── Guest OS
           └── Application

Container:
Host
 └── Container
      └── Application
```

That’s one reason containers can be lightweight compared with full VMs.

---

# **13. Why our first Dockerfile isn’t ideal**

Our first Dockerfile assumes:

```text
JAR already exists
```

So we’d have to do:

```text
./mvnw package
      ↓
docker build
      ↓
docker run
```

But we can do better.

We can have Docker perform the build too.

That’s where **multi-stage builds** come in.

---

# **14. Multi-stage builds**

Docker allows multiple `FROM` instructions.

For example:

```dockerfile
FROM eclipse-temurin:21-jdk AS builder

WORKDIR /build

COPY . .

RUN ./mvnw clean package
```

Then:

```dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app

COPY --from=builder /build/target/*.jar app.jar

ENTRYPOINT ["java", "-jar", "app.jar"]
```

Now:

```text
Builder stage
    │
    ├── JDK
    ├── Maven
    ├── source code
    └── build
         │
         ▼
       JAR
         │
         ▼
Runtime stage
    │
    ├── JRE
    └── JAR
```

The compiler and build tools don’t need to be present in the final runtime image.

Docker specifically recommends multi-stage builds for separating build environments from runtime environments, reducing the final image’s contents and attack surface.  

---

# **15. Why this matters**

Imagine your build environment contains:

```text
JDK
Maven
source code
test tools
debugging tools
temporary files
```

You don’t need those to run:

```bash
java -jar projecthub.jar
```

So:

```text
Build image
    ↓
lots of tools

Runtime image
    ↓
only what is needed to run
```

That’s a cleaner production boundary.

---

# **16. Spring Boot’s optimized layering**

Spring Boot has another optimization.

A Spring Boot JAR can be organized into layers such as:

```text
dependencies
spring-boot-loader
snapshot-dependencies
application
```

This lets Docker reuse layers when only application code changes.  

Why is that useful?

Imagine:

```text
100 MB dependencies
20 MB Spring libraries
5 MB your application
```

You change one Java class.

Without good layering:

```text
rebuild everything
upload everything
```

With layers:

```text
dependencies     ← unchanged
Spring libraries ← unchanged
application      ← changed
```

Docker can reuse cached layers.

That’s particularly useful in CI/CD.

---

# **17. Spring Boot’s current Docker approach**

Current Spring Boot documentation provides a Dockerfile approach using its JAR layering/jarmode tools, including a builder stage and runtime stage.  

You don’t need to memorize that Dockerfile yet.

The important architectural idea is:

```text
Build efficiently
        ↓
Layer dependencies separately
        ↓
Keep runtime image focused
        ↓
Reuse Docker cache
```

We’ll eventually create a proper production Dockerfile for ProjectHub.

---

# **18. Buildpacks**

There’s another option.

Spring Boot supports **Cloud Native Buildpacks**.

Instead of writing a Dockerfile yourself, the Spring Boot Maven/Gradle plugin can create a container image for you.  

Conceptually:

```text
Spring Boot project
       ↓
Buildpack
       ↓
Container image
```

This is attractive when you don’t need detailed Dockerfile control.

---

# **19. Dockerfile vs Buildpacks**

Think of it this way:

### **Dockerfile**

```text
You control the image construction.
```

Good for learning and situations where you need explicit control.

### **Buildpacks**

```text
Spring Boot/tooling determines much of the image construction.
```

Good when you want convenient, sensible containerization without maintaining a Dockerfile.

We’ll learn Dockerfiles first because understanding what’s actually happening is valuable.

---

# **20. Docker and configuration**

Remember our previous lesson?

We don’t put production secrets inside the image.

Bad:

```dockerfile
ENV DB_PASSWORD=mySecretPassword
```

Don’t do that.

Instead:

```text
Container
    ↑
environment variables
    ↑
deployment system
```

For example:

```bash
docker run \
  -e SPRING_PROFILES_ACTIVE=prod \
  -e DB_URL=... \
  -e DB_USERNAME=... \
  -e DB_PASSWORD=... \
  projecthub:1.0
```

Now the image remains the same.

Only configuration changes.

That’s exactly what we learned in Lesson 29.

---

# **21. One image, multiple environments**

This is a very important deployment principle.

You don’t want:

```text
projecthub-dev-image
projecthub-test-image
projecthub-prod-image
```

just because configuration differs.

Prefer:

```text
             projecthub:1.0
                   │
        ┌──────────┼──────────┐
        │          │          │
       dev        test       prod
        │          │          │
     config      config     config
```

Same application artifact.

Different environment configuration.

---

# **22. Docker networking**

Here’s where things become interesting.

Suppose we have:

```text
ProjectHub
PostgreSQL
```

If both run in containers, don’t assume ProjectHub should connect to:

```text
localhost:5432
```

Why?

Inside the ProjectHub container:

```text
localhost
```

means:

**the ProjectHub container itself**

not your PostgreSQL container.

Instead, with Docker networking, containers can communicate using service/container names.

Conceptually:

```text
projecthub
    │
    │ postgres:5432
    ▼
postgres
```

This is the foundation for the next lesson on Docker Compose.

---

# **23. This is a critical mental model**

On your host:

```text
localhost
```

means:

```text
your computer
```

Inside ProjectHub:

```text
localhost
```

means:

```text
ProjectHub container
```

Inside PostgreSQL:

```text
localhost
```

means:

```text
PostgreSQL container
```

Every container has its own network context.

---

# **24. ProjectHub architecture is changing**

Before Docker:

```text
Your machine
│
├── Spring Boot
└── PostgreSQL
```

After containerization:

```text
Docker
│
├── ProjectHub container
│     └── Spring Boot
│
└── PostgreSQL container
      └── PostgreSQL
```

And eventually:

```text
Docker
│
├── projecthub
├── postgres
├── redis
├── rabbitmq
└── monitoring
```

That’s where **Docker Compose** becomes extremely useful.

---

# **25. Containerizing isn’t deployment**

Another important distinction.

Docker gives us:

```text
packaging
isolation
repeatability
```

It doesn’t automatically give us:

```text
high availability
load balancing
backups
secret management
monitoring
automatic scaling
```

Those are deployment/infrastructure concerns.

Eventually we’ll learn how containers fit into those systems.

---

# **26. Don’t put PostgreSQL inside the ProjectHub image**

This is a common beginner mistake.

Don’t create:

```text
ProjectHub container
 ├── Spring Boot
 └── PostgreSQL
```

Instead:

```text
ProjectHub container
        │
        │ network
        ▼
PostgreSQL container
```

Each container should generally have a focused responsibility.

We’ll make this concrete in Docker Compose.

---

# **27. ProjectHub’s future local environment**

We’re heading toward:

```text
                 Docker Compose
                      │
       ┌──────────────┼──────────────┐
       │              │              │
       ▼              ▼              ▼
   ProjectHub      PostgreSQL      Redis
    :8080           :5432          :6379
```

Later:

```text
       ┌──────────────┼───────────────┐
       │              │               │
    RabbitMQ        Prometheus       Grafana
```

This will give us a reproducible development environment.

---

# **28. One more production concept: immutable images**

Ideally, after creating:

```text
projecthub:1.0
```

you don’t SSH into the container and manually modify files.

Instead:

```text
code change
   ↓
new build
   ↓
projecthub:1.1
   ↓
deploy new container
```

So:

```text
1.0 → 1.1 → 1.2 → 1.3
```

rather than:

```text
running container
   ↓
random manual changes
   ↓
"what exactly is running?"
```

This makes deployments reproducible.

---

# **Exercise 32**

Before we write our real Docker setup, answer these:

### **1. Image vs container**

Explain the difference between:

```text
projecthub:1.0
```

and:

```text
a running ProjectHub container
```

---

### **2. Ports**

If we run:

```bash
docker run -p 8080:8080 projecthub
```

what does each `8080` represent?

---

### **3. Multi-stage build**

Why is this preferable?

```text
Builder:
JDK + Maven + source code
        ↓
       JAR
        ↓
Runtime:
JRE + JAR
```

instead of putting everything into one image?

---

### **4. Configuration**

Why shouldn’t this be inside your Docker image?

```text
DB_PASSWORD=super-secret-production-password
```

Where should it come from instead?

---

### 

### **5.**

**`localhost`**

Suppose:

```text
projecthub container
postgres container
```

Why would this usually be wrong from ProjectHub?

```text
jdbc:postgresql://localhost:5432/projecthub
```

What concept should we use instead?

---

### **6. Architecture**

Draw the architecture you think we’re heading toward:

```text
Docker
 ├── ProjectHub
 ├── PostgreSQL
 └── Redis
```

and explain how ProjectHub communicates with PostgreSQL.

---

**Next lesson: Lesson 33 — Docker Compose**, where we’ll actually run **ProjectHub + PostgreSQL together**, configure their network, environment variables, persistent database storage, and health checks.