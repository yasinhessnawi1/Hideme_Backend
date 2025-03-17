import time
import asyncio
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

    try:
        # Validate allowed MIME types
        allowed_types = ["application/pdf", "text/plain", "text/csv", "text/markdown", "text/html"]
        if not validate_mime_type(file.content_type, allowed_types):
            return JSONResponse(
                status_code=415,
                content={"detail": "Unsupported file type. Please upload a PDF or text file."}
            )

        # Process requested entities
        entity_list = None
        if requested_entities:
            try:
                entity_list = validate_requested_entities(requested_entities)
            except Exception as e:
                error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                    e, "entity_validation", 400
                )
                return JSONResponse(status_code=status_code, content=error_response)

        # Read file content only once into memory
        file_read_start = time.time()
        contents = await file.read()
        processing_times["file_read_time"] = time.time() - file_read_start

        # Validate file content (format, safety, size)
        is_valid, reason, detected_mime = await validate_file_content_async(
            contents, file.filename, file.content_type
        )
        if not is_valid:
            return JSONResponse(
                status_code=415,
                content={"detail": reason}
            )

        # Extract text using the centralized utility function
        extract_start = time.time()
        extracted_data = await extract_text_data_in_memory(file.content_type, contents)
        processing_times["extraction_time"] = time.time() - extract_start

        # Apply data minimization
        extracted_data = minimize_extracted_data(extracted_data)

        # Get the Gemini detector instance
        detector = initialization_service.get_gemini_detector()

        # Set detection timeout and run detection
        detection_timeout = 40
        detection_start = time.time()
        try:
            detection_task = detector.detect_sensitive_data_async(extracted_data, entity_list)
            detection_result = await asyncio.wait_for(detection_task, timeout=detection_timeout)
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=408,
                content={"detail": f"Gemini detection timed out after {detection_timeout} seconds"}
            )

        if detection_result is None:
            return JSONResponse(
                status_code=500,
                content={"detail": "Detection failed to return results"}
            )

        anonymized_text, entities, redaction_mapping = detection_result
        processing_times["detection_time"] = time.time() - detection_start

        total_time = time.time() - start_time
        processing_times["total_time"] = total_time

        total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
        processing_times["words_count"] = total_words
        processing_times["pages_count"] = len(extracted_data.get("pages", []))
        if total_words > 0 and entities:
            processing_times["entity_density"] = (len(entities) / total_words) * 1000

        record_keeper.record_processing(
            operation_type="gemini_detection",
            document_type=file.content_type,
            entity_types_processed=entity_list or [],
            processing_time=total_time,
            entity_count=len(entities),
        )

        sanitized_response = sanitize_detection_output(
            anonymized_text, entities, redaction_mapping, processing_times
        )
        sanitized_response["file_info"] = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(contents)
        }
        sanitized_response["model_info"] = {"engine": "gemini"}

        mem_stats = memory_monitor.get_memory_stats()
        sanitized_response["_debug"] = {
            "memory_usage": mem_stats["current_usage"],
            "peak_memory": mem_stats["peak_usage"]
        }

        log_sensitive_operation(
            "Gemini Detection",
            len(entities),
            total_time,
            pages=processing_times["pages_count"],
            words=total_words,
            extract_time=processing_times["extraction_time"],
            detect_time=processing_times["detection_time"]
        )

        return JSONResponse(content=sanitized_response)

    except HTTPException as e:
        raise e
    except Exception as e:
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "gemini_detection", 500
        )
        return JSONResponse(status_code=status_code, content=error_response)