import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

class TextUtils:
    @staticmethod
    def reconstruct_text_and_mapping(words):
        """
        Reconstructs the full text from a list of word dictionaries and builds a mapping
        from each word to its start and end character offsets.
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
    def map_offsets_to_bboxes(full_text, mapping, sensitive_offsets):
        """
        Maps a sensitive text span (given as character offsets) to a bounding box.
        Ensures bounding boxes are calculated per line to prevent covering unnecessary text.

        :param full_text: Full extracted text
        :param mapping: List of tuples with (word_data, start_offset, end_offset)
        :param sensitive_offsets: Tuple of (start, end) offsets for the entity
        :return: List of bounding box dicts [{"x0", "y0", "x1", "y1"}, ...] or empty list
        """
        s_start, s_end = sensitive_offsets
        word_bboxes = []

        for word, w_start, w_end in mapping:
            # Ensure word overlaps with the entity's offset
            if w_end < s_start or w_start > s_end:
                continue  # Skip words outside the entity span

            # ✅ Reduce box size slightly to prevent overlap
            word_bboxes.append({
                "x0": word["x0"],
                "y0": word["y0"] + 2,  # 🔹 Shift box down slightly
                "x1": word["x1"],
                "y1": word["y1"] - 2  # 🔹 Reduce height slightly
            })

        # 🚨 Prevent empty results
        if not word_bboxes:
            logger.warning(f"⚠️ No valid bounding box found for entity at {s_start}-{s_end}")
            return []

        # ✅ Group words by y0 to handle multi-line entities
        lines = defaultdict(list)
        for bbox in word_bboxes:
            lines[bbox["y0"]].append(bbox)

        # ✅ Create separate bounding boxes per line
        bboxes_per_line = []
        for y0, boxes in sorted(lines.items()):
            x0 = min(b["x0"] for b in boxes)
            x1 = max(b["x1"] for b in boxes)
            y1 = max(b["y1"] for b in boxes)  # Keep correct height per line

            # ✅ Limit max height to avoid blocking text above
            max_height = 40  # 🔹 Adjust this if needed
            if (y1 - y0) > max_height:
                y1 = y0 + max_height  # 🔹 Reduce box height

            bboxes_per_line.append({
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1
            })

        return bboxes_per_line

    @staticmethod
    def recompute_offsets(full_text, entity_text):
        """
        Finds all occurrences of an entity inside the full extracted text.

        :param full_text: The extracted text from the PDF.
        :param entity_text: The entity text detected by Presidio or NER.
        :return: List of tuples [(start, end), (start, end), ...] for all occurrences.
        """
        entity_text = entity_text.strip()
        matches = []

        # Search for all occurrences of entity_text in full_text
        start_positions = [i for i in range(len(full_text)) if full_text.startswith(entity_text, i)]

        if start_positions:
            for start in start_positions:
                end = start + len(entity_text)
                matches.append((start, end))  # Store each match

        if not matches:
            logger.warning(f"⚠️ No match found for entity: '{entity_text}' in full_text")

        return matches  # Return all detected matches

    @staticmethod
    def merge_overlapping_entities(entities):
        """
        Merges overlapping entities by keeping the longest span.
        If two entities overlap, we merge them into a single entity.

        :param entities: List of RecognizerResult entities
        :return: List of merged entities
        """
        if not entities:
            return []

        # Sort entities by start index
        entities.sort(key=lambda e: e.start)

        merged_entities = []
        prev_entity = entities[0]

        for curr_entity in entities[1:]:
            # Check if entities overlap (allow partial overlap)
            if curr_entity.start <= prev_entity.end:
                # Merge by keeping the longest span
                prev_entity.start = min(prev_entity.start, curr_entity.start)
                prev_entity.end = max(prev_entity.end, curr_entity.end)
                prev_entity.score = max(prev_entity.score, curr_entity.score)  # Keep the highest confidence score
            else:
                merged_entities.append(prev_entity)
                prev_entity = curr_entity

        # Append the last entity
        merged_entities.append(prev_entity)

        return merged_entities

