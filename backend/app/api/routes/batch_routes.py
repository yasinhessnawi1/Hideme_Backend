"""
Optimized batch processing routes using the unified service architecture.

This module provides API endpoints for batch processing operations, leveraging the
centralized BatchProcessingService and ensuring proper separation of concerns between
route handlers and business logic.
"""
import time
from typing import List, Optional

from fastapi import APIRouter, File, UploadFile, Form, BackgroundTasks, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

from backend.app.entity_detection import EntityDetectionEngine
from backend.app.services import BatchDetectService, BatchRedactService, BatchExtractService
from backend.app.utils.logging.logger import log_info, log_error
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.memory_management import memory_optimized

# Configure rate limiter
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


@router.post("/detect")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=75)
async def batch_detect_sensitive(
        request: Request,
        files: List[UploadFile] = File(...),
        requested_entities: Optional[str] = Form(None),
        detection_engine: Optional[str] = Form("presidio"),
        max_parallel_files: Optional[int] = Form(4),
        remove_words: Optional[str] = Form(None)  # New parameter
):
    """
    Process multiple files for entity detection in parallel.
    """
    operation_id = f"batch_detect_{int(time.time())}"
    log_info(f"[BATCH] Starting batch entity detection [operation_id={operation_id}]")
    try:
        engine_map = {
            "presidio": EntityDetectionEngine.PRESIDIO,
            "gemini": EntityDetectionEngine.GEMINI,
            "gliner": EntityDetectionEngine.GLINER,
            "hybrid": EntityDetectionEngine.HYBRID
        }
        if detection_engine not in engine_map:
            return JSONResponse(
                status_code=400,
                content={"detail": f"Invalid detection engine. Must be one of: {', '.join(engine_map.keys())}"}
            )
        engine_enum = engine_map[detection_engine]
        # Pass remove_words to the service call.
        result = await BatchDetectService.detect_entities_in_files(
            files=files,
            requested_entities=requested_entities,
            detection_engine=engine_enum,
            max_parallel_files=max_parallel_files,
            use_presidio=True,
            use_gemini=(detection_engine == "hybrid"),
            remove_words=remove_words
        )
        return JSONResponse(content=result)
    except Exception as e:
        log_error(f"[BATCH] Unhandled exception in batch detection: {str(e)} [operation_id={operation_id}]")
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "batch_detection", 500
        )
        return JSONResponse(status_code=status_code, content=error_response)

@router.post("/extract")
@memory_optimized(threshold_mb=50)
async def batch_extract_text(
        request: Request,
        files: List[UploadFile] = File(...),
        max_parallel_files: Optional[int] = Form(4)
):
    """
    Extract text from multiple PDF files in parallel.

    Uses the centralized batch processing service for efficient text extraction
    with optimized resource utilization and comprehensive error handling.
    """
    operation_id = f"batch_extract_{int(time.time())}"
    log_info(f"[BATCH] Starting batch text extraction [operation_id={operation_id}]")

    try:
        # Process using the batch processing service
        result = await BatchExtractService.batch_extract_text(
            files=files,
            max_parallel_files=max_parallel_files
        )

        return JSONResponse(content=result)

    except Exception as e:
        log_error(f"[BATCH] Unhandled exception in batch extraction: {str(e)} [operation_id={operation_id}]")
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "batch_extraction", 500
        )
        return JSONResponse(status_code=status_code, content=error_response)


@router.post("/redact")
@limiter.limit("3/minute")
@memory_optimized(threshold_mb=200)
async def batch_redact_documents(
        request: Request,
        background_tasks: BackgroundTasks,
        files: List[UploadFile] = File(...),
        redaction_mappings: str = Form(...),
        remove_images: bool = Form(False),
        max_parallel_files: Optional[int] = None
):
    """
    Apply redactions to multiple documents and return them as a ZIP file.

    Uses the centralized batch processing service for efficient document redaction
    with streaming response, background cleanup, and resource management.

    The `remove_images` parameter controls whether images in the documents
    should also be detected and redacted.
    """
    operation_id = f"batch_redact_{int(time.time())}"
    log_info(f"[BATCH] Starting batch redaction [operation_id={operation_id}]")

    try:
        # Process using the batch processing service, passing the remove_images flag.
        response = await BatchRedactService.batch_redact_documents(
            files=files,
            redaction_mappings=redaction_mappings,
            max_parallel_files=max_parallel_files,
            background_tasks=background_tasks,
            remove_images=remove_images
        )
        return response

    except Exception as e:
        log_error(f"[BATCH] Unhandled exception in batch redaction: {str(e)} [operation_id={operation_id}]")
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "batch_redaction", 500
        )
        return JSONResponse(status_code=status_code, content=error_response)


@router.post("/hybrid_detect")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=200)
async def batch_hybrid_detect_sensitive(
        request: Request,
        files: List[UploadFile] = File(...),
        requested_entities: Optional[str] = Form(None),
        use_presidio: bool = Form(True),
        use_gemini: bool = Form(True),
        use_gliner: bool = Form(False),
        max_parallel_files: Optional[int] = Form(4),
        remove_words: Optional[str] = Form(None)  # New parameter
):
    """
    Process multiple files using hybrid detection combining multiple engines.

    This endpoint combines multiple detection engines for comprehensive entity detection:
    - Presidio for structured entities like emails, phone numbers, etc.
    - Gemini for broader context-aware detection
    - GLiNER for specialized entity recognition (optional, more resource-intensive)

    Uses the centralized batch processing service with adaptive resource management.
    """
    operation_id = f"batch_hybrid_{int(time.time())}"
    log_info(f"[BATCH] Starting hybrid batch detection [operation_id={operation_id}]")

    try:
        # Validate that at least one engine is selected
        if not any([use_presidio, use_gemini, use_gliner]):
            return JSONResponse(
                status_code=400,
                content={"detail": "At least one detection engine must be selected"}
            )

        # Process using the batch processing service
        result = await BatchDetectService.detect_entities_in_files(
            files=files,
            requested_entities=requested_entities,
            detection_engine=EntityDetectionEngine.HYBRID,
            max_parallel_files=max_parallel_files,
            use_presidio=use_presidio,
            use_gemini=use_gemini,
            use_gliner=use_gliner,
            remove_words = remove_words
        )

        return JSONResponse(content=result)

    except Exception as e:
        log_error(f"[BATCH] Unhandled exception in hybrid detection: {str(e)} [operation_id={operation_id}]")
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "batch_hybrid_detection", 500
        )
        return JSONResponse(status_code=status_code, content=error_response)