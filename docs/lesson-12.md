---
title: Lesson 12: JPA Relationships in Depth
sidebar_position: 12
---

This is one of the most important JPA lessons.

The annotations themselves are easy:

```java
@ManyToOne
@OneToMany
@ManyToMany
```

The difficult part is understanding **who owns the relationship, what gets stored in the database, what gets loaded, and what happens when entities are deleted or updated.**

We’ll build this around our ProjectHub model.

---

# **1. Start from SQL, not Java**

Our database looks roughly like:

```text
users
----------------
id
username
email


posts
----------------
id
title
content
author_id


comments
----------------
id
content
author_id
post_id


projects
----------------
id
name


project_members
----------------
project_id
user_id
```

The important thing is:

**The database relationship is defined by foreign keys.**

JPA is simply giving us a Java representation of those relationships.

---

# **2. `@ManyToOne`**

We’ve already seen this:

```java
@Entity
public class Post {

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "author_id")
    private User author;
}
```

Why `ManyToOne`?

Because:

```text
One User
   │
   ├── Post
   ├── Post
   └── Post
```

Many posts → one user.

The database stores:

```text
posts
----------------------
id | title | author_id
```

The **foreign key is on** **`posts`**.

That fact becomes extremely important.

---

# **3. The owning side**

Consider:

```java
Post.author
```

and:

```java
User.posts
```

Which one controls the database foreign key?

**Post.**

Why?

Because the foreign key physically exists here:

```text
posts.author_id
```

Therefore:

```java
@ManyToOne
@JoinColumn(name = "author_id")
private User author;
```

is the **owning side**.

This is one of the most important JPA concepts.

---

# **4. Bidirectional relationship**

We can make the relationship navigable in both directions.

### **Post**

```java
@Entity
public class Post {

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "author_id", nullable = false)
    private User author;

}
```

### **User**

```java
@Entity
public class User {

    @OneToMany(mappedBy = "author")
    private List<Post> posts = new ArrayList<>();

}
```

Now Java can navigate:

```text
User
 ↓
posts
 ↓
Post
 ↓
author
 ↓
User
```

---


# **5. What does `mappedBy` mean?**

This:

```java
@OneToMany(mappedBy = "author")
```

means:

“The relationship is already mapped by the `author` field on the `Post` entity.”

In other words:

```text
User.posts
    ↓
mappedBy = "author"
    ↓
Post.author
```

It does **not** mean the database has a column called `author`.

It references the **Java field name**.

This distinction is critical.

For example:

```java
private User author;
```

means:

```java
mappedBy = "author"
```

not:

```java
mappedBy = "author_id"
```

---

# **6. The common mistake**

People often write:

```java
user.getPosts().add(post);
```

and expect the database relationship to be created.

But remember:

```java
@OneToMany(mappedBy = "author")
```

is the inverse side.

The actual foreign-key owner is:

```java
post.setAuthor(user);
```

So if you only do:

```java
user.getPosts().add(post);
```

you haven’t necessarily changed the relationship that Hibernate persists.

This is why bidirectional relationships often use helper methods.

---

# **7. Helper methods**

Instead of allowing this:

```java
user.getPosts().add(post);
post.setAuthor(user);
```

everywhere in the application, we can put the relationship management inside `User`.

```java
public void addPost(Post post) {
    posts.add(post);
    post.setAuthor(this);
}
```

Now:

```java
user.addPost(post);
```

keeps both sides synchronized.

Likewise:

```java
public void removePost(Post post) {
    posts.remove(post);
    post.setAuthor(null);
}
```

Although whether you should allow `null` depends on your business/database constraints.

This is a broader design principle:

If two objects must stay synchronized, centralize that invariant rather than relying on every caller to remember it.

---

# **8. `@OneToMany`**

Now let’s examine:

```java
@OneToMany(mappedBy = "author")
private List<Post> posts;
```

This means:

One User has many Posts.

Notice that `@OneToMany` by itself doesn’t tell Hibernate where the foreign key is.

`mappedBy` points to the other side:

```text
User.posts
     ↓
Post.author
```

And `Post.author` contains:

```java
@JoinColumn(name = "author_id")
```

which maps to:

```text
posts.author_id
```

---

# **9. Do we always need both sides?**

**No.**

This is important.

You don’t have to make every relationship bidirectional.

For example, you might have:

```java
@Entity
public class Post {

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "author_id")
    private User author;
}
```

and no:

```java
@OneToMany
private List<Post> posts;
```

That’s completely valid.

Then you can navigate:

```text
Post → User
```

but not directly:

```text
User → Posts
```

You can still query posts by user using:

```java
List<Post> findByAuthorId(Long authorId);
```

In fact, **unidirectional relationships are sometimes preferable** because they keep your entity model simpler.

Don’t add bidirectional relationships just because you can.

---


# **10. `@OneToMany`**

**can be expensive**

Imagine:

```java
User user = ...
user.getPosts();
```

A user could have:

```text
10 posts
```

or:

```text
1,000,000 posts
```

Do you really want a `User` object to naturally carry an enormous collection?

Usually not.

This is one reason it’s often useful to query the collection explicitly:

```java
postRepository.findByAuthorId(userId);
```

rather than treating:

```java
user.getPosts()
```

as your universal way to access posts.

---

# **11. `@ManyToMany`**

Now let’s return to:

```text
Users ↔ Projects
```

A user can belong to many projects.

A project can contain many users.

SQL solves this with:

```text
users
projects
project_members
```

where:

```text
project_members
--------------------
project_id
user_id
```

---

# **12. JPA representation**

You can represent that as:

```java
@Entity
public class Project {

    @ManyToMany
    @JoinTable(
        name = "project_members",
        joinColumns = @JoinColumn(name = "project_id"),
        inverseJoinColumns = @JoinColumn(name = "user_id")
    )
    private Set<User> members = new HashSet<>();
}
```

Let’s understand it.

### **`@JoinTable`**

The relationship is stored in:

```text
project_members
```

### **`joinColumns`**

```java
@JoinColumn(name = "project_id")
```

means:

This side of the relationship uses `project_id`.

### **`inverseJoinColumns`**

```java
@JoinColumn(name = "user_id")
```

means:

The other entity uses `user_id`.

So:

```text
Project
   │
   ▼
project_members
   │
   ▼
User
```

---

# **13. Why I usually don’t recommend blindly using**

**`@ManyToMany`**

This is a very useful real-world lesson.

Suppose project membership eventually needs:

```text
user_id
project_id
role
joined_at
invited_by
status
```

Our join table isn’t just a dumb relationship anymore.

It’s an actual domain concept:

```text
ProjectMembership
```

So instead of:

```java
@ManyToMany
Set<User> members;
```

you may model:

```text
Project
   │
   │ 1:N
   ▼
ProjectMembership
   ▲
   │ N:1
   │
 User
```

Then:

```java
@Entity
public class ProjectMembership {

    @ManyToOne
    private Project project;

    @ManyToOne
    private User user;

    private String role;

    private Instant joinedAt;
}
```

This is often much more flexible.

For ProjectHub, we’ll eventually want project roles/permissions, so **`ProjectMembership`** **is likely a better domain model than a bare** **`@ManyToMany`****.**

---

# **14. Cascades**

Now we reach a dangerous topic.

You may see:

```java
cascade = CascadeType.ALL
```

and think:

“I’ll just put this everywhere.”

Don’t.

Let’s understand what cascade means.

Suppose:

```text
Parent
  ↓
Child
```

Cascade controls whether certain persistence operations applied to the parent propagate to the child.

For example:

```java
@OneToMany(cascade = CascadeType.PERSIST)
private List<Post> posts;
```

Persisting the user can also persist newly associated posts.

---

# **15. Cascade types**

The important ones are:

```text
PERSIST
MERGE
REMOVE
REFRESH
DETACH
```

and:

```java
CascadeType.ALL
```

means all of them.

You don’t need to memorize every one right now.

The important conceptual distinction is:

**Cascade controls persistence operations.**

It does **not** mean:

“These entities are conceptually the same thing.”

---

# 16. `CascadeType.REMOVE

**can be dangerous**

Imagine:

```text
User
 ├── Post
 ├── Post
 └── Post
```

If you configure:

```java
cascade = CascadeType.REMOVE
```

then deleting the user can cause the posts to be deleted.

Sometimes that’s correct.

But sometimes it’s absolutely not.

For example, maybe deleting a user should:

```text
disable user
```

while preserving their historical posts.

So don’t use cascade based on convenience.

Ask:

“Should the lifecycle of the child really depend on the lifecycle of the parent?”

That’s the real question.

---

# **17. Orphan removal**

Now consider:

```java
@OneToMany(
    mappedBy = "author",
    orphanRemoval = true
)
private List<Post> posts;
```

Conceptually:

```text
User
 └── Post
```

If you remove a post from the parent’s collection:

```java
user.removePost(post);
```

the child may be deleted from the database.

That’s **orphan removal**.

This is useful when the child has no meaningful existence outside the parent.

For example:

```text
Order
 └── OrderLine
```

An `OrderLine` may be conceptually owned by the order.

But:

```text
User
 └── Post
```

is a much more debatable relationship.

A post may need to survive the user’s deletion.

So don’t automatically use:

```java
orphanRemoval = true
```

everywhere.

---

# **18. Cascade vs orphan removal**

This distinction is worth remembering:

### **Cascade**

```text
Operation on parent
        ↓
propagates to child
```

### **Orphan removal**

```text
Child removed from parent's relationship
        ↓
child may be deleted
```

They’re related concepts, but they’re not the same thing.

---

# **19. Lazy vs eager loading**

This is another huge topic.

Consider:

```java
@ManyToOne(fetch = FetchType.LAZY)
private User author;
```

With lazy loading:

```text
Load Post
   ↓
Post loaded
   ↓
author may not be loaded yet
```

With eager loading:

```text
Load Post
   ↓
Post + User loaded
```

You might think:

“EAGER sounds easier.”

But eager relationships can cause massive unintended queries and data loading.

For that reason, a common approach is to prefer **LAZY associations** and explicitly fetch what a particular use case needs.

We’ll practice this when we start writing real queries.

---

# **20. The N+1 problem**

Let’s make this concrete.

Suppose:

```java
List<Post> posts = postRepository.findAll();

for (Post post : posts) {
    System.out.println(post.getAuthor().getUsername());
}
```

Potentially:

```text
Query 1:
SELECT posts...

Query 2:
SELECT user WHERE id = 1

Query 3:
SELECT user WHERE id = 2

Query 4:
SELECT user WHERE id = 3

...
```

If there are 100 posts, you might end up with:

```text
1 + 100 = 101 queries
```

That’s the N+1 problem.

The exact behavior depends on the mapping, persistence context, query, and access pattern, but the underlying issue is:

We’re unintentionally performing many database queries when one appropriately designed query could retrieve the needed data.

---

# **21. Solving N+1**

Later we’ll learn several strategies.

One is a fetch join:

```java
@Query("""
    select p
    from Post p
    join fetch p.author
""")
List<Post> findAllWithAuthor();
```

Conceptually this becomes something like:

```sql
SELECT ...
FROM posts p
JOIN users u
    ON p.author_id = u.id;
```

Now Hibernate can retrieve the posts and authors together.

This is one reason understanding SQL joins from Lesson 10 was important.

---

# **22. Entity graphs**

Another approach is an entity graph.

For example:

```java
@EntityGraph(attributePaths = "author")
List<Post> findAll();
```

This can tell Spring Data/Hibernate that for this repository operation, we want the author fetched as part of the query plan.

We’ll go much deeper into this later.

---

# **23. Don’t return entities directly from controllers**

This becomes even more important with relationships.

Imagine:

```java
@GetMapping("/{id}")
public User getUser(@PathVariable Long id) {
    return userService.getUser(id);
}
```

Your `User` contains:

```java
List<Post> posts;
```

and each `Post` contains:

```java
User author;
```

You can end up with:

```text
User
 ↓
Posts
 ↓
Author
 ↓
Posts
 ↓
Author
 ↓
...
```

Even if serialization doesn’t literally recurse forever in every setup, you can run into:

- recursive JSON
- huge responses
- unexpected lazy-loading
- database queries during serialization
- exposing internal fields

This is another strong reason for DTOs.

---

# **24. DTOs define what relationships the API exposes**

Instead of:

```java
public User getUser(...)
```

we might return:

```java
public record UserResponse(
    Long id,
    String username
) {}
```

And for a post:

```java
public record PostResponse(
    Long id,
    String title,
    String content,
    Long authorId,
    String authorUsername
) {}
```

Now the API explicitly says:

A post response contains the author’s ID and username.

Not:

Serialize my entire entity graph.

That’s much safer.

---

# **25. One more relationship: comments**

Our comment model is:

```text
User 1 ───── N Comment
Post 1 ───── N Comment
```

So:

```java
@Entity
public class Comment {

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "author_id", nullable = false)
    private User author;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "post_id", nullable = false)
    private Post post;
}
```

That’s actually two separate `ManyToOne` relationships.

The database becomes:

```text
comments
--------------------------------
id
content
author_id → users.id
post_id   → posts.id
```

This is a very common relational pattern.

---

# **26. Our ProjectHub relationships**

We now have:

```text
User
 │
 ├──── 1:N ────> Post
 │
 ├──── 1:N ────> Comment
 │
 └──── 1:N ────> ProjectMembership
                         │
                         │ N:1
                         ▼
                      Project
                         │
                         └──── 1:N ────> Post
```

Notice something interesting:

We haven’t actually needed `@ManyToMany`.

That’s deliberate.

Instead of:

```text
User ↔ Project
```

we have:

```text
User → ProjectMembership ← Project
```

because membership itself can carry information.

Eventually:

```text
ProjectMembership
----------------------
id
user_id
project_id
role
```

and perhaps:

```text
PROJECT_OWNER
PROJECT_ADMIN
PROJECT_MEMBER
```

This will fit beautifully with the permission system we discussed earlier.

---

# **27. A practical rulebook**

When designing JPA relationships, ask these questions in order:

### **Question 1**

What is the database relationship?

```text
1:1
1:N
N:M
```

### **Question 2**

Where is the foreign key?

That usually tells you which side owns the relationship.

### **Question 3**

Do I actually need navigation in both directions?

If not, don’t create a bidirectional relationship.

### **Question 4**

Should the relationship be lazy?

Usually start with lazy for associations and fetch what each use case needs.

### **Question 5**

Should persistence cascade?

Only if the lifecycle relationship makes sense.

### **Question 6**

Should deleting/removing the parent delete the child?

If yes, consider `orphanRemoval`/`REMOVE` based on the exact lifecycle semantics.

### **Question 7**

Could this produce N+1 queries?

Always keep this possibility in mind.

---
