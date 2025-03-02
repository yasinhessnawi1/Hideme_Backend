import json
from collections import namedtuple

import spacy
from gliner_spacy.pipeline import GlinerSpacy

from backend.app.utils.helpers.text_utils import TextUtils, logger


class Gliner:
    """
    A spaCy pipeline component for integrating GLiNER.
    """

    def detect_entities(self, extracted_data: dict, labels = None):
        """
        Detect entities in text  using GLiNER.

        :param text:
        :return: A list of detected entities.
        """
        logger.info("🔍 Detecting these requested entities using GLiNER..." + labels)
        custom_spacy_config = {
            "gliner_model": "urchade/gliner_multi_pii-v1",
            "chunk_size": 250,
            "labels": json.loads(labels),
            "style": "ent",
            "threshold": 0.3,
            "map_location": "cpu",  # only available in v.0.0.7
        }
        nlp = spacy.blank("nb")
        nlp.add_pipe("gliner_spacy", config=custom_spacy_config)
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




            doc = nlp(full_text)
            page_results = []
            for ent in doc.ents:
                page_results.append(EntityResult(
                    entity_type=ent.label_,
                    start=ent.start_char,
                    end=ent.end_char,
                    score=ent._.score  # Using your custom attribute
                ))

            combined_results.extend(page_results)

            page_sensitive = []
            for res in page_results:
                entity_text = full_text[res.start:res.end]

                # ✅ Ensure recompute_offsets returns (start, end)
                matches = TextUtils.recompute_offsets(full_text, entity_text)

                # If there are multiple matches, process each one separately
                if matches:
                    for recomputed_start, recomputed_end in matches:
                        mapped_bboxes = TextUtils.map_offsets_to_bboxes(full_text, mapping,
                                                                        (recomputed_start, recomputed_end))

                        if mapped_bboxes:
                            for bbox in mapped_bboxes:  # ✅ Loop over multiple bounding boxes
                                page_sensitive.append({
                                    "original_text": full_text[recomputed_start:recomputed_end],
                                    "entity_type": res.entity_type,
                                    "start": recomputed_start,
                                    "end": recomputed_end,
                                    "score": res.score,
                                    "bbox": bbox  # ✅ Now stores correct per-line bounding boxes!
                                })

                else:
                    logger.warning(f"⚠️ No matches found for entity '{entity_text}', skipping.")

            # Store results for this page
            redaction_mapping["pages"].append({"page": page_number, "sensitive": page_sensitive})


        return redaction_mapping




