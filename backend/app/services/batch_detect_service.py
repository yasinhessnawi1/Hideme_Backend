import asyncio
import time
import uuid
from typing import List, Dict, Any, Optional, Tuple

from fastapi import UploadFile

from backend.app.document_processing.detection_updater import DetectionResultUpdater
from backend.app.document_processing.pdf_extractor import PDFTextExtractor
from backend.app.entity_detection import EntityDetectionEngine
from backend.app.services.base_detect_service import BaseDetectionService
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.helpers.json_helper import validate_requested_entities
from backend.app.utils.logging.logger import log_info, log_error
from backend.app.utils.logging.secure_logging import log_batch_operation
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.system_utils.memory_management import memory_monitor
from backend.app.utils.validation.data_minimization import minimize_extracted_data
from backend.app.utils.validation.sanitize_utils import sanitize_detection_output



class BatchDetectService(BaseDetectionService):
    """
    Service for batch entity detection.
    This service reads PDF files, extracts their text in batch mode,
    and applies entity detection using a pre-initialized detector.
    """

    @staticmethod
    async def detect_entities_in_files(
            files: List[UploadFile],
            requested_entities: Optional[str] = None,
            detection_engine: EntityDetectionEngine = EntityDetectionEngine.PRESIDIO,
            max_parallel_files: Optional[int] = None,
            use_presidio: bool = True,
            use_gemini: bool = False,
            use_gliner: bool = False,
            remove_words: Optional[str] = None
    ) -> Dict[str, Any]:
        start_time = time.time()
        batch_id = str(uuid.uuid4())
        log_info(f"Starting batch entity detection (Batch ID: {batch_id})")

        # Validate and prepare the entity list.
        try:
            entity_list = validate_requested_entities(requested_entities) if requested_entities else []
        except Exception as e:
            return SecurityAwareErrorHandler.handle_batch_processing_error(e, "entity_validation", len(files))

        # Initialize the detector.
        try:
            detector = await BatchDetectService._get_initialized_detector(
                detection_engine, use_presidio, use_gemini, use_gliner, entity_list
            )
        except Exception as e:
            return SecurityAwareErrorHandler.handle_batch_processing_error(e, "detector_initialization", len(files))

        # Determine optimal parallelism; default to 4 workers if not provided.
        optimal_workers = max_parallel_files if max_parallel_files is not None else 4
        log_info(f"Processing {len(files)} files with {optimal_workers} workers (Batch ID: {batch_id})")

        # Read file contents, filenames, and metadata.
        pdf_files, file_names, file_metadata = await BatchDetectService._read_pdf_files(files)

        # Filter valid PDFs.
        valid_pdf_files = [content for content in pdf_files if content is not None]

        # Batch extract text from valid PDFs.
        extraction_map = await BatchDetectService._batch_extract_text(valid_pdf_files, optimal_workers)

        # Process each file for detection.
        detection_results = []
        valid_count = 0
        for i, filename in enumerate(file_names):
            if pdf_files[i] is None:
                detection_results.append({
                    "file": filename,
                    "status": "error",
                    "error": "Not a valid PDF file."
                })
                continue
            extracted = extraction_map.get(valid_count)
            valid_count += 1
            if not extracted or ("error" in extracted and extracted["error"]):
                detection_results.append({
                    "file": filename,
                    "status": "error",
                    "error": extracted.get("error", "Extraction failed") if extracted else "Extraction missing"
                })
                continue
            result = await BatchDetectService._process_detection_for_file(
                extracted, filename, file_metadata[i], entity_list, detector,
                detection_engine, use_presidio, use_gemini, use_gliner,
                remove_words=remove_words
            )
            detection_results.append(result)

        total_time = time.time() - start_time
        batch_summary = {
            "batch_id": batch_id,
            "total_files": len(files),
            "successful": sum(1 for d in detection_results if d["status"] == "success"),
            "failed": sum(1 for d in detection_results if d["status"] != "success"),
            "total_time": total_time,
            "workers": optimal_workers
        }
        log_batch_operation("Batch Entity Detection", len(files), batch_summary["successful"], total_time)
        record_keeper.record_processing(
            operation_type="batch_entity_detection",
            document_type="multiple_files",
            entity_types_processed=entity_list,
            processing_time=total_time,
            file_count=len(files),
            entity_count=sum(len(d.get("results", {}).get("entities", []))
                             for d in detection_results if d["status"] == "success"),
            success=(batch_summary["successful"] > 0)
        )
        return {
            "batch_summary": batch_summary,
            "file_results": detection_results,
            "_debug": {
                "memory_usage": memory_monitor.get_memory_stats().get("current_usage"),
                "peak_memory": memory_monitor.get_memory_stats().get("peak_usage"),
                "operation_id": batch_id
            }
        }

    @staticmethod
    async def _read_pdf_files(files: List[UploadFile]) -> Tuple[List[Optional[bytes]], List[str], List[Dict[str, Any]]]:
        pdf_files = []
        file_names = []
        file_metadata = []
        for file in files:
            try:
                content_type = file.content_type or "application/octet-stream"
                if "pdf" in content_type.lower():
                    await file.seek(0)
                    content = await file.read()
                    pdf_files.append(content)
                    file_names.append(file.filename)
                    file_metadata.append({
                        "filename": file.filename,
                        "content_type": content_type,
                        "size": len(content)
                    })
                else:
                    pdf_files.append(None)
                    file_names.append(file.filename)
                    file_metadata.append({
                        "filename": file.filename,
                        "content_type": content_type,
                        "size": 0
                    })
            except Exception as e:
                log_error(f"Error reading file {file.filename}: {str(e)}")
                pdf_files.append(None)
                file_names.append(file.filename)
                file_metadata.append({
                    "filename": file.filename,
                    "content_type": "unknown",
                    "size": 0
                })
        return pdf_files, file_names, file_metadata

    @staticmethod
    async def _batch_extract_text(valid_pdf_files: List[bytes], optimal_workers: int) -> Dict[int, Dict[str, Any]]:
        extraction_results: List[Tuple[int, Dict[str, Any]]] = await PDFTextExtractor.extract_batch_text(
            valid_pdf_files, max_workers=optimal_workers
        )
        return {idx: result for idx, result in extraction_results}

    @staticmethod
    async def _process_detection_for_file(
            extracted: Dict[str, Any],
            filename: str,
            file_meta: Dict[str, Any],
            entity_list: List[str],
            detector: Any,
            detection_engine: EntityDetectionEngine,
            use_presidio: bool,
            use_gemini: bool,
            use_gliner: bool,
            remove_words: Optional[str] = None
    ) -> Dict[str, Any]:
        try:
            minimized_extracted = minimize_extracted_data(extracted)
            detection_raw = await asyncio.to_thread(detector.detect_sensitive_data, minimized_extracted, entity_list)
            if not (isinstance(detection_raw, tuple) and len(detection_raw) == 2):
                raise ValueError("Invalid detection result format")
            entities, redaction_mapping = detection_raw

            if remove_words:
                words_to_remove = BatchDetectService.parse_remove_words(remove_words)
                detection_result = (entities, redaction_mapping)
                updater = DetectionResultUpdater(minimized_extracted, detection_result)
                updated_result = updater.update_result(words_to_remove)
                redaction_mapping = updated_result.get("redaction_mapping", redaction_mapping)

            total_words = sum(len(page.get("words", [])) for page in minimized_extracted.get("pages", []))
            pages_count = len(minimized_extracted.get("pages", []))
            processing_times = {
                "words_count": total_words,
                "pages_count": pages_count,
                "entity_density": (len(entities) / total_words * 1000) if total_words > 0 else 0
            }
            sanitized = sanitize_detection_output(entities, redaction_mapping, processing_times)
            sanitized["file_info"] = {
                "filename": filename,
                "content_type": file_meta.get("content_type", "unknown"),
                "size": f"{round(file_meta.get('size', 0) / (1024 * 1024), 2)} MB"
            }
            model_info = {"engine": detection_engine.name}
            if detection_engine == EntityDetectionEngine.HYBRID:
                model_info = {
                    "engine": "hybrid",
                    "engines_used": {
                        "presidio": use_presidio,
                        "gemini": use_gemini,
                        "gliner": use_gliner
                    }
                }
            sanitized["model_info"] = model_info
            return {
                "file": filename,
                "status": "success",
                "results": sanitized
            }
        except Exception as e:
            log_error(f"Error detecting entities in file {filename}: {str(e)}")
            return {
                "file": filename,
                "status": "error",
                "error": str(e)
            }

    @staticmethod
    async def _get_initialized_detector(
            detection_engine: EntityDetectionEngine,
            use_presidio: bool = True,
            use_gemini: bool = False,
            use_gliner: bool = False,
            entity_list: Optional[List[str]] = None
    ) -> Any:
        if detection_engine == EntityDetectionEngine.HYBRID:
            config = {
                "use_presidio": use_presidio,
                "use_gemini": use_gemini,
                "use_gliner": use_gliner
            }
            if entity_list:
                config["entities"] = entity_list
            detector = initialization_service.get_detector(detection_engine, config)
        else:
            if entity_list and detection_engine == EntityDetectionEngine.GLINER:
                config = {"entities": entity_list}
                detector = initialization_service.get_detector(detection_engine, config)
            else:
                detector = initialization_service.get_detector(detection_engine, None)
        if detector is None:
            raise ValueError(f"Failed to initialize {detection_engine.name} detector")
        return detector