"""
BatchDetectService Module

This service processes a batch of PDF files for entity detection. It reads and validates PDF files,
extracts text in batch mode, and applies entity detection using a pre-initialized detector. It supports
both single and hybrid detection engines. The service logs operations, handles errors securely using
SecurityAwareErrorHandler, and tracks resource usage and processing metrics.
"""

import asyncio
import time
import uuid
from typing import List, Dict, Any, Optional, Tuple

from fastapi import UploadFile

# Import PDF extraction and entity detection modules.
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
    BatchDetectService Class

    This service processes multiple PDF files for entity detection in a batch.
    It reads and validates files, extracts text, and applies entity detection using either
    a single or a hybrid detection engine. The service logs processing details, handles errors securely,
    and records resource usage and performance metrics.
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
            remove_words: Optional[str] = None,
            threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Process a batch of PDF files for entity detection.

        Args:
            files: A list of UploadFile objects representing the files to process.
            requested_entities: A comma-separated string of entity types to detect.
            detection_engine: The detection engine to use (e.g., PRESIDIO, GLINER, HYBRID).
            max_parallel_files: Maximum number of files to process in parallel (default is 4 if not provided).
            use_presidio: Flag to enable the Presidio engine in hybrid mode.
            use_gemini: Flag to enable the Gemini engine in hybrid mode.
            use_gliner: Flag to enable the Gliner engine in hybrid mode.
            remove_words: Optional words to remove from the detected output.
            threshold (Optional[float]): A numeric threshold (0.00 to 1.00) for filtering the detection results.

        Returns:
            A dictionary containing the batch summary, individual file results, and debug information.

        Raises:
            Exception: Exceptions are logged and processed using SecurityAwareErrorHandler.
        """
        # Record the start time of the operation.
        start_time = time.time()
        # Generate a unique batch identifier.
        batch_id = str(uuid.uuid4())
        log_info(f"Starting batch entity detection (Batch ID: {batch_id})")

        # Check if the number of files exceeds the allowed maximum.
        if len(files) > MAX_FILES_COUNT:
            error_message = f"Too many files uploaded. Maximum allowed is {MAX_FILES_COUNT}."
            log_error(f"[SECURITY] {error_message} [operation_id={batch_id}]")
            return {"detail": error_message, "operation_id": batch_id}

        # Validate and prepare the list of requested entities.
        try:
            entity_list = validate_all_engines_requested_entities(requested_entities)
        except Exception as e:
            # Use SecurityAwareErrorHandler to log and create an error response for entity validation.
            return SecurityAwareErrorHandler.handle_batch_processing_error(e, "entity_validation", len(files))

        # Initialize the detection engine (detector) based on the provided engine type and flags.
        try:
            detector = await BatchDetectService._get_initialized_detector(
                detection_engine, use_presidio, use_gemini, use_gliner, entity_list
            )
        except Exception as e:
            # Use SecurityAwareErrorHandler to log and create an error response for detector initialization.
            return SecurityAwareErrorHandler.handle_batch_processing_error(e, "detector_initialization", len(files))

        # Determine the optimal number of workers for parallel processing.
        optimal_workers = max_parallel_files if max_parallel_files is not None else 4
        log_info(f"Processing {len(files)} files with {optimal_workers} workers (Batch ID: {batch_id})")

        # Read and validate PDF files, collecting contents, filenames, and metadata.
        pdf_files, file_names, file_metadata = await BatchDetectService._read_pdf_files(files, batch_id)

        # Filter out invalid PDF files.
        valid_pdf_files = [content for content in pdf_files if content is not None]

        # Batch extract text from the valid PDFs using parallel processing.
        try:
            extraction_map = await BatchDetectService._batch_extract_text(valid_pdf_files, optimal_workers)
        except Exception as e:
            # Use SecurityAwareErrorHandler to log and create an error response for extraction errors.
            return SecurityAwareErrorHandler.handle_batch_processing_error(e, "extraction", len(files))

        # Initialize an empty list to hold detection results for each file.
        detection_results = []
        valid_count = 0  # To align valid files with indices in the extraction map.
        # Loop through each file based on its filename.
        for i, filename in enumerate(file_names):
            # Check if the file content is valid; if not, append an error result.
            if pdf_files[i] is None:
                detection_results.append({
                    "file": filename,
                    "status": "error",
                    "error": "Not a valid PDF file."
                })
                continue

            # Retrieve the extraction result for the current valid file.
            extracted = extraction_map.get(valid_count)
            valid_count += 1

            # Check if extraction failed or returned an error.
            if not extracted or ("error" in extracted and extracted["error"]):
                detection_results.append({
                    "file": filename,
                    "status": "error",
                    "error": extracted.get("error", "Extraction failed") if extracted else "Extraction missing"
                })
                continue

            # Process entity detection for the current file with the defined threshold.
            result = await BatchDetectService._process_detection_for_file(
                extracted, filename, file_metadata[i], entity_list, detector,
                detection_engine, use_presidio, use_gemini, use_gliner,
                remove_words=remove_words,
                threshold=threshold
            )
            detection_results.append(result)

        # Calculate total processing time.
        total_time = time.time() - start_time
        # Build the batch summary.
        batch_summary = {
            "batch_id": batch_id,
            "total_files": len(files),
            "successful": sum(1 for d in detection_results if d["status"] == "success"),
            "failed": sum(1 for d in detection_results if d["status"] != "success"),
            "total_time": total_time,
            "workers": optimal_workers
        }
        # Log the batch operation with secure logging.
        log_batch_operation("Batch Entity Detection", len(files), batch_summary["successful"], total_time)
        # Record processing details for compliance.
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
        # Build the final response including debug information.
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
        Asynchronously read and validate a list of PDF files.

        For each file, this method:
          - Calls read_and_validate_file to perform comprehensive validation.
          - Appends file content (or None if validation fails) to the list.
          - Collects the filename and metadata such as content type, size, and read time.

        Args:
            files: A list of uploaded file objects.
            operation_id: Unique identifier for the operation (used for logging).

        Returns:
            A tuple containing:
              - A list of file contents (bytes) or None for invalid files.
              - A list of filenames.
              - A list of metadata dictionaries for each file.
        """
        pdf_files = []  # List to store file contents.
        file_names = []  # List to store file names.
        file_metadata = []  # List to store metadata for each file.
        # Iterate over each file in the input list.
        for file in files:
            try:
                # Validate and read the file.
                content, error_response, read_time = await read_and_validate_file(file, operation_id)
                # If validation fails, log an error and append None as the file content.
                if error_response:
                    log_error(f"[SECURITY] Validation failed for file {file.filename} [operation_id={operation_id}]")
                    pdf_files.append(None)
                else:
                    # If validation is successful, append the file content.
                    pdf_files.append(content)
                # Append the filename.
                file_names.append(file.filename)
                # Build metadata dictionary and append.
                file_metadata.append({
                    "filename": file.filename,
                    "content_type": file.content_type or "application/octet-stream",
                    "size": len(content) if content else 0,
                    "read_time": read_time
                })
            except Exception as e:
                # Log exceptions securely and record default metadata.
                log_error(f"[SECURITY] Exception reading file {file.filename}: {str(e)} [operation_id={operation_id}]")
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
        Extract text from a batch of valid PDF files concurrently.

        Args:
            valid_pdf_files: List of valid PDF file contents (bytes).
            optimal_workers: Number of workers to use concurrently.

        Returns:
            A mapping from file index to its extraction result (dictionary).
        """
        try:
            # Call the batch extraction method from PDFTextExtractor using the specified number of workers.
            extraction_results: List[Tuple[int, Dict[str, Any]]] = await PDFTextExtractor.extract_batch_text(
                valid_pdf_files, max_workers=optimal_workers
            )
            # Convert the list of tuples into a dictionary for easy access.
            return {idx: result for idx, result in extraction_results}
        except Exception as e:
            # Log extraction errors securely and propagate the exception.
            log_error(f"[SECURITY] Error in batch text extraction: {str(e)}")
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
            remove_words: Optional[str] = None,
            threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Process entity detection for a single file.

        This method minimizes the extracted text data, selects the proper detection function (hybrid or single),
        and then sanitizes and filters the detection output based on a given threshold.
        It computes processing metrics and constructs the final result.

        Args:
            extracted: Raw text extraction result from a PDF file.
            filename: Name of the file.
            file_meta: Metadata for the file.
            entity_list: List of entity types to detect.
            detector: Initialized detection engine instance.
            detection_engine: Enum representing the detection engine type.
            use_presidio: Flag for using Presidio in hybrid mode.
            use_gemini: Flag for using Gemini in hybrid mode.
            use_gliner: Flag for using Gliner in hybrid mode.
            remove_words: Optional words to remove from the detection output.
            threshold: Optional numeric threshold (0.00 to 1.00) used to filter detection results.

        Returns:
            A dictionary with the file name, status, and detection results (after threshold filtering).
        """
        try:
            # Minimize the extracted data to remove redundant or sensitive information.
            minimized_extracted = minimize_extracted_data(extracted)

            # Depending on the detection engine type, choose hybrid or single detection.
            if detection_engine == EntityDetectionEngine.HYBRID:
                combined_entities, combined_redaction_mapping = await BatchDetectService._process_hybrid_detection(
                    minimized_extracted, entity_list, detector, remove_words
                )
            else:
                combined_entities, combined_redaction_mapping = await BatchDetectService._process_single_detection(
                    minimized_extracted, entity_list, detector, remove_words
                )

            # Calculate total words and page count for performance metrics.
            total_words = sum(len(page.get("words", [])) for page in minimized_extracted.get("pages", []))
            pages_count = len(minimized_extracted.get("pages", []))
            processing_times = {
                "words_count": total_words,
                "pages_count": pages_count,
                "entity_density": (len(combined_entities) / total_words * 1000) if total_words > 0 else 0
            }

            # Apply threshold filtering ---
            # Use the centralized method from BaseDetectionService to filter the detection results.
            filtered_entities, filtered_redaction_mapping = BaseDetectionService.apply_threshold_filter(
                combined_entities, combined_redaction_mapping, threshold
            )

            # Sanitize the detection output using the filtered results.
            sanitized = sanitize_detection_output(filtered_entities, filtered_redaction_mapping, processing_times)

            # Append file metadata.
            sanitized["file_info"] = {
                "filename": filename,
                "content_type": file_meta.get("content_type", "unknown"),
                "size": f"{round(file_meta.get('size', 0) / (1024 * 1024), 2)} MB"
            }
            # Append model information based on the detection engine type.
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

            # Return the successful result for this file.
            return {
                "file": filename,
                "status": "success",
                "results": sanitized
            }
        except Exception as e:
            # Log detection errors securely and return an error result.
            log_error(f"[SECURITY] Error detecting entities in file {filename}: {str(e)}")
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
        Process entity detection using a hybrid engine that runs multiple detectors concurrently.

        Args:
            minimized_extracted: Minimized text extracted from a PDF.
            entity_list: List of entity types to detect.
            detector: Hybrid detector containing multiple individual detectors.
            remove_words: Optional words to remove from detection output.

        Returns:
            A tuple with:
              - A combined list of detected entities.
              - A merged redaction mapping dictionary.
        """
        combined_entities = []  # Initialize list to accumulate detected entities.
        combined_redaction_mapping = {"pages": []}  # Initialize combined redaction mapping.
        try:
            engine_tasks = []  # List to hold tasks for each individual detector.
            # Iterate over each individual detector in the hybrid detector.
            for individual_detector in detector.detectors:
                # Get the engine name by converting the class name to lowercase and removing 'entitydetector' suffix.
                engine_name = type(individual_detector).__name__.lower()
                if engine_name.endswith("entitydetector"):
                    engine_name = engine_name.replace("entitydetector", "")
                # Create a task to run the detector's sensitive data detection in a thread.
                task = asyncio.to_thread(
                    individual_detector.detect_sensitive_data,
                    minimized_extracted,
                    entity_list
                )
                engine_tasks.append((engine_name, task))
            # Unpack engine names and their corresponding tasks.
            engines_used, tasks = zip(*engine_tasks) if engine_tasks else ([], [])
            # Await all detection tasks concurrently.
            results = await asyncio.gather(*tasks, return_exceptions=True)
            # Process results from each detector.
            for engine, result in zip(engines_used, results):
                # If the result is an exception, log the error securely.
                if isinstance(result, Exception):
                    log_error(f"[SECURITY] Detection failed for engine {engine}: {result}")
                    continue
                # Verify that the result is a tuple with two elements.
                if not (isinstance(result, tuple) and len(result) == 2):
                    log_error(f"[SECURITY] Invalid result format for engine {engine}")
                    continue

                entities, redaction_mapping = result

                # If remove_words is specified, adjust the output accordingly.
                if remove_words:
                    entities, redaction_mapping = BatchDetectService.apply_removal_words(
                        minimized_extracted, (entities, redaction_mapping), remove_words
                    )

                # Replace original text in redaction mapping with sanitized values.
                redaction_mapping = replace_original_text_in_redaction(redaction_mapping, engine_name=engine)
                # Append the detected entities from this engine.
                combined_entities.extend(entities)
                # Merge redaction mapping pages.
                BatchDetectService._merge_pages(combined_redaction_mapping, redaction_mapping)
            return combined_entities, combined_redaction_mapping
        except Exception as e:
            # Log any errors in hybrid detection securely and propagate the exception.
            log_error(f"[SECURITY] Error in hybrid detection: {str(e)}")
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
        # Iterate over each page in the new redaction mapping.
        for page in redaction_mapping.get("pages", []):
            # Get the page number.
            page_number = page.get("page")
            # Find if this page already exists in the combined mapping.
            existing_page = next(
                (p for p in combined_mapping["pages"] if p.get("page") == page_number),
                None
            )
            # If the page exists, extend its 'sensitive' list.
            if existing_page:
                existing_page["sensitive"].extend(page.get("sensitive", []))
            else:
                # Otherwise, append the new page.
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
            minimized_extracted: Minimized text extracted from a PDF.
            entity_list: List of entity types to detect.
            detector: The detection engine to use.
            remove_words: Optional words to remove from the output.

        Returns:
            A tuple containing:
              - The list of detected entities.
              - The redaction mapping dictionary.
        """
        try:
            # Run the detection in a separate thread and await its result.
            detection_raw = await asyncio.to_thread(detector.detect_sensitive_data, minimized_extracted, entity_list)
            # Check if the result has the expected tuple format.
            if not (isinstance(detection_raw, tuple) and len(detection_raw) == 2):
                raise ValueError("Invalid detection result format")
            entities, redaction_mapping = detection_raw

            # If removal words are provided, adjust the output accordingly.
            if remove_words:
                entities, redaction_mapping = BatchDetectService.apply_removal_words(
                    minimized_extracted, (entities, redaction_mapping), remove_words
                )
            # Derive the engine name from the detector class name.
            engine_name = type(detector).__name__.lower()
            if engine_name.endswith("entitydetector"):
                engine_name = engine_name.replace("entitydetector", "")
            # Sanitize the redaction mapping by replacing original text.
            redaction_mapping = replace_original_text_in_redaction(redaction_mapping, engine_name=engine_name)
            return entities, redaction_mapping
        except Exception as e:
            # Log errors securely and propagate the exception.
            log_error(f"[SECURITY] Error in single detection: {str(e)}")
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
            # If using a hybrid detection engine, build the configuration accordingly.
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
                # For non-hybrid engines, pass configuration if needed.
                if entity_list and detection_engine == EntityDetectionEngine.GLINER:
                    config = {"entities": entity_list}
                    detector = initialization_service.get_detector(detection_engine, config)
                else:
                    detector = initialization_service.get_detector(detection_engine, None)
            # If initialization fails, raise an error.
            if detector is None:
                raise ValueError(f"Failed to initialize {detection_engine.name} detector")
            return detector
        except Exception as e:
            # Log detector initialization errors securely.
            log_error(f"[SECURITY] Error initializing detector: {str(e)}")
            raise e
