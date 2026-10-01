---
title: Lesson 54: Kubernetes Security
sidebar_position: 54
---

We’ve now built a fairly complete deployment:

```text
Internet
   ↓
Gateway
   ↓
Service
   ↓
ProjectHub Pods
   ↓
PostgreSQL / Redis / RabbitMQ
```

But there’s a dangerous assumption hiding underneath:

**What stops one compromised Pod from accessing everything else?**

That’s what this lesson is about.

Kubernetes security is layered. Its official security guidance covers RBAC, ServiceAccounts, Secrets, NetworkPolicies, Pod Security Standards, admission controls, and workload isolation.  

---

# **1. Think in security layers**

A production Kubernetes environment should look conceptually like:

```text
                    Kubernetes Security
                           |
       +-------------------+-------------------+
       |                   |                   |
       v                   v                   v
     RBAC              NetworkPolicy      Pod Security
       |                   |                   |
       v                   v                   v
 "Who can use       "Who can talk       "What can a
 Kubernetes API?"    to whom?"           Pod do?"
```

And separately:

```text
Secrets
 ↓
"What sensitive values can be accessed?"
```

These solve different problems.

---

# **2. Kubernetes has identities**

Earlier we discussed users and JWTs inside ProjectHub.

Kubernetes has its **own** identity system.

For workloads, the primary identity is a:

```text
ServiceAccount
```

A Pod can run as a particular ServiceAccount, and RBAC permissions can be granted to that ServiceAccount.  

So we now have two different security worlds:

```text
ProjectHub
   |
   +-- Users
   +-- Roles
   +-- Permissions
   +-- JWT
```

and:

```text
Kubernetes
   |
   +-- ServiceAccounts
   +-- Roles
   +-- RoleBindings
```

Don’t confuse them.

---

# **3. ProjectHub authorization vs Kubernetes RBAC**

Suppose Alice calls:

```http
DELETE /posts/42
```

ProjectHub asks:

```text
Does Alice have posts.delete?
```

That’s **Spring Security authorization**.

Kubernetes RBAC asks a completely different question:

```text
Can this ServiceAccount read Kubernetes Secrets?
Can it list Pods?
Can it modify Deployments?
```

That’s **Kubernetes authorization**.

So:

```text
Spring Security
     ↓
Application permissions

Kubernetes RBAC
     ↓
Cluster/API permissions
```

---

# **4. ServiceAccount**

We can create:

```yaml
apiVersion: v1
kind: ServiceAccount

metadata:
  name: projecthub
```

Then assign it to our Deployment:

```yaml
spec:
  template:
    spec:
      serviceAccountName: projecthub
```

Now our ProjectHub Pods run using:

```text
ServiceAccount/projecthub
```

Kubernetes supports assigning a ServiceAccount through `spec.serviceAccountName`; by default, credentials for the assigned ServiceAccount may be made available to the Pod. You can disable automatic token mounting when the workload doesn’t need Kubernetes API access.  

---

# **5. Does ProjectHub need Kubernetes API access?**

Probably not.

Our Spring Boot application needs to do:

```text
PostgreSQL
Redis
RabbitMQ
```

It probably does **not** need:

```text
list Pods
create Deployments
read Secrets
delete Services
```

So we should ask:

Why give it Kubernetes API credentials at all?

We don’t.

We can explicitly disable automatic ServiceAccount token mounting:

```yaml
spec:
  automountServiceAccountToken: false
```

This follows the Kubernetes least-privilege guidance for workloads that don’t need API access.  

---

# **6. Least privilege**

This is the security principle you’ll see everywhere:

**Give an identity only the permissions it actually needs.**

Bad:

```text
ProjectHub
   ↓
cluster-admin
```

Good:

```text
ProjectHub
   ↓
minimal permissions
```

Or, even better:

```text
ProjectHub
   ↓
no Kubernetes API permissions
```

if it doesn’t need them.

Kubernetes specifically recommends minimal RBAC rights, avoiding unnecessary wildcards, and preferring namespace-scoped permissions where possible.  

---

# **7. Role**

Suppose a worker really does need to read certain Kubernetes resources.

We could define:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role

metadata:
  name: projecthub-reader

rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get"]
```

This means roughly:

Within this namespace, this role can `get` ConfigMaps.

Notice what it **doesn’t** say:

```text
delete everything
list everything
modify everything
```

---

# **8. RoleBinding**

A Role doesn’t automatically give anyone permissions.

We bind it to the ServiceAccount:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding

metadata:
  name: projecthub-reader-binding

subjects:
  - kind: ServiceAccount
    name: projecthub

roleRef:
  kind: Role
  name: projecthub-reader
  apiGroup: rbac.authorization.k8s.io
```

Now:

```text
ServiceAccount
      |
      v
RoleBinding
      |
      v
Role
      |
      v
permissions
```

That’s the core Kubernetes RBAC model.

---

# **9. Role vs ClusterRole**

There are two concepts you’ll encounter:

```text
Role
```

and:

```text
ClusterRole
```

A `Role` is namespace-scoped.

A `ClusterRole` can define permissions usable for cluster-scoped resources or through bindings that grant access across namespaces.

For normal application workloads, prefer namespace-scoped permissions when possible. Kubernetes’ RBAC guidance explicitly recommends `RoleBinding` rather than `ClusterRoleBinding` where namespace-level access is sufficient.  

---

# 

# **10. Be extremely careful with**

**`*`**

This is dangerous:

```yaml
verbs: ["*"]
resources: ["*"]
```

You’re essentially saying:

```text
"Almost anything."
```

And Kubernetes warns against wildcard permissions because they can automatically include resources introduced in the future.  

Prefer:

```yaml
resources:
  - configmaps

verbs:
  - get
```

when that’s all the application needs.

---

# **11. Secrets**

We’ve already used:

```text
Secret
```

for:

```text
DB_PASSWORD
JWT_PRIVATE_KEY
```

But there’s an important correction to our earlier simplified mental model.

A Kubernetes Secret is **not automatically equivalent to a secure external secret manager**.

Kubernetes documentation notes that Secret objects are stored unencrypted in etcd by default unless encryption at rest is configured.  

So:

```text
Secret
≠
automatically encrypted database
```

---

# **12. Secret security**

A production cluster should consider:

```text
Encryption at rest
        +
RBAC
        +
limited access
        +
external secret management where appropriate
```

Kubernetes’ own guidance recommends encryption at rest, least-privilege RBAC, restricting Secret access to specific workloads, and considering external Secret stores.  

---

# 

# 

# **13. The**

**`base64`**

**misconception**

You may see:

```yaml
data:
  password: c29tZS1wYXNzd29yZA==
```

and think:

“It’s encrypted!”

No.

Kubernetes Secret `data` values are base64-encoded.

Base64 is encoding, not encryption.

The actual security of Secrets depends on access control and storage protection, including encryption at rest.

---

# **14. NetworkPolicy**

Now imagine this nightmare:

```text
Compromised ProjectHub Pod
          |
          +---- PostgreSQL
          |
          +---- Redis
          |
          +---- RabbitMQ
          |
          +---- Other services
          |
          +---- Internet
```

Even if the attacker compromises one Pod, we’d like to limit what it can communicate with.

That’s where:

```text
NetworkPolicy
```

comes in.

Kubernetes describes NetworkPolicies as controls for traffic between Pods and between Pods and external networks.  

---

# **15. NetworkPolicy mental model**

Think:

```text
RBAC
 ↓
Who can use Kubernetes API?

NetworkPolicy
 ↓
Who can communicate over the network?
```

They’re complementary.

---

# **16. Example policy**

Suppose only ProjectHub Pods should talk to PostgreSQL.

Conceptually:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy

metadata:
  name: postgres-ingress

spec:
  podSelector:
    matchLabels:
      app: postgres

  policyTypes:
    - Ingress

  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: projecthub

      ports:
        - protocol: TCP
          port: 5432
```

Read it as:

For PostgreSQL Pods, allow incoming TCP/5432 traffic from Pods labeled `app: projecthub`.

---

# **17. Before NetworkPolicy**

Conceptually:

```text
ProjectHub ──────→ PostgreSQL
Other Pod ────────→ PostgreSQL
Random Pod ───────→ PostgreSQL
```

After the policy:

```text
ProjectHub ──────→ PostgreSQL ✅

Other Pod ────────→ PostgreSQL ❌
Random Pod ───────→ PostgreSQL ❌
```

Assuming your cluster’s networking implementation enforces NetworkPolicy.

Kubernetes itself provides the NetworkPolicy API; enforcement is performed by the cluster’s network implementation. The Kubernetes security guidance explicitly says to make sure your cluster provides and enforces NetworkPolicy.  

---

# **18. NetworkPolicy is not a firewall for everything**

NetworkPolicy primarily controls Pod networking.

It doesn’t replace:

```text
TLS
application authentication
JWT
RBAC
firewalls
cloud security groups
API authorization
```

Again:

```text
Layered security.
```

---

# **19. Pod Security**

Now consider what a Pod itself is allowed to do.

A badly configured container might have dangerous privileges.

For example:

```text
run as root
privileged mode
host filesystem access
host networking
extra Linux capabilities
```

We want to restrict these.

Kubernetes provides **Pod Security Standards** with three profiles:

```text
Privileged
Baseline
Restricted
```

`Baseline` prevents known privilege-escalation patterns while `Restricted` is significantly more restrictive and follows current Pod-hardening practices.  

---

# **20. Pod Security Admission**

Kubernetes provides a built-in **Pod Security Admission** mechanism for enforcing these standards; it has been stable since Kubernetes 1.25.  

You can apply policies at the namespace level.

Conceptually:

```text
Namespace: projecthub
        |
        v
Restricted policy
        |
        v
Pod creation
        |
   +----+----+
   |         |
 valid     invalid
   |         |
 allow      reject
```

---

# **21. Why this matters**

Suppose someone tries to deploy:

```yaml
securityContext:
  privileged: true
```

into a namespace enforcing a sufficiently restrictive Pod Security policy.

The admission layer can reject the Pod.

So instead of discovering the problem after deployment:

```text
deploy
 ↓
security incident
```

we get:

```text
deploy
 ↓
admission policy
 ↓
❌ rejected
```

That’s a much better security model.

---

# **22. Don’t run your app as root**

Another useful hardening measure:

```yaml
securityContext:
  runAsNonRoot: true
```

And potentially:

```yaml
securityContext:
  allowPrivilegeEscalation: false
```

along with an appropriate seccomp profile and other restrictions.

Kubernetes’ application security checklist specifically recommends container security contexts, seccomp, and related hardening mechanisms.  

---

# **23. ProjectHub security layers**

Let’s combine everything.

```text
                    Internet
                       |
                       v
                    Gateway
                       |
                 TLS / routing
                       |
                       v
                ProjectHub Service
                       |
              +--------+--------+
              |        |        |
             Pod      Pod      Pod
              |        |        |
         +----+--------+--------+----+
         |         Security           |
         |                            |
         |  ServiceAccount            |
         |  Pod Security              |
         |  NetworkPolicy             |
         |  Secrets                   |
         +----------------------------+
                       |
            +----------+----------+
            |          |          |
            v          v          v
        PostgreSQL   Redis     RabbitMQ
```

And inside each Spring Boot Pod:

```text
JWT
 ↓
Authentication
 ↓
Authority
 ↓
@PreAuthorize
 ↓
Resource policy
```

---

# **24. Two authorization systems**

This is probably the most important concept of this lesson.

### **Kubernetes authorization**

```text
Can this workload:

read Secret X?
list Pods?
create Jobs?
modify ConfigMaps?
```

Handled by:

```text
ServiceAccount
+
RBAC
```

### **ProjectHub authorization**

```text
Can Alice:

create posts?
delete post 42?
manage project 7?
```

Handled by:

```text
Spring Security
+
permissions
+
resource policies
```

So:

```text
Kubernetes RBAC
       ≠
Spring Security RBAC
```

They solve different problems.

---

# **25. What happens if ProjectHub is compromised?**

Imagine an attacker gets remote code execution in a ProjectHub Pod.

Without good isolation, they might try:

```text
read ServiceAccount token
        ↓
call Kubernetes API
        ↓
read Secrets
        ↓
access other resources
```

We want:

```text
Compromised Pod
     |
     +-- Kubernetes API access? ❌
     |
     +-- read arbitrary Secrets? ❌
     |
     +-- access other Pods? restricted
     |
     +-- privileged container? ❌
```

That’s **blast-radius reduction**.

You can’t assume every component will remain uncompromised.

You design the system so that compromise doesn’t automatically become total compromise.

---

# **26. Namespaces**

We can separate environments:

```text
projecthub-dev
projecthub-staging
projecthub-prod
```

or applications:

```text
projecthub
monitoring
messaging
```

Namespaces provide an organizational and security boundary for many Kubernetes resources, but they are not by themselves a complete isolation mechanism. Kubernetes’ multi-tenancy guidance explicitly notes that namespace isolation requires additional access-control and networking configuration.  

---

# **27. Don’t think namespace = security wall**

This is a common misconception:

```text
namespace A
   |
   | "completely isolated"
   |
namespace B
```

Not automatically.

You may additionally need:

```text
RBAC
NetworkPolicy
Pod Security
resource quotas
admission policies
```

depending on your requirements.

---

# **28. Image security**

Security starts before the container reaches Kubernetes.

Our CI pipeline should consider:

```text
Source code
   ↓
Build
   ↓
Tests
   ↓
Dependency checks
   ↓
Container image
   ↓
Image scanning
   ↓
Registry
   ↓
Kubernetes
```

Kubernetes’ application security checklist recommends image scanning and, where appropriate, container image signing/verification.  

So Kubernetes security isn’t just:

“Write secure YAML.”

It starts in CI/CD.

---

# **29. Secrets should not be in Git**

Never do:

```yaml
stringData:
  DB_PASSWORD: "real-password"
```

and commit it to Git.

Even if you later delete the file, the secret may remain in Git history.

Instead, production systems commonly integrate with an external secret-management system or inject secrets through controlled deployment mechanisms.

Kubernetes itself recommends considering external Secret stores.  

---

# **30. A practical ProjectHub ServiceAccount**

Since our Spring Boot API doesn’t need Kubernetes API access, a reasonable starting point is:

```yaml
apiVersion: v1
kind: ServiceAccount

metadata:
  name: projecthub

automountServiceAccountToken: false
```

And:

```yaml
spec:
  template:
    spec:
      serviceAccountName: projecthub
```

Now we’ve explicitly stated:

ProjectHub has an identity, but don’t automatically give it Kubernetes API credentials.

That’s a good default when the application doesn’t need them.  

---

# **31. Security isn’t just preventing attacks**

Security also includes limiting accidents.

Imagine a developer has:

```text
delete Pods
```

permissions across the entire production cluster.

One typo:

```bash
kubectl delete pods --all
```

could cause a huge outage.

Least privilege protects against:

```text
malicious actions
+
accidental actions
```

That’s why RBAC is operationally important, not merely a security checkbox.

---

# **32. Our final security model**

ProjectHub now has multiple layers:

```text
                     Internet
                        |
                     HTTPS
                        |
                     Gateway
                        |
                  Network controls
                        |
                  ProjectHub Service
                        |
              +---------+---------+
              |         |         |
             Pod       Pod       Pod
              |         |         |
       +------+---------+---------+------+
       |              Pod Security       |
       |              SecurityContext    |
       |              ServiceAccount     |
       +---------------------------------+
                        |
                  NetworkPolicy
                        |
          +-------------+-------------+
          |             |             |
          v             v             v
      PostgreSQL      Redis        RabbitMQ
```

And inside ProjectHub:

```text
JWT
 ↓
Authentication
 ↓
Authorities
 ↓
@PreAuthorize
 ↓
Resource Policy
```

---

# **33. The security principle to remember**

When you design a production system, don’t ask:

“Is it secure?”

That’s too broad.

Ask specific questions:

```text
Who can access the Kubernetes API?

Who can read this Secret?

Which Pods can talk to PostgreSQL?

Can this container run as root?

Can this Pod access the host filesystem?

Can this ServiceAccount create workloads?

Can one compromised Pod reach another service?

Can a developer modify production?

Can an image with a known vulnerability be deployed?
```

Now security becomes something you can actually reason about.

---

# **Lesson 54 Summary**

You’ve learned:

- Kubernetes ServiceAccounts
- Kubernetes RBAC
- Role vs RoleBinding
- ClusterRole vs Role
- Least privilege
- Secret security
- Encryption at rest
- NetworkPolicy
- Pod Security Standards
- Pod Security Admission
- SecurityContext
- Namespaces
- Image security
- Blast-radius reduction
- Difference between Kubernetes RBAC and Spring Security authorization

The big picture:

```text
                  Kubernetes Security
                          |
        +-----------------+------------------+
        |                 |                  |
        v                 v                  v
       RBAC         NetworkPolicy       Pod Security
        |                 |                  |
   API access        network access      container behavior
        |                 |                  |
        +-----------------+------------------+
                          |
                       Secrets
                          |
                    sensitive data
```

Kubernetes’ current security guidance emphasizes least-privilege RBAC, controlled Secret access, NetworkPolicies, Pod Security Standards, and image security as complementary controls rather than one single security mechanism.  

---

# **Exercise 54**

### **1.**

Explain the difference between:

```text
Spring Security RBAC
```

and:

```text
Kubernetes RBAC
```

using a ProjectHub example.

---

### **2.**

Why might this be unnecessary for ProjectHub?

```yaml
serviceAccountName: projecthub
```

if the Pod doesn’t need to call the Kubernetes API?

What additional setting could reduce unnecessary credential exposure?

---

### **3.**

What’s wrong with:

```yaml
verbs: ["*"]
resources: ["*"]
```

?

---

### **4.**

Suppose a compromised ProjectHub Pod tries to connect directly to Redis.

Which Kubernetes security mechanism could restrict that network communication?

---

### **5.**

What problem does Pod Security solve that NetworkPolicy doesn’t?

---

### **6.**

Why isn’t this enough?

```text
Kubernetes Secret
   ↓
DB_PASSWORD
```

What additional protections should we consider?

---

### **7. Final security challenge**

Imagine an attacker gets remote code execution inside a ProjectHub Pod.

Describe **at least five independent controls** that could limit the damage.

Think about:

```text
ServiceAccount
RBAC
NetworkPolicy
Pod Security
Secrets
container privileges
image security
namespaces
```

Don’t just list them — explain **what each one prevents**.

**Next: Lesson 55 — Production Security Architecture: we’ll connect Kubernetes security, Spring Security/JWT, TLS, secrets, network boundaries, and CI/CD into one end-to-end threat model for ProjectHub.**