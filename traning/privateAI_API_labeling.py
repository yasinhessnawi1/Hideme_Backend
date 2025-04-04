import os
import json
import requests
import random
import time
import pdfplumber  # For extracting text from PDFs
from tqdm import tqdm  # For progress tracking

# Configuration
API_KEY = "c368fa8f9e1648ce8162cf19c3f90cff"
API_ENDPOINT = "https://api.private-ai.com/community/v4/process/text"
PDF_FOLDER = r"C:\Users\anwar\final_backend_2\data_generation\data_for_evaluation\bekymeringsmeldinger"
OUTPUT_FILE = "private_AI_labeling_2.json"
NUM_FILES_TO_PROCESS = 50  # Number of files to process (set to None to process all)
MAX_TEXT_LENGTH = 50000  # Maximum text length to send in a single request
RETRY_COUNT = 3  # Number of retries for API requests
REQUEST_DELAY = 2  # Seconds to wait between API requests
RETRY_DELAY_BASE = 5  # Base seconds to wait when retrying (will increase with exponential backoff)
SAVE_PROGRESS_INTERVAL = 5  # Save progress to file after every N files


def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file using pdfplumber."""
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text
    except Exception as e:
        print(f"Error extracting text from {pdf_path}: {e}")
        return ""


def split_text(text, max_length=MAX_TEXT_LENGTH):
    """Split text into chunks of max_length characters if needed."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    for i in range(0, len(text), max_length):
        chunks.append(text[i:i + max_length])
    return chunks


def process_text_chunk_with_retry(chunk, headers, retries=RETRY_COUNT):
    """Process a text chunk with retry logic."""
    for attempt in range(retries):
        try:
            payload = {"text": [chunk]}
            response = requests.post(API_ENDPOINT, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()

            # Add delay between successful requests to avoid rate limiting
            time.sleep(REQUEST_DELAY)
            return result

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if hasattr(e, 'response') else "unknown"
            print(f"HTTP Error (Attempt {attempt + 1}/{retries}): {e} (Status code: {status_code})")

            if hasattr(e, 'response') and e.response:
                print(f"Response: {e.response.text}")

            # If we've reached max retries, give up
            if attempt + 1 >= retries:
                print(f"Max retries reached for chunk of length {len(chunk)}")
                return None

            # For rate limiting (429), use a longer delay
            if status_code == 429:
                wait_time = RETRY_DELAY_BASE * (2 ** attempt)
                print(f"Rate limit exceeded. Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            else:
                # Normal backoff for other errors
                wait_time = RETRY_DELAY_BASE * (2 ** attempt)
                print(f"Error occurred. Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)

        except Exception as e:
            print(f"Unexpected error (Attempt {attempt + 1}/{retries}): {e}")

            # If we've reached max retries, give up
            if attempt + 1 >= retries:
                return None

            # Wait before retrying
            wait_time = RETRY_DELAY_BASE * (2 ** attempt)
            print(f"Waiting {wait_time} seconds before retry...")
            time.sleep(wait_time)

    return None


def process_text_with_private_ai(text_chunks):
    """Process text using Private AI API, handling large texts by splitting them."""
    headers = {"x-api-key": API_KEY}
    all_results = []

    for i, chunk in enumerate(text_chunks):
        print(f"Processing chunk {i + 1}/{len(text_chunks)}, length: {len(chunk)}")

        # Add delay before processing each chunk to avoid hitting rate limits
        if i > 0:
            print(f"Waiting {REQUEST_DELAY} seconds before processing next chunk...")
            time.sleep(REQUEST_DELAY)

        result = process_text_chunk_with_retry(chunk, headers)

        if result:
            all_results.extend(result)
            print(f"Successfully processed chunk {i + 1}")
        else:
            print(f"Failed to process chunk {i + 1}")

    return all_results if all_results else None


def save_progress(results, filename=OUTPUT_FILE):
    """Save current progress to a JSON file."""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
    print(f"Progress saved to {filename}")


def main():
    # Get list of PDF files
    try:
        pdf_files = [f for f in os.listdir(PDF_FOLDER) if f.lower().endswith('.pdf')]
        print(f"Found {len(pdf_files)} PDF files in the folder")

        # If there are more than the specified number of files, randomly select
        if len(pdf_files) > NUM_FILES_TO_PROCESS:
            pdf_files = random.sample(pdf_files, NUM_FILES_TO_PROCESS)
            print(f"Randomly selected {NUM_FILES_TO_PROCESS} files for processing")

        results = []

        # Try to load existing progress if available
        try:
            if os.path.exists(OUTPUT_FILE):
                with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                    results = json.load(f)
                    processed_files = [item["filename"] for item in results]
                    print(f"Loaded existing progress with {len(processed_files)} processed files")

                    # Filter out already processed files
                    pdf_files = [f for f in pdf_files if f not in processed_files]
                    print(f"Remaining files to process: {len(pdf_files)}")
        except Exception as e:
            print(f"Could not load existing progress: {e}")
            results = []

        # Process each PDF file with progress tracking
        for i, pdf_file in enumerate(tqdm(pdf_files, desc="Processing PDF files")):
            pdf_path = os.path.join(PDF_FOLDER, pdf_file)
            print(f"\nProcessing file {i + 1}/{len(pdf_files)}: {pdf_file}")

            # Add delay between files to avoid hitting rate limits
            if i > 0:
                wait_time = REQUEST_DELAY * 2
                print(f"Waiting {wait_time} seconds before processing next file...")
                time.sleep(wait_time)

            # Extract text from PDF
            text = extract_text_from_pdf(pdf_path)

            if text:
                print(f"Successfully extracted text: {len(text)} characters")

                # Split text if it's too large
                text_chunks = split_text(text)
                print(f"Split into {len(text_chunks)} chunks")

                # Process text with Private AI
                ai_results = process_text_with_private_ai(text_chunks)

                if ai_results:
                    # Store results with filename for reference
                    results.append({
                        "filename": pdf_file,
                        "ai_results": ai_results
                    })
                    print(f"Successfully processed and saved results for {pdf_file}")
                else:
                    print(f"No AI results obtained for {pdf_file}")
            else:
                print(f"No text extracted from {pdf_file}")

            # Save progress periodically
            if (i + 1) % SAVE_PROGRESS_INTERVAL == 0:
                save_progress(results)

        # Save final results to JSON file
        save_progress(results)
        print(f"Processing complete. All results saved to {OUTPUT_FILE}")

    except Exception as e:
        print(f"An error occurred during execution: {e}")
        # Try to save any partial results
        if results:
            save_progress(results, f"partial_{OUTPUT_FILE}")
            print(f"Partial results saved to partial_{OUTPUT_FILE}")


if __name__ == "__main__":
    main()