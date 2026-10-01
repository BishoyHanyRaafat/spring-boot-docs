---
title: "Lesson 5: Spring Boot Starters, Auto-Configuration SpringApplication"
sidebar_position: 5
---


Now we’re moving from **Spring itself** into what **Spring Boot** adds on top.

As of today, the current stable Spring Boot release is **4.1.1**. It requires at least Java 17.  

---

## **1. First: Spring vs Spring Boot**

This distinction is important.

### **Spring Framework**

Spring gives you things like:

- Dependency Injection
- IoC container
- Beans
- `ApplicationContext`
- MVC
- Transactions
- Security integration
- etc.

### **Spring Boot**

Spring Boot’s goal is essentially:

**“Give me sensible defaults so I can build and run a Spring application without configuring everything manually.”**

Spring Boot provides things like:

- Auto-configuration
- Starter dependencies
- Embedded web servers
- Externalized configuration
- Production features
- Convenient application startup

That’s why a Spring Boot application can often be started with:

```bash
java -jar application.jar
```

rather than requiring you to deploy it manually to an external server.  

---

# **2. What happens when you write this?**

You’ve already seen:

```java
@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

It looks tiny.

But this line:

```java
SpringApplication.run(Application.class, args);
```

starts a surprisingly large process.

Conceptually:

```text
main()
   ↓
SpringApplication.run()
   ↓
Create/configure ApplicationContext
   ↓
Read configuration
   ↓
Discover components
   ↓
Apply auto-configuration
   ↓
Create beans
   ↓
Wire dependencies
   ↓
Start embedded server
   ↓
Application ready
```

Spring’s own documentation describes `SpringApplication.run()` as bootstrapping Spring and, for a web application, starting the auto-configured embedded server.  

---

# **3. The magic annotation**

You’ve seen:

```java
@SpringBootApplication
```

This is actually a combination of three important concepts:

```text
@SpringBootApplication
       │
       ├── @SpringBootConfiguration
       ├── @EnableAutoConfiguration
       └── @ComponentScan
```

Spring Boot’s documentation confirms this composition.  

Let’s understand each.

---


# 4. `@ComponentScan`

We already learned this one.

It tells Spring:

Find my Spring components.

For example:

```java
@Service
public class UserService {
}
```

and:

```java
@RestController
public class UserController {
}
```

Spring scans your application packages and discovers them.

So:

```text
com.example.project
│
├── Application.java
│
├── controller
│     └── UserController
│
├── service
│     └── UserService
│
└── repository
      └── UserRepository
```

can be discovered automatically.

This is one reason your main application class is normally near the top/root package.

---


# **5. @EnableAutoConfiguration`

This is the really important Spring Boot concept.

Imagine you add a web dependency to your project.

Spring Boot sees things such as:

```text
Spring MVC
Tomcat
JSON libraries
HTTP-related classes
```

and essentially says:

“Looks like this application is probably a web application. I’ll configure the common web infrastructure.”

That’s **auto-configuration**.

Spring Boot’s documentation describes it as configuring the application based on the dependencies present on the classpath.  

---

# **6. A concrete example**

Suppose your project has the web starter.

You don’t manually create:

```java
TomcatServer server = new TomcatServer();
```

You don’t manually configure every MVC component.

You don’t manually create an HTTP request dispatcher.

Instead, Boot sees the relevant dependencies and configures the infrastructure.

Conceptually:

```text
You add web dependency
        ↓
Spring Boot detects web-related classes
        ↓
Auto-configuration activates
        ↓
Web infrastructure configured
        ↓
Embedded server configured
        ↓
Your @RestController becomes available
```

That’s the “Boot” part of Spring Boot.

---

# **7. But auto-configuration isn’t magic guessing**

This is an important mental model.

Don’t think:

“Spring Boot randomly guesses what I want.”

Think:

**Spring Boot has predefined configuration rules that activate when certain conditions are true.**

For example, conceptually:

```text
IF web-related classes exist
AND
IF you haven't provided your own conflicting configuration
THEN
configure the default web infrastructure
```

This idea of **conditional configuration** is fundamental to understanding Spring Boot.

We’ll go deeper into it later.

---

# **8. Starters**

Now let’s look at another important feature.

You’ve probably seen dependencies like:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

What’s a **starter**?

A starter is basically a convenient dependency bundle.

Instead of manually selecting a bunch of libraries that commonly belong together, you choose a starter.

Conceptually:

```text
spring-boot-starter-web
        │
        ├── Spring MVC
        ├── JSON support
        ├── embedded server support
        └── other web infrastructure
```

Then Boot’s auto-configuration uses those dependencies to configure the application.

The important relationship is:

```text
Starter
   ↓
Dependencies added to classpath
   ↓
Auto-configuration detects them
   ↓
Infrastructure gets configured
```

Starters and auto-configuration work particularly well together, although they are technically separate concepts.  

---

# **9. This is why dependencies matter so much**

Consider:

```text
No database dependency
        ↓
Boot doesn't configure JPA/database infrastructure

Add JPA-related dependency
        ↓
Boot can configure JPA infrastructure

Add PostgreSQL driver
        ↓
Boot can work with PostgreSQL

Add web dependencies
        ↓
Boot configures web infrastructure
```

So your `pom.xml` or `build.gradle` isn’t merely a list of things your application imports.

Your dependencies can actually influence **how Spring Boot configures the application**.

This is one of the most important concepts to understand before we reach Spring Data JPA.

---

# **10. What if I don’t like the auto-configuration?**

You can override it.

For example, imagine Boot provides a default bean:

```text
DefaultSomething
```

but you explicitly configure your own:

```java
@Bean
public Something something() {
    return new MySomething();
}
```

Depending on the particular auto-configuration, your explicit configuration can cause Boot’s default configuration to back off.

This leads to an important philosophy:

**Spring Boot gives you defaults, but you can take control when you need to.**

That is one of the core ideas behind Boot.

---


# **11.**

**`application.properties`**

There’s another major piece of Spring Boot we need to introduce.

You will commonly have:

```text
src/
└── main/
    └── resources/
        └── application.properties
```

For example:

```properties
spring.application.name=projecthub
server.port=8081
```

Then Boot reads those properties and uses them for configuration.

Spring Boot supports configuration through properties/YAML files, environment variables, command-line arguments, and other sources.  

So instead of hardcoding:

```java
int port = 8081;
```

you can configure:

```properties
server.port=8081
```

This becomes extremely important later when we have:

```text
Development
    ↓
PostgreSQL localhost
    ↓
Production
    ↓
PostgreSQL production server
```

We don’t want to recompile our application every time configuration changes.

---

# **12. Why this matters for our ProjectHub**

Remember our project:

```text
ProjectHub
│
├── Users
├── Projects
├── Posts
├── Comments
└── Permissions
```

Eventually we’ll have configuration like:

```properties
spring.application.name=projecthub

server.port=8080

database.url=...
database.username=...
database.password=...

jwt.secret=...
jwt.expiration=...
```

And later:

```text
Development
        ↓
application.properties

Production
        ↓
Environment variables / external configuration
```

Spring Boot is designed specifically to make this kind of externalized configuration practical.  

---

# **13. Put everything together**

When you start:

```java
@SpringBootApplication
public class ProjectHubApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProjectHubApplication.class, args);
    }
}
```

you can mentally think:

```text
                 Spring Boot
                      │
          ┌───────────┼────────────┐
          ↓           ↓            ↓
   Component Scan  Auto-config   Configuration
          │           │            │
          ↓           ↓            ↓
       Your beans   Framework     Properties
          │        infrastructure
          └───────────┬────────────┘
                      ↓
               ApplicationContext
                      ↓
               Dependency wiring
                      ↓
              Embedded web server
                      ↓
                  Application
```

That’s a much better mental model than thinking:

“`SpringApplication.run()` somehow starts Spring.”

---

# **14. One subtle but important point**

Earlier we learned:

```java
@Service
public class UserService {
}
```

Spring creates the bean.

Now we can understand **why**.

It’s roughly:

```text
@SpringBootApplication
        ↓
@ComponentScan
        ↓
Find @Service
        ↓
Register bean definition
        ↓
Create UserService
        ↓
Resolve constructor dependencies
        ↓
Create/wire dependency beans
```

So the lessons are starting to connect:

**Lesson 1**

Dependency Injection

↓

**Lesson 2**

Spring builds the object graph

↓

**Lesson 3**

ApplicationContext + component scanning

↓

**Lesson 4**

Explicit beans + resolving multiple implementations

↓

**Lesson 5**

Spring Boot automates much of the infrastructure around all of this

That’s the progression I want you to understand.

---

# **🧠 Your first mental model checkpoint**

Before continuing, make sure you can explain these four terms in your own words:

### **1. Spring**

The framework providing things like IoC and dependency injection.

### **2. Spring Boot**

The layer that makes building/running Spring applications easier through defaults, auto-configuration, starters, embedded infrastructure, etc.

### **3. Starter**

A convenient dependency bundle for a particular application capability.

### **4. Auto-configuration**

Spring Boot automatically configuring infrastructure based on what’s available and what you’ve explicitly configured.

---