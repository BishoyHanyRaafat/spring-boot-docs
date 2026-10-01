---
title: Lesson 47: Containers and Docker for Spring Boot Applications
sidebar_position: 47
---

Welcome to a major transition point.

So far we learned how to **build backend systems**:

- Spring Boot APIs
- Security
- Databases
- Redis
- Messaging
- Observability

But a real question appears:

How do we take our application and run it reliably on another machine?

Example:

You develop on your laptop:

```text
Windows/Mac

Java 21

PostgreSQL 16

Redis

RabbitMQ
```

Production server:

```text
Linux

Different Java version

Different configuration

Different installed software
```

Problems happen.

Docker solves this.

---

# **1. What is Docker?**

Docker packages your application with everything it needs.

Instead of:

```text
 id="oldway"

Server

Install Java

Install PostgreSQL

Install Redis

Copy application

Configure everything
```

We create:

```text
 id="dockerway"

Docker Image

+
Application

+
Java Runtime

+
Dependencies
```

Then run it anywhere.

---

# **2. Virtual machines vs containers**

Before Docker:

Companies used virtual machines.

Example:

```text
 id="vm"

Physical Server

        |

        v

Virtual Machine

        |

        v

Operating System

        |

        v

Application
```

---

Problem:

A full operating system for every application.

Heavy.

---

Docker:

```text
 id="container"

Physical Server

        |

        v

Docker Engine

   |       |       |

   v       v       v

 App1    App2    App3
```

Containers share the host OS.

Much lighter.

---

# **3. Important Docker concepts**

Docker has four main concepts:

```text
1. Image

2. Container

3. Dockerfile

4. Registry
```

---

# **4. Docker Image**

An image is a blueprint.

Like a class in Java.

Example:

```text
 id="image"

Spring Boot Application Image

Contains:

- Java
- application.jar
- configuration
```

You create an image once.

---

# **5. Docker Container**

A container is a running instance of an image.

Like an object in Java.

Example:

Image:

```text
 id="java"

ProjectHub Image
```

Run:

```bash
docker run projecthub
```

Creates:

```text
 id="container"

ProjectHub Container
```

---

# **6. Docker Registry**

A place to store images.

Example:

Docker Hub

You can:

push:

```text
Your laptop

   |
   v

Docker Hub
```

pull:

```text
Server

   |
   v

Docker Hub
```

---

# **7. The Docker workflow**

Typical workflow:

```text
 id="workflow"

Write code

    |

Build Spring Boot jar

    |

Create Docker image

    |

Push image

    |

Deploy container
```

---

# **8. Spring Boot application without Docker**

Normally:

Build:

```bash
mvn clean package
```

Creates:

```text
 id="jar"

projecthub.jar
```

Run:

```bash
java -jar projecthub.jar
```

Works on your machine.

---

# **9. Dockerfile**

A Dockerfile tells Docker how to build the image.

Example:

```dockerfile
FROM eclipse-temurin:21-jdk

WORKDIR /app

COPY target/projecthub.jar app.jar

EXPOSE 8080

ENTRYPOINT [
"java",
"-jar",
"app.jar"
]
```

---

Let’s understand it.

---

## **FROM**

```dockerfile
FROM eclipse-temurin:21-jdk
```

Means:

Start with Java 21.

Base image:

```text
Java runtime
```

---

## **WORKDIR**

```dockerfile
WORKDIR /app
```

Inside container:

```text
/app
```

becomes the working folder.

---

## **COPY**

```dockerfile
COPY target/projecthub.jar app.jar
```

Copy your application.

Before:

```text
Laptop:

target/projecthub.jar
```

After:

```text
Container:

app.jar
```

---

## **EXPOSE**

```dockerfile
EXPOSE 8080
```

Documents that the application uses:

```text
port 8080
```

---

## **ENTRYPOINT**

```dockerfile
ENTRYPOINT [
"java",
"-jar",
"app.jar"
]
```

Command executed when container starts.

---

# **10. Build Docker image**

Inside project:

```bash
docker build -t projecthub .
```

Meaning:

Create image:

```text
projecthub
```

---

Check images:

```bash
docker images
```

Example:

```text
REPOSITORY

projecthub

TAG

latest
```

---

# **11. Run container**

```bash
docker run -p 8080:8080 projecthub
```

Meaning:

Host:

```text
8080
```

maps to:

Container:

```text
8080
```

Now:

```text
Browser

localhost:8080

        |

        v

Spring Boot Container
```

---

# **12. Container lifecycle**

Create:

```bash
docker create
```

Start:

```bash
docker start
```

Stop:

```bash
docker stop
```

Remove:

```bash
docker rm
```

---

# **13. Viewing containers**

Running:

```bash
docker ps
```

All:

```bash
docker ps -a
```

Example:

```text
CONTAINER ID

abc123

IMAGE

projecthub

STATUS

Up 5 minutes
```

---

# **14. Logs**

Very important.

Application logs:

```bash
docker logs projecthub
```

Example:

```text
Started ProjectApplication

Tomcat running on port 8080
```

---

# **15. Environment variables**

Never hardcode production values.

Bad:

```properties
spring.datasource.password=password123
```

---

Better:

```properties
spring.datasource.password=${DB_PASSWORD}
```

Docker:

```bash
docker run \
-e DB_PASSWORD=mysecret \
projecthub
```

---

# **16. Spring Boot configuration**

Example:

application.yml:

```yaml
spring:
 datasource:
   url: ${DATABASE_URL}
   username: ${DATABASE_USER}
   password: ${DATABASE_PASSWORD}
```

Container receives:

```text
DATABASE_URL

DATABASE_USER

DATABASE_PASSWORD
```

---

# **17. Docker Compose**

A real application has multiple services.

ProjectHub:

```text
 id="services"

Spring Boot

+

PostgreSQL

+

Redis

+

RabbitMQ
```

Running manually:

```bash
docker run postgres

docker run redis

docker run rabbitmq

docker run projecthub
```

Painful.

---

Docker Compose:

One file:

```yaml
docker-compose.yml
```

defines everything.

---

# **18. Example Docker Compose**

```yaml
services:

  app:
    image: projecthub
    ports:
      - "8080:8080"

  postgres:
    image: postgres
    environment:
      POSTGRES_PASSWORD: password

  redis:
    image: redis

  rabbitmq:
    image: rabbitmq
```

Start:

```bash
docker compose up
```

Now:

```text
 id="compose"

ProjectHub

     |

     +---- PostgreSQL

     +---- Redis

     +---- RabbitMQ
```

---

# **19. Docker networking**

Containers can talk using service names.

Example:

```yaml
services:

 postgres:
   image: postgres

 app:
   image: projecthub
```

Inside Spring:

Instead of:

```properties
localhost
```

Use:

```properties
postgres
```

Because Docker creates a network.

---

# **20. Database persistence problem**

Containers are temporary.

Example:

```bash
docker rm postgres
```

Database disappears.

Problem.

---

Solution:

Volumes.

---

# **21. Docker volumes**

A volume stores data outside the container.

Example:

```yaml
postgres:

 volumes:

 - postgres-data:/var/lib/postgresql/data
```

Now:

Container deleted:

```text
Database data remains
```

---

# **22. Multi-stage Docker builds**

A production improvement.

Bad:

```dockerfile
FROM jdk

copy source

build

run
```

Image contains:

- source code
- Maven
- build tools

Large.

---

Better:

Stage 1:

Build:

```dockerfile
FROM maven

compile application
```

Stage 2:

Run:

```dockerfile
FROM java-runtime

copy jar
```

Result:

Small image.

---

Example:

```dockerfile
FROM maven:3.9 AS build

WORKDIR /app

COPY . .

RUN mvn package


FROM eclipse-temurin:21

COPY --from=build \
target/*.jar app.jar

ENTRYPOINT [
"java",
"-jar",
"app.jar"
]
```

---

# **23. Docker security basics**

Do not run as root.

Bad:

```text
Container

root user
```

Better:

```dockerfile
USER appuser
```

---

Do not store secrets:

Bad:

```dockerfile
ENV PASSWORD=12345
```

Use:

- environment variables
- secret managers

---

# **24. Health checks**

Docker can check your application.

Example:

```dockerfile
HEALTHCHECK CMD curl localhost:8080/actuator/health
```

---

Application:

```text
UP
```

Container:

```text
healthy
```

---

# **25. Spring Boot + Docker architecture**

ProjectHub:

```text
                 User


                  |

                  v


             Load Balancer


                  |

        +---------+---------+

        |         |         |

        v         v         v


    Container Container Container


        |

        v


     Docker Network


        |

 +------+------+------+


 v             v      v


Postgres     Redis  RabbitMQ
```

---

# **26. Docker in production**

Usually:

Developer:

```text
Code
```

↓

CI/CD:

```text
Build image
Run tests
Push image
```

↓

Production:

```text
Pull image

Run containers
```

---

# **27. Docker vs Kubernetes**

Docker:

Creates and runs containers.

Kubernetes:

Manages many containers.

Example:

Docker:

```text
Run one ProjectHub container
```

Kubernetes:

```text
Run 100 ProjectHub containers

Replace failed containers

Scale automatically

Load balance
```

---

# **28. When Docker becomes essential**

Almost every modern backend:

✅ Microservices  
✅ Cloud deployment  
✅ CI/CD pipelines  
✅ Kubernetes  
✅ Testing environments

---

# **29. ProjectHub deployment evolution**

## **Development**

```text
Laptop

Spring Boot

Postgres

Redis
```

---

## **Docker Compose**

```text
Docker

 + Spring Boot

 + PostgreSQL

 + Redis

 + RabbitMQ
```

---

## **Production**

```text
Kubernetes Cluster


 + ProjectHub Pods

 + Database

 + Redis Cluster

 + Message Brokers
```

---

# **Lesson 47 Summary**

You learned:

✅ Why containers exist  
✅ Docker images  
✅ Containers  
✅ Dockerfile  
✅ Building Spring Boot images  
✅ Running containers  
✅ Environment variables  
✅ Docker Compose  
✅ Volumes  
✅ Networking  
✅ Multi-stage builds  
✅ Docker security  
✅ Production deployment flow

---

# **Exercise 47**

Answer:

### **1.**

Explain the difference:

```
Docker Image
```

vs

```
Docker Container
```

---

### **2.**

Why should we avoid:

```properties
database.password=secret123
```

inside application files?

---

### **3.**

ProjectHub needs:

- Spring Boot
- PostgreSQL
- Redis
- RabbitMQ

Would you run them manually or use Docker Compose? Why?

---

### **4.**

Why do databases need Docker volumes?

---

### **5.**

Design a Docker architecture:

```
ProjectHub

     |

 ?

     |

PostgreSQL
Redis
RabbitMQ
```

---

Next lesson:

# **Lesson 48 — Kubernetes Fundamentals: Pods, Deployments, Services, Scaling, and Production Spring Boot**

We will learn:

- why Docker is not enough
- Kubernetes architecture
- pods
- deployments
- services
- config maps
- secrets
- auto scaling
- rolling updates

This is where backend developers enter cloud-native engineering.