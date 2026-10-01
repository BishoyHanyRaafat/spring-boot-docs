import sys

file_path = sys.argv[1]
user_name = sys.argv[2]
repo_name = sys.argv[3]

with open(file_path, 'r') as f:
    content = f.read()

content = content.replace("url: 'https://your-docusaurus-site.example.com'", f"url: 'https://{user_name}.github.io/{repo_name}'")
content = content.replace("baseUrl: '/'", f"baseUrl: '/{repo_name}/'")
content = content.replace("organizationName: 'facebook'", f"organizationName: '{user_name}'")
content = content.replace("projectName: 'docusaurus'", f"projectName: '{repo_name}'")

with open(file_path, 'w') as f:
    f.write(content)
