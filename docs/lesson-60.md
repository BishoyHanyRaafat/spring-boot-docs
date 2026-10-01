---
title: "Lesson 60: Advanced Database Concurrency"
sidebar_position: 60
---

This lesson is one of the most important database lessons in the entire course.

So far we’ve learned:

```text
@Transactional
locking
@Version
race conditions
```

Now we’re going to understand **why** these mechanisms exist.

The central question is:

**What happens when two requests try to change the same data at the same time?**

PostgreSQL uses MVCC plus transaction-isolation mechanisms to control concurrent access, and it also provides explicit row/table locks when application-level consistency requires them.  

---

# **1. Concurrency is normal**

Imagine ProjectHub has:

```text
Alice
Bob
Carol
```

All three use the application simultaneously.

So PostgreSQL might receive:

```text
Transaction A
Transaction B
Transaction C
```

at nearly the same time.

The database needs to answer:

```text
Who sees what?
Who can change what?
What happens when they conflict?
```

That’s **concurrency control**.

---

# **2. The simplest race condition**

Suppose:

```text
balance = 100
```

Alice withdraws:

```text
30
```

Bob withdraws:

```text
80
```

Both requests arrive simultaneously.

Naive application logic:

```text
read balance
if balance >= amount
    subtract amount
```

Alice:

```text
100 >= 30 → yes
```

Bob:

```text
100 >= 80 → yes
```

Both proceed.

Potential result:

```text
100 - 30 - 80 = -10
```

But our business rule was:

```text
balance must never be negative
```

We have a concurrency bug.

---

# 

# 

# **3. Why**

**`if`**

**isn’t enough**

You might write:

```java
if (account.getBalance().compareTo(amount) >= 0) {
    account.setBalance(account.getBalance().subtract(amount));
}
```

This is logically correct **for one request**.

But two requests can execute the read before either update becomes visible.

The problem isn’t Java syntax.

It’s the gap between:

```text
CHECK
```

and:

```text
CHANGE
```

That’s the classic:

**check-then-act race condition**

---

# **4. Transactions don’t automatically solve every race**

This is an important distinction.

You might think:

```java
@Transactional
public void withdraw(...) {
    ...
}
```

means:

“Nobody else can interfere.”

No.

A transaction gives you atomicity and isolation according to its configured isolation level, but concurrent transactions can still interact in ways your business rule doesn’t permit.

PostgreSQL’s default isolation level is **Read Committed**. A normal `SELECT` sees data committed before that particular query began; two successive `SELECT`s in the same transaction can therefore see different committed states.  

So:

```text
@Transactional
```

is not synonymous with:

```text
"exclusive access"
```

---

# **5. Isolation levels**

A database isolation level defines how transactions interact with concurrent transactions.

The major levels you’ll encounter are:

```text
Read Uncommitted
Read Committed
Repeatable Read
Serializable
```

PostgreSQL’s implementation has specific behavior around these levels, and its documented concurrency-control chapter covers Read Committed, Repeatable Read and Serializable.  

For ProjectHub, focus heavily on:

```text
Read Committed
Repeatable Read
Serializable
```

---

# **6. Dirty reads**

Imagine:

```text
Transaction A
```

changes:

```text
name = "Alice"
```

but hasn’t committed yet.

Transaction B reads:

```text
"Alice"
```

Then A rolls back.

Now B read data that never actually became committed.

That’s a:

**dirty read**

PostgreSQL’s normal Read Committed behavior does not expose uncommitted changes this way.  

---

# **7. Non-repeatable reads**

Suppose Transaction A does:

```sql
SELECT balance FROM accounts WHERE id = 1;
```

and sees:

```text
100
```

Then Transaction B commits:

```text
balance = 50
```

Transaction A executes the same query again.

It might now see:

```text
50
```

Same transaction.

Same query.

Different result.

That’s a:

**non-repeatable read**

Under PostgreSQL’s Read Committed behavior, this is possible because each statement gets its own snapshot.  

---

# **8. Repeatable Read**

Repeatable Read gives the transaction a stable view of the data for its execution.

Conceptually:

```text
Transaction A starts
       ↓
snapshot
       ↓
SELECT → 100
       ↓
Transaction B changes value
       ↓
SELECT → still based on A's snapshot
```

So the transaction doesn’t simply see arbitrary changes appearing between its reads.

But there’s an important detail:

Repeatable Read does not mean “nothing can conflict.”

Concurrent writes can still cause serialization failures or other conflicts that the application must handle appropriately. PostgreSQL documents these concurrency behaviors explicitly.  

---

# **9. Serializable**

At the strongest standard isolation level:

```text
SERIALIZABLE
```

the database aims to make concurrent transactions behave as if they had executed one after another.

Conceptually:

```text
A then B
```

or:

```text
B then A
```

rather than allowing an invalid interleaving.

PostgreSQL’s Serializable mode uses Serializable Snapshot Isolation and may abort transactions with serialization failures; applications should be prepared to retry those transactions.  

---

# **10. Serializable doesn’t mean “free”**

You might think:

“Why don’t we just use Serializable everywhere?”

Because stronger concurrency guarantees can reduce concurrency and produce transaction retries.

Imagine:

```text
100 concurrent transactions
```

If many conflict:

```text
successful transactions
+
serialization failures
+
retries
```

can increase workload.

So the right question is:

**What isolation does this particular business operation require?**

---

# **11. A ProjectHub example**

Suppose:

```text
Project 7
maximum members = 10
current members = 9
```

Two requests arrive:

```text
Alice adds Bob
Alice adds Carol
```

We need this invariant:

```text
members <= 10
```

A plain:

```text
SELECT COUNT(*)
```

followed by:

```text
INSERT
```

can race.

We need a concurrency strategy.

---

# **12. Strategy 1 — Lock something**

One approach is to lock the project row.

Conceptually:

```sql
SELECT *
FROM projects
WHERE id = 7
FOR UPDATE;
```

Then:

```text
Transaction A
    ↓
locks Project 7
    ↓
checks membership count
    ↓
inserts member
    ↓
commit

Transaction B
    ↓
waits for Project 7
    ↓
checks updated count
    ↓
may reject
```

PostgreSQL’s `FOR UPDATE` locks selected rows against conflicting updates/deletes/locking operations until the transaction ends.  

---

# **13. Why lock the project row?**

Notice something interesting.

The thing we’re actually changing is:

```text
project_members
```

But we’re locking:

```text
projects.id = 7
```

Why?

Because we’re using the project row as a **coordination point**.

We’re effectively saying:

“Any operation that changes membership capacity for Project 7 must first obtain the Project 7 lock.”

Then concurrent membership operations serialize around that row.

---

# **14. This requires discipline**

Suppose one piece of code does:

```text
lock Project 7
insert member
```

but another does:

```text
insert member
```

without acquiring the lock.

Then your coordination rule is incomplete.

So explicit locking works only when all relevant operations respect the same protocol.

---

# **15. Strategy 2 — Optimistic locking**

Instead of blocking other transactions, we can detect conflicts.

Entity:

```java
@Entity
public class Project {

    @Id
    private Long id;

    @Version
    private Long version;
}
```

Spring Data’s `@Version` marks a property used for optimistic locking.  

Imagine:

```text
Project version = 5
```

Alice reads:

```text
version 5
```

Bob reads:

```text
version 5
```

Alice updates:

```text
5 → 6
```

Bob then tries to update based on version 5.

The expected version no longer matches.

Result:

```text
conflict
```

rather than silently overwriting Alice’s change.

---

# **16. Optimistic locking mindset**

Think:

```text
Pessimistic:

"Nobody else touch this while I'm working."


Optimistic:

"Go ahead, but I'll detect if someone changed it."
```

Optimistic locking is often attractive when conflicts are relatively uncommon.

---

# **17. Lost updates**

Consider:

```text
title = "Hello"
```

Alice changes:

```text
"Hello" → "Hello Alice"
```

Bob changes:

```text
"Hello" → "Hello Bob"
```

If both read the old value and then blindly write their own version:

```text
Alice writes
Bob writes
```

the final value could be:

```text
"Hello Bob"
```

Alice’s update disappeared.

That’s a:

**lost update**

Optimistic locking can detect this instead of silently accepting the second stale write.

---

# **18. Explicit row locking**

PostgreSQL supports several row-level lock modes.

The most familiar is:

```sql
SELECT ...
FOR UPDATE;
```

There are also:

```text
FOR NO KEY UPDATE
FOR SHARE
FOR KEY SHARE
```

with different conflict behavior. PostgreSQL documents these row-level locks as tools for application-controlled concurrency where MVCC alone isn’t enough.  

For now, remember:

```text
FOR UPDATE
```

means:

“I intend to modify these rows; coordinate concurrent writers around them.”

---

# **19. Locks live inside transactions**

Consider:

```text
BEGIN

SELECT ... FOR UPDATE;

UPDATE ...

COMMIT
```

The lock is associated with the transaction and is normally held until the transaction ends.  

Therefore:

```text
long transaction
```

can mean:

```text
long-held lock
```

which can mean:

```text
other transactions waiting
```

which can mean:

```text
higher latency
```

This connects directly to our performance lesson.

---

# **20. Lock contention**

Suppose:

```text
Project 7
```

is extremely popular.

Every membership operation locks:

```text
Project 7
```

Then:

```text
Request A ─┐
Request B ─┤
Request C ─┤→ waiting for Project 7
Request D ─┤
Request E ─┘
```

Now correctness is protected, but throughput may suffer.

This is **lock contention**.

---

# **21. Correctness vs concurrency**

This is the tradeoff:

```text
More coordination
      ↓
stronger control
      ↓
potentially less concurrency
```

while:

```text
Less coordination
      ↓
more concurrency
      ↓
greater risk of races
```

Good backend engineering finds the smallest amount of coordination necessary to protect the business invariant.

---

# **22. Deadlocks**

Here’s a classic example.

Transaction A:

```text
lock Project 1
lock Project 2
```

Transaction B:

```text
lock Project 2
lock Project 1
```

Timeline:

```text
A locks 1
B locks 2

A waits for 2
B waits for 1
```

That’s:

```text
A → waiting for B
B → waiting for A
```

Deadlock.

PostgreSQL detects deadlocks and aborts one of the conflicting transactions so the system can continue. Its documentation explicitly covers deadlocks as part of explicit locking.  

---

# **23. Preventing deadlocks**

A very useful technique:

**Acquire locks in a consistent order.**

For example:

```text
always lock lower project ID first
```

So everyone follows:

```text
Project 1 → Project 2
```

rather than:

```text
sometimes 1 → 2
sometimes 2 → 1
```

This reduces circular waiting.

---

# **24. Locking isn’t always the answer**

Suppose we have:

```text
10 million posts
```

and a normal read:

```sql
SELECT * FROM posts WHERE project_id = 7;
```

We generally don’t want every read to lock those rows.

PostgreSQL’s MVCC is specifically designed to let normal reads and writes proceed with much less blocking than traditional locking approaches.  

So:

```text
normal read
```

usually doesn’t need:

```text
FOR UPDATE
```

---

# **25. Use locking for a business invariant**

Good candidate:

```text
withdraw money
reserve inventory
allocate limited resource
enforce capacity
```

Less appropriate:

```text
ordinary GET /posts
```

Ask:

**What concurrent operation would make this result invalid?**

That’s the key question.

---

# **26. Atomic SQL can sometimes be better**

Consider inventory:

```text
stock = 5
```

You want:

```text
decrease stock by 1
```

Instead of:

```text
SELECT stock
↓
Java checks stock
↓
UPDATE stock
```

you can sometimes make the database operation itself conditional:

```sql
UPDATE products
SET stock = stock - 1
WHERE id = :id
  AND stock > 0;
```

Then inspect the number of affected rows.

Conceptually:

```text
1 row updated → reservation succeeded
0 rows updated → insufficient stock / no matching item
```

Now the condition and modification happen together in one database operation.

That’s often much cleaner.

---

# **27. Why atomic operations are powerful**

Instead of:

```text
READ
CHECK
WRITE
```

try to express:

```text
CONDITIONAL WRITE
```

when possible.

This reduces the race window.

It’s one of the most useful concurrency patterns to learn.

---

# **28. Unique constraints are another form of concurrency control**

Suppose usernames must be unique.

Don’t rely solely on:

```java
if (!userRepository.existsByUsername(username)) {
    save(user);
}
```

Two requests can both observe:

```text
username doesn't exist
```

Instead:

```sql
username VARCHAR(100) UNIQUE
```

makes the database the final authority.

Then:

```text
Request A → INSERT → success
Request B → INSERT → constraint violation
```

The application translates that into something like:

```http
409 Conflict
```

---

# **29. Database constraints are extremely valuable**

For ProjectHub:

```text
users.username UNIQUE
users.email UNIQUE

permissions.name UNIQUE
roles.name UNIQUE

role_permissions
PRIMARY KEY(role_id, permission_id)

user_roles
PRIMARY KEY(user_id, role_id)
```

These aren’t just schema decorations.

They’re **correctness guarantees**.

---

# **30. Isolation vs locking**

These concepts are related but different.

### **Isolation level**

Controls the transaction’s visibility/concurrency semantics.

```text
READ COMMITTED
REPEATABLE READ
SERIALIZABLE
```

### **Explicit locking**

Says:

```text
"Coordinate access to this particular data."
```

Example:

```sql
SELECT ... FOR UPDATE
```

You can use both together.

---

# **31. A ProjectHub membership operation**

Let’s design it conceptually.

Requirement:

```text
Project may have at most 10 members.
```

Service:

```text
@Transactional
addMember(projectId, userId)
```

Possible flow:

```text
1. Lock project row
2. Check project is active
3. Check user isn't already a member
4. Count current members
5. If count >= 10 → reject
6. Insert membership
7. Commit
```

The critical part is that the relevant checks happen inside the same transaction and under the chosen concurrency-control strategy.

---

# **32. What happens concurrently?**

Request A:

```text
lock Project 7
```

Request B:

```text
tries to lock Project 7
```

B waits.

A:

```text
count = 9
insert
commit
```

Now B continues.

B sees:

```text
count = 10
```

and rejects.

Invariant preserved:

```text
members <= 10
```

PostgreSQL explicitly documents `SELECT FOR UPDATE` as a mechanism for protecting rows against concurrent updates within a transaction.  

---

# **33. But what about duplicate membership?**

We should still have:

```sql
PRIMARY KEY(project_id, user_id)
```

or an equivalent unique constraint.

Why?

Because locking the project row doesn’t necessarily protect against every possible code path.

The database should enforce:

```text
one membership per user/project
```

So we have multiple layers:

```text
Application policy
       +
Transaction
       +
Lock/concurrency strategy
       +
Database constraint
```

That’s robust engineering.

---

# **34. Serialization failures**

With Serializable isolation, you may get:

```text
Transaction A
Transaction B
      ↓
conflict
      ↓
one transaction aborted
```

This isn’t necessarily a system failure.

It can be the database saying:

“These operations couldn’t safely be serialized together. Try again.”

Therefore some serializable workflows need retry logic.

PostgreSQL explicitly documents serialization failures and the need for applications to handle them.  

---

# **35. Retry carefully**

Suppose:

```text
@Transactional
operation()
```

fails due to a serialization conflict.

A retry may be appropriate.

But don’t blindly retry everything.

You need to consider:

```text
Was the transaction actually rolled back?
Is the operation safe to retry?
Could external side effects have occurred?
Could retries amplify load?
```

This connects concurrency with our earlier lesson on idempotency.

---

# **36. Concurrency + external APIs**

Imagine:

```text
@Transactional
createOrder()
```

and inside it:

```text
callExternalPaymentAPI()
```

If the database transaction later rolls back, the payment provider might already have charged the customer.

Now we have:

```text
DB = rolled back
Payment = succeeded
```

That’s why local database transactions should not be confused with distributed transactions.

Use patterns such as:

```text
transactional state
+
outbox
+
idempotent external operation
+
asynchronous workflow
```

where appropriate.

---

# **37. Spring/JPA perspective**

At the service level, you might have:

```java
@Transactional
public void addMember(Long projectId, Long userId) {
    // concurrency-sensitive operation
}
```

The transaction boundary is important.

But JPA also needs to know whether you’re using:

```text
optimistic locking
```

or:

```text
pessimistic locking
```

For example, Spring Data JPA supports locking metadata on repository methods.

Conceptually:

```java
@Lock(LockModeType.PESSIMISTIC_WRITE)
Optional<Project> findById(Long id);
```

The exact locking behavior ultimately comes from the database and SQL generated by the persistence layer.

The database is the authority.

---

# **38. Don’t overuse pessimistic locking**

If every repository method becomes:

```text
PESSIMISTIC_WRITE
```

you can end up with:

```text
lots of locks
lots of waiting
low concurrency
deadlocks
poor throughput
```

Use it deliberately.

Most ordinary reads should remain ordinary reads.

---

# **39. A useful decision tree**

When you have a concurrency-sensitive operation, ask:

```text
Does the database have a constraint
that expresses the invariant?
        |
       yes
        ↓
Use the constraint.

       no
        ↓
Can the operation be expressed
as one atomic SQL statement?
        |
       yes
        ↓
Use atomic update/insert.

       no
        ↓
Can optimistic locking detect conflicts?
        |
       yes
        ↓
Use @Version / optimistic strategy.

       no
        ↓
Would explicit locking protect the invariant?
        |
       yes
        ↓
Use appropriate row locking.

       no
        ↓
Consider stronger isolation /
different data model / workflow design.
```

This is a much better mental model than:

“When in doubt, add a lock.”

---

# **40. The most important distinction**

Memorize this:

```text
Transaction
    ≠
Lock
    ≠
Isolation level
    ≠
Optimistic locking
```

They’re related but solve different problems.

### **Transaction**

Defines an atomic unit of database work.

### **Isolation**

Defines how concurrent transactions interact/observe data.

### **Explicit lock**

Coordinates access to particular database resources.

### **Optimistic locking**

Detects conflicting updates rather than preventing them up front.

---

# **41. ProjectHub concurrency toolbox**

For ProjectHub, you’ll eventually use:

```text
Database constraints
        ↓
Unique / FK / CHECK

Transactions
        ↓
@Transactional

Optimistic locking
        ↓
@Version

Pessimistic locking
        ↓
SELECT FOR UPDATE / JPA lock modes

Isolation
        ↓
READ COMMITTED / REPEATABLE READ / SERIALIZABLE

Atomic SQL
        ↓
conditional UPDATE/INSERT

Retries
        ↓
serialization/conflict recovery

Idempotency
        ↓
safe repeated operations
```

These are tools, not competing religions.

---

# **42. The engineer’s mindset**

When someone says:

“This endpoint sometimes creates duplicate memberships.”

Don’t immediately say:

“Use synchronized.”

Instead ask:

```text
Where is the invariant?

Who can violate it?

Can two requests execute concurrently?

What transaction boundary exists?

What isolation level?

Is there a database constraint?

Can the operation be atomic?

Would optimistic locking work?

Would a row lock work?

Can retries occur?

Are there external side effects?
```

That’s how you diagnose concurrency bugs.

---

# **Exercise 60**

### **1. Isolation**

Explain the difference between:

```text
READ COMMITTED
REPEATABLE READ
SERIALIZABLE
```

You don’t need to memorize every database-specific implementation detail yet.

Focus on the conceptual guarantee.

---

### **2. Lost update**

Initial:

```text
title = "Hello"
```

Alice and Bob both read it.

Alice changes:

```text
"Hello Alice"
```

Bob changes:

```text
"Hello Bob"
```

Both save.

Explain how Bob can accidentally overwrite Alice.

Then explain how:

```java
@Version
```

changes the outcome.

---

### **3. Membership race**

Project 7:

```text
members = 9
max = 10
```

Two concurrent requests add members.

Design **two solutions**:

**A.** Optimistic approach  
**B.** Pessimistic/locking approach

Explain the exact sequence for each.

---

### **4. Atomic SQL**

You have:

```text
stock = 3
```

Write the SQL conceptually needed to safely decrement stock only when stock is greater than zero.

Then explain why:

```text
SELECT stock
↓
Java if
↓
UPDATE
```

is more vulnerable to races.

---

### **5. Constraints**

Why should this database table have:

```sql
UNIQUE(project_id, user_id)
```

even if your service already checks:

```java
membershipRepository.existsByProjectIdAndUserId(...)
```

?

---

### **6. Lock contention**

Suppose Project 7 gets:

```text
10,000 membership requests/sec
```

and every request locks the same Project row.

What happens?

Would the lock still be correct?

Could it become a performance bottleneck?

---

### **7. Serializable**

Suppose a Serializable transaction fails with a serialization conflict.

Should the application necessarily treat that as a permanent business failure?

What might it do instead?

What must you consider before retrying?

---

### **8. Final ProjectHub challenge**

Design this operation:

```http
POST /projects/{projectId}/members/{userId}
```

Requirements:

```text
1. User must have permission to manage members.
2. Project must be active.
3. User cannot already be a member.
4. Project has a maximum of 10 members.
5. Two simultaneous requests must not create 11 members.
6. Duplicate membership must be impossible.
```

Describe:

```text
Controller
    ↓
Service
    ↓
Transaction
    ↓
Authorization
    ↓
Concurrency strategy
    ↓
Database constraints
```

**Don’t write the full code yet.**

Design the solution first.

That’s the skill we’re building.

**Next: Lesson 61 — Advanced JPA Concurrency:** **`@Version`****, pessimistic locks,** **`@Lock`****, transaction boundaries, retries, and implementing the ProjectHub membership operation safely.**