"""
MashinLearningService Module

This module provides the MashinLearningService class for machine learning–based sensitive data detection.
It supports detectors such as "presidio" and "gliner". The service processes an uploaded file to extract text,
minimizes the data, selects the appropriate detector, performs detection, and returns a sanitized JSON response.
Comprehensive error handling is implemented throughout the detection pipeline using SecurityAwareErrorHandler to ensure
robust error management and logging.

In addition to the standard processing, the service accepts a 'threshold' parameter (a value between 0.00 and 1.00).
This threshold is used to filter the detection results so that only entities with a confidence score greater than or equal
to the threshold are retained. Both the flat list of entities and the nested redaction mapping are filtered accordingly.
"""

import time
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


class MashinLearningService(BaseDetectionService):
    """
    Service for machine learning sensitive data detection.

    This class processes an uploaded file to detect sensitive information using a machine learning
    detector. It supports detectors such as "presidio" and "gliner". The detection pipeline includes:
      1. Preparing the detection context.
      2. Minimizing the extracted data.
      3. Selecting the appropriate detector based on the provided type.
      4. Performing detection with a specified timeout.
      5. Optionally applying removal words.
      6. Computing statistics and recording processing metrics.
      7. Updating the redaction mapping with engine-specific markers.
      8. Filtering the detection results based on a provided threshold.
      9. Preparing the final sanitized JSON response with file, engine metadata and debug info.

    The 'threshold' parameter (expected between 0.00 and 1.00) is used to filter both the flat list of detected entities
    and the nested redaction mapping. If not provided, a default value of 0.85 is used.
    """

    def __init__(self, detector_type: str):
        # Store the detector type in lowercase for consistency.
        self.detector_type = detector_type.lower()

    async def detect(self, file: UploadFile, requested_entities: Optional[str],
                     operation_id: str, remove_words: Optional[str] = None,
                     threshold: Optional[float] = None) -> JSONResponse:
        """
        Asynchronously detects sensitive data in the uploaded file using a machine learning detector.

        The method performs the following steps:
          1. Records the start time and logs the beginning of the operation.
          2. Prepares the detection context by extracting necessary data from the file.
          3. Minimizes the extracted data.
          4. Initializes the appropriate detector based on the detector type.
          5. Performs detection with a timeout and unpacks the raw results.
          6. Computes total processing time and logs detection metrics.
          7. Optionally applies removal words to update the detection results.
          8. Computes additional statistics and records processing metrics.
          9. Updates the redaction mapping with engine-specific markers.
         10. Filters the detection results based on the provided threshold.
         11. Prepares the final sanitized JSON response using a centralized helper method.
         12. Returns the final JSON response.

        Parameters:
            file (UploadFile): The uploaded file for processing.
            requested_entities (Optional[str]): Specific entities to detect (as a string or JSON).
            operation_id (str): Unique identifier for the operation used for logging and tracing.
            remove_words (Optional[str]): Optional words/phrases to remove from the detection output.
            threshold (Optional[float]): A numeric threshold (expected between 0.00 and 1.00) used for filtering
                                         detection results. If not provided, a default of 0.85 is used.

        Returns:
            JSONResponse: A JSON response containing the sanitized detection output along with file and engine metadata
                          and additional debug information.
        """
        # Record the start time of the detection operation.
        start_time = time.time()
        log_info(f"[ML] Starting {self.detector_type} detection operation [operation_id={operation_id}]")
        try:
            # STEP 1: Prepare the detection context (e.g., file validation, text extraction).
            extracted_data, file_content, entity_list, processing_times, error = await self.prepare_detection_context(
                file, requested_entities, operation_id, start_time
            )
            if error:
                return error

            # STEP 2: Minimize the extracted data for efficient processing.
            minimized_data = minimize_extracted_data(extracted_data)

            # STEP 3: Initialize the appropriate detector based on the detector type.
            if self.detector_type == "presidio" and hasattr(initialization_service, "get_presidio_detector"):
                detector = initialization_service.get_presidio_detector()
            elif self.detector_type == "gliner" and hasattr(initialization_service, "get_gliner_detector"):
                detector = initialization_service.get_gliner_detector(entity_list)
            elif self.detector_type == "hideme" and hasattr(initialization_service, "get_hideme_detector"):
                detector = initialization_service.get_hideme_detector(entity_list)
            else:
                return JSONResponse(
                    status_code=400,
                    content={"detail": f"Unsupported detector type: {self.detector_type}"}
                )

            # STEP 4: Perform detection using the selected detector with a timeout.
            detection_start = time.time()
            detection_result, detection_error = await self.perform_detection(
                detector, minimized_data, entity_list, detection_timeout=600, operation_id=operation_id
            )
            if detection_error:
                return detection_error
            processing_times["detection_time"] = time.time() - detection_start

            # STEP 5: Validate and unpack the detection results.
            if detection_result is None:
                log_error(f"[ML] {self.detector_type} detection returned no results [operation_id={operation_id}]")
                return JSONResponse(
                    status_code=500,
                    content={"detail": f"{self.detector_type} detection failed to return results",
                             "operation_id": operation_id}
                )
            entities, redaction_mapping = detection_result

        except Exception as e:
            # Handle exceptions in the detection pipeline.
            error_response = SecurityAwareErrorHandler.handle_safe_error(e, "detection_ml_detect")
            status = error_response.get("status_code", 500)
            return JSONResponse(status_code=status, content=error_response)

        try:
            # STEP 6: Compute total processing time.
            total_time = time.time() - start_time
            processing_times["total_time"] = total_time
            log_info(f"[ML] {self.detector_type} detection completed in {processing_times['detection_time']:.3f}s. "
                     f"Found {len(entities)} entities [operation_id={operation_id}]")

            # STEP 7: Optionally apply removal words if provided.
            if remove_words:
                entities, redaction_mapping = self.apply_removal_words(extracted_data, detection_result, remove_words)

            # STEP 8: Compute additional statistics and update processing metrics.
            stats = self.compute_statistics(extracted_data, entities)
            processing_times.update(stats)
            if "entity_density" in stats:
                log_info(f"[ML] Entity density: {stats['entity_density']:.2f} entities per 1000 words "
                         f"[operation_id={operation_id}]")

            # STEP 9: Record processing details for auditing.
            record_keeper.record_processing(
                operation_type=f"{self.detector_type}_detection",
                document_type=file.content_type,
                entity_types_processed=entity_list or [],
                processing_time=total_time,
                entity_count=len(entities),
                success=True
            )

            # STEP 10: Update the redaction mapping with engine-specific markers.
            redaction_mapping = replace_original_text_in_redaction(redaction_mapping, engine_name=self.detector_type)

            # STEP 11-13: Use the centralized helper method to apply threshold filtering,
            # sanitize the detection output, and append file and engine metadata.
            final_response = BaseDetectionService.prepare_final_response(
                file=file,
                file_content=file_content,
                entities=entities,
                redaction_mapping=redaction_mapping,
                processing_times=processing_times,
                threshold=threshold,
                engine_name=self.detector_type
            )
            # Log the successful completion before returning.
            log_info(f"[ML] {self.detector_type} detection operation completed successfully in {total_time:.3f}s "
                     f"[operation_id={operation_id}]")
            return final_response
        except Exception as e:
            # Handle errors during post-detection processing.
            error_response = SecurityAwareErrorHandler.handle_safe_error(e, "detection_post_processing")
            status = error_response.get("status_code", 500)
            return JSONResponse(status_code=status, content=error_response)
