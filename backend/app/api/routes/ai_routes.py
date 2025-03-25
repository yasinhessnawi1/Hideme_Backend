import time
import asyncio
import uuid
from typing import Optional

from fastapi import APIRouter, File, UploadFile, Form, Request, HTTPException
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.document_processing.pdf import PDFTextExtractor
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.helpers.json_helper import validate_requested_entities
from backend.app.utils.logging.logger import log_info, log_error, log_warning
from backend.app.utils.validation.sanitize_utils import sanitize_detection_output
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.validation.data_minimization import minimize_extracted_data
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.validation.file_validation import validate_mime_type, validate_file_content_async
from backend.app.utils.memory_management import memory_optimized, memory_monitor

# Configure rate limiter
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


@router.post("/detect")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=75)
async def ai_detect_sensitive(
        request: Request,
        file: UploadFile = File(...),
        requested_entities: Optional[str] = Form(None)
):
    """
    Detect sensitive information in a document using Gemini AI with enhanced security.

    This endpoint leverages the centralized PDFTextExtractor for text extraction and
    the cached Gemini detector for entity detection with optimized memory usage.
    """
    start_time = time.time()
    processing_times = {}
    operation_id = str(uuid.uuid4())

    log_info(f"[SECURITY] Starting Gemini AI detection operation [operation_id={operation_id}]")

    try:
        # Validate allowed MIME types
        allowed_types = ["application/pdf", "text/plain", "text/csv", "text/markdown", "text/html"]
        if not validate_mime_type(file.content_type, allowed_types):
            log_warning(f"[SECURITY] Unsupported file type: {file.content_type} [operation_id={operation_id}]")
            return JSONResponse(
                status_code=415,
                content={"detail": "Unsupported file type. Please upload a PDF or text file."}
            )

        # Process requested entities
        entity_list = None
        if requested_entities:
            try:
                entity_list = validate_requested_entities(requested_entities)
                log_info(f"[SECURITY] Validated entities: {entity_list} [operation_id={operation_id}]")
            except Exception as e:
                log_error(f"[SECURITY] Entity validation error: {str(e)} [operation_id={operation_id}]")
                error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                    e, "entity_validation", 400
                )
                return JSONResponse(status_code=status_code, content=error_response)

        # Read file content
        file_read_start = time.time()
        file_content = await file.read()
        processing_times["file_read_time"] = time.time() - file_read_start

        log_info(
            f"[SECURITY] File read completed in {processing_times['file_read_time']:.3f}s. "
            f"Size: {len(file_content) / 1024:.1f}KB [operation_id={operation_id}]")

        # Validate file content (format, safety, size)
        is_valid, reason, detected_mime = await validate_file_content_async(
            file_content, file.filename, file.content_type
        )
        if not is_valid:
            log_warning(f"[SECURITY] File validation failed: {reason} [operation_id={operation_id}]")
            return JSONResponse(
                status_code=415,
                content={"detail": reason}
            )

        # Extract text using the centralized PDFTextExtractor
        extract_start = time.time()
        log_info(f"[SECURITY] Starting text extraction [operation_id={operation_id}]")

        try:
            # Initialize the text extractor with the file content
            extractor = PDFTextExtractor(file_content)
            extracted_data = extractor.extract_text(detect_images=True)
            extractor.close()
        except Exception as e:
            log_error(f"[SECURITY] Extraction error: {str(e)} [operation_id={operation_id}]")
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                e, "text_extraction", 500, file.filename
            )
            return JSONResponse(status_code=status_code, content=error_response)

        processing_times["extraction_time"] = time.time() - extract_start
        log_info(
            f"[SECURITY] Text extraction completed in {processing_times['extraction_time']:.3f}s [operation_id={operation_id}]")

        # Apply data minimization to reduce exposure of sensitive information
        minimized_data = minimize_extracted_data(extracted_data)

        # Get Gemini detector from the initialization service
        detector_start = time.time()
        detector = initialization_service.get_gemini_detector()
        processing_times["detector_init_time"] = time.time() - detector_start

        # Set detection timeout and run detection
        detection_timeout = 200
        detection_start = time.time()
        log_info(f"[SECURITY] Starting Gemini AI detection [operation_id={operation_id}]")

        try:
            # Use the asynchronous detect method if available, otherwise run in a thread
            if hasattr(detector, 'detect_sensitive_data_async') and callable(
                    getattr(detector, 'detect_sensitive_data_async')):
                detection_task = detector.detect_sensitive_data_async(minimized_data, entity_list)
                detection_result = await asyncio.wait_for(detection_task, timeout=detection_timeout)
            else:
                detection_result = await asyncio.to_thread(
                    detector.detect_sensitive_data, minimized_data, entity_list
                )
        except asyncio.TimeoutError:
            log_error(f"[SECURITY] Gemini detection timed out after {detection_timeout}s [operation_id={operation_id}]")
            return JSONResponse(
                status_code=408,
                content={
                    "detail": f"Gemini detection timed out after {detection_timeout} seconds",
                    "operation_id": operation_id
                }
            )

        if detection_result is None:
            log_error(f"[SECURITY] Gemini detection returned no results [operation_id={operation_id}]")
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Detection failed to return results",
                    "operation_id": operation_id
                }
            )

        anonymized_text, entities, redaction_mapping = detection_result
        processing_times["detection_time"] = time.time() - detection_start
        processing_times["total_time"] = time.time() - start_time

        log_info(f"[SECURITY] Gemini detection completed in {processing_times['detection_time']:.3f}s. "
                 f"Found {len(entities)} entities [operation_id={operation_id}]")

        # Calculate statistics for logging and monitoring
        total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
        processing_times["words_count"] = total_words
        processing_times["pages_count"] = len(extracted_data.get("pages", []))

        if total_words > 0 and entities:
            processing_times["entity_density"] = (len(entities) / total_words) * 1000
            log_info(
                f"[SECURITY] Entity density: {processing_times['entity_density']:.2f} entities per 1000 words [operation_id={operation_id}]")

        # Record processing for GDPR compliance
        record_keeper.record_processing(
            operation_type="gemini_detection",
            document_type=file.content_type,
            entity_types_processed=entity_list or [],
            processing_time=processing_times["total_time"],
            entity_count=len(entities),
            success=True
        )

        # Prepare sanitized response
        log_info(f"[SECURITY] Preparing sanitized response [operation_id={operation_id}]")
        sanitized_response = sanitize_detection_output(
            anonymized_text, entities, redaction_mapping, processing_times
        )

        sanitized_response["file_info"] = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(file_content)
        }

        sanitized_response["model_info"] = {"engine": "gemini"}

        # Add memory usage stats
        mem_stats = memory_monitor.get_memory_stats()
        sanitized_response["_debug"] = {
            "memory_usage": mem_stats["current_usage"],
            "peak_memory": mem_stats["peak_usage"],
            "operation_id": operation_id
        }

        # Log operation completion
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

        log_info(
            f"[SECURITY] Gemini detection operation completed successfully in {processing_times['total_time']:.3f}s [operation_id={operation_id}]")

        return JSONResponse(content=sanitized_response)

    except HTTPException as e:
        log_error(
            f"[SECURITY] HTTP exception in Gemini detection: {e.detail} (status {e.status_code}) [operation_id={operation_id}]")
        raise e
    except Exception as e:
        log_error(f"[SECURITY] Unhandled exception in Gemini detection: {str(e)} [operation_id={operation_id}]")
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "gemini_detection", 500
        )
        return JSONResponse(status_code=status_code, content=error_response)