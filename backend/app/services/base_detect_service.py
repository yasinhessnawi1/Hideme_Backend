"""
BaseDetectionService provides common functionality for PDF entity detection.

This class includes methods for:
  - Parsing removal words.
  - Validating file input (MIME type, size, content) using centralized utility functions.
  - Extracting text from PDF content.
  - Processing requested entities.
  - Performing detection (with timeout support).
  - Preparing a complete detection context (combining all steps with performance metrics).
  - Applying removal words to update detection results.
  - Computing statistics from the extracted data.
  - Filtering detection results based on a score threshold.
  - Preparing the final JSON response by sanitizing the detection output and appending file and engine metadata.

Comprehensive error handling via try/except is implemented in each method.
"""

import asyncio
import json
import time
from typing import Optional, Tuple, Any, List, Dict

from fastapi.responses import JSONResponse

from backend.app.document_processing.detection_updater import DetectionResultUpdater
from backend.app.document_processing.pdf_extractor import PDFTextExtractor
from backend.app.domain.models import BatchDetectionResponse, FileResult, BatchSummary, BatchDetectionDebugInfo
from backend.app.entity_detection import BaseEntityDetector
from backend.app.utils.helpers.json_helper import validate_all_engines_requested_entities
from backend.app.utils.logging.logger import log_warning, log_error
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.system_utils.memory_management import memory_monitor
from backend.app.utils.validation.file_validation import read_and_validate_file, validate_file_content_async
from backend.app.utils.validation.sanitize_utils import sanitize_detection_output


class BaseDetectionService:
    # Allowed MIME types for file validation.
    allowed_mime_types = ["application/pdf"]

    @staticmethod
    def parse_remove_words(remove_words: str) -> list:
        """
        Parses the remove_words parameter into a list of words/phrases.

        Args:
            remove_words (str): A JSON string or comma-separated string of words/phrases.

        Returns:
            list: A list of cleaned words/phrases.
        """
        try:
            # Attempt to parse the removal words as JSON.
            parsed = json.loads(remove_words)
            # If the parsed result is a list, clean each item.
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
            # Otherwise, treat it as a single string and return as a one-item list.
            return [str(parsed).strip()]
        except Exception as e:
            # Log a warning if JSON parsing fails.
            log_warning(f"Error parsing removal words: {str(e)}")
            # Fallback: split the string by commas and clean each word.
            return [word.strip() for word in remove_words.split(",") if word.strip()]

    @staticmethod
    def extract_text(file_content: bytes, filename: str, operation_id: str) -> Tuple[
        Optional[Any], Optional[JSONResponse]]:
        """
        Extracts text from the provided PDF file content.

        Args:
            file_content (bytes): The PDF file content.
            filename (str): The filename of the PDF.
            operation_id (str): Operation identifier for logging.

        Returns:
            Tuple[Optional[Any], Optional[JSONResponse]]:
              - Extracted data if successful; otherwise, None.
              - A JSONResponse error if extraction fails; otherwise, None.
        """
        try:
            # Create a PDFTextExtractor instance with the file content.
            extractor = PDFTextExtractor(file_content)
            # Extract text/data from the PDF.
            extracted_data = extractor.extract_text()
            # Close the extractor to release any resources.
            extractor.close()
            # Return the extracted data and no error.
            return extracted_data, None
        except Exception as e:
            # Log the error that occurred during text extraction.
            log_error(f"Error during text extraction: {str(e)} [operation_id={operation_id}]")
            # Create an API error response using the SecurityAwareErrorHandler.
            error_response = SecurityAwareErrorHandler.handle_safe_error(
                e, "file_text_extraction", filename
            )
            # Include the operation ID in the error response.
            error_response["operation_id"] = operation_id
            # Return no extracted data and the error response.
            return None, JSONResponse(content=error_response)

    @staticmethod
    def process_requested_entities(requested_entities: Optional[str], operation_id: str) -> Tuple[
        Optional[Any], Optional[JSONResponse]]:
        """
        Processes and validates the requested entities.

        Args:
            requested_entities (Optional[str]): A string or JSON specifying requested entity types.
            operation_id (str): Operation identifier for logging.

        Returns:
            Tuple[Optional[Any], Optional[JSONResponse]]:
              - A validated list of entities if successful.
              - A JSONResponse error if validation fails.
        """
        try:
            # Validate the requested entities using the helper function.
            entity_list = validate_all_engines_requested_entities(requested_entities)
            # Return the validated entity list and no error.
            return entity_list, None
        except Exception as e:
            # Log a warning if entity validation fails.
            log_warning(f"Error processing requested entities: {str(e)} [operation_id={operation_id}]")
            # Create an API error response for the entity validation error.
            error_response = SecurityAwareErrorHandler.handle_safe_error(
                e, "file_text_process_requested_entities"
            )
            # Include the operation ID in the error response.
            error_response["operation_id"] = operation_id
            # Return no extracted data and the error response.
            return None, JSONResponse(content=error_response)

    @classmethod
    def validate_mime(cls, file, operation_id: str) -> Optional[JSONResponse]:
        """
        Validates the MIME type of the uploaded file.

        Args:
            file: The uploaded file.
            operation_id (str): Operation identifier for logging.

        Returns:
            Optional[JSONResponse]: A JSONResponse error if the MIME type is invalid; otherwise, None.
        """
        try:
            # Check if the file has a valid content type and if it is allowed.
            if not file.content_type or file.content_type.split(';')[0].strip().lower() not in cls.allowed_mime_types:
                # Return an error response for unsupported file types.
                return JSONResponse(
                    status_code=415,
                    content={
                        "detail": "Unsupported file type. Please upload a PDF or text file.",
                        "operation_id": operation_id
                    }
                )
            # Return None if the MIME type is valid.
            return None
        except Exception as e:
            # Log a warning if an exception occurs during MIME validation.
            log_warning(f"Exception during MIME validation: {str(e)} [operation_id={operation_id}]")
            # Return a generic internal server error response.
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal Server Error during MIME validation", "operation_id": operation_id}
            )

    @staticmethod
    async def perform_detection(detector, minimized_data: Any, entity_list: Optional[Any],
                                detection_timeout: int, operation_id: str) -> Tuple[
        Optional[Any], Optional[JSONResponse]]:
        """
        Performs detection using the provided detector.

        Args:
            detector: The detector instance.
            minimized_data (Any): The data to process.
            entity_list (Optional[Any]): List of entity types to process.
            detection_timeout (int): Timeout in seconds for detection.
            operation_id (str): Operation identifier for logging.

        Returns:
            Tuple[Optional[Any], Optional[JSONResponse]]: Detection result and any error response.
        """
        try:
            # Check if the detector has an asynchronous detection method.
            if hasattr(detector, 'detect_sensitive_data_async') and callable(
                    getattr(detector, 'detect_sensitive_data_async')):
                # Start the asynchronous detection task.
                detection_task = detector.detect_sensitive_data_async(minimized_data, entity_list)
                # Wait for the detection task to complete within the specified timeout.
                detection_result = await asyncio.wait_for(detection_task, timeout=detection_timeout)
            else:
                # If no asynchronous method is available, run the detection in a separate thread.
                detection_result = await asyncio.to_thread(detector.detect_sensitive_data, minimized_data, entity_list)
            # Return the detection result with no error.
            return detection_result, None
        except asyncio.TimeoutError:
            # Return a timeout error response if detection exceeds the allowed time.
            return None, JSONResponse(
                status_code=408,
                content={
                    "detail": f"Detection timed out after {detection_timeout} seconds",
                    "operation_id": operation_id
                }
            )
        except Exception as e:
            # Log any error that occurs during detection.
            log_error(f"Error performing detection: {str(e)} [operation_id={operation_id}]")
            # Create an API error response for the detection error.
            error_response = SecurityAwareErrorHandler.handle_safe_error(
                e, "detection_base_perform"
            )
            # Include the operation ID in the error response.
            error_response["operation_id"] = operation_id
            # Return no extracted data and the error response.
            return None, JSONResponse(content=error_response)

    @staticmethod
    async def prepare_detection_context(file, requested_entities: Optional[str], operation_id: str,
                                        start_time: float) -> Tuple[
        Optional[Any], Optional[bytes], Optional[Any], Optional[dict], Optional[JSONResponse]]:
        """
        Prepares the detection context by:
          1. Validating the file's MIME type.
          2. Processing requested entities.
          3. Reading and validating file content using the shared utility.
          4. Asynchronously validating the file content.
          5. Extracting text from the file.

        Args:
            file: The uploaded file.
            requested_entities (Optional[str]): The requested entity types.
            operation_id (str): Operation identifier for logging.
            start_time (float): Timestamp when detection started.

        Returns:
            Tuple containing:
              - extracted_data (Optional[Any]): The extracted text/data.
              - file_content (Optional[bytes]): The raw file content.
              - entity_list (Optional[Any]): The validated requested entities.
              - processing_times (Optional[dict]): Performance metrics.
              - error_response (Optional[JSONResponse]): An error response if any step fails.
        """
        # Initialize a dictionary to keep track of processing times.
        processing_times = {}
        try:
            # Step 1: Validate MIME type.
            mime_error = BaseDetectionService.validate_mime(file, operation_id)
            if mime_error:
                # Return early if MIME validation fails.
                return None, None, None, None, mime_error

            # Step 2: Process requested entities.
            entity_list, entity_error = BaseDetectionService.process_requested_entities(requested_entities,
                                                                                        operation_id)
            if entity_error:
                # Return early if processing requested entities fails.
                return None, None, None, None, entity_error

            # Step 3: Read and validate file content using the shared utility.
            file_content, error, read_time = await read_and_validate_file(file, operation_id)
            # Record the time taken to read the file.
            processing_times["file_read_time"] = read_time
            if error:
                # Return early if file reading fails.
                return None, None, None, None, error

            # Step 4: Validate file content asynchronously.
            is_valid, reason, _ = await validate_file_content_async(file_content, file.filename, file.content_type)
            if not is_valid:
                # Return an error response if file content is invalid.
                return None, None, None, None, JSONResponse(
                    status_code=415,
                    content={"detail": reason, "operation_id": operation_id}
                )

            # Step 5: Extract text from the file.
            extracted_data, extraction_error = BaseDetectionService.extract_text(file_content, file.filename,
                                                                                 operation_id)
            if extraction_error:
                # Return early if text extraction fails.
                return None, None, None, None, extraction_error
            # Calculate the extraction time.
            processing_times["extraction_time"] = time.time() - start_time - processing_times.get("file_read_time", 0)

            # Return the extracted data, file content, processed entities, timing metrics, and no error.
            return extracted_data, file_content, entity_list, processing_times, None
        except Exception as e:
            # Log any exception that occurs during the detection context preparation.
            log_error(f"Exception in prepare_detection_context: {str(e)} [operation_id={operation_id}]")
            # Return a generic internal server error response.
            return None, None, None, None, JSONResponse(
                status_code=500,
                content={"detail": "Internal Server Error", "operation_id": operation_id}
            )

    @staticmethod
    def apply_removal_words(extracted_data: Any, detection_result: Tuple[Any, Any], remove_words: str) -> Tuple[
        Any, Any]:
        """
        Applies removal words to update the detection result.

        Args:
            extracted_data (Any): The data extracted from the file.
            detection_result (Tuple[Any, Any]): Raw detection result (entities, redaction_mapping).
            remove_words (str): A string of words/phrases to remove.

        Returns:
            Tuple[Any, Any]: Updated (entities, redaction_mapping).
        """
        try:
            # Parse the removal words into a list.
            words_to_remove = BaseDetectionService.parse_remove_words(remove_words)
            # Create a DetectionResultUpdater instance with the extracted data and raw detection result.
            updater = DetectionResultUpdater(extracted_data, detection_result)
            # Update the detection result using the removal words.
            updated_result = updater.update_result(words_to_remove)
            # Get the updated redaction mapping; fallback to original if not provided.
            redaction_mapping = updated_result.get("redaction_mapping", detection_result[1])
            # Return the original entities and the updated redaction mapping.
            return detection_result[0], redaction_mapping
        except Exception as e:
            # Log a warning if an error occurs during removal words application.
            log_warning(f"Error applying removal words: {str(e)}")
            # In case of error, return the original detection result.
            return detection_result[0], detection_result[1]

    @staticmethod
    def compute_statistics(extracted_data: Any, entities: list) -> dict:
        """
        Computes statistics from the extracted data such as total words, total pages, and entity density.

        Args:
            extracted_data (Any): The data extracted from the file.
            entities (list): List of detected entities.

        Returns:
            dict: A dictionary containing computed statistics.
        """
        try:
            # Sum the total number of words in all pages.
            total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
            # Count the total number of pages.
            total_pages = len(extracted_data.get("pages", []))
            # Initialize the stat's dictionary.
            stats = {"words_count": total_words, "pages_count": total_pages}
            # If there are words and detected entities, compute the entity density.
            if total_words > 0 and entities:
                stats["entity_density"] = (len(entities) / total_words) * 1000
            # Return the computed statistics.
            return stats
        except Exception as e:
            # Log a warning if an error occurs during statistics computation.
            log_warning(f"Error computing statistics: {str(e)}")
            # Return an empty dictionary if an error occurs.
            return {}

    @staticmethod
    def apply_threshold_filter(entities: List[Dict[str, Any]],
                               redaction_mapping: Dict[str, Any],
                               threshold: Optional[float] = None
                               ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Apply threshold-based filtering on both a flat list of entity dictionaries and a redaction mapping.

        Only entities with a 'score' greater than or equal to the threshold are retained.
        If no threshold is provided, a default value of 0.85 is used.

        Args:
            entities: List of detected entity dictionaries.
            redaction_mapping: Dictionary containing redaction mapping data, typically with a 'pages' key.
            threshold: Optional numeric threshold (expected between 0.00 and 1.00).

        Returns:
            A tuple containing:
              - The filtered list of entity dictionaries.
              - The filtered redaction mapping dictionary.
        """
        effective_threshold = threshold if threshold is not None else 0.85
        # Filter the flat entities list using the helper method from BaseEntityDetector.
        filtered_entities = BaseEntityDetector.filter_by_score(entities, threshold=effective_threshold)
        # Filter the redaction mapping similarly.
        filtered_redaction_mapping = BaseEntityDetector.filter_by_score(redaction_mapping,
                                                                        threshold=effective_threshold)
        return filtered_entities, filtered_redaction_mapping

    @staticmethod
    def prepare_final_response(file, file_content: bytes, entities: List[Dict[str, Any]],
                               redaction_mapping: Dict[str, Any], processing_times: dict,
                               threshold: Optional[float], engine_name: str,
                               batch_id: str, operation_id: str) -> BatchDetectionResponse:
        """
        Prepares the final JSON response for detection output by applying threshold filtering,
        sanitizing the detection output, and appending file and engine metadata along with debug info.

        Args:
            file: The uploaded file object.
            file_content: Raw contents of the file (bytes).
            entities: List of detected entity dictionaries.
            redaction_mapping: Dictionary with redaction mappings.
            processing_times: Dictionary containing processing timing metrics.
            threshold: Optional numeric threshold for filtering (default 0.85 if not provided).
            engine_name: The name of the detection engine (e.g., "gemini", "presidio", "gliner").
            batch_id: unique ID for this run (Note here is not batch just one file, but I need it for the model)
            operation_id: unique ID for this run

        Returns:
            A BatchDetectionResponse containing the sanitized output with appended metadata.
        """
        # Apply the threshold filter.
        filtered_entities, filtered_redaction_mapping = BaseDetectionService.apply_threshold_filter(
            entities, redaction_mapping, threshold
        )
        # Sanitize the detection results.
        sanitized_response = sanitize_detection_output(filtered_entities, filtered_redaction_mapping, processing_times)
        # Append file metadata.
        sanitized_response["file_info"] = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": f"{round(len(file_content) / (1024 * 1024), 2)} MB"
        }
        sanitized_response["model_info"] = {"engine": engine_name}

        # build the single FileResult
        file_result = FileResult(
            file=file.filename,
            status="success",
            results=sanitized_response
        )

        # build the batch summary
        summary = BatchSummary(
            batch_id=batch_id,
            total_files=1,
            successful=1,
            failed=0,
            total_time=processing_times.get("total_time", 0.0)
        )

        # debug info
        mem = memory_monitor.get_memory_stats()
        debug = BatchDetectionDebugInfo(
            memory_usage=mem["current_usage"],
            peak_memory=mem["peak_usage"],
            operation_id=operation_id
        )

        # return the Pydantic wrapper
        return BatchDetectionResponse(
            batch_summary=summary,
            file_results=[file_result],
            debug=debug
        )
