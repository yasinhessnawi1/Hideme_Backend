"""
Unified parallel processing core with enhanced async support, monitoring, and error handling.

This module provides the core functionality for parallel task execution with comprehensive
monitoring, adaptive resource allocation, and standardized error handling. It serves as
the foundation for all batch processing operations throughout the application.
"""
import asyncio
import os
import time
import psutil
import logging
from typing import List, Dict, Any, Callable, TypeVar, Awaitable, Tuple, Optional, Union, Coroutine

from backend.app.utils.synchronization_utils import AsyncTimeoutSemaphore, LockPriority, AsyncTimeoutLock
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.memory_management import memory_monitor
from backend.app.utils.logging.secure_logging import log_sensitive_operation

# Type variables for generic functions
T = TypeVar('T')
R = TypeVar('R')

# Configure logger
logger = logging.getLogger(__name__)

# Default timeouts
DEFAULT_BATCH_TIMEOUT = 300.0  # 5 minutes for batch operations
DEFAULT_ITEM_TIMEOUT = 60.0    # 1 minute per item
DEFAULT_LOCK_TIMEOUT = 10.0    # 10 seconds for lock acquisition


class ParallelProcessingCore:
    """
    Core functionality for parallel task execution with enhanced monitoring and error handling.

    This class provides the foundation for all parallel processing in the application, with
    features including:

    - Dynamic worker allocation based on system resources
    - Comprehensive monitoring and logging
    - Standardized error handling and reporting
    - Timeout management at both batch and item levels
    - Resource-aware execution to prevent system overload
    """

    # Class-level lock for synchronizing resource allocation
    _resource_lock = AsyncTimeoutLock("parallel_core_lock", priority=LockPriority.MEDIUM)

    @classmethod
    def get_optimal_workers(
        cls,
        items_count: int,
        memory_per_item: Optional[int] = None,
        min_workers: int = 2,
        max_workers: int = 8
    ) -> int:
        """
        Calculate the optimal number of worker threads based on system resources.

        This method takes into account:
        - CPU core count
        - Available memory
        - Current system load
        - Memory requirements per item (if provided)

        Args:
            items_count: Number of items to process
            memory_per_item: Estimated memory required per item in bytes (optional)
            min_workers: Minimum number of workers to use
            max_workers: Maximum number of workers to use

        Returns:
            Optimal number of worker threads
        """
        # Get system information
        cpu_count = os.cpu_count() or 4
        available_memory = psutil.virtual_memory().available
        current_load = psutil.cpu_percent(interval=0.1) / 100.0
        current_memory_usage = memory_monitor.get_memory_usage() / 100.0

        # Base worker count on CPU cores and load
        cpu_based_workers = max(1, int(cpu_count * (1 - current_load * 0.5)))

        # If memory requirements are specified, factor them in
        if memory_per_item is not None and memory_per_item > 0:
            # Calculate how many workers we can support based on memory
            memory_based_workers = max(1, min(
                int(available_memory * 0.8 / memory_per_item),
                cpu_based_workers
            ))
        else:
            # Without specific memory requirements, use a heuristic based on current memory usage
            memory_factor = 1.0 - (current_memory_usage * 1.5)  # Reduce workers as memory usage increases
            memory_factor = max(0.25, memory_factor)  # Ensure at least 25% of calculated workers
            memory_based_workers = max(1, int(cpu_based_workers * memory_factor))

        # Final worker count is bounded by items_count, min_workers, and max_workers
        optimal_workers = min(memory_based_workers, items_count, max_workers)
        optimal_workers = max(optimal_workers, min_workers)

        log_info(f"Calculated optimal workers: {optimal_workers} (CPU: {cpu_count}, "
                f"Load: {current_load:.2f}, Memory: {current_memory_usage:.2f})")

        return optimal_workers

    @classmethod
    async def process_in_parallel(
        cls,
        items: List[T],
        processor: Callable[[T], Awaitable[R]],
        max_workers: Optional[int] = None,
        batch_timeout: Optional[float] = None,
        item_timeout: Optional[float] = None,
        operation_id: Optional[str] = None,
        adaptive: bool = True,
        progress_callback: Optional[Callable[[int, int, float], Awaitable[None]]] = None
    ) -> List[Tuple[int, Optional[R]]]:
        """
        Process items in parallel with comprehensive monitoring and error handling.

        This method provides:
        - Dynamic worker allocation (if adaptive=True)
        - Per-item timeout protection
        - Overall batch timeout protection
        - Detailed progress logging
        - Comprehensive error handling
        - Optional progress callback for UI updates

        Args:
            items: List of items to process
            processor: Async function to process each item
            max_workers: Maximum number of parallel workers (auto-calculated if None)
            batch_timeout: Timeout for entire batch processing (default: 5 minutes)
            item_timeout: Timeout for individual item processing (default: 1 minute)
            operation_id: Unique identifier for the operation (for logging)
            adaptive: Whether to dynamically adjust worker count based on system load
            progress_callback: Optional async function called with (completed, total, elapsed_time)

        Returns:
            List of tuples (index, result) for each item, where result is None if processing failed
        """
        if not items:
            return []

        # Generate operation ID if not provided
        if operation_id is None:
            operation_id = f"parallel_{time.time():.0f}"

        # Set default timeouts
        batch_timeout = batch_timeout or DEFAULT_BATCH_TIMEOUT
        item_timeout = item_timeout or DEFAULT_ITEM_TIMEOUT

        # Calculate optimal worker count if not specified or if adaptive
        start_time = time.time()
        worker_count = max_workers

        if worker_count is None or adaptive:
            try:
                async with cls._resource_lock.acquire_timeout(DEFAULT_LOCK_TIMEOUT):
                    worker_count = cls.get_optimal_workers(len(items))
                    if max_workers is not None:
                        worker_count = min(worker_count, max_workers)
            except TimeoutError:
                # If we can't acquire the lock, use a conservative default
                worker_count = max(2, min(4, len(items)))
                log_warning(f"Timeout acquiring resource lock, using {worker_count} workers")

        # Create semaphore for limiting concurrent tasks
        semaphore = AsyncTimeoutSemaphore(
            name=f"parallel_semaphore_{operation_id}",
            value=worker_count,
            priority=LockPriority.MEDIUM
        )

        # Statistics for logging
        completed = 0
        failed = 0
        last_progress_log = start_time

        log_info(f"Starting parallel processing of {len(items)} items with {worker_count} workers [operation_id={operation_id}]")

        async def process_with_semaphore(index: int, item: T) -> Tuple[int, Optional[R]]:
            """Process a single item with semaphore, timeout, and error handling."""
            nonlocal completed, failed

            async with semaphore.acquire_timeout(timeout=DEFAULT_LOCK_TIMEOUT):
                try:
                    # Process with item timeout
                    result = await asyncio.wait_for(processor(item), timeout=item_timeout)

                    # Update statistics
                    completed += 1

                    # Log progress at reasonable intervals
                    nonlocal last_progress_log
                    current_time = time.time()
                    if current_time - last_progress_log > 5.0:  # Log every 5 seconds
                        elapsed = current_time - start_time
                        progress = completed / len(items)
                        estimated_total = elapsed / max(progress, 0.01)
                        remaining = estimated_total - elapsed

                        log_info(f"Progress: {completed}/{len(items)} ({progress*100:.1f}%), "
                                f"Elapsed: {elapsed:.1f}s, Remaining: {remaining:.1f}s "
                                f"[operation_id={operation_id}]")

                        last_progress_log = current_time

                        # Call progress callback if provided
                        if progress_callback:
                            await progress_callback(completed, len(items), elapsed)

                    return index, result

                except asyncio.TimeoutError:
                    failed += 1
                    log_warning(f"Item {index} processing timed out after {item_timeout}s [operation_id={operation_id}]")
                    return index, None

                except Exception as e:
                    failed += 1
                    error_id = SecurityAwareErrorHandler.log_processing_error(
                        e, "parallel_processing", f"item_{index}"
                    )
                    log_error(f"Error processing item {index}: {str(e)} [error_id={error_id}, operation_id={operation_id}]")
                    return index, None

        # Create and gather tasks
        tasks = [process_with_semaphore(i, item) for i, item in enumerate(items)]

        try:
            # Apply overall batch timeout
            results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=batch_timeout)

            # Log completion
            total_time = time.time() - start_time
            success_rate = (completed / len(items)) * 100 if items else 100

            log_info(f"Completed processing {len(items)} items in {total_time:.2f}s: "
                    f"{completed} completed ({success_rate:.1f}%), {failed} failed "
                    f"[operation_id={operation_id}]")

            # Log as sensitive operation for audit purposes
            log_sensitive_operation(
                "Parallel Processing",
                len(items),
                total_time,
                completed=completed,
                failed=failed,
                operation_id=operation_id
            )

            return results

        except asyncio.TimeoutError:
            log_error(f"Batch processing timed out after {batch_timeout}s [operation_id={operation_id}]")

            # Return any completed results and None for the rest
            # This provides partial results even in timeout scenarios
            partial_results = []
            completed_indices = set(result[0] for result in tasks if result.done() and not result.exception())

            for i in range(len(items)):
                if i in completed_indices:
                    # Find the completed task with this index
                    for task in tasks:
                        if task.done() and not task.exception() and task.result()[0] == i:
                            partial_results.append(task.result())
                            break
                else:
                    partial_results.append((i, None))

            return partial_results


class BatchProcessor:
    """
    High-level batch processing utilities built on the ParallelProcessingCore.

    This class provides specialized batch processing methods for common operations,
    integrating with the document processing functionality to ensure consistent
    processing across the application.
    """

    @staticmethod
    async def adaptive_batch_size(
        total_items: int,
        memory_per_item: Optional[int] = None
    ) -> int:
        """
        Calculate the optimal batch size adaptively based on current system resources.

        Args:
            total_items: Total number of items to process
            memory_per_item: Estimated memory required per item in bytes (optional)

        Returns:
            Optimal batch size
        """
        return await asyncio.to_thread(
            ParallelProcessingCore.get_optimal_workers,
            total_items,
            memory_per_item
        )

    @staticmethod
    async def split_into_batches(
        items: List[T],
        batch_size: Optional[int] = None,
        memory_per_item: Optional[int] = None
    ) -> List[List[T]]:
        """
        Split items into optimally sized batches based on system resources.

        Args:
            items: List of items to process
            batch_size: Size of each batch (calculated automatically if None)
            memory_per_item: Estimated memory required per item in bytes (optional)

        Returns:
            List of batches, each containing a subset of items
        """
        if not items:
            return []

        # Calculate optimal batch size if not provided
        if batch_size is None:
            batch_size = await BatchProcessor.adaptive_batch_size(
                len(items),
                memory_per_item
            )

        # Split items into batches
        return [items[i:i+batch_size] for i in range(0, len(items), batch_size)]

    @staticmethod
    async def process_with_progress(
        items: List[T],
        processor: Callable[[T], Awaitable[R]],
        max_workers: Optional[int] = None,
        operation_id: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, float], Awaitable[None]]] = None
    ) -> List[Tuple[int, Optional[R]]]:
        """
        Process items in parallel with progress tracking.

        This is a convenience wrapper around ParallelProcessingCore.process_in_parallel
        with a focus on progress reporting.

        Args:
            items: List of items to process
            processor: Async function to process each item
            max_workers: Maximum number of parallel workers (auto-calculated if None)
            operation_id: Unique identifier for the operation (for logging)
            progress_callback: Optional async function called with (completed, total, elapsed_time)

        Returns:
            List of tuples (index, result) for each item
        """
        return await ParallelProcessingCore.process_in_parallel(
            items=items,
            processor=processor,
            max_workers=max_workers,
            operation_id=operation_id,
            progress_callback=progress_callback
        )