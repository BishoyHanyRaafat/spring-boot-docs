---
title: "Lesson 6: Configuration & Properties"
sidebar_position: 6
---

This is where Spring Boot starts becoming something you’ll use constantly in real projects.

The key idea is:

**Your application code should not need to know which environment it’s running in.**

Spring Boot supports external configuration through properties/YAML files, environment variables, command-line arguments, and more.  

---

## **1. The problem**

Imagine our ProjectHub application needs:

```text
Application name
Server port
Database URL
JWT expiration
Maximum upload size
External API URL
```

A beginner might write:

```java
public class DatabaseService {

    private String url =
        "jdbc:postgresql://localhost:5432/projecthub";

    private String username = "postgres";

    private String password = "password";
}
```

This is bad.

Why?

Because production might use:

```text
jdbc:postgresql://production-db:5432/projecthub
```

and completely different credentials.

We don’t want to modify Java code when deploying.

---

# **2. External configuration**

Instead, put configuration outside your Java classes.

For example:

```properties
spring.application.name=projecthub
server.port=8080

app.max-posts-per-page=50
app.jwt-expiration=30m
```

Now your Java code can consume those values.

The architecture becomes:

```text
              Configuration
                    │
       ┌────────────┼────────────┐
       ↓            ↓            ↓
 application    environment   command line
 .properties     variables       args
       │            │            │
       └────────────┼────────────┘
                    ↓
          Spring Environment
                    ↓
             Your application
```

Spring Boot has a defined property-source ordering, so higher-priority sources can override lower-priority ones.  

---


#  3.`application.properties`

The simplest configuration file:

```text
src/
└── main/
    └── resources/
        └── application.properties
```

Example:

```properties
spring.application.name=projecthub
server.port=8080

app.max-posts-per-page=50
app.jwt-expiration=30m
```

Spring Boot automatically looks for `application.properties` and `application.yaml` when starting the application.  

---

# **4. YAML**

You can also use:

```text
application.yaml
```

Instead of:

```properties
spring.application.name=projecthub
server.port=8080

app.max-posts-per-page=50
app.jwt-expiration=30m
```

you could write:

```yaml
spring:
  application:
    name: projecthub

  # ...

server:
  port: 8080

app:
  max-posts-per-page: 50
  jwt-expiration: 30m
```

Both are configuration formats.

For a project, I’d recommend choosing **one format and sticking with it** rather than mixing them. Spring’s current documentation explicitly recommends that approach.  

---

#  5. Getting a property with `@Value`

The simplest way is:

```java
@Service
public class PostService {

    private final int maxPostsPerPage;

    public PostService(
            @Value("${app.max-posts-per-page}") int maxPostsPerPage) {

        this.maxPostsPerPage = maxPostsPerPage;
    }
}
```

Given:

```properties
app.max-posts-per-page=50
```

Spring injects:

```text
50
```

into the constructor.

This is dependency injection again!

The difference is that we’re injecting a **configuration value** rather than another Spring bean.

---

# **6. Default values**

You can provide a fallback:

```java
@Value("${app.max-posts-per-page:20}")
```

Meaning:

```text
If app.max-posts-per-page exists
    → use it

Otherwise
    → use 20
```

This can be useful for simple values.

But there’s a better approach when configuration starts becoming more complicated.

---


# **7. The problem with lots of**

**`@Value`**

Imagine ProjectHub has:

```properties
app.jwt.secret=...
app.jwt.expiration=30m
app.jwt.issuer=projecthub
app.jwt.refresh-expiration=7d
```

You could do:

```java
@Value("${app.jwt.secret}")
private String secret;

@Value("${app.jwt.expiration}")
private Duration expiration;

@Value("${app.jwt.issuer}")
private String issuer;

@Value("${app.jwt.refresh-expiration}")
private Duration refreshExpiration;
```

But now configuration is scattered around your application.

And imagine you have 20 properties.

That gets ugly quickly.

---


# **8.** `@ConfigurationProperties`

Spring Boot provides a better mechanism for structured configuration.

You can create:

```java
@ConfigurationProperties(prefix = "app.jwt")
public record JwtProperties(
        String secret,
        Duration expiration,
        String issuer,
        Duration refreshExpiration
) {
}
```

Then:

```properties
app.jwt.secret=my-secret
app.jwt.expiration=30m
app.jwt.issuer=projecthub
app.jwt.refresh-expiration=7d
```

Spring Boot binds those values into the object.

Conceptually:

```text
application.properties
        ↓
app.jwt.secret
app.jwt.expiration
app.jwt.issuer
app.jwt.refresh-expiration
        ↓
@ConfigurationProperties
        ↓
JwtProperties
        ↓
Your services
```

This is **type-safe configuration**.

Spring Boot’s documentation specifically recommends `@ConfigurationProperties` when you have a group of related configuration keys.  

---

# **9. Why I prefer this approach**

Compare these:

### **Scattered**

```java
@Value("${app.jwt.secret}")
private String secret;

@Value("${app.jwt.expiration}")
private Duration expiration;

@Value("${app.jwt.issuer}")
private String issuer;
```

versus:

```java
@ConfigurationProperties(prefix = "app.jwt")
public record JwtProperties(
        String secret,
        Duration expiration,
        String issuer
) {
}
```

Now you have a meaningful object:

```text
JwtProperties
```

which represents one concept:

**JWT configuration**

That’s much easier to reason about.

---

# **10. Making it available as a Spring bean**

For configuration-property classes, Spring Boot can discover them using configuration-property scanning.

For example:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class ProjectHubApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProjectHubApplication.class, args);
    }
}
```

Then:

```java
@ConfigurationProperties(prefix = "app.jwt")
public record JwtProperties(
        String secret,
        Duration expiration,
        String issuer
) {
}
```

Now you can inject it normally:

```java
@Service
public class JwtService {

    private final JwtProperties properties;

    public JwtService(JwtProperties properties) {
        this.properties = properties;
    }
}
```

Notice what happened.

We’ve returned to our Lesson 1 concept:

```text
Dependency Injection
```

`JwtProperties` is now something Spring can provide to another bean.

Spring Boot’s current documentation supports `@ConfigurationPropertiesScan` for discovering these classes.  

---

# **11. A very useful feature: type conversion**

Look at:

```properties
app.jwt.expiration=30m
```

and:

```java
Duration expiration
```

Spring Boot can convert configuration values into appropriate Java types.

So you don’t necessarily have to manually do:

```java
Duration.ofMinutes(30)
```

Spring’s configuration binding supports types such as `Duration` and `DataSize`, with unit notation such as `30s`, `30m`, `10MB`, etc.  

That’s one of the reasons `@ConfigurationProperties` is powerful.

---

# **12. Environment variables**

Now imagine we deploy ProjectHub to Docker.

We don’t want:

```properties
app.jwt.secret=my-real-production-secret
```

committed to Git.

Instead, we can provide configuration externally.

For example, an environment variable:

```text
APP_JWT_SECRET=some-secret
```

Spring Boot’s relaxed binding allows environment-variable names to map to configuration properties.  

Conceptually:

```text
APP_JWT_SECRET
      ↓
app.jwt.secret
      ↓
JwtProperties.secret()
```

This becomes extremely important when we reach:

- Docker
- deployment
- CI/CD
- secrets
- production configuration

---

# **13. Profiles**

There’s another major concept.

Suppose we want different configuration for development and production.

We can have:

```text
application.yaml
application-dev.yaml
application-prod.yaml
```

For example:

### **`application.yaml`**

```yaml
app:
  max-posts-per-page: 20
```

### **`application-dev.yaml`**

```yaml
server:
  port: 8080
```

### **`application-prod.yaml`**

```yaml
server:
  port: 80
```

Then we can activate a profile.

Conceptually:

```text
dev
 ↓
application.yaml
+
application-dev.yaml
```

or:

```text
prod
 ↓
application.yaml
+
application-prod.yaml
```

Profile-specific configuration is part of Spring Boot’s configuration system.  

We’ll spend more time on profiles when we reach production configuration.

---

# **14. Configuration validation**

Here’s another reason `@ConfigurationProperties` is useful.

Imagine:

```java
@ConfigurationProperties(prefix = "app")
@Validated
public record AppProperties(
        @Min(1)
        @Max(100)
        int maxPostsPerPage
) {
}
```

Then:

```properties
app.max-posts-per-page=5000
```

can be rejected during application startup rather than allowing an invalid configuration to silently enter the application.

Spring Boot supports validation of `@ConfigurationProperties` using Jakarta Bean Validation constraints.  

This is excellent for production applications.

---

# **15. Important security rule**

Never casually put secrets into Git:

```properties
app.jwt.secret=REAL_SECRET
```

or:

```properties
spring.datasource.password=REAL_PASSWORD
```

For local development you might have local configuration, but production secrets should generally come from an appropriate secret/environment configuration mechanism.

We’ll cover this properly later.

---

# **16. Our ProjectHub configuration**

Let’s imagine the project eventually has:

```yaml
spring:
  application:
    name: projecthub

server:
  port: 8080

app:
  jwt:
    issuer: projecthub
    expiration: 30m
    refresh-expiration: 7d

  pagination:
    default-size: 20
    max-size: 100
```

We could model that with:

```text
App configuration
│
├── JwtProperties
│   ├── issuer
│   ├── expiration
│   └── refreshExpiration
│
└── PaginationProperties
    ├── defaultSize
    └── maxSize
```

That’s a clean configuration model.

---

# **17. The mental model**

You should now think of Spring Boot configuration like this:

```text
                    Configuration sources
                           │
            ┌──────────────┼──────────────┐
            ↓              ↓              ↓
       properties        YAML       environment
            │              │              │
            └──────────────┼──────────────┘
                           ↓
                  Spring Environment
                           ↓
              ┌────────────┴────────────┐
              ↓                         ↓
           @Value              @ConfigurationProperties
              ↓                         ↓
        Simple values            Structured config
                                        ↓
                                  Your services
```

And for our application:

```text
Configuration
      ↓
JwtProperties
      ↓
JwtService
      ↓
Authentication
```

That is dependency injection applied to configuration.

---

