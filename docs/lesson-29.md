---
title: Lesson 29: Production Configuration & Profiles
sidebar_position: 29
---

We’ve reached the **production-readiness** phase.

Until now, we’ve mostly been focused on building features:

```text
Spring
 → REST
 → JPA
 → PostgreSQL
 → Security
 → JWT
 → Authorization
 → Testing
```

Now we need to answer:

How does the same application behave differently in development, testing, and production **without changing Java code**?

That’s the purpose of **externalized configuration and Spring Profiles**.

Spring Boot 4.1.1 is currently the stable release line, and its configuration system supports properties/YAML, environment variables, command-line arguments, and structured `@ConfigurationProperties` binding.  

---

## **1. The problem**

Imagine your application needs:

```text
Database URL
Database username
Database password
JWT issuer
JWT private key
Redis URL
server port
logging level
```

Development might use:

```text
localhost
local database
debug logging
```

Production might use:

```text
production database
production credentials
restricted logging
real JWT keys
```

You **do not** want:

```java
if (production) {
    databaseUrl = "...";
} else {
    databaseUrl = "...";
}
```

Configuration should be outside your business code.

---

# **2. Externalized configuration**

Spring Boot allows configuration to come from several sources, including:

```text
application.yaml
environment variables
system properties
command-line arguments
external configuration files
```

and uses a defined precedence system so higher-priority sources can override lower-priority values.  

So your Java code can simply say:

```java
@ConfigurationProperties(prefix = "app.jwt")
public record JwtProperties(
        String issuer,
        Duration accessTokenExpiration
) {}
```

The application doesn’t care whether those values came from:

```text
application.yaml
```

or:

```text
APP_JWT_ISSUER
```

or another supported configuration source.

---

# **3. Profiles**

A **profile** lets us activate configuration for a particular environment or situation.

Typical ProjectHub profiles:

```text
dev
test
prod
```

You might have:

```text
application.yaml
application-dev.yaml
application-test.yaml
application-prod.yaml
```

Spring Boot loads the general configuration and then applies profile-specific configuration when that profile is active. Profile-specific configuration overrides the non-specific configuration.  

---

# **4. Base configuration**

Imagine:

```yaml
spring:
  application:
    name: projecthub

server:
  port: 8080

app:
  jwt:
    access-token-expiration: 15m
```

These are reasonable defaults.

Then development can override things.

---

# **5. Development profile**

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/projecthub_dev
    username: projecthub
    password: projecthub

logging:
  level:
    com.example.projecthub: DEBUG
```

Now:

```text
dev
 ↓
local PostgreSQL
 ↓
debug logging
```

---

# **6. Production profile**

Production might contain:

```yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}

logging:
  level:
    root: INFO
```

Notice something important:

We haven’t written:

```yaml
password: my-super-secret-password
```

Instead:

```yaml
password: ${DB_PASSWORD}
```

The actual secret comes from the environment.

---

# **7. Never commit production secrets**

This is one of the rules I want you to remember permanently:

**Configuration is not necessarily secret, but credentials are.**

This is fine:

```yaml
server:
  port: 8080
```

This is not:

```yaml
spring:
  datasource:
    password: myProductionPassword
```

And especially don’t commit:

```text
private JWT signing key
database password
API secret
cloud credentials
encryption key
```

to Git.

Once a secret is committed, deleting it from the latest commit doesn’t necessarily remove it from repository history.

---

# **8. Environment variables**

Suppose we have:

```yaml
app:
  jwt:
    issuer: projecthub
```

An environment variable can represent the same property using uppercase/underscore notation:

```text
APP_JWT_ISSUER
```

Spring Boot supports relaxed binding for environment variables.  

For example:

```text
DB_URL
DB_USERNAME
DB_PASSWORD
APP_JWT_ISSUER
```

can provide production configuration without modifying the packaged application.

---

# **9. The application’s code stays the same**

This is the goal.

Development:

```text
ProjectHub.jar
     +
dev configuration
```

Production:

```text
ProjectHub.jar
     +
prod configuration
```

Same compiled application.

Different environment.

```text
       ProjectHub application
              │
       ┌──────┴──────┐
       │             │
      dev           prod
       │             │
 local config    production config
```

That’s much cleaner than building different Java applications.

---

# **10. Activating a profile**

You can activate a profile using configuration such as:

```text
spring.profiles.active=dev
```

or externally:

```text
SPRING_PROFILES_ACTIVE=prod
```

or a command-line argument:

```text
--spring.profiles.active=prod
```

Spring Boot supports `spring.profiles.active`, and external higher-priority configuration can override a value defined in application configuration.  

---

# **11. Be careful with this**

You might put:

```yaml
spring:
  profiles:
    active: dev
```

in your main `application.yaml`.

That’s convenient locally.

But there’s a problem:

You don’t want your production deployment accidentally forced into `dev`.

A common approach is to let the deployment environment determine the active profile:

```text
Development:
SPRING_PROFILES_ACTIVE=dev

Production:
SPRING_PROFILES_ACTIVE=prod
```

That keeps the deployment decision outside the application artifact.

---

# **12. Profiles aren’t just “environments”**

A profile doesn’t have to mean:

```text
dev
prod
```

It can represent a configuration capability.

For example:

```text
postgres
redis
messaging
metrics
```

Spring Boot supports **profile groups**, where activating one logical profile can activate several related profiles.  

For example:

```yaml
spring:
  profiles:
    group:
      production:
        - postgres
        - redis
        - messaging
```

Then:

```text
SPRING_PROFILES_ACTIVE=production
```

can activate the grouped profiles.

But don’t create 30 profiles just because you can.

---

# 

# **13.**

**`@Profile`**

Profiles can also control whether a bean exists.

For example:

```java
@Configuration
@Profile("dev")
public class DevConfiguration {

    @Bean
    DevEmailService devEmailService() {
        return new DevEmailService();
    }
}
```

That bean exists only when the `dev` profile is active.

Spring Boot supports `@Profile` on components, configuration classes, and configuration-properties-related configuration.  

---

# 

# **14. But don’t abuse**

**`@Profile`**

This is bad architecture:

```java
@Service
@Profile("dev")
public class UserService { ... }

@Service
@Profile("prod")
public class AnotherUserService { ... }
```

Now your business logic changes dramatically depending on environment.

Prefer:

```text
same business logic
+
different configuration
```

Use profiles primarily for genuinely environment-specific infrastructure/configuration.

---

# **15. Example: email service**

Suppose ProjectHub sends emails.

In development, you might not want to send real emails.

You could have:

```text
DevEmailSender
ProductionEmailSender
```

Development:

```text
User registers
    ↓
EmailSender
    ↓
log email instead of sending
```

Production:

```text
User registers
    ↓
EmailSender
    ↓
real email provider
```

That is a legitimate use of profiles.

---

# **16. Configuration properties are still our preferred approach**

Remember Lesson 6.

Instead of:

```java
@Value("${app.jwt.issuer}")
private String issuer;
```

we prefer structured configuration:

```java
@ConfigurationProperties(prefix = "app.jwt")
public record JwtProperties(
        String issuer,
        Duration accessTokenExpiration
) {}
```

This becomes increasingly valuable as configuration grows.

For example:

```yaml
app:
  jwt:
    issuer: projecthub
    access-token-expiration: 15m
    refresh-token-expiration: 7d
```

maps naturally to:

```java
public record JwtProperties(
        String issuer,
        Duration accessTokenExpiration,
        Duration refreshTokenExpiration
) {}
```

---

# **17. Configuration validation**

Here’s an important production principle:

If a required configuration value is missing, fail during startup rather than discovering the problem during a user request.

For example:

```java
@ConfigurationProperties(prefix = "app.jwt")
@Validated
public record JwtProperties(

        @NotBlank
        String issuer,

        @NotNull
        Duration accessTokenExpiration

) {}
```

Now an invalid configuration can prevent the application from starting.

That’s good.

Imagine production starts with:

```text
JWT issuer = missing
```

You’d rather get:

```text
Application failed to start
```

than:

```text
Application starts successfully
...
first login request
...
500 Internal Server Error
```

Fail fast.

---

# **18. Configuration vs secrets**

This distinction is worth making explicit.

### **Normal configuration**

```text
server.port=8080
logging.level=INFO
app.jwt.access-token-expiration=15m
```

Could potentially live in configuration files.

### **Secret**

```text
DB_PASSWORD
JWT_PRIVATE_KEY
STRIPE_SECRET_KEY
```

Should be supplied securely by the deployment environment/secrets system.

Spring Boot supports environment variables and configuration trees for external configuration, including secrets mounted by platforms such as Kubernetes.  

---

# **19. Configuration trees**

This is something you’ll encounter later.

A platform might mount:

```text
/config/secrets/
    DB_PASSWORD
    JWT_PRIVATE_KEY
```

instead of putting secrets directly into environment variables.

Spring Boot supports `configtree:` imports for this kind of directory-based configuration.  

You don’t need this for ProjectHub yet.

Just understand the idea:

```text
Secret manager
      ↓
mounted files
      ↓
Spring configuration
      ↓
@ConfigurationProperties
```

---

# **20. Don’t log secrets**

This sounds obvious, but it’s a common production mistake.

Don’t do:

```java
log.info("JWT secret = {}", properties.secret());
```

or:

```java
log.info("Database password = {}", password);
```

Also be careful with:

```text
request headers
Authorization
cookies
connection strings
```

because logs often end up in external systems.

We’ll cover production logging in a later lesson.

---

# **21. Configuration precedence**

This is something you’ll eventually need to debug.

Suppose:

```yaml
application.yaml
```

says:

```text
app.jwt.issuer=projecthub
```

and an environment variable says:

```text
APP_JWT_ISSUER=production-projecthub
```

Which wins?

Spring Boot has an ordered property-source system; higher-priority sources can override lower-priority ones. Environment variables have higher priority than packaged application config.  

The exact precedence is worth consulting when debugging complicated deployments rather than memorizing every layer.

The important mental model:

```text
default config
      ↓
profile config
      ↓
external config
      ↓
environment/system/command-line overrides
```

with the precise ordering defined by Spring Boot.

---

# **22. ProjectHub configuration design**

I’d like our application eventually to look roughly like:

```text
src/main/resources/
    application.yaml
    application-dev.yaml
    application-test.yaml
    application-prod.yaml
```

### **`application.yaml`**

Common configuration:

```text
application name
common server settings
common JPA behavior
common JWT durations
```

### **`application-dev.yaml`**

Development conveniences:

```text
local database
debug logging
development integrations
```

### **`application-test.yaml`**

Testing:

```text
test-specific settings
```

Although our Testcontainers database connection will be supplied dynamically.

### **`application-prod.yaml`**

Production defaults:

```text
production-safe logging
production-specific behavior
```

while actual secrets come externally.

---

# **23. One important architectural rule**

Don’t put this:

```yaml
app:
  admin:
    password: ...
```

in `application-prod.yaml`.

Instead:

```yaml
app:
  admin:
    password: ${ADMIN_PASSWORD}
```

Then:

```text
production environment
       ↓
ADMIN_PASSWORD
       ↓
Spring configuration
       ↓
application
```

The configuration file tells the application **where** the secret comes from.

The deployment environment supplies the secret.

---

# **24. Profiles don’t provide security**

This is important.

Someone might think:

```text
prod profile = secure
dev profile = insecure
```

Profiles themselves don’t secure anything.

They’re simply configuration activation mechanisms.

For example:

```text
@Profile("prod")
```

doesn’t magically encrypt anything.

Security comes from:

```text
authentication
authorization
secret management
network controls
encryption
least privilege
```

Profiles only help configure those systems appropriately.

---

# **25. Our architecture is becoming production-ready**

We’re now approaching:

```text
                     ProjectHub
                         │
        ┌────────────────┼────────────────┐
        │                │                │
   Application       Configuration      Security
        │                │                │
      REST          Profiles/env       JWT/auth
        │                │                │
      Service       Secrets           Permissions
        │                │                │
       JPA          Database          Policies
        │
    PostgreSQL
        │
     Flyway
        │
   Testcontainers
```

The next production concern is:

**How do we know what’s happening inside this application once it’s running?**

That’s **observability**.

---

# **Exercise 29**

Before we move on, design the ProjectHub configuration.

Create these four files conceptually:

```text
application.yaml
application-dev.yaml
application-test.yaml
application-prod.yaml
```

Put the following into the appropriate places:

### **Common**

```text
app.jwt.issuer
app.jwt.access-token-expiration
```

### **Development**

```text
local PostgreSQL URL
local PostgreSQL username
local PostgreSQL password
DEBUG logging
```

### **Production**

```text
DB_URL
DB_USERNAME
DB_PASSWORD
JWT issuer
INFO logging
```

And answer these questions:

1. **Why shouldn’t the production DB password be committed to Git?**
2. **Why is** **`@ConfigurationProperties`** **preferable to many** **`@Value`** **fields for JWT configuration?**
3. **What happens if** **`SPRING_PROFILES_ACTIVE=prod`** **is supplied externally while** **`application.yaml`** **says** **`dev`****?**
4. **Why should a missing production JWT configuration ideally cause startup failure?**
5. **What’s the difference between a profile and a secret?**

Once you’ve got that, the next lesson is **Lesson 30 — Actuator, Health Checks, Metrics & Observability**, where we’ll start making ProjectHub behave like a service that can actually be operated in production.