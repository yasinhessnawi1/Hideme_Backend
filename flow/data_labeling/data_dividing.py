import os
import math
import json

# Configuration
input_file = r"C:\Users\anwar\final_backend_2\data_generation\combined_data.jsonl"
output_dir = r"C:\Users\anwar\final_backend_2\data_generation\chunked_data"
num_chunks = 10


def create_chunks():
    """
    Divides a JSONL file into a specified number of equal-sized chunks.
    Each JSON object (line) is kept intact in a single chunk.
    """
    # Create output directory if it doesn't exist
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created output directory: {output_dir}")

    # Count total lines in the input file
    print(f"Counting lines in {input_file}...")
    total_lines = 0
    with open(input_file, 'r', encoding='utf-8') as infile:
        for _ in infile:
            total_lines += 1

    print(f"Total lines to process: {total_lines}")

    # Calculate lines per chunk (rounded up to ensure all lines are included)
    lines_per_chunk = math.ceil(total_lines / num_chunks)
    print(f"Lines per chunk: {lines_per_chunk}")

    # Process the file in chunks
    with open(input_file, 'r', encoding='utf-8') as infile:
        for chunk_idx in range(num_chunks):
            chunk_file = os.path.join(output_dir, f"chunk{chunk_idx + 1}.jsonl")
            print(f"Creating {chunk_file}...")

            # Calculate the start and end line for this chunk
            start_line = chunk_idx * lines_per_chunk
            end_line = min((chunk_idx + 1) * lines_per_chunk, total_lines)
            lines_to_write = end_line - start_line

            # Skip to the start line
            infile.seek(0)
            for _ in range(start_line):
                next(infile)

            # Write the chunk
            with open(chunk_file, 'w', encoding='utf-8') as outfile:
                for _ in range(lines_to_write):
                    try:
                        line = next(infile)
                        # Validate that the line contains valid JSON (optional check)
                        json.loads(line.strip())
                        outfile.write(line)
                    except StopIteration:
                        # End of file reached
                        break
                    except json.JSONDecodeError:
                        # Invalid JSON, but we'll include it anyway as requested
                        outfile.write(line)

            print(f"Wrote {lines_to_write} lines to chunk{chunk_idx + 1}.jsonl")

    print("\nChunking complete. Summary:")
    for chunk_idx in range(num_chunks):
        chunk_file = os.path.join(output_dir, f"chunk{chunk_idx + 1}.jsonl")
        file_size = os.path.getsize(chunk_file) / (1024 * 1024)  # Size in MB
        print(f"  chunk{chunk_idx + 1}.jsonl: {file_size:.2f} MB")


if __name__ == "__main__":
    try:
        print("Starting file chunking process...")
        create_chunks()
        print(f"\nAll chunks created successfully in {output_dir}")
    except Exception as e:
        print(f"Error: {str(e)}")