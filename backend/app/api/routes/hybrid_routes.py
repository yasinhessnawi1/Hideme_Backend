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

# Define constants for file thresholds
LARGE_FILE_THRESHOLD = 5 * 1024 * 1024  # 5MB
CHUNK_SIZE = 1 * 1024 * 1024  # 1MB

# Shared detector lock
_detector_resource_lock = None


def get_detector_resource_lock():
    """
    Get (and initialize if needed) the shared detector resource lock.
    """
    global _detector_resource_lock
    if _detector_resource_lock is None:
        _detector_resource_lock = AsyncTimeoutLock("hybrid_detector_lock", priority=LockPriority.HIGH)
        log_info("[SYSTEM] Hybrid detector resource lock initialized")
    return _detector_resource_lock


def get_entity_list(requested_entities: Optional[str], use_gliner: bool):
    """
    Validate and return the list of requested entities.
    """
    entity_list = validate_requested_entities(requested_entities)
    if not entity_list and use_gliner:
        entity_list = GLINER_ENTITIES
    return entity_list


async def process_small_file_branch(
    file: UploadFile,
    operation_id: str,
    entity_list,
    use_presidio: bool,
    use_gemini: bool,
    use_gliner: bool,
    start_time: float,
    file_read_start: float
) -> JSONResponse:
    """
    Process small files (under 50KB) without acquiring the detector lock.
    """
    processing_times = {}
    try:
        file_content = await file.read()
        processing_times["file_read_time"] = time.time() - file_read_start
        is_valid, reason, _ = await validate_file_content_async(
            file_content, file.filename, file.content_type
        )
        if not is_valid:
            return JSONResponse(status_code=415, content={"detail": reason})

        log_info(
            f"[HYBRID] Processing small file without lock: {len(file_content) / 1024:.1f}KB [operation_id={operation_id}]"
        )

        extract_start = time.time()
        extracted_data = await SecureTempFileManager.process_content_in_memory_async(
            file_content, extraction_processor, use_path=False
        )
        processing_times["extraction_time"] = time.time() - extract_start

        extracted_data = minimize_extracted_data(extracted_data)

        # Use the provided flags for all engines
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
        detection_start = time.time()
        detection_result = await asyncio.wait_for(
            detector.detect_sensitive_data_async(extracted_data, entity_list),
            timeout=600.0
        )

        if detection_result is None:
            raise ValueError("Detection failed to return results in the small file method")
        anonymized_text, entities, redaction_mapping = detection_result
        processing_times["detection_time"] = time.time() - detection_start
        processing_times["total_time"] = time.time() - start_time

        log_info(f"[HYBRID] Small file processed successfully without lock [operation_id={operation_id}]")

        sanitized_response = sanitize_detection_output(anonymized_text, entities, redaction_mapping, processing_times)
        sanitized_response["model_info"] = {
            "engine": "hybrid",
            "engines_used": {
                "presidio": use_presidio,
                "gemini": use_gemini,
                "gliner": use_gliner
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
        sanitized_response["_debug"] = {
            "memory_usage": memory_monitor.get_memory_usage(),
            "peak_memory": memory_monitor.get_memory_stats().get("peak_usage"),
            "operation_id": operation_id,
            "lock_used": False
        }

        return JSONResponse(content=sanitized_response)
    except Exception as e:
        log_warning(
            f"[HYBRID] Small file processing failed, falling back to lock: {str(e)} [operation_id={operation_id}]"
        )
        await file.seek(0)
        raise e

async def _try_process_small_file_branch(
    file: UploadFile,
    operation_id: str,
    entity_list,
    use_presidio: bool,
    use_gemini: bool,
    use_gliner: bool,
    start_time: float,
    file_read_start: float
) -> Optional[JSONResponse]:
    """
    Attempt to process a small file. If processing fails, log the error and return None.
    """
    try:
        return await process_small_file_branch(
            file, operation_id, entity_list, use_presidio, use_gemini, use_gliner, start_time, file_read_start
        )
    except Exception as err:
        log_warning(
            f"[HYBRID] Small file processing failed, falling back to standard processing: {str(err)} [operation_id={operation_id}]"
        )
        return None


async def _handle_endpoint_exception(e: Exception, operation_id: str, use_presidio: bool, use_gemini: bool, use_gliner: bool) -> JSONResponse:
    """
    Handle exceptions for the endpoint. Releases Gemini slots if necessary and builds an error response.
    """
    if 'gemini' in str(e).lower():
        try:
            await gemini_usage_manager.gemini_usage_manager.release_request_slot()
        except Exception:
            pass

    if isinstance(e, HTTPException):
        raise e

    error_response = SecurityAwareErrorHandler.handle_detection_error(e, "hybrid_detection")
    error_response["model_info"] = {
        "engine": "hybrid",
        "engines_used": {"presidio": use_presidio, "gemini": use_gemini, "gliner": use_gliner},
        "operation_id": operation_id
    }
    return JSONResponse(status_code=500, content=error_response)


async def process_chunked_file_branch(
    file: UploadFile,
    entity_list,
    use_presidio: bool,
    use_gemini: bool,
    use_gliner: bool,
    start_time: float,
    operation_id: str
) -> JSONResponse:
    """
    Process large files via chunked processing.
    """
    detector_lock = get_detector_resource_lock()
    try:
        async with detector_lock.acquire_timeout(timeout=30.0) as acquired:
            if not acquired:
                log_warning(
                    f"[HYBRID] Failed to acquire detector lock for chunked processing [operation_id={operation_id}]"
                )
                return await _fallback_processing(
                    file, entity_list, start_time, operation_id,
                    use_presidio, use_gemini, use_gliner, timeout_recovery=False
                )
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
            f"[HYBRID] Timeout acquiring detector lock for chunked processing [operation_id={operation_id}]"
        )
        return await _fallback_processing(
            file, entity_list, start_time, operation_id,
            use_presidio, use_gemini, use_gliner, timeout_recovery=True
        )


async def _fallback_processing(
    file: UploadFile,
    entity_list,
    start_time: float,
    operation_id: str,
    use_presidio: bool,
    use_gemini: bool,
    use_gliner: bool,
    timeout_recovery: bool
) -> JSONResponse:
    """
    Fallback processing for chunked files using reduced engines (Presidio only).
    """
    try:
        result = await process_file_in_chunks(
            file,
            entity_list,
            use_presidio=True,
            use_gemini=False,
            use_gliner=False,
            start_time=start_time,
            operation_id=operation_id
        )
        if isinstance(result, JSONResponse):
            return _handle_result(result, use_presidio, use_gemini, use_gliner, add_timeout_recovery=timeout_recovery)
        return result
    except Exception as e:
        if timeout_recovery:
            log_error(
                f"[HYBRID] Emergency chunked processing failed: {str(e)} [operation_id={operation_id}]"
            )
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Service timeout. System is under extreme load.",
                    "retry_after": 120,
                    "operation_id": operation_id
                }
            )
        else:
            log_error(
                f"[HYBRID] Fallback chunked processing failed: {str(e)} [operation_id={operation_id}]"
            )
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Unable to process large file. System is under heavy load.",
                    "retry_after": 60,
                    "operation_id": operation_id
                }
            )


def _handle_result(
    result: JSONResponse,
    use_presidio: bool,
    use_gemini: bool,
    use_gliner: bool,
    add_timeout_recovery: bool
) -> JSONResponse:
    """
    Modify and return the JSON response for fallback processing.
    """
    try:
        import json
        content = result.body.decode()
        data = json.loads(content)
        data["model_info"]["emergency_mode"] = True
        if add_timeout_recovery:
            data["model_info"]["timeout_recovery"] = True
        data["model_info"]["requested_engines"] = {
            "presidio": use_presidio,
            "gemini": use_gemini,
            "gliner": use_gliner
        }
        return JSONResponse(content=data)
    except Exception:
        return result



async def process_standard_file_branch(
    file: UploadFile,
    file_content: bytes,
    entity_list,
    use_presidio: bool,
    use_gemini: bool,
    use_gliner: bool,
    start_time: float,
    operation_id: str,
    processing_times: dict,
    extract_start: float
) -> JSONResponse:
    """
    Process standard files (non-chunked) using the detector lock.
    """
    detector_lock = get_detector_resource_lock()
    try:
        is_valid, reason, _ = await validate_file_content_async(
            file_content, file.filename, file.content_type
        )
        if not is_valid:
            return JSONResponse(status_code=415, content={"detail": reason})
        async with detector_lock.acquire_timeout(timeout=30.0) as acquired:
            if not acquired:
                log_warning(
                    f"[HYBRID] Failed to acquire detector lock - attempting with reduced engines [operation_id={operation_id}]"
                )
                try:
                    extracted_data = await SecureTempFileManager.process_content_in_memory_async(
                        file_content, extraction_processor, use_path=False
                    )
                    processing_times["extraction_time"] = time.time() - extract_start
                    extracted_data = minimize_extracted_data(extracted_data)

                    config = {
                        "use_presidio": False,
                        "use_gemini": False,
                        "use_gliner": False,
                        "gliner_model_name": GLINER_MODEL_NAME,
                        "entities": entity_list
                    }
                    detector_create_start = time.time()
                    detector = initialization_service.get_hybrid_detector(config)
                    processing_times["detector_init_time"] = time.time() - detector_create_start

                    detection_start = time.time()
                    detection_result = await asyncio.wait_for(
                        detector.detect_sensitive_data_async(extracted_data, entity_list),
                        timeout=30.0
                    )
                    if detection_result is None:
                        raise ValueError("Detection failed to return results")
                    anonymized_text, entities, redaction_mapping = detection_result
                    processing_times["detection_time"] = time.time() - detection_start
                    processing_times["total_time"] = time.time() - start_time

                    log_info(
                        f"[HYBRID] Detection completed with reduced engines (Presidio only) [operation_id={operation_id}]"
                    )

                    sanitized_response = sanitize_detection_output(
                        anonymized_text, entities, redaction_mapping, processing_times
                    )
                    sanitized_response["model_info"] = {
                        "engine": "hybrid",
                        "engines_used": {"presidio": True, "gemini": False, "gliner": False},
                        "requested_engines": {"presidio": use_presidio, "gemini": use_gemini, "gliner": use_gliner},
                        "emergency_mode": True
                    }
                    sanitized_response["file_info"] = {
                        "filename": file.filename,
                        "content_type": file.content_type,
                        "size": len(file_content)
                    }
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
                        f"[HYBRID] Fallback processing failed: {str(fallback_error)} [operation_id={operation_id}]"
                    )
                    return JSONResponse(
                        status_code=503,
                        content={
                            "detail": "Detection service unavailable due to system load.",
                            "retry_after": 30,
                            "operation_id": operation_id
                        }
                    )
            # With lock acquired: proceed with standard processing
            extracted_data = await SecureTempFileManager.process_content_in_memory_async(
                file_content, extraction_processor, use_path=False
            )
            processing_times["extraction_time"] = time.time() - extract_start
            extracted_data = minimize_extracted_data(extracted_data)

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

            detection_start = time.time()
            detection_result = await asyncio.wait_for(
                detector.detect_sensitive_data_async(extracted_data, entity_list),
                timeout=60.0
            )
            if detection_result is None:
                raise ValueError("Detection failed to return results")
            anonymized_text, entities, redaction_mapping = detection_result
            processing_times["detection_time"] = time.time() - detection_start
            processing_times["total_time"] = time.time() - start_time

            log_info(f"[HYBRID] Detection completed successfully with lock [operation_id={operation_id}]")

            sanitized_response = sanitize_detection_output(
                anonymized_text, entities, redaction_mapping, processing_times
            )
            sanitized_response["model_info"] = {
                "engine": "hybrid",
                "engines_used": {"presidio": use_presidio, "gemini": use_gemini, "gliner": use_gliner}
            }
            sanitized_response["file_info"] = {
                "filename": file.filename,
                "content_type": file.content_type,
                "size": len(file_content)
            }
            mem_stats = memory_monitor.get_memory_stats()
            sanitized_response["_debug"] = {
                "memory_usage": mem_stats["current_usage"],
                "peak_memory": mem_stats["peak_usage"],
                "operation_id": operation_id,
                "lock_used": True
            }

            record_keeper.record_processing(
                operation_type="hybrid_detection",
                document_type=file.content_type,
                entity_types_processed=entity_list or [],
                processing_time=processing_times["total_time"],
                entity_count=len(entities),
                success=True
            )

            log_sensitive_operation(
                "Hybrid Detection",
                len(entities),
                processing_times["total_time"],
                pages=processing_times.get("pages_count", 0),
                words=processing_times.get("words_count", 0),
                engines={"presidio": use_presidio, "gemini": use_gemini, "gliner": use_gliner},
                extract_time=processing_times["extraction_time"],
                detect_time=processing_times["detection_time"]
            )
            return JSONResponse(content=sanitized_response)
    except TimeoutError:
        log_error(f"[HYBRID] Timeout acquiring detector lock [operation_id={operation_id}]")
        try:
            log_warning(f"[HYBRID] Final emergency attempt after timeout [operation_id={operation_id}]")
            extracted_data = await SecureTempFileManager.process_content_in_memory_async(
                file_content, extraction_processor, use_path=False
            )
            processing_times["extraction_time"] = time.time() - extract_start
            extracted_data = minimize_extracted_data(extracted_data)

            config = {"use_presidio": True, "use_gemini": False, "use_gliner": False, "entities": entity_list}
            detector = initialization_service.get_hybrid_detector(config)
            detection_result = await asyncio.wait_for(
                detector.detect_sensitive_data_async(extracted_data, entity_list),
                timeout=30.0
            )
            anonymized_text, entities, redaction_mapping = detection_result

            sanitized_response = sanitize_detection_output(anonymized_text, entities, redaction_mapping, processing_times)
            sanitized_response["model_info"] = {
                "engine": "hybrid",
                "engines_used": {"presidio": True, "gemini": False, "gliner": False},
                "requested_engines": {"presidio": use_presidio, "gemini": use_gemini, "gliner": use_gliner},
                "emergency_mode": True,
                "timeout_recovery": True
            }
            return JSONResponse(content=sanitized_response)
        except Exception as final_error:
            log_error(
                f"[HYBRID] Final emergency attempt failed: {str(final_error)} [operation_id={operation_id}]"
            )
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Service unavailable due to extreme load.",
                    "retry_after": 120,
                    "operation_id": operation_id
                }
            )


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
    Endpoint to detect sensitive information using multiple detection engines.
    The processing is divided into branches for small files, large files (chunked processing),
    and standard file processing.
    """
    start_time = time.time()
    processing_times = {}
    operation_id = f"hybrid_detect_{int(time.time())}"
    allowed_types = ["application/pdf", "text/plain", "text/csv", "text/markdown", "text/html"]


    if not validate_mime_type(file.content_type, allowed_types):
        return JSONResponse(
            status_code=415,
            content={"detail": "Unsupported file type. Please upload a PDF or text file."}
        )

    try:
        entity_list = get_entity_list(requested_entities, use_gliner)
    except Exception as e:
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "entity_validation", 400
        )
        return JSONResponse(status_code=status_code, content=error_response)

    try:
        file_read_start = time.time()
        first_chunk = await file.read(8192)
        await file.seek(0)

        max_size = MAX_PDF_SIZE_BYTES if "pdf" in file.content_type.lower() else MAX_TEXT_SIZE_BYTES
        if len(first_chunk) > max_size:
            return JSONResponse(
                status_code=413,
                content={"detail": f"File size exceeds maximum allowed ({max_size // (1024 * 1024)}MB)"}
            )

        small_file = len(first_chunk) < 50 * 1024

        # Branch for small files
        if small_file:
            result = await _try_process_small_file_branch(
                file, operation_id, entity_list, use_presidio, use_gemini, use_gliner, start_time, file_read_start
            )
            if result is not None:
                return result

        # Branch for large files using chunked processing
        if hasattr(file, 'size') and file.size and file.size > LARGE_FILE_THRESHOLD:
            return await process_chunked_file_branch(
                file, entity_list, use_presidio, use_gemini, use_gliner, start_time, operation_id
            )

        # Standard processing branch
        file_content = await file.read()
        processing_times["file_read_time"] = time.time() - file_read_start
        extract_start = time.time()
        return await process_standard_file_branch(
            file, file_content, entity_list, use_presidio, use_gemini, use_gliner,
            start_time, operation_id, processing_times, extract_start
        )
    except Exception as e:
        return _handle_endpoint_exception(e, operation_id, use_presidio, use_gemini, use_gliner)
