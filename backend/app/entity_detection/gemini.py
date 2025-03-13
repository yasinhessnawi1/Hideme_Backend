"""
Gemini AI-based entity detection implementation with advanced usage management.
"""
import asyncio
import threading
import time
from typing import Dict, Any, List, Optional, Tuple, Union

from backend.app.entity_detection.base import BaseEntityDetector
from backend.app.utils.helpers.gemini_helper import GeminiHelper
from backend.app.utils.helpers.text_utils import TextUtils
from backend.app.utils.helpers.parallel_helper import ParallelProcessingHelper
from backend.app.utils.logger import default_logger as logger, log_info, log_warning

# Import the new usage manager
from backend.app.utils.helpers.gemini_usage_manager import gemini_usage_manager


class GeminiEntityDetector(BaseEntityDetector):
    """
    Enhanced service for detecting sensitive information using Gemini AI
    with advanced usage management and parallel processing.
    """

    def __init__(self):
        """Initialize the Gemini entity detector."""
        self.gemini_helper = GeminiHelper()
        self.api_lock = threading.RLock()
        self._initialization_time = time.time()
        self._last_used = self._initialization_time

    def detect_sensitive_data(
        self,
        extracted_data: Dict[str, Any],
        requested_entities: Optional[List[str]] = None
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        """
        Synchronous method to detect sensitive entities in extracted text.

        Args:
            extracted_data: Dictionary containing text and bounding box information
            requested_entities: List of entity types to detect

        Returns:
            Tuple of (anonymized_text, results_json, redaction_mapping)
        """
        try:
            # Run the async method in an event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    self.detect_sensitive_data_async(extracted_data, requested_entities)
                )
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"[ERROR] Error in synchronous sensitive data detection: {e}")
            # Return empty results in case of failure
            return "", [], {"pages": []}

    async def detect_sensitive_data_async(
        self,
        extracted_data: Dict[str, Any],
        requested_entities: Optional[List[str]] = None
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        """
        Detect sensitive entities in extracted text using the Gemini API
        with advanced usage management.

        Args:
            extracted_data: Dictionary containing text and bounding box information
            requested_entities: List of entity types to detect

        Returns:
            Tuple of (anonymized_text, results_json, redaction_mapping)
        """
        start_time = time.time()
        combined_results = []
        redaction_mapping = {"pages": []}
        anonymized_texts = []

        # Extract all pages
        pages = extracted_data.get("pages", [])
        if not pages:
            return "", [], {"pages": []}

        # Process text reconstruction sequentially
        page_texts_and_mappings = {}
        for page in pages:
            words = page.get("words", [])
            page_number = page.get("page")

            if not words:
                redaction_mapping["pages"].append({"page": page_number, "sensitive": []})
                continue

            full_text, mapping = TextUtils.reconstruct_text_and_mapping(words)
            anonymized_texts.append(full_text)
            page_texts_and_mappings[page_number] = (full_text, mapping)

        # Define a function to process a single page
        async def process_page(page_data):
            try:
                page_start_time = time.time()
                page_number = page_data.get("page")
                words = page_data.get("words", [])

                if not words:
                    return {"page": page_number, "sensitive": []}, []

                # Get the text and mapping for this page
                full_text, mapping = page_texts_and_mappings[page_number]

                # Use usage manager to manage text processing
                processed_text = await gemini_usage_manager.manage_page_processing(
                    full_text,
                    requested_entities,
                    page_number
                )

                if processed_text is None:
                    log_warning(f"[WARNING] Page {page_number} processing blocked by usage manager")
                    return {"page": page_number, "sensitive": []}, []

                # Call Gemini API with processed text
                log_info(f"[OK] Processing text with Gemini API on page {page_number}")
                response = await asyncio.to_thread(
                    self.gemini_helper.process_text,
                    processed_text,
                    requested_entities
                )

                # Release API request slot
                try:
                    await gemini_usage_manager.release_request_slot()
                except Exception as release_error:
                    log_warning(f"[WARNING] Error releasing request slot: {release_error}")

                if response is None:
                    log_warning(f"[WARNING] Gemini API processing failed on page {page_number}")
                    return {"page": page_number, "sensitive": []}, []

                # Extract entities from response
                page_entities = self._extract_entities_from_response(response, full_text)

                if not page_entities:
                    log_info(f"[OK] No entities detected on page {page_number}")
                    return {"page": page_number, "sensitive": []}, []

                entity_count = len(page_entities)
                log_info(f"[OK] Found {entity_count} entities on page {page_number}")

                # Process entities for this page in parallel if there are many entities
                entity_start_time = time.time()
                if entity_count > 5:
                    processed_entities, page_redaction_info = await ParallelProcessingHelper.process_entities_in_parallel(
                        self, full_text, mapping, page_entities, page_number
                    )
                else:
                    # For small numbers of entities, process sequentially
                    processed_entities, page_redaction_info = self.process_entities_for_page(
                        page_number, full_text, mapping, page_entities
                    )

                entity_time = time.time() - entity_start_time
                page_time = time.time() - page_start_time

                # Log performance metrics with safety against division by zero
                if entity_count > 0:
                    safe_entity_time = max(entity_time, 0.001)  # Ensure minimum time to prevent division by zero
                    log_info(f"[PERF] Page {page_number}: {entity_count} entities processed in {entity_time:.2f}s "
                             f"({entity_count / safe_entity_time:.2f} entities/s)")
                else:
                    log_info(f"[PERF] Page {page_number}: No entities processed")

                log_info(f"[PERF] Page {page_number} total processing time: {page_time:.2f}s")

                return page_redaction_info, processed_entities

            except Exception as e:
                logger.error(f"[ERROR] Error processing page {page_data.get('page')}: {str(e)}")
                return {"page": page_data.get('page'), "sensitive": []}, []

        # Process all pages in parallel
        log_info(f"[OK] Processing {len(pages)} pages with Gemini API in parallel")
        max_api_workers = min(4, len(pages))  # Limit concurrent API calls

        page_results = await ParallelProcessingHelper.process_pages_in_parallel(
            pages,
            process_page,
            max_workers=max_api_workers
        )

        # Collect all results
        for page_number, (page_redaction_info, processed_entities) in page_results:
            if page_redaction_info:
                redaction_mapping["pages"].append(page_redaction_info)
            if processed_entities:
                combined_results.extend(processed_entities)

        # Sort redaction mapping pages by page number
        redaction_mapping["pages"].sort(key=lambda x: x.get("page", 0))

        # Update last used timestamp
        self._last_used = time.time()

        # Log performance statistics
        total_time = time.time() - start_time
        entity_count = len(combined_results)
        log_info(f"[PERF] Gemini processing summary: {entity_count} entities across {len(pages)} pages in {total_time:.2f}s "
                f"({entity_count/total_time:.2f} entities/s)")

        # Log usage summary
        usage_summary = gemini_usage_manager.get_usage_summary()
        log_info(f"[USAGE] Gemini API Usage: {usage_summary}")

        # Return results
        anonymized_text = "\n".join(anonymized_texts)
        return anonymized_text, combined_results, redaction_mapping

    def _extract_entities_from_response(
        self,
        response: Dict[str, Any],
        full_text: str
    ) -> List[Dict[str, Any]]:
        """
        Extract entities from Gemini API response.

        Args:
            response: Gemini API response dictionary
            full_text: Full text of the document page

        Returns:
            List of extracted entities
        """
        entities = []

        try:
            # Extract entities from the Gemini response structure
            for page_data in response.get("pages", []):
                for text_entry in page_data.get("text", []):
                    for entity in text_entry.get("entities", []):
                        # Ensure original_text is included if not already present
                        if "original_text" not in entity and "start" in entity and "end" in entity:
                            try:
                                start = int(entity["start"])
                                end = int(entity["end"])
                                if 0 <= start < end <= len(full_text):
                                    entity["original_text"] = full_text[start:end]
                            except (ValueError, IndexError, TypeError):
                                log_warning("[WARNING] Could not extract original_text from entity indices")

                        entities.append(entity)

            return entities
        except Exception as e:
            logger.error(f"[ERROR] Error extracting entities from Gemini response: {e}")
            return []

    def _convert_to_entity_dict(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert a Gemini entity to a standardized dictionary.

        Args:
            entity: Entity dictionary from Gemini API

        Returns:
            Standardized entity dictionary
        """
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