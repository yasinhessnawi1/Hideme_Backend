"""
Optimized GLiNER entity detection implementation with proper initialization flag handling.

This module ensures the _is_initialized flag is correctly set after model loading.
"""
import os
import asyncio
import re
import threading
import time
import shutil
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
from backend.app.utils.sanitize_utils import deduplicate_entities


class GlinerEntityDetector(BaseEntityDetector):
    """
    Service for detecting sensitive information using GLiNER with proper initialization flag handling.
    """

    # Class-level lock for model initialization
    _model_lock = threading.RLock()

    # Class-level flag to track initialization status
    _global_initializing = False

    # Class-level variable to track initialization time
    _global_initialization_time = None

    def __init__(
        self,
        model_name: str = GLINER_MODEL_NAME,
        entities: Optional[List[str]] = None,
        local_model_path: Optional[str] = None,
        local_files_only: bool = False
    ):
        """
        Initialize the GLiNER entity detector with proper initialization flag handling.

        Args:
            model_name: Name or path of the GLiNER model to use
            entities: Entity types to detect (initialized lazily if None)
            local_model_path: Path to local model directory
            local_files_only: If True, only use local model files
        """
        self.model_name = model_name
        self.model = None

        # Local model settings
        self.local_model_path = local_model_path or os.path.dirname(GLINER_MODEL_PATH)
        self.local_files_only = local_files_only
        self.model_dir_path = GLINER_MODEL_PATH

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
        Initialize the GLiNER model with proper initialization flag handling.

        Args:
            max_retries: Maximum number of retries for initialization

        Returns:
            True if initialization succeeded, False otherwise
        """
        if not GLINER_AVAILABLE:
            log_error("[ERROR] GLiNER package not installed. Please install with 'pip install gliner'")
            return False

        # Check if already initialized
        if self._is_initialized and self.model is not None:
            return True

        # If global initialization is in progress, wait for it to complete
        with self._model_lock:
            if GlinerEntityDetector._global_initializing:
                # Another thread is initializing, wait a bit and check if it completes
                init_start_time = time.time()
                max_wait_time = 60  # Wait up to 60 seconds

                log_info("[GLINER] Another thread is initializing the GLiNER model, waiting...")

                while GlinerEntityDetector._global_initializing and (time.time() - init_start_time) < max_wait_time:
                    # Release the lock temporarily
                    self._model_lock.release()
                    time.sleep(1)  # Wait for 1 second
                    self._model_lock.acquire()

                # Check if initialization completed while waiting
                if not GlinerEntityDetector._global_initializing and GlinerEntityDetector._global_initialization_time:
                    # Model was initialized by another thread
                    self._is_initialized = True
                    self._initialization_time = GlinerEntityDetector._global_initialization_time
                    self._last_used = time.time()
                    return True

                # If still initializing after max wait time, continue with own initialization
                if GlinerEntityDetector._global_initializing:
                    log_warning("[GLINER] Timeout waiting for another thread to initialize GLiNER model, proceeding with own initialization")

            # Set global initializing flag
            GlinerEntityDetector._global_initializing = True

        try:
            start_time = time.time()

            # Determine if we should try to load from local model directory
            local_model_exists = self._check_local_model_exists()
            log_info(f"[GLINER] Local model exists check: {local_model_exists}")

            if local_model_exists:
                log_info(f"[GLINER] Model directory contents: {os.listdir(self.model_dir_path)}")

                # Fix configuration file discrepancy if needed
                self._fix_config_file_discrepancy()

            # Save original local_files_only setting
            original_local_files_only = self.local_files_only

            # Try to initialize with retries
            for attempt in range(max_retries):
                try:
                    if local_model_exists:
                        # Try to load from local directory
                        log_info(f"[OK] Loading GLiNER model from local directory: {self.model_dir_path}")
                        if self._load_local_model(self.model_dir_path):
                            break
                        else:
                            local_model_exists = False  # Failed to load, try downloading
                            log_warning("[WARNING] Failed to load GLiNER model from local directory, will try downloading")
                            # Reset local_files_only to allow downloading
                            self.local_files_only = False

                    if not local_model_exists:
                        if original_local_files_only:
                            log_warning(
                                "[WARNING] Local model directory not found but local_files_only=True, attempting download anyway")

                        # Download from HuggingFace
                        log_info(f"[OK] Downloading GLiNER model from HuggingFace: {self.model_name}")
                        self.model = GLiNER.from_pretrained(self.model_name)

                        # Save model to local directory if path is specified
                        if self.local_model_path:
                            self._save_model_to_directory(self.model_dir_path)

                    # IMPORTANT: Explicitly check if model was loaded properly
                    if self.model is not None:
                        # Explicitly set initialized flag to True
                        self._is_initialized = True
                        self._initialization_time = time.time() - start_time
                        self._last_used = time.time()

                        # Update global initialization time
                        GlinerEntityDetector._global_initialization_time = self._initialization_time

                        log_info(f"[OK] GLiNER model initialized successfully in {self._initialization_time:.2f}s")
                        log_info(f"[OK] Initialization flag explicitly set to: {self._is_initialized}")

                        # Test model with simple prediction
                        test_success = self._test_model()

                        # Only set initialized to True if test also succeeds
                        if not test_success:
                            log_warning("[WARNING] Model was loaded but failed test, setting initialized to False")
                            self._is_initialized = False

                        # Restore original local_files_only setting
                        self.local_files_only = original_local_files_only
                        return self._is_initialized

                except Exception as e:
                    log_error(f"[ERROR] Failed to initialize GLiNER model (attempt {attempt + 1}/{max_retries}): {e}")

                # Wait before retry
                if attempt < max_retries - 1:
                    time.sleep(2)  # Short wait between retries

            # Restore original local_files_only setting
            self.local_files_only = original_local_files_only
            return self._is_initialized

        finally:
            # Reset global initializing flag
            with self._model_lock:
                GlinerEntityDetector._global_initializing = False

    def _fix_config_file_discrepancy(self) -> None:
        """
        Fix configuration file discrepancy by creating a copy of gliner_config.json as config.json.

        This resolves the issue where the GLiNER library expects config.json but the
        model directory has gliner_config.json instead.
        """
        try:
            # Check if gliner_config.json exists but config.json doesn't
            gliner_config_path = os.path.join(self.model_dir_path, 'gliner_config.json')
            config_path = os.path.join(self.model_dir_path, 'config.json')

            if os.path.exists(gliner_config_path) and not os.path.exists(config_path):
                log_info(f"[GLINER] Creating config.json from gliner_config.json")
                shutil.copy2(gliner_config_path, config_path)
                log_info(f"[GLINER] Successfully created config.json")
        except Exception as e:
            log_warning(f"[GLINER] Failed to fix config file discrepancy: {e}")

    def _check_local_model_exists(self) -> bool:
        """
        Check if a valid local model directory exists.

        Returns:
            True if a valid local model directory exists, False otherwise
        """
        # Check if the directory exists
        if not os.path.exists(self.model_dir_path):
            log_warning(f"[GLINER] Model directory does not exist: {self.model_dir_path}")
            return False

        # Check if it's a directory
        if not os.path.isdir(self.model_dir_path):
            log_warning(f"[GLINER] Model path is not a directory: {self.model_dir_path}")
            return False

        # Check for required model files
        required_files = ['pytorch_model.bin']
        # Either config.json or gliner_config.json should exist
        config_files = ['config.json', 'gliner_config.json']

        # Check if at least one config file exists
        has_config = any(os.path.exists(os.path.join(self.model_dir_path, f)) for f in config_files)
        if not has_config:
            log_warning(f"[GLINER] No configuration file found in model directory")
            return False

        # Check for other required files
        missing_files = [f for f in required_files if not os.path.exists(os.path.join(self.model_dir_path, f))]

        if missing_files:
            log_warning(f"[GLINER] Missing required model files: {missing_files}")
            return False

        log_info(f"[GLINER] Found valid model directory at {self.model_dir_path}")
        return True

    def _test_model(self) -> bool:
        """
        Test the GLiNER model with a simple prediction to verify functionality.

        Returns:
            True if the test was successful, False otherwise
        """
        try:
            if not self.model:
                log_warning("[WARNING] Cannot test model - model not initialized")
                return False

            test_text = "John Smith works at Microsoft."
            test_entities = ["Person", "Organization"]

            # Test if the predict_entities method exists and can be called
            if not hasattr(self.model, "predict_entities"):
                log_warning("[WARNING] Model doesn't have predict_entities method")
                return False

            # Try to run a prediction
            results = self.model.predict_entities(test_text, test_entities, threshold=0.5)

            # Log test results
            log_info(f"[OK] GLiNER model test successful. Found {len(results)} entities.")
            return True
        except Exception as test_error:
            log_warning(f"[WARNING] GLiNER model test failed: {test_error}")
            return False

    def _save_model_to_directory(self, model_dir: str) -> bool:
        """
        Save model to directory using GLiNER's native method.

        Args:
            model_dir: Directory path where to save the model

        Returns:
            True if saving succeeded, False otherwise
        """
        try:
            if not self.model:
                log_error("[ERROR] Cannot save model - model not initialized")
                return False

            # Create directory
            os.makedirs(model_dir, exist_ok=True)
            log_info(f"[OK] Saving GLiNER model to directory: {model_dir}")

            # Use GLiNER's native save method if available
            if hasattr(self.model, "save_pretrained"):
                self.model.save_pretrained(model_dir)
                log_info("[OK] Used GLiNER's native save_pretrained method")
            else:
                # Fallback to manual save
                torch.save(self.model.state_dict(), os.path.join(model_dir, "pytorch_model.bin"))
                if hasattr(self.model, "config"):
                    self.model.config.save_pretrained(model_dir)

            log_info(f"[OK] GLiNER model saved successfully to {model_dir}")
            return True
        except Exception as e:
            log_error(f"[ERROR] Failed to save model to directory: {e}")
            return False

    def _load_local_model(self, model_dir: str) -> bool:
        """
        Load model from directory using GLiNER's native method with additional error handling.

        Args:
            model_dir: Path to the model directory

        Returns:
            True if loading succeeded, False otherwise
        """
        try:
            log_info(f"[OK] Loading GLiNER model from directory: {model_dir}")

            # Check if it's a directory
            if not os.path.isdir(model_dir):
                log_error(f"[ERROR] Expected a directory for model path: {model_dir}")
                return False

            # Fix config file discrepancy before loading
            self._fix_config_file_discrepancy()

            # Use GLiNER's from_pretrained method with error catching
            try:
                # Check if the config.json file exists after fixing
                config_path = os.path.join(model_dir, 'config.json')
                if not os.path.exists(config_path):
                    log_warning(f"[GLINER] config.json still doesn't exist after fix attempt")

                self.model = GLiNER.from_pretrained(
                    model_dir,
                    local_files_only=True
                )

                # Explicitly set the initialized flag to True after successful load
                self._is_initialized = True

                log_info("[OK] Loaded model using GLiNER's native from_pretrained method")
                log_info(f"[LOAD] Initialization flag explicitly set to: {self._is_initialized}")
                return True
            except Exception as load_error:
                log_error(f"[ERROR] Failed to load model with native method: {load_error}")

                # Try specifying the configuration file directly
                try:
                    # Check if gliner_config.json exists
                    gliner_config_path = os.path.join(model_dir, 'gliner_config.json')
                    config_path = os.path.join(model_dir, 'config.json')

                    config_file = config_path if os.path.exists(config_path) else gliner_config_path

                    if os.path.exists(config_file):
                        log_info(f"[GLINER] Trying to load with explicit config path: {config_file}")

                        # Import necessary classes if available
                        try:
                            from transformers import AutoConfig
                            config = AutoConfig.from_pretrained(config_file)
                            self.model = GLiNER.from_pretrained(
                                model_dir,
                                config=config,
                                local_files_only=True
                            )

                            # Explicitly set the initialized flag to True after successful load
                            self._is_initialized = True

                            log_info("[OK] Loaded model with explicit config")
                            log_info(f"[LOAD] Initialization flag explicitly set to: {self._is_initialized}")
                            return True
                        except ImportError:
                            log_warning("[WARNING] Could not import AutoConfig from transformers")
                except Exception as config_error:
                    log_error(f"[ERROR] Failed to load with explicit config: {config_error}")

                return False
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

            # Check initialization status explicitly
            log_info(f"[GLINER] Current initialization status: {self._is_initialized}, model is {'available' if self.model is not None else 'not available'}")

            # Make sure the model is initialized
            if not self._is_initialized or self.model is None:
                # Try to initialize again if needed
                log_info("[GLINER] Model not initialized, attempting initialization")
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

            # Check if model is available before processing
            if not self.model:
                log_warning(f"[WARNING] GLiNER model not available, skipping page {page_number}")
                return {"page": page_number, "sensitive": []}, []

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
        Process text with GLiNER to extract entities with robust error handling.

        Args:
            text: Text to process
            requested_entities: List of entity types to detect

        Returns:
            List of detected entities
        """
        try:
            if not text or len(text.strip()) < 3:
                return []

            # Ensure model is initialized and available
            if not self.model:
                log_error("[ERROR] GLiNER model not available in _process_text_with_gliner")
                return []

            # Check initialization status explicitly
            if not self._is_initialized:
                log_error("[ERROR] GLiNER model not properly initialized in _process_text_with_gliner")
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
            deduplicated_entities = deduplicate_entities(all_entities)
            filtered_entities = self._filter_norwegian_pronouns(deduplicated_entities)

            return filtered_entities

        except Exception as e:
            logger.error(f"[ERROR] Error in _process_text_with_gliner: {e}")
            return []

    def _process_paragraph(self, paragraph: str, full_text: str, requested_entities: List[str]) -> List[Dict[str, Any]]:
        """
        Process a single paragraph to extract entities with additional error handling.

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
                # Add robust error handling around the predict_entities call
                try:
                    paragraph_entities = self.model.predict_entities(
                        paragraph,
                        requested_entities,
                        threshold=0.5
                    )
                except Exception as predict_error:
                    log_warning(f"[WARNING] Error in GLiNER predict_entities: {predict_error}")
                    return []

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

            # Add robust error handling around the predict_entities call
            try:
                # Process with GLiNER
                group_entities = self.model.predict_entities(
                    text_group,
                    requested_entities,
                    threshold=0.5
                )
            except Exception as predict_error:
                log_warning(f"[WARNING] Error in GLiNER predict_entities for text group: {predict_error}")
                return []

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
            "model_dir_path": self.model_dir_path,
            "model_directory_exists": os.path.isdir(self.model_dir_path) if self.model_dir_path else False,
            "model_files": os.listdir(self.model_dir_path) if self.model_dir_path and os.path.isdir(self.model_dir_path) else [],
            "config_files": {
                "config.json": os.path.exists(os.path.join(self.model_dir_path, "config.json")) if self.model_dir_path else False,
                "gliner_config.json": os.path.exists(os.path.join(self.model_dir_path, "gliner_config.json")) if self.model_dir_path else False
            },
            "global_initializing": GlinerEntityDetector._global_initializing,
            "global_initialization_time": GlinerEntityDetector._global_initialization_time
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