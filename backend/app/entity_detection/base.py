"""
Base implementation for entity detection.
"""
from abc import ABC
from typing import Dict, Any, List, Tuple, Optional, Union

from backend.app.domain.interfaces import EntityDetector
from backend.app.utils.helpers.text_utils import TextUtils
from backend.app.utils.logger import default_logger as logger, log_warning, log_info


class BaseEntityDetector(EntityDetector, ABC):
    """
    Base class for entity detectors with common functionality.

    This class provides shared functionality for different entity detection
    implementations and defines the interface they should implement.
    """

    def process_entities_for_page(
            self,
            page_number: int,
            full_text: str,
            mapping: List[Tuple[Dict[str, Any], int, int]],
            entities: List[Any]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
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

        for entity in entities:
            try:
                # Convert entity to standard dictionary format
                entity_dict = self._convert_to_entity_dict(entity)

                # Get entity text - try different approaches based on entity type
                entity_text = self._get_entity_text(entity_dict, full_text)

                if not entity_text:
                    log_warning(f"[WARNING] Could not determine entity text, skipping entity")
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
                logger.error(f"Entity data: {entity}")

        # Create page redaction info
        page_redaction_info = {
            "page": page_number,
            "sensitive": page_sensitive
        }

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