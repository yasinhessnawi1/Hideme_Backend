"""
PresidioEntityDetector class implementation.
This module provides a robust implementation of entity detection using Microsoft Presidio.
It ensures enhanced GDPR compliance by minimizing data, supports asynchronous processing,
and applies standardized error handling to avoid leaking sensitive information. Configuration
files (YAML) are loaded for advanced analyzer and anonymizer setup, with fallbacks to defaults.
"""

import asyncio
import hashlib
import json
import os
import time
from typing import Dict, Any, List, Optional, Tuple

# Import Presidio libraries for analysis and anonymization.
from presidio_analyzer import AnalyzerEngine
from presidio_analyzer import AnalyzerEngineProvider
from presidio_anonymizer import AnonymizerEngine

from backend.app.configs.presidio_config import (DEFAULT_LANGUAGE, PRESIDIO_AVAILABLE_ENTITIES)
from backend.app.entity_detection.base import BaseEntityDetector
from backend.app.utils.helpers.json_helper import validate_presidio_requested_entities
from backend.app.utils.helpers.text_utils import TextUtils, EntityUtils
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.parallel.core import ParallelProcessingCore
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.system_utils.synchronization_utils import TimeoutLock, LockPriority
from backend.app.utils.validation.data_minimization import minimize_extracted_data


class PresidioEntityDetector(BaseEntityDetector):
    """
    Service for detecting sensitive information using Microsoft Presidio.

    This detector leverages Microsoft Presidio's AnalyzerEngine and AnonymizerEngine
    to detect and anonymize sensitive entities from input text. It loads configuration
    from YAML files for custom setups, falls back to default settings if needed, and
    employs robust error handling and caching to ensure GDPR compliance and operational resilience.
    """

    def __init__(self) -> None:
        """
        Initialize the Presidio entity detector using YAML configuration.

        This constructor sets up paths to configuration files, creates a lazy lock for
        analyzer operations, and initializes the Presidio analyzer and anonymizer.
        """
        # Call the parent class initializer.
        super().__init__()
        # Lock to synchronize analyzer operations; created lazily.
        self._analyzer_lock: Optional[TimeoutLock] = None
        # AnalyzerEngine instance; will be set during initialization.
        self.analyzer: Optional[AnalyzerEngine] = None
        # AnonymizerEngine instance; will be set during initialization.
        self.anonymizer: Optional[AnonymizerEngine] = None
        # Cache to store analysis results for reuse.
        self.cache = {}

        # Determine the base directory (two levels up from current file).
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # Configuration directory path.
        config_dir = os.path.join(base_dir, "configs")

        # Define full paths to required configuration files.
        self._analyzer_conf_file = os.path.join(config_dir, "analyzer-config.yml")
        self._nlp_engine_conf_file = os.path.join(config_dir, "nlp-config.yml")
        self._recognizer_registry_conf_file = os.path.join(config_dir, "recognizers-config.yml")

        # Load Presidio analyzer and anonymizer with proper configuration.
        self._initialize_presidio()

    def _get_analyzer_lock(self) -> TimeoutLock:
        """
        Lazily create and return the TimeoutLock for analyzer operations.

        This lock ensures that configuration and analysis operations are thread-safe.

        Returns:
            TimeoutLock: The analyzer lock.
        """
        if self._analyzer_lock is None:
            try:
                self._analyzer_lock = TimeoutLock(
                    name="presidio_analyzer_lock",
                    priority=LockPriority.HIGH,
                    timeout=30.0
                )
            except Exception as exc:
                # Log the error using our error handling utility.
                SecurityAwareErrorHandler.log_processing_error(exc, "analyzer_lock_init", self._analyzer_conf_file)
        return self._analyzer_lock

    @staticmethod
    def _cache_key(text: str, entities: List[str]) -> str:
        """
        Create a unique cache key based on the input text and list of entities.

        Args:
            text: The text to analyze.
            entities: List of entity types.

        Returns:
            A string representing the MD5 hash of the combined input.
        """
        key_data = text + '|' + ','.join(sorted(entities))
        return hashlib.md5(key_data.encode('utf-8')).hexdigest()

    def _initialize_presidio(self) -> None:
        """
        Initialize the Presidio analyzer and anonymizer using YAML configuration.

        Checks for existence of configuration files; if any are missing or if the
        lock cannot be acquired, falls back to default initialization.
        """
        # List to store missing configuration file paths.
        missing_files = []
        for file_path in [
            self._analyzer_conf_file,
            self._nlp_engine_conf_file,
            self._recognizer_registry_conf_file
        ]:
            if not os.path.exists(file_path):
                missing_files.append(file_path)

        # Acquire the analyzer lock to ensure only one initialization occurs.
        analyzer_lock = self._get_analyzer_lock()
        acquired = analyzer_lock.acquire(timeout=60.0)  # 1-minute timeout
        if not acquired:
            log_error("[ERROR] Failed to acquire lock for Presidio analyzer initialization")
            # Fallback to default initialization if lock acquisition fails.
            self.analyzer = AnalyzerEngine(supported_languages=[DEFAULT_LANGUAGE])
            self.anonymizer = AnonymizerEngine()
            return

        try:
            # If configuration files are missing, log a warning and use default settings.
            if missing_files:
                log_warning("[WARNING] Missing configuration files: " + ", ".join(missing_files))
                log_warning("[WARNING] Using default configuration")
                self.analyzer = AnalyzerEngine(supported_languages=[DEFAULT_LANGUAGE])
            else:
                log_info("[OK] Loading Presidio configuration from YAML files")
                # Create an AnalyzerEngineProvider with configuration file paths.
                provider = AnalyzerEngineProvider(
                    analyzer_engine_conf_file=self._analyzer_conf_file,
                    nlp_engine_conf_file=self._nlp_engine_conf_file,
                    recognizer_registry_conf_file=self._recognizer_registry_conf_file
                )
                # Create the analyzer engine from configuration.
                self.analyzer = provider.create_engine()
                log_info("[OK] Successfully created analyzer engine from configuration")

            # Always initialize the anonymizer engine.
            self.anonymizer = AnonymizerEngine()

        finally:
            # Release the lock regardless of success.
            analyzer_lock.release()

    async def detect_sensitive_data_async(
            self,
            extracted_data: Dict[str, Any],
            requested_entities: Optional[List[str]] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Asynchronously detect sensitive entities using Microsoft Presidio.

        This method:
          - Validates and minimizes input data.
          - Processes each page of the document asynchronously.
          - Aggregates and filters results based on confidence scores.
          - Records processing details for GDPR compliance.

        Args:
            extracted_data: Dictionary containing text and bounding box information.
            requested_entities: List of entity types to detect.

        Returns:
            A tuple containing a list of detected entities and a redaction mapping.
        """
        start_time = time.time()  # Record start time for performance metrics
        operation_type = "presidio_detection"
        document_type = "document"

        try:
            # Validate requested entities; if not provided, use default available entities.
            if requested_entities is not None:
                requested_entities_json = json.dumps(requested_entities)
                validated_entities = validate_presidio_requested_entities(requested_entities_json)
            else:
                validated_entities = PRESIDIO_AVAILABLE_ENTITIES
        except Exception as e:
            log_error("[Presidio] Entity validation failed: " + str(e))
            # Record failure in processing.
            record_keeper.record_processing(
                operation_type=operation_type,
                document_type=document_type,
                entity_types_processed=requested_entities or [],
                processing_time=time.time() - start_time,
                entity_count=0,
                success=False
            )
            return [], {"pages": []}

        # If no valid entities remain after validation, return empty results.
        if not validated_entities:
            log_warning("[Presidio] No valid entities remain after filtering, returning empty results")
            record_keeper.record_processing(
                operation_type=operation_type,
                document_type=document_type,
                entity_types_processed=[],
                processing_time=time.time() - start_time,
                entity_count=0,
                success=False
            )
            return [], {"pages": []}

        # Minimize data for GDPR compliance.
        minimized_data = minimize_extracted_data(extracted_data)

        try:
            # Get the list of pages from the minimized data.
            pages = minimized_data.get("pages", [])
            if not pages:
                return [], {"pages": []}

            # Process all pages asynchronously using engine-specific parallel processing.
            local_page_results = await self._process_all_pages_async(pages, validated_entities)

            # Aggregate the detection results from all pages.
            combined_entities, redaction_mapping = self._aggregate_page_results(local_page_results)

            total_time = time.time() - start_time
            # Update usage metrics from the base class.
            self.update_usage_metrics(len(combined_entities), total_time)
            # Record processing for auditing and GDPR compliance.
            record_keeper.record_processing(
                operation_type=operation_type,
                document_type=document_type,
                entity_types_processed=validated_entities,
                processing_time=total_time,
                entity_count=len(combined_entities),
                success=True
            )

            # Log performance metrics for the detection process.
            self._log_detection_performance(combined_entities, redaction_mapping, pages, total_time)

            return combined_entities, redaction_mapping

        except Exception as exc:
            log_error("[ERROR] Error in Presidio detection: " + str(exc))
            record_keeper.record_processing(
                operation_type=operation_type,
                document_type=document_type,
                entity_types_processed=validated_entities,
                processing_time=time.time() - start_time,
                entity_count=0,
                success=False
            )
            return [], {"pages": []}

    async def _process_all_pages_async(
            self,
            pages: List[Dict[str, Any]],
            local_requested_entities: List[str]
    ) -> List[Tuple[int, Tuple[Dict[str, Any], List[Dict[str, Any]]]]]:
        """
        Process all pages in parallel using a global timeout.

        For each page, the text is reconstructed and analyzed in a separate thread.

        Args:
            pages: List of page dictionaries.
            local_requested_entities: List of requested entity types.

        Returns:
            A list of tuples: (page_number, (page_redaction_info, processed_entities))
        """

        async def _process_single_page_async(local_page: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
            """
            Processes a single page for entity detection.

            Args:
                local_page: Dictionary representing a page.

            Returns:
                A tuple with page redaction information and a list of processed entities.
            """
            try:
                # Get page number and word data.
                local_page_number = local_page.get("page")
                local_words = local_page.get("words", [])
                if not local_words:
                    # Return empty result if no words are present.
                    return {"page": local_page_number, "sensitive": []}, []

                # Reconstruct the full text and mapping from the word data.
                full_text, mapping = TextUtils.reconstruct_text_and_mapping(local_words)
                log_info(f"[OK] Processing page {local_page_number} with {len(local_words)} words")

                # Analyze the text in a separate thread with a 30-second timeout.
                try:
                    page_results = await asyncio.wait_for(
                        asyncio.to_thread(
                            self._analyze_text,
                            full_text,
                            DEFAULT_LANGUAGE,
                            local_requested_entities
                        ),
                        timeout=30.0
                    )
                except asyncio.TimeoutError:
                    log_warning(f"[WARNING] Timeout analyzing text on page {local_page_number}")
                    return {"page": local_page_number, "sensitive": []}, []

                # Merge overlapping entities using text utilities.
                filtered_results = EntityUtils.merge_overlapping_entities(page_results)
                if not filtered_results:
                    return {"page": local_page_number, "sensitive": []}, []

                # Convert raw entities into standardized dictionaries.
                entity_dicts = [self._convert_to_entity_dict(ent) for ent in filtered_results]
                log_info(f"[OK] Found {len(entity_dicts)} entities on page {local_page_number}")

                # Process entities to compute redaction information.
                processed_entities, local_page_redaction_info = await ParallelProcessingCore.process_entities_in_parallel(
                    self, full_text, mapping, entity_dicts, local_page_number
                )
                return local_page_redaction_info, processed_entities

            except Exception as page_exc:
                # Log error for the page and return empty results.
                SecurityAwareErrorHandler.log_processing_error(
                    page_exc, "presidio_page_processing",
                    f"page_{local_page.get('page', 'unknown')}"
                )
                return {"page": local_page.get('page', 0), "sensitive": []}, []

        # Execute processing for all pages in parallel with a 2-minute timeout.
        try:
            return await asyncio.wait_for(
                ParallelProcessingCore.process_pages_in_parallel(pages, _process_single_page_async),
                timeout=120.0
            )
        except asyncio.TimeoutError:
            log_error("[ERROR] Global timeout processing pages with Presidio")
            return []

    @staticmethod
    def _aggregate_page_results(
            local_page_results: List[Tuple[int, Tuple[Dict[str, Any], List[Dict[str, Any]]]]]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Aggregate detection results from all pages.

        Args:
            local_page_results: List of tuples (page_number, (page_redaction_info, processed_entities))

        Returns:
            A tuple (combined_entities, redaction_mapping)
        """
        combined_entities: List[Dict[str, Any]] = []
        redaction_mapping = {"pages": []}
        # Iterate over the results from each page.
        for result_page_number, (local_page_redaction_info, local_processed_entities) in local_page_results:
            if local_page_redaction_info:
                redaction_mapping["pages"].append(local_page_redaction_info)
            if local_processed_entities:
                combined_entities.extend(local_processed_entities)
        # Sort redaction mapping by page number.
        redaction_mapping["pages"].sort(key=lambda x: x.get("page", 0))
        return combined_entities, redaction_mapping

    @staticmethod
    def _log_detection_performance(
            combined_entities: List[Dict[str, Any]],
            redaction_mapping: Dict[str, Any],
            pages: List[Dict[str, Any]],
            total_time: float
    ) -> None:
        """
        Log the overall performance of the detection process.

        Args:
            combined_entities: Aggregated list of detected entities.
            redaction_mapping: Combined redaction mapping.
            pages: List of original pages.
            total_time: Total time taken for detection.
        """
        # Create a summary of entities per page.
        page_summaries = [
            f"page_{info['page']}:{len(info['sensitive'])}"
            for info in redaction_mapping["pages"]
        ]
        # Log sensitive operation metrics.
        log_sensitive_operation(
            "Presidio Detection",
            len(combined_entities),
            total_time,
            pages=len(pages),
            entities_per_page=", ".join(page_summaries)
        )

    def _analyze_text(
            self,
            text: str,
            language: str,
            entities: List[str]
    ) -> List[Any]:
        """
        Thread-safe wrapper for the Presidio analyzer's analyze method with timeout handling.

        Args:
            text: Text to analyze.
            language: Language of the text.
            entities: List of entity types to detect.

        Returns:
            List of recognized entities.
        """
        # Compute a unique cache key using the helper function.
        key = self._cache_key(text, entities)
        if key in self.cache:
            log_info("[Presidio] ✅ Using cached analysis result")
            return self.cache[key]

        # Acquire the analyzer lock to ensure safe concurrent access.
        lock = self._get_analyzer_lock()
        acquired = lock.acquire(timeout=30.0)
        if not acquired:
            log_warning("[WARNING] Failed to acquire lock for Presidio analysis")
            return []

        try:
            # Check if the analyzer is properly initialized.
            if self.analyzer is None:
                log_warning("[WARNING] Presidio analyzer not initialized, returning empty result")
                return []
            # Run the analysis using Presidio's analyzer.
            result = self.analyzer.analyze(text=text, language=language, entities=entities)
            # Cache the result for future reuse.
            self.cache[key] = result
            return result
        except Exception as analyze_exc:
            # Log any analysis error using our error handling.
            SecurityAwareErrorHandler.log_processing_error(analyze_exc, "presidio_analysis")
            return []
        finally:
            # Always release the lock.
            lock.release()
