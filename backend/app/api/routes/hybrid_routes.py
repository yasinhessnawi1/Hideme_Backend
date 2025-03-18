import asyncio
import time
from typing import Optional

from fastapi import APIRouter, File, UploadFile, Form, Request, HTTPException
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.configs.gliner_config import GLINER_MODEL_NAME, GLINER_ENTITIES
from backend.app.document_processing.pdf import extraction_processor
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.data_minimization import minimize_extracted_data
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.file_validation import (
    validate_mime_type,
    validate_file_content_async,
    MAX_PDF_SIZE_BYTES,
    MAX_TEXT_SIZE_BYTES
)
from backend.app.utils.helpers import gemini_usage_manager
from backend.app.utils.helpers.hybrid_detection_helper import process_file_in_chunks
from backend.app.utils.helpers.json_helper import validate_requested_entities
from backend.app.utils.logger import log_warning, log_error, log_info
from backend.app.utils.memory_management import memory_optimized, memory_monitor
from backend.app.utils.processing_records import record_keeper
from backend.app.utils.sanitize_utils import sanitize_detection_output
from backend.app.utils.secure_file_utils import SecureTempFileManager
from backend.app.utils.secure_logging import log_sensitive_operation
from backend.app.utils.synchronization_utils import AsyncTimeoutLock, LockPriority

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

# Define chunk size for large document processing
LARGE_FILE_THRESHOLD = 5 * 1024 * 1024  # 5MB
CHUNK_SIZE = 1 * 1024 * 1024  # 1MB

# Shared lock for managing access to detector resources
_detector_resource_lock = None


def get_detector_resource_lock():
    """
    Get the detector resource lock, initializing it if needed.
    This ensures a single lock instance is used across the application.
    """
    global _detector_resource_lock
    if _detector_resource_lock is None:
        _detector_resource_lock = AsyncTimeoutLock("hybrid_detector_lock", priority=LockPriority.HIGH)
        log_info("[SYSTEM] Hybrid detector resource lock initialized")
    return _detector_resource_lock


@router.post("/detect")
@limiter.limit("8/minute")
@memory_optimized(threshold_mb=100)
async def hybrid_detect_sensitive(
        request: Request,
        file: UploadFile = File(...),
        requested_entities: Optional[str] = Form(None),
        use_presidio: bool = Form(True),
        use_gemini: bool = Form(True),
        use_gliner: bool = Form(False)
):
    """
    Detect sensitive information using multiple detection engines with enhanced security.

    This endpoint processes the uploaded document with optimized memory usage for large files
    using chunked processing when needed, and avoids unnecessary temporary files.

    Performance characteristics:
    - Memory usage: Adaptive, uses chunked processing for large files
    - Processing time: Increases with document size and complexity
    - Supported engines: Presidio, Gemini, and GLiNER (optional combinations)
    """
    start_time = time.time()
    processing_times = {}
    operation_id = f"hybrid_detect_{int(time.time())}"

    # Validate allowed MIME types
    allowed_types = ["application/pdf", "text/plain", "text/csv", "text/markdown", "text/html"]
    if not validate_mime_type(file.content_type, allowed_types):
        return JSONResponse(
            status_code=415,
            content={"detail": "Unsupported file type. Please upload a PDF or text file."}
        )

    try:
        # Process requested entities
        try:
            # Parse and validate the requested entity types from form data
            entity_list = validate_requested_entities(requested_entities)
            # If GLiNER is enabled but no entities specified, use default GLiNER entities
            if not entity_list and use_gliner:
                entity_list = GLINER_ENTITIES
        except Exception as e:
            # Handle entity validation errors with security-aware error handling
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                e, "entity_validation", 400
            )
            return JSONResponse(status_code=status_code, content=error_response)

        # Check file size - this doesn't need a lock
        file_read_start = time.time()
        first_chunk = await file.read(8192)
        await file.seek(0)

        # Determine max size based on file type
        max_size = MAX_PDF_SIZE_BYTES if "pdf" in file.content_type.lower() else MAX_TEXT_SIZE_BYTES

        # Validate file size before reading full content to prevent DoS attacks
        if len(first_chunk) > max_size:
            return JSONResponse(
                status_code=413,
                content={"detail": f"File size exceeds maximum allowed ({max_size // (1024 * 1024)}MB)"}
            )

        # For very small files, try processing without lock
        small_file = len(first_chunk) < 50 * 1024  # Under 50KB

        if small_file:
            try:
                # Read file content
                file_content = await file.read()
                processing_times["file_read_time"] = time.time() - file_read_start

                # Validate file content
                is_valid, reason, detected_mime = await validate_file_content_async(
                    file_content, file.filename, file.content_type
                )
                if not is_valid:
                    return JSONResponse(
                        status_code=415,
                        content={"detail": reason}
                    )

                # Process small file directly
                log_info(
                    f"[HYBRID] Processing small file without lock: {len(file_content) / 1024:.1f}KB [operation_id={operation_id}]")

                # Extract text data
                extract_start = time.time()
                extracted_data = await SecureTempFileManager.process_content_in_memory_async(
                    file_content,
                    extraction_processor,
                    use_path=False
                )
                processing_times["extraction_time"] = time.time() - extract_start

                # Apply data minimization
                extracted_data = minimize_extracted_data(extracted_data)

                # Configure hybrid detector - use limited engines for small files
                config = {
                    "use_presidio": use_presidio,  # Keep primary detector
                    "use_gemini": False,  # Skip Gemini for small files (reduces API calls)
                    "use_gliner": False,  # Skip GLiNER for small files (memory intensive)
                    "gliner_model_name": GLINER_MODEL_NAME,
                    "entities": entity_list
                }

                detector_create_start = time.time()
                # Get detector (without lock)
                detector = initialization_service.get_hybrid_detector(config)
                processing_times["detector_init_time"] = time.time() - detector_create_start

                # Detect entities with timeout
                detection_start = time.time()
                detection_result = await asyncio.wait_for(
                    detector.detect_sensitive_data_async(extracted_data, entity_list),
                    timeout=10.0  # Short timeout for small files
                )

                if detection_result is None:
                    raise ValueError("Detection failed to return results")

                # Unpack detection results
                anonymized_text, entities, redaction_mapping = detection_result
                processing_times["detection_time"] = time.time() - detection_start
                processing_times["total_time"] = time.time() - start_time

                # Process completed successfully without lock
                log_info(f"[HYBRID] Small file processed successfully without lock [operation_id={operation_id}]")

                # Prepare and return response
                sanitized_response = sanitize_detection_output(
                    anonymized_text, entities, redaction_mapping, processing_times
                )
                sanitized_response["model_info"] = {
                    "engine": "hybrid",
                    "engines_used": {
                        "presidio": use_presidio,
                        "gemini": False,  # Was skipped
                        "gliner": False  # Was skipped
                    },
                    "requested_engines": {
                        "presidio": use_presidio,
                        "gemini": use_gemini,
                        "gliner": use_gliner
                    },
                    "small_file_mode": True
                }
                sanitized_response["file_info"] = {
                    "filename": file.filename,
                    "content_type": file.content_type,
                    "size": len(file_content)
                }

                # Add performance info
                sanitized_response["_debug"] = {
                    "memory_usage": memory_monitor.get_memory_usage(),
                    "peak_memory": memory_monitor.get_peak_usage(),
                    "operation_id": operation_id,
                    "lock_used": False
                }

                return JSONResponse(content=sanitized_response)
            except Exception as small_file_error:
                # If small file processing fails, continue to regular processing
                log_warning(
                    f"[HYBRID] Small file processing failed, falling back to lock: {str(small_file_error)} [operation_id={operation_id}]")
                # Need to reset file position
                await file.seek(0)

        # Decide whether to use chunked processing for larger files
        use_chunked_processing = False
        if hasattr(file, 'size') and file.size and file.size > LARGE_FILE_THRESHOLD:
            use_chunked_processing = True

        # Get the detector resource lock
        detector_lock = get_detector_resource_lock()

        if use_chunked_processing:
            # For large files, try chunked processing with lock
            try:
                async with detector_lock.acquire_timeout(timeout=30.0) as acquired:
                    if not acquired:
                        log_warning(
                            f"[HYBRID] Failed to acquire detector lock for chunked processing [operation_id={operation_id}]")

                        # Try fallback processing without lock - simplified engine config
                        try:
                            # Process with reduced engines to minimize resource contention
                            result = await process_file_in_chunks(
                                file,
                                entity_list,
                                use_presidio=True,  # Always use Presidio
                                use_gemini=False,  # Skip Gemini in fallback mode
                                use_gliner=False,  # Skip GLiNER in fallback mode
                                start_time=start_time,
                                operation_id=operation_id
                            )
                            # Add fallback flags
                            if isinstance(result, JSONResponse):
                                try:
                                    content = result.body.decode()
                                    import json
                                    data = json.loads(content)
                                    data["model_info"]["emergency_mode"] = True
                                    data["model_info"]["requested_engines"] = {
                                        "presidio": use_presidio,
                                        "gemini": use_gemini,
                                        "gliner": use_gliner
                                    }
                                    return JSONResponse(content=data)
                                except:
                                    # If parsing fails, return original response
                                    return result
                            return result
                        except Exception as fallback_error:
                            log_error(
                                f"[HYBRID] Fallback chunked processing failed: {str(fallback_error)} [operation_id={operation_id}]")
                            return JSONResponse(
                                status_code=503,
                                content={
                                    "detail": "Unable to process large file. System is under heavy load.",
                                    "retry_after": 60,
                                    "operation_id": operation_id
                                }
                            )

                    # With lock acquired, process chunked file normally
                    result = await process_file_in_chunks(
                        file,
                        entity_list,
                        use_presidio=use_presidio,
                        use_gemini=use_gemini,
                        use_gliner=use_gliner,
                        start_time=start_time,
                        operation_id=operation_id
                    )
                    return result
            except TimeoutError:
                log_error(
                    f"[HYBRID] Timeout acquiring detector lock for chunked processing [operation_id={operation_id}]")

                # Final emergency fallback without lock
                try:
                    # Process with only Presidio to minimize resource usage
                    result = await process_file_in_chunks(
                        file,
                        entity_list,
                        use_presidio=True,
                        use_gemini=False,
                        use_gliner=False,
                        start_time=start_time,
                        operation_id=operation_id
                    )

                    # Add emergency flags if possible
                    if isinstance(result, JSONResponse):
                        try:
                            content = result.body.decode()
                            import json
                            data = json.loads(content)
                            data["model_info"]["emergency_mode"] = True
                            data["model_info"]["timeout_recovery"] = True
                            data["model_info"]["requested_engines"] = {
                                "presidio": use_presidio,
                                "gemini": use_gemini,
                                "gliner": use_gliner
                            }
                            return JSONResponse(content=data)
                        except:
                            # If parsing fails, return original response
                            return result
                    return result
                except Exception as timeout_error:
                    log_error(
                        f"[HYBRID] Emergency chunked processing failed: {str(timeout_error)} [operation_id={operation_id}]")
                    return JSONResponse(
                        status_code=503,
                        content={
                            "detail": "Service timeout. System is under extreme load.",
                            "retry_after": 120,
                            "operation_id": operation_id
                        }
                    )

        # For standard-sized files, process with regular approach
        try:
            # Read file content (if not already read)
            file_content = await file.read()
            processing_times["file_read_time"] = time.time() - file_read_start

            # Validate file content
            is_valid, reason, detected_mime = await validate_file_content_async(
                file_content, file.filename, file.content_type
            )
            if not is_valid:
                return JSONResponse(
                    status_code=415,
                    content={"detail": reason}
                )

            # Initialize extraction
            extract_start = time.time()

            # Try to acquire detector lock with timeout for extraction and processing
            try:
                async with detector_lock.acquire_timeout(timeout=30.0) as acquired:
                    if not acquired:
                        log_warning(
                            f"[HYBRID] Failed to acquire detector lock - attempting with reduced engines [operation_id={operation_id}]")

                        # Try processing with reduced engines (Presidio only)
                        try:
                            # Extract text data
                            extracted_data = await SecureTempFileManager.process_content_in_memory_async(
                                file_content,
                                extraction_processor,
                                use_path=False
                            )
                            processing_times["extraction_time"] = time.time() - extract_start

                            # Apply data minimization
                            extracted_data = minimize_extracted_data(extracted_data)

                            # Configure with Presidio only
                            config = {
                                "use_presidio": True,
                                "use_gemini": False,
                                "use_gliner": False,
                                "gliner_model_name": GLINER_MODEL_NAME,
                                "entities": entity_list
                            }

                            # Get detector with simplified config
                            detector_create_start = time.time()
                            detector = initialization_service.get_hybrid_detector(config)
                            processing_times["detector_init_time"] = time.time() - detector_create_start

                            # Detect entities with timeout
                            detection_start = time.time()
                            detection_result = await asyncio.wait_for(
                                detector.detect_sensitive_data_async(extracted_data, entity_list),
                                timeout=30.0
                            )

                            if detection_result is None:
                                raise ValueError("Detection failed to return results")

                            # Unpack detection results
                            anonymized_text, entities, redaction_mapping = detection_result
                            processing_times["detection_time"] = time.time() - detection_start
                            processing_times["total_time"] = time.time() - start_time

                            # Log partial success
                            log_info(
                                f"[HYBRID] Detection completed with reduced engines (Presidio only) [operation_id={operation_id}]")

                            # Create response with fallback indicators
                            sanitized_response = sanitize_detection_output(
                                anonymized_text, entities, redaction_mapping, processing_times
                            )
                            sanitized_response["model_info"] = {
                                "engine": "hybrid",
                                "engines_used": {
                                    "presidio": True,
                                    "gemini": False,
                                    "gliner": False
                                },
                                "requested_engines": {
                                    "presidio": use_presidio,
                                    "gemini": use_gemini,
                                    "gliner": use_gliner
                                },
                                "emergency_mode": True
                            }
                            sanitized_response["file_info"] = {
                                "filename": file.filename,
                                "content_type": file.content_type,
                                "size": len(file_content)
                            }

                            # Add memory usage statistics
                            mem_stats = memory_monitor.get_memory_stats()
                            sanitized_response["_debug"] = {
                                "memory_usage": mem_stats["current_usage"],
                                "peak_memory": mem_stats["peak_usage"],
                                "operation_id": operation_id,
                                "lock_used": False
                            }

                            return JSONResponse(content=sanitized_response)
                        except Exception as fallback_error:
                            log_error(
                                f"[HYBRID] Fallback processing failed: {str(fallback_error)} [operation_id={operation_id}]")
                            return JSONResponse(
                                status_code=503,
                                content={
                                    "detail": "Detection service unavailable due to system load.",
                                    "retry_after": 30,
                                    "operation_id": operation_id
                                }
                            )

                    # With lock acquired, process normally
                    # Extract text data
                    extracted_data = await SecureTempFileManager.process_content_in_memory_async(
                        file_content,
                        extraction_processor,
                        use_path=False
                    )
                    processing_times["extraction_time"] = time.time() - extract_start

                    # Apply data minimization
                    extracted_data = minimize_extracted_data(extracted_data)

                    # Configure hybrid detector with requested engines
                    config = {
                        "use_presidio": use_presidio,
                        "use_gemini": use_gemini,
                        "use_gliner": use_gliner,
                        "gliner_model_name": GLINER_MODEL_NAME,
                        "entities": entity_list
                    }

                    # Get detector
                    detector_create_start = time.time()
                    detector = initialization_service.get_hybrid_detector(config)
                    processing_times["detector_init_time"] = time.time() - detector_create_start

                    # Detect entities with timeout
                    detection_start = time.time()
                    detection_result = await asyncio.wait_for(
                        detector.detect_sensitive_data_async(extracted_data, entity_list),
                        timeout=60.0
                    )

                    if detection_result is None:
                        raise ValueError("Detection failed to return results")

                    # Unpack detection results
                    anonymized_text, entities, redaction_mapping = detection_result
                    processing_times["detection_time"] = time.time() - detection_start
                    processing_times["total_time"] = time.time() - start_time

                    # Log success
                    log_info(f"[HYBRID] Detection completed successfully with lock [operation_id={operation_id}]")

                    # Create response
                    sanitized_response = sanitize_detection_output(
                        anonymized_text, entities, redaction_mapping, processing_times
                    )
                    sanitized_response["model_info"] = {
                        "engine": "hybrid",
                        "engines_used": {
                            "presidio": use_presidio,
                            "gemini": use_gemini,
                            "gliner": use_gliner
                        }
                    }
                    sanitized_response["file_info"] = {
                        "filename": file.filename,
                        "content_type": file.content_type,
                        "size": len(file_content)
                    }

                    # Add memory usage statistics
                    mem_stats = memory_monitor.get_memory_stats()
                    sanitized_response["_debug"] = {
                        "memory_usage": mem_stats["current_usage"],
                        "peak_memory": mem_stats["peak_usage"],
                        "operation_id": operation_id,
                        "lock_used": True
                    }

                    # Record successful processing
                    record_keeper.record_processing(
                        operation_type="hybrid_detection",
                        document_type=file.content_type,
                        entity_types_processed=entity_list or [],
                        processing_time=processing_times["total_time"],
                        entity_count=len(entities),
                        success=True
                    )

                    # Log operation details
                    log_sensitive_operation(
                        "Hybrid Detection",
                        len(entities),
                        processing_times["total_time"],
                        pages=processing_times["pages_count"] if "pages_count" in processing_times else 0,
                        words=processing_times.get("words_count", 0),
                        engines={"presidio": use_presidio, "gemini": use_gemini, "gliner": use_gliner},
                        extract_time=processing_times["extraction_time"],
                        detect_time=processing_times["detection_time"]
                    )

                    return JSONResponse(content=sanitized_response)
            except TimeoutError:
                log_error(f"[HYBRID] Timeout acquiring detector lock [operation_id={operation_id}]")

                # Final emergency attempt without lock
                try:
                    log_warning(f"[HYBRID] Final emergency attempt after timeout [operation_id={operation_id}]")

                    # Extract text data (if not already done)
                    extracted_data = await SecureTempFileManager.process_content_in_memory_async(
                        file_content,
                        extraction_processor,
                        use_path=False
                    )
                    processing_times["extraction_time"] = time.time() - extract_start

                    # Apply data minimization
                    extracted_data = minimize_extracted_data(extracted_data)

                    # Get detector with Presidio only - most reliable fallback
                    config = {
                        "use_presidio": True,
                        "use_gemini": False,
                        "use_gliner": False,
                        "entities": entity_list
                    }

                    detector = initialization_service.get_hybrid_detector(config)

                    # Process with minimal timeout
                    detection_result = await asyncio.wait_for(
                        detector.detect_sensitive_data_async(extracted_data, entity_list),
                        timeout=30.0
                    )

                    # Unpack and prepare emergency response
                    anonymized_text, entities, redaction_mapping = detection_result

                    sanitized_response = sanitize_detection_output(
                        anonymized_text, entities, redaction_mapping, processing_times
                    )
                    sanitized_response["model_info"] = {
                        "engine": "hybrid",
                        "engines_used": {
                            "presidio": True,
                            "gemini": False,
                            "gliner": False
                        },
                        "requested_engines": {
                            "presidio": use_presidio,
                            "gemini": use_gemini,
                            "gliner": use_gliner
                        },
                        "emergency_mode": True,
                        "timeout_recovery": True
                    }

                    return JSONResponse(content=sanitized_response)
                except Exception as final_error:
                    log_error(
                        f"[HYBRID] Final emergency attempt failed: {str(final_error)} [operation_id={operation_id}]")
                    return JSONResponse(
                        status_code=503,
                        content={
                            "detail": "Service unavailable due to extreme load.",
                            "retry_after": 120,
                            "operation_id": operation_id
                        }
                    )
        except Exception as e:
            # Always release resources if needed
            if 'gemini' in str(e).lower():
                # Release Gemini API slot if using it
                try:
                    await gemini_usage_manager.gemini_usage_manager.release_request_slot()
                except:
                    pass
            raise e

    except HTTPException as e:
        # Let FastAPI handle HTTP exceptions directly
        raise e
    except Exception as e:
        # For all other exceptions, use the security-aware error handler
        # This ensures no sensitive information is leaked in error messages
        error_response = SecurityAwareErrorHandler.handle_detection_error(e, "hybrid_detection")
        error_response["model_info"] = {
            "engine": "hybrid",
            "engines_used": {"presidio": use_presidio, "gemini": use_gemini, "gliner": use_gliner},
            "operation_id": operation_id
        }
        return JSONResponse(status_code=500, content=error_response)