import asyncio
import time
import uuid
from typing import List, Dict, Any, Optional, Tuple

from fastapi import UploadFile

from backend.app.document_processing.pdf import PDFTextExtractor
from backend.app.entity_detection import EntityDetectionEngine
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.helpers.json_helper import validate_requested_entities
from backend.app.utils.logging.logger import log_info, log_error
from backend.app.utils.logging.secure_logging import log_batch_operation
from backend.app.utils.memory_management import memory_monitor
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.validation.sanitize_utils import sanitize_detection_output

class BatchDetectService:
    """
    Service for batch entity detection.
    This service extracts text from PDFs in batch mode and applies entity detection using a specified detector.
    """

    @staticmethod
    async def detect_entities_in_files(
            files: List[UploadFile],
            requested_entities: Optional[str] = None,
            detection_engine: EntityDetectionEngine = EntityDetectionEngine.PRESIDIO,
            max_parallel_files: Optional[int] = None,
            use_presidio: bool = True,
            use_gemini: bool = False,
            use_gliner: bool = False
    ) -> Dict[str, Any]:
        start_time = time.time()
        batch_id = str(uuid.uuid4())
        log_info(f"Starting batch entity detection (Batch ID: {batch_id})")

        # Validate and prepare the entity list.
        try:
            entity_list = validate_requested_entities(requested_entities) if requested_entities else []
        except Exception as e:
            return SecurityAwareErrorHandler.handle_batch_processing_error(
                e, "entity_validation", len(files)
            )

        # Pre-initialize the detector.
        try:
            detector = await BatchDetectService._get_initialized_detector(
                detection_engine, use_presidio, use_gemini, use_gliner, entity_list
            )
        except Exception as e:
            return SecurityAwareErrorHandler.handle_batch_processing_error(
                e, "detector_initialization", len(files)
            )

        # Determine optimal parallelism; default to 4 workers if not provided.
        optimal_workers = max_parallel_files if max_parallel_files is not None else 4
        log_info(f"Processing {len(files)} files with {optimal_workers} workers (Batch ID: {batch_id})")

        # Prepare file contents and filenames.
        pdf_files = []
        file_names = []
        for file in files:
            try:
                content_type = file.content_type or "application/octet-stream"
                if "pdf" in content_type.lower():
                    await file.seek(0)
                    content = await file.read()
                    pdf_files.append(content)
                    file_names.append(file.filename)
                else:
                    pdf_files.append(None)
                    file_names.append(file.filename)
            except Exception as e:
                log_error(f"Error reading file {file.filename}: {str(e)}")
                pdf_files.append(None)
                file_names.append(file.filename)

        # Filter out non-PDF files.
        valid_pdf_files = [content for content in pdf_files if content is not None]
        valid_indices = [i for i, content in enumerate(pdf_files) if content is not None]

        # Batch extract text from valid PDFs.
        extraction_results: List[Tuple[int, Dict[str, Any]]] = await PDFTextExtractor.extract_batch_text(
            valid_pdf_files, max_workers=optimal_workers
        )
        extraction_map = {i: result for i, result in extraction_results}

        detection_results = []
        valid_count = 0
        for i, filename in enumerate(file_names):
            if pdf_files[i] is None:
                detection_results.append({
                    "file": filename,
                    "status": "error",
                    "error": "Not a valid PDF file."
                })
            else:
                extracted = extraction_map.get(valid_count)
                valid_count += 1
                if extracted is None or ("error" in extracted and extracted["error"]):
                    detection_results.append({
                        "file": filename,
                        "status": "error",
                        "error": extracted.get("error", "Extraction failed") if extracted else "Extraction missing"
                    })
                else:
                    try:
                        # Run the detector in an async thread.
                        detection_raw = await asyncio.to_thread(detector.detect_sensitive_data, extracted, entity_list)
                        if not (isinstance(detection_raw, tuple) and len(detection_raw) == 3):
                            raise ValueError("Invalid detection result format")
                        anonymized_text, entities, redaction_mapping = detection_raw
                        total_words = sum(len(page.get("words", [])) for page in extracted.get("pages", []))
                        pages_count = len(extracted.get("pages", []))
                        processing_times = {
                            "words_count": total_words,
                            "pages_count": pages_count,
                            "entity_density": (len(entities) / total_words * 1000) if total_words > 0 else 0
                        }
                        sanitized = sanitize_detection_output(anonymized_text, entities, redaction_mapping, processing_times)
                        sanitized["file_info"] = {
                            "filename": filename,
                            "content_type": extracted.get("content_type", "unknown"),
                            "size": extracted.get("size", 0)
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
                        detection_results.append({
                            "file": filename,
                            "status": "success",
                            "results": sanitized
                        })
                        record_keeper.record_processing(
                            operation_type="batch_file_detection",
                            document_type=extracted.get("content_type", "unknown"),
                            entity_types_processed=entity_list,
                            processing_time=0.0,
                            file_count=1,
                            entity_count=len(entities),
                            success=True
                        )
                    except Exception as e:
                        log_error(f"Error detecting entities in file {filename}: {str(e)}")
                        detection_results.append({
                            "file": filename,
                            "status": "error",
                            "error": str(e)
                        })

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