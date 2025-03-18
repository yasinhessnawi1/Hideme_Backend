"""
Refactored machine learning entity detection routes that utilize shared code and utilities.

This module provides API endpoints for detecting sensitive information in uploaded files
using different machine learning models. It implements consistent error handling and
leverages shared processing logic to maintain code quality and reliability.

Enhanced with timeout lock handling for shared resources to prevent deadlocks.
"""
import time
from typing import Optional

from fastapi import APIRouter, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.services.initialization_service import initialization_service
from backend.app.utils.common_detection import process_common_detection
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.memory_management import memory_optimized
from backend.app.utils.synchronization_utils import AsyncTimeoutLock, LockPriority
from backend.app.utils.logger import log_info, log_warning, log_error

# Configure rate limiter
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

# Create shared lock for ML detection endpoints
_ml_resource_lock = AsyncTimeoutLock("ml_detection_lock", priority=LockPriority.HIGH)


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
    identification numbers with high precision. Presidio excels at detecting structured
    PII patterns using a combination of regex patterns and machine learning models.

    Args:
        request: Request object for rate limiting
        file: The uploaded document file (PDF or text-based formats)
        requested_entities: Optional comma-separated list of entity types to detect
                           (if not provided, all supported entity types will be used)

    Returns:
        JSON with detected entities, anonymized text, and redaction mapping

    Raises:
        HTTPException: For invalid file formats, size limits, or processing errors
    """
    operation_id = f"presidio_detect_{int(time.time())}" if 'time' in globals() else "presidio_detect"

    try:
        log_info(f"[ML] Starting Presidio detection processing [operation_id={operation_id}]")
        return await process_common_detection(
            file=file,
            requested_entities=requested_entities,
            detector_type="presidio",
            get_detector_func=lambda entity_list: initialization_service.get_presidio_detector()
        )
    except HTTPException as e:
        # Pass through HTTP exceptions directly
        raise e
    except Exception as e:
        # Use security-aware error handling for generic exceptions
        log_error(f"[ML] Error in Presidio detection: {str(e)} [operation_id={operation_id}]")
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "presidio_detection", 500, file.filename if file else None
        )
        return JSONResponse(status_code=status_code, content=error_response)


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
    entity types that traditional NER systems might miss. GLiNER leverages transfer learning
    techniques to identify complex entities like medical conditions, financial instruments,
    and specialized identifiers.

    Args:
        request: Request object for rate limiting
        file: The uploaded document file (PDF or text-based formats)
        requested_entities: Optional comma-separated list of entity types to detect
                           (if not provided, default GLiNER entities will be used)

    Returns:
        JSON with detected entities, anonymized text, and redaction mapping

    Raises:
        HTTPException: For invalid file formats, size limits, or processing errors
    """
    operation_id = f"gliner_detect_{int(time.time())}" if 'time' in globals() else "gliner_detect"

    try:
        # Try to acquire GLiNER-specific lock for resource-intensive operation
        async with _ml_resource_lock.acquire_timeout(timeout=30.0) as acquired:
            if acquired:
                log_info(f"[ML] Acquired ML resource lock for GLiNER detection [operation_id={operation_id}]")
                return await process_common_detection(
                    file=file,
                    requested_entities=requested_entities,
                    detector_type="gliner",
                    get_detector_func=lambda entity_list: initialization_service.get_gliner_detector(entity_list)
                )
            else:
                log_warning(f"[ML] Failed to acquire ML resource lock for GLiNER detection [operation_id={operation_id}]")
                # Continue without lock as fallback
                return await process_common_detection(
                    file=file,
                    requested_entities=requested_entities,
                    detector_type="gliner",
                    get_detector_func=lambda entity_list: initialization_service.get_gliner_detector(entity_list)
                )
    except Exception as e:
        # Handle any lock-related errors or other exceptions
        log_error(f"[ML] Error in GLiNER detection: {str(e)} [operation_id={operation_id}]")
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "gliner_detection", 500, file.filename if file else None
        )
        return JSONResponse(status_code=status_code, content=error_response)