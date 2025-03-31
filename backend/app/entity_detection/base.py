"""
base implementation for entity detection with improved error handling and GDPR compliance.

This module provides a unified base class for entity detection implementations
with standardized error handling, performance tracking, and data protection features.
"""
import asyncio
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional

from backend.app.domain.interfaces import EntityDetector
from backend.app.utils.validation.data_minimization import minimize_extracted_data
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.helpers.text_utils import TextUtils
from backend.app.utils.logging.logger import default_logger as logger, log_warning
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.system_utils.synchronization_utils import TimeoutLock, LockPriority


class BaseEntityDetector(EntityDetector, ABC):
    """
    Enhanced base class for entity detectors with common functionality.

    This class provides shared functionality for different entity detection
    implementations including standardized error handling, performance tracking,
    and data protection features compliant with GDPR requirements.

    Features:
    - Standardized entity processing
    - Parallel processing capabilities
    - Performance tracking
    - GDPR-compliant data handling
    - Unified error management
    - Enhanced synchronization with deadlock prevention
    """

    def __init__(self):
        """Initialize the base entity detector with tracking metrics."""
        self._initialization_time = time.time()
        self._last_used = self._initialization_time
        self._total_calls = 0
        self._total_entities_detected = 0
        self._total_processing_time = 0
        # Do not create the lock here; instead, set it to None for lazy creation
        self._lock: Optional[TimeoutLock] = None

    def _get_access_lock(self) -> TimeoutLock:
        """
        Lazily create and return the TimeoutLock with the desired configuration.
        This avoids potential event-loop binding issues when the class is instantiated.
        """
        if self._lock is None:
            self._lock = TimeoutLock(
                name="entity_detector_lock",
                priority=LockPriority.MEDIUM,
                timeout=10.0
            )
        return self._lock

    async def detect_sensitive_data_async(
        self,
        extracted_data: Dict[str, Any],
        requested_entities: Optional[List[str]] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Asynchronous method to detect sensitive entities in extracted text.
        Must be implemented by derived classes.

        Args:
            extracted_data: Dictionary containing text and bounding box information
            requested_entities: List of entity types to detect

        Returns:
            Tuple of (results_json, redaction_mapping)
        """
        raise NotImplementedError("Subclasses must implement this method")

    def detect_sensitive_data(
        self,
        extracted_data: Dict[str, Any],
        requested_entities: Optional[List[str]] = None
    ) -> tuple[list[Any], dict[str, list[Any]]] | None:
        """
        Synchronous method to detect sensitive entities in extracted text.
        This is a wrapper around the async version with improved error handling.

        Args:
            extracted_data: Dictionary containing text and bounding box information
            requested_entities: List of entity types to detect

        Returns:
            Tuple of (results_json, redaction_mapping)
        """
        # Apply data minimization before processing
        minimized_data = minimize_extracted_data(extracted_data)

        try:
            # Create an event loop for the synchronous method
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                success, result, error_msg = SecurityAwareErrorHandler.safe_execution(
                    func=lambda: loop.run_until_complete(
                        self.detect_sensitive_data_async(minimized_data, requested_entities)
                    ),
                    error_type="entity_detection",
                    default=([], {"pages": []})
                )
                if not success:
                    log_warning("Entity detection encountered error: " + error_msg)
                return result
            finally:
                loop.close()
        except Exception as exc:
            # Use standardized error handling
            return SecurityAwareErrorHandler.handle_safe_error(
                exc, "entity_detection", "", default_return=([], {"pages": []})
            )

    async def process_entities_for_page(
        self,
        page_number: int,
        full_text: str,
        mapping: List[Tuple[Dict[str, Any], int, int]],
        entities: List[Any]
    ) -> tuple[
        list[dict[str, int | Any]],
        dict[str, int | list[dict[str, int | str | dict[str, float] | Any]]]
    ] | None:
        """
        Process entities for a single page.

        Args:
            page_number: Current page number
            full_text: Text of the current page
            mapping: Mapping of text to positions
            entities: List of detected entities

        Returns:
            Tuple of (processed_entities, page_redaction_info)
        """
        start_time = time.time()

        # 1. Standardize raw entities (convert them to a consistent dict format, etc.)
        standardized_entities = self._standardize_raw_entities(entities, full_text)

        # 2. Sanitize entities (merge overlapping and remove duplicates).
        sanitized_entities = self.sanitize_entities(standardized_entities)

        # 3. Process sanitized entities to find bounding boxes and positions.
        processed_entities, page_sensitive = self._process_sanitized_entities(
            sanitized_entities,
            full_text,
            mapping
        )

        # 4. Create page redaction info.
        page_redaction_info = {"page": page_number, "sensitive": page_sensitive}

        # 5. Update metrics and record processing for GDPR compliance.
        processing_time = time.time() - start_time
        self._update_entity_metrics(processed_entities, processing_time)
        self._record_entity_processing(processed_entities, processing_time)

        return processed_entities, page_redaction_info

    def _standardize_raw_entities(
        self,
        raw_entities: List[Any],
        full_text: str
    ) -> List[Dict[str, Any]]:
        """
        Convert raw entities to standardized dictionaries where possible.
        Entities without discernible text are skipped.

        Args:
            raw_entities: List of raw entity objects or dicts
            full_text: The full page text for reference

        Returns:
            A list of standardized entity dictionaries
        """
        standardized_entities = []
        for raw_entity in raw_entities:
            try:
                converted_entity = self._convert_to_entity_dict(raw_entity)
                if not converted_entity:
                    log_warning("[WARNING] _convert_to_entity_dict returned None. Skipping entity.")
                    continue

                entity_text = self._get_entity_text(converted_entity, full_text)
                if entity_text:
                    standardized_entities.append(converted_entity)
                else:
                    log_warning("[WARNING] Could not determine entity text, skipping entity.")
            except Exception as exc:
                logger.error("Error processing entity: " + str(exc))
                logger.error("Entity data: " + str(raw_entity))
                SecurityAwareErrorHandler.log_processing_error(exc, "entity_processing")
        return standardized_entities

    def _process_sanitized_entities(
        self,
        sanitized_entities: List[Dict[str, Any]],
        full_text: str,
        mapping: List[Tuple[Dict[str, Any], int, int]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Process each sanitized entity to find matches in the text and corresponding bounding boxes.

        Args:
            sanitized_entities: Entities after merging/removing duplicates
            full_text: The full page text
            mapping: Mapping of text to positions

        Returns:
            A tuple of:
            - processed_entities: List of processed entity dictionaries with start/end positions
            - page_sensitive: List of items with bounding box info for redaction
        """
        processed_entities = []
        page_sensitive = []

        for sanitized_entity in sanitized_entities:
            try:
                local_processed, local_sensitive = self._process_single_entity(
                    sanitized_entity,
                    full_text,
                    mapping
                )
                processed_entities.extend(local_processed)
                page_sensitive.extend(local_sensitive)
            except Exception as exc:
                logger.error("Error processing entity: " + str(exc))
                logger.error("Entity data: " + str(sanitized_entity))
                SecurityAwareErrorHandler.log_processing_error(exc, "entity_processing")

        return processed_entities, page_sensitive

    def _process_single_entity(
        self,
        sanitized_entity: Dict[str, Any],
        full_text: str,
        mapping: List[Tuple[Dict[str, Any], int, int]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        For a single sanitized entity, find all occurrences in the text,
        map bounding boxes, and build processed/sensitive lists.

        Args:
            sanitized_entity: A sanitized entity dictionary
            full_text: The full page text
            mapping: Mapping of text to positions

        Returns:
            A tuple of:
            - local_processed: processed entity metadata (start, end, score, etc.)
            - local_sensitive: sensitive items with bounding box info
        """
        local_processed = []
        local_sensitive = []

        entity_text = self._get_entity_text(sanitized_entity, full_text)
        if not entity_text:
            log_warning("[WARNING] Could not determine entity text after sanitization. Skipping entity.")
            return local_processed, local_sensitive

        matches = TextUtils.recompute_offsets(full_text, entity_text)
        if not matches:
            log_warning("[WARNING] No matches found for entity '{0}', skipping".format(entity_text))
            return local_processed, local_sensitive

        for start_offset, end_offset in matches:
            mapped_bboxes = TextUtils.map_offsets_to_bboxes(full_text, mapping, (start_offset, end_offset))
            if not mapped_bboxes:
                continue

            # Build local_sensitive data
            for bbox in mapped_bboxes:
                sensitive_item = {
                    "original_text": full_text[start_offset:end_offset],
                    "entity_type": sanitized_entity["entity_type"],
                    "start": start_offset,
                    "end": end_offset,
                    "score": sanitized_entity["score"],
                    "bbox": bbox
                }
                local_sensitive.append(sensitive_item)

            # Build local_processed data
            local_processed.append({
                "entity_type": sanitized_entity["entity_type"],
                "start": start_offset,
                "end": end_offset,
                "score": sanitized_entity["score"]
            })

        return local_processed, local_sensitive

    def _update_entity_metrics(self, processed_entities: List[Dict[str, Any]], processing_time: float) -> None:
        """
        Update internal counters for entity detection metrics, using a timeout lock.

        Args:
            processed_entities: The list of entities processed in this call
            processing_time: Time spent processing
        """
        lock = self._get_access_lock()
        acquired = lock.acquire(timeout=2.0)
        if acquired:
            try:
                self._total_entities_detected += len(processed_entities)
                self._total_processing_time += processing_time
            finally:
                lock.release()
        else:
            log_warning("Failed to acquire lock for updating entity statistics")

    @staticmethod
    def _record_entity_processing(
        processed_entities: List[Dict[str, Any]],
        processing_time: float
    ) -> None:
        """
        Record entity processing details for GDPR compliance.

        Args:
            processed_entities: The list of processed entities
            processing_time: Time spent processing
        """
        record_keeper.record_processing(
            operation_type="entity_processing",
            document_type="page_entity_detection",
            entity_types_processed=[ent.get("entity_type") for ent in processed_entities],
            processing_time=processing_time,
            entity_count=len(processed_entities),
            success=True
        )

    @staticmethod
    def _get_entity_text(entity_dict: Dict[str, Any], full_text: str) -> Optional[str]:
        """
        Get the text of an entity from different possible sources.

        Args:
            entity_dict: Entity dictionary
            full_text: Full text from which to extract entity text

        Returns:
            Entity text or None if not available
        """
        if "original_text" in entity_dict and entity_dict["original_text"]:
            return entity_dict["original_text"]

        if (
            "start" in entity_dict and "end" in entity_dict
            and entity_dict["start"] is not None
            and entity_dict["end"] is not None
        ):
            try:
                start = int(entity_dict["start"])
                end = int(entity_dict["end"])
                if 0 <= start < end <= len(full_text):
                    return full_text[start:end]
            except (ValueError, TypeError, IndexError):
                pass

        if "text" in entity_dict and entity_dict["text"]:
            return entity_dict["text"]

        return None

    @abstractmethod
    def _convert_to_entity_dict(self, entity: Any) -> Dict[str, Any]:
        """
        Convert an entity to a standard dictionary format.

        Args:
            entity: Entity object or dictionary

        Returns:
            Standardized entity dictionary

        Raises:
            NotImplementedError: Must be implemented by derived classes
        """
        raise NotImplementedError("Subclasses must implement this method")

    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the entity detector.

        Returns:
            Dictionary with status information
        """
        lock = self._get_access_lock()
        acquired = lock.acquire(timeout=1.0)
        try:
            if acquired:
                status = {
                    "initialized": True,
                    "initialization_time": self._initialization_time,
                    "initialization_time_readable": datetime.fromtimestamp(
                        self._initialization_time, timezone.utc
                    ).strftime('%Y-%m-%d %H:%M:%S'),
                    "last_used": self._last_used,
                    "last_used_readable": (
                        datetime.fromtimestamp(self._last_used, timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                        if self._last_used else "Never Used"
                    ),
                    "idle_time": (time.time() - self._last_used) if self._last_used else None,
                    "idle_time_readable": (
                        "{:.2f} seconds".format(time.time() - self._last_used)
                        if self._last_used else "N/A"
                    ),
                    "total_calls": self._total_calls,
                    "total_entities_detected": self._total_entities_detected,
                    "total_processing_time": self._total_processing_time,
                    "average_processing_time": (
                        self._total_processing_time / self._total_calls
                        if self._total_calls > 0 else None
                    )
                }
                return status
            else:
                return {
                    "initialized": True,
                    "initialization_time": self._initialization_time,
                    "lock_acquisition_failed": True
                }
        finally:
            if acquired:
                lock.release()

    def update_usage_metrics(self, entities_count: int, processing_time: float) -> None:
        """
        Update usage metrics for the entity detector.

        Args:
            entities_count: Number of entities detected
            processing_time: Time taken for processing
        """
        lock = self._get_access_lock()
        acquired = lock.acquire(timeout=1.0)
        try:
            if acquired:
                self._last_used = time.time()
                self._total_calls += 1
                self._total_entities_detected += entities_count
                self._total_processing_time += processing_time
            else:
                log_warning("Failed to acquire lock for updating entity metrics")
        finally:
            if acquired:
                lock.release()

    def sanitize_entities(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Sanitizes the detected entities by:
        1. Merging overlapping entities
        2. Removing duplicates with the same start and end indices

        This method ensures that the entity detection results are clean and
        without redundancy before further processing.

        Args:
            entities: List of entity dictionaries

        Returns:
            Sanitized list of entities
        """
        entity_dicts = []
        for ent in entities:
            if isinstance(ent, dict):
                entity_dicts.append(ent)
            else:
                entity_dicts.append(self._convert_to_entity_dict(ent))

        # Import here to avoid circular imports
        from backend.app.utils.helpers.text_utils import EntityUtils

        merged_entities = EntityUtils.merge_overlapping_entity_dicts(entity_dicts)
        deduplicated_entities = EntityUtils.remove_duplicate_entities(merged_entities)

        return deduplicated_entities