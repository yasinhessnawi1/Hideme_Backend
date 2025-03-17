import asyncio
import os
import time
import uuid
from typing import List, Dict, Any, Optional

from fastapi import UploadFile

from backend.app.factory.document_processing_factory import (
    DocumentProcessingFactory,
    DocumentFormat,
    EntityDetectionEngine
)
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.helpers.json_helper import validate_requested_entities
from backend.app.utils.helpers.parallel_helper import ParallelProcessingHelper
from backend.app.utils.logger import log_info
from backend.app.utils.sanitize_utils import sanitize_detection_output
from backend.app.utils.secure_file_utils import SecureTempFileManager
from backend.app.utils.secure_logging import log_batch_operation, log_sensitive_operation
from backend.app.utils.data_minimization import minimize_extracted_data
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.processing_records import record_keeper
from backend.app.utils.memory_management import MemoryOptimizedReader

# Threshold (in bytes) above which the file will be streamed rather than fully read in memory.
LARGE_FILE_THRESHOLD = 5 * 1024 * 1024  # 5MB

class BatchProcessingService:
    """
    Optimized service for processing multiple files in a single request.

    This service handles:
    - Processing multiple files with different formats.
    - Configurable parallel processing.
    - Memory-efficient processing by streaming large files.
    - Aggregated response formatting.
    - Detailed performance tracking.
    - Comprehensive GDPR compliance.
    - Advanced data minimization.
    - Enhanced security measures.
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
            detection_engine: EntityDetectionEngine = EntityDetectionEngine.PRESIDIO,
            detector_provider: Optional[Any] = None  # Optional dependency injection container
    ) -> Dict[str, Any]:
        start_time = time.time()
        batch_id = str(uuid.uuid4())

        # Validate entity list
        try:
            entity_list = validate_requested_entities(requested_entities) if requested_entities else []
        except Exception as e:
            return SecurityAwareErrorHandler.handle_batch_processing_error(
                e, "entity_validation", len(files)
            )

        # Pre-initialize detectors using dependency injection if provided
        log_info(f"[BATCH] Pre-initializing detectors for batch processing (Batch ID: {batch_id})")
        try:
            detectors = await BatchProcessingService._pre_initialize_detectors(
                detection_engine,
                use_presidio,
                use_gemini,
                use_gliner,
                entity_list,
                detector_provider=detector_provider
            )
        except Exception as e:
            return SecurityAwareErrorHandler.handle_batch_processing_error(
                e, "detector_initialization", len(files)
            )

        # Prepare file metadata (avoid storing file content in memory if possible)
        file_meta = {}
        for i, file in enumerate(files):
            try:
                file_id = f"batch_{batch_id}_file_{i}"
                file_meta[file_id] = {
                    "original_name": file.filename,
                    "content_type": file.content_type,
                    "size": 0,  # Updated after reading
                    "file_object": file  # Reference to file object
                }
            except Exception as e:
                SecurityAwareErrorHandler.log_processing_error(
                    e, "batch_file_preparation", file.filename or "unknown_file"
                )

        if not file_meta:
            return SecurityAwareErrorHandler.handle_batch_processing_error(
                ValueError("No valid files provided for processing"),
                "batch_file_validation",
                len(files)
            )

        optimal_workers = ParallelProcessingHelper.get_optimal_workers(
            len(file_meta), min_workers=1, max_workers=max_parallel_files
        )

        log_info(f"[BATCH] Processing {len(file_meta)} files with {optimal_workers} workers (Batch ID: {batch_id})")

        async def process_file(file_id: str) -> Dict[str, Any]:
            """Process a single file with optimized memory and streaming for large files."""
            file_start_time = time.time()
            meta = file_meta[file_id]
            file_name = meta.get("original_name", "unknown")
            content_type = meta.get("content_type", "application/octet-stream")
            file_object = meta.get("file_object")
            operation_id = f"{batch_id}_{file_id}"

            try:
                await file_object.seek(0)
                # Read a small chunk to decide on processing mode
                first_chunk = await file_object.read(1024)
                if len(first_chunk) < LARGE_FILE_THRESHOLD:
                    rest = await file_object.read()
                    contents = first_chunk + rest
                else:
                    file_object.seek(0)
                    contents = await MemoryOptimizedReader.read_file_chunks(file_object.fileno())

                meta["size"] = len(contents)

                # Determine document format from file extension
                doc_format = None
                if file_name.lower().endswith('.pdf'):
                    doc_format = DocumentFormat.PDF
                elif file_name.lower().endswith(('.docx', '.doc')):
                    doc_format = DocumentFormat.DOCX
                elif file_name.lower().endswith('.txt'):
                    doc_format = DocumentFormat.TXT

                extract_start = time.time()

                if doc_format == DocumentFormat.PDF:
                    # Process PDF entirely in memory
                    import io
                    import pymupdf
                    buffer = io.BytesIO(contents)
                    pdf_document = pymupdf.open(stream=buffer, filetype="pdf")
                    extracted_data = {"pages": []}
                    for page_num in range(len(pdf_document)):
                        page = pdf_document[page_num]
                        words = page.get_text("words")
                        page_words = []
                        for word in words:
                            x0, y0, x1, y1, text, *_ = word
                            if text.strip():
                                page_words.append({
                                    "text": text.strip(),
                                    "x0": x0,
                                    "y0": y0,
                                    "x1": x1,
                                    "y1": y1
                                })
                        if page_words:
                            extracted_data["pages"].append({
                                "page": page_num + 1,
                                "words": page_words
                            })
                    pdf_document.close()
                else:
                    # For non-PDF formats, process in memory if possible using the secure utility.
                    def process_extraction(file_obj):
                        extractor = DocumentProcessingFactory.create_document_extractor(file_obj, doc_format)
                        result = extractor.extract_text()
                        extractor.close()
                        return result

                    extracted_data = SecureTempFileManager.process_content_in_memory(
                        contents,
                        process_extraction,
                        use_path=False,
                        extension=f".{doc_format.name.lower()}" if doc_format else ".txt"
                    )

                extract_time = time.time() - extract_start
                minimized_data = minimize_extracted_data(extracted_data)

                detection_start = time.time()
                detector = detectors["detector"]

                if hasattr(detector, 'detect_sensitive_data_async'):
                    anonymized_text, entities, redaction_mapping = await detector.detect_sensitive_data_async(
                        minimized_data, entity_list
                    )
                else:
                    anonymized_text, entities, redaction_mapping = await asyncio.to_thread(
                        detector.detect_sensitive_data, minimized_data, entity_list
                    )

                detection_time = time.time() - detection_start

                total_words = sum(len(page.get("words", [])) for page in minimized_data.get("pages", []))
                entity_density = (len(entities) / total_words) * 1000 if total_words > 0 else 0

                processing_times = {
                    "extraction_time": extract_time,
                    "detection_time": detection_time,
                    "total_time": time.time() - file_start_time,
                    "words_count": total_words,
                    "pages_count": len(minimized_data.get("pages", [])),
                    "entity_density": entity_density
                }

                record_keeper.record_processing(
                    operation_type="batch_file_detection",
                    document_type=content_type,
                    entity_types_processed=entity_list,
                    processing_time=time.time() - file_start_time,
                    file_count=1,
                    entity_count=len(entities),
                    success=True
                )

                log_sensitive_operation(
                    "Batch File Detection",
                    len(entities),
                    time.time() - file_start_time,
                    file_type=os.path.splitext(file_name)[1] if file_name else "unknown",
                    words=total_words,
                    pages=processing_times["pages_count"],
                    operation_id=operation_id
                )

                sanitized_response = sanitize_detection_output(
                    anonymized_text, entities, redaction_mapping, processing_times
                )
                sanitized_response["file_info"] = {
                    "filename": file_name,
                    "content_type": content_type,
                    "size": meta["size"]
                }
                sanitized_response["model_info"] = detectors["model_info"]

                return {
                    "file": file_name,
                    "status": "success",
                    "results": sanitized_response
                }
            except Exception as e:
                record_keeper.record_processing(
                    operation_type="batch_file_detection",
                    document_type=content_type,
                    entity_types_processed=entity_list,
                    processing_time=time.time() - file_start_time,
                    file_count=1,
                    entity_count=0,
                    success=False
                )
                return SecurityAwareErrorHandler.handle_file_processing_error(e, "batch_file_detection", file_name)

        tasks = [process_file(file_id) for file_id in file_meta.keys()]
        results = await asyncio.gather(*tasks)

        batch_time = time.time() - start_time
        success_count = sum(1 for r in results if r.get("status") == "success")
        error_count = len(results) - success_count
        total_entities = sum(
            r.get("results", {}).get("entities_detected", {}).get("total", 0)
            for r in results if r.get("status") == "success"
        )

        response = {
            "batch_summary": {
                "batch_id": batch_id,
                "total_files": len(files),
                "successful": success_count,
                "failed": error_count,
                "total_entities": total_entities,
                "total_time": batch_time,
                "workers": optimal_workers
            },
            "file_results": results
        }

        record_keeper.record_processing(
            operation_type="batch_processing",
            document_type="multiple_files",
            entity_types_processed=entity_list,
            processing_time=batch_time,
            file_count=len(files),
            entity_count=total_entities,
            success=(success_count > 0)
        )

        log_batch_operation(
            "Batch Entity Detection",
            len(files),
            success_count,
            batch_time
        )

        return response

    @staticmethod
    async def _pre_initialize_detectors(
        detection_engine: EntityDetectionEngine,
        use_presidio: bool = True,
        use_gemini: bool = False,
        use_gliner: bool = False,
        entity_list: Optional[List[str]] = None,
        detector_provider: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Pre-initialize detectors before processing, using dependency injection if available.

        Args:
            detection_engine: Engine to use.
            use_presidio: Whether to use Presidio.
            use_gemini: Whether to use Gemini.
            use_gliner: Whether to use GLiNER.
            entity_list: List of entity types.
            detector_provider: Optional provider for detector instances (DI container).

        Returns:
            Dictionary with detector instance and model information.
        """
        async with BatchProcessingService._detector_access_lock:
            log_info(f"[BATCH] Pre-initializing {detection_engine.name} detector")
            detector = None
            model_info = {}

            if detection_engine == EntityDetectionEngine.HYBRID:
                config = {
                    "use_presidio": use_presidio,
                    "use_gemini": use_gemini,
                    "use_gliner": use_gliner,
                    "entities": entity_list
                }
                if detector_provider:
                    if use_presidio:
                        detector_provider.get_presidio_detector()
                    if use_gemini:
                        detector_provider.get_gemini_detector()
                    if use_gliner:
                        detector_provider.get_gliner_detector(entity_list)
                    detector = detector_provider.get_hybrid_detector(config)
                else:
                    if use_presidio:
                        initialization_service.get_presidio_detector()
                    if use_gemini:
                        initialization_service.get_gemini_detector()
                    if use_gliner:
                        initialization_service.get_gliner_detector(entity_list)
                    detector = initialization_service.get_hybrid_detector(config)
                model_info = {
                    "engine": "hybrid",
                    "engines_used": {
                        "presidio": use_presidio,
                        "gemini": use_gemini,
                        "gliner": use_gliner
                    }
                }
            elif detection_engine == EntityDetectionEngine.PRESIDIO:
                detector = detector_provider.get_presidio_detector() if detector_provider else initialization_service.get_presidio_detector()
                model_info = {"engine": "presidio"}
            elif detection_engine == EntityDetectionEngine.GEMINI:
                detector = detector_provider.get_gemini_detector() if detector_provider else initialization_service.get_gemini_detector()
                model_info = {"engine": "gemini"}
            elif detection_engine == EntityDetectionEngine.GLINER:
                detector = detector_provider.get_gliner_detector(entity_list) if detector_provider else initialization_service.get_gliner_detector(entity_list)
                model_info = {"engine": "gliner"}

            if detector is None:
                error = SecurityAwareErrorHandler.handle_detection_error(
                    ValueError(f"Failed to initialize {detection_engine.name} detector"),
                    "detector_initialization"
                )
                raise ValueError(error["error"])

            log_info(f"[BATCH] Successfully pre-initialized {detection_engine.name} detector")
            return {
                "detector": detector,
                "model_info": model_info
            }
