"""
Utility functions for text processing and entity handling.

This module provides classes for:
- Reconstructing full text from word components and mapping their character offsets.
- Mapping text offsets to bounding boxes with customizable padding.
- Recomputing entity offsets by finding all occurrences of an entity string.
- Merging multiple bounding boxes into a single encompassing box.
- Merging overlapping entities by retaining the longest spans.
"""

from collections import defaultdict
from typing import Dict, List, Tuple, Any

from presidio_analyzer import RecognizerResult

from backend.app.utils.logging.logger import log_warning


class TextUtils:
    """Utilities for text processing and entity mapping."""

    @staticmethod
    def reconstruct_text_and_mapping(
        words: List[Dict[str, Any]],
    ) -> Tuple[str, List[Tuple[Dict[str, Any], int, int]]]:
        """
        Reconstructs the full text from a list of word dictionaries and builds a mapping
        from each word to its start and end character offsets.

        Args:
            words: List of word dictionaries with text and position information.

        Returns:
            Tuple of (full_text, mapping)
            - full_text: The complete text string.
            - mapping: A list of tuples (word_dict, start_offset, end_offset).
        """
        # Initialize a list to hold individual word texts.
        word_texts = []
        # Initialize a list to hold the mapping tuples.
        mapping = []
        # Set the starting character offset to 0.
        current_offset = 0

        # Loop over each word dictionary in the provided list.
        for word in words:
            # Retrieve the 'text' value from the word dictionary and strip whitespace.
            text = word["text"].strip()
            # Skip processing if the text is empty.
            if not text:
                continue  # Skip empty words.
            # Append the cleaned text to the list of word texts.
            word_texts.append(text)
            # Record the starting offset for this word.
            start = current_offset
            # Calculate the ending offset for this word.
            end = start + len(text)
            # Append a tuple containing the word dictionary and its start and end offsets.
            mapping.append((word, start, end))
            # Update the current offset: add the length of the word and one extra character for the space.
            current_offset = end + 1

        # Join all word texts with a space to form the full text.
        full_text = " ".join(word_texts)
        # Return the full text along with the mapping.
        return full_text, mapping

    @staticmethod
    def map_offsets_to_bboxes(
        full_text: str,
        mapping: List[Tuple[Dict[str, Any], int, int]],
        sensitive_offsets: Tuple[int, int],
        padding: Dict[str, int] = None,
    ) -> List[Dict[str, float]]:
        """
        Maps a sensitive text span (given as character offsets) to bounding boxes.
        Ensures bounding boxes are calculated per line to prevent covering unnecessary text.

        Args:
            full_text: Full extracted text.
            mapping: List of tuples with (word_data, start_offset, end_offset).
            sensitive_offsets: Tuple of (start, end) offsets for the entity.
            padding: Optional dict with custom padding values (keys: top, right, bottom, left).

        Returns:
            List of bounding box dictionaries [{"x0": float, "y0": float, "x1": float, "y1": float}, ...].
        """
        # Unpack the sensitive offset start and end.
        s_start, s_end = sensitive_offsets
        # Initialize an empty list to accumulate word bounding boxes.
        word_bboxes = []

        # If no padding is provided, set the default padding values.
        if padding is None:
            padding = {"top": 2, "right": 0, "bottom": 2, "left": 0}

        # Iterate over each (word, start, end) tuple in the mapping.
        for word, w_start, w_end in mapping:
            # Check if the word's offset does not intersect with the sensitive range.
            if w_end < s_start or w_start > s_end:
                continue  # Skip words outside the entity span.
            # Append a new bounding box dictionary for the word with adjusted padding.
            word_bboxes.append(
                {
                    "x0": word["x0"] - padding["left"],  # Adjust left boundary.
                    "y0": word["y0"] + padding["top"],  # Adjust top boundary.
                    "x1": word["x1"] + padding["right"],  # Adjust right boundary.
                    "y1": word["y1"] - padding["bottom"],  # Adjust bottom boundary.
                }
            )

        # If no bounding boxes were identified, log a warning and return an empty list.
        if not word_bboxes:
            log_warning(
                f"[OK] No valid bounding box found for entity at {s_start}-{s_end}"
            )
            return []

        # Initialize a default dictionary to group bounding boxes by their y0 coordinate (line start).
        lines = defaultdict(list)
        # Loop over each bounding box.
        for bbox in word_bboxes:
            # Group the box under its y0 key.
            lines[bbox["y0"]].append(bbox)

        # Initialize a list to hold the final bounding boxes per line.
        bboxes_per_line = []
        # Process each line group sorted by y0 coordinate.
        for y0, boxes in sorted(lines.items()):
            # Determine the minimum x0 among the boxes on this line.
            x0 = min(b["x0"] for b in boxes)
            # Determine the maximum x1 among the boxes on this line.
            x1 = max(b["x1"] for b in boxes)
            # Determine the maximum y1 among the boxes on this line.
            y1 = max(b["y1"] for b in boxes)
            # Set a maximum allowed height for the bounding box.
            max_height = 40
            # Adjust y1 if the height exceeds the maximum.
            if (y1 - y0) > max_height:
                y1 = y0 + max_height
            # Append the computed bounding box for the line.
            bboxes_per_line.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1})

        # Return the list of bounding boxes per line.
        return bboxes_per_line

    @staticmethod
    def recompute_offsets(full_text: str, entity_text: str) -> List[Tuple[int, int]]:
        """
        Finds all occurrences of an entity inside the full extracted text.

        Args:
            full_text: The extracted text from the document.
            entity_text: The entity text detected by an entity detector.

        Returns:
            List of tuples [(start, end), ...] for all occurrences.
        """
        # Remove any extra whitespace from the entity_text.
        entity_text = entity_text.strip()
        # Initialize a list to store all matching offsets.
        matches = []

        # Iterate over all positions in full_text where the text starts with entity_text.
        start_positions = [
            i for i in range(len(full_text)) if full_text.startswith(entity_text, i)
        ]

        # If any starting positions are found, compute their end positions.
        if start_positions:
            for start in start_positions:
                # Calculate the end position as the start plus the length of the entity_text.
                end = start + len(entity_text)
                # Append the (start, end) tuple to the list of matches.
                matches.append((start, end))

        # Log a warning if no matches were found.
        if not matches:
            log_warning("[OK] No match found for entity in full text")

        # Return the list of matching offsets.
        return matches

    @staticmethod
    def _cap_height(box: Dict[str, Any], max_height: float) -> Dict[str, Any]:
        """
        Limit the height of a bounding box to max_height.

        Args:
            box: A bounding box dictionary with keys "x0", "y0", "x1", "y1".
            max_height: The maximum allowed height of the merged box.

        Returns:
            The bounding box with its height capped if it exceeds max_height.
        """
        # Compute the height of the box.
        if (box["y1"] - box["y0"]) > max_height:
            # Adjust the bottom coordinate so the height equals max_height.
            box["y1"] = box["y0"] + max_height
        return box

    @staticmethod
    def _merge_group(boxes: List[Dict[str, Any]], max_height: float) -> Dict[str, Any]:
        """
        Merge a list of bounding boxes into one bounding box.

        Args:
            boxes: A list of bounding boxes to merge.
            max_height: The maximum allowed height for the merged box.

        Returns:
            A single bounding box covering all input boxes, with its height capped.
        """
        # Calculate the smallest x0 and y0 from all boxes.
        merged = {
            "x0": min(b["x0"] for b in boxes),  # Left boundary: smallest x0.
            "y0": min(b["y0"] for b in boxes),  # Top boundary: smallest y0.
            "x1": max(b["x1"] for b in boxes),  # Right boundary: largest x1.
            "y1": max(b["y1"] for b in boxes),  # Bottom boundary: largest y1.
        }
        # Apply height restriction to ensure the merged box doesn't exceed max_height.
        return TextUtils._cap_height(merged, max_height)

    @staticmethod
    def merge_bounding_boxes(bboxes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Merge multiple bounding boxes into a composite box along with per-line boxes.

        The function uses a vertical threshold of 5.0 pixels to decide whether boxes belong
        to the same line. It then merges boxes in each line individually and also merges all boxes
        into a single (composite) box. The maximum allowed height is set to 20 pixels.

        Args:
            bboxes: A list of bounding box dictionaries each with keys "x0", "y0", "x1", "y1".

        Returns:
            A dictionary with:
              - "composite": A merged bounding box covering all input boxes.
              - "lines": A list of merged bounding boxes for each detected line.

        Raises:
            ValueError: If the input list is empty.
        """
        # Validate that there is at least one bounding box.
        if not bboxes:
            raise ValueError("No bounding boxes to merge.")

        # If only one box exists, return it for both composite and per-line.
        if len(bboxes) == 1:
            return {"composite": bboxes[0], "lines": [bboxes[0]]}

        # Define the threshold for grouping boxes on the same line.
        line_threshold = 5.0
        # Define the maximum height allowed for a merged box.
        max_height = 20

        # Sort the input boxes by their top coordinate (y0)
        bboxes.sort(key=lambda b: b["y0"])

        # Group boxes into lines: boxes whose y0 values differ by less than or equal to line_threshold.
        groups: List[List[Dict[str, Any]]] = []
        current_group = [bboxes[0]]  # Start the first group with the first box.
        for bbox in bboxes[1:]:
            # If the current box is nearly on the same line as the previous one...
            if abs(bbox["y0"] - current_group[-1]["y0"]) <= line_threshold:
                current_group.append(bbox)  # Add it to the current group.
            else:
                groups.append(current_group)  # Save the finished group.
                current_group = [bbox]  # Start a new group.
        groups.append(current_group)  # Append the final group.

        # Merge each group into a single bounding box.
        merged_lines = [TextUtils._merge_group(group, max_height) for group in groups]

        # Merge all boxes together to form a composite bounding box.
        composite_box = TextUtils._merge_group(bboxes, max_height)

        # Return a dictionary with both the composite bounding box and per-line merged boxes.
        return {"composite": composite_box, "lines": merged_lines}


class EntityUtils:
    """Utilities for processing and manipulating entities."""

    @staticmethod
    def merge_overlapping_entities(
        entities: List[RecognizerResult],
    ) -> List[RecognizerResult]:
        """
        Merges overlapping entities by keeping the longest span.

        Note: This method is specific to Presidio RecognizerResult objects.
        For generic entity dictionaries, use merge_overlapping_entity_dicts().

        Args:
            entities: List of entity results (must have start, end, and score attributes).

        Returns:
            List of merged entities.
        """
        # Return an empty list if there are no entities to process.
        if not entities:
            return []

        # Sort the entities in ascending order based on their start index.
        entities.sort(key=lambda e: e.start)
        # Initialize an empty list to store the merged entities.
        merged_entities = []
        # Set the first entity as the initial previous entity for comparison.
        prev_entity = entities[0]

        # Iterate over the remaining entities.
        for curr_entity in entities[1:]:
            # Check if the current entity overlaps with the previous entity.
            if curr_entity.start <= prev_entity.end:
                # Merge overlapping entities by taking the minimum start and maximum end.
                prev_entity.start = min(prev_entity.start, curr_entity.start)
                prev_entity.end = max(prev_entity.end, curr_entity.end)
                # Update the score to be the maximum of the two scores.
                prev_entity.score = max(prev_entity.score, curr_entity.score)
            else:
                # Append the non-overlapping previous entity to the merged list.
                merged_entities.append(prev_entity)
                # Update the previous entity to the current one.
                prev_entity = curr_entity

        # Append the last processed entity.
        merged_entities.append(prev_entity)
        # Return the list of merged entities.
        return merged_entities
