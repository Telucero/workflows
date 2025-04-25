import yaml
import os
import re
import requests
import json
from transform_tables import transform_html_tables_to_markdown

# Load configuration
config_path = os.path.join(os.path.dirname(__file__), 'llms_config.json')
with open(config_path, 'r', encoding='utf-8') as f:
    config = json.load(f)

PROJECT_NAME = config["projectName"]
PROJECT_URL = config["projectUrl"]
PROJECT_DESCRIPTION = config["projectDescription"]
RAW_BASE_URL = config["raw_base_url"]

# Define documentation structure
docs_repo = 'docs'  # Folder name where docs are stored
docs_url = 'https://example.com/docs/'  # Update to actual docs URL

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
docs_dir = os.path.join(base_dir, docs_repo)
yaml_path = os.path.join(base_dir, docs_repo, 'variables.yml')
output_file = os.path.join(docs_dir, 'llms-full.txt')
snippet_dir = os.path.join(docs_dir, '.snippets')
structure_output = os.path.join(docs_dir, 'llms.txt')

SNIPPET_REGEX = r"--8<--\s*['\"](https?://[^'\"]+|[^'\"]+)['\"]"

def get_all_markdown_files(directory):
    results = []
    for root, _, files in os.walk(directory):
        if root == directory or any(x in root for x in ['.github', 'node_modules', 'venv']):
            continue
        for file in files:
            if file.endswith(('.md', '.mdx')):
                results.append(os.path.join(root, file))
    return sorted(results)

def parse_line_range(snippet_path):
    parts = snippet_path.split(':')
    file = parts[0]
    line_start = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
    line_end = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
    return file, line_start, line_end

def fetch_local_snippet(snippet_ref, snippet_directory):
    file, start, end = parse_line_range(snippet_ref)
    snippet_path = os.path.join(snippet_directory, file)
    if not os.path.exists(snippet_path):
        return snippet_ref
    with open(snippet_path, 'r', encoding='utf-8') as f:
        content = f.read()
        content = transform_html_tables_to_markdown(content)
    if start is not None and end is not None:
        lines = content.split('\n')
        content = '\n'.join(lines[start:end])
    return content.strip()

def fetch_remote_snippet(snippet_ref, yaml_data):
    match = re.match(r'^(https?://[^:]+)(?::(\d+))?(?::(\d+))?$', snippet_ref)
    if not match:
        return f"Invalid snippet reference: {snippet_ref}"

    url = resolve_placeholders(match.group(1), yaml_data)
    if "{{" in url:
        return f"Unresolved template: {url}"

    try:
        response = requests.get(url)
        response.raise_for_status()
        content = response.text
        if match.group(2) and match.group(3):
            lines = content.split('\n')
            content = '\n'.join(lines[int(match.group(2))-1:int(match.group(3))])
        return content.strip()
    except Exception as e:
        return f"Error fetching snippet: {e}"

def resolve_placeholders(text, data):
    while True:
        match = re.search(r'{{(.*?)}}', text)
        if not match:
            break
        key_path = match.group(1).strip()
        value = get_value_from_path(data, key_path)
        if value is None:
            break
        text = text.replace(match.group(0), str(value))
    return text

def get_value_from_path(data, path):
    keys = path.split('.')
    for key in keys:
        data = data.get(key)
        if data is None:
            return None
    return data

def replace_snippets(markdown, snippet_dir, yaml_data):
    def repl(match):
        ref = match.group(1)
        return fetch_remote_snippet(ref, yaml_data) if ref.startswith("http") else fetch_local_snippet(ref, snippet_dir)
    return re.sub(SNIPPET_REGEX, repl, markdown)

def load_yaml(path):
    with open(path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)

def build_index(files):
    section = "## List of doc pages:\n"
    for file in files:
        rel_path = os.path.relpath(file, docs_dir)
        if '.snippets' not in rel_path:
            raw_url = f"{RAW_BASE_URL}/{rel_path.replace(os.sep, '/')}"
            section += f"Doc-Page: {raw_url}\n"
    return section

def build_content(files, yaml_data):
    section = "\n## Full content for each doc page\n\n"
    for file in files:
        rel_path = os.path.relpath(file, docs_dir)
        if '.snippets' in rel_path:
            continue
        doc_url = f"{docs_url}{re.sub(r'.(md|mdx)$', '', rel_path)}"
        if doc_url.endswith('/index'):
            doc_url = doc_url[:-6]
        with open(file, 'r', encoding='utf-8') as f:
            content = f.read()
        content = replace_snippets(content, snippet_dir, yaml_data)
        section += f"Doc-Content: {doc_url}/\n--- BEGIN CONTENT ---\n{content.strip()}\n--- END CONTENT ---\n\n"
    return section

def generate_structure_txt(files):
    lines = [
        f"# {PROJECT_NAME}",
        f"> {PROJECT_DESCRIPTION}",
        "## Docs", ""
    ]
    for file in files:
        if not os.path.exists(file) or '.snippets' in file:
            continue
        with open(file, 'r', encoding='utf-8') as f:
            content = f.read()
        metadata = re.search(r"---\n(.*?)\n---", content, re.DOTALL)
        if metadata:
            data = yaml.safe_load(metadata.group(1))
            title = data.get("title", "Untitled")
            desc = data.get("description", "No description available.")
        else:
            title, desc = "Untitled", "No description available."
        rel_path = os.path.relpath(file, docs_dir)
        doc_url = f"{RAW_BASE_URL}/{rel_path.replace(os.sep, '/')}"
        lines.append(f"- [{title}]({doc_url}): {desc}")
    with open(structure_output, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"[✓] Generated llms.txt at: {structure_output}")

def generate_standard_llms():
    files = get_all_markdown_files(docs_dir)
    yaml_data = load_yaml(yaml_path)
    output = f"# {PROJECT_NAME} llms-full.txt\n{PROJECT_DESCRIPTION}\n\n"
    output += "## Generated automatically. Do not edit directly.\n\n"
    output += f"Documentation: {docs_url}\n\n"
    output += build_index(files)
    output += build_content(files, yaml_data)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(output)
    print(f"[✓] Generated llms-full.txt at: {output_file}")
    generate_structure_txt(files)

if __name__ == "__main__":
    generate_standard_llms()
