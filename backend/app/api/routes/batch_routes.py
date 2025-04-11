"""
Optimized batch processing routes using the unified service architecture.

This module provides API endpoints for batch processing operations, leveraging the centralized service architecture.
These endpoints separate route handling from business logic and support various detection engines. In addition to the
usual parameters, the detection endpoints now accept a 'threshold' parameter (a value between 0.00 and 1.00). This
parameter is used to filter detection results so that only entities with a confidence score greater than or equal to
the threshold are retained.

The module includes endpoints for:
  - batch_detect_sensitive: Batch processing of files for sensitive data detection using one detection engine.
  - batch_hybrid_detect_sensitive: Batch processing using a hybrid detection approach (multiple engines).
  - batch_search_text: Searching for specific text strings in multiple files.
  - batch_redact_documents: Redacting sensitive information in multiple documents.
  - batch_find_words_by_bbox: Finding words in PDF files based on a specified bounding box.
"""

import json
import time
from fastapi import HTTPException
from typing import List, Optional

from fastapi import APIRouter, File, UploadFile, Form, BackgroundTasks, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

# Import service modules for batch detection and redaction.
from backend.app.entity_detection import EntityDetectionEngine
from backend.app.services import BatchDetectService, BatchRedactService
from backend.app.services.batch_search_service import BatchSearchService
from backend.app.utils.helpers.json_helper import validate_threshold_score
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.logging.logger import log_info, log_error
from backend.app.utils.system_utils.memory_management import memory_optimized

# Configure the rate limiter to use the client's remote address as the key.
limiter = Limiter(key_func=get_remote_address)
# Create the API router instance for batch processing endpoints.
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
        remove_words: Optional[str] = Form(None),
        threshold: Optional[float] = Form(None)
) -> JSONResponse:
    """
    Process multiple files for entity detection in parallel with threshold-based filtering.

    This endpoint receives a list of files along with optional parameters:
      - requested_entities: A comma-separated string indicating which entities to detect.
      - detection_engine: The detection engine to use (e.g., 'presidio', 'gemini', 'gliner', or 'hybrid').
      - max_parallel_files: The maximum number of files to process concurrently.
      - remove_words: Optional comma-separated words to remove from the file content before processing.
      - threshold: Optional numeric threshold (0.00 to 1.00) for filtering detection results.
                   Only entities with a confidence score greater than or equal to this value are retained.
                   If not provided, a default (typically 0.85) will be used in the business logic.

    Returns:
        JSONResponse: A JSON response containing the detection results as returned by BatchDetectService.
                      In case of an error, a secure error response is returned.
    """
    try:
        # Validate the provided threshold value.
        validate_threshold_score(threshold)  # May raise HTTPException for invalid values.
    except HTTPException as e:
        # Securely handle threshold validation errors.
        error_info = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_sensitive", endpoint=str(request.url)
        )  # Get a sanitized error message.
        status = error_info.get("status_code", 500)  # Determine response status.
        # Return an error response in JSON format.
        return JSONResponse(
            content=error_info,
            status_code=status,
            media_type="application/json"
        )

    # Create a unique operation ID using the current timestamp.
    operation_id = f"batch_detect_{int(time.time())}"
    log_info(f"[BATCH] Starting batch entity detection [operation_id={operation_id}]")
    try:
        # Map detection engine names to their corresponding enum values.
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

        # Retrieve the corresponding engine enum.
        engine_enum = engine_map[detection_engine]

        # Call the BatchDetectService to process the files with the provided parameters.
        result = await BatchDetectService.detect_entities_in_files(
            files=files,
            requested_entities=requested_entities,
            detection_engine=engine_enum,
            max_parallel_files=max_parallel_files,
            use_presidio=True,
            use_gemini=(detection_engine == "hybrid"),
            remove_words=remove_words,
            threshold=threshold
        )
        # Return the detection result in a JSONResponse.
        return JSONResponse(content=result)
    except Exception as e:
        # Log unhandled exceptions with the operation ID.
        log_error(f"[BATCH] Unhandled exception in batch detection: {str(e)} [operation_id={operation_id}]")
        # Securely handle the error and prepare a sanitized error response.
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_hybrid", resource_id=str(request.url)
        )
        status = error_response.get("status_code", 500)  # Set status code.
        # Return the sanitized error response.
        return JSONResponse(content=error_response, status_code=status)


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
        remove_words: Optional[str] = Form(None),
        threshold: Optional[float] = Form(None)  # New threshold parameter.
) -> JSONResponse:
    """
    Process multiple files using a hybrid detection approach with threshold-based filtering.

    This endpoint combines multiple detection engines for comprehensive entity detection:
      - Presidio for structured entities (e.g., emails, phone numbers).
      - Gemini for broader, context-aware detection.
      - GLiNER for specialized entity recognition (optional and more resource-intensive).

    Optional parameters include:
      - requested_entities: A comma-separated string of entities to detect.
      - use_presidio, use_gemini, use_gliner: Boolean flags to enable specific detection engines.
      - max_parallel_files: The maximum number of files to process concurrently.
      - remove_words: Optional comma-separated words to remove before detection.
      - threshold: Optional numeric threshold (0.00 to 1.00) for filtering detection results.
                   Only entities with a confidence score greater than or equal to the threshold are retained.

    Returns:
        JSONResponse: A JSON response containing the detection results as returned by BatchDetectService.
                      If an error occurs, a secure error response is returned.
    """
    try:
        # Validate the threshold value.
        validate_threshold_score(threshold)
    except HTTPException as e:
        # Securely handle threshold validation error.
        error_info = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_hybrid_sensitive", endpoint=str(request.url)
        )
        status = error_info.get("status_code", 500)
        # Return a JSON error response.
        return JSONResponse(
            content=error_info,
            status_code=status,
            media_type="application/json"
        )

    # Generate a unique operation ID.
    operation_id = f"batch_hybrid_{int(time.time())}"
    log_info(f"[BATCH] Starting hybrid batch detection [operation_id={operation_id}]")
    try:
        # Validate that at least one detection engine is enabled.
        if not any([use_presidio, use_gemini, use_gliner]):
            return JSONResponse(
                status_code=400,
                content={"detail": "At least one detection engine must be selected"}
            )
        # Use the BatchDetectService with the hybrid approach.
        result = await BatchDetectService.detect_entities_in_files(
            files=files,
            requested_entities=requested_entities,
            detection_engine=EntityDetectionEngine.HYBRID,
            max_parallel_files=max_parallel_files,
            use_presidio=use_presidio,
            use_gemini=use_gemini,
            use_gliner=use_gliner,
            remove_words=remove_words,
            threshold=threshold
        )
        # Return the result in a JSON response.
        return JSONResponse(content=result)
    except Exception as e:
        # Log the exception with operation ID.
        log_error(f"[BATCH] Unhandled exception in hybrid detection: {str(e)} [operation_id={operation_id}]")
        # Securely handle the error.
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_hybrid", resource_id=str(request.url)
        )
        status = error_response.get("status_code", 500)
        # Return the sanitized error response.
        return JSONResponse(content=error_response, status_code=status)


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
    # Generate a unique operation ID.
    operation_id = f"batch_search_{int(time.time())}"
    log_info(f"[BATCH] Starting batch text search [operation_id={operation_id}]")
    try:
        # Delegate the batch text search to the BatchSearchService.
        result = await BatchSearchService.batch_search_text(
            files=files,
            search_terms=search_terms,
            max_parallel_files=max_parallel_files,
            case_sensitive=case_sensitive,
            ai_search=ai_search
        )
        # Return the search result.
        return JSONResponse(content=result)
    except Exception as e:
        # Log any unhandled exception.
        log_error(f"[BATCH] Unhandled exception in batch search: {str(e)} [operation_id={operation_id}]")
        # Securely handle the error.
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_search", resource_id=str(request.url)
        )
        status = error_response.get("status_code", 500)
        # Return the secure error response.
        return JSONResponse(content=error_response, status_code=status)


@router.post("/find_words")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=50)
async def batch_find_words_by_bbox(
        request: Request,
        files: List[UploadFile] = File(...),
        bounding_box: str = Form(...)
) -> JSONResponse:
    """
    Find words in multiple PDF files based on the provided bounding box.

    This endpoint accepts:
      - files: A list of PDF files to process.
      - bounding_box: A JSON string representing a bounding box. It should be a JSON object with keys:
                      "x0", "y0", "x1", and "y1" (all float values) that define the coordinate region.

    The processing logic for file reading, text extraction, and locating words within the bounding box
    is delegated to BatchSearchService.

    Returns:
        JSONResponse: A JSON response containing the batch search results, or a secure error response if an exception occurs.
    """
    try:
        # Parse the bounding_box JSON string.
        bbox = json.loads(bounding_box)
        # Define the required keys for the bounding box.
        required_keys = {"x0", "y0", "x1", "y1"}
        # Verify that bbox is a dict and contains all required keys.
        if not isinstance(bbox, dict) or not required_keys.issubset(bbox.keys()):
            raise HTTPException(
                status_code=400,
                detail="Bounding box must be a JSON object with keys: x0, y0, x1, and y1"
            )
    except Exception as e:
        # Log the error parsing the bounding box.
        log_error(f"Error parsing bounding box: {str(e)}")
        # Return a JSON error response with status 400.
        return JSONResponse(status_code=400, content={"detail": "Invalid bounding box format."})

    # Generate a unique operation ID for this processing request.
    operation_id = f"batch_find_words_{int(time.time())}"
    log_info(f"[BATCH] Starting batch find words operation [operation_id={operation_id}]")
    try:
        # Delegate the task of finding words by bounding box to BatchSearchService.
        result = await BatchSearchService.find_words_by_bbox(
            files=files,
            bounding_box=bbox,
            operation_id=operation_id
        )
        # Return the result.
        return JSONResponse(content=result)
    except Exception as e:
        # Log any exceptions encountered during processing.
        log_error(f"[BATCH] Unhandled exception in batch find words: {str(e)} [operation_id={operation_id}]")
        # Securely handle the error.
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_find_words", resource_id=str(request.url)
        )
        status = error_response.get("status_code", 500)
        # Return the secure error response.
        return JSONResponse(content=error_response, status_code=status)


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
        remove_images (bool): Flag indicating whether images in the documents should also be redacted.
        max_parallel_files (Optional[int]): Optional maximum number of files to process concurrently.

    Returns:
        Response: A response containing the redacted documents as a ZIP file, or a secure error response if an exception occurs.
    """
    # Generate a unique operation ID for the batch redaction.
    operation_id = f"batch_redact_{int(time.time())}"
    log_info(f"[BATCH] Starting batch redaction [operation_id={operation_id}]")
    try:
        # Invoke the BatchRedactService to process the redaction.
        response_obj = await BatchRedactService.batch_redact_documents(
            files=files,
            redaction_mappings=redaction_mappings,
            max_parallel_files=max_parallel_files,
            background_tasks=background_tasks,
            remove_images=remove_images
        )
        # Return the response object (e.g., ZIP file response).
        return response_obj
    except Exception as e:
        # Log any unhandled exceptions with the operation ID.
        log_error(f"[BATCH] Unhandled exception in batch redaction: {str(e)} [operation_id={operation_id}]")
        # Securely handle the error to prevent leaking sensitive information.
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_redact", resource_id=str(request.url)
        )
        status = error_response.get("status_code", 500)
        # Return a JSON response with the sanitized error information.
        return JSONResponse(content=error_response, status_code=status)
