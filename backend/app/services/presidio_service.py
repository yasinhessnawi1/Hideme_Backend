from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerResult

from presidio_analyzer.nlp_engine import NlpEngineProvider, NerModelConfiguration
from presidio_anonymizer import AnonymizerEngine

from backend.app.configs.presidio_config import (
    DEFAULT_LANGUAGE, ENTITIES_CONFIG, REQUESTED_ENTITIES, SPACY_MODEL, LOCAL_HF_MODEL_PATH
)
from backend.app.utils.logger import default_logger as logger
from backend.app.utils.helpers.ml_models_helper import get_spacy_model, get_hf_ner_pipeline
from backend.app.utils.helpers.json_helper import presidiotojsonconverter
from backend.app.utils.helpers.text_utils import TextUtils


class PresidioService:
    """
    A service for detecting sensitive information using Presidio.
    This class:
    - Initializes the Analyzer and Anonymizer.
    - Registers custom recognizers from configuration.
    - Sets up a custom NER pipeline.
    - Maps detected character offsets to PDF word bounding boxes.
    """

    def __init__(self):
        spacy_model = SPACY_MODEL
        get_spacy_model(spacy_model)  # Ensure spaCy model is loaded

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
            patterns = [Pattern(name=p["name"], regex=p["regex"], score=p["score"]) for p in config.get("patterns", [])]
            recognizer = PatternRecognizer(supported_entity=entity, patterns=patterns,
                                           supported_language=DEFAULT_LANGUAGE)
            self.analyzer.registry.add_recognizer(recognizer)
            logger.info(f"✅ Registered custom recognizer for {entity}")

        # Define the entity mapping for NER models
        ner_model_config = NerModelConfiguration(model_to_presidio_entity_mapping={"GPE_LOC": "LOCATION"})

        # Manually update entity mapping in the recognizer registry
        for entity, mapped_entity in ner_model_config.model_to_presidio_entity_mapping.items():
            if entity in self.analyzer.registry.recognizers:
                self.analyzer.registry.recognizers[entity].supported_entities = [mapped_entity]
        logger.info("✅ Manually updated NerModelConfiguration.")

        # Initialize custom NER pipeline
        self.ner_pipeline = get_hf_ner_pipeline(LOCAL_HF_MODEL_PATH)
        logger.info(
            "✅ Custom NER pipeline initialized successfully!" if self.ner_pipeline else "❌ Failed to initialize NER pipeline.")

    def detect_sensitive_data(self, extracted_data, requested_entities=None):
        """
        Detects sensitive entities in each page's text using Presidio Analyzer and the custom NER pipeline.
        Then, maps detected character offsets to bounding boxes.

        :param extracted_data: Dictionary containing text and bounding box information.
        :param requested_entities: List of entity types to detect.
        :return: (anonymized_text, results_json, redaction_mapping)
        """
        requested_entities = requested_entities or REQUESTED_ENTITIES

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

            # Run Presidio Analyzer
            page_results = self.analyzer.analyze(text=full_text, language=DEFAULT_LANGUAGE, entities=requested_entities)

            # Run custom NER pipeline if available
            if self.ner_pipeline:
                try:
                    ner_results = self.ner_pipeline(full_text)
                    page_results.extend([
                        RecognizerResult(
                            entity_type=e["entity_group"],
                            start=e["start"],
                            end=e["end"],
                            score=float(e["score"])
                        )
                        for e in ner_results if
                        e["entity_group"] in ["PER", "LOC", "DATE", "MISC", "GPE", "PROD", "EVT", "DRV"]
                    ])
                except Exception as e:
                    logger.error(f"❌ Custom NER pipeline failed on page {page_number}: {e}")

            # Merge overlapping entities before processing
            filtered_results = TextUtils.merge_overlapping_entities(page_results)
            combined_results.extend(filtered_results)

            page_sensitive = []
            for res in filtered_results:
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

        # Perform anonymization on the full text
        anonymized_text = self.anonymizer.anonymize("\n".join(anonymized_texts), combined_results).text
        results_json = presidiotojsonconverter(combined_results)

        return anonymized_text, results_json, redaction_mapping
