import time
import uuid
from typing import Optional

from fastapi import UploadFile
from fastapi.responses import JSONResponse

from backend.app.services.initialization_service import initialization_service
from backend.app.utils.logging.logger import log_info, log_error
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.system_utils.memory_management import memory_monitor
from backend.app.utils.validation.data_minimization import minimize_extracted_data
from backend.app.utils.validation.sanitize_utils import sanitize_detection_output
from backend.app.services.base_detect_service import BaseDetectionService



class AIDetectService(BaseDetectionService):
    """
    Service for Gemini AI sensitive data detection.
    """

    async def detect(self, file: UploadFile, requested_entities: Optional[str],
                     remove_words: Optional[str] = None) -> JSONResponse:
        start_time = time.time()
        operation_id = str(uuid.uuid4())
        detection_timeout = 200

        log_info(f"[SECURITY] Starting Gemini AI detection operation [operation_id={operation_id}]")

        # Prepare the common detection context.
        extracted_data, file_content, entity_list, processing_times, error = await self.prepare_detection_context(
            file, requested_entities, operation_id, start_time
        )
        if error:
            return error

        # Minimize extracted data.
        minimized_data = minimize_extracted_data(extracted_data)

        # Get the detector.
        detector = initialization_service.get_gemini_detector()

        # Perform detection.
        detection_start = time.time()
        detection_result, detection_error = await self.perform_detection(detector, minimized_data, entity_list,
                                                                         detection_timeout, operation_id)
        if detection_error:
            return detection_error
        processing_times["detection_time"] = time.time() - detection_start

        if detection_result is None:
            log_error(f"[SECURITY] Gemini detection returned no results [operation_id={operation_id}]")
            return JSONResponse(
                status_code=500,
                content={"detail": "Detection failed to return results", "operation_id": operation_id}
            )

        entities, redaction_mapping = detection_result
        processing_times["total_time"] = time.time() - start_time
        log_info(f"[SECURITY] Gemini detection completed in {processing_times['detection_time']:.3f}s. "
                 f"Found {len(entities)} entities [operation_id={operation_id}]")

        # Apply removal words if provided.
        if remove_words:
            entities, redaction_mapping = self.apply_removal_words(extracted_data, detection_result, remove_words)

        # Compute statistics.
        stats = self.compute_statistics(extracted_data, entities)
        processing_times.update(stats)
        if "entity_density" in stats:
            log_info(
                f"[SECURITY] Entity density: {stats['entity_density']:.2f} entities per 1000 words [operation_id={operation_id}]")

        record_keeper.record_processing(
            operation_type="gemini_detection",
            document_type=file.content_type,
            entity_types_processed=entity_list or [],
            processing_time=processing_times["total_time"],
            entity_count=len(entities),
            success=True
        )

        # Prepare response.
        response_payload = sanitize_detection_output(entities, redaction_mapping, processing_times)
        response_payload["file_info"] = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": f"{round(len(file_content) / (1024 * 1024), 2)} MB"
        }
        response_payload["model_info"] = {"engine": "gemini"}
        mem_stats = memory_monitor.get_memory_stats()
        response_payload["_debug"] = {
            "memory_usage": mem_stats["current_usage"],
            "peak_memory": mem_stats["peak_usage"],
            "operation_id": operation_id
        }
        log_sensitive_operation(
            "Gemini Detection",
            len(entities),
            processing_times["total_time"],
            pages=processing_times.get("pages_count", 0),
            words=processing_times.get("words_count", 0),
            extract_time=processing_times.get("extraction_time", 0),
            detect_time=processing_times.get("detection_time", 0),
            operation_id=operation_id
        )
        log_info(
            f"[SECURITY] Gemini detection operation completed successfully in {processing_times['total_time']:.3f}s [operation_id={operation_id}]")
        return JSONResponse(content=response_payload)
