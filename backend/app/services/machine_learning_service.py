import time
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



class MashinLearningService(BaseDetectionService):
    """
    Service for machine learning sensitive data detection.
    Supports detectors like "presidio" and "gliner".
    """

    def __init__(self, detector_type: str):
        self.detector_type = detector_type.lower()

    async def detect(self, file: UploadFile, requested_entities: Optional[str],
                     operation_id: str, remove_words: Optional[str] = None) -> JSONResponse:
        start_time = time.time()
        log_info(f"[ML] Starting {self.detector_type} detection operation [operation_id={operation_id}]")

        # Prepare the common detection context.
        extracted_data, file_content, entity_list, processing_times, error = await self.prepare_detection_context(
            file, requested_entities, operation_id, start_time
        )
        if error:
            return error

        # Minimize extracted data.
        minimized_data = minimize_extracted_data(extracted_data)

        # Initialize detector.
        if self.detector_type == "presidio" and hasattr(initialization_service, "get_presidio_detector"):
            detector = initialization_service.get_presidio_detector()
        elif self.detector_type == "gliner" and hasattr(initialization_service, "get_gliner_detector"):
            detector = initialization_service.get_gliner_detector(entity_list)
        else:
            return JSONResponse(
                status_code=400,
                content={"detail": f"Unsupported detector type: {self.detector_type}"}
            )

        # Perform detection.
        detection_start = time.time()
        detection_result, detection_error = await self.perform_detection(detector, minimized_data, entity_list,
                                                                         detection_timeout=600,
                                                                         operation_id=operation_id)
        if detection_error:
            return detection_error
        processing_times["detection_time"] = time.time() - detection_start

        if detection_result is None:
            log_error(f"[ML] {self.detector_type} detection returned no results [operation_id={operation_id}]")
            return JSONResponse(
                status_code=500,
                content={"detail": f"{self.detector_type} detection failed to return results",
                         "operation_id": operation_id}
            )

        entities, redaction_mapping = detection_result
        total_time = time.time() - start_time
        processing_times["total_time"] = total_time
        log_info(f"[ML] {self.detector_type} detection completed in {processing_times['detection_time']:.3f}s. "
                 f"Found {len(entities)} entities [operation_id={operation_id}]")

        # Apply removal words if provided.
        if remove_words:
            entities, redaction_mapping = self.apply_removal_words(extracted_data, detection_result, remove_words)

        # Compute statistics.
        stats = self.compute_statistics(extracted_data, entities)
        processing_times.update(stats)
        if "entity_density" in stats:
            log_info(
                f"[ML] Entity density: {stats['entity_density']:.2f} entities per 1000 words [operation_id={operation_id}]")

        # Record processing.
        record_keeper.record_processing(
            operation_type=f"{self.detector_type}_detection",
            document_type=file.content_type,
            entity_types_processed=entity_list or [],
            processing_time=total_time,
            entity_count=len(entities),
            success=True
        )

        # Prepare response.
        sanitized_response = sanitize_detection_output(entities, redaction_mapping, processing_times)
        sanitized_response["file_info"] = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": f"{round(len(file_content) / (1024 * 1024), 2)} MB"
        }
        sanitized_response["model_info"] = {"engine": self.detector_type}
        mem_stats = memory_monitor.get_memory_stats()
        sanitized_response["_debug"] = {
            "memory_usage": mem_stats["current_usage"],
            "peak_memory": mem_stats["peak_usage"],
            "operation_id": operation_id
        }

        log_sensitive_operation(
            f"{self.detector_type.capitalize()} Detection",
            len(entities),
            total_time,
            pages=processing_times.get("pages_count", 0),
            words=processing_times.get("words_count", 0),
            extract_time=processing_times.get("extraction_time", 0),
            detect_time=processing_times.get("detection_time", 0),
            operation_id=operation_id
        )
        log_info(
            f"[ML] {self.detector_type} detection operation completed successfully in {total_time:.3f}s [operation_id={operation_id}]")
        return JSONResponse(content=sanitized_response)
