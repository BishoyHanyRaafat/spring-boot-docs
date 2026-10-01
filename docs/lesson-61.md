---
title: Lesson 61: Advanced JPA Concurrency
sidebar_position: 61
---

Today we’re going to take the theory from Lesson 60 and turn it into **real Spring Data JPA code**.

We’re currently on Spring Data JPA **4.1.1**, the latest stable line shown in the official documentation. Spring Data JPA supports repository-level locking with `@Lock`, while Spring’s transaction infrastructure provides the transaction boundary around the operation.  

Our goal is to safely implement:

```text
POST /projects/{projectId}/members/{userId}
```

with:

```text
maximum 10 members
no duplicate membership
concurrent requests handled safely
```

---

# **1. First: the architecture**

Don’t start with the lock.

Start with the business operation:

```text
HTTP request
     ↓
Controller
     ↓
Authorization
     ↓
Service
     ↓
Transaction
     ↓
Concurrency control
     ↓
Repositories
     ↓
PostgreSQL
```

For our operation:

```text
POST /projects/7/members/42
```

we need to answer:

1. Can this authenticated user manage members?
2. Does Project 7 exist?
3. Is Project 7 active?
4. Is User 42 already a member?
5. Are there fewer than 10 members?
6. Insert membership.
7. Commit.

The difficult part is **4–6 happening concurrently**.

---

# **2. The database model**

We have something conceptually like:

```text
projects
---------
id
name
status


users
-----
id
username


project_members
---------------
project_id
user_id
role
created_at
```

And critically:

```sql
PRIMARY KEY (project_id, user_id)
```

That gives us:

A user can belong to a project only once.

This constraint remains important even if our Java code checks for duplicates.

---

# **3. Our entity**

Simplified:

```java
@Entity
@Table(name = "projects")
public class Project {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @Enumerated(EnumType.STRING)
    private ProjectStatus status;

    // ...
}
```

We could add:

```java
@Version
private Long version;
```

but **don’t automatically do that yet**.

Why?

Because `@Version` is useful when we’re detecting conflicting modifications to the same entity.

Our membership-capacity problem is slightly different.

We need to coordinate:

```text
project row
+
membership rows
```

So an explicit locking strategy can be more direct.

---

# **4. Locking the project**

Spring Data JPA allows a repository query method to specify a JPA lock mode using `@Lock`.  

Conceptually:

```java
public interface ProjectRepository
        extends JpaRepository<Project, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
        select p
        from Project p
        where p.id = :projectId
        """)
    Optional<Project> findByIdForUpdate(Long projectId);
}
```

The important part is:

```java
@Lock(LockModeType.PESSIMISTIC_WRITE)
```

We’re telling the persistence layer:

“When this transaction retrieves this project, acquire a write-oriented database lock.”

The exact SQL and locking semantics are ultimately determined by the JPA provider/database combination.

---

# **5. Why do we lock the project?**

This is the clever part.

We aren’t necessarily locking every membership row.

We’re using:

```text
Project 7
```

as the **coordination point**.

Imagine two requests:

```text
Request A                    Request B
    |                            |
    | lock Project 7             |
    |                            | try lock Project 7
    |                            |
    | count members              |
    |                            |
    | insert Bob                 |
    |                            |
    | COMMIT                     |
    |                            |
    |                       lock acquired
    |                            |
    |                       count members
    |                            |
    |                       reject if full
```

So concurrent membership changes for the same project serialize around the project row.

---

# **6. The service transaction**

Now we create the service boundary:

```java
@Transactional
public void addMember(Long projectId, Long userId) {
    // ...
}
```

Spring’s declarative transaction support wraps the method with transaction infrastructure; the transaction is normally thread-bound for imperative applications.  

Conceptually:

```text
enter method
    ↓
BEGIN
    ↓
lock project
    ↓
perform checks
    ↓
insert membership
    ↓
COMMIT
```

If the operation fails:

```text
BEGIN
   ↓
...
   ↓
exception
   ↓
ROLLBACK
```

---

# **7. The actual sequence**

Our service should conceptually do:

```text
1. Authorize caller
2. BEGIN transaction
3. Lock project
4. Verify project active
5. Verify target user exists
6. Verify membership doesn't already exist
7. Count members
8. Reject if >= 10
9. Insert membership
10. COMMIT
```

The important thing is that the concurrency-sensitive steps happen inside the same transaction.

---

# **8. Why order matters**

Suppose we instead did:

```text
count members
      ↓
lock project
      ↓
insert
```

That’s wrong.

Another transaction could change membership between:

```text
count
```

and:

```text
lock
```

We want the coordination point established **before** making the decision.

So:

```text
LOCK
 ↓
CHECK
 ↓
CHANGE
```

is the important pattern.

---

# **9. Membership repository**

We want a method like:

```java
public interface ProjectMembershipRepository
        extends JpaRepository<ProjectMembership, ProjectMembershipId> {

    boolean existsByProjectIdAndUserId(
            Long projectId,
            Long userId
    );

    long countByProjectId(Long projectId);
}
```

Now our service can express the business rules clearly.

But there’s another important detail.

---

# **10. Duplicate membership**

Suppose two requests both try:

```text
Project 7 + User 42
```

Our application checks:

```java
existsByProjectIdAndUserId(7L, 42L)
```

Both could theoretically see:

```text
false
```

if the operation wasn’t coordinated properly.

Therefore:

```sql
PRIMARY KEY (project_id, user_id)
```

is still our final safety net.

This is a general rule:

**Application checks improve behavior; database constraints enforce invariants.**

---

# **11. The service design**

Conceptually:

```java
@Transactional
public void addMember(Long projectId, Long userId) {

    Project project =
        projectRepository.findByIdForUpdate(projectId)
            .orElseThrow(ProjectNotFoundException::new);

    if (project.getStatus() != ProjectStatus.ACTIVE) {
        throw new ProjectNotActiveException();
    }

    if (membershipRepository.existsByProjectIdAndUserId(
            projectId, userId)) {
        throw new AlreadyMemberException();
    }

    long memberCount =
        membershipRepository.countByProjectId(projectId);

    if (memberCount >= 10) {
        throw new ProjectFullException();
    }

    membershipRepository.save(
        new ProjectMembership(projectId, userId)
    );
}
```

Don’t memorize this code.

Understand the sequence:

```text
lock
 ↓
validate
 ↓
check duplicate
 ↓
check capacity
 ↓
insert
```

---

# **12. What happens with two requests?**

Suppose:

```text
Project 7 = 9 members
```

Request A:

```text
Alice adds Bob
```

Request B:

```text
Alice adds Carol
```

Both arrive simultaneously.

### **Request A**

```text
LOCK Project 7
```

succeeds.

### **Request B**

```text
LOCK Project 7
```

waits.

A checks:

```text
9 < 10
```

Then inserts Bob:

```text
10 members
```

A commits.

Now B obtains the lock.

B checks:

```text
10 >= 10
```

So:

```text
ProjectFullException
```

No 11th member.

---

# **13. This is pessimistic concurrency control**

We’re essentially saying:

“Conflicts are possible, so coordinate access before proceeding.”

That’s why it’s called pessimistic.

We don’t wait until the conflict happens.

We prevent competing operations from simultaneously making the decision.

---

# **14. What if we used optimistic locking instead?**

Let’s consider another design.

Project:

```text
id = 7
version = 20
```

Two transactions read:

```text
A → version 20
B → version 20
```

A modifies project:

```text
20 → 21
```

B later tries to modify version 20.

The version doesn’t match.

The second operation fails with an optimistic-locking conflict.

Spring Data JPA supports optimistic locking through JPA’s versioning mechanism.  

---

# **15. But there’s a subtle problem**

Our membership count is stored in:

```text
project_members
```

while the version is on:

```text
projects
```

If our operation doesn’t actually update the `Project` entity, simply having:

```java
@Version
private Long version;
```

doesn’t magically serialize membership inserts.

That’s an important lesson.

**Optimistic locking protects versioned entity updates; it isn’t a universal lock around related tables.**

For our capacity invariant, locking the project row explicitly is easier to reason about.

---

# **16. Could we maintain a member count?**

Suppose Project has:

```text
member_count = 9
```

Then our operation might be:

```text
UPDATE projects
SET member_count = member_count + 1
WHERE id = 7
  AND member_count < 10;
```

Then inspect affected rows.

```text
1 row → success
0 rows → full
```

This is an example of the **atomic SQL** strategy from the previous lesson.

It can be extremely efficient.

But now we have to keep:

```text
member_count
```

consistent with:

```text
project_members
```

So we’ve introduced another invariant.

There is no free lunch.

---

# **17. Database design matters**

You might think:

“Why not just store `member_count`?”

Sometimes that’s a good optimization.

But then you have:

```text
project.member_count
```

and:

```text
COUNT(project_members)
```

which must agree.

If something inserts a membership without incrementing the counter:

```text
member_count = 9
actual rows = 10
```

your system is inconsistent.

This is why denormalized counters should be introduced deliberately.

---

# **18. Transaction boundaries**

Here’s something very important.

Don’t do:

```text
Controller
 ↓
check capacity
 ↓
Service
 ↓
save
```

with the transaction only around the save.

The concurrency-sensitive operation needs one transaction:

```text
BEGIN
 ↓
lock
 ↓
check
 ↓
insert
 ↓
COMMIT
```

Spring’s transaction abstraction is specifically intended to define such transactional boundaries.  

---

# **19. What about authorization?**

Remember our earlier rule:

```text
posts.delete
AND
resource policy
```

For member management:

```text
projects.members.manage
AND
caller is project OWNER
```

Authorization should happen before we perform the mutation.

For example:

```java
@PreAuthorize(
    "hasAuthority('projects.members.manage') " +
    "and @projectPolicy.canManageMembers(authentication, #projectId)"
)
@Transactional
public void addMember(Long projectId, Long userId) {
    ...
}
```

But be careful.

If `projectPolicy` itself performs a database query, we need to think about the transaction and locking behavior.

---

# **20. Authorization and locking are different**

Don’t confuse:

```text
Can Alice manage Project 7?
```

with:

```text
Can Alice safely add another member to Project 7?
```

The first is:

```text
authorization
```

The second is:

```text
concurrency/correctness
```

You need both.

---

# **21. A better service boundary**

Often I’d structure the operation conceptually as:

```text
Controller
   ↓
authorization
   ↓
transactional application service
   ↓
lock project
   ↓
business invariants
   ↓
database mutation
```

The authorization policy can establish **who may attempt the operation**.

The transaction establishes **whether the operation can safely occur under concurrency**.

---

# **22. What if the lock fails?**

Locks can encounter:

```text
timeout
deadlock
transaction failure
database connectivity failure
```

These aren’t necessarily business errors.

For example:

```text
ProjectFullException
```

means:

The operation is not allowed because the project is full.

Whereas:

```text
PessimisticLockingFailureException
```

indicates a concurrency/infrastructure problem.

Don’t turn both into:

```http
400 Bad Request
```

---

# **23. Retrying concurrency failures**

Some transient concurrency failures are retryable.

Spring’s current documentation specifically discusses retrying concurrency failures such as deadlock losers, and emphasizes that the operation should be appropriate to retry/idempotent. It also notes that when `@Retryable` is combined with `@Transactional`, retry should surround the transaction so each attempt gets a fresh transaction.  

Conceptually:

```text
Retry
  ↓
Transaction
  ↓
Operation
```

not:

```text
Transaction
  ↓
Retry
  ↓
Operation
```

Why?

Because after a transaction fails, you want:

```text
rollback
 ↓
fresh transaction
 ↓
retry
```

rather than trying to reuse a broken transaction.

---

# **24. Don’t retry business failures**

This is extremely important.

Don’t do:

```text
ProjectFullException
 ↓
retry
 ↓
ProjectFullException
 ↓
retry
```

The project is actually full.

Retrying won’t change that.

Retry things like:

```text
temporary deadlock
transient database failure
serialization conflict
```

when your operation is safe to retry.

Don’t blindly retry:

```text
invalid request
permission denied
duplicate business operation
project full
user doesn't exist
```

---

# **25. The retry storm problem**

Imagine 1,000 requests all hit a temporary DB conflict.

You retry all 1,000 immediately.

Now:

```text
DB overloaded
 ↓
requests fail
 ↓
1,000 retries
 ↓
DB even more overloaded
 ↓
more failures
```

That’s a retry storm.

So production retry policies generally need:

```text
limited attempts
+
backoff
+
possibly jitter
+
only retry appropriate failures
```

We covered this conceptually in the reliability lesson; now you can see how it applies to database concurrency.

---

# **26. Don’t hold locks while doing external calls**

This is one of the most important practical rules.

Bad:

```java
@Transactional
public void addMember(...) {

    lockProject();

    callEmailProvider(); // network call

    saveMembership();
}
```

Now your database lock might remain held while:

```text
email provider
```

takes:

```text
3 seconds
```

or:

```text
30 seconds
```

or:

```text
times out
```

You’ve unnecessarily tied database resources to an external system.

---

# **27. Better architecture**

Instead:

```text
Transaction
    ↓
insert membership
    ↓
outbox event
    ↓
COMMIT
```

Then:

```text
Outbox
    ↓
RabbitMQ
    ↓
Notification Worker
    ↓
Email Provider
```

Now the DB transaction isn’t waiting for the email provider.

This is exactly where the Outbox pattern we learned earlier becomes valuable.

---

# **28. Entity lifecycle matters**

Suppose:

```java
@Transactional
public void addMember(...) {

    Project project = repository.findByIdForUpdate(...);

    // project is managed

    // ...

    membershipRepository.save(...);
}
```

Inside the transaction, the JPA persistence context tracks managed entities.

At commit:

```text
managed changes
      ↓
flush
      ↓
SQL
      ↓
database
```

This connects back to our earlier persistence-context lesson.

---

# 

# 

# **29.**

**`save()`**

**isn’t always the interesting part**

Developers sometimes think:

```java
repository.save(project);
```

is what makes the transaction work.

Not necessarily.

If:

```text
project
```

is already managed, modifying it can be enough:

```java
project.setStatus(ProjectStatus.ACTIVE);
```

and dirty checking detects the change.

The transaction boundary is what gives us the unit of work.

---

# **30. Repository method with locking**

A clean repository might look like:

```java
public interface ProjectRepository
        extends JpaRepository<Project, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
        select p
        from Project p
        where p.id = :projectId
        """)
    Optional<Project> findForUpdate(Long projectId);
}
```

Spring Data JPA’s `@Lock` is specifically designed to apply a JPA `LockModeType` to repository query methods, including redeclared CRUD methods.  

---

# 

# 

# **31. Why not put**

**`@Transactional`**

**on the repository?**

You generally want the transaction boundary around the **business operation**, not an individual repository call.

We need:

```text
lock
+
check
+
insert
```

to belong to one transaction.

So:

```java
@Transactional
public void addMember(...) {
    projectRepository.findForUpdate(...);
    membershipRepository.count(...);
    membershipRepository.save(...);
}
```

is conceptually correct.

---

# **32. The complete design**

Here’s our ProjectHub operation:

```text
POST /projects/7/members/42
                |
                v
        Spring Security
                |
                v
        Authorization policy
                |
                v
       MembershipService
                |
          @Transactional
                |
                v
     lock Project 7
                |
                v
       project active?
                |
                v
       already member?
                |
                v
       member count < 10?
                |
                v
       insert membership
                |
                v
       create outbox event
                |
                v
             COMMIT
                |
                v
          HTTP 201/204
```

Then asynchronously:

```text
Outbox
   ↓
Publisher
   ↓
RabbitMQ
   ↓
Notification Worker
```

That’s a production-quality architectural pattern.

---

# **33. One more subtle issue: counting**

We used:

```java
long count = membershipRepository.countByProjectId(projectId);
```

That works conceptually.

But remember:

```text
count query
+
insert
```

must occur under the appropriate concurrency strategy.

If you remove the project lock:

```text
count = 9
```

two transactions can both make the decision.

So the correctness comes from the **whole operation**, not from the count query itself.

---

# **34. Alternative: optimistic design**

There are cases where we’d prefer:

```text
Project
version
```

and retry on conflict.

For example:

```text
1. read project
2. determine new state
3. update versioned entity
4. if version conflict → retry
```

That’s especially useful when:

```text
conflicts are relatively rare
```

and blocking isn’t desirable.

For highly contended shared resources, explicit locking or an atomic database operation may be easier to reason about.

---

# **35. Don’t choose based on fashion**

Bad reasoning:

```text
"Optimistic locking is modern."
```

or:

```text
"Pessimistic locking is safer."
```

Instead:

```text
What is the invariant?
How frequently do conflicts occur?
How expensive is waiting?
Can we express the invariant atomically?
Can the DB enforce it?
Can the operation be retried?
```

That’s engineering.

---

# **36. Our ProjectHub rulebook**

For this specific membership feature, I’d establish:

### **Database**

```text
PRIMARY KEY(project_id, user_id)
```

### **Transaction**

```text
@Transactional
```

### **Coordination**

```text
PESSIMISTIC_WRITE on Project
```

### **Business rules**

```text
project active
user not already member
member count < 10
```

### **Side effects**

```text
outbox event
```

### **External notification**

```text
asynchronous
```

### **Retry**

```text
only appropriate transient concurrency failures
```

That’s a complete design.

---

# **37. What you’ve learned**

You can now connect several previously separate concepts:

```text
JPA
 ↓
Persistence Context
 ↓
Transactions
 ↓
Database Isolation
 ↓
Locks
 ↓
Concurrency
 ↓
Spring Data @Lock
 ↓
Optimistic @Version
 ↓
Retries
 ↓
Outbox
 ↓
RabbitMQ
```

This is the point where Spring Boot stops being merely:

“How do I create a REST API?”

and becomes:

“How do I build a backend that stays correct when many things happen simultaneously?”

That’s a much more important skill.

---

# **Exercise 61**

Don’t write a giant amount of code yet. Design first.

### **1. Repository**

Write the `ProjectRepository` method that retrieves a project using:

```text
PESSIMISTIC_WRITE
```

and explain why it needs to be used inside a transaction.

---

### **2. Service**

Design the sequence for:

```text
addMember(projectId, userId)
```

using:

```text
@Transactional
```

Include the exact order of:

```text
authorization
lock
validation
duplicate check
capacity check
insert
outbox
commit
```

---

### **3. Concurrency**

Starting with:

```text
Project 7 = 9 members
```

show what happens when:

```text
Request A
Request B
```

arrive simultaneously.

Show which request waits and why the final count cannot become 11.

---

### **4. Database constraint**

Write the database constraint that prevents:

```text
Project 7 + User 42
```

from appearing twice.

Then explain why the constraint is still necessary even though Java checks for an existing membership.

---

### **5. Retry**

Suppose Request A gets a transient deadlock/concurrency failure.

Explain:

```text
rollback
   ↓
fresh transaction
   ↓
retry
```

Why shouldn’t we simply continue using the failed transaction?

Spring’s current transaction/retry documentation explicitly describes the importance of a fresh transaction per retry attempt.  

---

### **6. Architecture**

Explain why this is dangerous:

```text
@Transactional
lock Project
   ↓
call external email API
   ↓
insert membership
   ↓
commit
```

Then redesign it using:

```text
transaction
+
outbox
+
RabbitMQ
```

---

### **7. Final challenge**

Compare these three approaches for the “maximum 10 members” invariant:

```text
A. Pessimistic lock on Project
B. Optimistic @Version
C. Atomic SQL update/counter
```

For each, explain:

- How it prevents the race
- What happens under contention
- What happens when a conflict occurs
- What additional invariant/complexity it introduces

Once you understand that comparison, you’ll be able to choose concurrency strategies rather than just memorizing annotations.

**Next: Lesson 62 — Spring Transactions Deep Dive: propagation,** **`REQUIRES_NEW`****, rollback rules, isolation configuration, transaction boundaries, self-invocation, and the traps that cause production data bugs.**