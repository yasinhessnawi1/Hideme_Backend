"""
Centralized utility for entity detection processing leveraging optimized PDF processing.

This module provides a unified processing function that can be used by different detection
endpoints to ensure consistent file validation, error handling, and response formatting.
With enhanced performance through centralized PDF processing and optimized synchronization.
"""
import time
import asyncio
from typing import Any, List, Optional, Callable, Dict, Union

from fastapi import UploadFile
from starlette.responses import JSONResponse

from backend.app.document_processing.pdf import PDFTextExtractor
from backend.app.factory.document_processing_factory import DocumentFormat, DocumentProcessingFactory
from backend.app.utils.validation.data_minimization import minimize_extracted_data
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.validation.file_validation import (
    validate_mime_type,
    validate_file_content_async,
    MAX_PDF_SIZE_BYTES,
    MAX_TEXT_SIZE_BYTES
)
from backend.app.utils.helpers.json_helper import validate_requested_entities
from backend.app.utils.synchronization_utils import AsyncTimeoutLock, LockPriority
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.memory_management import memory_monitor
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.validation.sanitize_utils import sanitize_detection_output
from backend.app.utils.logging.secure_logging import log_sensitive_operation


# Shared resource lock for detection processing with lower-level locking
_detection_resource_lock = AsyncTimeoutLock("common_detection_lock", priority=LockPriority.MEDIUM)


async def process_common_detection(
        file: UploadFile,
        requested_entities: Optional[str],
        detector_type: str,
        get_detector_func: Callable[[Optional[List[str]]], Any]
) -> JSONResponse:
    """
    Common processing logic for entity detection endpoints with optimized file processing.

    This enhanced implementation leverages centralized PDF processing and optimized synchronization
    to improve performance while maintaining consistent error handling and response formatting.

    Args:
        file: The uploaded file
        requested_entities: Optional string with requested entity types
        detector_type: Type of detector being used (for logging)
        get_detector_func: Function to get the appropriate detector instance

    Returns:
        JSON response with detection results or error
    """
    start_time = time.time()
    processing_times = {}
    operation_id = f"{detector_type}_{int(time.time())}"

    try:
        # Validate allowed MIME types
        allowed_types = ["application/pdf", "text/plain", "text/csv", "text/markdown", "text/html"]
        if not validate_mime_type(file.content_type, allowed_types):
            return JSONResponse(
                status_code=415,
                content={"detail": "Unsupported file type. Please upload a PDF or text file."}
            )

        # Validate entity list
        try:
            entity_list = validate_requested_entities(requested_entities)
        except Exception as e:
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                e, "entity_validation", 400
            )
            return JSONResponse(status_code=status_code, content=error_response)

        # Validate file size with a small read first
        file_read_start = time.time()
        first_chunk = await file.read(8192)
        await file.seek(0)

        # Determine max size based on file type
        max_size = MAX_PDF_SIZE_BYTES if "pdf" in file.content_type.lower() else MAX_TEXT_SIZE_BYTES

        # Check initial chunk size
        if len(first_chunk) > max_size:
            return JSONResponse(
                status_code=413,
                content={"detail": f"File size exceeds maximum allowed ({max_size // (1024 * 1024)}MB)"}
            )

        # Read full content
        contents = await file.read()
        if len(contents) > max_size:
            return JSONResponse(
                status_code=413,
                content={"detail": f"File size exceeds maximum allowed ({max_size // (1024 * 1024)}MB)"}
            )

        processing_times["file_read_time"] = time.time() - file_read_start

        # Validate file content
        is_valid, reason, detected_mime = await validate_file_content_async(
            contents, file.filename, file.content_type
        )
        if not is_valid:
            return JSONResponse(
                status_code=415,
                content={"detail": reason}
            )

        # Step 1: Extract text data using the centralized PDFTextExtractor
        extract_start = time.time()
        log_info(f"[DETECTION] Extracting text for detection [operation_id={operation_id}]")

        if "pdf" in file.content_type.lower():
            # Use centralized PDFTextExtractor for PDF files
            extractor = PDFTextExtractor(contents)
            extracted_data = extractor.extract_text(detect_images=True)
            extractor.close()
        else:
            # For non-PDF formats, use the appropriate extractor
            document_format = None
            if file.filename:
                if file.filename.lower().endswith('.pdf'):
                    document_format = DocumentFormat.PDF
                elif file.filename.lower().endswith(('.docx', '.doc')):
                    document_format = DocumentFormat.DOCX
                elif file.filename.lower().endswith('.txt'):
                    document_format = DocumentFormat.TXT

            # Use DocumentProcessingFactory with in-memory content
            extractor = DocumentProcessingFactory.create_document_extractor(contents, document_format)
            extracted_data = extractor.extract_text()
            extractor.close()

        processing_times["extraction_time"] = time.time() - extract_start

        # Apply data minimization
        minimized_data = minimize_extracted_data(extracted_data)

        # Try to get detector with lock - handle timeout gracefully
        detector_start = time.time()
        log_info(f"[DETECTION] Attempting to acquire detector lock for {detector_type} [operation_id={operation_id}]")

        detector = None
        try:
            # Use lock with timeout to prevent deadlocks
            async with _detection_resource_lock.acquire_timeout(timeout=10.0):
                log_info(f"[DETECTION] Successfully acquired lock for {detector_type} detector [operation_id={operation_id}]")
                detector = get_detector_func(entity_list)
                processing_times["detector_init_time"] = time.time() - detector_start
        except Exception as lock_error:
            log_warning(f"[DETECTION] Error acquiring detector lock: {str(lock_error)} [operation_id={operation_id}]")
            # Try to get detector without lock as fallback
            detector = get_detector_func(entity_list)
            processing_times["detector_init_time"] = time.time() - detector_start

        if detector is None:
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                ValueError("Failed to initialize detector"), f"{detector_type}_detector_init", 500
            )
            return JSONResponse(status_code=status_code, content=error_response)

        # Run detection with timeout
        detection_start = time.time()
        try:
            # Use timeout for detection to prevent hanging
            if hasattr(detector, 'detect_sensitive_data_async'):
                detection_result = await asyncio.wait_for(
                    detector.detect_sensitive_data_async(minimized_data, entity_list),
                    timeout=120.0  # 2 minute timeout for detection
                )
            else:
                detection_result = await asyncio.wait_for(
                    asyncio.to_thread(detector.detect_sensitive_data, minimized_data, entity_list),
                    timeout=120.0  # 2 minute timeout for detection
                )
        except asyncio.TimeoutError:
            log_error(f"[DETECTION] Detection operation timed out for {detector_type} [operation_id={operation_id}]")
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                TimeoutError(f"Detection operation timed out after 120.0 seconds"),
                f"{detector_type}_detection_timeout",
                504  # Gateway Timeout status
            )
            return JSONResponse(status_code=status_code, content=error_response)

        processing_times["detection_time"] = time.time() - detection_start

        if detection_result is None:
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                ValueError("Detection returned no results"), f"{detector_type}_detection", 500
            )
            return JSONResponse(status_code=status_code, content=error_response)

        anonymized_text, entities, redaction_mapping = detection_result
        processing_times["total_time"] = time.time() - start_time

        # Calculate statistics and prepare response
        total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
        processing_times["words_count"] = total_words
        processing_times["pages_count"] = len(extracted_data.get("pages", []))

        if total_words > 0 and entities:
            processing_times["entity_density"] = (len(entities) / total_words) * 1000

        # Record processing
        record_keeper.record_processing(
            operation_type=f"{detector_type}_detection",
            document_type=file.content_type,
            entity_types_processed=entity_list or [],
            processing_time=processing_times["total_time"],
            entity_count=len(entities),
            success=True
        )

        # Prepare response
        sanitized_response = sanitize_detection_output(
            anonymized_text, entities, redaction_mapping, processing_times
        )
        sanitized_response["model_info"] = {"engine": detector_type}
        sanitized_response["file_info"] = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(contents)
        }

        # Add memory statistics
        mem_stats = memory_monitor.get_memory_stats()
        sanitized_response["_debug"] = {
            "memory_usage": mem_stats["current_usage"],
            "peak_memory": mem_stats["peak_usage"],
            "operation_id": operation_id
        }

        # Log operation
        log_sensitive_operation(
            f"{detector_type.capitalize()} Detection",
            len(entities),
            processing_times["total_time"],
            pages=processing_times["pages_count"],
            words=total_words,
            extract_time=processing_times["extraction_time"],
            detect_time=processing_times["detection_time"]
        )

        return JSONResponse(content=sanitized_response)

    except Exception as e:
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, f"{detector_type}_detection", 500
        )
        return JSONResponse(status_code=status_code, content=error_response)


async def process_multiple_detection(
        files: List[UploadFile],
        requested_entities: Optional[str],
        detector_type: str,
        get_detector_func: Callable[[Optional[List[str]]], Any],
        max_workers: Optional[int] = None
) -> JSONResponse:
    """
    Process multiple files for entity detection in parallel using optimized PDF processing.

    Args:
        files: List of uploaded files
        requested_entities: Optional string with requested entity types
        detector_type: Type of detector being used (for logging)
        get_detector_func: Function to get the appropriate detector instance
        max_workers: Maximum number of parallel workers (None for auto)

    Returns:
        JSON response with detection results for all files
    """
    from backend.app.utils.parallel.batch import BatchProcessingUtils as BatchProcessingHelper

    start_time = time.time()
    operation_id = f"multiple_{detector_type}_{int(time.time())}"

    try:
        # Validate entity list
        try:
            entity_list = validate_requested_entities(requested_entities)
        except Exception as e:
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                e, "entity_validation", 400
            )
            return JSONResponse(status_code=status_code, content=error_response)

        # Initialize detector
        detector = None
        try:
            async with _detection_resource_lock.acquire_timeout(timeout=10.0):
                detector = get_detector_func(entity_list)
        except Exception as lock_error:
            log_warning(f"[DETECTION] Error acquiring detector lock: {str(lock_error)} [operation_id={operation_id}]")
            # Try to get detector without lock as fallback
            detector = get_detector_func(entity_list)

        if detector is None:
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                ValueError("Failed to initialize detector"), f"{detector_type}_detector_init", 500
            )
            return JSONResponse(status_code=status_code, content=error_response)

        # Separate PDF files from others for optimized processing
        pdf_files = []
        pdf_indices = []
        other_files = []
        other_indices = []

        for i, file in enumerate(files):
            content_type = file.content_type or "application/octet-stream"
            if "pdf" in content_type.lower():
                pdf_files.append(file)
                pdf_indices.append(i)
            else:
                other_files.append(file)
                other_indices.append(i)

        # Process PDF files with batch helper if available
        pdf_results = []
        if pdf_files and hasattr(BatchProcessingHelper, 'batch_process_pdf_text_extraction'):
            log_info(f"[DETECTION] Processing {len(pdf_files)} PDF files with batch helper [operation_id={operation_id}]")
            try:
                extraction_results = await BatchProcessingHelper.batch_process_pdf_text_extraction(
                    pdf_files,
                    max_workers=max_workers,
                    detect_images=True
                )

                # Process extracted data for entity detection
                for i, (idx, extracted_data) in enumerate(extraction_results):
                    try:
                        # Skip files with extraction errors
                        if "error" in extracted_data:
                            pdf_results.append((pdf_indices[i], {
                                "status": "error",
                                "error": extracted_data.get("error", "Extraction failed")
                            }))
                            continue

                        # Apply data minimization
                        minimized_data = minimize_extracted_data(extracted_data)

                        # Detect entities
                        if hasattr(detector, 'detect_sensitive_data_async'):
                            detection_result = await detector.detect_sensitive_data_async(minimized_data, entity_list)
                        else:
                            detection_result = await asyncio.to_thread(
                                detector.detect_sensitive_data, minimized_data, entity_list
                            )

                        anonymized_text, entities, redaction_mapping = detection_result

                        # Calculate statistics
                        total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
                        processing_times = {
                            "total_time": time.time() - start_time,
                            "words_count": total_words,
                            "pages_count": len(extracted_data.get("pages", [])),
                            "entity_density": (len(entities) / total_words) * 1000 if total_words > 0 else 0
                        }

                        # Prepare response
                        file = pdf_files[i]
                        sanitized_response = sanitize_detection_output(
                            anonymized_text, entities, redaction_mapping, processing_times
                        )
                        sanitized_response["model_info"] = {"engine": detector_type}
                        sanitized_response["file_info"] = {
                            "filename": file.filename,
                            "content_type": file.content_type
                        }

                        pdf_results.append((pdf_indices[i], {
                            "status": "success",
                            "results": sanitized_response
                        }))
                    except Exception as e:
                        pdf_results.append((pdf_indices[i], {
                            "status": "error",
                            "error": str(e)
                        }))
            except Exception as e:
                log_error(f"[DETECTION] Batch PDF processing failed: {str(e)} [operation_id={operation_id}]")
                # Continue with individual processing for PDFs

        # Process remaining files individually (and PDFs if batch processing failed)
        if not pdf_results:
            # Process all PDFs individually
            for i, file in enumerate(pdf_files):
                try:
                    response = await process_common_detection(file, requested_entities, detector_type, get_detector_func)
                    pdf_results.append((pdf_indices[i], {
                        "status": "success" if response.status_code == 200 else "error",
                        "results": response.body if response.status_code == 200 else {"error": "Detection failed"}
                    }))
                except Exception as e:
                    pdf_results.append((pdf_indices[i], {
                        "status": "error",
                        "error": str(e)
                    }))

        # Process other file types
        other_results = []
        for i, file in enumerate(other_files):
            try:
                response = await process_common_detection(file, requested_entities, detector_type, get_detector_func)
                other_results.append((other_indices[i], {
                    "status": "success" if response.status_code == 200 else "error",
                    "results": response.body if response.status_code == 200 else {"error": "Detection failed"}
                }))
            except Exception as e:
                other_results.append((other_indices[i], {
                    "status": "error",
                    "error": str(e)
                }))

        # Combine and sort results
        all_results = pdf_results + other_results
        sorted_results = [result for _, result in sorted(all_results, key=lambda x: x[0])]

        # Calculate summary
        successful = sum(1 for r in sorted_results if r.get("status") == "success")
        total_entities = sum(
            r.get("results", {}).get("entities_detected", {}).get("total", 0)
            for r in sorted_results if r.get("status") == "success"
        )

        # Create response
        response = {
            "batch_summary": {
                "total_files": len(files),
                "successful": successful,
                "failed": len(files) - successful,
                "total_entities": total_entities,
                "total_time": time.time() - start_time
            },
            "file_results": sorted_results
        }

        # Record batch processing
        record_keeper.record_processing(
            operation_type=f"multiple_{detector_type}_detection",
            document_type="multiple_files",
            entity_types_processed=entity_list or [],
            processing_time=time.time() - start_time,
            file_count=len(files),
            entity_count=total_entities,
            success=(successful > 0)
        )

        return JSONResponse(content=response)
    except Exception as e:
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, f"multiple_{detector_type}_detection", 500
        )
        return JSONResponse(status_code=status_code, content=error_response)