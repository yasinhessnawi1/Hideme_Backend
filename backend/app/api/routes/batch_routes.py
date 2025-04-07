"""
Optimized batch processing routes using the unified service architecture.

This module provides API endpoints for batch processing operations, leveraging the
centralized BatchProcessingService and ensuring proper separation of concerns between
route handlers and business logic.
"""

import time
from typing import List, Optional

from fastapi import APIRouter, File, UploadFile, Form, BackgroundTasks, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

from backend.app.entity_detection import EntityDetectionEngine
from backend.app.services import BatchDetectService, BatchRedactService
from backend.app.services.batch_search_service import BatchSearchService
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.logging.logger import log_info, log_error
from backend.app.utils.system_utils.memory_management import memory_optimized

# Configure rate limiter using client's remote address.
limiter = Limiter(key_func=get_remote_address)
# Create the API router.
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
        remove_words: Optional[str] = Form(None)
) -> JSONResponse:
    """
    Process multiple files for entity detection in parallel.

    This endpoint receives a list of files to process along with optional parameters:
      - requested_entities: A comma-separated string indicating which entities to detect.
      - detection_engine: The detection engine to use (e.g., 'presidio', 'gemini', 'gliner', or 'hybrid').
      - max_parallel_files: The maximum number of files to process concurrently.
      - remove_words: Optional comma-separated words to remove from the file content before processing.

    Returns:
        JSONResponse: A JSON response containing the detection results as returned by BatchDetectService.
                      If an error occurs, a secure error response is returned.
    """
    # Create a unique operation identifier based on current time.
    operation_id = f"batch_detect_{int(time.time())}"
    log_info(f"[BATCH] Starting batch entity detection [operation_id={operation_id}]")
    try:
        # Map string engine names to enum values.
        engine_map = {
            "presidio": EntityDetectionEngine.PRESIDIO,
            "gemini": EntityDetectionEngine.GEMINI,
            "gliner": EntityDetectionEngine.GLINER,
            "hybrid": EntityDetectionEngine.HYBRID
        }
        # Validate the provided detection engine.
        if detection_engine not in engine_map:
            return JSONResponse(
                status_code=400,
                content={"detail": f"Invalid detection engine. Must be one of: {', '.join(engine_map.keys())}"}
            )
        # Get the corresponding enum value.
        engine_enum = engine_map[detection_engine]
        # Call the BatchDetectService, passing the remove_words parameter.
        result = await BatchDetectService.detect_entities_in_files(
            files=files,
            requested_entities=requested_entities,
            detection_engine=engine_enum,
            max_parallel_files=max_parallel_files,
            use_presidio=True,
            use_gemini=(detection_engine == "hybrid"),
            remove_words=remove_words
        )
        # Return the detection results as a JSON response.
        return JSONResponse(content=result)
    except Exception as e:
        # Log the exception with operation details.
        log_error(f"[BATCH] Unhandled exception in batch detection: {str(e)} [operation_id={operation_id}]")
        # Create a secure error response, including the request URL.
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "batch_detection", 500, resource_id=str(request.url)
        )
        return JSONResponse(status_code=status_code, content=error_response)


@router.post("/search")
@memory_optimized(threshold_mb=50)
async def batch_search_text(
        request: Request,
        files: List[UploadFile] = File(...),
        search_terms: str = Form(...),
        case_sensitive: bool = Form(False),
        ai_search: bool = Form(False),
        max_parallel_files: Optional[int] = Form(4)
) -> JSONResponse:
    """
    Search for specific terms in multiple PDF files in parallel.

    Parameters:
        request (Request): The incoming HTTP request.
        files (List[UploadFile]): A list of PDF files to search.
        search_terms (str): A single string containing the search terms. If multiple words are provided,
                            each word is searched individually.
        case_sensitive (bool): Indicates whether the search should be case-sensitive.
        ai_search (bool): Flag to enable AI-powered search features.
        max_parallel_files (Optional[int]): The maximum number of files to process concurrently.

    Returns:
        JSONResponse: A JSON response containing detailed matching results, or a secure error response if an exception occurs.
    """
    # Generate a unique operation identifier.
    operation_id = f"batch_search_{int(time.time())}"
    log_info(f"[BATCH] Starting batch text search [operation_id={operation_id}]")
    try:
        # Call the BatchSearchService with provided parameters.
        result = await BatchSearchService.batch_search_text(
            files=files,
            search_terms=search_terms,
            max_parallel_files=max_parallel_files,
            case_sensitive=case_sensitive,
            ai_search=ai_search
        )
        # Return search results.
        return JSONResponse(content=result)
    except Exception as e:
        # Log the error.
        log_error(f"[BATCH] Unhandled exception in batch search: {str(e)} [operation_id={operation_id}]")
        # Create a secure error response including the request URL.
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "batch_search", 500, resource_id=str(request.url)
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
) -> Response:
    """
    Apply redactions to multiple documents and return them as a ZIP file.

    Uses the centralized batch redaction service for efficient document redaction with streaming response,
    background cleanup, and resource management.

    Parameters:
        request (Request): The incoming HTTP request.
        background_tasks (BackgroundTasks): A BackgroundTasks instance to schedule cleanup tasks.
        files (List[UploadFile]): A list of documents to be redacted.
        redaction_mappings (str): A string representing the redaction mappings to apply.
        remove_images (bool): A flag indicating whether images in the documents should also be redacted.
        max_parallel_files (Optional[int]): Optional maximum number of files to process concurrently.

    Returns:
        Response: A response containing the redacted documents as a ZIP file, or a secure error response if an exception occurs.
    """
    # Generate a unique operation ID.
    operation_id = f"batch_redact_{int(time.time())}"
    log_info(f"[BATCH] Starting batch redaction [operation_id={operation_id}]")
    try:
        # Call the BatchRedactService with the provided parameters.
        response_obj = await BatchRedactService.batch_redact_documents(
            files=files,
            redaction_mappings=redaction_mappings,
            max_parallel_files=max_parallel_files,
            background_tasks=background_tasks,
            remove_images=remove_images
        )
        # Return the response (e.g., ZIP file).
        return response_obj
    except Exception as e:
        # Log the exception.
        log_error(f"[BATCH] Unhandled exception in batch redaction: {str(e)} [operation_id={operation_id}]")
        # Create a secure error response, including the request URL.
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "batch_redaction", 500, resource_id=str(request.url)
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
        use_gemini: bool = Form(False),
        use_gliner: bool = Form(False),
        max_parallel_files: Optional[int] = Form(4),
        remove_words: Optional[str] = Form(None)
) -> JSONResponse:
    """
    Process multiple files using a hybrid detection approach combining multiple engines.

    This endpoint combines multiple detection engines for comprehensive entity detection:
      - Presidio for structured entities like emails and phone numbers.
      - Gemini for broader, context-aware detection.
      - GLiNER for specialized entity recognition (optional and more resource-intensive).

    Parameters:
        request (Request): The incoming HTTP request.
        files (List[UploadFile]): A list of files to process.
        requested_entities (Optional[str]): Comma-separated string of entities to detect.
        use_presidio (bool): Flag to enable the Presidio detection engine.
        use_gemini (bool): Flag to enable the Gemini detection engine.
        use_gliner (bool): Flag to enable the GLiNER detection engine.
        max_parallel_files (Optional[int]): The maximum number of files to process concurrently.
        remove_words (Optional[str]): Optional comma-separated words to remove before detection.

    Returns:
        JSONResponse: A JSON response containing the detection results, or a secure error response if an exception occurs.
    """
    # Generate a unique operation ID.
    operation_id = f"batch_hybrid_{int(time.time())}"
    log_info(f"[BATCH] Starting hybrid batch detection [operation_id={operation_id}]")
    try:
        # Validate that at least one detection engine is selected.
        if not any([use_presidio, use_gemini, use_gliner]):
            return JSONResponse(
                status_code=400,
                content={"detail": "At least one detection engine must be selected"}
            )
        # Call the BatchDetectService using the hybrid detection approach.
        result = await BatchDetectService.detect_entities_in_files(
            files=files,
            requested_entities=requested_entities,
            detection_engine=EntityDetectionEngine.HYBRID,
            max_parallel_files=max_parallel_files,
            use_presidio=use_presidio,
            use_gemini=use_gemini,
            use_gliner=use_gliner,
            remove_words=remove_words
        )
        # Return the detection results.
        return JSONResponse(content=result)
    except Exception as e:
        # Log the error along with the operation ID.
        log_error(f"[BATCH] Unhandled exception in hybrid detection: {str(e)} [operation_id={operation_id}]")
        # Create a secure error response using the error handling utility, passing the request URL.
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "batch_hybrid_detection", 500, resource_id=str(request.url)
        )
        return JSONResponse(status_code=status_code, content=error_response)
