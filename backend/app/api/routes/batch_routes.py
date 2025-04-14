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

    Parameters:
        request (Request): The incoming HTTP request.
        files (List[UploadFile]): A list of files to be processed.
        requested_entities (Optional[str]): Comma-separated entities to detect.
        detection_engine (Optional[str]): The detection engine to use (e.g., 'presidio', 'gemini').
        max_parallel_files (Optional[int]): Maximum number of concurrent file processes.
        remove_words (Optional[str]): Comma-separated words to remove from content.
        threshold (Optional[float]): Confidence threshold (0.00 to 1.00) for filtering detection results.

    Returns:
        JSONResponse: JSON response with detection results or an error response.
    """
    # Try block to validate the threshold value.
    try:
        # Call helper to validate the threshold score.
        validate_threshold_score(threshold)
    except HTTPException as e:
        # Handle threshold validation errors securely.
        error_info = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_sensitive", endpoint=str(request.url)
        )
        # Retrieve status code from error information.
        status = error_info.get("status_code", 500)
        # Return a JSON error response with the validation error details.
        return JSONResponse(
            content=error_info,
            status_code=status,
            media_type="application/json"
        )

    # Generate a unique operation ID using the current timestamp.
    operation_id = f"batch_detect_{int(time.time())}"
    # Log the start of the batch detection process.
    log_info(f"[BATCH] Starting batch entity detection [operation_id={operation_id}]")
    try:
        # Map detection engine names to their corresponding enum values.
        engine_map = {
            "presidio": EntityDetectionEngine.PRESIDIO,
            "gemini": EntityDetectionEngine.GEMINI,
            "gliner": EntityDetectionEngine.GLINER,
            "hideme": EntityDetectionEngine.HIDEME,
            "hybrid": EntityDetectionEngine.HYBRID
        }
        # Check if the provided detection engine is valid.
        if detection_engine not in engine_map:
            # Return an error response for an invalid detection engine.
            return JSONResponse(
                status_code=400,
                content={"detail": f"Invalid detection engine. Must be one of: {', '.join(engine_map.keys())}"}
            )
        # Retrieve the enum corresponding to the provided detection engine.
        engine_enum = engine_map[detection_engine]
        # Call the batch detection service to process the files with given parameters.
        result = await BatchDetectService.detect_entities_in_files(
            files=files,
            requested_entities=requested_entities,
            detection_engine=engine_enum,
            max_parallel_files=max_parallel_files,
            remove_words=remove_words,
            threshold=threshold
        )
        # Return the result in a JSON response.
        return JSONResponse(content=result)
    except Exception as e:
        # Log any unhandled exceptions with the operation ID.
        log_error(f"[BATCH] Unhandled exception in batch detection: {str(e)} [operation_id={operation_id}]")
        # Handle the exception securely and prepare a sanitized error message.
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_hybrid", resource_id=str(request.url)
        )
        # Get the status code for the error response.
        status = error_response.get("status_code", 500)
        # Return the error response in JSON format.
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
        use_hideme: bool = Form(False),
        max_parallel_files: Optional[int] = Form(4),
        remove_words: Optional[str] = Form(None),
        threshold: Optional[float] = Form(None)
) -> JSONResponse:
    """
    Process multiple files using a hybrid detection approach with threshold-based filtering.

    Parameters:
        request (Request): The incoming HTTP request.
        files (List[UploadFile]): A list of files for detection.
        requested_entities (Optional[str]): Comma-separated entities to detect.
        use_presidio (bool): Flag to enable the Presidio detection engine.
        use_gemini (bool): Flag to enable the Gemini detection engine.
        use_gliner (bool): Flag to enable the GLiNER detection engine.
        use_hideme (bool): Flag to enable the HideMe detection engine.
        max_parallel_files (Optional[int]): Maximum number of files to process concurrently.
        remove_words (Optional[str]): Comma-separated words to remove from the file content.
        threshold (Optional[float]): Numeric threshold for filtering detection results.

    Returns:
        JSONResponse: JSON response with the detection results or an error response.
    """
    # Attempt to validate the threshold value.
    try:
        # Validate the threshold value using the helper function.
        validate_threshold_score(threshold)
    except HTTPException as e:
        # Handle the threshold validation exception securely.
        error_info = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_hybrid_sensitive", endpoint=str(request.url)
        )
        # Extract status code from error information.
        status = error_info.get("status_code", 500)
        # Return a JSON error response with the validation error details.
        return JSONResponse(
            content=error_info,
            status_code=status,
            media_type="application/json"
        )

    # Create a unique operation ID using the current timestamp.
    operation_id = f"batch_hybrid_{int(time.time())}"
    # Log the initiation of hybrid batch detection.
    log_info(f"[BATCH] Starting hybrid batch detection [operation_id={operation_id}]")
    try:
        # Check if at least one detection engine is enabled.
        if not any([use_presidio, use_gemini, use_gliner, use_hideme]):
            # Return an error response if no detection engine is selected.
            return JSONResponse(
                status_code=400,
                content={"detail": "At least one detection engine must be selected"}
            )
        # Call the batch detection service using hybrid detection configuration.
        result = await BatchDetectService.detect_entities_in_files(
            files=files,
            requested_entities=requested_entities,
            detection_engine=EntityDetectionEngine.HYBRID,
            max_parallel_files=max_parallel_files,
            use_presidio=use_presidio,
            use_gemini=use_gemini,
            use_gliner=use_gliner,
            use_hideme=use_hideme,
            remove_words=remove_words,
            threshold=threshold
        )
        # Return the detection results as a JSON response.
        return JSONResponse(content=result)
    except Exception as e:
        # Log any unhandled exceptions with the operation ID.
        log_error(f"[BATCH] Unhandled exception in hybrid detection: {str(e)} [operation_id={operation_id}]")
        # Securely handle the exception and prepare a sanitized error message.
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_hybrid", resource_id=str(request.url)
        )
        # Retrieve the appropriate status code for the error response.
        status = error_response.get("status_code", 500)
        # Return the sanitized error response as JSON.
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
        files (List[UploadFile]): List of PDF files to be searched.
        search_terms (str): String of search terms (each word is searched individually).
        case_sensitive (bool): Flag indicating if the search is case-sensitive.
        ai_search (bool): Flag to enable AI-powered search features.
        max_parallel_files (Optional[int]): Maximum number of files to process concurrently.

    Returns:
        JSONResponse: JSON response containing matching results or an error response.
    """
    # Generate a unique operation ID using the current timestamp.
    operation_id = f"batch_search_{int(time.time())}"
    # Log the start of the batch text search operation.
    log_info(f"[BATCH] Starting batch text search [operation_id={operation_id}]")
    try:
        # Delegate the search operation to the BatchSearchService.
        result = await BatchSearchService.batch_search_text(
            files=files,
            search_terms=search_terms,
            max_parallel_files=max_parallel_files,
            case_sensitive=case_sensitive,
            ai_search=ai_search
        )
        # Return the search results as a JSON response.
        return JSONResponse(content=result)
    except Exception as e:
        # Log any exceptions that occur during the search.
        log_error(f"[BATCH] Unhandled exception in batch search: {str(e)} [operation_id={operation_id}]")
        # Handle the exception securely using the error handler.
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_search", resource_id=str(request.url)
        )
        # Get the error response's status code.
        status = error_response.get("status_code", 500)
        # Return the sanitized error response as JSON.
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

    Parameters:
        request (Request): The incoming HTTP request.
        files (List[UploadFile]): List of PDF files to be processed.
        bounding_box (str): JSON string representing a bounding box with keys: "x0", "y0", "x1", and "y1".

    Returns:
        JSONResponse: JSON response with the search results or an error response.
    """
    # Attempt to parse the bounding_box JSON string.
    try:
        # Convert the bounding_box string into a JSON object.
        bbox = json.loads(bounding_box)
        # Define the required keys for a valid bounding box.
        required_keys = {"x0", "y0", "x1", "y1"}
        # Verify that the bbox is a dictionary and contains all required keys.
        if not isinstance(bbox, dict) or not required_keys.issubset(bbox.keys()):
            # Raise an HTTPException if the bounding box format is invalid.
            raise HTTPException(
                status_code=400,
                detail="Bounding box must be a JSON object with keys: x0, y0, x1, and y1"
            )
    except Exception as e:
        # Log the error encountered during bounding box parsing.
        log_error(f"Error parsing bounding box: {str(e)}")
        # Return a JSON response indicating invalid bounding box format.
        return JSONResponse(status_code=400, content={"detail": "Invalid bounding box format."})

    # Generate a unique operation ID for the batch find words request.
    operation_id = f"batch_find_words_{int(time.time())}"
    # Log the start of the batch find words operation.
    log_info(f"[BATCH] Starting batch find words operation [operation_id={operation_id}]")
    try:
        # Delegate finding words by bounding box to the BatchSearchService.
        result = await BatchSearchService.find_words_by_bbox(
            files=files,
            bounding_box=bbox,
            operation_id=operation_id
        )
        # Return the results as a JSON response.
        return JSONResponse(content=result)
    except Exception as e:
        # Log any unhandled exceptions that occur during processing.
        log_error(f"[BATCH] Unhandled exception in batch find words: {str(e)} [operation_id={operation_id}]")
        # Securely handle the exception and prepare a sanitized error response.
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_find_words", resource_id=str(request.url)
        )
        # Retrieve the appropriate status code from the error response.
        status = error_response.get("status_code", 500)
        # Return the sanitized error response as JSON.
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

    Parameters:
        request (Request): The incoming HTTP request.
        background_tasks (BackgroundTasks): Instance to schedule background tasks.
        files (List[UploadFile]): List of documents to be redacted.
        redaction_mappings (str): Redaction mappings as a string.
        remove_images (bool): Flag indicating whether to remove images from the documents.
        max_parallel_files (Optional[int]): Maximum number of files to process concurrently.

    Returns:
        Response: A response containing the redacted documents as a ZIP file or an error response.
    """
    # Generate a unique operation ID using the current timestamp.
    operation_id = f"batch_redact_{int(time.time())}"
    # Log the initiation of the batch redaction process.
    log_info(f"[BATCH] Starting batch redaction [operation_id={operation_id}]")
    try:
        # Call the batch redaction service to process documents for redaction.
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
        # Log any unhandled exceptions that occur during redaction.
        log_error(f"[BATCH] Unhandled exception in batch redaction: {str(e)} [operation_id={operation_id}]")
        # Handle the error securely to prevent exposing sensitive information.
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_redact", resource_id=str(request.url)
        )
        # Retrieve the error response status code.
        status = error_response.get("status_code", 500)
        # Return a JSON response containing the sanitized error details.
        return JSONResponse(content=error_response, status_code=status)
