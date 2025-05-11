"""
This module provides the BatchSearchService class that facilitates batch text search across multiple PDF files.
It validates and reads PDF files, extracts text using PDFTextExtractor in parallel, searches for specified terms within the extracted data using PDFSearcher, and returns a summary of results.
SecurityAwareErrorHandler is used throughout to securely handle and log errors.
"""

import time
import uuid
from typing import List, Dict, Any, Optional, Tuple, Union

from fastapi import UploadFile, HTTPException

from backend.app.document_processing.pdf_extractor import PDFTextExtractor
from backend.app.document_processing.pdf_searcher import PDFSearcher
from backend.app.domain.models import BatchDetectionResponse, BatchSummary, BatchDetectionDebugInfo, FileResult
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
    ) -> BatchDetectionResponse:
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
            A BatchDetectionResponse containing:
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
            raise HTTPException(status_code=400, detail=error_message)

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
            summary = BatchSummary(
                batch_id=batch_id,
                total_files=len(files),
                successful=0,
                failed=len(files),
                total_time=round(time.time() - start_time, 2),
                workers=optimal_workers,
                total_matches=0,
                search_term=", ".join(search_words),
            )
            debug = BatchDetectionDebugInfo(
                memory_usage=memory_monitor.get_memory_stats().get("current_usage"),
                peak_memory=memory_monitor.get_memory_stats().get("peak_usage"),
                operation_id=batch_id,
            )
            return BatchDetectionResponse(batch_summary=summary, file_results=[], debug=debug)

        # Extract text from valid PDF files in parallel using PDFTextExtractor.
        extraction_results = await PDFTextExtractor.extract_batch_text(valid_pdf_files, max_workers=optimal_workers)
        # Create a mapping from the valid file index to its corresponding extraction result.
        extraction_map = {idx: result for idx, result in extraction_results}

        # Initialize an empty list to hold individual file results.
        file_results: List[FileResult] = []
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
                file_results.append(
                    FileResult(
                        file=metadata.get("original_name"),
                        status="error",
                        error=metadata.get("error", "File validation failed.")
                    )
                )
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
                file_results.append(FileResult(**result_data))
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
                file_results.append(FileResult(
                    file=metadata.get("original_name", f"file_{i}"),
                    status="error",
                    error=f"Unhandled processing error: {str(e)}"
                )
                )
                # Increment the failure counter.
                failed += 1

        # Calculate the total query time for processing the batch.
        query_time = time.time() - start_time
        # Build the batch summary dictionary and memory statistics for debugging purposes.
        summary = BatchSummary(
            batch_id=batch_id,
            total_files=len(files),
            successful=successful,
            failed=failed,
            total_time=query_time,
            workers=optimal_workers,
            total_matches=total_matches,
            search_term=", ".join(search_words),
        )
        debug = BatchDetectionDebugInfo(
            memory_usage=memory_monitor.get_memory_stats().get("current_usage"),
            peak_memory=memory_monitor.get_memory_stats().get("peak_usage"),
            operation_id=batch_id,
        )
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

        return BatchDetectionResponse(batch_summary=summary, file_results=file_results, debug=debug)

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
    ) -> BatchDetectionResponse:
        """
        Combines all extracted PDF pages into one logical document and finds the phrase
        defined by `bounding_box` across all PDFs.

        Steps:
          1. Read & validate uploaded files.
          2. Extract text/pages from valid PDFs in parallel.
          3. Tag each page with its source file and merge into a single list.
          4. Use PDFSearcher.find_target_phrase_occurrences() to detect the phrase,
             merging multi-word bounding boxes correctly across pages.
          5. Group the found matches back by original file.
          6. Audit the batch operation via record_keeper.

        Returns:
            A BatchDetectionResponse containing:
              - batch_summary: metrics and the target_bbox used (as a string)
              - file_results: list of per-file results (pages + match_count)
              - _debug: memory usage and operation_id for diagnostics
        """
        # Record when the search began, for timing
        start_time = time.time()
        # Counters for how many files succeeded/failed and total matches found
        successful, failed, total_matches = 0, 0, 0
        # This will accumulate every PDF page (with its words & metadata)
        combined_pages: List[Dict[str, Any]] = []

        # Read and validate all UploadFile PDFs
        try:
            pdf_files, file_metadata = await BatchSearchService._read_files_for_extraction(
                files, operation_id
            )
        except Exception as e:
            log_error(
                f"[SECURITY] Error reading files in find_words_by_bbox: {e} "
                f"[operation_id={operation_id}]"
            )
            raise HTTPException(status_code=400, detail="Error reading files")

        # Filter out any that failed validation (None content)
        valid_pdf_files = [content for content in pdf_files if content is not None]
        if not valid_pdf_files:
            # Early return if no valid PDFs remain
            summary = BatchSummary(
                batch_id=operation_id,
                total_files=len(files),
                successful=0,
                failed=len(files),
                total_time=round(time.time() - start_time, 2),
                target_bbox=str(bounding_box),
                total_matches=0,
            )
            debug = BatchDetectionDebugInfo(
                memory_usage=memory_monitor.get_memory_stats().get("current_usage"),
                peak_memory=memory_monitor.get_memory_stats().get("peak_usage"),
                operation_id=operation_id,
            )
            return BatchDetectionResponse(batch_summary=summary, file_results=[], debug=debug)

        # Extract pages/text from valid PDFs in parallel
        extraction_results = await PDFTextExtractor.extract_batch_text(valid_pdf_files)
        # Map each combined-page index back to its source file name
        page_to_file_map: Dict[int, str] = {}
        page_index = 0

        for i, (_, result) in enumerate(extraction_results):
            if result and "pages" in result:
                source_name = file_metadata[i]["original_name"]
                for page in result["pages"]:
                    # Tag the raw page dict with its originating filename
                    page["source_file"] = source_name
                    # Remember which file this combined page index comes from
                    page_to_file_map[page_index] = source_name
                    combined_pages.append(page)
                    page_index += 1
                successful += 1
            else:
                # Log that this file's extraction failed or returned no pages
                failed += 1

        # Run the bounding-box-based phrase detection on the combined pages
        combined_data = {"pages": combined_pages}
        try:
            searcher = PDFSearcher(combined_data)
            phrase_result, match_count = searcher.find_target_phrase_occurrences(
                bounding_box
            )
            total_matches = match_count
        except Exception as e:
            log_error(
                f"[SECURITY] Error running phrase detection: {e} "
                f"[operation_id={operation_id}]"
            )
            raise HTTPException(status_code=500, detail="Error during phrase detection")

        # Step 4: Group each matched page result by its original file
        file_results_map: Dict[str, FileResult] = {}
        for idx, page_result in enumerate(phrase_result.get("pages", [])):
            source_file = page_to_file_map.get(idx, "unknown")
            if source_file not in file_results_map:
                # Initialize a new entry for this file
                file_results_map[source_file] = FileResult(
                    file=source_file,
                    status="success",
                    results={"pages": [], "match_count": 0}
                )
            # Add this page's matches to the file's results
            file_results_map[source_file].results["pages"].append(page_result)
            file_results_map[source_file].results["match_count"] += len(page_result.get("matches", []))

        # Convert the map of file->results into a list for the response
        file_results = list(file_results_map.values())

        # Audit the operation
        query_time = round(time.time() - start_time, 2)
        record_keeper.record_processing(
            operation_type="batch_text_search",
            document_type="multiple_files",
            entity_types_processed=[str(bounding_box)],
            processing_time=query_time,
            file_count=len(files),
            entity_count=total_matches,
            success=(successful > 0)
        )

        # Construct and return the final payload
        summary = BatchSummary(
            batch_id=operation_id,
            total_files=len(files),
            successful=successful,
            failed=failed,
            total_time=query_time,
            target_bbox=str(bounding_box),
            total_matches=total_matches,
        )
        debug = BatchDetectionDebugInfo(
            memory_usage=memory_monitor.get_memory_stats().get("current_usage"),
            peak_memory=memory_monitor.get_memory_stats().get("peak_usage"),
            operation_id=operation_id,
        )
        return BatchDetectionResponse(batch_summary=summary, file_results=file_results, debug=debug)
