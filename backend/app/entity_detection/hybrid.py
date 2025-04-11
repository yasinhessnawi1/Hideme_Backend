"""
HybridEntityDetector class implementation.
This class combines results from multiple detection engines (such as Presidio, Gemini, and GLiNER)
to perform robust entity detection with comprehensive GDPR compliance, data minimization,
and error handling. It supports both asynchronous and synchronous detection methods.
"""

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Tuple, cast

from fastapi import HTTPException

from backend.app.domain.interfaces import EntityDetector
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.system_utils.synchronization_utils import AsyncTimeoutLock, LockPriority
from backend.app.utils.validation.data_minimization import minimize_extracted_data

# Constants for available entities by detector type
PRESIDIO_AVAILABLE_ENTITIES = ["CREDIT_CARD", "EMAIL_ADDRESS", "PHONE_NUMBER", "US_SSN", "US_BANK_ACCOUNT",
                               "US_DRIVER_LICENSE", "US_PASSPORT", "IP_ADDRESS", "DATE_TIME"]
GLINER_AVAILABLE_ENTITIES = ["PERSON", "ORGANIZATION", "LOCATION", "DATE", "MONEY", "PERCENT", "TIME", "URL"]
GEMINI_AVAILABLE_ENTITIES = {
    "PERSON_NAME": "Person names",
    "EMAIL_ADDRESS": "Email addresses",
    "PHONE_NUMBER": "Phone numbers",
    "ADDRESS": "Physical addresses",
    "CREDIT_CARD": "Credit card numbers",
    "US_SSN": "US Social Security Numbers",
    "US_TAX_ID": "US Tax IDs",
    "US_PASSPORT": "US Passport numbers",
    "BANK_ACCOUNT": "Bank account numbers"
}


class HybridEntityDetector(EntityDetector):
    """
    Enhanced hybrid entity detector that combines results from multiple engines.

    This detector runs all configured detection engines and merges their results.
    It implements comprehensive GDPR compliance, data minimization, and robust error handling.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the hybrid detector with configuration.

        Args:
            config: Configuration dictionary with settings for each detector.
        """
        # Initialize the list to store the individual detection engine instances.
        self.detectors: List[EntityDetector] = []
        # Save the provided configuration.
        self.config = config
        # Record the current time as the initialization time.
        self._initialization_time = time.time()
        # Set the last used time equal to the initialization time.
        self._last_used = self._initialization_time
        # Initialize a counter for the total detection calls.
        self._total_calls = 0
        # Initialize a counter for the total number of entities detected.
        self._total_entities_detected = 0
        # Set the detector lock to None for lazy creation.
        self._detector_lock: Optional[AsyncTimeoutLock] = None

        # If configuration requests, initialize the Presidio detector.
        if config.get("use_presidio", True):
            # Get the Presidio detector instance from the initialization service.
            presidio = initialization_service.get_presidio_detector()
            # If the Presidio detector is available...
            if presidio:
                # Append the Presidio detector to the list of detectors.
                self.detectors.append(presidio)
                self.detector_types[type(presidio).__name__] = "presidio"
                log_info("[INIT] Presidio Detector Initialized Successfully")
        # If configuration requests, initialize the Gemini detector.
        if config.get("use_gemini", True):
            # Get the Gemini detector instance.
            gemini = initialization_service.get_gemini_detector()
            # If the Gemini detector is available...
            if gemini:
                # Append it to the list of detectors.
                self.detectors.append(gemini)
                self.detector_types[type(gemini).__name__] = "gemini"
                log_info("[INIT] Gemini Detector Initialized Successfully")
            else:
                # Log a warning if Gemini detection could not be initialized.
                log_warning("[INIT] Gemini Detector Initialization Failed")
        # If configuration requests, initialize the GLiNER detector.
        if config.get("use_gliner", True):
            # Retrieve the list of entities to detect from configuration.
            entity_list = config.get("entities", [])
            # Get the GLiNER detector instance with the provided entity list.
            gliner = initialization_service.get_gliner_detector(entity_list)
            # If the GLiNER detector is available...
            if gliner:
                # Append it to the detectors list.
                self.detectors.append(gliner)
                self.detector_types[type(gliner).__name__] = "gliner"
                log_info("[INIT] GLiNER Detector Initialized Successfully")
            else:
                # Log a warning if GLiNER detector initialization failed.
                log_warning("[INIT] GLiNER Detector Initialization Failed")

    async def _get_detector_lock(self) -> AsyncTimeoutLock:
        """
        Lazily create and return the AsyncTimeoutLock to avoid event-loop conflicts.
        This lock is used to safely update usage metrics.

        Returns:
            AsyncTimeoutLock: The detector lock.
        """
        # If the detector lock has not been created yet...
        if self._detector_lock is None:
            try:
                # Create a new AsyncTimeoutLock with medium priority and a 30-second timeout.
                self._detector_lock = AsyncTimeoutLock(
                    name="hybrid_detector_lock",
                    priority=LockPriority.MEDIUM,
                    timeout=30.0
                )
            except Exception as exc:
                # Log any error during the detector lock initialization.
                SecurityAwareErrorHandler.log_processing_error(exc, "detector_lock_init", "")
        # Return the detector lock.
        return self._detector_lock

    async def detect_sensitive_data_async(
            self,
            extracted_data: Dict[str, Any],
            requested_entities: Optional[List[str]] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Detect sensitive entities using multiple detection engines asynchronously.

        This method performs the following steps:
          1. Prepares and minimizes input data, and checks if detectors exist.
          2. Increments usage metrics.
          3. Runs all detection engines in parallel.
          4. Processes and aggregates results.
          5. Finalizes detection results by merging mappings and updating records.

        Args:
            extracted_data: Dictionary containing text and bounding box information.
            requested_entities: List of three lists of entity types to detect for each detector.

        Returns:
            Tuple containing a list of detected entities and a redaction mapping.
        """
        # Mark the start time for performance tracking.
        start_time = time.time()
        try:
            # Step 1: Minimize input data for GDPR compliance.
            minimized_data = minimize_extracted_data(extracted_data)
            # Check that at least one detection engine is configured.
            if not self._prepare_data_and_check_detectors():
                # If no detectors are available, return empty results.
                return [], {"pages": []}

            # Step 2: Increment usage metrics.
            await self._increment_usage_metrics(start_time)

            # Step 3: Run each configured detector in parallel.
            parallel_results = await self._run_all_detectors_in_parallel(minimized_data, requested_entities)

            # Step 4: Process the results from all detectors.
            combined_entities, all_redaction_mappings, success_count, failure_count = \
                self._process_detection_results(parallel_results)

            # If no detector succeeded, log an error and return empty results.
            if success_count == 0:
                log_error("[ERROR] All detection engines failed")
                return [], {"pages": []}

            # Step 5: Finalize detection results by merging mappings and updating records.
            final_entities, final_mapping = await self._finalize_detection(
                combined_entities, all_redaction_mappings, extracted_data,
                requested_entities, start_time, success_count, failure_count
            )

            # Return the final aggregated results.
            return final_entities, final_mapping

        except Exception as exc:
            # Log any unexpected errors and return empty results.
            log_error(f"[ERROR] Unexpected error in hybrid detection: {str(exc)}")
            return [], {"pages": []}

    def _prepare_data_and_check_detectors(self) -> bool:
        """
        Ensure that there is at least one detection engine configured.

        Returns:
            True if detectors are available, False otherwise.
        """
        # If the detectors list is empty...
        if not self.detectors:
            # Log a warning.
            log_warning("[WARNING] No detection engines available in hybrid detector")
            return False
        # Otherwise, return True.
        return True

    async def _increment_usage_metrics(self, start_time: float) -> None:
        """
        Acquire the detector lock and update usage metrics.
        Increments the call counter and updates the last used timestamp.

        Args:
            start_time: The start time of the detection operation.
        """
        # Retrieve the detector lock asynchronously.
        detector_lock = await self._get_detector_lock()
        # Acquire the lock with a timeout.
        async with detector_lock.acquire_timeout(timeout=5.0) as acquired:
            # If the lock was acquired...
            if acquired:
                # Increment the call counter.
                self._total_calls += 1
                # Update the last used time to the start time.
                self._last_used = start_time

    async def _run_all_detectors_in_parallel(
            self,
            minimized_data: Dict[str, Any],
            requested_entities: Optional[List[str]]
    ) -> List[Dict[str, Any]]:
        """
        Create and run tasks for each configured detection engine in parallel.

        Args:
            minimized_data: The pre-processed, minimized input data.
            requested_entities: List of entity types to detect.

        Match each detector with its corresponding entity list:
        - Index 0: Presidio entities
        - Index 1: GLiNER entities
        - Index 2: Gemini entities

        Returns:
            List of dictionaries, each containing detection results from one engine.
        """
        # Create a list of asyncio tasks, one for each detection engine.
        tasks = [
            asyncio.create_task(
                self._process_single_detector(det, minimized_data, requested_entities)
            )
            for det in self.detectors
        ]
        # Execute all tasks concurrently and return the list of results.
        return await self._execute_detector_tasks(tasks)

    @staticmethod
    async def _execute_detector_tasks(tasks: List[asyncio.Future]) -> List[Dict[str, Any]]:
        """
        Helper method to run a list of detection tasks concurrently with a global timeout.

        Args:
            tasks: List of asyncio tasks.

        Returns:
            List of results from each task, or an empty list if a timeout occurs.
        """
        try:
            # Wait for all tasks to complete with a timeout.
            return await asyncio.wait_for(asyncio.gather(*tasks), timeout=600.0)
        except asyncio.TimeoutError:
            # Log an error if a global timeout occurs.
            log_error("[ERROR] Global timeout for all detection engines")
            return []

    @staticmethod
    async def _process_single_detector(
            engine_detector: EntityDetector,
            minimized_data: Dict[str, Any],
            requested_entities: Optional[List[str]]
    ) -> Dict[str, Any]:
        """
        Process a single detection engine with timeout and error handling.

        Args:
            engine_detector: The instance of a detection engine.
            minimized_data: The pre-processed input data.
            requested_entities: List of requested entity types.

        Returns:
            A dictionary containing the detection result, success flag, engine name, and timing.
        """
        # Get the engine detector's class name.
        engine_name = type(engine_detector).__name__
        # Record the engine start time.
        engine_start_time = time.time()
        try:
            # Check if the engine has an asynchronous detection method.
            if hasattr(engine_detector, "detect_sensitive_data_async"):
                # Run the engine asynchronously.
                result_tuple = await HybridEntityDetector._run_async_detector(engine_detector, minimized_data,
                                                                              requested_entities)
            else:
                # Run the engine synchronously in a separate thread.
                result_tuple = await HybridEntityDetector._run_sync_detector(engine_detector, minimized_data,
                                                                             requested_entities)
            # Check if the result is a tuple with two elements.
            if not isinstance(result_tuple, tuple) or len(result_tuple) != 2:
                return HybridEntityDetector._engine_failure_dict(engine_name,
                                                                 f"Invalid result format: {type(result_tuple)}",
                                                                 engine_start_time)
            # Unpack the results.
            found_entities, found_mapping = result_tuple
            # If the entities result is not a list, log a warning.
            if not isinstance(found_entities, list):
                log_warning(f"[WARNING] Entities result from {engine_name} is not a list")
                found_entities = []
            # If the mapping is not a dict, log a warning.
            if not isinstance(found_mapping, dict):
                log_warning(f"[WARNING] Redaction mapping from {engine_name} is not a dict")
                found_mapping = {"pages": []}
            # Compute the time taken by the engine.
            engine_time = time.time() - engine_start_time
            log_info(f"[OK] {engine_name} found {len(found_entities)} entities in {engine_time:.2f}s")
            # Record processing metrics for the engine.
            record_keeper.record_processing(
                operation_type=f"hybrid_detection_{engine_name.lower()}",
                document_type="document",
                entity_types_processed=requested_entities or [],
                processing_time=engine_time,
                entity_count=len(found_entities),
                success=True
            )
            # Return a dictionary with successful detection details.
            return {
                "success": True,
                "engine": engine_name,
                "entities": found_entities,
                "mapping": found_mapping,
                "time": engine_time
            }
        except Exception as detect_exc:
            # Log any error that occurred during detection.
            SecurityAwareErrorHandler.log_processing_error(detect_exc, f"hybrid_{engine_name.lower()}_detection",
                                                           "document")
            return HybridEntityDetector._engine_failure_dict(engine_name, str(detect_exc), engine_start_time)

    @staticmethod
    async def _run_async_detector(
            detector: EntityDetector,
            minimized_data: Dict[str, Any],
            requested_entities: Optional[List[str]]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Run an asynchronous detector with a 10-minute timeout.

        Args:
            detector: The detection engine instance with an async method.
            minimized_data: Pre-processed data.
            requested_entities: List of requested entity types.

        Returns:
            A tuple containing a list of entities and a redaction mapping.
        """
        engine_name = type(detector).__name__
        try:
            # Use cast to call the asynchronous detection method with a timeout.
            return await asyncio.wait_for(
                cast(Any, detector).detect_sensitive_data_async(minimized_data, requested_entities),
                timeout=600.0
            )
        except asyncio.TimeoutError:
            log_warning(f"[WARNING] Timeout in {engine_name} detector")
            return [], {"pages": []}

    @staticmethod
    async def _run_sync_detector(
            detector: EntityDetector,
            minimized_data: Dict[str, Any],
            requested_entities: Optional[List[str]]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Run a synchronous detector in a separate thread.

        Args:
            detector: The detection engine instance with a sync method.
            minimized_data: Pre-processed data.
            requested_entities: List of requested entity types.

        Returns:
            A tuple containing a list of entities and a redaction mapping.
        """
        engine_name = type(detector).__name__
        try:
            return await asyncio.to_thread(
                detector.detect_sensitive_data,
                minimized_data,
                requested_entities
            )
        except asyncio.TimeoutError:
            log_warning(f"[WARNING] Timeout in {engine_name} detector (sync mode)")
            return [], {"pages": []}

    @staticmethod
    def _engine_failure_dict(engine_name: str, error_msg: str, start_time: float) -> Dict[str, Any]:
        """
        Return a standardized failure dictionary for a detection engine.

        Args:
            engine_name: Name of the detection engine.
            error_msg: Error message encountered.
            start_time: Start time of the engine processing.

        Returns:
            A dictionary representing a failure result.
        """
        return {
            "success": False,
            "engine": engine_name,
            "error": error_msg,
            "time": time.time() - start_time
        }

    @staticmethod
    def _process_detection_results(
            parallel_results: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int, int]:
        """
        Process the results from all detection engines.
        Aggregates entities, redaction mappings, and counts successes and failures.

        Args:
            parallel_results: List of result dictionaries from each engine.

        Returns:
            A tuple containing:
              - All detected entities.
              - List of all redaction mappings.
              - Count of successful engines.
              - Count of failed engines.
        """
        all_entities: List[Dict[str, Any]] = []
        all_redaction_mappings: List[Dict[str, Any]] = []
        success_count = 0
        failure_count = 0
        # Iterate over each engine's result.
        for engine_result in parallel_results:
            # If the engine returned a success flag...
            if engine_result.get("success"):
                found_entities = engine_result.get("entities", [])
                found_mapping = engine_result.get("mapping", {})
                log_sensitive_operation(
                    f"{engine_result['engine']} Detection",
                    len(found_entities),
                    engine_result.get("time", 0.0),
                    engine=engine_result["engine"]
                )
                all_entities.extend(found_entities)
                all_redaction_mappings.append(found_mapping)
                success_count += 1
            else:
                failure_count += 1
        # Return aggregated results and counts.
        return all_entities, all_redaction_mappings, success_count, failure_count

    async def _finalize_detection(
            self,
            combined_entities: List[Dict[str, Any]],
            all_redaction_mappings: List[Dict[str, Any]],
            original_data: Dict[str, Any],
            requested_entities: Optional[List[str]],
            start_time: float,
            success_count: int,
            failure_count: int
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Finalize the detection by merging redaction mappings, deduplicating entities,
        updating usage metrics, and recording processing details.

        Args:
            combined_entities: Aggregated list of entities from all detectors.
            all_redaction_mappings: List of redaction mappings from each detector.
            original_data: The original input data.
            requested_entities: List of entity types to detect.
            start_time: Start time of the detection process.
            success_count: Number of engines that succeeded.
            failure_count: Number of engines that failed.

        Returns:
            A tuple containing final entities and the final merged redaction mapping.
        """
        # Merge all redaction mappings into one unified mapping.
        merged_mapping = self._merge_redaction_mappings(all_redaction_mappings)
        if not merged_mapping.get("pages"):
            merged_mapping["pages"] = []
        # Deduplicate entities using a helper function.
        from backend.app.utils.validation.sanitize_utils import deduplicate_entities
        final_entities = deduplicate_entities(combined_entities)
        total_time = time.time() - start_time
        # Update overall usage metrics using the detector lock.
        detector_lock = await self._get_detector_lock()
        async with detector_lock.acquire_timeout(timeout=5.0) as acquired:
            if acquired:
                self._total_entities_detected += len(final_entities)
        # Record overall processing details for audit and GDPR compliance.
        record_keeper.record_processing(
            operation_type="hybrid_detection",
            document_type="document",
            entity_types_processed=flat_entities or [],
            processing_time=total_time,
            file_count=1,
            entity_count=len(final_entities),
            success=(success_count > 0)
        )

        log_info(f"[PERF] Hybrid detection completed in {total_time:.2f}s "
                 f"with {success_count} successful engines and {failure_count} failures")
        log_info(f"[PERF] Total {len(final_entities)} entities detected "
                 f"across {len(original_data.get('pages', []))} pages")
        log_sensitive_operation(
            "Hybrid Detection",
            len(final_entities),
            total_time,
            engines_used=success_count,
            engines_failed=failure_count
        )
        return final_entities, merged_mapping

    @staticmethod
    def _merge_redaction_mappings(mappings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Merge multiple redaction mappings into a single unified mapping.

        Args:
            mappings: List of redaction mapping dictionaries.

        Returns:
            A merged redaction mapping dictionary.
        """
        if not mappings:
            return {"pages": []}
        merged_result = {"pages": []}
        pages_dict = {}
        # Iterate over each mapping.
        for single_mapping in mappings:
            if not isinstance(single_mapping, dict) or "pages" not in single_mapping:
                continue
            # Iterate over each page's redaction info.
            for page_info in single_mapping.get("pages", []):
                page_num = page_info.get("page")
                if page_num is None:
                    continue
                # If this page number is not yet in the dictionary, initialize it.
                if page_num not in pages_dict:
                    pages_dict[page_num] = {"page": page_num, "sensitive": []}
                # Extend the sensitive list with current page's sensitive items.
                pages_dict[page_num]["sensitive"].extend(page_info.get("sensitive", []))
        # Convert the pages dictionary to a sorted list.
        for pg_num in sorted(pages_dict.keys()):
            merged_result["pages"].append(pages_dict[pg_num])
        return merged_result

    def detect_sensitive_data(
            self,
            extracted_data: Dict[str, Any],
            requested_entities: Optional[List[str]] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Synchronous wrapper for detecting sensitive entities using multiple detection engines.

        This method creates a new event loop, executes the asynchronous detection method with a timeout,
        and returns the aggregated detection results.

        Args:
            extracted_data: Dictionary containing text and bounding box information.
            requested_entities: List of three lists for entity types to detect
                              [presidio_entities, gliner_entities, gemini_entities].

        Returns:
            Tuple of (detected entities, redaction mapping).
        """
        try:
            # Minimize input data for GDPR compliance.
            minimized_data = minimize_extracted_data(extracted_data)
            # Create a new event loop for synchronous execution.
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Define an async function that runs the detection with a timeout.
                async def run_with_timeout():
                    return await asyncio.wait_for(
                        self.detect_sensitive_data_async(minimized_data, requested_entities),
                        timeout=600.0
                    )

                # Run the async detection and return its result.
                return loop.run_until_complete(run_with_timeout())
            finally:
                # Ensure the event loop is closed after execution.
                loop.close()
        except asyncio.TimeoutError:
            # Log and return empty results on timeout.
            log_error("[ERROR] Global timeout in hybrid entity detection (sync wrapper)")
            return [], {"pages": []}
        except RuntimeError as exc:
            # Handle runtime errors due to interpreter shutdown gracefully.
            if "cannot schedule new futures after interpreter shutdown" in str(exc):
                log_warning(f"[WARNING] Shutdown in progress, returning empty results: {exc}")
                return [], {"pages": []}
            SecurityAwareErrorHandler.log_processing_error(exc, "hybrid_detection_runtime", "document")
            return [], {"pages": []}
        except Exception as exc:
            # Log any other unexpected errors and return empty results.
            SecurityAwareErrorHandler.log_processing_error(exc, "hybrid_detection", "document")
            return [], {"pages": []}

    async def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the hybrid entity detector.

        Returns:
            A dictionary with status information, including initialization times, usage metrics,
            and the list of configured detectors.
        """

        async def get_status_async() -> Dict[str, Any]:
            # Acquire the detector lock to safely read status.
            detector_lock = await self._get_detector_lock()
            async with detector_lock.acquire_timeout(timeout=1.0):
                # Return key status details.
                return {
                    "initialized": True,
                    "initialization_time": self._initialization_time,
                    "last_used": self._last_used,
                    "idle_time": time.time() - self._last_used if self._last_used else None,
                    "total_calls": self._total_calls,
                    "total_entities_detected": self._total_entities_detected,
                    "detectors": [type(det).__name__ for det in self.detectors],
                    "detector_count": len(self.detectors),
                    "config": {k: v for k, v in self.config.items() if k != "detectors"}
                }

        try:
            # Create a new event loop and run the async status function.
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(asyncio.wait_for(get_status_async(), timeout=2.0))
            finally:
                loop.close()
        except asyncio.TimeoutError:
            log_warning("[WARNING] Timeout while fetching hybrid detector status")
            return {
                "initialized": True,
                "initialization_time": self._initialization_time,
                "detectors": [type(det).__name__ for det in self.detectors],
                "detector_count": len(self.detectors),
                "status_timeout": True
            }
        except RuntimeError as exc:
            log_warning(f"[WARNING] Event loop runtime issue in get_status: {exc}")
            return {
                "initialized": True,
                "initialization_time": self._initialization_time,
                "detectors": [type(det).__name__ for det in self.detectors],
                "detector_count": len(self.detectors),
                "runtime_error": str(exc)
            }
        except Exception as exc:
            log_error(f"[ERROR] Unexpected error in get_status: {exc}")
            return {
                "initialized": True,
                "initialization_time": self._initialization_time,
                "detectors": [type(det).__name__ for det in self.detectors],
                "detector_count": len(self.detectors),
                "lock_acquisition_failed": True,
                "error": str(exc)
            }
