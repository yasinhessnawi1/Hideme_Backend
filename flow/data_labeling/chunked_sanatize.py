import json
import re
import os
import glob
from pathlib import Path

# Configuration
input_dir = r"C:\Users\anwar\final_backend_2\data_generation\chunked_data"
output_dir = r"C:\Users\anwar\final_backend_2\data_generation\chunked_sanitized_data"


def sanitize_text(text):
    """
    Sanitize text according to specified rules:
    1. Remove all slashes except in reference patterns and N/A
    2. Remove all asterisks
    3. Remove all backslash-quote sequences
    """
    if not text:
        return text

    # Step 1: Protect patterns where slashes should be kept

    # Protect "Deres ref: ..." patterns
    ref_pattern1 = r'(Deres\s+ref:?\s*[A-Za-z0-9\-/]+)'
    protected_text = re.sub(ref_pattern1, lambda m: m.group(0).replace('/', '___PROTECTED_SLASH___'), text)

    # Protect "Vår ref: ..." patterns
    ref_pattern2 = r'(Vår\s+ref:?\s*[A-Za-z0-9\-/]+)'
    protected_text = re.sub(ref_pattern2, lambda m: m.group(0).replace('/', '___PROTECTED_SLASH___'), protected_text)

    # Protect "N/A" pattern
    na_pattern = r'\bN/A\b'
    protected_text = re.sub(na_pattern, 'N___PROTECTED_SLASH___A', protected_text)

    # Step 2: Remove unwanted characters

    # Remove all remaining slashes
    no_slashes = protected_text.replace('/', '')

    # Remove all asterisks
    no_asterisks = no_slashes.replace('*', '')

    # Remove all backslash-quote sequences
    no_backslash_quotes = no_asterisks.replace('\\"', '')

    # Remove all backslash-quote sequences
    no_backslash_quotes = no_asterisks.replace('\"', '')

    # Step 3: Restore protected patterns
    final_text = no_backslash_quotes.replace('___PROTECTED_SLASH___', '/')

    return final_text


def process_file(input_file, output_file):
    """Process a single JSONL file and create a sanitized version."""
    print(f"Processing {input_file}...")

    processed_count = 0
    error_count = 0

    with open(input_file, 'r', encoding='utf-8') as infile, open(output_file, 'w', encoding='utf-8') as outfile:
        for line_num, line in enumerate(infile, 1):
            try:
                # Parse the JSON object
                data = json.loads(line.strip())

                # Sanitize the text_input field if present
                if 'text_input' in data:
                    data['text_input'] = sanitize_text(data['text_input'])

                # Write the sanitized data to the output file
                outfile.write(json.dumps(data, ensure_ascii=False) + '\n')
                processed_count += 1

            except json.JSONDecodeError as e:
                print(f"Error parsing JSON at line {line_num} in {input_file}: {e}")
                # Write the original line to avoid data loss
                outfile.write(line)
                error_count += 1
            except Exception as e:
                print(f"Unexpected error at line {line_num} in {input_file}: {e}")
                # Write the original line to avoid data loss
                outfile.write(line)
                error_count += 1

    print(f"Completed {input_file}: Processed {processed_count} lines, encountered {error_count} errors")
    return processed_count, error_count


def main():
    """Process all chunk files in the input directory."""
    # Create output directory if it doesn't exist
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {output_dir}")

    # Get all chunk files
    chunk_files = sorted(glob.glob(os.path.join(input_dir, "chunk*.jsonl")))

    if not chunk_files:
        print(f"No chunk files found in {input_dir}")
        return

    print(f"Found {len(chunk_files)} chunk files to process")

    # Process each chunk file
    total_processed = 0
    total_errors = 0

    for input_file in chunk_files:
        # Determine the output filename
        base_name = os.path.basename(input_file)
        chunk_num = re.search(r'chunk(\d+)', base_name).group(1)
        output_file = os.path.join(output_dir, f"chunk{chunk_num}_sanitized.jsonl")

        # Process the file
        processed, errors = process_file(input_file, output_file)
        total_processed += processed
        total_errors += errors

    print("\nSanitization Summary:")
    print(f"Total processed lines: {total_processed}")
    print(f"Total errors: {total_errors}")
    print(f"All sanitized files saved to: {output_dir}")


if __name__ == "__main__":
    main()