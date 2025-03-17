"""
Centralized utility for entity detection processing to ensure consistent handling.

This module provides a unified processing function that can be used by different detection
endpoints to ensure consistent file validation, error handling, and response formatting.
"""
import time
from typing import Any, List, Optional, Callable

from fastapi import UploadFile
from starlette.responses import JSONResponse

from backend.app.utils.document_processing_utils import extract_text_data_in_memory
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.file_validation import (
    validate_mime_type
)
from backend.app.utils.helpers.json_helper import validate_requested_entities


async def process_common_detection(
        file: UploadFile,
        requested_entities: Optional[str],
        detector_type: str,
        get_detector_func: Callable[[Optional[List[str]]], Any]
) -> JSONResponse:
    """
    Common processing logic for entity detection endpoints to reduce code duplication.

    Args:
        file: The uploaded file
        requested_entities: Optional string with requested entity types
        detector_type: Type of detector being used (for logging)
        get_detector_func: Function to get the appropriate detector instance

    Returns:
        JSON response with detection results or error
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
    
        # Validate entity list
        try:
            entity_list = validate_requested_entities(requested_entities)
        except Exception as e:
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                e, "entity_validation", 400
            )
            return JSONResponse(status_code=status_code, content=error_response)
    
        # Validate file size and read content
        from backend.app.utils.file_validation import (
            MAX_PDF_SIZE_BYTES, MAX_TEXT_SIZE_BYTES, validate_file_content_async
        )
    
        # Check size with a small read first
        file_read_start = time.time()
        first_chunk = await file.read(8192)
        await file.seek(0)
    
        # Determine max size based on file type
        max_size = MAX_PDF_SIZE_BYTES if "pdf" in file.content_type.lower() else MAX_TEXT_SIZE_BYTES
    
        # Check initial chunk size
        if len(first_chunk) > max_size:
            return JSONResponse(
                status_code=413,
                content={"detail": f"File size exceeds maximum allowed ({max_size // (1024 * 1024)}MB)"}
            )
    
        # Read full content
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
    
        # Extract text data
        extract_start = time.time()
        extracted_data = await extract_text_data_in_memory(file.content_type, contents)
        processing_times["extraction_time"] = time.time() - extract_start
    
        # Apply data minimization
        from backend.app.utils.data_minimization import minimize_extracted_data
    
        minimized_data = minimize_extracted_data(extracted_data)
    
        # Get detector
        detector = get_detector_func(entity_list)
    
        # Run detection
        detection_start = time.time()
        detection_result = await detector.detect_sensitive_data_async(minimized_data, entity_list)
        processing_times["detection_time"] = time.time() - detection_start
    
        if detection_result is None:
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                ValueError("Detection returned no results"), f"{detector_type}_detection", 500
            )
            return JSONResponse(status_code=status_code, content=error_response)
    
        anonymized_text, entities, redaction_mapping = detection_result
        processing_times["total_time"] = time.time() - start_time
    
        # Calculate statistics and prepare response
        from backend.app.utils.sanitize_utils import sanitize_detection_output
        from backend.app.utils.processing_records import record_keeper
        from backend.app.utils.secure_logging import log_sensitive_operation
        from backend.app.utils.memory_management import memory_monitor
    
        total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
        processing_times["words_count"] = total_words
        processing_times["pages_count"] = len(extracted_data.get("pages", []))
    
        if total_words > 0 and entities:
            processing_times["entity_density"] = (len(entities) / total_words) * 1000
    
        # Record processing
        record_keeper.record_processing(
            operation_type=f"{detector_type}_detection",
            document_type=file.content_type,
            entity_types_processed=entity_list or [],
            processing_time=processing_times["total_time"],
            entity_count=len(entities),
            success=True
        )
    
        # Prepare response
        sanitized_response = sanitize_detection_output(
            anonymized_text, entities, redaction_mapping, processing_times
        )
        sanitized_response["model_info"] = {"engine": detector_type}
        sanitized_response["file_info"] = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(contents)
        }
    
        # Add memory statistics
        mem_stats = memory_monitor.get_memory_stats()
        sanitized_response["_debug"] = {
            "memory_usage": mem_stats["current_usage"],
            "peak_memory": mem_stats["peak_usage"]
        }
    
        # Log operation
        log_sensitive_operation(
            f"{detector_type.capitalize()} Detection",
            len(entities),
            processing_times["total_time"],
            pages=processing_times["pages_count"],
            words=total_words,
            extract_time=processing_times["extraction_time"],
            detect_time=processing_times["detection_time"]
        )
    
        return JSONResponse(content=sanitized_response)
    
    except Exception as e:
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, f"{detector_type}_detection", 500
        )
        return JSONResponse(status_code=status_code, content=error_response)
