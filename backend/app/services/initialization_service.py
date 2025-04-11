"""
Enhanced model initialization service with improved thread safety.
This service manages the initialization and caching of detection engines with improved synchronization using a basic lock (acquire/release)
for concurrent access.

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

from backend.app.entity_detection import EntityDetectionEngine, GlinerEntityDetector
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.system_utils.memory_management import memory_monitor
from backend.app.utils.system_utils.synchronization_utils import TimeoutLock, LockPriority, AsyncTimeoutLock

logger = logging.getLogger(__name__)

class InitializationService:
    """
    Service for initializing and caching ML models and detectors with improved thread safety.

    This class:
        - Initializes detectors lazily to avoid blocking application startup.
        - Manages caches for multiple detector types (Presidio, Gemini, GLiNER, Hybrid).
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
        # Set max cache size from provided argument or from configuration default.
        self.max_cache_size = max_cache_size or get_config("max_detector_cache_size", MAX_DETECTOR_CACHE_SIZE)
        # Instantiate a synchronous lock with high priority and a 15-second timeout.
        self._lock = TimeoutLock("detector_cache_lock", priority=LockPriority.HIGH, timeout=15.0)
        # Instantiate an asynchronous lock with high priority and a 15-second timeout.
        self._async_lock = AsyncTimeoutLock("detector_async_lock", priority=LockPriority.HIGH, timeout=15.0)
        # Initialize a dictionary to track whether each detector has been successfully initialized.
        self._initialization_status: Dict[str, bool] = {
            "presidio": False,
            "gemini": False,
            "gliner": False,
            "hybrid": False
        }
        # Initialize the Presidio detector cache to None.
        self._presidio_detector = None
        # Initialize the Gemini detector cache to None.
        self._gemini_detector = None
        # Initialize the GLiNER detector cache as an empty dictionary.
        self._gliner_detectors: Dict[str, Any] = {}
        # Initialize the Hybrid detector cache as an empty dictionary.
        self._hybrid_detectors: Dict[str, Any] = {}
        # Initialize usage metrics for each detector.
        self._usage_metrics: Dict[str, Any] = {
            "presidio": {"uses": 0, "last_used": None},
            "gemini": {"uses": 0, "last_used": None},
            "gliner": {}  # This will be populated per cache key.
        }
        # Log that the initialization service has started with the specified max cache size.
        log_info(f"Initialization service started with max cache size: {self.max_cache_size}")

    async def initialize_detectors_lazy(self):
        """
        Lazily initialize detectors at application startup without blocking other services.
        This method initializes Presidio, Gemini, and conditionally GLiNER detectors in the background.
        """
        # Log the start of lazy initialization.
        log_info("[STARTUP] Starting lazy initialization of detectors...")
        try:
            # Lazily initialize the Presidio detector.
            await self._lazy_init_presidio()
            # Wait a short pause between initializations.
            await asyncio.sleep(1.0)
            # Lazily initialize the Gemini detector.
            await self._lazy_init_gemini()
            # Conditionally lazily initialize the GLiNER detector.
            await self._maybe_lazy_init_gliner()
            # Log that lazy initialization has completed successfully.
            log_info("[STARTUP] Lazy initialization of detectors completed successfully.")
        except Exception as exc:
            # Log any error using the error handler and the log function.
            SecurityAwareErrorHandler().log_processing_error(exc, "initialize_detectors_lazy")
            log_error(f"[STARTUP] Error during detector lazy initialization: {str(exc)}")

    async def _lazy_init_presidio(self):
        """
        Background-thread initialization for the Presidio detector.
        """
        # Log that lazy initialization of the Presidio detector has started.
        log_info("[STARTUP] Lazily initializing Presidio detector...")
        try:
            # Offload the initialization to a background thread.
            presidio_detector = await asyncio.to_thread(self._initialize_presidio_detector)
            # Store the initialized detector.
            self._presidio_detector = presidio_detector
            # Mark the Presidio detector as initialized.
            self._initialization_status["presidio"] = True
            # Log that the Presidio detector initialization is complete.
            log_info("[STARTUP] Presidio detector lazy initialization complete.")
        except Exception as exc:
            # Log the exception using the error handler.
            SecurityAwareErrorHandler().log_processing_error(exc, "_lazy_init_presidio")
            # Log the error message.
            log_error(f"[STARTUP] Error during Presidio lazy initialization: {str(exc)}")

    async def _lazy_init_gemini(self):
        """
        Background-thread initialization for the Gemini detector.
        """
        # Log that lazy initialization of the Gemini detector has started.
        log_info("[STARTUP] Lazily initializing Gemini detector...")
        try:
            # Offload Gemini detector initialization to a background thread.
            gemini_detector = await asyncio.to_thread(self._initialize_gemini_detector)
            # Store the initialized Gemini detector.
            self._gemini_detector = gemini_detector
            # Mark the Gemini detector as initialized.
            self._initialization_status["gemini"] = True
            # Log that Gemini detector lazy initialization is complete.
            log_info("[STARTUP] Gemini detector lazy initialization complete.")
        except Exception as exc:
            # Log any initialization error using the error handler.
            SecurityAwareErrorHandler().log_processing_error(exc, "_lazy_init_gemini")
            # Log the error message.
            log_error(f"[STARTUP] Error during Gemini lazy initialization: {str(exc)}")

    async def _maybe_lazy_init_gliner(self):
        """
        Conditionally initialize the GLiNER detector if memory usage is below a threshold.
        """
        # Check if the current memory usage is below the 60% threshold.
        if memory_monitor.get_memory_usage() < 60.0:
            # Log that GLiNER detector lazy initialization will be attempted.
            log_info("[STARTUP] Lazily initializing GLiNER detector...")
            try:
                # Offload the GLiNER initialization to a background thread with model name and entities.
                gliner_detector = await asyncio.to_thread(
                    self._initialize_gliner_detector,
                    GLINER_MODEL_NAME,
                    GLINER_AVAILABLE_ENTITIES
                )
                # Generate a cache key for the GLiNER detector.
                cache_key = self._get_gliner_cache_key(GLINER_AVAILABLE_ENTITIES)
                # Store the GLiNER detector in the cache.
                self._gliner_detectors[cache_key] = gliner_detector
                # Mark the GLiNER detector as initialized.
                self._initialization_status["gliner"] = True
                # Log that GLiNER detector initialization is complete.
                log_info("[STARTUP] GLiNER detector lazy initialization complete.")
            except Exception as exc:
                # Log any error using the error handler.
                SecurityAwareErrorHandler().log_processing_error(exc, "_maybe_lazy_init_gliner")
                # Log the error message.
                log_error(f"[STARTUP] Error during GLiNER lazy initialization: {str(exc)}")
        else:
            # Log that GLiNER detector initialization is skipped due to high memory usage.
            log_info("[STARTUP] Skipping GLiNER lazy initialization due to memory pressure.")

    def _initialize_presidio_detector(self):
        """
        Initialize a Presidio detector instance with error handling.

        Returns:
            An instance of the Presidio detector.
        """
        # Log that the Presidio detector initialization is starting.
        log_info("Initializing Presidio detector")
        # Record the start time for initialization.
        start_time = time.time()
        try:
            # Import and instantiate the PresidioEntityDetector.
            from backend.app.entity_detection.presidio import PresidioEntityDetector
            detector = PresidioEntityDetector()
            # Mark Presidio as initialized.
            self._initialization_status["presidio"] = True
            # Log the time taken to initialize.
            log_info(f"Presidio detector initialized in {time.time() - start_time:.2f}s")
            # Return the detector instance.
            return detector
        except Exception as exc:
            # Mark initialization as failed.
            self._initialization_status["presidio"] = False
            # Log the error with the error handler.
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
        # Log that Gemini detector initialization is starting.
        log_info("Initializing Gemini detector")
        # Record the start time for initialization.
        start_time = time.time()
        try:
            # Import and instantiate the GeminiEntityDetector.
            from backend.app.entity_detection.gemini import GeminiEntityDetector
            detector = GeminiEntityDetector()
            # Mark Gemini as initialized.
            self._initialization_status["gemini"] = True
            # Log the time taken to initialize.
            log_info(f"Gemini detector initialized in {time.time() - start_time:.2f}s")
            # Return the detector instance.
            return detector
        except Exception as exc:
            # Mark initialization as failed.
            self._initialization_status["gemini"] = False
            # Log the error with the error handler.
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
        # Log the start of GLiNER detector initialization with provided model and entities.
        log_info(f"Initializing GLiNER detector with model {model_name} for entities: {entities}")
        # Record the start time.
        start_time = time.time()
        try:
            # Instantiate the GlinerEntityDetector with model details.
            detector = GlinerEntityDetector(
                model_name=model_name,
                entities=entities or GLINER_AVAILABLE_ENTITIES,
                local_model_path=GLINER_MODEL_PATH
            )
            # Mark GLiNER as initialized.
            self._initialization_status["gliner"] = True
            # Log the time taken for initialization.
            log_info(f"GLiNER detector initialized in {time.time() - start_time:.2f}s")
            # Return the detector instance.
            return detector
        except Exception as exc:
            # Mark GLiNER initialization as failed.
            self._initialization_status["gliner"] = False
            # Log the error.
            SecurityAwareErrorHandler().log_processing_error(exc, "_initialize_gliner_detector")
            log_error(f"Error initializing GLiNER detector: {str(exc)}")
            # Propagate the exception.
            raise

    def _initialize_hybrid_detector(self, config: Dict[str, Any]):
        """
        Initialize a hybrid detector instance with error handling.

        Args:
            config (Dict[str, Any]): Configuration for the hybrid detector.

        Returns:
            An instance of the hybrid detector.
        """
        # Log the initialization of the Hybrid detector with provided configuration.
        log_info(f"Initializing Hybrid detector with config: {config}")
        # Record the start time.
        start_time = time.time()
        try:
            # Import and instantiate the HybridEntityDetector.
            from backend.app.entity_detection.hybrid import HybridEntityDetector
            detector = HybridEntityDetector(config)
            # Mark Hybrid detector as initialized.
            self._initialization_status["hybrid"] = True
            # Log the time taken for Hybrid detector initialization.
            log_info(f"Hybrid detector initialized in {time.time() - start_time:.2f}s")
            # Return the Hybrid detector instance.
            return detector
        except Exception as exc:
            # Mark Hybrid initialization as failed.
            self._initialization_status["hybrid"] = False
            # Log the error.
            SecurityAwareErrorHandler().log_processing_error(exc, "_initialize_hybrid_detector")
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
            # If the Presidio detector has an async shutdown, call it.
            if self._presidio_detector and hasattr(self._presidio_detector, "shutdown_async"):
                await self._presidio_detector.shutdown_async()
            # If the Gemini detector has an async shutdown, call it.
            if self._gemini_detector and hasattr(self._gemini_detector, "shutdown_async"):
                await self._gemini_detector.shutdown_async()
            # For each GLiNER detector in the cache, call async shutdown if available.
            for detector in self._gliner_detectors.values():
                if hasattr(detector, "shutdown_async"):
                    await detector.shutdown_async()
            # For each hybrid detector in the cache, call async shutdown if available.
            for detector in self._hybrid_detectors.values():
                if hasattr(detector, "shutdown_async"):
                    await detector.shutdown_async()
        except Exception as exc:
            # Log any error that occurs during shutdown.
            SecurityAwareErrorHandler().log_processing_error(exc, "shutdown_async")
            log_error(f"Error during asynchronous shutdown: {exc}")

    def get_presidio_detector(self):
        """
        Retrieve a Presidio detector instance with basic thread safety.

        Returns:
            The Presidio detector instance.
        """
        # Delegate to the generic get_detector API for the PRESIDIO engine.
        return self.get_detector(EntityDetectionEngine.PRESIDIO)

    def get_gemini_detector(self):
        """
        Retrieve a Gemini detector instance with basic thread safety.

        Returns:
            The Gemini detector instance.
        """
        # Delegate to the generic get_detector API for the GEMINI engine.
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
        # Build the configuration dictionary for the GLiNER detector.
        config = {"entities": entities or GLINER_AVAILABLE_ENTITIES}
        # Delegate to the generic get_detector API for the GLINER engine.
        return self.get_detector(EntityDetectionEngine.GLINER, config)

    def get_detector(self, engine: EntityDetectionEngine, config: Optional[Dict[str, Any]] = None):
        """
        Retrieve a detector instance for the specified engine using lock management.
        This method performs a quick cache check and initializes the detector if necessary.

        Args:
            engine (EntityDetectionEngine): The detection engine type.
            config (Dict[str, Any], optional): Configuration for detector initialization.

        Returns:
            The detector instance for the requested engine.
        """
        # Ensure configuration is a dictionary.
        if config is None:
            config = {}
        # Step 1: Perform a quick check of the cache for the detector.
        maybe_cached = self._quick_check_cache(engine, config)
        # If found, return the cached detector.
        if maybe_cached is not None:
            return maybe_cached
        # Step 2: Attempt to acquire the lock with a 0.5-second timeout.
        if self._try_acquire_lock(0.5):
            try:
                # Recheck the cache while holding the lock.
                rechecked = self._quick_check_cache(engine, config)
                if rechecked is not None:
                    return rechecked
            finally:
                # Always release the lock.
                self._lock.release()
        else:
            # Log a warning if the lock could not be acquired.
            log_warning("[WARNING] Timeout acquiring lock for quick cache check")
        # Step 3: Acquire lock with a 1.0-second timeout for detector initialization.
        if self._try_acquire_lock(1.0):
            try:
                # Recheck the cache under lock again.
                final_cached = self._quick_check_cache(engine, config)
                if final_cached is not None:
                    return final_cached
                # Initialize and store the detector if still not cached.
                return self._initialize_and_store_detector(engine, config)
            finally:
                # Release the lock.
                self._lock.release()
        else:
            # Log a warning if unable to acquire the lock.
            log_warning("[WARNING] Timeout acquiring lock for detector initialization")
        # Step 4: Fallback: initialize the detector without lock acquisition.
        return self._fallback_init(engine, config)

    def _quick_check_cache(self, engine: EntityDetectionEngine, config: Dict[str, Any]) -> Optional[Any]:
        """
        Quickly check if a detector instance exists in the cache.
        If found, updates its usage metrics.

        Args:
            engine (EntityDetectionEngine): The detection engine type.
            config (Dict[str, Any]): Configuration parameters.

        Returns:
            The cached detector instance if available; otherwise, None.
        """
        # Check for PRESIDIO detector in the cache.
        if engine == EntityDetectionEngine.PRESIDIO and self._presidio_detector:
            self._update_usage_metrics_no_lock("presidio")
            return self._presidio_detector
        # Check for GEMINI detector in the cache.
        if engine == EntityDetectionEngine.GEMINI and self._gemini_detector:
            self._update_usage_metrics_no_lock("gemini")
            return self._gemini_detector
        # Check for GLINER detector in the cache using the generated key.
        if engine == EntityDetectionEngine.GLINER:
            key = self._get_gliner_cache_key(config.get("entities", []))
            if key in self._gliner_detectors:
                self._update_usage_metrics_no_lock(f"gliner_{key}")
                return self._gliner_detectors[key]
        # Check for HYBRID detector in the cache.
        if engine == EntityDetectionEngine.HYBRID:
            key = self._get_hybrid_cache_key(config)
            if key in self._hybrid_detectors:
                return self._hybrid_detectors[key]
        # If no detector found, return None.
        return None

    def _try_acquire_lock(self, timeout: float) -> bool:
        """
        Attempt to acquire the main lock within a specified timeout.

        Args:
            timeout (float): The timeout in seconds.

        Returns:
            True if the lock was acquired; otherwise, False.
        """
        try:
            # Try to acquire the lock with given timeout.
            return self._lock.acquire(timeout=timeout)
        except TimeoutError:
            # Return False if a TimeoutError occurs.
            return False

    def _initialize_and_store_detector(self, engine: EntityDetectionEngine, config: Dict[str, Any]) -> Any:
        """
        Under lock, initialize the requested detector and store it in the cache.
        Delegates to helper methods based on the engine type.

        Args:
            engine (EntityDetectionEngine): The detection engine type.
            config (Dict[str, Any]): Configuration parameters.

        Returns:
            The initialized detector instance.
        """
        # Determine which detector to initialize based on the engine type.
        if engine in (EntityDetectionEngine.PRESIDIO, EntityDetectionEngine.GEMINI):
            return self._initialize_presidio_or_gemini(engine)
        elif engine == EntityDetectionEngine.GLINER:
            return self._initialize_gliner(config)
        elif engine == EntityDetectionEngine.HYBRID:
            return self._initialize_hybrid(config)
        else:
            # Raise an error if the engine type is not supported.
            raise ValueError(f"Unsupported detection engine: {engine}")

    def _initialize_presidio_or_gemini(self, engine: EntityDetectionEngine) -> Any:
        """
        Initialize a Presidio or Gemini detector, store it in cache, and update usage metrics.

        Args:
            engine (EntityDetectionEngine): The detection engine type.

        Returns:
            The detector instance.
        """
        # For PRESIDIO engine, check if detector exists; if not, initialize and store.
        if engine == EntityDetectionEngine.PRESIDIO:
            if self._presidio_detector:
                self._update_usage_metrics_no_lock("presidio")
                return self._presidio_detector
            new_det = self._initialize_presidio_detector()
            self._presidio_detector = new_det
            self._update_usage_metrics_no_lock("presidio")
            return new_det
        else:
            # For GEMINI engine, check if detector exists; if not, initialize and store.
            if self._gemini_detector:
                self._update_usage_metrics_no_lock("gemini")
                return self._gemini_detector
            new_det = self._initialize_gemini_detector()
            self._gemini_detector = new_det
            self._update_usage_metrics_no_lock("gemini")
            return new_det

    def _initialize_gliner(self, config: Dict[str, Any]) -> Any:
        """
        Initialize a GLiNER detector, managing cache eviction if necessary,
        and update its usage metrics.

        Args:
            config (Dict[str, Any]): Configuration parameters for GLiNER.

        Returns:
            The GLiNER detector instance.
        """
        # Retrieve the entities list from config and generate a cache key.
        entities = config.get("entities", [])
        cache_key = self._get_gliner_cache_key(entities)
        # If the detector exists in the cache, update its usage and return it.
        if cache_key in self._gliner_detectors:
            self._update_usage_metrics_no_lock(f"gliner_{cache_key}")
            return self._gliner_detectors[cache_key]
        # Retrieve the model name from config.
        model_name = config.get("model_name", GLINER_MODEL_NAME)
        # Initialize a new GLiNER detector.
        new_det = self._initialize_gliner_detector(model_name, entities)
        # If the cache is full, evict the least recently used detector.
        if len(self._gliner_detectors) >= self.max_cache_size:
            self._evict_least_recently_used("gliner")
        # Cache the new detector.
        self._gliner_detectors[cache_key] = new_det
        self._update_usage_metrics_no_lock(f"gliner_{cache_key}")
        return new_det

    def _initialize_hybrid(self, config: Dict[str, Any]) -> Any:
        """
        Initialize a Hybrid detector, managing cache eviction if necessary.

        Args:
            config (Dict[str, Any]): Configuration parameters for Hybrid.

        Returns:
            The Hybrid detector instance.
        """
        # Generate a cache key from the configuration.
        cache_key = self._get_hybrid_cache_key(config)
        # If the detector exists in the cache, return it.
        if cache_key in self._hybrid_detectors:
            return self._hybrid_detectors[cache_key]
        # Otherwise, initialize a new hybrid detector.
        new_det = self._initialize_hybrid_detector(config)
        # If the cache is full, evict the least recently used entry.
        if len(self._hybrid_detectors) >= self.max_cache_size:
            self._evict_least_recently_used("hybrid")
        # Cache the new hybrid detector.
        self._hybrid_detectors[cache_key] = new_det
        return new_det

    def _fallback_init(self, engine: EntityDetectionEngine, config: Dict[str, Any]) -> Any:
        """
        Fallback initialization in case lock acquisition fails.
        Uses direct initialization without acquiring the lock.

        Args:
            engine (EntityDetectionEngine): The detection engine type.
            config (Dict[str, Any]): Configuration parameters.

        Returns:
            The initialized detector instance.
        """
        # Log a warning about fallback initialization.
        log_warning("Timeout acquiring detector lock - proceeding with fallback initialization")
        # For PRESIDIO engine, return the cached detector or initialize new.
        if engine == EntityDetectionEngine.PRESIDIO:
            if self._presidio_detector:
                return self._presidio_detector
            return self._initialize_presidio_detector()
        # For GEMINI engine, return the cached detector or initialize new.
        if engine == EntityDetectionEngine.GEMINI:
            if self._gemini_detector:
                return self._gemini_detector
            return self._initialize_gemini_detector()
        # For GLINER engine, check cache and initialize if not present.
        if engine == EntityDetectionEngine.GLINER:
            key = self._get_gliner_cache_key(config.get("entities", []))
            if key in self._gliner_detectors:
                return self._gliner_detectors[key]
            model_name = config.get("model_name", GLINER_MODEL_NAME)
            return self._initialize_gliner_detector(model_name, config.get("entities", []))
        # For HYBRID engine, check cache and initialize if not present.
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
            current_time (float): The current timestamp.
        """
        # Check if the detector key represents a GLiNER detector.
        if detector_key.startswith("gliner_"):
            # Initialize the GLiNER usage metrics if not already present.
            self._usage_metrics.setdefault("gliner", {})
            self._usage_metrics["gliner"].setdefault(detector_key, {"uses": 0, "last_used": None})
            # Increment the use count.
            self._usage_metrics["gliner"][detector_key]["uses"] += 1
            # Update the last used timestamp.
            self._usage_metrics["gliner"][detector_key]["last_used"] = current_time
        else:
            # For non-GLiNER detectors, update their usage metrics.
            if detector_key in self._usage_metrics:
                self._usage_metrics[detector_key]["uses"] += 1
                self._usage_metrics[detector_key]["last_used"] = current_time

    def _update_usage_metrics_no_lock(self, detector_key: str):
        """
        Update usage metrics for a detector without acquiring the lock.
        Designed for high-traffic scenarios where lock contention should be minimized.

        Args:
            detector_key (str): Key identifying the detector.
        """
        # Get the current time.
        current_time = time.time()
        try:
            # Increment the usage metrics.
            self._increment_usage_metrics(detector_key, current_time)
        except Exception as exc:
            # Log any non-critical errors during metric update.
            SecurityAwareErrorHandler().log_processing_error(exc, "_update_usage_metrics_no_lock")
            log_warning(f"Exception in updating usage metrics (non-critical): {exc}")

    def _evict_least_recently_used(self, detector_type: str):
        """
        Evict the least recently used detector from the cache based on usage metrics.

        Args:
            detector_type (str): Cache type ("gliner" or "hybrid").
        """
        # Eviction for GLiNER detectors.
        if detector_type == "gliner":
            lru_key = None
            oldest_time = float('inf')
            # Iterate through GLiNER usage metrics.
            for key, metrics in self._usage_metrics.get("gliner", {}).items():
                # Identify the detector with the oldest last_used time.
                if metrics and metrics.get("last_used", float('inf')) < oldest_time:
                    oldest_time = metrics.get("last_used", float('inf'))
                    lru_key = key.replace("gliner_", "")
            # If an LRU key is found and exists in the cache, evict it.
            if lru_key and lru_key in self._gliner_detectors:
                log_info(f"Evicting least recently used GLiNER detector: {lru_key}")
                del self._gliner_detectors[lru_key]
        # Eviction for Hybrid detectors.
        elif detector_type == "hybrid":
            # If the Hybrid cache is empty, do nothing.
            if not self._hybrid_detectors:
                return
            # Evict the first Hybrid detector found in the cache.
            lru_key = next(iter(self._hybrid_detectors))
            log_info("Evicting hybrid detector from cache")
            del self._hybrid_detectors[lru_key]

    @staticmethod
    def _get_gliner_cache_key(entities: List[str]) -> str:
        """
        Generate a cache key for GLiNER detector based on a sorted list of entities.

        Args:
            entities (List[str]): List of entity types.

        Returns:
            A string to be used as a cache key.
        """
        # If no entities provided, return default key.
        if not entities:
            return "default"
        # Sort the entities.
        sorted_entities = sorted(entities)
        # Join the sorted entities with underscores.
        return "_".join(sorted_entities)

    @staticmethod
    def _get_hybrid_cache_key(config: Dict[str, Any]) -> str:
        """
        Generate a cache key for a Hybrid detector based on its configuration.

        Args:
            config (Dict[str, Any]): Detector configuration.

        Returns:
            A string representing the cache key.
        """
        # Get boolean flags from config with default values.
        use_presidio = config.get("use_presidio", True)
        use_gemini = config.get("use_gemini", False)
        use_gliner = config.get("use_gliner", False)
        # Get entities list and sort if available.
        entities = config.get("entities", [])
        sorted_entities = sorted(entities) if entities else []
        entities_str = "_".join(sorted_entities) if sorted_entities else "none"
        # Build and return the cache key string.
        return f"p{int(use_presidio)}_g{int(use_gemini)}_gl{int(use_gliner)}_{entities_str}"

    def get_initialization_status(self) -> Dict[str, bool]:
        """
        Retrieve the initialization status for all detectors.

        Returns:
            A dictionary mapping each detector type to its initialization status.
        """
        try:
            # Attempt to acquire lock for status retrieval.
            if self._lock.acquire(timeout=1.0):
                try:
                    # Return a copy of the initialization status.
                    return dict(self._initialization_status)
                finally:
                    # Always release the lock.
                    self._lock.release()
            else:
                # If lock cannot be acquired, return current status.
                return dict(self._initialization_status)
        except Exception as exc:
            # Log error if lock acquisition fails.
            SecurityAwareErrorHandler().log_processing_error(exc, "get_initialization_status")
            log_warning(f"Lock acquisition failed in get_initialization_status: {str(exc)}")
            return dict(self._initialization_status)

    def get_usage_metrics(self) -> Dict[str, Any]:
        """
        Retrieve usage metrics for all detectors.

        Returns:
            A dictionary containing usage statistics for each detector.
        """
        try:
            # Acquire lock to read usage metrics.
            if self._lock.acquire(timeout=1.0):
                try:
                    # Build a copy of usage metrics for presidio and gemini.
                    metrics_copy = {
                        "presidio": dict(self._usage_metrics.get("presidio", {})),
                        "gemini": dict(self._usage_metrics.get("gemini", {})),
                    }
                    # Also copy GLiNER metrics if available.
                    if "gliner" in self._usage_metrics:
                        metrics_copy["gliner"] = {
                            key: dict(val)
                            for key, val in self._usage_metrics["gliner"].items()
                        }
                    # Return the copied metrics.
                    return metrics_copy
                finally:
                    # Release the lock.
                    self._lock.release()
            else:
                # Return default empty metrics if lock acquisition fails.
                return {"presidio": {}, "gemini": {}, "gliner": {}}
        except Exception as exc:
            # Log error retrieving usage metrics.
            SecurityAwareErrorHandler().log_processing_error(exc, "get_usage_metrics")
            log_error(f"Error getting usage metrics: {str(exc)}")
            return {"presidio": {}, "gemini": {}, "gliner": {}}

    def check_health(self) -> Dict[str, Any]:
        """
        Check and report the health status of all detector caches.

        Returns:
            A dictionary containing health information such as cache size, timestamp,
            and the initialization status of each detector.
        """
        try:
            # Acquire lock for health check.
            if self._lock.acquire(timeout=2.0):
                try:
                    # Compute the total cache size.
                    cache_size = (
                        (1 if self._presidio_detector else 0) +
                        (1 if self._gemini_detector else 0) +
                        len(self._gliner_detectors) +
                        len(self._hybrid_detectors)
                    )
                    # Build the health status dictionary.
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
                # Return a limited health status if lock acquisition times out.
                return {
                    "health": "limited",
                    "timestamp": datetime.now().isoformat(),
                    "cache_size": -1,
                    "max_cache_size": self.max_cache_size,
                    "detectors": dict(self._initialization_status),
                    "error": "Lock acquisition timeout"
                }
        except Exception as exc:
            # Log error during health check.
            SecurityAwareErrorHandler().log_processing_error(exc, "check_health")
            log_error(f"Error checking health: {str(exc)}")
            return {
                "health": "error",
                "timestamp": datetime.now().isoformat(),
                "error": str(exc)
            }

# Create a singleton instance of InitializationService.
initialization_service = InitializationService()
