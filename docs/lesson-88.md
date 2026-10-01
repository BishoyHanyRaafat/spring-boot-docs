---
title: "Lesson 88: Production Configuration & Environment Management"
sidebar_position: 88
---

We’re going to keep the remaining series **fast and practical**. This lesson is about making the same application run safely in dev, test, staging, and production.

Spring Boot supports external configuration through YAML/properties, environment variables, command-line arguments, and structured `@ConfigurationProperties`. Later property sources override earlier ones according to Spring Boot’s defined precedence rules.  

---

## **1. The problem**

You don’t want this:

```text
application.yaml

database:
  password: myProductionPassword
```

committed to Git.

And you definitely don’t want:

```text
JWT_SECRET=my-real-secret
```

inside your source code.

Instead:

```text
                 Same application
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
         DEV         TEST         PROD
          │            │            │
       config        config       config
```

The **code stays the same**.

The environment supplies different configuration.

---

# **2. `application.yaml`**

Safe defaults can live here:

```yaml
spring:
  application:
    name: projecthub

server:
  port: 8080

app:
  pagination:
    default-size: 20
    max-size: 100
```

These aren’t secrets.

They’re application configuration.

---

# **3. Profiles**

Spring Profiles let you separate configuration for environments such as development and production.  

For example:

```text
application.yaml
application-dev.yaml
application-test.yaml
application-prod.yaml
```

You might have:

```yaml
# application-dev.yaml

spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/projecthub
```

while production receives its database URL externally.

Activate a profile with:

```text
SPRING_PROFILES_ACTIVE=prod
```

Spring Boot then loads the appropriate profile-specific configuration.  

---

# **4. But don’t go crazy with profiles**

A common beginner pattern is:

```text
application-dev
application-test
application-staging
application-prod
application-docker
application-kubernetes
application-local
application-local-windows
...
```

Don’t do this.

Profiles should primarily represent meaningful runtime differences.

For example:

```text
dev
test
prod
```

And environment-specific secrets/configuration can come from the deployment environment.

---

# **5. Environment variables**

Suppose your application expects:

```yaml
spring:
  datasource:
    url: ...
    username: ...
    password: ...
```

You can provide those through environment variables.

Spring Boot’s relaxed binding maps environment variable names to configuration properties. For example:

```text
SPRING_DATASOURCE_URL
SPRING_DATASOURCE_USERNAME
SPRING_DATASOURCE_PASSWORD
```

maps to:

```text
spring.datasource.url
spring.datasource.username
spring.datasource.password
```

So Docker/Kubernetes can provide configuration without changing the application artifact.

---

# 

# **6. Use**

**`@ConfigurationProperties`**

For your own application settings, prefer structured configuration.

For example:

```java
@ConfigurationProperties("app.jwt")
public record JwtProperties(
    String issuer,
    Duration accessTokenLifetime
) {}
```

Then:

```yaml
app:
  jwt:
    issuer: projecthub
    access-token-lifetime: 15m
```

Your service receives a strongly typed object rather than scattering:

```java
@Value("${...}")
```

throughout the codebase.

Spring Boot supports binding configuration into `@ConfigurationProperties` objects and recommends this approach for structured configuration.  

---

# **7. Secrets**

Think of configuration in two categories.

### **Normal configuration**

```text
PORT=8080
MAX_PAGE_SIZE=100
KAFKA_TOPIC=projecthub.events
```

### **Secrets**

```text
DATABASE_PASSWORD
JWT_PRIVATE_KEY
RABBITMQ_PASSWORD
```

The second category should come from a proper secret mechanism rather than Git.

In Kubernetes, for example:

```text
ConfigMap → normal configuration
Secret    → sensitive configuration
```

Spring Boot can also consume mounted configuration trees, which is useful for Kubernetes/Docker-style secret files.  

---

# **8. The production principle**

Your Docker image should ideally be:

```text
projecthub.jar
```

or an image containing it.

You don’t rebuild the application because the database password changed.

Instead:

```text
Same image
    │
    ├── dev configuration
    ├── staging configuration
    └── production configuration
```

This is a fundamental deployment principle:

**Build once, configure per environment.**

---

# **9. What should NEVER happen**

Don’t do:

```java
String jwtSecret = "super-secret-key";
```

Don’t commit:

```yaml
password: production-password
```

Don’t have production configuration depend on:

```text
"works on my laptop"
```

And don’t make your application require developers to manually edit source code before deployment.

---

# **10. ProjectHub configuration architecture**

Eventually:

```text
                 ProjectHub image
                       │
             ┌─────────┴─────────┐
             │                   │
          Kubernetes          local Docker
             │                   │
          ConfigMap           env vars
          Secret              env vars
             │
             ▼
        Spring Environment
             │
             ▼
    @ConfigurationProperties
             │
             ▼
        Application
```

That’s the model I want you to remember.

---

## **We’re moving quickly now**

The remaining sequence is:

```text
88  Configuration              ← NOW
89  Logging + Observability
90  Performance
91  CI/CD
92  Production Deployment
93  Final ProjectHub Architecture
94  Final review / what to learn next
```

So we’re genuinely close to wrapping the series.

**Next: Lesson 89 — Production Logging, Actuator, Health Checks & Observability.**