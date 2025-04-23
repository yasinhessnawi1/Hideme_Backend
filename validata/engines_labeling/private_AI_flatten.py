"""
flatten_private_ai.py

Reads two Private-AI output JSON files (paths from .env),
extracts every detected entity into a flat list of records with:
    {
        "filename": "<PDF filename>",
        "Page":    "",                   # Private-AI doesn’t return page info
        "sensitive": "<the text span>",
        "entity":    "<the best_label>"
    }
and writes the combined list to `private_labeling_1.json`.
"""

import os
import json
from dotenv import load_dotenv

# Load environment variables from .env in this directory
# Expect OUTPUT_FILE_1 and OUTPUT_FILE_2 to point at your two Private-AI JSONs

load_dotenv()
INPUT_FILES = [
    os.getenv("OUTPUT_FILE_1"),
    os.getenv("OUTPUT_FILE_2"),
]
if not all(INPUT_FILES):
    raise RuntimeError("ERROR: Please set OUTPUT_FILE_1 and OUTPUT_FILE_2 in your .env")

# Path for our merged, flattened output
OUTPUT_FILE = "private_labeling_1.json"


def flatten_private_ai(json_path):
    """
    Given one Private-AI JSON file, return a list of flat records:
      filename   – comes from the top-level "filename" key
      Page       – Private-AI doesn’t provide pages, so always ""
      sensitive  – the raw "text" of each entity.
      entity     – the corresponding "best_label"
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Ensure we have a list at top level
    docs = data if isinstance(data, list) else [data]
    flat = []

    for doc in docs:
        # Get the source PDFs filename
        pdf_name = doc.get("filename", os.path.splitext(os.path.basename(json_path))[0])

        # Each doc may have multiple ai_results entries
        for result in doc.get("ai_results", []):
            # Within each ai_result, look at each entity
            for ent in result.get("entities", []):
                flat.append({
                    "filename":  pdf_name,
                    "Page":      "",  # no page info in Private-AI output
                    "sensitive": ent.get("text", ""),
                    "entity":    ent.get("best_label", "")
                })

    return flat


def main():
    """
    Main entry point: gather PDFs, then run each configured in sequence.
    """
    all_hits = []

    # Process each input file in turn
    for path in INPUT_FILES:
        if not os.path.exists(path):
            print(f" Warning: file not found: {path}")
            continue

        hits = flatten_private_ai(path)
        print(f"→ Extracted {len(hits)} entities from {os.path.basename(path)}")
        all_hits.extend(hits)

    # Write merged output
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out_f:
        json.dump(all_hits, out_f, indent=2, ensure_ascii=False)

    print(f" Wrote {len(all_hits)} total records to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
