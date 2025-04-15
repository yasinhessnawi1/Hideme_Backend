"""
This module provides the BatchSearchService class that facilitates batch text search across multiple PDF files.
It validates and reads PDF files, extracts text using PDFTextExtractor in parallel, searches for specified terms within the extracted data using PDFSearcher, and returns a summary of results.
SecurityAwareErrorHandler is used throughout to securely handle and log errors.
"""

import time
import uuid
from typing import List, Dict, Any, Optional, Tuple, Union

from fastapi import UploadFile

from backend.app.document_processing.pdf_extractor import PDFTextExtractor
from backend.app.document_processing.pdf_searcher import PDFSearcher
from backend.app.utils.constant.constant import MAX_FILES_COUNT
from backend.app.utils.logging.logger import log_info, log_error
from backend.app.utils.logging.secure_logging import log_batch_operation
from backend.app.utils.system_utils.memory_management import memory_monitor
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.validation.file_validation import read_and_validate_file
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler


class BatchSearchService:
    """
    BatchSearchService Class

    This class supports batch text search across multiple PDF files. It first validates and reads the provided files,
    then extracts text in parallel using PDFTextExtractor. After text extraction, it searches for the specified search terms
    in each file using PDFSearcher. The service aggregates results and performance metrics, logs the batch operation,
    and handles errors securely using SecurityAwareErrorHandler.
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
        # Record the start time of the batch search operation.
        start_time = time.time()
        # Generate a unique batch ID using UUID.
        batch_id = f"search-{str(uuid.uuid4())}"
        # Log the start of the batch search operation with its unique ID.
        log_info(f"Starting batch text search (Batch ID: {batch_id})")

        # Check if the number of files exceeds the allowed maximum.
        if len(files) > MAX_FILES_COUNT:
            # Create an error message indicating too many files uploaded.
            error_message = f"Too many files uploaded. Maximum allowed is {MAX_FILES_COUNT}."
            # Log the error message with security context.
            log_error(f"[SECURITY] {error_message} [operation_id={batch_id}]")
            # Return an error dictionary with the detail and operation id.
            return {"detail": error_message, "operation_id": batch_id}

        # Set optimal number of parallel workers (default to 4 if not provided).
        optimal_workers = max_parallel_files if max_parallel_files is not None else 4

        # Parse and clean the search terms into a list.
        search_words = BatchSearchService._parse_search_words(search_terms)

        # Read and validate the files for extraction; get file contents and metadata.
        pdf_files, file_metadata = await BatchSearchService._read_files_for_extraction(files, batch_id)

        # Filter out any files that failed validation.
        valid_pdf_files = [content for content in pdf_files if content is not None]
        # If there are no valid PDF files, prepare and return an error summary.
        if not valid_pdf_files:
            # Return a summary with no successful files.
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

        # Extract text from valid PDF files in parallel using PDFTextExtractor.
        extraction_results = await PDFTextExtractor.extract_batch_text(valid_pdf_files, max_workers=optimal_workers)
        # Create a mapping from the valid file index to its corresponding extraction result.
        extraction_map = {idx: result for idx, result in extraction_results}

        # Initialize an empty list to hold individual file results.
        file_results: List[Dict[str, Any]] = []
        # Initialize counters for successful and failed file processing.
        successful = 0
        failed = 0
        # Initialize total match count.
        total_matches = 0
        # Initialize a counter for valid file indices alignment.
        valid_count = 0

        # Process each file's metadata and its corresponding extraction result.
        for i, metadata in enumerate(file_metadata):
            # Check if the file validation failed based on its metadata status.
            if metadata.get("status") == "error":
                # Append the error result for this file.
                file_results.append({
                    "file": metadata.get("original_name"),
                    "status": "error",
                    "error": metadata.get("error", "File validation failed.")
                })
                # Increment the failure counter.
                failed += 1
                # Continue to the next file.
                continue

            # Retrieve the extraction result corresponding to the valid file counter.
            extraction_result = extraction_map.get(valid_count)
            # Increment the valid file counter.
            valid_count += 1

            try:
                # Process the search on the extraction result for a single file.
                result_data, success_flag, fail_flag, match_count = await BatchSearchService._process_single_file_result(
                    metadata, extraction_result, search_words, case_sensitive, ai_search
                )
                # Append the processed result data to the file results.
                file_results.append(result_data)
                # Update success and failure counters accordingly.
                successful += success_flag
                failed += fail_flag
                # Update the total match count found in this file.
                total_matches += match_count
            except Exception as e:
                # Log any unexpected error with security context.
                log_error(
                    f"[SECURITY] Error processing file {metadata.get('original_name')}: {str(e)} [operation_id={batch_id}]")
                # Append an error result for this file.
                file_results.append({
                    "file": metadata.get("original_name", f"file_{i}"),
                    "status": "error",
                    "error": f"Unhandled processing error: {str(e)}"
                })
                # Increment the failure counter.
                failed += 1

        # Calculate the total query time for processing the batch.
        query_time = time.time() - start_time
        # Build the batch summary dictionary.
        batch_summary = {
            "batch_id": batch_id,
            "total_files": len(files),
            "successful": successful,
            "failed": failed,
            "total_matches": total_matches,
            "search_term": ", ".join(search_words),
            "query_time": round(query_time, 2)
        }
        # Log the overall batch operation details.
        log_batch_operation("Batch Text Search", len(files), successful, query_time)

        # Record processing details for auditing purposes.
        record_keeper.record_processing(
            operation_type="batch_text_search",
            document_type="multiple_files",
            entity_types_processed=search_words,
            processing_time=query_time,
            file_count=len(files),
            entity_count=total_matches,
            success=(successful > 0)
        )

        # Retrieve memory statistics for debugging purposes.
        mem_stats = memory_monitor.get_memory_stats()
        # Prepare the complete response object with batch summary, file results, and debug info.
        response = {
            "batch_summary": batch_summary,
            "file_results": file_results,
            "_debug": {
                "memory_usage": mem_stats.get("current_usage"),
                "peak_memory": mem_stats.get("peak_usage"),
                "operation_id": batch_id
            }
        }
        # Return the complete response.
        return response

    @staticmethod
    async def _read_files_for_extraction(files: List[UploadFile], operation_id: str) -> Tuple[
        List[Optional[bytes]], List[Dict[str, Any]]]:
        """
        Reads and validates a list of files for text extraction.

        This method iterates over each file, attempts to read and validate it using a utility.
        For files that fail validation, an error is logged securely and noted in the metadata.
        It returns a tuple of file contents (or None) and the corresponding file metadata.

        Args:
            files: A list of UploadFile objects.
            operation_id: A unique identifier for the batch operation.

        Returns:
            A tuple containing:
              - List of file contents (bytes) or None for files that failed validation.
              - List of dictionaries with metadata and status for each file.
        """
        # Initialize an empty list to hold file contents (or None).
        pdf_files: List[Optional[bytes]] = []
        # Initialize an empty list to hold metadata for each file.
        file_metadata: List[Dict[str, Any]] = []
        # Iterate over each file along with its index.
        for i, file in enumerate(files):
            try:
                # Attempt to read and validate the file.
                content, error_response, read_time = await read_and_validate_file(file, operation_id)
                # Check if there was an error during validation.
                if error_response:
                    # Log the error with security context.
                    log_error(f"[SECURITY] Validation failed for file {file.filename} [operation_id={operation_id}]")
                    # Append None for this file's content.
                    pdf_files.append(None)
                    # Use SecurityAwareErrorHandler to generate a safe error message.
                    error_info = SecurityAwareErrorHandler.handle_safe_error(
                        Exception("File validation error"), "file_validation", file.filename
                    )
                    # Append the metadata for this file indicating an error.
                    file_metadata.append({
                        "original_name": file.filename or f"file_{i}",
                        "content_type": file.content_type or "application/octet-stream",
                        "size": 0,
                        "read_time": read_time,
                        "status": "error",
                        "error": error_info.get("error", "File validation failed")
                    })
                else:
                    # Append the valid file content.
                    pdf_files.append(content)
                    # Append the metadata for the successfully read file.
                    file_metadata.append({
                        "original_name": file.filename or f"file_{i}.pdf",
                        "content_type": file.content_type or "application/octet-stream",
                        "size": len(content),
                        "read_time": read_time,
                        "status": "success"
                    })
            except Exception as e:
                # Log any unexpected exception with security context.
                log_error(f"[SECURITY] Exception reading file {file.filename}: {str(e)} [operation_id={operation_id}]")
                # Use SecurityAwareErrorHandler to generate a safe error message.
                error_info = SecurityAwareErrorHandler.handle_safe_error(e, "file_read", file.filename)
                # Append None for the file content due to error.
                pdf_files.append(None)
                # Append the metadata for this file with the error information.
                file_metadata.append({
                    "original_name": file.filename or f"file_{i}",
                    "content_type": "unknown",
                    "size": 0,
                    "read_time": 0,
                    "status": "error",
                    "error": error_info.get("error", str(e))
                })
        # Return the list of file contents and corresponding metadata.
        return pdf_files, file_metadata

    @staticmethod
    def _parse_search_words(search_words: Union[str, List[str]]) -> List[str]:
        """
        Parses the search_words parameter into a list of clean words/phrases.

        This helper function trims whitespace and, if provided as a string, splits it into individual words.
        It also removes any enclosing quotes.

        Args:
            search_words: A string or list of strings representing search terms.

        Returns:
            A list of cleaned search words.
        """

        # Define an inner function to trim whitespace from a word.
        def clean(word: str) -> str:
            # Return the word stripped of leading and trailing whitespace.
            return word.strip()

        # If search_words is already a list, process each element.
        if isinstance(search_words, list):
            # Return a list of cleaned words, excluding any empty strings.
            return [clean(word) for word in search_words if clean(word)]
        # Otherwise, treat search_words as a string and strip it.
        s = search_words.strip()
        # If the string starts and ends with quotes, remove them.
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            s = s[1:-1].strip()
        # Split the string into words, clean each, and return the list.
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

        This method checks for extraction errors, and if valid, it instantiates PDFSearcher to search for the search terms
        within the extracted data. It returns a tuple containing the result dictionary, a success flag, a failure flag,
        and the count of matches found.

        Args:
            metadata: Dictionary containing file metadata.
            extraction_result: The text extraction result for the file.
            search_words: List of search terms to look for.
            case_sensitive: Whether the search should be case-sensitive.
            ai_search: Whether to use AI-powered search enhancements.

        Returns:
            A tuple consisting of:
              - Result dictionary with file name and search results.
              - Success flag (1 for success, 0 otherwise).
              - Failure flag (1 for failure, 0 otherwise).
              - Count of matches found.
        """
        # Check if the extraction result is invalid or contains an error.
        if extraction_result is None or (isinstance(extraction_result, dict) and "error" in extraction_result):
            # Return an error result tuple indicating extraction failure.
            return ({
                        "file": metadata["original_name"],
                        "status": "error",
                        "error": extraction_result.get("error",
                                                       "Extraction failed") if extraction_result else "Extraction missing"
                    }, 0, 1, 0)
        try:
            # Instantiate PDFSearcher with the extracted result.
            searcher = PDFSearcher(extraction_result)
            # Perform the search asynchronously with the provided search words and options.
            search_result = await searcher.search_terms(search_words, case_sensitive=case_sensitive,
                                                        ai_search=ai_search)
            # Return a success result tuple with the search result and match count.
            return ({
                        "file": metadata["original_name"],
                        "status": "success",
                        "results": search_result
                    }, 1, 0, search_result.get("match_count", 0))
        except Exception as e:
            # Log any exception during search with security context.
            log_error(f"[SECURITY] Error searching file {metadata.get('original_name')}: {str(e)}")
            # Return an error result tuple indicating search failure.
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
        Process a batch of PDF files to find all occurrences of the word(s) that appear within a specified bounding box.

        For each file, the method:
          1. Reads and validates the PDF file.
          2. Extracts the text content.
          3. Instantiates PDFSearcher with the extracted data.
          4. Calls PDFSearcher (e.g. `find_target_phrase_occurrences`) to get a result dictionary containing
             the pages with matches and the overall match count.
          5. Aggregates the results for each file.

        Returns:
            A dictionary containing:
              - "batch_summary": Summary information for the batch operation.
              - "file_results": List of dictionaries for each file.
              - "_debug": Debug information including memory statistics and the operation ID.
        """
        # Record the start time of the batch operation.
        start_time = time.time()
        # Initialize an empty list to hold file-specific results.
        file_results: List[Dict[str, Any]] = []
        # Initialize counters for successful and failed file operations.
        successful = 0
        failed = 0
        # Initialize the counter for total matches found across files.
        total_matches = 0

        try:
            # Read and validate all PDF files and gather their metadata.
            pdf_files, file_metadata = await BatchSearchService._read_files_for_extraction(files, operation_id)
        except Exception as e:
            # Log any error encountered during file reading with security context.
            log_error(f"[SECURITY] Error reading files in find_words_by_bbox: {str(e)} [operation_id={operation_id}]")
            # Return an error response immediately.
            return {"detail": "Error reading files", "operation_id": operation_id}

        # Process each file along with its corresponding metadata.
        for idx, meta in enumerate(file_metadata):
            try:
                # Retrieve the original filename from the metadata.
                filename = meta.get("original_name")
                # Check if the file failed validation.
                if pdf_files[idx] is None:
                    # Append an error result if the file is not valid.
                    file_results.append({
                        "file": filename,
                        "status": "error",
                        "error": "File validation failed."
                    })
                    # Increment the failure counter.
                    failed += 1
                    # Skip processing this file.
                    continue

                # Instantiate PDFTextExtractor to extract text from the PDF.
                extractor = PDFTextExtractor(pdf_files[idx])
                # Extract the text content from the PDF.
                extracted_data = extractor.extract_text()
                # Close the extractor to free resources.
                extractor.close()

                # Instantiate PDFSearcher with the extracted data.
                searcher = PDFSearcher(extracted_data)
                # Find all target phrase occurrences within the given bounding box.
                result_data, match_count = searcher.find_target_phrase_occurrences(bounding_box)
                # Append a successful result entry for this file.
                file_results.append({
                    "file": filename,
                    "status": "success",
                    "results": {
                        "pages": result_data.get("pages", []),
                        "match_count": match_count,
                    }
                })
                # Increment the successful counter.
                successful += 1
                # Update the total match count with matches from this file.
                total_matches += match_count
            except Exception as e:
                # Log any exception that occurs during processing with security context.
                log_error(
                    f"[SECURITY] Error processing file {meta.get('original_name')}: {str(e)} [operation_id={operation_id}]")
                # Append an error result entry for this file.
                file_results.append({
                    "file": meta.get("original_name", "unknown"),
                    "status": "error",
                    "error": str(e)
                })
                # Increment the failure counter.
                failed += 1

        # Calculate the total elapsed time for the batch operation.
        total_time = time.time() - start_time
        # Build the batch summary with counts and timing.
        batch_summary = {
            "batch_id": operation_id,
            "total_files": len(files),
            "successful": successful,
            "failed": failed,
            "total_matches": total_matches,
            "search_term": f"Bounding Box: {bounding_box}",
            "query_time": round(total_time, 2)
        }
        # Gather memory usage and debug statistics.
        debug_info = {
            "memory_usage": memory_monitor.get_memory_stats().get("current_usage"),
            "peak_memory": memory_monitor.get_memory_stats().get("peak_usage"),
            "operation_id": operation_id
        }
        # Record processing details for auditing purposes.
        record_keeper.record_processing(
            operation_type="batch_find_words",
            document_type="PDF_files",
            entity_types_processed=[f"Bounding Box: {bounding_box}"],
            processing_time=total_time,
            file_count=len(files),
            entity_count=total_matches,
            success=(successful > 0)
        )
        # Return the complete batch result including the summary, file results, and debug info.
        return {
            "batch_summary": batch_summary,
            "file_results": file_results,
            "_debug": debug_info,
        }
