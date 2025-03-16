import asyncio
import json
import time
import io

from fastapi import APIRouter, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.utils.logger import log_warning
from backend.app.utils.secure_logging import log_sensitive_operation
from backend.app.utils.data_minimization import minimize_extracted_data
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.processing_records import record_keeper
from backend.app.utils.file_validation import MAX_PDF_SIZE_BYTES, validate_file_content_async, validate_mime_type
from backend.app.utils.memory_management import memory_optimized, memory_monitor
from backend.app.document_processing.pdf import PDFTextExtractor, PDFRedactionService

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
    This version processes the PDF entirely in-memory, avoiding temporary file creation.

    Performance characteristics:
    - Memory usage: Scales with PDF size but optimized with streaming output
    - Processing time: Proportional to PDF size and number of redactions
    - Output: Returns the redacted PDF as a streamed response to minimize memory footprint
    """
    start_time = time.time()

    # Validate file type
    if not validate_mime_type(file.content_type, ["application/pdf"]):
        return JSONResponse(
            status_code=415,
            content={"detail": "Only PDF files are supported"}
        )

    try:
        # Read file content once into memory
        contents = await file.read()
        if len(contents) > MAX_PDF_SIZE_BYTES:
            return JSONResponse(
                status_code=413,
                content={"detail": f"PDF file size exceeds maximum allowed ({MAX_PDF_SIZE_BYTES // (1024 * 1024)}MB)"}
            )

        # Validate PDF using the file validation utility
        is_valid, reason, detected_mime = await validate_file_content_async(
            contents, file.filename, file.content_type
        )
        if not is_valid:
            return JSONResponse(
                status_code=415,
                content={"detail": reason}
            )

        # Parse redaction mapping JSON
        if redaction_mapping:
            try:
                mapping_data = json.loads(redaction_mapping)
            except Exception as e:
                error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                    e, "redaction_mapping_parse", 400, file.filename
                )
                return JSONResponse(status_code=status_code, content=error_response)
        else:
            mapping_data = {"pages": []}

        total_redactions = sum(len(page.get("sensitive", [])) for page in mapping_data.get("pages", []))

        # Process the PDF entirely in memory
        redact_start = time.time()
        try:
            # Create a PDFRedactionService instance with the PDF content as bytes
            redaction_service = PDFRedactionService(contents)

            # Apply redactions in memory and get the redacted content as bytes
            redacted_content = redaction_service.apply_redactions_to_memory(mapping_data)
        except Exception as e:
            log_warning(f"Error applying redactions: {str(e)}")
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                e, "pdf_redaction_service", 500, file.filename
            )
            return JSONResponse(status_code=status_code, content=error_response)

        redact_time = time.time() - redact_start
        total_time = time.time() - start_time

        record_keeper.record_processing(
            operation_type="pdf_redaction",
            document_type="PDF",
            entity_types_processed=[],
            processing_time=total_time,
            entity_count=total_redactions,
            success=True
        )

        log_sensitive_operation(
            "PDF Redaction",
            total_redactions,
            total_time,
            redact_time=redact_time,
            file_type="PDF"
        )

        mem_stats = memory_monitor.get_memory_stats()

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
                "X-Peak-Memory": f"{mem_stats['peak_usage']:.1f}%"
            }
        )

    except Exception as e:
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

    This version uses the optimized PDFTextExtractor for direct in-memory processing and
    implements chunked streaming for large PDFs to minimize memory usage.

    Performance characteristics:
    - Memory usage: O(1) for streaming mode, proportional to page count otherwise
    - Processing time: Scales linearly with document complexity
    - Large files: Automatically processed in streaming mode to reduce memory footprint
    """
    start_time = time.time()

    # Validate file type
    if not validate_mime_type(file.content_type, ["application/pdf"]):
        return JSONResponse(
            status_code=415,
            content={"detail": "Only PDF files are supported"}
        )

    try:
        # Detect file size to determine processing strategy
        file_size = 0
        chunk = await file.read(8192)  # Read a small chunk to check size
        file_size += len(chunk)

        # Determine if we should use streaming mode based on file size
        use_streaming = file_size > LARGE_PDF_THRESHOLD

        if use_streaming:
            # Reset file position for streaming
            await file.seek(0)

            # Process large PDFs in streaming mode for memory efficiency
            return await process_pdf_streaming(file, start_time)

        # For smaller files, process entirely in memory
        contents = chunk + await file.read()

        is_valid, reason, _ = await validate_file_content_async(contents, file.filename, file.content_type)
        if not is_valid:
            return JSONResponse(
                status_code=415,
                content={"detail": reason}
            )

        # Use the optimized PDFTextExtractor with direct memory processing
        extract_start = time.time()

        # Create an in-memory buffer from the file contents
        buffer = io.BytesIO(contents)

        # Use PDFTextExtractor with the buffer
        extractor = PDFTextExtractor(buffer)
        extracted_data = extractor.extract_text_with_positions()
        extractor.close()

        extract_time = time.time() - extract_start
        total_time = time.time() - start_time

        # Apply data minimization
        extracted_data = minimize_extracted_data(extracted_data)

        # Add performance statistics
        pages_count = len(extracted_data.get("pages", []))
        words_count = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
        extracted_data["performance"] = {
            "extraction_time": extract_time,
            "total_time": total_time,
            "pages_count": pages_count,
            "words_count": words_count
        }
        extracted_data["file_info"] = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(contents)
        }

        mem_stats = memory_monitor.get_memory_stats()
        extracted_data["_debug"] = {
            "memory_usage": mem_stats["current_usage"],
            "peak_memory": mem_stats["peak_usage"]
        }

        record_keeper.record_processing(
            operation_type="pdf_extraction",
            document_type="PDF",
            entity_types_processed=[],
            processing_time=total_time,
            entity_count=0,
            success=True
        )

        log_sensitive_operation(
            "PDF Extraction",
            0,
            total_time,
            pages=pages_count,
            words=words_count,
            extraction_time=extract_time
        )

        return JSONResponse(content=extracted_data)

    except HTTPException as e:
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "pdf_extraction", e.status_code, file.filename
        )
        return JSONResponse(status_code=status_code, content=error_response)
    except Exception as e:
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "pdf_extraction", 500, file.filename
        )
        return JSONResponse(status_code=status_code, content=error_response)


async def process_pdf_streaming(file: UploadFile, start_time: float):
    """
    Process a PDF file in streaming mode for large files to minimize memory usage.

    Args:
        file: The uploaded PDF file
        start_time: Start time for performance tracking

    Returns:
        JSONResponse with extracted text data
    """
    extract_start = time.time()

    try:
        import pymupdf

        # Use streaming extraction by using the file stream directly
        doc = pymupdf.open(stream=file.file, filetype="pdf")
        extracted_data = {"pages": []}

        # Process the PDF page by page to minimize memory usage
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            words = page.get_text("words")
            page_words = []

            for word in words:
                x0, y0, x1, y1, text, *_ = word
                if text.strip():  # Only include words with non-whitespace content
                    page_words.append({
                        "text": text.strip(),
                        "x0": x0,
                        "y0": y0,
                        "x1": x1,
                        "y1": y1
                    })

            if page_words:
                extracted_data["pages"].append({
                    "page": page_idx + 1,
                    "words": page_words
                })

            # Allow other async tasks to run between pages for better concurrency
            await asyncio.sleep(0)

        doc.close()

        # Apply data minimization
        extracted_data = minimize_extracted_data(extracted_data)

        # Calculate statistics and performance metrics
        extract_time = time.time() - extract_start
        total_time = time.time() - start_time
        pages_count = len(extracted_data.get("pages", []))
        words_count = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))

        # Add performance statistics
        extracted_data["performance"] = {
            "extraction_time": extract_time,
            "total_time": total_time,
            "pages_count": pages_count,
            "words_count": words_count,
            "streaming_mode": True
        }

        # Add file information
        extracted_data["file_info"] = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": "streamed"  # We don't have the exact size in streaming mode
        }

        # Add memory statistics
        mem_stats = memory_monitor.get_memory_stats()
        extracted_data["_debug"] = {
            "memory_usage": mem_stats["current_usage"],
            "peak_memory": mem_stats["peak_usage"]
        }

        # Record processing for compliance
        record_keeper.record_processing(
            operation_type="pdf_extraction_streaming",
            document_type="PDF",
            entity_types_processed=[],
            processing_time=total_time,
            entity_count=0,
            success=True
        )

        # Log operation details
        log_sensitive_operation(
            "PDF Streaming Extraction",
            0,
            total_time,
            pages=pages_count,
            words=words_count,
            extraction_time=extract_time
        )

        return JSONResponse(content=extracted_data)

    except Exception as e:
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "pdf_streaming_extraction", 500, file.filename
        )
        return JSONResponse(status_code=status_code, content=error_response)