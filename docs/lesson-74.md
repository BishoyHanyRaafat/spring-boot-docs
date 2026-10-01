---
title: "Lesson 74: Kafka Reliability Retries, DLTs & Idempotency"
sidebar_position: 74
---

Now we’re getting into the part that actually makes Kafka production-worthy.

Our basic pipeline was:

```text
Producer
   ↓
Kafka topic
   ↓
@KafkaListener
   ↓
Business logic
```

But what happens when business logic fails?

For example:

```text
Kafka
  ↓
PostCreated
  ↓
NotificationService
  ↓
Email provider
  ↓
💥 timeout
```

We need a strategy.

Spring Kafka 4.1.1 provides `DefaultErrorHandler`, retry/backoff support, `DeadLetterPublishingRecoverer`, and `@RetryableTopic` for these scenarios.  

---

# **1. First principle: not every failure is the same**

Suppose our consumer gets:

```text
PostCreated
```

and processing fails.

There are at least two fundamentally different possibilities.

### **Temporary failure**

```text
Database temporarily unavailable
HTTP timeout
Rate limit
Network failure
```

Trying again may succeed.

### **Permanent failure**

```text
Invalid event
Unsupported event version
Corrupt payload
Business rule violation
```

Trying again 1,000 times won’t fix it.

So:

```text
temporary → retry

permanent → recover / DLT
```

That’s the foundation.

---

# **2. The naive implementation**

Imagine:

```java
@KafkaListener(
        topics = "projecthub.events",
        groupId = "notifications"
)
public void consume(PostCreatedEvent event) {

    notificationService.send(event);
}
```

And:

```java
notificationService.send(event);
```

throws an exception.

What should happen?

If we simply keep retrying forever:

```text
PostCreated
   ↓
FAIL
   ↓
retry
   ↓
FAIL
   ↓
retry
   ↓
FAIL
   ↓
...
```

we’ve created a **poison message**.

One bad record can prevent useful progress.

---

# **3. Retry with backoff**

A retry strategy should generally look more like:

```text
attempt 1
   ↓
failure
   ↓
wait
   ↓
attempt 2
   ↓
failure
   ↓
wait longer
   ↓
attempt 3
   ↓
failure
   ↓
DLT
```

That waiting period is called **backoff**.

For example:

```text
1 second
5 seconds
30 seconds
```

The exact numbers depend on the application.

---

# 

# **4. Spring’s**

**`DefaultErrorHandler`**

Spring Kafka provides:

```text
DefaultErrorHandler
```

for handling listener exceptions.

It can work with a `BackOff` and, when retries are exhausted, a recoverer such as `DeadLetterPublishingRecoverer`.  

Conceptually:

```text
@KafkaListener
      ↓
exception
      ↓
DefaultErrorHandler
      ↓
retry/backoff
      ↓
recoverer
```

---

# **5. Fixed backoff**

For our first example:

```text
1 second between attempts
2 retries
```

means:

```text
initial attempt
retry #1
retry #2
then recover
```

Spring’s documentation demonstrates this pattern using `FixedBackOff`.  

Conceptually:

```java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1000L, 2L)
    );
}
```

The important part isn’t memorizing the constructor.

Understand the policy:

```text
retry twice
wait 1 second between attempts
then recover
```

---

# **6. What is the recoverer?**

A recoverer answers:

“We’ve decided we’re done retrying. What do we do with this record?”

Spring provides:

```text
DeadLetterPublishingRecoverer
```

which can publish the failed record to another Kafka topic.  

So our flow becomes:

```text
projecthub.events
       ↓
notifications consumer
       ↓
       💥
       ↓
retry
       ↓
retry
       ↓
retry exhausted
       ↓
projecthub.events.DLT
```

---

# **7. Dead Letter Topic**

With Kafka, you’ll commonly hear:

```text
DLT
```

meaning:

**Dead Letter Topic**

It’s the Kafka equivalent of the dead-letter destination we’ve discussed with RabbitMQ.

For example:

```text
projecthub.events
projecthub.events.DLT
```

A failed record can be moved to the DLT after its retry policy is exhausted.

With Spring’s default `DeadLetterPublishingRecoverer` destination convention, the DLT is commonly the original topic plus `-dlt`, and the default resolver preserves the original partition.  

---

# **8. Why not just delete the bad message?**

Because that destroys information.

Suppose:

```text
PostCreated
```

failed because of:

```text
unexpected application bug
```

If we discard it:

```text
Kafka
 ↓
💥
 ↓
gone
```

we’ve lost the ability to investigate it.

Instead:

```text
Kafka
 ↓
💥
 ↓
DLT
```

Now operations can inspect:

```text
event
exception
headers
partition
offset
```

Spring adds exception-related DLT headers when publishing through `DeadLetterPublishingRecoverer`.  

---

# **9. DLT doesn’t mean “problem solved”**

Very important.

A DLT is not a trash can.

It’s more like:

**quarantine.**

You should eventually answer:

```text
Why did this event fail?
```

Then possibly:

```text
fix application
   ↓
reprocess DLT event
```

or:

```text
mark permanently invalid
```

---

# **10. Retry topology**

There are two broad approaches you’ll encounter.

### **Blocking retry**

```text
consumer
   ↓
failure
   ↓
wait
   ↓
retry
```

The consumer processing path waits according to the backoff.

### **Non-blocking retry**

The failed record can be routed through retry topics:

```text
main
 ↓
retry-1
 ↓
retry-2
 ↓
DLT
```

Spring Kafka supports this with `@RetryableTopic`.  

For now, learn the first approach first.

It makes the underlying mechanics easier to understand.

---

# **11. Why non-blocking retries exist**

Imagine:

```text
Partition 0

A
B
C
D
```

Suppose A fails and needs to wait 5 minutes.

If we’re doing blocking retry, we can create undesirable delays for subsequent records depending on listener/container configuration.

A retry-topic architecture can instead move A into a retry flow:

```text
main topic
   │
   ├── A → retry topic
   │
   ├── B → continue
   ├── C → continue
   └── D → continue
```

That’s useful when you need delayed retries without tying up the main consumption path.

But it introduces additional topics and ordering considerations.

---

# **12. Ordering gets interesting**

Remember Lesson 71.

Suppose:

```text
PostCreated version 1
PostUpdated version 2
```

arrive in order.

Now:

```text
version 1 → fails → retry
version 2 → succeeds
```

You could temporarily have:

```text
v2 processed
v1 waiting
```

That’s one reason retry architecture and ordering requirements have to be considered together.

If your business requires strict per-aggregate ordering, you can’t blindly bolt retries onto the system.

---

# **13. Now the really important part: duplicates**

Suppose our consumer does:

```text
process event
    ↓
database commit succeeds
    ↓
application crashes
    ↓
offset wasn't committed
```

Kafka may process the event again.

So:

```text
PostCreated
   ↓
process
   ↓
SUCCESS
   ↓
crash
   ↓
PostCreated AGAIN
```

This is why our earlier lesson emphasized:

**at-least-once delivery means your consumer must tolerate duplicates.**

---

# **14. Idempotency**

An operation is idempotent when repeating it produces the same intended final result.

For example:

```text
set user.email = "a@example.com"
```

is naturally easier to make idempotent than:

```text
send $100
```

because:

```text
send $100
send $100
```

is obviously not equivalent to one operation.

Our event consumers need to think carefully about this.

---

# 

# 

# **15.**

**`eventId`**

**is our idempotency key**

Remember:

```java
public record PostCreatedEvent(
        UUID eventId,
        int version,
        Instant occurredAt,
        Long postId,
        Long projectId,
        Long authorId
) {}
```

We can use:

```text
eventId
```

as the identity of the event.

Then maintain:

```sql
CREATE TABLE processed_events (
    event_id UUID PRIMARY KEY,
    processed_at TIMESTAMP WITH TIME ZONE NOT NULL
);
```

We’ve already seen this pattern with RabbitMQ.

It applies here too.

---

# **16. The critical transaction**

Suppose processing means:

```text
PostCreated
    ↓
create notification
```

We want:

```text
BEGIN

insert notification

insert processed_events(eventId)

COMMIT
```

Now suppose the same event arrives again.

We check:

```text
processed_events
```

and discover:

```text
eventId already exists
```

Therefore:

```text
don't perform business operation again
```

---

# **17. Why the unique constraint matters**

Don’t rely only on:

```java
if (alreadyProcessed(eventId)) {
    return;
}
```

because two consumers/processes could race.

Imagine:

```text
Consumer A:
check → not found

Consumer B:
check → not found
```

Both continue.

Instead, let PostgreSQL enforce uniqueness:

```sql
event_id UUID PRIMARY KEY
```

Then only one transaction can successfully insert that event ID.

This is a very powerful pattern:

**Use the database’s uniqueness constraint as part of your concurrency control.**

---

# **18. But be careful with the transaction boundary**

This is wrong:

```text
BEGIN
insert processed_events
COMMIT

send notification
```

because:

```text
processed_events = recorded
notification = failed
```

Now the retry sees the event as processed and won’t retry the notification.

Instead, for local database side effects:

```text
BEGIN

perform business change

record eventId

COMMIT
```

Then the business change and idempotency record succeed/fail together.

---

# **19. External side effects are harder**

Suppose our consumer does:

```text
Kafka event
   ↓
PostgreSQL
   ↓
Stripe/payment provider
```

You cannot make this magically atomic with a normal PostgreSQL transaction.

You might have:

```text
DB COMMIT
   ↓
payment API
   ↓
💥
```

or:

```text
payment succeeds
   ↓
DB transaction rolls back
```

So external side effects need their **own idempotency mechanisms** where supported.

This is the same principle we learned with the Outbox Pattern:

Database transactions don’t automatically include external systems.

---

# **20. Deserialization failure**

There’s another failure category:

```text
Kafka bytes
   ↓
JSON deserialization
   ↓
💥
```

Your listener might never even receive the Java object.

That’s why Spring Kafka provides:

```text
ErrorHandlingDeserializer
```

It can capture deserialization failures and make the failed record available to the container’s error-handling infrastructure.  

This is important because otherwise you might configure a beautiful business-level retry system but fail before business-level processing even begins.

---

# **21. Think in layers**

A robust Kafka consumer can have:

```text
Kafka record
     ↓
deserialization
     ↓
validation
     ↓
business processing
     ↓
database transaction
     ↓
offset progress
```

Each layer can fail differently.

For example:

|**Failure**|**Typical response**|
|---|---|
|Temporary DB outage|Retry|
|HTTP timeout|Retry|
|Rate limit|Retry/backoff|
|Invalid JSON|DLT|
|Unsupported event version|Usually DLT|
|Business invariant violation|Usually DLT / explicit rejection|
|Duplicate event|Ignore safely|
|External API duplicate|Provider idempotency key|

---

# **22. Don’t retry everything**

This is a major production lesson.

Suppose:

```text
event:
postId = -1
```

and validation says:

```text
postId must be positive
```

Retrying:

```text
1 sec
5 sec
30 sec
5 min
```

doesn’t make the event valid.

That’s wasted work.

Instead:

```text
invalid event
   ↓
DLT
```

---

# **23. Retry transient failures**

Suppose:

```text
PostCreated
   ↓
Notification Service
   ↓
HTTP 503
```

That’s different.

The service may recover.

So:

```text
503
 ↓
wait
 ↓
retry
```

makes sense.

The art is determining which failures are **transient** and which are **permanent**.

---

# **24. A useful ProjectHub policy**

For our project, we could conceptually define:

```text
PostCreated
     ↓
Notification Consumer
     │
     ├── success
     │
     ├── duplicate → ignore
     │
     ├── transient failure
     │       ↓
     │     retry
     │
     └── permanent failure
             ↓
            DLT
```

That’s the architecture I want you to have in your head before we write configuration.

---

# **25. RabbitMQ vs Kafka reliability**

Now compare the two systems we’ve learned.

### **RabbitMQ**

```text
delivery
   ↓
consumer ACK
   ↓
message completion
```

Failure:

```text
no ACK
   ↓
redelivery/retry policy
```

### **Kafka**

```text
record
   ↓
processing
   ↓
offset progress/commit
```

Failure:

```text
processing failure
   ↓
retry/recovery
   ↓
offset handling
```

Both require:

```text
idempotent consumers
```

when processing can be repeated.

---

# **26. DLT vs Outbox**

Don’t mix these up.

### **Outbox**

Protects:

```text
Database → Message Broker
```

against the dual-write problem.

```text
DB change + outbox
       ↓
    COMMIT
       ↓
publisher
       ↓
Kafka
```

### **DLT**

Protects:

```text
Message Broker → Consumer
```

from permanently failing records.

```text
Kafka
 ↓
consumer
 ↓
retries exhausted
 ↓
DLT
```

Different problems.

---

# **27. The complete ProjectHub reliability architecture**

Now we have:

```text
                 PostgreSQL
                     │
             ┌───────┴───────┐
             │               │
          Post row       Outbox row
             │               │
             └────── COMMIT ─┘
                     │
                     ▼
              Outbox Publisher
                     │
                     ▼
              Kafka Topic
             projecthub.events
                     │
             ┌───────┴────────┐
             ↓                ↓
      Notifications       Analytics
        consumer            consumer
             │
       ┌─────┴──────┐
       ↓            ↓
    success       failure
                    │
              ┌─────┴─────┐
              ↓           ↓
            retry        DLT
```

And the consumer itself:

```text
Kafka
  ↓
deserialize
  ↓
validate
  ↓
idempotency check
  ↓
business transaction
  ↓
successful offset progress
```

That’s becoming a real production architecture.

---

# 

# **28. One more Spring option:**

**`@RetryableTopic`**

Spring Kafka also provides:

```java
@RetryableTopic
```

which can configure non-blocking retry topics around a listener.  

Conceptually:

```text
projecthub.events
       ↓
projecthub.events-retry
       ↓
projecthub.events-retry
       ↓
projecthub.events-dlt
```

It’s convenient, but **don’t start there**.

I want you to understand `DefaultErrorHandler` first because then `@RetryableTopic` becomes a useful abstraction rather than magic.

---

# **29. Exercise 74**

Now implement the reliability layer.

### **Step 1**

Create a listener that intentionally fails:

```text
postId = 999
```

For example:

```text
if postId == 999:
    throw ...
```

---

### **Step 2**

Configure:

```text
DefaultErrorHandler
```

with:

```text
2 retries
1 second backoff
```

Observe:

```text
attempt 1
attempt 2
attempt 3
```

then recovery.

---

### **Step 3**

Configure:

```text
DeadLetterPublishingRecoverer
```

and verify the failed record arrives in:

```text
projecthub.events.DLT
```

---

### **Step 4**

Create:

```text
processed_events
```

with:

```text
event_id PRIMARY KEY
```

Then deliberately publish the **same** **`eventId`** **twice**.

Your consumer should perform the business operation once.

Conceptually:

```text
event A
   ↓
process
   ↓
record eventId

event A again
   ↓
eventId already exists
   ↓
skip
```

---

### **Step 5 — The important questions**

Answer these in your own words:

1. Why shouldn’t every exception be retried?
2. What’s the difference between a retry and a DLT?
3. What’s the difference between a DLT and an Outbox?
4. Why can Kafka process the same record more than once?
5. Why is `eventId` useful for idempotency?
6. Why do we still need a database `PRIMARY KEY`/`UNIQUE` constraint?
7. Why must a local business change and its `processed_events` insert ideally be in the same transaction?
8. Why can’t a PostgreSQL transaction automatically make an external HTTP API call atomic?
9. What happens if a message can’t even be deserialized?
10. Why can retry strategy affect ordering?

Once you’ve worked through that, the next step is **Lesson 75 — Kafka + Outbox**, where we’ll replace our RabbitMQ publisher with a real Kafka outbox publisher and examine the tricky failure window:

```text
Kafka accepted event
       ↓
💥 publisher crashes
       ↓
outbox still says PROCESSING
```

That is where **at-least-once delivery, idempotency, publisher acknowledgements, and recovery** all come together.