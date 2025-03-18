"""
Refactored machine learning entity detection routes that utilize shared code and utilities.

This module provides API endpoints for detecting sensitive information in uploaded files
using different machine learning models. It implements consistent error handling and
leverages shared processing logic to maintain code quality and reliability.

Enhanced with optimized timeout lock handling and exponential backoff for shared resources
to prevent deadlocks and improve concurrency.
"""
import asyncio
import random
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

# Create shared lock for ML detection endpoints with shorter timeout
# Reduced from 30.0 to 5.0 seconds
_ml_resource_lock = AsyncTimeoutLock("ml_detection_lock", priority=LockPriority.HIGH)

# Exponential backoff configuration
INITIAL_TIMEOUT = 2.0  # Start with a shorter initial timeout
MAX_TIMEOUT = 8.0      # Maximum timeout value
MAX_RETRIES = 3        # Maximum number of retry attempts


async def acquire_lock_with_backoff(operation_id: str, resource_name: str = "ML resource"):
    """
    Attempt to acquire the ML resource lock with exponential backoff.

    Args:
        operation_id: ID for the current operation for logging
        resource_name: Name of the resource for logging purposes

    Returns:
        Tuple of (acquired, context_manager) - If acquired is True,
        context_manager should be used in a with statement.
        If acquired is False, no lock was obtained.
    """
    timeout = INITIAL_TIMEOUT

    for attempt in range(MAX_RETRIES):
        try:
            # Add jitter to avoid thundering herd problem
            jitter = random.uniform(0, 0.5)
            current_timeout = min(timeout * (1.5 ** attempt) + jitter, MAX_TIMEOUT)

            log_info(f"[ML] Attempting to acquire {resource_name} lock (attempt {attempt+1}/{MAX_RETRIES}, "
                    f"timeout={current_timeout:.2f}s) [operation_id={operation_id}]")

            # Create the context manager with current timeout
            context = _ml_resource_lock.acquire_timeout(timeout=current_timeout)
            ctx_manager = await context.__aenter__()

            if ctx_manager:
                log_info(f"[ML] Successfully acquired {resource_name} lock on attempt {attempt+1} "
                        f"[operation_id={operation_id}]")
                # Return the context manager which the caller should use in a with statement
                return True, context

            log_warning(f"[ML] Failed to acquire {resource_name} lock on attempt {attempt+1} "
                       f"[operation_id={operation_id}]")

            # Release the failed context manager
            await context.__aexit__(None, None, None)

            # Add delay before retry with random jitter
            if attempt < MAX_RETRIES - 1:
                delay = 0.5 * (1.5 ** attempt) + random.uniform(0, 0.5)
                log_info(f"[ML] Waiting {delay:.2f}s before retry [operation_id={operation_id}]")
                await asyncio.sleep(delay)
        except Exception as e:
            log_warning(f"[ML] Error during lock acquisition attempt {attempt+1}: {str(e)} "
                       f"[operation_id={operation_id}]")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(0.5 * (1.5 ** attempt))

    log_warning(f"[ML] Failed to acquire {resource_name} lock after {MAX_RETRIES} attempts "
               f"[operation_id={operation_id}]")
    return False, None


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
        # Presidio is lightweight, so we don't need lock acquisition for it
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
        # Try to acquire GLiNER-specific lock with exponential backoff
        acquired, lock_ctx = await acquire_lock_with_backoff(
            operation_id=operation_id,
            resource_name="GLiNER"
        )

        if acquired:
            try:
                log_info(f"[ML] Processing with GLiNER detection using lock [operation_id={operation_id}]")
                return await process_common_detection(
                    file=file,
                    requested_entities=requested_entities,
                    detector_type="gliner",
                    get_detector_func=lambda entity_list: initialization_service.get_gliner_detector(entity_list)
                )
            finally:
                # Ensure lock is always released
                await lock_ctx.__aexit__(None, None, None)
        else:
            # Continue without lock as fallback if all retries failed
            log_warning(f"[ML] Processing GLiNER detection without lock after retry failure [operation_id={operation_id}]")

            # Check system load before proceeding without lock
            from backend.app.utils.memory_management import memory_monitor
            current_load = memory_monitor.get_memory_usage()

            if current_load > 85:
                # System under heavy load - return error rather than proceeding unsafely
                log_error(f"[ML] System under heavy load ({current_load}%), rejecting GLiNER request [operation_id={operation_id}]")
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "System is currently under heavy load. Please try again later.",
                        "retry_after": 30,
                        "operation_id": operation_id
                    }
                )

            # Proceed with fallback (without lock) only if system load is acceptable
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