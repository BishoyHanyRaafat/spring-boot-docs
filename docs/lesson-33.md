---
title: Lesson 33: Docker Compose
sidebar_position: 33
---

Last lesson we put **ProjectHub itself** into a container.

But ProjectHub depends on PostgreSQL.

Soon it will also depend on Redis, RabbitMQ, and perhaps other infrastructure.

Running these individually would be annoying:

```text
docker run postgres ...
docker run redis ...
docker run projecthub ...
```

Docker Compose solves this by letting us define the **whole multi-container application stack** in one YAML file. Docker describes Compose as a tool for defining and running multi-container applications, including their services, networks, and volumes.  

---

# **1. The architecture**

Our local ProjectHub environment becomes:

```text
                 Docker Compose
                      │
          ┌───────────┴───────────┐
          │                       │
          ▼                       ▼
     ProjectHub               PostgreSQL
       :8080                    :5432
          │                       │
          └────────── network ────┘
```

Later:

```text
                 Docker Compose
                      │
     ┌────────────────┼────────────────┐
     ▼                ▼                ▼
 ProjectHub       PostgreSQL         Redis
   :8080             :5432           :6379
```

And eventually:

```text
                 Docker Compose
                      │
 ┌──────────┬────────┼────────┬──────────┐
 ▼          ▼        ▼        ▼          ▼
API       Postgres  Redis   RabbitMQ  Monitoring
```

---

# 

# **2.**

**`compose.yaml`**

Create:

```text
compose.yaml
```

A very simple starting point:

```yaml
services:

  app:
    build: .
    ports:
      - "8080:8080"

  postgres:
    image: postgres:18
    environment:
      POSTGRES_DB: projecthub
      POSTGRES_USER: projecthub
      POSTGRES_PASSWORD: projecthub
```

Notice that we don’t need to manually define a network.

Compose creates a default network for the application and makes services discoverable by their service names.  

---

# **3. The service name becomes important**

We called our database:

```yaml
postgres:
```

Therefore ProjectHub can reach it using:

```text
postgres
```

rather than:

```text
localhost
```

So the database URL becomes conceptually:

```text
jdbc:postgresql://postgres:5432/projecthub
```

Think:

```text
ProjectHub container
       │
       │ postgres:5432
       ▼
PostgreSQL container
```

Docker’s internal DNS resolves `postgres` to the appropriate container.  

---

# 

# 

# **4.**

**`localhost`**

**is still a trap**

Inside ProjectHub:

```text
localhost
```

means:

```text
ProjectHub container
```

It does **not** mean:

```text
PostgreSQL container
```

So this:

```text
jdbc:postgresql://localhost:5432/projecthub
```

would be wrong for container-to-container communication.

Instead:

```text
jdbc:postgresql://postgres:5432/projecthub
```

because `postgres` is the Compose service name.

---

# **5. Environment variables**

We don’t want this hardcoded in our application:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://postgres:5432/projecthub
```

We can provide configuration through environment variables.

For example:

```yaml
services:

  app:
    build: .
    ports:
      - "8080:8080"
    environment:
      SPRING_PROFILES_ACTIVE: docker
      DB_URL: jdbc:postgresql://postgres:5432/projecthub
      DB_USERNAME: projecthub
      DB_PASSWORD: projecthub

  postgres:
    image: postgres:18
    environment:
      POSTGRES_DB: projecthub
      POSTGRES_USER: projecthub
      POSTGRES_PASSWORD: projecthub
```

Then our Spring configuration can use:

```yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
```

Now the Java application doesn’t know anything about Docker.

That’s exactly what we want.

---

# **6. But these passwords are still visible**

You might notice:

```yaml
POSTGRES_PASSWORD: projecthub
```

That’s okay **for a disposable local-development environment**.

It is not an appropriate production secret.

For production, we’d use an external secret mechanism rather than committing real credentials into the Compose file.

Remember:

```text
Development:
simple local credentials

Production:
externally managed secrets
```

---

# **7. PostgreSQL needs persistent storage**

Here’s an important problem.

Containers are disposable.

Suppose PostgreSQL stores:

```text
User Alice
Project 7
Post 42
```

Then you remove the PostgreSQL container.

If the database files existed only inside the container’s writable filesystem, you can lose them when that container is removed.

We therefore need a **volume**.

Docker volumes are persistent data stores managed by the container engine.  

---

# **8. Named volume**

Our Compose file becomes:

```yaml
services:

  postgres:
    image: postgres:18
    environment:
      POSTGRES_DB: projecthub
      POSTGRES_USER: projecthub
      POSTGRES_PASSWORD: projecthub
    volumes:
      - postgres-data:/var/lib/postgresql/data

volumes:
  postgres-data:
```

The important part:

```yaml
volumes:
  - postgres-data:/var/lib/postgresql/data
```

Conceptually:

```text
PostgreSQL container
        │
        │ database files
        ▼
postgres-data volume
```

Now the database’s data has a lifecycle separate from the PostgreSQL container.

---

# **9. Container lifecycle vs data lifecycle**

This distinction is critical.

You can have:

```text
Container A
    ↓
destroyed

Volume
    ↓
still exists
```

Then:

```text
new PostgreSQL container
        ↓
same postgres-data volume
        ↓
same database data
```

So:

```text
Container = replaceable
Volume    = persistent
```

---

# 

# **10.**

**`docker compose up`**

Now:

```bash
docker compose up
```

Compose reads:

```text
compose.yaml
```

and creates/starts the required services.

Conceptually:

```text
docker compose up
       │
       ├── network
       ├── postgres container
       ├── postgres volume
       └── projecthub container
```

You don’t need to manually create each piece.

---

# **11. Detached mode**

You can also run:

```bash
docker compose up -d
```

The `-d` means detached.

Your terminal returns while the containers continue running.

Then:

```bash
docker compose ps
```

lets you inspect the services.

And:

```bash
docker compose logs
```

lets you inspect their logs.

Compose provides commands for starting/stopping services, checking status, streaming logs, and running one-off commands.  

---

# **12. Logs for one service**

Instead of:

```bash
docker compose logs
```

you can target:

```bash
docker compose logs app
```

or:

```bash
docker compose logs postgres
```

And follow logs:

```bash
docker compose logs -f app
```

This connects nicely to the production logging lesson.

---

# 

# **13.**

**`depends_on`**

We know ProjectHub depends on PostgreSQL.

We can express that:

```yaml
services:

  app:
    build: .
    depends_on:
      - postgres

  postgres:
    image: postgres:18
```

This expresses a startup dependency.

But here’s an important detail:

**Container started does not necessarily mean service ready.**

PostgreSQL could have started its container but still be initializing.

That’s why health checks matter.

---

# **14. Health checks**

Compose supports a `healthcheck` for a service.  

For PostgreSQL:

```yaml
postgres:
  image: postgres:18
  environment:
    POSTGRES_DB: projecthub
    POSTGRES_USER: projecthub
    POSTGRES_PASSWORD: projecthub

  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U projecthub -d projecthub"]
    interval: 5s
    timeout: 5s
    retries: 10
```

Now Docker can distinguish:

```text
container running
```

from:

```text
PostgreSQL actually responding
```

---

# 

# **15.**

**`service_healthy`**

We can then tell Compose:

```yaml
app:
  depends_on:
    postgres:
      condition: service_healthy
```

Conceptually:

```text
Start PostgreSQL
      ↓
Health check
      ↓
Not ready
      ↓
Wait
      ↓
Healthy
      ↓
Start ProjectHub
```

This avoids a common startup race.

Docker’s Compose documentation demonstrates the same pattern with `depends_on.condition: service_healthy`.  

---

# **16. A better Compose file**

Now we’re getting somewhere:

```yaml
services:

  app:
    build: .
    ports:
      - "8080:8080"

    environment:
      SPRING_PROFILES_ACTIVE: docker
      DB_URL: jdbc:postgresql://postgres:5432/projecthub
      DB_USERNAME: projecthub
      DB_PASSWORD: projecthub

    depends_on:
      postgres:
        condition: service_healthy

  postgres:
    image: postgres:18

    environment:
      POSTGRES_DB: projecthub
      POSTGRES_USER: projecthub
      POSTGRES_PASSWORD: projecthub

    volumes:
      - postgres-data:/var/lib/postgresql/data

    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U projecthub -d projecthub"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  postgres-data:
```

Read it from top to bottom.

---

# **17. What happens during startup?**

When you run:

```bash
docker compose up
```

roughly:

```text
                 Compose
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
      PostgreSQL            ProjectHub
          │                   │
          ▼                   │
    health check              │
          │                   │
          ▼                   │
       HEALTHY ───────────────┘
                              │
                              ▼
                        Spring Boot
                              │
                              ▼
                           Flyway
                              │
                              ▼
                         PostgreSQL
```

This is a beautiful example of how the concepts we’ve learned fit together.

---

# **18. Flyway now becomes especially useful**

Remember our migration strategy:

```text
Flyway
 ↓
V1__create_users.sql
V2__create_projects.sql
V3__create_posts.sql
...
```

When ProjectHub starts against the PostgreSQL container:

```text
Spring Boot
    ↓
Flyway
    ↓
PostgreSQL
    ↓
apply missing migrations
```

So a new developer doesn’t need to manually create the database schema.

---

# **19. Docker Compose and Spring Boot**

There’s an interesting Spring Boot feature here.

Modern Spring Boot also has **Docker Compose support** for development. It can discover a Compose file, start services, and create service connections for supported containers.  

That means there are actually two approaches:

### **Approach A**

You manually run:

```bash
docker compose up
```

and Spring Boot connects to those services.

### **Approach B**

Spring Boot’s Docker Compose development support manages the Compose lifecycle.

For our course, we’ll understand **normal Docker Compose first**.

That’s important because you should understand the infrastructure rather than relying on magic.

---

# **20. Service connections**

Spring Boot’s Docker Compose integration can discover supported services and create connection details automatically. Those connection details take precedence over ordinary connection properties.  

For example, with a supported PostgreSQL Compose service, Spring Boot can discover the connection information rather than requiring you to manually construct every connection property.

This is convenient.

But again:

First understand the explicit architecture.

Then convenience features become easy to understand.

---

# **21. Do we need to expose PostgreSQL’s port?**

Notice something interesting.

We have:

```yaml
app:
  ports:
    - "8080:8080"
```

But we haven’t necessarily written:

```yaml
postgres:
  ports:
    - "5432:5432"
```

Why?

Because ProjectHub doesn’t need PostgreSQL exposed to your host.

The containers can communicate through their Compose network.

```text
Host
 │
 └── :8080 → ProjectHub
                  │
                  │ internal network
                  ▼
              PostgreSQL
```

That’s actually a better security boundary.

---

# **22. When would we expose PostgreSQL?**

During local development, you might want:

```text
DBeaver
    ↓
localhost:5432
    ↓
PostgreSQL container
```

Then:

```yaml
postgres:
  ports:
    - "5432:5432"
```

Now your host can connect.

But it isn’t necessary for ProjectHub itself.

This distinction is important:

```text
ports:
    host ↔ container

network:
    container ↔ container
```

---

# **23. Redis will work the same way**

Soon we’ll add:

```yaml
redis:
  image: redis:...
```

ProjectHub will connect to:

```text
redis:6379
```

not:

```text
localhost:6379
```

So:

```text
ProjectHub
   │
   ├── postgres:5432
   │
   └── redis:6379
```

Docker’s internal DNS handles the service names.  

---

# **24. Don’t use container IP addresses**

Avoid:

```text
172.20.0.4
```

in your configuration.

Why?

Container IPs can change.

Instead:

```text
postgres
redis
rabbitmq
```

Service names are stable within the Compose network.

That’s exactly what service discovery is for.

---

# 

# **25.**

**`docker compose down`**

When you’re finished:

```bash
docker compose down
```

This stops/removes the Compose-managed containers and network.

Your named volume normally remains unless you explicitly remove volumes.

That’s useful:

```text
docker compose down
       ↓
containers gone
       ↓
database volume remains
```

If you deliberately want to remove the volumes too:

```bash
docker compose down -v
```

Be careful.

For our database:

```text
down -v
```

means:

**delete the persistent database volume**

That’s a very different operation.

---

# **26. This is why migrations + volumes work together**

Suppose you start fresh:

```text
Volume doesn't exist
       ↓
PostgreSQL creates database
       ↓
ProjectHub starts
       ↓
Flyway applies V1...V10
```

Later:

```text
docker compose down
docker compose up
```

The volume remains:

```text
existing database
       ↓
Flyway checks migration history
       ↓
nothing new
       ↓
application starts
```

Then you add:

```text
V11__add_comments.sql
```

Next startup:

```text
Flyway
   ↓
sees V11 is missing
   ↓
applies V11
```

This is the deployment model we’ve been building toward since Lesson 15.

---

# **27. The full local development stack**

We’re now approaching something like:

```text
                    Docker Compose
                         │
          ┌──────────────┼──────────────┐
          │              │              │
          ▼              ▼              ▼
      ProjectHub      PostgreSQL       Redis
       :8080            :5432          :6379
          │              │              │
          └──────────────┴──────────────┘
                     network
```

And inside ProjectHub:

```text
HTTP
 ↓
Spring Security
 ↓
Controller
 ↓
Service
 ↓
JPA
 ↓
Flyway-managed PostgreSQL
```

This is starting to look like a real backend environment.

---

# **28. A subtle but important distinction**

Docker Compose is primarily describing **infrastructure**.

Spring Boot is describing **application behavior**.

So:

```text
Compose:
"Give me PostgreSQL."

Spring:
"I need a DataSource."

Flyway:
"I need these migrations applied."

JPA:
"I need to map these entities."

Security:
"I need authentication/authorization."
```

Each layer has a responsibility.

That’s good architecture.

---

# **29. Your mental model now**

I want you to be able to look at:

```yaml
services:
  app:
    build: .
    depends_on:
      postgres:
        condition: service_healthy

  postgres:
    image: postgres:18
    volumes:
      - postgres-data:/var/lib/postgresql/data
```

and immediately understand:

```text
app
 ↓
runs our Spring Boot image

postgres
 ↓
runs PostgreSQL

depends_on
 ↓
startup dependency

healthcheck
 ↓
readiness signal

volume
 ↓
persistent database storage

service name
 ↓
internal DNS/network address
```

If that mental model is solid, you’re doing well.

---

# **Exercise 33**

Now I want you to build the Compose configuration yourself.

Create a `compose.yaml` containing:

### **`app`**

```text
build from your Dockerfile
port 8080 → 8080
SPRING_PROFILES_ACTIVE=docker
DB_URL
DB_USERNAME
DB_PASSWORD
depends on PostgreSQL health
```

### **`postgres`**

```text
PostgreSQL
database: projecthub
username: projecthub
password: projecthub
persistent named volume
healthcheck using pg_isready
```

### **Questions**

**1.** Why does ProjectHub use:

```text
postgres:5432
```

instead of:

```text
localhost:5432
```

?

**2.** Why do we need a named volume for PostgreSQL?

**3.** What is the difference between:

```bash
docker compose down
```

and:

```bash
docker compose down -v
```

?

**4.** Why is:

```yaml
depends_on:
  postgres:
    condition: service_healthy
```

better than simply:

```yaml
depends_on:
  - postgres
```

for our use case?

**5.** Why don’t we need to expose PostgreSQL’s port to the host for ProjectHub to communicate with it?

**6.** Explain this entire startup flow in your own words:

```text
docker compose up
        ↓
PostgreSQL
        ↓
healthcheck
        ↓
healthy
        ↓
ProjectHub
        ↓
Flyway
        ↓
JPA
        ↓
REST API
```

---

### **Next: Lesson 34 — Redis & Caching**

We’ll add **Redis** to ProjectHub and learn why caching exists, cache-aside, TTLs, cache invalidation, Redis data structures, Spring’s caching abstraction, and—most importantly—**when caching makes things worse rather than better**.