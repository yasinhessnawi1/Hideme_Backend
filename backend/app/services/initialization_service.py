"""
Enhanced model initialization service with improved thread safety.
This service manages the initialization and caching of detection engines
with improved synchronization using a basic lock (acquire/release)
for concurrent access.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, List

from backend.app.configs.config_singleton import get_config
from backend.app.configs.gdpr_config import MAX_DETECTOR_CACHE_SIZE
from backend.app.configs.gliner_config import GLINER_MODEL_NAME, GLINER_AVAILABLE_ENTITIES, GLINER_MODEL_PATH
from backend.app.entity_detection import EntityDetectionEngine
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.synchronization_utils import TimeoutLock, LockPriority, AsyncTimeoutLock

# Configure logger
logger = logging.getLogger(__name__)


class InitializationService:
    """
    Service for initializing and caching ML models and detectors with improved thread safety.

    Features:
    - Thread-safe detector initialization and retrieval using basic lock acquire/release
    - Detector cache with LRU eviction policy for memory management
    - Performance metrics tracking for detector usage
    - Health check reporting for monitoring
    """

    def __init__(self, max_cache_size: int = None):
        """
        Initialize the service with detector caching and basic synchronization.

        Args:
            max_cache_size: Maximum number of cached detectors (from config or default).
        """
        self.max_cache_size = max_cache_size or get_config("max_detector_cache_size", MAX_DETECTOR_CACHE_SIZE)

        # Locks for synchronization
        self._lock = TimeoutLock("detector_cache_lock", priority=LockPriority.HIGH, timeout=15.0)
        self._async_lock = AsyncTimeoutLock("detector_async_lock", priority=LockPriority.HIGH, timeout=15.0)

        # Track initialization status for each detector type
        self._initialization_status: Dict[str, bool] = {
            "presidio": False,
            "gemini": False,
            "gliner": False,
            "hybrid": False
        }

        # Detector caches
        self._presidio_detector = None
        self._gemini_detector = None
        self._gliner_detectors: Dict[str, Any] = {}  # entity-lists -> detector
        self._hybrid_detectors: Dict[str, Any] = {}  # config -> detector

        # Usage metrics for monitoring and analytics
        self._usage_metrics: Dict[str, Any] = {
            "presidio": {"uses": 0, "last_used": None},
            "gemini": {"uses": 0, "last_used": None},
            "gliner": {}  # key -> { "uses": int, "last_used": float }
        }

        log_info(f"Initialization service started with max cache size: {self.max_cache_size}")

    # 1) Lazy initialization methods  #

    async def initialize_detectors_lazy(self):
        """
        Lazily initialize detectors at application startup without blocking other services.
        Splits out the logic for Presidio, Gemini, and GLiNER.
        """
        log_info("[STARTUP] Starting lazy initialization of detectors...")
        try:
            await self._lazy_init_presidio()
            await asyncio.sleep(1.0)
            await self._lazy_init_gemini()
            await self._maybe_lazy_init_gliner()
            log_info("[STARTUP] Lazy initialization of detectors completed successfully.")
        except Exception as exc:
            log_error(f"[STARTUP] Error during detector lazy initialization: {str(exc)}")

    async def _lazy_init_presidio(self):
        """Background-thread initialization for Presidio."""
        log_info("[STARTUP] Lazily initializing Presidio detector...")
        try:
            presidio_detector = await asyncio.to_thread(self._initialize_presidio_detector)
            self._presidio_detector = presidio_detector
            self._initialization_status["presidio"] = True
            log_info("[STARTUP] Presidio detector lazy initialization complete.")
        except Exception as exc:
            log_error(f"[STARTUP] Error during Presidio lazy initialization: {str(exc)}")

    async def _lazy_init_gemini(self):
        """Background-thread initialization for Gemini."""
        log_info("[STARTUP] Lazily initializing Gemini detector...")
        try:
            gemini_detector = await asyncio.to_thread(self._initialize_gemini_detector)
            self._gemini_detector = gemini_detector
            self._initialization_status["gemini"] = True
            log_info("[STARTUP] Gemini detector lazy initialization complete.")
        except Exception as exc:
            log_error(f"[STARTUP] Error during Gemini lazy initialization: {str(exc)}")

    async def _maybe_lazy_init_gliner(self):
        """
        Conditionally initialize GLiNER if memory usage is low enough.
        """
        from backend.app.utils.memory_management import memory_monitor
        if memory_monitor.get_memory_usage() < 60.0:
            log_info("[STARTUP] Lazily initializing GLiNER detector...")
            try:
                gliner_detector = await asyncio.to_thread(
                    self._initialize_gliner_detector,
                    GLINER_MODEL_NAME,
                    GLINER_AVAILABLE_ENTITIES
                )
                cache_key = self._get_gliner_cache_key(GLINER_AVAILABLE_ENTITIES)
                self._gliner_detectors[cache_key] = gliner_detector
                self._initialization_status["gliner"] = True
                log_info("[STARTUP] GLiNER detector lazy initialization complete.")
            except Exception as exc:
                log_error(f"[STARTUP] Error during GLiNER lazy initialization: {str(exc)}")
        else:
            log_info("[STARTUP] Skipping GLiNER lazy initialization due to memory pressure.")

    # 2) Detector initialization APIs #

    def _initialize_presidio_detector(self):
        """
        Initialize a Presidio detector instance with error handling.
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
            self._initialization_status["presidio"] = False
            log_error(f"Error initializing Presidio detector: {str(exc)}")
            raise

    def _initialize_gemini_detector(self):
        """
        Initialize a Gemini detector instance with error handling.
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
            self._initialization_status["gemini"] = False
            log_error(f"Error initializing Gemini detector: {str(exc)}")
            raise

    def _initialize_gliner_detector(self, model_name: str, entities: List[str]):
        """
        Initialize a GLiNER detector instance with error handling.

        Args:
            model_name: Name of the GLiNER model
            entities: List of entity types to detect
        """
        log_info(f"Initializing GLiNER detector with model {model_name} for entities: {entities}")
        start_time = time.time()
        try:
            from backend.app.entity_detection.gliner import GlinerEntityDetector
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
            log_error(f"Error initializing GLiNER detector: {str(exc)}")
            raise

    def _initialize_hybrid_detector(self, config: Dict[str, Any]):
        """
        Initialize a hybrid detector instance with error handling.

        Args:
            config: Configuration for the hybrid detector
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
            log_error(f"Error initializing Hybrid detector: {str(exc)}")
            raise

    # 3) Public "get" methods (sync/async)#

    def get_presidio_detector(self):
        """Get a Presidio detector instance with basic thread safety."""
        return self.get_detector(EntityDetectionEngine.PRESIDIO)

    def get_gemini_detector(self):
        """Get a Gemini detector instance with basic thread safety."""
        return self.get_detector(EntityDetectionEngine.GEMINI)

    def get_gliner_detector(self, entities: Optional[List[str]] = None):
        """
        Get a GLiNER detector instance for specific entities with basic thread safety.
        """
        config = {"entities": entities or GLINER_AVAILABLE_ENTITIES}
        return self.get_detector(EntityDetectionEngine.GLINER, config)

    def get_hybrid_detector(self, config: Optional[Dict[str, Any]] = None):
        """Get a hybrid detector instance with basic thread safety."""
        return self.get_detector(EntityDetectionEngine.HYBRID, config or {})

    # 4) Main "get_detector" logic  #

    def get_detector(self, engine: EntityDetectionEngine, config: Optional[Dict[str, Any]] = None):
        """
        Get a detector instance for the specified engine with basic lock management.
        """
        if config is None:
            config = {}

        # Step 1: Quick check
        maybe_cached = self._quick_check_cache(engine, config)
        if maybe_cached is not None:
            return maybe_cached

        # Step 2: Attempt to acquire lock for a second check
        if self._try_acquire_lock(0.5):
            try:
                rechecked = self._quick_check_cache(engine, config)
                if rechecked is not None:
                    return rechecked
            finally:
                self._lock.release()
        else:
            log_warning("[WARNING] Timeout acquiring lock for quick cache check")

        # Step 3: Acquire lock to initialize or retrieve
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

        # Step 4: Fallback if lock fails
        return self._fallback_init(engine, config)

    def _quick_check_cache(self, engine: EntityDetectionEngine, config: Dict[str, Any]) -> Optional[Any]:
        """Quickly check if a cached instance already exists, updating usage if found."""
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
        """Attempt to acquire the main lock within a given timeout."""
        try:
            return self._lock.acquire(timeout=timeout)
        except TimeoutError:
            return False

    def _initialize_and_store_detector(self, engine: EntityDetectionEngine, config: Dict[str, Any]) -> Any:
        """
        Initialize the requested detector under lock and store it in the appropriate cache.

        This method delegates the actual initialization to smaller helper methods based
        on the specified engine. Each helper checks whether the detector is already in
        memory, initializes if necessary, updates usage metrics, and returns the instance.
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
        Handle initialization for Presidio or Gemini detectors.
        If the detector is already in memory, returns it; otherwise, initializes, stores, and returns.
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
        Handle initialization for a GLiNER detector.
        Checks for an existing cache entry; if missing, initializes a new detector,
        evicts if the cache is full, updates usage, then returns it.
        """
        entities = config.get("entities", [])
        cache_key = self._get_gliner_cache_key(entities)
        if cache_key in self._gliner_detectors:
            self._update_usage_metrics_no_lock(f"gliner_{cache_key}")
            return self._gliner_detectors[cache_key]

        model_name = config.get("model_name", GLINER_MODEL_NAME)
        new_det = self._initialize_gliner_detector(model_name, entities)
        if len(self._gliner_detectors) >= self.max_cache_size:
            self._evict_least_recently_used("gliner")

        self._gliner_detectors[cache_key] = new_det
        self._update_usage_metrics_no_lock(f"gliner_{cache_key}")
        return new_det

    def _initialize_hybrid(self, config: Dict[str, Any]) -> Any:
        """
        Handle initialization for a Hybrid detector.
        Checks for an existing cache entry; if missing, initializes a new detector,
        evicts if the cache is full, then returns it.
        """
        cache_key = self._get_hybrid_cache_key(config)
        if cache_key in self._hybrid_detectors:
            return self._hybrid_detectors[cache_key]

        new_det = self._initialize_hybrid_detector(config)
        if len(self._hybrid_detectors) >= self.max_cache_size:
            self._evict_least_recently_used("hybrid")

        self._hybrid_detectors[cache_key] = new_det
        return new_det

    def _fallback_init(self, engine: EntityDetectionEngine, config: Dict[str, Any]) -> Any:
        """
        Fallback initialization if locks cannot be acquired.
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
        Helper method to increment usage metrics for a detector.
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
        Update usage metrics for a detector without acquiring a lock.
        Used for high-traffic scenarios where contention should be avoided.
        """
        current_time = time.time()
        try:
            self._increment_usage_metrics(detector_key, current_time)
        except Exception as exc:
            log_warning(f"Exception in updating usage metrics (non-critical): {exc}")

    def _evict_least_recently_used(self, detector_type: str):
        """
        Evict the least recently used detector from the cache.

        Args:
            detector_type: Type of detector cache to evict from ("gliner" or "hybrid")
        """
        if detector_type == "gliner":
            lru_key = None
            oldest_time = float('inf')
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
            lru_key = next(iter(self._hybrid_detectors))
            log_info("Evicting hybrid detector from cache")
            del self._hybrid_detectors[lru_key]

    # 6) Cache key helper methods  #

    @staticmethod
    def _get_gliner_cache_key(entities: List[str]) -> str:
        """
        Generate a cache key for GLiNER detector based on entities.

        Args:
            entities: List of entity types
        """
        if not entities:
            return "default"
        sorted_entities = sorted(entities)
        return "_".join(sorted_entities)

    @staticmethod
    def _get_hybrid_cache_key(config: Dict[str, Any]) -> str:
        """
        Generate a cache key for hybrid detector based on configuration.

        Args:
            config: Detector configuration
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
        Get the initialization status for all detectors.

        Returns:
            Dictionary mapping detector types to their initialization status
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
            log_warning(f"Lock acquisition failed in get_initialization_status: {str(exc)}")
            return dict(self._initialization_status)

    def get_usage_metrics(self) -> Dict[str, Any]:
        """
        Get usage metrics for all detectors.

        Returns:
            Dictionary with detector usage statistics
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
            log_error(f"Error getting usage metrics: {str(exc)}")
            return {"presidio": {}, "gemini": {}, "gliner": {}}

    def check_health(self) -> Dict[str, Any]:
        """
        Check the health status of all detector caches.

        Returns:
            Dictionary with health information
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
            log_error(f"Error checking health: {str(exc)}")
            return {
                "health": "error",
                "timestamp": datetime.now().isoformat(),
                "error": str(exc)
            }

# Create a singleton instance
initialization_service = InitializationService()