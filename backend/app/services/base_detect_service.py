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

Comprehensive error handling via try/except is implemented in each method.
"""

import asyncio
import json
import time
from typing import Optional, Tuple, Any

from fastapi.responses import JSONResponse

from backend.app.document_processing.detection_updater import DetectionResultUpdater
from backend.app.document_processing.pdf_extractor import PDFTextExtractor
from backend.app.utils.helpers.json_helper import validate_all_engines_requested_entities
from backend.app.utils.logging.logger import log_warning, log_error
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.validation.file_validation import read_and_validate_file, validate_file_content_async


class BaseDetectionService:
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
            parsed = json.loads(remove_words)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
            return [str(parsed).strip()]
        except Exception as e:
            log_warning(f"Error parsing removal words: {str(e)}")
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
            extractor = PDFTextExtractor(file_content)
            extracted_data = extractor.extract_text()
            extractor.close()
            return extracted_data, None
        except Exception as e:
            log_error(f"Error during text extraction: {str(e)} [operation_id={operation_id}]")
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                e, "text_extraction", 500, filename)
            error_response["operation_id"] = operation_id
            return None, JSONResponse(status_code=status_code, content=error_response)

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
            entity_list = validate_all_engines_requested_entities(requested_entities)
            return entity_list, None
        except Exception as e:
            log_warning(f"Error processing requested entities: {str(e)} [operation_id={operation_id}]")
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                e, "entity_validation", 400)
            error_response["operation_id"] = operation_id
            return None, JSONResponse(status_code=status_code, content=error_response)

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
            # Here you could use a shared MIME validation utility if available.
            if not file.content_type or file.content_type.split(';')[0].strip().lower() not in cls.allowed_mime_types:
                return JSONResponse(
                    status_code=415,
                    content={
                        "detail": "Unsupported file type. Please upload a PDF or text file.",
                        "operation_id": operation_id
                    }
                )
            return None
        except Exception as e:
            log_warning(f"Exception during MIME validation: {str(e)} [operation_id={operation_id}]")
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
            if hasattr(detector, 'detect_sensitive_data_async') and callable(
                    getattr(detector, 'detect_sensitive_data_async')):
                detection_task = detector.detect_sensitive_data_async(minimized_data, entity_list)
                detection_result = await asyncio.wait_for(detection_task, timeout=detection_timeout)
            else:
                detection_result = await asyncio.to_thread(detector.detect_sensitive_data, minimized_data, entity_list)
            return detection_result, None
        except asyncio.TimeoutError:
            return None, JSONResponse(
                status_code=408,
                content={
                    "detail": f"Detection timed out after {detection_timeout} seconds",
                    "operation_id": operation_id
                }
            )
        except Exception as e:
            log_error(f"Error performing detection: {str(e)} [operation_id={operation_id}]")
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(e, "detection", 500)
            error_response["operation_id"] = operation_id
            return None, JSONResponse(status_code=status_code, content=error_response)

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
        processing_times = {}
        try:
            # Step 1: Validate MIME type.
            mime_error = BaseDetectionService.validate_mime(file, operation_id)
            if mime_error:
                return None, None, None, None, mime_error

            # Step 2: Process requested entities.
            entity_list, entity_error = BaseDetectionService.process_requested_entities(requested_entities,
                                                                                        operation_id)
            if entity_error:
                return None, None, None, None, entity_error

            # Step 3: Read and validate file content using the shared utility.
            file_content, error, read_time = await read_and_validate_file(file, operation_id)
            processing_times["file_read_time"] = read_time
            if error:
                return None, None, None, None, error

            # Step 4: Validate file content asynchronously.
            is_valid, reason, _ = await validate_file_content_async(file_content, file.filename, file.content_type)
            if not is_valid:
                return None, None, None, None, JSONResponse(
                    status_code=415,
                    content={"detail": reason, "operation_id": operation_id}
                )

            # Step 5: Extract text from the file.
            extracted_data, extraction_error = BaseDetectionService.extract_text(file_content, file.filename,
                                                                                 operation_id)
            if extraction_error:
                return None, None, None, None, extraction_error
            processing_times["extraction_time"] = time.time() - start_time - processing_times.get("file_read_time", 0)

            return extracted_data, file_content, entity_list, processing_times, None
        except Exception as e:
            log_error(f"Exception in prepare_detection_context: {str(e)} [operation_id={operation_id}]")
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
            words_to_remove = BaseDetectionService.parse_remove_words(remove_words)
            updater = DetectionResultUpdater(extracted_data, detection_result)
            updated_result = updater.update_result(words_to_remove)
            redaction_mapping = updated_result.get("redaction_mapping", detection_result[1])
            return detection_result[0], redaction_mapping
        except Exception as e:
            log_warning(f"Error applying removal words: {str(e)}")
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
            total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
            total_pages = len(extracted_data.get("pages", []))
            stats = {"words_count": total_words, "pages_count": total_pages}
            if total_words > 0 and entities:
                stats["entity_density"] = (len(entities) / total_words) * 1000
            return stats
        except Exception as e:
            log_warning(f"Error computing statistics: {str(e)}")
            return {}