"""
This module defines the API endpoint for AI sensitive data detection.
It integrates rate limiting via SlowAPI and memory optimization via a decorator,
while delegating the file processing to AIDetectService. All errors are handled securely
using SecurityAwareErrorHandler to prevent leaking sensitive information.
"""

from http.client import HTTPException
from typing import Optional

from fastapi import APIRouter, File, UploadFile, Form, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.services.ai_detect_service import AIDetectService
from backend.app.utils.constant.constant import JSON_MEDIA_TYPE
from backend.app.utils.helpers.json_helper import validate_threshold_score
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
        threshold: Optional[float] = Form(None)
) -> Response:
    """
    Endpoint to detect sensitive information in an uploaded file using the AI detection service.

    This endpoint receives an uploaded file along with optional parameters specifying
    the entities to detect, words to remove, and a threshold to filter the detection results.
    Processing is delegated to AIDetectService which performs AI-based sensitive data detection.
    If any error occurs during processing, the error is securely handled using SecurityAwareErrorHandler
    to provide a sanitized error response.

    Parameters:
        request (Request): The incoming HTTP request.
        file (UploadFile): The file uploaded by the client.
        requested_entities (Optional[str]): A comma-separated list of entities to detect.
        remove_words (Optional[str]): A comma-separated list of words to remove from the document.
        threshold (Optional[float]): A numeric threshold (0.00 to 1.00) for filtering the detection results.

    Returns:
        Response: The detection results as returned by AIDetectService, or a sanitized error response if an exception occurs.
    """
    try:
        # Validate the threshold score; will raise HTTPException if threshold is invalid.
        validate_threshold_score(threshold)
    except HTTPException as e:
        # Handle threshold validation error securely.
        error_info = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_ai_detect_sensitive", endpoint=str(request.url)
        )
        # Retrieve the status code from the error info, defaulting to 500 if not present.
        status = error_info.get("status_code", 500)
        # Return a Response with the safe error information.
        return Response(
            content=error_info,
            status_code=status,
            media_type=JSON_MEDIA_TYPE
        )
    # Instantiate the AI detection service.
    service = AIDetectService()
    try:
        # Delegate file processing to the AI detection service, passing all relevant parameters.
        result = await service.detect(file, requested_entities, remove_words, threshold)
        # Return the processing result.
        return result
    except Exception as e:
        # Securely handle any exceptions during AI detection.
        error_info = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_ai_detect_sensitive", endpoint=str(request.url)
        )
        # Determine the status code from the error information.
        status = error_info.get("status_code", 500)
        # Return a Response containing the sanitized error message.
        return Response(
            content=error_info,
            status_code=status,
            media_type=JSON_MEDIA_TYPE
        )
