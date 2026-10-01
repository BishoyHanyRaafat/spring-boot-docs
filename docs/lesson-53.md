---
title: "Lesson 53: Kubernetes Storage & Stateful Applications"
sidebar_position: 53
---

So far, we’ve treated ProjectHub Pods as **replaceable**:

```text
Pod A
  ↓
dies
  ↓
Pod D replaces it
```

That’s perfect for our Spring Boot application.

But now consider PostgreSQL.

If PostgreSQL writes:

```text
users
projects
posts
```

to disk, we absolutely cannot say:

“It’s okay if the Pod disappears; we’ll just create another one.”

We need to understand the boundary between **stateless** and **stateful** workloads.

Kubernetes explicitly distinguishes `Deployment` as a good fit for stateless workloads and `StatefulSet` for workloads that need persistent state, stable identity, or related guarantees.  

---

# **1. Stateless vs Stateful**

### **Stateless application**

Our Spring Boot API:

```text
Request
   ↓
Pod
   ↓
Response
```

The Pod itself doesn’t need to permanently remember anything.

If:

```text
Pod A
```

dies, we can create:

```text
Pod B
```

and continue.

That’s **stateless**.

---

### **Stateful application**

PostgreSQL:

```text
PostgreSQL
    |
    v
users
projects
posts
```

The data must survive:

```text
Pod restart
Pod replacement
Node failure
application upgrade
```

That’s **stateful**.

---

# **2. Why container storage isn’t enough**

A container has a writable filesystem.

But that filesystem is not the right place to keep important application data.

Kubernetes documents that container-local filesystem state is ephemeral; persistent volumes exist beyond an individual Pod’s lifetime.  

Imagine:

```text
PostgreSQL Pod
     |
     v
container filesystem
     |
     v
projecthub database
```

Pod dies:

```text
PostgreSQL Pod ❌
```

If the database was only using ephemeral container storage:

```text
DATABASE ❌
```

That’s unacceptable.

---

# **3. Kubernetes Volumes**

Kubernetes provides **Volumes**.

Conceptually:

```text
Pod
 |
 +-- Container
 |
 +-- Volume
```

The container mounts the volume:

```text
/var/lib/postgresql/data
```

The important distinction is:

```text
Container filesystem
       ≠
Persistent storage
```

Persistent volumes can outlive the Pod that uses them.  

---

# **4. PersistentVolume**

A **PersistentVolume**, or PV, represents storage available to the Kubernetes cluster.

Think:

```text
PersistentVolume
        |
        v
Actual storage
```

It might ultimately be backed by:

```text
cloud disk
network storage
SAN
NFS
CSI storage system
```

The exact implementation depends on the cluster.

Kubernetes describes a PV as storage with a lifecycle independent of an individual Pod.  

---

# **5. PersistentVolumeClaim**

Applications usually don’t say:

“Give me this exact disk.”

Instead they request storage.

That’s a **PersistentVolumeClaim**, or PVC.

Think:

```text
Application
    |
    v
PVC
    |
    v
PV
    |
    v
Actual storage
```

The application says something like:

“I need 100 GiB of persistent storage.”

---

# **6. PVC example**

```yaml
apiVersion: v1
kind: PersistentVolumeClaim

metadata:
  name: postgres-data

spec:
  accessModes:
    - ReadWriteOnce

  resources:
    requests:
      storage: 100Gi
```

This is a **request** for storage.

Kubernetes can then bind the claim to an appropriate PersistentVolume.

---

# **7. StorageClass**

But who creates the actual storage?

This is where **StorageClass** comes in.

A StorageClass describes a class/type of storage and can be used for dynamic provisioning.  

Conceptually:

```text
PVC
 |
 | "I need 100 GiB"
 v
StorageClass
 |
 | dynamically provision
 v
PersistentVolume
 |
 v
Actual disk
```

This means you don’t necessarily manually create every PV.

---

# **8. Think of StorageClass like a menu**

Imagine your infrastructure offers:

```text
fast-ssd
standard
archive
```

A PVC can request:

```yaml
storageClassName: fast-ssd
```

The cluster’s storage system knows how to provision that class.

The exact StorageClass names and behavior depend on the Kubernetes environment. Kubernetes itself doesn’t prescribe what a storage class must represent.  

---

# **9. The complete storage relationship**

Memorize this picture:

```text
                  Application Pod
                       |
                       v
                     PVC
                       |
                       v
                      PV
                       |
                       v
                 StorageClass/
                 storage backend
                       |
                       v
                 Actual storage
```

More precisely, a StorageClass is commonly involved in **dynamically provisioning** the PV; an existing PV can also be statically provisioned.  

---

# **10. Why StatefulSet exists**

Now we arrive at the big concept.

A Deployment assumes its Pods are basically interchangeable:

```text
projecthub-abc
projecthub-def
projecthub-ghi
```

We don’t care which one handles the request.

A StatefulSet is different.

It gives Pods stable identities.

For example:

```text
postgres-0
postgres-1
postgres-2
```

Those identities remain associated with their storage/network identities. Kubernetes documents StatefulSet as providing stable network identity and storage identity for its Pods.  

---

# **11. Deployment vs StatefulSet**

This is worth memorizing.

|**Deployment**|**StatefulSet**|
|---|---|
|Stateless workloads|Stateful workloads|
|Pods interchangeable|Pods have stable identities|
|`projecthub-abc`|`postgres-0`|
|Usually ephemeral local state|Persistent storage commonly required|
|Scaling is generally interchangeable|Scaling/order can matter|
|API servers|Databases, brokers, clustered systems|

But there’s an important warning:

**StatefulSet does not magically make an application stateful or highly available.**

It gives Kubernetes mechanisms useful for stateful workloads.

The database itself still needs correct replication, failover, backup, consistency, etc.

---

# **12. Example StatefulSet**

A simplified example:

```yaml
apiVersion: apps/v1
kind: StatefulSet

metadata:
  name: postgres

spec:
  serviceName: postgres
  replicas: 1

  selector:
    matchLabels:
      app: postgres

  template:
    metadata:
      labels:
        app: postgres

    spec:
      containers:
        - name: postgres
          image: postgres:18

          volumeMounts:
            - name: postgres-data
              mountPath: /var/lib/postgresql/data

  volumeClaimTemplates:
    - metadata:
        name: postgres-data

      spec:
        accessModes:
          - ReadWriteOnce

        resources:
          requests:
            storage: 100Gi
```

Don’t deploy this yet.

We’re using it to understand the architecture.

---

# 

# **13.**

**`volumeClaimTemplates`**

This is particularly interesting:

```yaml
volumeClaimTemplates:
  - metadata:
      name: postgres-data
```

The StatefulSet can create a PVC associated with each Pod.

For example:

```text
postgres-0
    |
    +-- postgres-data-postgres-0

postgres-1
    |
    +-- postgres-data-postgres-1
```

Each StatefulSet Pod gets its own persistent storage identity.

Kubernetes documents that `volumeClaimTemplates` provide stable storage for StatefulSet Pods when dynamically provisioned storage is available.  

---

# **14. Why this matters**

Suppose:

```text
postgres-0
```

dies.

Kubernetes may recreate:

```text
postgres-0
```

The important thing is that its identity and associated storage relationship can be preserved.

Conceptually:

```text
postgres-0
     |
     v
PVC A
     |
     v
Database data
```

Pod dies:

```text
postgres-0 ❌
```

New Pod:

```text
postgres-0
     |
     v
PVC A
     |
     v
same persistent data
```

That’s fundamentally different from a disposable Spring Boot Pod.

---

# **15. Stable network identity**

StatefulSet Pods can have predictable names:

```text
postgres-0
postgres-1
postgres-2
```

They can also have stable DNS identities when used with the appropriate Service configuration. Kubernetes documents that StatefulSets use a governing Service for Pod network identity.  

This matters for distributed systems where nodes need to know who they are.

---

# **16. Why databases care about identity**

Imagine a distributed database cluster:

```text
postgres-0
postgres-1
postgres-2
```

They may have roles such as:

```text
postgres-0 → primary
postgres-1 → replica
postgres-2 → replica
```

The database software itself manages replication and failover.

Kubernetes provides stable infrastructure identity.

But Kubernetes doesn’t automatically understand:

“postgres-0 is the database primary.”

That’s database-level logic.

This distinction is extremely important.

---

# **17. StatefulSet ≠ database HA**

A common beginner misconception:

“If I put PostgreSQL in a StatefulSet with 3 replicas, I have highly available PostgreSQL.”

No.

You could accidentally create:

```text
Postgres Pod A
Postgres Pod B
Postgres Pod C
```

with three independent databases.

That’s not automatically replication.

You need PostgreSQL replication/configuration or an operator/managed database solution.

Kubernetes provides workload primitives; the database needs its own distributed-system semantics.

---

# **18. This is why managed databases are common**

In production, many teams choose:

```text
Kubernetes
   |
   v
Spring Boot Pods
```

but:

```text
PostgreSQL
```

is provided by a managed database service.

Then the architecture becomes:

```text
Kubernetes
   |
   +---- ProjectHub Pods
   |
   +---- Redis
   |
   +---- Workers
   |
   v
Managed PostgreSQL
```

The managed database provider handles much of:

```text
backups
replication
storage
failover
patching
```

The exact responsibilities depend on the service.

---

# **19. Backups are different from persistence**

This is **very important**.

Suppose:

```text
PostgreSQL
   |
   v
Persistent Volume
```

Your Pod dies.

The data survives.

Great.

But what if:

```text
DELETE FROM posts;
```

runs accidentally?

The persistent disk faithfully preserves:

```text
the deleted state
```

Persistence doesn’t protect you from logical mistakes.

That’s why you need backups.

---

# **20. Persistence vs backup**

### **Persistence**

Protects against things like:

```text
Pod replacement
container restart
rescheduling
```

### **Backup**

Protects against things like:

```text
accidental deletion
corruption
bad migration
application bug
disaster
```

These are different problems.

---

# **21. Volume snapshots**

Kubernetes has a standardized VolumeSnapshot API for creating point-in-time snapshots of supported persistent volumes through CSI drivers.  

Conceptually:

```text
Persistent Volume
       |
       v
   Snapshot
       |
       v
point-in-time copy
```

For example:

```text
PostgreSQL data
     10:00
       |
       v
Snapshot
```

Then later:

```text
Restore
  ↓
new volume
```

But again:

A volume snapshot is not automatically a complete database backup strategy.

Database consistency, transaction state, retention, off-cluster storage and restore testing still matter.

Kubernetes itself notes that snapshot support depends on CSI drivers and the cluster’s snapshot components.  

---

# **22. The backup mindset**

A serious production backup strategy asks:

```text
Where is the backup?
How often?
How long retained?
Encrypted?
Off-site?
Can we restore it?
How long does restore take?
```

The most important question is often:

**Have we successfully restored from backup?**

A backup that has never been tested is not something you should blindly trust.

---

# **23. Stateful applications beyond PostgreSQL**

The same concepts apply to:

### **Redis**

Depending on configuration and architecture:

```text
persistent data
replication
failover
```

### **RabbitMQ**

```text
queues
messages
durability
cluster identity
```

### **Kafka**

```text
brokers
partitions
logs
replication
```

These systems have their own distributed-system requirements.

StatefulSet can provide useful Kubernetes primitives, but the application/system itself remains responsible for its semantics.

---

# **24. Why Spring Boot should remain a Deployment**

Our ProjectHub API is still:

```text
Deployment
    |
    +-- Pod
    +-- Pod
    +-- Pod
```

not:

```text
StatefulSet
    |
    +-- projecthub-0
    +-- projecthub-1
    +-- projecthub-2
```

Why?

Because we don’t need:

```text
stable identity
```

for our HTTP API.

Any healthy Pod can handle:

```text
GET /posts
```

or:

```text
POST /projects
```

The actual state lives in:

```text
PostgreSQL
Redis
RabbitMQ
```

not inside the individual API Pod.

---

# **25. This is the stateless architecture we want**

```text
                 ProjectHub
                     |
              Kubernetes Service
                     |
        +------------+------------+
        |            |            |
       Pod          Pod          Pod
        |            |            |
        +------------+------------+
                     |
          +----------+----------+
          |          |          |
          v          v          v
       Postgres    Redis     RabbitMQ
```

The API Pods are disposable.

The data infrastructure is persistent/stateful.

---

# **26. A very important design principle**

Try to keep application Pods as stateless as possible.

For example, don’t store uploaded files inside:

```text
/app/uploads
```

inside a Pod and assume they’ll always be there.

Instead use dedicated persistent/object storage.

Similarly, don’t store:

```text
important user sessions
```

only in one Pod’s memory if another Pod must be able to serve the next request.

Instead use something shared:

```text
Redis
database
external session store
```

depending on the architecture.

---

# **27. The request can now travel across the entire system**

Let’s follow:

```text
POST /projects
```

### **Step 1**

Internet:

```text
api.projecthub.com
```

### **Step 2**

Gateway:

```text
HTTPS termination
routing
```

### **Step 3**

Service:

```text
ProjectHub Service
```

### **Step 4**

Pod:

```text
Spring Boot
```

### **Step 5**

Security:

```text
JWT
 ↓
posts.create
```

### **Step 6**

Business logic:

```text
ProjectService
```

### **Step 7**

Database:

```text
PostgreSQL
```

### **Step 8**

Response:

```text
201 Created
```

And if an asynchronous event is required:

```text
Project created
      ↓
RabbitMQ
      ↓
Notification worker
```

That’s our complete backend system.

---

# **28. Stateful vs stateless: memorize this**

When deciding how to deploy something, ask:

**Can I destroy this instance and create a completely equivalent replacement without losing important state?**

If yes:

```text
Likely stateless
→ Deployment
```

If no:

```text
Potentially stateful
→ persistent storage
→ StatefulSet or another appropriate stateful architecture
```

But don’t automatically conclude:

“StatefulSet.”

Sometimes the better answer is:

```text
Use a managed database.
```

That’s a very important production engineering judgment.

---

# **Lesson 53 Summary**

You’ve learned:

- Stateless vs stateful workloads
- Kubernetes Volumes
- PersistentVolume (PV)
- PersistentVolumeClaim (PVC)
- StorageClass
- StatefulSet
- Stable Pod identity
- `volumeClaimTemplates`
- Persistent storage vs ephemeral storage
- Persistence vs backup
- Volume snapshots
- Why StatefulSet doesn’t automatically provide database replication
- Why managed databases are often preferable
- Why ProjectHub’s API should remain stateless
- How PostgreSQL/Redis/RabbitMQ fit into the architecture

The key picture:

```text
             Stateless
          Spring Boot API
                 |
          Kubernetes Deployment
                 |
        +--------+--------+
        |        |        |
       Pod      Pod      Pod
        |        |        |
        +--------+--------+
                 |
          Stateful systems
                 |
       +---------+---------+
       |         |         |
       v         v         v
   PostgreSQL  Redis   RabbitMQ
       |
   Persistent
    Storage
       |
      PVC
       |
      PV
       |
 Storage backend
```

Kubernetes’ official documentation describes PVs as having a lifecycle independent of individual Pods, PVCs as requests for storage, and StatefulSets as maintaining stable Pod identities and storage relationships.  

---

# **Exercise 53**

### **1.**

What’s the fundamental difference between:

```text
Deployment
```

and:

```text
StatefulSet
```

?

---

### **2.**

Explain this chain:

```text
Pod
 ↓
PVC
 ↓
PV
 ↓
StorageClass
 ↓
actual storage
```

Be precise about which relationship is a **request** and which represents the actual provisioned storage.

---

### **3.**

Why is this dangerous?

```text
PostgreSQL
   ↓
container filesystem
```

with no persistent volume?

---

### **4.**

Why doesn’t this automatically create a highly available PostgreSQL cluster?

```yaml
kind: StatefulSet

spec:
  replicas: 3
```

---

### **5.**

What’s the difference between:

```text
persistent storage
```

and:

```text
backup
```

Give an example of a failure that each protects against.

---

### **6. Architecture challenge**

Suppose ProjectHub has:

```text
Spring Boot
PostgreSQL
Redis
RabbitMQ
```

Decide which should conceptually be:

```text
Deployment
StatefulSet
Managed external service
```

You can choose more than one reasonable architecture, but **explain your reasoning**.

**Next: Lesson 54 — Kubernetes Security: ServiceAccounts, RBAC, Secrets, NetworkPolicies, Pod Security, and how to stop one compromised Pod from accessing everything in the cluster.**