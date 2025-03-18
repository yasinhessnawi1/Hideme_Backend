import time
import asyncio
import uuid
from typing import Optional

from fastapi import APIRouter, File, UploadFile, Form, Request, HTTPException
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.services.initialization_service import initialization_service
from backend.app.utils.helpers.json_helper import validate_requested_entities
from backend.app.utils.sanitize_utils import sanitize_detection_output
from backend.app.utils.secure_logging import log_sensitive_operation
from backend.app.utils.data_minimization import minimize_extracted_data
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.processing_records import record_keeper
from backend.app.utils.file_validation import validate_mime_type, validate_file_content_async
from backend.app.utils.memory_management import memory_optimized, memory_monitor
from backend.app.utils.document_processing_utils import extract_text_data_in_memory
from backend.app.utils.secure_file_utils import SecureTempFileManager
from backend.app.utils.logger import log_info, log_warning, log_error

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

    The entire file is read once into memory and processed using in-memory buffers,
    avoiding unnecessary temporary files. Common validation and extraction logic is
    centralized in a shared helper function.
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

        # Read file content using SecureTempFileManager
        log_info(f"[SECURITY] Reading file content for processing: {file.filename} [operation_id={operation_id}]")
        file_read_start = time.time()

        # Use SecureTempFileManager to determine whether to use in-memory or file-based processing
        file_content = await file.read()
        processing_times["file_read_time"] = time.time() - file_read_start
        log_info(
            f"[SECURITY] File read completed in {processing_times['file_read_time']:.3f}s. Size: {len(file_content) / 1024:.1f}KB [operation_id={operation_id}]")

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

        # Extract text using SecureTempFileManager
        extract_start = time.time()
        log_info(
            f"[SECURITY] Starting text extraction from {detected_mime or file.content_type} [operation_id={operation_id}]")

        # Define processor function for extraction
        async def extraction_processor(content):
            # If we received a BytesIO object, extract the bytes from it
            if hasattr(content, 'read') and hasattr(content, 'seek'):
                content.seek(0)  # Reset position to beginning
                content = content.read()  # Read all bytes
            return await extract_text_data_in_memory(file.content_type, content)

        # Use SecureTempFileManager for memory-efficient processing
        extracted_data = await SecureTempFileManager.process_content_in_memory_async(
            file_content,
            extraction_processor,
            use_path=False,
            extension="." + (file.filename.split(".")[-1] if "." in file.filename else "tmp")
        )

        processing_times["extraction_time"] = time.time() - extract_start
        log_info(
            f"[SECURITY] Text extraction completed in {processing_times['extraction_time']:.3f}s [operation_id={operation_id}]")

        # Apply data minimization to reduce exposure of sensitive information
        log_info(f"[SECURITY] Applying data minimization [operation_id={operation_id}]")
        extracted_data = minimize_extracted_data(extracted_data)

        # Get the Gemini detector instance
        log_info(f"[SECURITY] Initializing Gemini detector [operation_id={operation_id}]")
        detector = initialization_service.get_gemini_detector()

        # Set detection timeout and run detection
        detection_timeout = 40
        detection_start = time.time()
        log_info(
            f"[SECURITY] Starting Gemini AI detection with timeout {detection_timeout}s [operation_id={operation_id}]")
        try:
            detection_task = detector.detect_sensitive_data_async(extracted_data, entity_list)
            detection_result = await asyncio.wait_for(detection_task, timeout=detection_timeout)
        except asyncio.TimeoutError:
            log_error(f"[SECURITY] Gemini detection timed out after {detection_timeout}s [operation_id={operation_id}]")
            return JSONResponse(
                status_code=408,
                content={"detail": f"Gemini detection timed out after {detection_timeout} seconds"}
            )

        if detection_result is None:
            log_error(f"[SECURITY] Gemini detection returned no results [operation_id={operation_id}]")
            return JSONResponse(
                status_code=500,
                content={"detail": "Detection failed to return results"}
            )

        anonymized_text, entities, redaction_mapping = detection_result
        processing_times["detection_time"] = time.time() - detection_start
        log_info(
            f"[SECURITY] Gemini detection completed in {processing_times['detection_time']:.3f}s. Found {len(entities)} entities [operation_id={operation_id}]")

        total_time = time.time() - start_time
        processing_times["total_time"] = total_time

        # Calculate statistics for logging and monitoring
        total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
        processing_times["words_count"] = total_words
        processing_times["pages_count"] = len(extracted_data.get("pages", []))
        if total_words > 0 and entities:
            processing_times["entity_density"] = (len(entities) / total_words) * 1000
            log_info(
                f"[SECURITY] Entity density: {processing_times['entity_density']:.2f} entities per 1000 words [operation_id={operation_id}]")

        log_info(
            f"[SECURITY] Recording processing metrics. Total words: {total_words}, Pages: {processing_times['pages_count']} [operation_id={operation_id}]")
        record_keeper.record_processing(
            operation_type="gemini_detection",
            document_type=file.content_type,
            entity_types_processed=entity_list or [],
            processing_time=total_time,
            entity_count=len(entities),
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
        log_info(
            f"[SECURITY] Memory usage: current={mem_stats['current_usage']:.1f}%, peak={mem_stats['peak_usage']:.1f}% [operation_id={operation_id}]")

        # Log operation completion
        log_sensitive_operation(
            "Gemini Detection",
            len(entities),
            total_time,
            pages=processing_times["pages_count"],
            words=total_words,
            extract_time=processing_times["extraction_time"],
            detect_time=processing_times["detection_time"],
            operation_id=operation_id
        )
        log_info(
            f"[SECURITY] Gemini detection operation completed successfully in {total_time:.3f}s [operation_id={operation_id}]")

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