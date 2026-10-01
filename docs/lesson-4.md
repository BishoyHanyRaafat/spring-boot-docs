---
title: Lesson 4: —@Bean, @Configuration,@Primary, and @Qualifier
sidebar_position: 4
---


Today we’re going to solve two important problems:

1. **How do I explicitly create a Spring Bean?**
2. **What happens when Spring has multiple implementations of the same interface?**

These are concepts you’ll use constantly in real Spring applications.

---

# Part 1 —`@Bean`  and `@Configuration`

We’ve already seen:

```java
@Service
public class EmailService {
}
```

Spring discovers it automatically through component scanning.

But sometimes you want to create the bean yourself.

That’s where `@Bean` comes in.

## 

## **1. Basic**

**`@Bean`**

```java
@Configuration
public class AppConfig {

    @Bean
    public EmailService emailService() {
        return new EmailService();
    }
}
```

Now Spring sees:

```java
@Bean
public EmailService emailService()
```

and registers the returned object as a Spring Bean.

Conceptually:

```text
@Configuration
       ↓
AppConfig
       ↓
@Bean
       ↓
new EmailService()
       ↓
Spring Bean
```

---

# **2. Why would we need this?**

You might wonder:

“Why not just use `@Service` everywhere?”

Good question.

Suppose you have a class you own:

```java
@Service
public class EmailService {
}
```

That’s easy.

But suppose you use a third-party library:

```java
SomeHttpClient
```

You can’t modify the library and add:

```java
@Component
```

So you configure it:

```java
@Configuration
public class AppConfig {

    @Bean
    public SomeHttpClient httpClient() {
        return new SomeHttpClient();
    }
}
```

Now Spring manages it.

This pattern is extremely common.

---


# 3. `@Configuration`

This:

```java
@Configuration
public class AppConfig {
}
```

basically tells Spring:

“This class contains configuration for the application.”

Then:

```java
@Bean
public SomeObject someObject() {
    return new SomeObject();
}
```

defines a bean.

So:

```text
@Configuration
       │
       ├── @Bean
       ├── @Bean
       └── @Bean
```

You might have:

```java
@Configuration
public class AppConfig {

    @Bean
    public EmailService emailService() {
        return new EmailService();
    }

    @Bean
    public SmsService smsService() {
        return new SmsService();
    }
}
```

Spring now manages both.

---


# 4.`@Bean`  **vs** @Component`

This distinction is worth memorizing conceptually.

### **`@Component`**

You’re saying:

“Spring, discover this class and manage it.”

```java
@Component
public class EmailService {
}
```

### **`@Bean`**

You’re saying:

“Spring, use this method to create the object and manage the returned object.”

```java
@Configuration
public class AppConfig {

    @Bean
    public EmailService emailService() {
        return new EmailService();
    }
}
```

So:

```text
@Component
    → component scanning

@Bean
    → explicit configuration
```

---

# **Part 2 — Multiple implementations**

Now let’s tackle a very common situation.

Imagine we have:

```java
public interface NotificationService {

    void send(String message);
}
```

We have an email implementation:

```java
@Service
public class EmailNotificationService
        implements NotificationService {

    @Override
    public void send(String message) {
        System.out.println("Email: " + message);
    }
}
```

And an SMS implementation:

```java
@Service
public class SmsNotificationService
        implements NotificationService {

    @Override
    public void send(String message) {
        System.out.println("SMS: " + message);
    }
}
```

So now Spring has:

```text
             NotificationService
                    ▲
                   / \
                  /   \
                 /     \
                ▼       ▼
             Email     SMS
```

Both are beans.

---

# **5. Now the problem**

Suppose:

```java
@Service
public class UserService {

    private final NotificationService notificationService;

    public UserService(NotificationService notificationService) {
        this.notificationService = notificationService;
    }
}
```

Spring asks:

“Which `NotificationService` should I inject?”

There are two:

```text
EmailNotificationService
SmsNotificationService
```

Spring can’t choose automatically.

You’ll get an error because the dependency is ambiguous.

---


# **6. Solution #1 —**

**`@Primary`**

Suppose email should be the default.

```java
@Service
@Primary
public class EmailNotificationService
        implements NotificationService {

    @Override
    public void send(String message) {
        System.out.println("Email: " + message);
    }
}
```

Now when Spring sees:

```java
NotificationService notificationService
```

it chooses the `@Primary` implementation.

So:

```text
NotificationService
       │
       ├── Email ← @Primary
       │
       └── SMS
```

Then:

```java
@Service
public class UserService {

    private final NotificationService notificationService;

    public UserService(NotificationService notificationService) {
        this.notificationService = notificationService;
    }
}
```

gets:

```text
EmailNotificationService
```

---



# **7. Solution #2 —**

**`@Qualifier`**

But sometimes you don’t want a global default.

You want to explicitly say:

“This particular class needs SMS.”

Then use `@Qualifier`.

First, give your beans names:

```java
@Service("email")
public class EmailNotificationService
        implements NotificationService {

    @Override
    public void send(String message) {
        System.out.println("Email");
    }
}
```

```java
@Service("sms")
public class SmsNotificationService
        implements NotificationService {

    @Override
    public void send(String message) {
        System.out.println("SMS");
    }
}
```

Then:

```java
@Service
public class UserService {

    private final NotificationService notificationService;

    public UserService(
            @Qualifier("sms")
            NotificationService notificationService
    ) {
        this.notificationService = notificationService;
    }
}
```

Now Spring knows exactly which bean you want.

```text
UserService
     │
     │ @Qualifier("sms")
     ▼
SmsNotificationService
```

---


# 8. `@Primary` vs `@Qualifier`

Think of them this way:

### **`@Primary`**

“This is the default implementation.”

```java
@Primary
@Service
public class EmailNotificationService {
}
```

### **`@Qualifier`**

“I specifically want this implementation here.”

```java
public UserService(
    @Qualifier("sms")
    NotificationService notificationService
) {
}
```

A useful rule:

```text
One obvious default?
    → @Primary

Need a specific implementation?
    → @Qualifier
```

---

# **9. You can also use qualifiers without custom bean names**

For example:

```java
@Service
@Qualifier("email")
public class EmailNotificationService
        implements NotificationService {
}
```

and:

```java
@Service
@Qualifier("sms")
public class SmsNotificationService
        implements NotificationService {
}
```

Then:

```java
public UserService(
    @Qualifier("sms")
    NotificationService notificationService
) {
    this.notificationService = notificationService;
}
```

We’ll generally use clear names rather than relying on class-name-derived bean names.

---

# **Part 3 — Injecting all implementations**

Here’s another useful situation.

Maybe you don’t want just one notification service.

You want **all** of them.

Spring can inject a collection:

```java
@Service
public class NotificationManager {

    private final List<NotificationService> services;

    public NotificationManager(
            List<NotificationService> services
    ) {
        this.services = services;
    }
}
```

Spring can provide:

```text
List<NotificationService>

[
    EmailNotificationService,
    SmsNotificationService
]
```

Now you could do:

```java
public void notifyAll(String message) {

    for (NotificationService service : services) {
        service.send(message);
    }
}
```

This pattern becomes very powerful when you have plugin-like behavior.

---

# **10. Ordering implementations**

Suppose you want:

```text
1. Email
2. SMS
3. Push
```

You can use `@Order`.

For example:

```java
@Service
@Order(1)
public class EmailNotificationService
        implements NotificationService {
}
```

```java
@Service
@Order(2)
public class SmsNotificationService
        implements NotificationService {
}
```

When Spring injects the list, the ordering can be respected.

We’ll revisit this when we talk about Spring’s collection injection.

---

# **Part 4 — A realistic example**

Imagine we’re building our ProjectHub backend.

We have:

```text
NotificationService
```

with:

```java
public interface NotificationService {

    void send(User user, String message);
}
```

Then:

```text
EmailNotificationService
SmsNotificationService
PushNotificationService
```

All implement it.

Now a service might say:

```java
public UserService(
    @Qualifier("email")
    NotificationService notificationService
) {
    this.notificationService = notificationService;
}
```

The business logic doesn’t need to know:

```text
How is the email client created?
Which library is being used?
How is the SMTP connection configured?
```

Those concerns can live in configuration.

That’s one of the major benefits of dependency injection.

---

# **Part 5 — One more important distinction**

There are two different questions:

### **“Which object should Spring create?”**

That’s where:

```text
@Component
@Service
@Repository
@Bean
```

come in.

### **“Which implementation should Spring inject?”**

That’s where:

```text
@Primary
@Qualifier
```

come in.

Keep these two ideas separate.

---

# **Part 6 — A common mistake**

Don’t do this:

```java
@Service
public class UserService {

    private final EmailNotificationService service =
        new EmailNotificationService();
}
```

You’ve just bypassed Spring.

You lose the benefit of dependency injection.

Instead:

```java
@Service
public class UserService {

    private final NotificationService service;

    public UserService(
            @Qualifier("email")
            NotificationService service
    ) {
        this.service = service;
    }
}
```

Now Spring owns the dependency graph.

---

# **Part 7 — The mental model**

At this point, you should have:

```text
                   Spring Container
                         │
           ┌─────────────┼──────────────┐
           │             │              │
           ▼             ▼              ▼
      EmailService   UserService   ProductService
                         │
                         │
                    NotificationService
                         ▲
                    ┌────┴────┐
                    │         │
                  Email      SMS
                    │
                 @Primary
```

Spring’s job is essentially:

```text
Discover
   ↓
Register
   ↓
Create
   ↓
Resolve dependencies
   ↓
Inject
   ↓
Manage lifecycle
```

---

