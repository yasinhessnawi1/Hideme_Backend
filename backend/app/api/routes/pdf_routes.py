import asyncio
import json
import time
import io

from fastapi import APIRouter, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.utils.logger import log_warning, log_info, log_error
from backend.app.utils.secure_logging import log_sensitive_operation
from backend.app.utils.data_minimization import minimize_extracted_data
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.processing_records import record_keeper
from backend.app.utils.file_validation import MAX_PDF_SIZE_BYTES, validate_file_content_async, validate_mime_type
from backend.app.utils.memory_management import memory_optimized, memory_monitor
from backend.app.document_processing.pdf import PDFTextExtractor, PDFRedactionService
from backend.app.utils.secure_file_utils import SecureTempFileManager

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
    operation_id = f"pdf_redact_{time.time()}"

    # Validate file type
    if not validate_mime_type(file.content_type, ["application/pdf"]):
        log_warning(f"[SECURITY] Unsupported file type attempted: {file.content_type} [operation_id={operation_id}]")
        return JSONResponse(
            status_code=415,
            content={"detail": "Only PDF files are supported"}
        )

    try:
        # Read file content into memory using SecureTempFileManager
        log_info(f"[SECURITY] Starting PDF redaction processing [operation_id={operation_id}]")

        # Define a function to read the file
        async def read_file_content():
            contents = await file.read()
            return contents

        # Use SecureTempFileManager to process content
        contents = await read_file_content()

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

        # Process the PDF using SecureTempFileManager
        redact_start = time.time()
        try:
            # Define a processor function for redaction
            async def redaction_processor(content):
                # Create a PDFRedactionService instance with the PDF content as bytes
                redaction_service = PDFRedactionService(content)
                # Apply redactions in memory and get the redacted content as bytes
                return redaction_service.apply_redactions_to_memory(mapping_data)

            # Use SecureTempFileManager for memory-efficient processing
            redacted_content = await SecureTempFileManager.process_content_in_memory_async(
                contents,
                redaction_processor,
                use_path=False,
                extension=".pdf"
            )
            log_info(
                f"[SECURITY] PDF redaction completed successfully: {total_redactions} redactions applied [operation_id={operation_id}]")

        except Exception as e:
            log_error(f"[SECURITY] Error applying redactions: {str(e)} [operation_id={operation_id}]")
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
        log_info(
            f"[SECURITY] Memory usage after PDF redaction: current={mem_stats['current_usage']:.1f}%, peak={mem_stats['peak_usage']:.1f}% [operation_id={operation_id}]")

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

    This version uses the optimized PDFTextExtractor for direct in-memory processing and
    implements chunked streaming for large PDFs to minimize memory usage.

    Performance characteristics:
    - Memory usage: O(1) for streaming mode, proportional to page count otherwise
    - Processing time: Scales linearly with document complexity
    - Large files: Automatically processed in streaming mode to reduce memory footprint
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
        # Detect file size to determine processing strategy
        file_size = 0
        chunk = await file.read(8192)  # Read a small chunk to check size
        file_size += len(chunk)
        log_info(
            f"[SECURITY] PDF extraction: file size initial check {file_size / 1024:.1f}KB [operation_id={operation_id}]")

        # Determine if we should use streaming mode based on file size
        use_streaming = file_size > LARGE_PDF_THRESHOLD

        if use_streaming:
            log_info(
                f"[SECURITY] Using streaming mode for large PDF ({file_size / 1024:.1f}KB) [operation_id={operation_id}]")
            # Reset file position for streaming
            await file.seek(0)

            # Process large PDFs in streaming mode for memory efficiency
            return await process_pdf_streaming(file, start_time, operation_id)

        # For smaller files, process entirely in memory using SecureTempFileManager
        log_info(
            f"[SECURITY] Using in-memory processing for PDF ({file_size / 1024:.1f}KB) [operation_id={operation_id}]")
        contents = chunk + await file.read()

        is_valid, reason, _ = await validate_file_content_async(contents, file.filename, file.content_type)
        if not is_valid:
            log_warning(f"[SECURITY] Invalid PDF content: {reason} [operation_id={operation_id}]")
            return JSONResponse(
                status_code=415,
                content={"detail": reason}
            )

        # Use the optimized PDFTextExtractor with SecureTempFileManager
        extract_start = time.time()

        # Define extraction processor function
        async def extraction_processor(content):
            # Create an in-memory buffer from the file contents
            buffer = io.BytesIO(content)

            # Use PDFTextExtractor with the buffer
            extractor = PDFTextExtractor(buffer)
            extracted_data = extractor.extract_text_with_positions()
            extractor.close()
            return extracted_data

        # Use SecureTempFileManager for memory-efficient processing
        extracted_data = await SecureTempFileManager.process_content_in_memory_async(
            contents,
            extraction_processor,
            use_path=False,
            extension=".pdf"
        )

        extract_time = time.time() - extract_start
        total_time = time.time() - start_time
        log_info(f"[SECURITY] PDF extraction completed in {extract_time:.3f}s [operation_id={operation_id}]")

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
        log_error(
            f"[SECURITY] HTTP exception in PDF extraction: {e.detail} (status {e.status_code}) [operation_id={operation_id}]")
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "pdf_extraction", e.status_code, file.filename
        )
        return JSONResponse(status_code=status_code, content=error_response)
    except Exception as e:
        log_error(f"[SECURITY] Unhandled exception in PDF extraction: {str(e)} [operation_id={operation_id}]")
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "pdf_extraction", 500, file.filename
        )
        return JSONResponse(status_code=status_code, content=error_response)


async def process_pdf_streaming(file: UploadFile, start_time: float, operation_id: str):
    """
    Process a PDF file in streaming mode for large files to minimize memory usage.

    Args:
        file: The uploaded PDF file
        start_time: Start time for performance tracking
        operation_id: Unique operation identifier for logging

    Returns:
        JSONResponse with extracted text data
    """
    extract_start = time.time()
    log_info(f"[SECURITY] Starting streaming PDF extraction [operation_id={operation_id}]")

    try:
        import pymupdf

        # Use streaming extraction by using the file stream directly
        try:
            doc = pymupdf.open(stream=file.file, filetype="pdf")
            log_info(f"[SECURITY] Successfully opened PDF with {len(doc)} pages [operation_id={operation_id}]")
        except Exception as e:
            log_error(f"[SECURITY] Failed to open PDF with pymupdf: {str(e)} [operation_id={operation_id}]")
            raise ValueError(f"Failed to open PDF: {str(e)}")

        extracted_data = {"pages": []}

        # Process the PDF page by page to minimize memory usage
        for page_idx in range(len(doc)):
            try:
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

                # Log progress for large documents
                if page_idx % 10 == 0 and page_idx > 0:
                    log_info(f"[SECURITY] Processed {page_idx}/{len(doc)} pages [operation_id={operation_id}]")

            except Exception as e:
                log_error(f"[SECURITY] Error processing page {page_idx}: {str(e)} [operation_id={operation_id}]")
                # Continue with other pages despite error on this page
                extracted_data["pages"].append({
                    "page": page_idx + 1,
                    "words": [],
                    "error": f"Error processing page: {str(e)}"
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
        log_info(
            f"[SECURITY] Streaming PDF extraction completed: {pages_count} pages, {words_count} words, {extract_time:.3f}s [operation_id={operation_id}]")

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
        log_error(f"[SECURITY] Error in streaming PDF extraction: {str(e)} [operation_id={operation_id}]")
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "pdf_streaming_extraction", 500, file.filename
        )
        return JSONResponse(status_code=status_code, content=error_response)