"""
GLiNER entity detection implementation with GDPR compliance and error handling.

This module provides a robust implementation of GLiNER entity detection with
improved initialization, GDPR compliance, and standardized error handling.
"""
import asyncio
import os
import re
import shutil
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

import torch

from backend.app.utils.parallel.core import ParallelProcessingCore

# Import GLiNER with error handling
try:
    from gliner import GLiNER
    GLINER_AVAILABLE = True
except ImportError:
    GLINER_AVAILABLE = False

from backend.app.entity_detection.base import BaseEntityDetector
from backend.app.utils.helpers.text_utils import TextUtils
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.configs.gliner_config import GLINER_MODEL_PATH, GLINER_MODEL_NAME, GLINER_ENTITIES
from backend.app.utils.validation.sanitize_utils import deduplicate_entities
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.validation.data_minimization import minimize_extracted_data
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.synchronization_utils import TimeoutLock, LockPriority


class GlinerEntityDetector(BaseEntityDetector):
    """
    Enhanced service for detecting sensitive information using GLiNER with GDPR compliance and standardized error handling.
    Uses a singleton pattern so that the GLiNER model is loaded only once per process.
    """

    # Singleton shared instance and lock for thread safety
    _shared_instance = None
    _shared_instance_lock = TimeoutLock(name="gliner_shared_instance_lock", priority=LockPriority.HIGH, timeout=30.0)

    # Global cache (in case multiple configurations are desired in the future)
    _model_lock = TimeoutLock(name="gliner_model_lock", priority=LockPriority.HIGH, timeout=30.0)
    _global_initializing = False
    _global_initialization_time = None
    _model_cache = {}  # Cache key -> {"model": loaded_model, "init_time": initialization_time}

    def __new__(cls, *args, **kwargs):
        if cls._shared_instance is None:
            acquired = cls._shared_instance_lock.acquire(timeout=30.0)
            try:
                if cls._shared_instance is None:
                    cls._shared_instance = super().__new__(cls)
            finally:
                cls._shared_instance_lock.release()
        return cls._shared_instance

    def __init__(self, model_name: str = GLINER_MODEL_NAME, entities: Optional[List[str]] = None,
                 local_model_path: Optional[str] = None, local_files_only: bool = False):
        """
        Initialize the GLiNER entity detector with improved error handling and caching.
        This __init__ is only effective on the first instantiation; subsequent instantiations will reuse the singleton.

        Args:
            model_name: Name or path of the GLiNER model to use.
            entities: Entity types to detect (initialized lazily if None).
            local_model_path: Path to local model directory.
            local_files_only: If True, only use local model files.
        """
        # Avoid reinitializing if already initialized
        if getattr(self, '_already_initialized', False):
            return

        super().__init__()
        self.model_name = model_name
        self.model = None
        self.default_entities = entities or GLINER_ENTITIES
        self.local_model_path = local_model_path or os.path.dirname(GLINER_MODEL_PATH)
        self.local_files_only = local_files_only
        self.model_dir_path = GLINER_MODEL_PATH
        self._is_initialized = False
        self._initialization_time = time.time()
        self._last_used = self._initialization_time

        # Instance-specific lock (not used for singleton, but kept for potential parallel tasks)
        self._instance_lock = TimeoutLock(name=f"gliner_instance_{id(self)}", priority=LockPriority.MEDIUM, timeout=15.0)

        self.detectors = [self]  # This allows the hybrid detector to use this class

        self._total_calls = 0
        self.total_processing_time = 0.0

        if not GLINER_AVAILABLE:
            log_error("[ERROR] GLiNER package not installed. Please install with 'pip install gliner'")

        self.norwegian_pronouns = self._init_norwegian_pronouns()
        self._initialize_model()

        # Mark as initialized so that __init__ won’t re-run
        self._already_initialized = True

    def _initialize_model(self, max_retries: int = 2) -> bool | None:
        """
        Initialize the GLiNER model with simplified logic and model caching.
        If a model with the same configuration is already loaded, it is reused.

        Args:
            max_retries: Maximum number of retries for initialization.

        Returns:
            True if initialization succeeded, False otherwise.
        """
        if not GLINER_AVAILABLE:
            log_error("[ERROR] GLiNER package not installed. Please install with 'pip install gliner'")
            return False

        if self._is_initialized and self.model is not None:
            return True

        # Create a cache key based on configuration
        cache_key = (self.model_name, self.local_files_only, tuple(sorted(self.default_entities)))

        # Check if model exists in cache
        acquired = GlinerEntityDetector._model_lock.acquire(timeout=5.0)
        if not acquired:
            log_warning("[GLINER] Timeout acquiring model lock for cache check")
            return False
        try:
            if cache_key in GlinerEntityDetector._model_cache:
                cached = GlinerEntityDetector._model_cache[cache_key]
                self.model = cached["model"]
                self._is_initialized = True
                self._initialization_time = cached["init_time"]
                self._last_used = time.time()
                log_info(f"[GLINER] Loaded model from cache in {self._initialization_time:.2f}s")
                return True
        finally:
            GlinerEntityDetector._model_lock.release()

        start_time = time.time()

        acquired = GlinerEntityDetector._model_lock.acquire(timeout=60.0)
        if not acquired:
            log_error("[GLINER] Timeout acquiring model lock for initialization")
            return False

        try:
            if cache_key in GlinerEntityDetector._model_cache:
                cached = GlinerEntityDetector._model_cache[cache_key]
                self.model = cached["model"]
                self._initialization_time = cached["init_time"]
                self._is_initialized = True
                self._last_used = time.time()
                log_info(f"[GLINER] Loaded model from cache (after double-check) in {self._initialization_time:.2f}s")
                return True

            if GlinerEntityDetector._global_initializing:
                log_info("[GLINER] Another thread is already initializing the model")
                wait_until = time.time() + 60.0
                while GlinerEntityDetector._global_initializing and time.time() < wait_until:
                    time.sleep(1)
                if cache_key in GlinerEntityDetector._model_cache:
                    cached = GlinerEntityDetector._model_cache[cache_key]
                    self.model = cached["model"]
                    self._initialization_time = cached["init_time"]
                    self._is_initialized = True
                    self._last_used = time.time()
                    log_info(f"[GLINER] Loaded model from cache after waiting in {self._initialization_time:.2f}s")
                    return True

            GlinerEntityDetector._global_initializing = True

            try:
                local_model_exists = self._check_local_model_exists()
                log_info(f"[GLINER] Local model exists: {local_model_exists}")

                for attempt in range(max_retries):
                    try:
                        if local_model_exists:
                            log_info(f"[OK] Attempting to load model from local directory: {self.model_dir_path}")
                            if self._load_local_model(self.model_dir_path):
                                break
                            else:
                                local_model_exists = False
                                log_warning("[WARNING] Failed to load model from local directory, attempting download")
                                self.local_files_only = False
                        if not local_model_exists:
                            log_info(f"[OK] Downloading GLiNER model: {self.model_name}")
                            self.model = GLiNER.from_pretrained(self.model_name)
                            if self.local_model_path:
                                self._save_model_to_directory(self.model_dir_path)
                        if self.model is not None:
                            self._is_initialized = True
                            self._initialization_time = time.time() - start_time
                            self._last_used = time.time()
                            log_info(f"[OK] Model initialized in {self._initialization_time:.2f}s")
                            GlinerEntityDetector._model_cache[cache_key] = {
                                "model": self.model,
                                "init_time": self._initialization_time
                            }
                            GlinerEntityDetector._global_initialization_time = self._initialization_time
                            return True
                    except Exception as e:
                        SecurityAwareErrorHandler.log_processing_error(
                            e, f"gliner_initialization_attempt_{attempt}", self.model_name)
                    if attempt < max_retries - 1:
                        time.sleep(2)
                return self._is_initialized
            finally:
                GlinerEntityDetector._global_initializing = False
        finally:
            GlinerEntityDetector._model_lock.release()
            record_keeper.record_processing(
                operation_type="gliner_model_initialization",
                document_type="model",
                entity_types_processed=self.default_entities,
                processing_time=time.time() - start_time,
                entity_count=0,
                success=self._is_initialized
            )

    def _init_norwegian_pronouns(self) -> set:
        """
        Initialize the set of Norwegian pronouns for filtering.

        Returns:
            Set of Norwegian pronouns in lowercase
        """
        norwegian_pronouns = {
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
        return {word.lower() for word in norwegian_pronouns}

    def _fix_config_file_discrepancy(self) -> None:
        """
        Fix configuration file discrepancy by creating a copy of gliner_config.json as config.json.

        This resolves the issue where the GLiNER library expects config.json but the
        model directory has gliner_config.json instead.
        """
        try:
            gliner_config_path = os.path.join(self.model_dir_path, 'gliner_config.json')
            config_path = os.path.join(self.model_dir_path, 'config.json')
            if os.path.exists(gliner_config_path) and not os.path.exists(config_path):
                log_info(f"[GLINER] Creating config.json from gliner_config.json")
                shutil.copy2(gliner_config_path, config_path)
                log_info(f"[GLINER] Successfully created config.json")
        except Exception as e:
            SecurityAwareErrorHandler.log_processing_error(e, "gliner_config_fix", self.model_dir_path)

    def _check_local_model_exists(self) -> bool:
        """
        Check if a valid local model directory exists.

        Returns:
            True if a valid local model directory exists, False otherwise
        """
        # Check if the directory exists
        if not os.path.exists(self.model_dir_path):
            log_warning(f"[GLINER] Model directory does not exist: {self.model_dir_path}")
            return False
        if not os.path.isdir(self.model_dir_path):
            log_warning(f"[GLINER] Model path is not a directory: {self.model_dir_path}")
            return False
        required_files = ['pytorch_model.bin']
        config_files = ['config.json', 'gliner_config.json']
        has_config = any(os.path.exists(os.path.join(self.model_dir_path, f)) for f in config_files)
        if not has_config:
            log_warning(f"[GLINER] No configuration file found in model directory")
            return False
        missing_files = [f for f in required_files if not os.path.exists(os.path.join(self.model_dir_path, f))]
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
        except Exception as e:
            SecurityAwareErrorHandler.log_processing_error(e, "gliner_model_save", model_dir)
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
            try:
                config_path = os.path.join(model_dir, 'config.json')
                if not os.path.exists(config_path):
                    log_warning(f"[GLINER] config.json still doesn't exist after fix attempt")
                self.model = GLiNER.from_pretrained(model_dir, local_files_only=True)
                self._is_initialized = True
                self._initialization_time = time.time()
                log_info("[OK] Loaded model using GLiNER's native from_pretrained method")
                log_info(f"[LOAD] Initialization flag explicitly set to: {self._is_initialized}")
                return True
            except Exception as load_error:
                SecurityAwareErrorHandler.log_processing_error(load_error, "gliner_model_load_native", model_dir)
                try:
                    gliner_config_path = os.path.join(model_dir, 'gliner_config.json')
                    config_path = os.path.join(model_dir, 'config.json')
                    config_file = config_path if os.path.exists(config_path) else gliner_config_path
                    if os.path.exists(config_file):
                        log_info(f"[GLINER] Trying to load with explicit config path: {config_file}")
                        try:
                            from transformers import AutoConfig
                            config = AutoConfig.from_pretrained(config_file)
                            self.model = GLiNER.from_pretrained(model_dir, config=config, local_files_only=True)
                            self._is_initialized = True
                            log_info("[OK] Loaded model with explicit config")
                            log_info(f"[LOAD] Initialization flag explicitly set to: {self._is_initialized}")
                            return True
                        except ImportError:
                            log_warning("[WARNING] Could not import AutoConfig from transformers")
                except Exception as config_error:
                    SecurityAwareErrorHandler.log_processing_error(config_error, "gliner_model_load_explicit_config", model_dir)
                return False
        except Exception as e:
            SecurityAwareErrorHandler.log_processing_error(e, "gliner_model_load", model_dir)
            return False

    async def detect_sensitive_data_async(
            self,
            extracted_data: Dict[str, Any],
            requested_entities: Optional[List[str]] = None
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        """
        Asynchronously detect sensitive entities in extracted data with GDPR compliance.

        Args:
            extracted_data: Dictionary containing text and bounding box information
            requested_entities: List of entity types to detect

        Returns:
            Tuple of (anonymized_text, results_json, redaction_mapping)
        """
        start_time = time.time()
        operation_id = f"gliner_{time.time()}_{hash(str(requested_entities)) % 10000}"
        minimized_data = minimize_extracted_data(extracted_data)
        self._total_calls += 1
        self._last_used = time.time()
        try:
            pages = minimized_data.get("pages", [])
            if not pages:
                return "", [], {"pages": []}
            page_texts_and_mappings, anonymized_texts, redaction_mapping = self._prepare_page_data(pages)
            if not page_texts_and_mappings:
                return "", [], {"pages": []}
            operation_type = "gliner_detection"
            document_type = "document"
            entity_list = requested_entities or self.default_entities

            async def process_page(page):
                try:
                    return await asyncio.wait_for(
                        self._process_page_async(page, page_texts_and_mappings, entity_list),
                        timeout=60.0
                    )
                except asyncio.TimeoutError:
                    log_warning(f"[WARNING] Timeout processing page {page.get('page', 'unknown')} with GLiNER")
                    return {"page": page.get('page'), "sensitive": []}, []
                except Exception as e:
                    SecurityAwareErrorHandler.log_processing_error(e, "gliner_page_processing_timeout", f"page_{page.get('page', 'unknown')}")
                    return {"page": page.get('page'), "sensitive": []}, []

            page_results = await ParallelProcessingCore.process_pages_in_parallel(pages, process_page)
            combined_results = []
            for page_number, (page_redaction_info, processed_entities) in page_results:
                if page_redaction_info:
                    redaction_mapping["pages"].append(page_redaction_info)
                if processed_entities:
                    combined_results.extend(processed_entities)
            combined_results = self.sanitize_entities(combined_results)
            redaction_mapping["pages"].sort(key=lambda x: x.get("page", 0))
            anonymized_text = "\n".join(anonymized_texts)
            total_time = time.time() - start_time
            record_keeper.record_processing(
                operation_type=operation_type,
                document_type=document_type,
                entity_types_processed=entity_list,
                processing_time=total_time,
                entity_count=len(combined_results),
                success=True
            )
            log_info(f"[PERF] GLiNER detection completed in {total_time:.2f}s")
            log_info(f"[PERF] Found {len(combined_results)} entities across {len(pages)} pages")
            log_sensitive_operation("GLiNER Detection", len(combined_results), total_time, pages=len(pages))
            return anonymized_text, combined_results, redaction_mapping
        except Exception as e:
            error_time = time.time() - start_time
            record_keeper.record_processing(
                operation_type="gliner_detection",
                document_type="document",
                entity_types_processed=requested_entities or [],
                processing_time=error_time,
                entity_count=0,
                success=False
            )
            SecurityAwareErrorHandler.log_processing_error(e, "gliner_detection", operation_id)
            return "", [], {"pages": []}

    def _prepare_page_data(self, pages: List[Dict[str, Any]]) -> Tuple[Dict[int, Tuple[str, List]], List[str], Dict[str, Any]]:
        """
        Prepare page data for processing by extracting text and creating mappings.

        Args:
            pages: List of page dictionaries with word data

        Returns:
            Tuple of (page_texts_and_mappings, anonymized_texts, redaction_mapping)
        """
        page_texts_and_mappings = {}
        anonymized_texts = []
        redaction_mapping = {"pages": []}
        for page in pages:
            words = page.get("words", [])
            page_number = page.get("page")
            if not words:
                redaction_mapping["pages"].append({"page": page_number, "sensitive": []})
                continue
            has_content = any(word.get("text", "").strip() for word in words)
            if not has_content:
                log_info(f"[OK] Skipping empty page {page_number}")
                redaction_mapping["pages"].append({"page": page_number, "sensitive": []})
                continue
            full_text, mapping = TextUtils.reconstruct_text_and_mapping(words)
            anonymized_texts.append(full_text)
            page_texts_and_mappings[page_number] = (full_text, mapping)
        return page_texts_and_mappings, anonymized_texts, redaction_mapping

    async def _process_page_async(
        self,
        page_data: Dict[str, Any],
        page_texts_and_mappings: Dict[int, Tuple[str, List]],
        requested_entities: List[str]
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Process a single page asynchronously to detect entities with enhanced
        error handling and GDPR compliance.

        Args:
            page_data: Dictionary with page information
            page_texts_and_mappings: Dictionary mapping page numbers to (text, mapping) tuples
            requested_entities: List of entity types to detect

        Returns:
            Tuple of (page_redaction_info, processed_entities)
        """
        try:
            page_start_time = time.time()
            page_number = page_data.get("page")
            words = page_data.get("words", [])
            operation_id = f"page_{page_number}"
            if not words:
                return {"page": page_number, "sensitive": []}, []
            full_text, mapping = page_texts_and_mappings.get(page_number, ("", []))
            if not full_text or not mapping:
                return {"page": page_number, "sensitive": []}, []
            log_info(f"[OK] Processing text with GLiNER on page {page_number}")
            if not self.model:
                log_warning(f"[WARNING] GLiNER model not available, skipping page {page_number}")
                return {"page": page_number, "sensitive": []}, []
            page_entities = await asyncio.to_thread(self._process_text_with_gliner, full_text, requested_entities)
            if not page_entities:
                log_info(f"[OK] No entities detected by GLiNER on page {page_number}")
                return {"page": page_number, "sensitive": []}, []
            entity_count = len(page_entities)
            log_info(f"[OK] Found {entity_count} entities on page {page_number}")
            entity_start_time = time.time()
            try:
                processed_entities, page_redaction_info = await self.process_entities_for_page(
                    page_number, full_text, mapping, page_entities
                )
            except Exception as entity_error:
                SecurityAwareErrorHandler.log_processing_error(entity_error, "gliner_entity_processing", operation_id)
                return {"page": page_number, "sensitive": []}, []
            entity_time = time.time() - entity_start_time
            page_time = time.time() - page_start_time
            record_keeper.record_processing(
                operation_type="gliner_page_processing",
                document_type=f"page_{page_number}",
                entity_types_processed=requested_entities,
                processing_time=page_time,
                entity_count=len(processed_entities),
                success=True
            )
            log_sensitive_operation("GLiNER Page Detection", len(processed_entities), page_time,
                                    page_number=page_number, entity_processing_time=entity_time, operation_id=operation_id)
            return page_redaction_info, processed_entities
        except Exception as e:
            SecurityAwareErrorHandler.log_processing_error(e, "gliner_page_processing", f"page_{page_data.get('page', 'unknown')}")
            return {"page": page_data.get('page'), "sensitive": []}, []

    def _finalize_results(
        self,
        page_results: List[Tuple[int, Tuple[Dict[str, Any], List[Dict[str, Any]]]]],
        anonymized_texts: List[str],
        redaction_mapping: Dict[str, Any]
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        """
        Finalize detection results by combining page results.

        Args:
            page_results: List of tuples with page number and processing results
            anonymized_texts: List of page texts
            redaction_mapping: Initial redaction mapping dictionary

        Returns:
            Tuple of (anonymized_text, combined_results, redaction_mapping)
        """
        combined_results = []
        for page_number, (page_redaction_info, processed_entities) in page_results:
            if page_redaction_info:
                redaction_mapping["pages"].append(page_redaction_info)
            if processed_entities:
                combined_results.extend(processed_entities)
        redaction_mapping["pages"].sort(key=lambda x: x.get("page", 0))
        anonymized_text = "\n".join(anonymized_texts)
        return anonymized_text, combined_results, redaction_mapping

    def _process_text_with_gliner(self, text: str, requested_entities: List[str]) -> List[Dict[str, Any]]:
        """
        Process text with GLiNER to extract entities with robust error handling.

        Args:
            text: Text to process
            requested_entities: List of entity types to detect

        Returns:
            List of detected entities
        """
        operation_id = f"gliner_process_{hash(text) % 10000}"
        start_time = time.time()
        try:
            if not text or len(text.strip()) < 3:
                return []
            if not self.model:
                error = SecurityAwareErrorHandler.handle_safe_error(
                    ValueError("GLiNER model not available"),
                    "gliner_model_unavailable",
                    operation_id,
                    default_return=[]
                )
                return error if isinstance(error, list) else []
            if not self._is_initialized:
                error = SecurityAwareErrorHandler.handle_safe_error(
                    ValueError("GLiNER model not properly initialized"),
                    "gliner_model_not_initialized",
                    operation_id,
                    default_return=[]
                )
                return error if isinstance(error, list) else []
            self._last_used = time.time()
            paragraphs = [p for p in text.split('\n') if p.strip()]
            all_entities = []
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
        except Exception as e:
            return SecurityAwareErrorHandler.handle_safe_error(
                e,
                "gliner_text_processing",
                operation_id,
                default_return=[]
            )

    def _process_paragraph_batch(self, paragraphs: List[str], full_text: str, requested_entities: List[str]) -> List[Dict[str, Any]]:
        batch_entities = []
        entity_groups = {}
        for entity_type in requested_entities:
            group_key = entity_type[0] if entity_type else '_'
            entity_groups.setdefault(group_key, []).append(entity_type)
        for group_key, entity_types in entity_groups.items():
            for paragraph in paragraphs:
                if not paragraph.strip():
                    continue
                base_offset = full_text.find(paragraph)
                if base_offset == -1:
                    continue
                sentence_groups = self._split_into_sentence_groups(paragraph, 350)
                for group in sentence_groups:
                    try:
                        group_offset = paragraph.find(group)
                        if group_offset == -1:
                            continue
                        absolute_offset = base_offset + group_offset
                        try:
                            group_entities = self.model.predict_entities(group, entity_types, threshold=0.5)
                        except Exception as predict_error:
                            SecurityAwareErrorHandler.log_processing_error(
                                predict_error,
                                "gliner_predict_entities",
                                f"group_{hash(group) % 10000}"
                            )
                            continue
                        for entity in group_entities:
                            entity_dict = {
                                "entity_type": entity.get("label", "UNKNOWN").upper(),
                                "start": absolute_offset + entity.get("start", 0),
                                "end": absolute_offset + entity.get("end", 0),
                                "score": entity.get("score", 0.5),
                                "original_text": entity.get("text", "")
                            }
                            batch_entities.append(entity_dict)
                    except Exception as e:
                        SecurityAwareErrorHandler.log_processing_error(
                            e,
                            "gliner_paragraph_processing",
                            f"paragraph_{hash(paragraph) % 10000}"
                        )
        return batch_entities

    def _process_paragraph(self, paragraph: str, full_text: str, requested_entities: List[str]) -> List[Dict[str, Any]]:
        """
        Process a single paragraph to extract entities with enhanced error handling.
        For backward compatibility - now delegates to the batch method.

        Args:
            paragraph: Paragraph text to process
            full_text: The full document text (for offset calculation)
            requested_entities: List of entity types to detect

        Returns:
            List of entities detected in the paragraph
        """
        return self._process_paragraph_batch([paragraph], full_text, requested_entities)

    def _split_into_sentence_groups(self, text: str, max_tokens: int = 300) -> List[str]:
        """
        Split text into smaller groups that fit within GLiNER's token limit.
        Uses a more conservative approach to prevent any truncation.

        Args:
            text: Text to split
            max_tokens: Maximum tokens per group (default 300 for safety)

        Returns:
            List of text groups
        """
        # Split text into sentences
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
        groups = []
        current_group = ""
        current_token_count = 0
        for sentence in sentences:
            estimated_tokens = len(sentence.split()) + max(3, int(len(sentence.split()) * 0.2))
            if estimated_tokens > max_tokens:
                if current_group:
                    groups.append(current_group)
                    current_group = ""
                    current_token_count = 0
                words = sentence.split()
                chunk = []
                chunk_token_count = 0
                for word in words:
                    word_tokens = len(word) // 3 + 1
                    if (chunk_token_count + word_tokens) > max_tokens and chunk:
                        groups.append(" ".join(chunk))
                        chunk = [word]
                        chunk_token_count = word_tokens
                    else:
                        chunk.append(word)
                        chunk_token_count += word_tokens
                if chunk:
                    groups.append(" ".join(chunk))
            elif current_token_count + estimated_tokens > max_tokens:
                if current_group:
                    groups.append(current_group)
                current_group = sentence
                current_token_count = estimated_tokens
            else:
                if current_group:
                    current_group += " " + sentence
                    current_token_count += estimated_tokens
                else:
                    current_group = sentence
                    current_token_count = estimated_tokens
        if current_group:
            groups.append(current_group)
        return groups

    def _process_text_group(self, text_group: str, paragraph: str, full_text: str, requested_entities: List[str]) -> List[Dict[str, Any]]:
        """
        Process a group of text (sentences) to extract entities with enhanced error handling.

        Args:
            text_group: Text group to process
            paragraph: Parent paragraph containing the text group
            full_text: The full document text
            requested_entities: List of entity types to detect

        Returns:
            List of entities detected in the text group
        """
        entities = []
        operation_id = f"group_{hash(text_group) % 10000}"
        try:
            group_offset = paragraph.find(text_group)
            if group_offset == -1:
                return []
            para_offset = full_text.find(paragraph)
            if para_offset == -1:
                return []
            abs_offset = para_offset + group_offset
            try:
                group_entities = self.model.predict_entities(text_group, requested_entities, threshold=0.5)
            except Exception as predict_error:
                SecurityAwareErrorHandler.log_processing_error(
                    predict_error, "gliner_predict_entities_group", operation_id
                )
                return []
            for entity in group_entities:
                entity_dict = {
                    "entity_type": entity.get("label", "UNKNOWN").upper(),
                    "start": abs_offset + entity.get("start", 0),
                    "end": abs_offset + entity.get("end", 0),
                    "score": entity.get("score", 0.5),
                    "original_text": entity.get("text", "")
                }
                entities.append(entity_dict)
        except Exception as e:
            SecurityAwareErrorHandler.log_processing_error(
                e, "gliner_text_group_processing", operation_id
            )
        return entities

    def _filter_norwegian_pronouns(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter out Norwegian pronouns that are incorrectly identified as person names.

        Args:
            entities: List of detected entities

        Returns:
            Filtered list of entities without Norwegian pronouns
        """
        # Filter out entities that match Norwegian pronouns
        filtered_entities = []
        for entity in entities:
            if entity["entity_type"] in {"PERSON", "PER"}:
                entity_text = entity.get("original_text", "").strip()
                entity_words = entity_text.split()
                if len(entity_words) == 1 and entity_words[0].lower() in self.norwegian_pronouns:
                    log_info(f"[FILTER] Removed Norwegian pronoun incorrectly detected as PERSON")
                    continue
                if len(entity_words) > 1 and all(word.lower() in self.norwegian_pronouns for word in entity_words):
                    log_info(f"[FILTER] Removed compound Norwegian pronoun incorrectly detected as PERSON")
                    continue
            filtered_entities.append(entity)
        return filtered_entities

    def _convert_to_entity_dict(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert a GLiNER entity to a standardized dictionary format.

        Args:
            entity: GLiNER entity dictionary

        Returns:
            Standardized entity dictionary
        """
        entity_dict = {
            "entity_type": entity.get("entity_type", "UNKNOWN"),
            "start": entity.get("start", 0),
            "end": entity.get("end", 0),
            "score": float(entity.get("score", 0.5))
        }
        if "original_text" in entity:
            entity_dict["original_text"] = entity["original_text"]
        return entity_dict

    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the GLiNER detector.

        Returns:
            Dictionary with status information
        """
        return {
            "initialized": self._is_initialized,
            "initialization_time": self._initialization_time,
            "initialization_time_readable": datetime.fromtimestamp(self._initialization_time, timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
            "last_used": self._last_used,
            "last_used_readable": datetime.fromtimestamp(self._last_used, timezone.utc).strftime('%Y-%m-%d %H:%M:%S') if self._last_used else "Never Used",
            "idle_time": time.time() - self._last_used if self._last_used else None,
            "idle_time_readable": f"{(time.time() - self._last_used):.2f} seconds" if self._last_used else "N/A",
            "total_calls": self._total_calls,
            "total_entities_detected": getattr(self, '_total_entities_detected', 0),
            "total_processing_time": self.total_processing_time,
            "average_processing_time": (self.total_processing_time / self._total_calls if self._total_calls > 0 else None),
            "model_available": self.model is not None,
            "model_name": self.model_name,
            "gliner_package_available": GLINER_AVAILABLE,
            "local_model_path": self.local_model_path,
            "local_files_only": self.local_files_only,
            "model_dir_path": self.model_dir_path,
            "model_directory_exists": os.path.isdir(self.model_dir_path) if self.model_dir_path else False,
            "model_files": os.listdir(self.model_dir_path) if self.model_dir_path and os.path.isdir(self.model_dir_path) else [],
            "config_files": {
                "config.json": os.path.exists(os.path.join(self.model_dir_path, "config.json")) if self.model_dir_path else False,
                "gliner_config.json": os.path.exists(os.path.join(self.model_dir_path, "gliner_config.json")) if self.model_dir_path else False
            },
            "global_initializing": GlinerEntityDetector._global_initializing,
            "global_initialization_time": GlinerEntityDetector._global_initialization_time
        }

    def detect_sensitive_data(
        self,
        extracted_data: Dict[str, Any],
        requested_entities: Optional[List[str]] = None
    ) -> tuple[str, list[Any], dict[str, list[Any]]] | None:
        """
        Detect sensitive entities in extracted text. Synchronous wrapper with
        enhanced GDPR compliance and error handling.

        Args:
            extracted_data: Dictionary containing text and bounding box information
            requested_entities: List of entity types to detect

        Returns:
            Tuple of (anonymized_text, results_json, redaction_mapping)
        """
        minimized_data = minimize_extracted_data(extracted_data)
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    self.detect_sensitive_data_async(minimized_data, requested_entities)
                )
            finally:
                loop.close()
        except Exception as e:
            SecurityAwareErrorHandler.log_processing_error(e, "gliner_detection_sync", "")
            record_keeper.record_processing(
                operation_type="gliner_detection_sync",
                document_type="document",
                entity_types_processed=requested_entities or [],
                processing_time=0.0,
                entity_count=0,
                success=False
            )
            return "", [], {"pages": []}