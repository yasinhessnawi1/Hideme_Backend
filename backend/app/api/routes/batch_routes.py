import asyncio
import os
import time
from typing import List, Optional

from fastapi import APIRouter, File, UploadFile, Form, HTTPException, BackgroundTasks, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

from backend.app.configs.gdpr_config import TEMP_FILE_RETENTION_SECONDS
from backend.app.factory import DocumentFormat, EntityDetectionEngine, DocumentProcessingFactory
from backend.app.services.batch_processing_service import BatchProcessingService
from backend.app.utils.batch_processing_utils import (
    validate_detection_engine,
    adjust_parallelism_based_on_memory,
    validate_redaction_mappings,
    determine_processing_strategy,
    process_batch_in_memory,
    process_batch_with_temp_files
)
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.helpers.batch_processing_helper import validate_batch_files_optimized, BatchProcessingHelper
from backend.app.utils.logger import log_warning, log_error
from backend.app.utils.memory_management import memory_optimized, memory_monitor
from backend.app.utils.processing_records import record_keeper
from backend.app.utils.retention_management import retention_manager
from backend.app.utils.secure_file_utils import SecureTempFileManager
from backend.app.utils.secure_logging import log_batch_operation
from backend.app.utils.synchronization_utils import AsyncTimeoutLock, LockPriority

# Configure rate limiter
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

# Create shared lock for managing batch processing resources
_batch_resource_lock = None


def get_batch_resource_lock():
    """
    Get the batch processing lock, initializing it if needed.
    This ensures a single lock instance is used across the application.
    """
    global _batch_resource_lock
    if _batch_resource_lock is None:
        _batch_resource_lock = AsyncTimeoutLock("batch_processing_lock", priority=LockPriority.MEDIUM)
    return _batch_resource_lock


@router.post("/detect")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=75)
async def batch_detect_sensitive(
        request: Request,
        files: List[UploadFile] = File(...),
        requested_entities: Optional[str] = Form(None),
        detection_engine: Optional[str] = Form("presidio"),
        max_parallel_files: Optional[int] = Form(4)
):
    """
    Process multiple files for entity detection with enhanced memory efficiency.

    This optimized implementation:
    - Processes files in memory when possible to avoid temp file creation
    - Uses streaming for large files to reduce memory usage
    - Implements adaptive parallelism based on memory pressure
    - Ensures proper cleanup of any temporary resources
    """
    start_time = time.time()
    operation_id = f"batch_detect_{int(time.time())}"

    try:
        # Validate detection engine
        is_valid, engine_result = await validate_detection_engine(detection_engine)
        if not is_valid:
            return JSONResponse(status_code=400, content=engine_result)

        # Adjust parallelism based on memory pressure
        adjusted_parallel_files = adjust_parallelism_based_on_memory(max_parallel_files)

        # Get the shared batch lock instance
        batch_lock = get_batch_resource_lock()

        # First check if this is a small batch that can be processed without lock
        if len(files) <= 2:  # Small batches can be processed directly
            try:
                # Process small batches directly without lock
                allowed_types = {"application/pdf", "text/plain", "text/csv", "text/markdown", "text/html"}
                async for valid_files in validate_batch_files_optimized(files, allowed_types):
                    # Process files with optimized parallelization
                    results = await BatchProcessingService.detect_entities_in_files(
                        files=[f[0] for f in valid_files],
                        requested_entities=requested_entities,
                        detection_engine=engine_result,
                        max_parallel_files=adjusted_parallel_files
                    )

                    # Add processing timing
                    total_time = time.time() - start_time
                    results["batch_summary"]["api_time"] = total_time
                    results["batch_summary"]["lock_used"] = False

                    # Add engine information
                    results["model_info"] = {
                        "engine": detection_engine,
                        "max_parallel": adjusted_parallel_files,
                        "actual_parallel": results["batch_summary"].get("workers", adjusted_parallel_files)
                    }

                    # Add memory statistics
                    mem_stats = memory_monitor.get_memory_stats()
                    results["_debug"] = {
                        "memory_usage": mem_stats["current_usage"],
                        "peak_memory": mem_stats["peak_usage"],
                        "operation_id": operation_id
                    }

                    return JSONResponse(content=results)
            except Exception as e:
                # If small batch processing fails, fall back to using lock
                log_warning(f"[BATCH] Small batch direct processing failed, falling back to lock: {str(e)}")
                # Continue to lock-based processing

        # For larger batches or if direct processing failed, use lock
        try:
            # Try to acquire lock with 15 second timeout
            async with batch_lock.acquire_timeout(timeout=15.0) as acquired:
                if not acquired:
                    log_warning(
                        f"[BATCH] Failed to acquire batch processing lock - attempting direct processing [operation_id={operation_id}]")

                    # If lock acquisition fails, try direct processing as fallback
                    try:
                        allowed_types = {"application/pdf", "text/plain", "text/csv", "text/markdown", "text/html"}
                        async for valid_files in validate_batch_files_optimized(files, allowed_types):
                            # Process with reduced parallelism to avoid overwhelming system
                            reduced_parallel = max(1, adjusted_parallel_files // 2)
                            results = await BatchProcessingService.detect_entities_in_files(
                                files=[f[0] for f in valid_files],
                                requested_entities=requested_entities,
                                detection_engine=engine_result,
                                max_parallel_files=reduced_parallel
                            )

                            # Add processing timing
                            total_time = time.time() - start_time
                            results["batch_summary"]["api_time"] = total_time
                            results["batch_summary"]["lock_used"] = False
                            results["batch_summary"]["emergency_mode"] = True

                            # Add engine information
                            results["model_info"] = {
                                "engine": detection_engine,
                                "max_parallel": reduced_parallel,
                                "actual_parallel": results["batch_summary"].get("workers", reduced_parallel)
                            }

                            # Add memory statistics
                            mem_stats = memory_monitor.get_memory_stats()
                            results["_debug"] = {
                                "memory_usage": mem_stats["current_usage"],
                                "peak_memory": mem_stats["peak_usage"],
                                "operation_id": operation_id
                            }

                            return JSONResponse(content=results)
                    except Exception as fallback_error:
                        log_error(
                            f"[BATCH] Emergency direct processing failed: {str(fallback_error)} [operation_id={operation_id}]")
                        return JSONResponse(
                            status_code=503,
                            content={
                                "detail": "Batch processing service is overloaded. Try again with fewer files or wait.",
                                "retry_after": 30,
                                "operation_id": operation_id
                            }
                        )

                # With lock acquired, process normally
                allowed_types = {"application/pdf", "text/plain", "text/csv", "text/markdown", "text/html"}
                async for valid_files in validate_batch_files_optimized(files, allowed_types):
                    # Process files with optimized parallelization
                    results = await BatchProcessingService.detect_entities_in_files(
                        files=[f[0] for f in valid_files],
                        requested_entities=requested_entities,
                        detection_engine=engine_result,
                        max_parallel_files=adjusted_parallel_files
                    )

                    # Add processing timing
                    total_time = time.time() - start_time
                    results["batch_summary"]["api_time"] = total_time
                    results["batch_summary"]["lock_used"] = True

                    # Add engine information
                    results["model_info"] = {
                        "engine": detection_engine,
                        "max_parallel": adjusted_parallel_files,
                        "actual_parallel": results["batch_summary"].get("workers", adjusted_parallel_files)
                    }

                    # Add memory statistics
                    mem_stats = memory_monitor.get_memory_stats()
                    results["_debug"] = {
                        "memory_usage": mem_stats["current_usage"],
                        "peak_memory": mem_stats["peak_usage"],
                        "operation_id": operation_id
                    }

                    return JSONResponse(content=results)
        except TimeoutError:
            log_error(f"[BATCH] Timeout acquiring batch processing lock [operation_id={operation_id}]")

            # Final emergency attempt without lock
            try:
                log_warning(f"[BATCH] Final emergency attempt after lock timeout [operation_id={operation_id}]")
                allowed_types = {"application/pdf", "text/plain", "text/csv", "text/markdown", "text/html"}
                async for valid_files in validate_batch_files_optimized(files, allowed_types):
                    # Use minimum parallelism to avoid overloading system
                    min_parallel = 1
                    results = await BatchProcessingService.detect_entities_in_files(
                        files=[f[0] for f in valid_files],
                        requested_entities=requested_entities,
                        detection_engine=engine_result,
                        max_parallel_files=min_parallel
                    )

                    # Add emergency processing flags
                    total_time = time.time() - start_time
                    results["batch_summary"]["api_time"] = total_time
                    results["batch_summary"]["lock_used"] = False
                    results["batch_summary"]["emergency_mode"] = True
                    results["batch_summary"]["timeout_recovery"] = True

                    # Add engine information
                    results["model_info"] = {
                        "engine": detection_engine,
                        "max_parallel": min_parallel,
                        "actual_parallel": results["batch_summary"].get("workers", min_parallel)
                    }

                    return JSONResponse(content=results)
            except Exception as e:
                log_error(f"[BATCH] Final emergency attempt failed: {str(e)} [operation_id={operation_id}]")
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "Service unable to process batch due to system load.",
                        "retry_after": 60,
                        "operation_id": operation_id
                    }
                )

    except HTTPException as e:
        # Re-raise HTTP exceptions
        raise e
    except Exception as e:
        error_response = SecurityAwareErrorHandler.handle_detection_error(e, "batch_detection")
        error_response.update({
            "batch_summary": {
                "total_files": len(files),
                "successful": 0,
                "failed": len(files),
                "total_time": time.time() - start_time,
                "operation_id": operation_id
            }
        })
        return JSONResponse(status_code=500, content=error_response)


@router.post("/redact")
@limiter.limit("3/minute")
@memory_optimized(threshold_mb=200)
async def batch_redact_documents(
        request: Request,
        background_tasks: BackgroundTasks,
        files: List[UploadFile] = File(...),
        redaction_mappings: str = Form(...),
        max_parallel_files: Optional[int] = Form(4)
):
    """
    Apply redactions to multiple documents and return them as a ZIP file via streaming.

    This optimized implementation:
    - Avoids temporary directory creation when possible
    - Processes PDFs entirely in memory
    - Uses an in-memory ZIP buffer for smaller batches
    - Falls back to disk-based processing only for large files
    - Streams the output directly to the client
    """
    start_time = time.time()
    operation_id = f"batch_redact_{int(time.time())}"

    # Adjust parallelism based on memory pressure
    adjusted_parallel_files = adjust_parallelism_based_on_memory(max_parallel_files)

    try:
        # Validate and parse redaction mappings
        is_valid, mappings_result = await validate_redaction_mappings(redaction_mappings)
        if not is_valid:
            return JSONResponse(status_code=400, content=mappings_result)

        mappings_data = mappings_result

        # Get batch lock instance
        batch_lock = get_batch_resource_lock()

        # For very small batches (1-2 files), try processing without lock first
        if len(files) <= 2:
            try:
                # Determine if we can use in-memory processing
                use_memory_buffer, total_size = await determine_processing_strategy(files)

                # Process the small batch directly
                if use_memory_buffer:
                    return await process_batch_in_memory(
                        files, mappings_data, adjusted_parallel_files, start_time, background_tasks
                    )
                else:
                    return await process_batch_with_temp_files(
                        files, mappings_data, adjusted_parallel_files, start_time, background_tasks
                    )
            except Exception as e:
                # If direct processing fails, fall back to lock approach
                log_warning(f"[BATCH] Small batch redaction failed, falling back to lock: {str(e)}")
                # Continue to lock-based processing

        # For larger batches or if direct processing failed, use lock
        try:
            # Try to acquire lock with generous timeout for redaction
            async with batch_lock.acquire_timeout(timeout=20.0) as acquired:
                if not acquired:
                    log_warning(
                        f"[BATCH] Failed to acquire lock for batch redaction - attempting direct processing [operation_id={operation_id}]")

                    # If lock acquisition fails, try direct processing with reduced parallelism
                    try:
                        # Use minimum parallelism to reduce resource usage
                        reduced_parallel = max(1, adjusted_parallel_files // 2)

                        # Determine processing strategy
                        use_memory_buffer, total_size = await determine_processing_strategy(files)

                        if use_memory_buffer:
                            return await process_batch_in_memory(
                                files, mappings_data, reduced_parallel, start_time, background_tasks
                            )
                        else:
                            return await process_batch_with_temp_files(
                                files, mappings_data, reduced_parallel, start_time, background_tasks
                            )
                    except Exception as fallback_error:
                        log_error(
                            f"[BATCH] Emergency direct redaction failed: {str(fallback_error)} [operation_id={operation_id}]")
                        return JSONResponse(
                            status_code=503,
                            content={
                                "detail": "Batch redaction service is overloaded. Try again with fewer files or wait.",
                                "retry_after": 30,
                                "operation_id": operation_id
                            }
                        )

                # With lock acquired, process normally
                use_memory_buffer, total_size = await determine_processing_strategy(files)

                # Use appropriate processing strategy
                if use_memory_buffer:
                    return await process_batch_in_memory(
                        files, mappings_data, adjusted_parallel_files, start_time, background_tasks
                    )
                else:
                    return await process_batch_with_temp_files(
                        files, mappings_data, adjusted_parallel_files, start_time, background_tasks
                    )
        except TimeoutError:
            log_error(f"[BATCH] Timeout acquiring batch processing lock for redaction [operation_id={operation_id}]")

            # Final emergency attempt with minimum parallelism
            try:
                log_warning(
                    f"[BATCH] Final emergency redaction attempt after lock timeout [operation_id={operation_id}]")
                # Use absolute minimum parallelism
                min_parallel = 1
                use_memory_buffer, total_size = await determine_processing_strategy(files)

                if use_memory_buffer:
                    return await process_batch_in_memory(
                        files, mappings_data, min_parallel, start_time, background_tasks
                    )
                else:
                    return await process_batch_with_temp_files(
                        files, mappings_data, min_parallel, start_time, background_tasks
                    )
            except Exception as e:
                log_error(f"[BATCH] Final emergency redaction attempt failed: {str(e)} [operation_id={operation_id}]")
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "Service unable to process batch due to system load.",
                        "retry_after": 60,
                        "operation_id": operation_id
                    }
                )

    except Exception as e:
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "batch_redaction", 500
        )
        error_response["operation_id"] = operation_id
        return JSONResponse(status_code=status_code, content=error_response)


@router.post("/hybrid_detect")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=200)
async def batch_hybrid_detect_sensitive(
        request: Request,
        files: List[UploadFile] = File(...),
        requested_entities: Optional[str] = Form(None),
        use_presidio: bool = Form(True),
        use_gemini: bool = Form(True),
        use_gliner: bool = Form(False),
        max_parallel_files: Optional[int] = Form(4)
):
    """
    Process multiple files using hybrid detection with enhanced security and memory optimization.

    Processes files under GDPR Article 6(1)(f) for legitimate interests of enhancing
    document security and privacy.
    """
    start_time = time.time()
    operation_id = f"batch_hybrid_{int(time.time())}"

    try:
        # Validate detection engines are selected
        if not any([use_presidio, use_gemini, use_gliner]):
            return JSONResponse(
                status_code=400,
                content={"detail": "At least one detection engine must be selected"}
            )

        # Adjust max parallel files with memory-aware constraint
        max_parallel_files = BatchProcessingHelper.get_optimal_batch_size(
            len(files),
            sum(file.size or 0 for file in files)
        )

        # Get batch lock instance
        batch_lock = get_batch_resource_lock()

        # For single-file "batches", try processing directly first
        if len(files) == 1:
            try:
                # Process directly without lock
                results = await BatchProcessingService.detect_entities_in_files(
                    files=files,
                    requested_entities=requested_entities,
                    use_presidio=use_presidio,
                    use_gemini=use_gemini,
                    use_gliner=use_gliner,
                    max_parallel_files=1,  # Single file, single worker
                    detection_engine=EntityDetectionEngine.HYBRID
                )

                # Add processing information
                total_time = time.time() - start_time
                results["batch_summary"]["api_time"] = total_time
                results["batch_summary"]["lock_used"] = False

                # Add model information
                results["model_info"] = {
                    "engine": "hybrid",
                    "engines_used": {
                        "presidio": use_presidio,
                        "gemini": use_gemini,
                        "gliner": use_gliner
                    },
                    "max_parallel": 1,
                    "actual_parallel": results["batch_summary"].get("workers", 1),
                    "operation_id": operation_id
                }

                # Log performance and return results
                log_batch_operation(
                    "Single File Hybrid Detection - No Lock",
                    1,
                    results["batch_summary"]["successful"],
                    total_time
                )

                return JSONResponse(content=results)
            except Exception as e:
                # If direct processing fails, fall back to lock approach
                log_warning(f"[BATCH] Single file hybrid detect failed, falling back to lock: {str(e)}")
                # Continue to lock-based processing

        # For larger batches or if direct processing failed, use lock
        try:
            # Try to acquire lock with timeout
            async with batch_lock.acquire_timeout(timeout=20.0) as acquired:
                if not acquired:
                    log_warning(
                        f"[BATCH] Failed to acquire lock for hybrid detection - attempting direct processing [operation_id={operation_id}]")

                    # If lock acquisition fails, try with reduced parallelism
                    try:
                        # Use minimum parallelism to reduce load
                        reduced_parallel = max(1, max_parallel_files // 2)

                        # Process with reduced settings
                        # If gliner is enabled, disable it in emergency mode as it's the most resource-intensive
                        emergency_gliner = False if use_gliner else False

                        results = await BatchProcessingService.detect_entities_in_files(
                            files=files,
                            requested_entities=requested_entities,
                            use_presidio=use_presidio,
                            use_gemini=use_gemini,
                            use_gliner=emergency_gliner,  # May disable GLiNER in emergency mode
                            max_parallel_files=reduced_parallel,
                            detection_engine=EntityDetectionEngine.HYBRID
                        )

                        # Add emergency flags
                        total_time = time.time() - start_time
                        results["batch_summary"]["api_time"] = total_time
                        results["batch_summary"]["lock_used"] = False
                        results["batch_summary"]["emergency_mode"] = True
                        if use_gliner and not emergency_gliner:
                            results["batch_summary"]["gliner_disabled_emergency"] = True

                        # Add model information
                        results["model_info"] = {
                            "engine": "hybrid",
                            "engines_used": {
                                "presidio": use_presidio,
                                "gemini": use_gemini,
                                "gliner": emergency_gliner
                            },
                            "max_parallel": reduced_parallel,
                            "actual_parallel": results["batch_summary"].get("workers", reduced_parallel),
                            "operation_id": operation_id
                        }

                        # Log performance
                        log_batch_operation(
                            "Batch Hybrid Detection - Emergency Mode",
                            len(files),
                            results["batch_summary"]["successful"],
                            total_time
                        )

                        return JSONResponse(content=results)
                    except Exception as fallback_error:
                        log_error(
                            f"[BATCH] Emergency hybrid detection failed: {str(fallback_error)} [operation_id={operation_id}]")
                        return JSONResponse(
                            status_code=503,
                            content={
                                "detail": "Hybrid detection service is overloaded. Try again with fewer files or fewer engines.",
                                "retry_after": 60,
                                "operation_id": operation_id
                            }
                        )

                # With lock acquired, process normally
                results = await BatchProcessingService.detect_entities_in_files(
                    files=files,
                    requested_entities=requested_entities,
                    use_presidio=use_presidio,
                    use_gemini=use_gemini,
                    use_gliner=use_gliner,
                    max_parallel_files=max_parallel_files,
                    detection_engine=EntityDetectionEngine.HYBRID
                )

                # Add processing timing
                total_time = time.time() - start_time
                results["batch_summary"]["api_time"] = total_time
                results["batch_summary"]["lock_used"] = True

                # Get total entities found
                total_entities = results["batch_summary"].get("total_entities", 0)

                # Record the processing operation
                record_keeper.record_processing(
                    operation_type="batch_hybrid_detection",
                    document_type="multiple",
                    entity_types_processed=[],  # Entity types are handled per file
                    processing_time=total_time,
                    file_count=len(files),
                    entity_count=total_entities,
                )

                # Log performance without sensitive details
                log_batch_operation(
                    "Batch Hybrid Detection",
                    len(files),
                    results["batch_summary"]["successful"],
                    total_time
                )

                # Add model information
                results["model_info"] = {
                    "engine": "hybrid",
                    "engines_used": {
                        "presidio": use_presidio,
                        "gemini": use_gemini,
                        "gliner": use_gliner
                    },
                    "max_parallel": max_parallel_files,
                    "actual_parallel": results["batch_summary"].get("workers", max_parallel_files),
                    "operation_id": operation_id
                }

                # Add memory statistics
                mem_stats = memory_monitor.get_memory_stats()
                results["_debug"] = {
                    "memory_usage": mem_stats["current_usage"],
                    "peak_memory": mem_stats["peak_usage"]
                }

                return JSONResponse(content=results)
        except TimeoutError:
            log_error(f"[BATCH] Timeout acquiring lock for hybrid detection [operation_id={operation_id}]")

            # Final emergency attempt with absolute minimum resources
            try:
                log_warning(
                    f"[BATCH] Final emergency hybrid detection attempt after lock timeout [operation_id={operation_id}]")

                # Process with absolute minimal settings - only use presidio
                results = await BatchProcessingService.detect_entities_in_files(
                    files=files,
                    requested_entities=requested_entities,
                    use_presidio=True,  # Always use Presidio as fallback
                    use_gemini=False,  # Disable Gemini in extreme emergency
                    use_gliner=False,  # Disable GLiNER in extreme emergency
                    max_parallel_files=1,  # Absolute minimum parallelism
                    detection_engine=EntityDetectionEngine.HYBRID
                )

                # Add emergency flags
                total_time = time.time() - start_time
                results["batch_summary"]["api_time"] = total_time
                results["batch_summary"]["lock_used"] = False
                results["batch_summary"]["emergency_mode"] = True
                results["batch_summary"]["timeout_recovery"] = True
                results["batch_summary"]["minimum_engines"] = True

                # Add model information
                results["model_info"] = {
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
                    "max_parallel": 1,
                    "actual_parallel": results["batch_summary"].get("workers", 1),
                    "operation_id": operation_id
                }

                return JSONResponse(content=results)
            except Exception as e:
                log_error(f"[BATCH] Final emergency hybrid detection failed: {str(e)} [operation_id={operation_id}]")
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "Service unable to process hybrid detection due to extreme system load.",
                        "retry_after": 120,
                        "operation_id": operation_id
                    }
                )

    except HTTPException as e:
        # Re-raise HTTP exceptions
        raise e
    except Exception as e:
        # Enhanced error handling
        error_response = SecurityAwareErrorHandler.handle_detection_error(e, "batch_hybrid_detection")
        error_response.update({
            "batch_summary": {
                "total_files": len(files),
                "successful": 0,
                "failed": len(files),
                "total_time": time.time() - start_time,
                "operation_id": operation_id
            },
            "model_info": {
                "engine": "hybrid",
                "engines_used": {
                    "presidio": use_presidio,
                    "gemini": use_gemini,
                    "gliner": use_gliner
                }
            }
        })
        return JSONResponse(status_code=500, content=error_response)


@router.post("/extract")
@limiter.limit("15/minute")
@memory_optimized(threshold_mb=50)
async def batch_extract_text(
        request: Request,
        files: List[UploadFile] = File(...),
        max_parallel_files: Optional[int] = Form(4)
):
    """
    Extract text with positions from multiple files in parallel with enhanced security.

    Processes files under GDPR Article 6(1)(f) - legitimate interests of document
    security and privacy processing.

    Args:
        request: FastAPI request object for rate limiting
        files: List of uploaded files
        max_parallel_files: Maximum number of files to process in parallel

    Returns:
        JSON response with extracted text and positions for each file
    """
    start_time = time.time()
    operation_id = f"batch_extract_{int(time.time())}"

    # Optimize parallel files based on system resources
    max_parallel_files = BatchProcessingHelper.get_optimal_batch_size(
        len(files),
        sum(file.size or 0 for file in files)
    )

    try:
        # Get batch lock instance
        batch_lock = get_batch_resource_lock()

        # For small batches (1-2 files), try without lock first
        if len(files) <= 2:
            try:
                # Process small batches directly
                valid_files_list = []
                async for batch in validate_batch_files_optimized(files):
                    valid_files_list.extend(batch)

                # Define text extraction function
                async def extract_file(file_tuple):
                    """Extract text from a single file with enhanced security."""
                    file_start_time = time.time()
                    file, file_path, content, safe_filename = file_tuple
                    file_name = file.filename or "unnamed_file"

                    try:
                        # Register with retention manager for automatic cleanup
                        if file_path:
                            retention_manager.register_processed_file(file_path, TEMP_FILE_RETENTION_SECONDS)

                        # Determine document format
                        doc_format = None
                        if file_name.lower().endswith('.pdf'):
                            doc_format = DocumentFormat.PDF
                        elif file_name.lower().endswith(('.docx', '.doc')):
                            doc_format = DocumentFormat.DOCX
                        elif file_name.lower().endswith('.txt'):
                            doc_format = DocumentFormat.TXT

                        # Create extractor
                        extractor = DocumentProcessingFactory.create_document_extractor(
                            file_path if file_path else content,
                            doc_format
                        )

                        # Extract text with performance tracking
                        extracted_data = await asyncio.to_thread(extractor.extract_text)
                        extractor.close()

                        # Apply data minimization
                        from backend.app.utils.data_minimization import minimize_extracted_data
                        extracted_data = minimize_extracted_data(extracted_data)

                        # Calculate statistics
                        total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))

                        # Add performance metrics
                        extraction_time = time.time() - file_start_time
                        extracted_data["performance"] = {
                            "extraction_time": extraction_time,
                            "pages_count": len(extracted_data.get("pages", [])),
                            "words_count": total_words
                        }

                        # Add file information (no sensitive content)
                        extracted_data["file_info"] = {
                            "filename": file_name,
                            "content_type": file.content_type or "application/octet-stream",
                            "size": len(content)
                        }

                        return {
                            "file": file_name,
                            "status": "success",
                            "results": extracted_data
                        }
                    except Exception as e:
                        return SecurityAwareErrorHandler.handle_file_processing_error(e, "text_extraction", file_name)
                    finally:
                        # Ensure temporary file is cleaned up
                        if file_path and os.path.exists(file_path):
                            await SecureTempFileManager.secure_delete_file_async(file_path)

                # Process files in parallel
                tasks = [extract_file(file_tuple) for file_tuple in valid_files_list]
                results = await asyncio.gather(*tasks)

                # Calculate batch statistics
                batch_time = time.time() - start_time
                success_count = sum(1 for r in results if r.get("status") == "success")

                # Build response
                response = {
                    "batch_summary": {
                        "total_files": len(files),
                        "successful": success_count,
                        "failed": len(results) - success_count,
                        "total_time": batch_time,
                        "workers": len(valid_files_list),
                        "operation_id": operation_id,
                        "lock_used": False
                    },
                    "file_results": results
                }

                # Log performance
                log_batch_operation(
                    "Small Batch Text Extraction - No Lock",
                    len(files),
                    success_count,
                    batch_time
                )

                return JSONResponse(content=response)
            except Exception as e:
                # If direct processing fails, fall back to lock approach
                log_warning(f"[BATCH] Small batch extraction failed, falling back to lock: {str(e)}")
                # Continue to lock-based processing

        # For larger batches or if direct processing failed, use lock
        try:
            # Try to acquire lock with timeout
            async with batch_lock.acquire_timeout(timeout=15.0) as acquired:
                if not acquired:
                    log_warning(
                        f"[BATCH] Failed to acquire batch lock for extraction - attempting with reduced parallelism [operation_id={operation_id}]")

                    # If lock acquisition fails, try with reduced resources
                    try:
                        # Process files using reduced parallelism
                        reduced_parallel = max(1, max_parallel_files // 2)
                        valid_files_list = []
                        async for batch in validate_batch_files_optimized(files):
                            valid_files_list.extend(batch)

                        # Define extraction function
                        async def extract_file(file_tuple):
                            """Extract text from a single file with enhanced security."""
                            file_start_time = time.time()
                            file, file_path, content, safe_filename = file_tuple
                            file_name = file.filename or "unnamed_file"

                            try:
                                # Register with retention manager for automatic cleanup
                                if file_path:
                                    retention_manager.register_processed_file(file_path, TEMP_FILE_RETENTION_SECONDS)

                                # Determine document format
                                doc_format = None
                                if file_name.lower().endswith('.pdf'):
                                    doc_format = DocumentFormat.PDF
                                elif file_name.lower().endswith(('.docx', '.doc')):
                                    doc_format = DocumentFormat.DOCX
                                elif file_name.lower().endswith('.txt'):
                                    doc_format = DocumentFormat.TXT

                                # Create extractor
                                extractor = DocumentProcessingFactory.create_document_extractor(
                                    file_path if file_path else content,
                                    doc_format
                                )

                                # Extract text with performance tracking
                                extracted_data = await asyncio.to_thread(extractor.extract_text)
                                extractor.close()

                                # Apply data minimization
                                from backend.app.utils.data_minimization import minimize_extracted_data
                                extracted_data = minimize_extracted_data(extracted_data)

                                # Add file info and metrics
                                extraction_time = time.time() - file_start_time
                                extracted_data["performance"] = {
                                    "extraction_time": extraction_time,
                                    "pages_count": len(extracted_data.get("pages", [])),
                                    "words_count": sum(
                                        len(page.get("words", [])) for page in extracted_data.get("pages", []))
                                }
                                extracted_data["file_info"] = {
                                    "filename": file_name,
                                    "content_type": file.content_type or "application/octet-stream",
                                    "size": len(content)
                                }

                                return {
                                    "file": file_name,
                                    "status": "success",
                                    "results": extracted_data
                                }
                            except Exception as e:
                                return SecurityAwareErrorHandler.handle_file_processing_error(e, "text_extraction",
                                                                                              file_name)
                            finally:
                                # Ensure temporary file is cleaned up
                                if file_path and os.path.exists(file_path):
                                    await SecureTempFileManager.secure_delete_file_async(file_path)

                        # Create semaphore to limit concurrent processing
                        semaphore = asyncio.Semaphore(reduced_parallel)

                        async def process_with_semaphore(file_tuple):
                            async with semaphore:
                                return await extract_file(file_tuple)

                        # Process files with controlled concurrency
                        tasks = [process_with_semaphore(file_tuple) for file_tuple in valid_files_list]
                        results = await asyncio.gather(*tasks)

                        # Calculate batch statistics
                        batch_time = time.time() - start_time
                        success_count = sum(1 for r in results if r.get("status") == "success")

                        # Build response
                        response = {
                            "batch_summary": {
                                "total_files": len(files),
                                "successful": success_count,
                                "failed": len(results) - success_count,
                                "total_time": batch_time,
                                "workers": reduced_parallel,
                                "operation_id": operation_id,
                                "lock_used": False,
                                "emergency_mode": True
                            },
                            "file_results": results
                        }

                        # Log performance
                        log_batch_operation(
                            "Batch Text Extraction - Emergency Mode",
                            len(files),
                            success_count,
                            batch_time
                        )

                        return JSONResponse(content=response)
                    except Exception as fallback_error:
                        log_error(
                            f"[BATCH] Emergency extraction failed: {str(fallback_error)} [operation_id={operation_id}]")
                        return JSONResponse(
                            status_code=503,
                            content={
                                "detail": "Text extraction service is overloaded. Try again with fewer files.",
                                "retry_after": 30,
                                "operation_id": operation_id
                            }
                        )

                # With lock acquired, process normally
                valid_files_list = []
                async for batch in validate_batch_files_optimized(files):
                    valid_files_list.extend(batch)

                # Define extraction function (same as above)
                async def extract_file(file_tuple):
                    """Extract text from a single file with enhanced security."""
                    file_start_time = time.time()
                    file, file_path, content, safe_filename = file_tuple
                    file_name = file.filename or "unnamed_file"

                    try:
                        # Register with retention manager for automatic cleanup
                        if file_path:
                            retention_manager.register_processed_file(file_path, TEMP_FILE_RETENTION_SECONDS)

                        # Determine document format
                        doc_format = None
                        if file_name.lower().endswith('.pdf'):
                            doc_format = DocumentFormat.PDF
                        elif file_name.lower().endswith(('.docx', '.doc')):
                            doc_format = DocumentFormat.DOCX
                        elif file_name.lower().endswith('.txt'):
                            doc_format = DocumentFormat.TXT

                        # Create extractor
                        extractor = DocumentProcessingFactory.create_document_extractor(
                            file_path if file_path else content,
                            doc_format
                        )

                        # Extract text with performance tracking
                        extracted_data = await asyncio.to_thread(extractor.extract_text)
                        extractor.close()

                        # Apply data minimization
                        from backend.app.utils.data_minimization import minimize_extracted_data
                        extracted_data = minimize_extracted_data(extracted_data)

                        # Calculate statistics
                        total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))

                        # Add performance metrics
                        extraction_time = time.time() - file_start_time
                        extracted_data["performance"] = {
                            "extraction_time": extraction_time,
                            "pages_count": len(extracted_data.get("pages", [])),
                            "words_count": total_words
                        }

                        # Add file information (no sensitive content)
                        extracted_data["file_info"] = {
                            "filename": file_name,
                            "content_type": file.content_type or "application/octet-stream",
                            "size": len(content)
                        }

                        return {
                            "file": file_name,
                            "status": "success",
                            "results": extracted_data
                        }
                    except Exception as e:
                        return SecurityAwareErrorHandler.handle_file_processing_error(e, "text_extraction", file_name)
                    finally:
                        # Ensure temporary file is cleaned up
                        if file_path and os.path.exists(file_path):
                            await SecureTempFileManager.secure_delete_file_async(file_path)

                # Process files in parallel
                tasks = [extract_file(file_tuple) for file_tuple in valid_files_list]
                results = await asyncio.gather(*tasks)

                # Calculate batch statistics
                batch_time = time.time() - start_time
                success_count = sum(1 for r in results if r.get("status") == "success")
                error_count = len(results) - success_count
                total_words = sum(
                    r.get("results", {}).get("performance", {}).get("words_count", 0)
                    for r in results if r.get("status") == "success"
                )
                total_pages = sum(
                    r.get("results", {}).get("performance", {}).get("pages_count", 0)
                    for r in results if r.get("status") == "success"
                )

                # Record the processing operation
                record_keeper.record_processing(
                    operation_type="batch_text_extraction",
                    document_type="multiple",
                    entity_types_processed=[],
                    processing_time=batch_time,
                    file_count=len(files),
                    entity_count=0,
                )

                # Build response
                response = {
                    "batch_summary": {
                        "total_files": len(files),
                        "successful": success_count,
                        "failed": error_count,
                        "total_pages": total_pages,
                        "total_words": total_words,
                        "total_time": batch_time,
                        "workers": max_parallel_files,
                        "operation_id": operation_id,
                        "lock_used": True
                    },
                    "file_results": results
                }

                # Log performance
                log_batch_operation(
                    "Batch Text Extraction Completed",
                    len(files),
                    success_count,
                    batch_time
                )

                # Add memory statistics
                mem_stats = memory_monitor.get_memory_stats()
                response["_debug"] = {
                    "memory_usage": mem_stats["current_usage"],
                    "peak_memory": mem_stats["peak_usage"]
                }

                return JSONResponse(content=response)
        except TimeoutError:
            log_error(f"[BATCH] Timeout acquiring batch lock for extraction [operation_id={operation_id}]")

            # Final emergency attempt with absolute minimum resources
            try:
                log_warning(f"[BATCH] Final emergency extraction attempt [operation_id={operation_id}]")

                # Process with absolute minimal settings
                # Take only the first few files if there are many
                files_to_process = files[:min(5, len(files))]

                valid_files_list = []
                async for batch in validate_batch_files_optimized(files_to_process):
                    valid_files_list.extend(batch)

                # Define extraction function
                async def extract_file(file_tuple):
                    """Extract text from a single file with enhanced security."""
                    # Same implementation as above
                    file_start_time = time.time()
                    file, file_path, content, safe_filename = file_tuple
                    file_name = file.filename or "unnamed_file"

                    try:
                        # Register with retention manager for automatic cleanup
                        if file_path:
                            retention_manager.register_processed_file(file_path, TEMP_FILE_RETENTION_SECONDS)

                        # Determine document format
                        doc_format = None
                        if file_name.lower().endswith('.pdf'):
                            doc_format = DocumentFormat.PDF
                        elif file_name.lower().endswith(('.docx', '.doc')):
                            doc_format = DocumentFormat.DOCX
                        elif file_name.lower().endswith('.txt'):
                            doc_format = DocumentFormat.TXT

                        # Create extractor
                        extractor = DocumentProcessingFactory.create_document_extractor(
                            file_path if file_path else content,
                            doc_format
                        )

                        # Extract text with performance tracking
                        extracted_data = await asyncio.to_thread(extractor.extract_text)
                        extractor.close()

                        # Apply data minimization
                        from backend.app.utils.data_minimization import minimize_extracted_data
                        extracted_data = minimize_extracted_data(extracted_data)

                        # Calculate statistics
                        total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))

                        # Add performance metrics
                        extraction_time = time.time() - file_start_time
                        extracted_data["performance"] = {
                            "extraction_time": extraction_time,
                            "pages_count": len(extracted_data.get("pages", [])),
                            "words_count": total_words
                        }

                        # Add file information (no sensitive content)
                        extracted_data["file_info"] = {
                            "filename": file_name,
                            "content_type": file.content_type or "application/octet-stream",
                            "size": len(content)
                        }

                        return {
                            "file": file_name,
                            "status": "success",
                            "results": extracted_data
                        }
                    except Exception as e:
                        return SecurityAwareErrorHandler.handle_file_processing_error(e, "text_extraction", file_name)
                    finally:
                        # Ensure temporary file is cleaned up
                        if file_path and os.path.exists(file_path):
                            await SecureTempFileManager.secure_delete_file_async(file_path)

                # Process files sequentially to minimize resource usage
                results = []
                for file_tuple in valid_files_list:
                    result = await extract_file(file_tuple)
                    results.append(result)

                # Calculate and return results
                batch_time = time.time() - start_time
                success_count = sum(1 for r in results if r.get("status") == "success")

                # Build response
                response = {
                    "batch_summary": {
                        "total_files": len(files),
                        "processed_files": len(files_to_process),
                        "file_limit_applied": len(files) > len(files_to_process),
                        "successful": success_count,
                        "failed": len(results) - success_count,
                        "total_time": batch_time,
                        "workers": 1,
                        "operation_id": operation_id,
                        "lock_used": False,
                        "emergency_mode": True,
                        "sequential_processing": True
                    },
                    "file_results": results
                }

                # If some files were skipped, add a message
                if len(files) > len(files_to_process):
                    response["batch_summary"][
                        "message"] = f"Only processed {len(files_to_process)} files due to system load. Please resubmit remaining files later."

                return JSONResponse(content=response)
            except Exception as e:
                log_error(f"[BATCH] Final emergency extraction failed: {str(e)} [operation_id={operation_id}]")
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "Service unable to process batch due to extreme load.",
                        "retry_after": 60,
                        "operation_id": operation_id
                    }
                )

    except HTTPException as e:
        raise e
    except Exception as e:
        # Enhanced error handling
        error_response = SecurityAwareErrorHandler.handle_detection_error(e, "batch_extract")
        error_response.update({
            "batch_summary": {
                "total_files": len(files),
                "successful": 0,
                "failed": len(files),
                "total_time": time.time() - start_time,
                "operation_id": operation_id
            }
        })
        return JSONResponse(status_code=500, content=error_response)