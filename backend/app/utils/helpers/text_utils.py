import logging

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
        Maps a sensitive text span (given as character offsets) to a bounding box that covers all overlapping words.
        """
        s_start, s_end = sensitive_offsets
        x0s, y0s, x1s, y1s = [], [], [], []

        for word, w_start, w_end in mapping:
            if w_end < s_start or w_start > s_end:
                continue
            x0s.append(word["x0"])
            y0s.append(word["y0"])
            x1s.append(word["x1"])
            y1s.append(word["y1"])

        if x0s and y0s and x1s and y1s:
            return {
                "x0": min(x0s),
                "y0": min(y0s),
                "x1": max(x1s),
                "y1": max(y1s)
            }
        return None

    @staticmethod
    def recompute_offsets(full_text, entity_text):
        """
        Recomputes the start and end offsets for an entity using substring search.
        """
        start = full_text.find(entity_text)
        if start == -1:
            logger.warning(f"⚠️ Could not find exact match for entity: {entity_text}")
            return None, None
        end = start + len(entity_text)
        return start, end
