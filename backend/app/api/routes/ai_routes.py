"""
This module defines the API endpoint for AI sensitive data detection.
It integrates rate limiting via SlowAPI and memory optimization via a decorator,
while delegating the file processing to AIDetectService. All errors are handled securely
using SecurityAwareErrorHandler to prevent leaking sensitive information.
"""

from typing import Optional

import json
from fastapi import APIRouter, File, UploadFile, Form, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.services.ai_detect_service import AIDetectService
from backend.app.utils.constant.constant import JSON_MEDIA_TYPE
from backend.app.utils.system_utils.memory_management import memory_optimized
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler

# Configure the rate limiter (using the client's remote address) and the API router.
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


@router.post("/detect")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=75)
async def ai_detect_sensitive(
        request: Request,
        file: UploadFile = File(...),
        requested_entities: Optional[str] = Form(None),
        remove_words: Optional[str] = Form(None)
) -> Response:
    """
    Endpoint to detect sensitive information in an uploaded file using the AI detection service.

    This endpoint receives an uploaded file along with optional parameters specifying
    the entities to detect and words to remove from the document. The processing is
    delegated to AIDetectService which performs AI-based sensitive data detection.
    If any error occurs during processing, the error is securely handled using
    SecurityAwareErrorHandler to provide a sanitized error response.

    Parameters:
        request (Request): The incoming HTTP request.
        file (UploadFile): The file uploaded by the client.
        requested_entities (Optional[str]): A comma-separated list of entities to detect.
        remove_words (Optional[str]): A comma-separated list of words to remove from the document.

    Returns:
        Response: The detection results as returned by AIDetectService, or a sanitized error response if an exception occurs.
    """
    service = AIDetectService()
    try:
        # Delegate file processing to the AI detection service.
        result = await service.detect(file, requested_entities, remove_words)
        return result
    except Exception as e:
        # If an error occurs, log it and return a secure error response as JSON.
        error_info = SecurityAwareErrorHandler.handle_api_gateway_error(
            e, "ai_detect_sensitive", endpoint=str(request.url)
        )
        return Response(
            content=json.dumps(error_info),
            status_code=500,
            media_type=JSON_MEDIA_TYPE
        )
