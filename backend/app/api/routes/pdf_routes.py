import asyncio
import json
import time
from typing import Optional

from fastapi import APIRouter, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.document_processing.pdf import PDFTextExtractor, PDFRedactionService
from backend.app.utils.logging.logger import log_warning, log_info, log_error
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.validation.data_minimization import minimize_extracted_data
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.validation.file_validation import (
    MAX_PDF_SIZE_BYTES,
    validate_file_content_async,
    validate_mime_type
)
from backend.app.utils.memory_management import memory_optimized, memory_monitor

# Configure rate limiter
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

# File size limits
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB
CHUNK_SIZE = 64 * 1024  # 64KB for streaming
LARGE_PDF_THRESHOLD = 5 * 1024 * 1024  # 5MB threshold for streaming extraction


@router.post("/redact")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=100)  # PDF redaction is memory-intensive
async def pdf_redact(
        request: Request,
        file: UploadFile = File(...),
        redaction_mapping: str = Form(None)
):
    """
    Apply redactions to a PDF file using the provided redaction mapping with streaming response.
    This version processes the PDF entirely in-memory using the centralized PDFRedactionService.

    Performance characteristics:
    - Memory usage: Scales with PDF size but optimized with streaming output
    - Processing time: Proportional to PDF size and number of redactions
    - Output: Returns the redacted PDF as a streamed response to minimize memory footprint
    """
    start_time = time.time()
    operation_id = f"pdf_redact_{time.time()}"

    # Validate file type
    if not validate_mime_type(file.content_type, ["application/pdf"]):
        log_warning(f"[SECURITY] Unsupported file type attempted: {file.content_type} [operation_id={operation_id}]")
        return JSONResponse(
            status_code=415,
            content={"detail": "Only PDF files are supported"}
        )

    try:
        # Read the file content
        log_info(f"[SECURITY] Starting PDF redaction processing [operation_id={operation_id}]")
        contents = await file.read()

        if len(contents) > MAX_PDF_SIZE_BYTES:
            log_warning(
                f"[SECURITY] PDF size exceeds limit: {len(contents) / (1024 * 1024):.2f}MB > {MAX_PDF_SIZE_BYTES / (1024 * 1024)}MB [operation_id={operation_id}]")
            return JSONResponse(
                status_code=413,
                content={"detail": f"PDF file size exceeds maximum allowed ({MAX_PDF_SIZE_BYTES // (1024 * 1024)}MB)"}
            )

        # Validate PDF using the file validation utility
        is_valid, reason, detected_mime = await validate_file_content_async(
            contents, file.filename, file.content_type
        )
        if not is_valid:
            log_warning(f"[SECURITY] Invalid PDF content: {reason} [operation_id={operation_id}]")
            return JSONResponse(
                status_code=415,
                content={"detail": reason}
            )

        # Parse redaction mapping JSON
        if redaction_mapping:
            try:
                mapping_data = json.loads(redaction_mapping)
                log_info(
                    f"[SECURITY] Successfully parsed redaction mapping with {sum(len(page.get('sensitive', [])) for page in mapping_data.get('pages', []))} redactions [operation_id={operation_id}]")
            except Exception as e:
                log_error(f"[SECURITY] Error parsing redaction mapping: {str(e)} [operation_id={operation_id}]")
                error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                    e, "redaction_mapping_parse", 400, file.filename
                )
                return JSONResponse(status_code=status_code, content=error_response)
        else:
            mapping_data = {"pages": []}
            log_info(f"[SECURITY] No redaction mapping provided, using empty mapping [operation_id={operation_id}]")

        total_redactions = sum(len(page.get("sensitive", [])) for page in mapping_data.get("pages", []))

        # Process the PDF using the centralized PDFRedactionService
        redact_start = time.time()

        try:
            # Initialize the redaction service with the PDF content
            redaction_service = PDFRedactionService(contents)

            # Apply redactions directly in memory using the optimized service
            redacted_content = redaction_service.apply_redactions_to_memory(mapping_data)
            redaction_service.close()

            log_info(
                f"[SECURITY] PDF redaction completed successfully: {total_redactions} redactions [operation_id={operation_id}]")
        except Exception as e:
            log_error(f"[SECURITY] Error applying redactions: {str(e)} [operation_id={operation_id}]")
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                e, "pdf_redaction_service", 500, file.filename
            )
            return JSONResponse(status_code=status_code, content=error_response)

        redact_time = time.time() - redact_start
        total_time = time.time() - start_time

        # Record processing for GDPR compliance
        record_keeper.record_processing(
            operation_type="pdf_redaction",
            document_type="PDF",
            entity_types_processed=[],
            processing_time=total_time,
            entity_count=total_redactions,
            success=True
        )

        # Log the sensitive operation
        log_sensitive_operation(
            "PDF Redaction",
            total_redactions,
            total_time,
            redact_time=redact_time,
            file_type="PDF"
        )

        # Get memory statistics
        mem_stats = memory_monitor.get_memory_stats()
        log_info(
            f"[SECURITY] Memory usage after PDF redaction: current={mem_stats['current_usage']:.1f}%, "
            f"peak={mem_stats['peak_usage']:.1f}% [operation_id={operation_id}]")

        # Stream the redacted content directly to the client
        async def content_streamer():
            chunk_size = CHUNK_SIZE
            for i in range(0, len(redacted_content), chunk_size):
                yield redacted_content[i:i + chunk_size]

        return StreamingResponse(
            content_streamer(),
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=redacted.pdf",
                "X-Redaction-Time": f"{redact_time:.3f}s",
                "X-Total-Time": f"{total_time:.3f}s",
                "X-Redactions-Applied": str(total_redactions),
                "X-Memory-Usage": f"{mem_stats['current_usage']:.1f}%",
                "X-Peak-Memory": f"{mem_stats['peak_usage']:.1f}%",
                "X-Operation-ID": operation_id
            }
        )

    except Exception as e:
        log_error(f"[SECURITY] Unhandled exception in PDF redaction: {str(e)} [operation_id={operation_id}]")
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "pdf_redaction", 500, file.filename
        )
        return JSONResponse(status_code=status_code, content=error_response)


@router.post("/extract")
@limiter.limit("15/minute")
@memory_optimized(threshold_mb=50)
async def pdf_extract(request: Request, file: UploadFile = File(...)):
    """
    Extract text with positions from a PDF file with performance metrics and memory optimization.

    Uses the centralized PDFTextExtractor for direct in-memory processing, eliminating
    the previous complex locking and processing logic with a simpler, more efficient approach.

    Performance characteristics:
    - Memory usage: Optimized with adaptive buffer management
    - Processing time: Scales linearly with document complexity
    - Enhanced error handling: Comprehensive error management with detailed logging
    """
    start_time = time.time()
    operation_id = f"pdf_extract_{time.time()}"

    # Validate file type
    if not validate_mime_type(file.content_type, ["application/pdf"]):
        log_warning(f"[SECURITY] Unsupported file type attempted: {file.content_type} [operation_id={operation_id}]")
        return JSONResponse(
            status_code=415,
            content={"detail": "Only PDF files are supported"}
        )

    try:
        # Read file content
        log_info(f"[SECURITY] Starting PDF extraction [operation_id={operation_id}]")
        file_read_start = time.time()
        content = await file.read()
        file_read_time = time.time() - file_read_start

        # Validate file size
        if len(content) > MAX_PDF_SIZE_BYTES:
            log_warning(f"[SECURITY] PDF size exceeds limit: {len(content) / (1024 * 1024):.2f}MB > "
                        f"{MAX_PDF_SIZE_BYTES / (1024 * 1024)}MB [operation_id={operation_id}]")
            return JSONResponse(
                status_code=413,
                content={"detail": f"PDF file size exceeds maximum allowed ({MAX_PDF_SIZE_BYTES // (1024 * 1024)}MB)"}
            )

        # Validate file content
        is_valid, reason, _ = await validate_file_content_async(content, file.filename, file.content_type)
        if not is_valid:
            log_warning(f"[SECURITY] Invalid PDF content: {reason} [operation_id={operation_id}]")
            return JSONResponse(
                status_code=415,
                content={"detail": reason}
            )

        # Extract text using the centralized PDFTextExtractor
        extract_start = time.time()

        try:
            # Initialize the text extractor with the PDF content
            extractor = PDFTextExtractor(content)

            # Extract text with option to detect images
            extracted_data = extractor.extract_text(detect_images=True)
            extractor.close()

            log_info(f"[SECURITY] PDF extraction completed successfully [operation_id={operation_id}]")
        except Exception as e:
            log_error(f"[SECURITY] Error extracting text: {str(e)} [operation_id={operation_id}]")
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                e, "pdf_text_extraction", 500, file.filename
            )
            return JSONResponse(status_code=status_code, content=error_response)

        extract_time = time.time() - extract_start
        total_time = time.time() - start_time

        # Apply data minimization
        extracted_data = minimize_extracted_data(extracted_data)

        # Add performance statistics
        pages_count = len(extracted_data.get("pages", []))
        words_count = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))

        extracted_data["performance"] = {
            "file_read_time": file_read_time,
            "extraction_time": extract_time,
            "total_time": total_time,
            "pages_count": pages_count,
            "words_count": words_count,
            "operation_id": operation_id
        }

        extracted_data["file_info"] = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(content)
        }

        # Record processing for GDPR compliance
        record_keeper.record_processing(
            operation_type="pdf_extraction",
            document_type="PDF",
            entity_types_processed=[],
            processing_time=total_time,
            entity_count=0,
            success=True
        )

        # Log the sensitive operation
        log_sensitive_operation(
            "PDF Extraction",
            0,
            total_time,
            pages=pages_count,
            words=words_count,
            extraction_time=extract_time
        )

        # Add memory statistics
        mem_stats = memory_monitor.get_memory_stats()
        extracted_data["_debug"] = {
            "memory_usage": mem_stats["current_usage"],
            "peak_memory": mem_stats["peak_usage"]
        }

        return JSONResponse(content=extracted_data)

    except HTTPException as e:
        log_error(
            f"[SECURITY] HTTP exception in PDF extraction: {e.detail} (status {e.status_code}) [operation_id={operation_id}]")
        raise e
    except Exception as e:
        log_error(f"[SECURITY] Unhandled exception in PDF extraction: {str(e)} [operation_id={operation_id}]")
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "pdf_extraction", 500, file.filename
        )
        return JSONResponse(status_code=status_code, content=error_response)