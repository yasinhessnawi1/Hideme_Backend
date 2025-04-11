import json
import re
import os
import sys
from math import ceil

# Configuration
input_file = r"C:\Users\anwar\final_backend_2\data_generation\combined_data.jsonl"
output_dir = r"C:\Users\anwar\final_backend_2\data_generation\data_sanatizing"
num_chunks = 5
sample_file = os.path.join(output_dir, "verification_samples.jsonl")
stats_file = os.path.join(output_dir, "sanitization_stats.txt")

# Create output directory if it doesn't exist
if not os.path.exists(output_dir):
    os.makedirs(output_dir)
    print(f"Created output directory: {output_dir}")


def sanitize_text(text):
    """
    Sanitize text by removing unwanted characters while preserving reference patterns.

    1. Removes all slashes (/) except in reference patterns like "ref: 2023/456"
    2. Removes all backslashes (\)
    3. Removes all asterisks (*)
    """
    # Count characters before sanitization
    original_slash_count = text.count('/')
    original_backslash_count = text.count('\\')
    original_asterisk_count = text.count('*')

    # Protect reference patterns
    ref_pattern = r'(\b(?:ref|referanse)[:\s]+[A-Za-z0-9\-]+/[A-Za-z0-9\-/]+|\b\d{4}/\d+\b)'
    protected_text = re.sub(ref_pattern, lambda m: m.group(0).replace('/', '___PROTECTED_SLASH___'), text)

    # Remove all slashes and backslashes
    no_slashes = protected_text.replace('/', '')
    no_backslashes = no_slashes.replace('\\', '')

    # Remove all asterisks
    no_asterisks = no_backslashes.replace('*', '')

    # Restore protected reference patterns
    final_text = no_asterisks.replace('___PROTECTED_SLASH___', '/')

    # Count characters after sanitization
    final_slash_count = final_text.count('/')
    final_backslash_count = final_text.count('\\')
    final_asterisk_count = final_text.count('*')

    # Return the sanitized text and character removal statistics
    return final_text, {
        'removed_slashes': original_slash_count - final_slash_count,
        'removed_backslashes': original_backslash_count - final_backslash_count,
        'removed_asterisks': original_asterisk_count - final_asterisk_count
    }


def process_chunk(lines, chunk_id, total_stats):
    """Process a chunk of lines and write to a separate output file."""
    output_file = os.path.join(output_dir, f"sanatize_data{chunk_id}.jsonl")
    sample_records = []
    chunk_stats = {
        'removed_slashes': 0,
        'removed_backslashes': 0,
        'removed_asterisks': 0,
        'processed_lines': 0,
        'error_lines': 0
    }

    with open(output_file, 'w', encoding='utf-8') as outfile:
        for i, line in enumerate(lines):
            try:
                # Parse JSON
                data = json.loads(line.strip())

                # Clean text_input field
                if 'text_input' in data:
                    original_text = data['text_input']
                    sanitized_text, stats = sanitize_text(original_text)
                    data['text_input'] = sanitized_text

                    # Update statistics
                    for key in stats:
                        chunk_stats[key] += stats[key]

                    # Sample some records for verification
                    if i % max(1, len(lines) // 5) == 0:
                        sample_records.append({
                            'chunk': chunk_id,
                            'index': i,
                            'original': original_text,
                            'sanitized': sanitized_text
                        })

                # Write sanitized JSON
                outfile.write(json.dumps(data, ensure_ascii=False) + '\n')
                chunk_stats['processed_lines'] += 1

            except json.JSONDecodeError:
                outfile.write(line)  # Keep original if we can't parse it
                chunk_stats['error_lines'] += 1

    # Update total statistics
    for key in chunk_stats:
        if key in total_stats:
            total_stats[key] += chunk_stats[key]
        else:
            total_stats[key] = chunk_stats[key]

    print(f"Chunk {chunk_id}: Processed {chunk_stats['processed_lines']} lines, " +
          f"removed {chunk_stats['removed_slashes']} slashes, " +
          f"{chunk_stats['removed_backslashes']} backslashes, " +
          f"{chunk_stats['removed_asterisks']} asterisks")

    return sample_records


def write_sample_file(samples):
    """Write sample records to a verification file."""
    with open(sample_file, 'w', encoding='utf-8') as f:
        f.write("# SANITIZATION VERIFICATION SAMPLES\n")
        f.write("# This file contains examples of original and sanitized text for verification\n\n")

        for sample in samples:
            f.write(f"## Chunk {sample['chunk']}, Index {sample['index']}\n\n")
            f.write("### ORIGINAL TEXT:\n")
            f.write(sample['original'] + "\n\n")
            f.write("### SANITIZED TEXT:\n")
            f.write(sample['sanitized'] + "\n\n")
            f.write("-" * 80 + "\n\n")


def write_stats_file(stats):
    """Write sanitization statistics to a file."""
    with open(stats_file, 'w', encoding='utf-8') as f:
        f.write("# SANITIZATION STATISTICS\n\n")

        f.write("## PROCESSING SUMMARY\n")
        f.write(f"Total lines processed: {stats['processed_lines']}\n")
        f.write(f"Lines with errors: {stats['error_lines']}\n\n")

        f.write("## CHARACTER REMOVAL\n")
        f.write(f"Total slashes (/) removed: {stats['removed_slashes']}\n")
        f.write(f"Total backslashes (\\) removed: {stats['removed_backslashes']}\n")
        f.write(f"Total asterisks (*) removed: {stats['removed_asterisks']}\n")


# Main process
def main():
    try:
        print(f"Reading input file: {input_file}")
        with open(input_file, 'r', encoding='utf-8') as infile:
            all_lines = infile.readlines()

        total_lines = len(all_lines)
        print(f"Total lines to process: {total_lines}")

        # Calculate chunk sizes
        chunk_size = ceil(total_lines / num_chunks)
        chunks = []
        for i in range(num_chunks):
            start_idx = i * chunk_size
            end_idx = min((i + 1) * chunk_size, total_lines)
            chunks.append(all_lines[start_idx:end_idx])

        # Process each chunk
        all_samples = []
        total_stats = {}

        for i, chunk in enumerate(chunks):
            print(f"Processing chunk {i + 1}/{num_chunks} ({len(chunk)} lines)...")
            samples = process_chunk(chunk, i + 1, total_stats)
            all_samples.extend(samples)

        # Write verification files
        print(f"Writing verification samples to: {sample_file}")
        write_sample_file(all_samples)

        print(f"Writing statistics to: {stats_file}")
        write_stats_file(total_stats)

        print("\nSanitization Summary:")
        print(f"- Total lines processed: {total_stats['processed_lines']}")
        print(f"- Total characters removed:")
        print(f"  - Slashes (/): {total_stats['removed_slashes']}")
        print(f"  - Backslashes (\\): {total_stats['removed_backslashes']}")
        print(f"  - Asterisks (*): {total_stats['removed_asterisks']}")
        print(f"\nOutput files saved in: {output_dir}")
        print(f"Verification samples: {sample_file}")
        print(f"Statistics report: {stats_file}")

    except Exception as e:
        print(f"Error: {str(e)}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())