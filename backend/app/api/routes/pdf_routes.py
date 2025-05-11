"""
This router defines endpoints for PDF processing, including redaction and text extraction.
It leverages dedicated services for document redaction and extraction, and includes memory optimization,
rate limiting, and secure error handling to protect sensitive data while ensuring performance.
The endpoints allow clients to upload PDF files and receive either a redacted version of the PDF as a stream,
or extracted text along with positional information, with robust error handling to avoid information leakage.
"""

from fastapi import APIRouter, File, UploadFile, Form, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi.responses import JSONResponse

from backend.app.services.document_extract_service import DocumentExtractService
from backend.app.services.document_redact_service import DocumentRedactionService
from backend.app.utils.system_utils.memory_management import memory_optimized
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler

# Configure the rate limiter using the client's remote address.
limiter = Limiter(key_func=get_remote_address)
# Create the API router instance.
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

    This endpoint processes a PDF file by applying redactions as defined in the provided redaction mapping.
    If 'remove_images' is set to True, images on the PDF pages will also be redacted.
    The endpoint returns the redacted PDF as a streamed response to minimize memory footprint.

    Parameters:
        request (Request): The incoming HTTP request.
        file (UploadFile): The PDF file uploaded by the client.
        redaction_mapping (str): The redaction mapping to apply, provided as a string.
        remove_images (bool): Flag indicating whether images should be removed during redaction.

    Returns:
        Response: A streamed response containing the redacted PDF, or a secure error response if an exception occurs.
    """
    # Initialize the DocumentRedactionService instance.
    service = DocumentRedactionService()
    try:
        # Call the redaction service to process the file with provided redaction mapping and image removal flag.
        result = await service.redact(file, redaction_mapping, remove_images)
        # Return the resulting streamed response.
        return result
    except Exception as e:
        # Handle any exception by generating a secure error response.
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_pdf_redact_router", resource_id=str(request.url)
        )
        # Retrieve the status code from the error response, default to 500 if not provided.
        status = error_response.get("status_code", 500)
        # Return a JSONResponse with the error details.
        return JSONResponse(content=error_response, status_code=status)


@router.post("/extract")
@limiter.limit("15/minute")
@memory_optimized(threshold_mb=50)
async def pdf_extract(request: Request, file: UploadFile = File(...)) -> Response:
    """
    Extract text with positions from a PDF file with performance metrics and memory optimization.

    This endpoint uses DocumentExtractService to extract text along with their positional information
    from an uploaded PDF file. Extraction is performed in-memory with enhanced error handling.

    Parameters:
        request (Request): The incoming HTTP request.
        file (UploadFile): The PDF file uploaded by the client.

    Returns:
        Response: A response containing the extracted text and positional information,
                      or a secure error response if an exception occurs.
    """
    # Initialize the DocumentExtractService instance.
    service = DocumentExtractService()  # Initialize extraction service.
    try:
        # Use the extraction service to process the PDF file.
        result = await service.extract(file)
        # Check if the result is already a Response instance.
        if isinstance(result, Response):
            # Return the response directly if it is a Response.
            return result
        else:
            # Otherwise, wrap the result in a JSONResponse.
            return JSONResponse(content=result.model_dump(exclude_none=True))
    except Exception as e:
        # If an exception occurs, generate a secure error response.
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_pdf_extract_router", resource_id=str(request.url)
        )
        # Retrieve the status code from the error response, default to 500.
        status = error_response.get("status_code", 500)
        # Return a JSONResponse containing the sanitized error details.
        return JSONResponse(content=error_response, status_code=status)
