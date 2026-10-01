---
title: Lesson 87: Testing Kafka and the Outbox
sidebar_position: 87
---

We’re going to make this one concise.

The critical flow is:

```text
DB transaction
     ↓
Post + Outbox
     ↓
Outbox publisher
     ↓
Kafka
     ↓
Consumer
```

We need to test **each boundary**.

### **Test 1 — Outbox transaction**

```text
create post
   ↓
Post exists
   ↓
Outbox exists
```

Both should be committed together.

### **Test 2 — Publisher**

```text
PENDING outbox
   ↓
Kafka publish
   ↓
PUBLISHED
```

### **Test 3 — Consumer**

```text
Kafka event
   ↓
consumer
   ↓
business change
```

### **Test 4 — Duplicate**

```text
same event twice
       ↓
business action once
```

That’s our idempotency guarantee.

### **Test 5 — Failure**

```text
consumer fails
     ↓
retry
     ↓
DLT
```

For these tests, Testcontainers can provide real Kafka when we want infrastructure-level confidence.

---

# **The key lesson**

Don’t test Kafka itself.

Test **your behavior around Kafka**.

Bad:

“Kafka successfully stores messages.”

Useful:

“When `PostCreated` is consumed, ProjectHub creates the expected notification.”

And:

“When the same `eventId` is delivered twice, the notification is created only once.”

That’s the level of testing that matters.

---

## **Testing phase: DONE ✅**

We’ve now covered:

```text
JUnit
Mockito
@WebMvcTest
MockMvc
Security tests
@DataJpaTest
PostgreSQL
Testcontainers
@SpringBootTest
Kafka/Outbox testing
```

So we’re moving on.

# **Lesson 88 — Production Configuration & Environment Management**

This is our last major phase.

We’ll cover:

```text
application.yaml
      ↓
profiles
      ↓
environment variables
      ↓
secrets
      ↓
Docker
      ↓
Kubernetes
      ↓
CI/CD
```

Then we’ll finish the series with **production architecture, observability, performance, and the final ProjectHub architecture**.