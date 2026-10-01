---
title: "Lesson 3: Beans, ApplicationContext, and Component Scanning"
sidebar_position: 3
---


Now we get into one of the most important parts of Spring.

If you understand this lesson well, a lot of Spring Boot will stop feeling like magic.

---

# **1. What exactly is a Bean?**

We’ve been saying:

“Spring creates beans.”

But what is a bean?

A **Spring Bean is an object managed by the Spring IoC container.**

For example:

```java
@Service
public class ProductService {
}
```

Spring will create an instance of `ProductService` and manage it.

Conceptually:

```java
ProductService productService = new ProductService();
```

But instead of you doing this, **Spring does it**.

That object is now a Spring Bean.

---

# **2. Where are Beans stored?**

Spring has a container.

The most important abstraction you’ll encounter is:

```java
ApplicationContext
```

Think of it as a registry/container of the application’s beans.

Conceptually:

```text
┌─────────────────────────────────────┐
│        ApplicationContext           │
│                                     │
│ ProductController                   │
│ ProductService                      │
│ ProductRepository                   │
│ UserService                         │
│ EmailService                        │
│ ...                                 │
└─────────────────────────────────────┘
```

Each object is managed by Spring.

---

# **3. You can actually access the ApplicationContext**

For example:

```java
@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {

        ApplicationContext context =
                SpringApplication.run(
                        DemoApplication.class,
                        args
                );

        ProductService service =
                context.getBean(ProductService.class);
    }
}
```

This:

```java
context.getBean(ProductService.class)
```

basically says:

“Spring, give me the `ProductService` bean.”

Notice that we didn’t write:

```java
new ProductService();
```

Spring already created it.

---


# **4. But don’t start using `getBean()` everywhere

You might think:

“Cool! I’ll just use `context.getBean()` everywhere.”

Don’t.

This:

```java
ProductService service =
    context.getBean(ProductService.class);
```

is useful for understanding the container and for certain framework-level cases, but your application code should normally use **dependency injection**.

Prefer:

```java
@Service
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }
}
```

rather than manually asking the container for dependencies.

The difference is important:

```text
Bad-ish application style:

Your code → Spring container → dependency


Preferred:

Spring container → injects dependency → your code
```

---

# **5. How does Spring discover your classes?**

This is where **component scanning** comes in.

Suppose your project is:

```text
com.example.demo
│
├── DemoApplication.java
│
├── controller
│    └── ProductController.java
│
├── service
│    └── ProductService.java
│
└── repository
     └── ProductRepository.java
```

Your main class:

```java
package com.example.demo;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(
            DemoApplication.class,
            args
        );
    }
}
```

Spring Boot will scan the application’s package and its subpackages for components.

So it finds:

```text
com.example.demo.controller
com.example.demo.service
com.example.demo.repository
```

---

# **6. Component scanning**

Suppose:

```java
@Service
public class ProductService {
}
```

When Spring scans the package, it sees:

```text
@Service
```

and registers that class as a bean candidate.

Similarly:

```java
@Repository
public class ProductRepository {
}
```

and:

```java
@RestController
public class ProductController {
}
```

Spring discovers them.

So:

```text
Component scanning
        ↓
Find annotated classes
        ↓
Register bean definitions
        ↓
Create/manage beans
```

---

# **7. Why package structure matters**

This is a common beginner problem.

Suppose your main class is:

```text
com.example.demo.DemoApplication
```

and your service is:

```text
com.example.service.ProductService
```

Notice:

```text
com.example.demo
```

and:

```text
com.example.service
```

`service` isn’t underneath `demo`.

Depending on your configuration, Spring’s default component scanning won’t discover it.

A typical structure is:

```text
com.example.demo
│
├── DemoApplication
│
├── controller
├── service
├── repository
└── entity
```

Keep your application packages underneath the package containing your main class unless you have a reason to configure scanning differently.

---


# **8. `@Component`**

Let’s start with the most general annotation.

```java
@Component
public class EmailService {
}
```

This tells Spring:

“Create and manage this class as a bean.”

So:

```text
@Component
     ↓
Spring-managed object
```

---


# **9. `@Service`**

Now:

```java
@Service
public class ProductService {
}
```

`@Service` is a specialized form of component registration intended to communicate:

“This component contains application/service logic.”

It’s still a Spring-managed component.

Use:

```java
@Service
```

for your service layer.

---


# **10. `@Repository`**

Similarly:

```java
@Repository
public class ProductRepository {
}
```

This communicates:

“This component is responsible for persistence/data access.”

With Spring Data JPA, you’ll often see interfaces instead:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
```

We will get to that later.

For now, understand the conceptual layer:

```text
Controller
    ↓
Service
    ↓
Repository
    ↓
Database
```

---


# **11.**  `@Controller` vs `@RestController`

For web applications:

```java
@Controller
```

is associated with Spring MVC controllers.

And:

```java
@RestController
```

is what you’ll commonly use for REST APIs.

For example:

```java
@RestController
public class ProductController {

    @GetMapping("/products")
    public String getProduct() {
        return "Laptop";
    }
}
```

The return value becomes part of the HTTP response.

We’ll go deeply into REST controllers later.

---


# **12. What’s special about**

**`@SpringBootApplication`**

**?**

You’ve seen:

```java
@SpringBootApplication
public class DemoApplication {
}
```

This annotation is extremely important.

Conceptually, it combines several Spring features, including:

```text
@SpringBootConfiguration
@EnableAutoConfiguration
@ComponentScan
```

You don’t need to memorize that yet.

The important one for today’s lesson is:

```text
@ComponentScan
```

It tells Spring to scan for components.

So your main class effectively establishes the starting point for discovering your application components.

---

# **13. Bean lifecycle**

Spring doesn’t just create objects.

It manages their lifecycle.

Very roughly:

```text
Application starts
       ↓
Spring creates bean
       ↓
Dependencies injected
       ↓
Initialization
       ↓
Bean available
       ↓
Application runs
       ↓
Application shuts down
       ↓
Bean destroyed
```

Later we’ll learn lifecycle hooks such as:

```java
@PostConstruct
```

and:

```java
@PreDestroy
```

These can be useful when a bean needs initialization or cleanup.

---

# **14. Singleton — an important concept**

By default, Spring beans are **singleton scoped**.

For example:

```java
@Service
public class ProductService {
}
```

Normally Spring creates one instance of `ProductService` in the application context.

So if:

```java
ProductController
```

needs `ProductService` and another component also needs `ProductService`, they normally receive the same managed instance.

Conceptually:

```text
             ProductService
                    ▲
                   / \
                  /   \
                 /     \
                ▼       ▼
       ProductController
       
       AnotherComponent
```

There isn’t normally a new `ProductService` created for every injection.

This is why you should **not put request-specific mutable state inside singleton services**.

For example, don’t do:

```java
@Service
public class ProductService {

    private String currentUser;
}
```

and modify it for every HTTP request.

Multiple requests can use the same bean concurrently.

We’ll discuss concurrency and bean scopes later.

---

# **15. Singleton does NOT mean one object for the entire JVM**

This distinction matters.

Spring’s default singleton means roughly:

One bean instance per Spring `ApplicationContext`.

It’s not a universal Java singleton like:

```java
public static ProductService INSTANCE;
```

Spring manages the lifecycle and scope.

---

# **16. Bean scopes**

Spring supports different scopes.

The major ones you’ll encounter include:

```text
singleton
prototype
request
session
application
```

For example:

```java
@Scope("prototype")
@Component
public class SomeComponent {
}
```

This tells Spring that a new instance can be created when requested rather than using the default singleton behavior.

For normal services/controllers/repositories, you’ll overwhelmingly use the default singleton scope.

---

# **17. A subtle but important concept: Bean definition vs Bean**

Spring internally doesn’t just immediately throw every object into a container.

It maintains metadata describing beans.

Conceptually:

```text
Bean Definition
       ↓
How should this bean be created?
       ↓
Class
Scope
Dependencies
Configuration
       ↓
Bean instance
```

You don’t normally interact with bean definitions directly, but understanding the distinction helps when we eventually discuss:

- configuration
- `@Bean`
- auto-configuration
- conditional beans
- profiles

---


# **18.**

**`@Component`**

**isn’t the only way to create a Bean**

This is very important.

You can also explicitly define beans using:

```java
@Configuration
public class AppConfig {

    @Bean
    public EmailService emailService() {
        return new EmailService();
    }
}
```

Now `EmailService` becomes a Spring bean.

So there are two broad patterns:

### **Component scanning**

```java
@Service
public class EmailService {
}
```

### **Explicit configuration**

```java
@Configuration
public class AppConfig {

    @Bean
    EmailService emailService() {
        return new EmailService();
    }
}
```

We’ll spend an entire lesson on `@Configuration` and `@Bean`.

---



# **19. When is `@Bean` useful?**

Suppose you’re using a third-party library.

You don’t own this class:

```java
SomeThirdPartyClient
```

You can’t modify it to add:

```java
@Component
```

So you can configure it yourself:

```java
@Configuration
public class AppConfig {

    @Bean
    public SomeThirdPartyClient client() {
        return new SomeThirdPartyClient();
    }
}
```

Now Spring manages it.

This becomes extremely useful when configuring:

- HTTP clients
- database-related components
- SDKs
- serializers
- custom infrastructure
- third-party libraries

---

# **20. The complete picture**

At this point, your mental model should look like this:

```text
                   Spring Boot
                       │
                       ▼
              ApplicationContext
                       │
                Component Scan
                       │
       ┌───────────────┼────────────────┐
       ▼               ▼                ▼
 @RestController    @Service        @Repository
       │               │                │
       └───────────────┼────────────────┘
                       │
                       ▼
                 Spring Beans
                       │
                       ▼
              Dependency Injection
```

And then your application code:

```text
HTTP
 │
 ▼
Controller
 │
 ▼
Service
 │
 ▼
Repository
 │
 ▼
Database
```

Spring is primarily taking care of the **object creation, wiring, lifecycle, and infrastructure around this application**.

---
