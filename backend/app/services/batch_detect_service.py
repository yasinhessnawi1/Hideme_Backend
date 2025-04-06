import asyncio
import time
import uuid
from typing import List, Dict, Any, Optional, Tuple

from fastapi import UploadFile

from backend.app.document_processing.pdf_extractor import PDFTextExtractor
from backend.app.entity_detection import EntityDetectionEngine
from backend.app.services.base_detect_service import BaseDetectionService
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.helpers.json_helper import validate_all_engines_requested_entities
from backend.app.utils.logging.logger import log_info, log_error
from backend.app.utils.logging.secure_logging import log_batch_operation
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.system_utils.memory_management import memory_monitor
from backend.app.utils.validation.data_minimization import minimize_extracted_data
from backend.app.utils.validation.file_validation import read_and_validate_file, MAX_FILES_COUNT
from backend.app.utils.validation.sanitize_utils import sanitize_detection_output, replace_original_text_in_redaction


class BatchDetectService(BaseDetectionService):
    """
    Service for batch entity detection. This service reads PDF files, extracts their text in batch mode,
    and applies entity detection using a pre-initialized detector. It supports both single and hybrid detection engines.
    Additionally, it performs logging, error handling, and resource tracking.
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
        """
        Process a batch of PDF files for entity detection.

        Args:
            files: A list of UploadFile objects representing the files to be processed.
            requested_entities: A comma-separated string of entity types to detect.
            detection_engine: The detection engine to use (e.g., PRESIDIO, GLINER, HYBRID).
            max_parallel_files: Maximum number of files to process in parallel. Defaults to 4 if not provided.
            use_presidio: Flag to enable Presidio engine (used in hybrid mode).
            use_gemini: Flag to enable Gemini engine (used in hybrid mode).
            use_gliner: Flag to enable Gliner engine (used in hybrid mode).
            remove_words: Optional words to remove from the detected output.

        Returns:
            A dictionary containing the batch summary, individual file results, and debug information.

        Raises:
            Exception: Propagates exceptions after logging and recording processing errors.
        """
        start_time = time.time()
        batch_id = str(uuid.uuid4())
        log_info(f"Starting batch entity detection (Batch ID: {batch_id})")

        # Check if the number of files exceeds the maximum allowed.
        if len(files) > MAX_FILES_COUNT:
            error_message = f"Too many files uploaded. Maximum allowed is {MAX_FILES_COUNT}."
            log_error(f"[SECURITY] {error_message} [operation_id={batch_id}]")
            return {"detail": error_message, "operation_id": batch_id}

        # Validate and prepare the entity list.
        try:
            entity_list = validate_all_engines_requested_entities(requested_entities)
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
        pdf_files, file_names, file_metadata = await BatchDetectService._read_pdf_files(files, batch_id)

        # Filter valid PDFs.
        valid_pdf_files = [content for content in pdf_files if content is not None]

        # Batch extract text from valid PDFs.
        try:
            extraction_map = await BatchDetectService._batch_extract_text(valid_pdf_files, optimal_workers)
        except Exception as e:
            return SecurityAwareErrorHandler.handle_batch_processing_error(e, "extraction", len(files))

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
    async def _read_pdf_files(
            files: List[UploadFile],
            operation_id: str
    ) -> Tuple[List[Optional[bytes]], List[str], List[Dict[str, Any]]]:
        """
        Asynchronously read and validate a list of PDF files using the enhanced file validation utilities.

        For each file, this method:
          - Invokes `read_and_validate_file` to perform comprehensive validation (MIME type, file size, PDF header,
            and safety checks).
          - Builds a list of file contents (as bytes) or `None` for invalid files.
          - Constructs a list of filenames and metadata (including content type, size, and read time).

        Args:
            files (List[UploadFile]): A list of uploaded file objects.
            operation_id (str): A unique identifier for the current operation (used for logging).

        Returns:
            Tuple[List[Optional[bytes]], List[str], List[Dict[str, Any]]]:
              - A list of file contents (or `None` if the file failed validation).
              - A list of filenames corresponding to the files.
              - A list of metadata dictionaries for each file (e.g., content type, size, read time).
        """
        pdf_files = []
        file_names = []
        file_metadata = []
        for file in files:
            try:
                # Validate and read each file using the validate file utility.
                content, error_response, read_time = await read_and_validate_file(file, operation_id)
                if error_response:
                    log_error(f"Validation failed for file {file.filename} [operation_id={operation_id}]")
                    pdf_files.append(None)
                else:
                    pdf_files.append(content)
                file_names.append(file.filename)
                file_metadata.append({
                    "filename": file.filename,
                    "content_type": file.content_type or "application/octet-stream",
                    "size": len(content) if content else 0,
                    "read_time": read_time
                })
            except Exception as e:
                log_error(f"Exception reading file {file.filename}: {str(e)} [operation_id={operation_id}]")
                pdf_files.append(None)
                file_names.append(file.filename)
                file_metadata.append({
                    "filename": file.filename,
                    "content_type": "unknown",
                    "size": 0,
                    "read_time": 0
                })
        return pdf_files, file_names, file_metadata

    @staticmethod
    async def _batch_extract_text(valid_pdf_files: List[bytes], optimal_workers: int) -> Dict[int, Dict[str, Any]]:
        """
        Extract text from a batch of valid PDF files using multiple workers.

        Args:
            valid_pdf_files: A list of PDF file contents (bytes).
            optimal_workers: Number of workers to use concurrently.

        Returns:
            A mapping from index to extraction result (dictionary).
        """
        try:
            extraction_results: List[Tuple[int, Dict[str, Any]]] = await PDFTextExtractor.extract_batch_text(
                valid_pdf_files, max_workers=optimal_workers
            )
            return {idx: result for idx, result in extraction_results}
        except Exception as e:
            log_error(f"Error in batch text extraction: {str(e)}")
            raise e

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
        """
        Process entity detection for a single file.

        This method minimizes the extracted data and delegates the detection task
        to either a hybrid or a single engine detection helper function.
        After detection, it computes processing metrics and sanitizes the output.

        Args:
            extracted: The raw extraction result from a PDF file.
            filename: The name of the file being processed.
            file_meta: Metadata dictionary for the file.
            entity_list: List of entities to detect.
            detector: The initialized detection engine (or hybrid detector).
            detection_engine: Enum representing the detection engine type.
            use_presidio: Flag for using the Presidio engine in hybrid mode.
            use_gemini: Flag for using the Gemini engine in hybrid mode.
            use_gliner: Flag for using the Gliner engine in hybrid mode.
            remove_words: Optional string of words to remove from the output.

        Returns:
            A dictionary with file processing status and results.
        """
        try:
            minimized_extracted = minimize_extracted_data(extracted)

            if detection_engine == EntityDetectionEngine.HYBRID:
                combined_entities, combined_redaction_mapping = await BatchDetectService._process_hybrid_detection(
                    minimized_extracted, entity_list, detector, remove_words
                )
            else:
                combined_entities, combined_redaction_mapping = await BatchDetectService._process_single_detection(
                    minimized_extracted, entity_list, detector, remove_words
                )

            total_words = sum(len(page.get("words", [])) for page in minimized_extracted.get("pages", []))
            pages_count = len(minimized_extracted.get("pages", []))
            processing_times = {
                "words_count": total_words,
                "pages_count": pages_count,
                "entity_density": (len(combined_entities) / total_words * 1000) if total_words > 0 else 0
            }
            sanitized = sanitize_detection_output(combined_entities, combined_redaction_mapping, processing_times)
            sanitized["file_info"] = {
                "filename": filename,
                "content_type": file_meta.get("content_type", "unknown"),
                "size": f"{round(file_meta.get('size', 0) / (1024 * 1024), 2)} MB"
            }
            if detection_engine == EntityDetectionEngine.HYBRID:
                sanitized["model_info"] = {
                    "engine": "hybrid",
                    "engines_used": {
                        "presidio": use_presidio,
                        "gemini": use_gemini,
                        "gliner": use_gliner
                    }
                }
            else:
                sanitized["model_info"] = {"engine": detection_engine.name}

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
    async def _process_hybrid_detection(
            minimized_extracted: Dict[str, Any],
            entity_list: List[str],
            detector: Any,
            remove_words: Optional[str] = None
    ) -> Tuple[List[Any], Dict[str, Any]]:
        """
        Process entity detection using a hybrid detection engine that utilizes multiple detectors concurrently.

        Args:
            minimized_extracted: The minimized text extracted from a PDF.
            entity_list: A list of entity types to detect.
            detector: A hybrid detector containing multiple individual detectors.
            remove_words: Optional string of words to remove from the detection output.

        Returns:
            A tuple containing:
                - A combined list of detected entities.
                - A merged redaction mapping dictionary.
        """
        combined_entities = []
        combined_redaction_mapping = {"pages": []}
        try:
            # Build a list of (engine_name, task) tuples for each detector.
            engine_tasks = []
            for individual_detector in detector.detectors:
                engine_name = type(individual_detector).__name__.lower()
                if engine_name.endswith("entitydetector"):
                    engine_name = engine_name.replace("entitydetector", "")
                task = asyncio.to_thread(
                    individual_detector.detect_sensitive_data,
                    minimized_extracted,
                    entity_list
                )
                engine_tasks.append((engine_name, task))

            engines_used, tasks = zip(*engine_tasks) if engine_tasks else ([], [])
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process each detector's result.
            for engine, result in zip(engines_used, results):
                if isinstance(result, Exception):
                    log_error(f"Detection failed for engine {engine}: {result}")
                    continue
                if not (isinstance(result, tuple) and len(result) == 2):
                    log_error(f"Invalid result format for engine {engine}")
                    continue

                entities, redaction_mapping = result

                if remove_words:
                    entities, redaction_mapping = BatchDetectService.apply_removal_words(
                        minimized_extracted, (entities, redaction_mapping), remove_words
                    )

                redaction_mapping = replace_original_text_in_redaction(redaction_mapping, engine_name=engine)
                combined_entities.extend(entities)
                BatchDetectService._merge_pages(combined_redaction_mapping, redaction_mapping)

            return combined_entities, combined_redaction_mapping
        except Exception as e:
            log_error(f"Error in hybrid detection: {str(e)}")
            raise e

    @staticmethod
    def _merge_pages(
            combined_mapping: Dict[str, Any],
            redaction_mapping: Dict[str, Any]
    ) -> None:
        """
        Merge pages from a new redaction mapping into the combined redaction mapping.

        Args:
            combined_mapping: The current combined redaction mapping.
            redaction_mapping: The new redaction mapping to merge.
        """
        for page in redaction_mapping.get("pages", []):
            page_number = page.get("page")
            existing_page = next(
                (p for p in combined_mapping["pages"] if p.get("page") == page_number),
                None
            )
            if existing_page:
                existing_page["sensitive"].extend(page.get("sensitive", []))
            else:
                combined_mapping["pages"].append(page)

    @staticmethod
    async def _process_single_detection(
            minimized_extracted: Dict[str, Any],
            entity_list: List[str],
            detector: Any,
            remove_words: Optional[str] = None
    ) -> Tuple[List[Any], Dict[str, Any]]:
        """
        Process entity detection using a single detection engine.

        Args:
            minimized_extracted: The minimized text extracted from a PDF.
            entity_list: A list of entity types to detect.
            detector: The detection engine to use.
            remove_words: Optional string of words to remove from the detection output.

        Returns:
            A tuple containing:
                - The list of detected entities.
                - The redaction mapping dictionary.
        """
        try:
            detection_raw = await asyncio.to_thread(detector.detect_sensitive_data, minimized_extracted, entity_list)
            if not (isinstance(detection_raw, tuple) and len(detection_raw) == 2):
                raise ValueError("Invalid detection result format")
            entities, redaction_mapping = detection_raw

            if remove_words:
                entities, redaction_mapping = BatchDetectService.apply_removal_words(
                    minimized_extracted, (entities, redaction_mapping), remove_words
                )
            # Replace original text in redaction mapping using the engine name derived from the detector.
            engine_name = type(detector).__name__.lower()
            if engine_name.endswith("entitydetector"):
                engine_name = engine_name.replace("entitydetector", "")
            redaction_mapping = replace_original_text_in_redaction(redaction_mapping, engine_name=engine_name)
            return entities, redaction_mapping
        except Exception as e:
            log_error(f"Error in single detection: {str(e)}")
            raise e

    @staticmethod
    async def _get_initialized_detector(
            detection_engine: EntityDetectionEngine,
            use_presidio: bool = True,
            use_gemini: bool = False,
            use_gliner: bool = False,
            entity_list: Optional[List[str]] = None
    ) -> Any:
        """
        Initialize and return an entity detection engine instance.

        Args:
            detection_engine: The detection engine to initialize.
            use_presidio: Flag to enable Presidio (for hybrid mode).
            use_gemini: Flag to enable Gemini (for hybrid mode).
            use_gliner: Flag to enable Gliner (for hybrid mode).
            entity_list: Optional list of entity types to detect.

        Returns:
            An initialized detector instance.

        Raises:
            ValueError: If the detector fails to initialize.
        """
        try:
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
        except Exception as e:
            log_error(f"Error initializing detector: {str(e)}")
            raise e
