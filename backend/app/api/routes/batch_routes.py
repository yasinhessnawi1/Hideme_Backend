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
  - batch_find_words_by_bbox: Finding words in PDF files based on a specified bounding box.
  - batch_redact_documents: Redacting sensitive information in multiple documents.

Each endpoint now supports three modes of input handling:
  1. Session-authenticated mode: headers `session_key` + `api_key_id`
  2. Raw-API-key mode: header `raw_api_key`
  3. Public mode: no decryption/encryption
"""
import base64
import json
import time
from typing import Optional, List

from fastapi import APIRouter, File, UploadFile, Form, Header, BackgroundTasks, Request, Response, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse, StreamingResponse

from backend.app.entity_detection import EntityDetectionEngine
from backend.app.services import BatchDetectService, BatchRedactService
from backend.app.services.batch_search_service import BatchSearchService
from backend.app.utils.helpers.json_helper import validate_threshold_score
from backend.app.utils.logging.logger import log_info, log_error
from backend.app.utils.security.session_encryption import session_manager
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.system_utils.memory_management import memory_optimized

# Instantiate a limiter keyed by the client's IP address
limiter = Limiter(key_func=get_remote_address)
# Instantiate the FastAPI router
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
        threshold: Optional[float] = Form(None),
        session_key: Optional[str] = Header(None),
        api_key_id: Optional[str] = Header(None),
        raw_api_key: Optional[str] = Header(None),
) -> JSONResponse:
    """
    Batch-sensitive entity detection endpoint.

    This endpoint accepts multiple file uploads, optional detection parameters, and three modes of encryption:
      1. Session-authenticated (session_key + api_key_id)
      2. Raw-API-key (raw_api_key)
      3. Public (no decryption/encryption)

    Steps:
      1. Conditionally decrypt inputs via SessionEncryptionManager.
      2. Validate the confidence threshold.
      3. Dispatch to the BatchDetectService.
      4. Wrap and optionally encrypt the response.

    Parameters:
      - request: Incoming HTTP request object.
      - files: List of files to analyze.
      - requested_entities: Comma-separated entity types to detect.
      - detection_engine: Which detection engine to use.
      - max_parallel_files: Max concurrent file analyzes.
      - remove_words: Comma-separated words to strip before analysis.
      - threshold: Confidence cutoff (0.0–1.0) for filtering results.
      - session_key: Bearer token header for session mode.
      - api_key_id: API key identifier header for session mode.
      - raw_api_key: Standalone API key header for raw mode.

    Returns:
      - JSONResponse containing detection results, encrypted if an AES key was used.
    """
    # Decrypt inputs (files + form fields) or pass through unchanged
    files, decrypted_fields, api_key = await session_manager.prepare_inputs(
        files,
        {"requested_entities": requested_entities, "remove_words": remove_words},
        session_key,
        api_key_id,
        raw_api_key,
    )
    # Replace form values with decrypted ones if available
    requested_entities = decrypted_fields.get("requested_entities")
    remove_words = decrypted_fields.get("remove_words")

    # Validate the optional threshold parameter
    try:
        validate_threshold_score(threshold)
    except HTTPException as e:
        # Securely handle invalid threshold errors
        error_info = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_sensitive", endpoint=str(request.url)
        )
        return JSONResponse(content=error_info, status_code=error_info.get("status_code", 400))

    # Generate a unique ID for logging this batch operation
    operation_id = f"batch_detect_{int(time.time())}"
    # Log the start of the batch detection process
    log_info(f"[BATCH] Starting batch entity detection [operation_id={operation_id}]")

    try:
        # Map string engine names to enum values
        engine_map = {
            "presidio": EntityDetectionEngine.PRESIDIO,
            "gemini": EntityDetectionEngine.GEMINI,
            "gliner": EntityDetectionEngine.GLINER,
            "hideme": EntityDetectionEngine.HIDEME,
            "hybrid": EntityDetectionEngine.HYBRID,
        }
        # Return error if an unsupported engine is specified
        if detection_engine not in engine_map:
            return JSONResponse(
                status_code=400,
                content={"detail": f"Invalid detection engine. Choose one of: {', '.join(engine_map)}"}
            )

        # Invoke the detection service with all parameters
        result = await BatchDetectService.detect_entities_in_files(
            files=files,
            requested_entities=requested_entities,
            detection_engine=engine_map[detection_engine],
            max_parallel_files=max_parallel_files,
            remove_words=remove_words,
            threshold=threshold,
        )
        # Wrap the result, encrypting if an AES key is present
        return session_manager.wrap_response(result.model_dump(exclude_none=True), api_key)

    except Exception as e:
        # Log unexpected exceptions for debugging/audit
        log_error(f"[BATCH] Unhandled exception in batch detection: {e} [operation_id={operation_id}]")
        # Securely sanitize and return the error
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_sensitive", resource_id=str(request.url)
        )
        return JSONResponse(content=error_response, status_code=error_response.get("status_code", 500))


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
        threshold: Optional[float] = Form(None),
        session_key: Optional[str] = Header(None),
        api_key_id: Optional[str] = Header(None),
        raw_api_key: Optional[str] = Header(None),
) -> JSONResponse:
    """
    Batch-hybrid entity detection endpoint.

    This endpoint processes multiple files using a hybrid detection approach. It supports:
      - Session-authenticated mode (session_key + api_key_id)
      - Raw-API-key mode (raw_api_key)
      - Public mode (no encryption/decryption)

    Detection engines (Presidio, Gemini, GLiNER, HideMe) can be toggled via boolean flags.
    A confidence 'threshold' may be provided to filter results.

    Parameters:
      - request: Incoming HTTP request object.
      - files: Uploaded files to analyze.
      - requested_entities: Comma-separated list of entities to detect.
      - use_presidio: Enable Presidio engine.
      - use_gemini: Enable Gemini engine.
      - use_gliner: Enable GLiNER engine.
      - use_hideme: Enable HideMe engine.
      - max_parallel_files: Maximum concurrent file analyzes.
      - remove_words: Words to remove before detection.
      - threshold: Confidence cutoff (0.0–1.0).
      - session_key: Header for session-authenticated mode.
      - api_key_id: Header for session-authenticated mode.
      - raw_api_key: Header for raw-API-key mode.

    Returns:
      - JSONResponse containing detection results, encrypted if an AES key was used.
    """
    # decrypt inputs or pass through unchanged
    files, decrypted_fields, api_key = await session_manager.prepare_inputs(
        files,
        {"requested_entities": requested_entities, "remove_words": remove_words},
        session_key,
        api_key_id,
        raw_api_key,
    )
    # Override input parameters with decrypted values if provided
    requested_entities = decrypted_fields.get("requested_entities")
    remove_words = decrypted_fields.get("remove_words")

    # validate the 'threshold' parameter
    try:
        validate_threshold_score(threshold)
    except HTTPException as e:
        # Securely format validation errors
        error_info = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_hybrid_sensitive", endpoint=str(request.url)
        )
        return JSONResponse(content=error_info, status_code=error_info.get("status_code", 400))

    # log the start of the hybrid detection run
    operation_id = f"batch_hybrid_{int(time.time())}"
    log_info(f"[BATCH] Starting hybrid batch detection [operation_id={operation_id}]")

    try:
        # Ensure at least one detection engine is enabled
        if not any([use_presidio, use_gemini, use_gliner, use_hideme]):
            return JSONResponse(
                status_code=400,
                content={"detail": "Select at least one detection engine"}
            )

        # call the batch detection service in hybrid mode
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
            threshold=threshold,
        )
        # Step 5: wrap and encrypt response if an AES key is present
        return session_manager.wrap_response(result.model_dump(exclude_none=True), api_key)

    except Exception as e:
        # Log any unexpected exceptions
        log_error(f"[BATCH] Unhandled exception in hybrid detection: {e} [operation_id={operation_id}]")
        # Securely sanitize and handle the error
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_hybrid", resource_id=str(request.url)
        )
        return JSONResponse(
            content=error_response,
            status_code=error_response.get("status_code", 500),
        )


@router.post("/search")
@memory_optimized(threshold_mb=50)
async def batch_search_text(
        request: Request,
        files: List[UploadFile] = File(...),
        search_terms: str = Form(...),
        case_sensitive: bool = Form(False),
        ai_search: bool = Form(False),
        max_parallel_files: Optional[int] = Form(4),
        session_key: Optional[str] = Header(None),
        api_key_id: Optional[str] = Header(None),
        raw_api_key: Optional[str] = Header(None),
) -> JSONResponse:
    """
    Search for specific terms in multiple PDF files in parallel.

    This endpoint supports three modes:
      - Session-authenticated: headers `session_key` + `api_key_id`
      - Raw-API-key: header `raw_api_key`
      - Public mode: no encryption/decryption

    It accepts plain or encrypted inputs and returns results encrypted
    if decryption was applied to any input.

    Parameters:
      - request: Incoming HTTP request object.
      - files: List of PDF files to search.
      - search_terms: Space-separated words to search within files.
      - case_sensitive: Whether the search should be case-sensitive.
      - ai_search: Whether to enable AI-powered search enhancements.
      - max_parallel_files: Maximum number of files to process concurrently.
      - session_key: Optional header for session-authenticated mode.
      - api_key_id: Optional header for session-authenticated mode.
      - raw_api_key: Optional header for raw-API-key mode.

    Returns:
      - JSONResponse: Contains search results, possibly encrypted.
    """
    # Decrypt or passthrough files and form fields based on provided headers
    files, decrypted_fields, api_key = await session_manager.prepare_inputs(
        files,
        {"search_terms": search_terms},
        session_key,
        api_key_id,
        raw_api_key,
    )
    # Override the search_terms with decrypted value if decryption occurred
    search_terms = decrypted_fields.get("search_terms")

    # Generate a unique operation ID using the current timestamp
    operation_id = f"batch_search_{int(time.time())}"
    # Log the start of the batch search operation
    log_info(f"[BATCH] Starting batch text search [operation_id={operation_id}]")

    try:
        # Delegate the search operation to the BatchSearchService
        result = await BatchSearchService.batch_search_text(
            files=files,
            search_terms=search_terms,
            max_parallel_files=max_parallel_files,
            case_sensitive=case_sensitive,
            ai_search=ai_search,
        )
        # Wrap the result in a JSONResponse, encrypting if an AES key is present
        return session_manager.wrap_response(result.model_dump(exclude_none=True), api_key)

    except Exception as e:
        # Log any unhandled exceptions for debugging
        log_error(f"[BATCH] Unhandled exception in batch search: {e} [operation_id={operation_id}]")
        # Securely handle the exception without exposing sensitive details
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_search", resource_id=str(request.url)
        )
        # Return a sanitized error JSONResponse with appropriate status code
        return JSONResponse(
            content=error_response,
            status_code=error_response.get("status_code", 500),
        )


@router.post("/find_words")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=50)
async def batch_find_words_by_bbox(
        request: Request,
        files: List[UploadFile] = File(...),
        bounding_box: str = Form(...),
        session_key: Optional[str] = Header(None),
        api_key_id: Optional[str] = Header(None),
        raw_api_key: Optional[str] = Header(None),
) -> JSONResponse:
    """
    Find words in multiple PDF files based on a provided bounding box.

    Supports three modes:
      1. Session-authenticated: headers `session_key` + `api_key_id`
      2. Raw-API-key:           header `raw_api_key`
      3. Public:                no decryption/encryption

    Parses the bounding box from JSON, delegates to the word-finding service,
    and returns results encrypted if any input was decrypted.

    Parameters:
      - request: the incoming HTTP request.
      - files: list of PDF files to process.
      - bounding_box: JSON string with numeric keys "x0", "y0", "x1", "y1".
      - session_key: optional bearer token for session mode.
      - api_key_id: optional API key ID for session mode.
      - raw_api_key: optional standalone API key for raw mode.

    Returns:
      - JSONResponse containing found words (possibly encrypted).
    """
    # decrypt or passthrough inputs based on provided headers
    files, decrypted_fields, api_key = await session_manager.prepare_inputs(
        files,
        {"bounding_box": bounding_box},
        session_key,
        api_key_id,
        raw_api_key
    )
    # override bounding_box with decrypted value if available
    bounding_box = decrypted_fields.get("bounding_box")

    # attempt to parse the bounding_box JSON string
    try:
        bbox = json.loads(bounding_box)
        required_keys = {"x0", "y0", "x1", "y1"}
        # validate presence of all required keys
        if not isinstance(bbox, dict) or not required_keys.issubset(bbox):
            raise HTTPException(status_code=400, detail="Invalid bounding box keys")
    except HTTPException:
        # propagate HTTPExceptions unchanged
        raise
    except Exception as e:
        # log parse errors and return a client error
        log_error(f"[BATCH] Error parsing bounding box: {e}")
        return JSONResponse(status_code=400, content={"detail": "Invalid bounding box format."})

    # log the start of the operation with a unique ID
    operation_id = f"batch_find_words_{int(time.time())}"
    log_info(f"[BATCH] Starting batch find words [operation_id={operation_id}]")

    try:
        # delegate to the BatchSearchService for word extraction
        result = await BatchSearchService.find_words_by_bbox(
            files=files,
            bounding_box=bbox,
            operation_id=operation_id
        )
        # wrap and optionally encrypt the response
        return session_manager.wrap_response(result.model_dump(exclude_none=True), api_key)

    except Exception as e:
        # log any unexpected exceptions
        log_error(f"[BATCH] Unhandled exception in batch find words: {e} [operation_id={operation_id}]")
        # securely handle the error without leaking internals
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_find_words", resource_id=str(request.url)
        )
        # return sanitized error JSONResponse
        return JSONResponse(
            content=error_response,
            status_code=error_response.get("status_code", 500),
        )


@router.post("/redact")
@limiter.limit("3/minute")
@memory_optimized(threshold_mb=200)
async def batch_redact_documents(
        request: Request,
        background_tasks: BackgroundTasks,
        files: List[UploadFile] = File(...),
        redaction_mappings: str = Form(...),
        remove_images: bool = Form(False),
        max_parallel_files: Optional[int] = None,
        session_key: Optional[str] = Header(None),
        api_key_id: Optional[str] = Header(None),
        raw_api_key: Optional[str] = Header(None),
) -> Response:
    """
    Apply redactions to one or more PDF documents and return the results as a ZIP archive.

    Supports three modes of operation:
      1. Session mode
         - Supply both `session-key` and `api-key-id` headers
         - All inputs (PDF bytes + form fields) are expected AES-GCM encrypted
         - Response ZIP is AES-GCM encrypted and base64-wrapped
      2. Raw-API-key mode
         - Supply `raw-api-key` header only
         - Inputs MAY be encrypted; we try to decrypt, but if decryption fails we treat them as plaintext
         - If any decryption succeeded, the response ZIP will be encrypted; otherwise it streams raw
      3. Public mode
         - No encryption/decryption at all; everything is plaintext

    **Parameters**
    - request            – the incoming FastAPI request (for logging/context)
    - background_tasks   – FastAPI’s BackgroundTasks to register any post-response clean-up
    - files              – one or more uploaded PDF files
    - redaction_mappings – a JSON string (or encrypted blob) describing exactly which regions to redact
    - remove_images      – whether to strip images out of the PDF in addition to text redactions
    - max_parallel_files – optional cap on concurrent per-file workers
    - session_key        – (header `session-key`) bearer token for session-authenticated mode
    - api_key_id         – (header `api-key-id`) specifies which per-tenant AES key to fetch
    - raw_api_key        – (header `raw-api-key`) standalone API key for raw-mode decryption

    **Returns**
    - On encryption mode:
      ```json
      { "encrypted_data": "<base64-url AES-GCM-ciphertext>" }
      ```
    - On public mode: streams a standard ZIP file of redacted PDFs
    """

    # Decrypt or passthrough all inputs based on headers
    files, decrypted_fields, api_key = await session_manager.prepare_inputs(
        files,
        {"redaction_mappings": redaction_mappings},
        session_key,
        api_key_id,
        raw_api_key
    )
    # If session/raw decryption yielded a plaintext mapping, use that
    redaction_mappings = decrypted_fields.get("redaction_mappings", redaction_mappings)

    # Generate a unique ID to tag all log messages for this request
    operation_id = f"batch_redact_{int(time.time())}"
    log_info(f"[BATCH] Starting batch redaction [operation_id={operation_id}]")

    try:
        # Delegate the heavy lifting to the service layer
        # Returns either a FileResponse or StreamingResponse wrapping the ZIP
        response_obj: Response = await BatchRedactService.batch_redact_documents(
            files=files,
            redaction_mappings=redaction_mappings,
            max_parallel_files=max_parallel_files,
            background_tasks=background_tasks,
            remove_images=remove_images
        )

        # If we obtained an AES key, we must encrypt the raw ZIP bytes
        if api_key:
            raw_zip = b""
            if isinstance(response_obj, StreamingResponse):
                # consume every chunk from the streaming iterator
                async for chunk in response_obj.body_iterator:
                    raw_zip += chunk
            else:
                # normal Response has .body already loaded
                raw_zip = response_obj.body

            # AES-GCM encrypt then base64-URL-encode
            cipher = session_manager.encrypt_response(raw_zip, api_key)
            b64 = base64.urlsafe_b64encode(cipher).decode()

            # return as a small JSON blob
            return JSONResponse({"encrypted_data": b64})

        # Otherwise (public mode), just forward the raw ZIP response
        return response_obj

    except Exception as e:
        # Log and sanitize any unexpected errors
        log_error(f"[BATCH] Unhandled exception in batch redaction: {e} [operation_id={operation_id}]")
        err = SecurityAwareErrorHandler.handle_safe_error(e, "api_redact", resource_id=str(request.url))
        return JSONResponse(content=err, status_code=err.get("status_code", 500))
