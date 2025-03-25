"""
Enhanced model initialization service with improved thread safety.

This service manages the initialization and caching of detection engines
with improved synchronization using ReadWriteLock for concurrent reads
but exclusive writes during detector initialization.
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, List

from backend.app.configs.config_singleton import get_config
from backend.app.configs.gdpr_config import MAX_DETECTOR_CACHE_SIZE
from backend.app.configs.gliner_config import GLINER_MODEL_NAME, GLINER_ENTITIES, GLINER_MODEL_PATH
from backend.app.factory.document_processing_factory import EntityDetectionEngine
from backend.app.utils.logging.logger import log_info, log_warning, log_error
# Keep ReadWriteLock but also import AsyncTimeoutLock
from backend.app.utils.synchronization_utils import TimeoutLock, LockPriority, AsyncTimeoutLock

# Configure logger
logger = logging.getLogger(__name__)


class InitializationService:
    """
    Service for initializing and caching ML models and detectors with improved thread safety.

    Features:
    - Thread-safe detector initialization and retrieval
    - ReadWriteLock for allowing concurrent reads but exclusive writes
    - Detector cache with LRU eviction policy for memory management
    - Performance metrics tracking for detector usage
    - Health check reporting for monitoring
    """

    def __init__(self, max_cache_size: int = None):
        """
        Initialize the service with detector caching and improved synchronization.

        Args:
            max_cache_size: Maximum number of cached detectors (from config or default)
        """
        self.max_cache_size = max_cache_size or get_config("max_detector_cache_size", MAX_DETECTOR_CACHE_SIZE)

        # Keep ReadWriteLock but reduce timeout values
        self._lock = TimeoutLock("detector_cache_lock", priority=LockPriority.HIGH, timeout=15.0)

        # Add AsyncTimeoutLock for async-friendly operations if needed
        self._async_lock = AsyncTimeoutLock("detector_async_lock", priority=LockPriority.HIGH, timeout=15.0)

        # Track initialization status for each detector type
        self._initialization_status = {
            "presidio": False,
            "gemini": False,
            "gliner": False,
            "hybrid": False
        }

        # Detector caches with type-specific storage
        self._presidio_detector = None
        self._gemini_detector = None
        self._gliner_detectors = {}  # Map entity lists to detector instances
        self._hybrid_detectors = {}  # Map configurations to detector instances

        # Cache for performance optimization
        self._detector_cache = {}  # LRU cache mapping detector keys to instances
        self._cache_keys = []  # Ordered list for LRU implementation

        # Usage metrics for monitoring and analytics
        self._usage_metrics = {
            "presidio": {"uses": 0, "last_used": None},
            "gemini": {"uses": 0, "last_used": None},
            "gliner": {}  # Map model_name_entity_type to metrics
        }

        log_info(f"Initialization service started with max cache size: {self.max_cache_size}")

    def _initialize_presidio_detector(self):
        """
        Initialize a Presidio detector instance with enhanced error handling.

        Returns:
            Presidio detector instance
        """
        log_info("Initializing Presidio detector")
        start_time = time.time()

        try:
            from backend.app.entity_detection.presidio import PresidioEntityDetector
            detector = PresidioEntityDetector()

            self._initialization_status["presidio"] = True
            log_info(f"Presidio detector initialized in {time.time() - start_time:.2f}s")
            return detector
        except Exception as e:
            self._initialization_status["presidio"] = False
            log_error(f"Error initializing Presidio detector: {str(e)}")
            raise

    def _initialize_gemini_detector(self):
        """
        Initialize a Gemini detector instance with enhanced error handling.

        Returns:
            Gemini detector instance
        """
        log_info("Initializing Gemini detector")
        start_time = time.time()

        try:
            from backend.app.entity_detection.gemini import GeminiEntityDetector
            detector = GeminiEntityDetector()

            self._initialization_status["gemini"] = True
            log_info(f"Gemini detector initialized in {time.time() - start_time:.2f}s")
            return detector
        except Exception as e:
            self._initialization_status["gemini"] = False
            log_error(f"Error initializing Gemini detector: {str(e)}")
            raise

    def _initialize_gliner_detector(self, model_name: str, entities: List[str]):
        """
        Initialize a GLiNER detector instance with enhanced error handling.

        Args:
            model_name: Name of the GLiNER model
            entities: List of entity types to detect

        Returns:
            GLiNER detector instance
        """
        log_info(f"Initializing GLiNER detector with model {model_name} for entities: {entities}")
        start_time = time.time()

        try:
            from backend.app.entity_detection.gliner import GlinerEntityDetector
            detector = GlinerEntityDetector(
                model_name=model_name,
                entities=entities or GLINER_ENTITIES,
                local_model_path=GLINER_MODEL_PATH
            )

            self._initialization_status["gliner"] = True
            log_info(f"GLiNER detector initialized in {time.time() - start_time:.2f}s")
            return detector
        except Exception as e:
            self._initialization_status["gliner"] = False
            log_error(f"Error initializing GLiNER detector: {str(e)}")
            raise

    # Add this method to the InitializationService class

    async def initialize_detectors_lazy(self):
        """
        Lazily initialize detector instances in the background.

        This method is called during application startup to prepare
        common detectors without blocking the main startup sequence.
        """
        log_info("[STARTUP] Starting lazy initialization of detectors...")

        try:
            # Initialize Presidio detector in background
            log_info("[STARTUP] Lazily initializing Presidio detector...")
            try:
                # We use a separate thread for CPU-bound operations
                presidio_detector = await asyncio.to_thread(self._initialize_presidio_detector)

                # Use a short timeout for lock acquisition to avoid blocking
                with self._lock.write_locked(timeout=1.0):
                    self._presidio_detector = presidio_detector
                    self._initialization_status["presidio"] = True
                    log_info("[STARTUP] Presidio detector lazy initialization complete.")
            except Exception as e:
                log_error(f"[STARTUP] Error during Presidio lazy initialization: {str(e)}")

            # Short delay between initializations to reduce resource contention
            await asyncio.sleep(1.0)

            # Initialize Gemini detector in background
            log_info("[STARTUP] Lazily initializing Gemini detector...")
            try:
                # We use a separate thread for CPU-bound operations
                gemini_detector = await asyncio.to_thread(self._initialize_gemini_detector)

                # Use a short timeout for lock acquisition to avoid blocking
                with self._lock.write_locked(timeout=1.0):
                    self._gemini_detector = gemini_detector
                    self._initialization_status["gemini"] = True
                    log_info("[STARTUP] Gemini detector lazy initialization complete.")
            except Exception as e:
                log_error(f"[STARTUP] Error during Gemini lazy initialization: {str(e)}")

            # Only initialize GLiNER if we have enough memory available
            from backend.app.utils.memory_management import memory_monitor
            if memory_monitor.get_memory_usage() < 60.0:  # Only if under 60% memory usage
                log_info("[STARTUP] Lazily initializing GLiNER detector...")
                try:
                    # We use a separate thread for CPU-bound operations
                    entities = GLINER_ENTITIES
                    model_name = GLINER_MODEL_NAME
                    gliner_detector = await asyncio.to_thread(
                        self._initialize_gliner_detector,
                        model_name,
                        entities
                    )

                    # Use a short timeout for lock acquisition to avoid blocking
                    with self._lock.write_locked(timeout=1.0):
                        cache_key = self._get_gliner_cache_key(entities)
                        self._gliner_detectors[cache_key] = gliner_detector
                        self._initialization_status["gliner"] = True
                        log_info("[STARTUP] GLiNER detector lazy initialization complete.")
                except Exception as e:
                    log_error(f"[STARTUP] Error during GLiNER lazy initialization: {str(e)}")
            else:
                log_info("[STARTUP] Skipping GLiNER lazy initialization due to memory pressure.")

            log_info("[STARTUP] Lazy initialization of detectors completed successfully.")
        except Exception as e:
            log_error(f"[STARTUP] Error during detector lazy initialization: {str(e)}")

    def _initialize_hybrid_detector(self, config: Dict[str, Any]):
        """
        Initialize a hybrid detector instance with enhanced error handling.

        Args:
            config: Configuration for the hybrid detector

        Returns:
            Hybrid detector instance
        """
        log_info(f"Initializing Hybrid detector with config: {config}")
        start_time = time.time()

        try:
            from backend.app.entity_detection.hybrid import HybridEntityDetector
            detector = HybridEntityDetector(config)

            self._initialization_status["hybrid"] = True
            log_info(f"Hybrid detector initialized in {time.time() - start_time:.2f}s")
            return detector
        except Exception as e:
            self._initialization_status["hybrid"] = False
            log_error(f"Error initializing Hybrid detector: {str(e)}")
            raise

    # Update the initialization_service.py - focusing on key methods with lock issues

    # Update in initialization_service.py

    def get_detector(self, engine: EntityDetectionEngine, config: Optional[Dict[str, Any]] = None):
        """
        Get a detector instance for the specified engine with improved lock management.

        Args:
            engine: The detection engine to use
            config: Optional engine-specific configuration

        Returns:
            The detector instance
        """
        # First try a very quick check without any lock
        if engine == EntityDetectionEngine.PRESIDIO and self._presidio_detector:
            self._update_usage_metrics_no_lock("presidio")
            return self._presidio_detector

        elif engine == EntityDetectionEngine.GEMINI and self._gemini_detector:
            self._update_usage_metrics_no_lock("gemini")
            return self._gemini_detector

        elif engine == EntityDetectionEngine.GLINER:
            entities = config.get("entities", []) if isinstance(config, dict) else []
            cache_key = self._get_gliner_cache_key(entities)
            if cache_key in self._gliner_detectors:
                self._update_usage_metrics_no_lock(f"gliner_{cache_key}")
                return self._gliner_detectors[cache_key]

        elif engine == EntityDetectionEngine.HYBRID:
            cache_key = self._get_hybrid_cache_key(config or {})
            if cache_key in self._hybrid_detectors:
                return self._hybrid_detectors[cache_key]
        log_info(f"Creating hybrid detector with config: {config}")

        # Use TimeoutLock with acquire() instead of read_locked/write_locked
        try:
            # Try with lock for cache check
            acquired = self._lock.acquire(timeout=0.5)
            if not acquired:
                log_warning("[WARNING] Timeout acquiring lock for detector check")
            else:
                try:
                    # Double-check cache after acquiring lock
                    if engine == EntityDetectionEngine.PRESIDIO and self._presidio_detector:
                        self._update_usage_metrics_no_lock("presidio")
                        return self._presidio_detector

                    elif engine == EntityDetectionEngine.GEMINI and self._gemini_detector:
                        self._update_usage_metrics_no_lock("gemini")
                        return self._gemini_detector

                    elif engine == EntityDetectionEngine.GLINER:
                        entities = config.get("entities", []) if isinstance(config, dict) else []
                        cache_key = self._get_gliner_cache_key(entities)
                        if cache_key in self._gliner_detectors:
                            self._update_usage_metrics_no_lock(f"gliner_{cache_key}")
                            return self._gliner_detectors[cache_key]

                    elif engine == EntityDetectionEngine.HYBRID:
                        cache_key = self._get_hybrid_cache_key(config or {})
                        if cache_key in self._hybrid_detectors:
                            return self._hybrid_detectors[cache_key]
                finally:
                    self._lock.release()

            # We need to initialize a detector - try with lock but with short timeout
            acquired = self._lock.acquire(timeout=1.0)
            if not acquired:
                log_warning("[WARNING] Timeout acquiring lock for detector initialization")
            else:
                try:
                    # Triple-check to avoid duplicate initialization
                    if engine == EntityDetectionEngine.PRESIDIO:
                        if self._presidio_detector:
                            self._update_usage_metrics_no_lock("presidio")
                            return self._presidio_detector

                        detector = self._initialize_presidio_detector()
                        self._presidio_detector = detector
                        self._initialization_status["presidio"] = True
                        self._update_usage_metrics_no_lock("presidio")
                        return detector

                    elif engine == EntityDetectionEngine.GEMINI:
                        if self._gemini_detector:
                            self._update_usage_metrics_no_lock("gemini")
                            return self._gemini_detector

                        detector = self._initialize_gemini_detector()
                        self._gemini_detector = detector
                        self._initialization_status["gemini"] = True
                        self._update_usage_metrics_no_lock("gemini")
                        return detector

                    elif engine == EntityDetectionEngine.GLINER:
                        entities = config.get("entities", []) if isinstance(config, dict) else []
                        cache_key = self._get_gliner_cache_key(entities)

                        if cache_key in self._gliner_detectors:
                            self._update_usage_metrics_no_lock(f"gliner_{cache_key}")
                            return self._gliner_detectors[cache_key]

                        model_name = config.get("model_name", GLINER_MODEL_NAME) if isinstance(config,
                                                                                               dict) else GLINER_MODEL_NAME
                        detector = self._initialize_gliner_detector(model_name, entities)

                        # Add to cache with LRU eviction if needed
                        if len(self._gliner_detectors) >= self.max_cache_size:
                            self._evict_least_recently_used("gliner")

                        self._gliner_detectors[cache_key] = detector
                        self._initialization_status["gliner"] = True
                        self._update_usage_metrics_no_lock(f"gliner_{cache_key}")
                        return detector

                    elif engine == EntityDetectionEngine.HYBRID:
                        cache_key = self._get_hybrid_cache_key(config or {})

                        if cache_key in self._hybrid_detectors:
                            return self._hybrid_detectors[cache_key]

                        detector = self._initialize_hybrid_detector(config or {})

                        # Add to cache with LRU eviction if needed
                        if len(self._hybrid_detectors) >= self.max_cache_size:
                            self._evict_least_recently_used("hybrid")

                        self._hybrid_detectors[cache_key] = detector
                        self._initialization_status["hybrid"] = True
                        return detector

                    else:
                        raise ValueError(f"Unsupported detection engine: {engine}")
                finally:
                    self._lock.release()

        except TimeoutError:
            log_warning("Timeout acquiring detector lock - proceeding with fallback initialization")
        except Exception as e:
            log_error(f"Error during detector initialization with locks: {str(e)} - proceeding without lock")

        # If all lock attempts fail, fall back to direct initialization without locks
        try:
            if engine == EntityDetectionEngine.PRESIDIO:
                if self._presidio_detector:
                    return self._presidio_detector
                detector = self._initialize_presidio_detector()
                return detector

            elif engine == EntityDetectionEngine.GEMINI:
                if self._gemini_detector:
                    return self._gemini_detector
                detector = self._initialize_gemini_detector()
                return detector

            elif engine == EntityDetectionEngine.GLINER:
                entities = config.get("entities", []) if isinstance(config, dict) else []
                cache_key = self._get_gliner_cache_key(entities)
                if cache_key in self._gliner_detectors:
                    return self._gliner_detectors[cache_key]

                model_name = config.get("model_name", GLINER_MODEL_NAME) if isinstance(config,
                                                                                       dict) else GLINER_MODEL_NAME
                detector = self._initialize_gliner_detector(model_name, entities)
                return detector

            elif engine == EntityDetectionEngine.HYBRID:
                cache_key = self._get_hybrid_cache_key(config or {})
                if cache_key in self._hybrid_detectors:
                    return self._hybrid_detectors[cache_key]

                detector = self._initialize_hybrid_detector(config or {})
                return detector

            else:
                raise ValueError(f"Unsupported detection engine: {engine}")
        except Exception as e:
            log_error(f"Error during fallback detector initialization: {str(e)}")
            raise

    def _update_usage_metrics_no_lock(self, detector_key: str):
        """
        Update usage metrics for a detector without acquiring a lock.

        This method is used for high-traffic scenarios where contention should be avoided.

        Args:
            detector_key: Identifier for the detector
        """
        current_time = time.time()

        try:
            if detector_key.startswith("gliner_"):
                # GLiNER detector metrics are stored by model+entities key
                if "gliner" not in self._usage_metrics:
                    self._usage_metrics["gliner"] = {}

                if detector_key not in self._usage_metrics["gliner"]:
                    self._usage_metrics["gliner"][detector_key] = {"uses": 0, "last_used": None}

                # These operations are reasonably atomic
                self._usage_metrics["gliner"][detector_key]["uses"] += 1
                self._usage_metrics["gliner"][detector_key]["last_used"] = current_time
            else:
                # Standard detector metrics
                if detector_key in self._usage_metrics:
                    self._usage_metrics[detector_key]["uses"] += 1
                    self._usage_metrics[detector_key]["last_used"] = current_time
        except Exception:
            # Truly ignore failures for non-critical metrics
            pass

    def get_presidio_detector(self):
        """
        Get a Presidio detector instance with improved thread safety.

        Returns:
            Presidio detector instance
        """
        return self.get_detector(EntityDetectionEngine.PRESIDIO)

    def get_gemini_detector(self):
        """
        Get a Gemini detector instance with improved thread safety.

        Returns:
            Gemini detector instance
        """
        return self.get_detector(EntityDetectionEngine.GEMINI)

    def get_gliner_detector(self, entities: Optional[List[str]] = None):
        """
        Get a GLiNER detector instance for specific entities with improved thread safety.

        Args:
            entities: List of entity types to detect

        Returns:
            GLiNER detector instance configured for the specified entities
        """
        config = {"entities": entities or GLINER_ENTITIES}
        return self.get_detector(EntityDetectionEngine.GLINER, config)

    def get_hybrid_detector(self, config: Optional[Dict[str, Any]] = None):
        """
        Get a hybrid detector instance with improved thread safety.

        Args:
            config: Configuration for the hybrid detector

        Returns:
            Hybrid detector instance
        """
        return self.get_detector(EntityDetectionEngine.HYBRID, config)

    # Add an async version for async contexts
    async def get_detector_async(self, engine: EntityDetectionEngine, config: Optional[Dict[str, Any]] = None):
        """
        Async version of get_detector for use in async contexts.

        Args:
            engine: The detection engine to use
            config: Optional engine-specific configuration

        Returns:
            The detector instance
        """
        # For lightweight operations, we can just use the sync version
        try:
            return self.get_detector(engine, config)
        except Exception as e:
            log_error(f"Error in sync detector access, trying async approach: {str(e)}")
            # Fall back to async implementation if needed

            async with self._async_lock.acquire_timeout(timeout=5.0):
                # Mirror the sync implementation but using async patterns
                if engine == EntityDetectionEngine.PRESIDIO:
                    if self._presidio_detector:
                        self._update_usage_metrics("presidio")
                        return self._presidio_detector

                    # Use asyncio.to_thread for CPU-bound initialization
                    detector = await asyncio.to_thread(self._initialize_presidio_detector)
                    self._presidio_detector = detector
                    self._initialization_status["presidio"] = True
                    self._update_usage_metrics("presidio")
                    return detector

                # Similar implementations for other detector types...
                elif engine == EntityDetectionEngine.GEMINI:
                    if self._gemini_detector:
                        self._update_usage_metrics("gemini")
                        return self._gemini_detector

                    detector = await asyncio.to_thread(self._initialize_gemini_detector)
                    self._gemini_detector = detector
                    self._initialization_status["gemini"] = True
                    self._update_usage_metrics("gemini")
                    return detector

                # And so on for the other engines...
                else:
                    # Fall back to synchronous implementation
                    return self.get_detector(engine, config)

    async def get_presidio_detector_async(self):
        """Async version of get_presidio_detector."""
        return await self.get_detector_async(EntityDetectionEngine.PRESIDIO)

    async def get_gemini_detector_async(self):
        """Async version of get_gemini_detector."""
        return await self.get_detector_async(EntityDetectionEngine.GEMINI)

    async def get_gliner_detector_async(self, entities: Optional[List[str]] = None):
        """Async version of get_gliner_detector."""
        config = {"entities": entities or GLINER_ENTITIES}
        return await self.get_detector_async(EntityDetectionEngine.GLINER, config)

    async def get_hybrid_detector_async(self, config: Optional[Dict[str, Any]] = None):
        """Async version of get_hybrid_detector."""
        return await self.get_detector_async(EntityDetectionEngine.HYBRID, config)

    def _evict_least_recently_used(self, detector_type: str):
        """
        Evict the least recently used detector from the cache.

        Args:
            detector_type: Type of detector cache to evict from (gliner, hybrid)
        """
        if detector_type == "gliner":
            # Find LRU GLiNER detector
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
            # Find LRU hybrid detector by key
            if not self._hybrid_detectors:
                return

            # Simple approach - just remove the first one (chronological)
            lru_key = next(iter(self._hybrid_detectors))
            log_info(f"Evicting hybrid detector from cache")
            del self._hybrid_detectors[lru_key]

    def _update_usage_metrics(self, detector_key: str):
        """
        Update usage metrics for a detector.

        Args:
            detector_key: Identifier for the detector
        """
        current_time = time.time()

        try:
            # Use a more aggressive timeout for this non-critical operation
            with self._lock.write_locked(timeout=0.5):  # Very short timeout for stats update
                if detector_key.startswith("gliner_"):
                    # GLiNER detector metrics are stored by model+entities key
                    if "gliner" not in self._usage_metrics:
                        self._usage_metrics["gliner"] = {}

                    if detector_key not in self._usage_metrics["gliner"]:
                        self._usage_metrics["gliner"][detector_key] = {"uses": 0, "last_used": None}

                    self._usage_metrics["gliner"][detector_key]["uses"] += 1
                    self._usage_metrics["gliner"][detector_key]["last_used"] = current_time
                else:
                    # Standard detector metrics
                    if detector_key in self._usage_metrics:
                        self._usage_metrics[detector_key]["uses"] += 1
                        self._usage_metrics[detector_key]["last_used"] = current_time
        except TimeoutError:
            # Non-critical operation, can be skipped if lock acquisition fails
            log_warning(f"Timeout updating usage metrics for {detector_key}")

            # Try updating without lock for non-critical metrics
            try:
                if detector_key.startswith("gliner_"):
                    if "gliner" in self._usage_metrics and detector_key in self._usage_metrics["gliner"]:
                        self._usage_metrics["gliner"][detector_key]["uses"] += 1
                        self._usage_metrics["gliner"][detector_key]["last_used"] = current_time
                else:
                    if detector_key in self._usage_metrics:
                        self._usage_metrics[detector_key]["uses"] += 1
                        self._usage_metrics[detector_key]["last_used"] = current_time
            except:
                # Truly ignore failures for non-critical metrics
                pass

    def _get_gliner_cache_key(self, entities: List[str]) -> str:
        """
        Generate a cache key for GLiNER detector based on entities.

        Args:
            entities: List of entity types

        Returns:
            Cache key string
        """
        if not entities:
            return "default"

        # Sort for consistent ordering regardless of input order
        sorted_entities = sorted(entities)
        return "_".join(sorted_entities)

    def _get_hybrid_cache_key(self, config: Dict[str, Any]) -> str:
        """
        Generate a cache key for hybrid detector based on configuration.

        Args:
            config: Detector configuration

        Returns:
            Cache key string
        """
        # Extract key components from config
        use_presidio = config.get("use_presidio", True)
        use_gemini = config.get("use_gemini", False)
        use_gliner = config.get("use_gliner", False)
        entities = config.get("entities", [])

        # Sort entities for consistent key regardless of input order
        sorted_entities = sorted(entities) if entities else []
        entities_str = "_".join(sorted_entities) if sorted_entities else "none"

        return f"p{int(use_presidio)}_g{int(use_gemini)}_gl{int(use_gliner)}_{entities_str}"

    def get_initialization_status(self) -> Dict[str, bool]:
        """
        Get the initialization status for all detectors.

        Returns:
            Dictionary mapping detector types to their initialization status
        """
        try:
            with self._lock.read_locked(timeout=1.0):
                return self._initialization_status.copy()
        except TimeoutError:
            # Return a best-effort copy if lock acquisition fails
            return dict(self._initialization_status)

    def get_usage_metrics(self) -> Dict[str, Any]:
        """
        Get usage metrics for all detectors.

        Returns:
            Dictionary with detector usage statistics
        """
        try:
            with self._lock.read_locked(timeout=1.0):
                metrics_copy = {
                    "presidio": dict(self._usage_metrics["presidio"]),
                    "gemini": dict(self._usage_metrics["gemini"]),
                }

                if "gliner" in self._usage_metrics:
                    metrics_copy["gliner"] = {
                        key: dict(value)
                        for key, value in self._usage_metrics["gliner"].items()
                    }

                return metrics_copy
        except TimeoutError:
            # Return empty metrics if lock acquisition fails
            return {"presidio": {}, "gemini": {}, "gliner": {}}
        except Exception as e:
            log_error(f"Error getting usage metrics: {str(e)}")
            return {"presidio": {}, "gemini": {}, "gliner": {}}

    def check_health(self) -> Dict[str, Any]:
        """
        Check the health status of all detector caches.

        Returns:
            Dictionary with health information
        """
        try:
            with self._lock.read_locked(timeout=2.0):
                cache_size = len(self._gliner_detectors) + len(self._hybrid_detectors) + \
                             (1 if self._presidio_detector else 0) + \
                             (1 if self._gemini_detector else 0)

                return {
                    "health": "ok",
                    "timestamp": datetime.now().isoformat(),
                    "cache_size": cache_size,
                    "max_cache_size": self.max_cache_size,
                    "detectors": self._initialization_status.copy()
                }
        except TimeoutError:
            # Return limited health info if lock acquisition fails
            return {
                "health": "limited",
                "timestamp": datetime.now().isoformat(),
                "cache_size": -1,
                "max_cache_size": self.max_cache_size,
                "detectors": dict(self._initialization_status),
                "error": "Lock acquisition timeout"
            }
        except Exception as e:
            log_error(f"Error checking health: {str(e)}")
            return {
                "health": "error",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }

# Create a singleton instance
initialization_service = InitializationService()