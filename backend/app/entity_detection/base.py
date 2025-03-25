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
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.helpers.text_utils import TextUtils
from backend.app.utils.logging.logger import default_logger as logger, log_warning
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.synchronization_utils import TimeoutLock, LockPriority


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
        # Replace RLock with TimeoutLock with appropriate priority
        self._access_lock = TimeoutLock(name="entity_detector_lock",
                                        priority=LockPriority.MEDIUM,
                                        timeout=10.0)

    async def detect_sensitive_data_async(
        self,
        extracted_data: Dict[str, Any],
        requested_entities: Optional[List[str]] = None
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        """
        Asynchronous method to detect sensitive entities in extracted text.
        Must be implemented by derived classes.

        Args:
            extracted_data: Dictionary containing text and bounding box information
            requested_entities: List of entity types to detect

        Returns:
            Tuple of (anonymized_text, results_json, redaction_mapping)
        """
        raise NotImplementedError("Subclasses must implement this method")

    def detect_sensitive_data(
            self,
            extracted_data: Dict[str, Any],
            requested_entities: Optional[List[str]] = None
    ) -> tuple[str, list[Any], dict[str, list[Any]]] | None:
        """
        Synchronous method to detect sensitive entities in extracted text.
        This is a wrapper around the async version with improved error handling.

        Args:
            extracted_data: Dictionary containing text and bounding box information
            requested_entities: List of entity types to detect

        Returns:
            Tuple of (anonymized_text, results_json, redaction_mapping)
        """
        # Apply data minimization before processing
        minimized_data = minimize_extracted_data(extracted_data)

        # Use SecurityAwareErrorHandler's safe_execution for consistent error handling
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
                    default=("", [], {"pages": []})
                )
                return result
            finally:
                loop.close()
        except Exception as e:
            # Use standardized error handling
            return SecurityAwareErrorHandler.handle_safe_error(
                e, "entity_detection", "", default_return=("", [], {"pages": []})
            )

    async def process_entities_for_page(
            self,
            page_number: int,
            full_text: str,
            mapping: List[Tuple[Dict[str, Any], int, int]],
            entities: List[Any]
    ) -> tuple[list[dict[str, int | Any]], dict[str, int | list[dict[str, int | str | dict[str, float] | Any]]]] | None:
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
        processed_entities = []
        page_sensitive = []

        # Track processing for GDPR compliance
        start_time = time.time()

        # Convert entities to standard format for sanitization
        standardized_entities = []
        for entity in entities:
            try:
                # Convert entity to standard dictionary format
                entity_dict = self._convert_to_entity_dict(entity)

                # Get entity text - try different approaches based on entity type
                entity_text = self._get_entity_text(entity_dict, full_text)

                if entity_text:
                    standardized_entities.append(entity_dict)
                else:
                    log_warning(f"[WARNING] Could not determine entity text, skipping entity")
            except Exception as e:
                logger.error(f"Error processing entity: {str(e)}")
                logger.error(f"Entity data: {entity}")
                SecurityAwareErrorHandler.log_processing_error(e, "entity_processing")

        # Sanitize entities (merge overlapping and remove duplicates)
        sanitized_entities = self.sanitize_entities(standardized_entities)

        for entity_dict in sanitized_entities:
            try:
                # Get entity text again after sanitization
                entity_text = self._get_entity_text(entity_dict, full_text)

                if not entity_text:
                    log_warning(f"[WARNING] Could not determine entity text after sanitization, skipping entity")
                    continue

                # Find all occurrences in case of multiple matches
                matches = TextUtils.recompute_offsets(full_text, entity_text)

                if not matches:
                    log_warning(f"[WARNING] No matches found for entity '{entity_text}', skipping")
                    continue

                for recomputed_start, recomputed_end in matches:
                    # Map to bounding boxes
                    mapped_bboxes = TextUtils.map_offsets_to_bboxes(
                        full_text, mapping, (recomputed_start, recomputed_end)
                    )

                    if not mapped_bboxes:
                        continue

                    # Create entity entry for each bounding box
                    for bbox in mapped_bboxes:
                        sensitive_item = {
                            "original_text": full_text[recomputed_start:recomputed_end],
                            "entity_type": entity_dict["entity_type"],
                            "start": recomputed_start,
                            "end": recomputed_end,
                            "score": entity_dict["score"],
                            "bbox": bbox
                        }
                        page_sensitive.append(sensitive_item)

                    # Add to processed entities list (only once per match)
                    processed_entities.append({
                        "entity_type": entity_dict["entity_type"],
                        "start": recomputed_start,
                        "end": recomputed_end,
                        "score": entity_dict["score"]
                    })
            except Exception as e:
                logger.error(f"Error processing entity: {str(e)}")
                logger.error(f"Entity data: {entity_dict}")

                # Use standardized error handling
                SecurityAwareErrorHandler.log_processing_error(e, "entity_processing")

        # Create page redaction info
        page_redaction_info = {
            "page": page_number,
            "sensitive": page_sensitive
        }

        # Track metrics for GDPR compliance - Use timeout lock
        processing_time = time.time() - start_time

        # Use the timeout lock instead of directly accessing
        acquired = self._access_lock.acquire(timeout=2.0)  # 2 second timeout
        if acquired:
            try:
                self._total_entities_detected += len(processed_entities)
                self._total_processing_time += processing_time
            finally:
                self._access_lock.release()
        else:
            # Log warning if lock acquisition failed
            log_warning("Failed to acquire lock for updating entity statistics")

        # Record entity processing for GDPR compliance
        record_keeper.record_processing(
            operation_type="entity_processing",
            document_type="page_entity_detection",
            entity_types_processed=[entity.get("entity_type") for entity in processed_entities],
            processing_time=processing_time,
            entity_count=len(processed_entities),
            success=True
        )

        return processed_entities, page_redaction_info

    def _get_entity_text(self, entity_dict: Dict[str, Any], full_text: str) -> Optional[str]:
        """
        Get the text of an entity from different possible sources.

        Args:
            entity_dict: Entity dictionary
            full_text: Full text from which to extract entity text

        Returns:
            Entity text or None if not available
        """
        # Try getting original_text directly (Gemini style)
        if "original_text" in entity_dict and entity_dict["original_text"]:
            return entity_dict["original_text"]

        # Try extracting text using start/end indices (Presidio style)
        if ("start" in entity_dict and "end" in entity_dict and
            entity_dict["start"] is not None and entity_dict["end"] is not None):
            try:
                start = int(entity_dict["start"])
                end = int(entity_dict["end"])
                if 0 <= start < end <= len(full_text):
                    return full_text[start:end]
            except (ValueError, TypeError, IndexError):
                pass

        # Try a text field if it exists
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
        # Use timeout lock with a short timeout to avoid blocking for status check
        acquired = self._access_lock.acquire(timeout=1.0)
        try:
            if acquired:
                status = {
                "initialized": True,
                "initialization_time": self._initialization_time,
                "initialization_time_readable": datetime.fromtimestamp(self._initialization_time, timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                "last_used": self._last_used,
                "last_used_readable": datetime.fromtimestamp(self._last_used, timezone.utc).strftime('%Y-%m-%d %H:%M:%S') if self._last_used else "Never Used",
                "idle_time": time.time() - self._last_used if self._last_used else None,
                "idle_time_readable": f"{(time.time() - self._last_used):.2f} seconds" if self._last_used else "N/A",
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
                # Return limited info if lock acquisition fails
                return {
                    "initialized": True,
                    "initialization_time": self._initialization_time,
                    "lock_acquisition_failed": True
                }
        finally:
            if acquired:
                self._access_lock.release()

    def update_usage_metrics(self, entities_count: int, processing_time: float) -> None:
        """
        Update usage metrics for the entity detector.

        Args:
            entities_count: Number of entities detected
            processing_time: Time taken for processing
        """
        # Use timeout lock with a short timeout to avoid blocking for metrics update
        acquired = self._access_lock.acquire(timeout=1.0)
        try:
            if acquired:
                self._last_used = time.time()
                self._total_calls += 1
                self._total_entities_detected += entities_count
                self._total_processing_time += processing_time
            else:
                # Log warning if lock acquisition failed
                log_warning("Failed to acquire lock for updating entity metrics")
        finally:
            if acquired:
                self._access_lock.release()

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
        # Convert all entities to a standard dictionary format if they're not already
        entity_dicts = []
        for entity in entities:
            # Check if entity is already a dictionary
            if isinstance(entity, dict):
                entity_dicts.append(entity)
            else:
                # Convert to dictionary using the conversion method
                entity_dicts.append(self._convert_to_entity_dict(entity))

        # Import here to avoid circular imports
        from backend.app.utils.helpers.text_utils import EntityUtils

        # First, merge overlapping entities
        merged_entities = EntityUtils.merge_overlapping_entity_dicts(entity_dicts)

        # Then, remove duplicates (entities with the same start and end positions)
        deduplicated_entities = EntityUtils.remove_duplicate_entities(merged_entities)

        return deduplicated_entities