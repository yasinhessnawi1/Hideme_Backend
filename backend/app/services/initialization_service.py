"""
Service for initializing and caching detection engines with simplified GLiNER model handling.

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
from backend.app.configs.presidio_config import REQUESTED_ENTITIES
from backend.app.utils.logger import default_logger as logger, log_info, log_warning, log_error


class InitializationService:
    """
    Service for initializing and caching entity detectors with simplified GLiNER model handling.

    This service creates and caches instances of entity detectors to avoid
    recreating them on each request, significantly improving performance.

    The GLiNER model is downloaded once at server startup and saved to a local file,
    then loaded from this local file for all subsequent requests.
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

                # Single GLiNER model instance (we'll only have one)
                self._gliner_model = None

                # Track initialization status
                self._initialization_status = {
                    'presidio': False,
                    'gemini': False,
                    'gliner': False
                }

                # Track detector usage
                self._detector_metrics = {
                    'presidio': {'uses': 0, 'last_used': None},
                    'gemini': {'uses': 0, 'last_used': None},
                    'gliner': {'uses': 0, 'last_used': None}
                }

                # Ensure model directory exists
                os.makedirs(GLINER_CONFIG['local_model_path'], exist_ok=True)

                self._initialized = True
                logger.info("[INIT] Initialization service created")

    def initialize_detectors(self, force_reload: bool = False):
        """
        Initialize all detectors at startup, with simplified GLiNER handling.

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

                # Initialize GLiNER model - simplified approach
                if force_reload or self._gliner_model is None:
                    self._initialize_gliner_model()

                log_info("[INIT] All detectors initialized")
            except Exception as e:
                log_error(f"[ERROR] Failed to initialize detectors: {e}")
                raise

    def _initialize_gliner_model(self):
        """
        Download and initialize the GLiNER model once, saving it to a local file.

        This simplified approach downloads the model if not found locally,
        then saves it for future use.
        """
        try:
            log_info("[INIT] Initializing GLiNER model...")
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
            self._gliner_model = DocumentProcessingFactory.create_entity_detector(
                EntityDetectionEngine.GLINER,
                config=config
            )

            # Update status tracking
            self._initialization_status['gliner'] = True
            self._detector_metrics['gliner']['last_used'] = time.time()

            load_time = time.time() - start_time
            log_info(f"[INIT] GLiNER model initialized successfully in {load_time:.2f}s")

            # Verify model is working with a simple test
            self._test_gliner_model()

        except Exception as e:
            self._initialization_status['gliner'] = False
            log_error(f"[ERROR] Failed to initialize GLiNER model: {e}")

    def _test_gliner_model(self):
        """Verify the GLiNER model is working correctly with a simple test."""
        try:
            if not self._gliner_model or not hasattr(self._gliner_model, 'model'):
                log_warning("[WARNING] GLiNER model not properly initialized, cannot test")
                return

            # Get model status
            if hasattr(self._gliner_model, 'get_status'):
                status = self._gliner_model.get_status()
                log_info(f"[INIT] GLiNER model status: initialized={status.get('initialized', False)}, model_available={status.get('model_available', False)}")

            # Run a simple test prediction
            if hasattr(self._gliner_model, '_process_text_with_gliner'):
                test_text = "John Smith lives at 123 Main St. and works for Microsoft."
                test_entities = ["Person", "Organization", "Address"]
                results = self._gliner_model._process_text_with_gliner(test_text, test_entities)
                log_info(f"[INIT] GLiNER model test successful. Found {len(results)} entities.")

        except Exception as e:
            log_warning(f"[WARNING] GLiNER model test failed: {e}")

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

        This simplified approach uses a single GLiNER model instance for all entity types.

        Args:
            entities: Entity types to detect (ignored in simplified approach)

        Returns:
            GLiNER detector instance or None if not initialized
        """
        with self._lock:
            # Initialize if needed
            if self._gliner_model is None:
                log_info("[LAZY] Lazily initializing GLiNER model")
                self._initialize_gliner_model()

            # Update usage metrics if model is available
            if self._gliner_model is not None:
                self._detector_metrics['gliner']['uses'] += 1
                self._detector_metrics['gliner']['last_used'] = time.time()

            return self._gliner_model

    def get_detector(self, engine_type: str, entities: Optional[List[str]] = None):
        """
        Get a detector based on engine type.

        Args:
            engine_type: Type of engine (presidio, gemini, gliner)
            entities: List of entity types for GLiNER

        Returns:
            Detector instance
        """
        if engine_type.lower() == 'presidio':
            return self.get_presidio_detector()
        elif engine_type.lower() == 'gemini':
            return self.get_gemini_detector()
        elif engine_type.lower() == 'gliner':
            return self.get_gliner_detector(entities)
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
                'gliner': self._initialization_status['gliner']
            },
            'model_dir': GLINER_CONFIG['local_model_path'],
            'models_available': os.path.exists(GLINER_CONFIG['local_model_path']) and len(os.listdir(GLINER_CONFIG['local_model_path'])) > 0
        }

        # Set overall status
        if not all([health['detectors']['presidio'], health['detectors']['gemini']]):
            health['status'] = 'degraded'

        return health


# Create a singleton instance
initialization_service = InitializationService()