"""
Hybrid entity detection implementation combining multiple detection engines.

This module provides a dedicated implementation of the HybridEntityDetector
that properly handles asynchronous operations and event loops, and uses cached
detector instances from the initialization service when available.
"""
import asyncio
from typing import Dict, Any, List, Optional, Tuple

from backend.app.domain.interfaces import EntityDetector
from backend.app.utils.logger import log_info, log_warning
from backend.app.services.initialization_service import initialization_service


class HybridEntityDetector(EntityDetector):
    """
    A hybrid entity detector that combines results from multiple engines.

    This detector runs all configured detection engines and merges their results,
    with proper handling of async/sync operations and event loops. It also uses
    cached detector instances from the initialization service when available.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the hybrid detector with configuration.

        Args:
            config: Configuration dictionary with settings for each detector
        """
        self.detectors = []
        self.config = config

        # If pre-created detectors are provided, use them directly
        if "detectors" in config and isinstance(config["detectors"], list):
            self.detectors = config["detectors"]
            detector_types = [type(d).__name__ for d in self.detectors]
            log_info(f"[HYBRID] Using pre-created detectors: {detector_types}")
            return

        # Create detectors based on configuration, using cached instances from initialization service
        if config.get("use_presidio", True):
            # Get cached Presidio detector
            detector = initialization_service.get_presidio_detector()
            self.detectors.append(detector)

        if config.get("use_gemini", False):
            # Get cached Gemini detector
            detector = initialization_service.get_gemini_detector()
            self.detectors.append(detector)

        if config.get("use_gliner", False):
            # For GLiNER, get the specific model based on requested entities
            entity_list = config.get("entities", [])

            # Get cached GLiNER detector
            detector = initialization_service.get_gliner_detector(entity_list)
            self.detectors.append(detector)

        if not self.detectors:
            # Default to Presidio if no detectors specified
            detector = initialization_service.get_presidio_detector()
            self.detectors.append(detector)

        detector_types = [type(d).__name__ for d in self.detectors]
        log_info(f"[OK] Created hybrid entity detector with {len(self.detectors)} detection engines: {detector_types}")

    async def detect_sensitive_data_async(
            self,
            extracted_data: Dict[str, Any],
            requested_entities: Optional[List[str]] = None
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        """
        Detect sensitive entities using multiple detection engines asynchronously.

        Args:
            extracted_data: Dictionary containing text and bounding box information
            requested_entities: List of entity types to detect

        Returns:
            Tuple of (anonymized_text, results_json, redaction_mapping)
        """
        all_entities = []
        all_redaction_mappings = []
        anonymized_text = None

        # Run detection with each engine
        for detector in self.detectors:
            engine_name = type(detector).__name__
            try:
                log_info(f"[OK] Running detection with {engine_name}")

                if hasattr(detector, 'detect_sensitive_data_async'):
                    # Use async version if available
                    anon_text, entities, redaction_mapping = await detector.detect_sensitive_data_async(
                        extracted_data, requested_entities
                    )
                else:
                    # Fall back to sync version if needed
                    anon_text, entities, redaction_mapping = await asyncio.to_thread(
                        detector.detect_sensitive_data,
                        extracted_data, requested_entities
                    )

                # Log detection results
                log_info(f"[OK] {engine_name} found {len(entities)} entities")

                # Use the first anonymized text (we'll merge entities, not text)
                if anonymized_text is None:
                    anonymized_text = anon_text

                all_entities.extend(entities)
                all_redaction_mappings.append(redaction_mapping)
            except Exception as e:
                log_warning(f"[WARNING] Error with detector {engine_name}: {e}")
                continue

        # Merge redaction mappings
        merged_mapping = self._merge_redaction_mappings(all_redaction_mappings)

        return anonymized_text or "", all_entities, merged_mapping

    def detect_sensitive_data(
            self,
            extracted_data: Dict[str, Any],
            requested_entities: Optional[List[str]] = None
    ) -> tuple[str, list[Any], dict[str, list[Any]]] | None | tuple[str, list[Any], dict[str, list[Any]]] | tuple[
        str, list[Any], dict[str, list[Any]]]:
        """
        Detect sensitive entities using multiple detection engines (sync wrapper).

        Args:
            extracted_data: Dictionary containing text and bounding box information
            requested_entities: List of entity types to detect

        Returns:
            Tuple of (anonymized_text, results_json, redaction_mapping)
        """
        try:
            # Create a new event loop for this method
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    self.detect_sensitive_data_async(extracted_data, requested_entities)
                )
            finally:
                loop.close()
        except RuntimeError as e:
            if "cannot schedule new futures after interpreter shutdown" in str(e):
                # Handle the case where we're shutting down
                log_warning(f"[WARNING] Shutdown in progress, returning empty results: {e}")
                return "", [], {"pages": []}
            log_warning(f"[WARNING] Runtime error in detect_sensitive_data: {e}")
            # In case of event loop issues, attempt to return something useful
            return "", [], {"pages": []}
        except Exception as e:
            log_warning(f"[WARNING] Unexpected error in detect_sensitive_data: {e}")
            return "", [], {"pages": []}

    def _merge_redaction_mappings(
            self,
            redaction_mappings: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Merge multiple redaction mappings into one.

        Args:
            redaction_mappings: List of redaction mappings to merge

        Returns:
            Merged redaction mapping
        """
        if not redaction_mappings:
            return {"pages": []}

        merged = {"pages": []}
        page_mappings = {}

        # Group mappings by page
        for mapping in redaction_mappings:
            for page_info in mapping.get("pages", []):
                page_num = page_info.get("page")
                sensitive_items = page_info.get("sensitive", [])

                if page_num not in page_mappings:
                    page_mappings[page_num] = []

                page_mappings[page_num].extend(sensitive_items)

        # Create merged mapping
        for page_num, sensitive_items in sorted(page_mappings.items()):
            merged["pages"].append({
                "page": page_num,
                "sensitive": sensitive_items
            })

        return merged