---
title: Lesson 41: Service-to-Service Communication REST, OpenFeign, gRPC, and Events
sidebar_position: 41
---

Now our ProjectHub has multiple services:

```text
                         Client

                           |
                           v

                    API Gateway

                           |
        +------------------+------------------+

        v                  v                  v

 Identity Service    Project Service    Notification Service
```

The big question:

**How do these services communicate with each other?**

Example:

A user creates a project.

Project Service needs to know:

“Is this user allowed to create projects?”

It needs Identity Service.

How?

There are several approaches.

---

# **1. The three communication styles**

In backend systems, services usually communicate in three ways:

```text
1. REST HTTP

2. gRPC

3. Messaging / Events
```

---

# **2. REST communication**

The simplest.

Service A calls Service B using HTTP.

Example:

```text
Project Service

       |
       |
       v

Identity Service
```

Request:

```http
GET /users/10
```

Response:

```json
{
  "id":10,
  "username":"john",
  "active":true
}
```

---

# **3. Example without libraries**

You can call another service using:

```java
RestTemplate
```

Example:

```java
@Service
public class UserClient {


private final RestTemplate restTemplate;


public UserClient(
    RestTemplate restTemplate
){
    this.restTemplate = restTemplate;
}



public UserDTO getUser(Long id){

    return restTemplate.getForObject(
        "http://identity-service/users/" + id,
        UserDTO.class
    );

}

}
```

Flow:

```text
Project Service

        |
        |
 HTTP GET

        |
        v

Identity Service
```

---

# **4. The problem with manual REST calls**

Imagine this everywhere:

```java
"http://identity-service/users/"
```

Problems:

- URLs everywhere
- repeated code
- error handling everywhere
- difficult testing

Spring gives us a better approach.

---

# **5. OpenFeign**

OpenFeign lets you create an interface.

Instead of writing HTTP code:

```java
restTemplate.getForObject(...)
```

You write:

```java
userClient.getUser(10);
```

Spring creates the HTTP call.

---

# **6. Add OpenFeign dependency**

In Project Service:

```xml
<dependency>

    <groupId>
        org.springframework.cloud
    </groupId>

    <artifactId>
        spring-cloud-starter-openfeign
    </artifactId>

</dependency>
```

---

# **7. Enable Feign**

Main class:

```java
@SpringBootApplication
@EnableFeignClients
public class ProjectApplication {


public static void main(String[] args){

    SpringApplication.run(
        ProjectApplication.class,
        args
    );

}

}
```

---

# **8. Create a Feign client**

Example:

```java
@FeignClient(
    name="identity-service"
)
public interface UserClient {


@GetMapping("/users/{id}")
UserDTO getUser(
    @PathVariable Long id
);


}
```

Now Spring knows:

```text
identity-service

GET /users/{id}
```

---

# **9. Using the client**

Inside Project Service:

```java
@Service
@RequiredArgsConstructor
public class ProjectService {


private final UserClient userClient;



public Project createProject(
        Long userId
){


UserDTO user =
    userClient.getUser(userId);


if(!user.active()){

    throw new RuntimeException(
        "Inactive user"
    );

}


return create();

}

}
```

Looks like a normal Java method.

But behind the scenes:

```text
Java method call

        |

        v

HTTP request

        |

        v

Identity Service
```

---

# **10. Service discovery with Feign**

Hardcoded:

```java
@FeignClient(
 name="http://localhost:8082"
)
```

Bad.

Because:

- servers change
- containers restart
- multiple instances exist

Better:

```java
@FeignClient(
 name="identity-service"
)
```

Then:

```text
identity-service

Instance 1
Instance 2
Instance 3
```

Service discovery finds one.

---

# **11. Synchronous communication**

REST and Feign are synchronous.

Meaning:

The caller waits.

Example:

```text
Project Service

   |
   |
 "Give me user"

   |
   |
(wait)

   |
   v

Identity Service
```

The response is needed immediately.

---

# **12. When should we use synchronous calls?**

Good examples:

## **Permission check**

Question:

```text
Can user 10 edit project 5?
```

Need answer:

```text
YES / NO
```

Use REST.

---

## **Getting current user profile**

Example:

```text
Display user information
```

Use REST.

---

# **13. When NOT to use REST**

Bad:

```text
Project created

        |
        v

Call Notification Service

        |
        v

Send email

        |
        v

Call Analytics Service

        |
        v

Update dashboard
```

Why?

Because creating a project now depends on:

- notification
- analytics
- search

If one fails:

```text
Project creation fails
```

Not good.

---

# **14. Use events for reactions**

Better:

```text
Project Service

creates project


publishes:

PROJECT_CREATED


        |
        v

RabbitMQ


        |
        +-------- Notification
        |
        +-------- Analytics
        |
        +-------- Search
```

Project Service says:

“A project was created.”

It does not care who listens.

---

# **15. REST vs Events decision**

A simple rule:

## **Ask a question?**

Use REST.

Example:

```text
Is this user an admin?
```

Answer required now.

---

## **Announce a fact?**

Use events.

Example:

```text
ProjectCreated
```

Something happened.

---

# **16. gRPC**

Now another communication style.

gRPC is:

- faster than REST
- strongly typed
- binary communication

Common in internal service communication.

Architecture:

```text
Project Service

       |
       |
      gRPC

       |
       v

Identity Service
```

---

# **17. REST vs gRPC**

REST:

Message:

```json
{
"id":10,
"name":"John"
}
```

Human-readable.

---

gRPC:

Message:

```text
Binary format
```

Smaller and faster.

---

# **18. Protocol Buffers**

gRPC uses:

```text
.proto files
```

Example:

```protobuf
syntax="proto3";


service UserService {


rpc GetUser(UserRequest)
returns(UserResponse);


}


message UserRequest {

int64 id = 1;

}


message UserResponse {

string name = 1;

}
```

This defines the contract.

---

# **19. gRPC flow**

You write:

```protobuf
GetUser()
```

Tools generate:

Client code:

```java
userStub.getUser()
```

Server code:

```java
override getUser()
```

Both sides share the contract.

---

# **20. When use gRPC?**

Good:

Internal communication:

```text
Microservice A

        |

      gRPC

        |

Microservice B
```

Examples:

- high traffic systems
- low latency requirements
- internal APIs

---

Less useful:

Public APIs:

```text
Browser

  |

gRPC
```

Browsers usually prefer REST.

---

# **21. Failure problem**

Imagine:

```text
Project Service

      |

Identity Service

      X
```

What happens?

Your request waits forever.

---

We need:

- timeout
- retry
- circuit breaker

---

# **22. Timeouts**

Never do:

```text
wait forever
```

Example:

```yaml
timeout:
  2 seconds
```

Meaning:

```text
Identity Service does not answer

after 2 seconds

stop waiting
```

---

# **23. Retry**

Example:

First attempt:

```text
Identity Service

     X
```

Retry:

```text
Attempt 2

     X
```

Retry:

```text
Attempt 3

     OK
```

Useful for temporary failures.

---

# **24. But retries can be dangerous**

Example:

Payment:

```text
Charge card
```

Request fails.

Retry:

```text
Charge card again
```

Possible:

```text
Customer charged twice
```

Retries require careful design.

---

# **25. Circuit breaker**

Imagine Identity Service is down.

Without protection:

```text
1000 requests

       |

1000 failures
```

With circuit breaker:

```text
Identity Service fails


Circuit opens


Requests fail immediately
```

---

States:

## **Closed**

Normal:

```text
Request
 |
 v
Service
```

---

## **Open**

Broken:

```text
Request

 |
 v

Rejected immediately
```

---

## **Half-open**

Testing:

```text
Try a request

If successful:

close circuit
```

---

# **26. Resilience4j example**

Dependency:

```xml
<dependency>

<groupId>
io.github.resilience4j
</groupId>

<artifactId>
resilience4j-spring-boot3
</artifactId>

</dependency>
```

---

Example:

```java
@CircuitBreaker(
name="identity",
fallbackMethod="fallback"
)
public UserDTO getUser(Long id){

    return userClient.getUser(id);

}
```

Fallback:

```java
public UserDTO fallback(
Long id,
Exception e
){

    return null;

}
```

---

# **27. The complete ProjectHub communication map**

Now:

```text
                    API Gateway


                         |

        +----------------+----------------+

        |                                 |

        v                                 v


 Project Service                  Identity Service


        |

        |

        +------ REST/Feign ------>

        |
        |
        |
        +------ Event ---------->

                    RabbitMQ

                       |

        +--------------+--------------+

        v              v              v


 Notification     Analytics       Search
```

---

# **28. Communication rules for ProjectHub**

Let’s define them.

## **Identity Service**

Provides:

```text
GET /users/{id}
```

Used by:

```text
Project Service
Billing Service
```

---

## **Project Service**

Publishes:

```text
PROJECT_CREATED
PROJECT_UPDATED
PROJECT_DELETED
```

---

## **Notification Service**

Consumes:

```text
PROJECT_CREATED
```

---

## **Analytics Service**

Consumes:

```text
PROJECT_CREATED
PROJECT_UPDATED
```

---

# **29. Important architecture principle**

Avoid this:

```text
Project Service

calls

Identity Service

calls

Notification Service

calls

Analytics Service
```

This creates a chain:

```text
A → B → C → D
```

Failure spreads.

---

Prefer:

```text
A

 |
 +---- REST ---> B

 |
 +---- Event ---> C

 |
 +---- Event ---> D
```

---

# **Lesson 41 Summary**

Today you learned:

✅ Service-to-service communication  
✅ REST between services  
✅ OpenFeign clients  
✅ Service discovery concept  
✅ Synchronous communication  
✅ Event-driven communication  
✅ REST vs Events decision  
✅ gRPC basics  
✅ Timeouts  
✅ Retries  
✅ Circuit breakers  
✅ Communication design rules

---

# **Exercise 41**

Answer:

### **1.**

Project Service needs:

```text
"Can user edit this project?"
```

Would you use:

A) RabbitMQ event  
B) REST call  
C) Database sharing

Explain.

---

### **2.**

Notification after project creation:

REST or Event?

Why?

---

### **3.**

Why is this dangerous?

```text
A → B → C → D
```

---

### **4.**

What problem does OpenFeign solve?

---

### **5.**

Explain:

```text
At least once delivery
```

and why consumers need idempotency.

---

Next lesson:

# **Lesson 42 — Distributed Security: JWT Between Microservices**

We will build:

```text
Client

 |
 v

Gateway

 |
JWT

 |
 v

Project Service

 |
 v

Identity Service
```

Topics:

- JWT propagation
- service authentication
- user identity forwarding
- OAuth2 concepts
- service-to-service security
- protecting internal APIs

This is where our security architecture becomes production-grade.