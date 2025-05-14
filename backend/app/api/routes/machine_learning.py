"""
This module defines machine learning based sensitive information detection endpoints.
It supports three detection modes:
  - Presidio detection using Microsoft Presidio NER.
  - GLiNER detection using specialized entity recognition with memory monitoring.
  - HIDEME detection using specialized entity recognition with memory monitoring.

Each endpoint:
  - Accepts encrypted input (files and form fields) in Session or Raw-API-Key mode.
  - Decrypts inputs via SessionEncryptionManager.
  - Delegates detection to MashinLearningService.
  - Wraps and optionally encrypts the response.
  - Handles errors securely using SecurityAwareErrorHandler.

All endpoints are rate-limited and memory-optimized.
"""

import time
from typing import Optional

from fastapi import APIRouter, File, UploadFile, Form, Request, Header
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

from backend.app.services.machine_learning_service import MashinLearningService
from backend.app.utils.logging.logger import log_info, log_warning
from backend.app.utils.security.session_encryption import session_manager
from backend.app.utils.system_utils.memory_management import (
    memory_optimized,
    memory_monitor,
)
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.helpers.json_helper import validate_threshold_score

# Set up rate limiting using client IP
limiter = Limiter(key_func=get_remote_address)

# FastAPI router for ML detection endpoints
router = APIRouter()


async def _handle_detection_request(
    *,
    detector_type: str,
    request: Request,
    file: UploadFile,
    requested_entities: Optional[str],
    remove_words: Optional[str],
    threshold: Optional[float],
    session_key: Optional[str],
    api_key_id: Optional[str],
    raw_api_key: Optional[str],
    memory_warn_threshold: float = 85.0,
) -> JSONResponse:
    """
    Unified handler for ML detection endpoints.

    Parameters:
        detector_type: "presidio", "gliner", or "hideme".
        request: FastAPI request object.
        file: The uploaded file.
        requested_entities: Comma-separated string of entity types.
        remove_words: Words to exclude from detection.
        threshold: Confidence filter (0.0–1.0).
        session_key: For session mode.
        api_key_id: For session mode.
        raw_api_key: For API-key mode.
        memory_warn_threshold: % threshold to log memory warning (default 85%).

    Returns:
        JSONResponse with detection results (encrypted if needed).
    """
    # Validate threshold
    try:
        validate_threshold_score(threshold)
    except Exception as e:
        error_info = SecurityAwareErrorHandler.handle_safe_error(
            e, f"api_{detector_type}_threshold", endpoint=str(request.url)
        )
        return JSONResponse(
            status_code=error_info.get("status_code", 500), content=error_info
        )

    # Decrypt input
    try:
        files, decrypted_fields, api_key = await session_manager.prepare_inputs(
            [file],
            {"requested_entities": requested_entities, "remove_words": remove_words},
            session_key,
            api_key_id,
            raw_api_key,
        )
    except Exception as e:
        error_info = SecurityAwareErrorHandler.handle_safe_error(
            e, f"api_{detector_type}_decrypt", endpoint=str(request.url)
        )
        return JSONResponse(
            status_code=error_info.get("status_code", 500), content=error_info
        )

    # Extract the decrypted file (first and only file)
    file = files[0]
    # Extract decrypted form field values
    requested_entities = decrypted_fields.get("requested_entities")
    remove_words = decrypted_fields.get("remove_words")

    # Create operation ID
    operation_id = f"{detector_type}_detect_{int(time.time())}"
    # Log the start of detection operation
    log_info(
        f"[ML] Starting {detector_type.upper()} detection [operation_id={operation_id}]"
    )

    # Optionally warn if memory pressure is high
    mem_usage = memory_monitor.get_memory_usage()
    if mem_usage > memory_warn_threshold:
        log_warning(
            f"[ML] High memory pressure ({mem_usage:.1f}%) during {detector_type.upper()} detection [operation_id={operation_id}]"
        )

    # Run detection using the machine learning service
    try:
        # Instantiate detection service with the selected engine
        service = MashinLearningService(detector_type=detector_type)
        # Call detection method with all required parameters
        result = await service.detect(
            file, requested_entities, operation_id, remove_words, threshold
        )
        # Wrap the response in encryption if input was encrypted
        return session_manager.wrap_response(
            result.model_dump(exclude_none=True), api_key
        )

    # Handle any runtime errors during detection
    except Exception as e:
        # Log and sanitize any unhandled error securely
        log_warning(
            f"[ML] Exception in {detector_type.upper()} detection: {e} [operation_id={operation_id}]"
        )
        error = SecurityAwareErrorHandler.handle_safe_error(
            e, f"api_{detector_type}_router", resource_id=str(request.url)
        )
        # Return a JSONResponse containing the sanitized error message.
        return JSONResponse(content=error, status_code=error.get("status_code", 500))


@router.post("/detect")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=75)
async def presidio_detect_sensitive(
    request: Request,
    file: UploadFile = File(...),
    requested_entities: Optional[str] = Form(None),
    remove_words: Optional[str] = Form(None),
    threshold: Optional[float] = Form(None),
    session_key: Optional[str] = Header(None),
    api_key_id: Optional[str] = Header(None),
    raw_api_key: Optional[str] = Header(None),
) -> JSONResponse:
    """
    Detect sensitive information using Microsoft Presidio.

    Accepts encrypted input in session/api-key mode and optionally encrypts output.

    Parameters:
        request: Incoming HTTP request.
        file: File to analyze.
        requested_entities: Comma-separated types to detect.
        remove_words: Words to exclude from detection.
        threshold: Optional float between 0.0 and 1.0.
        session_key: Session-based authentication header.
        api_key_id: API key ID (paired with session_key).
        raw_api_key: Raw API key (alternative to session mode).

    Returns:
        JSONResponse with encrypted or plaintext detection result.
    """
    return await _handle_detection_request(
        detector_type="presidio",
        request=request,
        file=file,
        requested_entities=requested_entities,
        remove_words=remove_words,
        threshold=threshold,
        session_key=session_key,
        api_key_id=api_key_id,
        raw_api_key=raw_api_key,
        memory_warn_threshold=85.0,
    )


@router.post("/gl_detect")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=200)
async def gliner_detect_sensitive_entities(
    request: Request,
    file: UploadFile = File(...),
    requested_entities: Optional[str] = Form(None),
    remove_words: Optional[str] = Form(None),
    threshold: Optional[float] = Form(None),
    session_key: Optional[str] = Header(None),
    api_key_id: Optional[str] = Header(None),
    raw_api_key: Optional[str] = Header(None),
) -> JSONResponse:
    """
    Detect sensitive information using GLiNER (memory-intensive).

    Accepts encrypted input in session/api-key mode and optionally encrypts output.

    Parameters:
        request: Incoming HTTP request.
        file: File to analyze.
        requested_entities: Comma-separated types to detect.
        remove_words: Words to exclude from detection.
        threshold: Optional float between 0.0 and 1.0.
        session_key: Session-based authentication header.
        api_key_id: API key ID (paired with session_key).
        raw_api_key: Raw API key (alternative to session mode).

    Returns:
        JSONResponse with encrypted or plaintext detection result.
    """
    return await _handle_detection_request(
        detector_type="gliner",
        request=request,
        file=file,
        requested_entities=requested_entities,
        remove_words=remove_words,
        threshold=threshold,
        session_key=session_key,
        api_key_id=api_key_id,
        raw_api_key=raw_api_key,
        memory_warn_threshold=85.0,
    )


@router.post("/hm_detect")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=200)
async def hideme_detect_sensitive_entities(
    request: Request,
    file: UploadFile = File(...),
    requested_entities: Optional[str] = Form(None),
    remove_words: Optional[str] = Form(None),
    threshold: Optional[float] = Form(None),
    session_key: Optional[str] = Header(None),
    api_key_id: Optional[str] = Header(None),
    raw_api_key: Optional[str] = Header(None),
) -> JSONResponse:
    """
    Detect sensitive information using HIDEME (memory-intensive).

    Accepts encrypted input in session/api-key mode and optionally encrypts output.

    Parameters:
        request: Incoming HTTP request.
        file: File to analyze.
        requested_entities: Comma-separated types to detect.
        remove_words: Words to exclude from detection.
        threshold: Optional float between 0.0 and 1.0.
        session_key: Session-based authentication header.
        api_key_id: API key ID (paired with session_key).
        raw_api_key: Raw API key (alternative to session mode).

    Returns:
        JSONResponse with encrypted or plaintext detection result.
    """
    return await _handle_detection_request(
        detector_type="hideme",
        request=request,
        file=file,
        requested_entities=requested_entities,
        remove_words=remove_words,
        threshold=threshold,
        session_key=session_key,
        api_key_id=api_key_id,
        raw_api_key=raw_api_key,
        memory_warn_threshold=85.0,
    )
