from collections import namedtuple
import spacy

from backend.app.utils.helpers.text_utils import TextUtils, logger

# ✅ Load GLiNER model only once
custom_spacy_config = {
    "gliner_model": "urchade/gliner_multi_pii-v1",
    "chunk_size": 250,
    "style": "ent",
    "threshold": 0.3,
    "map_location": "cpu",
}

nlp = spacy.blank("nb")  # Load spaCy pipeline once
nlp.add_pipe("gliner_spacy", config=custom_spacy_config)  # Load GLiNER once

class Gliner:
    """
    A spaCy pipeline component for integrating GLiNER.
    """

    def detect_entities(self, extracted_data: dict, labels=None):
        """
        Detect entities in text using GLiNER.

        :param extracted_data: The input dictionary containing text.
        :param labels: JSON string with entity labels.
        :return: A list of detected entities.
        """
        logger.info(f"🔍 Detecting these requested entities using GLiNER... {labels}")

        EntityResult = namedtuple("EntityResult", ["entity_type", "start", "end", "score"])

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

            # ✅ Reuse the global `nlp` pipeline instead of reloading every time
            doc = nlp(full_text)

            page_results = []
            for ent in doc.ents:
                score = getattr(ent._, "score", None)  # ✅ Fix potential attribute error
                if score is None:
                    score = 1.0  # Default score if missing

                page_results.append(EntityResult(
                    entity_type=ent.label_,
                    start=ent.start_char,
                    end=ent.end_char,
                    score=score
                ))

            combined_results.extend(page_results)

            page_sensitive = []
            for res in page_results:
                entity_text = full_text[res.start:res.end]

                matches = TextUtils.recompute_offsets(full_text, entity_text)

                if matches:
                    for recomputed_start, recomputed_end in matches:
                        mapped_bboxes = TextUtils.map_offsets_to_bboxes(full_text, mapping,
                                                                        (recomputed_start, recomputed_end))

                        if mapped_bboxes:
                            for bbox in mapped_bboxes:
                                page_sensitive.append({
                                    "original_text": full_text[recomputed_start:recomputed_end],
                                    "entity_type": res.entity_type,
                                    "start": recomputed_start,
                                    "end": recomputed_end,
                                    "score": res.score,
                                    "bbox": bbox
                                })

                else:
                    logger.warning(f"⚠️ No matches found for entity '{entity_text}', skipping.")

            redaction_mapping["pages"].append({"page": page_number, "sensitive": page_sensitive})

        return redaction_mapping
