"""
This router defines endpoints for PDF processing, including redaction and text extraction.
It leverages dedicated services for document redaction and extraction, and includes memory optimization,
rate limiting, and secure error handling to protect sensitive data while ensuring performance.
"""

from fastapi import APIRouter, File, UploadFile, Form, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi.responses import JSONResponse

from backend.app.services.document_extract_service import DocumentExtractService
from backend.app.services.document_redact_service import DocumentRedactionService
from backend.app.utils.system_utils.memory_management import memory_optimized
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler

# Configure rate limiter using the client's remote address.
limiter = Limiter(key_func=get_remote_address)
# Create the API router.
router = APIRouter()


@router.post("/redact")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=100)
async def pdf_redact(
        request: Request,
        file: UploadFile = File(...),
        redaction_mapping: str = Form(None),
        remove_images: bool = Form(False)
) -> Response:
    """
    Apply redactions to a PDF file using the provided redaction mapping.

    If `remove_images` is True, images on the PDF pages will also be redacted.
    Returns the redacted PDF as a streamed response to minimize memory footprint.

    Parameters:
        request (Request): The incoming HTTP request.
        file (UploadFile): The PDF file uploaded by the client.
        redaction_mapping (str): The redaction mapping to apply, provided as a string.
        remove_images (bool): Flag indicating whether images should be removed during redaction.

    Returns:
        Response: A streamed response containing the redacted PDF, or a secure error response if an exception occurs.
    """
    # Initialize the document redaction service.
    service = DocumentRedactionService()
    try:
        # Call the redaction service with the provided parameters.
        result = await service.redact(file, redaction_mapping, remove_images)
        return result
    except Exception as e:
        # Log the error and create a secure error response using SecurityAwareErrorHandler.
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "pdf_redact", 500, resource_id=str(request.url)
        )
        return JSONResponse(status_code=status_code, content=error_response)


@router.post("/extract")
@limiter.limit("15/minute")
@memory_optimized(threshold_mb=50)
async def pdf_extract(request: Request, file: UploadFile = File(...)) -> JSONResponse:
    """
    Extract text with positions from a PDF file with performance metrics and memory optimization.

    Uses the centralized DocumentExtractService for direct in-memory text extraction with enhanced error handling.

    Parameters:
        request (Request): The incoming HTTP request.
        file (UploadFile): The PDF file uploaded by the client.

    Returns:
        JSONResponse: A JSON response containing the extracted text and positional information,
                      or a secure error response if an exception occurs.
    """
    # Initialize the document extraction service.
    service = DocumentExtractService()
    try:
        # Call the extraction service to process the file.
        result = await service.extract(file)
        # If result is already a Response, return it directly.
        if isinstance(result, Response):
            return result
        else:
            return JSONResponse(content=result)
    except Exception as e:
        # Generate a secure error response using SecurityAwareErrorHandler.
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "pdf_extract", 500, resource_id=str(request.url)
        )
        return JSONResponse(status_code=status_code, content=error_response)
