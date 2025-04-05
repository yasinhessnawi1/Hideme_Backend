import os
import requests
import time
import json
from pathlib import Path

# Constants
PDF_DIR = r"C:\Users\anwar\final_backend_2\data_generation\data_for_evaluation\bekymeringsmeldinger"
API_ENDPOINT = "http://localhost:8000/ml/detect"
OUTPUT_FILE = "presidio_labeling.json"
REQUEST_DELAY = 4  # seconds
MAX_FILES = 100  # maximum number of files to process


def get_pdf_files(directory):
    """Get all PDF files from the specified directory."""
    pdf_files = []
    for filename in os.listdir(directory):
        if filename.lower().endswith('.pdf'):
            pdf_files.append(os.path.join(directory, filename))
    return pdf_files


def load_existing_results(output_file):
    """Load existing results from the output file if it exists."""
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading existing results: {str(e)}")
    return []


def get_processed_filenames(results):
    """Get a list of filenames that have already been processed."""
    return [result['filename'] for result in results]


def process_pdf_files(pdf_files, existing_results=None, max_files=MAX_FILES):
    """Process PDF files and send them to the API."""
    if existing_results is None:
        existing_results = []

    results = existing_results.copy()
    processed_filenames = get_processed_filenames(results)

    # Filter out already processed files
    pdf_files_to_process = [
        pdf_path for pdf_path in pdf_files
        if os.path.basename(pdf_path) not in processed_filenames
    ]

    # Limit to max_files total (including existing results)
    files_remaining = max_files - len(results)
    if files_remaining <= 0:
        print(f"Already processed {len(results)} files, which is at or above the limit of {max_files}.")
        return results

    pdf_files_to_process = pdf_files_to_process[:files_remaining]

    print(f"Processing {len(pdf_files_to_process)} new files, {len(results)} already processed.")

    for i, pdf_path in enumerate(pdf_files_to_process):
        print(f"Processing {i + 1}/{len(pdf_files_to_process)}: {os.path.basename(pdf_path)}")

        try:
            # Open the PDF file in binary mode
            with open(pdf_path, 'rb') as pdf_file:
                # Create a dictionary with the file
                files = {'file': (os.path.basename(pdf_path), pdf_file, 'application/pdf')}

                # Send the file to the API
                response = requests.post(API_ENDPOINT, files=files)

                # Check if the request was successful
                if response.status_code == 200:
                    # Add the result to our list
                    result = {
                        'filename': os.path.basename(pdf_path),
                        'path': pdf_path,
                        'response': response.json()
                    }
                    results.append(result)

                    # Save after each successful processing
                    save_results_to_json(results, OUTPUT_FILE)
                else:
                    print(f"Error processing {pdf_path}: {response.status_code} - {response.text}")

        except Exception as e:
            print(f"Exception processing {pdf_path}: {str(e)}")

        # Wait between requests to avoid rate limiting
        if i < len(pdf_files_to_process) - 1:  # Don't wait after the last file
            print(f"Waiting {REQUEST_DELAY} seconds before next request...")
            time.sleep(REQUEST_DELAY)

    return results


def save_results_to_json(results, output_file):
    """Save the results to a JSON file."""
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=4, ensure_ascii=False)
    print(f"Results saved to {output_file}")


def main():
    # Get all PDF files
    pdf_files = get_pdf_files(PDF_DIR)
    print(f"Found {len(pdf_files)} PDF files in {PDF_DIR}")

    # Load existing results if any
    existing_results = load_existing_results(OUTPUT_FILE)
    print(f"Loaded {len(existing_results)} existing results from {OUTPUT_FILE}")

    # Process the files
    results = process_pdf_files(pdf_files, existing_results)

    # Save the final results
    save_results_to_json(results, OUTPUT_FILE)
    print(f"Processed a total of {len(results)} files.")


if __name__ == "__main__":
    main()