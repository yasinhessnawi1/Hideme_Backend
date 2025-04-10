"""
AIDetectService Module

This module provides the AIDetectService class that uses the Gemini AI engine to detect sensitive data
within an uploaded file. The service handles the detection pipeline by preparing the context, performing
the detection, processing the results (including applying removal words and filtering results based on
a score threshold), and returning a sanitized JSON response. The module integrates with various utility
modules for logging, memory management, data minimization, and error handling. Robust error handling is
implemented using the SecurityAwareErrorHandler class to ensure that no sensitive information is leaked
during exception handling.

In addition to the standard processing, the service accepts a 'threshold' parameter (a value between 0.00
and 1.00). This threshold is used to filter the detection results so that only entities with a confidence
score greater than or equal to the threshold are retained. Both the flat entities list and the nested
redaction mapping are filtered for consistent output.
"""

import time
import uuid
from typing import Optional

from fastapi import UploadFile
from fastapi.responses import JSONResponse

from backend.app.services.base_detect_service import BaseDetectionService
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.logging.logger import log_info, log_error
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.validation.data_minimization import minimize_extracted_data
from backend.app.utils.validation.sanitize_utils import replace_original_text_in_redaction


class AIDetectService(BaseDetectionService):
    """
    Service for Gemini AI sensitive data detection.

    This class processes an uploaded file to detect sensitive information using the Gemini AI engine.
    It follows these steps:
      1. Prepares the detection context (extracts file content and validates inputs).
      2. Minimizes the extracted data for processing efficiency.
      3. Retrieves the Gemini detector from the initialization service.
      4. Performs detection within a specified timeout.
      5. Unpacks and validates the raw detection results.
      6. Optionally applies removal words to update the detection results.
      7. Computes statistics and records processing metrics.
      8. Filters the detection results based on a provided threshold.
      9. Prepares the final sanitized JSON response by appending file and engine metadata,
         as well as debug information.

    The 'threshold' parameter (expected between 0.00 and 1.00) is used to filter both the flat list of
    detected entities and the nested redaction mapping. If no threshold is provided, a default value of 0.85 is used.
    """

    async def detect(self, file: UploadFile, requested_entities: Optional[str],
                     remove_words: Optional[str] = None,
                     threshold: Optional[float] = None) -> JSONResponse:
        # Record the start time of the detection operation.
        start_time = time.time()
        # Generate a unique operation ID for logging and tracing.
        operation_id = str(uuid.uuid4())
        # Set the maximum time allowed for the detection process.
        detection_timeout = 200
        log_info(f"[SECURITY] Starting Gemini AI detection operation [operation_id={operation_id}]")

        try:
            # STEP 1: Prepare the detection context (validate file, extract text, etc.).
            extracted_data, file_content, entity_list, processing_times, error = await self.prepare_detection_context(
                file, requested_entities, operation_id, start_time
            )
            if error:
                return error

            # STEP 2: Minimize the extracted data for more efficient processing.
            minimized_data = minimize_extracted_data(extracted_data)

            # STEP 3: Retrieve the Gemini detector using the initialization service.
            detector = initialization_service.get_gemini_detector()

            # STEP 4: Execute detection with a timeout.
            detection_start = time.time()
            detection_result, detection_error = await self.perform_detection(
                detector, minimized_data, entity_list, detection_timeout, operation_id
            )
            if detection_error:
                return detection_error
            processing_times["detection_time"] = time.time() - detection_start

            # STEP 5: Check and unpack the detection results.
            if detection_result is None:
                log_error(f"[SECURITY] Gemini detection returned no results [operation_id={operation_id}]")
                return JSONResponse(
                    status_code=500,
                    content={"detail": "Detection failed to return results", "operation_id": operation_id}
                )
            entities, redaction_mapping = detection_result

        except Exception as e:
            error_response = SecurityAwareErrorHandler.handle_detection_error(e, "detection_pipeline")
            return JSONResponse(status_code=500, content=error_response)

        try:
            # STEP 6: Calculate the total processing time.
            processing_times["total_time"] = time.time() - start_time

            # STEP 7: Optionally apply removal words to the detection result.
            if remove_words:
                entities, redaction_mapping = self.apply_removal_words(
                    extracted_data, detection_result, remove_words
                )

            # STEP 8: Compute additional statistics and update processing metrics.
            stats = self.compute_statistics(extracted_data, entities)
            processing_times.update(stats)
            if "entity_density" in stats:
                log_info(f"[SECURITY] Entity density: {stats['entity_density']:.2f} entities per 1000 words "
                         f"[operation_id={operation_id}]")

            # STEP 9: Record processing details for auditing.
            record_keeper.record_processing(
                operation_type="gemini_detection",
                document_type=file.content_type,
                entity_types_processed=entity_list or [],
                processing_time=processing_times["total_time"],
                entity_count=len(entities),
                success=True
            )

            # STEP 10: Update the redaction mapping with engine-specific markers.
            redaction_mapping = replace_original_text_in_redaction(redaction_mapping, engine_name="gemini")

            # STEPS 11-13: Prepare final JSON response using the centralized helper.
            # This helper applies threshold filtering, sanitizes output, and appends metadata.
            # Note: The helper method returns a JSONResponse for consistency.
            final_response = BaseDetectionService.prepare_final_response(
                file=file,
                file_content=file_content,
                entities=entities,
                redaction_mapping=redaction_mapping,
                processing_times=processing_times,
                threshold=threshold,
                engine_name="gemini"
            )
            # Log successful operation details immediately before returning.
            log_info(
                f"[SECURITY] Gemini detection operation completed successfully in {processing_times['total_time']:.3f}s [operation_id={operation_id}]")
            return final_response

        except Exception as e:
            error_response = SecurityAwareErrorHandler.handle_safe_error(e, "post_processing")
            return JSONResponse(status_code=500, content=error_response)
