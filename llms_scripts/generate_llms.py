import sys
import os
import json
from generate_llms_standard import generate_standard_llms, load_yaml
from generate_llms_by_category import generate_all_categories

def main():
    # Parse command-line arguments
    if len(sys.argv) != 5:
        print("Usage: python generate_llms.py --docs_path <docs_path> --config_path <config_path>")
        sys.exit(1)

    docs_path = None
    config_path = None
    args = sys.argv[1:]
    for i in range(0, len(args), 2):
        if args[i] == "--docs_path":
            docs_path = args[i + 1]
        elif args[i] == "--config_path":
            config_path = args[i + 1]

    if not docs_path or not config_path:
        print("Missing required arguments: --docs_path or --config_path")
        sys.exit(1)

    # Load YAML config from path
    yaml_file = load_yaml(config_path)

    # ✅ Run Standard Generator
    generate_standard_llms(docs_path, yaml_file)

    # ✅ Run Category Generator
    generate_all_categories()

if __name__ == "__main__":
    main()
