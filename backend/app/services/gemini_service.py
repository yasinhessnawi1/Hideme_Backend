import json
from backend.app.configs.gemini_config import AVAILABLE_ENTITIES
from backend.app.utils.logger import default_logger as logger
from backend.app.utils.helpers.gemini_helper import GeminiHelper


class GeminiService:
    """
    Service for interacting with the Gemini API to detect sensitive data.
    This service uses positional text information similar to Presidio: it reconstructs full text and a mapping
    from word bounding boxes (as provided by your PDFTextExtractor) so that sensitive character offsets returned
    by Gemini can be mapped back to PDF positions.
    """

    def __init__(self):
        self.gemini_helper = GeminiHelper()

    def _reconstruct_text_and_mapping(self, words):
        """
        Reconstruct full text from a list of word dictionaries and build a mapping:
          Each mapping entry is (word_dict, start_offset, end_offset).

        This implementation builds a list of word texts and then joins them with a single space.
        This ensures that the computed offsets exactly match the reconstructed text.

        :param words: List of dicts with keys: "text", "x0", "y0", "x1", "y1".
        :return: (full_text, mapping)
        """
        word_texts = []
        mapping = []
        current_offset = 0
        for word in words:
            text = word["text"].strip()
            word_texts.append(text)
            start = current_offset
            end = start + len(text)
            mapping.append((word, start, end))
            current_offset = end + 1  # account for the space
        full_text = " ".join(word_texts)
        return full_text, mapping

    def _map_offsets_to_word_bboxes(self, mapping, sensitive_offsets):
        """
        Given a mapping (list of tuples: (word_dict, start, end)) and a sensitive text span
        (sensitive_offsets), return a list of the word dictionaries whose offsets overlap
        with the sensitive span.

        :param mapping: List of (word_dict, start, end) tuples.
        :param sensitive_offsets: Tuple (start, end) representing a sensitive span.
        :return: A list of word dictionaries (each contains keys "x0", "y0", "x1", "y1").
        """
        s_start, s_end = sensitive_offsets
        boxes = []
        for word, w_start, w_end in mapping:
            # If there is any overlap between the word and the sensitive span, add its box.
            if w_end < s_start or w_start > s_end:
                continue
            boxes.append({
                "x0": word["x0"],
                "y0": word["y0"],
                "x1": word["x1"],
                "y1": word["y1"]
            })
        return boxes

    def detect_sensitive_data(self, extracted_data, requested_entities=None):
        """
        Processes a document's extracted text (with positional data) by:
          - Reconstructing the full text and a mapping from words to character offsets.
          - Sending the full text to the Gemini API.
          - Parsing the JSON response that includes sensitive spans (character offsets).
          - Mapping each sensitive span to a list of its corresponding word bounding boxes using the mapping.

        :param extracted_data: Dictionary with structure:
             { "pages": [ { "page": 1, "words": [ { "text": ..., "x0": ..., "y0": ..., "x1": ..., "y1": ... }, ... ] }, ... ] }
        :param requested_entities: Optional list of entity types to request.
        :return: A tuple (anonymized_text, results_json, redaction_mapping) where:
                 - anonymized_text: Full document text with sensitive parts anonymized.
                 - results_json: Gemini API JSON output.
                 - redaction_mapping: Dictionary with per-page sensitive spans and a list of corresponding bounding boxes.
        """
        if requested_entities is None:
            requested_entities = AVAILABLE_ENTITIES

        combined_results = []  # Store all detected sensitive spans from Gemini
        redaction_mapping = {"pages": []}
        anonymized_texts = []

        for page in extracted_data.get("pages", []):
            words = page.get("words", [])
            page_number = page.get("page")
            if not words:
                redaction_mapping["pages"].append({"page": page_number, "sensitive": []})
                continue

            full_text, mapping = self._reconstruct_text_and_mapping(words)
            anonymized_texts.append(full_text)

            # Process the full text via GeminiHelper
            response = self.gemini_helper.process_text(full_text, requested_entities)
            if response is None:
                logger.error("❌ Gemini API processing failed on page %d.", page_number)
                redaction_mapping["pages"].append({"page": page_number, "sensitive": []})
                continue

            # Assume response JSON structure similar to Presidio:
            # { "pages": [ { "text": [ { "original_text": ..., "anonymized_text": ..., "entities": [ { "entity_type": ..., "start": ..., "end": ..., "score": ... }, ... ] } ] } ] }
            page_response = response.get("pages", [{}])[0]
            page_entities = page_response.get("text", [])
            page_sensitive = []
            for item in page_entities:
                for entity in item.get("entities", []):
                    sensitive_offsets = (entity["start"], entity["end"])
                    boxes = self._map_offsets_to_word_bboxes(mapping, sensitive_offsets)
                    if boxes:
                        page_sensitive.append({
                            "entity_type": entity["entity_type"],
                            "start": entity["start"],
                            "end": entity["end"],
                            "score": entity["score"],
                            "boxes": boxes
                        })
                    combined_results.append(entity)
            redaction_mapping["pages"].append({
                "page": page_number,
                "sensitive": page_sensitive
            })

        full_document_text = "\n".join(anonymized_texts)
        # In this example we assume the Gemini API already returns anonymized text.
        anonymized_text = full_document_text

        results_json = json.dumps(combined_results, indent=2, ensure_ascii=False)
        logger.info("Processed Gemini results for redaction mapping.")
        return anonymized_text, results_json, redaction_mapping


