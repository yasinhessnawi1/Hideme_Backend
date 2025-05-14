"""
This router defines endpoints for PDF processing, including redaction and text extraction.
It leverages dedicated services for document redaction and extraction, and includes:
- Session-authenticated or raw-API-key decryption/encryption
- Memory optimization
- Rate limiting
- Secure error handling

Clients can upload PDF files and:
- Receive a redacted PDF stream
- Extract text + positional data (JSON)
"""

import base64
from typing import Optional

from fastapi import APIRouter, File, UploadFile, Form, Request, Header, Response
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.services.document_extract_service import DocumentExtractService
from backend.app.services.document_redact_service import DocumentRedactionService
from backend.app.utils.security.session_encryption import session_manager
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.system_utils.memory_management import memory_optimized

# Rate limiter by client IP
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


@router.post("/redact")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=100)
async def pdf_redact(
    request: Request,
    file: UploadFile = File(...),
    redaction_mapping: str = Form(...),
    remove_images: bool = Form(False),
    session_key: Optional[str] = Header(None),
    api_key_id: Optional[str] = Header(None),
    raw_api_key: Optional[str] = Header(None),
) -> Response:
    """
    Redact a PDF using the specified redaction mapping.

    Modes:
    - Session-authenticated (session_key + api_key_id): requires encrypted inputs, returns encrypted output.
    - Raw-API-key (raw_api_key): accepts plaintext or encrypted input; returns encrypted output if any decryption succeeded.

    Args:
        request: The incoming HTTP request.
        file: The uploaded PDF file (potentially encrypted).
        redaction_mapping: JSON string of what to redact (can be encrypted).
        remove_images: Whether to strip images from the document.
        session_key: Bearer token for session-authenticated mode.
        api_key_id: API key ID to retrieve AES key in session mode.
        raw_api_key: Standalone API key for raw-mode access.

    Returns:
        JSONResponse or StreamingResponse containing either:
        - Encrypted redacted ZIP content (base64-encoded), or
        - Unencrypted redacted PDF/ZIP file stream.
    """
    # Decrypt inputs (if encrypted) or pass through as-is
    try:
        files, decrypted_fields, api_key = await session_manager.prepare_inputs(
            files=[file],
            form_fields={"redaction_mapping": redaction_mapping},
            session_key=session_key,
            api_key_id=api_key_id,
            raw_api_key=raw_api_key,
        )
    except Exception as e:
        # Gracefully handle decryption or validation errors
        error_info = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_redact_decrypt", endpoint=str(request.url)
        )
        return JSONResponse(
            status_code=error_info.get("status_code", 500), content=error_info
        )

    # Extract the decrypted file and mapping (fallback to original if not decrypted)
    file = files[0]
    mapping = decrypted_fields.get("redaction_mapping", redaction_mapping)

    # Apply redactions using the redaction service
    try:
        service = DocumentRedactionService()
        result: Response = await service.redact(file, mapping, remove_images)
    except Exception as e:
        # Catch errors in the redaction process and wrap them securely
        err = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_pdf_redact_router", resource_id=str(request.url)
        )
        return JSONResponse(content=err, status_code=err.get("status_code", 500))

    # If AES key was used for decryption, encrypt the output
    return await session_manager.wrap_streaming_or_file_response(result, api_key)


@router.post("/extract")
@limiter.limit("15/minute")
@memory_optimized(threshold_mb=50)
async def pdf_extract(
    request: Request,
    file: UploadFile = File(...),
    session_key: Optional[str] = Header(None),
    api_key_id: Optional[str] = Header(None),
    raw_api_key: Optional[str] = Header(None),
) -> Response:
    """
    Extract text and bounding box metadata from a PDF file.

    Modes:
    - Session-authenticated mode (session_key + api_key_id): requires AES-GCM encrypted input, returns encrypted output.
    - Raw-API-key mode (raw_api_key): accepts encrypted or plaintext; encrypts response if any decryption succeeds.

    Args:
        request: The incoming HTTP request context.
        file: PDF file to extract from (possibly encrypted).
        session_key: Bearer token for session-authenticated input.
        api_key_id: ID of the API key to fetch the AES key (used with session_key).
        raw_api_key: Standalone API key (used in raw mode).

    Returns:
        JSONResponse or Response with extracted text and positions.
        Output is encrypted if decryption was applied.
    """
    # Decrypt the file if needed (session or raw mode)
    try:
        files, _, api_key = await session_manager.prepare_inputs(
            files=[file],
            form_fields={},  # No form fields for this route
            session_key=session_key,
            api_key_id=api_key_id,
            raw_api_key=raw_api_key,
        )
    except Exception as e:
        # Gracefully handle input decryption or validation errors
        error_info = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_extract_decrypt", endpoint=str(request.url)
        )
        return JSONResponse(
            status_code=error_info.get("status_code", 500), content=error_info
        )

    file = files[0]

    # Extract text and positional metadata using the service
    try:
        service = DocumentExtractService()
        result = await service.extract(file)
    except Exception as e:
        # Catch and wrap extraction-related errors
        err = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_pdf_extract_router", resource_id=str(request.url)
        )
        return JSONResponse(content=err, status_code=err.get("status_code", 500))

    # If the result is a raw FastAPI Response (rare), handle like /redact
    if isinstance(result, Response):
        if api_key:
            # Encrypt response if input was encrypted
            raw_bytes = result.body
            cipher = session_manager.encrypt_response(raw_bytes, api_key)
            encoded = base64.urlsafe_b64encode(cipher).decode()
            return JSONResponse({"encrypted_data": encoded})
        return result

    # If result is a Pydantic model or plain dict, serialize it
    payload = result.model_dump(exclude_none=True)

    # Wrap in encrypted response if applicable, otherwise return as JSON
    return session_manager.wrap_response(payload, api_key)
