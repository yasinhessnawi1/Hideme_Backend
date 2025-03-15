"""
Batch processing service for handling multiple files in a single request.

This module provides functionality to process multiple files for entity detection
in a single request, with support for multiple file formats and response aggregation.
"""
import asyncio
import os
import time
import uuid
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import List, Dict, Any, Optional, Union

from fastapi import UploadFile, HTTPException

from backend.app.factory.document_processing import (
    DocumentProcessingFactory,
    DocumentFormat,
    EntityDetectionEngine
)
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.helpers.json_helper import validate_requested_entities
from backend.app.utils.helpers.parallel_helper import ParallelProcessingHelper
from backend.app.utils.logger import log_info, log_warning, log_error
from backend.app.utils.sanitize_utils import sanitize_detection_output


class BatchProcessingService:
    """
    Service for processing multiple files in a single request.

    This service handles:
    - Processing multiple files with different formats
    - Configurable parallel processing
    - Aggregated response formatting
    - Detailed performance tracking
    """

    # Class-level lock for detector access during parallel processing
    _detector_access_lock = asyncio.Lock()

    @staticmethod
    async def detect_entities_in_files(
            files: List[UploadFile],
            requested_entities: Optional[str] = None,
            use_presidio: bool = True,
            use_gemini: bool = False,
            use_gliner: bool = False,
            max_parallel_files: int = 4,
            detection_engine: EntityDetectionEngine = EntityDetectionEngine.PRESIDIO
    ) -> Dict[str, Any]:
        """
        Process multiple files for entity detection.

        Args:
            files: List of uploaded files
            requested_entities: JSON string of entity types to detect (optional)
            use_presidio: Whether to use Presidio in hybrid mode
            use_gemini: Whether to use Gemini in hybrid mode
            use_gliner: Whether to use GLiNER in hybrid mode
            max_parallel_files: Maximum number of files to process in parallel
            detection_engine: Entity detection engine to use (for non-hybrid mode)

        Returns:
            Dictionary with batch processing results
        """
        start_time = time.time()

        # Validate entity list
        entity_list = validate_requested_entities(requested_entities) if requested_entities else []

        # Pre-initialize detectors before parallel processing
        # This ensures all threads will use the same detector instances
        log_info("[BATCH] Pre-initializing detectors for batch processing")
        detectors = await BatchProcessingService._pre_initialize_detectors(
            detection_engine,
            use_presidio,
            use_gemini,
            use_gliner,
            entity_list
        )

        # Create temp directory for file processing
        with TemporaryDirectory() as temp_dir:
            # Save files to disk and prepare processing tasks
            file_paths = []
            file_meta = {}

            for file in files:
                try:
                    # Generate a unique filename to avoid collisions
                    file_uuid = str(uuid.uuid4())
                    file_ext = os.path.splitext(file.filename)[1].lower() if file.filename else ".txt"
                    tmp_path = os.path.join(temp_dir, f"{file_uuid}{file_ext}")

                    # Read file contents and save to disk
                    contents = await file.read()
                    with open(tmp_path, "wb") as f:
                        f.write(contents)

                    # Reset file cursor for potential future reads
                    await file.seek(0)

                    # Store file metadata
                    file_meta[tmp_path] = {
                        "original_name": file.filename,
                        "content_type": file.content_type,
                        "size": len(contents)
                    }

                    file_paths.append(tmp_path)
                except Exception as e:
                    log_error(f"[ERROR] Failed to process file {file.filename}: {str(e)}")
                    continue

            if not file_paths:
                raise HTTPException(status_code=400, detail="No valid files provided for processing")

            # Process files in parallel
            log_info(f"[OK] Processing {len(file_paths)} files in parallel")

            # Use adaptive concurrency
            optimal_workers = ParallelProcessingHelper.get_optimal_workers(
                len(file_paths),
                min_workers=1,
                max_workers=max_parallel_files
            )

            # Define file processing function with shared detector access
            async def process_file(file_path: str) -> Dict[str, Any]:
                """Process a single file and return results."""
                file_start_time = time.time()
                file_name = file_meta[file_path]["original_name"]
                content_type = file_meta[file_path]["content_type"]

                try:
                    # Get document format based on file extension
                    doc_format = None
                    if file_path.lower().endswith('.pdf'):
                        doc_format = DocumentFormat.PDF
                    elif file_path.lower().endswith(('.docx', '.doc')):
                        doc_format = DocumentFormat.DOCX
                    elif file_path.lower().endswith('.txt'):
                        doc_format = DocumentFormat.TXT

                    # Extract text with positions
                    extract_start = time.time()
                    extractor = DocumentProcessingFactory.create_document_extractor(
                        file_path, doc_format
                    )
                    extracted_data = await asyncio.to_thread(extractor.extract_text_with_positions)
                    extractor.close()
                    extract_time = time.time() - extract_start

                    # Get detector from pre-initialized detectors
                    detection_start = time.time()

                    # Get appropriate detector from pre-initialized detectors
                    detector = detectors["detector"]

                    # Detect entities
                    if hasattr(detector, 'detect_sensitive_data_async'):
                        anonymized_text, entities, redaction_mapping = await detector.detect_sensitive_data_async(
                            extracted_data, entity_list
                        )
                    else:
                        anonymized_text, entities, redaction_mapping = await asyncio.to_thread(
                            detector.detect_sensitive_data,
                            extracted_data, entity_list
                        )

                    detection_time = time.time() - detection_start

                    # Calculate metrics
                    total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
                    entity_density = (len(entities) / total_words) * 1000 if total_words > 0 else 0

                    # Build performance metrics
                    processing_times = {
                        "extraction_time": extract_time,
                        "detection_time": detection_time,
                        "total_time": time.time() - file_start_time,
                        "words_count": total_words,
                        "pages_count": len(extracted_data.get("pages", [])),
                        "entity_density": entity_density
                    }

                    # Sanitize output for consistent response format
                    sanitized_response = sanitize_detection_output(
                        anonymized_text, entities, redaction_mapping, processing_times
                    )

                    # Add file information
                    sanitized_response["file_info"] = {
                        "filename": file_name,
                        "content_type": content_type,
                        "size": file_meta[file_path]["size"]
                    }

                    # Add model information
                    sanitized_response["model_info"] = detectors["model_info"]

                    return {
                        "file": file_name,
                        "status": "success",
                        "results": sanitized_response
                    }
                except Exception as e:
                    log_error(f"[ERROR] Error processing file {file_name}: {str(e)}")
                    return {
                        "file": file_name,
                        "status": "error",
                        "error": str(e),
                        "processing_time": time.time() - file_start_time
                    }

            # Process all files in parallel with optimized concurrency
            tasks = [process_file(file_path) for file_path in file_paths]
            results = await asyncio.gather(*tasks)

        # Calculate batch statistics
        batch_time = time.time() - start_time
        success_count = sum(1 for r in results if r.get("status") == "success")
        error_count = len(results) - success_count
        total_entities = sum(
            r.get("results", {}).get("entities_detected", {}).get("total", 0)
            for r in results if r.get("status") == "success"
        )

        # Build batch response
        response = {
            "batch_summary": {
                "total_files": len(files),
                "successful": success_count,
                "failed": error_count,
                "total_entities": total_entities,
                "total_time": batch_time,
                "workers": optimal_workers
            },
            "file_results": results
        }

        log_info(f"[PERF] Batch processing completed in {batch_time:.2f}s. "
                 f"Successfully processed {success_count}/{len(files)} files. "
                 f"Found {total_entities} entities.")

        return response

    @staticmethod
    async def _pre_initialize_detectors(
        detection_engine: EntityDetectionEngine,
        use_presidio: bool = True,
        use_gemini: bool = False,
        use_gliner: bool = False,
        entity_list: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Pre-initialize detectors before parallel processing.

        This ensures all threads will use the same detector instances.

        Args:
            detection_engine: Entity detection engine to use
            use_presidio: Whether to use Presidio in hybrid mode
            use_gemini: Whether to use Gemini in hybrid mode
            use_gliner: Whether to use GLiNER in hybrid mode
            entity_list: List of entity types to detect

        Returns:
            Dictionary with detector and model information
        """
        # Acquire lock to ensure thread-safe detector initialization
        async with BatchProcessingService._detector_access_lock:
            log_info(f"[BATCH] Pre-initializing {detection_engine.name} detector")

            detector = None
            model_info = {}

            if detection_engine == EntityDetectionEngine.HYBRID:
                # Configure hybrid detector options
                config = {
                    "use_presidio": use_presidio,
                    "use_gemini": use_gemini,
                    "use_gliner": use_gliner,
                    "entities": entity_list
                }

                # Get or initialize required component detectors first
                if use_presidio:
                    initialization_service.get_presidio_detector()
                if use_gemini:
                    initialization_service.get_gemini_detector()
                if use_gliner:
                    initialization_service.get_gliner_detector(entity_list)

                # Get hybrid detector from initialization service
                detector = initialization_service.get_hybrid_detector(config)

                # Model info
                model_info = {
                    "engine": "hybrid",
                    "engines_used": {
                        "presidio": use_presidio,
                        "gemini": use_gemini,
                        "gliner": use_gliner
                    }
                }
            elif detection_engine == EntityDetectionEngine.PRESIDIO:
                detector = initialization_service.get_presidio_detector()
                model_info = {"engine": "presidio"}
            elif detection_engine == EntityDetectionEngine.GEMINI:
                detector = initialization_service.get_gemini_detector()
                model_info = {"engine": "gemini"}
            elif detection_engine == EntityDetectionEngine.GLINER:
                detector = initialization_service.get_gliner_detector(entity_list)
                model_info = {"engine": "gliner"}

            # Validate that a detector was successfully initialized
            if detector is None:
                log_error(f"[BATCH] Failed to initialize {detection_engine.name} detector")
                raise ValueError(f"Failed to initialize {detection_engine.name} detector")

            log_info(f"[BATCH] Successfully pre-initialized {detection_engine.name} detector")

            return {
                "detector": detector,
                "model_info": model_info
            }