import time
import asyncio
from typing import Optional

from fastapi import APIRouter, File, UploadFile, Form, Request, HTTPException
from fastapi.responses import JSONResponse

from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.configs.gliner_config import GLINER_MODEL_NAME, GLINER_ENTITIES
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.helpers.json_helper import validate_requested_entities
from backend.app.utils.helpers.hybrid_detection_helper import process_file_in_chunks
from backend.app.utils.secure_logging import log_sensitive_operation
from backend.app.utils.data_minimization import minimize_extracted_data
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.processing_records import record_keeper
from backend.app.utils.sanitize_utils import sanitize_detection_output
from backend.app.utils.file_validation import (
    validate_mime_type,
    validate_file_content_async,
    MAX_PDF_SIZE_BYTES,
    MAX_TEXT_SIZE_BYTES
)
from backend.app.utils.memory_management import memory_optimized, memory_monitor
from backend.app.utils.document_processing_utils import extract_text_data_in_memory

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

# Define chunk size for large document processing
LARGE_FILE_THRESHOLD = 5 * 1024 * 1024  # 5MB
CHUNK_SIZE = 1 * 1024 * 1024  # 1MB


@router.post("/detect")
@limiter.limit("8/minute")
@memory_optimized(threshold_mb=100)
async def hybrid_detect_sensitive(
        request: Request,
        file: UploadFile = File(...),
        requested_entities: Optional[str] = Form(None),
        use_presidio: bool = Form(True),
        use_gemini: bool = Form(True),
        use_gliner: bool = Form(False)
):
    """
    Detect sensitive information using multiple detection engines with enhanced security.

    This endpoint processes the uploaded document with optimized memory usage for large files
    using chunked processing when needed, and avoids unnecessary temporary files.

    Performance characteristics:
    - Memory usage: Adaptive, uses chunked processing for large files
    - Processing time: Increases with document size and complexity
    - Supported engines: Presidio, Gemini, and GLiNER (optional combinations)
    """
    start_time = time.time()
    processing_times = {}

    # Validate allowed MIME types
    allowed_types = ["application/pdf", "text/plain", "text/csv", "text/markdown", "text/html"]
    if not validate_mime_type(file.content_type, allowed_types):
        return JSONResponse(
            status_code=415,
            content={"detail": "Unsupported file type. Please upload a PDF or text file."}
        )

    try:
        # Process requested entities
        try:
            entity_list = validate_requested_entities(requested_entities)
            if not entity_list and use_gliner:
                entity_list = GLINER_ENTITIES
        except Exception as e:
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                e, "entity_validation", 400
            )
            return JSONResponse(status_code=status_code, content=error_response)

        # Check if the file is large and needs chunked processing
        file_read_start = time.time()
        first_chunk = await file.read(8192)
        await file.seek(0)

        # Determine max size based on file type
        max_size = MAX_PDF_SIZE_BYTES if "pdf" in file.content_type.lower() else MAX_TEXT_SIZE_BYTES

        # Validate file size before reading full content
        if len(first_chunk) > max_size:
            return JSONResponse(
                status_code=413,
                content={"detail": f"File size exceeds maximum allowed ({max_size // (1024 * 1024)}MB)"}
            )

        # Decide whether to use chunked processing
        use_chunked_processing = False

        # For large files, use chunked processing
        if hasattr(file, 'size') and file.size and file.size > LARGE_FILE_THRESHOLD:
            use_chunked_processing = True

        if use_chunked_processing:
            # Process large file in chunks
            result = await process_file_in_chunks(
                file,
                entity_list,
                use_presidio,
                use_gemini,
                use_gliner,
                start_time
            )
            return result

        # For smaller files, process normally
        contents = await file.read()
        if len(contents) > max_size:
            return JSONResponse(
                status_code=413,
                content={"detail": f"File size exceeds maximum allowed ({max_size // (1024 * 1024)}MB)"}
            )

        processing_times["file_read_time"] = time.time() - file_read_start

        # Validate file content
        is_valid, reason, detected_mime = await validate_file_content_async(
            contents, file.filename, file.content_type
        )
        if not is_valid:
            return JSONResponse(
                status_code=415,
                content={"detail": reason}
            )

        # Extract text
        extract_start = time.time()
        extracted_data = await extract_text_data_in_memory(file.content_type, contents)
        processing_times["extraction_time"] = time.time() - extract_start

        # Apply data minimization
        extracted_data = minimize_extracted_data(extracted_data)

        # Configure hybrid detector options and get detector instance
        config = {
            "use_presidio": use_presidio,
            "use_gemini": use_gemini,
            "use_gliner": use_gliner,
            "gliner_model_name": GLINER_MODEL_NAME,
            "entities": entity_list
        }
        detector_create_start = time.time()
        detector = initialization_service.get_hybrid_detector(config)
        processing_times["detector_init_time"] = time.time() - detector_create_start

        detection_timeout = 60
        detection_start = time.time()
        try:
            if hasattr(detector, 'detect_sensitive_data_async'):
                detection_task = detector.detect_sensitive_data_async(extracted_data, entity_list)
                detection_result = await asyncio.wait_for(detection_task, timeout=detection_timeout)
            else:
                detection_task = asyncio.to_thread(detector.detect_sensitive_data, extracted_data, entity_list)
                detection_result = await asyncio.wait_for(detection_task, timeout=detection_timeout)
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=408,
                content={"detail": f"Hybrid detection timed out after {detection_timeout} seconds"}
            )

        if detection_result is None:
            return JSONResponse(
                status_code=500,
                content={"detail": "Detection failed to return results"}
            )

        anonymized_text, entities, redaction_mapping = detection_result
        processing_times["detection_time"] = time.time() - detection_start
        processing_times["total_time"] = time.time() - start_time

        total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
        processing_times["words_count"] = total_words
        processing_times["pages_count"] = len(extracted_data.get("pages", []))
        if total_words > 0 and entities:
            processing_times["entity_density"] = (len(entities) / total_words) * 1000

        record_keeper.record_processing(
            operation_type="hybrid_detection",
            document_type=file.content_type,
            entity_types_processed=entity_list or [],
            processing_time=processing_times["total_time"],
            entity_count=len(entities),
            success=True
        )

        engines_used = {
            "presidio": use_presidio,
            "gemini": use_gemini,
            "gliner": use_gliner
        }
        file_info = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(contents)
        }
        sanitized_response = sanitize_detection_output(
            anonymized_text, entities, redaction_mapping, processing_times
        )
        sanitized_response["model_info"] = {"engine": "hybrid", "engines_used": engines_used}
        sanitized_response["file_info"] = file_info

        mem_stats = memory_monitor.get_memory_stats()
        sanitized_response["_debug"] = {
            "memory_usage": mem_stats["current_usage"],
            "peak_memory": mem_stats["peak_usage"]
        }

        log_sensitive_operation(
            "Hybrid Detection",
            len(entities),
            processing_times["total_time"],
            pages=processing_times["pages_count"],
            words=total_words,
            engines=engines_used,
            extract_time=processing_times["extraction_time"],
            detect_time=processing_times["detection_time"]
        )

        return JSONResponse(content=sanitized_response)

    except HTTPException as e:
        raise e
    except Exception as e:
        error_response = SecurityAwareErrorHandler.handle_detection_error(e, "hybrid_detection")
        error_response["model_info"] = {
            "engine": "hybrid",
            "engines_used": {"presidio": use_presidio, "gemini": use_gemini, "gliner": use_gliner}
        }
        return JSONResponse(status_code=500, content=error_response)


