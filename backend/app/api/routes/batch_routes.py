import asyncio
import os
import time
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, File, UploadFile, Form, HTTPException, BackgroundTasks, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse, Response

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
from backend.app.utils.data_minimization import minimize_extracted_data
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.helpers.batch_processing_helper import validate_batch_files_optimized, BatchProcessingHelper
from backend.app.utils.logger import log_warning, log_error, log_info, log_debug
from backend.app.utils.memory_management import memory_optimized, memory_monitor
from backend.app.utils.processing_records import record_keeper
from backend.app.utils.retention_management import retention_manager
from backend.app.utils.secure_file_utils import SecureTempFileManager
from backend.app.utils.secure_logging import log_batch_operation
from backend.app.utils.synchronization_utils import AsyncTimeoutLock, LockPriority, get_lock_report

# Configure rate limiter
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


async def process_valid_files(
        files: List[UploadFile],
        requested_entities: Optional[str],
        engine_result,
        detection_engine: str,
        max_parallel: int,
        start_time: float,
        operation_id: str,
        lock_used: bool,
        emergency_flags: Optional[Dict[str, bool]] = None
) -> JSONResponse:
    """
    Helper function to process the batch files and add common metadata.
    """
    emergency_flags = emergency_flags or {}
    allowed_types = {"application/pdf", "text/plain", "text/csv", "text/markdown", "text/html"}
    async for valid_files in validate_batch_files_optimized(files, allowed_types):
        results = await BatchProcessingService.detect_entities_in_files(
            files=[f[0] for f in valid_files],
            requested_entities=requested_entities,
            detection_engine=engine_result,
            max_parallel_files=max_parallel
        )
        total_time = time.time() - start_time
        results["batch_summary"]["api_time"] = total_time
        results["batch_summary"]["lock_used"] = lock_used
        # Add any emergency flags if provided
        for flag, value in emergency_flags.items():
            results["batch_summary"][flag] = value

        results["model_info"] = {
            "engine": detection_engine,
            "max_parallel": max_parallel,
            "actual_parallel": results["batch_summary"].get("workers", max_parallel)
        }
        mem_stats = memory_monitor.get_memory_stats()
        results["_debug"] = {
            "memory_usage": mem_stats["current_usage"],
            "peak_memory": mem_stats["peak_usage"],
            "operation_id": operation_id
        }
        return JSONResponse(content=results)
    # In case the async for loop completes without yielding a response
    raise HTTPException(status_code=400, detail="No valid files found.")


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

    This refactored implementation splits the processing logic into helper functions:
      - process_valid_files: Handles the core file processing and metadata enrichment.
      - The main endpoint branches into small batch, lock-based processing,
        and emergency fallback modes.
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
        log_info(f"[LOCK DEBUG] Lock owned by: {batch_lock.owner}, locked: {batch_lock.lock.locked()}")
        active_locks = get_lock_report().get("active_locks", {})
        log_info(f"[LOCK DEBUG] Active locks: {active_locks}")

        # 1. Attempt small batch processing without lock if possible
        if len(files) <= 2:
            try:
                return await process_valid_files(
                    files=files,
                    requested_entities=requested_entities,
                    engine_result=engine_result,
                    detection_engine=detection_engine,
                    max_parallel=adjusted_parallel_files,
                    start_time=start_time,
                    operation_id=operation_id,
                    lock_used=False
                )
            except Exception as e:
                log_warning(f"[BATCH] Small batch direct processing failed, falling back to lock: {str(e)}")
                # Continue to lock-based processing

        # 2. For larger batches, try processing using the lock
        try:
            log_info(f"[LOCK] Attempting to acquire lock [operation_id={operation_id}]")
            async with batch_lock.acquire_timeout(timeout=80.0):
                log_debug(f"Lock acquired for operation_id={operation_id}")
                # With lock acquired, process normally
                return await process_valid_files(
                    files=files,
                    requested_entities=requested_entities,
                    engine_result=engine_result,
                    detection_engine=detection_engine,
                    max_parallel=adjusted_parallel_files,
                    start_time=start_time,
                    operation_id=operation_id,
                    lock_used=True
                )
        except TimeoutError:
            log_error(f"[BATCH] Timeout acquiring batch processing lock [operation_id={operation_id}]")
            # 3. Final emergency attempt without lock after timeout
            try:
                log_warning(f"[BATCH] Final emergency attempt after lock timeout [operation_id={operation_id}]")
                return await process_valid_files(
                    files=files,
                    requested_entities=requested_entities,
                    engine_result=engine_result,
                    detection_engine=detection_engine,
                    max_parallel=1,
                    start_time=start_time,
                    operation_id=operation_id,
                    lock_used=False,
                    emergency_flags={"emergency_mode": True, "timeout_recovery": True}
                )
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



async def process_redaction_batch(
    files: List[UploadFile],
    mappings_data,
    parallel: int,
    start_time: float,
    background_tasks: BackgroundTasks
) -> Response:
    """
    Helper function that determines whether to process the redaction batch entirely in memory
    or via temporary files, returning a streaming response.
    """
    use_memory_buffer, _ = await determine_processing_strategy(files)
    if use_memory_buffer:
        return await process_batch_in_memory(
            files, mappings_data, parallel, start_time, background_tasks
        )
    else:
        return await process_batch_with_temp_files(
            files, mappings_data, parallel, start_time, background_tasks
        )


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

    - process_redaction_batch: Determines processing strategy (in-memory vs. temp file) and executes redaction.
    - The main endpoint handles small batch direct processing, lock-based processing, and emergency fallback.
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

        # Get the shared batch lock instance
        batch_lock = get_batch_resource_lock()

        # For very small batches (1-2 files), try processing without a lock first
        if len(files) <= 2:
            try:
                return await process_redaction_batch(
                    files, mappings_data, adjusted_parallel_files, start_time, background_tasks
                )
            except Exception as e:
                log_warning(f"[BATCH] Small batch redaction failed, falling back to lock: {str(e)}")
                # Continue to lock-based processing

        # For larger batches (or if direct processing failed), try acquiring the lock
        try:
            async with batch_lock.acquire_timeout(timeout=20.0) as acquired:
                if not acquired:
                    log_warning(
                        f"[BATCH] Failed to acquire lock for batch redaction - attempting direct processing [operation_id={operation_id}]"
                    )
                    try:
                        # Reduce parallelism when lock acquisition fails
                        reduced_parallel = max(1, adjusted_parallel_files // 2)
                        return await process_redaction_batch(
                            files, mappings_data, reduced_parallel, start_time, background_tasks
                        )
                    except Exception as fallback_error:
                        log_error(
                            f"[BATCH] Emergency direct redaction failed: {str(fallback_error)} [operation_id={operation_id}]"
                        )
                        return JSONResponse(
                            status_code=503,
                            content={
                                "detail": "Batch redaction service is overloaded. Try again with fewer files or wait.",
                                "retry_after": 30,
                                "operation_id": operation_id
                            }
                        )
                # With the lock acquired, process normally
                return await process_redaction_batch(
                    files, mappings_data, adjusted_parallel_files, start_time, background_tasks
                )
        except TimeoutError:
            log_error(f"[BATCH] Timeout acquiring batch processing lock for redaction [operation_id={operation_id}]")
            # Final emergency attempt with minimum parallelism after lock timeout
            try:
                log_warning(
                    f"[BATCH] Final emergency redaction attempt after lock timeout [operation_id={operation_id}]"
                )
                min_parallel = 1
                return await process_redaction_batch(
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


async def process_single_file_hybrid(
    files: List[UploadFile],
    requested_entities: Optional[str],
    use_presidio: bool,
    use_gemini: bool,
    use_gliner: bool,
    start_time: float,
    operation_id: str
) -> JSONResponse:
    """
    Process a single file using hybrid detection directly without lock.
    """
    results = await BatchProcessingService.detect_entities_in_files(
        files=files,
        requested_entities=requested_entities,
        use_presidio=use_presidio,
        use_gemini=use_gemini,
        use_gliner=use_gliner,
        max_parallel_files=1,  # Single file, single worker
        detection_engine=EntityDetectionEngine.HYBRID
    )
    total_time = time.time() - start_time
    results["batch_summary"]["api_time"] = total_time
    results["batch_summary"]["lock_used"] = False
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
    log_batch_operation("Single File Hybrid Detection - No Lock", 1, results["batch_summary"]["successful"], total_time)
    return JSONResponse(content=results)


async def process_reduced_parallel_hybrid(
    files: List[UploadFile],
    requested_entities: Optional[str],
    use_presidio: bool,
    use_gemini: bool,
    use_gliner: bool,
    max_parallel_files: int,
    start_time: float,
    operation_id: str
) -> JSONResponse:
    """
    Process the hybrid detection using reduced parallelism when the lock could not be acquired.
    Disables GLiNER in emergency mode to reduce resource usage.
    """
    print("❌Reduced is work❌❌❌❌")
    reduced_parallel = max(1, max_parallel_files // 2)
    emergency_gliner = False  # Disable GLiNER for emergency processing
    results = await BatchProcessingService.detect_entities_in_files(
        files=files,
        requested_entities=requested_entities,
        use_presidio=use_presidio,
        use_gemini=use_gemini,
        use_gliner=emergency_gliner,
        max_parallel_files=reduced_parallel,
        detection_engine=EntityDetectionEngine.HYBRID
    )
    total_time = time.time() - start_time
    results["batch_summary"]["api_time"] = total_time
    results["batch_summary"]["lock_used"] = False
    results["batch_summary"]["emergency_mode"] = True
    if use_gliner and not emergency_gliner:
        results["batch_summary"]["gliner_disabled_emergency"] = True
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
    log_batch_operation("Batch Hybrid Detection - Emergency Mode", len(files), results["batch_summary"]["successful"], total_time)
    return JSONResponse(content=results)


async def process_normal_batch_hybrid(
    files: List[UploadFile],
    requested_entities: Optional[str],
    use_presidio: bool,
    use_gemini: bool,
    use_gliner: bool,
    max_parallel_files: int,
    start_time: float,
    operation_id: str
) -> JSONResponse:
    """
    Process hybrid detection normally with the lock acquired.
    """
    print("❌Normal is work❌❌❌❌")
    results = await BatchProcessingService.detect_entities_in_files(
        files=files,
        requested_entities=requested_entities,
        use_presidio=use_presidio,
        use_gemini=use_gemini,
        use_gliner=use_gliner,
        max_parallel_files=max_parallel_files,
        detection_engine=EntityDetectionEngine.HYBRID
    )
    total_time = time.time() - start_time
    results["batch_summary"]["api_time"] = total_time
    results["batch_summary"]["lock_used"] = True

    total_entities = results["batch_summary"].get("total_entities", 0)
    record_keeper.record_processing(
        operation_type="batch_hybrid_detection",
        document_type="multiple",
        entity_types_processed=[],  # Processed per file
        processing_time=total_time,
        file_count=len(files),
        entity_count=total_entities,
    )
    log_batch_operation("Batch Hybrid Detection", len(files), results["batch_summary"]["successful"], total_time)
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
    mem_stats = memory_monitor.get_memory_stats()
    results["_debug"] = {
        "memory_usage": mem_stats["current_usage"],
        "peak_memory": mem_stats["peak_usage"]
    }
    return JSONResponse(content=results)


async def process_final_emergency_hybrid(
    files: List[UploadFile],
    requested_entities: Optional[str],
    start_time: float,
    operation_id: str
) -> JSONResponse:
    """
    Final emergency attempt for hybrid detection with absolute minimal settings.
    Uses only Presidio as a fallback.
    """
    print("❌Emergency is work❌❌❌❌")
    results = await BatchProcessingService.detect_entities_in_files(
        files=files,
        requested_entities=requested_entities,
        use_presidio=True,    # Always use Presidio in extreme emergency
        use_gemini=False,     # Disable Gemini
        use_gliner=False,     # Disable GLiNER
        max_parallel_files=1,  # Absolute minimal parallelism
        detection_engine=EntityDetectionEngine.HYBRID
    )
    total_time = time.time() - start_time
    results["batch_summary"]["api_time"] = total_time
    results["batch_summary"]["lock_used"] = False
    results["batch_summary"]["emergency_mode"] = True
    results["batch_summary"]["timeout_recovery"] = True
    results["batch_summary"]["minimum_engines"] = True
    results["model_info"] = {
        "engine": "hybrid",
        "engines_used": {
            "presidio": True,
            "gemini": False,
            "gliner": False
        },
        "requested_engines": {
            "presidio": True,
            "gemini": False,
            "gliner": False
        },
        "max_parallel": 1,
        "actual_parallel": results["batch_summary"].get("workers", 1),
        "operation_id": operation_id
    }
    return JSONResponse(content=results)


async def select_and_process_hybrid_detection(
        method: str,
        files: List[UploadFile],
        requested_entities: Optional[str],
        use_presidio: bool,
        use_gemini: bool,
        use_gliner: bool,
        optimal_parallel_files: int,
        start_time: float,
        operation_id: str
) -> JSONResponse:
    """
    Selects and invokes the appropriate hybrid detection processing function.

    Args:
        method: One of "normal", "reduced", or "emergency".
        files: List of files to process.
        requested_entities: Optional entities to detect.
        use_presidio: Whether to use Presidio.
        use_gemini: Whether to use Gemini.
        use_gliner: Whether to use GLiNER.
        optimal_parallel_files: The optimal number of parallel files to process.
        start_time: The start time of the operation.
        operation_id: The unique operation ID.

    Returns:
        JSONResponse from the selected processing function.
    """
    if method == "normal":
        return await process_normal_batch_hybrid(
            files=files,
            requested_entities=requested_entities,
            use_presidio=use_presidio,
            use_gemini=use_gemini,
            use_gliner=use_gliner,
            max_parallel_files=optimal_parallel_files,
            start_time=start_time,
            operation_id=operation_id
        )
    elif method == "reduced":
        return await process_reduced_parallel_hybrid(
            files=files,
            requested_entities=requested_entities,
            use_presidio=use_presidio,
            use_gemini=use_gemini,
            use_gliner=use_gliner,
            max_parallel_files=optimal_parallel_files,
            start_time=start_time,
            operation_id=operation_id
        )
    else:  # method == "emergency"
        return await process_final_emergency_hybrid(
            files=files,
            requested_entities=requested_entities,
            start_time=start_time,
            operation_id=operation_id
        )


async def process_multi_file_hybrid_detection(
        files: List[UploadFile],
        chosen_method: str,
        requested_entities: Optional[str],
        use_presidio: bool,
        use_gemini: bool,
        use_gliner: bool,
        optimal_parallel_files: int,
        start_time: float,
        operation_id: str,
        batch_lock: AsyncTimeoutLock
) -> JSONResponse:
    """
    Processes multi-file hybrid detection using the shared lock.
    If the lock is acquired, the function calls the appropriate processing function
    based on the chosen method (normal, reduced, or emergency) via
    select_and_process_hybrid_detection.
    If the lock acquisition times out, it falls back to a direct processing branch:
      - If chosen_method is "normal" or "reduced", it calls process_reduced_parallel_hybrid.
      - Otherwise, it calls process_final_emergency_hybrid.

    Args:
        files: List of files to process.
        chosen_method: One of "normal", "reduced", or "emergency".
        requested_entities: Optional entities to detect.
        use_presidio: Whether to use Presidio.
        use_gemini: Whether to use Gemini.
        use_gliner: Whether to use GLiNER.
        optimal_parallel_files: Optimal number of parallel files to process.
        start_time: Start time of the operation.
        operation_id: Unique operation identifier.
        batch_lock: Shared asynchronous lock for resource management.

    Returns:
        A JSONResponse from the selected processing function.
    """
    try:
        async with batch_lock.acquire_timeout(timeout=20.0):
            log_debug(f"Lock acquired for operation_id={operation_id}")
            # When the lock is acquired, delegate to the helper which already
            # selects between process_normal_batch_hybrid, process_reduced_parallel_hybrid, or emergency.
            return await select_and_process_hybrid_detection(
                method=chosen_method,
                files=files,
                requested_entities=requested_entities,
                use_presidio=use_presidio,
                use_gemini=use_gemini,
                use_gliner=use_gliner,
                optimal_parallel_files=optimal_parallel_files,
                start_time=start_time,
                operation_id=operation_id
            )
    except TimeoutError:
        log_error(f"[BATCH] Timeout acquiring lock for hybrid detection [operation_id={operation_id}]")
        # Fallback branch: if chosen method is "normal" or "reduced", use reduced processing.
        if chosen_method in ("normal", "reduced"):
            return await process_reduced_parallel_hybrid(
                files=files,
                requested_entities=requested_entities,
                use_presidio=use_presidio,
                use_gemini=use_gemini,
                use_gliner=use_gliner,
                max_parallel_files=optimal_parallel_files,
                start_time=start_time,
                operation_id=operation_id
            )
        # Otherwise, fall back to emergency processing.
        return await process_final_emergency_hybrid(
            files=files,
            requested_entities=requested_entities,
            start_time=start_time,
            operation_id=operation_id
        )

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

    This endpoint processes documents under GDPR Article 6(1)(f) for enhancing document security and privacy.
    Processing method selection:
      - Single file: uses the single-file method.
      - >1 file & total size < 1 MB: uses the normal method.
      - >1 file & total size between 1 MB and 2 MB: uses the reduced (emergency) method.
      - >1 file & total size > 2 MB: uses the final emergency method.
    """
    start_time = time.time()
    operation_id = f"batch_hybrid_{int(time.time())}"

    try:
        if not any([use_presidio, use_gemini, use_gliner]):
            return JSONResponse(
                status_code=400,
                content={"detail": "At least one detection engine must be selected"}
            )

        optimal_parallel_files = BatchProcessingHelper.get_optimal_batch_size(
            len(files),
            sum(file.size or 0 for file in files)
        )
        total_size_mb = sum(file.size or 0 for file in files) / (1024 * 1024)
        batch_lock = get_batch_resource_lock()

        if len(files) == 1:
            try:
                print("❌1❌❌❌❌")
                return await process_single_file_hybrid(
                    files=files,
                    requested_entities=requested_entities,
                    use_presidio=use_presidio,
                    use_gemini=use_gemini,
                    use_gliner=use_gliner,
                    start_time=start_time,
                    operation_id=operation_id
                )
            except Exception as e:
                log_warning(f"[BATCH] Single file hybrid detect failed, falling back to lock: {str(e)}")
                # Continue to multi-file processing fallback.

        # Determine processing method for multi-file batches based on total file size.
        if total_size_mb < 1:
            print("❌ Normal (Presidio, Gemini, Gliner) More than 1 file❌ Size < 1 MB❌❌❌")
            chosen_method = "normal"
        elif total_size_mb < 2:
            print("❌ Reduced (Presidio, Gemini) More than 1 file❌ Size < 2 MB❌❌❌")
            chosen_method = "reduced"
        else:
            print("❌ Emergency (Presidio) More than 1 file❌ Size > 2 MB❌❌❌")
            chosen_method = "emergency"

        return await process_multi_file_hybrid_detection(
            files=files,
            chosen_method=chosen_method,
            requested_entities=requested_entities,
            use_presidio=use_presidio,
            use_gemini=use_gemini,
            use_gliner=use_gliner,
            optimal_parallel_files=optimal_parallel_files,
            start_time=start_time,
            operation_id=operation_id,
            batch_lock=batch_lock
        )
    except HTTPException as e:
        raise e
    except Exception as e:
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


async def get_valid_files(files: List[UploadFile]) -> List[Any]:
    """
    Returns a flat list of valid file tuples obtained from the optimized validation.
    """
    valid_files = []
    async for batch in validate_batch_files_optimized(files):
        valid_files.extend(batch)
    return valid_files


async def extract_text_from_file(file_tuple: Any) -> dict:
    """
    Extract text (with positions) from a single file while applying enhanced security and cleanup.

    Args:
        file_tuple: A tuple containing (file, file_path, content, safe_filename).

    Returns:
        A dict with the file name, status, and extracted results or error details.
    """
    file_start_time = time.time()
    file, file_path, content, _ = file_tuple
    file_name = file.filename or "unnamed_file"

    try:
        # Register file for automatic cleanup if a temporary path is used.
        if file_path:
            retention_manager.register_processed_file(file_path, TEMP_FILE_RETENTION_SECONDS)

        # Determine document format.
        doc_format = None
        lower_name = file_name.lower()
        if lower_name.endswith('.pdf'):
            doc_format = DocumentFormat.PDF
        elif lower_name.endswith(('.docx', '.doc')):
            doc_format = DocumentFormat.DOCX
        elif lower_name.endswith('.txt'):
            doc_format = DocumentFormat.TXT

        # Create the document extractor.
        extractor = DocumentProcessingFactory.create_document_extractor(
            file_path if file_path else content,
            doc_format
        )

        # Extract text (using a thread for blocking operations).
        extracted_data = await asyncio.to_thread(extractor.extract_text)
        extractor.close()

        extracted_data = minimize_extracted_data(extracted_data)

        # Calculate statistics.
        total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
        extraction_time = time.time() - file_start_time
        extracted_data["performance"] = {
            "extraction_time": extraction_time,
            "pages_count": len(extracted_data.get("pages", [])),
            "words_count": total_words
        }
        extracted_data["file_info"] = {
            "filename": file_name,
            "content_type": file.content_type or "application/octet-stream",
            "size": len(content)
        }

        return {"file": file_name, "status": "success", "results": extracted_data}

    except Exception as e:
        error_result = SecurityAwareErrorHandler.handle_file_processing_error(e, "text_extraction", file_name)
        if error_result is None:
            error_result = {
                "file": file_name,
                "status": "error",
                "results": f"An error occurred during text extraction: {str(e)}"
            }
        return error_result

    finally:
        # Ensure temporary file cleanup.
        if file_path and os.path.exists(file_path):
            await SecureTempFileManager.secure_delete_file_async(file_path)


async def process_small_batch(files: List[UploadFile], start_time: float, operation_id: str) -> JSONResponse:
    """
    Processes small batches (1-2 files) directly without acquiring a lock.
    """
    valid_files_list = await get_valid_files(files)
    tasks = [extract_text_from_file(file_tuple) for file_tuple in valid_files_list]
    results = await asyncio.gather(*tasks)

    batch_time = time.time() - start_time
    success_count = sum(1 for r in results if r.get("status") == "success")
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
    log_batch_operation("Small Batch Text Extraction - No Lock", len(files), success_count, batch_time)
    return JSONResponse(content=response)


async def process_reduced_parallel_batch(files: List[UploadFile], start_time: float, operation_id: str, reduced_parallel: int) -> JSONResponse:
    """
    Processes batches with reduced parallelism (emergency mode) when lock acquisition fails.
    """
    valid_files_list = await get_valid_files(files)
    semaphore = asyncio.Semaphore(reduced_parallel)

    async def process_with_semaphore(file_tuple):
        async with semaphore:
            return await extract_text_from_file(file_tuple)

    tasks = [process_with_semaphore(file_tuple) for file_tuple in valid_files_list]
    results = await asyncio.gather(*tasks)

    batch_time = time.time() - start_time
    success_count = sum(1 for r in results if r.get("status") == "success")
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
    log_batch_operation("Batch Text Extraction - Emergency Mode", len(files), success_count, batch_time)
    return JSONResponse(content=response)


async def process_normal_batch(files: List[UploadFile], start_time: float, operation_id: str, max_parallel: int) -> JSONResponse:
    """
    Processes batches normally with the batch lock acquired.
    """
    valid_files_list = await get_valid_files(files)
    tasks = [extract_text_from_file(file_tuple) for file_tuple in valid_files_list]
    results = await asyncio.gather(*tasks)

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

    # Record the processing operation.
    record_keeper.record_processing(
        operation_type="batch_text_extraction",
        document_type="multiple",
        entity_types_processed=[],
        processing_time=batch_time,
        file_count=len(files),
        entity_count=0,
    )

    response = {
        "batch_summary": {
            "total_files": len(files),
            "successful": success_count,
            "failed": error_count,
            "total_pages": total_pages,
            "total_words": total_words,
            "total_time": batch_time,
            "workers": max_parallel,
            "operation_id": operation_id,
            "lock_used": True
        },
        "file_results": results
    }
    log_batch_operation("Batch Text Extraction Completed", len(files), success_count, batch_time)
    mem_stats = memory_monitor.get_memory_stats()
    response["_debug"] = {
        "memory_usage": mem_stats["current_usage"],
        "peak_memory": mem_stats["peak_usage"]
    }
    return JSONResponse(content=response)


async def process_emergency_batch(files: List[UploadFile], start_time: float, operation_id: str) -> JSONResponse:
    """
    Final emergency processing attempt with minimal resources:
    processes only a subset of files sequentially.
    """
    files_to_process = files[:min(5, len(files))]
    valid_files_list = await get_valid_files(files_to_process)
    results = []
    for file_tuple in valid_files_list:
        result = await extract_text_from_file(file_tuple)
        results.append(result)

    batch_time = time.time() - start_time
    success_count = sum(1 for r in results if r.get("status") == "success")
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
    if len(files) > len(files_to_process):
        response["batch_summary"]["message"] = (
            f"Only processed {len(files_to_process)} files due to system load. Please resubmit remaining files later."
        )
    return JSONResponse(content=response)


@router.post("/extract")
@memory_optimized(threshold_mb=50)
async def batch_extract_text(
    request: Request,
    files: List[UploadFile] = File(...),
    max_parallel_files: Optional[int] = Form(4)
):
    """
    Extract text with positions from multiple files in parallel with enhanced security.

    Processes files under GDPR Article 6(1)(f) for document security and privacy processing.
    """
    start_time = time.time()
    operation_id = f"batch_extract_{int(time.time())}"

    # Optimize the maximum parallel files based on system resources.
    optimal_parallel_files = BatchProcessingHelper.get_optimal_batch_size(
        len(files),
        sum(file.size or 0 for file in files)
    )

    try:
        batch_lock = get_batch_resource_lock()

        # For small batches (1-2 files), attempt direct processing without a lock.
        if len(files) <= 2:
            try:
                return await process_small_batch(files, start_time, operation_id)
            except Exception as e:
                log_warning(f"[BATCH] Small batch extraction failed, falling back to lock: {str(e)}")

        # For larger batches (or if small-batch processing fails), use a lock.
        try:
            async with batch_lock.acquire_timeout(timeout=15.0) as acquired:
                if not acquired:
                    log_warning(
                        f"[BATCH] Failed to acquire batch lock for extraction - "
                        f"attempting with reduced parallelism [operation_id={operation_id}]"
                    )
                    try:
                        reduced_parallel = max(1, optimal_parallel_files // 2)
                        return await process_reduced_parallel_batch(files, start_time, operation_id, reduced_parallel)
                    except Exception as fallback_error:
                        log_error(
                            f"[BATCH] Emergency extraction failed: {str(fallback_error)} "
                            f"[operation_id={operation_id}]"
                        )
                        return JSONResponse(
                            status_code=503,
                            content={
                                "detail": "Text extraction service is overloaded. Try again with fewer files.",
                                "retry_after": 30,
                                "operation_id": operation_id
                            }
                        )
                # With the lock acquired, process normally.
                return await process_normal_batch(files, start_time, operation_id, optimal_parallel_files)
        except TimeoutError:
            log_error(f"[BATCH] Timeout acquiring batch lock for extraction [operation_id={operation_id}]")
            try:
                return await process_emergency_batch(files, start_time, operation_id)
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