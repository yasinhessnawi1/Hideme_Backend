"""
This module contains the HybridEntityDetector class, an advanced entity detection tool that combines multiple detection engines
(such as Presidio, Gemini, GLiNER, and HIDEME) to perform robust sensitive data detection. It handles GDPR compliance through data minimization,
aggregates and deduplicates detected entities, and manages usage metrics with secure logging and error handling.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple, cast

from backend.app.domain.interfaces import EntityDetector
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.system_utils.synchronization_utils import AsyncTimeoutLock, LockPriority
from backend.app.utils.validation.data_minimization import minimize_extracted_data
from backend.app.utils.validation.sanitize_utils import deduplicate_entities


class HybridEntityDetector(EntityDetector):
    """
    Enhanced hybrid entity detector that aggregates multiple detection engine results.

    The HybridEntityDetector class initializes various detection engines according to the configuration provided,
    then uses them concurrently to detect sensitive data. It handles data minimization for GDPR compliance,
    aggregates and deduplicates entities from multiple engines, updates usage metrics securely, and provides
    both asynchronous and synchronous interfaces.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the hybrid detector with configuration.

        Args:
            config (Dict[str, Any]): Configuration dictionary with settings for each detector.
        """
        # Initialize the list to store individual detection engine instances.
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
        # Initialize the detector types dictionary.
        self.detector_types = {}

        # Check if configuration enables the Presidio detector.
        if config.get("use_presidio", True):
            # Retrieve the Presidio detector instance from the initialization service.
            presidio = initialization_service.get_presidio_detector()
            # If the Presidio detector instance is available...
            if presidio:
                # Append the Presidio detector to the detectors list.
                self.detectors.append(presidio)
                # Log that the Presidio detector has been successfully initialized.
                log_info("[INIT] Presidio Detector Initialized Successfully")
        # Check if configuration enables the Gemini detector.
        if config.get("use_gemini", True):
            # Retrieve the Gemini detector instance.
            gemini = initialization_service.get_gemini_detector()
            # If the Gemini detector instance is available...
            if gemini:
                # Append the Gemini detector to the detectors list.
                self.detectors.append(gemini)
                # Log successful initialization of the Gemini detector.
                log_info("[INIT] Gemini Detector Initialized Successfully")
            else:
                # Log a warning if the Gemini detector could not be initialized.
                log_warning("[INIT] Gemini Detector Initialization Failed")
        # Check if configuration enables the GLiNER detector.
        if config.get("use_gliner", True):
            # Retrieve the list of entities to detect from configuration.
            entity_list = config.get("entities", [])
            # Retrieve the GLiNER detector instance with the given entity list.
            gliner = initialization_service.get_gliner_detector(entity_list)
            # If the GLiNER detector instance is available...
            if gliner:
                # Append the GLiNER detector to the detectors list.
                self.detectors.append(gliner)
                # Log successful initialization of the GLiNER detector.
                log_info("[INIT] GLiNER Detector Initialized Successfully")
            else:
                # Log a warning if GLiNER detector initialization failed.
                log_warning("[INIT] GLiNER Detector Initialization Failed")
        # Check if configuration enables the HIDEME detector.
        if config.get("use_hideme", True):
            # Retrieve the list of entities to detect from configuration.
            entity_list = config.get("entities", [])
            # Retrieve the HIDEME detector instance with the given entity list.
            hideme = initialization_service.get_hideme_detector(entity_list)
            # If the HIDEME detector instance is available...
            if hideme:
                # Append the HIDEME detector to the detectors list.
                self.detectors.append(hideme)
                # Log successful initialization of the HIDEME detector.
                log_info("[INIT] HIDEME Detector Initialized Successfully")
            else:
                # Log a warning if HIDEME detector initialization failed.
                log_warning("[INIT] HIDEME Detector Initialization Failed")

    async def _get_detector_lock(self) -> AsyncTimeoutLock:
        """
        Lazily create and return the AsyncTimeoutLock to avoid event-loop conflicts.

        This lock is used to safely update usage metrics.

        Returns:
            AsyncTimeoutLock: The detector lock.
        """
        # Check if the detector lock has not been created yet.
        if self._detector_lock is None:
            try:
                # Create a new AsyncTimeoutLock with a medium priority and a 30-second timeout.
                self._detector_lock = AsyncTimeoutLock(
                    name="hybrid_detector_lock",
                    priority=LockPriority.MEDIUM,
                    timeout=30.0
                )
            except Exception as exc:
                # Log any error during detector lock creation.
                SecurityAwareErrorHandler.log_processing_error(exc, "detector_lock_init", "")
        # Return the detector lock instance.
        return self._detector_lock

    async def detect_sensitive_data_async(
            self,
            extracted_data: Dict[str, Any],
            requested_entities: Optional[List[str]] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Asynchronously detect sensitive entities using multiple detection engines.

        The method minimizes input data, increases usage metrics, concurrently runs the detection engines,
        processes their results, and returns an aggregated list of entities alongside the redaction mapping.

        Args:
            extracted_data (Dict[str, Any]): Dictionary containing the input text and bounding box information.
            requested_entities (Optional[List[str]]): List of entity types to detect; if not provided, all configured types are processed.

        Returns:
            Tuple[List[Dict[str, Any]], Dict[str, Any]]: A tuple containing the list of detected entities and the redaction mapping.
        """
        # Record the start time for performance tracking.
        start_time = time.time()
        try:
            # Minimize the input data for GDPR compliance.
            minimized_data = minimize_extracted_data(extracted_data)
            # Check if there are any configured detectors.
            if not self._prepare_data_and_check_detectors():
                # Return empty results if no detectors are available.
                return [], {"pages": []}
            # Increment usage metrics using the current start time.
            await self._increment_usage_metrics(start_time)
            # Run each configured detector concurrently.
            parallel_results = await self._run_all_detectors_in_parallel(minimized_data, requested_entities)
            # Process the parallel results to aggregate entities and mappings.
            combined_entities, all_redaction_mappings, success_count, failure_count = \
                self._process_detection_results(parallel_results)
            # Check if none of the detectors succeeded.
            if success_count == 0:
                # Log an error if all detection engines have failed.
                log_error("[ERROR] All detection engines failed")
                # Return empty result sets.
                return [], {"pages": []}
            # Finalize the detection by merging mappings and updating metrics.
            final_entities, final_mapping = await self._finalize_detection(
                combined_entities, all_redaction_mappings, extracted_data,
                requested_entities, start_time, success_count, failure_count
            )
            # Return the aggregated list of detected entities and the redaction mapping.
            return final_entities, final_mapping
        except Exception as exc:
            # Log any unexpected exception during detection.
            log_error(f"[ERROR] Unexpected error in hybrid detection: {str(exc)}")
            # Return empty results if an exception occurs.
            return [], {"pages": []}

    def _prepare_data_and_check_detectors(self) -> bool:
        """
        Check if at least one detection engine is configured.

        Returns:
            bool: True if detectors exist; False otherwise.
        """
        # Verify whether the detectors list is empty.
        if not self.detectors:
            # Log a warning if no detectors are available.
            log_warning("[WARNING] No detection engines available in hybrid detector")
            # Return False indicating insufficient detectors.
            return False
        # Return True indicating detectors are available.
        return True

    async def _increment_usage_metrics(self, start_time: float) -> None:
        """
        Update usage metrics by incrementing the call counter and updating the last used timestamp safely.

        Args:
            start_time (float): The time at which the detection operation started.
        """
        # Retrieve (or create) the detector lock.
        detector_lock = await self._get_detector_lock()
        # Acquire the lock using a 5-second timeout.
        async with detector_lock.acquire_timeout(timeout=5.0) as acquired:
            # Check if the lock acquisition was successful.
            if acquired:
                # Increment the total calls counter.
                self._total_calls += 1
                # Update the last used time with the provided start time.
                self._last_used = start_time

    async def _run_all_detectors_in_parallel(
            self,
            minimized_data: Dict[str, Any],
            requested_entities: Optional[List[str]]
    ) -> List[Dict[str, Any]]:
        """
        Run detection tasks for all configured engines concurrently.

        Args:
            minimized_data (Dict[str, Any]): The preprocessed and GDPR-compliant input data.
            requested_entities (Optional[List[str]]): List of entity types to detect.

        Returns:
            List[Dict[str, Any]]: The list of results from each detection engine.
        """
        # Create a list of asyncio tasks for each detector.
        tasks = [
            asyncio.create_task(
                self._process_single_detector(det, minimized_data, requested_entities)
            )
            for det in self.detectors
        ]
        # Await the completion of all detector tasks concurrently.
        return await self._execute_detector_tasks(tasks)

    @staticmethod
    async def _execute_detector_tasks(tasks: List[asyncio.Future]) -> List[Dict[str, Any]]:
        """
        Execute a list of detection tasks concurrently with a global timeout.

        Args:
            tasks (List[asyncio.Future]): The list of asyncio tasks to execute.

        Returns:
            List[Dict[str, Any]]: The list of results from each task or an empty list in case of a timeout.
        """
        try:
            # Use asyncio.wait_for to set a global timeout of 600 seconds for task completion.
            return await asyncio.wait_for(asyncio.gather(*tasks), timeout=600.0)
        except asyncio.TimeoutError:
            # Log an error message if a global timeout occurs.
            log_error("[ERROR] Global timeout for all detection engines")
            # Return an empty list of results if timeout is encountered.
            return []

    @staticmethod
    async def _process_single_detector(
            engine_detector: EntityDetector,
            minimized_data: Dict[str, Any],
            requested_entities: Optional[List[str]]
    ) -> Dict[str, Any]:
        """
        Process detection for a single engine with timeout and error handling.

        Args:
            engine_detector (EntityDetector): The detection engine instance.
            minimized_data (Dict[str, Any]): The preprocessed input data.
            requested_entities (Optional[List[str]]): List of entity types to detect.

        Returns:
            Dict[str, Any]: A dictionary containing the result details (success flag, engine name, detected entities, mapping, and execution time).
        """
        # Get the class name of the engine.
        engine_name = type(engine_detector).__name__
        # Record the start time for this engine.
        engine_start_time = time.time()
        try:
            # Check if the engine supports asynchronous detection.
            if hasattr(engine_detector, "detect_sensitive_data_async"):
                # Run the detection asynchronously.
                result_tuple = await HybridEntityDetector._run_async_detector(engine_detector, minimized_data,
                                                                              requested_entities)
            else:
                # Run the detection synchronously in a separate thread.
                result_tuple = await HybridEntityDetector._run_sync_detector(engine_detector, minimized_data,
                                                                             requested_entities)
            # Verify that the result is a tuple with exactly two elements.
            if not isinstance(result_tuple, tuple) or len(result_tuple) != 2:
                # Return a standardized failure dictionary if the format is invalid.
                return HybridEntityDetector._engine_failure_dict(engine_name,
                                                                 f"Invalid result format: {type(result_tuple)}",
                                                                 engine_start_time)
            # Unpack the tuple into found entities and mapping.
            found_entities, found_mapping = result_tuple
            # Check whether the found entities is a list.
            if not isinstance(found_entities, list):
                # Log a warning if the entities result is not in list format.
                log_warning(f"[WARNING] Entities result from {engine_name} is not a list")
                # Default to an empty list.
                found_entities = []
            # Check whether the redaction mapping is a dictionary.
            if not isinstance(found_mapping, dict):
                # Log a warning if the mapping result is not a dict.
                log_warning(f"[WARNING] Redaction mapping from {engine_name} is not a dict")
                # Default to a structure with an empty pages list.
                found_mapping = {"pages": []}
            # Calculate the elapsed time for this engine.
            engine_time = time.time() - engine_start_time
            # Log the detection performance for this engine.
            log_info(f"[OK] {engine_name} found {len(found_entities)} entities in {engine_time:.2f}s")
            # Record processing metrics for auditing purposes.
            record_keeper.record_processing(
                operation_type=f"hybrid_detection_{engine_name.lower()}",
                document_type="document",
                entity_types_processed=requested_entities or [],
                processing_time=engine_time,
                entity_count=len(found_entities),
                success=True
            )
            # Return a dictionary containing successful detection details.
            return {
                "success": True,
                "engine": engine_name,
                "entities": found_entities,
                "mapping": found_mapping,
                "time": engine_time
            }
        except Exception as detect_exc:
            # Log any exception occurring during engine detection.
            SecurityAwareErrorHandler.log_processing_error(detect_exc, f"hybrid_{engine_name.lower()}_detection",
                                                           "document")
            # Return a standardized failure result for this engine.
            return HybridEntityDetector._engine_failure_dict(engine_name, str(detect_exc), engine_start_time)

    @staticmethod
    async def _run_async_detector(
            detector: EntityDetector,
            minimized_data: Dict[str, Any],
            requested_entities: Optional[List[str]]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Run an asynchronous detection engine with a timeout.

        Args:
            detector (EntityDetector): The asynchronous detection engine instance.
            minimized_data (Dict[str, Any]): The preprocessed input data.
            requested_entities (Optional[List[str]]): List of requested entity types.

        Returns:
            Tuple[List[Dict[str, Any]], Dict[str, Any]]: A tuple containing the list of detected entities and the redaction mapping.
        """
        # Get the class name of the detector.
        engine_name = type(detector).__name__
        try:
            # Call the detector's asynchronous detection method with a timeout of 600 seconds.
            return await asyncio.wait_for(
                cast(Any, detector).detect_sensitive_data_async(minimized_data, requested_entities),
                timeout=600.0
            )
        except asyncio.TimeoutError:
            # Log a warning if the asynchronous detector times out.
            log_warning(f"[WARNING] Timeout in {engine_name} detector")
            # Return empty results for timeout case.
            return [], {"pages": []}

    @staticmethod
    async def _run_sync_detector(
            detector: EntityDetector,
            minimized_data: Dict[str, Any],
            requested_entities: Optional[List[str]]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Execute a synchronous detector in a separate thread.

        Args:
            detector (EntityDetector): The synchronous detection engine instance.
            minimized_data (Dict[str, Any]): The preprocessed input data.
            requested_entities (Optional[List[str]]): List of requested entity types.

        Returns:
            Tuple[List[Dict[str, Any]], Dict[str, Any]]: A tuple containing the list of detected entities and the redaction mapping.
        """
        # Get the class name of the detector.
        engine_name = type(detector).__name__
        try:
            # Run the synchronous detection method in a separate thread.
            return await asyncio.to_thread(
                detector.detect_sensitive_data,
                minimized_data,
                requested_entities
            )
        except asyncio.TimeoutError:
            # Log a warning if the synchronous detection method times out.
            log_warning(f"[WARNING] Timeout in {engine_name} detector (sync mode)")
            # Return empty results for timeout.
            return [], {"pages": []}

    @staticmethod
    def _engine_failure_dict(engine_name: str, error_msg: str, start_time: float) -> Dict[str, Any]:
        """
        Create a standardized failure dictionary for a detection engine.

        Args:
            engine_name (str): Name of the detection engine.
            error_msg (str): Error message that occurred.
            start_time (float): The start time of the engine processing.

        Returns:
            Dict[str, Any]: A dictionary with failure details including error message and time taken.
        """
        # Calculate the elapsed time since the start of processing.
        elapsed_time = time.time() - start_time
        # Return a dictionary encapsulating the failure information.
        return {
            "success": False,
            "engine": engine_name,
            "error": error_msg,
            "time": elapsed_time
        }

    @staticmethod
    def _process_detection_results(
            parallel_results: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int, int]:
        """
        Process and aggregate results from all detection engines.

        Args:
            parallel_results (List[Dict[str, Any]]): List of result dictionaries from individual engines.

        Returns:
            Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int, int]:
                - Aggregated list of detected entities.
                - Aggregated list of redaction mappings.
                - Count of successful detection engines.
                - Count of failed detection engines.
        """
        # Initialize an empty list to store all detected entities.
        all_entities: List[Dict[str, Any]] = []
        # Initialize an empty list to store all redaction mappings.
        all_redaction_mappings: List[Dict[str, Any]] = []
        # Initialize the counter for successful detection engines.
        success_count = 0
        # Initialize the counter for failed detection engines.
        failure_count = 0
        # Iterate over each result from the detection engines.
        for engine_result in parallel_results:
            # Check if the engine reported a success.
            if engine_result.get("success"):
                # Retrieve the list of detected entities.
                found_entities = engine_result.get("entities", [])
                # Retrieve the redaction mapping.
                found_mapping = engine_result.get("mapping", {})
                # Log a secure operation with the detection details.
                log_sensitive_operation(
                    f"{engine_result['engine']} Detection",
                    len(found_entities),
                    engine_result.get("time", 0.0),
                    engine=engine_result["engine"]
                )
                # Append the entities from this engine to the aggregated list.
                all_entities.extend(found_entities)
                # Append the mapping from this engine to the aggregated mapping list.
                all_redaction_mappings.append(found_mapping)
                # Increment the successful engine counter.
                success_count += 1
            else:
                # Increment the failed engine counter if the engine did not report success.
                failure_count += 1
        # Return the aggregated entities, mappings, and the counts of successes and failures.
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
        Finalize the detection results by merging mappings, deduplicating entities, and updating usage metrics.

        Args:
            combined_entities (List[Dict[str, Any]]): Aggregated list of entities from all engines.
            all_redaction_mappings (List[Dict[str, Any]]): List of redaction mappings from all engines.
            original_data (Dict[str, Any]): The original input data.
            requested_entities (Optional[List[str]]): List of requested entity types.
            start_time (float): The start time of the overall detection process.
            success_count (int): Number of engines that succeeded.
            failure_count (int): Number of engines that failed.

        Returns:
            Tuple[List[Dict[str, Any]], Dict[str, Any]]: A tuple containing the deduplicated entities and the merged redaction mapping.
        """
        # Merge the individual redaction mappings into one unified mapping.
        merged_mapping = self._merge_redaction_mappings(all_redaction_mappings)
        # Ensure the merged mapping contains a pages list.
        if not merged_mapping.get("pages"):
            merged_mapping["pages"] = []
        # Deduplicate the aggregated list of detected entities.
        final_entities = deduplicate_entities(combined_entities)
        # Compute the total processing time.
        total_time = time.time() - start_time
        # Acquire the detector lock to safely update the overall usage metrics.
        detector_lock = await self._get_detector_lock()
        async with detector_lock.acquire_timeout(timeout=5.0) as acquired:
            # If the lock was successfully acquired...
            if acquired:
                # Update the total count of detected entities.
                self._total_entities_detected += len(final_entities)
        # Record overall processing details for auditing and compliance purposes.
        record_keeper.record_processing(
            operation_type="hybrid_detection",
            document_type="document",
            entity_types_processed=requested_entities or [],
            processing_time=total_time,
            file_count=1,
            entity_count=len(final_entities),
            success=(success_count > 0)
        )
        # Log performance details for the hybrid detection operation.
        log_info(f"[PERF] Hybrid detection completed in {total_time:.2f}s "
                 f"with {success_count} successful engines and {failure_count} failures")
        log_info(f"[PERF] Total {len(final_entities)} entities detected "
                 f"across {len(original_data.get('pages', []))} pages")
        # Log a sensitive operation with overall detection metrics.
        log_sensitive_operation(
            "Hybrid Detection",
            len(final_entities),
            total_time,
            engines_used=success_count,
            engines_failed=failure_count
        )
        # Return the final deduplicated entities and the merged redaction mapping.
        return final_entities, merged_mapping

    @staticmethod
    def _merge_redaction_mappings(mappings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Merge multiple redaction mappings into a single unified mapping.

        Args:
            mappings (List[Dict[str, Any]]): A list of redaction mapping dictionaries.

        Returns:
            Dict[str, Any]: A merged redaction mapping dictionary with aggregated page information.
        """
        # Check if the mappings list is empty.
        if not mappings:
            # Return a default mapping if no mappings are provided.
            return {"pages": []}
        # Initialize the merged result dictionary with an empty pages list.
        merged_result = {"pages": []}
        # Create a dictionary to hold pages' aggregated details.
        pages_dict = {}
        # Iterate over each single mapping in the mappings list.
        for single_mapping in mappings:
            # Validate that the current mapping is a dictionary and contains a "pages" key.
            if not isinstance(single_mapping, dict) or "pages" not in single_mapping:
                # Skip the mapping if it does not meet the required format.
                continue
            # Iterate over each page information within the mapping.
            for page_info in single_mapping.get("pages", []):
                # Retrieve the page number from the current page info.
                page_num = page_info.get("page")
                # Skip the page if the page number is missing.
                if page_num is None:
                    continue
                # Initialize a new entry in pages_dict if this page number does not exist yet.
                if page_num not in pages_dict:
                    pages_dict[page_num] = {"page": page_num, "sensitive": []}
                # Aggregate the sensitive items from the current page into pages_dict.
                pages_dict[page_num]["sensitive"].extend(page_info.get("sensitive", []))
        # Convert the aggregated pages information into a sorted list.
        for pg_num in sorted(pages_dict.keys()):
            # Append each aggregated page info to the merged result.
            merged_result["pages"].append(pages_dict[pg_num])
        # Return the merged redaction mapping.
        return merged_result

    def detect_sensitive_data(
            self,
            extracted_data: Dict[str, Any],
            requested_entities: Optional[List[str]] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Synchronous wrapper for detecting sensitive entities using multiple detection engines.

        This method sets up a new event loop to run the asynchronous detection method and returns the final results.

        Args:
            extracted_data (Dict[str, Any]): Dictionary containing text and bounding box information.
            requested_entities (Optional[List[str]]): List of entity types to detect.

        Returns:
            Tuple[List[Dict[str, Any]], Dict[str, Any]]: A tuple with detected entities and the redaction mapping.
        """
        try:
            # Preprocess and minimize input data for compliance.
            minimized_data = minimize_extracted_data(extracted_data)
            # Create a new asyncio event loop for synchronous execution.
            loop = asyncio.new_event_loop()
            # Set the newly created event loop as the current event loop.
            asyncio.set_event_loop(loop)
            try:
                # Define an asynchronous helper function that runs detection with a 600-second timeout.
                async def run_with_timeout():
                    # Await and return the asynchronous detection result.
                    return await asyncio.wait_for(
                        self.detect_sensitive_data_async(minimized_data, requested_entities),
                        timeout=600.0
                    )

                # Run the asynchronous detection method until complete and capture its result.
                result = loop.run_until_complete(run_with_timeout())
                # Return the detection result.
                return result
            finally:
                # Ensure that the event loop is properly closed.
                loop.close()
        except asyncio.TimeoutError:
            # Log an error message if a timeout occurs in the synchronous wrapper.
            log_error("[ERROR] Global timeout in hybrid entity detection (sync wrapper)")
            # Return empty detection results on timeout.
            return [], {"pages": []}
        except RuntimeError as exc:
            # Handle runtime errors related to interpreter shutdown gracefully.
            if "cannot schedule new futures after interpreter shutdown" in str(exc):
                # Log a warning regarding the shutdown.
                log_warning(f"[WARNING] Shutdown in progress, returning empty results: {exc}")
                # Return empty results due to shut down.
                return [], {"pages": []}
            # Log any other runtime errors during processing.
            SecurityAwareErrorHandler.log_processing_error(exc, "hybrid_detection_runtime", "document")
            # Return empty detection results on runtime error.
            return [], {"pages": []}
        except Exception as exc:
            # Log any unexpected exceptions that occur.
            SecurityAwareErrorHandler.log_processing_error(exc, "hybrid_detection", "document")
            # Return empty results if an exception is raised.
            return [], {"pages": []}

    async def get_status(self) -> Dict[str, Any]:
        """
        Retrieve the current status of the hybrid entity detector.

        The status includes initialization and usage metrics, the list of configured detectors, and other operational details.

        Returns:
            Dict[str, Any]: A dictionary containing the current status information of the detector.
        """

        # Define an asynchronous helper function to retrieve status details.
        async def get_status_async() -> Dict[str, Any]:
            # Acquire the detector lock to safely access internal status.
            detector_lock = await self._get_detector_lock()
            async with detector_lock.acquire_timeout(timeout=1.0):
                # Return a dictionary containing key status information.
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
            # Create a new asyncio event loop for running the status function.
            loop = asyncio.new_event_loop()
            # Set the newly created event loop as the current event loop.
            asyncio.set_event_loop(loop)
            try:
                # Run the asynchronous status helper with a timeout of 2 seconds.
                result = loop.run_until_complete(asyncio.wait_for(get_status_async(), timeout=2.0))
                # Return the status information.
                return result
            finally:
                # Ensure that the event loop is closed after execution.
                loop.close()
        except asyncio.TimeoutError:
            # Log a warning if there is a timeout while fetching the status.
            log_warning("[WARNING] Timeout while fetching hybrid detector status")
            # Return a partial status dictionary indicating a timeout occurred.
            return {
                "initialized": True,
                "initialization_time": self._initialization_time,
                "detectors": [type(det).__name__ for det in self.detectors],
                "detector_count": len(self.detectors),
                "status_timeout": True
            }
        except RuntimeError as exc:
            # Log a warning if a runtime error occurs while accessing the event loop.
            log_warning(f"[WARNING] Event loop runtime issue in get_status: {exc}")
            # Return a partial status dictionary with the runtime error details.
            return {
                "initialized": True,
                "initialization_time": self._initialization_time,
                "detectors": [type(det).__name__ for det in self.detectors],
                "detector_count": len(self.detectors),
                "runtime_error": str(exc)
            }
        except Exception as exc:
            # Log an error for any unexpected exceptions during status retrieval.
            log_error(f"[ERROR] Unexpected error in get_status: {exc}")
            # Return a status dictionary indicating a failure to acquire the lock.
            return {
                "initialized": True,
                "initialization_time": self._initialization_time,
                "detectors": [type(det).__name__ for det in self.detectors],
                "detector_count": len(self.detectors),
                "lock_acquisition_failed": True,
                "error": str(exc)
            }
