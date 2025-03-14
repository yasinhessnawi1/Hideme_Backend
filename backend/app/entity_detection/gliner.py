"""
Simplified GLiNER entity detection implementation with improved model persistence.

This module provides a streamlined implementation of the GLiNER entity detector
that downloads the model once and saves it to a local file for future use.
"""
import os
import asyncio
import re
import threading
import time
import torch
from typing import Dict, Any, List, Optional, Tuple, Union

from backend.app.domain import SensitiveEntity

# Import GLiNER with error handling
try:
    from gliner import GLiNER
    GLINER_AVAILABLE = True
except ImportError:
    GLINER_AVAILABLE = False

from backend.app.entity_detection.base import BaseEntityDetector
from backend.app.utils.helpers.text_utils import TextUtils
from backend.app.utils.helpers.parallel_helper import ParallelProcessingHelper
from backend.app.utils.logger import default_logger as logger, log_info, log_warning, log_error
from backend.app.configs.gliner_config import GLINER_MODEL_PATH, GLINER_MODEL_NAME, GLINER_ENTITIES


class GlinerEntityDetector(BaseEntityDetector):
    """
    Service for detecting sensitive information using GLiNER with improved model persistence.

    This implementation downloads the model once and saves it to a local file, then
    loads it from this file for all subsequent requests.
    """

    # Class-level lock for model initialization
    _model_lock = threading.RLock()

    def __init__(
        self,
        model_name: str = GLINER_MODEL_NAME,
        entities: Optional[List[str]] = None,
        local_model_path: Optional[str] = None,
        local_files_only: bool = False
    ):
        """
        Initialize the GLiNER entity detector with improved model persistence.

        Args:
            model_name: Name or path of the GLiNER model to use
            entities: Entity types to detect (initialized lazily if None)
            local_model_path: Path to local model directory
            local_files_only: If True, only use local model files
        """
        self.model_name = model_name
        self.model = None

        # Local model settings
        self.local_model_path = local_model_path
        self.local_files_only = local_files_only
        self.model_file_path = GLINER_MODEL_PATH if local_model_path else None

        # Check if GLiNER is available
        if not GLINER_AVAILABLE:
            log_error("[ERROR] GLiNER package not installed. Please install with 'pip install gliner'")

        # Default entity types with proper casing for GLiNER
        self.default_entities = entities or GLINER_ENTITIES

        # Status tracking
        self._is_initialized = False
        self._initialization_time = None
        self._last_used = time.time()

        # Norwegian pronouns for filtering
        self.norwegian_pronouns = self._init_norwegian_pronouns()

        # Initialize the model
        self._initialize_model()

    def _init_norwegian_pronouns(self) -> set:
        """
        Initialize the set of Norwegian pronouns for filtering.

        Returns:
            Set of Norwegian pronouns in lowercase
        """
        norwegian_pronouns = {
            # Personal pronouns (subject)
            "jeg", "du", "han", "hun", "den", "det", "vi", "dere", "de",
            # Personal pronouns (object)
            "meg", "deg", "ham", "henne", "den", "det", "oss", "dem",
            # Possessive pronouns
            "min", "mi", "mitt", "mine", "din", "di", "ditt", "dine",
            "hans", "hennes", "dens", "dets", "vår", "vårt", "våre",
            "deres", "sin", "si", "sitt", "sine",
            # Reflexive pronouns
            "seg", "selv",
            # Demonstrative pronouns
            "denne", "dette", "disse",
            # Interrogative pronouns
            "hvem", "hva", "hvilken", "hvilket", "hvilke",
            # Indefinite pronouns
            "noen", "noe", "ingen", "ingenting", "alle", "enhver", "ethvert", "hver", "hvert",
            # Relative pronouns
            "som"
        }

        # Convert to lowercase for case-insensitive matching
        return {word.lower() for word in norwegian_pronouns}

    def _initialize_model(self, max_retries: int = 2) -> bool:
        """
        Initialize the GLiNER model with improved persistence.

        Args:
            max_retries: Maximum number of retries for initialization

        Returns:
            True if initialization succeeded, False otherwise
        """
        if not GLINER_AVAILABLE:
            log_error("[ERROR] GLiNER package not installed. Please install with 'pip install gliner'")
            return False

        with self._model_lock:
            # Check if already initialized
            if self._is_initialized and self.model is not None:
                return True

            start_time = time.time()

            # Determine if we should try to load from local file
            local_model_exists = self._check_local_model_exists()

            # Save original local_files_only setting
            original_local_files_only = self.local_files_only

            # Try to initialize with retries
            for attempt in range(max_retries):
                try:
                    if local_model_exists:
                        # Try to load from local file
                        log_info(f"[OK] Loading GLiNER model from local file: {self.model_file_path}")
                        if self._load_local_model(self.model_file_path):
                            break
                        else:
                            local_model_exists = False  # Failed to load, try downloading
                            log_warning("[WARNING] Failed to load GLiNER model from local file, will try downloading")
                            # Reset local_files_only to allow downloading
                            self.local_files_only = False

                    if not local_model_exists:
                        if original_local_files_only:
                            log_warning(
                                "[WARNING] Local model file not found but local_files_only=True, attempting download anyway")

                        # Download from HuggingFace
                        log_info(f"[OK] Downloading GLiNER model from HuggingFace: {self.model_name}")
                        self.model = GLiNER.from_pretrained(self.model_name)

                        # Save model to local file if path is specified
                        if self.local_model_path and self.model_file_path:
                            self._save_model_to_file(self.model_file_path)

                    if self.model is not None:
                        # Update status
                        self._is_initialized = True
                        self._initialization_time = time.time() - start_time
                        self._last_used = time.time()

                        log_info(f"[OK] GLiNER model initialized successfully in {self._initialization_time:.2f}s")

                        # Test model with simple prediction
                        self._test_model()

                        # Restore original local_files_only setting
                        self.local_files_only = original_local_files_only
                        return True

                except Exception as e:
                    log_error(f"[ERROR] Failed to initialize GLiNER model (attempt {attempt + 1}/{max_retries}): {e}")

                # Wait before retry
                if attempt < max_retries - 1:
                    time.sleep(2)  # Short wait between retries

            # Restore original local_files_only setting
            self.local_files_only = original_local_files_only
            return self._is_initialized

    def _check_local_model_exists(self) -> bool:
        """
        Check if a valid local model exists.

        Returns:
            True if a valid local model file exists, False otherwise
        """
        return (
            self.local_model_path and
            self.model_file_path and
            os.path.exists(self.model_file_path) and
            os.path.getsize(self.model_file_path) > 1000000  # Ensure it's a valid file (>1MB)
        )

    def _test_model(self) -> None:
        """Test the GLiNER model with a simple prediction to verify functionality."""
        try:
            test_text = "John Smith works at Microsoft."
            test_entities = ["Person", "Organization"]
            results = self.model.predict_entities(test_text, test_entities, threshold=0.5)
            log_info(f"[OK] GLiNER model test successful. Found {len(results)} entities.")
        except Exception as test_error:
            log_warning(f"[WARNING] GLiNER model test failed: {test_error}")

    def _save_model_to_file(self, model_path: str) -> bool:
        """
        Save model using GLiNER's native method.

        Args:
            model_path: Path where to save the model

        Returns:
            True if saving succeeded, False otherwise
        """
        try:
            if not self.model:
                log_error("[ERROR] Cannot save model - model not initialized")
                return False

            # Create directory
            os.makedirs(os.path.dirname(model_path), exist_ok=True)
            log_info(f"[OK] Saving GLiNER model to directory: {model_path}")

            # Use GLiNER's native save method if available
            if hasattr(self.model, "save_pretrained"):
                self.model.save_pretrained(model_path)
                log_info("[OK] Used GLiNER's native save_pretrained method")
            else:
                # Fallback to manual save
                torch.save(self.model.state_dict(), os.path.join(model_path, "model.pt"))
                if hasattr(self.model, "config"):
                    self.model.config.save_pretrained(model_path)

            log_info(f"[OK] GLiNER model saved successfully to {model_path}")
            return True
        except Exception as e:
            log_error(f"[ERROR] Failed to save model to file: {e}")
            return False

    def _load_local_model(self, model_path: str) -> bool:
        """
        Load model using GLiNER's native method.

        Args:
            model_path: Path to the model directory

        Returns:
            True if loading succeeded, False otherwise
        """
        try:
            log_info(f"[OK] Loading GLiNER model from directory: {model_path}")

            # Check if it's a directory or file
            if os.path.isdir(model_path):
                # Use GLiNER's from_pretrained method
                self.model = GLiNER.from_pretrained(
                    model_path,
                    local_files_only=True
                )
                log_info("[OK] Loaded model using GLiNER's native from_pretrained method")
            else:
                log_error("[ERROR] Expected a directory for model path")
                return False

            return True
        except Exception as e:
            log_error(f"[ERROR] Failed to load local model: {e}")
            return False

    async def detect_sensitive_data_async(
        self,
        extracted_data: Dict[str, Any],
        requested_entities: Optional[List[str]] = None
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        """
        Detect sensitive entities in extracted text using GLiNER with async processing.

        Args:
            extracted_data: Dictionary containing text and bounding box information
            requested_entities: List of entity types to detect

        Returns:
            Tuple of (anonymized_text, results_json, redaction_mapping)
        """
        start_time = time.time()

        # Default empty result in case of errors
        empty_result = ("", [], {"pages": []})

        try:
            # Initialize with the requested entities
            if not requested_entities:
                requested_entities = self.default_entities

            # Make sure the model is initialized
            if not self._is_initialized or self.model is None:
                # Try to initialize again if needed
                success = self._initialize_model()
                if not success:
                    log_error("[ERROR] GLiNER model initialization failed. Returning empty results.")
                    return empty_result

            # Extract all pages (empty pages are already filtered by the extractor)
            pages = extracted_data.get("pages", [])
            if not pages:
                return empty_result

            # Process text reconstruction and prepare for analysis
            page_texts_and_mappings, anonymized_texts, redaction_mapping = self._prepare_page_data(pages)

            # Process all pages in parallel
            log_info(f"[OK] Processing {len(pages)} pages with GLiNER in parallel")

            try:
                page_results = await ParallelProcessingHelper.process_pages_in_parallel(
                    pages,
                    lambda page_data: self._process_page_async(page_data, page_texts_and_mappings, requested_entities)
                )
            except Exception as parallel_error:
                log_error(f"[ERROR] Error in parallel processing: {parallel_error}")
                # Return default empty result if parallel processing fails
                return empty_result

            # Collect and finalize results
            anonymized_text, combined_results, final_redaction_mapping = self._finalize_results(
                page_results, anonymized_texts, redaction_mapping
            )

            # Log performance statistics
            total_time = time.time() - start_time
            entity_count = len(combined_results)
            safe_total_time = max(total_time, 0.001)
            log_info(f"[PERF] GLiNER processing summary: {entity_count} entities across {len(pages)} pages in {total_time:.2f}s "
                    f"({entity_count/safe_total_time:.2f} entities/s)")

            # Update last used timestamp
            self._last_used = time.time()

            return anonymized_text, combined_results, final_redaction_mapping

        except Exception as e:
            log_error(f"[ERROR] Unhandled exception in detect_sensitive_data_async: {e}")
            return empty_result  # Return empty result on any exception

    def _prepare_page_data(self, pages: List[Dict[str, Any]]) -> Tuple[Dict[int, Tuple[str, List]], List[str], Dict[str, Any]]:
        """
        Prepare page data for processing by extracting text and creating mappings.

        Args:
            pages: List of page dictionaries with word data

        Returns:
            Tuple of (page_texts_and_mappings, anonymized_texts, redaction_mapping)
        """
        page_texts_and_mappings = {}
        anonymized_texts = []
        redaction_mapping = {"pages": []}

        for page in pages:
            words = page.get("words", [])
            page_number = page.get("page")

            # Skip pages with no content
            if not words:
                redaction_mapping["pages"].append({"page": page_number, "sensitive": []})
                continue

            # Check if page has actual content (not just empty strings)
            has_content = False
            for word in words:
                if word.get("text", "").strip():
                    has_content = True
                    break

            if not has_content:
                log_info(f"[OK] Skipping empty page {page_number}")
                redaction_mapping["pages"].append({"page": page_number, "sensitive": []})
                continue

            full_text, mapping = TextUtils.reconstruct_text_and_mapping(words)
            anonymized_texts.append(full_text)
            page_texts_and_mappings[page_number] = (full_text, mapping)

        return page_texts_and_mappings, anonymized_texts, redaction_mapping

    async def _process_page_async(
        self,
        page_data: Dict[str, Any],
        page_texts_and_mappings: Dict[int, Tuple[str, List]],
        requested_entities: List[str]
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Process a single page asynchronously to detect entities.

        Args:
            page_data: Dictionary with page information
            page_texts_and_mappings: Dictionary mapping page numbers to (text, mapping) tuples
            requested_entities: List of entity types to detect

        Returns:
            Tuple of (page_redaction_info, processed_entities)
        """
        try:
            page_start_time = time.time()
            page_number = page_data.get("page")
            words = page_data.get("words", [])

            if not words:
                return {"page": page_number, "sensitive": []}, []

            # Get the text and mapping for this page
            full_text, mapping = page_texts_and_mappings.get(page_number, ("", []))

            # Safety check for empty text or mapping
            if not full_text or not mapping:
                return {"page": page_number, "sensitive": []}, []

            # Process text with GLiNER (this will run in a thread)
            log_info(f"[OK] Processing text with GLiNER on page {page_number}")
            page_entities = await asyncio.to_thread(self._process_text_with_gliner, full_text, requested_entities)

            if not page_entities:
                log_info(f"[OK] No entities detected by GLiNER on page {page_number}")
                return {"page": page_number, "sensitive": []}, []

            entity_count = len(page_entities)
            log_info(f"[OK] Found {entity_count} entities on page {page_number}")

            # Process entities for this page
            entity_start_time = time.time()
            try:
                processed_entities, page_redaction_info = self.process_entities_for_page(
                    page_number, full_text, mapping, page_entities
                )
            except Exception as entity_error:
                log_error(f"[ERROR] Error processing entities: {entity_error}")
                # Return empty result for this page on error
                return {"page": page_number, "sensitive": []}, []

            # Log performance metrics
            self._log_page_performance(page_number, entity_count, entity_start_time, page_start_time)

            return page_redaction_info, processed_entities

        except Exception as e:
            logger.error(f"[ERROR] Error processing page {page_data.get('page')}: {str(e)}")
            return {"page": page_data.get('page'), "sensitive": []}, []

    def _log_page_performance(self, page_number: int, entity_count: int, entity_start_time: float, page_start_time: float) -> None:
        """
        Log performance metrics for page processing.

        Args:
            page_number: Current page number
            entity_count: Number of entities detected
            entity_start_time: Time when entity processing started
            page_start_time: Time when page processing started
        """
        entity_time = time.time() - entity_start_time
        page_time = time.time() - page_start_time

        # Log performance metrics with safety against division by zero
        if entity_count > 0:
            safe_entity_time = max(entity_time, 0.001)  # Ensure minimum time to prevent division by zero
            log_info(f"[PERF] Page {page_number}: {entity_count} entities processed in {entity_time:.2f}s "
                    f"({entity_count/safe_entity_time:.2f} entities/s)")
        else:
            log_info(f"[PERF] Page {page_number}: No entities processed")

        log_info(f"[PERF] Page {page_number} total processing time: {page_time:.2f}s")

    def _finalize_results(
        self,
        page_results: List[Tuple[int, Tuple[Dict[str, Any], List[Dict[str, Any]]]]],
        anonymized_texts: List[str],
        redaction_mapping: Dict[str, Any]
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        """
        Finalize detection results by combining page results.

        Args:
            page_results: List of tuples with page number and processing results
            anonymized_texts: List of page texts
            redaction_mapping: Initial redaction mapping dictionary

        Returns:
            Tuple of (anonymized_text, combined_results, redaction_mapping)
        """
        combined_results = []

        # Collect all results
        for page_number, (page_redaction_info, processed_entities) in page_results:
            if page_redaction_info:
                redaction_mapping["pages"].append(page_redaction_info)
            if processed_entities:
                combined_results.extend(processed_entities)

        # Sort redaction mapping pages by page number
        redaction_mapping["pages"].sort(key=lambda x: x.get("page", 0))

        # Create combined anonymized text
        anonymized_text = "\n".join(anonymized_texts)

        return anonymized_text, combined_results, redaction_mapping

    def _process_text_with_gliner(self, text: str, requested_entities: List[str]) -> List[Dict[str, Any]]:
        """
        Process text with GLiNER to extract entities.

        Args:
            text: Text to process
            requested_entities: List of entity types to detect

        Returns:
            List of detected entities
        """
        try:
            if not text or len(text.strip()) < 3:
                return []

            # Ensure model is initialized
            if not self._is_initialized or self.model is None:
                success = self._initialize_model()
                if not success:
                    log_error("[ERROR] GLiNER model initialization failed in _process_text_with_gliner")
                    return []

            # Update last used timestamp
            self._last_used = time.time()

            # Split text into paragraphs for efficient processing
            paragraphs = [p for p in text.split('\n') if p.strip()]

            # Process all paragraphs and collect entities
            all_entities = []

            for paragraph in paragraphs:
                if not paragraph.strip():
                    continue

                # Process paragraph and get entities
                paragraph_entities = self._process_paragraph(paragraph, text, requested_entities)
                all_entities.extend(paragraph_entities)

            # Deduplicate and filter entities
            deduplicated_entities = self._deduplicate_entities(all_entities)
            filtered_entities = self._filter_norwegian_pronouns(deduplicated_entities)

            return filtered_entities

        except Exception as e:
            logger.error(f"[ERROR] Error in _process_text_with_gliner: {e}")
            return []

    def _process_paragraph(self, paragraph: str, full_text: str, requested_entities: List[str]) -> List[Dict[str, Any]]:
        """
        Process a single paragraph to extract entities.

        Args:
            paragraph: Paragraph text to process
            full_text: The full document text (for offset calculation)
            requested_entities: List of entity types to detect

        Returns:
            List of entities detected in the paragraph
        """
        # Use fixed window size (based on GLiNER's 384 token limit)
        max_tokens = 300  # Conservative estimate to avoid truncation
        entities = []

        # Calculate base offset for this paragraph in the full text
        base_offset = full_text.find(paragraph)
        if base_offset == -1:  # Safety check
            return []

        # If paragraph is short enough, process directly
        if len(paragraph.split()) <= max_tokens:
            try:
                paragraph_entities = self.model.predict_entities(
                    paragraph,
                    requested_entities,
                    threshold=0.5
                )

                # Add entities with correct offsets
                for entity in paragraph_entities:
                    entity_dict = {
                        "entity_type": entity.get("label", "UNKNOWN").upper(),
                        "start": base_offset + entity.get("start", 0),
                        "end": base_offset + entity.get("end", 0),
                        "score": entity.get("score", 0.5),
                        "original_text": entity.get("text", "")
                    }
                    entities.append(entity_dict)
            except Exception as e:
                log_warning(f"[WARNING] Error processing paragraph: {e}")

        else:
            # Process long paragraph by splitting into sentence groups
            sentence_groups = self._split_into_sentence_groups(paragraph, max_tokens)

            # Process each sentence group
            for group in sentence_groups:
                group_entities = self._process_text_group(group, paragraph, full_text, requested_entities)
                entities.extend(group_entities)

        return entities

    def _split_into_sentence_groups(self, text: str, max_tokens: int) -> List[str]:
        """
        Split text into groups of sentences that fit within token limit.

        Args:
            text: Text to split
            max_tokens: Maximum tokens per group

        Returns:
            List of sentence groups
        """
        # Split text into sentences
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]

        # Group sentences to stay within token limit
        groups = []
        current_group = ""

        for sentence in sentences:
            # If adding this sentence would exceed our limit
            if len(current_group.split()) + len(sentence.split()) > max_tokens:
                # Save current group if not empty
                if current_group:
                    groups.append(current_group)

                # Handle very long sentences
                if len(sentence.split()) > max_tokens:
                    # This sentence alone exceeds the limit, add it separately
                    groups.append(sentence)
                else:
                    # Start a new group with this sentence
                    current_group = sentence
            else:
                # Add to current group
                if current_group:
                    current_group += " " + sentence
                else:
                    current_group = sentence

        # Add final group if not empty
        if current_group:
            groups.append(current_group)

        return groups

    def _process_text_group(self, text_group: str, paragraph: str, full_text: str, requested_entities: List[str]) -> List[Dict[str, Any]]:
        """
        Process a group of text (sentences) to extract entities.

        Args:
            text_group: Text group to process
            paragraph: Parent paragraph containing the text group
            full_text: The full document text
            requested_entities: List of entity types to detect

        Returns:
            List of entities detected in the text group
        """
        entities = []

        try:
            # Find position of this group in the paragraph
            group_offset = paragraph.find(text_group)
            if group_offset == -1:
                return []

            # Find position of paragraph in full text
            para_offset = full_text.find(paragraph)
            if para_offset == -1:
                return []

            # Calculate absolute offset in full text
            abs_offset = para_offset + group_offset

            # Process with GLiNER
            group_entities = self.model.predict_entities(
                text_group,
                requested_entities,
                threshold=0.5
            )

            # Add entities with correct offsets
            for entity in group_entities:
                entity_dict = {
                    "entity_type": entity.get("label", "UNKNOWN").upper(),
                    "start": abs_offset + entity.get("start", 0),
                    "end": abs_offset + entity.get("end", 0),
                    "score": entity.get("score", 0.5),
                    "original_text": entity.get("text", "")
                }
                entities.append(entity_dict)

        except Exception as e:
            log_warning(f"[WARNING] Error processing text group: {e}")

        return entities

    def _deduplicate_entities(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deduplicate entities based on type, start, and end positions.

        Args:
            entities: List of entities to deduplicate

        Returns:
            Deduplicated list of entities
        """
        deduplicated_entities = []
        seen = set()

        for entity in entities:
            entity_key = (entity["entity_type"], entity["start"], entity["end"])
            if entity_key not in seen:
                seen.add(entity_key)
                deduplicated_entities.append(entity)

        return deduplicated_entities

    def _filter_norwegian_pronouns(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter out Norwegian pronouns that are incorrectly identified as person names.

        Args:
            entities: List of detected entities

        Returns:
            Filtered list of entities without Norwegian pronouns
        """
        # Filter out entities that match Norwegian pronouns
        filtered_entities = []
        for entity in entities:
            # Only apply filtering to PERSON entity types
            if entity["entity_type"] == "PERSON" or entity["entity_type"] == "PER":
                # Get the text of the entity
                entity_text = entity.get("original_text", "").strip()

                # Skip if it's a single-word entity that matches a Norwegian pronoun
                entity_words = entity_text.split()

                if len(entity_words) == 1 and entity_words[0].lower() in self.norwegian_pronouns:
                    log_info(f"[FILTER] Removed Norwegian pronoun '{entity_text}' incorrectly detected as PERSON")
                    continue

                # For multi-word entities, check if every word is a pronoun
                if len(entity_words) > 1 and all(word.lower() in self.norwegian_pronouns for word in entity_words):
                    log_info(f"[FILTER] Removed compound Norwegian pronoun '{entity_text}' incorrectly detected as PERSON")
                    continue

            # Keep all other entities
            filtered_entities.append(entity)

        return filtered_entities

    def _convert_to_entity_dict(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert a GLiNER entity to a standardized dictionary format.

        Args:
            entity: GLiNER entity dictionary

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

    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the GLiNER detector.

        Returns:
            Dictionary with status information
        """
        return {
            "initialized": self._is_initialized,
            "model_available": self.model is not None,
            "model_name": self.model_name,
            "initialization_time": self._initialization_time,
            "last_used": self._last_used,
            "idle_time": time.time() - self._last_used if self._last_used else None,
            "gliner_package_available": GLINER_AVAILABLE,
            "local_model_path": self.local_model_path,
            "local_files_only": self.local_files_only,
            "model_file_path": self.model_file_path
        }

    def detect_sensitive_data(
        self,
        extracted_data: Dict[str, Any],
        requested_entities: Optional[List[str]] = None
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        """
        Detect sensitive entities in extracted text. Synchronous wrapper.

        Args:
            extracted_data: Dictionary containing text and bounding box information
            requested_entities: List of entity types to detect

        Returns:
            Tuple of (anonymized_text, results_json, redaction_mapping)
        """
        # Create an event loop for the synchronous method
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.detect_sensitive_data_async(extracted_data, requested_entities)
            )
        finally:
            loop.close()