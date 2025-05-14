"""
AI Detection API Route

This module defines the API endpoint for AI-based sensitive data detection.
It supports only two secure modes of input handling:
  1. Session-authenticated mode: requires `session_key` + `api_key_id` headers.
  2. Raw-API-key mode: requires a standalone `raw_api_key` header.

All decryption is performed using the SessionEncryptionManager.
Responses are optionally encrypted based on whether the input was encrypted.
"""

from typing import Optional

from fastapi import APIRouter, File, UploadFile, Form, Request, Header
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

from backend.app.services.ai_detect_service import AIDetectService
from backend.app.utils.constant.constant import JSON_MEDIA_TYPE
from backend.app.utils.helpers.json_helper import validate_threshold_score
from backend.app.utils.security.session_encryption import session_manager
from backend.app.utils.system_utils.memory_management import memory_optimized
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler

# Configure the rate limiter using the client's remote address.
limiter = Limiter(key_func=get_remote_address)
# Create an instance of APIRouter for the AI detection endpoints.
router = APIRouter()


@router.post("/detect")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=75)
async def ai_detect_sensitive(
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
    Detect sensitive information in a single uploaded file using AI-based detection.

    Supports two secure modes:
      1. Session-authenticated mode:
         - Requires `session_key` + `api_key_id`
         - Inputs must be AES-GCM encrypted and base64-url encoded
         - Response will be encrypted

      2. Raw-API-key mode:
         - Requires `raw_api_key` only
         - Inputs may be encrypted or plaintext
         - Response will be encrypted only if input was decrypted

    Parameters:
        request (Request): FastAPI request object for context and logging.
        file (UploadFile): The file to scan (can be encrypted).
        requested_entities (Optional[str]): Entity types to extract (comma-separated).
        remove_words (Optional[str]): Words to strip before analysis.
        threshold (Optional[float]): Confidence score filter (0.0 to 1.0).
        session_key (Optional[str]): Bearer token for session-authenticated mode.
        api_key_id (Optional[str]): API key ID to fetch AES decryption key.
        raw_api_key (Optional[str]): Raw AES key for standalone API-key mode.

    Returns:
        JSONResponse:
          - Plain JSON if public/plaintext.
          - {"encrypted_data": "<base64-encoded-ciphertext>"} if encryption is active.
    """
    try:
        # Decrypt uploaded file and form fields
        files, decrypted_fields, api_key = await session_manager.prepare_inputs(
            files=[file],
            form_fields={
                "requested_entities": requested_entities,
                "remove_words": remove_words,
            },
            session_key=session_key,
            api_key_id=api_key_id,
            raw_api_key=raw_api_key,
        )

        # Extract decrypted values
        file = files[0]
        requested_entities = decrypted_fields.get("requested_entities")
        remove_words = decrypted_fields.get("remove_words")

        # Validate threshold score format (0.0–1.0)
        validate_threshold_score(threshold)

        # Run the AI detection business logic
        result = await AIDetectService().detect(
            file=file,
            requested_entities=requested_entities,
            remove_words=remove_words,
            threshold=threshold,
        )

        # Wrap and conditionally encrypt response
        return session_manager.wrap_response(
            result.model_dump(exclude_none=True), api_key
        )

    except Exception as e:
        # sanitize any unhandled error securely
        error_info = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_ai_detect_sensitive", endpoint=str(request.url)
        )
        # Return a JSONResponse containing the sanitized error message.
        return JSONResponse(
            content=error_info,
            status_code=error_info.get("status_code", 500),
            media_type=JSON_MEDIA_TYPE,
        )
