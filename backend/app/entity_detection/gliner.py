"""
GLiNER entity detection implementation with GDPR compliance and error handling.

This module provides a robust implementation of GLiNER entity detection with improved
initialization, GDPR compliance, and standardized error handling. It uses a singleton
pattern to ensure that the GLiNER model is loaded only once per process.
"""

import asyncio
import json
import os
import shutil
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

import torch

from backend.app.utils.constant.constant import GLINER_CONFIG_FILENAME, CONFIG_FILENAME
from backend.app.utils.helpers.gliner_helper import GLiNERHelper
from backend.app.utils.helpers.json_helper import validate_gliner_requested_entities

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


class GlinerEntityDetector(BaseEntityDetector):
    """
    Enhanced service for detecting sensitive information using GLiNER with GDPR compliance
    and standardized error handling. Uses a singleton pattern so that the GLiNER model is
    loaded only once per process.
    """

    _shared_instance = None
    _shared_instance_lock = TimeoutLock(name="gliner_shared_instance_lock", priority=LockPriority.HIGH, timeout=600.0)
    # Global caching for model: cache_key -> {"model": loaded_model, "init_time": initialization_time}
    _model_lock = TimeoutLock(name="gliner_model_lock", priority=LockPriority.HIGH, timeout=600.0)
    _global_initializing = False
    _global_initialization_time = None
    _model_cache = {}

    def __new__(cls, *args, **kwargs):
        """
        Enforce singleton pattern. If an instance does not exist, acquire a lock
        and create one. Otherwise, return the existing instance.
        """
        # If no shared instance exists...
        if cls._shared_instance is None:
            # Acquire the shared instance lock with a timeout.
            acquired = cls._shared_instance_lock.acquire(timeout=600.0)
            # If acquired...
            if acquired:
                try:
                    # Double-check if the shared instance is still None.
                    if cls._shared_instance is None:
                        # Create a new instance using the parent __new__.
                        cls._shared_instance = super().__new__(cls)
                finally:
                    # Always release the shared instance lock.
                    cls._shared_instance_lock.release()
        # Return the shared instance.
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
            entities: Entity types to detect (if None, uses GLINER_AVAILABLE_ENTITIES).
            local_model_path: Path to local model directory.
            local_files_only: If True, only use local model files.
        """
        # If the instance has already been initialized, then return without reinitializing.
        if getattr(self, "_already_initialized", False):
            return
        # Call the parent class initializer.
        super().__init__()
        # Store the provided model name.
        self.model_name = model_name
        # Initialize the model attribute to None.
        self.model = None
        # Store entity types or use default available entities.
        self.default_entities = entities or GLINER_AVAILABLE_ENTITIES
        # Set local model path from the provided value or fallback to the directory of GLINER_MODEL_PATH.
        self.local_model_path = local_model_path or os.path.dirname(GLINER_MODEL_PATH)
        # Store the flag indicating whether to use only local files.
        self.local_files_only = local_files_only
        # Set the model directory path.
        self.model_dir_path = GLINER_MODEL_PATH
        # Set the initialization flag to False initially.
        self._is_initialized = False
        # Initialize the instance-specific lock to None (lazy creation).
        self._instance_lock: Optional[TimeoutLock] = None
        # Initialize usage metrics for calls and total processing time.
        self._total_calls = 0
        self.total_processing_time = 0.0
        # If the GLiNER package is not available, log an error.
        if not GLINER_AVAILABLE:
            log_error("[ERROR] GLiNER package not installed. Please install with 'pip install gliner'")
        # Initialize language-specific resources (e.g., Norwegian pronouns).
        self.norwegian_pronouns = self._init_norwegian_pronouns()
        # Defer creation of the analyzer lock until needed; initialize to None.
        self._model_analyzer_lock: Optional[TimeoutLock] = None
        # Attempt to initialize the model with robust error handling.
        self._initialize_model()
        # Mark the instance as already initialized.
        self._already_initialized = True

    def _get_model_analyzer_lock(self) -> TimeoutLock:
        """
        Lazily create and return the TimeoutLock for the GLiNER analyzer.
        This lock is used to synchronize access during model inference.
        """
        # If the model analyzer lock has not been created yet...
        if self._model_analyzer_lock is None:
            try:
                # Create a new TimeoutLock with high priority and a long timeout.
                self._model_analyzer_lock = TimeoutLock(
                    name="gliner_analyzer_lock",
                    priority=LockPriority.HIGH,
                    timeout=600.0
                )
            except Exception as exc:
                # Log any error during lock creation using the error handler.
                SecurityAwareErrorHandler.log_processing_error(exc, "model_analyzer_lock_init", self.model_dir_path)
        # Return the analyzer lock.
        return self._model_analyzer_lock

    def _initialize_model(self) -> None:
        """
        Entry point for model initialization. Checks if GLiNER is available,
        loads the model from cache if possible, and performs model loading otherwise.
        """
        # If GLiNER package is not available, log error and return immediately.
        if not GLINER_AVAILABLE:
            log_error("[ERROR] GLiNER package not installed.")
            return
        # If already initialized and model is loaded, then do nothing.
        if self._is_initialized and self.model is not None:
            return
        # Create a unique cache key based on model configuration.
        cache_key = (self.model_name, self.local_files_only, tuple(sorted(self.default_entities)))
        # Try to load the model from the global cache.
        if self._try_load_model_from_cache(cache_key):
            return
        # Record the start time for initialization.
        start_time = time.time()
        # Acquire the global model lock with a timeout.
        acquired = GlinerEntityDetector._model_lock.acquire(timeout=600.0)
        # If the lock is not acquired, log an error and return.
        if not acquired:
            log_error("[GLINER] Timeout acquiring model lock for initialization")
            return
        try:
            # Double-check the cache after acquiring the lock.
            if self._try_load_model_from_cache(cache_key):
                return
            # If another thread is already initializing, wait.
            if self._handle_concurrent_initialization(cache_key):
                return
            # Mark that global initialization is in progress.
            GlinerEntityDetector._global_initializing = True
            try:
                # Perform the actual model initialization with retries.
                self._perform_model_initialization(cache_key, start_time)
            finally:
                # Clear the global initializing flag.
                GlinerEntityDetector._global_initializing = False
        finally:
            # Release the global model lock.
            GlinerEntityDetector._model_lock.release()

    def _try_load_model_from_cache(self, cache_key) -> bool:
        """
        Check if the model is already cached globally and load it if so.

        Args:
            cache_key: Unique key for this model configuration.

        Returns:
            True if the model was loaded from cache, False otherwise.
        """
        # Acquire the model lock for cache check with a short timeout.
        short_acquired = GlinerEntityDetector._model_lock.acquire(timeout=5.0)
        if not short_acquired:
            log_warning("[GLINER] Timeout acquiring model lock for cache check")
            return False
        try:
            # If the cache contains the key...
            if cache_key in GlinerEntityDetector._model_cache:
                # Load the model from cache and log the event.
                return self._load_model_from_cache_and_log(cache_key, "in")
            # Otherwise, return False.
            return False
        finally:
            # Release the model lock.
            GlinerEntityDetector._model_lock.release()

    def _handle_concurrent_initialization(self, cache_key) -> bool:
        """
        Wait if another thread is initializing the model. If the model is available in the cache
        after waiting, load it.

        Args:
            cache_key: Unique key for this model configuration.

        Returns:
            True if the model was loaded from cache after waiting, False otherwise.
        """
        # If another thread is globally initializing, then...
        if GlinerEntityDetector._global_initializing:
            log_info("[GLINER] Another thread is already initializing the model")
            # Wait up to 60 seconds for initialization.
            wait_until = time.time() + 60.0
            while GlinerEntityDetector._global_initializing and time.time() < wait_until:
                time.sleep(1)
            # After waiting, if the cache now contains the model, load it.
            if cache_key in GlinerEntityDetector._model_cache:
                return self._load_model_from_cache_and_log(cache_key, "after waiting ")
        # Otherwise, return False.
        return False

    def _perform_model_initialization(self, cache_key, start_time: float, max_retries: int = 2) -> None:
        """
        Load the model by either using local files or by downloading it, with retries.

        Args:
            cache_key: Unique key for this model configuration.
            start_time: Time when initialization started.
            max_retries: Number of attempts to initialize the model.
        """
        # Check if a valid local model directory exists.
        local_exists = self._check_local_model_exists()
        log_info(f"[GLINER] Local model exists: {local_exists}")
        # Try model initialization for a maximum number of retries.
        for attempt_index in range(max_retries):
            log_info(f"[GLINER] Attempt {attempt_index + 1}/{max_retries} for model initialization.")
            # Attempt model initialization.
            if self._attempt_model_init(local_exists, attempt_index):
                # Compute the initialization duration.
                init_duration = time.time() - start_time
                # Record the initialization time.
                self._initialization_time = init_duration
                # Mark the instance as initialized.
                self._is_initialized = True
                # Update the last used time.
                self._last_used = time.time()
                log_info(f"[OK] Model initialized in {init_duration:.2f}s")
                # Cache the loaded model globally.
                GlinerEntityDetector._model_cache[cache_key] = {
                    "model": self.model,
                    "init_time": init_duration
                }
                GlinerEntityDetector._global_initialization_time = init_duration
                return
            else:
                # After a failed attempt, do not rely on local files.
                local_exists = False
                log_warning(f"[WARNING] Attempt {attempt_index + 1}: failed to load local model, will attempt download")
                self.local_files_only = False
                time.sleep(2)
        # If initialization fails after retries, record the failure.
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
        Try to initialize the model either from a local directory or by downloading it.

        Args:
            local_exists: Whether a local model directory is present.
            attempt_index: Current attempt number.

        Returns:
            True if the model was successfully loaded, False otherwise.
        """
        try:
            # If a valid local model exists...
            if local_exists:
                log_info(f"[OK] Attempting to load model from local directory: {self.model_dir_path}")
                # Try to load the model from the local directory.
                if self._load_local_model(self.model_dir_path):
                    return True
                else:
                    local_exists = False
                    log_warning(
                        f"[WARNING] Attempt {attempt_index + 1}: failed to load local model, will attempt download")
                    # Set local_files_only too False to allow downloading.
                    self.local_files_only = False
            # If no local model exists or local loading failed...
            if not local_exists:
                log_info(f"[OK] Downloading GLiNER model: {self.model_name}")
                # Import GLiNER (in case of top-level errors).
                from gliner import GLiNER
                # Load the model by downloading from the pretrained source.
                self.model = GLiNER.from_pretrained(self.model_name)
                # If a local model path is set, save the model for future use.
                if self.local_model_path:
                    self._save_model_to_directory(self.model_dir_path)
            # Return True if the model is loaded successfully.
            return self.model is not None
        except Exception as init_exc:
            # Log any exceptions during model initialization.
            SecurityAwareErrorHandler.log_processing_error(init_exc, f"gliner_initialization_attempt_{attempt_index}",
                                                           self.model_name)
            return False

    def _load_model_from_cache_and_log(self, cache_key: tuple, reason: str) -> bool:
        """
        Load a cached model from the global cache and log the event.

        Args:
            cache_key: Unique key for this model configuration.
            reason: A phrase describing how the model was loaded (e.g., "after waiting").

        Returns:
            True if the model was loaded successfully.
        """
        # Retrieve the cached model information.
        cached = GlinerEntityDetector._model_cache[cache_key]
        # Set the model from cache.
        self.model = cached["model"]
        # Record the initialization time from cache.
        self._initialization_time = cached["init_time"]
        # Mark as initialized.
        self._is_initialized = True
        # Update the last used time.
        self._last_used = time.time()
        log_info(f"[GLINER] Loaded model from cache {reason}in {self._initialization_time:.2f}s")
        return True

    @staticmethod
    def _init_norwegian_pronouns() -> set:
        """
        Initialize a set of Norwegian pronouns used for filtering false positives.

        Returns:
            A set of lowercase Norwegian pronouns.
        """
        # Define a set of Norwegian pronouns.
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
        # Return the set of pronouns in lowercase.
        return {w.lower() for w in pronouns}

    def _fix_config_file_discrepancy(self) -> None:
        """
        Resolve configuration file discrepancies by copying gliner_config.json
        to config.json if the latter does not exist.
        """
        try:
            # Build the paths to gliner_config.json and config.json.
            gliner_config_path = os.path.join(self.model_dir_path, GLINER_CONFIG_FILENAME)
            config_path = os.path.join(self.model_dir_path, CONFIG_FILENAME)
            # If gliner_config.json exists and config.json does not...
            if os.path.exists(gliner_config_path) and not os.path.exists(config_path):
                log_info("[GLINER] Creating config.json from gliner_config.json")
                # Copy gliner_config.json to config.json.
                shutil.copy2(GLINER_CONFIG_FILENAME, CONFIG_FILENAME)
                log_info("[GLINER] Successfully created config.json")
        except Exception as exc:
            # Log any errors encountered during the configuration fix.
            SecurityAwareErrorHandler.log_processing_error(exc, "gliner_config_fix", self.model_dir_path)

    def _check_local_model_exists(self) -> bool:
        """
        Verify whether a valid local model directory exists by checking for required files.

        Returns:
            True if a valid model directory exists; False otherwise.
        """
        # Check if the model directory path exists.
        if not os.path.exists(self.model_dir_path):
            log_warning(f"[GLINER] Model directory does not exist: {self.model_dir_path}")
            return False
        # Check if the model directory path is actually a directory.
        if not os.path.isdir(self.model_dir_path):
            log_warning(f"[GLINER] Model path is not a directory: {self.model_dir_path}")
            return False
        # Define a list of required file names.
        required_files = ['pytorch_model.bin']
        # Define possible configuration file names.
        config_files = [CONFIG_FILENAME, GLINER_CONFIG_FILENAME]
        # Check if any configuration file exists.
        has_config = any(os.path.exists(os.path.join(self.model_dir_path, f)) for f in config_files)
        if not has_config:
            log_warning("[GLINER] No configuration file found in model directory")
            return False
        # Identify any missing required files.
        missing_files = [f for f in required_files if not os.path.exists(os.path.join(self.model_dir_path, f))]
        if missing_files:
            log_warning(f"[GLINER] Missing required model files: {missing_files}")
            return False
        log_info(f"[GLINER] Found valid model directory at {self.model_dir_path}")
        return True

    def _save_model_to_directory(self, model_dir: str) -> bool:
        """
        Save the loaded model to a directory using GLiNER's native saving method or torch.save.

        Args:
            model_dir: The directory to save the model in.

        Returns:
            True if the model was saved successfully, False otherwise.
        """
        try:
            # If the model is not loaded, log an error.
            if not self.model:
                log_error("[ERROR] Cannot save model - model not initialized")
                return False
            # Ensure that the model directory exists.
            os.makedirs(model_dir, exist_ok=True)
            log_info(f"[OK] Saving GLiNER model to directory: {model_dir}")
            # If the model has a save_pretrained method, use it.
            if hasattr(self.model, "save_pretrained"):
                self.model.save_pretrained(model_dir)
                log_info("[OK] Used GLiNER's native save_pretrained method")
            else:
                # Otherwise, use torch.save to save the model state dictionary.
                torch.save(self.model.state_dict(), os.path.join(model_dir, "pytorch_model.bin"))
                # If a configuration exists, save it as well.
                if hasattr(self.model, "config"):
                    self.model.config.save_pretrained(model_dir)
            log_info(f"[OK] GLiNER model saved successfully to {model_dir}")
            return True
        except Exception as exc:
            # Log any errors encountered during saving.
            SecurityAwareErrorHandler.log_processing_error(exc, "gliner_model_save", model_dir)
            return False

    def _load_local_model(self, model_dir: str) -> bool:
        """
        Load the model from a local directory using GLiNER's native method with error handling.

        Args:
            model_dir: The path to the model directory.

        Returns:
            True if the model was loaded successfully, False otherwise.
        """
        try:
            log_info(f"[OK] Loading GLiNER model from directory: {model_dir}")
            # Ensure the model directory is valid.
            if not os.path.isdir(model_dir):
                log_error(f"[ERROR] Expected a directory for model path: {model_dir}")
                return False
            # Fix any discrepancies in configuration files.
            self._fix_config_file_discrepancy()
            from gliner import GLiNER  # re-import for safety
            try:
                config_path = os.path.join(model_dir, CONFIG_FILENAME)
                if not os.path.exists(config_path):
                    log_warning("[GLINER] config.json still doesn't exist after fix attempt")
                # Load the model using GLiNER's native from_pretrained method.
                self.model = GLiNER.from_pretrained(model_dir, local_files_only=True)
                self._is_initialized = True
                self._initialization_time = time.time()
                log_info("[OK] Loaded model using GLiNER's native from_pretrained method")
                return True
            except Exception as load_error:
                # Log errors from the native load attempt.
                SecurityAwareErrorHandler.log_processing_error(load_error, "gliner_model_load_native", model_dir)
                # If native load fails, try loading with an explicit configuration.
                return self._attempt_explicit_config_load(model_dir)
        except Exception as exc:
            # Log any errors during local model loading.
            SecurityAwareErrorHandler.log_processing_error(exc, "gliner_model_load", model_dir)
            return False

    def _attempt_explicit_config_load(self, model_dir: str) -> bool:
        """
        Attempt to load the model with an explicit configuration file if the native load fails.

        Args:
            model_dir: The model directory path.

        Returns:
            True if loading succeeded, False otherwise.
        """
        try:
            from gliner import GLiNER
            # Build paths to the configuration files.
            gliner_config_path = os.path.join(model_dir, GLINER_CONFIG_FILENAME)
            config_path = os.path.join(model_dir, CONFIG_FILENAME)
            # Choose the configuration file that exists.
            chosen_config = config_path if os.path.exists(config_path) else gliner_config_path
            # If a configuration file is available...
            if os.path.exists(chosen_config):
                log_info(f"[GLINER] Trying to load with explicit config path: {chosen_config}")
                try:
                    # Load the configuration using transformers AutoConfig.
                    config = AutoConfig.from_pretrained(chosen_config)
                    # Load the model using the provided configuration.
                    self.model = GLiNER.from_pretrained(model_dir, config=config, local_files_only=True)
                    self._is_initialized = True
                    log_info("[OK] Loaded model with explicit config")
                    return True
                except ImportError:
                    log_warning("[WARNING] Could not import AutoConfig from transformers")
            return False
        except Exception as config_error:
            # Log errors during explicit configuration loading.
            SecurityAwareErrorHandler.log_processing_error(config_error, "gliner_model_load_explicit_config", model_dir)
            return False

    async def detect_sensitive_data_async(
            self,
            extracted_data: Dict[str, Any],
            requested_entities: Optional[List[str]] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Asynchronously detect sensitive entities in extracted data with GDPR compliance.

        This method minimizes input data, validates requested entities, prepares page data,
        and processes pages in parallel to extract and process entities.

        Args:
            extracted_data: Dictionary containing text and bounding box information.
            requested_entities: List of entity types to detect.

        Returns:
            Tuple of (detected entities, redaction mapping).
        """
        # Record the start time.
        start_time = time.time()
        # Minimize data for GDPR compliance.
        minimized_data = minimize_extracted_data(extracted_data)
        # Update call count and last used timestamp.
        self._total_calls += 1
        self._last_used = time.time()
        try:
            # If requested entities are provided, validate them.
            if requested_entities is not None:
                requested_entities_json = json.dumps(requested_entities)
                validated_entities = validate_gliner_requested_entities(requested_entities_json)
            else:
                # Otherwise, use default entities.
                validated_entities = self.default_entities
        except Exception as e:
            # Log an error if validation fails.
            log_error("[GLINER] Entity validation failed: " + str(e))
            record_keeper.record_processing(
                operation_type="gliner_detection",
                document_type="document",
                entity_types_processed=requested_entities or [],
                processing_time=time.time() - start_time,
                entity_count=0,
                success=False
            )
            return [], {"pages": []}
        # If no valid entities remain, record and return empty results.
        if not validated_entities:
            log_warning("[GLINER] No valid entities remain after filtering, returning empty results")
            record_keeper.record_processing(
                operation_type="gliner_detection",
                document_type="document",
                entity_types_processed=[],
                processing_time=time.time() - start_time,
                entity_count=0,
                success=False
            )
            return [], {"pages": []}
        try:
            # Retrieve pages from the minimized data.
            pages = minimized_data.get("pages", [])
            if not pages:
                return [], {"pages": []}
            # Prepare page texts and mapping data.
            page_texts_and_mappings, redaction_mapping = self._prepare_page_data(pages)
            if not page_texts_and_mappings:
                return [], {"pages": []}
            # Process pages concurrently using the GLiNER asynchronous method.
            page_results = await self._process_pages_gliner_async(pages, page_texts_and_mappings, validated_entities)
            # Combine entities from all pages.
            combined_results = []
            for local_page_number, (local_page_redaction_info, local_processed_entities) in page_results:
                if local_page_redaction_info:
                    redaction_mapping["pages"].append(local_page_redaction_info)
                if local_processed_entities:
                    combined_results.extend(local_processed_entities)
            # Sort the redaction mapping pages by page number.
            redaction_mapping["pages"].sort(key=lambda x: x.get("page", 0))
            total_time = time.time() - start_time
            # Record processing details.
            record_keeper.record_processing(
                operation_type="gliner_detection",
                document_type="document",
                entity_types_processed=validated_entities,
                processing_time=total_time,
                entity_count=len(combined_results),
                success=True
            )
            # Log sensitive operation metrics.
            log_sensitive_operation("GLiNER Detection", len(combined_results), total_time, pages=len(pages))
            # Return the combined results and redaction mapping.
            return combined_results, redaction_mapping
        except Exception as exc:
            # In case of error, record processing failure.
            error_time = time.time() - start_time
            record_keeper.record_processing(
                operation_type="gliner_detection",
                document_type="document",
                entity_types_processed=validated_entities,
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
            pages: List of page dictionaries.
            page_texts_and_mappings: Mapping from page number to (full_text, mapping).
            requested_entities: List of entity types to detect.

        Returns:
            List of tuples containing page number and a tuple of (redaction info, processed entities).
        """

        # Define an asynchronous function to process a single page with a timeout.
        async def process_page_async(local_page_data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
            try:
                # Process the single page with a timeout.
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

        # Process pages concurrently using ParallelProcessingCore.
        return await ParallelProcessingCore.process_pages_in_parallel(pages, process_page_async)

    async def _process_single_page_async(
            self,
            local_page_data: Dict[str, Any],
            page_texts_and_mappings: Dict[int, Tuple[str, List]],
            requested_entities: List[str]
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Process a single page asynchronously to detect entities with enhanced error handling and GDPR compliance.

        This method uses the GLiNER model to process the page text, extracts entities,
        and then processes these entities into redaction information.

        Args:
            local_page_data: Dictionary with page details.
            page_texts_and_mappings: Mapping of page numbers to (full_text, mapping).
            requested_entities: List of entity types to detect.

        Returns:
            Tuple of (page_redaction_info, processed_entities).
        """
        # Record the start time for processing this page.
        page_start_time = time.time()
        # Extract the page number.
        local_page_number = local_page_data.get("page")
        # Retrieve the list of words; if none, return empty results.
        local_words = local_page_data.get("words", [])
        if not local_words:
            return {"page": local_page_number, "sensitive": []}, []
        # Retrieve full text and mapping for the page.
        full_text, mapping = page_texts_and_mappings.get(local_page_number, ("", []))
        if not full_text or not mapping:
            return {"page": local_page_number, "sensitive": []}, []
        log_info(f"[OK] Processing text with GLiNER on page {local_page_number}")
        # If the model is not available, log a warning and skip the page.
        if not self.model:
            log_warning(f"[WARNING] GLiNER model not available, skipping page {local_page_number}")
            return {"page": local_page_number, "sensitive": []}, []
        # Process text with GLiNER using a thread since it may be CPU-bound.
        page_entities = await asyncio.to_thread(self._process_text_with_gliner, full_text, requested_entities)
        if not page_entities:
            log_info(f"[OK] No entities detected by GLiNER on page {local_page_number}")
            return {"page": local_page_number, "sensitive": []}, []
        entity_count = len(page_entities)
        log_info(f"[OK] Found {entity_count} entities on page {local_page_number}")
        # Process detected entities into redaction information using parallel processing.
        processed_entities, local_page_redaction_info = await ParallelProcessingCore.process_entities_in_parallel(
            self, full_text, mapping, page_entities, local_page_number
        )
        # Calculate the time taken to process the page.
        page_time = time.time() - page_start_time
        # Record sensitive processing metrics.
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
        Prepare page data by extracting full text and mapping for each page.

        Args:
            pages: List of page dictionaries with word data.

        Returns:
            A tuple containing:
              - page_texts_and_mappings: Mapping of page number to (full_text, mapping).
              - redaction_mapping: A dictionary initialized with an empty pages list.
        """
        # Initialize an empty dictionary for page texts and mappings.
        page_texts_and_mappings = {}
        # Initialize redaction mapping with an empty pages list.
        redaction_mapping = {"pages": []}
        # Iterate over each page.
        for page in pages:
            # Extract words from the page.
            words = page.get("words", [])
            local_page_number = page.get("page")
            # If there are no words, add an empty sensitive list and continue.
            if not words:
                redaction_mapping["pages"].append({"page": local_page_number, "sensitive": []})
                continue
            # Check if page has content.
            has_content = any(w.get("text", "").strip() for w in words)
            if not has_content:
                log_info(f"[OK] Skipping empty page {local_page_number}")
                redaction_mapping["pages"].append({"page": local_page_number, "sensitive": []})
                continue
            try:
                # Reconstruct full text and mapping using TextUtils.
                full_text, mapping = TextUtils.reconstruct_text_and_mapping(words)
                page_texts_and_mappings[local_page_number] = (full_text, mapping)
            except Exception as exc:
                SecurityAwareErrorHandler.log_processing_error(exc, "prepare_page_data", f"page_{local_page_number}")
        return page_texts_and_mappings, redaction_mapping

    def _process_text_with_gliner(
            self,
            text: str,
            requested_entities: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Process text with GLiNER to extract entities, with robust error handling.

        This method first checks for a cached result and returns it if available.
        If not, it processes the text by splitting it into paragraphs and batches,
        extracts entities for each group, deduplicates and filters results, and caches the result.

        Args:
            text: The text to process.
            requested_entities: List of entity types to detect.

        Returns:
            List of detected entity dictionaries.
        """
        # Generate a unique cache key based on the text and requested entities.
        key = GLiNERHelper.get_cache_key(text, requested_entities)
        # Attempt to retrieve a cached result.
        cached = GLiNERHelper.get_cached_result(key)
        if cached is not None:
            log_info("✅ Using cached GLiNER result")
            return cached
        # Record start time.
        start_time = time.time()
        # If text is too short, return an empty list.
        if not text or len(text.strip()) < 3:
            return []
        # Check if model is available; if not, log a safe error and return empty list.
        if not self.model:
            SecurityAwareErrorHandler.handle_safe_error(
                ValueError("GLiNER model not available"),
                "detection_gliner_model_unavailable",
                "",
                default_return=[]
            )
            return []
        # Ensure model has been initialized.
        if not self._is_initialized:
            SecurityAwareErrorHandler.handle_safe_error(
                ValueError("GLiNER model not properly initialized"),
                "detection_gliner_model_not_initialized",
                "",
                default_return=[]
            )
            return []
        # Split the text into paragraphs and filter out empty lines.
        paragraphs = [p for p in text.split('\n') if p.strip()]
        all_entities: List[Dict[str, Any]] = []
        # Define the batch size for paragraph processing.
        batch_size = 5
        # Process paragraphs in batches.
        for i in range(0, len(paragraphs), batch_size):
            batch_paragraphs = paragraphs[i:i + batch_size]
            # Process the batch and extract entities.
            batch_results = self._process_paragraph_batch(batch_paragraphs, text, requested_entities)
            all_entities.extend(batch_results)
        # Deduplicate entities.
        deduplicated_entities = deduplicate_entities(all_entities)
        # Filter out false positives based on Norwegian pronouns.
        filtered_entities = self._filter_norwegian_pronouns(deduplicated_entities)
        processing_time = time.time() - start_time
        self.total_processing_time += processing_time
        # Cache the filtered result.
        GLiNERHelper.set_cached_result(key, filtered_entities)
        return filtered_entities

    def _process_paragraph_batch(
            self,
            paragraphs: List[str],
            full_text: str,
            requested_entities: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Process a batch of paragraphs by splitting each paragraph into smaller groups
        and extracting entities for each group.

        For each paragraph:
          1. Determine the base offset.
          2. Split the paragraph into groups (max 800 characters).
          3. Process each group and adjust the offsets.
          4. Aggregate detected entities.

        Args:
            paragraphs: List of paragraph strings.
            full_text: The full page text.
            requested_entities: List of entity types to detect.

        Returns:
            A list of detected entity dictionaries.
        """
        all_entities = []
        # Iterate over each paragraph.
        for paragraph in paragraphs:
            if not paragraph.strip():
                continue
            # Determine the base offset of the paragraph in the full text.
            base_offset = full_text.find(paragraph)
            if base_offset == -1:
                continue
            # Split paragraph into sentence groups with a max size.
            sentence_groups = GLiNERHelper.split_into_sentence_groups(paragraph, 800)
            # Process each sentence group.
            for group_text in sentence_groups:
                group_offset = paragraph.find(group_text)
                if group_offset == -1:
                    continue
                # Calculate the absolute offset of the group in the full text.
                absolute_offset = base_offset + group_offset
                # Extract entities for the group.
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
        Extract entities from a text group using the model's prediction method.

        This method acquires a lock for thread-safe access, logs debug information,
        calls the model's predict_entities method, adjusts offsets, and returns the results.

        Args:
            group_text: The text chunk to process.
            requested_entities: List of entity types to detect.
            absolute_offset: Base offset of the group within the full text.

        Returns:
            List of detected entity dictionaries.
        """
        local_entities = []
        # Acquire the model analyzer lock.
        lock = self._get_model_analyzer_lock()
        if not lock.acquire(timeout=600.0):
            log_warning("[GLINER] Timeout acquiring model analyzer lock")
            return local_entities
        try:
            log_info(
                f"[DEBUG] Processing group_text (length {len(group_text)}): for entity_types: {requested_entities}")
            # Predict entities using the loaded GLiNER model.
            group_entities = self.model.predict_entities(group_text, requested_entities, threshold=0.5)
            # Adjust each detected entity's offsets.
            for entity in group_entities:
                entity_dict = {
                    "entity_type": entity.get("label", "UNKNOWN"),
                    "start": absolute_offset + entity.get("start", 0),
                    "end": absolute_offset + entity.get("end", 0),
                    "score": entity.get("score", 0.5),
                    "original_text": entity.get("text", "")
                }
                local_entities.append(entity_dict)
        except Exception as predict_error:
            log_error(
                f"[DEBUG] Error in predict_entities for group_text (length {len(group_text)}): Error: {predict_error}")
            SecurityAwareErrorHandler.log_processing_error(predict_error, "gliner_predict_entities",
                                                           f"group_{hash(group_text) % 10000}")
        finally:
            lock.release()
        return local_entities

    def _filter_norwegian_pronouns(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter out Norwegian pronouns that are incorrectly identified as person names.

        Args:
            entities: List of detected entity dictionaries.

        Returns:
            A filtered list of entities without false positives due to pronoun detection.
        """
        filtered_entities = []
        # Iterate over each detected entity.
        for ent in entities:
            etype = ent["entity_type"]
            # If the entity is detected as a person...
            if etype in {"person", "per"}:
                text_val = ent.get("original_text", "").strip()
                text_words = text_val.split()
                # If it's a single word that is a known pronoun, skip it.
                if len(text_words) == 1 and text_words[0].lower() in self.norwegian_pronouns:
                    log_info("[FILTER] Removed Norwegian pronoun incorrectly detected as person")
                    continue
                # If all words in a multi-word phrase are pronouns, skip it.
                if len(text_words) > 1 and all(w.lower() in self.norwegian_pronouns for w in text_words):
                    log_info("[FILTER] Removed compound Norwegian pronoun incorrectly detected as person")
                    continue
            filtered_entities.append(ent)
        return filtered_entities

    def get_status(self) -> Dict[str, Any]:
        """
        Retrieve the current status and performance metrics of the GLiNER detector.

        Returns:
            A dictionary containing initialization status, timings, model info, and file details.
        """
        # Build and return a status dictionary with various metrics and configuration details.
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
                self.total_processing_time / self._total_calls if self._total_calls > 0 else None),
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
