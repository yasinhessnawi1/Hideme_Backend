import asyncio
import time
import uuid
from typing import Optional, Tuple, Any

from fastapi import UploadFile, HTTPException
from fastapi.responses import JSONResponse

from backend.app.document_processing.pdf import PDFTextExtractor
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.helpers.json_helper import validate_requested_entities
from backend.app.utils.logging.logger import log_info, log_error, log_warning
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.memory_management import memory_monitor
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.validation.data_minimization import minimize_extracted_data
from backend.app.utils.validation.file_validation import validate_mime_type, validate_file_content_async
from backend.app.utils.validation.sanitize_utils import sanitize_detection_output


class AIDetectService:
    """
    Service that encapsulates all steps of sensitive information detection.
    """

    async def detect(self, file: UploadFile, requested_entities: Optional[str]) -> JSONResponse:
        start_time = time.time()
        processing_times = {}
        operation_id = str(uuid.uuid4())
        detection_timeout = 200

        log_info(f"[SECURITY] Starting Gemini AI detection operation [operation_id={operation_id}]")

        try:
            # Step 1: Validate MIME type.
            allowed_types = ["application/pdf", "text/plain", "text/csv", "text/markdown", "text/html"]
            mime_error = self._validate_mime(file, allowed_types, operation_id)
            if mime_error:
                return mime_error

            # Step 2: Process requested entities.
            entity_list, entity_error = self._process_requested_entities(requested_entities, operation_id)
            if entity_error:
                return entity_error

            # Step 3: Read file content.
            file_content, read_time = await self._read_file_content(file, operation_id)
            processing_times["file_read_time"] = read_time

            # Step 4: Validate file content.
            is_valid, reason, _ = await validate_file_content_async(file_content, file.filename, file.content_type)
            if not is_valid:
                log_warning(f"[SECURITY] File validation failed: {reason} [operation_id={operation_id}]")
                return JSONResponse(status_code=415, content={"detail": reason})

            # Step 5: Extract text.
            extracted_data, extraction_error = self._extract_text(file_content, file.filename, operation_id)
            if extraction_error:
                return extraction_error
            processing_times["extraction_time"] = time.time() - (start_time + processing_times.get("file_read_time", 0))

            # Step 6: Minimize data.
            minimized_data = minimize_extracted_data(extracted_data)

            # Step 7: Perform detection.
            processing_times["detector_init_time"] = 0  # Detector init is part of the detection call
            detection_start = time.time()
            detection_result, detection_error = await self._perform_detection(minimized_data, entity_list, operation_id, detection_timeout)
            if detection_error:
                return detection_error
            processing_times["detection_time"] = time.time() - detection_start

            if detection_result is None:
                log_error(f"[SECURITY] Gemini detection returned no results [operation_id={operation_id}]")
                return JSONResponse(
                    status_code=500,
                    content={"detail": "Detection failed to return results", "operation_id": operation_id}
                )

            anonymized_text, entities, redaction_mapping = detection_result
            processing_times["total_time"] = time.time() - start_time

            log_info(f"[SECURITY] Gemini detection completed in {processing_times['detection_time']:.3f}s. "
                     f"Found {len(entities)} entities [operation_id={operation_id}]")

            # Step 8: Logging statistics.
            total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
            processing_times["words_count"] = total_words
            processing_times["pages_count"] = len(extracted_data.get("pages", []))
            if total_words > 0 and entities:
                processing_times["entity_density"] = (len(entities) / total_words) * 1000
                log_info(f"[SECURITY] Entity density: {processing_times['entity_density']:.2f} entities per 1000 words [operation_id={operation_id}]")

            record_keeper.record_processing(
                operation_type="gemini_detection",
                document_type=file.content_type,
                entity_types_processed=entity_list or [],
                processing_time=processing_times["total_time"],
                entity_count=len(entities),
                success=True
            )

            # Step 9: Prepare response.
            response_payload = self._prepare_response(anonymized_text, entities, redaction_mapping, processing_times, file, file_content, operation_id)
            log_sensitive_operation(
                "Gemini Detection",
                len(entities),
                processing_times["total_time"],
                pages=processing_times["pages_count"],
                words=total_words,
                extract_time=processing_times["extraction_time"],
                detect_time=processing_times["detection_time"],
                operation_id=operation_id
            )
            log_info(f"[SECURITY] Gemini detection operation completed successfully in {processing_times['total_time']:.3f}s [operation_id={operation_id}]")

            return JSONResponse(content=response_payload)

        except HTTPException as e:
            log_error(f"[SECURITY] HTTP exception in Gemini detection: {e.detail} (status {e.status_code}) [operation_id={operation_id}]")
            raise e
        except Exception as e:
            log_error(f"[SECURITY] Unhandled exception in Gemini detection: {str(e)} [operation_id={operation_id}]")
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(e, "gemini_detection", 500)
            return JSONResponse(status_code=status_code, content=error_response)

    @staticmethod
    async def _read_file_content(file: UploadFile, operation_id: str) -> Tuple[bytes, float]:
        file_read_start = time.time()
        content = await file.read()
        elapsed = time.time() - file_read_start
        log_info(f"[SECURITY] File read completed in {elapsed:.3f}s. Size: {len(content)/1024:.1f}KB [operation_id={operation_id}]")
        return content, elapsed

    @staticmethod
    def _validate_mime(file: UploadFile, allowed_types: list, operation_id: str) -> Optional[JSONResponse]:
        if not validate_mime_type(file.content_type, allowed_types):
            log_warning(f"[SECURITY] Unsupported file type: {file.content_type} [operation_id={operation_id}]")
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
                log_info(f"[SECURITY] Validated entities: {entity_list} [operation_id={operation_id}]")
                return entity_list, None
            except Exception as e:
                log_error(f"[SECURITY] Entity validation error: {str(e)} [operation_id={operation_id}]")
                error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(e, "entity_validation", 400)
                return None, JSONResponse(status_code=status_code, content=error_response)
        return None, None

    @staticmethod
    def _extract_text(file_content: bytes, filename: str, operation_id: str) -> Tuple[Optional[Any], Optional[JSONResponse]]:
        log_info(f"[SECURITY] Starting text extraction [operation_id={operation_id}]")
        try:
            extractor = PDFTextExtractor(file_content)
            extracted_data = extractor.extract_text(detect_images=True)
            extractor.close()
            return extracted_data, None
        except Exception as e:
            log_error(f"[SECURITY] Extraction error: {str(e)} [operation_id={operation_id}]")
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(e, "text_extraction", 500, filename)
            return None, JSONResponse(status_code=status_code, content=error_response)

    @staticmethod
    async def _perform_detection(minimized_data: Any, entity_list: Optional[Any], operation_id: str, detection_timeout: int) -> Tuple[Optional[Any], Optional[JSONResponse]]:
        detector = initialization_service.get_gemini_detector()
        log_info(f"[SECURITY] Starting Gemini AI detection [operation_id={operation_id}]")
        try:
            if hasattr(detector, 'detect_sensitive_data_async') and callable(getattr(detector, 'detect_sensitive_data_async')):
                detection_task = detector.detect_sensitive_data_async(minimized_data, entity_list)
                detection_result = await asyncio.wait_for(detection_task, timeout=detection_timeout)
            else:
                detection_result = await asyncio.to_thread(detector.detect_sensitive_data, minimized_data, entity_list)
            return detection_result, None
        except asyncio.TimeoutError:
            log_error(f"[SECURITY] Gemini detection timed out after {detection_timeout}s [operation_id={operation_id}]")
            return None, JSONResponse(
                status_code=408,
                content={"detail": f"Gemini detection timed out after {detection_timeout} seconds", "operation_id": operation_id}
            )
        except Exception as e:
            log_error(f"[SECURITY] Error during detection: {str(e)} [operation_id={operation_id}]")
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(e, "gemini_detection", 500)
            return None, JSONResponse(status_code=status_code, content=error_response)

    @staticmethod
    def _prepare_response(anonymized_text: str, entities: list, redaction_mapping: dict, processing_times: dict,
                          file: UploadFile, file_content: bytes, operation_id: str) -> dict:
        sanitized_response = sanitize_detection_output(anonymized_text, entities, redaction_mapping, processing_times)
        sanitized_response["file_info"] = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(file_content)
        }
        sanitized_response["model_info"] = {"engine": "gemini"}
        mem_stats = memory_monitor.get_memory_stats()
        sanitized_response["_debug"] = {
            "memory_usage": mem_stats["current_usage"],
            "peak_memory": mem_stats["peak_usage"],
            "operation_id": operation_id
        }
        return sanitized_response