"""
private_ai_labeling.py

A script to process PDF files with the Private AI API, featuring:

- **Environment-variable configuration** (via a .env file)
- **PDF text extraction** using pdfplumber
- **Text chunking** for large documents
- **Retry logic** with exponential backoff on errors
- **Progress saving** and resume support
- **Command-line execution** entry point

Configuration (.env) keys:

    API_KEY                Private AI API key (string)
    API_ENDPOINT           Private AI API URL (string)
    PDF_FOLDER_1           Path to the primary PDF directory (string)
    PDF_FOLDER_2           Path to the secondary PDF directory (string, unused placeholder)
    OUTPUT_FILE_1          JSON output path for folder 1 results (string)
    OUTPUT_FILE_2          JSON output path for folder 2 results (string, unused placeholder)
    NUM_FILES_TO_PROCESS   Maximum number of PDFs to process (int)
    MAX_TEXT_LENGTH        Maximum characters per API request chunk (int)
    RETRY_COUNT            Number of retry attempts per chunk (int)
    REQUEST_DELAY          Seconds to wait between requests (float)
    RETRY_DELAY_BASE       Base delay in seconds for exponential backoff (int)
    SAVE_PROGRESS_INTERVAL Number of files between progress saves (int)

Requirements:

    pip install python-dotenv pdfplumber requests tqdm

Usage:

    python private_ai_labeling.py
"""
# -----------------------------------------------------------
# Imports & Configuration
# -----------------------------------------------------------
import os
import json
import random
import time
import requests
import pdfplumber
from tqdm import tqdm
from dotenv import load_dotenv

# Load settings from .env into environment variables
load_dotenv()

# Read configuration values
API_KEY = os.getenv("API_KEY")
API_ENDPOINT = os.getenv("API_ENDPOINT")
PDF_FOLDER_1 = os.getenv("PDF_FOLDER_1")
PDF_FOLDER_2 = os.getenv("PDF_FOLDER_2")  # placeholder
OUTPUT_FILE_1 = os.getenv("OUTPUT_FILE_1")
OUTPUT_FILE_2 = os.getenv("OUTPUT_FILE_2")  # placeholder

# Parse numeric configurations with defaults
NUM_FILES_TO_PROCESS = int(os.getenv("NUM_FILES_TO_PROCESS", 50))
MAX_TEXT_LENGTH = int(os.getenv("MAX_TEXT_LENGTH", 50000))
RETRY_COUNT = int(os.getenv("RETRY_COUNT", 3))
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", 2))
RETRY_DELAY_BASE = int(os.getenv("RETRY_DELAY_BASE", 5))
SAVE_PROGRESS_INTERVAL = int(os.getenv("SAVE_PROGRESS_INTERVAL", 5))


def extract_text_from_pdf(pdf_path):
    """
    Extract all text from the given PDF file.

    Args:
        pdf_path (str): Full path to the PDF file.

    Returns:
        str: Combined text from all pages, or empty if extraction fails.
    """
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                content = page.extract_text()
                if content:
                    text += content + "\n"
    except Exception as e:
        print(f"Error extracting text from {pdf_path}: {e}")
    return text


def split_text(text, max_length=MAX_TEXT_LENGTH):
    """
    Split the given text into chunks of at most max_length characters.

    Args:
        text (str): The input text to split.
        max_length (int): Maximum chunk size in characters.

    Returns:
        List[str]: List of text chunks.
    """
    if len(text) <= max_length:
        return [text]
    return [text[i: i + max_length] for i in range(0, len(text), max_length)]


def process_text_chunk_with_retry(chunk, headers, retries=RETRY_COUNT):
    """
    Send a single text chunk to the API, retrying on failure with exponential backoff.

    Args:
        chunk (str): Text chunk to send.
        headers (dict): HTTP headers (including API key).
        retries (int): Maximum retry attempts.

    Returns:
        dict or list: Parsed JSON response, or None if all attempts fail.
    """
    for attempt in range(1, retries + 1):
        try:
            response = requests.post(API_ENDPOINT, headers=headers, json={"text": [chunk]})
            response.raise_for_status()
            time.sleep(REQUEST_DELAY)  # throttle
            return response.json()

        except requests.exceptions.HTTPError as e:
            status = getattr(e.response, 'status_code', 'unknown')
            print(f"HTTP Error {status} (attempt {attempt}/{retries})")
            wait = RETRY_DELAY_BASE * (2 ** (attempt - 1))
            print(f"Backing off {wait}s before retry...")
            time.sleep(wait)

        except Exception as e:
            print(f"Error on attempt {attempt}/{retries}: {e}")
            if attempt < retries:
                wait = RETRY_DELAY_BASE * (2 ** (attempt - 1))
                time.sleep(wait)
    print(f"All {retries} attempts failed for this chunk.")
    return None


def process_text_with_private_ai(text_chunks):
    """
    Process a list of text chunks sequentially and aggregate API results.

    Args:
        text_chunks (List[str]): Chunks to send.

    Returns:
        List: Flattened list of all returned results, or None if none succeeded.
    """
    headers = {"x-api-key": API_KEY}
    aggregated = []
    for idx, chunk in enumerate(text_chunks, start=1):
        print(f"Processing chunk {idx}/{len(text_chunks)} (len={len(chunk)})")
        if idx > 1:
            time.sleep(REQUEST_DELAY)
        result = process_text_chunk_with_retry(chunk, headers)
        if result:
            aggregated.extend(result)
        else:
            print(f"Chunk {idx} failed.")
    return aggregated or None


def save_progress(results, filename):
    """
    Save intermediate results to a JSON file.

    Args:
        results (List[dict]): Current result list.
        filename (str): Destination JSON path.
    """
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=4)
        print(f"Progress saved to {filename}")
    except Exception as e:
        print(f"Failed to save progress: {e}")


def main():
    """
    Drive the full workflow:
      1. Discover & optionally sample PDFs
      2. Resume from saved progress
      3. Extract, chunk, and send each PDF
      4. Periodically save results
    """
    # Discover PDF filenames
    filenames = [f for f in os.listdir(PDF_FOLDER_1) if f.lower().endswith('.pdf')]
    print(f"Found {len(filenames)} PDFs in {PDF_FOLDER_1}")

    # Random sample if too many
    if len(filenames) > NUM_FILES_TO_PROCESS:
        filenames = random.sample(filenames, NUM_FILES_TO_PROCESS)
    print(f"Processing {len(filenames)} files")

    # Load prior progress to skip completed
    results = []
    if os.path.exists(OUTPUT_FILE_1):
        try:
            with open(OUTPUT_FILE_1, 'r', encoding='utf-8') as f:
                results = json.load(f)
                completed = {r['filename'] for r in results}
                filenames = [fn for fn in filenames if fn not in completed]
                print(f"Resuming: {len(completed)} done, {len(filenames)} left")
        except Exception as e:
            print(f"Error loading existing progress: {e}")

    # Iterate over PDFs with progress bar
    for idx, filename in enumerate(tqdm(filenames, desc="Processing PDFs"), start=1):
        pdf_path = os.path.join(PDF_FOLDER_1, filename)
        print(f"\n[{idx}/{len(filenames)}] {filename}")
        if idx > 1:
            time.sleep(REQUEST_DELAY * 2)

        # Extract text
        text = extract_text_from_pdf(pdf_path)
        if not text:
            print(f"Skipping {filename}: no text extracted")
            continue

        # Chunk & send to API
        chunks = split_text(text)
        print(f"Split into {len(chunks)} chunk(s)")
        api_output = process_text_with_private_ai(chunks)
        if api_output:
            results.append({"filename": filename, "ai_results": api_output})

        # Save periodically
        if idx % SAVE_PROGRESS_INTERVAL == 0:
            save_progress(results, OUTPUT_FILE_1)

    # Final save
    save_progress(results, OUTPUT_FILE_1)
    print("Processing complete.")


if __name__ == '__main__':
    main()
