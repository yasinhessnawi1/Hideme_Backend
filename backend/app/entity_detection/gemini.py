"""
Gemini AI-based entity detection implementation with enhanced GDPR compliance, error handling, and improved synchronization.

This module provides a robust implementation of entity detection using Google's Gemini API
with improved security features, GDPR compliance, and standardized error handling.
"""
import asyncio
import time
from typing import Dict, Any, List, Optional, Tuple

from backend.app.entity_detection.base import BaseEntityDetector
from backend.app.utils.parallel.core import ParallelProcessingCore
from backend.app.utils.validation.data_minimization import minimize_extracted_data
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.helpers.gemini_helper import GeminiHelper
from backend.app.utils.helpers.gemini_usage_manager import gemini_usage_manager
from backend.app.utils.helpers.text_utils import TextUtils
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.system_utils.synchronization_utils import AsyncTimeoutLock, LockPriority


class GeminiEntityDetector(BaseEntityDetector):
    """
    Enhanced service for detecting sensitive information using Gemini AI
    with advanced usage management, GDPR compliance, and error handling.
    """

    def __init__(self):
        """Initialize the Gemini entity detector."""
        super().__init__()
        self.gemini_helper = GeminiHelper()
        # Do not create the API lock here; instead, create it lazily to bind it to the correct event loop.
        self._api_lock: Optional[AsyncTimeoutLock] = None

    async def _get_api_lock(self) -> AsyncTimeoutLock:
        current_loop = asyncio.get_running_loop()
        # Check if _api_lock exists and if its internal loop is the current one.
        # (Accessing _loop is not public API but is a common workaround.)
        if self._api_lock is None or getattr(self._api_lock, "_loop", None) != current_loop:
            self._api_lock = AsyncTimeoutLock(
                "gemini_api_lock",
                priority=LockPriority.HIGH,
                timeout=30.0
            )
        return self._api_lock

    async def detect_sensitive_data_async(
        self,
        extracted_data: Dict[str, Any],
        requested_entities: Optional[List[str]] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Detect sensitive entities in extracted text using the Gemini API
        with advanced usage management and GDPR compliance features.

        This method has been refactored to reduce cognitive complexity by
        dividing it into smaller helper methods:
          1. _prepare_pages_and_mappings
          2. _process_all_pages_in_parallel
          3. _finalize_detection_results

        Args:
            extracted_data: Dictionary containing text and bounding box information.
            requested_entities: List of entity types to detect.

        Returns:
            Tuple of (results_json, redaction_mapping).
        """
        start_time = time.time()
        minimized_data = minimize_extracted_data(extracted_data)
        operation_type = "gemini_detection"
        document_type = "document"

        try:
            # 1. Prepare pages and their text mappings.
            pages, page_texts_and_mappings, redaction_mapping = self._prepare_pages_and_mappings(minimized_data)
            if not pages:
                return [], {"pages": []}

            # 2. Process all pages in parallel.
            combined_entities = await self._process_all_pages_in_parallel(
                pages,
                page_texts_and_mappings,
                requested_entities,
                redaction_mapping
            )

            # 3. Finalize results (sort pages, update usage metrics, record GDPR, etc.).
            final_results, final_redaction_mapping = self._finalize_detection_results(
                pages=pages,
                combined_entities=combined_entities,
                redaction_mapping=redaction_mapping,
                requested_entities=requested_entities,
                operation_type=operation_type,
                document_type=document_type,
                start_time=start_time
            )

            return final_results, final_redaction_mapping

        except Exception as exc:
            log_error("[ERROR] Error in Gemini detection: " + str(exc))
            record_keeper.record_processing(
                operation_type=operation_type,
                document_type=document_type,
                entity_types_processed=requested_entities or [],
                processing_time=time.time() - start_time,
                entity_count=0,
                success=False
            )
            return [], {"pages": []}

    @staticmethod
    def _prepare_pages_and_mappings(
        minimized_data: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], Dict[int, Tuple[str, List[Tuple[Dict[str, Any], int, int]]]], Dict[str, List[Dict[str, Any]]]]:
        """
        Prepare pages, text, and mapping data for processing.

        Args:
            minimized_data: The minimized extracted_data dictionary.

        Returns:
            A tuple containing:
              1. pages: List of page dictionaries.
              2. page_texts_and_mappings: Dict mapping page number to (full_text, mapping).
              3. redaction_mapping: Dict with a "pages" key to track redactions.
        """
        pages = minimized_data.get("pages", [])
        page_texts_and_mappings: Dict[int, Tuple[str, List[Tuple[Dict[str, Any], int, int]]]] = {}
        redaction_mapping = {"pages": []}

        for pg in pages:
            pg_words = pg.get("words", [])
            pg_number = pg.get("page")
            if not pg_words:
                redaction_mapping["pages"].append({"page": pg_number, "sensitive": []})
                continue

            reconstructed_text, text_mapping = TextUtils.reconstruct_text_and_mapping(pg_words)
            page_texts_and_mappings[pg_number] = (reconstructed_text, text_mapping)

        return pages, page_texts_and_mappings, redaction_mapping

    async def _process_all_pages_in_parallel(
        self,
        pages: List[Dict[str, Any]],
        page_texts_and_mappings: Dict[int, Tuple[str, List[Tuple[Dict[str, Any], int, int]]]],
        requested_entities: Optional[List[str]],
        redaction_mapping: Dict[str, List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """
        Process all pages in parallel using ParallelProcessingCore.

        Args:
            pages: List of page dictionaries.
            page_texts_and_mappings: Mapping of page number to (full_text, mapping).
            requested_entities: List of entity types to detect.
            redaction_mapping: Redaction mapping dictionary.

        Returns:
            Combined list of processed entities from all pages.
        """
        log_info("[OK] Processing {0} pages with Gemini API in parallel".format(len(pages)))
        max_api_workers = min(4, len(pages))
        page_results = await ParallelProcessingCore.process_pages_in_parallel(
            pages,
            lambda pg: self._process_single_page(
                pg,
                page_texts_and_mappings,
                requested_entities
            ),
            max_workers=max_api_workers
        )

        combined_results = []
        for _, (local_page_redaction_info, local_processed_entities) in page_results:
            if local_page_redaction_info:
                redaction_mapping["pages"].append(local_page_redaction_info)
            if local_processed_entities:
                combined_results.extend(local_processed_entities)

        return combined_results

    async def _process_single_page(
        self,
        single_page_data: Dict[str, Any],
        page_texts_and_mappings: Dict[int, Tuple[str, List[Tuple[Dict[str, Any], int, int]]]],
        requested_entities: Optional[List[str]]
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Process a single page with Gemini API and return its redaction info and detected entities.

        Args:
            single_page_data: Dictionary containing 'page' and 'words' for one page.
            page_texts_and_mappings: Mapping of page number to (full_text, mapping).
            requested_entities: List of entity types to detect.

        Returns:
            A tuple containing:
              1. page_redaction_info: Dict with "page" and "sensitive" keys.
              2. processed_entities: List of detected entity dictionaries.
        """
        page_start_time = time.time()
        local_page_number = single_page_data.get("page")
        local_words = single_page_data.get("words", [])
        if not local_words:
            return {"page": local_page_number, "sensitive": []}, []

        local_full_text, local_mapping = page_texts_and_mappings[local_page_number]

        processed_text = await gemini_usage_manager.manage_page_processing(
            local_full_text,
            requested_entities,
            local_page_number
        )
        if processed_text is None:
            log_warning("[WARNING] Page {0} processing blocked by usage manager".format(local_page_number))
            return {"page": local_page_number, "sensitive": []}, []

        log_info("[OK] Processing text with Gemini API on page {0}".format(local_page_number))
        try:
            # Acquire the API lock lazily to ensure it's bound to the current event loop.
            api_lock = await self._get_api_lock()
            async with api_lock.acquire_timeout(timeout=45.0):
                response = await self.gemini_helper.process_text(processed_text, requested_entities)
        finally:
            try:
                await gemini_usage_manager.release_request_slot()
            except Exception as release_error:
                SecurityAwareErrorHandler.log_processing_error(
                    release_error, "gemini_release_slot", "page_{0}".format(local_page_number)
                )

        if response is None:
            log_warning("[WARNING] Gemini API processing failed on page {0}".format(local_page_number))
            return {"page": local_page_number, "sensitive": []}, []

        page_entities = self._extract_entities_from_response(response, local_full_text)
        if not page_entities:
            log_info("[OK] No entities detected on page {0}".format(local_page_number))
            return {"page": local_page_number, "sensitive": []}, []

        detected_entity_count = len(page_entities)
        log_info("[OK] Found {0} entities on page {1}".format(detected_entity_count, local_page_number))

        processed_entities, page_redaction_info = await self.process_entities_for_page(
            local_page_number, local_full_text, local_mapping, page_entities
        )
        page_time = time.time() - page_start_time
        log_sensitive_operation(
            "Gemini Page Detection",
            len(processed_entities),
            page_time,
            page_number=local_page_number
        )
        return page_redaction_info, processed_entities

    def _finalize_detection_results(
        self,
        pages: List[Dict[str, Any]],
        combined_entities: List[Dict[str, Any]],
        redaction_mapping: Dict[str, List[Dict[str, Any]]],
        requested_entities: Optional[List[str]],
        operation_type: str,
        document_type: str,
        start_time: float
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Finalize detection results by sorting pages, updating usage metrics, recording GDPR,
        and returning final results.

        Args:
            pages: List of page dictionaries.
            combined_entities: Combined list of processed entities from all pages.
            redaction_mapping: Redaction mapping dictionary.
            requested_entities: List of entity types to detect.
            operation_type: Type of operation for GDPR logging.
            document_type: Document type for GDPR logging.
            start_time: Timestamp when detection started.

        Returns:
            Tuple of (final_results, final_redaction_mapping).
        """
        redaction_mapping["pages"].sort(key=lambda x: x.get("page", 0))
        total_time = time.time() - start_time
        self.update_usage_metrics(len(combined_entities), total_time)
        record_keeper.record_processing(
            operation_type=operation_type,
            document_type=document_type,
            entity_types_processed=requested_entities or [],
            processing_time=total_time,
            entity_count=len(combined_entities),
            success=True
        )
        entity_count_local = len(combined_entities)
        pages_count_local = len(pages)
        if total_time > 0:
            log_info("[PERF] Gemini processing summary: {0} entities across {1} pages in {2:.2f}s ({3:.2f} entities/s)".format(
                entity_count_local,
                pages_count_local,
                total_time,
                entity_count_local / total_time
            ))
        else:
            log_info("[PERF] Gemini processing summary: 0s total time recorded.")
        usage_summary = gemini_usage_manager.get_usage_summary()
        log_info("[USAGE] Gemini API Usage: {0}".format(usage_summary))
        return combined_entities, redaction_mapping

    def _extract_entities_from_response(
        self,
        api_response: Dict[str, Any],
        page_full_text: str
    ) -> List[Dict[str, Any]]:
        """
        Extract entities from Gemini API response. Refactored to reduce complexity
        by dividing the extraction into smaller helper methods.

        Args:
            api_response: Gemini API response dictionary.
            page_full_text: Full text of the document page.

        Returns:
            List of extracted entities.
        """
        try:
            raw_entities = self._gather_raw_entities(api_response)
            enriched_entities = [
                self._maybe_add_original_text(ent, page_full_text)
                for ent in raw_entities
            ]
            sanitized = self.sanitize_entities(enriched_entities)
            return sanitized
        except Exception as exc:
            SecurityAwareErrorHandler.log_processing_error(exc, "gemini_response_extraction")
            return []

    @staticmethod
    def _gather_raw_entities(api_response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Gather all raw entities from the 'pages' -> 'text' -> 'entities' hierarchy in the API response.

        Args:
            api_response: Gemini API response dictionary.

        Returns:
            List of raw entity dictionaries.
        """
        all_entities = []
        pages_in_response = api_response.get("pages", [])
        for p_data in pages_in_response:
            text_entries = p_data.get("text", [])
            for t_entry in text_entries:
                entity_list = t_entry.get("entities", [])
                all_entities.extend(entity_list)
        return all_entities

    @staticmethod
    def _maybe_add_original_text(
        entity: Dict[str, Any],
        page_full_text: str
    ) -> Dict[str, Any]:
        """
        If 'original_text' is missing, attempt to extract it from page_full_text
        using 'start' and 'end'. Returns the updated entity dictionary.

        Args:
            entity: A single entity dictionary from the Gemini API.
            page_full_text: Full text of the page.

        Returns:
            Updated entity dictionary with 'original_text' if found.
        """
        if "original_text" not in entity and "start" in entity and "end" in entity:
            try:
                start_idx = int(entity["start"])
                end_idx = int(entity["end"])
                if 0 <= start_idx < end_idx <= len(page_full_text):
                    entity["original_text"] = page_full_text[start_idx:end_idx]
            except (ValueError, IndexError, TypeError):
                log_warning("[WARNING] Could not extract original_text from entity indices")
        return entity

    def _convert_to_entity_dict(self, gemini_entity: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert a Gemini entity to a standardized dictionary.

        Args:
            gemini_entity: Entity dictionary from Gemini API.

        Returns:
            Standardized entity dictionary.
        """
        entity_dict_standard = {
            "entity_type": gemini_entity.get("entity_type", "UNKNOWN"),
            "start": gemini_entity.get("start", 0),
            "end": gemini_entity.get("end", 0),
            "score": float(gemini_entity.get("score", 0.5))
        }
        if "original_text" in gemini_entity:
            entity_dict_standard["original_text"] = gemini_entity["original_text"]
        return entity_dict_standard