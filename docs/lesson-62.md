---
title: "Lesson 62: Spring Transactions Deep Dive"
sidebar_position: 62
---

We’ve reached a point where `@Transactional` should no longer feel like a magic annotation.

Today we’ll answer:

**What exactly happens when transactional methods call other transactional methods?**

We’ll cover:

- `REQUIRED`
- `REQUIRES_NEW`
- `NESTED`
- rollback rules
- `readOnly`
- isolation
- transaction timeouts
- self-invocation
- `UnexpectedRollbackException`
- transaction boundaries in ProjectHub

Spring’s current transaction documentation still defines `REQUIRED` as the default propagation behavior, with `REQUIRES_NEW` creating an independent physical transaction.  

---

# **1. Start with the simplest case**

Imagine:

```java
@Transactional
public void createPost() {
    // save post
}
```

A request enters:

```text
HTTP
 ↓
Controller
 ↓
createPost()
 ↓
BEGIN
 ↓
database work
 ↓
COMMIT
```

If an appropriate exception causes rollback:

```text
BEGIN
 ↓
database work
 ↓
exception
 ↓
ROLLBACK
```

That’s the easy case.

The interesting part starts when methods call other methods.

---

# 

# **2.**

**`PROPAGATION_REQUIRED`**

This is the default.

Suppose:

```java
@Transactional
public void createProject() {
    projectRepository.save(project);
    auditService.record("PROJECT_CREATED");
}
```

and:

```java
@Transactional
public void record(String event) {
    auditRepository.save(...);
}
```

The call chain is:

```text
createProject()
      ↓
record()
```

Both use:

```text
REQUIRED
```

So the inner method normally **joins the existing transaction**.

Conceptually:

```text
createProject()
    |
    +-- BEGIN
    |
    +-- save project
    |
    +-- record()
          |
          +-- joins same transaction
          |
          +-- save audit
    |
    +-- COMMIT
```

There aren’t two independent database transactions here.

There’s one physical transaction.

Spring documents `REQUIRED` as the normal behavior for service calls that should participate in the same transaction.  

---

# **3. Think “join” for REQUIRED**

A useful mental model:

```text
@Transactional(REQUIRED)
```

means:

“Use the current transaction if one exists; otherwise create one.”

So:

```text
No transaction
     ↓
REQUIRED
     ↓
create transaction
```

while:

```text
Existing transaction
     ↓
REQUIRED
     ↓
join it
```

---

# **4. Why this matters**

Suppose:

```text
createProject()
   ↓
save project
   ↓
save audit
   ↓
something fails
```

Because both participate in the same transaction:

```text
project INSERT
audit INSERT
     ↓
failure
     ↓
ROLLBACK
```

Both changes can be rolled back together.

That’s usually exactly what we want.

---

# **5. Logical vs physical transactions**

Spring makes an important distinction.

You can have:

```text
Service A
@Transactional
   ↓
Service B
@Transactional
   ↓
Repository
@Transactional
```

There may be multiple **logical transaction scopes**:

```text
A
 ↓
B
 ↓
Repository
```

but they can all participate in the same **physical database transaction**.

That’s why an inner method can influence the final outcome of the outer transaction.  

---

# **6. The surprising rollback case**

Consider:

```java
@Transactional
public void outer() {

    repository.save(...);

    inner();

    repository.save(...);
}
```

and:

```java
@Transactional
public void inner() {
    throw new SomeRuntimeException();
}
```

The inner method participates in the outer transaction.

The transaction becomes rollback-only.

Eventually:

```text
outer()
 ↓
tries to commit
 ↓
transaction is rollback-only
 ↓
ROLLBACK
```

Spring can then throw:

```text
UnexpectedRollbackException
```

because the outer caller thought it was going to commit, but an inner scope had already marked the shared transaction rollback-only.  

This catches many developers by surprise.

---

# 

# **7.**

**`REQUIRES_NEW`**

Now we change the propagation:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordAudit(...) {
    ...
}
```

Now the meaning is:

**Suspend the current transaction and create a completely independent transaction.**

Conceptually:

```text
Outer transaction
      |
      | suspend
      v
Inner transaction
      |
      | commit/rollback
      v
resume outer transaction
```

Spring explicitly documents `REQUIRES_NEW` as using an independent physical transaction.  

---

# **8. Example: audit logging**

Suppose:

```text
Create project
```

should produce an audit record.

You might decide:

```text
project creation succeeds
      ↓
audit should commit

project creation fails
      ↓
audit should still record the failure
```

That could justify:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordAudit(...) {
    ...
}
```

But be careful: this is a design decision, not a default rule.

---

# **9. The big difference**

### **REQUIRED**

```text
Outer
 └── Inner

same transaction
```

### **REQUIRES_NEW**

```text
Outer transaction
      ↓
   suspended
      ↓
Inner transaction
      ↓
   committed
      ↓
outer resumes
```

This difference is fundamental.

---

# 

# 

# **10. A dangerous**

**`REQUIRES_NEW`**

**mistake**

Suppose:

```text
Outer transaction
   ↓
holds DB connection
   ↓
calls REQUIRES_NEW
   ↓
needs another DB connection
```

The outer transaction’s resources remain bound while the inner transaction obtains its own resources.

If many threads do this and the connection pool is too small, you can create connection exhaustion or even deadlock. Spring’s documentation explicitly warns about this behavior.  

So don’t casually sprinkle:

```java
REQUIRES_NEW
```

everywhere.

---

# 

# **11.**

**`NESTED`**

Another propagation mode is:

```java
Propagation.NESTED
```

Conceptually:

```text
BEGIN
 ↓
operation A
 ↓
SAVEPOINT
 ↓
operation B
 ↓
rollback to SAVEPOINT
 ↓
continue
 ↓
COMMIT
```

Unlike `REQUIRES_NEW`, it doesn’t normally create another physical transaction.

Spring describes `NESTED` in terms of a single physical transaction with savepoints, allowing partial rollback. Its availability depends on the transaction manager/resource configuration.  

For our ProjectHub course, you should understand it conceptually without reaching for it routinely.

---

# **12. Compare the three**

|**Propagation**|**Existing transaction?**|**New physical transaction?**|
|---|---|---|
|`REQUIRED`|joins it|No|
|`REQUIRES_NEW`|suspends it|Yes|
|`NESTED`|participates|Usually no; savepoint|

The most important one by far is:

```text
REQUIRED
```

Then understand:

```text
REQUIRES_NEW
```

when you genuinely need independent commit/rollback behavior.

---

# **13. Rollback rules**

By default, Spring’s declarative transaction behavior rolls back for unchecked exceptions (`RuntimeException` and `Error`), while checked exceptions do not automatically trigger rollback.  

For example:

```java
@Transactional
public void createPost() {
    ...
    throw new RuntimeException();
}
```

normally:

```text
ROLLBACK
```

But:

```java
@Transactional
public void createPost() throws IOException {
    ...
    throw new IOException();
}
```

doesn’t automatically mean rollback.

---

# **14. Changing rollback behavior**

You can explicitly specify:

```java
@Transactional(rollbackFor = IOException.class)
```

Then:

```text
IOException
    ↓
ROLLBACK
```

You can also configure exceptions that should **not** cause rollback.

The important idea is:

Transaction rollback is a policy, not simply “any exception means rollback.”

Spring provides declarative rollback rules for this purpose.  

---

# **15. Business exceptions**

Suppose ProjectHub has:

```java
public class ProjectFullException
        extends RuntimeException {
}
```

Then:

```java
@Transactional
public void addMember(...) {
    if (projectFull) {
        throw new ProjectFullException();
    }
}
```

The transaction normally rolls back.

That’s useful because the membership insert shouldn’t remain partially committed.

---

# **16. But think carefully about checked exceptions**

Suppose you create:

```java
public class ProjectFullException
        extends Exception {
}
```

Now it’s checked.

Spring won’t automatically treat it as a rollback-triggering exception under the default rules.

You could explicitly configure:

```java
@Transactional(
    rollbackFor = ProjectFullException.class
)
```

But for normal domain failures in our ProjectHub service, using appropriate unchecked application exceptions is often simpler.

---

# 

# **17.**

**`readOnly = true`**

You will frequently see:

```java
@Transactional(readOnly = true)
public PostResponse getPost(...) {
    ...
}
```

This communicates:

“This transaction is intended for reads.”

Spring Data JPA also documents read methods as using `readOnly` transaction configuration by default for inherited CRUD operations.  

But there’s an important misconception:

`readOnly = true` is **not a security mechanism preventing writes**.

Spring’s documentation explicitly describes it as a hint to the underlying infrastructure rather than a universal write prohibition. With Hibernate, it can enable optimizations such as adjusting flush behavior.  

---

# **18. So don’t think:**

```text
readOnly = true
```

means:

```text
"Database guarantees no UPDATE can ever happen."
```

Instead think:

```text
"this operation is intended to be read-only,
and the transaction infrastructure can optimize accordingly."
```

---

# **19. Transaction timeout**

You can specify a timeout:

```java
@Transactional(timeout = 5)
public void createPost(...) {
    ...
}
```

Conceptually:

```text
transaction starts
      ↓
work
      ↓
timeout exceeded
      ↓
transaction failure/rollback
```

The exact timeout behavior depends on the transaction infrastructure and underlying resource.

Timeouts are important because a transaction holding locks indefinitely can hurt the entire system.

Spring’s transaction settings document timeout as a configurable transaction attribute.  

---

# **20. Isolation configuration**

We previously discussed:

```text
READ COMMITTED
REPEATABLE READ
SERIALIZABLE
```

Spring lets you specify isolation:

```java
@Transactional(
    isolation = Isolation.SERIALIZABLE
)
```

Conceptually:

```text
Service method
     ↓
transaction begins
     ↓
SERIALIZABLE
```

But don’t set everything to `SERIALIZABLE`.

You should choose the isolation level based on the actual consistency requirement.

Spring’s transaction configuration supports isolation settings, with the default being `DEFAULT`, meaning the underlying transaction system/database determines it.  

---

# **21. The self-invocation trap**

This is one of the most important Spring concepts.

Imagine:

```java
@Service
public class ProjectService {

    public void createProject() {
        saveProject();
    }

    @Transactional
    public void saveProject() {
        ...
    }
}
```

You might expect:

```text
createProject()
   ↓
@Transactional saveProject()
   ↓
transaction
```

But that’s not necessarily what happens.

Why?

Spring’s normal annotation-driven transaction management uses proxies.

An external call:

```text
Other bean
   ↓
Spring proxy
   ↓
ProjectService
```

can be intercepted.

But:

```text
ProjectService
   ↓
this.saveProject()
```

doesn’t pass through the proxy.

Spring’s current documentation explicitly warns that self-invocation does not trigger transactional interception in proxy mode.  

---

# **22. Visualize the proxy**

Spring effectively gives you something conceptually like:

```text
Caller
  |
  v
Spring Proxy
  |
  | BEGIN TRANSACTION
  v
ProjectService
  |
  v
method()
  |
  | COMMIT
  v
return
```

But inside the object:

```text
ProjectService
   |
   +── this.otherMethod()
```

the call doesn’t travel through:

```text
Spring Proxy
```

So the annotation may not take effect as you expected.

---

# **23. Solution: move the operation**

Instead of:

```java
class ProjectService {

    void outer() {
        inner();
    }

    @Transactional
    void inner() {
    }
}
```

often use:

```text
ProjectService
      ↓
MembershipService
      ↓
@Transactional
```

For example:

```java
@Service
public class MembershipService {

    @Transactional
    public void addMember(...) {
        ...
    }
}
```

Then another bean calls it:

```text
ProjectService
      ↓
Spring proxy
      ↓
MembershipService
```

Now transaction interception works normally.

---

# **24. Transaction boundary should represent a use case**

This is one of the most useful architecture principles.

Don’t think:

```text
@Transactional
```

as:

“Put this on every method that talks to a repository.”

Instead think:

**A transaction should usually represent a coherent unit of business work.**

For ProjectHub:

```text
addMember
createPost
deletePost
changeProjectOwner
removeProjectMember
```

are good candidates for service-level transaction boundaries.

Spring Data JPA’s documentation similarly recommends defining transaction boundaries around a unit of work, typically at a service/facade level when multiple repository calls participate.  

---

# **25. A bad transaction boundary**

Imagine:

```java
@Transactional
public void processEntireImport() {

    for (...) {
        save(...);

        callExternalService();

        Thread.sleep(...);
    }
}
```

Now one transaction may remain open for:

```text
minutes
```

Potential problems:

```text
long-held DB connection
long-held locks
large persistence context
more contention
higher rollback cost
```

This is why transaction duration matters.

---

# **26. A better batch architecture**

Instead:

```text
read batch
 ↓
transaction
 ↓
process small unit
 ↓
commit
 ↓
next unit
```

or:

```text
message
 ↓
transaction
 ↓
process
 ↓
commit
```

The exact design depends on the workload.

---

# **27. ProjectHub example: creating a post**

Good:

```java
@Transactional
public PostResponse createPost(...) {

    Project project = ...;
    User author = ...;

    Post post = new Post(...);

    postRepository.save(post);

    outboxRepository.save(
        PostCreatedEvent(...)
    );

    return mapper.toResponse(post);
}
```

The database work is one coherent unit:

```text
post
+
outbox
```

Either both commit or neither does.

---

# **28. What about Redis?**

Suppose:

```text
@Transactional
createPost()
```

also does:

```text
redis.set(...)
```

Now the database transaction does **not automatically roll back Redis**.

You have:

```text
Database transaction
        +
Redis operation
```

These are separate systems.

If DB commits but Redis fails:

```text
DB = success
Redis = failure
```

If Redis changes first and DB rolls back:

```text
Redis = success
DB = rollback
```

That’s why cache updates are often designed around transaction events or invalidation strategies rather than pretending Redis is part of the JPA transaction.

---

# **29. What about RabbitMQ?**

Same principle.

Don’t think:

```text
@Transactional
database
rabbitmq
```

means:

“Everything commits atomically.”

They are separate resources unless you deliberately use a distributed transaction mechanism, which brings significant complexity.

For ProjectHub:

```text
DB transaction
    ↓
outbox row
    ↓
commit
    ↓
publisher
    ↓
RabbitMQ
```

is usually a better architecture.

---

# 

# 

# **30. The**

**`REQUIRES_NEW`**

**audit example**

Let’s make this concrete.

Suppose:

```text
Project deletion
```

fails.

You want to preserve an audit record:

```text
"Project deletion failed"
```

You could have:

```java
@Transactional
public void deleteProject(Long id) {

    try {
        ...
    } catch (Exception ex) {
        auditService.recordFailure(id);
        throw ex;
    }
}
```

with:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordFailure(Long projectId) {
    auditRepository.save(...);
}
```

Now:

```text
Outer transaction
     ↓
failure
     ↓
suspended
     ↓
audit transaction
     ↓
COMMIT
     ↓
outer transaction
     ↓
ROLLBACK
```

This is one legitimate use case for `REQUIRES_NEW`.

But remember the connection-pool warning.

---

# **31. A simpler alternative: outbox/audit event**

Depending on your requirements, an outbox may be preferable:

```text
transaction
    ↓
write audit/outbox row
    ↓
commit
```

Then a worker processes it.

Which approach is right depends on what “audit must survive” actually means.

Don’t introduce `REQUIRES_NEW` just because it sounds powerful.

---

# **32. Another subtle trap: catching exceptions**

Consider:

```java
@Transactional
public void createProject() {

    try {
        projectRepository.save(...);
        riskyOperation();
    } catch (RuntimeException e) {
        log.error("Failed", e);
    }
}
```

What happens?

You caught the exception.

The method may return normally.

Depending on where rollback-only status was set, you can end up with surprising behavior.

The key principle:

**Catching an exception does not automatically mean the transaction is healthy.**

If a participating operation has marked the transaction rollback-only, the outer transaction may still be unable to commit. This is one path to `UnexpectedRollbackException`.  

---

# **33. Don’t hide transaction failures**

Bad:

```java
catch (Exception e) {
    log.error("Something went wrong");
}
```

when the business operation actually needs to fail.

Better:

```java
catch (Exception e) {
    log.error("Project creation failed", e);
    throw e;
}
```

or translate it into an appropriate application exception.

The transaction system needs to know whether the operation should commit or roll back.

---

# **34. ProjectHub transaction map**

Here’s how I want you to think about our backend:

```text
HTTP request
     ↓
Controller
     ↓
Authorization
     ↓
Service use case
     ↓
@Transactional
     ↓
Repository A
     ↓
Repository B
     ↓
Outbox
     ↓
COMMIT
```

Everything inside that transaction should contribute to one coherent database operation.

---

# **35. Our rules from now on**

For ProjectHub:

### **Rule 1**

Put transaction boundaries primarily at the **service/use-case layer**.

### **Rule 2**

Use:

```java
@Transactional(readOnly = true)
```

for appropriate read-only service operations.

### **Rule 3**

Don’t use:

```text
REQUIRES_NEW
```

unless you specifically need independent commit/rollback.

### **Rule 4**

Don’t hold transactions open across slow external calls.

### **Rule 5**

Don’t assume Redis/RabbitMQ participate in your database transaction.

### **Rule 6**

Don’t put `@Transactional` on a method and then call it through `this`.

### **Rule 7**

Choose isolation deliberately for concurrency-sensitive operations.

### **Rule 8**

Use database constraints to protect invariants.

---

# **36. One final mental model**

When you see:

```java
@Transactional
```

ask five questions:

```text
1. What is the unit of work?

2. What transaction will this method participate in?

3. What causes rollback?

4. What happens if another transaction runs concurrently?

5. Does this transaction interact with anything outside the database?
```

If you can answer those five questions, you’re thinking like a backend engineer rather than merely using Spring annotations.

---

# **Exercise 62**

Let’s make this practical.

### **1. REQUIRED**

Given:

```java
@Transactional
void createProject() {
    saveProject();
    saveAudit();
}
```

and both `saveProject()` and `saveAudit()` use:

```java
@Transactional
```

Are there one or three physical database transactions?

Explain why.

---

### 

### **2.**

**`REQUIRES_NEW`**

Draw the transaction flow for:

```text
createProject()
    ↓
recordAudit()
```

where `recordAudit()` uses:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
```

Show:

```text
BEGIN
SUSPEND
BEGIN
COMMIT
RESUME
COMMIT/ROLLBACK
```

---

### 

### **3.**

**`UnexpectedRollbackException`**

Explain this scenario:

```text
outer()
  ↓
inner()
  ↓
inner marks transaction rollback-only
  ↓
inner returns
  ↓
outer tries to commit
```

Why can the outer method receive `UnexpectedRollbackException`?

---

### **4. Self-invocation**

Why doesn’t this reliably create a transaction?

```java
@Service
class ProjectService {

    public void outer() {
        this.inner();
    }

    @Transactional
    public void inner() {
        // database work
    }
}
```

What architectural change would you make?

---

### **5. Read-only**

Explain why:

```java
@Transactional(readOnly = true)
```

doesn’t mean:

“The database physically guarantees that no write can happen.”

What is its purpose instead?

---

### **6. ProjectHub**

Classify each operation:

|**Operation**|**Transaction strategy**|
|---|---|
|`GET /posts/{id}`|?|
|`POST /projects/{id}/posts`|?|
|`POST /projects/{id}/members/{userId}`|?|
|Audit failure that must survive outer rollback|?|
|Publish RabbitMQ event|?|

Don’t just give annotations. Explain **why**.

---

### **7. Final challenge**

Imagine:

```java
@Transactional
public void createPost() {

    postRepository.save(post);

    emailService.sendEmail();

    outboxRepository.save(event);
}
```

The email service takes 8 seconds.

Identify **everything that is potentially wrong with this design**.

Then redesign the operation using what we’ve learned about:

```text
transactions
outbox
RabbitMQ
REQUIRES_NEW
transaction duration
external calls
```

**Next: Lesson 63 — Spring Transaction Architecture in the Real World: transaction boundaries, domain events, outbox implementation, transactional event listeners, and how ProjectHub reliably publishes events after database commits.**