"""
Service for initializing and caching detection engines with improved resource management.

This module provides a thread-safe singleton service that loads entity detection engines
once at startup and provides optimized access to them throughout the application.
"""
import os
import threading
import time
from typing import Dict, Any, Optional, List

from backend.app.configs.gliner_config import GLINER_CONFIG, GLINER_ENTITIES, GLINER_MODEL_PATH
from backend.app.factory.document_processing import (
    DocumentProcessingFactory,
    EntityDetectionEngine
)
from backend.app.utils.logger import default_logger as logger, log_info, log_warning, log_error


class InitializationService:
    """
    Service for initializing and caching entity detectors with improved resource management.

    This service creates and caches instances of entity detectors to avoid
    recreating them on each request, significantly improving performance.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Ensure singleton pattern with thread safety."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(InitializationService, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the service if not already initialized."""
        with self._lock:
            if not getattr(self, '_initialized', False):
                # Initialize detector caches
                self._detectors = {}

                # Cache for hybrid detectors with different configurations
                self._hybrid_detectors = {}

                # Track initialization status
                self._initialization_status = {
                    'presidio': False,
                    'gemini': False,
                    'gliner': False,
                    'hybrid': False
                }

                # Track detector usage
                self._detector_metrics = {
                    'presidio': {'uses': 0, 'last_used': None},
                    'gemini': {'uses': 0, 'last_used': None},
                    'gliner': {'uses': 0, 'last_used': None},
                    'hybrid': {}  # Will contain metrics for different configurations
                }

                # Ensure model directory exists
                os.makedirs(GLINER_CONFIG['local_model_path'], exist_ok=True)

                self._initialized = True
                logger.info("[INIT] Initialization service created")

    def initialize_detectors(self, force_reload: bool = False):
        """
        Initialize all detectors at startup.

        Args:
            force_reload: Whether to force reloading of already initialized detectors
        """
        with self._lock:
            try:
                # Initialize Presidio detector if needed
                if force_reload or 'presidio' not in self._detectors:
                    log_info("[INIT] Initializing Presidio detector...")
                    self._detectors['presidio'] = DocumentProcessingFactory.create_entity_detector(
                        EntityDetectionEngine.PRESIDIO
                    )
                    self._initialization_status['presidio'] = True
                    self._detector_metrics['presidio']['last_used'] = time.time()
                    log_info("[INIT] Presidio detector initialized successfully")

                # Initialize Gemini detector if needed
                if force_reload or 'gemini' not in self._detectors:
                    log_info("[INIT] Initializing Gemini detector...")
                    self._detectors['gemini'] = DocumentProcessingFactory.create_entity_detector(
                        EntityDetectionEngine.GEMINI
                    )
                    self._initialization_status['gemini'] = True
                    self._detector_metrics['gemini']['last_used'] = time.time()
                    log_info("[INIT] Gemini detector initialized successfully")

                # Initialize GLiNER detector if needed
                if force_reload or 'gliner' not in self._detectors:
                    log_info("[INIT] Initializing GLiNER detector...")
                    self._initialize_gliner_detector()

                log_info("[INIT] All detectors initialized")
            except Exception as e:
                log_error(f"[ERROR] Failed to initialize detectors: {e}")
                raise

    def _initialize_gliner_detector(self):
        """
        Initialize the GLiNER detector with the default configuration.
        """
        try:
            log_info("[INIT] Initializing GLiNER detector...")
            start_time = time.time()

            # Check if model file already exists
            if os.path.exists(GLINER_MODEL_PATH) and os.path.getsize(GLINER_MODEL_PATH) > 1000000:
                log_info(f"[INIT] Using existing GLiNER model from {GLINER_MODEL_PATH}")
                local_files_only = True
            else:
                log_info(f"[INIT] GLiNER model not found locally, will download to {GLINER_MODEL_PATH}")
                local_files_only = False

            # Create configuration for GLiNER detector
            config = {
                "model_name": GLINER_CONFIG['model_name'],
                "entities": GLINER_ENTITIES,
                "local_model_path": GLINER_CONFIG['local_model_path'],
                "local_files_only": local_files_only
            }

            # Create GLiNER detector which will download or load the model
            self._detectors['gliner'] = DocumentProcessingFactory.create_entity_detector(
                EntityDetectionEngine.GLINER,
                config=config
            )

            # Update status tracking
            self._initialization_status['gliner'] = True
            self._detector_metrics['gliner']['last_used'] = time.time()

            load_time = time.time() - start_time
            log_info(f"[INIT] GLiNER detector initialized successfully in {load_time:.2f}s")

            # Test the GLiNER detector
            self._test_gliner_detector()

        except Exception as e:
            self._initialization_status['gliner'] = False
            log_error(f"[ERROR] Failed to initialize GLiNER detector: {e}")

    def _test_gliner_detector(self):
        """Test the GLiNER detector with a simple prediction."""
        try:
            if 'gliner' not in self._detectors or not hasattr(self._detectors['gliner'], 'model'):
                log_warning("[WARNING] GLiNER detector not properly initialized, cannot test")
                return

            # Get detector status
            if hasattr(self._detectors['gliner'], 'get_status'):
                status = self._detectors['gliner'].get_status()
                log_info(f"[INIT] GLiNER detector status: initialized={status.get('initialized', False)}, model_available={status.get('model_available', False)}")

            # Run a simple test prediction
            if hasattr(self._detectors['gliner'], '_process_text_with_gliner'):
                test_text = "John Smith lives at 123 Main St. and works for Microsoft."
                test_entities = ["Person", "Organization", "Address"]
                results = self._detectors['gliner']._process_text_with_gliner(test_text, test_entities)
                log_info(f"[INIT] GLiNER detector test successful. Found {len(results)} entities.")

        except Exception as e:
            log_warning(f"[WARNING] GLiNER detector test failed: {e}")

    def get_presidio_detector(self):
        """
        Get the cached Presidio detector.

        Returns:
            Presidio detector instance
        """
        with self._lock:
            if 'presidio' not in self._detectors:
                log_info("[LAZY] Lazily initializing Presidio detector")
                self._detectors['presidio'] = DocumentProcessingFactory.create_entity_detector(
                    EntityDetectionEngine.PRESIDIO
                )
                self._initialization_status['presidio'] = True

            # Update usage metrics
            self._detector_metrics['presidio']['uses'] += 1
            self._detector_metrics['presidio']['last_used'] = time.time()

            return self._detectors.get('presidio')

    def get_gemini_detector(self):
        """
        Get the cached Gemini detector.

        Returns:
            Gemini detector instance
        """
        with self._lock:
            if 'gemini' not in self._detectors:
                log_info("[LAZY] Lazily initializing Gemini detector")
                self._detectors['gemini'] = DocumentProcessingFactory.create_entity_detector(
                    EntityDetectionEngine.GEMINI
                )
                self._initialization_status['gemini'] = True

            # Update usage metrics
            self._detector_metrics['gemini']['uses'] += 1
            self._detector_metrics['gemini']['last_used'] = time.time()

            return self._detectors.get('gemini')

    def get_gliner_detector(self, entities: Optional[List[str]] = None):
        """
        Get the GLiNER detector instance.

        Args:
            entities: Entity types to detect (used for configuration)

        Returns:
            GLiNER detector instance
        """
        with self._lock:
            # Initialize if needed
            if 'gliner' not in self._detectors:
                log_info("[LAZY] Lazily initializing GLiNER detector")
                self._initialize_gliner_detector()

            # Update usage metrics
            if 'gliner' in self._detectors:
                self._detector_metrics['gliner']['uses'] += 1
                self._detector_metrics['gliner']['last_used'] = time.time()

            return self._detectors.get('gliner')

    def get_hybrid_detector(self, config: Dict[str, Any]):
        """
        Get or create a hybrid detector with the given configuration.

        This method creates and caches hybrid detectors with different configurations
        to avoid recreating them for each request.

        Args:
            config: Configuration dictionary for the hybrid detector

        Returns:
            Hybrid detector instance
        """
        # Create a configuration key to uniquely identify this configuration
        config_key = self._create_hybrid_config_key(config)

        # Get component detectors outside the lock to prevent deadlock
        detectors = []
        if config.get('use_presidio', True):
            detectors.append(self.get_presidio_detector())
        if config.get('use_gemini', False):
            detectors.append(self.get_gemini_detector())
        if config.get('use_gliner', False):
            detectors.append(self.get_gliner_detector(config.get('entities')))

        # Create config with pre-created detectors
        hybrid_config = config.copy()
        hybrid_config["detectors"] = detectors

        # Now get or create the hybrid detector
        with self._lock:
            if config_key not in self._hybrid_detectors:
                log_info(f"[LAZY] Creating new hybrid detector with configuration {config_key}")

                # Create hybrid detector with pre-created components
                from backend.app.entity_detection.hybrid import HybridEntityDetector
                detector = HybridEntityDetector(hybrid_config)

                self._hybrid_detectors[config_key] = detector

                # Initialize metrics
                if config_key not in self._detector_metrics['hybrid']:
                    self._detector_metrics['hybrid'][config_key] = {
                        'uses': 0, 'last_used': None
                    }

                self._initialization_status['hybrid'] = True

            # Update metrics
            self._detector_metrics['hybrid'][config_key]['uses'] += 1
            self._detector_metrics['hybrid'][config_key]['last_used'] = time.time()

            return self._hybrid_detectors[config_key]

    def _create_hybrid_config_key(self, config: Dict[str, Any]) -> str:
        """
        Create a unique key for a hybrid detector configuration.

        Args:
            config: Configuration dictionary

        Returns:
            String key uniquely identifying this configuration
        """
        # Extract key configuration parameters
        use_presidio = config.get('use_presidio', True)
        use_gemini = config.get('use_gemini', False)
        use_gliner = config.get('use_gliner', False)

        # Create a simple string key
        return f"presidio={use_presidio}_gemini={use_gemini}_gliner={use_gliner}"

    def get_detector(self, engine_type: EntityDetectionEngine, config: Optional[Dict[str, Any]] = None):
        """
        Get a detector based on engine type.

        Args:
            engine_type: Type of engine
            config: Configuration for the detector (for hybrid or specialized detectors)

        Returns:
            Detector instance
        """
        if engine_type == EntityDetectionEngine.PRESIDIO:
            return self.get_presidio_detector()
        elif engine_type == EntityDetectionEngine.GEMINI:
            return self.get_gemini_detector()
        elif engine_type == EntityDetectionEngine.GLINER:
            entities = config.get('entities') if config else None
            return self.get_gliner_detector(entities)
        elif engine_type == EntityDetectionEngine.HYBRID:
            if not config:
                config = {
                    'use_presidio': True,
                    'use_gemini': True,
                    'use_gliner': False
                }
            return self.get_hybrid_detector(config)
        else:
            raise ValueError(f"Unknown detector type: {engine_type}")

    def get_initialization_status(self):
        """
        Get the initialization status of all detectors.

        Returns:
            Dictionary with initialization status
        """
        return self._initialization_status

    def get_usage_metrics(self):
        """
        Get usage metrics for all detectors.

        Returns:
            Dictionary with usage metrics
        """
        return self._detector_metrics

    def check_health(self):
        """
        Check if all required detectors are healthy.

        Returns:
            Dictionary with health status
        """
        health = {
            'status': 'healthy',
            'detectors': {
                'presidio': self._initialization_status['presidio'],
                'gemini': self._initialization_status['gemini'],
                'gliner': self._initialization_status['gliner'],
                'hybrid': self._initialization_status['hybrid']
            },
            'model_dir': GLINER_CONFIG['local_model_path'],
            'models_available': os.path.exists(GLINER_CONFIG['local_model_path']) and len(os.listdir(GLINER_CONFIG['local_model_path'])) > 0,
            'hybrid_configurations': len(self._hybrid_detectors)
        }

        # Set overall status
        if not all([health['detectors']['presidio'], health['detectors']['gemini']]):
            health['status'] = 'degraded'

        return health


# Create a singleton instance
initialization_service = InitializationService()