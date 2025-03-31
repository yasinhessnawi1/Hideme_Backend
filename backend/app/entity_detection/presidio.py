"""
Presidio entity detection implementation with enhanced GDPR compliance and error handling.

This module provides a robust implementation of entity detection using Microsoft Presidio
with improved security features, GDPR compliance, and standardized error handling.
"""

import asyncio
import os
import time
from typing import Dict, Any, List, Optional, Tuple, Union

from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_analyzer import AnalyzerEngineProvider
from presidio_anonymizer import AnonymizerEngine

from backend.app.configs.presidio_config import (DEFAULT_LANGUAGE, PRESIDIO_AVAILABLE_ENTITIES)
from backend.app.entity_detection.base import BaseEntityDetector
from backend.app.utils.helpers.text_utils import TextUtils, EntityUtils
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.parallel.core import ParallelProcessingCore
from backend.app.utils.validation.data_minimization import minimize_extracted_data
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.system_utils.synchronization_utils import TimeoutLock, LockPriority


class PresidioEntityDetector(BaseEntityDetector):
    """
    Service for detecting sensitive information using Microsoft Presidio
    with robust async processing support and GDPR compliance features.
    """

    def __init__(self) -> None:
        """
        Initialize the Presidio entity detector using YAML configuration.

        The lock for the Presidio analyzer is now lazily created instead of
        being directly instantiated here.
        """
        super().__init__()
        self._analyzer_lock: Optional[TimeoutLock] = None
        self.analyzer: Optional[AnalyzerEngine] = None
        self.anonymizer: Optional[AnonymizerEngine] = None

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_dir = os.path.join(base_dir, "configs")

        self._analyzer_conf_file = os.path.join(config_dir, "analyzer-config.yml")
        self._nlp_engine_conf_file = os.path.join(config_dir, "nlp-config.yml")
        self._recognizer_registry_conf_file = os.path.join(config_dir, "recognizers-config.yml")

        # Perform initial loading of configuration
        self._initialize_presidio()

    def _get_analyzer_lock(self) -> TimeoutLock:
        """
        Lazily create and return the TimeoutLock for analyzer operations.
        """
        if self._analyzer_lock is None:
            self._analyzer_lock = TimeoutLock(
                name="presidio_analyzer_lock",
                priority=LockPriority.HIGH,
                timeout=30.0
            )
        return self._analyzer_lock

    def _initialize_presidio(self) -> None:
        """
        Initialize the Presidio analyzer and anonymizer using YAML configuration.
        If configuration files are missing or a lock cannot be acquired,
        falls back to default initialization.
        """
        # Check if configuration files exist
        missing_files = []
        for file_path in [
            self._analyzer_conf_file,
            self._nlp_engine_conf_file,
            self._recognizer_registry_conf_file
        ]:
            if not os.path.exists(file_path):
                missing_files.append(file_path)

        # Acquire lock for initialization
        analyzer_lock = self._get_analyzer_lock()
        acquired = analyzer_lock.acquire(timeout=60.0)  # 1-minute timeout
        if not acquired:
            log_error("[ERROR] Failed to acquire lock for Presidio analyzer initialization")
            # Fallback to default
            self.analyzer = AnalyzerEngine(supported_languages=[DEFAULT_LANGUAGE])
            self.anonymizer = AnonymizerEngine()
            return

        try:
            if missing_files:
                log_warning("[WARNING] Missing configuration files: " + ", ".join(missing_files))
                log_warning("[WARNING] Using default configuration")
                self.analyzer = AnalyzerEngine(supported_languages=[DEFAULT_LANGUAGE])
            else:
                log_info("[OK] Loading Presidio configuration from YAML files")
                provider = AnalyzerEngineProvider(
                    analyzer_engine_conf_file=self._analyzer_conf_file,
                    nlp_engine_conf_file=self._nlp_engine_conf_file,
                    recognizer_registry_conf_file=self._recognizer_registry_conf_file
                )
                self.analyzer = provider.create_engine()
                log_info("[OK] Successfully created analyzer engine from configuration")

            # Initialize anonymizer
            self.anonymizer = AnonymizerEngine()

        finally:
            analyzer_lock.release()

    async def detect_sensitive_data_async(
        self,
        extracted_data: Dict[str, Any],
        requested_entities: Optional[List[str]] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Asynchronous method to detect sensitive entities in extracted text.
        Refactored to reduce cognitive complexity by splitting logic into helper methods.

        Args:
            extracted_data: Dictionary containing text and bounding box information.
            requested_entities: List of entity types to detect.

        Returns:
            Tuple of (results_json, redaction_mapping).
        """
        start_time = time.time()
        local_requested_entities = requested_entities or PRESIDIO_AVAILABLE_ENTITIES
        minimized_data = minimize_extracted_data(extracted_data)

        # For GDPR compliance and logging
        operation_type = "presidio_detection"
        document_type = "document"

        try:
            pages = minimized_data.get("pages", [])
            if not pages:
                return [], {"pages": []}

            # 1. Process all pages in parallel
            local_page_results = await self._process_all_pages_async(pages, local_requested_entities)

            # 2. Aggregate results
            combined_entities, redaction_mapping = self._aggregate_page_results(local_page_results)

            # 3. Update usage metrics and record GDPR
            total_time = time.time() - start_time
            self.update_usage_metrics(len(combined_entities), total_time)
            record_keeper.record_processing(
                operation_type=operation_type,
                document_type=document_type,
                entity_types_processed=local_requested_entities,
                processing_time=total_time,
                entity_count=len(combined_entities),
                success=True
            )

            # 4. Log performance
            self._log_detection_performance(combined_entities, redaction_mapping, pages, total_time)

            return combined_entities, redaction_mapping

        except Exception as exc:
            # Log error with standardized handling
            log_error("[ERROR] Error in Presidio detection: " + str(exc))
            record_keeper.record_processing(
                operation_type=operation_type,
                document_type=document_type,
                entity_types_processed=local_requested_entities,
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
        Step 1: Process all pages in parallel with a global timeout.

        Args:
            pages: List of page dictionaries.
            local_requested_entities: The list of requested entity types.

        Returns:
            A list of tuples: (page_number, (page_redaction_info, processed_entities))
        """
        async def _process_single_page_async(local_page: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
            """
            Processes a single page for entity detection.

            Args:
                local_page: Dictionary representing a page of text.

            Returns:
                (page_redaction_info, processed_entities) for the page.
            """
            try:
                local_page_number = local_page.get("page")
                local_words = local_page.get("words", [])
                if not local_words:
                    return {"page": local_page_number, "sensitive": []}, []

                full_text, mapping = TextUtils.reconstruct_text_and_mapping(local_words)
                log_info(f"[OK] Processing page {local_page_number} with {len(local_words)} words")

                # Analyze text in a thread with a 30s timeout
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

                filtered_results = EntityUtils.merge_overlapping_entities(page_results)
                if not filtered_results:
                    return {"page": local_page_number, "sensitive": []}, []

                entity_dicts = [self._convert_to_entity_dict(ent) for ent in filtered_results]
                log_info(f"[OK] Found {len(entity_dicts)} entities on page {local_page_number}")

                processed_entities, local_page_redaction_info = await ParallelProcessingCore.process_entities_in_parallel(
                    self, full_text, mapping, entity_dicts, local_page_number
                )
                return local_page_redaction_info, processed_entities

            except Exception as page_exc:
                SecurityAwareErrorHandler.log_processing_error(
                    page_exc, "presidio_page_processing",
                    f"page_{local_page.get('page', 'unknown')}"
                )
                return {"page": local_page.get('page', 0), "sensitive": []}, []

        # Execute all pages in parallel with a 2-minute global timeout
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
        Step 2: Aggregate results from all pages.

        Args:
            local_page_results: A list of (page_number, (page_redaction_info, processed_entities)) tuples.

        Returns:
            (combined_entities, redaction_mapping)
        """
        combined_entities: List[Dict[str, Any]] = []
        redaction_mapping = {"pages": []}

        for result_page_number, (local_page_redaction_info, local_processed_entities) in local_page_results:
            if local_page_redaction_info:
                redaction_mapping["pages"].append(local_page_redaction_info)
            if local_processed_entities:
                combined_entities.extend(local_processed_entities)

        # Sort pages by page number
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
        Step 3: Log final performance metrics without sensitive details.

        Args:
            combined_entities: List of all detected entities across pages
            redaction_mapping: Redaction mapping dictionary with 'pages'
            pages: Original pages list
            total_time: Total detection time
        """
        page_summaries = [
            f"page_{info['page']}:{len(info['sensitive'])}"
            for info in redaction_mapping["pages"]
        ]
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
        Thread-safe wrapper for the Presidio analyzer's analyze method with improved timeout handling.

        Args:
            text: Text to analyze
            language: Language of the text
            entities: Entity types to detect

        Returns:
            List of recognized entities
        """
        lock = self._get_analyzer_lock()
        acquired = lock.acquire(timeout=30.0)
        if not acquired:
            log_warning("[WARNING] Failed to acquire lock for Presidio analysis")
            return []

        try:
            if self.analyzer is None:
                log_warning("[WARNING] Presidio analyzer not initialized, returning empty result")
                return []
            return self.analyzer.analyze(text=text, language=language, entities=entities)
        except Exception as analyze_exc:
            SecurityAwareErrorHandler.log_processing_error(analyze_exc, "presidio_analysis")
            return []
        finally:
            lock.release()

    def _convert_to_entity_dict(
        self,
        entity: Union[RecognizerResult, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Convert a Presidio RecognizerResult or a dictionary to a standardized entity dictionary.

        Args:
            entity: RecognizerResult object or dictionary

        Returns:
            Standardized entity dictionary
        """
        if isinstance(entity, RecognizerResult):
            # For Presidio RecognizerResult objects
            return {
                "entity_type": entity.entity_type,
                "start": entity.start,
                "end": entity.end,
                "score": float(entity.score)
            }
        elif isinstance(entity, dict):
            # For dictionary entities
            return self._convert_dict_entity(entity)
        else:
            # For any other type, attempt a generic conversion
            return self._convert_unknown_entity(entity)

    @staticmethod
    def _convert_dict_entity(entity: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert a dictionary-based entity into a standardized format.

        Args:
            entity: Dictionary representing an entity

        Returns:
            Standardized entity dictionary
        """
        entity_dict = {
            "entity_type": entity.get("entity_type", "UNKNOWN"),
            "start": entity.get("start", 0),
            "end": entity.get("end", 0),
            "score": float(entity.get("score", 0.5))
        }
        if "original_text" in entity:
            entity_dict["original_text"] = entity["original_text"]
        return entity_dict

    @staticmethod
    def _convert_unknown_entity(entity: Any) -> Dict[str, Any]:
        """
        Convert an unknown entity type into a minimal standardized format.

        Args:
            entity: An entity object with unknown attributes

        Returns:
            Standardized entity dictionary
        """
        log_warning(f"[WARNING] Unknown entity type: {type(entity)}, attempting basic conversion")
        try:
            return {
                "entity_type": getattr(entity, "entity_type", "UNKNOWN"),
                "start": getattr(entity, "start", 0),
                "end": getattr(entity, "end", 0),
                "score": float(getattr(entity, "score", 0.5))
            }
        except Exception as conversion_exc:
            SecurityAwareErrorHandler.log_processing_error(conversion_exc, "entity_conversion")
            return {"entity_type": "UNKNOWN", "start": 0, "end": 0, "score": 0.0}