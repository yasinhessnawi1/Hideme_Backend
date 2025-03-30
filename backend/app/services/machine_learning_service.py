import asyncio
import json
import time
from typing import Optional, Tuple, Any

from fastapi import APIRouter, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.document_processing.detection_updater import DetectionResultUpdater
from backend.app.document_processing.pdf_extractor import PDFTextExtractor
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.helpers.json_helper import validate_requested_entities
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.system_utils.memory_management import memory_monitor
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.validation.data_minimization import minimize_extracted_data
from backend.app.utils.validation.file_validation import validate_mime_type, validate_file_content_async
from backend.app.utils.validation.sanitize_utils import sanitize_detection_output

# Configure rate limiter and router
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


class MashinLearningService:
    """
    Service that encapsulates all steps of sensitive information detection for machine learning tasks.
    Supports two detector types: "presidio" and "gliner".
    """

    def __init__(self, detector_type: str):
        self.detector_type = detector_type.lower()

    async def detect(
        self,
        file: UploadFile,
        requested_entities: Optional[str],
        operation_id: str,
        remove_words: Optional[str] = None
    ) -> JSONResponse:
        start_time = time.time()
        processing_times: dict = {}
        log_info(f"[ML] Starting {self.detector_type} detection operation [operation_id={operation_id}]")
        try:
            # 1. Validate MIME type.
            mime_error = self._validate_mime(file, ["application/pdf"], operation_id)
            if mime_error:
                return mime_error

            # 2. Process requested entities.
            entity_list, entity_error = self._process_requested_entities(requested_entities, operation_id)
            if entity_error:
                return entity_error

            # 3. Read file content.
            file_content, read_time = await self._read_file_content(file, operation_id)
            processing_times["file_read_time"] = read_time

            # 4. Validate file content.
            is_valid, reason, _ = await validate_file_content_async(file_content, file.filename, file.content_type)
            if not is_valid:
                log_warning(f"[ML] File validation failed: {reason} [operation_id={operation_id}]")
                return JSONResponse(status_code=415, content={"detail": reason})

            # 5. Extract text.
            extracted_data, extraction_error = self._extract_text(file_content, file.filename, operation_id)
            if extraction_error:
                return extraction_error
            processing_times["extraction_time"] = time.time() - (start_time + processing_times.get("file_read_time", 0))
            log_info(f"[ML] Text extraction completed in {processing_times['extraction_time']:.3f}s [operation_id={operation_id}]")

            # 6. Minimize data.
            minimized_data = minimize_extracted_data(extracted_data)

            # 7. Perform detection.
            detection_start = time.time()
            detection_result, detection_error = await self._perform_detection(
                minimized_data, entity_list, operation_id, detection_timeout=200
            )
            if detection_error:
                return detection_error
            processing_times["detection_time"] = time.time() - detection_start

            if detection_result is None:
                log_error(f"[ML] {self.detector_type} detection returned no results [operation_id={operation_id}]")
                return JSONResponse(
                    status_code=500,
                    content={"detail": f"{self.detector_type} detection failed to return results", "operation_id": operation_id}
                )

            entities, redaction_mapping = detection_result
            total_time = time.time() - start_time
            processing_times["total_time"] = total_time
            log_info(
                f"[ML] {self.detector_type} detection completed in {processing_times['detection_time']:.3f}s. "
                f"Found {len(entities)} entities [operation_id={operation_id}]"
            )

            # 8. Optionally update detection result with removal words.
            if remove_words:
                words_to_remove = self._parse_remove_words(remove_words)
                updater = DetectionResultUpdater(extracted_data, detection_result)
                updated_result = updater.update_result(words_to_remove)
                redaction_mapping = updated_result.get("redaction_mapping", redaction_mapping)

            # 9. Calculate statistics.
            total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
            total_pages = len(extracted_data.get("pages", []))
            processing_times["words_count"] = total_words
            processing_times["pages_count"] = total_pages
            if total_words > 0 and entities:
                processing_times["entity_density"] = (len(entities) / total_words) * 1000
                log_info(
                    f"[ML] Entity density: {processing_times['entity_density']:.2f} entities per 1000 words [operation_id={operation_id}]"
                )

            # 10. Record processing for compliance.
            record_keeper.record_processing(
                operation_type=f"{self.detector_type}_detection",
                document_type=file.content_type,
                entity_types_processed=entity_list or [],
                processing_time=total_time,
                entity_count=len(entities),
                success=True
            )

            # 11. Prepare response.
            sanitized_response = self._prepare_response(
                entities, redaction_mapping,
                processing_times, file, file_content
            )
            sanitized_response["model_info"] = {"engine": self.detector_type}
            mem_stats = memory_monitor.get_memory_stats()
            sanitized_response["_debug"] = {
                "memory_usage": mem_stats["current_usage"],
                "peak_memory": mem_stats["peak_usage"],
                "operation_id": operation_id
            }

            log_sensitive_operation(
                f"{self.detector_type.capitalize()} Detection",
                len(entities),
                total_time,
                pages=total_pages,
                words=total_words,
                extract_time=processing_times["extraction_time"],
                detect_time=processing_times["detection_time"],
                operation_id=operation_id
            )
            log_info(f"[ML] {self.detector_type} detection operation completed successfully in {total_time:.3f}s [operation_id={operation_id}]")

            return JSONResponse(content=sanitized_response)

        except HTTPException as http_exc:
            log_error(
                f"[ML] HTTP exception in {self.detector_type} detection: {http_exc.detail} "
                f"(status {http_exc.status_code}) [operation_id={operation_id}]"
            )
            raise http_exc
        except Exception as e:
            # Broad exception clause kept here solely for logging purposes.
            log_error(f"[ML] Unhandled exception in {self.detector_type} detection: {str(e)} [operation_id={operation_id}]")
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                e, f"{self.detector_type}_detection", 500, getattr(file, 'filename', None)
            )
            return JSONResponse(status_code=status_code, content=error_response)

    @staticmethod
    def _parse_remove_words(remove_words: str) -> list:
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
    async def _read_file_content(file: UploadFile, operation_id: str) -> Tuple[bytes, float]:
        file_read_start = time.time()
        content = await file.read()
        elapsed = time.time() - file_read_start
        log_info(f"[ML] File read completed in {elapsed:.3f}s. Size: {len(content)/1024:.1f}KB [operation_id={operation_id}]")
        return content, elapsed

    @staticmethod
    def _validate_mime(file: UploadFile, allowed_types: list, operation_id: str) -> Optional[JSONResponse]:
        if not validate_mime_type(file.content_type, allowed_types):
            log_warning(f"[ML] Unsupported file type: {file.content_type} [operation_id={operation_id}]")
            return JSONResponse(
                status_code=415,
                content={"detail": "Unsupported file type. Please upload a PDF or text file."}
            )
        return None

    @staticmethod
    def _process_requested_entities(requested_entities: Optional[str], operation_id: str) -> Tuple[Optional[Any], Optional[JSONResponse]]:
        if requested_entities:
            try:
                entity_list = validate_requested_entities(requested_entities)
                log_info(f"[ML] Validated entities: {entity_list} [operation_id={operation_id}]")
                return entity_list, None
            except Exception as e:
                log_error(f"[ML] Entity validation error: {str(e)} [operation_id={operation_id}]")
                error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(e, "entity_validation", 400)
                return None, JSONResponse(status_code=status_code, content=error_response)
        return None, None

    @staticmethod
    def _extract_text(file_content: bytes, filename: str, operation_id: str) -> Tuple[Optional[Any], Optional[JSONResponse]]:
        log_info(f"[ML] Starting text extraction [operation_id={operation_id}]")
        try:
            extractor = PDFTextExtractor(file_content)
            extracted_data = extractor.extract_text()
            extractor.close()
            return extracted_data, None
        except Exception as e:
            log_error(f"[ML] Extraction error: {str(e)} [operation_id={operation_id}]")
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(e, "text_extraction", 500, filename)
            return None, JSONResponse(status_code=status_code, content=error_response)

    async def _perform_detection(
        self, minimized_data: Any, entity_list: Optional[Any], operation_id: str, detection_timeout: int
    ) -> Tuple[Optional[Any], Optional[JSONResponse]]:
        if self.detector_type == "presidio" and hasattr(initialization_service, "get_presidio_detector"):
            detector = initialization_service.get_presidio_detector()
        elif self.detector_type == "gliner" and hasattr(initialization_service, "get_gliner_detector"):
            detector = initialization_service.get_gliner_detector(entity_list)
        else:
            return None, JSONResponse(
                status_code=400,
                content={"detail": f"Unsupported detector type: {self.detector_type}"}
            )
        log_info(f"[ML] Starting {self.detector_type} detection [operation_id={operation_id}]")
        try:
            if hasattr(detector, 'detect_sensitive_data_async') and callable(getattr(detector, 'detect_sensitive_data_async')):
                detection_task = detector.detect_sensitive_data_async(minimized_data, entity_list)
                detection_result = await asyncio.wait_for(detection_task, timeout=detection_timeout)
            else:
                detection_result = await asyncio.to_thread(detector.detect_sensitive_data, minimized_data, entity_list)
            return detection_result, None
        except asyncio.TimeoutError:
            log_error(f"[ML] {self.detector_type.capitalize()} detection timed out after {detection_timeout}s [operation_id={operation_id}]")
            return None, JSONResponse(
                status_code=408,
                content={"detail": f"{self.detector_type.capitalize()} detection timed out after {detection_timeout} seconds", "operation_id": operation_id}
            )
        except Exception as e:
            log_error(f"[ML] Error during {self.detector_type} detection: {str(e)} [operation_id={operation_id}]")
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(e, f"{self.detector_type}_detection", 500)
            return None, JSONResponse(status_code=status_code, content=error_response)

    @staticmethod
    def _prepare_response(
        entities: list, redaction_mapping: dict, processing_times: dict,
        file: UploadFile, file_content: bytes
    ) -> dict:
        sanitized_response = sanitize_detection_output(entities, redaction_mapping, processing_times)
        sanitized_response["file_info"] = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": f"{round(len(file_content) / (1024 * 1024), 2)} MB"
        }
        return sanitized_response