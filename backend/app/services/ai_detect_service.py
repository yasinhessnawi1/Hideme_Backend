"""
AIDetectService Module

This module provides the AIDetectService class that uses the Gemini AI engine to detect sensitive data
within an uploaded file. The service handles the detection pipeline by preparing the context, performing
the detection, processing the results, and returning a sanitized JSON response. The module integrates
with various utility modules for logging, memory management, data minimization, and error handling.
Error handling throughout the service is implemented using the SecurityAwareErrorHandler class to
ensure that no sensitive information is leaked during exception handling.
"""

import time
import uuid
from typing import Optional

from fastapi import UploadFile
from fastapi.responses import JSONResponse

from backend.app.services.initialization_service import initialization_service
from backend.app.utils.logging.logger import log_info, log_error
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.system_utils.memory_management import memory_monitor
from backend.app.utils.validation.data_minimization import minimize_extracted_data
from backend.app.utils.validation.sanitize_utils import sanitize_detection_output, replace_original_text_in_redaction
from backend.app.services.base_detect_service import BaseDetectionService


class AIDetectService(BaseDetectionService):
    """
    Service for Gemini AI sensitive data detection.

    This class processes an uploaded file to detect sensitive information using the Gemini AI engine.
    It follows a series of steps including context preparation, data minimization, detection execution,
    result processing, and final response formulation. Robust error handling is implemented at every
    step to ensure security and privacy.

    Attributes:
        (Inherited from BaseDetectionService, if applicable)

    Methods:
        detect(file: UploadFile, requested_entities: Optional[str], remove_words: Optional[str] = None)
            Processes the uploaded file for sensitive data detection and returns a JSON response.
    """

    async def detect(self, file: UploadFile, requested_entities: Optional[str],
                     remove_words: Optional[str] = None) -> JSONResponse:
        """
        Asynchronously detect sensitive data in an uploaded file using the Gemini AI engine.

        This method performs the following steps:
            1. Records the start time and generates a unique operation ID.
            2. Prepares the detection context by extracting necessary data from the file.
            3. Minimizes the extracted data for efficient processing.
            4. Retrieves the Gemini detector and performs the detection within a specified timeout.
            5. Processes the detection results, including applying removal words if provided.
            6. Computes statistics and records processing metrics.
            7. Constructs a sanitized JSON response with detailed file and model information, along with debug data.
            8. Uses SecurityAwareErrorHandler for robust error handling throughout the process.

        Parameters:
            file (UploadFile): The file uploaded by the user for processing.
            requested_entities (Optional[str]): The specific entities requested for detection.
            remove_words (Optional[str]): Optional words to remove from the detection results.

        Returns:
            JSONResponse: A JSON response containing the sanitized detection output, file info, model info,
                          and additional debug data.
        """
        start_time = time.time()  # Start time for overall processing.
        operation_id = str(uuid.uuid4())  # Unique ID for the operation.
        detection_timeout = 200  # Maximum time allowed for detection.
        log_info(f"[SECURITY] Starting Gemini AI detection operation [operation_id={operation_id}]")

        # Grouping the detection pipeline steps in one try block.
        try:
            # 1. Prepare detection context.
            extracted_data, file_content, entity_list, processing_times, error = await self.prepare_detection_context(
                file, requested_entities, operation_id, start_time
            )
            if error:
                return error

            # 2. Minimize extracted data.
            minimized_data = minimize_extracted_data(extracted_data)

            # 3. Retrieve the detector.
            detector = initialization_service.get_gemini_detector()

            # 4. Execute detection.
            detection_start = time.time()
            detection_result, detection_error = await self.perform_detection(
                detector, minimized_data, entity_list, detection_timeout, operation_id
            )
            if detection_error:
                return detection_error
            processing_times["detection_time"] = time.time() - detection_start

            # 5. Validate and unpack detection results.
            if detection_result is None:
                log_error(f"[SECURITY] Gemini detection returned no results [operation_id={operation_id}]")
                return JSONResponse(
                    status_code=500,
                    content={"detail": "Detection failed to return results", "operation_id": operation_id}
                )
            entities, redaction_mapping = detection_result
        except Exception as e:
            # Handle any exception during the detection pipeline.
            error_response = SecurityAwareErrorHandler.handle_detection_error(e, "detection_pipeline")
            return JSONResponse(status_code=500, content=error_response)

        # Grouping post-detection processing steps in another try block.
        try:
            processing_times["total_time"] = time.time() - start_time  # Total processing time.

            # 6. Optionally apply removal words.
            if remove_words:
                entities, redaction_mapping = self.apply_removal_words(
                    extracted_data, detection_result, remove_words
                )

            # 7. Compute statistics and update processing times.
            stats = self.compute_statistics(extracted_data, entities)
            processing_times.update(stats)
            if "entity_density" in stats:
                log_info(
                    f"[SECURITY] Entity density: {stats['entity_density']:.2f} entities per 1000 words [operation_id={operation_id}]"
                )

            # 8. Record processing details for auditing.
            record_keeper.record_processing(
                operation_type="gemini_detection",
                document_type=file.content_type,
                entity_types_processed=entity_list or [],
                processing_time=processing_times["total_time"],
                entity_count=len(entities),
                success=True
            )

            # 9. Update redaction mapping with engine-specific markers.
            redaction_mapping = replace_original_text_in_redaction(redaction_mapping, engine_name="gemini")

            # 10. Sanitize the detection output.
            response_payload = sanitize_detection_output(entities, redaction_mapping, processing_times)

            # 11. Add file and model metadata.
            response_payload["file_info"] = {
                "filename": file.filename,
                "content_type": file.content_type,
                "size": f"{round(len(file_content) / (1024 * 1024), 2)} MB"
            }
            response_payload["model_info"] = {"engine": "gemini"}

            # 12. Retrieve memory statistics for debug information.
            mem_stats = memory_monitor.get_memory_stats()
            response_payload["_debug"] = {
                "memory_usage": mem_stats["current_usage"],
                "peak_memory": mem_stats["peak_usage"],
                "operation_id": operation_id
            }

            # 13. Log sensitive operation details for auditing.
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
        except Exception as e:
            # Handle any exception during post-detection processing.
            error_response = SecurityAwareErrorHandler.handle_safe_error(e, "post_processing")
            return JSONResponse(status_code=500, content=error_response)

        log_info(
            f"[SECURITY] Gemini detection operation completed successfully in {processing_times['total_time']:.3f}s [operation_id={operation_id}]"
        )
        return JSONResponse(content=response_payload)
