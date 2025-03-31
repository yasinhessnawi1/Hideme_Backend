import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple, cast

from backend.app.domain.interfaces import EntityDetector
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.system_utils.synchronization_utils import AsyncTimeoutLock, LockPriority
from backend.app.utils.validation.data_minimization import minimize_extracted_data


class HybridEntityDetector(EntityDetector):
    """
    Enhanced hybrid entity detector that combines results from multiple engines.

    This detector runs all configured detection engines and merges their results,
    with comprehensive GDPR compliance, data minimization, and enhanced error
    handling features.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the hybrid detector with configuration.

        Args:
            config: Configuration dictionary with settings for each detector.
        """
        self.detectors: List[EntityDetector] = []
        self.config = config
        self._initialization_time = time.time()
        self._last_used = self._initialization_time
        self._total_calls = 0
        self._total_entities_detected = 0

        # Use lazy lock creation instead of creating it here.
        self._detector_lock: Optional[AsyncTimeoutLock] = None

        if config.get("use_presidio", True):
            presidio = initialization_service.get_presidio_detector()
            if presidio:
                self.detectors.append(presidio)
                log_info("[INIT] Presidio Detector Initialized Successfully")

        if config.get("use_gemini", True):
            gemini = initialization_service.get_gemini_detector()
            if gemini:
                self.detectors.append(gemini)
                log_info("[INIT] Gemini Detector Initialized Successfully")
            else:
                log_warning("[INIT] Gemini Detector Initialization Failed")

        if config.get("use_gliner", True):
            entity_list = config.get("entities", [])
            gliner = initialization_service.get_gliner_detector(entity_list)
            if gliner:
                self.detectors.append(gliner)
                log_info("[INIT] GLiNER Detector Initialized Successfully")
            else:
                log_warning("[INIT] GLiNER Detector Initialization Failed")

    async def _get_detector_lock(self) -> AsyncTimeoutLock:
        """
        Lazily create and return the AsyncTimeoutLock to avoid event-loop conflicts.
        """
        if self._detector_lock is None:
            self._detector_lock = AsyncTimeoutLock(
                name="hybrid_detector_lock",
                priority=LockPriority.MEDIUM,
                timeout=30.0
            )
        return self._detector_lock

    async def detect_sensitive_data_async(
        self,
        extracted_data: Dict[str, Any],
        requested_entities: Optional[List[str]] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Detect sensitive entities using multiple detection engines asynchronously
        with concurrent processing, enhanced GDPR compliance, and error handling.

        Refactored into smaller helper methods to reduce complexity:
          1. _prepare_data_and_check_detectors
          2. _increment_usage_metrics
          3. _run_all_detectors_in_parallel
          4. _process_detection_results
          5. _finalize_detection

        Args:
            extracted_data: Dictionary containing text and bounding box information.
            requested_entities: List of entity types to detect.

        Returns:
            Tuple of (results_json, redaction_mapping).
        """
        start_time = time.time()

        try:
            # 1. Prepare data and check if we have any detectors.
            minimized_data = minimize_extracted_data(extracted_data)
            if not self._prepare_data_and_check_detectors():
                return [], {"pages": []}

            # 2. Increment usage metrics.
            await self._increment_usage_metrics(start_time)

            # 3. Run all detectors in parallel.
            parallel_results = await self._run_all_detectors_in_parallel(
                minimized_data, requested_entities
            )

            # 4. Process parallel results.
            combined_entities, all_redaction_mappings, success_count, failure_count = \
                self._process_detection_results(parallel_results)

            if success_count == 0:
                log_error("[ERROR] All detection engines failed")
                return [], {"pages": []}

            # 5. Finalize detection.
            final_entities, final_mapping = await self._finalize_detection(
                combined_entities, all_redaction_mappings, extracted_data,
                requested_entities, start_time, success_count, failure_count
            )

            return final_entities, final_mapping

        except Exception as exc:
            log_error(f"[ERROR] Unexpected error in hybrid detection: {str(exc)}")
            return [], {"pages": []}

    def _prepare_data_and_check_detectors(self) -> bool:
        """
        Step 1: Ensure we have at least one configured detector.

        Returns:
            True if detectors exist, False otherwise.
        """
        if not self.detectors:
            log_warning("[WARNING] No detection engines available in hybrid detector")
            return False
        return True

    async def _increment_usage_metrics(self, start_time: float) -> None:
        """
        Step 2: Acquire the lock to update usage metrics.
        """
        detector_lock = await self._get_detector_lock()
        async with detector_lock.acquire_timeout(timeout=5.0) as acquired:
            if acquired:
                self._total_calls += 1
                self._last_used = start_time

    async def _run_all_detectors_in_parallel(
        self,
        minimized_data: Dict[str, Any],
        requested_entities: Optional[List[str]]
    ) -> List[Dict[str, Any]]:
        """
        Step 3: Create and run tasks for each configured detector in parallel.

        Returns:
            List of dictionaries with detection results.
        """
        # Wrap each coroutine in a Task.
        tasks = [
            asyncio.create_task(
                self._process_single_detector(det, minimized_data, requested_entities)
            )
            for det in self.detectors
        ]
        return await self._execute_detector_tasks(tasks)

    @staticmethod
    async def _execute_detector_tasks(tasks: List[asyncio.Future]) -> List[Dict[str, Any]]:
        """
        Helper to run a list of detection tasks in parallel with a global timeout.

        Args:
            tasks: List of tasks to be awaited.

        Returns:
            List of results, or an empty list if timed out.
        """
        try:
            return await asyncio.wait_for(asyncio.gather(*tasks), timeout=600.0)
        except asyncio.TimeoutError:
            log_error("[ERROR] Global timeout for all detection engines")
            return []

    async def _process_single_detector(
        self,
        engine_detector: EntityDetector,
        minimized_data: Dict[str, Any],
        requested_entities: Optional[List[str]]
    ) -> Dict[str, Any]:
        """
        Process a single detection engine with timeout and error handling.

        Args:
            engine_detector: The detection engine instance.
            minimized_data: Pre-processed data.
            requested_entities: List of requested entity types.

        Returns:
            A dictionary with the detection result.
        """
        engine_name = type(engine_detector).__name__
        engine_start_time = time.time()

        try:
            if hasattr(engine_detector, "detect_sensitive_data_async"):
                result_tuple = await self._run_async_detector(engine_detector, minimized_data, requested_entities)
            else:
                result_tuple = await self._run_sync_detector(engine_detector, minimized_data, requested_entities)

            if not isinstance(result_tuple, tuple) or len(result_tuple) != 2:
                return self._engine_failure_dict(
                    engine_name,
                    f"Invalid result format: {type(result_tuple)}",
                    engine_start_time
                )

            found_entities, found_mapping = result_tuple
            if not isinstance(found_entities, list):
                log_warning(f"[WARNING] Entities result from {engine_name} is not a list")
                found_entities = []
            if not isinstance(found_mapping, dict):
                log_warning(f"[WARNING] Redaction mapping from {engine_name} is not a dict")
                found_mapping = {"pages": []}

            engine_time = time.time() - engine_start_time
            log_info(f"[OK] {engine_name} found {len(found_entities)} entities in {engine_time:.2f}s")
            record_keeper.record_processing(
                operation_type=f"hybrid_detection_{engine_name.lower()}",
                document_type="document",
                entity_types_processed=requested_entities or [],
                processing_time=engine_time,
                entity_count=len(found_entities),
                success=True
            )
            return {
                "success": True,
                "engine": engine_name,
                "entities": found_entities,
                "mapping": found_mapping,
                "time": engine_time
            }
        except Exception as detect_exc:
            SecurityAwareErrorHandler.log_processing_error(
                detect_exc, f"hybrid_{engine_name.lower()}_detection", "document"
            )
            return self._engine_failure_dict(engine_name, str(detect_exc), engine_start_time)

    @staticmethod
    async def _run_async_detector(
        detector: EntityDetector,
        minimized_data: Dict[str, Any],
        requested_entities: Optional[List[str]]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Run an async detector with a 10-minute timeout.

        Args:
            detector: The detection engine instance with an async method.
            minimized_data: Pre-processed data.
            requested_entities: List of requested entity types.

        Returns:
            A tuple (entities, mapping).
        """
        engine_name = type(detector).__name__
        try:
            # Use cast to bypass type checking for the async method.
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
        Run a sync detector in a thread.

        Args:
            detector: The detection engine instance with a sync method.
            minimized_data: Pre-processed data.
            requested_entities: List of requested entity types.

        Returns:
            A tuple (entities, mapping).
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
            error_msg: Error message.
            start_time: Start time for processing.

        Returns:
            A dictionary indicating failure.
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
        Process parallel results from each detector, collecting entities, mappings, and counting successes/failures.

        Returns:
            A tuple: (all_entities, all_redaction_mappings, success_count, failure_count)
        """
        all_entities: List[Dict[str, Any]] = []
        all_redaction_mappings: List[Dict[str, Any]] = []
        success_count = 0
        failure_count = 0

        for engine_result in parallel_results:
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
        Merge redaction mappings, deduplicate entities, update metrics, record GDPR,
        and log performance before returning final results.

        Returns:
            A tuple (final_entities, final_mapping).
        """
        merged_mapping = self._merge_redaction_mappings(all_redaction_mappings)
        if not merged_mapping.get("pages"):
            merged_mapping["pages"] = []

        from backend.app.utils.validation.sanitize_utils import deduplicate_entities
        final_entities = deduplicate_entities(combined_entities)
        total_time = time.time() - start_time

        detector_lock = await self._get_detector_lock()
        async with detector_lock.acquire_timeout(timeout=5.0) as acquired:
            if acquired:
                self._total_entities_detected += len(final_entities)

        record_keeper.record_processing(
            operation_type="hybrid_detection",
            document_type="document",
            entity_types_processed=requested_entities or [],
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
        Merge multiple redaction mappings into a single mapping.

        Args:
            mappings: List of redaction mappings.

        Returns:
            Merged redaction mapping.
        """
        if not mappings:
            return {"pages": []}

        merged_result = {"pages": []}
        pages_dict = {}

        for single_mapping in mappings:
            if not isinstance(single_mapping, dict) or "pages" not in single_mapping:
                continue

            for page_info in single_mapping.get("pages", []):
                page_num = page_info.get("page")
                if page_num is None:
                    continue

                if page_num not in pages_dict:
                    pages_dict[page_num] = {"page": page_num, "sensitive": []}

                pages_dict[page_num]["sensitive"].extend(page_info.get("sensitive", []))

        for pg_num in sorted(pages_dict.keys()):
            merged_result["pages"].append(pages_dict[pg_num])

        return merged_result

    def detect_sensitive_data(
        self,
        extracted_data: Dict[str, Any],
        requested_entities: Optional[List[str]] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Detect sensitive entities using multiple detection engines (sync wrapper).

        Args:
            extracted_data: Dictionary containing text and bounding box information.
            requested_entities: List of entity types to detect.

        Returns:
            Tuple of (results_json, redaction_mapping).
        """
        try:
            minimized_data = minimize_extracted_data(extracted_data)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                async def run_with_timeout():
                    return await asyncio.wait_for(
                        self.detect_sensitive_data_async(minimized_data, requested_entities),
                        timeout=600.0
                    )
                return loop.run_until_complete(run_with_timeout())
            finally:
                loop.close()
        except asyncio.TimeoutError:
            log_error("[ERROR] Global timeout in hybrid entity detection (sync wrapper)")
            return [], {"pages": []}
        except RuntimeError as exc:
            if "cannot schedule new futures after interpreter shutdown" in str(exc):
                log_warning(f"[WARNING] Shutdown in progress, returning empty results: {exc}")
                return [], {"pages": []}
            SecurityAwareErrorHandler.log_processing_error(exc, "hybrid_detection_runtime", "document")
            return [], {"pages": []}
        except Exception as exc:
            SecurityAwareErrorHandler.log_processing_error(exc, "hybrid_detection", "document")
            return [], {"pages": []}

    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the hybrid entity detector.

        Returns:
            Dictionary with status information.
        """
        async def get_status_async() -> Dict[str, Any]:
            detector_lock = await self._get_detector_lock()
            async with detector_lock.acquire_timeout(timeout=1.0):
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