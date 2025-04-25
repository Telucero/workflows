import yaml
import os
import re
import requests
import json
import sys
from transform_tables import transform_html_tables_to_markdown

def load_config(config_path):
    """Load configuration from a JSON file"""
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_yaml(yaml_file):
    """Load YAML file"""
    with open(yaml_file, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)

# Configuration loading
def get_config_path(default_path, input_config_path):
    """Resolve the config file path, defaulting to the provided or default location"""
    config_path = input_config_path if input_config_path else default_path
    if not os.path.isabs(config_path):
        config_path = os.path.join(os.getcwd(), config_path)
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found at {config_path}")
    return config_path

def get_all_markdown_files(directory):
    """Recursively collect all markdown (.md, .mdx) files from subdirectories of the given directory"""
    results = []
    if not os.path.exists(directory):
        print(f"Docs directory not found: {directory}")
        return results

    for root, _, files in os.walk(directory):
        # Skip the root directory
        if root == directory:
            continue

        # Skip '.github' and other irrelevant folders
        if '.github' in root.split(os.sep) or 'node_modules' in root.split(os.sep) or 'venv' in root.split(os.sep):
            continue

        for file in files:
            if file.endswith(('.md', '.mdx')):
                results.append(os.path.join(root, file))

    # Sort the files to ensure consistent order
    results.sort()  # Sorting alphabetically
    return results

def build_index_section(files, docs_url, yaml_file):
    """Generate index section for the documentation"""
    section = "## List of doc pages:\n"
    for file in files:
        relative_path = os.path.relpath(file, docs_url)
        if '.snippets' in relative_path.split(os.sep):
            continue
        rel_path = os.path.relpath(file, docs_url)
        raw_url = f"{yaml_file['raw_base_url']}/{rel_path.replace(os.sep, '/')}"
        section += f"Doc-Page: {raw_url}\n"
    return section

def replace_snippet_placeholders(markdown, snippet_directory, yaml_data):
    """Replace snippet placeholders with their actual content"""
    def replacement(match):
        snippet_ref = match.group(1)
        # Handle local file or remote GitHub snippet
        if snippet_ref.startswith("http"):
            return fetch_remote_snippet(snippet_ref, yaml_data)
        else:
            return fetch_local_snippet(snippet_ref, snippet_directory)

    return re.sub(r"--8<--\s*['\"](https?://[^'\"]+|[^'\"]+)['\"]", replacement, markdown)

def fetch_local_snippet(snippet_ref, snippet_directory):
    """Fetch snippet from local directory"""
    file_only, line_start, line_end = parse_line_range(snippet_ref)
    absolute_snippet_path = os.path.join(snippet_directory, file_only)

    if not os.path.exists(absolute_snippet_path):
        print(f"Snippet file not found: {absolute_snippet_path}. Leaving placeholder unchanged.")
        return snippet_ref

    with open(absolute_snippet_path, 'r', encoding='utf-8') as snippet_file:
        snippet_content = snippet_file.read()
        snippet_content = transform_html_tables_to_markdown(snippet_content)  # Transform tables to markdown

    if line_start is not None and line_end is not None:
        lines = snippet_content.split('\n')
        snippet_content = '\n'.join(lines[line_start:line_end])

    return snippet_content.strip()

def fetch_remote_snippet(snippet_ref, yaml_data):
    """Fetch snippet from remote URL"""
    match = re.match(r'^(https?://[^:]+)(?::(\d+))?(?::(\d+))?$', snippet_ref)
    if not match:
        print(f"Invalid snippet reference format: {snippet_ref}")
        return f"Invalid snippet reference: {snippet_ref}"

    url = match.group(1)
    line_start = int(match.group(2)) if match.group(2) else None
    line_end = int(match.group(3)) if match.group(3) else None

    url = resolve_placeholders(url, yaml_data)  # resolve any template placeholders

    if "{{" in url:
        print(f"Skipping snippet with unresolved template: {url}")
        return f"Unresolved template: {url}"

    try:
        response = requests.get(url)
        response.raise_for_status()
        snippet_content = response.text

        if line_start is not None and line_end is not None:
            lines = snippet_content.split('\n')
            snippet_content = '\n'.join(lines[line_start-1:line_end])

        return snippet_content.strip()
    except requests.RequestException as e:
        print(f"Failed to fetch snippet from {url}: {e}")
        return f"Error fetching snippet from {url}"

def resolve_placeholders(text, data):
    """Resolve placeholders in text using values from YAML config"""
    while True:
        match = re.search(r'{{(.*?)}}', text)
        if not match:
            break
        key_path = match.group(1).strip()
        value = get_value_from_path(data, key_path)
        if value is None:
            print(f"Warning: Unresolved key path {key_path} in {text}")
            break
        text = text.replace(match.group(0), str(value))
    return text

def get_value_from_path(data, path):
    """Retrieve value from nested YAML data using dotted key path"""
    keys = path.split('.')
    value = data
    for key in keys:
        if key not in value:
            return None
        value = value[key]
    return value

def parse_line_range(snippet_path):
    """Parse the line range for snippet references (e.g. 'file.py:10:20')"""
    parts = snippet_path.split(':')
    file_only = parts[0]
    line_start = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
    line_end = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
    return file_only, line_start, line_end

def build_content_section(files, yaml_file):
    """Generate the content section for each markdown file"""
    section = "\n## Full content for each doc page\n\n"
    for file in files:
        relative_path = os.path.relpath(file, yaml_file['docs_url'])

        # Skip printing .snippets individually
        if '.snippets' in relative_path.split(os.sep):
            continue

        doc_url_path = re.sub(r'\.(md|mdx)$', '', relative_path)
        doc_url = f"{yaml_file['docs_url']}{doc_url_path}"

        # Remove trailing /index from doc_url
        if doc_url.endswith('/index'):
            doc_url = doc_url[:-6]

        with open(file, 'r', encoding='utf-8') as file_content:
            content = file_content.read()

        # Replace snippet placeholders
        content = replace_snippet_placeholders(content, yaml_file['snippet_dir'], yaml_file)

        section += f"Doc-Content: {doc_url}/\n"
        section += "--- BEGIN CONTENT ---\n"
        section += content.strip()
        section += "\n--- END CONTENT ---\n\n"

    return section

def generate_llms_structure_txt(files, docs_url, yaml_file):
    """Generate a simple llms.txt file with documentation structure"""
    structure_output = os.path.join(docs_url, 'llms.txt')
    
    structure_lines = [
        f"# {yaml_file['projectName']}",
        "", 
        f"> {yaml_file['projectDescription']}",
        "",  
        "## Docs",
        ""
    ]

    for file in files:
        if not os.path.exists(file) or '.snippets' in file:
            continue

        with open(file, 'r', encoding='utf-8') as f:
            content = f.read()

        metadata_match = re.search(r"---\n(.*?)\n---", content, re.DOTALL)
        if metadata_match:
            try:
                metadata_yaml = yaml.safe_load(metadata_match.group(1))
                title = metadata_yaml.get('title', 'Untitled')
                description = metadata_yaml.get('description', 'No description available.')
            except yaml.YAMLError:
                title = 'Untitled'
                description = 'No description available.'
        else:
            title = 'Untitled'
            description = 'No description available.'

        rel_path = os.path.relpath(file, docs_url)
        doc_url = f"{yaml_file['raw_base_url']}/{rel_path.replace(os.sep, '/')}"

        structure_lines.append(f"- [{title}]({doc_url}): {description}")

    with open(structure_output, 'w', encoding='utf-8') as f:
        f.write('\n'.join(structure_lines))

    print(f"[✓] Generated llms.txt at: {structure_output}")

def generate_standard_llms(docs_dir, yaml_file):
    """Generate the full llms.txt file and the llms-full.txt"""
    files = get_all_markdown_files(docs_dir)

    llms_content = f"# {yaml_file['projectName']} llms-full.txt\n"
    llms_content += f"{yaml_file['projectName']}. {yaml_file['projectDescription']}\n\n"
    llms_content += "## Generated automatically. Do not edit directly.\n\n"
    llms_content += f"Documentation: {yaml_file['docs_url']}\n\n"

    llms_content += build_index_section(files, yaml_file['docs_url'], yaml_file)
    llms_content += build_content_section(files, yaml_file)

    output_file = os.path.join(docs_dir, 'llms-full.txt')
    with open(output_file, 'w', encoding='utf-8') as output:
        output.write(llms_content)

    print(f"[✓] Generated llms-full.txt at: {output_file}")

    generate_llms_structure_txt(files, yaml_file['docs_url'], yaml_file)

if __name__ == "__main__":
    try:
        # Get paths from environment variables
        docs_path = sys.argv[1]  # Pass docs_path
        config_path = sys.argv[2]  # Pass config_path
        
        # Load config and YAML
        config = load_config(config_path)
        yaml_file = load_yaml(config['yaml_path'])

        # Generate the LLMS files
        generate_standard_llms(docs_path, yaml_file)
    
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
