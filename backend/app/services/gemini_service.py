import json
from backend.app.configs.gemini_config import AVAILABLE_ENTITIES
from backend.app.utils.logger import default_logger as logger
from backend.app.utils.helpers.gemini_helper import GeminiHelper
from backend.app.utils.helpers.text_utils import TextUtils


class GeminiService:
    """
    Service for interacting with the Gemini API to detect sensitive data.
    This service:
    - Reconstructs full text and word-to-offset mappings.
    - Sends text to Gemini API for entity detection.
    - Corrects incorrect entity offsets.
    - Maps corrected offsets to bounding boxes.
    """

    def __init__(self):
        self.gemini_helper = GeminiHelper()

    def detect_sensitive_data(self, extracted_data, requested_entities=None):
        """
        Detects sensitive entities in extracted text using the Gemini API.

        :param extracted_data: Dictionary containing text and bounding box information.
        :param requested_entities: List of entity types to detect.
        :return: (anonymized_text, results_json, redaction_mapping)
        """
        requested_entities = requested_entities or AVAILABLE_ENTITIES
        combined_results = []
        redaction_mapping = {"pages": []}
        anonymized_texts = []

        for page in extracted_data.get("pages", []):
            words = page.get("words", [])
            page_number = page.get("page")

            if not words:
                redaction_mapping["pages"].append({"page": page_number, "sensitive": []})
                continue

            full_text, mapping = TextUtils.reconstruct_text_and_mapping(words)
            anonymized_texts.append(full_text)

            # Call Gemini API
            response = self.gemini_helper.process_text(full_text, requested_entities)
            if response is None:
                logger.error(f"❌ Gemini API processing failed on page {page_number}.")
                redaction_mapping["pages"].append({"page": page_number, "sensitive": []})
                continue

            page_sensitive = []
            for page_data in response.get("pages", []):
                for text_entry in page_data.get("text", []):
                    for entity in text_entry.get("entities", []):
                        entity_text = entity["original_text"]

                        # Fix incorrect offsets
                        fixed_start, fixed_end = TextUtils.recompute_offsets(full_text, entity_text)
                        if fixed_start is None or fixed_end is None:
                            continue  # Skip if we cannot match the entity

                        # Map corrected offsets to bounding boxes
                        bbox = TextUtils.map_offsets_to_bboxes(full_text, mapping, (fixed_start, fixed_end))

                        if bbox:
                            page_sensitive.append({
                                "entity_type": entity["entity_type"],
                                "start": fixed_start,
                                "end": fixed_end,
                                "score": entity["score"],
                                "bbox": bbox
                            })

                        combined_results.append({
                            "entity_type": entity["entity_type"],
                            "start": fixed_start,
                            "end": fixed_end,
                            "score": entity["score"]
                        })

            redaction_mapping["pages"].append({"page": page_number, "sensitive": page_sensitive})

        anonymized_text = "\n".join(anonymized_texts)
        return anonymized_text, combined_results, redaction_mapping
