import asyncio
import time
import uuid
from typing import Dict, Any, List, Optional, Tuple

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
from backend.app.utils.logger import log_info, log_warning, log_error

CHUNK_SIZE = 1 * 1024 * 1024  # 1MB


async def process_file_in_chunks(
        file: UploadFile,
        entity_list: List[str],
        use_presidio: bool,
        use_gemini: bool,
        use_gliner: bool,
        start_time: float,
        operation_id: str = None,
) -> JSONResponse:
    operation_id = operation_id or str(uuid.uuid4())
    processing_times = {}
    log_info(f"[SECURITY] Starting chunked processing [operation_id={operation_id}, file={file.filename}]")

    try:
        validation_result = await validate_initial_chunk(file, operation_id)
        if isinstance(validation_result, JSONResponse):
            return validation_result

        if "pdf" in file.content_type.lower():
            return await process_pdf_in_chunks(
                file, entity_list, use_presidio, use_gemini, use_gliner, start_time, operation_id
            )

        contents, total_size = await read_and_combine_chunks(file, operation_id)
        processing_times["file_read_time"] = time.time() - start_time

        extracted_data = await extract_and_minimize_text(file.content_type, contents, processing_times, operation_id)
        config = create_detector_config(use_presidio, use_gemini, use_gliner, entity_list)
        detector = await initialize_hybrid_detector(config, operation_id)

        detection_result = await execute_detection(
            detector, extracted_data, entity_list, processing_times, operation_id
        )
        if isinstance(detection_result, JSONResponse):
            return detection_result

        anonymized_text, entities, redaction_mapping = process_detection_results(
            detection_result, processing_times, start_time, operation_id
        )
        record_processing_metrics("hybrid_detection_chunked", file.content_type, entity_list, processing_times,
                                  entities)

        return construct_final_response(
            anonymized_text, entities, redaction_mapping, processing_times, file, total_size,
            use_presidio, use_gemini, use_gliner, operation_id, "chunked"
        )

    except Exception as e:
        return handle_processing_error(e, "chunked", use_presidio, use_gemini, use_gliner, operation_id)


async def process_pdf_in_chunks(
        file: UploadFile,
        entity_list: List[str],
        use_presidio: bool,
        use_gemini: bool,
        use_gliner: bool,
        start_time: float,
        operation_id: Optional[str] = None
) -> JSONResponse:
    operation_id = operation_id or str(uuid.uuid4())
    processing_times = {}
    log_info(f"[SECURITY] Starting PDF processing [operation_id={operation_id}, file={file.filename}]")

    try:
        extracted_data = await extract_pdf_text(file, operation_id)
        processing_times["extraction_time"] = time.time() - start_time

        config = create_detector_config(use_presidio, use_gemini, use_gliner, entity_list)
        detector = await initialize_hybrid_detector(config, operation_id)

        pages = extracted_data.get("pages", [])
        if len(pages) > 20:
            return await process_large_document_in_batches(
                pages, entity_list, config, file, start_time, processing_times, operation_id
            )

        detection_result = await execute_detection(
            detector, extracted_data, entity_list, processing_times, operation_id
        )
        if isinstance(detection_result, JSONResponse):
            return detection_result

        anonymized_text, entities, redaction_mapping = process_detection_results(
            detection_result, processing_times, start_time, operation_id
        )
        record_processing_metrics("hybrid_detection_pdf_chunked", "application/pdf", entity_list, processing_times,
                                  entities)

        return construct_final_response(
            anonymized_text, entities, redaction_mapping, processing_times, file, "streamed",
            use_presidio, use_gemini, use_gliner, operation_id, "pdf_chunked"
        )

    except Exception as e:
        return handle_processing_error(e, "pdf_chunked", use_presidio, use_gemini, use_gliner, operation_id)


async def process_large_document_in_batches(
        pages: List[Dict[str, Any]],
        entity_list: List[str],
        config: Dict[str, Any],
        file: UploadFile,
        start_time: float,
        processing_times: Dict[str, float],
        operation_id: Optional[str] = None
) -> JSONResponse:
    operation_id = operation_id or str(uuid.uuid4())
    log_info(f"[SECURITY] Starting batch processing [operation_id={operation_id}, pages={len(pages)}]")

    try:
        detector = await initialize_hybrid_detector(config, operation_id)
        batch_size = 10
        all_entities, all_redaction = await process_batches(
            pages, detector, entity_list, batch_size, operation_id
        )

        processing_times.update({
            "detection_time": time.time() - start_time,
            "total_time": time.time() - start_time,
            "pages_count": len(pages),
            "words_count": sum(len(p.get("words", [])) for p in pages)
        })

        record_processing_metrics("hybrid_detection_batched", file.content_type, entity_list, processing_times,
                                  all_entities)
        return construct_batch_response(all_entities, all_redaction, processing_times, file, config, operation_id,
                                        batch_size)

    except Exception as e:
        return handle_processing_error(e, "batched", config.get("use_presidio"), config.get("use_gemini"),
                                       config.get("use_gliner"), operation_id)


# Helper functions
async def validate_initial_chunk(file: UploadFile, operation_id: str) -> Optional[JSONResponse]:
    first_chunk = await file.read(8192)
    await file.seek(0)
    is_valid, reason, _ = await validate_file_content_async(first_chunk, file.filename, file.content_type)
    if not is_valid:
        log_warning(f"[SECURITY] Validation failed: {reason} [operation_id={operation_id}]")
        return JSONResponse(status_code=415, content={"detail": reason})
    return None


async def read_and_combine_chunks(file: UploadFile, operation_id: str) -> Tuple[bytes, int]:
    chunks: List[bytes] = []  # Explicit type annotation
    total_size = 0
    try:
        while True:
            chunk: bytes = await file.read(CHUNK_SIZE)  # Type annotation ensures bytes
            if not chunk:
                break
            if (total_size + len(chunk)) > MAX_TEXT_SIZE_BYTES:
                raise ValueError(f"File exceeds {MAX_TEXT_SIZE_BYTES // (1024 * 1024)}MB limit")
            chunks.append(chunk)
            total_size += len(chunk)
        return b''.join(chunks), total_size
    except ValueError as ve:
        log_warning(f"[SECURITY] Size exceeded: {ve} [operation_id={operation_id}]")
        raise
    except Exception as e:
        log_error(f"[SECURITY] Read error: {e} [operation_id={operation_id}]")
        raise


async def extract_and_minimize_text(
        content_type: str,
        contents: bytes,
        processing_times: Dict,
        operation_id: str
) -> Dict:
    try:
        # Handle text extraction
        start = time.time()
        extracted = await extract_text_data_in_memory(content_type, contents)
        processing_times["extraction_time"] = time.time() - start

        # Attempt minimization with fallback
        try:
            return minimize_extracted_data(extracted)
        except Exception as minimize_error:
            log_warning(
                f"[SECURITY] Minimization error, using original data: {minimize_error} "
                f"[operation_id={operation_id}]"
            )
            return extracted

    except Exception as extraction_error:
        # Handle extraction failures separately
        log_error(
            f"[SECURITY] Extraction failed: {extraction_error} "
            f"[operation_id={operation_id}]"
        )
        raise  # Re-raise to let caller handle extraction failures


def create_detector_config(use_presidio: bool, use_gemini: bool, use_gliner: bool, entities: List[str]) -> Dict:
    return {
        "use_presidio": use_presidio,
        "use_gemini": use_gemini,
        "use_gliner": use_gliner,
        "gliner_model_name": GLINER_MODEL_NAME,
        "entities": entities
    }


async def initialize_hybrid_detector(config: Dict, operation_id: str):
    try:
        log_info(f"[SECURITY] Initializing detector [operation_id={operation_id}]")
        return await initialization_service.get_hybrid_detector(config)
    except Exception as e:
        log_error(f"[SECURITY] Detector init failed: {e} [operation_id={operation_id}]")
        raise


async def execute_detection(detector, extracted_data, entity_list, processing_times, operation_id: str):
    try:
        start = time.time()
        if hasattr(detector, 'detect_sensitive_data_async'):
            task = detector.detect_sensitive_data_async(extracted_data, entity_list)
        else:
            task = asyncio.to_thread(detector.detect_sensitive_data, extracted_data, entity_list)
        result = await asyncio.wait_for(task, timeout=60)
        processing_times["detection_time"] = time.time() - start
        return result
    except asyncio.TimeoutError:
        log_error(f"[SECURITY] Detection timeout [operation_id={operation_id}]")
        return JSONResponse(status_code=408, content={"detail": "Detection timeout"})
    except Exception as e:
        log_error(f"[SECURITY] Detection error: {e} [operation_id={operation_id}]")
        raise


def process_detection_results(detection_result, processing_times, start_time, operation_id: str):
    try:
        anonymized_text, entities, redaction_mapping = detection_result
        processing_times["total_time"] = time.time() - start_time
        return anonymized_text, entities, redaction_mapping
    except Exception as e:
        log_error(f"[SECURITY] Result processing error: {e} [operation_id={operation_id}]")
        raise


def record_processing_metrics(operation_type: str, doc_type: str, entities: List[str],
                              processing_times: Dict, entities_found: List):
    try:
        record_keeper.record_processing(
            operation_type=operation_type,
            document_type=doc_type,
            entity_types_processed=entities,
            processing_time=processing_times["total_time"],
            entity_count=len(entities_found),
            success=True
        )
    except Exception as e:
        log_warning(f"[SECURITY] Metrics error: {e}")


def construct_final_response(anonymized_text, entities, redaction_mapping, processing_times,
                             file: UploadFile, size_val, use_presidio, use_gemini, use_gliner,
                             operation_id: str, mode: str) -> JSONResponse:
    engines_used = {"presidio": use_presidio, "gemini": use_gemini, "gliner": use_gliner}
    file_info = {
        "filename": file.filename,
        "content_type": file.content_type,
        "size": size_val,
        "processing_mode": mode,
        "operation_id": operation_id
    }

    response = sanitize_detection_output(anonymized_text, entities, redaction_mapping, processing_times)
    response.update({
        "model_info": {"engine": "hybrid", "engines_used": engines_used},
        "file_info": file_info,
        "_debug": get_memory_stats(operation_id)
    })

    log_operation_details(
        "Hybrid Detection", len(entities), processing_times, engines_used, operation_id, mode
    )
    return JSONResponse(content=response)


def get_memory_stats(operation_id: str) -> Dict:
    stats = memory_monitor.get_memory_stats()
    log_info(f"[SECURITY] Memory stats: {stats} [operation_id={operation_id}]")
    return {
        "memory_usage": stats["current_usage"],
        "peak_memory": stats["peak_usage"],
        "operation_id": operation_id
    }


def log_operation_details(op_name: str, entity_count: int, processing_times: Dict,
                          engines: Dict, operation_id: str, mode: str):
    log_sensitive_operation(
        op_name,
        entity_count,
        processing_times["total_time"],
        pages=processing_times.get("pages_count", 0),
        words=processing_times.get("words_count", 0),
        engines=engines,
        extract_time=processing_times.get("extraction_time", 0),
        detect_time=processing_times.get("detection_time", 0),
        operation_id=operation_id,
        processing_mode=mode
    )


async def extract_pdf_text(file: UploadFile, operation_id: str) -> Dict:
    try:
        import pymupdf
        doc = pymupdf.open(stream=file.file, filetype="pdf")
        extracted = {"pages": []}
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            words = [{"text": w[4].strip(), "x0": w[0], "y0": w[1], "x1": w[2], "y1": w[3]}
                     for w in page.get_text("words") if w[4].strip()]
            extracted["pages"].append({"page": page_idx + 1, "words": words})
        doc.close()
        return minimize_extracted_data(extracted)
    except Exception as e:
        log_error(f"[SECURITY] PDF extraction failed: {e} [operation_id={operation_id}]")
        raise


async def process_batches(
        pages: List[Dict],
        detector: Any,  # Should be proper detector type in real code
        entity_list: List[str],
        batch_size: int,
        operation_id: str
) -> Tuple[List[Dict], List[Dict]]:  # Fixed return type annotation
    all_entities: List[Dict] = []
    all_redaction_pages: List[Dict] = []  # Changed variable name for clarity

    for i in range(0, len(pages), batch_size):
        batch = pages[i:i + batch_size]
        try:
            result = await detector.detect_sensitive_data_async(
                {"pages": batch},
                entity_list
            )
            all_entities.extend(result[1])

            # Extract pages from redaction mapping and extend list
            redaction_mapping = result[2]
            all_redaction_pages.extend(redaction_mapping.get("pages", []))

        except Exception as e:
            log_warning(f"[SECURITY] Batch {i // batch_size} failed: {e} [operation_id={operation_id}]")

    return all_entities, all_redaction_pages


def construct_batch_response(entities, redaction, processing_times, file: UploadFile,
                             config: Dict, operation_id: str, batch_size: int) -> JSONResponse:
    response = sanitize_detection_output(
        "Batched processing complete", entities, redaction, processing_times
    )
    response.update({
        "model_info": {
            "engine": "hybrid",
            "engines_used": {
                "presidio": config["use_presidio"],
                "gemini": config["use_gemini"],
                "gliner": config["use_gliner"]
            },
            "batched": True
        },
        "file_info": {
            "filename": file.filename,
            "content_type": file.content_type,
            "batch_size": batch_size,
            "operation_id": operation_id
        },
        "_debug": get_memory_stats(operation_id)
    })
    return JSONResponse(content=response)


def handle_processing_error(error: Exception, mode: str, use_presidio: bool,
                            use_gemini: bool, use_gliner: bool, operation_id: str) -> JSONResponse:
    log_error(f"[SECURITY] {mode} processing failed: {error} [operation_id={operation_id}]")
    error_response = SecurityAwareErrorHandler.handle_detection_error(error, f"hybrid_{mode}_detection")
    error_response.update({
        "model_info": {
            "engine": "hybrid",
            "engines_used": {"presidio": use_presidio, "gemini": use_gemini, "gliner": use_gliner},
            "processing_mode": mode,
            "operation_id": operation_id
        }
    })
    return JSONResponse(status_code=500, content=error_response)
