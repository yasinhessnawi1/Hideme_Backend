"""
Gemini AI-based entity detection implementation with enhanced GDPR compliance, error handling, and improved synchronization.

This module provides a robust implementation of entity detection using Google's Gemini API
with improved security features, GDPR compliance, and standardized error handling.
"""
import asyncio
import time
from typing import Dict, Any, List, Optional, Tuple

from backend.app.entity_detection.base import BaseEntityDetector
from backend.app.utils.data_minimization import minimize_extracted_data
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.helpers.gemini_helper import GeminiHelper
# Import the usage manager
from backend.app.utils.helpers.gemini_usage_manager import gemini_usage_manager
from backend.app.utils.helpers.parallel_helper import ParallelProcessingHelper
from backend.app.utils.helpers.text_utils import TextUtils
from backend.app.utils.logger import log_info, log_warning, log_error
from backend.app.utils.processing_records import record_keeper
from backend.app.utils.secure_logging import log_sensitive_operation
from backend.app.utils.synchronization_utils import AsyncTimeoutLock, LockPriority


class GeminiEntityDetector(BaseEntityDetector):
    """
    Enhanced service for detecting sensitive information using Gemini AI
    with advanced usage management, GDPR compliance, and error handling.
    """

    def __init__(self):
        """Initialize the Gemini entity detector."""
        super().__init__()
        self.gemini_helper = GeminiHelper()
        # Replace basic asyncio.Lock with AsyncTimeoutLock for better timeout handling
        self.api_lock = AsyncTimeoutLock("gemini_api_lock",
                                        priority=LockPriority.HIGH,
                                        timeout=30.0)

    async def detect_sensitive_data_async(
        self,
        extracted_data: Dict[str, Any],
        requested_entities: Optional[List[str]] = None
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        """
        Detect sensitive entities in extracted text using the Gemini API
        with advanced usage management and GDPR compliance features.

        Args:
            extracted_data: Dictionary containing text and bounding box information
            requested_entities: List of entity types to detect

        Returns:
            Tuple of (anonymized_text, results_json, redaction_mapping)
        """
        start_time = time.time()

        # Apply data minimization principles
        minimized_data = minimize_extracted_data(extracted_data)

        # Track processing for GDPR compliance
        operation_type = "gemini_detection"
        document_type = "document"

        try:
            # Extract all pages
            pages = minimized_data.get("pages", [])
            if not pages:
                return "", [], {"pages": []}

            # Process text reconstruction sequentially
            page_texts_and_mappings = {}
            anonymized_texts = []
            redaction_mapping = {"pages": []}

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

                    # Call Gemini API with processed text - now with proper timeout lock
                    log_info(f"[OK] Processing text with Gemini API on page {page_number}")

                    # Use the AsyncTimeoutLock with proper timeout handling
                    async with self.api_lock.acquire_timeout(timeout=45.0):
                        response = await self.gemini_helper.process_text(processed_text, requested_entities)

                    # Release API request slot
                    try:
                        await gemini_usage_manager.release_request_slot()
                    except Exception as release_error:
                        SecurityAwareErrorHandler.log_processing_error(
                            release_error, "gemini_release_slot", f"page_{page_number}"
                        )

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

                    # Process entities for this page
                    processed_entities, page_redaction_info = await self.process_entities_for_page(
                        page_number, full_text, mapping, page_entities
                    )

                    # Log performance metrics
                    page_time = time.time() - page_start_time
                    log_sensitive_operation(
                        "Gemini Page Detection",
                        len(processed_entities),
                        page_time,
                        page_number=page_number
                    )

                    return page_redaction_info, processed_entities

                except Exception as e:
                    # Use standardized error handling
                    SecurityAwareErrorHandler.log_processing_error(
                        e, "gemini_page_processing", f"page_{page_data.get('page', 'unknown')}"
                    )
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
            combined_results = []
            for page_number, (page_redaction_info, processed_entities) in page_results:
                if page_redaction_info:
                    redaction_mapping["pages"].append(page_redaction_info)
                if processed_entities:
                    combined_results.extend(processed_entities)

            # Sort redaction mapping pages by page number
            redaction_mapping["pages"].sort(key=lambda x: x.get("page", 0))

            # Calculate processing time and update metrics
            total_time = time.time() - start_time
            self.update_usage_metrics(len(combined_results), total_time)

            # Record the processing operation for GDPR compliance
            record_keeper.record_processing(
                operation_type=operation_type,
                document_type=document_type,
                entity_types_processed=requested_entities or [],
                processing_time=total_time,
                entity_count=len(combined_results),
                success=True
            )

            # Log performance statistics and usage summary
            entity_count = len(combined_results)
            log_info(f"[PERF] Gemini processing summary: {entity_count} entities across {len(pages)} pages in {total_time:.2f}s "
                    f"({entity_count/total_time:.2f} entities/s)")

            # Log usage summary
            usage_summary = gemini_usage_manager.get_usage_summary()
            log_info(f"[USAGE] Gemini API Usage: {usage_summary}")

            # Return results
            anonymized_text = "\n".join(anonymized_texts)
            return anonymized_text, combined_results, redaction_mapping

        except Exception as e:
            # Log error with standardized handling
            log_error(f"[ERROR] Error in Gemini detection: {str(e)}")

            # Record failed processing for GDPR compliance
            record_keeper.record_processing(
                operation_type=operation_type,
                document_type=document_type,
                entity_types_processed=requested_entities or [],
                processing_time=time.time() - start_time,
                entity_count=0,
                success=False
            )

            # Return empty results to avoid crashing
            return "", [], {"pages": []}

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

            return self.sanitize_entities(entities)
        except Exception as e:
            # Use standardized error handling
            SecurityAwareErrorHandler.log_processing_error(e, "gemini_response_extraction")
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