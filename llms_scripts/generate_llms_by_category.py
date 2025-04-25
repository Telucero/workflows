import re
import os
import json
import argparse
import logging
import yaml  # For parsing YAML metadata (replace regex-based metadata extraction)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load configuration from llms_config.json
def load_config(config_file='llms_config.json'):
    """
    Load configuration from a JSON file
    """
    script_dir = os.path.dirname(__file__)
    config_path = os.path.join(script_dir, config_file)

    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

# Function to escape special characters in Markdown content
def escape_special_chars(text):
    """
    Escape characters that may interfere with Markdown formatting
    """
    return re.sub(r'([\\`*{}[\]()#+\-.!_>])', r'\\\1', text)

# Argument parsing for input and output directories
def parse_args():
    parser = argparse.ArgumentParser(description="Generate LLMS files from documentation.")
    parser.add_argument('--input', type=str, help="Path to the llms-full.txt file", default='docs/llms-full.txt')
    parser.add_argument('--output', type=str, help="Output directory for generated files", default='docs/llms-files')
    return parser.parse_args()

# Load config variables
config = load_config()

PROJECT_NAME = config["projectName"]
PROJECT_URL = config["projectUrl"]
RAW_BASE_URL = config["raw_base_url"]
PROJECT_DESCRIPTION = config["projectDescription"]
SECTION_PRIORITY = config["sectionPriority"]
AI_PROMPT_TEMPLATE = config["aiPromptTemplate"].format(PROJECT_NAME=PROJECT_NAME, PROJECT_URL=PROJECT_URL)
CATEGORIES = config.get("categories", [])
SHARED_CATEGORIES = config.get("sharedCategories", [])

# Get paths from arguments or defaults
args = parse_args()
llms_input_path = args.input
output_dir = args.output

os.makedirs(output_dir, exist_ok=True)  # Create the output directory if not exists

def infer_section_label(url, section_priority):
    """
    Returns which section label from section_priority is present in the URL path.
    """
    for section in section_priority:
        if f"/{section}/" in url:
            return section
    return "other"

def sort_key_by_section(index_line, section_priority):
    """
    Sorts doc pages by the order in `section_priority`.
    """
    match = re.search(r"\[type: (.+?)\]", index_line)
    if not match:
        return (len(section_priority), index_line)  # fallback
    section_label = match.group(1)
    try:
        i = section_priority.index(section_label)
        return (i, index_line)
    except ValueError:
        return (len(section_priority), index_line)

def extract_category(category, section_priority, shared_data=None): 
    """
    Extracts and writes a per-category LLMS file.
    """
    try:
        with open(llms_input_path, 'r', encoding='utf-8') as f: 
            llms = f.read() 

        blocks = re.findall(
            r"Doc-Content: (.*?)\n--- BEGIN CONTENT ---\n(.*?)\n--- END CONTENT ---", 
            llms, re.DOTALL
        )

        index_lines = [] 
        content_blocks = [] 

        for url, content in blocks: 
            metadata_match = re.search(r"---\n(.*?)\n---", content, re.DOTALL) 
            if not metadata_match:
                continue

            metadata = metadata_match.group(1)
            
            # Try parsing YAML metadata
            try:
                metadata_dict = yaml.safe_load(metadata)
            except yaml.YAMLError:
                logger.error(f"YAML parsing error in metadata for {url}")
                continue

            # Get categories from the metadata
            tags = [tag.strip().lower() for tag in metadata_dict.get("categories", "").split(',')] 

            if category.lower() in tags:
                section_label = infer_section_label(url, SECTION_PRIORITY)

                if "/docs/" in url:
                    rel_path = url.split("/docs/")[1].rstrip("/") + ".md"
                    raw_url = f"{RAW_BASE_URL}/{rel_path}"
                else:
                    raw_url = url

                index_lines.append(f"Doc-Page: {raw_url} [type: {section_label}]")
                content_blocks.append(f"Doc-Content: {url}\n--- BEGIN CONTENT ---\n{escape_special_chars(content.strip())}\n--- END CONTENT ---")

        if not content_blocks: 
            logger.warning(f"[!] Skipping {category} – no matching pages.")
            with open(os.path.join(output_dir, f"llms-{category.lower()}.txt"), 'w', encoding='utf-8') as f:
                f.write(f"# No documentation found for category {category}\n")
                f.write(f"No pages matched the category {category}.")
            return

        output_file = os.path.join(output_dir, f"llms-{category.lower()}.txt") 
        with open(output_file, 'w', encoding='utf-8') as f:

            f.write(f"# {PROJECT_NAME} Developer Documentation (LLMS Format)\n\n")
            f.write(f"This file contains documentation for {PROJECT_NAME} ({PROJECT_URL}). {PROJECT_DESCRIPTION}\n")
            f.write("It is intended for use with large language models (LLMs) to support developers.\n\n")

            if category.lower() in [sc['name'].lower() for sc in SHARED_CATEGORIES]:
                f.write(f"This file includes shared documentation for the category: {category}\n\n")
            else:
                f.write(f"This file includes documentation for the product: {category}\n\n")
                f.write(AI_PROMPT_TEMPLATE)
                f.write("\n")

            combined = list(zip(index_lines, content_blocks))
            combined.sort(key=lambda p: sort_key_by_section(p[0], SECTION_PRIORITY))
            sorted_index_lines, sorted_content_blocks = zip(*combined) if combined else ([], [])

            f.write(f"## List of doc pages:\n")
            f.write('\n'.join(sorted_index_lines))
            f.write("\n\n## Full content for each doc page\n\n")
            f.write('\n\n'.join(sorted_content_blocks))

            if shared_data and category.lower() not in [sc['name'].lower() for sc in SHARED_CATEGORIES]:
                for shared_cat_name, shared_cat_info in shared_data.items():
                    context_index = shared_cat_info["index"]
                    context_content = shared_cat_info["content"]
                    context_description = shared_cat_info["contextDescription"]

                    f.write(f"\n\n## Shared Concepts from '{shared_cat_name}'\n\n")
                    f.write(context_description)
                    f.write("\n---\n\n")
                    f.write("## List of shared concept pages:\n")
                    f.write(context_index + "\n\n")
                    f.write("## Full content for shared concepts:\n\n")
                    f.write(context_content)

        logger.info(f"[✓] Generated {output_file} with {len(content_blocks)} pages")

    except Exception as e:
        logger.error(f"Error generating LLMS for category {category}: {e}")

def generate_all_categories():
    """
    Generate LLMS files for shared categories and normal categories.
    """
    shared_data = {}

    for sc in SHARED_CATEGORIES:
        cat_name = sc["name"]
        cat_description = sc["contextDescription"].format(PROJECT_NAME=PROJECT_NAME)

        extract_category(cat_name, SECTION_PRIORITY)

        path = os.path.join(output_dir, f"llms-{cat_name.lower()}.txt")
        if not os.path.isfile(path):
            logger.warning(f"[!] Shared category file not found for {cat_name}: {path}")
            continue

        with open(path, 'r', encoding='utf-8') as f:
            raw = f.read()

        index_match = re.search(
            r"## List of doc pages:\n(.*?)\n+## Full content for each doc page",
            raw,
            re.DOTALL
        )
        index = index_match.group(1).strip() if index_match else ""

        blocks = re.findall(
            r"Doc-Content: (.*?)\n--- BEGIN CONTENT ---\n(.*?)\n--- END CONTENT ---",
            raw, re.DOTALL
        )

        content = ""
        for url, block in blocks:
            content += f"Doc-Content: {url}\n--- BEGIN CONTENT ---\n{block.strip()}\n--- END CONTENT ---\n\n"

        shared_data[cat_name.lower()] = {
            "index": index,
            "content": content.strip(),
            "contextDescription": cat_description
        }

    for cat in CATEGORIES:
        extract_category(cat, SECTION_PRIORITY, shared_data)

if __name__ == "__main__":
    generate_all_categories()
