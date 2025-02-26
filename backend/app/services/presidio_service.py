import os

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerResult

from presidio_analyzer.nlp_engine import NlpEngineProvider, NerModelConfiguration
from presidio_anonymizer import AnonymizerEngine

from backend.app.configs.presidio_config import (
    DEFAULT_LANGUAGE, ENTITIES_CONFIG, REQUESTED_ENTITIES, SPACY_MODEL, NER_MODEL, NER_MODEL_DIR_NAME
)
from backend.app.utils.logger import default_logger as logger
from backend.app.utils.helpers.ml_models_helper import get_spacy_model, get_hf_ner_pipeline
from backend.app.utils.helpers.json_helper import presidiotojsonconverter, print_analyzer_results
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

        # Configure NerModel
        ner_model_config = NerModelConfiguration(model_to_presidio_entity_mapping={"GPE_LOC": "LOCATION"})
        ner_model_config.labels_to_ignore.update(["GPE_LOC", "DRV", "PROD"])
        try:
            self.analyzer.registry.set_configuration(ner_model_config)
            logger.info("✅ Updated NerModelConfiguration via set_configuration().")
        except Exception as e:
            logger.warning(f"⚠️ Could not update NerModelConfiguration: {e}")

        # Initialize custom NER pipeline
        MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"../models/local_{NER_MODEL_DIR_NAME}")
        self.ner_pipeline = get_hf_ner_pipeline(NER_MODEL, cache_dir=MODEL_DIR)
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
                        RecognizerResult(entity_type=e["entity_group"], start=e["start"], end=e["end"],
                                         score=float(e["score"]))
                        for e in ner_results if
                        e["entity_group"] in ["PER", "LOC", "DATE", "MISC", "GPE", "PROD", "EVT", "DRV"]
                    ])
                except Exception as e:
                    logger.error(f"❌ Custom NER pipeline failed on page {page_number}: {e}")

            combined_results.extend(page_results)

            # Map detected sensitive spans to bounding boxes
            page_sensitive = [
                {"entity_type": res.entity_type, "start": res.start, "end": res.end, "score": res.score,
                 "bbox": TextUtils.map_offsets_to_bboxes(full_text, mapping, (res.start, res.end))}
                for res in page_results if TextUtils.map_offsets_to_bboxes(full_text, mapping, (res.start, res.end))
            ]

            redaction_mapping["pages"].append({"page": page_number, "sensitive": page_sensitive})

        anonymized_text = self.anonymizer.anonymize("\n".join(anonymized_texts), combined_results).text
        results_json = presidiotojsonconverter(combined_results)

        return anonymized_text, results_json, redaction_mapping
