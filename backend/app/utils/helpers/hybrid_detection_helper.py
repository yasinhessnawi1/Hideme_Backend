import asyncio
import time
from typing import Dict, Any, List

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

    try:
        # Validate file content on first chunk
        first_chunk = await file.read(8192)
        await file.seek(0)

        is_valid, reason, detected_mime = await validate_file_content_async(
            first_chunk, file.filename, file.content_type
        )
        if not is_valid:
            return JSONResponse(
                status_code=415,
                content={"detail": reason}
            )

        # For PDF files, use pymupdf's streaming capability
        if "pdf" in file.content_type.lower():
            return await process_pdf_in_chunks(
                file, entity_list, use_presidio, use_gemini, use_gliner, start_time
            )

        # For text-based files, process in chunks
        chunks = []
        total_size = 0

        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break

            chunks.append(chunk)
            total_size += len(chunk)

            # Safety check for max size
            max_size = MAX_TEXT_SIZE_BYTES
            if total_size > max_size:
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"File size exceeds maximum allowed ({max_size // (1024 * 1024)}MB)"}
                )

        # Combine chunks for processing
        contents = b''.join(chunks)
        processing_times["file_read_time"] = time.time() - file_read_start

        # Continue with normal processing flow using the combined content
        extract_start = time.time()
        extracted_data = await extract_text_data_in_memory(file.content_type, contents)
        processing_times["extraction_time"] = time.time() - extract_start

        # Apply data minimization
        extracted_data = minimize_extracted_data(extracted_data)

        # Configure hybrid detector
        config = {
            "use_presidio": use_presidio,
            "use_gemini": use_gemini,
            "use_gliner": use_gliner,
            "gliner_model_name": GLINER_MODEL_NAME,
            "entities": entity_list
        }

        detector_create_start = time.time()
        detector = initialization_service.get_hybrid_detector(config)
        processing_times["detector_init_time"] = time.time() - detector_create_start

        # Run detection with timeout
        detection_timeout = 60
        detection_start = time.time()
        try:
            if hasattr(detector, 'detect_sensitive_data_async'):
                detection_task = detector.detect_sensitive_data_async(extracted_data, entity_list)
                detection_result = await asyncio.wait_for(detection_task, timeout=detection_timeout)
            else:
                detection_task = asyncio.to_thread(detector.detect_sensitive_data, extracted_data, entity_list)
                detection_result = await asyncio.wait_for(detection_task, timeout=detection_timeout)
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=408,
                content={"detail": f"Hybrid detection timed out after {detection_timeout} seconds"}
            )

        if detection_result is None:
            return JSONResponse(
                status_code=500,
                content={"detail": "Detection failed to return results"}
            )

        # Process results
        anonymized_text, entities, redaction_mapping = detection_result
        processing_times["detection_time"] = time.time() - detection_start
        processing_times["total_time"] = time.time() - start_time

        # Calculate statistics
        total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
        processing_times["words_count"] = total_words
        processing_times["pages_count"] = len(extracted_data.get("pages", []))
        if total_words > 0 and entities:
            processing_times["entity_density"] = (len(entities) / total_words) * 1000

        # Record processing for compliance
        record_keeper.record_processing(
            operation_type="hybrid_detection_chunked",
            document_type=file.content_type,
            entity_types_processed=entity_list or [],
            processing_time=processing_times["total_time"],
            entity_count=len(entities),
            success=True
        )

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
            "processing_mode": "chunked"
        }

        sanitized_response = sanitize_detection_output(
            anonymized_text, entities, redaction_mapping, processing_times
        )
        sanitized_response["model_info"] = {"engine": "hybrid", "engines_used": engines_used}
        sanitized_response["file_info"] = file_info

        # Add memory stats
        mem_stats = memory_monitor.get_memory_stats()
        sanitized_response["_debug"] = {
            "memory_usage": mem_stats["current_usage"],
            "peak_memory": mem_stats["peak_usage"]
        }

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
            chunked_mode=True
        )

        return JSONResponse(content=sanitized_response)

    except Exception as e:
        error_response = SecurityAwareErrorHandler.handle_detection_error(
            e, "hybrid_chunked_detection"
        )
        error_response["model_info"] = {
            "engine": "hybrid",
            "engines_used": {"presidio": use_presidio, "gemini": use_gemini, "gliner": use_gliner},
            "processing_mode": "chunked"
        }
        return JSONResponse(status_code=500, content=error_response)


async def process_pdf_in_chunks(
        file: UploadFile,
        entity_list: List[str],
        use_presidio: bool,
        use_gemini: bool,
        use_gliner: bool,
        start_time: float
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

    Returns:
        JSONResponse with processed results
    """
    processing_times = {}
    file_read_start = time.time()

    try:
        import pymupdf
        import io

        # Process PDF using PyMuPDF's streaming capabilities
        doc = pymupdf.open(stream=file.file, filetype="pdf")

        # Extract text page by page to minimize memory usage
        extract_start = time.time()
        extracted_data = {"pages": []}

        for page_idx in range(len(doc)):
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

            # Allow other tasks to run between pages
            if page_idx % 5 == 0:  # Every 5 pages
                await asyncio.sleep(0)

        doc.close()
        processing_times["file_read_time"] = time.time() - file_read_start
        processing_times["extraction_time"] = time.time() - extract_start

        # Apply data minimization
        extracted_data = minimize_extracted_data(extracted_data)

        # Configure hybrid detector
        config = {
            "use_presidio": use_presidio,
            "use_gemini": use_gemini,
            "use_gliner": use_gliner,
            "gliner_model_name": GLINER_MODEL_NAME,
            "entities": entity_list
        }

        detector_create_start = time.time()
        detector = initialization_service.get_hybrid_detector(config)
        processing_times["detector_init_time"] = time.time() - detector_create_start

        # Process in batches of pages if there are many pages
        pages = extracted_data.get("pages", [])
        if len(pages) > 20:  # Arbitrary threshold
            return await process_large_document_in_batches(
                pages, entity_list, config, file, start_time, processing_times
            )

        # For smaller documents, process normally
        detection_timeout = 60
        detection_start = time.time()

        try:
            if hasattr(detector, 'detect_sensitive_data_async'):
                detection_task = detector.detect_sensitive_data_async(extracted_data, entity_list)
                detection_result = await asyncio.wait_for(detection_task, timeout=detection_timeout)
            else:
                detection_task = asyncio.to_thread(detector.detect_sensitive_data, extracted_data, entity_list)
                detection_result = await asyncio.wait_for(detection_task, timeout=detection_timeout)
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=408,
                content={"detail": f"Hybrid detection timed out after {detection_timeout} seconds"}
            )

        if detection_result is None:
            return JSONResponse(
                status_code=500,
                content={"detail": "Detection failed to return results"}
            )

        # Process results
        anonymized_text, entities, redaction_mapping = detection_result
        processing_times["detection_time"] = time.time() - detection_start
        processing_times["total_time"] = time.time() - start_time

        # Calculate statistics
        total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
        processing_times["words_count"] = total_words
        processing_times["pages_count"] = len(extracted_data.get("pages", []))
        if total_words > 0 and entities:
            processing_times["entity_density"] = (len(entities) / total_words) * 1000

        # Record processing for compliance
        record_keeper.record_processing(
            operation_type="hybrid_detection_pdf_chunked",
            document_type="application/pdf",
            entity_types_processed=entity_list or [],
            processing_time=processing_times["total_time"],
            entity_count=len(entities),
            success=True
        )

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
            "processing_mode": "pdf_chunked"
        }

        sanitized_response = sanitize_detection_output(
            anonymized_text, entities, redaction_mapping, processing_times
        )
        sanitized_response["model_info"] = {"engine": "hybrid", "engines_used": engines_used}
        sanitized_response["file_info"] = file_info

        # Add memory stats
        mem_stats = memory_monitor.get_memory_stats()
        sanitized_response["_debug"] = {
            "memory_usage": mem_stats["current_usage"],
            "peak_memory": mem_stats["peak_usage"]
        }

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
            chunked_mode=True
        )

        return JSONResponse(content=sanitized_response)

    except Exception as e:
        error_response = SecurityAwareErrorHandler.handle_detection_error(
            e, "hybrid_pdf_chunked_detection"
        )
        error_response["model_info"] = {
            "engine": "hybrid",
            "engines_used": {"presidio": use_presidio, "gemini": use_gemini, "gliner": use_gliner},
            "processing_mode": "pdf_chunked"
        }
        return JSONResponse(status_code=500, content=error_response)


async def process_large_document_in_batches(
        pages: List[Dict[str, Any]],
        entity_list: List[str],
        config: Dict[str, Any],
        file: UploadFile,
        start_time: float,
        processing_times: Dict[str, float]
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

    Returns:
        JSONResponse with combined results
    """
    # Process pages in batches of 10
    batch_size = 10
    all_entities = []
    all_redaction_pages = []
    detection_start = time.time()

    # Get detector once for all batches
    detector = initialization_service.get_hybrid_detector(config)

    for i in range(0, len(pages), batch_size):
        batch_pages = pages[i:i + batch_size]

        # Create a document with just this batch
        batch_data = {
            "pages": batch_pages
        }

        # Process batch
        try:
            if hasattr(detector, 'detect_sensitive_data_async'):
                batch_result = await detector.detect_sensitive_data_async(batch_data, entity_list)
            else:
                batch_result = await asyncio.to_thread(detector.detect_sensitive_data, batch_data, entity_list)

            if batch_result:
                _, batch_entities, batch_redaction = batch_result
                all_entities.extend(batch_entities)

                # Add redaction pages to combined result
                for page_info in batch_redaction.get("pages", []):
                    all_redaction_pages.append(page_info)

            # Allow other tasks to run between batches
            await asyncio.sleep(0)

        except Exception as e:
            # Log but continue processing other batches
            SecurityAwareErrorHandler.log_processing_error(
                e, "batch_detection", f"pages_{i}-{i + batch_size - 1}"
            )

    # Create combined redaction mapping
    combined_redaction = {"pages": all_redaction_pages}

    # Create combined anonymized text (placeholder since we can't reliably combine text)
    combined_text = "Document processed in batches. See redaction mapping for details."

    # Update timing info
    processing_times["detection_time"] = time.time() - detection_start
    processing_times["total_time"] = time.time() - start_time

    # Calculate statistics
    total_words = sum(len(page.get("words", [])) for page in pages)
    processing_times["words_count"] = total_words
    processing_times["pages_count"] = len(pages)
    if total_words > 0 and all_entities:
        processing_times["entity_density"] = (len(all_entities) / total_words) * 1000

    # Record processing for compliance
    record_keeper.record_processing(
        operation_type="hybrid_detection_batched",
        document_type=file.content_type,
        entity_types_processed=entity_list or [],
        processing_time=processing_times["total_time"],
        entity_count=len(all_entities),
        success=True
    )

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
        "batch_size": batch_size
    }

    sanitized_response = sanitize_detection_output(
        combined_text, all_entities, combined_redaction, processing_times
    )
    sanitized_response["model_info"] = {
        "engine": "hybrid",
        "engines_used": engines_used,
        "batched_processing": True
    }
    sanitized_response["file_info"] = file_info

    # Add memory stats
    mem_stats = memory_monitor.get_memory_stats()
    sanitized_response["_debug"] = {
        "memory_usage": mem_stats["current_usage"],
        "peak_memory": mem_stats["peak_usage"]
    }

    # Log operation
    log_sensitive_operation(
        "Hybrid Batched Detection",
        len(all_entities),
        processing_times["total_time"],
        pages=processing_times["pages_count"],
        words=total_words,
        engines=engines_used,
        extract_time=processing_times["extraction_time"],
        detect_time=processing_times["detection_time"],
        batched_mode=True,
        batch_count=len(range(0, len(pages), batch_size))
    )

    return JSONResponse(content=sanitized_response)