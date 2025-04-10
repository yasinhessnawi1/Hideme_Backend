"""
Gemini AI-based entity detection implementation with enhanced GDPR compliance, error handling,
and improved synchronization.

This module provides a robust implementation of entity detection using Google's Gemini API.
It includes advanced usage management, comprehensive error handling using SecurityAwareErrorHandler,
and standardized processing of extracted text. The implementation leverages asynchronous parallel
processing and lazy-initialized locks to prevent issues related to event loop binding.
"""

import asyncio
import time
import json
from typing import Dict, Any, List, Optional, Tuple

from backend.app.entity_detection.base import BaseEntityDetector
from backend.app.utils.parallel.core import ParallelProcessingCore
from backend.app.utils.helpers.json_helper import validate_gemini_requested_entities
from backend.app.utils.validation.data_minimization import minimize_extracted_data
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.helpers.gemini_helper import gemini_helper
from backend.app.utils.helpers.gemini_usage_manager import gemini_usage_manager
from backend.app.utils.helpers.text_utils import TextUtils
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.system_utils.synchronization_utils import AsyncTimeoutLock, LockPriority


class GeminiEntityDetector(BaseEntityDetector):
    """
    Enhanced service for detecting sensitive information using Gemini AI.

    This class provides a robust implementation that interacts with the Gemini API to detect
    sensitive entities from text. It manages usage, synchronizes API calls using an asynchronous
    lock, and ensures GDPR compliance through data minimization and thorough error handling.
    """

    def __init__(self):
        """Initialize the Gemini entity detector and prepare the helper and API lock."""
        super().__init__()
        # Reference to the gemini helper which encapsulates API calls.
        self.gemini_helper = gemini_helper
        # The API lock is created lazily to ensure proper binding with the current event loop.
        self._api_lock: Optional[AsyncTimeoutLock] = None

    async def _get_api_lock(self) -> AsyncTimeoutLock:
        """
        Lazily obtain and return the asynchronous API lock.

        The lock is re-created if it is not bound to the current event loop.

        Returns:
            AsyncTimeoutLock: The API lock used to synchronize Gemini API calls.
        """
        current_loop = asyncio.get_running_loop()
        # If the lock does not exist or is bound to a different loop, create a new one.
        if self._api_lock is None or getattr(self._api_lock, "_loop", None) != current_loop:
            try:
                self._api_lock = AsyncTimeoutLock(
                    "gemini_api_lock",
                    priority=LockPriority.HIGH,
                    timeout=30.0
                )
            except Exception as exc:
                SecurityAwareErrorHandler.log_processing_error(exc, "api_lock_initialization")
        return self._api_lock

    async def detect_sensitive_data_async(
            self,
            extracted_data: Dict[str, Any],
            requested_entities: Optional[List[str]] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Detect sensitive entities in extracted text using the Gemini API.

        This method prepares the input data, validates the requested entities, and processes each
        page in parallel. It then finalizes and filters the detection results.

        Args:
            extracted_data: Dictionary containing text and bounding box information.
            requested_entities: List of entity types to detect.

        Returns:
            Tuple containing the list of processed entities and the redaction mapping.
        """
        start_time = time.time()
        operation_type = "gemini_detection"
        document_type = "document"

        # If no specific entities are requested, log a warning, record the process, and return empty results.
        if requested_entities is None:
            log_warning("[Gemini] No specific entities requested, returning empty results")
            record_keeper.record_processing(
                operation_type=operation_type,
                document_type=document_type,
                entity_types_processed=[],
                processing_time=0.0,
                entity_count=0,
                success=False
            )
            return [], {"pages": []}

        # Validate the requested entities using the Gemini-specific validator.
        try:
            requested_entities_json = json.dumps(requested_entities)
            validated_entities = validate_gemini_requested_entities(requested_entities_json)
        except Exception as e:
            log_error("[Gemini] Entity validation failed: " + str(e))
            record_keeper.record_processing(
                operation_type=operation_type,
                document_type=document_type,
                entity_types_processed=requested_entities,
                processing_time=time.time() - start_time,
                entity_count=0,
                success=False
            )
            return [], {"pages": []}

        # If no valid entities remain after validation, return empty results.
        if not validated_entities:
            log_warning("[Gemini] No valid entities remain after filtering, returning empty results")
            record_keeper.record_processing(
                operation_type=operation_type,
                document_type=document_type,
                entity_types_processed=[],
                processing_time=time.time() - start_time,
                entity_count=0,
                success=False
            )
            return [], {"pages": []}

        # Minimize data to comply with GDPR before further processing.
        minimized_data = minimize_extracted_data(extracted_data)

        try:
            # 1. Prepare pages and mappings.
            pages, page_texts_and_mappings, redaction_mapping = self._prepare_pages_and_mappings(minimized_data)
            if not pages:
                return [], {"pages": []}

            # 2. Process all pages concurrently using parallel processing.
            combined_entities = await self._process_all_pages_in_parallel(
                pages,
                page_texts_and_mappings,
                validated_entities,
                redaction_mapping
            )

            # 3. Finalize the detection results (sorting, metrics update, GDPR recording, etc.).
            final_results, final_redaction_mapping = self._finalize_detection_results(
                pages=pages,
                combined_entities=combined_entities,
                redaction_mapping=redaction_mapping,
                requested_entities=validated_entities,
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
        Prepare pages, reconstructed text, and mapping data from the minimized input.

        This helper method extracts the pages from the input data, reconstructs the full text of
        each page along with its corresponding mapping of words to positions, and initializes a
        redaction mapping structure.

        Args:
            minimized_data: The minimized extracted_data dictionary.

        Returns:
            A tuple containing:
              1. pages: List of page dictionaries.
              2. page_texts_and_mappings: Dictionary mapping page number to (full_text, mapping).
              3. redaction_mapping: Dictionary with a "pages" key to track redaction details.
        """
        pages = minimized_data.get("pages", [])
        page_texts_and_mappings: Dict[int, Tuple[str, List[Tuple[Dict[str, Any], int, int]]]] = {}
        redaction_mapping = {"pages": []}

        # Process each page to reconstruct text and mapping.
        for pg in pages:
            pg_words = pg.get("words", [])
            pg_number = pg.get("page")
            if not pg_words:
                # If no words exist for the page, initialize empty sensitive info.
                redaction_mapping["pages"].append({"page": pg_number, "sensitive": []})
                continue
            try:
                # Reconstruct the full text and mapping from the list of words.
                reconstructed_text, text_mapping = TextUtils.reconstruct_text_and_mapping(pg_words)
                page_texts_and_mappings[pg_number] = (reconstructed_text, text_mapping)
            except Exception as exc:
                # Log errors during text reconstruction.
                SecurityAwareErrorHandler.log_processing_error(exc, "prepare_pages")
        return pages, page_texts_and_mappings, redaction_mapping

    async def _process_all_pages_in_parallel(
        self,
        pages: List[Dict[str, Any]],
        page_texts_and_mappings: Dict[int, Tuple[str, List[Tuple[Dict[str, Any], int, int]]]],
        requested_entities: Optional[List[str]],
        redaction_mapping: Dict[str, List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """
        Process all pages concurrently using ParallelProcessingCore.

        Each page is processed individually by calling _process_single_page.
        The results from all pages are combined into a single list of entities.

        Args:
            pages: List of page dictionaries.
            page_texts_and_mappings: Mapping from page number to (full_text, mapping).
            requested_entities: List of entity types to detect.
            redaction_mapping: Redaction mapping dictionary to be updated.

        Returns:
            Combined list of processed entities from all pages.
        """
        log_info("[OK] Processing {0} pages with Gemini API in parallel".format(len(pages)))
        # Determine the maximum number of API workers based on the number of pages.
        max_api_workers = min(4, len(pages))
        # Process pages concurrently.
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
        # Update the redaction mapping and combine processed entities.
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
        Process a single page using the Gemini API and return its redaction info and detected entities.

        This method extracts the page's full text and mapping, manages usage quotas,
        acquires an API lock, and processes the text via Gemini API. It then extracts
        entities from the response and processes them for redaction.

        Args:
            single_page_data: Dictionary containing the page number and words.
            page_texts_and_mappings: Mapping from page number to (full_text, mapping).
            requested_entities: List of entity types to detect.

        Returns:
            A tuple containing:
              1. page_redaction_info: Dictionary with redaction details for the page.
              2. processed_entities: List of detected entity dictionaries.
        """
        page_start_time = time.time()
        local_page_number = single_page_data.get("page")
        local_words = single_page_data.get("words", [])
        # If there are no words on the page, return empty results.
        if not local_words:
            return {"page": local_page_number, "sensitive": []}, []

        local_full_text, local_mapping = page_texts_and_mappings[local_page_number]

        # Manage API usage for this page.
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
            # Acquire the API lock for exclusive access to the Gemini API.
            api_lock = await self._get_api_lock()
            async with api_lock.acquire_timeout(timeout=45.0):
                # Call the Gemini API to process the text.
                response = await self.gemini_helper.process_text(processed_text, requested_entities)
        finally:
            # Always release the usage slot even if errors occur.
            try:
                await gemini_usage_manager.release_request_slot()
            except Exception as release_error:
                SecurityAwareErrorHandler.log_processing_error(
                    release_error, "gemini_release_slot", f"page_{local_page_number}"
                )

        # If the API did not return a response, log and return empty results.
        if response is None:
            log_warning("[WARNING] Gemini API processing failed on page {0}".format(local_page_number))
            return {"page": local_page_number, "sensitive": []}, []

        # Extract entities from the Gemini API response.
        page_entities = self._extract_entities_from_response(response, local_full_text)
        if not page_entities:
            log_info("[OK] No entities detected on page {0}".format(local_page_number))
            return {"page": local_page_number, "sensitive": []}, []

        detected_entity_count = len(page_entities)
        log_info("[OK] Found {0} entities on page {1}".format(detected_entity_count, local_page_number))

        # Process the entities to generate redaction info.
        processed_entities, page_redaction_info = await self.process_entities_for_page(
            local_page_number, local_full_text, local_mapping, page_entities
        )
        page_time = time.time() - page_start_time
        # Log sensitive operation metrics.
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
        Finalize detection results by sorting pages, updating usage metrics, and recording processing.

        This method sorts the redaction mapping, updates overall usage metrics, records the processing
        details for GDPR compliance, and logs a performance summary.

        Args:
            pages: List of page dictionaries.
            combined_entities: Combined list of processed entities from all pages.
            redaction_mapping: Dictionary containing redaction details.
            requested_entities: List of entity types to detect.
            operation_type: Operation type for logging purposes.
            document_type: Document type for logging purposes.
            start_time: Timestamp marking the start of detection.

        Returns:
            A tuple containing the final list of entities and the updated redaction mapping.
        """
        # Sort the redaction mapping pages by page number.
        redaction_mapping["pages"].sort(key=lambda x: x.get("page", 0))
        total_time = time.time() - start_time
        # Update overall usage metrics.
        self.update_usage_metrics(len(combined_entities), total_time)
        # Record the processing details for audit and GDPR compliance.
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
        Extract entities from the Gemini API response.

        This method delegates the extraction to helper functions that gather raw entities
        and then attempts to enrich them with original text when missing.

        Args:
            api_response: The Gemini API response as a dictionary.
            page_full_text: Full text of the page for reference.

        Returns:
            A list of extracted and enriched entity dictionaries.
        """
        try:
            # Gather raw entities from the response.
            raw_entities = self._gather_raw_entities(api_response)
            # Enrich each entity with the original text if not present.
            enriched_entities = [
                self._maybe_add_original_text(ent, page_full_text)
                for ent in raw_entities
            ]
            return enriched_entities
        except Exception as exc:
            SecurityAwareErrorHandler.log_processing_error(exc, "gemini_response_extraction")
            return []

    @staticmethod
    def _gather_raw_entities(api_response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Gather all raw entities from the Gemini API response structure.

        This method navigates through the nested structure (pages -> text -> entities)
        and aggregates all entity dictionaries into a single list.

        Args:
            api_response: The Gemini API response dictionary.

        Returns:
            A list of raw entity dictionaries.
        """
        all_entities = []
        # Iterate over each page in the response.
        pages_in_response = api_response.get("pages", [])
        for p_data in pages_in_response:
            # Retrieve text entries for the page.
            text_entries = p_data.get("text", [])
            for t_entry in text_entries:
                # Retrieve entities from each text entry.
                entity_list = t_entry.get("entities", [])
                all_entities.extend(entity_list)
        return all_entities

    @staticmethod
    def _maybe_add_original_text(
        entity: Dict[str, Any],
        page_full_text: str
    ) -> Dict[str, Any]:
        """
        Ensure that the entity dictionary contains the 'original_text' field.

        If the 'original_text' is missing, attempt to extract it from the page's full text using the
        'start' and 'end' indices. If extraction fails, log a warning and return the entity unmodified.

        Args:
            entity: A dictionary representing a single entity.
            page_full_text: The full text of the page.

        Returns:
            The updated entity dictionary, including 'original_text' if it was missing.
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
