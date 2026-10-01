---
title: "Lesson 45: Database Scaling Indexes, Read Replicas, Sharding, and High Traffic Design"
sidebar_position: 45
---

Welcome to one of the most important backend engineering topics.

Until now, we improved performance using:

```text
Client
 |
 v
Gateway
 |
 v
Service
 |
 v
Redis
 |
 v
Database
```

But eventually:

- Redis is not enough
- Database receives millions of requests
- Tables contain billions of rows

Now we need database scaling.

---

# **1. The database scaling problem**

Imagine ProjectHub grows:

```text
Users:

10 million


Projects:

500 million


Tasks:

5 billion
```

Now this query:

```sql
SELECT *
FROM projects
WHERE owner_id = 100;
```

can become slow.

Why?

Because the database has to search a huge amount of data.

---

# **2. The first optimization: indexes**

Before scaling databases, optimize queries.

An index is a data structure that helps the database find data faster.

Think of a book.

Without an index:

```text
Read every page until you find the topic.
```

With an index:

```text
Topic → Page number
```

You jump directly.

---

# **3. Without an index**

Table:

```text
projects

id | owner_id | name
--------------------
1  | 10       | App
2  | 20       | Shop
3  | 10       | Website
4  | 50       | CRM
```

Query:

```sql
SELECT *
FROM projects
WHERE owner_id = 10;
```

Database:

```text
Check row 1
Check row 2
Check row 3
Check row 4
...
```

This is:

```text
O(n)
```

---

# **4. With an index**

Create:

```sql
CREATE INDEX idx_project_owner
ON projects(owner_id);
```

Now database maintains:

```text
owner_id

10 → rows 1,3

20 → row 2

50 → row 4
```

Search becomes much faster.

---

# **5. Index types**

## **B-Tree index**

Most common.

Good for:

```sql
=
<
>
BETWEEN
ORDER BY
```

Example:

```sql
WHERE created_at > '2026-01-01'
```

---

## **Hash index**

Good for exact matching:

```sql
WHERE email='john@test.com'
```

---

## **Full-text index**

For searching text:

Example:

```text
"find projects containing Spring Boot"
```

---

# **6. What columns should be indexed?**

Good candidates:

## **Frequently searched columns**

Example:

```sql
WHERE user_id = ?
```

Index:

```text
user_id
```

---

## **Foreign keys**

Example:

```sql
project_members

project_id
user_id
```

Usually indexed.

---

## **Sorting columns**

Example:

```sql
ORDER BY created_at DESC
```

Index:

```text
created_at
```

---

# **7. Do not index everything**

Indexes have a cost.

Every index:

- consumes storage
- slows inserts
- slows updates

Example:

Insert:

```text
New project created
```

Database updates:

```text
projects table

+

10 indexes
```

---

# **8. Composite indexes**

Sometimes queries use multiple columns.

Example:

```sql
SELECT *
FROM tasks
WHERE project_id = 10
AND status='DONE';
```

Create:

```sql
CREATE INDEX idx_task_project_status
ON tasks(project_id,status);
```

---

Order matters.

This index helps:

```sql
WHERE project_id=10
```

and:

```sql
WHERE project_id=10
AND status='DONE'
```

but not necessarily:

```sql
WHERE status='DONE'
```

---

# **9. Query optimization**

Bad:

```sql
SELECT *
FROM projects;
```

If you only need:

```text
id
name
```

Do:

```sql
SELECT id,name
FROM projects;
```

Why?

Less data transferred.

---

# **10. Pagination**

Bad:

```sql
SELECT *
FROM projects
LIMIT 50 OFFSET 1000000;
```

Problem:

Database still scans previous rows.

---

Better:

Cursor pagination.

Example:

```sql
SELECT *
FROM projects
WHERE id > 10000
ORDER BY id
LIMIT 50;
```

Meaning:

“Give me the next 50 after ID 10000.”

---

# **11. Database scaling types**

There are two main approaches:

```text
1. Vertical scaling

2. Horizontal scaling
```

---

# **12. Vertical scaling**

Increase server power.

Example:

Before:

```text
CPU: 8 cores
RAM: 32GB
```

After:

```text
CPU: 64 cores
RAM: 256GB
```

---

Advantages:

- simple
- no application changes

---

Problems:

There is a limit.

You cannot buy an infinite machine.

---

# **13. Horizontal scaling**

Add more database servers.

Example:

```text
        Database


       +-------+

       |       |

       v       v


    Server1  Server2
```

Harder.

---

# **14. Read replicas**

One of the most common strategies.

Most applications have:

```text
Many reads

Few writes
```

Example:

ProjectHub:

Reads:

```text
GET /projects
GET /profile
GET /tasks
```

Writes:

```text
CREATE project
UPDATE task
```

---

Architecture:

```text
                 Application


                     |

          +----------+----------+

          |                     |

          v                     v


       Primary             Replica


       WRITE               READ


          |
          |
       Replication

          |
          v

       Replica
```

---

# **15. How replication works**

Primary:

```sql
INSERT INTO projects
VALUES (...)
```

Then:

```text
Primary

   |
   |
 copies changes

   |
   v

Replica
```

---

# **16. Important: replication delay**

Replicas are not always instant.

Example:

User creates:

```text
Project A
```

Primary:

```text
exists
```

Replica:

```text
not yet updated
```

This is called:

```text
Replication lag
```

---

# **17. Read/write splitting**

Application decides:

Writes:

```java
saveProject()
```

go to:

```text
Primary database
```

Reads:

```java
findProjects()
```

go to:

```text
Replica
```

---

Architecture:

```text
Project Service


        |

 +------+------+

 |             |

 v             v


WRITE        READ


Primary     Replica
```

---

# **18. Spring Boot multiple databases**

Example:

Primary datasource:

```yaml
spring:
 datasource:
   primary:
     url: jdbc:postgresql://primary/projecthub
```

Replica:

```yaml
spring:
 datasource:
   replica:
     url: jdbc:postgresql://replica/projecthub
```

---

Usually implemented with:

- routing datasource
- transaction rules

---

# **19. Database partitioning**

Partitioning means:

Split one table internally.

Example:

Huge table:

```text
events

5 billion rows
```

Partition by date:

```text
events_2026_01

events_2026_02

events_2026_03
```

---

Query:

```sql
WHERE date='2026-02-10'
```

Database only checks:

```text
events_2026_02
```

---

# **20. Partitioning vs indexing**

Index:

```text
Find rows faster
```

Partition:

```text
Reduce the amount of data searched
```

They solve different problems.

---

# **21. Sharding**

The big one.

Sharding means:

Split data across multiple databases.

Example:

Users:

```text
Database 1

users 1-1,000,000
```

```text
Database 2

users 1,000,001-2,000,000
```

---

Architecture:

```text
                Application


                    |

               Sharding Logic


        +-----------+-----------+

        |                       |

        v                       v


    Database A             Database B
```

---

# **22. Sharding key**

You need a rule.

Example:

```text
user_id % number_of_shards
```

Example:

3 databases:

```text
user_id 10

10 % 3 = 1

Database 1
```

---

# **23. Problems with sharding**

Sharding is powerful but difficult.

Problems:

## **Cross-shard queries**

Example:

“Find all users.”

Need:

```text
Database 1
+
Database 2
+
Database 3
```

---

## **Transactions**

Before:

```text
One database transaction
```

After:

```text
Multiple databases
```

Much harder.

---

## **Rebalancing**

Adding a new shard:

Before:

```text
3 databases
```

After:

```text
4 databases
```

Data movement required.

---

# **24. When should you shard?**

Usually only when:

- one database cannot handle the data
- replicas are not enough
- partitioning is not enough

Do not shard early.

---

# **25. Connection pooling**

A hidden database problem.

Every request:

```text
Open connection

Query

Close connection
```

is expensive.

Instead:

```text
Application

 |
 v

Connection Pool

 |
 +--- connection 1
 |
 +--- connection 2
 |
 +--- connection 3

 |
 v

Database
```

---

Spring Boot uses:

```text
HikariCP
```

by default.

---

# **26. Connection pool settings**

Example:

```yaml
spring:
 datasource:
   hikari:
     maximum-pool-size: 20
```

Meaning:

Maximum:

```text
20 database connections
```

---

# **27. Database transactions at scale**

A long transaction:

```sql
BEGIN;

update huge_table;

COMMIT;
```

can:

- lock rows
- slow others

Keep transactions short.

---

# **28. Event-driven database updates**

Instead of:

```text
Project Service

updates:

projects
users
analytics
notifications
```

Use:

```text
Project Service

updates project


publishes:

PROJECT_UPDATED


        |

        v

Other services update themselves
```

---

# **29. ProjectHub database architecture evolution**

## **Small system**

```text
Project Service

       |

 PostgreSQL
```

---

## **Growing system**

```text
Project Service

       |

      Redis

       |

 PostgreSQL
```

---

## **Bigger system**

```text
             Project Service


                    |

          +---------+---------+

          |                   |

          v                   v


      Primary            Replicas


      WRITE              READ
```

---

## **Very large system**

```text
                Application


                    |

               Sharding Layer


        +-----------+-----------+

        v                       v


    Database A              Database B
```

---

# **30. Production database checklist**

Before scaling:

✅ Add indexes  
✅ Optimize queries  
✅ Use pagination  
✅ Add caching  
✅ Use connection pooling

Then:

✅ Read replicas  
✅ Partitioning

Finally:

✅ Sharding

---

# **Lesson 45 Summary**

You learned:

✅ Database performance problems  
✅ Indexes  
✅ Composite indexes  
✅ Query optimization  
✅ Pagination  
✅ Vertical scaling  
✅ Horizontal scaling  
✅ Read replicas  
✅ Replication lag  
✅ Partitioning  
✅ Sharding  
✅ Connection pooling  
✅ Large-scale database architecture

---

# **Exercise 45**

Answer:

### **1.**

Why does this query become slow?

```sql
SELECT *
FROM projects
WHERE owner_id=10;
```

on a table with 500 million rows?

---

### **2.**

What is the difference between:

```
Index
```

and:

```
Partition
```

---

### **3.**

Why are read replicas useful?

---

### **4.**

Why can replication lag create problems?

---

### **5.**

When would you choose sharding?

---

### **6.**

Design the database architecture for ProjectHub with:

- 10 million users
- 500 million projects
- heavy reading
- normal writing

Draw:

```text
Application

     |

 ?

     |

Database architecture
```

---

Next lesson:

# **Lesson 46 — Messaging Systems: RabbitMQ, Kafka, Events, and Event-Driven Architecture**

We will go deeper into:

- message brokers
- queues vs topics
- RabbitMQ architecture
- Kafka architecture
- producers and consumers
- event ordering
- retries
- dead letter queues
- building reliable async systems

This is where ProjectHub becomes a true distributed system.