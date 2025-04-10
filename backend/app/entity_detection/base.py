"""
This module contains the enhanced base implementation for entity detection.
It provides a unified base class for different entity detection implementations
with standardized error handling, detailed performance tracking, and GDPR-compliant
data minimization and data protection features. The class uses a lazy-initialized lock
to avoid potential deadlocks and implements both asynchronous and synchronous interfaces.
Detailed error handling is provided by SecurityAwareErrorHandler to ensure that no sensitive
information is leaked and to enable robust distributed tracing and logging.
"""

import asyncio
import time
from abc import ABC
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional, Union

from backend.app.domain.interfaces import EntityDetector
from backend.app.utils.helpers.text_utils import TextUtils
from backend.app.utils.logging.logger import default_logger as logger, log_warning
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.system_utils.synchronization_utils import TimeoutLock, LockPriority
from backend.app.utils.validation.data_minimization import minimize_extracted_data


class BaseEntityDetector(EntityDetector, ABC):
    """
    Enhanced base class for entity detectors with common functionality.

    This class provides shared functionality for various entity detection implementations.
    It supports:
      - Standardized entity processing with conversion to uniform dictionary formats.
      - Both asynchronous and synchronous methods for entity detection.
      - Performance tracking for GDPR compliance and auditing purposes.
      - Error handling through the SecurityAwareErrorHandler to avoid sensitive data leaks.
      - Enhanced synchronization using a lazily created TimeoutLock to prevent deadlocks.

    The class is intended to be subclassed and the asynchronous method `detect_sensitive_data_async`
    must be implemented by the derived class.
    """

    def __init__(self):
        """Initialize the base entity detector with tracking metrics and a lazy lock."""
        # Record the initialization time for performance tracking.
        self._initialization_time = time.time()
        self._last_used = self._initialization_time
        self._total_calls = 0
        self._total_entities_detected = 0
        self._total_processing_time = 0
        # The lock is lazily instantiated to avoid event loop binding issues.
        self._lock: Optional[TimeoutLock] = None

    def _get_access_lock(self) -> TimeoutLock:
        """
        Lazily create and return the TimeoutLock with the desired configuration.

        This lock is used for synchronizing access to shared metrics and preventing race conditions.
        Returns:
            TimeoutLock: The configured lock.
        """
        if self._lock is None:
            try:
                self._lock = TimeoutLock(
                    name="entity_detector_lock",
                    priority=LockPriority.MEDIUM,
                    timeout=10.0
                )
            except Exception as exc:
                # Log and handle lock creation failure.
                SecurityAwareErrorHandler.log_processing_error(exc, "lock_initialization")
        return self._lock

    async def detect_sensitive_data_async(
            self,
            extracted_data: Dict[str, Any],
            requested_entities: Optional[List[str]] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Asynchronous method to detect sensitive entities in extracted text.

        This method must be implemented by subclasses. It should return a tuple containing
        a list of detected entities (as dictionaries) and a redaction mapping for sensitive areas.

        Args:
            extracted_data: Dictionary containing text and bounding box information.
            requested_entities: Optional list of entity types to detect.

        Returns:
            Tuple[List[Dict[str, Any]], Dict[str, Any]]: Detected entities and redaction mapping.

        Raises:
            NotImplementedError: Always, as this method must be overridden.
        """
        raise NotImplementedError("Subclasses must implement this method")

    def detect_sensitive_data(
            self,
            extracted_data: Dict[str, Any],
            requested_entities: Optional[List[str]] = None
    ) -> tuple[list[Any], dict[str, list[Any]]] | None:
        """
        Synchronous wrapper around the asynchronous sensitive data detection method.

        It applies data minimization before processing and handles errors using SecurityAwareErrorHandler.

        Args:
            extracted_data: Dictionary containing text and bounding box information.
            requested_entities: Optional list of entity types to detect.

        Returns:
            Tuple containing detected entities and redaction mapping. In case of error,
            returns a default empty result.
        """
        # Apply data minimization for GDPR compliance.
        minimized_data = minimize_extracted_data(extracted_data)

        try:
            # Create a new event loop for synchronous execution.
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Use safe execution to catch errors during asynchronous processing.
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
            # Catch any unforeseen errors and handle them safely.
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

        The method standardizes raw entities, maps bounding boxes, and prepares a redaction mapping.
        It also updates performance metrics and records processing details for GDPR compliance.

        Args:
            page_number: The current page number.
            full_text: The full text of the page.
            mapping: List mapping text positions to bounding boxes.
            entities: List of detected entities (raw format).

        Returns:
            A tuple containing:
                - processed_entities: List of processed entity metadata.
                - page_redaction_info: Dictionary containing redaction mapping info for the page.
        """
        start_time = time.time()
        try:
            # Standardize raw entity data.
            standardized_entities = self._standardize_raw_entities(entities, full_text)
        except Exception as exc:
            # Handle any error in standardizing entities.
            SecurityAwareErrorHandler.log_processing_error(exc, "standardize_entities")
            standardized_entities = []

        try:
            # Process sanitized entities to compute positions and bounding boxes.
            processed_entities, page_sensitive = self._process_sanitized_entities(
                standardized_entities,
                full_text,
                mapping
            )
        except Exception as exc:
            SecurityAwareErrorHandler.log_processing_error(exc, "process_sanitized_entities")
            processed_entities, page_sensitive = [], []

        # Build the redaction mapping for the current page.
        page_redaction_info = {"page": page_number, "sensitive": page_sensitive}

        # Compute processing time and update metrics.
        processing_time = time.time() - start_time
        try:
            self._update_entity_metrics(processed_entities, processing_time)
            self._record_entity_processing(processed_entities, processing_time)
        except Exception as exc:
            SecurityAwareErrorHandler.log_processing_error(exc, "update_metrics")
        return processed_entities, page_redaction_info

    def _standardize_raw_entities(
            self,
            raw_entities: List[Any],
            full_text: str
    ) -> List[Dict[str, Any]]:
        """
        Convert raw entities into a standardized dictionary format.

        Each raw entity is converted by the helper method `_convert_to_entity_dict` and validated to have extractable text.
        Entities that cannot be converted or lack text are skipped.

        Args:
            raw_entities: List of raw entity objects or dictionaries.
            full_text: The full text of the page for reference.

        Returns:
            List of standardized entity dictionaries.
        """
        standardized_entities = []
        for raw_entity in raw_entities:
            try:
                # Convert raw entity to a dictionary.
                converted_entity = self._convert_to_entity_dict(raw_entity)
                if not converted_entity:
                    log_warning("[WARNING] _convert_to_entity_dict returned None. Skipping entity.")
                    continue

                # Extract entity text from the full text.
                entity_text = self._get_entity_text(converted_entity, full_text)
                if entity_text:
                    standardized_entities.append(converted_entity)
                else:
                    log_warning("[WARNING] Could not determine entity text, skipping entity.")
            except Exception as exc:
                # Log the error without stopping processing of subsequent entities.
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
        Process sanitized entities to determine text positions and bounding boxes.

        Each sanitized entity is further processed to determine its exact positions in the text and to compute
        corresponding bounding boxes for redaction.

        Args:
            sanitized_entities: List of entities already converted to a standardized format.
            full_text: The complete text of the page.
            mapping: Mapping information from text to bounding boxes.

        Returns:
            A tuple containing:
              - processed_entities: List of processed entity metadata.
              - page_sensitive: List of sensitive items with bounding box information.
        """
        processed_entities = []
        page_sensitive = []

        for sanitized_entity in sanitized_entities:
            try:
                # Process each entity individually.
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
        Process a single sanitized entity to determine all occurrences in the text.

        This method finds all occurrences of the entity's text in the full text, maps them to bounding boxes,
        and constructs both the processed entity metadata and sensitive redaction items.

        Args:
            sanitized_entity: A dictionary representing the sanitized entity.
            full_text: The complete text from which to extract the entity.
            mapping: Mapping from text positions to bounding boxes.

        Returns:
            A tuple containing:
              - local_processed: List of processed entity metadata (with start, end, and score).
              - local_sensitive: List of sensitive items with bounding box info.
        """
        local_processed = []
        local_sensitive = []

        # Get the text representation of the entity.
        entity_text = self._get_entity_text(sanitized_entity, full_text)
        if not entity_text:
            log_warning("[WARNING] Could not determine entity text after sanitization. Skipping entity.")
            return local_processed, local_sensitive

        try:
            # Recompute the offsets where the entity text occurs.
            matches = TextUtils.recompute_offsets(full_text, entity_text)
        except Exception as exc:
            SecurityAwareErrorHandler.log_processing_error(exc, "recompute_offsets")
            return local_processed, local_sensitive

        if not matches:
            log_warning("[WARNING] No matches found for entity '{0}', skipping".format(entity_text))
            return local_processed, local_sensitive

        # Deduplicate matches by (start, end) offsets.
        unique_matches = {}
        for start_offset, end_offset in matches:
            key = (start_offset, end_offset)
            if key not in unique_matches:
                unique_matches[key] = (start_offset, end_offset)

        # Process each unique match to compute bounding boxes.
        for start_offset, end_offset in unique_matches.values():
            try:
                bboxes = TextUtils.map_offsets_to_bboxes(full_text, mapping, (start_offset, end_offset))
            except Exception as exc:
                SecurityAwareErrorHandler.log_processing_error(exc, "map_offsets_to_bboxes")
                continue

            if not bboxes:
                continue
            # If multiple bounding boxes are found, merge them into one.
            merged_bbox = TextUtils.merge_bounding_boxes(bboxes)

            # Build the sensitive item with redaction details.
            sensitive_item = {
                "original_text": full_text[start_offset:end_offset],
                "entity_type": sanitized_entity["entity_type"],
                "start": start_offset,
                "end": end_offset,
                "score": sanitized_entity["score"],
                "bbox": merged_bbox
            }
            local_sensitive.append(sensitive_item)

            # Build the processed entity metadata.
            local_processed.append({
                "entity_type": sanitized_entity["entity_type"],
                "start": start_offset,
                "end": end_offset,
                "score": sanitized_entity["score"]
            })

        return local_processed, local_sensitive

    def _update_entity_metrics(self, processed_entities: List[Dict[str, Any]], processing_time: float) -> None:
        """
        Update internal counters to track entity detection metrics.

        Uses a timeout lock to safely update metrics in concurrent environments.

        Args:
            processed_entities: The list of entities processed in this operation.
            processing_time: The time taken to process these entities.
        """
        lock = self._get_access_lock()
        acquired = lock.acquire(timeout=2.0)
        if acquired:
            try:
                self._total_entities_detected += len(processed_entities)
                self._total_processing_time += processing_time
            except Exception as exc:
                SecurityAwareErrorHandler.log_processing_error(exc, "update_metrics")
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
        Record entity processing details for GDPR compliance and auditing.

        This logs the details of the entity processing operation such as types, count, and processing time.

        Args:
            processed_entities: The list of processed entity dictionaries.
            processing_time: Time taken to process the entities.
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
        Retrieve the text for an entity from multiple possible sources.

        The method checks for keys 'original_text', 'start' and 'end', and 'text' in that order.
        It ensures that the indices are valid when extracting a substring from full_text.

        Args:
            entity_dict: The dictionary representing the entity.
            full_text: The complete text for reference.

        Returns:
            The extracted entity text, or None if no valid text can be determined.
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
            except (ValueError, TypeError, IndexError) as exc:
                SecurityAwareErrorHandler.log_processing_error(exc, "entity_text_extraction")

        if "text" in entity_dict and entity_dict["text"]:
            return entity_dict["text"]

        return None

    def get_status(self) -> Dict[str, Any]:
        """
        Retrieve the current status and performance metrics of the entity detector.

        This includes initialization time, last used time, total calls, total entities detected,
        and average processing time.

        Returns:
            Dictionary containing status information.
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
        Update usage metrics such as last used time, call count, and processing times.

        This method is used to update internal counters each time entity detection is performed.

        Args:
            entities_count: The number of entities detected in this call.
            processing_time: The time taken to process these entities.
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
        except Exception as exc:
            SecurityAwareErrorHandler.log_processing_error(exc, "update_usage_metrics")
        finally:
            if acquired:
                lock.release()

    @staticmethod
    def filter_by_score(
            data: Union[List[Dict[str, Any]], Dict[str, Any]],
            threshold: float = 0.85
    ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Filter a list of entity dictionaries or a redaction mapping based on a score threshold.

        If data is a list, only entities with a 'score' greater than or equal to the threshold are retained.
        If data is a dictionary (expected to be a redaction mapping with a 'pages' key), then for each page,
        only the 'sensitive' entities with a score meeting the threshold are retained.

        Args:
            data: Either a list of entity dictionaries or a redaction mapping dictionary.
            threshold: Minimum score required (default: 0.85).

        Returns:
            The filtered data in the same structure as the input.

        Raises:
            ValueError: If the input data is not of an expected type.
        """
        if isinstance(data, list):
            # Data is a flat list of entities.
            return [entity for entity in data if entity.get("score", 0) >= threshold]
        elif isinstance(data, dict):
            # Data is assumed to be a redaction mapping with "pages".
            for page in data.get("pages", []):
                if "sensitive" in page:
                    page["sensitive"] = [
                        entity for entity in page["sensitive"]
                        if entity.get("score", 0) >= threshold
                    ]
            return data
        else:
            raise ValueError("Input data must be a list or a dictionary with a 'pages' key.")

    @staticmethod
    def _convert_to_entity_dict(entity: Any) -> Dict[str, Any]:
        """
        Convert an entity (a dictionary or an object with attributes) into a standardized format.

        The returned dictionary includes:
          - "entity_type": The type of the entity (default "UNKNOWN").
          - "start": The starting character offset (default 0).
          - "end": The ending character offset (default 0).
          - "score": The confidence score as a float (default 0.5).
          - "original_text": Optionally, the original text if present.

        Args:
            entity: The raw entity to be converted.

        Returns:
            A standardized dictionary representing the entity.
        """
        # Check if the entity is a dictionary.
        if isinstance(entity, dict):
            result = {
                "entity_type": entity.get("entity_type", "UNKNOWN"),
                "start": entity.get("start", 0),
                "end": entity.get("end", 0),
                "score": float(entity.get("score", 0.5))
            }
            if "original_text" in entity:
                result["original_text"] = entity["original_text"]
            return result

        # If the entity is an object with attributes (e.g., a RecognizerResult), extract them.
        if hasattr(entity, "entity_type"):
            return {
                "entity_type": getattr(entity, "entity_type", "UNKNOWN"),
                "start": getattr(entity, "start", 0),
                "end": getattr(entity, "end", 0),
                "score": float(getattr(entity, "score", 0.5))
            }

        # Attempt a generic extraction of attributes.
        try:
            return {
                "entity_type": getattr(entity, "entity_type", "UNKNOWN"),
                "start": getattr(entity, "start", 0),
                "end": getattr(entity, "end", 0),
                "score": float(getattr(entity, "score", 0.5))
            }
        except Exception as conversion_exc:
            SecurityAwareErrorHandler.log_processing_error(conversion_exc, "entity_conversion")
            return {"entity_type": "UNKNOWN", "start": 0, "end": 0, "score": 0.0}
