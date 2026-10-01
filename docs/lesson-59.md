---
title: "Lesson 59: Distributed Systems"
sidebar_position: 59
---

We’ve now built a fairly serious mental model of ProjectHub:

```text
Spring Boot
   ↓
PostgreSQL
   ↓
Redis
   ↓
RabbitMQ
   ↓
Docker
   ↓
Kubernetes
```

But there’s a fundamental change when we scale out:

**Once multiple machines/processes participate in one logical system, coordination becomes a problem.**

This is the world of distributed systems.

---

# **1. What is a distributed system?**

A simple application:

```text
Client
  ↓
ProjectHub
  ↓
PostgreSQL
```

is already distributed across processes.

But imagine:

```text
                    ┌── Pod A ──┐
                    │           │
Client → Gateway ───┼── Pod B ──┼── PostgreSQL
                    │           │
                    └── Pod C ──┘
                         │
                    Redis/RabbitMQ
```

Now:

- multiple application instances exist
- network communication can fail
- data can exist in multiple places
- operations can happen concurrently
- clocks aren’t perfectly synchronized
- one component can succeed while another fails

These create entirely new classes of problems.

---

# **2. The network is not reliable**

In a single-process application:

```java
service.createProject();
```

is a local method call.

If the method returns, you generally know what happened.

A network call is different:

```text
ProjectHub
    |
    | HTTP
    v
Payment Service
```

You might get:

```text
success
failure
timeout
connection reset
DNS failure
partial response
```

And the most interesting case is:

```text
request sent
    ↓
server processed request
    ↓
response lost
    ↓
client sees timeout
```

The client doesn’t necessarily know whether the operation happened.

That’s a fundamental distributed-systems problem.

---

# **3. The ambiguous result**

Suppose:

```http
POST /payments
```

Client sends it.

Server:

```text
payment created
```

But then:

```text
network failure
```

Client receives:

```text
timeout
```

From the client’s perspective:

```text
Did the payment happen?
```

There are at least two possibilities:

```text
A:
request failed
payment NOT created

B:
request succeeded
payment WAS created
response was lost
```

This is why we discussed idempotency keys in Lesson 57.

---

# **4. Distributed state**

Suppose ProjectHub has:

```text
Pod A
Pod B
Pod C
```

All need to know:

```text
Is user 42 currently allowed to delete posts?
```

If the answer comes from PostgreSQL:

```text
Pod A ─┐
Pod B ─┼── PostgreSQL
Pod C ─┘
```

we have one source of truth.

That’s relatively manageable.

But suppose each Pod maintains its own copy:

```text
Pod A → permission = ALLOWED
Pod B → permission = DENIED
Pod C → permission = ALLOWED
```

Now we’ve created a consistency problem.

---

# **5. One source of truth**

This is why ProjectHub’s authorization design was:

```text
JWT
 ↓
identity + general authorities

Database
 ↓
resource-specific relationships
```

For example:

```text
JWT:
posts.delete
```

while:

```text
Post 42
 ↓
Project 7
 ↓
Alice = OWNER
```

remains in the database.

This avoids trying to keep huge amounts of rapidly-changing resource state synchronized across JWTs and application instances.

---

# **6. Replication**

Now suppose PostgreSQL becomes too large or read-heavy.

We might introduce replicas:

```text
                 PostgreSQL Primary
                  /            \
                 /              \
          Replica A          Replica B
```

Writes:

```text
ProjectHub → Primary
```

Reads might be:

```text
ProjectHub → Replica
```

But there’s a catch.

---

# **7. Replication lag**

Imagine:

```text
t0:
Primary:
project.name = "Alpha"

Replica:
project.name = "Alpha"
```

User updates:

```text
Alpha → Beta
```

Primary immediately has:

```text
Beta
```

Replica may temporarily still have:

```text
Alpha
```

So:

```text
WRITE
 ↓
Primary = Beta

READ
 ↓
Replica = Alpha
```

This is **replication lag**.

---

# **8. Eventual consistency**

If the replica eventually receives the update:

```text
t0 → Alpha
t1 → Primary becomes Beta
t2 → Replica still Alpha
t3 → Replica becomes Beta
```

the system is eventually consistent with respect to that replicated state.

The important word is:

**Eventually**

During the interval between `t1` and `t3`, different nodes can have different observations.

---

# **9. Is eventual consistency bad?**

Not necessarily.

It depends on the data.

For example:

```text
view count
analytics
recommendations
search indexes
activity feeds
```

may tolerate some delay.

But:

```text
account balance
permission to delete a resource
payment status
```

may require stronger consistency guarantees.

So the question is:

**What consistency does this piece of data actually require?**

---

# **10. Strong vs eventual consistency**

Conceptually:

### **Stronger consistency**

After a successful write:

```text
all subsequent reads
```

observe the updated state according to the system’s consistency guarantees.

### **Eventual consistency**

Different replicas may temporarily disagree:

```text
Replica A → new value
Replica B → old value
```

but converge later if updates continue successfully.

Neither is universally “better.”

Stronger guarantees generally require more coordination and can cost performance/availability.

---

# **11. PostgreSQL already solves a different consistency problem**

Inside PostgreSQL, concurrent transactions need isolation.

PostgreSQL uses **MVCC (Multiversion Concurrency Control)**, maintaining multiple row versions so transactions can operate concurrently while following transaction-isolation rules.  

For example:

```text
Transaction A
       |
       v
UPDATE project

Transaction B
       |
       v
SELECT project
```

PostgreSQL’s transaction/isolation machinery determines what each transaction can observe.

That’s different from:

```text
Primary PostgreSQL
        ↓
Replica PostgreSQL
```

where we’re dealing with distributed replication.

---

# **12. Race conditions**

Distributed systems make race conditions much more common.

Suppose ProjectHub has:

```text
Project 7
maximum members = 10
current members = 9
```

Two users simultaneously request membership.

```text
Request A                 Request B
    |                         |
    v                         v
read = 9                   read = 9
    |                         |
    v                         v
add member                 add member
    |                         |
    +-----------+-------------+
                |
             result = 11
```

Our business rule was:

```text
maximum = 10
```

but we’ve exceeded it.

---

# **13. Why application code alone isn’t enough**

You might write:

```java
if (project.memberCount() < 10) {
    addMember();
}
```

Looks reasonable.

But two threads can both execute:

```text
memberCount() < 10
```

before either inserts.

So both see:

```text
9 < 10
```

and both proceed.

This is a classic **check-then-act race**.

---

# **14. Database constraints**

One powerful lesson:

**Put invariants as close to the data as practical.**

For uniqueness:

```sql
UNIQUE(username)
```

is much safer than relying only on:

```java
if (!userRepository.existsByUsername(username)) {
    userRepository.save(user);
}
```

Why?

Because two requests can both observe:

```text
username doesn't exist
```

and then both attempt insertion.

The database constraint provides the final guarantee.

---

# **15. Optimistic locking**

Suppose we have:

```text
Project
version = 7
```

User A reads it:

```text
version 7
```

User B reads it:

```text
version 7
```

User A updates:

```text
version 7 → 8
```

User B tries to update based on version 7.

The system detects:

```text
expected version = 7
actual version = 8
```

and rejects/conflicts with the second update.

This is the basic idea behind **optimistic locking**.

With JPA, you can use:

```java
@Version
private Long version;
```

Conceptually:

```text
read
 ↓
version = 7
 ↓
modify
 ↓
UPDATE ... WHERE version = 7
 ↓
version becomes 8
```

If another transaction already changed it, the update won’t match as expected.

---

# **16. Optimistic vs pessimistic locking**

### **Optimistic**

Assume conflicts are relatively uncommon.

```text
read
 ↓
work
 ↓
detect conflict at write
```

Good when:

```text
many reads
relatively few conflicts
```

### **Pessimistic**

Acquire a lock before modifying.

Conceptually:

```text
transaction
 ↓
lock row
 ↓
modify
 ↓
commit
```

Good for certain high-contention scenarios.

But locks can reduce concurrency and introduce blocking/deadlocks.

---

# **17. Deadlocks**

Imagine:

```text
Transaction A:
lock Project 1
then wants Project 2

Transaction B:
lock Project 2
then wants Project 1
```

Now:

```text
A → waiting for B
B → waiting for A
```

Neither can proceed.

That’s a deadlock.

Database systems detect/prevent certain deadlock situations and abort one transaction so the system can recover.

The application must be prepared to handle transaction failures appropriately.

---

# **18. Ordering reduces deadlocks**

Suppose your application always acquires locks in ascending ID order:

```text
Project 1
then
Project 2
```

rather than sometimes:

```text
1 → 2
```

and elsewhere:

```text
2 → 1
```

you reduce the possibility of circular waiting.

This leads to a broader principle:

**Consistent ordering is a powerful concurrency-control technique.**

---

# **19. Distributed transactions**

Now imagine:

```text
ProjectHub
   |
   +---- PostgreSQL
   |
   +---- Payment Service
```

We want:

```text
create project
+
charge payment
```

to behave like one atomic transaction.

Problem:

PostgreSQL can roll back:

```text
BEGIN
...
ROLLBACK
```

But it can’t magically roll back a remote payment service.

---

# **20. The impossible-looking sequence**

Suppose:

```text
1. Create project in DB
2. Charge payment
```

Payment succeeds:

```text
Project = created
Payment = charged
```

Great.

But what if:

```text
1. Create project
2. Charge payment
3. network fails
```

Now the caller doesn’t know whether payment happened.

Or:

```text
1. Create project
2. Payment fails
```

Should the project be rolled back?

Maybe.

But now we’re coordinating two independent systems.

---

# **21. Two-phase commit**

One historical approach is **two-phase commit (2PC)**.

Conceptually:

```text
Coordinator
   |
   +---- DB
   |
   +---- Service
```

Phase 1:

```text
"Can you commit?"
```

Participants prepare.

Phase 2:

```text
"Commit."
```

This can provide distributed transactional semantics, but introduces substantial coordination and operational complexity.

For many modern application architectures, teams prefer patterns such as:

```text
local transaction
+
outbox
+
events
+
compensation
```

instead of making every workflow one distributed ACID transaction.

---

# **22. Saga pattern**

Suppose:

```text
Create project
   ↓
Reserve resources
   ↓
Send notification
```

Instead of one global transaction:

```text
step 1 succeeds
step 2 succeeds
step 3 fails
```

we define compensating actions.

For example:

```text
Create project
     ↓
Reserve resources
     ↓
notification fails
     ↓
retry notification
```

or potentially:

```text
compensating action
     ↓
release resources
```

This is the basic idea of a **Saga**.

---

# **23. Saga doesn’t mean “undo everything”**

Important distinction.

A compensation isn’t necessarily a database rollback.

Suppose:

```text
Email sent
```

You can’t literally “unsend” the email.

So compensation means:

```text
perform another action
```

that restores the desired business state as closely as possible.

Distributed workflows are therefore fundamentally business-process problems as well as technical problems.

---

# **24. Events and consistency**

Suppose:

```text
POST /projects
```

creates:

```text
Project
```

Then we publish:

```text
ProjectCreated
```

A notification service receives it:

```text
ProjectCreated
      ↓
Notification Service
      ↓
email
```

The email isn’t necessarily sent in the same transaction as the project creation.

That’s **eventual consistency**.

The project can exist before the notification is processed.

---

# **25. Why this is often good**

It allows:

```text
Project API
     |
     v
PostgreSQL
     |
     v
fast response
```

while:

```text
RabbitMQ
   ↓
Notification Worker
   ↓
Email Provider
```

happens asynchronously.

The user doesn’t necessarily need to wait for the entire downstream workflow.

---

# **26. But now you need idempotency**

RabbitMQ consumer:

```text
ProjectCreated
```

could potentially receive/process the same event more than once depending on the delivery/retry architecture.

If the consumer does:

```text
send email
```

twice:

```text
📧
📧
```

that’s bad.

So the consumer needs an idempotency strategy.

For example:

```text
processed_events
----------------
event_id
```

Before processing:

```text
Has eventId already been handled?
```

If yes:

```text
ignore duplicate
```

If no:

```text
process
record eventId
```

The exact transaction boundaries matter, but the principle is critical.

---

# **27. Exactly-once is difficult**

You’ll hear:

“Exactly-once processing.”

Be careful.

Across distributed systems, “exactly once” is much harder than:

```text
at-least-once delivery
+
idempotent processing
```

Often the practical architecture is:

```text
message may arrive multiple times
        ↓
consumer safely handles duplicates
```

That’s much easier to reason about.

---

# **28. Distributed locks**

Sometimes multiple ProjectHub Pods need to coordinate:

```text
Pod A
Pod B
Pod C
```

Suppose we have a scheduled job:

```text
send daily report
```

If every Pod executes it:

```text
Pod A → report
Pod B → report
Pod C → report
```

we get duplicates.

We may need **leader election** or a distributed coordination mechanism.

Kubernetes itself uses Lease objects for coordination and leader-election scenarios.  

---

# **29. Don’t immediately invent your own distributed lock**

A dangerous beginner instinct is:

“I’ll create a Redis key and use that as a lock.”

Distributed locking has subtle failure modes:

```text
network partitions
timeouts
process crashes
clock assumptions
lease expiration
ownership loss
```

If you need coordination, use a well-understood mechanism and carefully define its guarantees.

---

# **30. Service discovery**

Now imagine:

```text
ProjectHub
   ↓
Notification Service
```

Where does ProjectHub find it?

With Kubernetes, a Service gives a stable network abstraction in front of changing Pods. Kubernetes also provides DNS-based discovery for Services.  

So:

```text
notification-service
```

can remain stable while:

```text
Notification Pod 1
Notification Pod 2
Notification Pod 3
```

change over time.

This is exactly why we don’t hardcode Pod IP addresses.

---

# **31. Distributed systems and Kubernetes**

Kubernetes itself is a distributed system platform.

You have:

```text
Control Plane
    |
    +--- Node 1
    |      |
    |     Pods
    |
    +--- Node 2
    |      |
    |     Pods
    |
    +--- Node 3
           |
          Pods
```

Kubernetes provides abstractions for service discovery, load balancing, storage, rollout and failover.  

But Kubernetes doesn’t make your application automatically distributed-system-safe.

Your application still needs:

```text
timeouts
idempotency
concurrency control
transaction boundaries
failure handling
```

---

# **32. CAP theorem**

Now we reach one of the most famous concepts.

CAP says that in a distributed data system, under a **network partition**, you cannot simultaneously guarantee all three:

```text
C = Consistency
A = Availability
P = Partition tolerance
```

The crucial part beginners often miss:

**The tradeoff becomes relevant when a partition occurs.**

---

# **33. What is a partition?**

Suppose:

```text
Node A
   |
   X   ← network broken
   |
Node B
```

Both nodes are alive.

But they cannot communicate.

That’s a network partition.

Now suppose both receive writes:

```text
A: balance = 100
B: balance = 200
```

They can’t coordinate.

What should a read return?

That’s the fundamental problem.

---

# **34. Consistency choice**

One strategy:

Refuse some operations until the nodes can communicate again.

That preserves stronger consistency but sacrifices availability during the partition.

Another strategy:

Continue accepting operations independently.

That preserves availability but can temporarily produce divergent state.

That’s the basic CAP tradeoff.

---

# **35. CAP does NOT mean:**

```text
"You can only choose two letters."
```

That’s an oversimplification.

Partition tolerance is effectively required for systems operating over unreliable networks.

The meaningful question is:

**When a partition occurs, do we prioritize consistency or availability for this operation/system?**

---

# **36. ProjectHub example**

Imagine a distributed permission system:

```text
Permission Service A
Permission Service B
```

Network partition.

User asks:

```text
Can Alice delete Post 42?
```

One node says:

```text
YES
```

another says:

```text
NO
```

For authorization, blindly choosing availability could be dangerous.

You may prefer:

```text
fail closed
```

for security-sensitive decisions.

This is why authorization data is especially interesting in distributed systems.

---

# **37. Security and consistency**

Suppose Alice’s permission is revoked:

```text
posts.delete
```

The authorization database says:

```text
DENIED
```

But an old JWT still says:

```text
posts.delete
```

Until the token expires, the system may temporarily observe different authorization states.

This is a form of **stale authorization state**.

That’s why we designed:

```text
short-lived access token
+
server-controlled refresh token
```

and resource-specific authorization through current database state.

---

# **38. Race condition in ProjectHub**

Let’s make this practical.

Suppose:

```text
POST /projects/7/members
```

has a rule:

```text
maximum 10 members
```

Current count:

```text
9
```

Requests:

```text
Alice adds Bob
Alice adds Carol
```

arrive simultaneously.

Naive code:

```text
count = 9

if (count < 10) {
    insert member
}
```

Both requests see:

```text
9 < 10
```

Both insert.

Now:

```text
members = 11
```

That’s a real distributed/concurrency bug.

---

# **39. How could we solve it?**

Possible approaches:

### **Database locking**

Lock the relevant project row while checking/updating.

### **Atomic database operation**

Move the invariant into an atomic SQL operation.

### **Optimistic locking**

Use:

```java
@Version
```

and retry/conflict when versions collide.

### **Database constraint**

Useful when the invariant can be represented as a constraint.

The right solution depends on the actual business rule.

---

# **40. Distributed systems principle**

Here’s one of the most important principles of the entire course:

**If correctness depends on two operations happening atomically, ask whether they actually share the same transaction boundary.**

For:

```text
update User
+
update Role
```

same PostgreSQL transaction:

```text
@Transactional
```

can handle it.

For:

```text
update PostgreSQL
+
send HTTP request to another company
```

you no longer have one local transaction.

You need a distributed workflow strategy.

---

# **41. The ProjectHub architecture**

At this point:

```text
                           Internet
                              |
                           Gateway
                              |
                   +----------+----------+
                   |          |          |
                 Pod A      Pod B      Pod C
                   |          |          |
                   +----------+----------+
                              |
                    +---------+---------+
                    |                   |
                 Redis             PostgreSQL
                                        |
                                      Outbox
                                        |
                                    RabbitMQ
                                        |
                              +---------+---------+
                              |                   |
                       Notification           Analytics
                         Worker                Worker
```

Now ask:

Which operations must be strongly consistent?

Likely:

```text
user identity
permissions
project ownership
membership invariants
financial state
```

And which can be eventually consistent?

Potentially:

```text
analytics
notifications
search indexes
activity feeds
caches
```

That distinction drives architecture.

---

# **42. A useful classification**

For every piece of data, ask:

```text
Who owns it?
       ↓
Where is the source of truth?
       ↓
Who can modify it?
       ↓
How quickly must changes become visible?
       ↓
Can stale reads happen?
       ↓
What happens during network failure?
```

This is much more useful than simply asking:

“Should we use microservices?”

---

# **43. Don’t create microservices just because you can**

Suppose we split ProjectHub into:

```text
User Service
Project Service
Post Service
Permission Service
Notification Service
```

Now one user request might become:

```text
API
 ↓
Project Service
 ↓
Permission Service
 ↓
User Service
 ↓
Post Service
```

We’ve traded:

```text
one application
```

for:

```text
network calls
timeouts
retries
distributed tracing
deployment coordination
data ownership
eventual consistency
```

Microservices can be useful.

But they create distributed-systems problems.

---

# **44. Modular monolith**

This is why a well-structured modular monolith can be an excellent architecture.

For ProjectHub:

```text
ProjectHub
├── users
├── projects
├── posts
├── permissions
├── notifications
└── authentication
```

Still one deployable application:

```text
ProjectHub
   ↓
PostgreSQL
```

but internally separated by modules.

You can later extract a module when there’s a real reason.

---

# **45. When extraction becomes valuable**

Potential reasons:

```text
independent scaling
independent deployment
different technology requirements
team ownership
fault isolation
very different workload
```

For example:

```text
Notification Worker
```

might naturally become a separate service because it can scale independently:

```text
ProjectHub
   ↓
RabbitMQ
   ↓
Notification Workers × 20
```

while ProjectHub itself remains:

```text
× 5 Pods
```

That’s a meaningful boundary.

---

# **46. Distributed systems mental model**

When you see:

```text
Service A → Service B
```

immediately think:

```text
What if B is slow?
What if B is down?
What if the request succeeded but response was lost?
What if A retries?
What if B processes twice?
What if the network partitions?
What if data is stale?
What if A crashes halfway through?
```

That checklist is extremely valuable.

---

# **Lesson 59 Summary**

You’ve now learned:

- Distributed systems
- Network failure
- Ambiguous outcomes
- Replication
- Replication lag
- Eventual consistency
- Stronger consistency
- Race conditions
- Database constraints
- Optimistic locking
- Pessimistic locking
- Deadlocks
- Distributed transactions
- Two-phase commit
- Saga patterns
- Eventual consistency with messaging
- Consumer idempotency
- Distributed coordination
- Service discovery
- CAP theorem
- Security consistency
- Microservice tradeoffs
- Modular monoliths

The biggest mental shift is this:

```text
Single process:

method call
   ↓
result


Distributed system:

network call
   ↓
success?
failure?
timeout?
duplicate?
partial success?
stale data?
partition?
```

Kubernetes gives applications stable Service abstractions and DNS-based discovery even as individual Pods change, but it doesn’t remove the underlying distributed-systems failure modes.  

PostgreSQL, meanwhile, provides transaction isolation and MVCC for concurrent database operations, but that local transactional guarantee does not automatically extend across remote services.  

---

# **Exercise 59**

### **1. Replication**

PostgreSQL has:

```text
Primary → Replica
```

A user updates their project name from:

```text
Alpha → Beta
```

Then immediately reads from the replica and sees:

```text
Alpha
```

Explain exactly how this can happen.

---

### **2. Race condition**

Project 7 has:

```text
9 members
maximum = 10
```

Two requests arrive simultaneously.

Both execute:

```java
if (memberCount < 10) {
    addMember();
}
```

Explain the race condition and give **two different ways** to prevent it.

---

### **3. Optimistic locking**

Explain what this means:

```java
@Version
private Long version;
```

Use this scenario:

```text
Alice reads version 5
Bob reads version 5

Alice updates → version 6

Bob updates using version 5
```

What should happen?

---

### **4. Distributed transaction**

ProjectHub does:

```text
1. Create project in PostgreSQL
2. Call external billing service
```

The billing service succeeds, but ProjectHub times out waiting for the response.

What makes this situation difficult?

How could an idempotency key help?

---

### **5. Eventual consistency**

Which of these would you be more comfortable making eventually consistent?

```text
A. Project analytics
B. User's password
C. User's permission to delete a post
D. Activity feed
```

Explain your reasoning for each.

---

### **6. CAP**

Two database replicas become unable to communicate:

```text
Replica A  X  Replica B
```

A write arrives.

Explain the fundamental choice between:

```text
stronger consistency
```

and:

```text
continued availability
```

during the partition.

---

### **7. ProjectHub architecture**

Which would you keep strongly transactional inside PostgreSQL?

Which would you potentially move to asynchronous/eventual processing?

Try to classify:

```text
User registration
Project creation
Project membership
Post creation
Email notification
Analytics
Activity feed
Search indexing
Permission changes
```

---

### **8. Architecture challenge**

Imagine we split ProjectHub into:

```text
User Service
Project Service
Post Service
Notification Service
```

A request:

```http
POST /projects/7/posts
```

needs:

```text
authentication
permission check
project membership check
post creation
notification
```

Draw the request flow and identify **every place where a network failure could occur**.

Then ask yourself:

**Would you actually want these to be separate services yet, or would a modular monolith be simpler?**

Don’t optimize for “microservices”.

Optimize for a clear ownership and consistency model.

**Next: Lesson 60 — Advanced Database Concurrency: isolation levels, lost updates, dirty/non-repeatable/phantom reads, locking, optimistic concurrency, and designing race-free ProjectHub operations.**