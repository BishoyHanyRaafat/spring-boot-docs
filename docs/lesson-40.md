---
title: "Lesson 40: API Gateway + Spring Cloud Gateway"
sidebar_position: 40
---

Today we build the **front door** of ProjectHub.

Until now our client talks directly to services:

```text
              Client

                |
        +-------+-------+
        |       |       |
        v       v       v

     Identity Project Notification
     Service  Service  Service
```

This works at small scale.

But it creates problems.

The client must know:

- where every service lives
- how authentication works
- how errors are handled
- how requests are routed

A better design:

```text
                 Client

                   |
                   v

             API Gateway

                   |
       +-----------+-----------+
       |           |           |

       v           v           v

 Identity     Project     Notification
 Service      Service      Service
```

The gateway becomes the single entry point.

---

# **1. What is an API Gateway?**

An API Gateway is a server that sits between:

```text
Client
```

and:

```text
Backend services
```

It receives requests and forwards them.

Example:

Client sends:

```http
GET /api/projects/10
```

Gateway decides:

```
/api/projects/**
        |
        v
Project Service
```

---

# **2. Responsibilities of a Gateway**

A gateway usually handles:

## **Routing**

Example:

```
/api/projects/**

        |

        v

Project Service
```

---

## **Authentication**

Example:

```
Request
   |
   v
Gateway

Check JWT

   |
   v

Allow / Reject
```

---

## **Rate limiting**

Example:

Prevent:

```
Client A

100,000 requests/sec
```

---

## **Logging**

Central place:

```
requestId
duration
status code
errors
```

---

## **Request transformation**

Example:

Client sends:

```json
{
 "username":"john"
}
```

Gateway modifies headers:

```
X-User-ID: 123
```

---

# **3. Spring Cloud Gateway**

Spring provides:

```
Spring Cloud Gateway
```

It is built on:

```
Spring WebFlux
```

not traditional Spring MVC.

Architecture:

```
Client

 |
 v

Spring Cloud Gateway

 |
 v

Microservices
```

---

# **4. Creating the Gateway project**

Create a new Spring Boot application:

```
projecthub-gateway
```

Dependencies:

```
Spring Cloud Gateway
Spring Security
OAuth2 Resource Server
```

---

# **5. Maven dependency**

Example:

```xml
<dependency>
    <groupId>
        org.springframework.cloud
    </groupId>

    <artifactId>
        spring-cloud-starter-gateway
    </artifactId>
</dependency>
```

---

# **6. Basic Gateway configuration**

application.yml:

```yaml
spring:

  cloud:

    gateway:

      routes:

        - id: project-service

          uri: http://project-service:8081

          predicates:

            - Path=/api/projects/**
```

Meaning:

```
Request:

/api/projects/**


goes to:


http://project-service:8081
```

---

# **7. Adding more services**

Example:

```yaml
spring:

 cloud:

  gateway:

   routes:

    - id: project-service

      uri: http://project-service:8081

      predicates:

       - Path=/api/projects/**



    - id: identity-service

      uri: http://identity-service:8082

      predicates:

       - Path=/api/auth/**
```

Now:

```
/api/projects

        |
        v

Project Service



/api/auth

        |
        v

Identity Service
```

---

# **8. The complete request flow**

User:

```http
GET /api/projects
```

Flow:

```
Browser

   |
   v

API Gateway

   |
   v

Project Service

   |
   v

Database
```

The client never knows:

```
project-service:8081
```

---

# **9. Why hide services?**

Imagine your infrastructure:

Today:

```
project-service:8081
```

Tomorrow:

```
10 instances
```

Maybe:

```
project-service-instance-1
project-service-instance-2
project-service-instance-3
```

The client should not care.

The gateway hides this complexity.

---

# **10. Gateway authentication**

Before:

Each service does:

```
Check JWT
Check roles
Check permissions
```

Example:

```
Project Service

    |
    v

Is token valid?
```

Every service repeats security code.

---

With gateway:

```
Client

 |
 v

Gateway

 |
 |
 Validate JWT

 |
 v

Project Service
```

Now invalid requests never reach services.

---

# **11. JWT validation architecture**

Example:

Client:

```http
GET /api/projects

Authorization:
Bearer eyJhbGci...
```

Gateway:

```
Extract token

      |

Verify signature

      |

Check expiration

      |

Extract claims

      |

Forward request
```

---

# **12. Spring Security at Gateway**

Security configuration:

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
            oauth ->
            oauth.jwt()
        )

        .build();
}

}
```

Notice:

Gateway uses:

```
WebFlux Security
```

not:

```
HttpSecurity
```

because Gateway is reactive.

---

# **13. What happens after authentication?**

JWT:

```json
{
 "sub":"123",
 "roles":[
    "USER"
 ]
}
```

Gateway validates it.

Then:

```
Request
   |
   |
 Headers added

X-User-ID:123

   |
   v

Project Service
```

---

# **14. Gateway filters**

Filters modify requests.

Example:

Before:

```
GET /api/projects
```

Filter:

```
Add:

X-Request-ID:
abc-123
```

After:

```
GET /api/projects

Header:

X-Request-ID=abc-123
```

---

# **15. Creating a custom filter**

Example:

```java
@Component
public class LoggingFilter
        implements GlobalFilter {


@Override
public Mono<Void> filter(
 ServerWebExchange exchange,
 GatewayFilterChain chain
){

    System.out.println(
        exchange
        .getRequest()
        .getURI()
    );


    return chain.filter(exchange);
}

}
```

Every request passes through it.

---

# **16. Request tracing**

In distributed systems:

One request touches:

```
Gateway

   |

Project Service

   |

Notification Service
```

How do we follow it?

Use:

```
Request ID
```

Example:

```
X-Correlation-ID:
abc-123
```

Every service logs:

```
abc-123
```

Now debugging is possible.

---

# **17. Rate limiting**

Example:

A user sends:

```
10000 requests/sec
```

Gateway says:

```
Too many requests

HTTP 429
```

Response:

```http
429 Too Many Requests
```

---

Common algorithms:

## **Token Bucket**

Imagine:

```
Bucket capacity: 100 tokens
```

Each request:

```
remove 1 token
```

Tokens refill over time.

---

# **18. Gateway vs Load Balancer**

These are different.

Load balancer:

```
Distributes traffic
```

Example:

```
Project Service

Instance 1
Instance 2
Instance 3
```

Gateway:

```
Understands APIs

Authentication
Routing
Filters
```

They can work together.

---

# **19. Service discovery**

Hardcoded:

```yaml
uri:
 http://project-service:8081
```

works for simple environments.

But production changes:

```
Instance count changes
Servers restart
IPs change
```

Use discovery.

Example:

```
Eureka
Consul
Kubernetes Service Discovery
```

Then:

```yaml
uri:
 lb://project-service
```

Meaning:

```
Find project-service automatically
```

---

# **20. Gateway architecture with discovery**

Now:

```
                 Client

                   |

                   v

             API Gateway

                   |

          Service Discovery

                   |

        +----------+----------+

        |          |          |

        v          v          v


    Project    Identity   Notification

    Service    Service    Service
```

---

# **21. Failure handling**

Imagine:

```
Gateway

   |

Project Service

   X

Database down
```

The gateway should not hang forever.

Solutions:

- timeout
- retry
- circuit breaker

---

# **22. Circuit breaker idea**

Without:

```
Request

 |
 v

Failed Service

 |
 v

Wait 30 seconds
```

Thousands of requests pile up.

---

Circuit breaker:

```
Healthy

  |
  v

Failure detected

  |
  v

OPEN

(stop calling service)

  |
  v

Try again later
```

Technology:

```
Resilience4j
```

---

# **23. ProjectHub final architecture**

Now:

```
                         Client

                           |
                           v

                    API Gateway

                           |
        +------------------+------------------+

        |                  |                  |

        v                  v                  v


 Identity Service    Project Service    Notification Service


        |                  |                  |

        v                  v                  v


 Identity DB        Project DB       Notification DB



                           |

                           v

                        RabbitMQ
```

---

# **24. Important design decision**

Should every service be behind the gateway?

Usually:

External traffic:

```
Client
 |
 Gateway
 |
 Services
```

Internal communication:

Maybe:

```
Service A
 |
Service B
```

directly.

Not everything needs to pass through the gateway.

---

# **25. Common beginner mistakes**

## **Mistake 1**

Putting business logic in gateway.

Bad:

```
Gateway:

Create project
Calculate permissions
Update database
```

Gateway should route, not become another monolith.

---

## **Mistake 2**

Making gateway a bottleneck.

Bad:

```
Everything goes through one giant gateway service
```

Keep it lightweight.

---

## **Mistake 3**

No observability.

Distributed systems need:

- logs
- metrics
- tracing

Otherwise debugging becomes painful.

---

# **Lesson 40 Summary**

You learned:

✅ What an API Gateway is  
✅ Why microservices use gateways  
✅ Spring Cloud Gateway basics  
✅ Routing  
✅ JWT authentication at gateway level  
✅ Filters  
✅ Request tracing  
✅ Rate limiting  
✅ Service discovery  
✅ Circuit breakers  
✅ Gateway architecture patterns

---

# **Exercise 40**

Answer these:

### **1.**

Why is this better?

```
Client

 |

Gateway

 |

Services
```

than:

```
Client

 |
 +---- Service A
 |
 +---- Service B
 |
 +---- Service C
```

---

### **2.**

What should a gateway NOT contain?

---

### **3.**

Explain the difference:

```
Gateway
```

vs

```
Load Balancer
```

---

### **4.**

Where should JWT validation happen?

Option A:

```
Every service
```

Option B:

```
Gateway only
```

Option C:

```
Both
```

Explain your choice.

---

### **5.**

Why do we need request IDs in microservices?

---

Next lesson:

# **Lesson 41 — Service-to-Service Communication: REST, OpenFeign, gRPC, and Events**

We will build communication between services:

```
Project Service

      |
      +---- REST ----> Identity Service

      |
      +---- Event ---> Notification Service
```

We will learn:

- OpenFeign
- REST clients
- gRPC basics
- synchronous vs asynchronous decisions
- timeouts
- retries
- circuit breakers

This is where our services start talking to each other.