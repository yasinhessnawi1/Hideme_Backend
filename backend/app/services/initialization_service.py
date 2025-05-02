"""
Enhanced model initialization service with improved thread safety.
This service manages the initialization and caching of detection engines with improved synchronization using a basic lock
(consume/release) for concurrent access.

This module contains the InitializationService class that:
    - Provides lazy initialization of detectors at startup.
    - Uses both synchronous and asynchronous locks to ensure thread safety.
    - Manages detector caches with an LRU eviction policy.
    - Tracks usage metrics for performance monitoring.
    - Integrates error handling via SecurityAwareErrorHandler.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, List

from backend.app.configs.config_singleton import get_config
from backend.app.configs.gdpr_config import MAX_DETECTOR_CACHE_SIZE
from backend.app.configs.gliner_config import GLINER_MODEL_NAME, GLINER_AVAILABLE_ENTITIES, GLINER_MODEL_PATH
from backend.app.configs.hideme_config import HIDEME_MODEL_NAME, HIDEME_AVAILABLE_ENTITIES, HIDEME_MODEL_PATH
from backend.app.entity_detection import EntityDetectionEngine, GlinerEntityDetector
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.system_utils.memory_management import memory_monitor
from backend.app.utils.system_utils.synchronization_utils import TimeoutLock, LockPriority, AsyncTimeoutLock

# Configure logger for the module.
logger = logging.getLogger(__name__)


class InitializationService:
    """
    Service for initializing and caching ML models and detectors with improved thread safety.

    This class:
        - Initializes detectors lazily to avoid blocking application startup.
        - Manages caches for multiple detector types (Presidio, Gemini, GLiNER, HIDEME, Hybrid).
        - Utilizes locks (synchronous and asynchronous) for thread-safe operations.
        - Tracks usage metrics for detectors to support LRU cache eviction.
        - Implements error handling with SecurityAwareErrorHandler in each method.

    Attributes:
        max_cache_size (int): Maximum number of cached detectors.
        _lock (TimeoutLock): Synchronous lock for thread-safe cache operations.
        _async_lock (AsyncTimeoutLock): Asynchronous lock for async operations.
        _initialization_status (dict): Tracks initialization status for each detector type.
        _presidio_detector: Cached Presidio detector instance.
        _gemini_detector: Cached Gemini detector instance.
        _gliner_detectors (dict): Cache for GLiNER detectors keyed by entity configurations.
        _hideme_detectors (dict): Cache for HIDEME detectors keyed by entity configurations.
        _hybrid_detectors (dict): Cache for Hybrid detectors keyed by configuration.
        _usage_metrics (dict): Metrics for tracking usage of detectors.
    """

    def __init__(self, max_cache_size: int = None):
        """
        Initialize the service with detector caching and basic synchronization.

        Args:
            max_cache_size (int, optional): Maximum number of cached detectors.
                Uses configuration default if not provided.
        """
        # Set max cache size from provided argument or configuration default.
        self.max_cache_size = max_cache_size or get_config("max_detector_cache_size", MAX_DETECTOR_CACHE_SIZE)
        # Create a synchronous lock for protecting cache operations.
        self._lock = TimeoutLock("detector_cache_lock", priority=LockPriority.HIGH, timeout=15.0)
        # Create an asynchronous lock for async operations.
        self._async_lock = AsyncTimeoutLock("detector_async_lock", priority=LockPriority.HIGH, timeout=15.0)
        # Initialize the initialization status for each detector type.
        self._initialization_status: Dict[str, bool] = {
            "presidio": False,
            "gemini": False,
            "gliner": False,
            "hideme": False,
            "hybrid": False
        }
        # Initialize the Presidio detector cache.
        self._presidio_detector = None
        # Initialize the Gemini detector cache.
        self._gemini_detector = None
        # Initialize the GLiNER detectors cache.
        self._gliner_detectors: Dict[str, Any] = {}
        # Initialize the HIDEME detectors cache.
        self._hideme_detectors: Dict[str, Any] = {}
        # Initialize the Hybrid detectors cache.
        self._hybrid_detectors: Dict[str, Any] = {}
        # Initialize the usage metrics dictionary.
        self._usage_metrics: Dict[str, Any] = {
            "presidio": {"uses": 0, "last_used": None},
            "gemini": {"uses": 0, "last_used": None},
            "gliner": {},
            "hideme": {}
        }
        # Log the service startup with the set maximum cache size.
        log_info(f"Initialization service started with max cache size: {self.max_cache_size}")

    async def initialize_detectors_lazy(self):
        """
        Lazily initialize detectors at application startup without blocking other services.
        This method initializes Presidio, Gemini, GLiNER, and HIDEME detectors in the background.
        """
        # Log the beginning of lazy initialization.
        log_info("[STARTUP] Starting lazy initialization of detectors...")
        try:
            # Call lazy initialization for the Presidio detector.
            await self._lazy_init_presidio()
            # Pause execution briefly.
            await asyncio.sleep(1.0)
            # Call lazy initialization for the Gemini detector.
            await self._lazy_init_gemini()
            # Optionally initialize GLiNER detector if conditions are met.
            await self._maybe_lazy_init_gliner()
            # Optionally initialize HIDEME detector if conditions are met.
            await self._maybe_lazy_init_hideme()
            # Log successful completion of lazy initialization.
            log_info("[STARTUP] Lazy initialization of detectors completed successfully.")
        except Exception as exc:
            # Handle any processing error that occurs during lazy initialization.
            SecurityAwareErrorHandler().log_processing_error(exc, "initialize_detectors_lazy")
            # Log the exception message.
            log_error(f"[STARTUP] Error during detector lazy initialization: {str(exc)}")

    async def _lazy_init_presidio(self):
        """
        Background-thread initialization for the Presidio detector.
        """
        # Log the start of Presidio detector lazy initialization.
        log_info("[STARTUP] Lazily initializing Presidio detector...")
        try:
            # Run the Presidio initialization in a background thread.
            presidio_detector = await asyncio.to_thread(self._initialize_presidio_detector)
            # Store the resulting Presidio detector.
            self._presidio_detector = presidio_detector
            # Mark the Presidio detector as initialized.
            self._initialization_status["presidio"] = True
            # Log successful Presidio detector lazy initialization.
            log_info("[STARTUP] Presidio detector lazy initialization complete.")
        except Exception as exc:
            # Log any processing errors that occur.
            SecurityAwareErrorHandler().log_processing_error(exc, "_lazy_init_presidio")
            # Log the error message.
            log_error(f"[STARTUP] Error during Presidio lazy initialization: {str(exc)}")

    async def _lazy_init_gemini(self):
        """
        Background-thread initialization for the Gemini detector.
        """
        # Log the start of Gemini detector lazy initialization.
        log_info("[STARTUP] Lazily initializing Gemini detector...")
        try:
            # Run the Gemini initialization in a background thread.
            gemini_detector = await asyncio.to_thread(self._initialize_gemini_detector)
            # Store the resulting Gemini detector.
            self._gemini_detector = gemini_detector
            # Mark the Gemini detector as initialized.
            self._initialization_status["gemini"] = True
            # Log successful Gemini detector lazy initialization.
            log_info("[STARTUP] Gemini detector lazy initialization complete.")
        except Exception as exc:
            # Log any processing errors that occur.
            SecurityAwareErrorHandler().log_processing_error(exc, "_lazy_init_gemini")
            # Log the error message.
            log_error(f"[STARTUP] Error during Gemini lazy initialization: {str(exc)}")

    async def _maybe_lazy_init_gliner(self):
        """
        Conditionally initialize the GLiNER detector if memory usage is below a threshold.
        """
        # Check if current memory usage is below the threshold value.
        if memory_monitor.get_memory_usage() < 60.0:
            # Log that GLiNER detector lazy initialization will proceed.
            log_info("[STARTUP] Lazily initializing GLiNER detector...")
            try:
                # Run the GLiNER initialization in a background thread.
                gliner_detector = await asyncio.to_thread(
                    self._initialize_gliner_detector,
                    GLINER_MODEL_NAME,
                    GLINER_AVAILABLE_ENTITIES
                )
                # Generate a cache key based on available entities.
                cache_key = self._get_gliner_cache_key(GLINER_AVAILABLE_ENTITIES)
                # Store the GLiNER detector in the cache using the generated key.
                self._gliner_detectors[cache_key] = gliner_detector
                # Mark the GLiNER detector as initialized.
                self._initialization_status["gliner"] = True
                # Log successful GLiNER detector lazy initialization.
                log_info("[STARTUP] GLiNER detector lazy initialization complete.")
            except Exception as exc:
                # Log any processing errors that occur.
                SecurityAwareErrorHandler().log_processing_error(exc, "_maybe_lazy_init_gliner")
                # Log the error message.
                log_error(f"[STARTUP] Error during GLiNER lazy initialization: {str(exc)}")
        else:
            # Log that the GLiNER initialization is skipped due to memory pressure.
            log_info("[STARTUP] Skipping GLiNER lazy initialization due to memory pressure.")

    async def _maybe_lazy_init_hideme(self):
        """
        Conditionally initialize the HIDEME detector if memory usage is below a threshold.
        HIDEME is handled identically to GLiNER.
        """
        # Check if current memory usage is below the threshold value.
        if memory_monitor.get_memory_usage() < 60.0:
            # Log that HIDEME detector lazy initialization will proceed.
            log_info("[STARTUP] Lazily initializing HIDEME detector...")
            try:
                # Run the HIDEME initialization in a background thread.
                hideme_detector = await asyncio.to_thread(
                    self._initialize_hideme_detector,
                    HIDEME_MODEL_NAME,
                    HIDEME_AVAILABLE_ENTITIES
                )
                # Generate a cache key based on HIDEME's available entities.
                cache_key = self._get_hideme_cache_key(HIDEME_AVAILABLE_ENTITIES)
                # Store the HIDEME detector in the cache using the generated key.
                self._hideme_detectors[cache_key] = hideme_detector
                # Mark the HIDEME detector as initialized.
                self._initialization_status["hideme"] = True
                # Log successful HIDEME detector lazy initialization.
                log_info("[STARTUP] HIDEME detector lazy initialization complete.")
            except Exception as exc:
                # Log any processing errors that occur.
                SecurityAwareErrorHandler().log_processing_error(exc, "_maybe_lazy_init_hideme")
                # Log the error message.
                log_error(f"[STARTUP] Error during HIDEME lazy initialization: {str(exc)}")
        else:
            # Log that the HIDEME initialization is skipped due to memory pressure.
            log_info("[STARTUP] Skipping HIDEME lazy initialization due to memory pressure.")

    def _initialize_presidio_detector(self):
        """
        Initialize a Presidio detector instance with error handling.

        Returns:
            An instance of the Presidio detector.
        """
        # Log the beginning of Presidio detector initialization.
        log_info("Initializing Presidio detector")
        # Record the start time for performance measurement.
        start_time = time.time()
        try:
            # Import the Presidio detector from its module.
            from backend.app.entity_detection.presidio import PresidioEntityDetector
            # Instantiate the Presidio detector.
            detector = PresidioEntityDetector()
            # Mark the Presidio detector as successfully initialized.
            self._initialization_status["presidio"] = True
            # Log the time taken to initialize the Presidio detector.
            log_info(f"Presidio detector initialized in {time.time() - start_time:.2f}s")
            # Return the initialized detector.
            return detector
        except Exception as exc:
            # Mark the Presidio detector as not initialized.
            self._initialization_status["presidio"] = False
            # Log the processing error.
            SecurityAwareErrorHandler().log_processing_error(exc, "_initialize_presidio_detector")
            # Log the error message.
            log_error(f"Error initializing Presidio detector: {str(exc)}")
            # Propagate the exception.
            raise

    def _initialize_gemini_detector(self):
        """
        Initialize a Gemini detector instance with error handling.

        Returns:
            An instance of the Gemini detector.
        """
        # Log the beginning of Gemini detector initialization.
        log_info("Initializing Gemini detector")
        # Record the start time for performance measurement.
        start_time = time.time()
        try:
            # Import the Gemini detector from its module.
            from backend.app.entity_detection.gemini import GeminiEntityDetector
            # Instantiate the Gemini detector.
            detector = GeminiEntityDetector()
            # Mark the Gemini detector as successfully initialized.
            self._initialization_status["gemini"] = True
            # Log the time taken to initialize the Gemini detector.
            log_info(f"Gemini detector initialized in {time.time() - start_time:.2f}s")
            # Return the initialized detector.
            return detector
        except Exception as exc:
            # Mark the Gemini detector as not initialized.
            self._initialization_status["gemini"] = False
            # Log the processing error.
            SecurityAwareErrorHandler().log_processing_error(exc, "_initialize_gemini_detector")
            # Log the error message.
            log_error(f"Error initializing Gemini detector: {str(exc)}")
            # Propagate the exception.
            raise

    def _initialize_gliner_detector(self, model_name: str, entities: List[str]):
        """
        Initialize a GLiNER detector instance with error handling.

        Args:
            model_name (str): Name of the GLiNER model.
            entities (List[str]): List of entity types to detect.

        Returns:
            An instance of the GLiNER detector.
        """
        # Log the beginning of GLiNER detector initialization with the provided model and entities.
        log_info(f"Initializing GLiNER detector with model {model_name}")
        # Record the start time for performance measurement.
        start_time = time.time()
        try:
            # Instantiate the GLiNER detector using the provided arguments.
            detector = GlinerEntityDetector(
                model_name=model_name,
                entities=entities or GLINER_AVAILABLE_ENTITIES,
                local_model_path=GLINER_MODEL_PATH
            )
            # Mark the GLiNER detector as successfully initialized.
            self._initialization_status["gliner"] = True
            # Log the time taken to initialize the GLiNER detector.
            log_info(f"GLiNER detector initialized in {time.time() - start_time:.2f}s")
            # Return the initialized detector.
            return detector
        except Exception as exc:
            # Mark the GLiNER detector as not initialized.
            self._initialization_status["gliner"] = False
            # Log the processing error.
            SecurityAwareErrorHandler().log_processing_error(exc, "_initialize_gliner_detector")
            # Log the error message.
            log_error(f"Error initializing GLiNER detector: {str(exc)}")
            # Propagate the exception.
            raise

    def _initialize_hideme_detector(self, model_name: str, entities: List[str]):
        """
        Initialize a HIDEME detector instance with error handling.

        Args:
            model_name (str): Name of the HIDEME model.
            entities (List[str]): List of entity types to detect.

        Returns:
            An instance of the HIDEME detector.
        """
        # Log the beginning of HIDEME detector initialization with the provided model.
        log_info(f"Initializing HIDEME detector with model {model_name}")
        # Record the start time for performance measurement.
        start_time = time.time()
        try:
            # Import the HIDEME detector from its module.
            from backend.app.entity_detection.hideme import HidemeEntityDetector
            # Instantiate the HIDEME detector.
            detector = HidemeEntityDetector(
                model_name=HIDEME_MODEL_NAME,
                entities=entities or HIDEME_AVAILABLE_ENTITIES,
                local_model_path=HIDEME_MODEL_PATH
            )
            # Mark the HIDEME detector as successfully initialized.
            self._initialization_status["hideme"] = True
            # Log the time taken to initialize the HIDEME detector.
            log_info(f"HIDEME detector initialized in {time.time() - start_time:.2f}s")
            # Return the initialized detector.
            return detector
        except Exception as exc:
            # Mark the HIDEME detector as not initialized.
            self._initialization_status["hideme"] = False
            # Log the processing error.
            SecurityAwareErrorHandler().log_processing_error(exc, "_initialize_hideme_detector")
            # Log the error message.
            log_error(f"Error initializing HIDEME detector: {str(exc)}")
            # Propagate the exception.
            raise

    def _initialize_hybrid_detector(self, config: Dict[str, Any]):
        """
        Initialize a Hybrid detector instance with error handling.

        Args:
            config (Dict[str, Any]): Configuration for the hybrid detector.

        Returns:
            An instance of the Hybrid detector.
        """
        # Log the beginning of Hybrid detector initialization.
        log_info("Initializing Hybrid detector")
        # Record the start time for performance measurement.
        start_time = time.time()
        try:
            # Import the Hybrid detector from its module.
            from backend.app.entity_detection.hybrid import HybridEntityDetector
            # Instantiate the Hybrid detector.
            detector = HybridEntityDetector(config)
            # Mark the Hybrid detector as successfully initialized.
            self._initialization_status["hybrid"] = True
            # Log the time taken to initialize the Hybrid detector.
            log_info(f"Hybrid detector initialized in {time.time() - start_time:.2f}s")
            # Return the initialized detector.
            return detector
        except Exception as exc:
            # Mark the Hybrid detector as not initialized.
            self._initialization_status["hybrid"] = False
            # Log the processing error.
            SecurityAwareErrorHandler().log_processing_error(exc, "_initialize_hybrid_detector")
            # Log the error message.
            log_error(f"Error initializing Hybrid detector: {str(exc)}")
            # Propagate the exception.
            raise

    async def shutdown_async(self) -> None:
        """
        Perform asynchronous shutdown tasks for the initialization service.

        This method checks if any detector instance provides an asynchronous shutdown routine
        and awaits the shutdown. Any exceptions during shutdown are caught and logged.
        """
        try:
            # If the Presidio detector supports asynchronous shutdown, call its shutdown.
            if self._presidio_detector and hasattr(self._presidio_detector, "shutdown_async"):
                await self._presidio_detector.shutdown_async()
            # If the Gemini detector supports asynchronous shutdown, call its shutdown.
            if self._gemini_detector and hasattr(self._gemini_detector, "shutdown_async"):
                await self._gemini_detector.shutdown_async()
            # Loop over GLiNER detectors and call asynchronous shutdown if supported.
            for detector in self._gliner_detectors.values():
                if hasattr(detector, "shutdown_async"):
                    await detector.shutdown_async()
            # Loop over HIDEME detectors and call asynchronous shutdown if supported.
            for detector in self._hideme_detectors.values():
                if hasattr(detector, "shutdown_async"):
                    await detector.shutdown_async()
            # Loop over Hybrid detectors and call asynchronous shutdown if supported.
            for detector in self._hybrid_detectors.values():
                if hasattr(detector, "shutdown_async"):
                    await detector.shutdown_async()
        except Exception as exc:
            # Log any processing error during shutdown.
            SecurityAwareErrorHandler().log_processing_error(exc, "shutdown_async")
            # Log the error message.
            log_error(f"Error during asynchronous shutdown: {exc}")

    def get_presidio_detector(self):
        """
        Retrieve a Presidio detector instance with basic thread safety.

        Returns:
            The Presidio detector instance.
        """
        # Delegate to the generic get_detector method specifying the PRESIDIO engine.
        return self.get_detector(EntityDetectionEngine.PRESIDIO)

    def get_gemini_detector(self):
        """
        Retrieve a Gemini detector instance with basic thread safety.

        Returns:
            The Gemini detector instance.
        """
        # Delegate to the generic get_detector method specifying the GEMINI engine.
        return self.get_detector(EntityDetectionEngine.GEMINI)

    def get_gliner_detector(self, entities: Optional[List[str]] = None):
        """
        Retrieve a GLiNER detector instance for specific entities with basic thread safety.

        Args:
            entities (List[str], optional): List of entity types to detect.
                Defaults to GLINER_AVAILABLE_ENTITIES if not provided.

        Returns:
            The GLiNER detector instance.
        """
        # Build configuration using the provided entities or the default.
        config = {"entities": entities or GLINER_AVAILABLE_ENTITIES}
        # Delegate to the generic get_detector method for the GLINER engine.
        return self.get_detector(EntityDetectionEngine.GLINER, config)

    def get_hideme_detector(self, entities: Optional[List[str]] = None):
        """
        Retrieve a HIDEME detector instance for specific entities with basic thread safety.

        Args:
            entities (List[str], optional): List of entity types to detect.
                Defaults to HIDEME_AVAILABLE_ENTITIES if not provided.

        Returns:
            The HIDEME detector instance.
        """
        # Build configuration using the provided entities or the default.
        config = {"entities": entities or HIDEME_AVAILABLE_ENTITIES}
        # Delegate to the generic get_detector method for the HIDEME engine.
        return self.get_detector(EntityDetectionEngine.HIDEME, config)

    def get_hybrid_detector(self, config: Dict[str, Any]):
        """
        Retrieve a hybrid detector instance with basic thread safety.

        Args:
            config (Dict[str, Any]): Configuration for the hybrid detector.

        Returns:
            The hybrid detector instance.
        """
        # Delegate to the generic get_detector method for the HYBRID engine.
        return self.get_detector(EntityDetectionEngine.HYBRID, config)

    def get_detector(self, engine: EntityDetectionEngine, config: Optional[Dict[str, Any]] = None):
        """
        Retrieve a detector instance for the specified engine using lock management.
        Performs a quick cache check and initializes the detector if necessary.

        Args:
            engine (EntityDetectionEngine): The detection engine type.
            config (Dict[str, Any], optional): Detector configuration.

        Returns:
            The detector instance.
        """
        # Set default configuration if none provided.
        if config is None:
            config = {}
        # Step 1: Perform a quick cache check.
        maybe_cached = self._quick_check_cache(engine, config)
        if maybe_cached is not None:
            # Return the cached detector if found.
            return maybe_cached
        # Step 2: Try to acquire a short-duration lock for a recheck.
        if self._try_acquire_lock(0.5):
            try:
                # Recheck the cache after acquiring the lock.
                rechecked = self._quick_check_cache(engine, config)
                if rechecked is not None:
                    # Return the rechecked detector if available.
                    return rechecked
            finally:
                # Release the short-duration lock.
                self._lock.release()
        else:
            # Log a warning if the short-duration lock could not be acquired.
            log_warning("[WARNING] Timeout acquiring lock for quick cache check")
        # Step 3: Try to acquire a longer lock to initialize or retrieve the detector.
        if self._try_acquire_lock(1.0):
            try:
                # Check the cache again under the longer lock.
                final_cached = self._quick_check_cache(engine, config)
                if final_cached is not None:
                    # Return the detector if found.
                    return final_cached
                # Initialize and store the detector under lock.
                return self._initialize_and_store_detector(engine, config)
            finally:
                # Release the long-duration lock.
                self._lock.release()
        else:
            # Log a warning if the long-duration lock could not be acquired.
            log_warning("[WARNING] Timeout acquiring lock for detector initialization")
        # Step 4: Fallback initialization if locks cannot be acquired.
        return self._fallback_init(engine, config)

    def _quick_check_cache(self, engine: EntityDetectionEngine, config: Dict[str, Any]) -> Optional[Any]:
        """
        Quickly check if a detector instance is cached.
        If found, update its usage metrics.

        Args:
            engine (EntityDetectionEngine): The detection engine type.
            config (Dict[str, Any]): Detector configuration.

        Returns:
            The cached detector instance if available; otherwise, None.
        """
        # Check cache for Presidio detector.
        if engine == EntityDetectionEngine.PRESIDIO and self._presidio_detector:
            self._update_usage_metrics_no_lock("presidio")
            return self._presidio_detector
        # Check cache for Gemini detector.
        if engine == EntityDetectionEngine.GEMINI and self._gemini_detector:
            self._update_usage_metrics_no_lock("gemini")
            return self._gemini_detector
        # Check cache for GLiNER detector.
        if engine == EntityDetectionEngine.GLINER:
            key = self._get_gliner_cache_key(config.get("entities", []))
            if key in self._gliner_detectors:
                self._update_usage_metrics_no_lock(f"gliner_{key}")
                return self._gliner_detectors[key]
        # Check cache for HIDEME detector.
        if engine == EntityDetectionEngine.HIDEME:
            key = self._get_hideme_cache_key(config.get("entities", []))
            if key in self._hideme_detectors:
                self._update_usage_metrics_no_lock(f"hideme_{key}")
                return self._hideme_detectors[key]
        # Check cache for Hybrid detector.
        if engine == EntityDetectionEngine.HYBRID:
            key = self._get_hybrid_cache_key(config)
            if key in self._hybrid_detectors:
                return self._hybrid_detectors[key]
        # Return None if detector is not found in cache.
        return None

    def _try_acquire_lock(self, timeout: float) -> bool:
        """
        Attempt to acquire the main lock within the given timeout.

        Args:
            timeout (float): Timeout in seconds.

        Returns:
            True if the lock was acquired; otherwise, False.
        """
        try:
            # Try to acquire the lock within the specified timeout.
            return self._lock.acquire(timeout=timeout)
        except TimeoutError:
            # Return False if lock acquisition times out.
            return False

    def _initialize_and_store_detector(self, engine: EntityDetectionEngine, config: Dict[str, Any]) -> Any:
        """
        Under lock, initialize the requested detector and store it in the cache.

        Args:
            engine (EntityDetectionEngine): The detection engine type.
            config (Dict[str, Any]): Detector configuration.

        Returns:
            The initialized detector instance.
        """
        # For Presidio or Gemini, delegate to the respective initialization routine.
        if engine in (EntityDetectionEngine.PRESIDIO, EntityDetectionEngine.GEMINI):
            return self._initialize_presidio_or_gemini(engine)
        # For GLiNER, initialize and store the detector.
        elif engine == EntityDetectionEngine.GLINER:
            return self._initialize_gliner(config)
        # For HIDEME, initialize and store the detector.
        elif engine == EntityDetectionEngine.HIDEME:
            return self._initialize_hideme(config)
        # For Hybrid, initialize and store the detector.
        elif engine == EntityDetectionEngine.HYBRID:
            return self._initialize_hybrid(config)
        else:
            # Raise an error for unsupported detection engine types.
            raise ValueError(f"Unsupported detection engine: {engine}")

    def _initialize_presidio_or_gemini(self, engine: EntityDetectionEngine) -> Any:
        """
        Initialize a Presidio or Gemini detector, update cache and usage metrics.

        Args:
            engine (EntityDetectionEngine): The detection engine type.

        Returns:
            The detector instance.
        """
        # For the PRESIDIO engine:
        if engine == EntityDetectionEngine.PRESIDIO:
            # If the Presidio detector is already cached, update and return it.
            if self._presidio_detector:
                self._update_usage_metrics_no_lock("presidio")
                return self._presidio_detector
            # Otherwise, initialize a new Presidio detector.
            new_det = self._initialize_presidio_detector()
            # Cache the newly initialized detector.
            self._presidio_detector = new_det
            # Update usage metrics.
            self._update_usage_metrics_no_lock("presidio")
            # Return the new detector.
            return new_det
        else:
            # For the GEMINI engine:
            if self._gemini_detector:
                self._update_usage_metrics_no_lock("gemini")
                return self._gemini_detector
            new_det = self._initialize_gemini_detector()
            self._gemini_detector = new_det
            self._update_usage_metrics_no_lock("gemini")
            return new_det

    def _initialize_gliner(self, config: Dict[str, Any]) -> Any:
        """
        Initialize a GLiNER detector and store it in cache, updating usage metrics.

        Args:
            config (Dict[str, Any]): Configuration parameters for GLiNER.

        Returns:
            The GLiNER detector instance.
        """
        # Extract the entities list from the configuration.
        entities = config.get("entities", [])
        # Generate a cache key based on the entities.
        key = self._get_gliner_cache_key(entities)
        # If the detector is already cached, update metrics and return it.
        if key in self._gliner_detectors:
            self._update_usage_metrics_no_lock(f"gliner_{key}")
            return self._gliner_detectors[key]
        # Get the model name from the configuration or use the default.
        model_name = config.get("model_name", GLINER_MODEL_NAME)
        # Initialize a new GLiNER detector.
        new_det = self._initialize_gliner_detector(model_name, entities)
        # Evict the least recently used detector if cache size exceeded.
        if len(self._gliner_detectors) >= self.max_cache_size:
            self._evict_least_recently_used("gliner")
        # Store the new detector in the cache.
        self._gliner_detectors[key] = new_det
        # Update the usage metrics.
        self._update_usage_metrics_no_lock(f"gliner_{key}")
        # Return the new detector.
        return new_det

    def _initialize_hideme(self, config: Dict[str, Any]) -> Any:
        """
        Initialize a HIDEME detector and store it in cache, updating usage metrics.
        HIDEME is handled similarly to GLiNER.

        Args:
            config (Dict[str, Any]): Configuration parameters for HIDEME.

        Returns:
            The HIDEME detector instance.
        """
        # Extract the entities list from the configuration.
        entities = config.get("entities", [])
        # Generate a cache key based on the entities.
        key = self._get_hideme_cache_key(entities)
        # If the detector is already cached, update metrics and return it.
        if key in self._hideme_detectors:
            self._update_usage_metrics_no_lock(f"hideme_{key}")
            return self._hideme_detectors[key]
        # Get the model name from the configuration or use the default.
        model_name = config.get("model_name", HIDEME_MODEL_NAME)
        # Initialize a new HIDEME detector.
        new_det = self._initialize_hideme_detector(model_name, entities)
        # Evict the least recently used detector if cache size exceeded.
        if len(self._hideme_detectors) >= self.max_cache_size:
            self._evict_least_recently_used("hideme")
        # Store the new detector in the cache.
        self._hideme_detectors[key] = new_det
        # Update the usage metrics.
        self._update_usage_metrics_no_lock(f"hideme_{key}")
        # Return the new detector.
        return new_det

    def _initialize_hybrid(self, config: Dict[str, Any]) -> Any:
        """
        Initialize a Hybrid detector and update cache.

        Args:
            config (Dict[str, Any]): Configuration for Hybrid.

        Returns:
            The Hybrid detector instance.
        """
        # Generate a cache key based on the hybrid configuration.
        key = self._get_hybrid_cache_key(config)
        # Return the detector if it is already cached.
        if key in self._hybrid_detectors:
            return self._hybrid_detectors[key]
        # Initialize a new Hybrid detector.
        new_det = self._initialize_hybrid_detector(config)
        # Evict the least recently used detector if cache size exceeded.
        if len(self._hybrid_detectors) >= self.max_cache_size:
            self._evict_least_recently_used("hybrid")
        # Store the new detector in the cache.
        self._hybrid_detectors[key] = new_det
        # Return the new detector.
        return new_det

    def _fallback_init(self, engine: EntityDetectionEngine, config: Dict[str, Any]) -> Any:
        """
        Fallback initialization if lock acquisition fails; directly initialize detector without locking.

        Args:
            engine (EntityDetectionEngine): The detection engine type.
            config (Dict[str, Any]): Configuration parameters.

        Returns:
            The initialized detector instance.
        """
        # Log a warning that a fallback initialization is being used.
        log_warning("Timeout acquiring detector lock - proceeding with fallback initialization")
        # For PRESIDIO, return the cached instance if available or initialize a new one.
        if engine == EntityDetectionEngine.PRESIDIO:
            if self._presidio_detector:
                return self._presidio_detector
            return self._initialize_presidio_detector()
        # For GEMINI, return the cached instance if available or initialize a new one.
        if engine == EntityDetectionEngine.GEMINI:
            if self._gemini_detector:
                return self._gemini_detector
            return self._initialize_gemini_detector()
        # For GLiNER, either return the cached detector or initialize a new one.
        if engine == EntityDetectionEngine.GLINER:
            key = self._get_gliner_cache_key(config.get("entities", []))
            if key in self._gliner_detectors:
                return self._gliner_detectors[key]
            model_name = config.get("model_name", GLINER_MODEL_NAME)
            return self._initialize_gliner_detector(model_name, config.get("entities", []))
        # For HIDEME, either return the cached detector or initialize a new one.
        if engine == EntityDetectionEngine.HIDEME:
            key = self._get_hideme_cache_key(config.get("entities", []))
            if key in self._hideme_detectors:
                return self._hideme_detectors[key]
            model_name = config.get("model_name", HIDEME_MODEL_NAME)
            return self._initialize_hideme_detector(model_name, config.get("entities", []))
        # For HYBRID, either return the cached detector or initialize a new one.
        if engine == EntityDetectionEngine.HYBRID:
            key = self._get_hybrid_cache_key(config)
            if key in self._hybrid_detectors:
                return self._hybrid_detectors[key]
            return self._initialize_hybrid_detector(config)
        # Raise an error if the engine type is unsupported.
        raise ValueError(f"Unsupported detection engine: {engine}")

    def _increment_usage_metrics(self, detector_key: str, current_time: float):
        """
        Increment usage metrics for a given detector.

        Args:
            detector_key (str): Key identifying the detector.
            current_time (float): Current timestamp.
        """
        # For GLiNER or HIDEME, update the category usage metrics.
        if detector_key.startswith("gliner_") or detector_key.startswith("hideme_"):
            # Determine the category based on the key prefix.
            category = "gliner" if detector_key.startswith("gliner_") else "hideme"
            # Ensure the category exists in the metrics.
            self._usage_metrics.setdefault(category, {})
            # Ensure the specific detector key is initialized.
            self._usage_metrics[category].setdefault(detector_key, {"uses": 0, "last_used": None})
            # Increment the usage count.
            self._usage_metrics[category][detector_key]["uses"] += 1
            # Update the last used timestamp.
            self._usage_metrics[category][detector_key]["last_used"] = current_time
        else:
            # For other detectors, update the usage metrics directly.
            if detector_key in self._usage_metrics:
                self._usage_metrics[detector_key]["uses"] += 1
                self._usage_metrics[detector_key]["last_used"] = current_time

    def _update_usage_metrics_no_lock(self, detector_key: str):
        """
        Update usage metrics for a detector without acquiring the lock.

        Args:
            detector_key (str): Key identifying the detector.
        """
        # Get the current timestamp.
        current_time = time.time()
        try:
            # Increment usage metrics using the helper method.
            self._increment_usage_metrics(detector_key, current_time)
        except Exception as exc:
            # Log any non-critical processing error.
            SecurityAwareErrorHandler().log_processing_error(exc, "_update_usage_metrics_no_lock")
            log_warning(f"Exception updating usage metrics (non-critical): {exc}")

    def _evict_least_recently_used(self, detector_type: str):
        """
        Evict the least recently used detector from the cache.

        Args:
            detector_type (str): Cache type ("gliner", "hideme", or "hybrid").
        """
        # Handle eviction for HYBRID detectors.
        if detector_type == "hybrid":
            if self._hybrid_detectors:
                lru_key = next(iter(self._hybrid_detectors))
                log_info("Evicting hybrid detector from cache")
                del self._hybrid_detectors[lru_key]
            return
        # For GLiNER and HIDEME, use usage metrics to determine the LRU detector.
        if detector_type in ("gliner", "hideme"):
            category_metrics = self._usage_metrics.get(detector_type, {})
            # If there are no metrics, no eviction is needed.
            if not category_metrics:
                return
            # Find the detector key with the smallest "last_used" value.
            lru_item = min(category_metrics.items(), key=lambda item: item[1].get("last_used", float('inf')))
            # Extract the actual cache key (remove prefix).
            lru_key = lru_item[0].split("_", 1)[-1]
            if detector_type == "gliner" and lru_key in self._gliner_detectors:
                log_info(f"Evicting least recently used GLiNER detector: {lru_key}")
                del self._gliner_detectors[lru_key]
            elif detector_type == "hideme" and lru_key in self._hideme_detectors:
                log_info(f"Evicting least recently used HIDEME detector: {lru_key}")
                del self._hideme_detectors[lru_key]
        elif detector_type == "hybrid":
            if not self._hybrid_detectors:
                return
            lru_key = next(iter(self._hybrid_detectors))
            log_info("Evicting hybrid detector from cache")
            del self._hybrid_detectors[lru_key]

    @staticmethod
    def _get_gliner_cache_key(entities: List[str]) -> str:
        """
        Generate a cache key for a GLiNER detector based on a sorted list of entities.

        Args:
            entities (List[str]): List of entity types.

        Returns:
            A string cache key.
        """
        # If no entities provided, return default key.
        if not entities:
            return "default"
        # Sort and join entities to form the cache key.
        return "_".join(sorted(entities))

    @staticmethod
    def _get_hideme_cache_key(entities: List[str]) -> str:
        """
        Generate a cache key for a HIDEME detector based on a sorted list of entities.

        Args:
            entities (List[str]): List of entity types.

        Returns:
            A string cache key.
        """
        # If no entities provided, return default key.
        if not entities:
            return "default"
        # Sort and join entities to form the cache key.
        return "_".join(sorted(entities))

    @staticmethod
    def _get_hybrid_cache_key(config: Dict[str, Any]) -> str:
        """
        Generate a cache key for a Hybrid detector based on its configuration.

        Args:
            config (Dict[str, Any]): Detector configuration.

        Returns:
            A string representing the cache key.
        """
        # Retrieve individual configuration flags.
        use_presidio = config.get("use_presidio", True)
        use_gemini = config.get("use_gemini", False)
        use_gliner = config.get("use_gliner", False)
        use_hideme = config.get("use_hideme", False)
        entities = config.get("entities", [])
        # Sort entities if provided.
        sorted_entities = sorted(entities) if entities else []
        # Convert entities to a string.
        entities_str = "_".join(sorted_entities) if sorted_entities else "none"
        # Format and return the combined cache key.
        return f"p{int(use_presidio)}_g{int(use_gemini)}_gl{int(use_gliner)}_h{int(use_hideme)}_{entities_str}"

    def get_initialization_status(self) -> Dict[str, bool]:
        """
        Retrieve the initialization status for all detectors.

        Returns:
            A dictionary mapping each detector type to its initialization status.
        """
        try:
            # Attempt to acquire the lock with a 1-second timeout.
            if self._lock.acquire(timeout=1.0):
                try:
                    # Return a copy of the initialization status.
                    return dict(self._initialization_status)
                finally:
                    # Always release the lock.
                    self._lock.release()
            else:
                # If lock acquisition fails, return the current initialization status.
                return dict(self._initialization_status)
        except Exception as exc:
            # Log any processing errors encountered.
            SecurityAwareErrorHandler().log_processing_error(exc, "get_initialization_status")
            log_warning(f"Lock acquisition failed in get_initialization_status: {str(exc)}")
            # Return the initialization status regardless.
            return dict(self._initialization_status)

    def get_usage_metrics(self) -> Dict[str, Any]:
        """
        Retrieve usage metrics for all detectors.

        Returns:
            A dictionary containing usage statistics for each detector.
        """
        try:
            # Attempt to acquire the lock with a 1-second timeout.
            if self._lock.acquire(timeout=1.0):
                try:
                    # Create a copy of the usage metrics for PRESIDIO and GEMINI.
                    metrics_copy = {
                        "presidio": dict(self._usage_metrics.get("presidio", {})),
                        "gemini": dict(self._usage_metrics.get("gemini", {})),
                    }
                    # Include GLiNER metrics if available.
                    if "gliner" in self._usage_metrics:
                        metrics_copy["gliner"] = {
                            key: dict(val) for key, val in self._usage_metrics["gliner"].items()
                        }
                    # Include HIDEME metrics if available.
                    if "hideme" in self._usage_metrics:
                        metrics_copy["hideme"] = {
                            key: dict(val) for key, val in self._usage_metrics["hideme"].items()
                        }
                    # Return the complete metrics copy.
                    return metrics_copy
                finally:
                    # Release the lock.
                    self._lock.release()
            else:
                # Return empty metrics if lock acquisition fails.
                return {"presidio": {}, "gemini": {}, "gliner": {}, "hideme": {}}
        except Exception as exc:
            # Log any processing errors that occur.
            SecurityAwareErrorHandler().log_processing_error(exc, "get_usage_metrics")
            log_error(f"Error getting usage metrics: {str(exc)}")
            # Return empty metrics on error.
            return {"presidio": {}, "gemini": {}, "gliner": {}, "hideme": {}}

    def check_health(self) -> Dict[str, Any]:
        """
        Check and report the health status of all detector caches.

        Returns:
            A dictionary containing health information such as cache size, timestamp,
            and the initialization status of each detector.
        """
        try:
            # Attempt to acquire the lock with a 2-second timeout.
            if self._lock.acquire(timeout=2.0):
                try:
                    # Calculate the total cache size from all detector caches.
                    cache_size = (
                            (1 if self._presidio_detector else 0) +
                            (1 if self._gemini_detector else 0) +
                            len(self._gliner_detectors) +
                            len(self._hideme_detectors) +
                            len(self._hybrid_detectors)
                    )
                    # Return the health status with cache metrics.
                    return {
                        "health": "ok",
                        "timestamp": datetime.now().isoformat(),
                        "cache_size": cache_size,
                        "max_cache_size": self.max_cache_size,
                        "detectors": dict(self._initialization_status)
                    }
                finally:
                    # Release the lock.
                    self._lock.release()
            else:
                # Return limited health status if lock acquisition times out.
                return {
                    "health": "limited",
                    "timestamp": datetime.now().isoformat(),
                    "cache_size": -1,
                    "max_cache_size": self.max_cache_size,
                    "detectors": dict(self._initialization_status),
                    "error": "Lock acquisition timeout"
                }
        except Exception as exc:
            # Log any processing errors that occur during the health check.
            SecurityAwareErrorHandler().log_processing_error(exc, "check_health")
            log_error(f"Error checking health: {str(exc)}")
            # Return an error health status.
            return {
                "health": "error",
                "timestamp": datetime.now().isoformat(),
                "error": str(exc)
            }


# Create a singleton instance of InitializationService.
initialization_service = InitializationService()
