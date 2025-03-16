"""
Presidio entity detection implementation with enhanced GDPR compliance and error handling.

This module provides a robust implementation of entity detection using Microsoft Presidio
with improved security features, GDPR compliance, and standardized error handling.
"""
import asyncio
import os
import threading
import time
from typing import Dict, Any, List, Optional, Tuple, Union

from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_analyzer import AnalyzerEngineProvider
from presidio_anonymizer import AnonymizerEngine

from backend.app.configs.presidio_config import (DEFAULT_LANGUAGE, REQUESTED_ENTITIES)
from backend.app.entity_detection.base import BaseEntityDetector
from backend.app.utils.helpers.parallel_helper import ParallelProcessingHelper
from backend.app.utils.helpers.text_utils import TextUtils, EntityUtils
from backend.app.utils.logger import log_info, log_warning, log_error
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.data_minimization import minimize_extracted_data
from backend.app.utils.secure_logging import log_sensitive_operation
from backend.app.utils.processing_records import record_keeper


class PresidioEntityDetector(BaseEntityDetector):
    """
    Enhanced service for detecting sensitive information using Microsoft Presidio
    with robust async processing support and GDPR compliance features.
    """

    def __init__(self):
        """Initialize the Presidio entity detector using YAML configuration."""
        super().__init__()

        # Thread safety lock for analyzer
        self.analyzer_lock = threading.RLock()

        # Get the base directory for configuration files
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_dir = os.path.join(base_dir, "configs")

        # Define paths to configuration files
        analyzer_conf_file = os.path.join(config_dir, "analyzer-config.yml")
        nlp_engine_conf_file = os.path.join(config_dir, "nlp-config.yml")
        recognizer_registry_conf_file = os.path.join(config_dir, "recognizers-config.yml")

        # Check if configuration files exist
        missing_files = []
        for file_path in [analyzer_conf_file, nlp_engine_conf_file, recognizer_registry_conf_file]:
            if not os.path.exists(file_path):
                missing_files.append(file_path)

        with self.analyzer_lock:
            if missing_files:
                log_warning(f"[WARNING] Missing configuration files: {', '.join(missing_files)}")
                log_warning("[WARNING] Using default configuration")

                # Initialize with default configuration if files are missing
                self.analyzer = AnalyzerEngine(supported_languages=[DEFAULT_LANGUAGE])
            else:
                # Create analyzer engine from configuration files
                log_info("[OK] Loading Presidio configuration from YAML files")
                provider = AnalyzerEngineProvider(analyzer_engine_conf_file=analyzer_conf_file,
                                                  nlp_engine_conf_file=nlp_engine_conf_file,
                                                  recognizer_registry_conf_file=recognizer_registry_conf_file)
                self.analyzer = provider.create_engine()
                log_info("[OK] Successfully created analyzer engine from configuration")

            # Initialize anonymizer
            self.anonymizer = AnonymizerEngine()

    async def detect_sensitive_data_async(
        self,
        extracted_data: Dict[str, Any],
        requested_entities: Optional[List[str]] = None
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        """
        Asynchronous method to detect sensitive entities in extracted text.

        Args:
            extracted_data: Dictionary containing text and bounding box information
            requested_entities: List of entity types to detect

        Returns:
            Tuple of (anonymized_text, results_json, redaction_mapping)
        """
        start_time = time.time()
        requested_entities = requested_entities or REQUESTED_ENTITIES

        # Apply data minimization principles
        minimized_data = minimize_extracted_data(extracted_data)

        # Track processing for GDPR compliance
        operation_type = "presidio_detection"
        document_type = "document"

        try:
            # Extract all pages
            pages = minimized_data.get("pages", [])
            if not pages:
                # Return empty results for empty input
                return "", [], {"pages": []}

            # Define async page processing function
            async def process_page(page):
                """
                Process a single page for entity detection.

                Args:
                    page: Dictionary representing a page of text

                Returns:
                    Tuple of (page_redaction_info, processed_entities)
                """
                try:
                    page_number = page.get("page")
                    words = page.get("words", [])

                    if not words:
                        return {"page": page_number, "sensitive": []}, []

                    # Reconstruct text and mapping
                    full_text, mapping = TextUtils.reconstruct_text_and_mapping(words)

                    # Log processing step without including sensitive content
                    log_info(f"[OK] Processing page {page_number} with {len(words)} words")

                    # Detect entities using Presidio (run in thread)
                    page_results = await asyncio.to_thread(
                        self._analyze_text,
                        full_text,
                        DEFAULT_LANGUAGE,
                        requested_entities
                    )

                    # Merge overlapping entities
                    filtered_results = EntityUtils.merge_overlapping_entities(page_results)

                    if not filtered_results:
                        return {"page": page_number, "sensitive": []}, []

                    # Convert to entity dictionaries
                    entity_dicts = [self._convert_to_entity_dict(entity) for entity in filtered_results]

                    # Log entity count without including sensitive details
                    log_info(f"[OK] Found {len(entity_dicts)} entities on page {page_number}")

                    # Process entities
                    processed_entities, page_redaction_info = await ParallelProcessingHelper.process_entities_in_parallel(
                        self, full_text, mapping, entity_dicts, page_number
                    )

                    return page_redaction_info, processed_entities

                except Exception as e:
                    # Use standardized error handling
                    SecurityAwareErrorHandler.log_processing_error(
                        e, f"presidio_page_processing", f"page_{page.get('page', 'unknown')}"
                    )
                    return {"page": page.get('page', 0), "sensitive": []}, []

            # Process pages in parallel
            page_results = await ParallelProcessingHelper.process_pages_in_parallel(pages, process_page)

            # Collect results from parallel processing
            combined_results = []
            redaction_mapping = {"pages": []}
            anonymized_texts = []

            for page_number, (page_redaction_info, processed_entities) in page_results:
                if page_redaction_info:
                    redaction_mapping["pages"].append(page_redaction_info)

                    # Store text for anonymization
                    page_text = next((
                        TextUtils.reconstruct_text_and_mapping(page['words'])[0]
                        for page in pages if page.get('page') == page_number
                    ), "")
                    anonymized_texts.append(page_text)

                if processed_entities:
                    combined_results.extend(processed_entities)

            # Sort redaction mapping pages by page number
            redaction_mapping["pages"].sort(key=lambda x: x.get("page", 0))

            # Perform anonymization on the full text
            anonymized_text = await asyncio.to_thread(
                self._anonymize_text,
                "\n".join(anonymized_texts),
                combined_results
            )

            # Calculate processing time and track metrics
            total_time = time.time() - start_time
            self.update_usage_metrics(len(combined_results), total_time)

            # Record the processing operation for GDPR compliance
            record_keeper.record_processing(
                operation_type=operation_type,
                document_type=document_type,
                entity_types_processed=requested_entities,
                processing_time=total_time,
                entity_count=len(combined_results),
                success=True
            )

            # Log performance metrics without sensitive details
            log_sensitive_operation(
                "Presidio Detection",
                len(combined_results),
                total_time,
                pages=len(pages),
                entities_per_page=", ".join([
                    f"page_{info['page']}:{len(info['sensitive'])}"
                    for info in redaction_mapping["pages"]
                ])
            )

            return anonymized_text, combined_results, redaction_mapping

        except Exception as e:
            # Log error with standardized handling
            log_error(f"[ERROR] Error in Presidio detection: {str(e)}")

            # Record failed processing for GDPR compliance
            record_keeper.record_processing(
                operation_type=operation_type,
                document_type=document_type,
                entity_types_processed=requested_entities,
                processing_time=time.time() - start_time,
                entity_count=0,
                success=False
            )

            # Return empty results to avoid crashing
            return "", [], {"pages": []}

    def _analyze_text(self, text: str, language: str, entities: List[str]) -> List[RecognizerResult]:
        """
        Thread-safe wrapper for the Presidio analyzer's analyze method.

        Args:
            text: Text to analyze
            language: Language of the text
            entities: Entity types to detect

        Returns:
            List of recognized entities
        """
        with self.analyzer_lock:
            try:
                return self.analyzer.analyze(text=text, language=language, entities=entities)
            except Exception as e:
                # Use standardized error handling
                SecurityAwareErrorHandler.log_processing_error(e, "presidio_analysis")
                return []

    def _anonymize_text(self, text: str, entities: List[Dict[str, Any]]) -> str:
        """
        Anonymize text using Presidio Anonymizer.

        Args:
            text: Text to anonymize
            entities: List of detected entities

        Returns:
            Anonymized text
        """
        # Convert dictionary entities to RecognizerResult
        recognizer_results = []
        for entity in entities:
            try:
                recognizer_results.append(
                    RecognizerResult(
                        entity_type=entity["entity_type"],
                        start=entity["start"],
                        end=entity["end"],
                        score=float(entity["score"])
                    )
                )
            except (KeyError, TypeError) as e:
                log_warning(f"[WARNING] Could not convert entity to RecognizerResult: {e}")

        # Apply anonymization
        try:
            with self.analyzer_lock:  # Use lock for thread safety
                anonymized = self.anonymizer.anonymize(text, recognizer_results)
                return anonymized.text
        except Exception as e:
            # Use standardized error handling
            SecurityAwareErrorHandler.log_processing_error(e, "presidio_anonymization")
            return text

    def _convert_to_entity_dict(self, entity: Union[RecognizerResult, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Convert a Presidio RecognizerResult to a standardized dictionary.

        Args:
            entity: RecognizerResult or dictionary

        Returns:
            Standardized entity dictionary
        """
        if isinstance(entity, RecognizerResult):
            # For Presidio RecognizerResult objects
            return {
                "entity_type": entity.entity_type,
                "start": entity.start,
                "end": entity.end,
                "score": float(entity.score)  # Ensure score is a float
            }
        elif isinstance(entity, dict):
            # For dictionary entities, ensure required fields
            entity_dict = {
                "entity_type": entity.get("entity_type", "UNKNOWN"),
                "start": entity.get("start", 0),
                "end": entity.get("end", 0),
                "score": float(entity.get("score", 0.5))
            }
            # Add original_text if it exists
            if "original_text" in entity:
                entity_dict["original_text"] = entity["original_text"]
            return entity_dict
        else:
            # For any other type, try to convert to a basic dictionary
            log_warning(f"[WARNING] Unknown entity type: {type(entity)}, attempting basic conversion")
            try:
                return {
                    "entity_type": getattr(entity, "entity_type", "UNKNOWN"),
                    "start": getattr(entity, "start", 0),
                    "end": getattr(entity, "end", 0),
                    "score": float(getattr(entity, "score", 0.5))
                }
            except Exception as e:
                # Use standardized error handling
                SecurityAwareErrorHandler.log_processing_error(e, "entity_conversion")
                # Return a minimal valid entity to avoid crashes
                return {"entity_type": "UNKNOWN", "start": 0, "end": 0, "score": 0.0}