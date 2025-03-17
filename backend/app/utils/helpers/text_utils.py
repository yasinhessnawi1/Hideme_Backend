"""
Utility functions for text processing and entity handling.
"""
from collections import defaultdict
from typing import Dict, List, Tuple, Any, Union

from presidio_analyzer import RecognizerResult

from backend.app.utils.logger import log_warning



class TextUtils:
    """Utilities for text processing and entity mapping."""

    @staticmethod
    def reconstruct_text_and_mapping(words: List[Dict[str, Any]]) -> Tuple[str, List[Tuple[Dict[str, Any], int, int]]]:
        """
        Reconstructs the full text from a list of word dictionaries and builds a mapping
        from each word to its start and end character offsets.

        Args:
            words: List of word dictionaries with text and position information

        Returns:
            Tuple of (full_text, mapping)
            - full_text is the complete text string
            - mapping is a list of tuples (word_dict, start_offset, end_offset)
        """
        word_texts = []
        mapping = []
        current_offset = 0

        for word in words:
            text = word["text"].strip()
            if not text:
                continue  # Skip empty words

            word_texts.append(text)
            start = current_offset
            end = start + len(text)
            mapping.append((word, start, end))
            current_offset = end + 1  # Plus one for the space

        full_text = " ".join(word_texts)
        return full_text, mapping

    @staticmethod
    def map_offsets_to_bboxes(
        full_text: str,
        mapping: List[Tuple[Dict[str, Any], int, int]],
        sensitive_offsets: Tuple[int, int],
        padding: Dict[str, int] = None
    ) -> List[Dict[str, float]]:
        """
        Maps a sensitive text span (given as character offsets) to bounding boxes.
        Ensures bounding boxes are calculated per line to prevent covering unnecessary text.

        Args:
            full_text: Full extracted text
            mapping: List of tuples with (word_data, start_offset, end_offset)
            sensitive_offsets: Tuple of (start, end) offsets for the entity
            padding: Optional dict with custom padding values (keys: top, right, bottom, left)

        Returns:
            List of bounding box dicts [{"x0": float, "y0": float, "x1": float, "y1": float}, ...]
        """
        s_start, s_end = sensitive_offsets
        word_bboxes = []

        # Set default padding if not provided
        if padding is None:
            padding = {"top": 2, "right": 0, "bottom": 2, "left": 0}

        for word, w_start, w_end in mapping:
            # Ensure word overlaps with the entity's offset
            if w_end < s_start or w_start > s_end:
                continue  # Skip words outside the entity span

            # Apply padding to the bounding box
            word_bboxes.append({
                "x0": word["x0"] - padding["left"],
                "y0": word["y0"] + padding["top"],
                "x1": word["x1"] + padding["right"],
                "y1": word["y1"] - padding["bottom"]
            })

        # Check for empty results
        if not word_bboxes:
            log_warning(f"[OK] No valid bounding box found for entity at {s_start}-{s_end}")
            return []

        # Group words by y0 to handle multi-line entities
        lines = defaultdict(list)
        for bbox in word_bboxes:
            lines[bbox["y0"]].append(bbox)

        # Create separate bounding boxes per line
        bboxes_per_line = []
        for y0, boxes in sorted(lines.items()):
            x0 = min(b["x0"] for b in boxes)
            x1 = max(b["x1"] for b in boxes)
            y1 = max(b["y1"] for b in boxes)

            # Limit max height if needed
            max_height = 40
            if (y1 - y0) > max_height:
                y1 = y0 + max_height

            bboxes_per_line.append({
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1
            })

        return bboxes_per_line

    @staticmethod
    def recompute_offsets(full_text: str, entity_text: str) -> List[Tuple[int, int]]:
        """
        Finds all occurrences of an entity inside the full extracted text.

        Args:
            full_text: The extracted text from the document
            entity_text: The entity text detected by an entity detector

        Returns:
            List of tuples [(start, end), ...] for all occurrences
        """
        entity_text = entity_text.strip()
        matches = []

        # Search for all occurrences of entity_text in full_text
        start_positions = [i for i in range(len(full_text)) if full_text.startswith(entity_text, i)]

        if start_positions:
            for start in start_positions:
                end = start + len(entity_text)
                matches.append((start, end))

        if not matches:
            log_warning(f"[OK] No match found for entity: '{entity_text}' in full text")

        return matches


class EntityUtils:
    """Utilities for processing and manipulating entities."""

    @staticmethod
    def merge_overlapping_entities(entities: List[RecognizerResult]) -> List[RecognizerResult]:
        """
        Merges overlapping entities by keeping the longest span.

        Args:
            entities: List of entity results (must have start, end, and score attributes)

        Returns:
            List of merged entities
        """
        if not entities:
            return []

        # Sort entities by start index
        entities.sort(key=lambda e: e.start)

        merged_entities = []
        prev_entity = entities[0]

        for curr_entity in entities[1:]:
            # Check if entities overlap
            if curr_entity.start <= prev_entity.end:
                # Merge by keeping the longest span
                prev_entity.start = min(prev_entity.start, curr_entity.start)
                prev_entity.end = max(prev_entity.end, curr_entity.end)
                prev_entity.score = max(prev_entity.score, curr_entity.score)
            else:
                merged_entities.append(prev_entity)
                prev_entity = curr_entity

        # Add the last entity
        merged_entities.append(prev_entity)

        return merged_entities

    @staticmethod
    def convert_entity_to_dict(entity: Union[RecognizerResult, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Converts an entity to a dictionary format.

        Args:
            entity: Entity object or dictionary

        Returns:
            Standardized entity dictionary
        """
        if isinstance(entity, dict):
            return {
                "entity_type": entity.get("entity_type", "UNKNOWN"),
                "start": entity.get("start", 0),
                "end": entity.get("end", 0),
                "score": float(entity.get("score", 0.0))
            }
        else:
            return {
                "entity_type": entity.entity_type,
                "start": entity.start,
                "end": entity.end,
                "score": float(entity.score)
            }
    @staticmethod
    def merge_redaction_mappings(
            redaction_mappings: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Merge multiple redaction mappings into one.

        Args:
            redaction_mappings: List of redaction mappings to merge

        Returns:
            Merged redaction mapping
        """
        if not redaction_mappings:
            return {"pages": []}

        merged = {"pages": []}
        page_mappings = {}

        # Group mappings by page
        for mapping in redaction_mappings:
            for page_info in mapping.get("pages", []):
                page_num = page_info.get("page")
                sensitive_items = page_info.get("sensitive", [])

                if page_num not in page_mappings:
                    page_mappings[page_num] = []

                page_mappings[page_num].extend(sensitive_items)

        # Create merged mapping
        for page_num, sensitive_items in sorted(page_mappings.items()):
            merged["pages"].append({
                "page": page_num,
                "sensitive": sensitive_items
            })

        return merged


    @staticmethod
    def format_sensitive_entities(
        full_text: str,
        entities: List[Union[RecognizerResult, Dict[str, Any]]],
        bboxes: List[Dict[str, float]],
        start: int,
        end: int
    ) -> List[Dict[str, Any]]:
        """
        Formats sensitive entities with their bounding boxes.

        Args:
            full_text: Original text
            entities: List of entities
            bboxes: List of bounding boxes
            start: Start offset in the text
            end: End offset in the text

        Returns:
            List of formatted sensitive entities
        """
        result = []

        for entity in entities:
            entity_dict = EntityUtils.convert_entity_to_dict(entity)

            for bbox in bboxes:
                result.append({
                    "original_text": full_text[start:end],
                    "entity_type": entity_dict["entity_type"],
                    "start": start,
                    "end": end,
                    "score": entity_dict["score"],
                    "bbox": bbox
                })

        return result


class JsonUtils:
    """Utilities for JSON handling and conversion."""

    @staticmethod
    def presidio_to_json_converter(detected_entities: List[RecognizerResult], min_score: float = 0.5) -> List[Dict[str, Any]]:
        """
        Converts Presidio RecognizerResult objects to JSON-serializable dictionaries.

        Args:
            detected_entities: List of Presidio RecognizerResult objects
            min_score: Minimum confidence score threshold (default: 0.5)

        Returns:
            List of entity dictionaries
        """
        return [
            {
                "entity_type": e.entity_type,
                "start": e.start,
                "end": e.end,
                "score": float(e.score)
            }
            for e in detected_entities if e.score > min_score
        ]