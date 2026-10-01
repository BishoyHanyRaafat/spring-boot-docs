---
title: Lesson 55: Production Security Architecture
sidebar_position: 55
---

We’ve now learned the individual security mechanisms:

```text
Spring Security
JWT
RBAC
ServiceAccounts
Secrets
NetworkPolicy
Pod Security
TLS
image security
```

The next step is to stop thinking about them individually.

A production system needs **defense in depth**: if one layer fails, another layer should still limit the damage. Kubernetes’ own application security checklist explicitly treats these controls as complementary rather than as a single security solution.  

---

# **1. The complete ProjectHub security model**

Our production architecture now looks like:

```text
                         Internet
                            |
                            | HTTPS
                            v
                     +-------------+
                     |   Gateway   |
                     +-------------+
                            |
                            v
                     ProjectHub Service
                            |
             +--------------+--------------+
             |              |              |
             v              v              v
          Pod A           Pod B           Pod C
             |              |              |
             +--------------+--------------+
                            |
              +-------------+-------------+
              |             |             |
              v             v             v
          PostgreSQL      Redis       RabbitMQ
```

And there are security controls around every layer.

---

# **2. Layer 1 — TLS**

The first question is:

Can someone intercept network traffic?

We want:

```text
Client
  |
  | HTTPS / TLS
  v
Gateway
```

instead of:

```text
Client
  |
  | HTTP
  v
Gateway
```

TLS protects data **in transit**.

For example, without TLS, an attacker positioned on the network could potentially observe sensitive traffic.

With TLS:

```text
Authorization: Bearer eyJ...
```

is protected while traveling across the network.

But TLS does **not** decide whether the token is valid.

That’s Spring Security’s job.

---

# **3. TLS doesn’t replace authentication**

Think of the layers:

```text
TLS
 ↓
"Can someone read/modify this network traffic?"

JWT
 ↓
"Who is making this request?"

Spring Security
 ↓
"What is this user allowed to do?"
```

These are different questions.

---

# **4. Gateway vs Spring Security**

Our Gateway might terminate TLS:

```text
HTTPS
  ↓
Gateway
  ↓
HTTP/internal TLS
  ↓
Spring Boot
```

The Gateway can handle things such as:

```text
TLS termination
routing
host/path matching
rate limiting
```

depending on the infrastructure.

But the application still needs:

```text
authentication
authorization
resource ownership
business rules
```

So:

```text
Gateway
   ≠
Spring Security
```

---

# **5. Layer 2 — Authentication**

A request reaches ProjectHub:

```http
GET /posts/42
Authorization: Bearer <JWT>
```

Spring Security’s Resource Server support validates the JWT, including its signature and standard claims such as `exp`, `nbf`, and `iss`; it then converts the JWT into an authenticated security context.  

Conceptually:

```text
HTTP request
    |
    v
Bearer token
    |
    v
JwtDecoder
    |
    v
signature + claims validation
    |
    v
Authentication
```

---

# **6. Layer 3 — Authorization**

Authentication answers:

Who are you?

Authorization answers:

What can you do?

For ProjectHub:

```text
Authentication
      ↓
alice
      ↓
authorities
      ↓
posts.read
posts.create
posts.delete
```

Then:

```java
@PreAuthorize("hasAuthority('posts.delete')")
```

checks the general permission.

But we’ve already learned that this isn’t sufficient for resource-level authorization.

---

# **7. Layer 4 — Resource authorization**

Suppose Alice has:

```text
posts.delete
```

She sends:

```http
DELETE /posts/42
```

We still need:

```text
Does Alice own post 42?
        OR
Is Alice the OWNER of its project?
```

So our policy becomes:

```text
posts.delete
AND
(
    owns post
    OR
    project OWNER
)
```

This is why our `PostDeletionPolicy` exists.

JWT:

```text
identity + general permissions
```

Database:

```text
ownership + project membership + current state
```

That’s an important separation.

---

# **8. Why not put everything in the JWT?**

Imagine Alice belongs to 5,000 projects.

We could theoretically create:

```json
{
  "sub": "alice",
  "projects": {
    "1": "OWNER",
    "2": "MEMBER",
    "3": "MEMBER",
    "...": "..."
  }
}
```

But now the JWT becomes:

```text
huge
+
stale
+
hard to revoke/update
```

And every permission change would have to be reflected in tokens.

Instead:

```text
JWT
 |
 +-- user identity
 +-- general permissions
 |
 v
Database
 |
 +-- project membership
 +-- ownership
 +-- resource state
```

This is the architecture we’ve been building toward.

---

# **9. Layer 5 — Kubernetes identity**

Now step outside ProjectHub.

The **Pod itself** has an identity:

```text
ProjectHub Pod
      |
      v
ServiceAccount
```

The Kubernetes API asks:

What is this workload allowed to do?

That’s Kubernetes RBAC.

So we have:

```text
Alice
 ↓
Spring Security
 ↓
ProjectHub permissions


ProjectHub Pod
 ↓
Kubernetes ServiceAccount
 ↓
Kubernetes RBAC
```

Two identities.

Two authorization systems.

---

# **10. Least privilege**

Our ProjectHub API probably doesn’t need:

```text
create Pods
delete Pods
read every Secret
modify Deployments
```

Therefore:

```yaml
automountServiceAccountToken: false
```

is a reasonable default when the application doesn’t need Kubernetes API access. Kubernetes’ application security checklist recommends disabling automatic ServiceAccount token mounting unless the workload specifically requires Kubernetes API access.  

This means:

```text
ProjectHub compromised
        |
        X
Kubernetes API credentials
```

We’ve reduced the blast radius.

---

# **11. Layer 6 — NetworkPolicy**

Now suppose an attacker compromises ProjectHub.

We don’t want:

```text
Compromised ProjectHub
       |
       +----> PostgreSQL
       +----> Redis
       +----> RabbitMQ
       +----> monitoring
       +----> random services
```

Instead:

```text
ProjectHub
    |
    +----> PostgreSQL     ✅
    +----> Redis          ✅
    +----> RabbitMQ       ✅
    +----> unrelated DB   ❌
    +----> random service ❌
```

NetworkPolicy can restrict expected ingress and egress traffic, provided the cluster’s networking implementation actually enforces NetworkPolicy.  

---

# **12. Egress matters too**

People often think only about:

```text
Who can connect TO my Pod?
```

But also ask:

Where can my Pod connect?

For example:

```text
ProjectHub
   |
   +----> PostgreSQL
   +----> Redis
   +----> RabbitMQ
```

Maybe that’s all it needs.

Why should it freely connect to:

```text
random-internet-site.example
```

?

Restricting egress can reduce the damage from:

```text
stolen credentials
remote code execution
malicious dependencies
compromised application
```

---

# **13. Layer 7 — Container hardening**

Suppose an attacker gets code execution inside the container.

We still want the container itself to be heavily restricted.

A hardened workload can use settings such as:

```yaml
securityContext:
  runAsNonRoot: true
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
```

and avoid privileged containers while dropping unnecessary Linux capabilities. Kubernetes’ application security checklist recommends these kinds of container-level restrictions.  

The idea is:

```text
RCE inside application
        ↓
attacker gets application process
        ↓
NOT automatically
        ↓
root + host access + cluster control
```

---

# **14. Read-only filesystem**

Consider:

```yaml
readOnlyRootFilesystem: true
```

Now the container’s root filesystem isn’t normally writable.

That’s useful because an attacker can’t simply assume they can modify arbitrary application files.

If the application genuinely needs temporary writable storage, we can explicitly provide an appropriate volume.

Security becomes:

```text
Writable
   ↓
only where necessary
```

rather than:

```text
Writable
   ↓
everywhere
```

---

# **15. Layer 8 — Image security**

Security starts before Kubernetes.

Our CI pipeline becomes:

```text
Git push
   |
   v
Compile
   |
   v
Unit tests
   |
   v
Integration tests
   |
   v
Dependency/security checks
   |
   v
Build container
   |
   v
Scan image
   |
   v
Registry
   |
   v
Kubernetes
```

Kubernetes’ current application-security guidance recommends image scanning and discusses image signing/verification as additional controls.  

---

# 

# 

# **16. Don’t use**

**`latest`**

**as your deployment identity**

Imagine:

```text
projecthub:latest
```

changes three times.

Which exact code is running?

That’s difficult to reason about.

Prefer immutable identifiers:

```text
projecthub:1.4.2
```

or:

```text
projecthub:<git-sha>
```

Then:

```text
Deployment
    |
    v
projecthub:8f31c2a
```

You know exactly which artifact you’re deploying.

---

# **17. Layer 9 — Secrets**

Our application needs:

```text
DB_PASSWORD
JWT signing keys
refresh-token configuration
external API credentials
```

These should not be:

```text
hardcoded
committed to Git
baked into Docker images
printed in logs
```

Kubernetes Secrets can provide controlled secret delivery, but Kubernetes documents that Secret objects are stored unencrypted in etcd by default unless encryption at rest is configured.  

So production security might look like:

```text
External Secret Manager
        |
        v
Kubernetes Secret
        |
        v
ProjectHub Pod
```

or another controlled secret-injection architecture.

---

# **18. Secret access should be narrow**

Suppose:

```text
ProjectHub
```

needs:

```text
DB_PASSWORD
```

That doesn’t mean:

```text
ProjectHub
```

should have access to:

```text
every Secret
```

Kubernetes specifically recommends restricting Secret access and avoiding broad `list`/`watch` permissions.  

Least privilege applies to secrets too.

---

# **19. Never log secrets**

This is one of the easiest mistakes to make.

Never:

```java
log.info("Login request: {}", request);
```

if `request` contains:

```text
password
refreshToken
```

Never log:

```text
Authorization: Bearer eyJ...
```

Never log:

```text
JWT private key
DB password
```

A secure secret that ends up in centralized logs has effectively become a leaked secret.

---

# **20. Layer 10 — CORS**

Now let’s bring the browser into the picture.

Suppose:

```text
Frontend:
https://app.projecthub.com

Backend:
https://api.projecthub.com
```

They’re different origins.

The browser enforces CORS rules.

Spring Security’s current documentation notes that CORS must be handled before Spring Security because browser preflight requests can otherwise be rejected as unauthenticated.  

Conceptually:

```text
Browser
   |
   | OPTIONS
   v
CORS configuration
   |
   v
Spring Security
```

---

# **21. CORS is not authentication**

Another very common misconception:

“CORS protects my API.”

Not exactly.

CORS is primarily a **browser cross-origin policy**.

It does not replace:

```text
JWT
authentication
authorization
NetworkPolicy
TLS
```

For example, a non-browser attacker can send HTTP requests without caring about your browser’s CORS restrictions.

So:

```text
CORS
 ≠
API authentication
```

---

# **22. CSRF**

Now another important distinction.

If your authentication mechanism uses cookies, CSRF becomes an important concern.

If your API uses:

```text
Authorization: Bearer <JWT>
```

and doesn’t authenticate requests through browser cookies, the CSRF threat model is different.

You shouldn’t blindly copy:

```java
csrf(csrf -> csrf.disable())
```

into every application.

Instead ask:

**How is the browser authenticated, and where is the credential stored?**

That determines the appropriate CSRF strategy.

---

# **23. JWT storage matters**

Suppose a browser application stores an access token somewhere accessible to JavaScript.

Then an XSS vulnerability can potentially expose that token.

That’s why authentication architecture isn’t just:

```text
"Use JWT."
```

You must also reason about:

```text
Where is the token stored?
Who can read it?
How long does it live?
Can it be revoked?
How are refresh tokens protected?
```

This is one reason browser authentication deserves its own security design rather than blindly following a JWT tutorial.

---

# **24. Access token vs refresh token**

Our ProjectHub model:

```text
Access token
   ↓
short-lived JWT
```

and:

```text
Refresh token
   ↓
longer-lived opaque credential
   ↓
stored server-side as hash
```

If an access token leaks:

```text
attacker
   ↓
access until expiration
```

If a refresh token leaks:

```text
attacker
   ↓
potentially obtain new access tokens
```

Therefore refresh-token protection is particularly important.

Our rotation model helps:

```text
Refresh A
   ↓
Refresh B
   ↓
Refresh C
```

and old tokens are revoked.

---

# **25. Key management**

Remember our JWT signing architecture:

```text
Private key
    |
    | signs
    v
JWT
```

Then:

```text
Public key
    |
    | verifies
    v
JWT signature
```

The private key is extremely sensitive.

Don’t put it in:

```text
Git
Dockerfile
application source
public ConfigMap
```

Use controlled secret management.

Spring Security Resource Server can validate JWTs using issuer/JWK configuration and supports key rotation when keys are exposed through the configured JWK set.  

---

# **26. Key rotation**

Imagine our private signing key is:

```text
K1
```

We eventually introduce:

```text
K2
```

We can have:

```text
K1 → old tokens
K2 → new tokens
```

while the public JWK set exposes the appropriate public keys.

Eventually:

```text
K1
 ↓
retired
```

This is much safer than having:

```text
one permanent private key
```

forever.

---

# **27. Threat modeling**

Now we’re ready for an important engineering skill:

**Threat modeling.**

Instead of saying:

“Make the system secure.”

We identify:

```text
asset
threat
attack path
control
remaining risk
```

---

# **28. Example threat: stolen JWT**

### **Asset**

User account.

### **Threat**

Access token stolen.

### **Attack**

```text
attacker
  ↓
stolen JWT
  ↓
GET /projects
```

### **Controls**

```text
TLS
short JWT lifetime
audience validation
issuer validation
permission checks
resource authorization
```

Spring Security’s JWT resource-server support can validate issuer and audience when configured, in addition to signature and standard time claims.  

---

# **29. Example threat: compromised Pod**

### **Threat**

Remote code execution in ProjectHub.

### **Attack**

```text
attacker
 ↓
ProjectHub process
 ↓
steal credentials
 ↓
access other infrastructure
```

### **Controls**

```text
non-root
read-only filesystem
no privilege escalation
minimal ServiceAccount
RBAC
NetworkPolicy
restricted Secrets
image scanning
```

This is defense in depth.

---

# **30. Example threat: stolen database password**

Suppose:

```text
DB_PASSWORD
```

leaks.

The attacker tries:

```text
attacker
   ↓
PostgreSQL
```

Possible controls:

```text
NetworkPolicy
database firewall
TLS to database
database user permissions
credential rotation
audit logging
```

Notice something important:

Kubernetes security alone isn’t enough.

PostgreSQL needs its own security model too.

---

# **31. Example threat: malicious image**

Suppose someone gets a vulnerable or malicious container image into the registry.

Controls:

```text
CI security scanning
dependency scanning
image scanning
image signing
signature verification
immutable image tags
restricted registry access
```

Then:

```text
malicious image
     ↓
admission/deployment controls
     ↓
rejected
```

where your chosen tooling and policies support that workflow.

---

# **32. Example threat: compromised developer account**

This one is often forgotten.

Suppose an attacker compromises a developer’s Git account.

They could potentially attempt:

```text
modify source
     ↓
CI
     ↓
production image
```

Controls might include:

```text
MFA
protected branches
pull-request review
short-lived CI credentials
least-privilege deployment identity
image signing
separation of environments
production approval
audit logs
```

Security includes the **software supply chain**, not just runtime infrastructure.

---

# **33. Our complete defense-in-depth architecture**

Now put everything together:

```text
                         INTERNET
                            |
                         HTTPS/TLS
                            |
                            v
                     +-------------+
                     |   Gateway   |
                     +-------------+
                            |
                    routing / policy
                            |
                            v
                  +-------------------+
                  | ProjectHub Service|
                  +-------------------+
                            |
             +--------------+--------------+
             |              |              |
             v              v              v
           Pod A           Pod B          Pod C
             |              |              |
       +-----+--------------+--------------+-----+
       |          Container Security             |
       |  non-root / no privilege escalation     |
       |  read-only filesystem / seccomp         |
       +-----------------------------------------+
                            |
                     NetworkPolicy
                            |
          +-----------------+----------------+
          |                 |                |
          v                 v                v
     PostgreSQL           Redis          RabbitMQ
```

And separately:

```text
Kubernetes API
      |
      v
ServiceAccount
      |
      v
RBAC
```

While inside the application:

```text
JWT
 ↓
JwtDecoder
 ↓
Authentication
 ↓
Authorities
 ↓
@PreAuthorize
 ↓
Resource Policy
 ↓
Database
```

And before deployment:

```text
Git
 ↓
CI
 ↓
Tests
 ↓
Security scans
 ↓
Image
 ↓
Image scan/signing
 ↓
Registry
 ↓
Kubernetes
```

That’s a real production security architecture.

---

# **34. The most important mental model**

Don’t think:

```text
"JWT secures my application."
```

Think:

```text
                    Security
                       |
      +----------------+----------------+
      |                |                |
      v                v                v
   Identity         Network          Runtime
      |                |                |
      v                v                v
    JWT            TLS/Policy      Pod Security
      |
      v
 Authorization
      |
      v
 Spring Security
      |
      v
 Resource Policy

      +

 Kubernetes
      |
      +-- ServiceAccount
      +-- RBAC
      +-- Secrets
      +-- NetworkPolicy
      +-- Admission
```

No individual layer is sufficient.

---

# **35. Security boundary vs trust boundary**

This is a useful concept for system design.

A **trust boundary** is where you stop assuming something is trustworthy.

For ProjectHub:

```text
Internet
   |
   | untrusted
   v
Gateway
   |
   | partially trusted
   v
Application
   |
   | controlled access
   v
Database
```

But even inside Kubernetes:

```text
Pod A
   |
   | don't automatically trust
   v
Pod B
```

That’s why NetworkPolicy exists.

And even inside the application:

```text
authenticated user
   |
   | don't automatically trust
   v
resource ownership
```

That’s why our `PostDeletionPolicy` exists.

---

# **36. Defense in depth appears everywhere**

Notice the pattern:

### **User**

```text
JWT
+
permission
+
resource ownership
```

### **Pod**

```text
ServiceAccount
+
RBAC
+
NetworkPolicy
+
Pod Security
```

### **Secret**

```text
RBAC
+
encryption at rest
+
limited access
+
rotation
```

### **Container**

```text
minimal image
+
scanning
+
non-root
+
read-only filesystem
+
dropped capabilities
```

This is what mature backend engineering looks like.

---

# **Lesson 55 Summary**

You now understand the complete security chain:

```text
Client
  ↓
TLS
  ↓
Gateway
  ↓
ProjectHub
  ↓
JWT authentication
  ↓
permission authorization
  ↓
resource authorization
  ↓
database
```

And the infrastructure security:

```text
Pod
 ↓
ServiceAccount
 ↓
RBAC
 ↓
NetworkPolicy
 ↓
Pod Security
 ↓
Secrets
```

And the supply chain:

```text
Git
 ↓
CI
 ↓
Tests
 ↓
Security scanning
 ↓
Signed/controlled image
 ↓
Registry
 ↓
Kubernetes
```

The central principle is:

**Assume individual layers can fail. Design the system so that one failure does not automatically become total compromise.**

---

# **Exercise 55 — Threat Modeling ProjectHub**

For each scenario, identify:

**1. What is being attacked?**  
**2. What is the attack path?**  
**3. At least 3 controls that reduce the risk.**

### **Scenario A — Stolen JWT**

```text
Attacker obtains Alice's access token.
```

What stops or limits them?

---

### **Scenario B — ProjectHub RCE**

```text
Attacker achieves remote code execution inside a ProjectHub Pod.
```

What stops the attacker from taking over the Kubernetes cluster?

---

### **Scenario C — Compromised developer account**

```text
Attacker gains access to a developer's Git account.
```

What stops them from silently deploying malicious code to production?

---

### **Scenario D — Database credentials leak**

```text
DB_PASSWORD is accidentally exposed.
```

What additional controls prevent this from becoming unrestricted database access?

---

### **Scenario E — Resource authorization**

Alice has:

```text
posts.delete
```

but tries:

```text
DELETE /posts/42
```

where Bob owns the post and Alice is only a regular project member.

Which **application-level** security layer should make the final decision?

---

### **Final challenge**

Draw ProjectHub’s security architecture from memory.

Include:

```text
Internet
↓
TLS
↓
Gateway
↓
Service
↓
Pods
↓
Spring Security
↓
PostgreSQL

and separately:

ServiceAccount
RBAC
NetworkPolicy
Secrets
Pod Security
CI/CD
```

Once you can explain **why each layer exists**, rather than merely naming it, you’ve crossed an important line from learning individual technologies to thinking like a backend/platform engineer.

**Next: Lesson 56 — Kubernetes Observability: Prometheus, metrics, logs, traces, alerts, SLOs, and how to actually know when ProjectHub is failing.**