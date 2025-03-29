import asyncio
import logging
import os
import time
from typing import List, Dict, Any, Callable, TypeVar, Awaitable, Tuple, Optional
import psutil
from weakref import WeakKeyDictionary

from backend.app.configs.config_singleton import get_config
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.memory_management import memory_monitor
from backend.app.utils.synchronization_utils import AsyncTimeoutSemaphore, LockPriority, AsyncTimeoutLock

# Type variables for generic functions
T = TypeVar('T')
R = TypeVar('R')

# Configure logger for this module.
logger = logging.getLogger(__name__)

# Default timeouts (in seconds)
DEFAULT_BATCH_TIMEOUT = 600.0  # Overall timeout for processing a batch of items
DEFAULT_ITEM_TIMEOUT = 600.0  # Timeout for processing an individual item
DEFAULT_LOCK_TIMEOUT = 20.0  # Timeout for acquiring locks

# Global cache for locks keyed by the current event loop.
_loop_locks = WeakKeyDictionary()


def get_resource_lock() -> AsyncTimeoutLock:
    """
    Retrieve an AsyncTimeoutLock instance bound to the current event loop.

    This ensures that the lock is created lazily for the event loop in use,
    avoiding errors from cross-event loop usage.

    Returns:
        An AsyncTimeoutLock instance bound to the current event loop.
    """
    loop = asyncio.get_running_loop()  # Get the current event loop.
    if loop not in _loop_locks:
        # Create a new lock for this loop if not already present.
        _loop_locks[loop] = AsyncTimeoutLock("parallel_core_lock", priority=LockPriority.MEDIUM)
    return _loop_locks[loop]


class ParallelProcessingCore:
    """
    Core functionality for executing tasks in parallel with enhanced monitoring,
    adaptive resource allocation, and robust error handling.

    Features:
      - Dynamically determine the optimal number of workers.
      - Process items concurrently with individual and overall timeouts.
      - Track progress and log periodic updates.
      - Aggregate results and handle partial successes if timeouts occur.
      - Process pages and entities concurrently in batches.

    All locks are created on-demand and bound to the current event loop.
    """

    @classmethod
    def get_optimal_workers(
            cls,
            items_count: int,
            memory_per_item: Optional[int] = None,
            min_workers: int = 2,
            max_workers: int = 8
    ) -> int:
        """
        Calculate the optimal number of parallel workers based on system resources.

        Args:
            items_count: Total number of items to process.
            memory_per_item: (Optional) Estimated memory required per item in bytes.
            min_workers: Minimum number of workers to use.
            max_workers: Maximum number of workers to use.

        Returns:
            The calculated optimal number of workers.
        """
        cpu_count = os.cpu_count() or 4  # Get CPU cores; default to 4 if not available.
        available_memory = psutil.virtual_memory().available  # Available system memory.
        current_load = psutil.cpu_percent(interval=0.1) / 100.0  # CPU load as a fraction.
        current_memory_usage = memory_monitor.get_memory_usage() / 100.0  # Memory usage as a fraction.

        # Calculate workers based on CPU availability and load.
        cpu_based_workers = max(1, int(cpu_count * (1 - current_load * 0.5)))

        if memory_per_item is not None and memory_per_item > 0:
            # Calculate how many workers can run based on available memory.
            memory_based_workers = max(1, min(int(available_memory * 0.8 / memory_per_item), cpu_based_workers))
        else:
            # Without a memory requirement, reduce workers as memory usage increases.
            memory_factor = 1.0 - (current_memory_usage * 1.5)
            memory_factor = max(0.25, memory_factor)
            memory_based_workers = max(1, int(cpu_based_workers * memory_factor))

        # Choose the optimal number of workers within provided bounds.
        optimal_workers = min(memory_based_workers, items_count, max_workers)
        optimal_workers = max(optimal_workers, min_workers)

        log_info(
            f"Calculated optimal workers: {optimal_workers} (CPU: {cpu_count}, "
            f"Load: {current_load:.2f}, Memory: {current_memory_usage:.2f})"
        )
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
        Process a list of items concurrently with monitoring and error handling.

        This method sets up the required semaphores, calculates optimal worker count,
        creates tasks for each item, and gathers the results with an overall batch timeout.

        Args:
            items: A list of items to process.
            processor: An asynchronous function to process each item.
            max_workers: Maximum number of parallel workers (auto-calculated if None).
            batch_timeout: Overall timeout for processing the entire batch.
            item_timeout: Timeout for processing an individual item.
            operation_id: Optional unique identifier for the operation (used in logging).
            adaptive: Whether to adjust worker count dynamically based on load.
            progress_callback: Optional async callback for progress updates (completed, total, elapsed).

        Returns:
            A list of tuples (index, result) for each item, with None for failures.
        """
        try:
            # Validate inputs and set default timeouts/operation ID.
            operation_id, batch_timeout, item_timeout, start_time = cls._validate_and_prepare_input(
                items, batch_timeout, item_timeout, operation_id
            )

            # Determine the number of workers to use, using a resource lock on the current event loop.
            worker_count = await cls._acquire_worker_count(items, max_workers, adaptive)

            # Create a semaphore to limit concurrent task execution.
            semaphore = cls._create_semaphore(worker_count, operation_id)

            # Initialize progress tracking data.
            progress_data = cls._init_progress_data(start_time, len(items))

            # Create a mapping of item indices to asyncio tasks.
            tasks_map = cls._create_tasks_map(
                items, semaphore, processor, item_timeout, operation_id,
                progress_data, progress_callback
            )

            # Wait for all tasks to complete (or timeout) and collect results.
            results = await cls._gather_tasks_with_timeout(
                tasks_map, batch_timeout, operation_id, progress_data
            )

            # Log a final summary of processing.
            cls._log_final_completion(results, progress_data, start_time, operation_id)
            return results

        except Exception as e:
            log_error(f"Unexpected error in process_in_parallel: {e} [operation_id={operation_id}]")
            raise

    @staticmethod
    def _validate_and_prepare_input(
            items: List[T],
            batch_timeout: Optional[float],
            item_timeout: Optional[float],
            operation_id: Optional[str]
    ) -> Tuple[str, float, float, float]:
        """
        Validate inputs and set defaults for timeouts and the operation ID.

        Args:
            items: List of items to process.
            batch_timeout: Overall batch processing timeout.
            item_timeout: Timeout for processing an individual item.
            operation_id: Optional operation identifier.

        Returns:
            A tuple (operation_id, batch_timeout, item_timeout, start_time).
        """
        if not items:
            return operation_id or "parallel_no_items", 0.0, 0.0, time.time()
        if operation_id is None:
            operation_id = f"parallel_{time.time():.0f}"
        batch_timeout = batch_timeout or DEFAULT_BATCH_TIMEOUT
        item_timeout = item_timeout or DEFAULT_ITEM_TIMEOUT
        start_time = time.time()  # Capture the start time for progress tracking.
        return operation_id, batch_timeout, item_timeout, start_time

    @classmethod
    async def _acquire_worker_count(
            cls,
            items: List[T],
            max_workers: Optional[int],
            adaptive: bool
    ) -> int:
        """
        Determine the optimal worker count using a lock to prevent race conditions.

        This method uses a resource lock (created per event loop) to ensure that the worker
        count is computed consistently across concurrent invocations.

        Args:
            items: List of items to process.
            max_workers: Maximum number of workers allowed.
            adaptive: Whether to adjust the worker count based on system load.

        Returns:
            The number of workers to use.
        """
        if max_workers is not None and not adaptive:
            return min(max_workers, len(items))
        resource_lock = get_resource_lock()  # Get lock bound to the current event loop.
        try:
            async with resource_lock.acquire_timeout(DEFAULT_LOCK_TIMEOUT):
                worker_count = cls.get_optimal_workers(len(items))
                if max_workers is not None:
                    worker_count = min(worker_count, max_workers)
        except TimeoutError:
            worker_count = max(2, min(4, len(items)))
            log_warning(f"Timeout acquiring resource lock, using {worker_count} workers")
        return worker_count

    @staticmethod
    def _create_semaphore(worker_count: int, operation_id: str) -> AsyncTimeoutSemaphore:
        """
        Create a semaphore limiting concurrency to the specified worker count.

        Args:
            worker_count: The number of concurrent tasks allowed.
            operation_id: Identifier for the current operation (for logging).

        Returns:
            An AsyncTimeoutSemaphore instance.
        """
        log_info(f"Creating semaphore with {worker_count} workers [operation_id={operation_id}]")
        return AsyncTimeoutSemaphore(
            name=f"parallel_semaphore_{operation_id}",
            value=worker_count,
            priority=LockPriority.MEDIUM
        )

    @staticmethod
    def _init_progress_data(start_time: float, total_items: int) -> Dict[str, Any]:
        """
        Initialize and return a dictionary to track progress of the batch.

        Args:
            start_time: Timestamp when processing started.
            total_items: Total number of items to process.

        Returns:
            A dictionary with keys such as 'completed', 'failed', etc.
        """
        return {
            "completed": 0,
            "failed": 0,
            "last_progress_log": start_time,  # Last time a progress update was logged.
            "total_items": total_items,
            "start_time": start_time,
            "last_index": None  # Last processed item's index.
        }

    @classmethod
    def _create_tasks_map(
            cls,
            items: List[T],
            semaphore: AsyncTimeoutSemaphore,
            processor: Callable[[T], Awaitable[R]],
            item_timeout: float,
            operation_id: str,
            progress_data: Dict[str, Any],
            progress_callback: Optional[Callable[[int, int, float], Awaitable[None]]]
    ) -> Dict[int, asyncio.Task]:
        """
        Create a mapping from item indices to their processing asyncio tasks.

        Args:
            items: List of items to process.
            semaphore: Semaphore controlling concurrency.
            processor: Asynchronous function to process each item.
            item_timeout: Timeout for processing an individual item.
            operation_id: Operation identifier.
            progress_data: Dictionary for tracking progress.
            progress_callback: Optional callback for progress updates.

        Returns:
            A dictionary mapping each item's index to its asyncio Task.
        """
        tasks_map = {}
        for i, item in enumerate(items):
            # Create a task for each item.
            task = asyncio.create_task(
                cls._process_with_semaphore(
                    i, item, semaphore, processor, item_timeout,
                    operation_id, progress_data, progress_callback
                ),
                name=str(i)
            )
            tasks_map[i] = task
        return tasks_map

    @classmethod
    async def _process_with_semaphore(
            cls,
            index: int,
            item: T,
            semaphore: AsyncTimeoutSemaphore,
            processor: Callable[[T], Awaitable[R]],
            item_timeout: float,
            operation_id: str,
            progress_data: Dict[str, Any],
            progress_callback: Optional[Callable[[int, int, float], Awaitable[None]]]
    ) -> Tuple[int, Optional[R]]:
        """
        Process a single item under semaphore control and within an item timeout.

        Args:
            index: Index of the item.
            item: The item to process.
            semaphore: Semaphore controlling concurrent processing.
            processor: Asynchronous function to process the item.
            item_timeout: Timeout for this item.
            operation_id: Operation identifier.
            progress_data: Dictionary tracking progress.
            progress_callback: Optional callback for progress updates.

        Returns:
            A tuple (index, result) where result is the processed output or None on failure.
        """
        async with semaphore.acquire_timeout(timeout=DEFAULT_LOCK_TIMEOUT):
            try:
                # Await processing of the item with the specified timeout.
                result = await asyncio.wait_for(processor(item), timeout=item_timeout)
                # Update progress information.
                cls._update_progress(index, operation_id, progress_data, progress_callback)
                return index, result
            except asyncio.TimeoutError:
                progress_data["failed"] += 1
                log_warning(f"Item {index} processing timed out after {item_timeout}s [operation_id={operation_id}]")
                return index, None
            except Exception as e:
                progress_data["failed"] += 1
                error_id = SecurityAwareErrorHandler.log_processing_error(e, "parallel_processing", f"item_{index}")
                log_error(f"Error processing item {index}: {str(e)} [error_id={error_id}, operation_id={operation_id}]")
                return index, None

    @classmethod
    def _update_progress(
            cls,
            index: int,
            operation_id: str,
            progress_data: Dict[str, Any],
            progress_callback: Optional[Callable[[int, int, float], Awaitable[None]]]
    ) -> None:
        """
        Update progress metrics and log a progress update if needed.

        Args:
            index: Index of the last processed item.
            operation_id: Operation identifier.
            progress_data: Dictionary with progress information.
            progress_callback: Optional asynchronous callback to report progress.
        """
        progress_data["completed"] += 1  # Increment the count of completed items.
        progress_data["last_index"] = index  # Store the index of the last processed item.
        current_time = time.time()
        elapsed = current_time - progress_data["start_time"]
        total_items = progress_data["total_items"]
        last_log_time = progress_data["last_progress_log"]

        # Log progress every 5 seconds or when processing is complete.
        if (current_time - last_log_time > 5.0) or (progress_data["completed"] == total_items):
            progress = progress_data["completed"] / total_items
            estimated_total = elapsed / max(progress, 0.01)
            remaining = estimated_total - elapsed
            log_info(
                f"Progress: {progress_data['completed']}/{total_items} "
                f"(Last processed index: {index}, {progress * 100:.1f}%), "
                f"Elapsed: {elapsed:.1f}s, Remaining: {remaining:.1f}s [operation_id={operation_id}]"
            )
            progress_data["last_progress_log"] = current_time
            # Trigger the progress callback if provided.
            if progress_callback:
                asyncio.create_task(progress_callback(progress_data["completed"], total_items, elapsed))

    @classmethod
    async def _gather_tasks_with_timeout(
            cls,
            tasks_map: Dict[int, asyncio.Task],
            batch_timeout: float,
            operation_id: str,
            progress_data: Dict[str, Any]
    ) -> List[Tuple[int, Optional[R]]]:
        """
        Await completion of all tasks with an overall batch timeout. If the timeout
        is reached, gather results only from completed tasks.

        Args:
            tasks_map: Dictionary mapping item indices to asyncio Tasks.
            batch_timeout: Overall timeout for the batch.
            operation_id: Operation identifier.
            progress_data: Dictionary tracking progress.

        Returns:
            A sorted list of (index, result) tuples.
        """
        try:
            gathered_results = await asyncio.wait_for(
                asyncio.gather(*tasks_map.values()),
                timeout=batch_timeout
            )
            sorted_results = sorted(gathered_results, key=lambda x: x[0])
            return sorted_results
        except asyncio.TimeoutError:
            log_error(
                f"Batch processing timed out after {batch_timeout}s with progress: "
                f"{progress_data['completed']}/{progress_data['total_items']} completed "
                f"[operation_id={operation_id}]"
            )
            # If timeout occurs, return partial results.
            return cls._collect_partial_results(tasks_map)

    @staticmethod
    def _collect_partial_results(tasks_map: Dict[int, asyncio.Task]) -> List[Tuple[int, Optional[R]]]:
        """
        Collect results from tasks that have completed. For tasks not done or that failed,
        return None for the result.

        Args:
            tasks_map: Dictionary mapping item indices to asyncio Tasks.

        Returns:
            A list of (index, result) tuples, sorted by index.
        """
        partial_results = {}
        for i, task in tasks_map.items():
            if task.done():
                if task.exception() is not None:
                    partial_results[i] = (i, None)
                else:
                    partial_results[i] = task.result()
            else:
                partial_results[i] = (i, None)
        return [partial_results[i] for i in sorted(partial_results.keys())]

    @staticmethod
    def _log_final_completion(
            results: List[Tuple[int, Optional[R]]],
            progress_data: Dict[str, Any],
            start_time: float,
            operation_id: str
    ) -> None:
        """
        Log a final summary of the parallel processing operation, including total time,
        number of successes, and number of failures.

        Args:
            results: List of (index, result) tuples from task processing.
            progress_data: Dictionary tracking progress.
            start_time: Timestamp when processing started.
            operation_id: Operation identifier.
        """
        total_time = time.time() - start_time
        total_items = progress_data["total_items"]
        completed = progress_data["completed"]
        failed = progress_data["failed"]
        success_count = sum(1 for _, result in results if result is not None)
        success_rate = (success_count / total_items * 100) if total_items else 100
        log_info(
            f"Completed processing {total_items} items in {total_time:.2f}s: "
            f"{success_count} succeeded ({success_rate:.1f}%), {failed} failed [operation_id={operation_id}]"
        )
        log_sensitive_operation(
            "Parallel Processing",
            total_items,
            total_time,
            completed=completed,
            failed=failed,
            operation_id=operation_id
        )

    @staticmethod
    async def process_pages_in_parallel(
            pages: List[Dict[str, Any]],
            process_func: Callable[[Dict[str, Any]], Awaitable[Tuple[Dict[str, Any], List[Dict[str, Any]]]]],
            max_workers: Optional[int] = None
    ) -> List[Tuple[int, Tuple[Dict[str, Any], List[Dict[str, Any]]]]]:
        """
        Process multiple document pages concurrently using a provided asynchronous function.

        Args:
            pages: List of page data dictionaries.
            process_func: Async function that processes a single page.
            max_workers: Maximum number of pages to process concurrently (auto-calculated if None).

        Returns:
            A list of tuples, each containing the page number and the result from process_func.
        """
        if not pages:
            return []
        if max_workers is None:
            max_workers = ParallelProcessingCore.get_optimal_workers(len(pages))
        else:
            max_workers = min(max_workers, len(pages))
        semaphore = asyncio.Semaphore(max_workers)

        async def process_with_semaphore(page: Dict[str, Any]) -> Tuple[
            int, Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
            page_number = page.get("page", 0)
            async with semaphore:
                try:
                    page_result = await process_func(page)
                    return page_number, page_result
                except Exception as e:
                    log_warning(f"[PARALLEL] Error processing page {page_number}: {e}")
                    return page_number, ({"page": page_number, "sensitive": []}, [])

        tasks = [asyncio.create_task(process_with_semaphore(page)) for page in pages]
        results = await asyncio.gather(*tasks)
        log_info(f"[PARALLEL] Processed {len(pages)} pages with {max_workers} workers")
        return results

    @staticmethod
    async def process_entities_in_parallel(
            detector,
            full_text: str,
            mapping: List[Tuple[Dict[str, Any], int, int]],
            entities: List[Any],
            page_number: int,
            batch_size: Optional[int] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Process entities concurrently for a single page by dividing them into batches.

        Args:
            detector: An instance with an async method process_entities_for_page.
            full_text: Full text content of the page.
            mapping: List of tuples mapping text positions.
            entities: List of entities to be processed.
            page_number: Current page number.
            batch_size: Optional batch size; if None, loaded from configuration.

        Returns:
            A tuple containing:
              - A list of processed entities.
              - A dictionary with redaction information.
        """
        if not entities:
            return [], {"page": page_number, "sensitive": []}
        if batch_size is None:
            batch_size = get_config("entity_batch_size", 10)
        log_info(
            f"[PARALLEL] Starting entity processing for page {page_number} with batch size {batch_size} "
            f"and {len(entities)} total entities"
        )
        # Split the entities into smaller batches.
        entity_batches = [entities[i:i + batch_size] for i in range(0, len(entities), batch_size)]
        batch_results = []
        batch_times = []
        for i, batch in enumerate(entity_batches):
            start_time = time.perf_counter()  # Measure batch processing time.
            try:
                result = await detector.process_entities_for_page(page_number, full_text, mapping, batch)
            except Exception as e:
                log_error(f"[PARALLEL] Error processing batch {i + 1}/{len(entity_batches)} on page {page_number}: {e}")
                result = ([], {"page": page_number, "sensitive": []})
            end_time = time.perf_counter()
            elapsed = end_time - start_time
            batch_results.append(result)
            batch_times.append(elapsed)
            log_info(
                f"[PARALLEL] Processed batch {i + 1}/{len(entity_batches)} with {len(batch)} entities in {elapsed:.2f}s")
        total_time = sum(batch_times)
        log_sensitive_operation("Entity Batch Processing", len(entities), total_time, page=page_number)
        processed_entities = []
        page_redaction_info = {"page": page_number, "sensitive": []}
        for processed, redaction in batch_results:
            processed_entities.extend(processed)
            page_redaction_info["sensitive"].extend(redaction.get("sensitive", []))
        log_info(f"[PARALLEL] Completed entity processing for page {page_number} in {total_time:.2f}s")
        return processed_entities, page_redaction_info
