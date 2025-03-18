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
from typing import List, Dict, Any, Callable, TypeVar, Coroutine, Tuple, Optional, Iterable, AsyncGenerator, Set

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
        # Get system information
        try:
            cpu_count = os.cpu_count() or 4
            available_memory = psutil.virtual_memory().available
            current_memory_percent = psutil.virtual_memory().percent
        except Exception:
            # Fallback values if psutil fails
            cpu_count = 4
            available_memory = 4 * 1024 * 1024 * 1024  # Assume 4GB
            current_memory_percent = 50

        # Base calculations on CPU cores, but adjust based on memory pressure
        cpu_based_workers = max(1, min(cpu_count - 1, file_count, cls.MAX_PARALLELISM))

        # Calculate memory constraints
        if total_bytes > 0:
            # Estimate memory needed per file
            avg_bytes_per_file = total_bytes / file_count
            estimated_memory_per_worker = avg_bytes_per_file * 5  # Assume 5x file size for processing
            memory_based_workers = max(1, int(available_memory / estimated_memory_per_worker))
        else:
            # Use a more conservative approach when file sizes are unknown
            memory_based_workers = max(1, int(available_memory / cls.MIN_MEMORY_PER_WORKER))

        # Further reduce workers based on current memory pressure
        if current_memory_percent > cls.MAX_MEMORY_PERCENTAGE:
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
                f"Memory: {available_memory/1024/1024:.1f}MB, Files: {file_count}, "
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
        Process a list of items in parallel with enhanced error handling and resource management.

        Args:
            items: List of items to process
            processor: Async function to process each item
            max_workers: Maximum number of parallel workers (calculated automatically if None)
            timeout: Overall timeout for the entire batch in seconds
            item_timeout: Timeout for individual item processing in seconds

        Returns:
            List of tuples (index, result) where index is the original item index
        """
        if not items:
            return []

        # Calculate optimal worker count if not provided
        if max_workers is None:
            max_workers = cls.get_optimal_batch_size(len(items))

        # Set timeouts
        batch_timeout = timeout or cls.DEFAULT_TIMEOUT
        single_item_timeout = item_timeout or (batch_timeout / 2)

        # Initialize the global semaphore with the correct worker count
        semaphore = await cls._init_global_semaphore(max_workers)
        operation_id = str(uuid.uuid4())[:8]
        log_info(f"[BATCH] Starting parallel processing of {len(items)} items with {max_workers} workers (operation: {operation_id})")

        # Track task statistics
        start_time = time.time()
        completed = 0
        failed = 0
        total = len(items)

        # Create async task processor with timeout handling
        async def process_item(index: int, item: T) -> Tuple[int, U]:
            nonlocal completed, failed

            # Acquire semaphore with timeout to limit concurrent tasks
            try:
                async with semaphore.acquire_timeout(timeout=30.0):  # 30s timeout for semaphore acquisition
                    item_start = time.time()
                    try:
                        # Process item with timeout
                        result = await asyncio.wait_for(processor(item), timeout=single_item_timeout)
                        item_duration = time.time() - item_start

                        # Track completion
                        completed += 1

                        # Log progress periodically
                        if completed % 10 == 0 or completed == total:
                            elapsed = time.time() - start_time
                            remaining = (elapsed / completed) * (total - completed) if completed > 0 else 0
                            mem_stats = memory_monitor.get_memory_stats()
                            log_info(f"[BATCH] Progress: {completed}/{total} completed, {failed} failed, "
                                    f"~{remaining:.1f}s remaining, memory: {mem_stats['current_usage']:.1f}% "
                                    f"(operation: {operation_id})")

                        return index, result
                    except asyncio.TimeoutError:
                        failed += 1
                        log_warning(f"[BATCH] Item {index} processing timed out after {single_item_timeout}s (operation: {operation_id})")
                        return index, None
                    except Exception as e:
                        failed += 1
                        error_id = SecurityAwareErrorHandler.log_processing_error(
                            e, "batch_item_processing", f"item_{index}"
                        )
                        log_error(f"[BATCH] Error processing item {index}: {str(e)} (error_id: {error_id}, operation: {operation_id})")
                        return index, None
            except TimeoutError:
                failed += 1
                log_error(f"[BATCH] Failed to acquire semaphore for item {index} - system may be overloaded (operation: {operation_id})")
                return index, None
            except Exception as e:
                failed += 1
                error_id = SecurityAwareErrorHandler.log_processing_error(
                    e, "batch_item_semaphore", f"item_{index}"
                )
                log_error(f"[BATCH] Unexpected error for item {index}: {str(e)} (error_id: {error_id}, operation: {operation_id})")
                return index, None

        # Create all tasks but don't execute them yet
        tasks = [process_item(i, item) for i, item in enumerate(items)]

        # Execute all tasks with overall timeout
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=False),
                timeout=batch_timeout
            )

            # Log completion
            duration = time.time() - start_time
            log_info(f"[BATCH] Completed processing {len(items)} items in {duration:.2f}s: "
                    f"{completed} completed, {failed} failed (operation: {operation_id})")

            return results
        except asyncio.TimeoutError:
            # Handle overall timeout gracefully
            log_error(f"[BATCH] Overall batch processing timed out after {batch_timeout}s (operation: {operation_id})")
            # Return whatever results we have
            return []

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
        # For small entity counts, process directly
        if len(entity_dicts) <= 5:
            return await processor.process_entities_for_page(
                page_number, full_text, mapping, entity_dicts
            )

        # For larger entity counts, use parallel processing
        max_workers = min(10, len(entity_dicts))

        # Simplified entity processor for parallelization
        async def process_entity(entity_dict):
            try:
                # This simplified method only processes a single entity
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

        # Process entities in parallel
        tasks = [process_entity(entity) for entity in entity_dicts]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        # Combine results
        all_processed = []
        all_sensitive = []

        for processed_entities, page_info in results:
            all_processed.extend(processed_entities)
            all_sensitive.extend(page_info.get("sensitive", []))

        # Create combined page redaction info
        page_redaction_info = {
            "page": page_number,
            "sensitive": all_sensitive
        }

        return all_processed, page_redaction_info

    @classmethod
    async def validate_batch_files_optimized(
        cls,
        files: List[UploadFile],
        allowed_types: Optional[Set[str]] = None,
        max_size_mb: int = 25,
        max_batch_size: int = 10
    ) -> AsyncGenerator[List[Tuple[UploadFile, str, bytes, str]], None]:
        """
        Validate and process batch files with optimized resource management.

        This generator validates files in batches to prevent memory pressure,
        creates temporary files for large content, and yields batches of validated files.

        Args:
            files: List of uploaded files to validate
            allowed_types: Set of allowed MIME types
            max_size_mb: Maximum file size in MB
            max_batch_size: Maximum number of files to process in each batch

        Yields:
            Batches of tuples (file, tmp_path or None, content, safe_filename)
        """
        if not files:
            return

        # Set default allowed types
        if allowed_types is None:
            allowed_types = {
                "application/pdf",
                "text/plain",
                "text/csv",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            }

        max_size_bytes = max_size_mb * 1024 * 1024

        # Process files in batches for memory efficiency
        for batch_start in range(0, len(files), max_batch_size):
            batch_end = min(batch_start + max_batch_size, len(files))
            current_batch = files[batch_start:batch_end]
            valid_files = []

            log_info(f"[BATCH] Validating file batch {batch_start+1}-{batch_end} of {len(files)}")

            for file in current_batch:
                try:
                    # Validate content type
                    content_type = file.content_type or "application/octet-stream"
                    if not validate_mime_type(content_type, allowed_types):
                        log_warning(f"[BATCH] Skipping file with unsupported type: {file.filename} ({content_type})")
                        continue

                    # Check file size and determine processing approach
                    await file.seek(0)
                    content = await file.read()

                    if len(content) > max_size_bytes:
                        log_warning(f"[BATCH] File too large: {file.filename} ({len(content)/1024/1024:.1f} MB > {max_size_mb} MB)")
                        continue

                    # Get sanitized filename
                    safe_filename = sanitize_filename(file.filename or "unnamed_file")

                    # For large files, use temporary file storage
                    tmp_path = None
                    if len(content) > 5 * 1024 * 1024:  # 5MB threshold
                        # Create a temporary file
                        tmp_path = await SecureTempFileManager.create_secure_temp_file_async(
                            content=content,
                            prefix="batch_",
                            suffix=os.path.splitext(safe_filename)[1]
                        )
                        valid_files.append((file, tmp_path, content, safe_filename))
                    else:
                        # Keep small files in memory
                        valid_files.append((file, None, content, safe_filename))

                except Exception as e:
                    error_id = SecurityAwareErrorHandler.log_processing_error(
                        e, "batch_file_validation", file.filename or "unnamed_file"
                    )
                    log_error(f"[BATCH] Error validating file {file.filename}: {str(e)} (error_id: {error_id})")

            if valid_files:
                yield valid_files

            # Force garbage collection after each batch
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
        yield batch


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