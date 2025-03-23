"""
Enhanced batch processing helper with improved synchronization and resource management.

This module provides optimized utilities for parallel batch processing with enhanced
error handling, timeout management, and dynamic resource allocation to prevent
memory pressure and system congestion.
"""
import asyncio
import os
import time
import uuid
import logging
import psutil
from typing import List, Dict, Any, Callable, TypeVar, Coroutine, Tuple, Optional, AsyncGenerator, Set

from fastapi import UploadFile
from backend.app.utils.logger import log_info, log_warning, log_error
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.file_validation import validate_mime_type, sanitize_filename
from backend.app.utils.memory_management import memory_monitor
from backend.app.utils.secure_file_utils import SecureTempFileManager
from backend.app.utils.synchronization_utils import AsyncTimeoutSemaphore, LockPriority, AsyncTimeoutLock

T = TypeVar('T')
U = TypeVar('U')

logger = logging.getLogger(__name__)

class BatchProcessingHelper:
    """
    Enhanced helper for batch processing with improved synchronization and resource management.

    Features:
    - Dynamic task scheduling based on system resources
    - Timeout handling for long-running operations
    - Thread-safe and deadlock-resistant design
    - Automatic resource constraint management
    - Graceful failure handling with partial results
    """
    # Class-level semaphore for controlling global parallel processing
    _global_semaphore: Optional[AsyncTimeoutSemaphore] = None
    _access_lock = AsyncTimeoutLock("batch_helper_access_lock", priority=LockPriority.MEDIUM)

    # Constants for resource management
    MAX_PARALLELISM = 12  # Hard limit on parallelism regardless of cores
    DEFAULT_TIMEOUT = 300.0  # Default timeout for batch processing (5 minutes)
    MIN_MEMORY_PER_WORKER = 250 * 1024 * 1024  # 250 MB per worker minimum
    MAX_MEMORY_PERCENTAGE = 80  # Maximum percentage of memory to use

    @classmethod
    async def _init_global_semaphore(cls, max_workers: int) -> AsyncTimeoutSemaphore:
        """
        Initialize or update the global semaphore with the appropriate number of workers.

        Args:
            max_workers: Maximum number of parallel workers

        Returns:
            AsyncTimeoutSemaphore configured for the current system
        """
        async with cls._access_lock.acquire_timeout(timeout=5.0):
            if cls._global_semaphore is None:
                cls._global_semaphore = AsyncTimeoutSemaphore(
                    name="global_batch_semaphore",
                    value=max_workers,
                    priority=LockPriority.MEDIUM,
                    timeout=cls.DEFAULT_TIMEOUT
                )
                log_info(f"[BATCH] Initialized global semaphore with {max_workers} workers")
            elif cls._global_semaphore.current_value != max_workers:
                # Need to create a new semaphore with the updated value
                old_semaphore = cls._global_semaphore
                cls._global_semaphore = AsyncTimeoutSemaphore(
                    name="global_batch_semaphore",
                    value=max_workers,
                    priority=LockPriority.MEDIUM,
                    timeout=cls.DEFAULT_TIMEOUT
                )
                log_info(f"[BATCH] Updated global semaphore from {old_semaphore.current_value} to {max_workers} workers")

            return cls._global_semaphore

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
        # Ensure file_count is valid
        if file_count < 0:
            raise ValueError("file_count cannot be negative")

        file_count = max(1, file_count)  # Ensure at least 1 worker
        total_bytes = max(0, total_bytes)  # Prevent negative file sizes

        # Get system information
        try:
            cpu_count = os.cpu_count() or 4
            available_memory = psutil.virtual_memory().available
            current_memory_percent = float(psutil.virtual_memory().percent)  # Ensure it's a number
        except Exception:
            cpu_count = 4  # Assume a default of 4 CPU cores
            available_memory = 4 * 1024 * 1024 * 1024  # Assume 4GB
            current_memory_percent = 50.0  # Assume 50% usage

        # Base calculations on CPU cores, but adjust based on memory pressure
        cpu_based_workers = max(1, min(cpu_count - 1, file_count, cls.MAX_PARALLELISM))

        # Calculate memory constraints
        if total_bytes > 0:
            avg_bytes_per_file = total_bytes / max(file_count, 1)  # Prevent division by zero
            estimated_memory_per_worker = avg_bytes_per_file * 5  # Assume 5x file size for processing
            memory_based_workers = max(1, int(available_memory / estimated_memory_per_worker))
        else:
            memory_based_workers = max(1, int(available_memory / cls.MIN_MEMORY_PER_WORKER))

        # Further reduce workers based on memory pressure
        if current_memory_percent > 90:
            memory_pressure_factor = 0.2  # Aggressive reduction for extreme memory usage
            log_warning(
                f"[BATCH] Critical memory pressure detected ({current_memory_percent}%), reducing workers to minimum")
        elif current_memory_percent > cls.MAX_MEMORY_PERCENTAGE:
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

    @classmethod
    async def process_in_parallel(
            cls,
            items: List[T],
            processor: Callable[[T], Coroutine[Any, Any, U]],
            max_workers: Optional[int] = None,
            timeout: Optional[float] = None,
            item_timeout: Optional[float] = None
    ) -> List[Tuple[int, U]]:
        """
        Process a list of items asynchronously in parallel while ensuring controlled concurrency,
        timeout management, and error handling.

        Args:
            items: A list of items to process.
            processor: An asynchronous function to process each item.
            max_workers: The maximum number of concurrent workers (determined automatically if None).
            timeout: The overall timeout for processing the entire batch.
            item_timeout: The timeout for processing individual items.

        Returns:
            A list of tuples (index, result), where index is the original item index.
        """
        if not items:
            return []

        worker_count = max_workers or cls.get_optimal_batch_size(len(items))
        batch_timeout = timeout or cls.DEFAULT_TIMEOUT
        single_item_timeout = item_timeout or (batch_timeout / 2)

        semaphore = await cls._init_global_semaphore(worker_count)
        operation_id = str(uuid.uuid4())[:8]
        log_info(
            f"[BATCH] Starting parallel processing of {len(items)} items with {worker_count} workers (operation: {operation_id})"
        )

        start_time = time.time()
        completed, failed, _ = 0, 0, len(items)  # Replaced `total` with `_` since it's unused

        tasks = [
            cls._process_item(i, item, processor, semaphore, start_time, operation_id, single_item_timeout)
            for i, item in enumerate(items)
        ]

        try:
            results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=False), timeout=batch_timeout)
            log_info(
                f"[BATCH] Completed processing {len(items)} items in {time.time() - start_time:.2f}s: "
                f"{completed} completed, {failed} failed (operation: {operation_id})"
            )
            return results
        except asyncio.TimeoutError:
            log_error(f"[BATCH] Overall batch processing timed out after {batch_timeout}s (operation: {operation_id})")
            return []

    @classmethod
    async def _process_item(
            cls, index: int, item: T, processor: Callable[[T], Coroutine[Any, Any, U]],
            semaphore: AsyncTimeoutSemaphore, start_time: float, operation_id: str, single_item_timeout: float
    ) -> Tuple[int, U]:
        """
        Processes an individual item asynchronously while ensuring concurrency limits and handling exceptions.

        Args:
            index: The index of the item in the original list.
            item: The item to be processed.
            processor: The function responsible for processing the item.
            semaphore: The semaphore used for controlling concurrency.
            start_time: The timestamp when processing started.
            operation_id: A unique identifier for tracking batch operations.
            single_item_timeout: The maximum time allowed for processing an individual item.

        Returns:
            A tuple (index, result) containing the processed result or None if an error occurred.
        """
        try:
            async with semaphore.acquire_timeout(timeout=30.0):
                return await cls._execute_processing(index, item, processor, start_time, operation_id,
                                                     single_item_timeout)
        except TimeoutError:
            return cls._handle_processing_error(index, "semaphore_timeout", TimeoutError("Failed to acquire semaphore"),
                                                operation_id)
        except Exception as e:
            return cls._handle_processing_error(index, "unexpected", e, operation_id)

    @classmethod
    async def _execute_processing(
            cls, index: int, item: T, processor: Callable[[T], Coroutine[Any, Any, U]],
            start_time: float, operation_id: str, single_item_timeout: float
    ) -> Tuple[int, U]:
        """
        Executes the processing function for an individual item with a timeout.

        Args:
            index: The index of the item in the original list.
            item: The item to be processed.
            processor: The asynchronous function responsible for processing.
            start_time: The timestamp when processing started.
            operation_id: A unique identifier for tracking batch operations.
            single_item_timeout: The maximum time allowed for processing an individual item.

        Returns:
            A tuple (index, result) containing the processed result or None if an error occurred.
        """
        try:
            result = await asyncio.wait_for(processor(item), timeout=single_item_timeout)
            cls._log_progress(start_time, operation_id)
            return index, result
        except asyncio.TimeoutError:
            return cls._handle_processing_error(index, "timeout",
                                                TimeoutError(f"Processing timed out after {single_item_timeout}s"),
                                                operation_id)
        except Exception as e:
            return cls._handle_processing_error(index, "processing_error", e, operation_id)

    @classmethod
    def _handle_processing_error(cls, index: int, error_type: str, exception: Exception, operation_id: str) -> Tuple[
        int, None]:
        """
        Handles processing errors by logging them and returning a default failure response.

        Args:
            index: The index of the item that caused the error.
            error_type: The category of the error (e.g., timeout, unexpected).
            exception: The exception instance that was raised.
            operation_id: A unique identifier for tracking batch operations.

        Returns:
            A tuple (index, None) indicating the failure.
        """
        error_id = SecurityAwareErrorHandler.log_processing_error(
            exception, f"batch_item_{error_type}", f"item_{index}"
        )
        log_error(
            f"[BATCH] Error processing item {index}: {str(exception)} (error_id: {error_id}, operation: {operation_id})"
        )
        return index, None

    @classmethod
    def _log_progress(cls, start_time: float, operation_id: str):
        """
        Logs the batch processing progress at regular intervals.

        Args:
            start_time: The timestamp when batch processing started.
            operation_id: A unique identifier for tracking batch operations.
        """
        elapsed = time.time() - start_time
        mem_stats = memory_monitor.get_memory_stats()
        log_info(
            f"[BATCH] Processing ongoing... Elapsed time: {elapsed:.1f}s, memory usage: {mem_stats['current_usage']:.1f}% (operation: {operation_id})"
        )

    @classmethod
    async def process_pages_in_parallel(
        cls,
        pages: List[Dict[str, Any]],
        processor: Callable[[Dict[str, Any]], Coroutine[Any, Any, Tuple[Dict[str, Any], List[Dict[str, Any]]]]],
        max_workers: Optional[int] = None
    ) -> List[Tuple[int, Tuple[Dict[str, Any], List[Dict[str, Any]]]]]:
        """
        Process document pages in parallel with enhanced error handling.

        Args:
            pages: List of page dictionaries
            processor: Async function to process each page
            max_workers: Maximum number of parallel workers (calculated automatically if None)

        Returns:
            List of tuples (page_number, (page_info, entities))
        """
        # Calculate optimal worker count if not provided
        if max_workers is None:
            max_workers = cls.get_optimal_batch_size(len(pages))

        # Assign page numbers if not already present
        for i, page in enumerate(pages):
            if "page" not in page:
                page["page"] = i + 1

        # Process pages in parallel
        results = await cls.process_in_parallel(
            items=pages,
            processor=processor,
            max_workers=max_workers,
            # Page processing can take longer, especially for large documents
            timeout=600.0,  # 10 minutes overall timeout
            item_timeout=120.0  # 2 minutes per page timeout
        )

        # Convert to page_number -> result mapping for better usability
        page_results = []
        for idx, result in results:
            if result is not None:
                page_number = pages[idx].get("page", idx + 1)
                page_results.append((page_number, result))

        return page_results

    @classmethod
    async def _process_entity_async(
        cls, processor: Any, full_text: str, mapping: List[Tuple[Dict[str, Any], int, int]],
        entity_dict: Dict[str, Any], page_number: int
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Processes a single entity asynchronously.

        Args:
            processor: The entity processor object.
            full_text: The full text of the page.
            mapping: Text position mapping.
            entity_dict: A dictionary representing the entity.
            page_number: The page number the entity belongs to.

        Returns:
            Tuple of (processed_entities, page_redaction_info).
        """
        try:
            processed, info = await processor.process_entities_for_page(
                page_number, full_text, mapping, [entity_dict]
            )
            return processed, info
        except Exception as e:
            error_id = SecurityAwareErrorHandler.log_processing_error(
                e, "entity_parallel_processing", f"page_{page_number}"
            )
            log_error(f"[BATCH] Error processing entity: {str(e)} (error_id: {error_id})")
            return [], {"page": page_number, "sensitive": []}

    @classmethod
    async def process_entities_in_parallel(
        cls,
        processor: Any,
        full_text: str,
        mapping: List[Tuple[Dict[str, Any], int, int]],
        entity_dicts: List[Dict[str, Any]],
        page_number: int
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Process entities in parallel for a single page.

        Args:
            processor: Entity processor object with process_entities_for_page method
            full_text: Full text of the page
            mapping: Text position mapping
            entity_dicts: List of entity dictionaries
            page_number: Page number

        Returns:
            Tuple of (processed_entities, page_redaction_info)
        """
        if len(entity_dicts) <= 5:
            try:
                return await processor.process_entities_for_page(
                    page_number, full_text, mapping, entity_dicts
                )
            except Exception as e:
                log_error(f"[BATCH] Error processing entities for page {page_number}: {str(e)}")
                return [], {"page": page_number, "sensitive": []}

        # Process entities in parallel using the extracted method
        tasks = [cls._process_entity_async(processor, full_text, mapping, entity, page_number) for entity in entity_dicts]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        # Combine results
        all_processed, all_sensitive = [], []
        for processed_entities, page_info in results:
            all_processed.extend(processed_entities)
            all_sensitive.extend(page_info.get("sensitive", []))

        return all_processed, {"page": page_number, "sensitive": all_sensitive}


    @classmethod
    async def validate_batch_files_optimized(
            cls,
            files: List[UploadFile],
            allowed_types: Optional[Set[str]] = None,
            max_size_mb: int = 25,
            max_batch_size: int = 10
    ) -> AsyncGenerator[List[Tuple[UploadFile, str, bytes, str]], None]:
        """
        Validate and process batch files efficiently, minimizing memory usage.

        This method:
        - Divides files into batches to prevent memory overload.
        - Validates file type and size.
        - Stores large files in temporary storage while keeping small files in memory.

        Args:
            files: List of uploaded files to validate.
            allowed_types: Allowed MIME types (default includes PDFs, text files, and Word documents).
            max_size_mb: Maximum allowed file size in MB.
            max_batch_size: Maximum number of files processed in a batch.

        Yields:
            Batches of tuples (file, tmp_path or None, content, safe_filename).
        """
        if not files:
            return

        allowed_types = cls._set_allowed_types(allowed_types)
        max_size_bytes = max_size_mb * 1024 * 1024

        for batch_start in range(0, len(files), max_batch_size):
            batch_end = min(batch_start + max_batch_size, len(files))
            batch_files = files[batch_start:batch_end]
            log_info(f"[BATCH] Validating file batch {batch_start + 1}-{batch_end} of {len(files)}")

            valid_files = await cls._process_file_batch(batch_files, allowed_types, max_size_bytes)

            if valid_files:
                yield valid_files

            cls._force_garbage_collection()

    @classmethod
    def _set_allowed_types(cls, allowed_types: Optional[Set[str]]) -> Set[str]:
        """
        Define allowed file types if not provided.

        Args:
            allowed_types: Custom MIME types.

        Returns:
            A set of allowed MIME types.
        """
        return allowed_types or {
            "application/pdf",
            "text/plain",
            "text/csv",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        }

    @classmethod
    async def _process_file_batch(
            cls,
            batch_files: List[UploadFile],
            allowed_types: Set[str],
            max_size_bytes: int
    ) -> List[Tuple[UploadFile, str, bytes, str]]:
        """
        Validates and processes a batch of files.

        Args:
            batch_files: List of files in the current batch.
            allowed_types: Allowed MIME types.
            max_size_bytes: Maximum allowed file size in bytes.

        Returns:
            List of validated files with their metadata.
        """
        valid_files = []

        for file in batch_files:
            file_data = await cls._validate_and_process_file(file, allowed_types, max_size_bytes)
            if file_data:
                valid_files.append(file_data)

        return valid_files

    @classmethod
    async def _validate_and_process_file(
            cls,
            file: UploadFile,
            allowed_types: Set[str],
            max_size_bytes: int
    ) -> Optional[Tuple[UploadFile, str, bytes, str]]:
        """
        Validates a file's type and size, processes its content, and determines storage.

        Args:
            file: The file to validate.
            allowed_types: Allowed MIME types.
            max_size_bytes: Maximum allowed file size in bytes.

        Returns:
            Tuple (file, tmp_path or None, content, safe_filename) if valid, otherwise None.
        """
        try:
            content_type = file.content_type or "application/octet-stream"
            if not validate_mime_type(content_type, allowed_types):
                log_warning(f"[BATCH] Skipping unsupported file type: {file.filename} ({content_type})")
                return None

            content = await cls._read_file_content(file, max_size_bytes)
            if content is None:
                return None  # File was too large

            safe_filename = sanitize_filename(file.filename) if file.filename else None
            if not safe_filename:
                log_warning(f"[BATCH] Skipping file with missing filename: {file.filename}")
                return None

            tmp_path = await cls._store_large_file(content, safe_filename) if len(content) > 5 * 1024 * 1024 else None
            return file, tmp_path, content, safe_filename

        except Exception as e:
            cls._log_file_processing_error(file, e)
            return None

    @classmethod
    async def _read_file_content(cls, file: UploadFile, max_size_bytes: int) -> Optional[bytes]:
        """
        Reads file content while checking for size limits.

        Args:
            file: The uploaded file.
            max_size_bytes: Maximum allowed file size in bytes.

        Returns:
            The file content if valid, otherwise None.
        """
        await file.seek(0)
        content = await file.read()

        if len(content) > max_size_bytes:
            log_warning(
                f"[BATCH] File too large: {file.filename} ({len(content) / 1024 / 1024:.1f} MB > {max_size_bytes / 1024 / 1024:.1f} MB)")
            return None

        return content
    @classmethod
    async def _store_large_file(cls, content: bytes, safe_filename: str) -> str:
        """
        Stores large file content in a temporary secure file.

        Args:
            content: File content in bytes.
            safe_filename: Sanitized filename.

        Returns:
            The temporary file path.
        """
        return await SecureTempFileManager.create_secure_temp_file_async(
            content=content,
            prefix="batch_",
            suffix=os.path.splitext(safe_filename)[1]
        )


    @classmethod
    def _log_file_processing_error(cls, file: UploadFile, exception: Exception):
        """
        Logs errors encountered while processing a file.

        Args:
            file: The file that caused the error.
            exception: The exception raised.
        """
        error_id = SecurityAwareErrorHandler.log_processing_error(
            exception, "batch_file_validation", file.filename or "unnamed_file"
        )
        log_error(f"[BATCH] Error validating file {file.filename}: {str(exception)} (error_id: {error_id})")

    @classmethod
    def _force_garbage_collection(cls):
        """
        Forces garbage collection to free memory after processing each batch.
        """
        import gc
        gc.collect()

async def validate_batch_files_optimized(
    files: List[UploadFile],
    allowed_types: Optional[Set[str]] = None,
    max_size_mb: int = 25
) -> AsyncGenerator[List[Tuple[UploadFile, str, bytes, str]], None]:
    """
    Backward-compatible wrapper for BatchProcessingHelper.validate_batch_files_optimized.

    Args:
        files: List of uploaded files to validate
        allowed_types: Set of allowed MIME types
        max_size_mb: Maximum file size in MB

    Yields:
        Batches of tuples (file, tmp_path or None, content, safe_filename)
    """
    async for batch in BatchProcessingHelper.validate_batch_files_optimized(
        files, allowed_types, max_size_mb
    ):
        if batch:
            yield batch
        else:
            log_warning("[BATCH] Skipping empty batch - No valid files found")


def get_optimal_batch_size(file_count: int, total_bytes: int = 0) -> int:
    """
    Backward-compatible wrapper for BatchProcessingHelper.get_optimal_batch_size.

    Args:
        file_count: Number of files to process
        total_bytes: Total size of all files in bytes

    Returns:
        Optimal number of parallel workers
    """
    return BatchProcessingHelper.get_optimal_batch_size(file_count, total_bytes)