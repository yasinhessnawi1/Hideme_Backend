"""
labeling_pipeline.py

A script to batch-process PDF files through multiple ML endpoints (Gemini, Presidio, Gliner, HideMe).
Reads configuration from a .env file, gathers to MAX_FILES PDFs from two directories,
and sends each PDF to each configured endpoint, saving results in separate JSON files.

Requirements:
    - python-dotenv
    - requests

Usage:
    python engines_labeling_pipeline.py for evaluation.
"""
import os
import time
import json
import requests
from dotenv import load_dotenv

# Load environment variables from .env

load_dotenv()

# Directories containing PDFs to process
PDF_DIR_1 = os.getenv("PDF_DIR_1")
PDF_DIR_2 = os.getenv("PDF_DIR_2")

# API endpoints for each service
API_ENDPOINTS = {
    "presidio": os.getenv("API_ENDPOINT_PRESIDIO"),
    "gemini": os.getenv("API_ENDPOINT_GEMINI"),
    "gliner": os.getenv("API_ENDPOINT_GLINER"),
    "hideme": os.getenv("API_ENDPOINT_HIDEME"),
}

# Output JSON filenames for each service
OUTPUT_FILES = {
    "gemini": os.getenv("OUTPUT_FILE_GEMINI"),
    "presidio": os.getenv("OUTPUT_FILE_PRESIDIO"),
    "gliner": os.getenv("OUTPUT_FILE_GLINER"),
    "hideme": os.getenv("OUTPUT_FILE_HIDEME"),
}

# Other parameters
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", 7))  # seconds between requests
MAX_FILES = int(os.getenv("MAX_FILES", 100))  # max PDFs to process in total
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # API key for Gemini service
THRESHOLD = float(os.getenv("THRESHOLD", "0.50"))  # The threshold of the detected entities.


def get_pdf_files(directory):  # pragma: no cover
    """
    Retrieve a sorted list of all PDF file paths in the given directory.

    Args:
        directory (str): Path to the directory containing PDF files.

    Returns:
        List[str]: Sorted list of full file paths for .pdf files.
    """
    try:
        files = sorted(os.listdir(directory))
    except FileNotFoundError:
        print(f"Directory not found: {directory}")
        return []

    return [
        os.path.join(directory, filename)
        for filename in files
        if filename.lower().endswith(".pdf")
    ]


def load_existing_results(output_file):
    """
    Load existing JSON results from disk to avoid re-processing.

    Args:
        output_file (str): Path to the JSON file.

    Returns:
        List[dict]: Previously saved results or empty list if none.
    """
    if not os.path.exists(output_file):
        return []

    try:
        with open(output_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"Failed to load existing results: {exc}")
        return []


def get_processed_filenames(results):
    """
    Extract the set of filenames already processed.

    Args:
        results (List[dict]): List of result entries with 'filename' keys.

    Returns:
        Set[str]: Filenames already processed.
    """
    return {entry.get("filename") for entry in results}


def save_results_to_json(results, output_file):
    """
    Write results to a JSON file (pretty-printed).

    Args:
        results (List[dict]): List of result entries.
        output_file (str): Path to the output JSON file.
    """
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=4, ensure_ascii=False)
        print(f"Saved {len(results)} records to {output_file}")
    except Exception as exc:
        print(f"Error saving results: {exc}")


def process_pdf_files(pdf_files, endpoint, output_file, api_key=None):
    """
    Process a list of PDF files by sending them to a specified API endpoint.
    Automatically retries PDF processing up to 3 times on HTTP 429 (rate limit) errors.

    Args:
        pdf_files (List[str]): List of full file paths to PDF documents.
        endpoint (str): The URL of the detection API endpoint.
        output_file (str): Path to the output JSON file for storing results.
        api_key (str, optional): Optional API key for the service.

    Returns:
        List[dict]: The full list of processed results including any newly added entries.
    """
    # Load previously processed results to avoid duplication
    results = load_existing_results(output_file)
    processed = get_processed_filenames(results)

    # Determine how many new PDFs can be processed based on MAX_FILES
    remaining_slots = MAX_FILES - len(results)
    to_do = [pdf for pdf in pdf_files if os.path.basename(pdf) not in processed]
    to_do = to_do[:remaining_slots]

    print(f"Endpoint '{endpoint}' -> {len(to_do)} new of {len(pdf_files)} total to process.")

    # Build headers including optional API key
    headers = {}
    if api_key:
        headers["X-API-KEY"] = api_key

    # Process each PDF file in sequence
    for idx, pdf_path in enumerate(to_do, start=1):
        filename = os.path.basename(pdf_path)
        print(f"  [{idx}/{len(to_do)}] {filename}")

        retries = 0  # Number of retry attempts
        success = False  # Flag to track success per file

        # Attempt to process the file up to 6 times if rate-limited
        while retries < 6 and not success:
            try:
                with open(pdf_path, "rb") as fd:
                    data = {"threshold": THRESHOLD}
                    response = requests.post(
                        endpoint,
                        headers=headers,
                        data=data,
                        files={"file": (filename, fd, "application/pdf")}
                    )

                # Successful request
                if response.status_code == 200:
                    results.append({
                        "filename": filename,
                        "response": response.json()
                    })
                    save_results_to_json(results, output_file)
                    success = True

                # Rate limited - wait and retry
                elif response.status_code == 429:
                    wait_time = 60
                    print(
                        f"    HTTP 429 Too Many Requests. Retrying in {wait_time} seconds... (Attempt {retries + 1}/6)")
                    retries += 1
                    time.sleep(wait_time)

                # ❌ Other non-retrievable error - skip file
                else:
                    print(f"    HTTP {response.status_code}: {response.text}")
                    break

            except Exception as exc:
                print(f"    Exception processing {filename}: {exc}")
                break  # Do not retry on local file or request errors

        # Optional delay between files to avoid hitting limits again
        if idx < len(to_do):
            time.sleep(REQUEST_DELAY)

    return results


def flatten_results(results):
    """
    Turn your nested results into a flat list of:
      {
        "filename": ...,
        "Page": ...,
        "sensitive": ...,
        "entity": ...
      }
    pulling the redaction_mapping out of entry["response"].
    """
    flat = []
    for entry in results:
        fn = entry["filename"]
        # dig into the JSON body returned by endpoint:
        redaction = entry.get("response", {}) \
            .get("redaction_mapping", {})
        pages = redaction.get("pages", [])
        for page in pages:
            pg = page.get("page")
            for hit in page.get("sensitive", []):
                flat.append({
                    "filename": fn,
                    "Page": str(pg),
                    "sensitive": hit["original_text"],
                    "entity": hit["entity_type"]
                })
    return flat


def main():
    """
    Main entry point: gather PDFs, then run each configured endpoint in sequence.
    """
    # Collect up to MAX_FILES PDFs from both directories
    pdfs1 = get_pdf_files(PDF_DIR_1)
    pdfs2 = get_pdf_files(PDF_DIR_2)
    all_pdfs = (pdfs1 + pdfs2)[:MAX_FILES]
    print(f"Total PDFs loaded: {len(all_pdfs)} (dir1={len(pdfs1)}, dir2={len(pdfs2)})")

    for service_name, endpoint in API_ENDPOINTS.items():
        output_file = OUTPUT_FILES[service_name]
        print(f"\n=== Service: {service_name.upper()} ===")

        # 1) process this service’s PDFs
        service_results = process_pdf_files(
            pdf_files=all_pdfs,
            endpoint=endpoint,
            output_file=output_file,
            api_key=GEMINI_API_KEY if service_name == "gemini" else None
        )

        # immediately flatten _just_ this service’s results
        flattened = flatten_results(service_results)

        # overwrite the configured OUTPUT_FILE_* with the flattened records
        with open(output_file, "w", encoding="utf-8") as fileout:
            json.dump(flattened, fileout, indent=2, ensure_ascii=False)
        print(f"Saved {len(flattened)} records to {output_file}")

    print("\nAll services completed.")


if __name__ == "__main__":
    main()
