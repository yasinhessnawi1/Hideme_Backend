"""
hybrid entity detection implementation with improved GDPR compliance features.

This module provides a dedicated implementation of the HybridEntityDetector
that combines multiple detection engines with comprehensive GDPR compliance,
data minimization, and enhanced error handling.
"""
import asyncio
import time
from typing import Dict, Any, List, Optional, Tuple

from backend.app.domain.interfaces import EntityDetector
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.data_minimization import minimize_extracted_data
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.helpers import EntityUtils
from backend.app.utils.logger import log_info, log_warning, log_error
from backend.app.utils.processing_records import record_keeper
from backend.app.utils.secure_logging import log_sensitive_operation
from backend.app.utils.synchronization_utils import AsyncTimeoutLock, LockPriority


class HybridEntityDetector(EntityDetector):
    """
    Enhanced hybrid entity detector that combines results from multiple engines.

    This detector runs all configured detection engines and merges their results,
    with comprehensive GDPR compliance, data minimization, and enhanced error
    handling features.

    Features:
    - Combines results from multiple detection engines
    - Applies data minimization principles
    - Maintains GDPR compliance records
    - Provides enhanced security features
    - Robust error handling
    - Improved synchronization to prevent deadlocks
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the hybrid detector with configuration.

        Args:
            config: Configuration dictionary with settings for each detector
        """
        self.detectors = []
        self.config = config
        self._initialization_time = time.time()
        self._last_used = self._initialization_time
        self._total_calls = 0
        self._total_entities_detected = 0

        # Add AsyncTimeoutLock with appropriate priority
        self._detector_lock = AsyncTimeoutLock(
            name="hybrid_detector_lock",
            priority=LockPriority.MEDIUM,
            timeout=30.0
        )

        # If pre-created detectors are provided, use them directly
        if "detectors" in config and isinstance(config["detectors"], list):
            self.detectors = config["detectors"]
            detector_types = [type(d).__name__ for d in self.detectors]
            log_info(f"[HYBRID] Using pre-created detectors: {detector_types}")
            return

        # Create detectors based on configuration, using cached instances from initialization service
        if config.get("use_presidio", True):
            # Get cached Presidio detector
            detector = initialization_service.get_presidio_detector()
            self.detectors.append(detector)

        if config.get("use_gemini", False):
            # Get cached Gemini detector
            detector = initialization_service.get_gemini_detector()
            self.detectors.append(detector)

        if config.get("use_gliner", False):
            # For GLiNER, get the specific model based on requested entities
            entity_list = config.get("entities", [])

            # Get cached GLiNER detector
            detector = initialization_service.get_gliner_detector(entity_list)
            self.detectors.append(detector)

        if not self.detectors:
            # Default to Presidio if no detectors specified
            detector = initialization_service.get_presidio_detector()
            self.detectors.append(detector)

        detector_types = [type(d).__name__ for d in self.detectors]
        log_info(f"[OK] Created hybrid entity detector with {len(self.detectors)} detection engines: {detector_types}")

    # In hybrid.py, update the detect_sensitive_data_async method to properly handle async operations
    # This is the key fix for "object HybridEntityDetector can't be used in 'await' expression"

    async def detect_sensitive_data_async(
            self,
            extracted_data: Dict[str, Any],
            requested_entities: Optional[List[str]] = None
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        """
        Detect sensitive entities using multiple detection engines asynchronously
        with concurrent processing, enhanced GDPR compliance and error handling.

        Args:
            extracted_data: Dictionary containing text and bounding box information
            requested_entities: List of entity types to detect

        Returns:
            Tuple of (anonymized_text, results_json, redaction_mapping)
        """
        start_time = time.time()
        all_entities = []
        all_redaction_mappings = []
        anonymized_text = None

        # Apply data minimization principles
        minimized_data = minimize_extracted_data(extracted_data)

        # Track detector usage - use async lock
        async with self._detector_lock.acquire_timeout(timeout=5.0) as acquired:
            if acquired:
                self._total_calls += 1
                self._last_used = start_time

        # Track processing for GDPR compliance
        operation_type = "hybrid_detection"
        document_type = "document"

        # For storing results from each engine
        success_count = 0
        failure_count = 0

        # Define a function to process with one detector
        async def process_with_detector(detector):
            engine_name = type(detector).__name__
            detector_start = time.time()

            try:
                # Use timeout handling with proper async/sync distinction
                if hasattr(detector, 'detect_sensitive_data_async'):
                    # Use async version with timeout
                    try:
                        result = await asyncio.wait_for(
                            detector.detect_sensitive_data_async(
                                minimized_data, requested_entities
                            ),
                            timeout=60.0  # 60 second timeout for detector
                        )
                    except asyncio.TimeoutError:
                        log_warning(f"[WARNING] Timeout in {engine_name} detector")
                        return {
                            "success": False,
                            "engine": engine_name,
                            "error": "Detection timeout",
                            "processing_time": time.time() - detector_start
                        }
                else:
                    # Fall back to sync version with timeout
                    try:
                        result = await asyncio.to_thread(
                            detector.detect_sensitive_data,
                            minimized_data, requested_entities
                        )
                    except asyncio.TimeoutError:
                        log_warning(f"[WARNING] Timeout in {engine_name} detector (sync mode)")
                        return {
                            "success": False,
                            "engine": engine_name,
                            "error": "Detection timeout in sync mode",
                            "processing_time": time.time() - detector_start
                        }

                # Calculate detector time
                detector_time = time.time() - detector_start

                # Log detection results without sensitive information
                log_info(f"[OK] {engine_name} found {len(result[1])} entities in {detector_time:.2f}s")

                # Record successful detection for GDPR compliance
                record_keeper.record_processing(
                    operation_type=f"{operation_type}_{engine_name.lower()}",
                    document_type=document_type,
                    entity_types_processed=requested_entities or [],
                    processing_time=detector_time,
                    entity_count=len(result[1]),
                    success=True
                )

                return {
                    "success": True,
                    "engine": engine_name,
                    "result": result,
                    "processing_time": detector_time
                }

            except Exception as e:
                # Use standardized error handling
                SecurityAwareErrorHandler.log_processing_error(
                    e, f"hybrid_{engine_name.lower()}_detection", "document"
                )

                return {
                    "success": False,
                    "engine": engine_name,
                    "error": str(e),
                    "processing_time": time.time() - detector_start
                }

        # Create tasks for all detectors
        tasks = []
        for detector in self.detectors:
            tasks.append(process_with_detector(detector))

        # Run all detector tasks concurrently with overall timeout
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=False),
                timeout=120.0  # Overall 2-minute timeout for all detectors
            )
        except asyncio.TimeoutError:
            log_error("[ERROR] Global timeout for all detection engines")
            # Return empty results to avoid crashing
            return "", [], {"pages": []}

        # Process results
        for result in results:
            if result["success"]:
                # Extract data from successful result
                engine_result = result["result"]
                anon_text, entities, redaction_mapping = engine_result

                # Log detection results without sensitive information
                log_sensitive_operation(
                    f"{result['engine']} Detection",
                    len(entities),
                    result["processing_time"],
                    engine=result["engine"]
                )

                # Use the first anonymized text (we'll merge entities, not text)
                if anonymized_text is None:
                    anonymized_text = anon_text

                # Add entities and redaction mappings
                all_entities.extend(entities)
                all_redaction_mappings.append(redaction_mapping)
                success_count += 1
            else:
                failure_count += 1

        # Handle the case where all detectors failed
        if success_count == 0:
            log_error("[ERROR] All detection engines failed")
            # Return empty results to avoid crashing
            return "", [], {"pages": []}

        merged_mapping = EntityUtils.merge_redaction_mappings(all_redaction_mappings)

        # Remove duplicate entities
        from backend.app.utils.sanitize_utils import deduplicate_entities
        all_entities = deduplicate_entities(all_entities)

        # Calculate total processing time
        total_time = time.time() - start_time

        # Track entity count using async lock
        async with self._detector_lock.acquire_timeout(timeout=5.0) as acquired:
            if acquired:
                self._total_entities_detected += len(all_entities)

        # Record the overall processing operation for GDPR compliance
        record_keeper.record_processing(
            operation_type=operation_type,
            document_type=document_type,
            entity_types_processed=requested_entities or [],
            processing_time=total_time,
            entity_count=len(all_entities),
            success=(success_count > 0)  # Consider successful if at least one engine succeeded
        )

        # Log performance metrics
        log_info(
            f"[PERF] Hybrid detection completed in {total_time:.2f}s with {success_count} successful engines and {failure_count} failures")
        log_info(
            f"[PERF] Total {len(all_entities)} entities detected across {len(extracted_data.get('pages', []))} pages")

        # Log detection summary with secure logging
        log_sensitive_operation(
            "Hybrid Detection",
            len(all_entities),
            total_time,
            engines_used=success_count,
            engines_failed=failure_count
        )

        return anonymized_text or "", all_entities, merged_mapping

    def detect_sensitive_data(
            self,
            extracted_data: Dict[str, Any],
            requested_entities: Optional[List[str]] = None
    ) -> tuple[str, list[Any], dict[str, list[Any]]] | None | tuple[str, list[Any], dict[str, list[Any]]] | tuple[
        str, list[Any], dict[str, list[Any]]]:
        """
        Detect sensitive entities using multiple detection engines (sync wrapper).

        Args:
            extracted_data: Dictionary containing text and bounding box information
            requested_entities: List of entity types to detect

        Returns:
            Tuple of (anonymized_text, results_json, redaction_mapping)
        """
        try:
            # Apply data minimization before processing
            minimized_data = minimize_extracted_data(extracted_data)

            # Create a new event loop for this method
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Add timeout for overall sync detection
                async def run_with_timeout():
                    return await asyncio.wait_for(
                        self.detect_sensitive_data_async(minimized_data, requested_entities),
                        timeout=180.0  # 3-minute timeout for overall sync detection
                    )

                return loop.run_until_complete(run_with_timeout())
            finally:
                loop.close()
        except asyncio.TimeoutError:
            log_error("[ERROR] Global timeout in hybrid entity detection (sync wrapper)")
            return "", [], {"pages": []}
        except RuntimeError as e:
            if "cannot schedule new futures after interpreter shutdown" in str(e):
                # Handle the case where we're shutting down
                log_warning(f"[WARNING] Shutdown in progress, returning empty results: {e}")
                return "", [], {"pages": []}

            # Use standardized error handling
            SecurityAwareErrorHandler.log_processing_error(e, "hybrid_detection_runtime", "document")
            return "", [], {"pages": []}
        except Exception as e:
            # Use standardized error handling
            SecurityAwareErrorHandler.log_processing_error(e, "hybrid_detection", "document")
            return "", [], {"pages": []}


    def get_status(self) -> dict[str, bool | list[Any] | float | int] | None:
        """
        Get the current status of the hybrid entity detector.

        Returns:
            Dictionary with status information
        """
        # Create async function to get status with lock
        async def get_status_async():
            async with self._detector_lock.acquire_timeout(timeout=1.0):
                return {
                    "initialized": True,
                    "initialization_time": self._initialization_time,
                    "last_used": self._last_used,
                    "idle_time": time.time() - self._last_used if self._last_used else None,
                    "total_calls": self._total_calls,
                    "total_entities_detected": self._total_entities_detected,
                    "detectors": [type(d).__name__ for d in self.detectors],
                    "detector_count": len(self.detectors),
                    "config": {k: v for k, v in self.config.items() if k != "detectors"}
                }

        # Run the async function in a new event loop
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    asyncio.wait_for(get_status_async(), timeout=2.0)
                )
            finally:
                loop.close()
        except (asyncio.TimeoutError, Exception):
            # Return limited information if lock acquisition fails
            return {
                "initialized": True,
                "initialization_time": self._initialization_time,
                "detectors": [type(d).__name__ for d in self.detectors],
                "detector_count": len(self.detectors),
                "lock_acquisition_failed": True
            }