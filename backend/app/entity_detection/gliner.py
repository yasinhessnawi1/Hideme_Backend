"""
GLiNER entity detection implementation with GDPR compliance and error handling.

This module provides a robust implementation of GLiNER entity detection with
improved initialization, GDPR compliance, and standardized error handling.
"""

import asyncio
import os
import shutil
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

import torch

from backend.app.utils.helpers.gliner_helper import GLiNERHelper

# Attempt to import GLiNER with error handling
try:
    from gliner import GLiNER

    GLINER_AVAILABLE = True
except ImportError:
    GLINER_AVAILABLE = False

from transformers import AutoConfig

from backend.app.entity_detection.base import BaseEntityDetector
from backend.app.utils.helpers.text_utils import TextUtils
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.configs.gliner_config import GLINER_MODEL_PATH, GLINER_MODEL_NAME, GLINER_AVAILABLE_ENTITIES
from backend.app.utils.validation.sanitize_utils import deduplicate_entities
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.validation.data_minimization import minimize_extracted_data
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.system_utils.synchronization_utils import TimeoutLock, LockPriority
from backend.app.utils.parallel.core import ParallelProcessingCore

# Constants to avoid duplicating these literal strings
GLINER_CONFIG_FILENAME = "gliner_config.json"
CONFIG_FILENAME = "config.json"


class GlinerEntityDetector(BaseEntityDetector):
    """
    Enhanced service for detecting sensitive information using GLiNER with GDPR compliance
    and standardized error handling. Uses a singleton pattern so that the GLiNER model
    is loaded only once per process.
    """

    _shared_instance = None
    _shared_instance_lock = TimeoutLock(name="gliner_shared_instance_lock", priority=LockPriority.HIGH, timeout=600.0)

    # Global caching for model
    _model_lock = TimeoutLock(name="gliner_model_lock", priority=LockPriority.HIGH, timeout=600.0)
    _global_initializing = False
    _global_initialization_time = None
    _model_cache = {}  # cache_key -> {"model": loaded_model, "init_time": initialization_time}

    def __new__(cls, *args, **kwargs):
        """
        Enforce singleton pattern. If an instance does not exist, acquire a lock
        and create one. Otherwise, return the existing instance.
        """
        if cls._shared_instance is None:
            acquired = cls._shared_instance_lock.acquire(timeout=600.0)
            if acquired:
                try:
                    if cls._shared_instance is None:
                        cls._shared_instance = super().__new__(cls)
                finally:
                    cls._shared_instance_lock.release()
        return cls._shared_instance

    def __init__(
            self,
            model_name: str = GLINER_MODEL_NAME,
            entities: Optional[List[str]] = None,
            local_model_path: Optional[str] = None,
            local_files_only: bool = False
    ):
        """
        Initialize the GLiNER entity detector with improved error handling and caching.
        The constructor only runs once due to the singleton pattern.

        Args:
            model_name: Name or path of the GLiNER model to use.
            entities: Entity types to detect (if None, uses GLINER_ENTITIES).
            local_model_path: Path to local model directory.
            local_files_only: If True, only use local model files.
        """
        # Prevent re-initialization if already initialized
        if getattr(self, "_already_initialized", False):
            return

        super().__init__()
        self.model_name = model_name
        self.model = None
        self.default_entities = entities or GLINER_AVAILABLE_ENTITIES
        self.local_model_path = local_model_path or os.path.dirname(GLINER_MODEL_PATH)
        self.local_files_only = local_files_only
        self.model_dir_path = GLINER_MODEL_PATH
        self._is_initialized = False

        # Lock for this instance (not the global model lock)
        self._instance_lock: Optional[TimeoutLock] = None

        # Keep track of calls and processing time
        self._total_calls = 0
        self.total_processing_time = 0.0

        # If GLiNER is not available, log an error
        if not GLINER_AVAILABLE:
            log_error("[ERROR] GLiNER package not installed. Please install with 'pip install gliner'")

        self.norwegian_pronouns = self._init_norwegian_pronouns()

        # Defer creation of the lock that was previously in the constructor
        self._model_analyzer_lock: Optional[TimeoutLock] = None

        # Attempt model initialization
        self._initialize_model()

        # Mark as initialized
        self._already_initialized = True

    def _get_model_analyzer_lock(self) -> TimeoutLock:
        """
        Lazily create and return the TimeoutLock for the GLiNER analyzer.
        """
        if self._model_analyzer_lock is None:
            self._model_analyzer_lock = TimeoutLock(
                name="gliner_analyzer_lock",
                priority=LockPriority.HIGH,
                timeout=600.0
            )
        return self._model_analyzer_lock

    # -------------------------------------------------------------------------
    # Model Initialization
    # -------------------------------------------------------------------------
    def _initialize_model(self) -> None:
        """
        Refactored entry point for model initialization to reduce complexity.
        """
        if not GLINER_AVAILABLE:
            log_error("[ERROR] GLiNER package not installed.")
            return

        if self._is_initialized and self.model is not None:
            return  # Already initialized

        cache_key = (self.model_name, self.local_files_only, tuple(sorted(self.default_entities)))
        if self._try_load_model_from_cache(cache_key):
            return

        start_time = time.time()
        acquired = GlinerEntityDetector._model_lock.acquire(timeout=600.0)
        if not acquired:
            log_error("[GLINER] Timeout acquiring model lock for initialization")
            return

        try:
            # Double-check after acquiring the lock
            if self._try_load_model_from_cache(cache_key):
                return

            if self._handle_concurrent_initialization(cache_key):
                return

            # Mark global as initializing
            GlinerEntityDetector._global_initializing = True

            try:
                self._perform_model_initialization(cache_key, start_time)
            finally:
                GlinerEntityDetector._global_initializing = False

        finally:
            GlinerEntityDetector._model_lock.release()

    def _try_load_model_from_cache(self, cache_key) -> bool:
        """
        Check if the model with this cache_key is already in the global cache.
        If so, load it and update initialization fields.

        Args:
            cache_key: Unique key for this model configuration.

        Returns:
            True if loaded from cache, otherwise False.
        """
        short_acquired = GlinerEntityDetector._model_lock.acquire(timeout=5.0)
        if not short_acquired:
            log_warning("[GLINER] Timeout acquiring model lock for cache check")
            return False
        try:
            if cache_key in GlinerEntityDetector._model_cache:
                return self._load_model_from_cache_and_log(
                    cache_key,
                    "in"
                )
            return False
        finally:
            GlinerEntityDetector._model_lock.release()

    def _handle_concurrent_initialization(self, cache_key) -> bool:
        """
        If another thread is already initializing, wait up to 60s. If the model
        appears in the cache afterward, load from there.

        Args:
            cache_key: Unique key for this model configuration

        Returns:
            True if the model was loaded from cache after waiting, otherwise False.
        """
        if GlinerEntityDetector._global_initializing:
            log_info("[GLINER] Another thread is already initializing the model")
            wait_until = time.time() + 60.0
            while GlinerEntityDetector._global_initializing and time.time() < wait_until:
                time.sleep(1)
            if cache_key in GlinerEntityDetector._model_cache:
                return self._load_model_from_cache_and_log(
                    cache_key,
                    "after waiting "
                )
        return False

    def _perform_model_initialization(self, cache_key, start_time: float, max_retries: int = 2) -> None:
        """
        Perform the actual model loading logic, either from local or by downloading.

        Args:
            cache_key: Unique key for this model configuration
            start_time: Time when initialization started
            max_retries: Number of times to retry initialization
        """
        local_exists = self._check_local_model_exists()
        log_info(f"[GLINER] Local model exists: {local_exists}")
        for attempt_index in range(max_retries):
            log_info(f"[GLINER] Attempt {attempt_index + 1}/{max_retries} for model initialization.")
            if self._attempt_model_init(local_exists, attempt_index):
                init_duration = time.time() - start_time
                self._initialization_time = init_duration
                self._is_initialized = True
                self._last_used = time.time()
                log_info(f"[OK] Model initialized in {init_duration:.2f}s")
                GlinerEntityDetector._model_cache[cache_key] = {
                    "model": self.model,
                    "init_time": init_duration
                }
                GlinerEntityDetector._global_initialization_time = init_duration
                return
            else:
                local_exists = False
                time.sleep(2)

        # If we exit the loop, initialization failed
        record_keeper.record_processing(
            operation_type="gliner_model_initialization",
            document_type="model",
            entity_types_processed=self.default_entities,
            processing_time=time.time() - start_time,
            entity_count=0,
            success=False
        )

    def _attempt_model_init(self, local_exists: bool, attempt_index: int) -> bool:
        """
        Attempt to initialize the model once, either from local or by downloading.

        Args:
            local_exists: Whether a local model directory is present.
            attempt_index: Current attempt number.

        Returns:
            True if the model is successfully loaded, False otherwise.
        """
        try:
            if local_exists:
                log_info(f"[OK] Attempting to load model from local directory: {self.model_dir_path}")
                if self._load_local_model(self.model_dir_path):
                    return True
                else:
                    local_exists = False
                    log_warning(
                        f"[WARNING] Attempt {attempt_index + 1}: failed to load local model, will attempt download")
                    self.local_files_only = False

            if not local_exists:
                log_info(f"[OK] Downloading GLiNER model: {self.model_name}")
                from gliner import GLiNER  # re-import to avoid top-level error
                self.model = GLiNER.from_pretrained(self.model_name)
                if self.local_model_path:
                    self._save_model_to_directory(self.model_dir_path)
            return self.model is not None
        except Exception as init_exc:
            SecurityAwareErrorHandler.log_processing_error(
                init_exc,
                f"gliner_initialization_attempt_{attempt_index}",
                self.model_name
            )
            return False

    def _load_model_from_cache_and_log(self, cache_key: tuple, reason: str) -> bool:
        """
        Helper to load a cached model and log the result to reduce duplicated code.

        Args:
            cache_key: Unique key for the model configuration
            reason: A small phrase to describe how the model was loaded (e.g., "after waiting")

        Returns:
            True to indicate the model was successfully loaded from cache
        """
        cached = GlinerEntityDetector._model_cache[cache_key]
        self.model = cached["model"]
        self._initialization_time = cached["init_time"]
        self._is_initialized = True
        self._last_used = time.time()
        log_info(f"[GLINER] Loaded model from cache {reason}in {self._initialization_time:.2f}s")
        return True

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------
    @staticmethod
    def _init_norwegian_pronouns() -> set:
        """
        Initialize the set of Norwegian pronouns for filtering.

        Returns:
            Set of Norwegian pronouns in lowercase
        """
        pronouns = {
            "jeg", "du", "han", "hun", "vi", "dere", "de",
            "meg", "deg", "ham", "henne", "den", "det", "oss", "dem",
            "min", "mi", "mitt", "mine", "din", "di", "ditt", "dine",
            "hans", "hennes", "dens", "dets", "vår", "vårt", "våre",
            "deres", "sin", "si", "sitt", "sine",
            "seg", "selv",
            "denne", "dette", "disse",
            "hvem", "hva", "hvilken", "hvilket", "hvilke",
            "noen", "noe", "ingen", "ingenting", "alle", "enhver", "ethvert", "hver", "hvert",
            "som"
        }
        return {w.lower() for w in pronouns}

    def _fix_config_file_discrepancy(self) -> None:
        """
        Fix configuration file discrepancy by creating a copy of gliner_config.json as config.json.
        """
        try:
            gliner_config_path = os.path.join(self.model_dir_path, GLINER_CONFIG_FILENAME)
            config_path = os.path.join(self.model_dir_path, CONFIG_FILENAME)
            if os.path.exists(gliner_config_path) and not os.path.exists(config_path):
                log_info("[GLINER] Creating config.json from gliner_config.json")
                shutil.copy2(gliner_config_path, config_path)
                log_info("[GLINER] Successfully created config.json")
        except Exception as exc:
            SecurityAwareErrorHandler.log_processing_error(exc, "gliner_config_fix", self.model_dir_path)

    def _check_local_model_exists(self) -> bool:
        """
        Check if a valid local model directory exists.

        Returns:
            True if a valid local model directory exists, False otherwise
        """
        if not os.path.exists(self.model_dir_path):
            log_warning(f"[GLINER] Model directory does not exist: {self.model_dir_path}")
            return False
        if not os.path.isdir(self.model_dir_path):
            log_warning(f"[GLINER] Model path is not a directory: {self.model_dir_path}")
            return False

        required_files = ['pytorch_model.bin']
        config_files = [CONFIG_FILENAME, GLINER_CONFIG_FILENAME]
        has_config = any(os.path.exists(os.path.join(self.model_dir_path, f)) for f in config_files)
        if not has_config:
            log_warning("[GLINER] No configuration file found in model directory")
            return False

        missing_files = [
            f for f in required_files
            if not os.path.exists(os.path.join(self.model_dir_path, f))
        ]
        if missing_files:
            log_warning(f"[GLINER] Missing required model files: {missing_files}")
            return False

        log_info(f"[GLINER] Found valid model directory at {self.model_dir_path}")
        return True

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
            os.makedirs(model_dir, exist_ok=True)
            log_info(f"[OK] Saving GLiNER model to directory: {model_dir}")
            if hasattr(self.model, "save_pretrained"):
                self.model.save_pretrained(model_dir)
                log_info("[OK] Used GLiNER's native save_pretrained method")
            else:
                torch.save(self.model.state_dict(), os.path.join(model_dir, "pytorch_model.bin"))
                if hasattr(self.model, "config"):
                    self.model.config.save_pretrained(model_dir)
            log_info(f"[OK] GLiNER model saved successfully to {model_dir}")
            return True
        except Exception as exc:
            SecurityAwareErrorHandler.log_processing_error(exc, "gliner_model_save", model_dir)
            return False

    def _load_local_model(self, model_dir: str) -> bool:
        """
        Load model from directory using GLiNER's native method with error handling.

        Args:
            model_dir: Path to the model directory

        Returns:
            True if loading succeeded, False otherwise
        """
        try:
            log_info(f"[OK] Loading GLiNER model from directory: {model_dir}")
            if not os.path.isdir(model_dir):
                log_error(f"[ERROR] Expected a directory for model path: {model_dir}")
                return False
            self._fix_config_file_discrepancy()

            from gliner import GLiNER  # re-import to avoid top-level error
            try:
                config_path = os.path.join(model_dir, CONFIG_FILENAME)
                if not os.path.exists(config_path):
                    log_warning("[GLINER] config.json still doesn't exist after fix attempt")
                self.model = GLiNER.from_pretrained(model_dir, local_files_only=True)
                self._is_initialized = True
                self._initialization_time = time.time()
                log_info("[OK] Loaded model using GLiNER's native from_pretrained method")
                return True
            except Exception as load_error:
                SecurityAwareErrorHandler.log_processing_error(load_error, "gliner_model_load_native", model_dir)
                return self._attempt_explicit_config_load(model_dir)
        except Exception as exc:
            SecurityAwareErrorHandler.log_processing_error(exc, "gliner_model_load", model_dir)
            return False

    def _attempt_explicit_config_load(self, model_dir: str) -> bool:
        """
        Attempt to load model with an explicit config file if the native method fails.

        Args:
            model_dir: Path to the model directory

        Returns:
            True if loading succeeded, False otherwise
        """
        try:
            from gliner import GLiNER
            gliner_config_path = os.path.join(model_dir, GLINER_CONFIG_FILENAME)
            config_path = os.path.join(model_dir, CONFIG_FILENAME)
            chosen_config = config_path if os.path.exists(config_path) else gliner_config_path

            if os.path.exists(chosen_config):
                log_info(f"[GLINER] Trying to load with explicit config path: {chosen_config}")
                try:
                    config = AutoConfig.from_pretrained(chosen_config)
                    self.model = GLiNER.from_pretrained(model_dir, config=config, local_files_only=True)
                    self._is_initialized = True
                    log_info("[OK] Loaded model with explicit config")
                    return True
                except ImportError:
                    log_warning("[WARNING] Could not import AutoConfig from transformers")
            return False
        except Exception as config_error:
            SecurityAwareErrorHandler.log_processing_error(config_error, "gliner_model_load_explicit_config", model_dir)
            return False

    # -------------------------------------------------------------------------
    # detect_sensitive_data_async
    # -------------------------------------------------------------------------

    async def detect_sensitive_data_async(
            self,
            extracted_data: Dict[str, Any],
            requested_entities: Optional[List[str]] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Asynchronously detect sensitive entities in extracted data with GDPR compliance.

        Args:
            extracted_data: Dictionary containing text and bounding box information
            requested_entities: List of entity types to detect

        Returns:
            Tuple of (results_json, redaction_mapping)
        """
        start_time = time.time()
        minimized_data = minimize_extracted_data(extracted_data)
        self._total_calls += 1
        self._last_used = time.time()

        try:
            pages = minimized_data.get("pages", [])
            if not pages:
                return [], {"pages": []}

            page_texts_and_mappings, redaction_mapping = self._prepare_page_data(pages)
            if not page_texts_and_mappings:
                return [], {"pages": []}

            local_entities = requested_entities or self.default_entities

            # Process pages in parallel
            page_results = await self._process_pages_gliner_async(pages, page_texts_and_mappings, local_entities)

            # Combine results
            combined_results = []
            for local_page_number, (local_page_redaction_info, local_processed_entities) in page_results:
                if local_page_redaction_info:
                    redaction_mapping["pages"].append(local_page_redaction_info)
                if local_processed_entities:
                    combined_results.extend(local_processed_entities)

            # Deduplicate final results
            combined_results = self.sanitize_entities(combined_results)
            redaction_mapping["pages"].sort(key=lambda x: x.get("page", 0))

            # Record processing for GDPR compliance
            total_time = time.time() - start_time
            record_keeper.record_processing(
                operation_type="gliner_detection",
                document_type="document",
                entity_types_processed=local_entities,
                processing_time=total_time,
                entity_count=len(combined_results),
                success=True
            )

            log_info(f"[PERF] GLiNER detection completed in {total_time:.2f}s")
            log_info(f"[PERF] Found {len(combined_results)} entities across {len(pages)} pages")
            log_sensitive_operation("GLiNER Detection", len(combined_results), total_time, pages=len(pages))

            log_info(f"[DEBUG] Combined entities before filtering [GLiNER]: {len(combined_results)}")
            # 3. Filter the final entity list.
            filter_final_entities = BaseEntityDetector.filter_entities_by_score(combined_results, threshold=0.5)
            log_info(f"[DEBUG] Final entities after filtering (score >= 0.85) [GLiNER]: {len(filter_final_entities)}")

            # 4. Also filter the redaction mapping.
            filter_final_redaction_mapping = BaseEntityDetector.filter_redaction_mapping_by_score(redaction_mapping, threshold=0.5)

            return filter_final_entities, filter_final_redaction_mapping

        except Exception as exc:
            error_time = time.time() - start_time
            record_keeper.record_processing(
                operation_type="gliner_detection",
                document_type="document",
                entity_types_processed=requested_entities or [],
                processing_time=error_time,
                entity_count=0,
                success=False
            )
            SecurityAwareErrorHandler.log_processing_error(exc, "gliner_detection", "")
            return [], {"pages": []}

    async def _process_pages_gliner_async(
            self,
            pages: List[Dict[str, Any]],
            page_texts_and_mappings: Dict[int, Tuple[str, List]],
            requested_entities: List[str]
    ) -> List[Tuple[int, Tuple[Dict[str, Any], List[Dict[str, Any]]]]]:
        """
        Process pages in parallel using the GLiNER model.

        Args:
            pages: List of page dictionaries
            page_texts_and_mappings: Mapping of page_number -> (full_text, mapping)
            requested_entities: List of entity types to detect

        Returns:
            A list of (page_number, (page_redaction_info, processed_entities))
        """

        async def process_page_async(local_page_data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
            try:
                return await asyncio.wait_for(
                    self._process_single_page_async(local_page_data, page_texts_and_mappings, requested_entities),
                    timeout=600.0
                )
            except asyncio.TimeoutError:
                local_page_number = local_page_data.get("page", 0)
                log_warning(f"[WARNING] Timeout processing page {local_page_number} with GLiNER")
                return {"page": local_page_number, "sensitive": []}, []
            except Exception as page_exc:
                SecurityAwareErrorHandler.log_processing_error(
                    page_exc, "gliner_page_processing", f"page_{local_page_data.get('page', 'unknown')}"
                )
                return {"page": local_page_data.get('page'), "sensitive": []}, []

        return await ParallelProcessingCore.process_pages_in_parallel(pages, process_page_async)

    async def _process_single_page_async(
            self,
            local_page_data: Dict[str, Any],
            page_texts_and_mappings: Dict[int, Tuple[str, List]],
            requested_entities: List[str]
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Process a single page asynchronously to detect entities with enhanced
        error handling and GDPR compliance.

        This version uses ParallelProcessingCore.process_entities_in_parallel
        to process the detected entities concurrently in batches.

        Args:
            local_page_data: Dictionary with page information.
            page_texts_and_mappings: Dictionary mapping page numbers to (text, mapping) tuples.
            requested_entities: List of entity types to detect.

        Returns:
            Tuple of (page_redaction_info, processed_entities) where:
              - page_redaction_info: A dict containing redaction details for the page.
              - processed_entities: A list of dictionaries for each detected entity,
                including keys: "entity_type", "start", "end", "score", "original_text".
        """
        page_start_time = time.time()
        local_page_number = local_page_data.get("page")
        local_words = local_page_data.get("words", [])
        if not local_words:
            return {"page": local_page_number, "sensitive": []}, []

        full_text, mapping = page_texts_and_mappings.get(local_page_number, ("", []))
        if not full_text or not mapping:
            return {"page": local_page_number, "sensitive": []}, []

        log_info(f"[OK] Processing text with GLiNER on page {local_page_number}")
        if not self.model:
            log_warning(f"[WARNING] GLiNER model not available, skipping page {local_page_number}")
            return {"page": local_page_number, "sensitive": []}, []

        # Process text with GLiNER to get initial detected entities.
        page_entities = await asyncio.to_thread(self._process_text_with_gliner, full_text, requested_entities)
        if not page_entities:
            log_info(f"[OK] No entities detected by GLiNER on page {local_page_number}")
            return {"page": local_page_number, "sensitive": []}, []

        entity_count = len(page_entities)
        log_info(f"[OK] Found {entity_count} entities on page {local_page_number}")

        # Process entities in parallel using the ParallelProcessingCore helper.
        # This method batches the processing of entities for the page.
        processed_entities, local_page_redaction_info = await ParallelProcessingCore.process_entities_in_parallel(
            self, full_text, mapping, page_entities, local_page_number
        )

        page_time = time.time() - page_start_time
        record_keeper.record_processing(
            operation_type="gliner_page_processing",
            document_type=f"page_{local_page_number}",
            entity_types_processed=requested_entities,
            processing_time=page_time,
            entity_count=len(processed_entities),
            success=True
        )
        log_sensitive_operation("GLiNER Page Detection", len(processed_entities), page_time,
                                page_number=local_page_number)
        return local_page_redaction_info, processed_entities

    @staticmethod
    def _prepare_page_data(
            pages: List[Dict[str, Any]]
    ) -> Tuple[Dict[int, Tuple[str, List]], Dict[str, Any]]:
        """
        Prepare page data for processing by extracting text and creating mappings.

        Args:
            pages: List of page dictionaries with word data

        Returns:
            Tuple of (page_texts_and_mappings, redaction_mapping)
        """
        page_texts_and_mappings = {}
        redaction_mapping = {"pages": []}

        for page in pages:
            words = page.get("words", [])
            local_page_number = page.get("page")
            if not words:
                redaction_mapping["pages"].append({"page": local_page_number, "sensitive": []})
                continue

            has_content = any(w.get("text", "").strip() for w in words)
            if not has_content:
                log_info(f"[OK] Skipping empty page {local_page_number}")
                redaction_mapping["pages"].append({"page": local_page_number, "sensitive": []})
                continue

            full_text, mapping = TextUtils.reconstruct_text_and_mapping(words)
            page_texts_and_mappings[local_page_number] = (full_text, mapping)

        return page_texts_and_mappings, redaction_mapping

    def _process_text_with_gliner(
            self,
            text: str,
            requested_entities: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Process text with GLiNER to extract entities with robust error handling.

        Args:
            text: Text to process
            requested_entities: List of entity types to detect

        Returns:
            List of detected entities
        """
        start_time = time.time()
        if not text or len(text.strip()) < 3:
            return []
        if not self.model:
            SecurityAwareErrorHandler.handle_safe_error(
                ValueError("GLiNER model not available"),
                "gliner_model_unavailable",
                "",
                default_return=[]
            )
            return []

        if not self._is_initialized:
            SecurityAwareErrorHandler.handle_safe_error(
                ValueError("GLiNER model not properly initialized"),
                "gliner_model_not_initialized",
                "",
                default_return=[]
            )
            return []

        paragraphs = [p for p in text.split('\n') if p.strip()]
        all_entities: List[Dict[str, Any]] = []
        batch_size = 5

        for i in range(0, len(paragraphs), batch_size):
            batch_paragraphs = paragraphs[i:i + batch_size]
            batch_results = self._process_paragraph_batch(batch_paragraphs, text, requested_entities)
            all_entities.extend(batch_results)

        deduplicated_entities = deduplicate_entities(all_entities)
        filtered_entities = self._filter_norwegian_pronouns(deduplicated_entities)
        processing_time = time.time() - start_time
        self.total_processing_time += processing_time
        return filtered_entities

    def _process_paragraph_batch(
            self,
            paragraphs: List[str],
            full_text: str,
            requested_entities: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Process a batch of paragraphs by splitting each paragraph into smaller text groups,
        each containing at most max_chars (800) characters, and then extracting entities from each group
        using the full list of requested entity types.

        For each paragraph:
          1. Determine the paragraph's base offset in the full text.
          2. Split the paragraph into groups (chunks) using _split_into_sentence_groups.
          3. For each group, compute the absolute offset and process the group with all requested entity types.
          4. Aggregate and return all detected entities.

        Args:
            paragraphs: A list of paragraph strings extracted from the page.
            full_text: The complete text content of the page.
            requested_entities: The full list of entity types to detect.

        Returns:
            A list of dictionaries representing the detected entities.
            Each dictionary contains keys: "entity_type", "start", "end", "score", "original_text".
        """
        all_entities = []
        for paragraph in paragraphs:
            if not paragraph.strip():
                continue
            base_offset = full_text.find(paragraph)
            if base_offset == -1:
                continue

            # Split the paragraph into groups with at most 800 characters.
            sentence_groups = GLiNERHelper.split_into_sentence_groups(paragraph, 800)
            for group_text in sentence_groups:
                group_offset = paragraph.find(group_text)
                if group_offset == -1:
                    continue
                absolute_offset = base_offset + group_offset
                # Process the group_text with the full list of requested entity types.
                group_entities = self._extract_entities_for_group(group_text, requested_entities, absolute_offset)
                all_entities.extend(group_entities)
        return all_entities

    def _extract_entities_for_group(
            self,
            group_text: str,
            requested_entities: List[str],
            absolute_offset: int
    ) -> List[Dict[str, Any]]:
        """
        Extract entities from a given text group using the full list of requested entity types.

        This method:
          1. Acquires a lock to ensure thread-safe access to the model.
          2. Logs debug information about the text group.
          3. Calls the model's predict_entities method once with all requested entity types.
          4. Adjusts the start and end offsets of each detected entity by adding the absolute offset.
          5. Returns a list of detected entity dictionaries.

        Args:
            group_text: The text group (chunk) to process.
            requested_entities: The full list of entity types to detect.
            absolute_offset: The starting offset of group_text within the full page text.

        Returns:
            A list of dictionaries representing detected entities.
            Each dictionary includes: "entity_type", "start", "end", "score", "original_text".
        """
        local_entities = []
        lock = self._get_model_analyzer_lock()
        if not lock.acquire(timeout=600.0):
            log_warning("[GLINER] Timeout acquiring model analyzer lock")
            return local_entities

        try:
            log_info(
                f"[DEBUG] Processing group_text (length {len(group_text)}): '{group_text[:100]}...' for entity_types: {requested_entities}")
            # Process the group_text with all requested entity types in one call.
            group_entities = self.model.predict_entities(group_text, requested_entities, threshold=0.5)
            for entity in group_entities:
                entity_dict = {
                    "entity_type": entity.get("label", "UNKNOWN").upper(),
                    "start": absolute_offset + entity.get("start", 0),
                    "end": absolute_offset + entity.get("end", 0),
                    "score": entity.get("score", 0.5),
                    "original_text": entity.get("text", "")
                }
                local_entities.append(entity_dict)
        except Exception as predict_error:
            log_error(
                f"[DEBUG] Error in predict_entities for group_text (length {len(group_text)}): '{group_text[:100]}...'. Error: {predict_error}")
            SecurityAwareErrorHandler.log_processing_error(
                predict_error, "gliner_predict_entities", f"group_{hash(group_text) % 10000}"
            )
        finally:
            lock.release()

        return local_entities

    def _filter_norwegian_pronouns(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter out Norwegian pronouns that are incorrectly identified as person names.

        Args:
            entities: List of detected entities

        Returns:
            Filtered list of entities without Norwegian pronouns
        """
        filtered_entities = []
        for ent in entities:
            etype = ent["entity_type"]
            if etype in {"PERSON", "PER"}:
                text_val = ent.get("original_text", "").strip()
                text_words = text_val.split()
                if len(text_words) == 1 and text_words[0].lower() in self.norwegian_pronouns:
                    log_info("[FILTER] Removed Norwegian pronoun incorrectly detected as PERSON")
                    continue
                if len(text_words) > 1 and all(w.lower() in self.norwegian_pronouns for w in text_words):
                    log_info("[FILTER] Removed compound Norwegian pronoun incorrectly detected as PERSON")
                    continue
            filtered_entities.append(ent)
        return filtered_entities

    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the GLiNER detector.

        Returns:
            Dictionary with status information
        """
        return {
            "initialized": self._is_initialized,
            "initialization_time": self._initialization_time,
            "initialization_time_readable": datetime.fromtimestamp(
                self._initialization_time, timezone.utc
            ).strftime('%Y-%m-%d %H:%M:%S'),
            "last_used": self._last_used,
            "last_used_readable": datetime.fromtimestamp(
                self._last_used, timezone.utc
            ).strftime('%Y-%m-%d %H:%M:%S') if self._last_used else "Never Used",
            "idle_time": time.time() - self._last_used if self._last_used else None,
            "idle_time_readable": f"{(time.time() - self._last_used):.2f} seconds" if self._last_used else "N/A",
            "total_calls": self._total_calls,
            "total_entities_detected": getattr(self, '_total_entities_detected', 0),
            "total_processing_time": self.total_processing_time,
            "average_processing_time": (
                self.total_processing_time / self._total_calls if self._total_calls > 0 else None
            ),
            "model_available": self.model is not None,
            "model_name": self.model_name,
            "gliner_package_available": GLINER_AVAILABLE,
            "local_model_path": self.local_model_path,
            "local_files_only": self.local_files_only,
            "model_dir_path": self.model_dir_path,
            "model_directory_exists": os.path.isdir(self.model_dir_path) if self.model_dir_path else False,
            "model_files": os.listdir(self.model_dir_path) if self.model_dir_path and os.path.isdir(
                self.model_dir_path) else [],
            "config_files": {
                CONFIG_FILENAME: os.path.exists(
                    os.path.join(self.model_dir_path, CONFIG_FILENAME)) if self.model_dir_path else False,
                GLINER_CONFIG_FILENAME: os.path.exists(
                    os.path.join(self.model_dir_path, GLINER_CONFIG_FILENAME)) if self.model_dir_path else False
            },
            "global_initializing": GlinerEntityDetector._global_initializing,
            "global_initialization_time": GlinerEntityDetector._global_initialization_time
        }