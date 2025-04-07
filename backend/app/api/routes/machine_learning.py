"""
This router defines machine learning based sensitive information detection endpoints.
It supports two detection modes:
  - Presidio detection using Microsoft Presidio NER.
  - GLiNER detection using specialized entity recognition with memory monitoring.
Each endpoint logs its operation and handles errors securely via SecurityAwareErrorHandler.
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

# Configure rate limiter using the client's remote address.
limiter = Limiter(key_func=get_remote_address)
# Create the API router.
router = APIRouter()


@router.post("/detect")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=75)
async def presidio_detect_sensitive(
        request: Request,
        file: UploadFile = File(...),
        requested_entities: Optional[str] = Form(None),
        remove_words: Optional[str] = Form(None)
) -> JSONResponse:
    """
    Detect sensitive information using Microsoft Presidio NER with enhanced security.

    This endpoint processes an uploaded file using the Presidio detection engine.
    Optionally, it accepts:
      - requested_entities: A comma-separated list of entities to detect.
      - remove_words: A comma-separated string of words to remove from the redaction mapping.

    Parameters:
        request (Request): The incoming HTTP request.
        file (UploadFile): The file uploaded by the client for processing.
        requested_entities (Optional[str]): Optional comma-separated entities to detect.
        remove_words (Optional[str]): Optional comma-separated words to remove.

    Returns:
        JSONResponse: A JSON response containing the detection results, or a secure error response if an exception occurs.
    """
    # Generate a unique operation ID using the current timestamp.
    operation_id = f"presidio_detect_{int(time.time())}"
    log_info(f"[ML] Starting Presidio detection processing [operation_id={operation_id}]")
    # Initialize the machine learning service with 'presidio' as the detector type.
    service = MashinLearningService(detector_type="presidio")
    try:
        # Call the detection service and pass all required parameters.
        result = await service.detect(file, requested_entities, operation_id, remove_words)
        # Return the service result as a JSON response.
        return result
    except Exception as e:
        # Log a warning including the operation ID.
        log_warning(f"[ML] Exception in Presidio detection: {str(e)} [operation_id={operation_id}]")
        # Create a secure error response using the error handling utility.
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "presidio_detection", 500, resource_id=str(request.url)
        )
        return JSONResponse(status_code=status_code, content=error_response)


@router.post("/gl_detect")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=200)  # GLiNER requires more memory.
async def gliner_detect_sensitive_entities(
        request: Request,
        file: UploadFile = File(...),
        requested_entities: Optional[str] = Form(None),
        remove_words: Optional[str] = Form(None)
) -> JSONResponse:
    """
    Detect sensitive information using GLiNER with enhanced security and specialized entity recognition.

    This endpoint processes an uploaded file using the GLiNER detection engine.
    Optionally, it accepts:
      - requested_entities: A comma-separated list of entities to detect.
      - remove_words: A comma-separated string of words to remove from the redaction mapping.

    Additionally, it monitors the current memory usage and logs a warning if usage exceeds 85%.

    Parameters:
        request (Request): The incoming HTTP request.
        file (UploadFile): The file uploaded by the client for processing.
        requested_entities (Optional[str]): Optional comma-separated entities to detect.
        remove_words (Optional[str]): Optional comma-separated words to remove.

    Returns:
        JSONResponse: A JSON response containing the detection results, or a secure error response if an exception occurs.
    """
    # Generate a unique operation ID using the current timestamp.
    operation_id = f"gliner_detect_{int(time.time())}"
    log_info(f"[ML] Starting GLiNER detection processing [operation_id={operation_id}]")
    try:
        # Check the current memory usage using the memory monitor.
        current_memory_usage = memory_monitor.get_memory_usage()
        # Log a warning if memory usage exceeds 85%.
        if current_memory_usage > 85:
            log_warning(
                f"[ML] High memory pressure ({current_memory_usage:.1f}%), may impact GLiNER performance [operation_id={operation_id}]")
        # Initialize the machine learning service with 'gliner' as the detector type.
        service = MashinLearningService(detector_type="gliner")
        # Call the detection service.
        result = await service.detect(file, requested_entities, operation_id, remove_words)
        # Return the detection result.
        return result
    except Exception as e:
        # Log a warning if an exception occurs.
        log_warning(f"[ML] Exception in GLiNER detection: {str(e)} [operation_id={operation_id}]")
        # Generate a secure error response using SecurityAwareErrorHandler.
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "gliner_detection", 500, resource_id=str(request.url)
        )
        return JSONResponse(status_code=status_code, content=error_response)
