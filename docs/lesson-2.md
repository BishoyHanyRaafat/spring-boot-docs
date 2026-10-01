---
title: Lesson 2: Letting Spring Build the Object Graph
sidebar_position: 2
---


In Lesson 1, you manually built this:

```text
UserController
      ↓
UserService
      ↓
EmailService
```

For example:

```java
EmailService emailService = new EmailService();

UserService userService =
        new UserService(emailService);

UserController userController =
        new UserController(userService);
```

The goal of Spring is to take responsibility for this wiring.

---

## **1. Create a Spring Boot project**

For our lessons, use:

- **Java 17+**; we’ll use Java 21+ examples when useful
- **Spring Boot 4.1.x**
- **Maven**
- Dependency: **Spring Web**

Create the project with Spring Initializr, which is the standard way to bootstrap Spring projects.

Your project will roughly look like:

```text
src/
 └── main/
      └── java/
           └── com.example.demo/
                └── DemoApplication.java
```

Your main class:

```java
@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Don’t worry about `@SpringBootApplication` yet. We’ll dissect it later.

---


# **2. Create**

**`EmailService`**

```java
@Service
public class EmailService {

    public void sendEmail() {
        System.out.println("Sending email...");
    }
}
```

The important part is:

```java
@Service
```

You’re telling Spring:

“I want Spring to manage an instance of this class.”

So when the application starts, Spring creates a bean for `EmailService`.

Conceptually:

```text
Spring Container
       │
       └── EmailService object
```

---


# **3. Create `UserService`**

```java
@Service
public class UserService {

    private final EmailService emailService;

    public UserService(EmailService emailService) {
        this.emailService = emailService;
    }

    public void createUser() {
        System.out.println("Creating user...");

        emailService.sendEmail();
    }
}
```

Notice something important.

We **didn’t** write:

```java
this.emailService = new EmailService();
```

Instead:

```java
public UserService(EmailService emailService)
```

We’re saying:

“I need an `EmailService`. Someone else should provide it.”

Spring sees that `UserService` needs `EmailService`.

Since `EmailService` is a Spring bean, Spring can provide it.

---


# **4. Create**

**`UserController`**

```java
@RestController
public class UserController {

    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    @GetMapping("/users")
    public String createUser() {
        userService.createUser();

        return "User created";
    }
}
```

Now our graph is:

```text
                    Spring
                      │
            ┌─────────┴─────────┐
            ▼                   ▼
     UserController        EmailService
            │
            ▼
       UserService
```

More accurately:

```text
UserController
      │
      │ requires
      ▼
UserService
      │
      │ requires
      ▼
EmailService
```

---

# **5. Start the application**

When Spring Boot starts, Spring discovers these classes.

It sees:

```java
@Service
public class EmailService
```

So it creates:

```text
EmailService bean
```

Then it sees:

```java
@Service
public class UserService
```

Spring examines its constructor:

```java
public UserService(EmailService emailService)
```

Spring says:

“UserService requires EmailService.”

It already has an `EmailService`, so it constructs:

```java
new UserService(emailService)
```

Then it sees:

```java
@RestController
public class UserController
```

Its constructor requires:

```java
UserService
```

Spring already has that too.

So conceptually:

```java
EmailService emailService =
        new EmailService();

UserService userService =
        new UserService(emailService);

UserController userController =
        new UserController(userService);
```

**Spring does the wiring.**

---

# **6. Try the endpoint**

Start your application and request:

```http
GET /users
```

The request reaches:

```java
UserController
```

which calls:

```java
userService.createUser();
```

which calls:

```java
emailService.sendEmail();
```

So:

```text
HTTP Request
     ↓
UserController
     ↓
UserService
     ↓
EmailService
     ↓
"Sending email..."
```

This is the basic Spring application flow.

---

# **7. What is the Spring Container?**

You’ll hear this constantly:

Spring Container

The container is responsible for managing Spring’s beans.

Think of it roughly as:

```text
┌────────────────────────────────────┐
│        Spring ApplicationContext   │
│                                    │
│  EmailService                      │
│  UserService                       │
│  UserController                    │
│  ...                               │
│                                    │
│  Dependency relationships          │
└────────────────────────────────────┘
```

The central interface you’ll encounter is:

```java
ApplicationContext
```

For now, think:

**ApplicationContext = Spring’s container that manages the application’s beans.**

We’ll eventually look at what it actually does internally.

---


# **8. `@Component`,`@Service`****, and `@Repository`

You might notice these:

```java
@Component
@Service
@Repository
@Controller
@RestController
```

They all participate in Spring’s component scanning, but they communicate different intentions.

For example:

```java
@Component
public class EmailService {
}
```

works.

And:

```java
@Service
public class EmailService {
}
```

also works.

`@Service` is essentially a more semantically meaningful specialization of `@Component`.

So:

```text
@Component
   │
   ├── @Service
   ├── @Repository
   └── @Controller
```

We’ll learn the precise behavior of each later.

For now:

```text
@Service
    → application/business service

@Repository
    → persistence/data access

@Controller
    → MVC controller

@RestController
    → REST controller

@Component
    → generic Spring-managed component
```

---

# **9. Why constructor injection matters**

Consider this:

```java
@Service
public class UserService {

    private final EmailService emailService;

    public UserService(EmailService emailService) {
        this.emailService = emailService;
    }
}
```

The class **cannot exist in a valid state without an** **`EmailService`**.

That’s good.

Compare that with field injection:

```java
@Service
public class UserService {

    @Autowired
    private EmailService emailService;
}
```

This hides the dependency.

Looking at the constructor tells you immediately:

```text
UserService requires EmailService
```

That’s one reason constructor injection is generally preferred.

---


# **10. You don’t need `@Autowired`**

**here**

You’ll see older tutorials write:

```java
@Autowired
public UserService(EmailService emailService) {
    this.emailService = emailService;
}
```

If the class has a **single constructor**, Spring can use that constructor without `@Autowired`.

So this is enough:

```java
public UserService(EmailService emailService) {
    this.emailService = emailService;
}
```

This is the style we’ll use.

---

# **11. What happens if Spring can’t find a dependency?**

Suppose you write:

```java
@Service
public class UserService {

    public UserService(PaymentService paymentService) {
    }
}
```

but `PaymentService` isn’t a Spring bean.

Spring can’t satisfy the dependency.

The application will fail during startup because it cannot construct `UserService`.

Conceptually:

```text
Spring:

Create UserService
       ↓
Need PaymentService
       ↓
Can't find PaymentService
       ↓
Application startup fails
```

This is actually useful.

Spring detects the broken dependency graph rather than letting your application run in an invalid state.

---

# **12. Multiple implementations**

Now things get interesting.

Suppose:

```java
public interface NotificationService {
    void notifyUser();
}
```

And we have:

```java
@Service
public class EmailNotificationService
        implements NotificationService {

    @Override
    public void notifyUser() {
        System.out.println("Email");
    }
}
```

and:

```java
@Service
public class SmsNotificationService
        implements NotificationService {

    @Override
    public void notifyUser() {
        System.out.println("SMS");
    }
}
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

Spring has a problem:

```text
NotificationService
       ↑
       │
 ┌─────┴──────┐
 │            │
Email         SMS
```

Which one should it inject?

This leads to:

- `@Qualifier`
- `@Primary`

We’ll learn these in the next lesson.

---

# **13. The big picture**

You should now understand this chain:

```text
              Spring Boot starts
                      │
                      ▼
             Spring ApplicationContext
                      │
                      ▼
               Finds components
                      │
                      ▼
              Creates Spring beans
                      │
                      ▼
            Resolves dependencies
                      │
                      ▼
             Injects dependencies
                      │
                      ▼
               Application ready
```

And our application:

```text
HTTP
 │
 ▼
UserController
 │
 ▼
UserService
 │
 ▼
EmailService
```

Spring handles the construction and wiring.

---

