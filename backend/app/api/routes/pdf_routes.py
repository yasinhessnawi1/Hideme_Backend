from fastapi import APIRouter, File, UploadFile, Form, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.services.document_extract_service import DocumentExtractService
from backend.app.services.document_redact_service import DocumentRedactionService
from backend.app.utils.memory_management import memory_optimized

# Configure rate limiter
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

@router.post("/redact")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=100)
async def pdf_redact(
    request: Request,
    file: UploadFile = File(...),
    redaction_mapping: str = Form(None),
    remove_images: bool = Form(False)  # New parameter to control image redaction
):
    """
    Apply redactions to a PDF file using the provided redaction mapping.
    If `remove_images` is True, images on the PDF pages will also be redacted.
    Returns the redacted PDF as a streamed response to minimize memory footprint.
    """
    service = DocumentRedactionService()
    return await service.redact(file, redaction_mapping, remove_images)


# Router: The endpoint simply delegates PDF extraction to PDFExtractService.
@router.post("/extract")
@limiter.limit("15/minute")
@memory_optimized(threshold_mb=50)
async def pdf_extract(request: Request, file: UploadFile = File(...)):
    """
    Extract text with positions from a PDF file with performance metrics and memory optimization.

    Uses the centralized PDFTextExtractor for direct in-memory processing with enhanced error handling.
    """
    service = DocumentExtractService()
    return await service.extract(file)