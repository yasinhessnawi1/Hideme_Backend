"""
Enhanced model initialization service with improved thread safety.
This service manages the initialization and caching of detection engines
with improved synchronization using a basic lock (acquire/release)
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

# Import configuration parameters and constants
from backend.app.configs.config_singleton import get_config
from backend.app.configs.gdpr_config import MAX_DETECTOR_CACHE_SIZE
from backend.app.configs.gliner_config import GLINER_MODEL_NAME, GLINER_AVAILABLE_ENTITIES, GLINER_MODEL_PATH

# Import detector classes and logging utilities
from backend.app.entity_detection import EntityDetectionEngine, GlinerEntityDetector
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.system_utils.memory_management import memory_monitor
from backend.app.utils.system_utils.synchronization_utils import TimeoutLock, LockPriority, AsyncTimeoutLock

# Configure logger for the module
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
        # Set max cache size from provided argument or config default.
        self.max_cache_size = max_cache_size or get_config("max_detector_cache_size", MAX_DETECTOR_CACHE_SIZE)

        # Instantiate locks for thread safety with high priority and a 15-second timeout.
        self._lock = TimeoutLock("detector_cache_lock", priority=LockPriority.HIGH, timeout=15.0)
        self._async_lock = AsyncTimeoutLock("detector_async_lock", priority=LockPriority.HIGH, timeout=15.0)

        # Dictionary to track whether each detector has been successfully initialized.
        self._initialization_status: Dict[str, bool] = {
            "presidio": False,
            "gemini": False,
            "gliner": False,
            "hybrid": False
        }

        # Initialize detector caches.
        self._presidio_detector = None
        self._gemini_detector = None
        self._gliner_detectors: Dict[str, Any] = {}  # Maps entity-lists to detector instance.
        self._hybrid_detectors: Dict[str, Any] = {}  # Maps configuration to detector instance.

        # Usage metrics to track how often detectors are used.
        self._usage_metrics: Dict[str, Any] = {
            "presidio": {"uses": 0, "last_used": None},
            "gemini": {"uses": 0, "last_used": None},
            "gliner": {}  # Will be populated per cache key.
        }

        log_info(f"Initialization service started with max cache size: {self.max_cache_size}")

    # 1) Lazy initialization methods  #

    async def initialize_detectors_lazy(self):
        """
        Lazily initialize detectors at application startup without blocking other services.
        This method initializes Presidio, Gemini, and conditionally GLiNER detectors in the background.
        """
        log_info("[STARTUP] Starting lazy initialization of detectors...")
        try:
            await self._lazy_init_presidio()
            await asyncio.sleep(1.0)  # Short pause between initializations.
            await self._lazy_init_gemini()
            await self._maybe_lazy_init_gliner()
            log_info("[STARTUP] Lazy initialization of detectors completed successfully.")
        except Exception as exc:
            # Handle error and log it.
            SecurityAwareErrorHandler().log_processing_error(exc, "initialize_detectors_lazy")
            log_error(f"[STARTUP] Error during detector lazy initialization: {str(exc)}")

    async def _lazy_init_presidio(self):
        """
        Background-thread initialization for the Presidio detector.
        """
        log_info("[STARTUP] Lazily initializing Presidio detector...")
        try:
            # Offload initialization to a background thread.
            presidio_detector = await asyncio.to_thread(self._initialize_presidio_detector)
            self._presidio_detector = presidio_detector
            self._initialization_status["presidio"] = True
            log_info("[STARTUP] Presidio detector lazy initialization complete.")
        except Exception as exc:
            # Invoke error handling and log error.
            SecurityAwareErrorHandler().log_processing_error(exc, "_lazy_init_presidio")
            log_error(f"[STARTUP] Error during Presidio lazy initialization: {str(exc)}")

    async def _lazy_init_gemini(self):
        """
        Background-thread initialization for the Gemini detector.
        """
        log_info("[STARTUP] Lazily initializing Gemini detector...")
        try:
            gemini_detector = await asyncio.to_thread(self._initialize_gemini_detector)
            self._gemini_detector = gemini_detector
            self._initialization_status["gemini"] = True
            log_info("[STARTUP] Gemini detector lazy initialization complete.")
        except Exception as exc:
            # Handle and log exception.
            SecurityAwareErrorHandler().log_processing_error(exc, "_lazy_init_gemini")
            log_error(f"[STARTUP] Error during Gemini lazy initialization: {str(exc)}")

    async def _maybe_lazy_init_gliner(self):
        """
        Conditionally initialize the GLiNER detector if memory usage is below a threshold.
        """
        # Check if current memory usage is low enough to allow detector initialization.
        if memory_monitor.get_memory_usage() < 60.0:
            log_info("[STARTUP] Lazily initializing GLiNER detector...")
            try:
                gliner_detector = await asyncio.to_thread(
                    self._initialize_gliner_detector,
                    GLINER_MODEL_NAME,
                    GLINER_AVAILABLE_ENTITIES
                )
                # Create a cache key for the detector.
                cache_key = self._get_gliner_cache_key(GLINER_AVAILABLE_ENTITIES)
                self._gliner_detectors[cache_key] = gliner_detector
                self._initialization_status["gliner"] = True
                log_info("[STARTUP] GLiNER detector lazy initialization complete.")
            except Exception as exc:
                # Handle error and log.
                SecurityAwareErrorHandler().log_processing_error(exc, "_maybe_lazy_init_gliner")
                log_error(f"[STARTUP] Error during GLiNER lazy initialization: {str(exc)}")
        else:
            log_info("[STARTUP] Skipping GLiNER lazy initialization due to memory pressure.")

    # 2) Detector initialization APIs #

    def _initialize_presidio_detector(self):
        """
        Initialize a Presidio detector instance with error handling.

        Returns:
            An instance of the Presidio detector.
        """
        log_info("Initializing Presidio detector")
        start_time = time.time()
        try:
            from backend.app.entity_detection.presidio import PresidioEntityDetector
            detector = PresidioEntityDetector()
            self._initialization_status["presidio"] = True
            log_info(f"Presidio detector initialized in {time.time() - start_time:.2f}s")
            return detector
        except Exception as exc:
            # Update status, handle error, and propagate the exception.
            self._initialization_status["presidio"] = False
            SecurityAwareErrorHandler().log_processing_error(exc, "_initialize_presidio_detector")
            log_error(f"Error initializing Presidio detector: {str(exc)}")
            raise

    def _initialize_gemini_detector(self):
        """
        Initialize a Gemini detector instance with error handling.

        Returns:
            An instance of the Gemini detector.
        """
        log_info("Initializing Gemini detector")
        start_time = time.time()
        try:
            from backend.app.entity_detection.gemini import GeminiEntityDetector
            detector = GeminiEntityDetector()
            self._initialization_status["gemini"] = True
            log_info(f"Gemini detector initialized in {time.time() - start_time:.2f}s")
            return detector
        except Exception as exc:
            # Handle error and update initialization status.
            self._initialization_status["gemini"] = False
            SecurityAwareErrorHandler().log_processing_error(exc, "_initialize_gemini_detector")
            log_error(f"Error initializing Gemini detector: {str(exc)}")
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
        log_info(f"Initializing GLiNER detector with model {model_name} for entities: {entities}")
        start_time = time.time()
        try:
            detector = GlinerEntityDetector(
                model_name=model_name,
                entities=entities or GLINER_AVAILABLE_ENTITIES,
                local_model_path=GLINER_MODEL_PATH
            )
            self._initialization_status["gliner"] = True
            log_info(f"GLiNER detector initialized in {time.time() - start_time:.2f}s")
            return detector
        except Exception as exc:
            self._initialization_status["gliner"] = False
            SecurityAwareErrorHandler().log_processing_error(exc, "_initialize_gliner_detector")
            log_error(f"Error initializing GLiNER detector: {str(exc)}")
            raise

    def _initialize_hybrid_detector(self, config: Dict[str, Any]):
        """
        Initialize a hybrid detector instance with error handling.

        Args:
            config (Dict[str, Any]): Configuration for the hybrid detector.

        Returns:
            An instance of the hybrid detector.
        """
        log_info(f"Initializing Hybrid detector with config: {config}")
        start_time = time.time()
        try:
            from backend.app.entity_detection.hybrid import HybridEntityDetector
            detector = HybridEntityDetector(config)
            self._initialization_status["hybrid"] = True
            log_info(f"Hybrid detector initialized in {time.time() - start_time:.2f}s")
            return detector
        except Exception as exc:
            self._initialization_status["hybrid"] = False
            SecurityAwareErrorHandler().log_processing_error(exc, "_initialize_hybrid_detector")
            log_error(f"Error initializing Hybrid detector: {str(exc)}")
            raise

    # 3) Public "get" methods (sync/async) #

    def get_presidio_detector(self):
        """
        Retrieve a Presidio detector instance with basic thread safety.

        Returns:
            The Presidio detector instance.
        """
        return self.get_detector(EntityDetectionEngine.PRESIDIO)

    def get_gemini_detector(self):
        """
        Retrieve a Gemini detector instance with basic thread safety.

        Returns:
            The Gemini detector instance.
        """
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
        config = {"entities": entities or GLINER_AVAILABLE_ENTITIES}
        return self.get_detector(EntityDetectionEngine.GLINER, config)

    # 4) Main "get_detector" logic  #

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
        if config is None:
            config = {}

        # Step 1: Quick cache check.
        maybe_cached = self._quick_check_cache(engine, config)
        if maybe_cached is not None:
            return maybe_cached

        # Step 2: Attempt to acquire the lock for a secondary cache check.
        if self._try_acquire_lock(0.5):
            try:
                rechecked = self._quick_check_cache(engine, config)
                if rechecked is not None:
                    return rechecked
            finally:
                self._lock.release()
        else:
            log_warning("[WARNING] Timeout acquiring lock for quick cache check")

        # Step 3: Acquire lock to either initialize or retrieve the detector.
        if self._try_acquire_lock(1.0):
            try:
                final_cached = self._quick_check_cache(engine, config)
                if final_cached is not None:
                    return final_cached
                return self._initialize_and_store_detector(engine, config)
            finally:
                self._lock.release()
        else:
            log_warning("[WARNING] Timeout acquiring lock for detector initialization")

        # Step 4: Fallback initialization if lock acquisition fails.
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
        if engine == EntityDetectionEngine.PRESIDIO and self._presidio_detector:
            self._update_usage_metrics_no_lock("presidio")
            return self._presidio_detector
        if engine == EntityDetectionEngine.GEMINI and self._gemini_detector:
            self._update_usage_metrics_no_lock("gemini")
            return self._gemini_detector
        if engine == EntityDetectionEngine.GLINER:
            key = self._get_gliner_cache_key(config.get("entities", []))
            if key in self._gliner_detectors:
                self._update_usage_metrics_no_lock(f"gliner_{key}")
                return self._gliner_detectors[key]
        if engine == EntityDetectionEngine.HYBRID:
            key = self._get_hybrid_cache_key(config)
            if key in self._hybrid_detectors:
                return self._hybrid_detectors[key]
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
            return self._lock.acquire(timeout=timeout)
        except TimeoutError:
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
        if engine in (EntityDetectionEngine.PRESIDIO, EntityDetectionEngine.GEMINI):
            return self._initialize_presidio_or_gemini(engine)
        elif engine == EntityDetectionEngine.GLINER:
            return self._initialize_gliner(config)
        elif engine == EntityDetectionEngine.HYBRID:
            return self._initialize_hybrid(config)
        else:
            raise ValueError(f"Unsupported detection engine: {engine}")

    def _initialize_presidio_or_gemini(self, engine: EntityDetectionEngine) -> Any:
        """
        Initialize a Presidio or Gemini detector, store it in cache, and update usage metrics.

        Args:
            engine (EntityDetectionEngine): The detection engine type.

        Returns:
            The detector instance.
        """
        if engine == EntityDetectionEngine.PRESIDIO:
            if self._presidio_detector:
                self._update_usage_metrics_no_lock("presidio")
                return self._presidio_detector
            new_det = self._initialize_presidio_detector()
            self._presidio_detector = new_det
            self._update_usage_metrics_no_lock("presidio")
            return new_det
        else:  # engine == EntityDetectionEngine.GEMINI
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
        entities = config.get("entities", [])
        cache_key = self._get_gliner_cache_key(entities)
        if cache_key in self._gliner_detectors:
            self._update_usage_metrics_no_lock(f"gliner_{cache_key}")
            return self._gliner_detectors[cache_key]

        model_name = config.get("model_name", GLINER_MODEL_NAME)
        new_det = self._initialize_gliner_detector(model_name, entities)
        # Check if cache size exceeds max limit; if so, evict the least recently used detector.
        if len(self._gliner_detectors) >= self.max_cache_size:
            self._evict_least_recently_used("gliner")

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
        cache_key = self._get_hybrid_cache_key(config)
        if cache_key in self._hybrid_detectors:
            return self._hybrid_detectors[cache_key]

        new_det = self._initialize_hybrid_detector(config)
        # Evict least recently used hybrid detector if cache is full.
        if len(self._hybrid_detectors) >= self.max_cache_size:
            self._evict_least_recently_used("hybrid")

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
        log_warning("Timeout acquiring detector lock - proceeding with fallback initialization")

        if engine == EntityDetectionEngine.PRESIDIO:
            if self._presidio_detector:
                return self._presidio_detector
            return self._initialize_presidio_detector()

        if engine == EntityDetectionEngine.GEMINI:
            if self._gemini_detector:
                return self._gemini_detector
            return self._initialize_gemini_detector()

        if engine == EntityDetectionEngine.GLINER:
            key = self._get_gliner_cache_key(config.get("entities", []))
            if key in self._gliner_detectors:
                return self._gliner_detectors[key]
            model_name = config.get("model_name", GLINER_MODEL_NAME)
            return self._initialize_gliner_detector(model_name, config.get("entities", []))

        if engine == EntityDetectionEngine.HYBRID:
            key = self._get_hybrid_cache_key(config)
            if key in self._hybrid_detectors:
                return self._hybrid_detectors[key]
            return self._initialize_hybrid_detector(config)

        raise ValueError(f"Unsupported detection engine: {engine}")

    # 5) Usage metrics & LRU eviction     #

    def _increment_usage_metrics(self, detector_key: str, current_time: float):
        """
        Increment usage metrics for a given detector.

        Args:
            detector_key (str): Key identifying the detector.
            current_time (float): The current timestamp.
        """
        if detector_key.startswith("gliner_"):
            self._usage_metrics.setdefault("gliner", {})
            self._usage_metrics["gliner"].setdefault(detector_key, {"uses": 0, "last_used": None})
            self._usage_metrics["gliner"][detector_key]["uses"] += 1
            self._usage_metrics["gliner"][detector_key]["last_used"] = current_time
        else:
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
        current_time = time.time()
        try:
            self._increment_usage_metrics(detector_key, current_time)
        except Exception as exc:
            # Log non-critical errors without interrupting the flow.
            SecurityAwareErrorHandler().log_processing_error(exc, "_update_usage_metrics_no_lock")
            log_warning(f"Exception in updating usage metrics (non-critical): {exc}")

    def _evict_least_recently_used(self, detector_type: str):
        """
        Evict the least recently used detector from the cache based on usage metrics.

        Args:
            detector_type (str): Cache type ("gliner" or "hybrid").
        """
        if detector_type == "gliner":
            lru_key = None
            oldest_time = float('inf')
            # Iterate over the GLiNER usage metrics to find the least recently used detector.
            for key, metrics in self._usage_metrics.get("gliner", {}).items():
                if metrics and metrics.get("last_used", float('inf')) < oldest_time:
                    oldest_time = metrics.get("last_used", float('inf'))
                    lru_key = key.replace("gliner_", "")
            if lru_key and lru_key in self._gliner_detectors:
                log_info(f"Evicting least recently used GLiNER detector: {lru_key}")
                del self._gliner_detectors[lru_key]
        elif detector_type == "hybrid":
            if not self._hybrid_detectors:
                return
            # For hybrid, simply evict the first one found in the cache.
            lru_key = next(iter(self._hybrid_detectors))
            log_info("Evicting hybrid detector from cache")
            del self._hybrid_detectors[lru_key]

    # 6) Cache key helper methods  #

    @staticmethod
    def _get_gliner_cache_key(entities: List[str]) -> str:
        """
        Generate a cache key for GLiNER detector based on a sorted list of entities.

        Args:
            entities (List[str]): List of entity types.

        Returns:
            A string to be used as a cache key.
        """
        if not entities:
            return "default"
        sorted_entities = sorted(entities)
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
        use_presidio = config.get("use_presidio", True)
        use_gemini = config.get("use_gemini", False)
        use_gliner = config.get("use_gliner", False)
        entities = config.get("entities", [])
        sorted_entities = sorted(entities) if entities else []
        entities_str = "_".join(sorted_entities) if sorted_entities else "none"
        return f"p{int(use_presidio)}_g{int(use_gemini)}_gl{int(use_gliner)}_{entities_str}"

    # 7) Additional Public APIs       #

    def get_initialization_status(self) -> Dict[str, bool]:
        """
        Retrieve the initialization status for all detectors.

        Returns:
            A dictionary mapping each detector type to its initialization status.
        """
        try:
            if self._lock.acquire(timeout=1.0):
                try:
                    return dict(self._initialization_status)
                finally:
                    self._lock.release()
            else:
                return dict(self._initialization_status)
        except Exception as exc:
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
            if self._lock.acquire(timeout=1.0):
                try:
                    metrics_copy = {
                        "presidio": dict(self._usage_metrics.get("presidio", {})),
                        "gemini": dict(self._usage_metrics.get("gemini", {})),
                    }
                    if "gliner" in self._usage_metrics:
                        metrics_copy["gliner"] = {
                            key: dict(val)
                            for key, val in self._usage_metrics["gliner"].items()
                        }
                    return metrics_copy
                finally:
                    self._lock.release()
            else:
                return {"presidio": {}, "gemini": {}, "gliner": {}}
        except Exception as exc:
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
            if self._lock.acquire(timeout=2.0):
                try:
                    cache_size = (
                            (1 if self._presidio_detector else 0) +
                            (1 if self._gemini_detector else 0) +
                            len(self._gliner_detectors) +
                            len(self._hybrid_detectors)
                    )
                    return {
                        "health": "ok",
                        "timestamp": datetime.now().isoformat(),
                        "cache_size": cache_size,
                        "max_cache_size": self.max_cache_size,
                        "detectors": dict(self._initialization_status)
                    }
                finally:
                    self._lock.release()
            else:
                return {
                    "health": "limited",
                    "timestamp": datetime.now().isoformat(),
                    "cache_size": -1,
                    "max_cache_size": self.max_cache_size,
                    "detectors": dict(self._initialization_status),
                    "error": "Lock acquisition timeout"
                }
        except Exception as exc:
            SecurityAwareErrorHandler().log_processing_error(exc, "check_health")
            log_error(f"Error checking health: {str(exc)}")
            return {
                "health": "error",
                "timestamp": datetime.now().isoformat(),
                "error": str(exc)
            }


# Create a singleton instance of InitializationService.
initialization_service = InitializationService()
