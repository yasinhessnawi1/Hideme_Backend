import os
from presidio_analyzer import (
    AnalyzerEngine,
    Pattern,
    PatternRecognizer,
    RecognizerResult
)
from presidio_analyzer.nlp_engine import NlpEngineProvider, NerModelConfiguration
from presidio_anonymizer import AnonymizerEngine

from backend.app.configs.presidio_config import DEFAULT_LANGUAGE, ENTITIES_CONFIG, REQUESTED_ENTITIES, SPACY_MODEL, \
    NER_MODEL, NER_MODEL_DIR_NAME
from backend.app.utils.logger import default_logger as logger
from backend.app.utils.helpers.ml_models_helper import get_spacy_model, get_hf_ner_pipeline
from backend.app.utils.helpers.json_helper import PresidioToJsonConverter, print_analyzer_results


class PresidioService:
    """
    A service for detecting sensitive information using Presidio.
    Initializes the Analyzer and Anonymizer, registers custom recognizers from configuration,
    sets up a custom NER pipeline via helper functions, and maps detected character offsets
    to PDF word bounding boxes.
    """

    def __init__(self):
        spacy_model = SPACY_MODEL
        # Ensure spaCy model is loaded (download if needed)
        get_spacy_model(spacy_model)

        nlp_configuration = {
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": DEFAULT_LANGUAGE, "model_name": spacy_model}]
        }
        provider = NlpEngineProvider()
        provider.nlp_configuration = nlp_configuration
        spacy_nlp_engine = provider.create_engine()

        self.analyzer = AnalyzerEngine(nlp_engine=spacy_nlp_engine, supported_languages=[DEFAULT_LANGUAGE])
        self.anonymizer = AnonymizerEngine()

        # Register custom recognizers based on configuration.
        for entity, config in ENTITIES_CONFIG.items():
            patterns = []
            for pattern_def in config.get("patterns", []):
                patterns.append(Pattern(
                    name=pattern_def.get("name"),
                    regex=pattern_def.get("regex"),
                    score=pattern_def.get("score")
                ))
            recognizer = PatternRecognizer(
                supported_entity=entity,
                patterns=patterns,
                supported_language=DEFAULT_LANGUAGE
            )
            self.analyzer.registry.add_recognizer(recognizer)
            logger.info(f"✅ Registered custom recognizer for {entity}")

        # Update NerModelConfiguration to suppress warnings.
        ner_model_config = NerModelConfiguration(model_to_presidio_entity_mapping={"GPE_LOC": "LOCATION"})
        ner_model_config.labels_to_ignore.update(["GPE_LOC", "DRV", "PROD"])
        try:
            self.analyzer.registry.set_configuration(ner_model_config)
            logger.info("✅ Updated NerModelConfiguration via set_configuration().")
        except Exception as e:
            try:
                self.analyzer.registry._ner_model_config = ner_model_config
                logger.info("✅ Updated NerModelConfiguration via fallback assignment.")
            except Exception as ex:
                logger.warning(f"Could not update NerModelConfiguration: {ex}")

        # Set up the custom NER pipeline using the Kushtrim model via helper.
        MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 f"../models/local_{NER_MODEL_DIR_NAME}")
        self.ner_pipeline = get_hf_ner_pipeline(NER_MODEL, cache_dir=MODEL_DIR)
        if self.ner_pipeline:
            logger.info("✅ Custom NER pipeline initialized successfully!")
        else:
            logger.error("❌ Failed to initialize custom NER pipeline.")

    def _reconstruct_text_and_mapping(self, words):
        """
        Reconstructs the full text from a list of word dictionaries and builds a mapping
        from each word to its start and end character offsets in the reconstructed text.
        This implementation collects the stripped word texts and joins them with a single space,
        ensuring consistent offsets.

        :param words: List of dicts with keys: "text", "x0", "y0", "x1", "y1".
        :return: (full_text, mapping) where mapping is a list of tuples: (word_dict, start_offset, end_offset)
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
            current_offset = end + 1  # plus one for the space
        full_text = " ".join(word_texts)
        return full_text, mapping

    def _map_offsets_to_bboxes(self, full_text, mapping, sensitive_offsets):
        """
        Maps a sensitive text span (given as character offsets) to a bounding box that covers all overlapping words.

        :param full_text: The reconstructed full text.
        :param mapping: List of (word_dict, start, end) tuples.
        :param sensitive_offsets: Tuple (start, end) representing a sensitive span.
        :return: A dict with bounding box coordinates or None if not found.
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

    def detect_sensitive_data(self, extracted_data, requested_entities=None):
        """
        Detects sensitive entities in each page's text using Presidio Analyzer and the custom NER pipeline.
        Then, maps the detected character offsets (from the full text) back to PDF word bounding boxes using the mapping.

        :param extracted_data: Dictionary with structure:
             { "pages": [ { "page": 1, "words": [ { "text": ..., "x0": ..., "y0": ..., "x1": ..., "y1": ... }, ... ] }, ... ] }
        :param requested_entities: Optional list of entity types to detect.
        :return: A tuple (anonymized_text, results_json, redaction_mapping) where:
                 - anonymized_text: The full concatenated text with sensitive data anonymized.
                 - results_json: JSON-serializable structure with combined detection results.
                 - redaction_mapping: Dictionary with per-page sensitive spans and their bounding boxes.
        """
        if requested_entities is None:
            requested_entities = REQUESTED_ENTITIES


        combined_results = []
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

            # Run Presidio Analyzer on the reconstructed full text.
            page_results = self.analyzer.analyze(
                text=full_text, language=DEFAULT_LANGUAGE, entities=requested_entities
            )
            # Also run the custom NER pipeline if available.
            if self.ner_pipeline:
                try:
                    ner_results = self.ner_pipeline(full_text)
                    custom_results = [
                        RecognizerResult(
                            entity_type=entity["entity_group"],
                            start=entity["start"],
                            end=entity["end"],
                            score=float(entity["score"])
                        )
                        for entity in ner_results
                        if entity["entity_group"] in ["PER", "LOC", "DATE", "MISC", "GPE", "PROD", "EVT", "DRV"]
                    ]
                    page_results.extend(custom_results)
                except Exception as e:
                    logger.error(f"❌ Custom NER pipeline failed on page {page_number}: {e}")

            combined_results.extend(page_results)

            # Map each detected sensitive span to its bounding box.
            page_sensitive = []
            for res in page_results:
                bbox = self._map_offsets_to_bboxes(full_text, mapping, (res.start, res.end))
                if bbox:
                    page_sensitive.append({
                        "entity_type": res.entity_type,
                        "start": res.start,
                        "end": res.end,
                        "score": res.score,
                        "bbox": bbox
                    })
            redaction_mapping["pages"].append({"page": page_number, "sensitive": page_sensitive})

        full_document_text = "\n".join(anonymized_texts)
        anonymized_text = self.anonymizer.anonymize(full_document_text, combined_results).text

        results_json = PresidioToJsonConverter(combined_results)
        print_analyzer_results(combined_results, full_document_text)

        return anonymized_text, results_json, redaction_mapping
