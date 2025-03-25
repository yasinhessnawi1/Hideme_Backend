"""
Consolidated batch processing utilities with unified PDF handling.

This module provides specialized batch processing functions that integrate directly
with the centralized PDF processing functionality, ensuring consistent behavior
across all batch operations while maintaining optimal performance and security.
"""
import asyncio
import json
import os
import time
import zipfile
from typing import List, Dict, Any, Tuple, Optional, Union, AsyncGenerator, Set, BinaryIO

from fastapi import UploadFile, BackgroundTasks
from starlette.responses import StreamingResponse

from backend.app.document_processing.pdf import PDFRedactionService, extraction_processor, PDFTextExtractor
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
        """
        Validate uploaded files, checking their types and sizes.

        Args:
            files: List of uploaded files
            allowed_types: Set of allowed MIME types
            max_size_mb: Maximum allowed file size in MB

        Returns:
            List of tuples (file, content, safe_filename) for valid files
        """
        if not files:
            return []

        # Set default allowed types if not provided
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
                # Validate MIME type
                content_type = file.content_type or "application/octet-stream"
                if not validate_mime_type(content_type, allowed_types):
                    log_warning(f"Skipping file with unsupported type: {file.filename} ({content_type})")
                    continue

                # Read and validate file size
                await file.seek(0)
                content = await file.read()

                if len(content) > max_size_bytes:
                    log_warning(
                        f"File too large: {file.filename} ({len(content) / (1024 * 1024):.1f} MB > {max_size_mb} MB)")
                    continue

                # Create safe filename
                safe_filename = sanitize_filename(file.filename or "unnamed_file")

                valid_files.append((file, content, safe_filename))

            except Exception as e:
                error_id = SecurityAwareErrorHandler.log_processing_error(e, "file_validation",
                                                                          file.filename or "unnamed_file")
                log_error(f"Error validating file {file.filename}: {str(e)} [error_id={error_id}]")

        return valid_files

    @staticmethod
    async def validate_files_in_batches(
            files: List[UploadFile],
            allowed_types: Optional[Set[str]] = None,
            max_size_mb: int = MAX_PDF_SIZE_MB,
            batch_size: int = MAX_BATCH_SIZE
    ) -> AsyncGenerator[List[Tuple[UploadFile, bytes, str]], None]:
        """
        Validate files in batches to manage memory usage efficiently.

        Args:
            files: List of uploaded files
            allowed_types: Set of allowed MIME types
            max_size_mb: Maximum allowed file size in MB
            batch_size: Maximum number of files per batch

        Yields:
            Batches of tuples (file, content, safe_filename) for valid files
        """
        if not files:
            return

        # Process files in batches
        for batch_start in range(0, len(files), batch_size):
            batch_end = min(batch_start + batch_size, len(files))
            batch_files = files[batch_start:batch_end]

            log_info(f"Validating file batch {batch_start + 1}-{batch_end} of {len(files)}")

            valid_files = await BatchProcessingUtils.validate_files(
                batch_files,
                allowed_types,
                max_size_mb
            )

            if valid_files:
                yield valid_files

            # Force garbage collection after each batch
            import gc
            gc.collect()

    @staticmethod
    async def extract_text_from_pdf_batch(
            pdf_files: List[Union[str, bytes, BinaryIO]],
            max_workers: Optional[int] = None,
            detect_images: bool = False,
            remove_images: bool = False
    ) -> List[Tuple[int, Dict[str, Any]]]:
        """
        Extract text from a batch of PDF files using the centralized PDFTextExtractor.

        Args:
            pdf_files: List of PDF files (paths, bytes, or file-like objects)
            max_workers: Maximum number of parallel workers (None for auto)
            detect_images: Whether to detect and include image information
            remove_images: Whether to remove images from the document

        Returns:
            List of tuples (index, extraction_result)
        """
        if not pdf_files:
            return []

        # Calculate optimal worker count if not specified
        if max_workers is None:
            max_workers = await BatchProcessor.adaptive_batch_size(len(pdf_files))

        log_info(f"Processing {len(pdf_files)} PDFs with {max_workers} workers")

        # Define processing function for each PDF
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

        # Create items with indices
        indexed_items = [(i, content) for i, content in enumerate(pdf_files) if content is not None]

        # Use parallel processing to process the batch
        operation_id = f"pdf_extraction_{time.time():.0f}"
        results = await ParallelProcessingCore.process_in_parallel(
            items=indexed_items,
            processor=process_pdf,
            max_workers=max_workers,
            operation_id=operation_id
        )

        # Return results with proper handling of None values
        return [result for result in results if result[1] is not None]

    @staticmethod
    async def detect_entities_in_batch(
            extracted_data_list: List[Tuple[int, Dict[str, Any]]],
            detector,
            requested_entities: Optional[List[str]] = None,
            max_workers: Optional[int] = None
    ) -> List[Tuple[int, Optional[Tuple[str, List[Dict[str, Any]], Dict[str, Any]]]]]:
        """
        Apply entity detection to a batch of extracted text data with improved error handling
        and result validation.

        Args:
            extracted_data_list: List of tuples (index, extracted_data)
            detector: Entity detector instance
            requested_entities: List of entity types to detect
            max_workers: Maximum number of parallel workers (calculated automatically if None)

        Returns:
            List of tuples (index, detection_result)
        """
        if not extracted_data_list:
            return []

        # Define processor function with improved error handling and validation
        async def detect_entities(item: Tuple[int, Dict[str, Any]]) -> Tuple[
            int, Optional[Tuple[str, List[Dict[str, Any]], Dict[str, Any]]]]:
            idx, data = item

            try:
                # Apply data minimization
                minimized_data = minimize_extracted_data(data)

                # Detect entities using the appropriate method with explicit timeout handling
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
                    log_warning(f"[WARNING] Detection timeout for item {idx}")
                    return idx, None
                except Exception as e:
                    log_error(f"[ERROR] Detection error for item {idx}: {str(e)}")
                    return idx, None

                # Validate the detection result format
                if raw_result is None:
                    log_warning(f"[WARNING] Null detection result for item {idx}")
                    return idx, None

                # Validate result is a tuple with 3 elements
                if not isinstance(raw_result, tuple) or len(raw_result) != 3:
                    log_warning(f"[WARNING] Invalid detection result format for item {idx}: {type(raw_result)}")
                    return idx, None

                # Validate individual components of the tuple
                anonymized_text, entities, redaction_mapping = raw_result

                if not isinstance(anonymized_text, str):
                    log_warning(f"[WARNING] Invalid anonymized_text type for item {idx}: {type(anonymized_text)}")
                    anonymized_text = ""  # Convert to valid type

                if not isinstance(entities, list):
                    log_warning(f"[WARNING] Invalid entities type for item {idx}: {type(entities)}")
                    entities = []  # Convert to valid type

                if not isinstance(redaction_mapping, dict):
                    log_warning(f"[WARNING] Invalid redaction_mapping type for item {idx}: {type(redaction_mapping)}")
                    redaction_mapping = {"pages": []}  # Convert to valid type

                # Ensure redaction_mapping has a "pages" key with a list value
                if "pages" not in redaction_mapping or not isinstance(redaction_mapping["pages"], list):
                    log_warning(f"[WARNING] Missing 'pages' in redaction_mapping for item {idx}")
                    redaction_mapping["pages"] = []

                # Return validated result
                return idx, (anonymized_text, entities, redaction_mapping)

            except Exception as e:
                error_id = SecurityAwareErrorHandler.log_processing_error(e, "entity_detection", f"file_{idx}")
                log_error(f"[ERROR] Error detecting entities in data at index {idx}: {str(e)} [error_id={error_id}]")
                return idx, None

        # Calculate optimal worker count if not specified
        if max_workers is None:
            max_workers = await BatchProcessor.adaptive_batch_size(len(extracted_data_list))

        # Process in parallel
        operation_id = f"entity_detection_{time.time():.0f}"
        log_info(
            f"Detecting entities in {len(extracted_data_list)} documents with {max_workers} workers [operation_id={operation_id}]")

        return await ParallelProcessingCore.process_in_parallel(
            items=extracted_data_list,
            processor=detect_entities,
            max_workers=max_workers,
            operation_id=operation_id
        )

    @staticmethod
    async def apply_redactions_to_batch(
            files: List[Tuple[int, Union[UploadFile, bytes, BinaryIO]]],
            redaction_mappings: List[Tuple[int, Dict[str, Any]]],
            output_dir: str,
            max_workers: Optional[int] = None
    ) -> list[Any] | list[tuple[int, tuple[int, dict[str, Any]] | None]]:
        """
        Apply redactions to a batch of PDF files using the centralized PDFRedactionService.

        Args:
            files: List of tuples (index, file)
            redaction_mappings: List of tuples (index, redaction_mapping)
            output_dir: Directory to save the redacted PDFs
            max_workers: Maximum number of parallel workers (calculated automatically if None)

        Returns:
            List of tuples (index, redaction_result)
        """
        if not files or not redaction_mappings:
            return []

        # Create a mapping of indices to redaction mappings
        mapping_dict = {idx: mapping for idx, mapping in redaction_mappings}

        # Prepare files and output paths
        process_items = []

        for idx, file in files:
            if idx not in mapping_dict:
                log_warning(f"No redaction mapping for file at index {idx}")
                continue

            mapping = mapping_dict[idx]

            # Prepare file content
            if isinstance(file, UploadFile):
                try:
                    await file.seek(0)
                    content = await file.read()
                    filename = file.filename or f"file_{idx}.pdf"
                except Exception as e:
                    log_error(f"Error reading file {getattr(file, 'filename', f'file_{idx}')}: {str(e)}")
                    continue
            elif isinstance(file, bytes):
                content = file
                filename = f"file_{idx}.pdf"
            elif hasattr(file, 'read') and callable(file.read):
                try:
                    content = file.read()
                    if hasattr(file, 'seek'):
                        await file.seek(0)
                    filename = getattr(file, 'name', f"file_{idx}.pdf")
                except Exception as e:
                    log_error(f"Error reading file-like object: {str(e)}")
                    continue
            else:
                log_warning(f"Unsupported file type at index {idx}: {type(file)}")
                continue

            # Create output path
            safe_filename = sanitize_filename(filename)
            output_path = os.path.join(output_dir, f"redacted_{safe_filename}")

            process_items.append((idx, content, mapping, output_path))

        if not process_items:
            return []

        # Define processor function
        async def apply_redaction(item: Tuple[int, bytes, Dict[str, Any], str]) -> Tuple[int, Dict[str, Any]]:
            idx, content, mapping, output_path = item

            try:
                # Use the centralized PDFRedactionService for consistent processing
                redactor = PDFRedactionService(content)
                redacted_path = redactor.apply_redactions(mapping, output_path)
                redactor.close()

                # Count the number of redactions applied
                redaction_count = sum(
                    len(page.get("sensitive", []))
                    for page in mapping.get("pages", [])
                )

                return idx, {
                    "status": "success",
                    "output_path": redacted_path,
                    "redactions_applied": redaction_count
                }
            except Exception as e:
                error_id = SecurityAwareErrorHandler.log_processing_error(e, "pdf_redaction", f"file_{idx}")
                log_error(f"Error applying redactions to PDF at index {idx}: {str(e)} [error_id={error_id}]")

                return idx, {
                    "status": "error",
                    "error": str(e)
                }

        # Calculate optimal worker count if not specified
        if max_workers is None:
            max_workers = await BatchProcessor.adaptive_batch_size(len(process_items))

        # Process in parallel
        operation_id = f"pdf_redaction_{time.time():.0f}"
        log_info(
            f"Applying redactions to {len(process_items)} PDFs with {max_workers} workers [operation_id={operation_id}]")

        return await ParallelProcessingCore.process_in_parallel(
            items=process_items,
            processor=apply_redaction,
            max_workers=max_workers,
            operation_id=operation_id
        )

    @staticmethod
    async def create_batch_zip_response(
            redaction_results: List[Tuple[int, Dict[str, Any]]],
            file_metadata: List[Dict[str, Any]],
            background_tasks: BackgroundTasks,
            start_time: float,
            batch_id: Optional[str] = None
    ) -> StreamingResponse:
        """
        Create a streaming response with a ZIP file containing redacted documents.

        Args:
            redaction_results: List of tuples (index, redaction_result)
            file_metadata: List of metadata for each file
            background_tasks: Background tasks for cleanup
            start_time: Start time of the batch processing
            batch_id: Optional batch identifier

        Returns:
            StreamingResponse with the ZIP file
        """
        # Create batch ID if not provided
        if batch_id is None:
            batch_id = f"batch_{time.time():.0f}"

        # Create a temporary ZIP file
        zip_path = await SecureTempFileManager.create_secure_temp_file_async(
            suffix=".zip",
            prefix=f"redaction_batch_{batch_id}_"
        )

        # Calculate batch summary
        successful = 0
        failed = 0
        total_redactions = 0

        # Create result mapping from (idx, result) tuples
        result_mapping = {}
        for idx, result in redaction_results:
            result_mapping[idx] = result
            if isinstance(result, dict) and result.get("status") == "success":
                successful += 1
                total_redactions += result.get("redactions_applied", 0)
            else:
                failed += 1

        total_time = time.time() - start_time

        # Create batch summary
        batch_summary = {
            "batch_id": batch_id,
            "total_files": len(file_metadata),
            "successful": successful,
            "failed": failed,
            "total_redactions": total_redactions,
            "total_time": total_time,
            "timestamp": time.time(),
            "file_results": []
        }

        # Create ZIP file
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Add redacted files to ZIP
            for idx, metadata in enumerate(file_metadata):
                # Add file to ZIP if redaction was successful
                if idx in result_mapping:
                    result = result_mapping[idx]

                    # Add result to batch summary
                    result_entry = {
                        "file": metadata.get("original_name", f"file_{idx}"),
                        "status": result.get("status", "error") if isinstance(result, dict) else "error",
                        "redactions_applied": result.get("redactions_applied", 0) if isinstance(result,
                                                                                                dict) and result.get(
                            "status") == "success" else 0
                    }

                    if isinstance(result, dict) and result.get("status") == "error" and "error" in result:
                        result_entry["error"] = result["error"]
                    elif not isinstance(result, dict):
                        result_entry["error"] = "Invalid result format"

                    batch_summary["file_results"].append(result_entry)

                    # Add file to ZIP if successful
                    if isinstance(result, dict) and result.get("status") == "success":
                        output_path = result.get("output_path")
                        if output_path and os.path.exists(output_path):
                            original_name = metadata.get("original_name", f"file_{idx}.pdf")
                            safe_name = sanitize_filename(original_name)
                            zipf.write(output_path, arcname=f"redacted_{safe_name}")
                else:
                    # Add missing result to summary
                    batch_summary["file_results"].append({
                        "file": metadata.get("original_name", f"file_{idx}"),
                        "status": "error",
                        "error": "No redaction result available"
                    })

            # Add batch summary to ZIP
            zipf.writestr("batch_summary.json", json.dumps(batch_summary, indent=2))

        # Record batch processing for GDPR compliance
        record_keeper.record_processing(
            operation_type="batch_redaction",
            document_type="multiple",
            entity_types_processed=[],
            processing_time=total_time,
            file_count=len(file_metadata),
            entity_count=total_redactions,
            success=(successful > 0)
        )

        # Log batch operation
        log_batch_operation(
            "Batch Redaction",
            len(file_metadata),
            successful,
            total_time
        )

        # Create streaming response
        async def stream_zip():
            try:
                with open(zip_path, "rb") as f:
                    while chunk := f.read(CHUNK_SIZE):
                        yield chunk
                        # Allow other tasks to run between chunks
                        await asyncio.sleep(0)
            except Exception as e:
                log_error(f"Error streaming ZIP file: {str(e)}")

        # Get memory statistics
        mem_stats = memory_monitor.get_memory_stats()

        # Schedule cleanup tasks
        background_tasks.add_task(
            lambda: asyncio.to_thread(SecureTempFileManager.secure_delete_file, zip_path)
        )

        # Create response
        return StreamingResponse(
             stream_zip(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename=redacted_batch_{batch_id}.zip",
                "X-Batch-ID": batch_id,
                "X-Batch-Time": f"{total_time:.3f}s",
                "X-Successful-Count": str(successful),
                "X-Failed-Count": str(failed),
                "X-Total-Redactions": str(total_redactions),
                "X-Memory-Usage": f"{mem_stats['current_usage']:.1f}%",
                "X-Peak-Memory": f"{mem_stats['peak_usage']:.1f}%"
            }
        )

    @staticmethod
    def determine_processing_strategy(
            files: List[UploadFile],
            current_memory_usage: Optional[float] = None
    ) -> Tuple[bool, int, int]:
        """
        Determine the optimal processing strategy based on files and system resources.

        Args:
            files: List of uploaded files
            current_memory_usage: Current memory usage percentage (obtained automatically if None)

        Returns:
            Tuple of (use_memory_processing, estimated_total_size, max_parallel_files)
        """
        # Get current memory usage if not provided
        if current_memory_usage is None:
            current_memory_usage = memory_monitor.get_memory_usage()

        # Estimate total size
        total_size = 0
        for file in files:
            file_size = getattr(file, 'size', None)
            if file_size is not None:
                total_size += file_size
            else:
                # Use a conservative estimate if size is unknown
                total_size += 1024 * 1024  # Assume 1MB per file

        # Determine processing strategy
        use_memory_processing = True

        # Use disk-based processing for large batches
        if total_size > 50 * 1024 * 1024:  # > 50MB total
            use_memory_processing = False

        # Use disk-based processing under high memory pressure
        if current_memory_usage > 75:  # > 75% memory usage
            use_memory_processing = False

        # Calculate max parallel files based on memory pressure
        if current_memory_usage > 80:
            max_parallel_files = 2  # Severe memory pressure
        elif current_memory_usage > 60:
            max_parallel_files = 4  # Moderate memory pressure
        else:
            max_parallel_files = 8  # Low memory pressure

        return use_memory_processing, total_size, max_parallel_files

    @classmethod
    def get_optimal_batch_size(cls, file_count: int, total_bytes: int = 0) -> int:
        """
        Calculate the optimal batch size based on system resources and file characteristics.

        Args:
            file_count: Number of files to process
            total_bytes: Total size of all files in bytes

        Returns:
            Optimal number of parallel workers
        """
        # Default configuration
        MAX_PARALLELISM = 8
        MIN_MEMORY_PER_WORKER = 100 * 1024 * 1024  # 100MB per worker
        MAX_MEMORY_PERCENTAGE = 80  # Max memory usage percentage

        # Ensure file_count is valid
        if file_count < 0:
            raise ValueError("file_count cannot be negative")

        file_count = max(1, file_count)  # Ensure at least 1 worker
        total_bytes = max(0, total_bytes)  # Prevent negative file sizes

        # Get system information
        try:
            import psutil
            cpu_count = os.cpu_count() or 4
            available_memory = psutil.virtual_memory().available
            current_memory_percent = float(psutil.virtual_memory().percent)  # Ensure it's a number
        except Exception:
            cpu_count = 4  # Assume a default of 4 CPU cores
            available_memory = 4 * 1024 * 1024 * 1024  # Assume 4GB
            current_memory_percent = 50.0  # Assume 50% usage

        # Base calculations on CPU cores, but adjust based on memory pressure
        cpu_based_workers = max(1, min(cpu_count - 1, file_count, MAX_PARALLELISM))

        # Calculate memory constraints
        if total_bytes > 0:
            avg_bytes_per_file = total_bytes / max(file_count, 1)  # Prevent division by zero
            estimated_memory_per_worker = avg_bytes_per_file * 5  # Assume 5x file size for processing
            memory_based_workers = max(1, int(available_memory / estimated_memory_per_worker))
        else:
            memory_based_workers = max(1, int(available_memory / MIN_MEMORY_PER_WORKER))

        # Further reduce workers based on memory pressure
        if current_memory_percent > 90:
            memory_pressure_factor = 0.2  # Aggressive reduction for extreme memory usage
            log_warning(
                f"[BATCH] Critical memory pressure detected ({current_memory_percent}%), reducing workers to minimum")
        elif current_memory_percent > MAX_MEMORY_PERCENTAGE:
            memory_pressure_factor = 0.5  # Reduce workers by half under high memory pressure
            log_warning(f"[BATCH] High memory pressure detected ({current_memory_percent}%), reducing parallelism")
        elif current_memory_percent > 70:
            memory_pressure_factor = 0.7  # Reduce workers by 30% under moderate memory pressure
            log_info(f"[BATCH] Moderate memory pressure detected ({current_memory_percent}%), adjusting parallelism")
        else:
            memory_pressure_factor = 1.0  # No reduction under normal memory pressure

        # Calculate final worker count based on all constraints
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
