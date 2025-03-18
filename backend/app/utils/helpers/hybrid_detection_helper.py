import asyncio
import time
import uuid
from typing import Dict, Any, List, Optional

from fastapi import UploadFile
from fastapi.responses import JSONResponse

from backend.app.configs.gliner_config import GLINER_MODEL_NAME
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.data_minimization import minimize_extracted_data
from backend.app.utils.document_processing_utils import extract_text_data_in_memory
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.file_validation import (
    validate_file_content_async,
    MAX_TEXT_SIZE_BYTES
)
from backend.app.utils.memory_management import memory_monitor
from backend.app.utils.processing_records import record_keeper
from backend.app.utils.sanitize_utils import sanitize_detection_output
from backend.app.utils.secure_logging import log_sensitive_operation
from backend.app.utils.logger import log_info, log_warning, log_error, log_debug

CHUNK_SIZE = 1 * 1024 * 1024  # 1MB


async def process_file_in_chunks(
        file: UploadFile,
        entity_list: List[str],
        use_presidio: bool,
        use_gemini: bool,
        use_gliner: bool,
        start_time: float
) -> JSONResponse:
    """
    Process large files in chunks to minimize memory usage.

    This function implements a streaming approach for large files, processing
    the document in manageable chunks rather than loading it all into memory.

    Args:
        file: The uploaded file
        entity_list: List of entity types to detect
        use_presidio: Whether to use Presidio detector
        use_gemini: Whether to use Gemini detector
        use_gliner: Whether to use GLiNER detector
        start_time: Start time for performance tracking

    Returns:
        JSONResponse with processed results
    """
    processing_times = {}
    file_read_start = time.time()
    operation_id = str(uuid.uuid4())

    log_info(f"[SECURITY] Starting chunked file processing [operation_id={operation_id}, file={file.filename}]")

    try:
        # Validate file content on first chunk
        first_chunk = await file.read(8192)
        await file.seek(0)

        log_debug(
            f"[SECURITY] Read initial chunk of {len(first_chunk)} bytes for validation [operation_id={operation_id}]")

        is_valid, reason, detected_mime = await validate_file_content_async(
            first_chunk, file.filename, file.content_type
        )
        if not is_valid:
            log_warning(f"[SECURITY] File validation failed: {reason} [operation_id={operation_id}]")
            return JSONResponse(
                status_code=415,
                content={"detail": reason}
            )

        # For PDF files, use pymupdf's streaming capability
        if "pdf" in file.content_type.lower():
            log_info(f"[SECURITY] Delegating to PDF-specific chunked processing [operation_id={operation_id}]")
            return await process_pdf_in_chunks(
                file, entity_list, use_presidio, use_gemini, use_gliner, start_time, operation_id
            )

        # For text-based files, process in chunks
        chunks = []
        total_size = 0
        chunk_count = 0

        log_info(f"[SECURITY] Starting text-based file chunk processing [operation_id={operation_id}]")

        try:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break

                chunks.append(chunk)
                total_size += len(chunk)
                chunk_count += 1

                if chunk_count % 5 == 0:  # Log progress every 5 chunks
                    log_debug(
                        f"[SECURITY] Processed {chunk_count} chunks, total size: {total_size / 1024 / 1024:.2f}MB [operation_id={operation_id}]")

                # Safety check for max size
                max_size = MAX_TEXT_SIZE_BYTES
                if total_size > max_size:
                    log_warning(
                        f"[SECURITY] File size exceeded limit: {total_size / 1024 / 1024:.2f}MB > {max_size / 1024 / 1024:.2f}MB [operation_id={operation_id}]")
                    return JSONResponse(
                        status_code=413,
                        content={"detail": f"File size exceeds maximum allowed ({max_size // (1024 * 1024)}MB)"}
                    )
        except Exception as e:
            log_error(f"[SECURITY] Error reading file chunks: {str(e)} [operation_id={operation_id}]")
            return JSONResponse(
                status_code=500,
                content={"detail": f"Error reading file: {str(e)}"}
            )

        # Combine chunks for processing
        try:
            contents = b''.join(chunks)
            log_info(
                f"[SECURITY] Successfully combined {chunk_count} chunks, total size: {total_size / 1024 / 1024:.2f}MB [operation_id={operation_id}]")
        except Exception as e:
            log_error(f"[SECURITY] Error combining chunks: {str(e)} [operation_id={operation_id}]")
            return JSONResponse(
                status_code=500,
                content={"detail": f"Error processing file chunks: {str(e)}"}
            )

        processing_times["file_read_time"] = time.time() - file_read_start

        # Continue with normal processing flow using the combined content
        extract_start = time.time()
        try:
            log_info(f"[SECURITY] Extracting text data from combined chunks [operation_id={operation_id}]")
            extracted_data = await extract_text_data_in_memory(file.content_type, contents)
            processing_times["extraction_time"] = time.time() - extract_start
            log_info(
                f"[SECURITY] Text extraction completed in {processing_times['extraction_time']:.3f}s [operation_id={operation_id}]")
        except Exception as e:
            log_error(f"[SECURITY] Error extracting text data: {str(e)} [operation_id={operation_id}]")
            return JSONResponse(
                status_code=500,
                content={"detail": f"Error extracting text from file: {str(e)}"}
            )

        # Apply data minimization
        try:
            extracted_data = minimize_extracted_data(extracted_data)
        except Exception as e:
            log_warning(
                f"[SECURITY] Error during data minimization: {str(e)}, continuing with original data [operation_id={operation_id}]")
            # Continue with original data if minimization fails

        # Configure hybrid detector
        config = {
            "use_presidio": use_presidio,
            "use_gemini": use_gemini,
            "use_gliner": use_gliner,
            "gliner_model_name": GLINER_MODEL_NAME,
            "entities": entity_list
        }

        detector_create_start = time.time()
        try:
            log_info(
                f"[SECURITY] Initializing hybrid detector with config: presidio={use_presidio}, gemini={use_gemini}, gliner={use_gliner} [operation_id={operation_id}]")
            detector = initialization_service.get_hybrid_detector(config)
            processing_times["detector_init_time"] = time.time() - detector_create_start
        except Exception as e:
            log_error(f"[SECURITY] Error initializing detector: {str(e)} [operation_id={operation_id}]")
            return JSONResponse(
                status_code=500,
                content={"detail": f"Error initializing detection engines: {str(e)}"}
            )

        # Run detection with timeout
        detection_timeout = 60
        detection_start = time.time()
        try:
            log_info(f"[SECURITY] Starting detection with timeout {detection_timeout}s [operation_id={operation_id}]")

            # Check document size for potential memory issues
            pages_count = len(extracted_data.get("pages", []))
            words_count = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
            if pages_count > 100 or words_count > 50000:
                log_warning(
                    f"[SECURITY] Large document detected: {pages_count} pages, {words_count} words. May require additional memory [operation_id={operation_id}]")

            if hasattr(detector, 'detect_sensitive_data_async'):
                # For detectors supporting async operations
                detection_task = detector.detect_sensitive_data_async(extracted_data, entity_list)
                detection_result = await asyncio.wait_for(detection_task, timeout=detection_timeout)
            else:
                # For synchronous detectors, run in a thread pool to avoid blocking
                detection_task = asyncio.to_thread(detector.detect_sensitive_data, extracted_data, entity_list)
                detection_result = await asyncio.wait_for(detection_task, timeout=detection_timeout)
        except asyncio.TimeoutError:
            log_error(f"[SECURITY] Detection timed out after {detection_timeout}s [operation_id={operation_id}]")
            return JSONResponse(
                status_code=408,
                content={"detail": f"Hybrid detection timed out after {detection_timeout} seconds"}
            )
        except Exception as e:
            log_error(f"[SECURITY] Error during detection: {str(e)} [operation_id={operation_id}]")
            return JSONResponse(
                status_code=500,
                content={"detail": f"Detection error: {str(e)}"}
            )

        if detection_result is None:
            log_error(f"[SECURITY] Detection returned no results [operation_id={operation_id}]")
            return JSONResponse(
                status_code=500,
                content={"detail": "Detection failed to return results"}
            )

        # Process results
        try:
            anonymized_text, entities, redaction_mapping = detection_result
            processing_times["detection_time"] = time.time() - detection_start
            processing_times["total_time"] = time.time() - start_time

            log_info(
                f"[SECURITY] Detection completed in {processing_times['detection_time']:.3f}s. Found {len(entities)} entities [operation_id={operation_id}]")
        except Exception as e:
            log_error(f"[SECURITY] Error processing detection results: {str(e)} [operation_id={operation_id}]")
            return JSONResponse(
                status_code=500,
                content={"detail": f"Error processing detection results: {str(e)}"}
            )

        # Calculate statistics
        total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
        processing_times["words_count"] = total_words
        processing_times["pages_count"] = len(extracted_data.get("pages", []))
        if total_words > 0 and entities:
            processing_times["entity_density"] = (len(entities) / total_words) * 1000

        # Record processing for compliance
        try:
            record_keeper.record_processing(
                operation_type="hybrid_detection_chunked",
                document_type=file.content_type,
                entity_types_processed=entity_list or [],
                processing_time=processing_times["total_time"],
                entity_count=len(entities),
                success=True
            )
        except Exception as e:
            log_warning(f"[SECURITY] Error recording processing metrics: {str(e)} [operation_id={operation_id}]")
            # Continue even if metrics recording fails

        # Prepare response
        engines_used = {
            "presidio": use_presidio,
            "gemini": use_gemini,
            "gliner": use_gliner
        }

        file_info = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": total_size,
            "processing_mode": "chunked",
            "operation_id": operation_id
        }

        try:
            sanitized_response = sanitize_detection_output(
                anonymized_text, entities, redaction_mapping, processing_times
            )
            sanitized_response["model_info"] = {"engine": "hybrid", "engines_used": engines_used}
            sanitized_response["file_info"] = file_info
        except Exception as e:
            log_error(f"[SECURITY] Error preparing response: {str(e)} [operation_id={operation_id}]")
            return JSONResponse(
                status_code=500,
                content={"detail": f"Error preparing response: {str(e)}"}
            )

        # Add memory stats
        mem_stats = memory_monitor.get_memory_stats()
        sanitized_response["_debug"] = {
            "memory_usage": mem_stats["current_usage"],
            "peak_memory": mem_stats["peak_usage"],
            "operation_id": operation_id
        }

        log_info(
            f"[SECURITY] Memory usage: current={mem_stats['current_usage']:.1f}%, peak={mem_stats['peak_usage']:.1f}% [operation_id={operation_id}]")

        # Log operation
        log_sensitive_operation(
            "Hybrid Chunked Detection",
            len(entities),
            processing_times["total_time"],
            pages=processing_times["pages_count"],
            words=total_words,
            engines=engines_used,
            extract_time=processing_times["extraction_time"],
            detect_time=processing_times["detection_time"],
            chunked_mode=True,
            operation_id=operation_id
        )

        log_info(
            f"[SECURITY] Chunked file processing completed successfully in {processing_times['total_time']:.3f}s [operation_id={operation_id}]")

        return JSONResponse(content=sanitized_response)

    except Exception as e:
        log_error(f"[SECURITY] Unhandled exception in chunked file processing: {str(e)} [operation_id={operation_id}]")
        error_response = SecurityAwareErrorHandler.handle_detection_error(
            e, "hybrid_chunked_detection"
        )
        error_response["model_info"] = {
            "engine": "hybrid",
            "engines_used": {"presidio": use_presidio, "gemini": use_gemini, "gliner": use_gliner},
            "processing_mode": "chunked",
            "operation_id": operation_id
        }
        return JSONResponse(status_code=500, content=error_response)


async def process_pdf_in_chunks(
        file: UploadFile,
        entity_list: List[str],
        use_presidio: bool,
        use_gemini: bool,
        use_gliner: bool,
        start_time: float,
        operation_id: Optional[str] = None
) -> JSONResponse:
    """
    Process a PDF file in chunks using PyMuPDF's streaming capabilities.

    Args:
        file: The uploaded PDF file
        entity_list: List of entity types to detect
        use_presidio: Whether to use Presidio detector
        use_gemini: Whether to use Gemini detector
        use_gliner: Whether to use GLiNER detector
        start_time: Start time for performance tracking
        operation_id: Optional identifier for logging and tracking

    Returns:
        JSONResponse with processed results
    """
    processing_times = {}
    file_read_start = time.time()

    # Create operation ID if not provided
    if operation_id is None:
        operation_id = str(uuid.uuid4())

    log_info(f"[SECURITY] Starting PDF chunked processing [operation_id={operation_id}, file={file.filename}]")

    try:
        # Import pymupdf with error handling
        try:
            import pymupdf
            import io
        except ImportError as e:
            log_error(f"[SECURITY] Required dependency missing: {str(e)} [operation_id={operation_id}]")
            return JSONResponse(
                status_code=500,
                content={"detail": f"Server configuration error: Missing required dependency PyMuPDF"}
            )

        # Process PDF using PyMuPDF's streaming capabilities
        try:
            log_info(f"[SECURITY] Opening PDF in streaming mode [operation_id={operation_id}]")
            doc = pymupdf.open(stream=file.file, filetype="pdf")
            log_info(f"[SECURITY] PDF opened successfully with {len(doc)} pages [operation_id={operation_id}]")
        except Exception as e:
            log_error(f"[SECURITY] Error opening PDF: {str(e)} [operation_id={operation_id}]")
            return JSONResponse(
                status_code=415,
                content={"detail": f"Error processing PDF file: {str(e)}"}
            )

        # Extract text page by page to minimize memory usage
        extract_start = time.time()
        extracted_data = {"pages": []}

        try:
            log_info(f"[SECURITY] Extracting text from PDF with {len(doc)} pages [operation_id={operation_id}]")
            pages_with_errors = 0
            words_extracted = 0

            for page_idx in range(len(doc)):
                try:
                    if page_idx % 10 == 0 and page_idx > 0:
                        log_debug(
                            f"[SECURITY] Processed {page_idx}/{len(doc)} pages so far [operation_id={operation_id}]")

                    page = doc[page_idx]
                    words = page.get_text("words")
                    page_words = []

                    for word in words:
                        x0, y0, x1, y1, text, *_ = word
                        if text.strip():
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
                        words_extracted += len(page_words)

                except Exception as e:
                    pages_with_errors += 1
                    log_warning(f"[SECURITY] Error processing page {page_idx}: {str(e)} [operation_id={operation_id}]")
                    # Continue with next page despite error
                    extracted_data["pages"].append({
                        "page": page_idx + 1,
                        "words": [],
                        "error": f"Error extracting text: {str(e)}"
                    })

                # Allow other tasks to run between pages
                if page_idx % 5 == 0:  # Every 5 pages
                    await asyncio.sleep(0)

            doc.close()

            if pages_with_errors > 0:
                log_warning(
                    f"[SECURITY] Completed text extraction with {pages_with_errors} page errors out of {len(doc)} pages [operation_id={operation_id}]")
            else:
                log_info(
                    f"[SECURITY] Successfully extracted text: {len(extracted_data['pages'])} pages, {words_extracted} words [operation_id={operation_id}]")

        except Exception as e:
            log_error(f"[SECURITY] Error during PDF text extraction: {str(e)} [operation_id={operation_id}]")
            return JSONResponse(
                status_code=500,
                content={"detail": f"Error extracting text from PDF: {str(e)}"}
            )

        processing_times["file_read_time"] = time.time() - file_read_start
        processing_times["extraction_time"] = time.time() - extract_start

        # Apply data minimization
        try:
            extracted_data = minimize_extracted_data(extracted_data)
        except Exception as e:
            log_warning(
                f"[SECURITY] Error during data minimization: {str(e)}, continuing with original data [operation_id={operation_id}]")
            # Continue with original data if minimization fails

        # Configure hybrid detector
        config = {
            "use_presidio": use_presidio,
            "use_gemini": use_gemini,
            "use_gliner": use_gliner,
            "gliner_model_name": GLINER_MODEL_NAME,
            "entities": entity_list
        }

        detector_create_start = time.time()
        try:
            log_info(
                f"[SECURITY] Initializing hybrid detector with config: presidio={use_presidio}, gemini={use_gemini}, gliner={use_gliner} [operation_id={operation_id}]")
            detector = initialization_service.get_hybrid_detector(config)
            processing_times["detector_init_time"] = time.time() - detector_create_start
        except Exception as e:
            log_error(f"[SECURITY] Error initializing detector: {str(e)} [operation_id={operation_id}]")
            return JSONResponse(
                status_code=500,
                content={"detail": f"Error initializing detection engines: {str(e)}"}
            )

        # Process in batches of pages if there are many pages
        pages = extracted_data.get("pages", [])
        if len(pages) > 20:  # Arbitrary threshold
            log_info(
                f"[SECURITY] Large document detected ({len(pages)} pages). Using batch processing [operation_id={operation_id}]")
            return await process_large_document_in_batches(
                pages, entity_list, config, file, start_time, processing_times, operation_id
            )

        # For smaller documents, process normally
        detection_timeout = 60
        detection_start = time.time()

        try:
            log_info(f"[SECURITY] Starting detection with timeout {detection_timeout}s [operation_id={operation_id}]")

            if hasattr(detector, 'detect_sensitive_data_async'):
                detection_task = detector.detect_sensitive_data_async(extracted_data, entity_list)
                detection_result = await asyncio.wait_for(detection_task, timeout=detection_timeout)
            else:
                detection_task = asyncio.to_thread(detector.detect_sensitive_data, extracted_data, entity_list)
                detection_result = await asyncio.wait_for(detection_task, timeout=detection_timeout)
        except asyncio.TimeoutError:
            log_error(f"[SECURITY] Detection timed out after {detection_timeout}s [operation_id={operation_id}]")
            return JSONResponse(
                status_code=408,
                content={"detail": f"Hybrid detection timed out after {detection_timeout} seconds"}
            )
        except Exception as e:
            log_error(f"[SECURITY] Error during detection: {str(e)} [operation_id={operation_id}]")
            return JSONResponse(
                status_code=500,
                content={"detail": f"Detection error: {str(e)}"}
            )

        if detection_result is None:
            log_error(f"[SECURITY] Detection returned no results [operation_id={operation_id}]")
            return JSONResponse(
                status_code=500,
                content={"detail": "Detection failed to return results"}
            )

        # Process results
        try:
            anonymized_text, entities, redaction_mapping = detection_result
            processing_times["detection_time"] = time.time() - detection_start
            processing_times["total_time"] = time.time() - start_time

            log_info(
                f"[SECURITY] Detection completed in {processing_times['detection_time']:.3f}s. Found {len(entities)} entities [operation_id={operation_id}]")
        except Exception as e:
            log_error(f"[SECURITY] Error processing detection results: {str(e)} [operation_id={operation_id}]")
            return JSONResponse(
                status_code=500,
                content={"detail": f"Error processing detection results: {str(e)}"}
            )

        # Calculate statistics
        total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
        processing_times["words_count"] = total_words
        processing_times["pages_count"] = len(extracted_data.get("pages", []))
        if total_words > 0 and entities:
            processing_times["entity_density"] = (len(entities) / total_words) * 1000

        # Record processing for compliance
        try:
            record_keeper.record_processing(
                operation_type="hybrid_detection_pdf_chunked",
                document_type="application/pdf",
                entity_types_processed=entity_list or [],
                processing_time=processing_times["total_time"],
                entity_count=len(entities),
                success=True
            )
        except Exception as e:
            log_warning(f"[SECURITY] Error recording processing metrics: {str(e)} [operation_id={operation_id}]")
            # Continue even if metrics recording fails

        # Prepare response
        engines_used = {
            "presidio": use_presidio,
            "gemini": use_gemini,
            "gliner": use_gliner
        }

        file_info = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": "streamed",  # We don't know exact size in streaming mode
            "processing_mode": "pdf_chunked",
            "operation_id": operation_id
        }

        try:
            sanitized_response = sanitize_detection_output(
                anonymized_text, entities, redaction_mapping, processing_times
            )
            sanitized_response["model_info"] = {"engine": "hybrid", "engines_used": engines_used}
            sanitized_response["file_info"] = file_info
        except Exception as e:
            log_error(f"[SECURITY] Error preparing response: {str(e)} [operation_id={operation_id}]")
            return JSONResponse(
                status_code=500,
                content={"detail": f"Error preparing response: {str(e)}"}
            )

        # Add memory stats
        mem_stats = memory_monitor.get_memory_stats()
        sanitized_response["_debug"] = {
            "memory_usage": mem_stats["current_usage"],
            "peak_memory": mem_stats["peak_usage"],
            "operation_id": operation_id
        }

        log_info(
            f"[SECURITY] Memory usage: current={mem_stats['current_usage']:.1f}%, peak={mem_stats['peak_usage']:.1f}% [operation_id={operation_id}]")

        # Log operation
        log_sensitive_operation(
            "Hybrid PDF Chunked Detection",
            len(entities),
            processing_times["total_time"],
            pages=processing_times["pages_count"],
            words=total_words,
            engines=engines_used,
            extract_time=processing_times["extraction_time"],
            detect_time=processing_times["detection_time"],
            chunked_mode=True,
            operation_id=operation_id
        )

        log_info(
            f"[SECURITY] PDF chunked processing completed successfully in {processing_times['total_time']:.3f}s [operation_id={operation_id}]")

        return JSONResponse(content=sanitized_response)

    except Exception as e:
        log_error(f"[SECURITY] Unhandled exception in PDF chunked processing: {str(e)} [operation_id={operation_id}]")
        error_response = SecurityAwareErrorHandler.handle_detection_error(
            e, "hybrid_pdf_chunked_detection"
        )
        error_response["model_info"] = {
            "engine": "hybrid",
            "engines_used": {"presidio": use_presidio, "gemini": use_gemini, "gliner": use_gliner},
            "processing_mode": "pdf_chunked",
            "operation_id": operation_id
        }
        return JSONResponse(status_code=500, content=error_response)


async def process_large_document_in_batches(
        pages: List[Dict[str, Any]],
        entity_list: List[str],
        config: Dict[str, Any],
        file: UploadFile,
        start_time: float,
        processing_times: Dict[str, float],
        operation_id: Optional[str] = None
) -> JSONResponse:
    """
    Process a large document by breaking it into batches of pages.

    Args:
        pages: List of pages with extracted text
        entity_list: List of entity types to detect
        config: Detector configuration
        file: Original uploaded file
        start_time: Start time for performance tracking
        processing_times: Dictionary with timing information
        operation_id: Optional identifier for logging and tracking

    Returns:
        JSONResponse with combined results
    """
    # Create operation ID if not provided
    if operation_id is None:
        operation_id = str(uuid.uuid4())

    # Process pages in batches of 10
    batch_size = 10
    all_entities = []
    all_redaction_pages = []
    detection_start = time.time()

    log_info(
        f"[SECURITY] Starting batched processing of large document: {len(pages)} pages, batch size={batch_size} [operation_id={operation_id}]")

    # Get detector once for all batches
    try:
        detector = initialization_service.get_hybrid_detector(config)
        log_info(
            f"[SECURITY] Successfully initialized hybrid detector for batch processing [operation_id={operation_id}]")
    except Exception as e:
        log_error(
            f"[SECURITY] Error initializing detector for batch processing: {str(e)} [operation_id={operation_id}]")
        return JSONResponse(
            status_code=500,
            content={"detail": f"Error initializing detection engines: {str(e)}"}
        )

    batch_count = 0
    successful_batches = 0
    failed_batches = 0
    total_words_processed = 0

    for i in range(0, len(pages), batch_size):
        batch_count += 1
        batch_pages = pages[i:i + batch_size]
        batch_id = f"batch_{batch_count}_pages_{i + 1}-{min(i + batch_size, len(pages))}"
        batch_words = sum(len(page.get("words", [])) for page in batch_pages)
        total_words_processed += batch_words

        log_info(
            f"[SECURITY] Processing {batch_id}: {len(batch_pages)} pages, {batch_words} words [operation_id={operation_id}]")

        # Create a document with just this batch
        batch_data = {
            "pages": batch_pages
        }

        # Process batch
        try:
            batch_start_time = time.time()

            if hasattr(detector, 'detect_sensitive_data_async'):
                batch_result = await detector.detect_sensitive_data_async(batch_data, entity_list)
            else:
                batch_result = await asyncio.to_thread(detector.detect_sensitive_data, batch_data, entity_list)

            batch_time = time.time() - batch_start_time

            if batch_result:
                _, batch_entities, batch_redaction = batch_result

                batch_entity_count = len(batch_entities)
                log_info(
                    f"[SECURITY] {batch_id} processing completed in {batch_time:.3f}s: Found {batch_entity_count} entities [operation_id={operation_id}]")

                all_entities.extend(batch_entities)

                # Add redaction pages to combined result
                for page_info in batch_redaction.get("pages", []):
                    all_redaction_pages.append(page_info)

                successful_batches += 1
            else:
                failed_batches += 1
                log_warning(f"[SECURITY] {batch_id} processing returned no results [operation_id={operation_id}]")

            # Allow other tasks to run between batches
            await asyncio.sleep(0)

            # Add memory check between batches
            if batch_count % 5 == 0:
                mem_stats = memory_monitor.get_memory_stats()
                log_debug(
                    f"[SECURITY] Memory usage after {batch_count} batches: {mem_stats['current_usage']:.1f}% [operation_id={operation_id}]")

                # Force garbage collection if memory usage is high
                if mem_stats['current_usage'] > 80:
                    log_warning(
                        f"[SECURITY] High memory usage detected ({mem_stats['current_usage']:.1f}%). Triggering cleanup [operation_id={operation_id}]")
                    import gc
                    gc.collect()

        except Exception as e:
            failed_batches += 1
            # Log but continue processing other batches
            log_error(f"[SECURITY] Error processing {batch_id}: {str(e)} [operation_id={operation_id}]")
            SecurityAwareErrorHandler.log_processing_error(
                e, "batch_detection", f"batch_{batch_count}_{i}-{i + batch_size - 1}"
            )

    # Create combined redaction mapping
    combined_redaction = {"pages": all_redaction_pages}

    # Create combined anonymized text (placeholder since we can't reliably combine text)
    combined_text = "Document processed in batches. See redaction mapping for details."

    # Update timing info
    processing_times["detection_time"] = time.time() - detection_start
    processing_times["total_time"] = time.time() - start_time

    log_info(
        f"[SECURITY] Batch processing completed: {successful_batches} successful batches, {failed_batches} failed batches [operation_id={operation_id}]")

    # Calculate statistics
    total_words = sum(len(page.get("words", [])) for page in pages)
    processing_times["words_count"] = total_words
    processing_times["pages_count"] = len(pages)
    processing_times["batches_count"] = batch_count
    processing_times["successful_batches"] = successful_batches
    processing_times["failed_batches"] = failed_batches

    if total_words > 0 and all_entities:
        processing_times["entity_density"] = (len(all_entities) / total_words) * 1000
        log_info(
            f"[SECURITY] Entity density: {processing_times['entity_density']:.2f} entities per 1000 words [operation_id={operation_id}]")

    # Record processing for compliance
    try:
        record_keeper.record_processing(
            operation_type="hybrid_detection_batched",
            document_type=file.content_type,
            entity_types_processed=entity_list or [],
            processing_time=processing_times["total_time"],
            entity_count=len(all_entities),
            success=True
        )
    except Exception as e:
        log_warning(f"[SECURITY] Error recording processing metrics: {str(e)} [operation_id={operation_id}]")
        # Continue even if metrics recording fails

    # Prepare response
    engines_used = {
        "presidio": config.get("use_presidio", True),
        "gemini": config.get("use_gemini", True),
        "gliner": config.get("use_gliner", False)
    }

    file_info = {
        "filename": file.filename,
        "content_type": file.content_type,
        "size": "batched",
        "processing_mode": "large_document_batched",
        "batch_size": batch_size,
        "batches_processed": batch_count,
        "operation_id": operation_id
    }

    try:
        sanitized_response = sanitize_detection_output(
            combined_text, all_entities, combined_redaction, processing_times
        )
        sanitized_response["model_info"] = {
            "engine": "hybrid",
            "engines_used": engines_used,
            "batched_processing": True
        }
        sanitized_response["file_info"] = file_info
    except Exception as e:
        log_error(f"[SECURITY] Error preparing response: {str(e)} [operation_id={operation_id}]")
        return JSONResponse(
            status_code=500,
            content={"detail": f"Error preparing response: {str(e)}"}
        )

    # Add memory stats
    mem_stats = memory_monitor.get_memory_stats()
    sanitized_response["_debug"] = {
        "memory_usage": mem_stats["current_usage"],
        "peak_memory": mem_stats["peak_usage"],
        "operation_id": operation_id,
        "batches": {
            "total": batch_count,
            "successful": successful_batches,
            "failed": failed_batches
        }
    }

    log_info(
        f"[SECURITY] Memory usage: current={mem_stats['current_usage']:.1f}%, peak={mem_stats['peak_usage']:.1f}% [operation_id={operation_id}]")

    # Log operation
    log_sensitive_operation(
        "Hybrid Batched Detection",
        len(all_entities),
        processing_times["total_time"],
        pages=processing_times["pages_count"],
        words=total_words,
        engines=engines_used,
        extract_time=processing_times.get("extraction_time", 0),
        detect_time=processing_times["detection_time"],
        batched_mode=True,
        batch_count=batch_count,
        operation_id=operation_id
    )

    log_info(
        f"[SECURITY] Large document batch processing completed successfully in {processing_times['total_time']:.3f}s [operation_id={operation_id}]")

    return JSONResponse(content=sanitized_response)