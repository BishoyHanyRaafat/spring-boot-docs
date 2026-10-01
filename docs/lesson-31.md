---
title: Lesson 31: Production Logging
sidebar_position: 31
---

In the previous lesson, we learned that observability has three major pillars:

```text
Logs
Metrics
Traces
```

Today we’ll focus on **logs**.

The goal isn’t simply to learn `log.info()`.

We want to learn how to design logs that are actually useful when ProjectHub is running in production.

Spring Boot uses Commons Logging internally and, with the standard starters, Logback is the default logging implementation.  

---

## **1. Why logging matters**

Imagine this happens:

```text
User reports:
"Deleting my post returned 500."
```

You open the application.

Without useful logging:

```text
¯\_(ツ)_/¯
```

With useful logging:

```text
2026-10-01 14:32:41 ERROR
Post deletion failed
postId=42
userId=17
reason=database timeout
```

Now you have somewhere to start.

Logging is primarily an **investigation tool**.

---

# 

# **2. Don’t use**

**`System.out.println`**

You’ve probably written:

```java
System.out.println("Creating post");
```

Don’t use that for application logging.

Instead:

```java
log.info("Creating post");
```

Why?

A logging framework gives you:

- log levels
- timestamps
- logger names
- structured output
- exception handling
- configuration
- filtering
- correlation IDs
- integration with log aggregation systems

---

# **3. SLF4J**

In application code, you’ll commonly interact with **SLF4J**.

For example:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Service
public class PostService {

    private static final Logger log =
            LoggerFactory.getLogger(PostService.class);

}
```

Then:

```java
log.info("Creating post");
```

Spring Boot’s defaults take care of the underlying logging implementation, so you generally don’t need to manually configure a logging dependency just to start logging.  

---

# **4. Log levels**

The common levels are:

```text
TRACE
DEBUG
INFO
WARN
ERROR
```

Think of them as increasing severity.

### **TRACE**

Extremely detailed diagnostic information.

```java
log.trace("Entering createPost()");
```

Usually not enabled in production.

### **DEBUG**

Developer-oriented diagnostic information.

```java
log.debug("Creating post for project {}", projectId);
```

Very useful while investigating problems.

### **INFO**

Normal important application events.

```java
log.info("Post {} created", postId);
```

### **WARN**

Something unusual happened, but the application can continue.

```java
log.warn("User {} attempted an operation without membership", userId);
```

### **ERROR**

Something failed.

```java
log.error("Failed to create post {}", postId, exception);
```

---

# **5. Don’t log everything at INFO**

This is a common beginner mistake.

Imagine:

```java
log.info("Entering method");
log.info("Loading user");
log.info("Loading project");
log.info("Checking permission");
log.info("Loading post");
log.info("Saving post");
log.info("Leaving method");
```

One request could generate dozens of logs.

At scale:

```text
10,000 requests
×
20 log lines
=
200,000 log lines
```

Instead, INFO should generally represent meaningful operational events.

Detailed implementation information belongs at DEBUG/TRACE.

---

# **6. Parameterized logging**

Prefer:

```java
log.info("User {} created post {}", userId, postId);
```

over:

```java
log.info("User " + userId + " created post " + postId);
```

This is the normal SLF4J style.

For exceptions:

```java
log.error("Failed to create post {}", postId, exception);
```

Notice that the exception is passed separately.

That allows the logging framework to render the stack trace properly.

---

# **7. Never log passwords**

This is one of the most important rules.

Never:

```java
log.info("Login request: {}", loginRequest);
```

if `loginRequest` contains:

```text
username
password
```

You don’t want:

```text
password=mySecretPassword
```

in your logs.

Because production logs may be copied into:

```text
Cloud logging
SIEM
Log aggregation
Monitoring systems
Developer machines
Backups
```

A secret in a log can spread very far.

---

# **8. JWTs and refresh tokens**

Same principle.

Never:

```java
log.info("JWT: {}", accessToken);
```

Never:

```java
log.debug("Refresh token: {}", refreshToken);
```

Never log:

```text
Authorization: Bearer eyJ...
```

unless you have an extremely deliberate, sanitized debugging mechanism—and normally you don’t need to.

For ProjectHub, logs should contain information **about** authentication, not the credentials themselves.

Good:

```java
log.info("Authentication succeeded for user {}", username);
```

Potentially useful:

```java
log.warn("Authentication failed for username {}", username);
```

But be careful about whether usernames themselves are considered sensitive in your environment.

---

# **9. Log business events, not implementation noise**

Consider:

```java
public PostResponse createPost(...) {

    log.debug("Entering createPost");

    Post post = new Post();

    log.debug("Created Post object");

    post.setTitle(request.title());

    log.debug("Set title");

    repository.save(post);

    log.debug("Repository save completed");

    return mapper.toResponse(post);
}
```

That’s noisy.

Instead:

```java
log.info(
    "Post created: postId={}, projectId={}, authorId={}",
    post.getId(),
    projectId,
    authorId
);
```

One meaningful event.

---

# **10. Structured logging**

This becomes extremely important in production.

Traditional logs look like:

```text
2026-10-01 14:32:10 INFO
Post 42 created by user 17
```

A machine-readable log might look like:

```json
{
  "timestamp": "2026-10-01T14:32:10Z",
  "level": "INFO",
  "message": "Post created",
  "postId": 42,
  "userId": 17,
  "projectId": 7
}
```

Now a logging system can query:

```text
projectId = 7
```

or:

```text
postId = 42
```

without trying to parse human sentences.

Spring Boot 4.1 supports structured logging formats including ECS, GELF, and Logstash.  

---

# **11. Spring Boot structured logging**

For example, Spring Boot supports configuration such as:

```yaml
logging:
  structured:
    format:
      console: ecs
```

This produces structured JSON logging suitable for machine processing.  

This is particularly useful when logs are being shipped to something like:

```text
ProjectHub
    ↓
Docker stdout
    ↓
log collector
    ↓
central logging system
```

---

# **12. Key-value logging**

Spring Boot’s structured logging also supports adding key/value data through SLF4J’s fluent logging API.  

Conceptually:

```java
log.atInfo()
   .setMessage("Post created")
   .addKeyValue("postId", postId)
   .addKeyValue("projectId", projectId)
   .addKeyValue("userId", userId)
   .log();
```

Instead of embedding everything into a sentence:

```text
"Post 42 created in project 7 by user 17"
```

you’re explicitly saying:

```text
postId = 42
projectId = 7
userId = 17
```

That’s much easier for machines to understand.

---

# **13. Logging configuration**

Spring Boot allows you to configure logging levels.

For example:

```yaml
logging:
  level:
    root: INFO
    com.example.projecthub: DEBUG
```

This means:

```text
everything
   ↓
INFO+

ProjectHub
   ↓
DEBUG+
```

So your own application can be more verbose while third-party libraries remain quieter.

---

# **14. Development vs production**

This fits perfectly with our previous lesson on profiles.

### **Development**

```yaml
logging:
  level:
    com.example.projecthub: DEBUG
```

### **Production**

```yaml
logging:
  level:
    root: INFO
    com.example.projecthub: INFO
```

So:

```text
Development
    ↓
more diagnostic information

Production
    ↓
less noise
```

You can also change logger levels through Actuator at runtime when the relevant endpoint is enabled and secured. Spring Boot’s Actuator logger endpoint supports viewing and configuring logger levels.  

---

# **15. Correlation IDs**

Now we connect logging to tracing.

Imagine one HTTP request:

```text
POST /projects/7/posts
```

causes:

```text
Controller
    ↓
Service
    ↓
Database
    ↓
Message broker
    ↓
Notification service
```

You want to know which logs belong to the same request.

That’s where a **correlation ID** helps.

Conceptually:

```text
traceId = abc123
```

Then:

```text
[abc123] Creating post
[abc123] Checking membership
[abc123] Saving post
[abc123] Publishing notification
```

Now you can search for:

```text
abc123
```

and follow the request.

---

# **16. Spring Boot + Micrometer Tracing**

When Micrometer Tracing is configured, Spring Boot can include `traceId` and `spanId` in log correlation information by default.  

Conceptually:

```text
traceId = abc123
spanId  = xyz789
```

The important distinction:

```text
traceId
   ↓
whole distributed request

spanId
   ↓
one operation within that request
```

---

# **17. Example**

Imagine:

```text
traceId=ABC
```

The request enters ProjectHub:

```text
trace=ABC span=111
POST /projects/7/posts
```

Then database operation:

```text
trace=ABC span=222
SELECT post...
```

Then notification:

```text
trace=ABC span=333
publish notification
```

Same trace.

Different spans.

This is why tracing and logging complement each other.

---

# **18. MDC**

You may encounter this term:

**MDC — Mapped Diagnostic Context**

It allows contextual values to be associated with the current logging context.

Conceptually:

```java
MDC.put("requestId", requestId);
```

Then logging can include:

```text
requestId=abc123
```

Spring Boot’s tracing support uses MDC values for trace/span correlation.  

You don’t need to manually build an MDC-based correlation system yet.

Later we’ll let the tracing infrastructure handle most of this.

---

# **19. A warning about async code**

Context isn’t automatically magical.

Suppose:

```text
HTTP request
    ↓
thread A
    ↓
async task
    ↓
thread B
```

Context such as tracing information needs to be propagated correctly.

This becomes important when we eventually introduce:

```text
@Async
virtual threads
message queues
RabbitMQ/Kafka
```

That’s one reason we’ll learn observability before messaging.

---

# **20. Logging security events**

ProjectHub has an authentication/authorization system.

Some security events are worth logging.

For example:

```text
Authentication failure
Authorization denial
Suspicious repeated requests
Unexpected privilege changes
Refresh-token reuse detection
```

For example:

```java
log.warn(
    "Authorization denied: userId={}, action={}, postId={}",
    userId,
    "DELETE",
    postId
);
```

Notice what we’re **not** logging:

```text
JWT
password
refresh token
private key
```

---

# **21. Don’t turn logs into an audit database**

This is an important architectural distinction.

You might think:

“I’ll just log every important event and use the logs as my audit trail.”

Usually that’s not enough.

If ProjectHub needs an actual audit record:

```text
who
did what
to which resource
when
```

you may eventually create an **audit log/table/event system**.

For example:

```text
audit_events

id
actor_id
action
resource_type
resource_id
created_at
```

That’s different from operational logging.

### **Operational log**

```text
"Post deletion took 340ms"
```

### **Audit record**

```text
"User 17 deleted Post 42 at 14:32 UTC"
```

They serve different purposes.

---

# **22. ProjectHub logging strategy**

I’d like our application to eventually follow something like:

```text
ERROR
  ↓
Unexpected failures

WARN
  ↓
Security/operational anomalies

INFO
  ↓
Important business/application events

DEBUG
  ↓
Developer diagnostics

TRACE
  ↓
Very detailed diagnostics
```

And:

```text
Secrets
   ↓
NEVER LOG

Passwords
   ↓
NEVER LOG

JWTs
   ↓
NEVER LOG

Refresh tokens
   ↓
NEVER LOG
```

---

# **23. Our production architecture is getting serious**

We’re now building toward:

```text
                       ProjectHub
                           │
             ┌─────────────┼─────────────┐
             │             │             │
           Logs          Metrics        Traces
             │             │             │
             └─────────────┼─────────────┘
                           │
                     Observability
                           │
          ┌────────────────┼────────────────┐
          │                │                │
       Logging          Actuator         Tracing
          │                │                │
       SLF4J            Health          traceId
       Logback          Metrics         spanId
       JSON             Readiness
```

This is the foundation we’ll later connect to Docker and monitoring systems.

---

# **Exercise 31**

Don’t code yet. I want you to reason about logging.

### **1. Choose the appropriate level**

For each event:

```text
A. User successfully created a project
B. Developer needs SQL debugging information
C. Database connection unexpectedly failed
D. User attempted an operation they aren't authorized to perform
E. Extremely detailed method-level diagnostic information
```

Choose from:

```text
TRACE / DEBUG / INFO / WARN / ERROR
```

---

### **2. Which is dangerous?**

Which of these should **not** be logged?

```java
log.info("User {} created post {}", userId, postId);

log.info("Login succeeded for {}", username);

log.debug("JWT = {}", accessToken);

log.error("Failed to save post {}", postId, exception);

log.debug("Refresh token = {}", refreshToken);
```

Explain why.

---

### **3. Structured logging**

Convert this conceptual log:

```text
"User 17 created post 42 in project 7"
```

into structured fields:

```text
?
```

Think:

```text
userId = ?
postId = ?
projectId = ?
```

---

### **4. Tracing**

Suppose you see:

```text
traceId=ABC123
```

in five different log entries.

What does that tell you?

---

### **5. Architecture**

Explain the difference between:

```text
Operational logging
```

and:

```text
Audit logging
```

---

Once you’ve answered those, we’ll move to **Lesson 32 — Docker for Spring Boot**, where we’ll take the ProjectHub application we’ve built and package it into a real container.