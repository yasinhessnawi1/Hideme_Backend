"""
Unified utilities for batch file processing with centralized PDF handling.

This class provides specialized functions for batch processing operations,
ensuring all operations use the centralized PDF processing functionality
for consistent behavior, optimal performance, and security.
"""
import asyncio
import json
import os
import time
import zipfile
from typing import List, Dict, Any, Tuple, Optional, Union, Set, BinaryIO

from fastapi import UploadFile, BackgroundTasks
from starlette.responses import StreamingResponse

from backend.app.document_processing.pdf import PDFRedactionService, PDFTextExtractor
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.logging.secure_logging import log_batch_operation
from backend.app.utils.memory_management import memory_monitor
from backend.app.utils.parallel.core import ParallelProcessingCore, BatchProcessor
from backend.app.utils.secure_file_utils import SecureTempFileManager
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.validation.data_minimization import minimize_extracted_data
from backend.app.utils.validation.file_validation import validate_mime_type, sanitize_filename

# Constants
CHUNK_SIZE = 64 * 1024  # 64KB for streaming responses
MAX_PDF_SIZE_MB = 25  # 25MB maximum PDF size
MAX_BATCH_SIZE = 10  # Maximum files per batch


class BatchProcessingUtils:
    """
    Unified utilities for batch file processing with centralized PDF handling.

    This class provides specialized functions for batch processing operations,
    ensuring all operations use the centralized PDF processing functionality
    for consistent behavior, optimal performance, and security.
    """

    @staticmethod
    async def validate_files(
            files: List[UploadFile],
            allowed_types: Optional[Set[str]] = None,
            max_size_mb: int = MAX_PDF_SIZE_MB
    ) -> List[Tuple[UploadFile, bytes, str]]:
        if not files:
            return []
        if allowed_types is None:
            allowed_types = {
                "application/pdf",
                "text/plain",
                "text/csv",
                "text/markdown",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            }
        max_size_bytes = max_size_mb * 1024 * 1024
        valid_files = []
        for file in files:
            try:
                content_type = file.content_type or "application/octet-stream"
                if not validate_mime_type(content_type, allowed_types):
                    log_warning(f"Skipping file with unsupported type: {file.filename} ({content_type})")
                    continue
                await file.seek(0)
                content = await file.read()
                if len(content) > max_size_bytes:
                    log_warning(
                        f"File too large: {file.filename} ({len(content) / (1024 * 1024):.1f} MB > {max_size_mb} MB)")
                    continue
                safe_filename = sanitize_filename(file.filename or "unnamed_file")
                valid_files.append((file, content, safe_filename))
            except Exception as e:
                error_id = SecurityAwareErrorHandler.log_processing_error(e, "file_validation",
                                                                          file.filename or "unnamed_file")
                log_error(f"Error validating file {file.filename}: {str(e)} [error_id={error_id}]")
        return valid_files


    @staticmethod
    async def extract_text_from_pdf_batch(
            pdf_files: List[Union[str, bytes, BinaryIO]],
            max_workers: Optional[int] = None,
            detect_images: bool = False,
            remove_images: bool = False
    ) -> List[Tuple[int, Dict[str, Any]]]:
        if not pdf_files:
            return []
        if max_workers is None:
            max_workers = await BatchProcessor.adaptive_batch_size(len(pdf_files))
        log_info(f"Processing {len(pdf_files)} PDFs with {max_workers} workers")
        async def process_pdf(item):
            try:
                idx, pdf_content = item
                extractor = PDFTextExtractor(pdf_content)
                result = extractor.extract_text(detect_images=detect_images, remove_images=remove_images)
                extractor.close()
                return idx, result
            except Exception as e:
                file_id = f"pdf_file_{idx}"
                error_id = SecurityAwareErrorHandler.log_processing_error(e, "batch_pdf_extraction", file_id)
                log_error(f"Error extracting text from PDF at index {idx}: {str(e)} [error_id={error_id}]")
                return idx, {"error": str(e), "pages": []}
        indexed_items = [(i, content) for i, content in enumerate(pdf_files) if content is not None]
        operation_id = f"pdf_extraction_{time.time():.0f}"
        results = await ParallelProcessingCore.process_in_parallel(
            items=indexed_items,
            processor=process_pdf,
            max_workers=max_workers,
            operation_id=operation_id
        )
        return [result for result in results if result[1] is not None]

    @staticmethod
    async def detect_entities_in_batch(
            extracted_data_list: List[Tuple[int, Any]],
            detector,
            requested_entities: Optional[List[str]] = None,
            max_workers: Optional[int] = None
    ) -> List[Tuple[int, Tuple[str, List[Dict[str, Any]], Dict[str, Any]]]]:
        """
        Process a batch of extracted documents to detect sensitive entities.

        Args:
            extracted_data_list: List of tuples (index, extracted_data) where extracted_data is expected to be a dict.
            detector: The entity detection engine instance.
            requested_entities: Optional list of entity types to detect.
            max_workers: Maximum number of parallel workers.

        Returns:
            List of tuples (index, detection_result) where detection_result is a tuple
            (anonymized_text, entities, redaction_mapping). In case of any error, an empty result is returned.
        """
        if not extracted_data_list:
            return []

        # This function now always returns a valid result tuple even if nothing is detected.
        DEFAULT_DETECTION_RESULT = ("", [], {"pages": []})

        async def detect_entities(item: Tuple[int, Any]) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
            _inner_idx, data = item
            try:
                # Convert data to dict if needed
                if not isinstance(data, dict):
                    if isinstance(data, tuple):
                        try:
                            if len(data) == 2:
                                full_text, pages = data
                                log_info(f"[DEBUG] Converting 2-element tuple to dict for item {_inner_idx}.")
                                data = {"full_text": full_text, "pages": pages}
                            elif len(data) >= 3:
                                log_info(f"[DEBUG] Converting tuple (len={len(data)}) to dict for item {_inner_idx}.")
                                data = {"full_text": data[0], "pages": data[1]}
                            else:
                                log_warning(f"[WARNING] Unexpected tuple format for item {_inner_idx}: {data}")
                                data = {}
                        except Exception as ex:
                            log_error(f"[ERROR] Failed to convert tuple to dict for item {_inner_idx}: {str(ex)}")
                            data = {}
                    else:
                        log_warning(
                            f"[WARNING] Extracted data at index {_inner_idx} is of type {type(data)}; expected dict or tuple.")
                        data = {}

                # Log the minimized data for debugging purposes.
                minimized_data = minimize_extracted_data(data)
                log_info(f"[DEBUG] Minimized data for item {_inner_idx}: {minimized_data}")

                # Ensure 'pages' key exists
                if "pages" not in minimized_data:
                    log_warning(
                        f"[WARNING] Minimized data for item {_inner_idx} missing 'pages' key. Adding empty list.")
                    minimized_data["pages"] = []

                # Call the detector (using async if available, or via thread)
                try:
                    if hasattr(detector, 'detect_sensitive_data_async'):
                        raw_result = await asyncio.wait_for(
                            detector.detect_sensitive_data_async(minimized_data, requested_entities),
                            timeout=120.0  # 2 minute timeout per document
                        )
                    else:
                        raw_result = await asyncio.to_thread(
                            detector.detect_sensitive_data, minimized_data, requested_entities
                        )
                except asyncio.TimeoutError:
                    log_warning(f"[WARNING] Detection timeout for item {_inner_idx}")
                    return DEFAULT_DETECTION_RESULT
                except Exception as e:
                    log_error(f"[ERROR] Detection error for item {_inner_idx}: {str(e)}")
                    return DEFAULT_DETECTION_RESULT

                if raw_result is None:
                    log_warning(f"[WARNING] Null detection result for item {_inner_idx}")
                    return DEFAULT_DETECTION_RESULT

                if not (isinstance(raw_result, tuple) and len(raw_result) == 3):
                    log_warning(f"[WARNING] Invalid detection result format for item {_inner_idx}: {type(raw_result)}")
                    return DEFAULT_DETECTION_RESULT

                anonymized_text, entities, redaction_mapping = raw_result

                if not isinstance(anonymized_text, str):
                    log_warning(
                        f"[WARNING] Invalid anonymized_text type for item {_inner_idx}: {type(anonymized_text)}. Converting to empty string.")
                    anonymized_text = ""
                if not isinstance(entities, list):
                    log_warning(
                        f"[WARNING] Invalid entities type for item {_inner_idx}: {type(entities)}. Converting to empty list.")
                    entities = []

                if not isinstance(redaction_mapping, dict):
                    if isinstance(redaction_mapping, tuple):
                        found = False
                        for element in redaction_mapping:
                            if isinstance(element, dict):
                                redaction_mapping = element
                                found = True
                                break
                        if not found:
                            log_warning(
                                f"[WARNING] No dict found in redaction_mapping tuple for item {_inner_idx}. Using default mapping.")
                            redaction_mapping = {"pages": []}
                    else:
                        log_warning(
                            f"[WARNING] Invalid redaction_mapping type for item {_inner_idx}: {type(redaction_mapping)}. Using default mapping.")
                        redaction_mapping = {"pages": []}
                else:
                    pages_val = redaction_mapping.get("pages")
                    if not isinstance(pages_val, list):
                        log_warning(
                            f"[WARNING] Invalid 'pages' in redaction_mapping for item {_inner_idx}: {type(pages_val)}. Setting to empty list.")
                        redaction_mapping["pages"] = []

                log_info(f"[DEBUG] Detection successful for item {_inner_idx}: {len(entities)} entities found.")
                return anonymized_text, entities, redaction_mapping
            except Exception as e:
                error_id = SecurityAwareErrorHandler.log_processing_error(e, "entity_detection", f"file_{_inner_idx}")
                log_error(
                    f"[ERROR] Exception during entity detection for item {_inner_idx}: {str(e)} [error_id={error_id}]")
                return DEFAULT_DETECTION_RESULT

        if max_workers is None:
            max_workers = await BatchProcessor.adaptive_batch_size(len(extracted_data_list))
        operation_id = f"entity_detection_{time.time():.0f}"
        log_info(
            f"Starting entity detection for {len(extracted_data_list)} documents with {max_workers} workers [operation_id={operation_id}]")
        detection_results = await ParallelProcessingCore.process_in_parallel(
            items=extracted_data_list,
            processor=detect_entities,
            max_workers=max_workers,
            operation_id=operation_id
        )
        # Ensure we always return valid tuples, even if some items failed.
        return [(idx, result if result is not None else DEFAULT_DETECTION_RESULT) for idx, result in detection_results]


    @staticmethod
    def determine_processing_strategy(
            files: List[UploadFile],
            current_memory_usage: Optional[float] = None
    ) -> Tuple[bool, int, int]:
        if current_memory_usage is None:
            current_memory_usage = memory_monitor.get_memory_usage()
        total_size = 0
        for file in files:
            file_size = getattr(file, 'size', None)
            if file_size is not None:
                total_size += file_size
            else:
                total_size += 1024 * 1024
        use_memory_processing = True
        if total_size > 50 * 1024 * 1024:
            use_memory_processing = False
        if current_memory_usage > 75:
            use_memory_processing = False
        if current_memory_usage > 80:
            max_parallel_files = 2
        elif current_memory_usage > 60:
            max_parallel_files = 4
        else:
            max_parallel_files = 8
        return use_memory_processing, total_size, max_parallel_files

    @classmethod
    def get_optimal_batch_size(cls, file_count: int, total_bytes: int = 0) -> int:
        MAX_PARALLELISM = 8
        MIN_MEMORY_PER_WORKER = 100 * 1024 * 1024
        MAX_MEMORY_PERCENTAGE = 80
        if file_count < 0:
            raise ValueError("file_count cannot be negative")
        file_count = max(1, file_count)
        total_bytes = max(0, total_bytes)
        try:
            import psutil
            cpu_count = os.cpu_count() or 4
            available_memory = psutil.virtual_memory().available
            current_memory_percent = float(psutil.virtual_memory().percent)
        except Exception:
            cpu_count = 4
            available_memory = 4 * 1024 * 1024 * 1024
            current_memory_percent = 50.0
        cpu_based_workers = max(1, min(cpu_count - 1, file_count, MAX_PARALLELISM))
        if total_bytes > 0:
            avg_bytes_per_file = total_bytes / max(file_count, 1)
            estimated_memory_per_worker = avg_bytes_per_file * 5
            memory_based_workers = max(1, int(available_memory / estimated_memory_per_worker))
        else:
            memory_based_workers = max(1, int(available_memory / MIN_MEMORY_PER_WORKER))
        if current_memory_percent > 90:
            memory_pressure_factor = 0.2
            log_warning(f"[BATCH] Critical memory pressure detected ({current_memory_percent}%), reducing workers to minimum")
        elif current_memory_percent > MAX_MEMORY_PERCENTAGE:
            memory_pressure_factor = 0.5
            log_warning(f"[BATCH] High memory pressure detected ({current_memory_percent}%), reducing parallelism")
        elif current_memory_percent > 70:
            memory_pressure_factor = 0.7
            log_info(f"[BATCH] Moderate memory pressure detected ({current_memory_percent}%), adjusting parallelism")
        else:
            memory_pressure_factor = 1.0
        optimal_workers = min(
            cpu_based_workers,
            memory_based_workers,
            max(1, int(cpu_based_workers * memory_pressure_factor)),
            file_count
        )
        log_info(f"[BATCH] Optimal batch size: {optimal_workers} workers (CPU: {cpu_count}, "
                 f"Memory: {available_memory / 1024 / 1024:.1f}MB, Files: {file_count}, "
                 f"Memory pressure: {current_memory_percent}%)")
        return optimal_workers
