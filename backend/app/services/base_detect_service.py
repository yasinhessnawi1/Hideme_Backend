import asyncio
import json
import time
from typing import Optional, Tuple, Any

from fastapi.responses import JSONResponse

from backend.app.document_processing.detection_updater import DetectionResultUpdater
from backend.app.document_processing.pdf_extractor import PDFTextExtractor
from backend.app.utils.helpers.json_helper import validate_requested_entities
from backend.app.utils.logging.logger import log_info
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.validation.file_validation import validate_mime_type, validate_file_content_async


class BaseDetectionService:
    allowed_mime_types = ["application/pdf"]

    @staticmethod
    def parse_remove_words(remove_words: str) -> list:
        """
        Parses the remove_words parameter into a list of words/phrases.
        """
        try:
            parsed = json.loads(remove_words)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
            return [str(parsed).strip()]
        except json.JSONDecodeError:
            return [word.strip() for word in remove_words.split(",") if word.strip()]

    @staticmethod
    async def read_file_content(file, operation_id: str) -> Tuple[bytes, float]:
        file_read_start = time.time()
        content = await file.read()
        elapsed = time.time() - file_read_start
        log_info(f"[BaseDetectionService] File read for operation_id={operation_id} completed in {elapsed:.3f}s.")
        return content, elapsed

    @staticmethod
    def extract_text(file_content: bytes, filename: str, operation_id: str) -> Tuple[Optional[Any], Optional[JSONResponse]]:
        try:
            extractor = PDFTextExtractor(file_content)
            extracted_data = extractor.extract_text()
            extractor.close()
            return extracted_data, None
        except Exception as e:
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                e, "text_extraction", 500, filename
            )
            error_response["operation_id"] = operation_id
            return None, JSONResponse(status_code=status_code, content=error_response)

    @staticmethod
    def process_requested_entities(requested_entities: Optional[str], operation_id: str) -> Tuple[Optional[Any], Optional[JSONResponse]]:
        if requested_entities:
            try:
                entity_list = validate_requested_entities(requested_entities)
                return entity_list, None
            except Exception as e:
                error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                    e, "entity_validation", 400
                )
                error_response["operation_id"] = operation_id
                return None, JSONResponse(status_code=status_code, content=error_response)
        return None, None

    @classmethod
    def validate_mime(cls, file, operation_id: str) -> Optional[JSONResponse]:
        if not validate_mime_type(file.content_type, cls.allowed_mime_types):
            return JSONResponse(
                status_code=415,
                content={
                    "detail": "Unsupported file type. Please upload a PDF or text file.",
                    "operation_id": operation_id
                }
            )
        return None

    @staticmethod
    async def perform_detection(detector, minimized_data: Any, entity_list: Optional[Any],
                                detection_timeout: int, operation_id: str) -> Tuple[Optional[Any], Optional[JSONResponse]]:
        try:
            if hasattr(detector, 'detect_sensitive_data_async') and callable(getattr(detector, 'detect_sensitive_data_async')):
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
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(e, "detection", 500)
            error_response["operation_id"] = operation_id
            return None, JSONResponse(status_code=status_code, content=error_response)

    @staticmethod
    async def prepare_detection_context(file, requested_entities: Optional[str], operation_id: str,
                                        start_time: float) -> Tuple[Optional[Any], Optional[bytes], Optional[Any], Optional[dict], Optional[JSONResponse]]:
        """
        Prepares the common context needed for detection:
          - Validates MIME type.
          - Processes requested entities.
          - Reads file content.
          - Validates file content.
          - Extracts text.
        Returns a tuple:
          (extracted_data, file_content, entity_list, processing_times, error_response)
        """
        processing_times = {}
        # Step 1: Validate MIME type.
        mime_error = BaseDetectionService.validate_mime(file, operation_id)
        if mime_error:
            return None, None, None, None, mime_error

        # Step 2: Process requested entities.
        entity_list, entity_error = BaseDetectionService.process_requested_entities(requested_entities, operation_id)
        if entity_error:
            return None, None, None, None, entity_error

        # Step 3: Read file content.
        file_content, read_time = await BaseDetectionService.read_file_content(file, operation_id)
        processing_times["file_read_time"] = read_time

        # Step 4: Validate file content.
        is_valid, reason, _ = await validate_file_content_async(file_content, file.filename, file.content_type)
        if not is_valid:
            return None, None, None, None, JSONResponse(
                status_code=415,
                content={"detail": reason, "operation_id": operation_id}
            )

        # Step 5: Extract text.
        extracted_data, extraction_error = BaseDetectionService.extract_text(file_content, file.filename, operation_id)
        if extraction_error:
            return None, None, None, None, extraction_error
        processing_times["extraction_time"] = time.time() - start_time - processing_times.get("file_read_time", 0)

        return extracted_data, file_content, entity_list, processing_times, None

    @staticmethod
    def apply_removal_words(extracted_data: Any, detection_result: Tuple[Any, Any], remove_words: str) -> Tuple[Any, Any]:
        """
        Applies removal words to update the detection result.
        Returns updated (entities, redaction_mapping).
        """
        words_to_remove = BaseDetectionService.parse_remove_words(remove_words)
        updater = DetectionResultUpdater(extracted_data, detection_result)
        updated_result = updater.update_result(words_to_remove)
        redaction_mapping = updated_result.get("redaction_mapping", detection_result[1])
        return detection_result[0], redaction_mapping

    @staticmethod
    def compute_statistics(extracted_data: Any, entities: list) -> dict:
        """
        Computes and returns statistics: total words, total pages, and entity density.
        """
        total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
        total_pages = len(extracted_data.get("pages", []))
        stats = {"words_count": total_words, "pages_count": total_pages}
        if total_words > 0 and entities:
            stats["entity_density"] = (len(entities) / total_words) * 1000
        return stats