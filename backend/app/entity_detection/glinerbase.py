"""
Generic entity detector implementations with GDPR compliance and error handling.

This module provides a generic base class to implement entity detection engines that share the same core logic,
such as initialization, caching, asynchronous detection, and error handling. Specific engine implementations
(such as GLiNER and HIDEME) inherit from this base class simply by overriding engine-specific configuration
attributes and optionally the validation methods. The design helps avoid code duplication while allowing
each engine to maintain its own instance, caching, and status tracking.
"""

import asyncio
import json
import os
import shutil
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

import torch
from transformers import AutoConfig

from backend.app.entity_detection.base import BaseEntityDetector
from backend.app.utils.helpers.gliner_helper import GLiNERHelper
from backend.app.utils.helpers.json_helper import validate_gliner_requested_entities
from backend.app.utils.helpers.text_utils import TextUtils
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.parallel.core import ParallelProcessingCore
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.system_utils.synchronization_utils import TimeoutLock, LockPriority
from backend.app.utils.validation.data_minimization import minimize_extracted_data
from backend.app.utils.validation.sanitize_utils import deduplicate_entities

# Attempt to import the underlying GLiNER library.
try:
    from gliner import GLiNER

    ENGINE_LIB_AVAILABLE = True
except ImportError:
    ENGINE_LIB_AVAILABLE = False


class GenericEntityDetector(BaseEntityDetector):
    """
    GenericEntityDetector is a generic base class for entity detection engines.

    It implements:
      - A singleton pattern (one instance per subclass).
      - Model initialization from local files or by download.
      - A global caching mechanism using a dedicated cache namespace.
      - Asynchronous entity detection with error handling.
      - Utility methods for pre-processing, extraction, post-processing, and validation.

    Subclasses should override these class attributes:
        ENGINE_NAME:        Engine name (e.g. "GLiNER" or "HIDEME").
        MODEL_NAME:         Model name or path.
        DEFAULT_ENTITIES:   List of default entity types.
        MODEL_DIR_PATH:     Directory where the model files are stored.
        CACHE_NAMESPACE:    Unique namespace for caching.
        CONFIG_FILE_NAME:   Engine-specific configuration filename.

    Subclasses can also override the validate_requested_entities() method if needed.
    """

    # Class attributes for engine configuration (to be overridden by subclasses)
    ENGINE_NAME: Optional[str] = None
    MODEL_NAME: Optional[str] = None
    DEFAULT_ENTITIES: Optional[List[str]] = None
    MODEL_DIR_PATH: Optional[str] = None
    CACHE_NAMESPACE: Optional[str] = None
    CONFIG_FILE_NAME: Optional[str] = None

    # Shared attributes for singleton behavior and caching.
    _shared_instance = None
    _shared_instance_lock = TimeoutLock(name="generic_shared_instance_lock", priority=LockPriority.HIGH, timeout=600.0)
    _model_lock = TimeoutLock(name="generic_model_lock", priority=LockPriority.HIGH, timeout=600.0)
    _global_initializing = False
    _global_initialization_time = None
    _model_cache = {}

    def __new__(cls, *args, **kwargs):
        """
        Enforce the singleton pattern: only one instance per subclass.
        """
        # Check if the shared instance is not created yet.
        if cls._shared_instance is None:
            # Acquire the shared instance lock.
            acquired = cls._shared_instance_lock.acquire(timeout=600.0)
            # If the lock is acquired successfully:
            if acquired:
                try:
                    # Double-check if the shared instance is still None.
                    if cls._shared_instance is None:
                        # Create a new instance using superclass __new__.
                        cls._shared_instance = super().__new__(cls)
                finally:
                    # Release the shared instance lock.
                    cls._shared_instance_lock.release()
        # Return the (singleton) shared instance.
        return cls._shared_instance

    def __init__(self,
                 model_name: Optional[str] = None,
                 entities: Optional[List[str]] = None,
                 local_model_path: Optional[str] = None,
                 local_files_only: bool = False):
        """
        Initialize the detector with error handling, caching, and language-specific resources.

        Args:
            model_name: Optional model name/path (if not provided, use the class attribute MODEL_NAME).
            entities: Optional entity types (if None, use the class attribute DEFAULT_ENTITIES).
            local_model_path: Optional directory for local model files (derived from MODEL_DIR_PATH if not provided).
            local_files_only: Boolean flag to load only from local files.
        """
        # If the instance was already initialized, then exit.
        if getattr(self, "_already_initialized", False):
            return
        # Call the initialization method of the base class.
        super().__init__()
        # Set the instance model name; use provided model_name or fallback to the class attribute.
        self._model_name: str = model_name if model_name is not None else self.MODEL_NAME
        # Set the default entities list; use provided or fallback to the class attribute.
        self._default_entities: List[str] = entities if entities is not None else self.DEFAULT_ENTITIES
        # Set the local model path; use provided value or derive it from the model directory path.
        self._local_model_path: str = local_model_path if local_model_path is not None else os.path.dirname(
            self.MODEL_DIR_PATH)
        # Set the flag to load only local files.
        self._local_files_only: bool = local_files_only
        # Save the model directory path.
        self._model_dir_path: str = self.MODEL_DIR_PATH
        # Initialize the model instance variable to None.
        self.model = None
        # Set a flag indicating if the model is initialized.
        self._is_initialized: bool = False
        # Initialize an instance lock (will be set later if needed).
        self._instance_lock: Optional[TimeoutLock] = None
        # Counter for total number of detection calls.
        self._total_calls: int = 0
        # Accumulate total processing time.
        self.total_processing_time: float = 0.0
        # Log an error if the underlying engine library is not available.
        if not ENGINE_LIB_AVAILABLE:
            log_error(f"[ERROR] {self.ENGINE_NAME} package not installed. Please install with 'pip install gliner'")
        # Initialize Norwegian pronouns for filtering.
        self.norwegian_pronouns = self._init_norwegian_pronouns()
        # Initialize model analyzer lock to None (will be created lazily).
        self._model_analyzer_lock: Optional[TimeoutLock] = None
        # Attempt to initialize the model.
        self._initialize_model()
        # Mark the instance as already initialized.
        self._already_initialized = True

    def _get_model_analyzer_lock(self) -> TimeoutLock:
        """
        Lazily create and return the analyzer lock for synchronizing model inference.

        Returns:
            TimeoutLock instance used for model analysis.
        """
        # If the analyzer lock is not created yet, then create it.
        if self._model_analyzer_lock is None:
            try:
                # Create a new TimeoutLock with a unique name based on the engine.
                self._model_analyzer_lock = TimeoutLock(
                    name=f"{self.ENGINE_NAME.lower()}_analyzer_lock",
                    priority=LockPriority.HIGH,
                    timeout=600.0
                )
            except Exception as exc:
                # Log any errors during lock creation using the error handler.
                SecurityAwareErrorHandler.log_processing_error(exc, "model_analyzer_lock_init", self._model_dir_path)
        # Return the analyzer lock.
        return self._model_analyzer_lock

    def _initialize_model(self) -> None:
        """
        Entry point for model initialization. Checks for engine library availability and then
        attempts to load the model from cache or initialize it with retries.
        """
        # If the engine library is not available, log an error and return.
        if not ENGINE_LIB_AVAILABLE:
            log_error(f"[ERROR] {self.ENGINE_NAME} package not installed.")
            return
        # If already initialized and a model is loaded, then exit early.
        if self._is_initialized and self.model is not None:
            return
        # Create a unique cache key based on model parameters.
        cache_key = (self._model_name, self._local_files_only, tuple(sorted(self._default_entities)))
        # Attempt to load the model from the cache.
        if self._try_load_model_from_cache(cache_key):
            return
        # Record the start time of initialization.
        start_time = time.time()
        # Acquire the model lock to avoid concurrent initializations.
        acquired = self.__class__._model_lock.acquire(timeout=600.0)
        # If acquiring the lock fails, log an error and return.
        if not acquired:
            log_error(f"[{self.ENGINE_NAME}] Timeout acquiring model lock for initialization")
            return
        try:
            # Try loading the model from cache again after acquiring the lock.
            if self._try_load_model_from_cache(cache_key):
                return
            # Handle concurrent initialization if another thread is already initializing.
            if self._handle_concurrent_initialization(cache_key):
                return
            # Mark the global initialization state as active.
            self.__class__._global_initializing = True
            try:
                # Perform the actual model initialization with retries.
                self._perform_model_initialization(cache_key, start_time)
            finally:
                # Reset the global initializing flag after the initialization attempt.
                self.__class__._global_initializing = False
        finally:
            # Release the model lock.
            self.__class__._model_lock.release()

    def _try_load_model_from_cache(self, cache_key) -> bool:
        """
        Check if the model is available in the cache and load it if found.

        Args:
            cache_key: A unique key representing the model configuration.

        Returns:
            True if the model was loaded from the cache, otherwise False.
        """
        # Acquire the model lock with a short timeout.
        acquired = self.__class__._model_lock.acquire(timeout=5.0)
        if not acquired:
            # Log a warning if the lock could not be acquired.
            log_warning(f"[{self.ENGINE_NAME}] Timeout acquiring model lock for cache check")
            return False
        try:
            # If the cache key exists in the model cache:
            if cache_key in self.__class__._model_cache:
                # Load the model from cache and log the event.
                return self._load_model_from_cache_and_log(cache_key, "in")
            # Otherwise, return False.
            return False
        finally:
            # Release the model lock.
            self.__class__._model_lock.release()

    def _handle_concurrent_initialization(self, cache_key) -> bool:
        """
        Wait for any concurrent initialization to finish and load from cache if available.

        Args:
            cache_key: Unique key for the model configuration.

        Returns:
            True if the model was loaded from cache after waiting; otherwise, False.
        """
        # Check if a global initialization is currently in progress.
        if self.__class__._global_initializing:
            # Log an info message indicating concurrent initialization.
            log_info(f"[{self.ENGINE_NAME}] Another thread is already initializing the model")
            # Set the maximum wait time.
            wait_until = time.time() + 60.0
            # Wait until initialization is done or time runs out.
            while self.__class__._global_initializing and time.time() < wait_until:
                time.sleep(1)
            # If the model is now in cache, load it.
            if cache_key in self.__class__._model_cache:
                return self._load_model_from_cache_and_log(cache_key, "after waiting ")
        # Otherwise, return False.
        return False

    def _perform_model_initialization(self, cache_key, start_time: float, max_retries: int = 2) -> None:
        """
        Attempt model initialization using local files or by downloading it, with a limited number of retries.

        Args:
            cache_key: Unique key for the model configuration.
            start_time: Start time of initialization.
            max_retries: Maximum number of initialization attempts.
        """
        # Check if a valid local model exists.
        local_exists = self._check_local_model_exists()
        # Log whether the local model exists.
        log_info(f"[{self.ENGINE_NAME}] Local model exists: {local_exists}")
        # Loop over the number of attempts.
        for attempt_index in range(max_retries):
            # Log the current attempt.
            log_info(f"[{self.ENGINE_NAME}] Attempt {attempt_index + 1}/{max_retries} for model initialization.")
            # Try to initialize the model in this attempt.
            if self._attempt_model_init(local_exists, attempt_index):
                # Calculate the elapsed initialization duration (for logging purposes).
                init_duration = time.time() - start_time
                # Set the absolute initialization time using time.time().
                self._initialization_time = time.time()
                # Mark the model as initialized.
                self._is_initialized = True
                # Update the last used time.
                self._last_used = time.time()
                # Log the successful initialization and elapsed duration.
                log_info(f"[OK] Model initialized in {init_duration:.2f}s")
                # Cache the model and the absolute initialization time.
                self.__class__._model_cache[cache_key] = {
                    "model": self.model,
                    "init_time": self._initialization_time
                }
                # Set the global initialization time to the absolute value.
                self.__class__._global_initialization_time = self._initialization_time
                return
            else:
                # Set local_exists to False for subsequent attempts.
                local_exists = False
                # Log a warning and indicate a download will be attempted.
                log_warning(f"[WARNING] Attempt {attempt_index + 1}: failed to load local model, will attempt download")
                # Disable local-only mode to allow downloads.
                self._local_files_only = False
                # Sleep briefly before retrying.
                time.sleep(2)
        # If all retries failed, record the failure.
        record_keeper.record_processing(
            operation_type=f"{self.ENGINE_NAME.lower()}_model_initialization",
            document_type="model",
            entity_types_processed=self._default_entities,
            processing_time=time.time() - start_time,
            entity_count=0,
            success=False
        )

    def _attempt_model_init(self, local_exists: bool, attempt_index: int) -> bool:
        """
        Try to initialize the model either from a local directory or by downloading it.

        Args:
            local_exists: Boolean indicating if a local model exists.
            attempt_index: Current attempt number.

        Returns:
            True if initialization succeeded; otherwise, False.
        """
        try:
            # If a local model exists, attempt to load it.
            if local_exists:
                log_info(f"[OK] Attempting to load model from local directory: {self._model_dir_path}")
                # If loading the local model succeeds, return True.
                if self._load_local_model(self._model_dir_path):
                    return True
                else:
                    # Otherwise, mark local_exists as False.
                    local_exists = False
                    # Log a warning indicating failure and intent to download.
                    log_warning(
                        f"[WARNING] Attempt {attempt_index + 1}: failed to load local model, will attempt download")
                    # Disable local_files_only mode.
                    self._local_files_only = False
            # If no local model exists, attempt to download the model.
            if not local_exists:
                log_info(f"[OK] Downloading {self.ENGINE_NAME} model: {self._model_name}")
                # Import GLiNER from gliner module.
                from gliner import GLiNER
                # Download the model using the from_pretrained method.
                self.model = GLiNER.from_pretrained(self._model_name)
                # If a local model path is specified, then save the model to that directory.
                if self._local_model_path:
                    self._save_model_to_directory(self._model_dir_path)
            # Return True if the model was successfully downloaded and set.
            return self.model is not None
        except Exception as init_exc:
            # Log any exception during model initialization.
            SecurityAwareErrorHandler.log_processing_error(init_exc,
                                                           f"{self.ENGINE_NAME.lower()}_initialization_attempt_{attempt_index}",
                                                           self._model_name)
            # Return False in case of failure.
            return False

    def _load_model_from_cache_and_log(self, cache_key: tuple, reason: str) -> bool:
        """
        Load the model from cache and log the event.

        Args:
            cache_key: Unique key for model configuration.
            reason: String explaining the context of cache loading.

        Returns:
            True if the model was successfully loaded from cache.
        """
        # Retrieve the cached model information using the cache key.
        cached = self.__class__._model_cache[cache_key]
        # Set the model instance variable from the cached model.
        self.model = cached["model"]
        # Set the initialization time from the cache.
        self._initialization_time = cached["init_time"]
        # Mark the model as initialized.
        self._is_initialized = True
        # Update the last used timestamp.
        self._last_used = time.time()
        # Log that the model was loaded from cache along with the reason.
        log_info(f"[{self.ENGINE_NAME}] Loaded model from cache {reason}in {self._initialization_time:.2f}s")
        # Return True indicating success.
        return True

    @staticmethod
    def _init_norwegian_pronouns() -> set:
        """
        Initialize and return a set of Norwegian pronouns in lowercase.

        Returns:
            A set containing Norwegian pronoun strings.
        """
        # Define a set of pronoun words.
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
        # Return the pronouns converted to lowercase.
        return {w.lower() for w in pronouns}

    def _fix_config_file_discrepancy(self) -> None:
        """
        Resolve configuration file discrepancies by copying the engine-specific configuration
        file to a common filename if necessary.
        """
        try:
            # Define the path for the engine-specific config file.
            engine_config_path = os.path.join(self._model_dir_path, self.CONFIG_FILE_NAME)
            # Define the path for the common config file.
            common_config_path = os.path.join(self._model_dir_path, "config.json")
            # If the engine-specific config exists but the common one does not:
            if os.path.exists(engine_config_path) and not os.path.exists(common_config_path):
                # Log the start of the copying process.
                log_info(f"[{self.ENGINE_NAME}] Creating config.json from {self.CONFIG_FILE_NAME}")
                # Copy the engine-specific config to the common location.
                shutil.copy2(engine_config_path, common_config_path)
                # Log a successful configuration file fix.
                log_info(f"[{self.ENGINE_NAME}] Successfully created config.json")
        except Exception as exc:
            # Log any error during the config discrepancy fix.
            SecurityAwareErrorHandler.log_processing_error(
                exc, f"{self.ENGINE_NAME.lower()}_config_fix", self._model_dir_path
            )

    def _check_local_model_exists(self) -> bool:
        """
        Verify whether a valid local model directory exists by checking for required files.

        Returns:
            True if the directory and required files are present; otherwise, False.
        """
        # Check if the model directory path exists.
        if not os.path.exists(self._model_dir_path):
            # Log a warning if the directory does not exist.
            log_warning(f"[{self.ENGINE_NAME}] Model directory does not exist: {self._model_dir_path}")
            return False
        # Check if the path is actually a directory.
        if not os.path.isdir(self._model_dir_path):
            # Log a warning if the path is not a directory.
            log_warning(f"[{self.ENGINE_NAME}] Model path is not a directory: {self._model_dir_path}")
            return False
        # Define the list of required model files.
        required_files = ['pytorch_model.bin']
        # Define configuration file names.
        config_files = [self.CONFIG_FILE_NAME, self.CONFIG_FILE_NAME]
        # Check if any of the configuration files exist.
        has_config = any(os.path.exists(os.path.join(self._model_dir_path, f)) for f in config_files)
        # If no configuration file is found:
        if not has_config:
            # Log a warning and return False.
            log_warning(f"[{self.ENGINE_NAME}] No configuration file found in model directory")
            return False
        # Identify any missing required files.
        missing_files = [f for f in required_files if not os.path.exists(os.path.join(self._model_dir_path, f))]
        # If required files are missing:
        if missing_files:
            # Log a warning mentioning the missing files.
            log_warning(f"[{self.ENGINE_NAME}] Missing required model files: {missing_files}")
            return False
        # Log that the model directory is valid.
        log_info(f"[{self.ENGINE_NAME}] Found valid model directory at {self._model_dir_path}")
        return True

    def _save_model_to_directory(self, model_dir: str) -> bool:
        """
        Save the loaded model using either the engine's native method or torch.save.

        Args:
            model_dir: Directory to which the model should be saved.

        Returns:
            True if the model was saved successfully; otherwise, False.
        """
        try:
            # If the model is not loaded, log an error and return False.
            if not self.model:
                log_error(f"[ERROR] Cannot save model - {self.ENGINE_NAME} model not initialized")
                return False
            # Ensure that the model directory exists.
            os.makedirs(model_dir, exist_ok=True)
            # Log the start of the saving process.
            log_info(f"[OK] Saving {self.ENGINE_NAME} model to directory: {model_dir}")
            # If the model has a native save_pretrained method:
            if hasattr(self.model, "save_pretrained"):
                # Save the model using the native method.
                self.model.save_pretrained(model_dir)
                # Log that the native method was used.
                log_info(f"[OK] Used {self.ENGINE_NAME}'s native save_pretrained method")
            else:
                # Otherwise, save the model state using torch.save.
                torch.save(self.model.state_dict(), os.path.join(model_dir, "pytorch_model.bin"))
                # If the model has a config attribute, save it as well.
                if hasattr(self.model, "config"):
                    self.model.config.save_pretrained(model_dir)
            # Log that the model was saved successfully.
            log_info(f"[OK] {self.ENGINE_NAME} model saved successfully to {model_dir}")
            return True
        except Exception as exc:
            # Log any exceptions encountered during model saving.
            SecurityAwareErrorHandler.log_processing_error(exc, f"{self.ENGINE_NAME.lower()}_model_save", model_dir)
            return False

    def _load_local_model(self, model_dir: str) -> bool:
        """
        Load the model from a local directory using the engine's native method.

        Args:
            model_dir: Directory from which to load the model.

        Returns:
            True if the model was loaded successfully; otherwise, False.
        """
        try:
            # Log the start of the local model loading process.
            log_info(f"[OK] Loading {self.ENGINE_NAME} model from directory: {model_dir}")
            # Check that the provided model_dir is a directory.
            if not os.path.isdir(model_dir):
                # Log an error if it is not a directory.
                log_error(f"[ERROR] Expected a directory for model path: {model_dir}")
                return False
            # Fix any configuration file discrepancy.
            self._fix_config_file_discrepancy()
            # Import GLiNER again for safety.
            from gliner import GLiNER
            try:
                # Define the path to the configuration file.
                config_path = os.path.join(model_dir, self.CONFIG_FILE_NAME)
                # Warn if the configuration file does not exist.
                if not os.path.exists(config_path):
                    log_warning(f"[{self.ENGINE_NAME}] config.json still doesn't exist after fix attempt")
                # Load the model using the native from_pretrained method.
                self.model = GLiNER.from_pretrained(model_dir, local_files_only=True)
                # Mark the model as initialized.
                self._is_initialized = True
                # Set the initialization time.
                self._initialization_time = time.time()
                # Log that the model was loaded successfully.
                log_info(f"[OK] Loaded model using {self.ENGINE_NAME}'s native from_pretrained method")
                return True
            except Exception as load_error:
                # Log any error during the native model load attempt.
                SecurityAwareErrorHandler.log_processing_error(load_error,
                                                               f"{self.ENGINE_NAME.lower()}_model_load_native",
                                                               model_dir)
                # Attempt to load the model using an explicit configuration file.
                return self._attempt_explicit_config_load(model_dir)
        except Exception as exc:
            # Log any errors encountered while trying to load the local model.
            SecurityAwareErrorHandler.log_processing_error(exc, f"{self.ENGINE_NAME.lower()}_model_load", model_dir)
            return False

    def _attempt_explicit_config_load(self, model_dir: str) -> bool:
        """
        Attempt to load the model using an explicit configuration file if the native load fails.

        Args:
            model_dir: Directory from which to load the model.

        Returns:
            True if the model was loaded successfully; otherwise, False.
        """
        try:
            # Import GLiNER from the gliner module.
            from gliner import GLiNER
            # Define the paths for the configuration files.
            engine_config_path = os.path.join(model_dir, self.CONFIG_FILE_NAME)
            config_path = os.path.join(model_dir, self.CONFIG_FILE_NAME)
            # Choose the configuration file that exists.
            chosen_config = config_path if os.path.exists(config_path) else engine_config_path
            # If the chosen configuration file exists:
            if os.path.exists(chosen_config):
                # Log that the explicit config load is being attempted.
                log_info(f"[{self.ENGINE_NAME}] Trying to load with explicit config path: {chosen_config}")
                try:
                    # Load the configuration using AutoConfig.
                    config = AutoConfig.from_pretrained(chosen_config)
                    # Load the model using the explicit configuration.
                    self.model = GLiNER.from_pretrained(model_dir, config=config, local_files_only=True)
                    # Mark the model as initialized.
                    self._is_initialized = True
                    # Log the success of the explicit config load.
                    log_info(f"[OK] Loaded model with explicit config for {self.ENGINE_NAME}")
                    return True
                except ImportError:
                    # Log a warning if AutoConfig could not be imported.
                    log_warning(f"[WARNING] Could not import AutoConfig from transformers for {self.ENGINE_NAME}")
            # If explicit config load failed, return False.
            return False
        except Exception as config_error:
            # Log any exception encountered during explicit config load.
            SecurityAwareErrorHandler.log_processing_error(config_error,
                                                           f"{self.ENGINE_NAME.lower()}_model_load_explicit_config",
                                                           model_dir)
            return False

    async def detect_sensitive_data_async(self,
                                          extracted_data: Dict[str, Any],
                                          requested_entities: Optional[List[str]] = None
                                          ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Asynchronously detect sensitive entities in the extracted data with GDPR compliance.

        Minimizes the data, validates requested entities, prepares page data, and processes pages concurrently.

        Args:
            extracted_data: Dictionary containing text and bounding box information.
            requested_entities: Optional list of requested entity types.

        Returns:
            A tuple containing:
              - A list of detected entity dictionaries.
              - A redaction mapping dictionary.
        """
        # Record the start time of the detection process.
        start_time = time.time()
        # Minimize the extracted data to reduce processing load.
        minimized_data = minimize_extracted_data(extracted_data)
        # Increment the total call counter.
        self._total_calls += 1
        # Update the last used timestamp.
        self._last_used = time.time()
        try:
            # If requested_entities is provided:
            if requested_entities is not None:
                # Convert the requested_entities list to a JSON string.
                requested_entities_json = json.dumps(requested_entities)
                # Validate the requested entities using the engine-specific validation.
                validated_entities = self.validate_requested_entities(requested_entities_json)
            else:
                # Otherwise, use the default entities.
                validated_entities = self._default_entities
        except Exception as e:
            # Log an error if entity validation fails.
            log_error(f"[{self.ENGINE_NAME}] Entity validation failed: " + str(e))
            # Record the processing failure.
            record_keeper.record_processing(
                operation_type=f"{self.ENGINE_NAME.lower()}_detection",
                document_type="document",
                entity_types_processed=requested_entities or [],
                processing_time=time.time() - start_time,
                entity_count=0,
                success=False
            )
            # Return empty results on validation failure.
            return [], {"pages": []}
        # If the validated entities list is empty:
        if not validated_entities:
            # Log a warning and record processing failure.
            log_warning(f"[{self.ENGINE_NAME}] No valid entities remain after filtering, returning empty results")
            record_keeper.record_processing(
                operation_type=f"{self.ENGINE_NAME.lower()}_detection",
                document_type="document",
                entity_types_processed=[],
                processing_time=time.time() - start_time,
                entity_count=0,
                success=False
            )
            # Return empty results.
            return [], {"pages": []}
        try:
            # Get the pages from the minimized data.
            pages = minimized_data.get("pages", [])
            # If no pages are found, return empty results.
            if not pages:
                return [], {"pages": []}
            # Prepare the page text and mappings along with the redaction mapping.
            page_texts_and_mappings, redaction_mapping = self._prepare_page_data(pages)
            # If there is no valid page text or mapping, return empty results.
            if not page_texts_and_mappings:
                return [], {"pages": []}
            # Process pages asynchronously.
            page_results = await self._process_pages_async(pages, page_texts_and_mappings, validated_entities)
            # Initialize an empty list to collect combined results.
            combined_results = []
            # Iterate over the results for each page.
            for local_page_number, (local_page_redaction_info, local_processed_entities) in page_results:
                # If redaction information exists, append it.
                if local_page_redaction_info:
                    redaction_mapping["pages"].append(local_page_redaction_info)
                # If processed entities exist, extend the combined results list.
                if local_processed_entities:
                    combined_results.extend(local_processed_entities)
            # Sort the redaction mapping pages by page number.
            redaction_mapping["pages"].sort(key=lambda x: x.get("page", 0))
            # Calculate the total processing time.
            total_time = time.time() - start_time
            # Record the successful processing.
            record_keeper.record_processing(
                operation_type=f"{self.ENGINE_NAME.lower()}_detection",
                document_type="document",
                entity_types_processed=validated_entities,
                processing_time=total_time,
                entity_count=len(combined_results),
                success=True
            )
            # Log the sensitive operation details.
            log_sensitive_operation(f"{self.ENGINE_NAME} Detection", len(combined_results), total_time,
                                    pages=len(pages))
            # Return the combined results and redaction mapping.
            return combined_results, redaction_mapping
        except Exception as exc:
            # Calculate the error processing time.
            error_time = time.time() - start_time
            # Record the processing error.
            record_keeper.record_processing(
                operation_type=f"{self.ENGINE_NAME.lower()}_detection",
                document_type="document",
                entity_types_processed=validated_entities,
                processing_time=error_time,
                entity_count=0,
                success=False
            )
            # Log the processing error using the error handler.
            SecurityAwareErrorHandler.log_processing_error(exc, f"{self.ENGINE_NAME.lower()}_detection", "")
            # Return empty results on error.
            return [], {"pages": []}

    async def _process_pages_async(self,
                                   pages: List[Dict[str, Any]],
                                   page_texts_and_mappings: Dict[int, Tuple[str, List]],
                                   requested_entities: List[str]
                                   ) -> List[Tuple[int, Tuple[Dict[str, Any], List[Dict[str, Any]]]]]:
        """
        Process pages concurrently using the engine's model in an asynchronous manner.

        Args:
            pages: List of dictionaries representing individual pages.
            page_texts_and_mappings: Dictionary mapping page numbers to a tuple of full text and mappings.
            requested_entities: List of requested entity types.

        Returns:
            A list of tuples where each tuple contains a page number and a tuple with redaction info and processed entities.
        """

        async def process_page_async(local_page_data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
            # Attempt processing a single page asynchronously with a timeout.
            try:
                return await asyncio.wait_for(
                    self._process_single_page_async(local_page_data, page_texts_and_mappings, requested_entities),
                    timeout=600.0
                )
            # Handle a timeout error specifically.
            except asyncio.TimeoutError:
                local_page_number = local_page_data.get("page", 0)
                log_warning(f"[WARNING] Timeout processing page {local_page_number} with {self.ENGINE_NAME}")
                return {"page": local_page_number, "sensitive": []}, []
            # Handle any other exceptions during page processing.
            except Exception as page_exc:
                SecurityAwareErrorHandler.log_processing_error(page_exc,
                                                               f"{self.ENGINE_NAME.lower()}_page_processing",
                                                               f"page_{local_page_data.get('page', 'unknown')}")
                return {"page": local_page_data.get("page"), "sensitive": []}, []

        # Process pages in parallel using the provided ParallelProcessingCore.
        return await ParallelProcessingCore.process_pages_in_parallel(pages, process_page_async)

    async def _process_single_page_async(self,
                                         local_page_data: Dict[str, Any],
                                         page_texts_and_mappings: Dict[int, Tuple[str, List]],
                                         requested_entities: List[str]
                                         ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Process a single page asynchronously to detect entities.

        Args:
            local_page_data: Dictionary containing page details.
            page_texts_and_mappings: Mapping of page numbers to full text and word mappings.
            requested_entities: List of entity types to detect.

        Returns:
            A tuple containing:
              - A dictionary with redaction information.
              - A list of processed entity dictionaries.
        """
        # Record the start time for processing the single page.
        page_start_time = time.time()
        # Retrieve the page number.
        local_page_number = local_page_data.get("page")
        # Retrieve the list of words from the page.
        local_words = local_page_data.get("words", [])
        # If there are no words, return empty redaction info and an empty entity list.
        if not local_words:
            return {"page": local_page_number, "sensitive": []}, []
        # Get the full text and mapping for the current page.
        full_text, mapping = page_texts_and_mappings.get(local_page_number, ("", []))
        # If full text or mapping is empty, return empty results.
        if not full_text or not mapping:
            return {"page": local_page_number, "sensitive": []}, []
        # Log that text processing will start on the current page.
        log_info(f"[OK] Processing text with {self.ENGINE_NAME} on page {local_page_number}")
        # If the model is not loaded, log a warning and skip this page.
        if not self.model:
            log_warning(f"[WARNING] {self.ENGINE_NAME} model not available, skipping page {local_page_number}")
            return {"page": local_page_number, "sensitive": []}, []
        # Process the text using the model in a separate thread.
        page_entities = await asyncio.to_thread(self._process_text, full_text, requested_entities)
        # If no entities are detected, log the event and return empty results.
        if not page_entities:
            log_info(f"[OK] No entities detected by {self.ENGINE_NAME} on page {local_page_number}")
            return {"page": local_page_number, "sensitive": []}, []
        # Count the number of detected entities.
        entity_count = len(page_entities)
        # Log the number of entities found.
        log_info(f"[OK] Found {entity_count} entities on page {local_page_number}")
        # Process entities concurrently.
        processed_entities, local_page_redaction_info = await ParallelProcessingCore.process_entities_in_parallel(
            self, full_text, mapping, page_entities, local_page_number)
        # Calculate the time taken for processing the page.
        page_time = time.time() - page_start_time
        # Record processing metrics for this page.
        record_keeper.record_processing(
            operation_type=f"{self.ENGINE_NAME.lower()}_page_processing",
            document_type=f"page_{local_page_number}",
            entity_types_processed=requested_entities,
            processing_time=page_time,
            entity_count=len(processed_entities),
            success=True)
        # Log the sensitive operation details for the page.
        log_sensitive_operation(f"{self.ENGINE_NAME} Page Detection", len(processed_entities), page_time,
                                page_number=local_page_number)
        # Return the redaction information and processed entities.
        return local_page_redaction_info, processed_entities

    @staticmethod
    def _prepare_page_data(pages: List[Dict[str, Any]]) -> Tuple[Dict[int, Tuple[str, List]], Dict[str, Any]]:
        """
        Prepare page data by extracting full text and mapping information.

        Args:
            pages: List of page dictionaries each containing word data.

        Returns:
            A tuple containing:
              - A dictionary mapping each page number to a tuple of (full_text, mapping).
              - A redaction mapping dictionary initialized with an empty "pages" list.
        """
        # Initialize an empty dictionary to store page texts and their mappings.
        page_texts_and_mappings = {}
        # Initialize the redaction mapping with an empty list for pages.
        redaction_mapping = {"pages": []}
        # Iterate over each page in the pages list.
        for page in pages:
            # Get the words from the page.
            words = page.get("words", [])
            # Get the page number.
            local_page_number = page.get("page")
            # If there are no words, add an empty redaction info entry for this page.
            if not words:
                redaction_mapping["pages"].append({"page": local_page_number, "sensitive": []})
                continue
            # Check if at least one word has non-empty text.
            has_content = any(w.get("text", "").strip() for w in words)
            # If the page has no content, log and add empty redaction info.
            if not has_content:
                log_info(f"[OK] Skipping empty page {local_page_number}")
                redaction_mapping["pages"].append({"page": local_page_number, "sensitive": []})
                continue
            try:
                # Reconstruct full text and mapping using the TextUtils helper.
                full_text, mapping = TextUtils.reconstruct_text_and_mapping(words)
                # Save the reconstructed text and mapping keyed by the page number.
                page_texts_and_mappings[local_page_number] = (full_text, mapping)
            except Exception as exc:
                # Log any error encountered during text reconstruction.
                SecurityAwareErrorHandler.log_processing_error(exc, "prepare_page_data", f"page_{local_page_number}")
        # Return the page texts and mappings along with the redaction mapping.
        return page_texts_and_mappings, redaction_mapping

    def _process_text(self, text: str, requested_entities: List[str]) -> List[Dict[str, Any]]:
        """
        Process text using the model to extract entities with error handling and caching.

        The method first checks the cache; if the result is not cached, it splits the text into paragraphs,
        processes them in batches, deduplicates, filters using Norwegian pronoun rules, and caches the result.

        Args:
            text: The full text string to be processed.
            requested_entities: List of entity types to detect.

        Returns:
            A list of dictionaries representing detected entities.
        """
        # Generate a unique cache key for this text and requested entities.
        key = GLiNERHelper.get_cache_key(text, requested_entities)
        # Attempt to retrieve cached results using the generated key.
        cached = GLiNERHelper.get_cached_result(key, cache_namespace=self.CACHE_NAMESPACE)
        # If cached results exist, log that caching is used.
        if cached is not None:
            log_info(f"✅ Using cached {self.ENGINE_NAME} result")
            return cached
        # Record the start time of text processing.
        start_time = time.time()
        # If text is empty or too short, return an empty list.
        if not text or len(text.strip()) < 3:
            return []
        # If the model is not loaded, log an error and handle the safe error.
        if not self.model:
            SecurityAwareErrorHandler.handle_safe_error(
                ValueError(f"{self.ENGINE_NAME} model not available"),
                f"detection_{self.ENGINE_NAME.lower()}_model_unavailable",
                "",
                default_return=[])
            return []
        # If the model is not initialized, log an error and handle it safely.
        if not self._is_initialized:
            SecurityAwareErrorHandler.handle_safe_error(
                ValueError(f"{self.ENGINE_NAME} model not properly initialized"),
                f"detection_{self.ENGINE_NAME.lower()}_model_not_initialized",
                "",
                default_return=[])
            return []
        # Split the text by newline to obtain paragraphs and filter non-empty ones.
        paragraphs = [p for p in text.split('\n') if p.strip()]
        # Initialize a list to collect all entity results.
        all_entities: List[Dict[str, Any]] = []
        # Define the batch size for processing paragraphs.
        batch_size = 5
        # Process paragraphs in batches.
        for i in range(0, len(paragraphs), batch_size):
            # Get a batch of paragraphs.
            batch_paragraphs = paragraphs[i:i + batch_size]
            # Process the batch and extract entities.
            batch_results = self._process_paragraph_batch(batch_paragraphs, text, requested_entities)
            # Extend the all_entities list with results from this batch.
            all_entities.extend(batch_results)
        # Deduplicate the detected entities.
        deduplicated_entities = deduplicate_entities(all_entities)
        # Filter out any false positives that are Norwegian pronouns.
        filtered_entities = self._filter_norwegian_pronouns(deduplicated_entities)
        # Calculate the total processing time.
        processing_time = time.time() - start_time
        # Add the processing time to the total accumulated time.
        self.total_processing_time += processing_time
        # Cache the result for future reuse.
        GLiNERHelper.set_cached_result(key, filtered_entities, cache_namespace=self.CACHE_NAMESPACE)
        # Return the filtered list of entities.
        return filtered_entities

    def _process_paragraph_batch(self, paragraphs: List[str], full_text: str, requested_entities: List[str]) -> List[
        Dict[str, Any]]:
        """
        Process a batch of paragraphs by splitting into sentence groups and extracting entities.

        Each paragraph is processed by computing its offset in the full text, splitting into manageable chunks,
        and then extracting entities with adjusted offsets.

        Args:
            paragraphs: List of paragraph strings.
            full_text: The complete text from which the paragraphs are derived.
            requested_entities: List of entity types to detect.

        Returns:
            A list of dictionaries representing detected entities from the batch.
        """
        # Initialize a list to collect entities from all paragraphs.
        all_entities = []
        # Iterate over each paragraph in the batch.
        for paragraph in paragraphs:
            # If the paragraph is empty, skip it.
            if not paragraph.strip():
                continue
            # Find the starting offset of the paragraph in the full text.
            base_offset = full_text.find(paragraph)
            # If the paragraph is not found, continue to the next one.
            if base_offset == -1:
                continue
            # Split the paragraph into sentence groups with a max length of 800.
            sentence_groups = GLiNERHelper.split_into_sentence_groups(paragraph, 800)
            # Iterate over each group of sentences.
            for group_text in sentence_groups:
                # Find the group's offset within the paragraph.
                group_offset = paragraph.find(group_text)
                # If the group is not found, continue.
                if group_offset == -1:
                    continue
                # Calculate the absolute offset in the full text.
                absolute_offset = base_offset + group_offset
                # Extract entities from this group with the computed offset.
                group_entities = self._extract_entities_for_group(group_text, requested_entities, absolute_offset)
                # Add the extracted entities to the overall list.
                all_entities.extend(group_entities)
        # Return all entities extracted from the batch.
        return all_entities

    def _extract_entities_for_group(self, group_text: str, requested_entities: List[str], absolute_offset: int) -> List[
        Dict[str, Any]]:
        """
        Extract entities from a text group using the model's predict method with proper thread safety.

        Adjusts detected entity offsets based on the absolute position of the group in the full text.

        Args:
            group_text: The chunk of text to process.
            requested_entities: List of entity types.
            absolute_offset: The starting offset of the group within the full text.

        Returns:
            A list of dictionaries representing the entities extracted from the group.
        """
        # Initialize an empty list to collect entities.
        local_entities = []
        # Acquire the model analyzer lock to ensure thread safety.
        lock = self._get_model_analyzer_lock()
        # Try to acquire the lock with a timeout.
        if not lock.acquire(timeout=600.0):
            log_warning(f"[{self.ENGINE_NAME}] Timeout acquiring model analyzer lock")
            return local_entities
        try:
            # Log the start of processing the group text.
            log_info(
                f"[DEBUG] Processing group_text (length {len(group_text)}): for entity_types: {requested_entities}")
            # Use the model's predict_entities method to extract entities from the group.
            group_entities = self.model.predict_entities(group_text, requested_entities, threshold=0.40)
            # Iterate over each detected entity.
            for entity in group_entities:
                # Create a dictionary for the entity with adjusted offsets.
                entity_dict = {
                    "entity_type": entity.get("label", "UNKNOWN"),
                    "start": absolute_offset + entity.get("start", 0),
                    "end": absolute_offset + entity.get("end", 0),
                    "score": entity.get("score", 0.5),
                    "original_text": entity.get("text", "")
                }
                # Append the entity dictionary to the local_entities list.
                local_entities.append(entity_dict)
        except Exception as predict_error:
            # Log any error during entity prediction.
            log_error(
                f"[DEBUG] Error in predict_entities for group_text (length {len(group_text)}): Error: {predict_error}")
            # Log the error using the error handler.
            SecurityAwareErrorHandler.log_processing_error(predict_error,
                                                           f"{self.ENGINE_NAME.lower()}_predict_entities",
                                                           f"group_{hash(group_text) % 10000}")
        finally:
            # Release the analyzer lock.
            lock.release()
        # Return the list of entities extracted from the group.
        return local_entities

    def _filter_norwegian_pronouns(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Remove false positives that are likely to be mis-detected Norwegian pronouns.

        Iterates over detected entities, and for those identified as 'person' or related,
        filters out texts that consist solely of known Norwegian pronouns.

        Args:
            entities: List of dictionaries representing detected entities.

        Returns:
            A filtered list of entity dictionaries.
        """
        # Initialize an empty list to hold entities that pass filtering.
        filtered_entities = []
        # Iterate over each detected entity.
        for ent in entities:
            # Retrieve the entity type.
            etype = ent["entity_type"]
            # Check if the entity type indicates a person.
            if etype in {"person", "per", "PERSON-H"}:
                # Extract and trim the original text of the entity.
                text_val = ent.get("original_text", "").strip()
                # Split the text into individual words.
                text_words = text_val.split()
                # If the text is a single word, and it is a known pronoun, skip the entity.
                if len(text_words) == 1 and text_words[0].lower() in self.norwegian_pronouns:
                    log_info("[FILTER] Removed Norwegian pronoun incorrectly detected as person")
                    continue
                # If the text contains multiple words and all are pronouns, skip the entity.
                if len(text_words) > 1 and all(w.lower() in self.norwegian_pronouns for w in text_words):
                    log_info("[FILTER] Removed compound Norwegian pronoun incorrectly detected as person")
                    continue
            # If the entity passed the checks, add it to the filtered list.
            filtered_entities.append(ent)
        # Return the filtered entities.
        return filtered_entities

    def validate_requested_entities(self, requested_entities_json: str) -> List[str]:
        """
        Validate and parse the requested entities from a JSON string.

        By default, it uses the GLiNER validation method. Subclasses can override this method if needed.

        Args:
            requested_entities_json: A JSON string representing the requested entity types.

        Returns:
            A list of validated entity type strings.
        """
        # Use the GLiNER-specific validation helper to validate the JSON input.
        return validate_gliner_requested_entities(requested_entities_json)

    def get_status(self) -> Dict[str, Any]:
        """
        Retrieve the current status and performance metrics of the detector.

        Returns:
            A dictionary containing details about initialization status, timings, model information,
            file details, and processing performance.
        """
        # Return a dictionary with all the status fields.
        return {
            "initialized": self._is_initialized,
            "initialization_time": self._initialization_time,
            "initialization_time_readable": datetime.fromtimestamp(self._initialization_time).strftime(
                '%Y-%m-%d %H:%M:%S'),
            "last_used": self._last_used,
            "last_used_readable": datetime.fromtimestamp(self._last_used).strftime(
                '%Y-%m-%d %H:%M:%S') if self._last_used else "Never Used",
            "idle_time": time.time() - self._last_used if self._last_used else None,
            "idle_time_readable": f"{(time.time() - self._last_used):.2f} seconds" if self._last_used else "N/A",
            "total_calls": self._total_calls,
            "total_entities_detected": getattr(self, '_total_entities_detected', 0),
            "total_processing_time": self.total_processing_time,
            "average_processing_time": (
                self.total_processing_time / self._total_calls if self._total_calls > 0 else None),
            "model_available": self.model is not None,
            "model_name": self._model_name,
            f"{self.ENGINE_NAME.lower()}_package_available": ENGINE_LIB_AVAILABLE,
            "local_model_path": self._local_model_path,
            "local_files_only": self._local_files_only,
            "model_dir_path": self._model_dir_path,
            "model_directory_exists": os.path.isdir(self._model_dir_path) if self._model_dir_path else False,
            "model_files": os.listdir(self._model_dir_path) if self._model_dir_path and os.path.isdir(
                self._model_dir_path) else [],
            "config_files": {
                self.CONFIG_FILE_NAME: os.path.exists(
                    os.path.join(self._model_dir_path, self.CONFIG_FILE_NAME)) if self._model_dir_path else False
            },
            "global_initializing": self.__class__._global_initializing,
            "global_initialization_time": self.__class__._global_initialization_time
        }
