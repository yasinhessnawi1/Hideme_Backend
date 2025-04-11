"""
This module defines machine learning based sensitive information detection endpoints.
It supports two detection modes:
  - Presidio detection using Microsoft Presidio NER.
  - GLiNER detection using specialized entity recognition with memory monitoring.
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
from backend.app.utils.logging.logger import log_info, log_warning
from backend.app.utils.system_utils.memory_management import memory_optimized, memory_monitor
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.helpers.json_helper import validate_threshold_score

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


@router.post("/detect")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=75)
async def presidio_detect_sensitive(
        request: Request,
        file: UploadFile = File(...),
        requested_entities: Optional[str] = Form(None),
        remove_words: Optional[str] = Form(None),
        threshold: Optional[float] = Form(None)
) -> JSONResponse:
    """
    Detect sensitive information using Microsoft Presidio NER with enhanced security.

    This endpoint processes an uploaded file using the Presidio detection engine.
    Optionally, it accepts:
      - requested_entities: A comma-separated list of entities to detect.
      - remove_words: A comma-separated string of words to remove from the redaction mapping.
      - threshold: A numeric threshold (expected between 0.00 and 1.00) to filter detection results.

    Parameters:
        request (Request): The incoming HTTP request.
        file (UploadFile): The file uploaded by the client for processing.
        requested_entities (Optional[str]): Optional comma-separated entities to detect.
        remove_words (Optional[str]): Optional comma-separated words to remove.
        threshold (Optional[float]): Numeric threshold for filtering detection results (e.g. 0.85).

    Returns:
        JSONResponse: A JSON response containing the detection results, or a secure error response if an exception occurs.
    """
    # Begin threshold validation in a try block.
    try:
        # Validate the threshold value using the JSON helper.
        validate_threshold_score(threshold)
    except Exception as e:
        # Handle any exceptions during threshold validation securely.
        error_info = SecurityAwareErrorHandler.handle_safe_error(e, "api_presidio_sensitive", endpoint=str(request.url))
        # Retrieve the HTTP status code from the error information, default to 500 if not found.
        status = error_info.get("status_code", 500)
        # Return a JSONResponse with the sanitized error information.
        return JSONResponse(status_code=status, content=error_info)

    # Generate a unique operation ID based on the current timestamp.
    operation_id = f"presidio_detect_{int(time.time())}"
    # Log the start of Presidio detection processing along with the operation ID.
    log_info(f"[ML] Starting Presidio detection processing [operation_id={operation_id}]")
    # Initialize the machine learning service with 'presidio' as the detector type.
    service = MashinLearningService(detector_type="presidio")
    # Begin the detection process in a try block.
    try:
        # Call the detection service's asynchronous detect method with provided parameters.
        result = await service.detect(file, requested_entities, operation_id, remove_words, threshold)
        # Return the detection result.
        return result
    except Exception as e:
        # Log a warning if an exception occurs during detection.
        log_warning(f"[ML] Exception in Presidio detection: {str(e)} [operation_id={operation_id}]")
        # Securely handle the exception using SecurityAwareErrorHandler.
        error_response = SecurityAwareErrorHandler.handle_safe_error(e, "api_presidio_router",
                                                                     resource_id=str(request.url))
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
        threshold: Optional[float] = Form(None)
) -> JSONResponse:
    """
    Detect sensitive information using GLiNER with enhanced security and specialized entity recognition.

    This endpoint processes an uploaded file using the GLiNER detection engine.
    Optionally, it accepts:
      - requested_entities: A comma-separated list of entities to detect.
      - remove_words: A comma-separated string of words to remove from the redaction mapping.
      - threshold: A numeric threshold (expected between 0.00 and 1.00) to filter detection results.

    Additionally, it monitors the current memory usage and logs a warning if usage exceeds 85%.

    Parameters:
        request (Request): The incoming HTTP request.
        file (UploadFile): The file uploaded by the client for processing.
        requested_entities (Optional[str]): Optional comma-separated entities to detect.
        remove_words (Optional[str]): Optional comma-separated words to remove.
        threshold (Optional[float]): Numeric threshold for filtering detection results.

    Returns:
        JSONResponse: A JSON response containing the detection results, or a secure error response if an exception occurs.
    """
    # Begin threshold validation in a try block.
    try:
        # Validate the threshold using the helper function.
        validate_threshold_score(threshold)
    except Exception as e:
        # Handle any exceptions during threshold validation securely.
        error_info = SecurityAwareErrorHandler.handle_safe_error(e, "api_gliner_sensitive_entities",
                                                                 endpoint=str(request.url))
        # Retrieve the HTTP status code from the error information, default to 500.
        status = error_info.get("status_code", 500)
        # Return a JSONResponse with the sanitized error information.
        return JSONResponse(status_code=status, content=error_info)

    # Generate a unique operation ID based on the current time.
    operation_id = f"gliner_detect_{int(time.time())}"
    # Log the start of GLiNER detection processing along with the generated operation ID.
    log_info(f"[ML] Starting GLiNER detection processing [operation_id={operation_id}]")
    # Begin the detection process in a try block.
    try:
        # Retrieve the current memory usage percentage.
        current_memory_usage = memory_monitor.get_memory_usage()
        # Check if memory usage is above 85% and log a warning if so.
        if current_memory_usage > 85:
            log_warning(
                f"[ML] High memory pressure ({current_memory_usage:.1f}%), may impact GLiNER performance [operation_id={operation_id}]")
        # Initialize the machine learning service with 'gliner' as the detector type.
        service = MashinLearningService(detector_type="gliner")
        # Call the detection service's asynchronous detect method with provided parameters.
        result = await service.detect(file, requested_entities, operation_id, remove_words, threshold)
        # Return the detection result.
        return result
    except Exception as e:
        # Log a warning if an exception occurs during GLiNER detection.
        log_warning(f"[ML] Exception in GLiNER detection: {str(e)} [operation_id={operation_id}]")
        # Securely handle the exception using SecurityAwareErrorHandler.
        error_response = SecurityAwareErrorHandler.handle_safe_error(e, "api_gliner_router",
                                                                     resource_id=str(request.url))
        # Retrieve the error status code, defaulting to 500 if not found.
        status = error_response.get("status_code", 500)
        # Return a JSONResponse with the sanitized error response.
        return JSONResponse(content=error_response, status_code=status)
