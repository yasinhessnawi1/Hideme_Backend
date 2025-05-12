"""
This module defines machine learning based sensitive information detection endpoints.
It supports three detection modes:
  - Presidio detection using Microsoft Presidio NER.
  - GLiNER detection using specialized entity recognition with memory monitoring.
  - HIDEME detection using specialized entity recognition with memory monitoring.
Each endpoint logs its operations and handles errors securely via SecurityAwareErrorHandler.
The endpoints are rate-limited and optimized for memory usage, and they delegate detection tasks
to MashinLearningService. This design ensures secure and efficient processing of uploaded files
for sensitive data detection.
"""

import time
from typing import Optional

from fastapi import APIRouter, File, UploadFile, Form, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

from backend.app.services.machine_learning_service import MashinLearningService
from backend.app.utils.constant.constant import JSON_MEDIA_TYPE
from backend.app.utils.logging.logger import log_info, log_warning
from backend.app.utils.system_utils.memory_management import (
    memory_optimized,
    memory_monitor,
)
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.helpers.json_helper import validate_threshold_score

# Configure the rate limiter using the client's remote address as the key.
limiter = Limiter(key_func=get_remote_address)
# Create an API router instance for the machine learning endpoints.
router = APIRouter()


@router.post("/detect")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=75)
async def presidio_detect_sensitive(
    request: Request,
    file: UploadFile = File(...),
    requested_entities: Optional[str] = Form(None),
    remove_words: Optional[str] = Form(None),
    threshold: Optional[float] = Form(None),
) -> JSONResponse:
    """
    Detect sensitive information using Microsoft Presidio NER with enhanced security.

    Parameters:
        request (Request): The incoming HTTP request.
        file (UploadFile): The file uploaded by the client for processing.
        requested_entities (Optional[str]): Optional comma-separated entities to detect.
        remove_words (Optional[str]): Optional comma-separated words to remove from the mapping.
        threshold (Optional[float]): Confidence threshold (expected between 0.00 and 1.00) for filtering detection results.

    Returns:
        JSONResponse: A JSON response containing the detection results, or a secure error response if an exception occurs.
    """
    # Begin threshold validation in a try block.
    try:
        # Validate the threshold value using the JSON helper.
        validate_threshold_score(threshold)
    except Exception as e:
        # Handle exceptions during threshold validation securely.
        error_info = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_presidio_sensitive", endpoint=str(request.url)
        )
        # Retrieve the HTTP status code from the error information (default to 500).
        status = error_info.get("status_code", 500)
        # Return a JSONResponse with the sanitized error information.
        return JSONResponse(status_code=status, content=error_info)

    # Generate a unique operation ID based on the current timestamp.
    operation_id = f"presidio_detect_{int(time.time())}"
    # Log the start of the Presidio detection processing with the generated operation ID.
    log_info(
        f"[ML] Starting Presidio detection processing [operation_id={operation_id}]"
    )
    # Initialize the machine learning service with 'presidio' as the detector type.
    service = MashinLearningService(detector_type="presidio")
    try:
        # Call the detection service's asynchronous detect method with the provided parameters.
        result = await service.detect(
            file, requested_entities, operation_id, remove_words, threshold
        )
        # Wrap the model dump in JSONResponse:
        return JSONResponse(
            content=result.model_dump(exclude_none=True), media_type=JSON_MEDIA_TYPE
        )
    except Exception as e:
        # Log a warning if an exception occurs during the detection process.
        log_warning(
            f"[ML] Exception in Presidio detection: {str(e)} [operation_id={operation_id}]"
        )
        # Handle the exception securely using SecurityAwareErrorHandler.
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_presidio_router", resource_id=str(request.url)
        )
        # Retrieve the error status code, defaulting to 500 if not available.
        status = error_response.get("status_code", 500)
        # Return a JSONResponse with the secure error response.
        return JSONResponse(content=error_response, status_code=status)


@router.post("/gl_detect")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=200)
async def gliner_detect_sensitive_entities(
    request: Request,
    file: UploadFile = File(...),
    requested_entities: Optional[str] = Form(None),
    remove_words: Optional[str] = Form(None),
    threshold: Optional[float] = Form(None),
) -> JSONResponse:
    """
    Detect sensitive information using GLiNER with enhanced security and specialized entity recognition.

    Parameters:
        request (Request): The incoming HTTP request.
        file (UploadFile): The file uploaded by the client for processing.
        requested_entities (Optional[str]): Optional comma-separated entities to detect.
        remove_words (Optional[str]): Optional comma-separated words to remove.
        threshold (Optional[float]): Confidence threshold for filtering detection results.

    Returns:
        JSONResponse: A JSON response containing the detection results, or a secure error response if an exception occurs.
    """
    # Begin threshold validation in a try block.
    try:
        # Validate the threshold value using the JSON helper.
        validate_threshold_score(threshold)
    except Exception as e:
        # Handle any exceptions during threshold validation securely.
        error_info = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_gliner_sensitive_entities", endpoint=str(request.url)
        )
        # Retrieve the HTTP status code from the error information (default to 500).
        status = error_info.get("status_code", 500)
        # Return a JSONResponse with the sanitized error information.
        return JSONResponse(status_code=status, content=error_info)

    # Generate a unique operation ID based on the current timestamp.
    operation_id = f"gliner_detect_{int(time.time())}"
    # Log the start of the GLiNER detection processing with the generated operation ID.
    log_info(f"[ML] Starting GLiNER detection processing [operation_id={operation_id}]")
    try:
        # Retrieve the current memory usage percentage.
        current_memory_usage = memory_monitor.get_memory_usage()
        # Check if current memory usage is above 85% and log a warning if so.
        if current_memory_usage > 85:
            log_warning(
                f"[ML] High memory pressure ({current_memory_usage:.1f}%), may impact GLiNER performance [operation_id={operation_id}]"
            )
        # Initialize the machine learning service with 'gliner' as the detector type.
        service = MashinLearningService(detector_type="gliner")
        # Call the detection service's asynchronous detect method with the provided parameters.
        result = await service.detect(
            file, requested_entities, operation_id, remove_words, threshold
        )
        # Wrap the model dump in JSONResponse:
        return JSONResponse(
            content=result.model_dump(exclude_none=True), media_type=JSON_MEDIA_TYPE
        )
    except Exception as e:
        # Log a warning if an exception occurs during the detection process.
        log_warning(
            f"[ML] Exception in GLiNER detection: {str(e)} [operation_id={operation_id}]"
        )
        # Handle the exception securely using SecurityAwareErrorHandler.
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_gliner_router", resource_id=str(request.url)
        )
        # Retrieve the error status code (default to 500 if not found).
        status = error_response.get("status_code", 500)
        # Return a JSONResponse with the secure error response.
        return JSONResponse(content=error_response, status_code=status)


@router.post("/hm_detect")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=200)
async def hideme_detect_sensitive_entities(
    request: Request,
    file: UploadFile = File(...),
    requested_entities: Optional[str] = Form(None),
    remove_words: Optional[str] = Form(None),
    threshold: Optional[float] = Form(None),
) -> JSONResponse:
    """
    Detect sensitive information using HIDEME with enhanced security and specialized entity recognition.

    Parameters:
        request (Request): The incoming HTTP request.
        file (UploadFile): The file uploaded for processing.
        requested_entities (Optional[str]): Optional comma-separated entities to detect.
        remove_words (Optional[str]): Optional words to remove from the mapping.
        threshold (Optional[float]): Confidence threshold for filtering detection results.

    Returns:
        JSONResponse: A JSON response containing the detection results, or a secure error response if an exception occurs.
    """
    # Begin threshold validation in a try block.
    try:
        # Validate the threshold value using the helper function.
        validate_threshold_score(threshold)
    except Exception as e:
        # Handle any exceptions during threshold validation securely.
        error_info = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_hideme_sensitive_entities", endpoint=str(request.url)
        )
        # Retrieve the HTTP status code from the error information (default to 500).
        status = error_info.get("status_code", 500)
        # Return a JSONResponse with the sanitized error information.
        return JSONResponse(status_code=status, content=error_info)

    # Generate a unique operation ID based on the current timestamp.
    operation_id = f"hideme_detect_{int(time.time())}"
    # Log the start of the HIDEME detection processing with the generated operation ID.
    log_info(f"[ML] Starting HIDEME detection processing [operation_id={operation_id}]")
    try:
        # Retrieve the current memory usage percentage.
        current_memory_usage = memory_monitor.get_memory_usage()
        # Check if current memory usage is above 85% and log a warning if so.
        if current_memory_usage > 85:
            log_warning(
                f"[ML] High memory pressure ({current_memory_usage:.1f}%), may impact HIDEME performance [operation_id={operation_id}]"
            )
        # Initialize the machine learning service with 'hideme' as the detector type.
        service = MashinLearningService(detector_type="hideme")
        # Call the detection service's asynchronous detect method with the provided parameters.
        result = await service.detect(
            file, requested_entities, operation_id, remove_words, threshold
        )
        # Wrap the model dump in JSONResponse:
        return JSONResponse(
            content=result.model_dump(exclude_none=True), media_type=JSON_MEDIA_TYPE
        )
    except Exception as e:
        # Log a warning if an exception occurs during HIDEME detection.
        log_warning(
            f"[ML] Exception in HIDEME detection: {str(e)} [operation_id={operation_id}]"
        )
        # Handle the exception securely using SecurityAwareErrorHandler.
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_hideme_router", resource_id=str(request.url)
        )
        # Retrieve the error status code (default to 500 if not available).
        status = error_response.get("status_code", 500)
        # Return a JSONResponse with the secure error response.
        return JSONResponse(content=error_response, status_code=status)
