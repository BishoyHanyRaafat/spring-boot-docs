---
title: "Lesson 80: Testing Spring Boot Properly"
sidebar_position: 80
---

Now we’re entering the testing phase.

The first distinction you need to understand is **unit test vs integration test**. Spring Boot provides `spring-boot-starter-test`, which brings in JUnit, AssertJ, Mockito, Spring Test, and other testing utilities.  

## **1. Unit testing**

Suppose we have:

```java
@Service
public class PostService {

    private final PostRepository repository;

    public PostService(PostRepository repository) {
        this.repository = repository;
    }

    public Post create(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Title is required");
        }

        return repository.save(new Post(title));
    }
}
```

The important thing is:

**We don’t need Spring to test this.**

We can create the service ourselves:

```text
PostService
    ↓
mock PostRepository
```

That’s a unit test.

Spring’s dependency injection actually makes this easier because dependencies are explicit constructor parameters.  

---

# **2. What are we actually testing?**

A good unit test answers:

Given these inputs and dependencies, does this class produce the expected behavior?

For example:

```text
create("Hello")
    ↓
repository.save(...)
    ↓
returns saved post
```

And:

```text
create("")
    ↓
throws IllegalArgumentException
    ↓
repository.save() must NOT happen
```

Notice that we’re testing **behavior**, not implementation details.

---

# **3. JUnit**

A basic JUnit test looks like:

```java
class PostServiceTest {

    @Test
    void shouldCreatePost() {
        // arrange

        // act

        // assert
    }
}
```

JUnit Jupiter is the modern JUnit programming model, and `@Test` identifies a test method. JUnit provides assertions such as `assertEquals`, `assertTrue`, `assertThrows`, etc.  

The standard structure is:

```text
Arrange
   ↓
Act
   ↓
Assert
```

### **Arrange**

Prepare the test.

### **Act**

Execute the behavior.

### **Assert**

Verify what happened.

---

# **4. Mockito**

Now we have a dependency:

```java
PostRepository
```

We don’t want our unit test talking to PostgreSQL.

So we create a **mock**.

Conceptually:

```text
Real repository

PostService → PostgreSQL
```

becomes:

```text
PostService → Mockito mock
                    │
                    └── controlled by test
```

Mockito is included by Spring Boot’s standard test starter.  

The important Mockito concepts are:

```text
mock()
when()
thenReturn()
verify()
```

For example:

```java
when(repository.save(any(Post.class)))
    .thenReturn(savedPost);
```

means:

When the service calls `repository.save(...)`, return `savedPost`.

And:

```java
verify(repository).save(any(Post.class));
```

means:

Verify that the repository was actually called.

---

# **5. The test we want**

Our first exercise should therefore test:

### **Case 1**

```text
valid title
    ↓
post saved
```

### **Case 2**

```text
blank title
    ↓
exception
    ↓
repository NOT called
```

That’s already teaching you something important:

**A good test suite tests both successful behavior and failure behavior.**

---

# 

# **6. Don’t start with**

**`@SpringBootTest`**

This is a common beginner mistake:

```java
@SpringBootTest
class PostServiceTest {
}
```

for every test.

`@SpringBootTest` creates a Spring application context. That’s useful for integration-level testing, but unnecessary overhead when you’re testing a plain service. Spring Boot explicitly supports both full application-context tests and more focused test slices.  

Think:

```text
Unit test
    ↓
No Spring
    ↓
Very fast
```

versus:

```text
Integration test
    ↓
Spring context
    ↓
Real framework behavior
```

We’ll need both.

---

# **7. The testing pyramid we’ll build**

Eventually your ProjectHub tests will look roughly like:

```text
                 E2E
                /   \
          Integration
             /       \
       Controller   Database
          /             \
       Unit tests — Services
```

Lots of:

```text
unit tests
```

Some:

```text
integration tests
```

Fewer:

```text
end-to-end tests
```

Because the lower-level tests should be fast and numerous, while infrastructure-heavy tests are more expensive.

---

# **Exercise 80**

Create a `PostServiceTest`.

You don’t need Spring.

Use Mockito to mock `PostRepository`.

Write **two tests**:

### **Test 1**

```text
shouldCreatePost()
```

Given:

```text
"Hello Spring"
```

verify that:

- `repository.save(...)` is called
- the returned post is the saved post

### **Test 2**

```text
shouldRejectBlankTitle()
```

Given:

```text
""
```

verify that:

- `IllegalArgumentException` is thrown
- `repository.save(...)` is never called

Don’t worry if the Mockito syntax is unfamiliar.

**Send me your test code when you’ve written it.** I’ll review it line by line, then we’ll move to `@SpringBootTest` and integration testing.

⁠Spring Boot Testing Reference