"""
BatchSearchService Module

This module provides the BatchSearchService class that facilitates batch processing for text search across
multiple PDF files. It validates and reads PDF files, extracts text using PDFTextExtractor in parallel,
searches for specified terms within the extracted data using PDFSearcher, and returns a summary of results.
SecurityAwareErrorHandler is used throughout to securely handle and log errors.
"""

import time
import uuid
from typing import List, Dict, Any, Optional, Tuple, Union

from fastapi import UploadFile

# Import custom modules for PDF extraction/search, logging, memory monitoring, file validation, and secure error handling.
from backend.app.document_processing.pdf_extractor import PDFTextExtractor
from backend.app.document_processing.pdf_searcher import PDFSearcher
from backend.app.utils.logging.logger import log_info, log_error
from backend.app.utils.logging.secure_logging import log_batch_operation
from backend.app.utils.system_utils.memory_management import memory_monitor
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.validation.file_validation import read_and_validate_file, MAX_FILES_COUNT
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler


class BatchSearchService:
    """
    BatchSearchService Class

    This class supports batch text search across multiple PDF files. It first validates and reads the
    provided files, then extracts text in parallel using PDFTextExtractor. After text extraction,
    it searches for the specified search terms in each file using PDFSearcher. The service aggregates
    results and performance metrics, logs the batch operation, and handles errors securely using
    SecurityAwareErrorHandler.
    """

    @staticmethod
    async def batch_search_text(
            files: List[UploadFile],
            search_terms: Union[str, List[str]],
            max_parallel_files: Optional[int] = None,
            case_sensitive: bool = False,
            ai_search: bool = False
    ) -> Dict[str, Any]:
        """
        Extract text from multiple PDF files and search for the specified terms.

        This method performs the following steps:
        1. Validates the number of files and logs the start of the batch search operation.
        2. Parses the provided search terms into a list.
        3. Reads and validates each file for extraction.
        4. Extracts text from the valid PDF files in parallel.
        5. Processes each file's extraction result by searching for the specified terms.
        6. Aggregates results, logs performance metrics, and returns a batch summary along with detailed file results.

        Args:
            files: A list of PDF files to process.
            search_terms: A string or list of strings representing the terms to search for.
            max_parallel_files: Optional maximum number of files to process in parallel. Defaults to 4.
            case_sensitive: Whether the search should be case-sensitive.
            ai_search: Whether to use AI-powered search enhancements.

        Returns:
            A dictionary containing:
                - batch_summary: Summary information for the batch operation.
                - file_results: List of dictionaries with individual file results.
                - _debug: Debug information including memory statistics and the batch operation ID.
        """
        start_time = time.time()
        batch_id = f"search-{str(uuid.uuid4())}"
        log_info(f"Starting batch text search (Batch ID: {batch_id})")

        # Check if the number of files exceeds the allowed maximum.
        if len(files) > MAX_FILES_COUNT:
            error_message = f"Too many files uploaded. Maximum allowed is {MAX_FILES_COUNT}."
            log_error(f"[SECURITY] {error_message} [operation_id={batch_id}]")
            # Optionally, you can also call SecurityAwareErrorHandler here if needed.
            return {"detail": error_message, "operation_id": batch_id}

        # Determine the optimal number of workers for parallel processing.
        optimal_workers = max_parallel_files if max_parallel_files is not None else 4

        # Parse the search terms into a list of clean words.
        search_words = BatchSearchService._parse_search_words(search_terms)

        # Read and validate files. Returns both file contents and metadata.
        pdf_files, file_metadata = await BatchSearchService._read_files_for_extraction(files, batch_id)

        # Filter out invalid files.
        valid_pdf_files = [content for content in pdf_files if content is not None]
        if not valid_pdf_files:
            return {
                "batch_summary": {
                    "batch_id": batch_id,
                    "total_files": len(files),
                    "successful": 0,
                    "failed": len(files),
                    "total_matches": 0,
                    "search_term": ", ".join(search_words),
                    "query_time": round(time.time() - start_time, 2)
                },
                "file_results": [],
                "_debug": {
                    "memory_usage": memory_monitor.get_memory_stats().get("current_usage"),
                    "peak_memory": memory_monitor.get_memory_stats().get("peak_usage"),
                    "operation_id": batch_id
                }
            }

        # Extract text from valid PDF files using parallel extraction.
        extraction_results = await PDFTextExtractor.extract_batch_text(valid_pdf_files, max_workers=optimal_workers)
        # Map each valid file index to its extraction result.
        extraction_map = {idx: result for idx, result in extraction_results}

        file_results: List[Dict[str, Any]] = []
        successful = 0
        failed = 0
        total_matches = 0
        valid_count = 0  # To align valid files with extraction_map indices

        # Process each file's result using the file metadata.
        for i, metadata in enumerate(file_metadata):
            # If file validation failed, log and record an error result.
            if metadata.get("status") == "error":
                file_results.append({
                    "file": metadata.get("original_name"),
                    "status": "error",
                    "error": metadata.get("error", "File validation failed.")
                })
                failed += 1
                continue

            # Get the extraction result corresponding to this valid file.
            extraction_result = extraction_map.get(valid_count)
            valid_count += 1

            try:
                # Process the search result for a single file.
                result_data, success_flag, fail_flag, match_count = await BatchSearchService._process_single_file_result(
                    metadata, extraction_result, search_words, case_sensitive, ai_search
                )
                file_results.append(result_data)
                successful += success_flag
                failed += fail_flag
                total_matches += match_count
            except Exception as e:
                # In case of unexpected errors, log the error securely.
                log_error(
                    f"[SECURITY] Error processing file {metadata.get('original_name')}: {str(e)} [operation_id={batch_id}]")
                file_results.append({
                    "file": metadata.get("original_name", f"file_{i}"),
                    "status": "error",
                    "error": f"Unhandled processing error: {str(e)}"
                })
                failed += 1

        query_time = time.time() - start_time
        batch_summary = {
            "batch_id": batch_id,
            "total_files": len(files),
            "successful": successful,
            "failed": failed,
            "total_matches": total_matches,
            "search_term": ", ".join(search_words),
            "query_time": round(query_time, 2)
        }
        log_batch_operation("Batch Text Search", len(files), successful, query_time)

        # Record processing details for compliance and audit.
        record_keeper.record_processing(
            operation_type="batch_text_search",
            document_type="multiple_files",
            entity_types_processed=search_words,
            processing_time=query_time,
            file_count=len(files),
            entity_count=total_matches,
            success=(successful > 0)
        )

        # Retrieve memory usage statistics for debugging.
        mem_stats = memory_monitor.get_memory_stats()
        response = {
            "batch_summary": batch_summary,
            "file_results": file_results,
            "_debug": {
                "memory_usage": mem_stats.get("current_usage"),
                "peak_memory": mem_stats.get("peak_usage"),
                "operation_id": batch_id
            }
        }
        return response

    @staticmethod
    async def _read_files_for_extraction(files: List[UploadFile], operation_id: str) -> Tuple[
        List[Optional[bytes]], List[Dict[str, Any]]]:
        """
        Reads and validates a list of files for text extraction.

        This method iterates over each file, attempts to read and validate it using a utility.
        For files that fail validation, an error is logged securely using SecurityAwareErrorHandler,
        and the error message is recorded. It returns a tuple containing the list of file contents (or None)
        and a list of corresponding file metadata.

        Args:
            files: A list of UploadFile objects.
            operation_id: A unique identifier for the batch operation.

        Returns:
            A tuple:
                - List of file contents (bytes) or None for files that failed validation.
                - List of dictionaries with metadata and status for each file.
        """
        pdf_files: List[Optional[bytes]] = []
        file_metadata: List[Dict[str, Any]] = []
        for i, file in enumerate(files):
            try:
                content, error_response, read_time = await read_and_validate_file(file, operation_id)
                if error_response:
                    log_error(f"[SECURITY] Validation failed for file {file.filename} [operation_id={operation_id}]")
                    pdf_files.append(None)
                    # Use SecurityAwareErrorHandler to create a secure error message
                    error_info= SecurityAwareErrorHandler.handle_safe_error(
                        Exception("File validation error"), "file_validation", file.filename
                    )
                    file_metadata.append({
                        "original_name": file.filename or f"file_{i}",
                        "content_type": file.content_type or "application/octet-stream",
                        "size": 0,
                        "read_time": read_time,
                        "status": "error",
                        "error": error_info.get("error", "File validation failed")
                    })
                else:
                    pdf_files.append(content)
                    file_metadata.append({
                        "original_name": file.filename or f"file_{i}.pdf",
                        "content_type": file.content_type or "application/octet-stream",
                        "size": len(content),
                        "read_time": read_time,
                        "status": "success"
                    })
            except Exception as e:
                # Handle unexpected exceptions using SecurityAwareErrorHandler for secure logging.
                log_error(f"[SECURITY] Exception reading file {file.filename}: {str(e)} [operation_id={operation_id}]")
                error_info = SecurityAwareErrorHandler.handle_safe_error(e, "file_read",file.filename)
                pdf_files.append(None)
                file_metadata.append({
                    "original_name": file.filename or f"file_{i}",
                    "content_type": "unknown",
                    "size": 0,
                    "read_time": 0,
                    "status": "error",
                    "error": error_info.get("error", str(e))
                })
        return pdf_files, file_metadata

    @staticmethod
    def _parse_search_words(search_words: Union[str, List[str]]) -> List[str]:
        """
        Parses the search_words parameter into a list of clean words/phrases.

        This helper function trims whitespace and, if provided as a string,
        splits it into individual words. It also removes enclosing quotes if present.

        Args:
            search_words: A string or list of strings representing search terms.

        Returns:
            A list of cleaned search words.
        """

        def clean(word: str) -> str:
            return word.strip()

        if isinstance(search_words, list):
            return [clean(word) for word in search_words if clean(word)]
        s = search_words.strip()
        # Remove surrounding quotes if present.
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            s = s[1:-1].strip()
        return [w.strip() for w in s.split() if w.strip()]

    @staticmethod
    async def _process_single_file_result(
            metadata: Dict[str, Any],
            extraction_result: Any,
            search_words: List[str],
            case_sensitive: bool,
            ai_search: bool
    ) -> Tuple[Dict[str, Any], int, int, int]:
        """
        Processes the extraction result for a single file by searching for the given terms.

        This method checks for extraction errors, and if valid, it instantiates PDFSearcher to search
        for the search terms within the extracted data. It returns a tuple containing:
            - A result dictionary with file name and search results.
            - A success flag (1 if successful, 0 otherwise).
            - A failure flag (1 if processing failed, 0 otherwise).
            - The number of matches found.

        Args:
            metadata: Dictionary containing file metadata.
            extraction_result: The text extraction result for the file.
            search_words: List of search terms to look for.
            case_sensitive: Whether the search should be case-sensitive.
            ai_search: Whether to use AI-powered search enhancements.

        Returns:
            A tuple of (result dictionary, success flag, failure flag, match count).
        """
        # Check if the extraction result indicates an error.
        if extraction_result is None or (isinstance(extraction_result, dict) and "error" in extraction_result):
            return ({
                        "file": metadata["original_name"],
                        "status": "error",
                        "error": extraction_result.get("error",
                                                       "Extraction failed") if extraction_result else "Extraction missing"
                    }, 0, 1, 0)
        try:
            # Initialize PDFSearcher with the extracted data.
            searcher = PDFSearcher(extraction_result)
            # Perform the search asynchronously.
            search_result = await searcher.search_terms(search_words, case_sensitive=case_sensitive,
                                                        ai_search=ai_search)
            return ({
                        "file": metadata["original_name"],
                        "status": "success",
                        "results": search_result
                    }, 1, 0, search_result.get("match_count", 0))
        except Exception as e:
            # Log the error securely using SecurityAwareErrorHandler.
            log_error(f"[SECURITY] Error searching file {metadata.get('original_name')}: {str(e)}")
            return ({
                        "file": metadata["original_name"],
                        "status": "error",
                        "error": f"Error during search: {str(e)}"
                    }, 0, 1, 0)

    @staticmethod
    async def find_words_by_bbox(
            files: List[UploadFile],
            bounding_box: Dict[str, float],
            operation_id: str
    ) -> Dict[str, Any]:
        """
        Process a batch of PDF files to find all occurrences of the word(s) that appear
        within a specified bounding box.

        For each file, the method:
          1. Reads and validates the PDF file.
          2. Extracts the text content.
          3. Instantiates PDFSearcher with the extracted data.
          4. Calls the PDFSearcher method (e.g. `find_target_phrase_occurrences_by_page`)
             to obtain a result dict that includes:
                 - "pages": a list of dictionaries containing page number and its matches.
                 - "word_count": the number of words in the candidate phrase.
             and the overall match count.
          5. Aggregates the result for each file.

        Returns a dictionary containing:
          - "batch_summary": Summary information for the batch operation.
          - "file_results": List of dictionaries for each file.
          - "_debug": Debug information including memory statistics and the operation ID.
        """
        # Record the start time of the batch process for performance measurement.
        start_time = time.time()

        # Initialize an empty list to collect results for each file.
        file_results: List[Dict[str, Any]] = []

        # Counters for tracking successful and failed file operations, as well as total matches.
        successful = 0
        failed = 0
        total_matches = 0

        # Try to read and validate the PDF files using the helper method for extraction.
        try:
            pdf_files, file_metadata = await BatchSearchService._read_files_for_extraction(files, operation_id)
        except Exception as e:
            # Log the error if file reading fails and return an early error response.
            log_error(f"[SECURITY] Error reading files in find_words_by_bbox: {str(e)} [operation_id={operation_id}]")
            return {"detail": "Error reading files", "operation_id": operation_id}

        # Process each file along with its corresponding metadata.
        for idx, meta in enumerate(file_metadata):
            try:
                # Retrieve the original filename from metadata.
                filename = meta.get("original_name")

                # Check if the file failed validation (i.e., if pdf_files[idx] is None).
                if pdf_files[idx] is None:
                    file_results.append({
                        "file": filename,
                        "status": "error",
                        "error": "File validation failed."
                    })
                    failed += 1
                    continue  # Skip further processing for this file.

                # Create an instance of PDFTextExtractor to extract text from the PDF.
                extractor = PDFTextExtractor(pdf_files[idx])
                extracted_data = extractor.extract_text()  # Extract the textual content.
                extractor.close()  # Close the extractor to free up resources.

                # Initialize PDFSearcher with the extracted text data.
                searcher = PDFSearcher(extracted_data)
                # Execute the search method to find target phrase occurrences within the bounding box.
                # This method returns a tuple: (result_data_dict, match_count)
                result_data, match_count = searcher.find_target_phrase_occurrences(bounding_box)

                # Append a successful result entry for the current file.
                file_results.append({
                    "file": filename,
                    "status": "success",
                    "results": {
                        "pages": result_data.get("pages", []),  # List of matches per page.
                        "match_count": match_count,  # Total matches found in the file.
                    }
                })
                successful += 1
                total_matches += match_count  # Accumulate the number of matches.
            except Exception as e:
                # Log any exceptions that occur during processing for this file.
                log_error(
                    f"[SECURITY] Error processing file {meta.get('original_name')}: {str(e)} [operation_id={operation_id}]"
                )
                # Append an error result for the file that failed processing.
                file_results.append({
                    "file": meta.get("original_name", "unknown"),
                    "status": "error",
                    "error": str(e)
                })
                failed += 1

        # Calculate the total elapsed time for the batch operation.
        total_time = time.time() - start_time

        # Compile a summary of the batch operation including counts and performance.
        batch_summary = {
            "batch_id": operation_id,
            "total_files": len(files),
            "successful": successful,
            "failed": failed,
            "total_matches": total_matches,
            "search_term": f"Bounding Box: {bounding_box}",
            "query_time": round(total_time, 2)
        }

        # Gather debug information including current and peak memory usage.
        debug_info = {
            "memory_usage": memory_monitor.get_memory_stats().get("current_usage"),
            "peak_memory": memory_monitor.get_memory_stats().get("peak_usage"),
            "operation_id": operation_id
        }

        # Record processing details for compliance and audit.
        record_keeper.record_processing(
            operation_type="batch_find_words",
            document_type="PDF_files",
            entity_types_processed=[f"Bounding Box: {bounding_box}"],
            processing_time=total_time,
            file_count=len(files),
            entity_count=total_matches,
            success=(successful > 0)
        )

        # Return the complete batch results including a summary, detailed file results, and debug information.
        return {
            "batch_summary": batch_summary,
            "file_results": file_results,
            "_debug": debug_info,
        }
