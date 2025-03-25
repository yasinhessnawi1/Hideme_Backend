"""
Machine learning entity detection routes using centralized PDF processing.

This module provides API endpoints for detecting sensitive information in uploaded files
using different machine learning models. It leverages the centralized PDFTextExtractor for
text extraction and maintains consistent error handling across endpoints.
"""
import time
from typing import Optional, Dict, Any

from fastapi import APIRouter, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.document_processing.pdf import PDFTextExtractor
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.validation.data_minimization import minimize_extracted_data
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.helpers.json_helper import validate_requested_entities
from backend.app.utils.memory_management import memory_optimized, memory_monitor
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.validation.file_validation import validate_mime_type, validate_file_content_async
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.validation.sanitize_utils import sanitize_detection_output
from backend.app.utils.logging.secure_logging import log_sensitive_operation

# Configure rate limiter
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


async def process_entity_detection(
    file: UploadFile,
    requested_entities: Optional[str],
    detector_type: str,
    operation_id: str
) -> JSONResponse:
    """
    Common processing function for entity detection that uses the centralized PDFTextExtractor.

    Args:
        file: The uploaded file
        requested_entities: Optional string with requested entity types
        detector_type: Type of detector (presidio, gliner)
        operation_id: Unique operation ID for tracking

    Returns:
        JSONResponse with detection results
    """
    start_time = time.time()
    processing_times = {}

    try:
        # Validate MIME type
        allowed_types = ["application/pdf", "text/plain", "text/csv", "text/markdown", "text/html"]
        if not validate_mime_type(file.content_type, allowed_types):
            log_warning(f"[ML] Unsupported file type: {file.content_type} [operation_id={operation_id}]")
            return JSONResponse(
                status_code=415,
                content={"detail": "Unsupported file type. Please upload a PDF or text file."}
            )

        # Process requested entities
        try:
            entity_list = validate_requested_entities(requested_entities) if requested_entities else None
        except Exception as e:
            log_error(f"[ML] Entity validation error: {str(e)} [operation_id={operation_id}]")
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                e, "entity_validation", 400
            )
            return JSONResponse(status_code=status_code, content=error_response)

        # Read file content
        file_read_start = time.time()
        content = await file.read()
        processing_times["file_read_time"] = time.time() - file_read_start

        # Validate file content
        is_valid, reason, _ = await validate_file_content_async(
            content, file.filename, file.content_type
        )
        if not is_valid:
            log_warning(f"[ML] Invalid file content: {reason} [operation_id={operation_id}]")
            return JSONResponse(
                status_code=415,
                content={"detail": reason}
            )

        # Extract text using the centralized PDFTextExtractor
        extract_start = time.time()
        log_info(f"[ML] Starting text extraction using {detector_type} [operation_id={operation_id}]")

        try:
            # Initialize the text extractor with the file content
            extractor = PDFTextExtractor(content)
            extracted_data = extractor.extract_text(detect_images=True)
            extractor.close()
        except Exception as e:
            log_error(f"[ML] Extraction error: {str(e)} [operation_id={operation_id}]")
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                e, "text_extraction", 500, file.filename
            )
            return JSONResponse(status_code=status_code, content=error_response)

        processing_times["extraction_time"] = time.time() - extract_start
        log_info(f"[ML] Text extraction completed in {processing_times['extraction_time']:.3f}s [operation_id={operation_id}]")

        # Apply data minimization
        minimized_data = minimize_extracted_data(extracted_data)

        # Get the appropriate detector
        detector_start = time.time()
        if detector_type == "presidio":
            detector = initialization_service.get_presidio_detector()
        elif detector_type == "gliner":
            detector = initialization_service.get_gliner_detector(entity_list)
        else:
            return JSONResponse(
                status_code=400,
                content={"detail": f"Unsupported detector type: {detector_type}"}
            )

        processing_times["detector_init_time"] = time.time() - detector_start

        # Run detection
        detection_start = time.time()
        log_info(f"[ML] Starting {detector_type} detection [operation_id={operation_id}]")

        # Use async detection if available
        if hasattr(detector, 'detect_sensitive_data_async'):
            detection_result = await detector.detect_sensitive_data_async(minimized_data, entity_list)
        else:
            # Fall back to running in a thread
            import asyncio
            detection_result = await asyncio.to_thread(detector.detect_sensitive_data, minimized_data, entity_list)

        if detection_result is None:
            log_error(f"[ML] {detector_type} detection returned no results [operation_id={operation_id}]")
            return JSONResponse(
                status_code=500,
                content={
                    "detail": f"{detector_type} detection failed to return results",
                    "operation_id": operation_id
                }
            )

        anonymized_text, entities, redaction_mapping = detection_result
        processing_times["detection_time"] = time.time() - detection_start
        total_time = time.time() - start_time
        processing_times["total_time"] = total_time

        log_info(f"[ML] {detector_type} detection completed in {processing_times['detection_time']:.3f}s. "
               f"Found {len(entities)} entities [operation_id={operation_id}]")

        # Calculate statistics
        total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
        total_pages = len(extracted_data.get("pages", []))
        processing_times["words_count"] = total_words
        processing_times["pages_count"] = total_pages

        if total_words > 0 and entities:
            processing_times["entity_density"] = (len(entities) / total_words) * 1000

        # Record GDPR compliance
        record_keeper.record_processing(
            operation_type=f"{detector_type}_detection",
            document_type=file.content_type,
            entity_types_processed=entity_list or [],
            processing_time=total_time,
            entity_count=len(entities),
            success=True
        )

        # Prepare sanitized response
        sanitized_response = sanitize_detection_output(
            anonymized_text, entities, redaction_mapping, processing_times
        )

        sanitized_response["file_info"] = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(content)
        }

        sanitized_response["model_info"] = {"engine": detector_type}

        # Add memory statistics
        mem_stats = memory_monitor.get_memory_stats()
        sanitized_response["_debug"] = {
            "memory_usage": mem_stats["current_usage"],
            "peak_memory": mem_stats["peak_usage"],
            "operation_id": operation_id
        }

        # Log operation completion
        log_sensitive_operation(
            f"{detector_type.capitalize()} Detection",
            len(entities),
            total_time,
            pages=total_pages,
            words=total_words,
            extract_time=processing_times["extraction_time"],
            detect_time=processing_times["detection_time"],
            operation_id=operation_id
        )

        log_info(f"[ML] {detector_type} detection operation completed successfully in {total_time:.3f}s [operation_id={operation_id}]")

        return JSONResponse(content=sanitized_response)

    except HTTPException as e:
        log_error(f"[ML] HTTP exception in {detector_type} detection: {e.detail} (status {e.status_code}) [operation_id={operation_id}]")
        raise e
    except Exception as e:
        log_error(f"[ML] Unhandled exception in {detector_type} detection: {str(e)} [operation_id={operation_id}]")
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, f"{detector_type}_detection", 500, file.filename if hasattr(file, 'filename') else None
        )
        return JSONResponse(status_code=status_code, content=error_response)


@router.post("/detect")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=75)
async def presidio_detect_sensitive(
        request: Request,
        file: UploadFile = File(...),
        requested_entities: Optional[str] = Form(None)
):
    """
    Detect sensitive information using Microsoft Presidio NER with enhanced security.

    This endpoint processes documents using Presidio's named entity recognition system,
    which is optimized for identifying standard PII entities like names, emails, and
    identification numbers with high precision.
    """
    operation_id = f"presidio_detect_{int(time.time())}"
    log_info(f"[ML] Starting Presidio detection processing [operation_id={operation_id}]")

    return await process_entity_detection(
        file=file,
        requested_entities=requested_entities,
        detector_type="presidio",
        operation_id=operation_id
    )


@router.post("/gl_detect")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=200)  # GLiNER requires more memory
async def gliner_detect_sensitive_entities(
        request: Request,
        file: UploadFile = File(...),
        requested_entities: Optional[str] = Form(None)
):
    """
    Detect sensitive information using GLiNER with enhanced security and specialized entity recognition.

    This endpoint processes documents using the GLiNER (Generalized Language-Independent Named Entity
    Recognition) model, which is particularly effective at detecting domain-specific or custom
    entity types that traditional NER systems might miss.
    """
    operation_id = f"gliner_detect_{int(time.time())}"
    log_info(f"[ML] Starting GLiNER detection processing [operation_id={operation_id}]")

    # Check memory pressure before proceeding with GLiNER (it's memory-intensive)
    current_memory_usage = memory_monitor.get_memory_usage()
    if current_memory_usage > 85:
        log_warning(f"[ML] High memory pressure ({current_memory_usage:.1f}%), may impact GLiNER performance [operation_id={operation_id}]")

    return await process_entity_detection(
        file=file,
        requested_entities=requested_entities,
        detector_type="gliner",
        operation_id=operation_id
    )