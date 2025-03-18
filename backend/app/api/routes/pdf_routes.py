import asyncio
import json
import time
import io

from fastapi import APIRouter, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.services.document_processing import extraction_processor
from backend.app.utils.logger import log_warning, log_info, log_error
from backend.app.utils.secure_logging import log_sensitive_operation
from backend.app.utils.data_minimization import minimize_extracted_data
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.processing_records import record_keeper
from backend.app.utils.file_validation import MAX_PDF_SIZE_BYTES, validate_file_content_async, validate_mime_type
from backend.app.utils.memory_management import memory_optimized, memory_monitor
from backend.app.document_processing.pdf import PDFTextExtractor, PDFRedactionService
from backend.app.utils.secure_file_utils import SecureTempFileManager
from backend.app.utils.synchronization_utils import AsyncTimeoutLock, LockPriority

# Configure rate limiter
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

# File size limits
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB
CHUNK_SIZE = 64 * 1024  # 64KB for streaming
LARGE_PDF_THRESHOLD = 5 * 1024 * 1024  # 5MB threshold for streaming extraction

# Create shared lock for PDF processing to prevent resource contention
# Using class variable to ensure a single instance across the application
_pdf_processing_lock = None


def get_pdf_processing_lock():
    """
    Get the PDF processing lock, initializing it if needed.
    This ensures a single lock instance is used across the application.
    """
    global _pdf_processing_lock
    if _pdf_processing_lock is None:
        _pdf_processing_lock = AsyncTimeoutLock("pdf_processing_lock", priority=LockPriority.MEDIUM)
        log_info("[SYSTEM] PDF processing lock initialized")
    return _pdf_processing_lock


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
        # Read file content into memory
        log_info(f"[SECURITY] Starting PDF redaction processing [operation_id={operation_id}]")

        # Read the file content
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

        # Process the PDF - Get and use the shared lock instance
        redact_start = time.time()
        pdf_lock = get_pdf_processing_lock()

        # Initialize redaction service outside the lock to minimize lock time
        redaction_service = PDFRedactionService(contents)

        # First try with no lock for small PDFs with few redactions
        if len(contents) < 1024 * 1024 and total_redactions < 10:  # Less than 1MB and few redactions
            try:
                redacted_content = redaction_service.apply_redactions_to_memory(mapping_data)
                log_info(
                    f"[SECURITY] PDF redaction completed without lock (small file): {total_redactions} redactions applied [operation_id={operation_id}]")
            except Exception as e:
                # Fall back to using lock if direct processing fails
                log_warning(
                    f"[SECURITY] Direct PDF redaction failed, trying with lock: {str(e)} [operation_id={operation_id}]")
                redacted_content = None
        else:
            # For larger PDFs, start with lock approach
            redacted_content = None

        # If direct processing failed or wasn't attempted, use lock
        if redacted_content is None:
            try:
                # Try to acquire lock with generous timeout (30 seconds for redaction)
                async with pdf_lock.acquire_timeout(timeout=30.0) as acquired:
                    if not acquired:
                        log_warning(
                            f"[SECURITY] Failed to acquire PDF processing lock - system may be overloaded [operation_id={operation_id}]")

                        # Instead of failing immediately, try processing without the lock
                        # This is a fallback mechanism that might work if the system isn't truly overloaded
                        try:
                            log_warning(
                                f"[SECURITY] Attempting emergency processing without lock [operation_id={operation_id}]")
                            redacted_content = redaction_service.apply_redactions_to_memory(mapping_data)
                            log_info(
                                f"[SECURITY] Emergency PDF redaction succeeded without lock: {total_redactions} redactions [operation_id={operation_id}]")
                        except Exception as fallback_error:
                            log_error(
                                f"[SECURITY] Emergency processing failed: {str(fallback_error)} [operation_id={operation_id}]")
                            return JSONResponse(
                                status_code=503,
                                content={
                                    "detail": "PDF processing service is currently overloaded. Please try again later.",
                                    "retry_after": 30  # Suggest retry after 30 seconds
                                }
                            )
                    else:
                        # We have the lock, process normally
                        try:
                            redacted_content = redaction_service.apply_redactions_to_memory(mapping_data)
                            log_info(
                                f"[SECURITY] PDF redaction completed successfully with lock: {total_redactions} redactions applied [operation_id={operation_id}]")
                        except TimeoutError:
                            log_warning(
                                f"[SECURITY] PDF redaction timed out, trying with increased timeout [operation_id={operation_id}]")
                            # Try again with a longer timeout
                            redaction_service = PDFRedactionService(contents)
                            redaction_service.DEFAULT_REDACTION_TIMEOUT = 600.0  # 10 minute timeout
                            redaction_service.DEFAULT_LOCK_TIMEOUT = 300.0  # 5 minute lock timeout
                            redaction_service.LOCK_RETRY_DELAY = 10.0  # 10 second retry delay
                            redacted_content = redaction_service.apply_redactions_to_memory(mapping_data)
                            log_info(
                                f"[SECURITY] PDF redaction completed with extended timeout: {total_redactions} redactions [operation_id={operation_id}]")
            except TimeoutError:
                log_error(f"[SECURITY] Timeout waiting for PDF processing resources [operation_id={operation_id}]")

                # Final emergency fallback - try one last time without lock
                try:
                    log_warning(
                        f"[SECURITY] Final emergency attempt without lock after timeout [operation_id={operation_id}]")
                    redacted_content = redaction_service.apply_redactions_to_memory(mapping_data)
                    log_info(
                        f"[SECURITY] Final emergency PDF redaction succeeded: {total_redactions} redactions [operation_id={operation_id}]")
                except Exception as e:
                    log_error(f"[SECURITY] Final emergency attempt failed: {str(e)} [operation_id={operation_id}]")
                    return JSONResponse(
                        status_code=503,
                        content={
                            "detail": "Service timeout waiting for PDF processing resources. System is under heavy load.",
                            "retry_after": 60
                        }
                    )
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

        # Get the shared lock instance
        pdf_lock = get_pdf_processing_lock()

        if use_streaming:
            log_info(
                f"[SECURITY] Using streaming mode for large PDF ({file_size / 1024:.1f}KB) [operation_id={operation_id}]")
            # Reset file position for streaming
            await file.seek(0)

            # Try processing with lock first, but have fallback
            try:
                # Try to acquire lock with reasonable timeout
                async with pdf_lock.acquire_timeout(timeout=10.0) as acquired:
                    if not acquired:
                        log_warning(
                            f"[SECURITY] Failed to acquire PDF processing lock for streaming extraction - proceeding without lock [operation_id={operation_id}]")
                        # For streaming extraction, we can proceed without lock as it's less resource-intensive
                        return await process_pdf_streaming(file, start_time, operation_id)
                    else:
                        # Process with lock acquired
                        result = await process_pdf_streaming(file, start_time, operation_id)
                        return result
            except TimeoutError:
                log_warning(
                    f"[SECURITY] Timeout acquiring lock for streaming extraction - proceeding without lock [operation_id={operation_id}]")
                # Proceed without lock as fallback
                return await process_pdf_streaming(file, start_time, operation_id)

        # For smaller files, process entirely in memory
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

        # Small files can be processed outside the lock first as a fast path
        extract_start = time.time()

        # First try direct processing without lock for small files
        if file_size < 512 * 1024:  # Less than 512KB
            try:
                extracted_data = await SecureTempFileManager.process_content_in_memory_async(
                    contents,
                    extraction_processor,
                    use_path=False,
                    extension=".pdf"
                )
                log_info(
                    f"[SECURITY] Small PDF extraction completed without lock in {time.time() - extract_start:.3f}s [operation_id={operation_id}]")
            except Exception as e:
                log_warning(
                    f"[SECURITY] Direct extraction failed, falling back to lock: {str(e)} [operation_id={operation_id}]")
                extracted_data = None
        else:
            # For medium files, use the lock approach first
            extracted_data = None

        # If direct processing failed or wasn't attempted, try with lock
        if extracted_data is None:
            try:
                # Try to acquire lock with timeout
                async with pdf_lock.acquire_timeout(timeout=10.0) as acquired:
                    if not acquired:
                        log_warning(
                            f"[SECURITY] Failed to acquire PDF processing lock for extraction - attempting emergency processing [operation_id={operation_id}]")

                        # Try processing without lock as emergency fallback
                        try:
                            extracted_data = await SecureTempFileManager.process_content_in_memory_async(
                                contents,
                                extraction_processor,
                                use_path=False,
                                extension=".pdf"
                            )
                            log_info(
                                f"[SECURITY] Emergency PDF extraction completed without lock in {time.time() - extract_start:.3f}s [operation_id={operation_id}]")
                        except Exception as fallback_error:
                            log_error(
                                f"[SECURITY] Emergency extraction failed: {str(fallback_error)} [operation_id={operation_id}]")
                            return JSONResponse(
                                status_code=503,
                                content={
                                    "detail": "PDF processing service is currently overloaded. Please try again later.",
                                    "retry_after": 15
                                }
                            )
                    else:
                        # Normal processing with lock
                        extracted_data = await SecureTempFileManager.process_content_in_memory_async(
                            contents,
                            extraction_processor,
                            use_path=False,
                            extension=".pdf"
                        )
                        log_info(
                            f"[SECURITY] PDF extraction completed with lock in {time.time() - extract_start:.3f}s [operation_id={operation_id}]")
            except TimeoutError:
                log_error(
                    f"[SECURITY] Timeout waiting for PDF processing lock - attempting emergency processing [operation_id={operation_id}]")

                # Final emergency attempt without lock
                try:
                    extracted_data = await SecureTempFileManager.process_content_in_memory_async(
                        contents,
                        extraction_processor,
                        use_path=False,
                        extension=".pdf"
                    )
                    log_info(
                        f"[SECURITY] Final emergency PDF extraction completed in {time.time() - extract_start:.3f}s [operation_id={operation_id}]")
                except Exception as e:
                    log_error(f"[SECURITY] Final extraction attempt failed: {str(e)} [operation_id={operation_id}]")
                    return JSONResponse(
                        status_code=503,
                        content={
                            "detail": "Service timeout. System is under heavy load.",
                            "retry_after": 30
                        }
                    )

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
            "words_count": words_count,
            "operation_id": operation_id
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
            "streaming_mode": True,
            "operation_id": operation_id
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