---
title: Lesson 42: Distributed Security JWT Between Microservices
sidebar_position: 42
---

Today we move from **single application security** into **distributed security**.

In a monolith:

```text
Client

  |
  v

Spring Boot Application

  |
  v

Database
```

The application controls everything.

But with microservices:

```text
                 Client

                   |
                   v

              API Gateway

                   |
       +-----------+-----------+

       v           v           v

 Identity     Project      Billing
 Service      Service      Service
```

Now we have new questions:

- Who authenticated the user?
- How does Project Service trust the request?
- Should every service validate JWT?
- How do services trust each other?
- How do we protect internal APIs?

Let’s build the security architecture.

---

# **1. The authentication flow**

The normal flow:

```text
User

 |
 |
 Login

 |
 v

Identity Service

 |
 |
 Creates JWT

 |
 v

Client receives token

 |
 |
 Sends token

 |
 v

API Gateway

 |
 |
 Validates JWT

 |
 v

Project Service
```

---

# **2. Where does authentication happen?**

Usually:

```text
Identity Service
```

is responsible for:

- login
- password verification
- token creation
- refresh tokens

Example:

Request:

```http
POST /api/auth/login
```

Body:

```json
{
 "email":"john@example.com",
 "password":"123456"
}
```

Identity Service:

```
verify password
       |
       v
create JWT
```

Response:

```json
{
 "accessToken":"eyJhbGc..."
}
```

---

# **3. JWT structure**

A JWT has three parts:

```
HEADER.PAYLOAD.SIGNATURE
```

Example:

```
xxxxx.yyyyy.zzzzz
```

---

## **Header**

Contains information about the token.

Example:

```json
{
 "alg":"RS256",
 "typ":"JWT"
}
```

Meaning:

```
Algorithm = RSA SHA256
```

---

## **Payload**

Contains claims.

Example:

```json
{
 "sub":"100",
 "username":"john",
 "roles":[
    "USER"
 ],
 "permissions":[
    "projects.read",
    "projects.create"
 ],
 "exp":1700000000
}
```

---

## **Signature**

Used to verify:

Was this token created by our Identity Service?

---

# **4. The gateway validates the JWT**

Request:

```http
GET /api/projects

Authorization:
Bearer eyJhbGc...
```

Gateway:

```
Extract token

        |

Verify signature

        |

Check expiration

        |

Read claims

        |

Forward request
```

If valid:

```
continue
```

If invalid:

```
401 Unauthorized
```

---

# **5. Symmetric vs asymmetric JWT signing**

Important production concept.

There are two common approaches.

---

# **HS256**

Uses one secret.

Example:

```
Identity Service

secret123

creates token


Project Service

secret123

checks token
```

Problem:

Every service needs the secret.

More places to leak it.

---

# **RS256**

Uses public/private keys.

Better for microservices.

Architecture:

```
             Identity Service


             PRIVATE KEY

                 |
                 |
             Sign JWT


                 |
                 v


              JWT Token


                 |
                 v


      +----------+----------+

      |                     |

Project Service       Gateway


PUBLIC KEY            PUBLIC KEY


Verify                Verify
```

Only Identity Service has the private key.

---

# **6. Gateway validation**

Spring Cloud Gateway uses:

```
OAuth2 Resource Server
```

Example:

```java
@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {


@Bean
SecurityWebFilterChain security(
    ServerHttpSecurity http
){

return http

.csrf(
 csrf -> csrf.disable()
)

.authorizeExchange(
 exchange -> exchange

 .pathMatchers(
   "/api/auth/**"
 )
 .permitAll()

 .anyExchange()
 .authenticated()

)

.oauth2ResourceServer(
 oauth -> oauth.jwt()
)

.build();

}

}
```

---

# **7. What happens after validation?**

The gateway now knows:

```json
{
 "sub":"100",
 "roles":[
   "ADMIN"
 ]
}
```

But how does Project Service know?

There are several patterns.

---

# **8. Pattern 1 — Forward the JWT**

The gateway sends:

```
Client JWT

        |
        v

Project Service
```

Project Service validates again.

Architecture:

```
Gateway

  |
  |
 JWT

  |
  v

Project Service
```

Advantages:

- services are independently secure
- zero trust approach

Disadvantage:

- every service needs JWT configuration

---

# **9. Pattern 2 — Trust the Gateway**

Gateway validates:

```
JWT
 |
 v
Gateway
 |
 v
Project Service
```

Gateway adds:

Header:

```
X-USER-ID:100
X-ROLE:ADMIN
```

Project Service trusts gateway.

Advantages:

- simpler services

Disadvantage:

- gateway becomes highly trusted

---

# **10. Pattern 3 — Hybrid approach**

Common production approach:

Gateway:

```
Validate external user JWT
```

Services:

```
Validate internal requests
```

Example:

```
Internet

   |
   v

Gateway

   |
   v

Services

   |
   v

Database
```

---

# **11. Spring Security in Project Service**

Project Service can also become a Resource Server.

Dependency:

```xml
<dependency>

<groupId>
org.springframework.boot
</groupId>

<artifactId>
spring-boot-starter-oauth2-resource-server
</artifactId>

</dependency>
```

---

Configuration:

```yaml
spring:

 security:

  oauth2:

   resourceserver:

    jwt:

     issuer-uri:
       http://identity-service
```

Now:

```
Project Service

trusts Identity Service tokens
```

---

# **12. Authorization after authentication**

Authentication:

```
Who are you?
```

Example:

```
User 100
```

Authorization:

```
What can you do?
```

Example:

```
Can user 100 delete project?
```

---

# **13. Permissions in microservices**

Remember our earlier design:

```
projects.read
projects.create
projects.delete
```

JWT:

```json
{
 "permissions":[
    "projects.read",
    "projects.create"
 ]
}
```

Project Service:

```java
@PreAuthorize(
"hasAuthority('projects.delete')"
)
public void deleteProject(){

}
```

---

# **14. The problem with permissions everywhere**

Imagine:

Identity Service:

```
projects.delete
```

Project Service:

```
projects.delete
```

Billing Service:

```
projects.delete
```

Now permissions are duplicated.

---

# **15. Central authorization**

A bigger system may use:

```
Authorization Server
```

Examples:

- Keycloak
- Auth0
- Okta

Architecture:

```
             Authorization Server


                    |
                    |
                  JWT


        +-----------+-----------+

        |                       |

 Project Service        Billing Service
```

---

# **16. Service-to-service authentication**

Important:

Not every request comes from a user.

Example:

```
Notification Service

       |

       v

Email Provider
```

or:

```
Project Service

       |

       v

Analytics Service
```

How do services prove identity?

---

# **17. Client Credentials Flow**

OAuth2 has a machine-to-machine flow.

Example:

```
Project Service

client_id:
project-service

client_secret:
abc123


        |

        v


Identity Provider


        |

        v


Access Token
```

Now:

```
Project Service
```

can call:

```
Analytics Service
```

securely.

---

# **18. User token vs Service token**

Very important distinction.

## **User token**

Represents:

```
John
```

Example:

```json
{
 "sub":"john",
 "roles":["USER"]
}
```

---

## **Service token**

Represents:

```
project-service
```

Example:

```json
{
 "client_id":
 "project-service"
}
```

Do not confuse them.

---

# **19. Internal APIs**

Example:

Project Service:

```
GET /internal/projects/10
```

Should not be public.

Protection:

```
Gateway blocks it

+

Service validates caller
```

---

# **20. Zero Trust Architecture**

Modern systems assume:

Never automatically trust a network location.

Meaning:

Even:

```
Project Service
        |
        v
Identity Service
```

must authenticate.

Being inside the same network is not enough.

---

# **21. Security architecture for ProjectHub**

Final design:

```
                         Client

                           |
                           v

                     API Gateway

                           |
                  Validate User JWT

                           |
        +------------------+------------------

        v                                     v


 Identity Service                      Project Service


 Creates JWT                           Validates JWT


        |                                     |

        +------------- Public Key ------------+
```

---

# **22. Complete request example**

User logs in:

```
POST /login
```

Identity Service:

```
verify password

create JWT
```

Returns:

```json
{
"accessToken":"abc.xyz"
}
```

---

User requests:

```
DELETE /api/projects/10
```

Header:

```
Authorization: Bearer abc.xyz
```

Gateway:

```
JWT valid
```

Project Service:

```
permission required:

projects.delete
```

Security:

```
allowed
```

Delete happens.

---

# **23. Common security mistakes**

## **Mistake 1**

Putting passwords in JWT.

Bad:

```json
{
 "password":"123456"
}
```

Never.

---

## **Mistake 2**

Huge JWTs.

Bad:

```json
{
 "allProjects":[
 10000 projects
 ]
}
```

Tokens travel everywhere.

---

## **Mistake 3**

Trusting headers from clients.

Bad:

Client sends:

```
X-USER-ID: ADMIN
```

Never trust that.

Only gateway/services should add trusted headers.

---

## **Mistake 4**

Sharing private keys.

Bad:

```
Identity Service private key

copied to every service
```

Use public keys.

---

# **Lesson 42 Summary**

You learned:

✅ JWT in microservices  
✅ Authentication flow  
✅ RS256 vs HS256  
✅ Gateway JWT validation  
✅ Resource servers  
✅ Authorization with permissions  
✅ User tokens vs service tokens  
✅ OAuth2 client credentials  
✅ Internal API protection  
✅ Zero trust principles  
✅ Production security architecture

---

# **Exercise 42**

Answer:

### **1.**

Why is RS256 usually preferred over HS256 in microservices?

---

### **2.**

What is the difference between:

```
Authentication
```

and:

```
Authorization
```

---

### **3.**

Should Notification Service receive:

```
User JWT
```

or:

```
Service token
```

when sending emails?

Explain.

---

### **4.**

Where should the private JWT signing key exist?

---

### **5.**

Design the login flow:

```
User
 |
 ?
 |
 JWT
 |
 Gateway
 |
 Project Service
```

Fill the missing parts.

---

Next lesson:

# **Lesson 43 — Observability: Logs, Metrics, Tracing, and Debugging Microservices**

We will learn how companies debug systems with:

- centralized logging
- Prometheus metrics
- Grafana dashboards
- distributed tracing
- correlation IDs
- OpenTelemetry

Because in microservices:

**If you cannot observe it, you cannot operate it.**