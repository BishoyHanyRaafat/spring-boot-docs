---
title: Lesson 1: What problem does Spring actually solve?
sidebar_position: 1
---


We’ll start from **plain Java**, then introduce Spring. Don’t worry about Spring annotations yet.

## **1. The problem: objects creating their own dependencies**

Imagine we have a `UserService` that needs a `UserRepository`.

Without Spring:

```java
public class UserRepository {

    public void save() {
        System.out.println("Saving user...");
    }
}
```

And:

```java
public class UserService {

    private UserRepository repository;

    public UserService() {
        this.repository = new UserRepository();
    }

    public void createUser() {
        repository.save();
    }
}
```

This works.

But notice this line:

```java
this.repository = new UserRepository();
```

`UserService` is responsible for **creating** its dependency.

That’s where things start getting messy.

---

# **2. Why is that a problem?**

Imagine `UserRepository` eventually needs a database:

```java
public class UserRepository {

    private final Database database;

    public UserRepository(Database database) {
        this.database = database;
    }
}
```

Now `UserService` has to know how to construct everything:

```java
public UserService() {
    Database database = new Database(...);
    UserRepository repository = new UserRepository(database);

    this.repository = repository;
}
```

And maybe `Database` needs configuration.

And another service needs `UserService`.

And another service needs that service.

You can end up with:

```text
Controller
   ↓ creates
Service
   ↓ creates
Repository
   ↓ creates
Database
   ↓ creates
ConnectionPool
   ↓ creates
...
```

Your classes become responsible for **building the entire object graph**.

That’s not what we want.

---

# **3. Dependency Injection**

Instead, we can say:

“I don’t want `UserService` to create a `UserRepository`. Give me one.”

Like this:

```java
public class UserService {

    private final UserRepository repository;

    public UserService(UserRepository repository) {
        this.repository = repository;
    }

    public void createUser() {
        repository.save();
    }
}
```

Now `UserService` doesn’t care **how** `UserRepository` was created.

It just says:

```text
I need a UserRepository.
```

Something else provides it.

That is **Dependency Injection**.

---

# **4. What is a dependency?**

Look at:

```java
public class UserService {

    private final UserRepository repository;

    public UserService(UserRepository repository) {
        this.repository = repository;
    }
}
```

`UserService` depends on `UserRepository`.

Why?

Because `UserService` cannot do its job without it.

So:

```text
UserService
     │
     │ depends on
     ▼
UserRepository
```

`UserRepository` is therefore a **dependency** of `UserService`.

---

# **5. Who provides the dependency?**

Now we have another problem.

If `UserService` isn’t creating `UserRepository`…

**Who is?**

This is where Spring comes in.

Spring can act as the object manager.

Conceptually:

```text
             Spring
                │
       ┌────────┴────────┐
       │                 │
       ▼                 ▼
 UserRepository      UserService
                          │
                          │ needs
                          ▼
                   UserRepository
```

Spring creates the objects and connects them together.

This is the basic idea behind **Inversion of Control (IoC)**.

---

# **6. Inversion of Control**

Normally, your code controls object creation:

```java
UserRepository repository = new UserRepository();
```

With Spring, the framework controls it.

Conceptually:

```text
You:
    "Spring, I need a UserService."

Spring:
    "Okay."

Spring:
    creates UserRepository

Spring:
    creates UserService
    and gives it UserRepository

Spring:
    gives UserService to your application
```

The control of object creation has moved from your code to the framework.

That’s why it’s called:

**Inversion of Control**

---

# **7. Now let’s actually use Spring**

Spring needs to know which classes it should manage.

We can tell it:

```java
@Service
public class UserService {

    private final UserRepository repository;

    public UserService(UserRepository repository) {
        this.repository = repository;
    }
}
```

And:

```java
@Repository
public class UserRepository {

    public void save() {
        System.out.println("Saving...");
    }
}
```

The annotations tell Spring:

```text
@Service
    ↓
"Spring, manage this class."

@Repository
    ↓
"Spring, manage this class."
```

These managed objects are called **beans**.

---

# **8. What is a Bean?**

This is one of the most important Spring terms.

A **Spring Bean** is essentially an object whose lifecycle is managed by Spring.

For example:

```java
@Service
public class UserService {
}
```

Spring discovers this class and creates an instance.

Conceptually:

```java
UserService userService = new UserService(...);
```

But **Spring** handles the creation and dependencies.

---

# **9. Constructor Injection**

This:

```java
@Service
public class UserService {

    private final UserRepository repository;

    public UserService(UserRepository repository) {
        this.repository = repository;
    }
}
```

is called **constructor injection**.

This is generally the style I want you to use.

Why?

Because the dependency is explicit.

You can immediately see:

```text
UserService requires UserRepository
```

And because it’s `final`, the dependency can’t accidentally be replaced later.

---

# **10. Spring builds the object graph**

Suppose we have:

```java
@Repository
public class UserRepository {
}
```

```java
@Service
public class UserService {

    private final UserRepository repository;

    public UserService(UserRepository repository) {
        this.repository = repository;
    }
}
```

```java
@RestController
public class UserController {

    private final UserService service;

    public UserController(UserService service) {
        this.service = service;
    }
}
```

The dependency graph is:

```text
UserController
      │
      ▼
 UserService
      │
      ▼
UserRepository
```

Spring sees this and effectively constructs:

```text
UserRepository
      ↓
UserService(UserRepository)
      ↓
UserController(UserService)
```

That’s one of the fundamental things Spring does for you.

---

# **11. Why this becomes powerful**

Imagine later we replace:

```java
UserRepository
```

with:

```java
PostgresUserRepository
```

or:

```java
MockUserRepository
```

or:

```java
CachedUserRepository
```

The service doesn’t necessarily need to know how they’re constructed.

This leads us to an extremely important programming concept:

## **Programming against abstractions**

Instead of:

```java
public class UserService {

    private final PostgresUserRepository repository;

    public UserService(PostgresUserRepository repository) {
        this.repository = repository;
    }
}
```

we can eventually do:

```java
public class UserService {

    private final UserRepository repository;

    public UserService(UserRepository repository) {
        this.repository = repository;
    }
}
```

where:

```java
public interface UserRepository {
    void save();
}
```

and:

```java
public class PostgresUserRepository implements UserRepository {
    
    @Override
    public void save() {
        // PostgreSQL implementation
    }
}
```

Now:

```text
UserService
     │
     │ depends on abstraction
     ▼
UserRepository
     ▲
     │
PostgresUserRepository
```

This is where Spring’s dependency injection becomes particularly useful.

---

# **12. One thing I don’t want you to memorize**

Don’t memorize:

`@Service` means service.

Instead understand:

**Spring needs to know which objects it should manage.**

`@Service`, `@Repository`, `@Controller`, and `@Component` are ways of participating in Spring’s component management.

We’ll learn the differences later.

---

# **13. The mental model I want you to have**

When you see:

```java
@Service
public class OrderService {

    private final PaymentService paymentService;

    public OrderService(PaymentService paymentService) {
        this.paymentService = paymentService;
    }
}
```

Think:

```text
Spring:

"I need to create OrderService."

"OrderService requires PaymentService."

"I'll find/create PaymentService."

"Then I'll give it to OrderService."

"Now OrderService is ready."
```

Not:

“Spring magically injects stuff.”

There is a real object graph being constructed.

---


should have:

```java
void sendEmail()
```

`UserService` should depend on `EmailService`.

`UserController` should depend on `UserService`.

**Use constructor injection manually**, like:

```java
new EmailService()
new UserService(emailService)
new UserController(userService)
```
