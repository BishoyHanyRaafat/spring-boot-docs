import sys

file_path = sys.argv[1]
user_name = sys.argv[2]

with open(file_path, 'r') as f:
    content = f.read()

# Fix URL to be just the domain
content = content.replace(f"url: 'https://{user_name}.github.io/spring-boot-docs'", f"url: 'https://{user_name}.github.io'")

with open(file_path, 'w') as f:
    f.write(content)
