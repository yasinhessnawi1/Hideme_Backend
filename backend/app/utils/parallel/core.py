"""
This module provides a robust implementation of a parallel processing core designed to execute tasks concurrently while
dynamically adjusting worker counts according to system resources and load. The ParallelProcessingCore class handles
the processing of individual items, pages, and entities with adaptive timeouts, detailed progress tracking, and
comprehensive error handling. It leverages system resource data (CPU, memory) to compute the optimal number of parallel
workers while ensuring safe asynchronous execution through semaphores and resource locks.
"""

import asyncio
import logging
import os
import time
from typing import List, Dict, Any, Callable, TypeVar, Awaitable, Tuple, Optional
import psutil
from weakref import WeakKeyDictionary

from backend.app.configs.config_singleton import get_config
from backend.app.utils.constant.constant import (
    DEFAULT_BATCH_TIMEOUT,
    DEFAULT_ITEM_TIMEOUT,
    DEFAULT_LOCK_TIMEOUT,
)
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.system_utils.memory_management import memory_monitor
from backend.app.utils.system_utils.synchronization_utils import (
    AsyncTimeoutSemaphore,
    LockPriority,
    AsyncTimeoutLock,
)

# Type variables for generic functions
T = TypeVar("T")
R = TypeVar("R")

# Configure logger for this module.
logger = logging.getLogger(__name__)
# Global cache for locks keyed by the current event loop.
_loop_locks = WeakKeyDictionary()


def get_resource_lock() -> AsyncTimeoutLock:
    """
    Retrieve an AsyncTimeoutLock instance bound to the current event loop.
    Returns:
        An AsyncTimeoutLock instance bound to the current event loop.
    """
    # Get the current event loop.
    loop = asyncio.get_running_loop()
    # If no lock exists for this loop, create one.
    if loop not in _loop_locks:
        # Create a new lock for this loop if not already present.
        _loop_locks[loop] = AsyncTimeoutLock(
            "parallel_core_lock", priority=LockPriority.MEDIUM
        )
    # Return the resource lock for the current loop.
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
        max_workers: int = 8,
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
        # Retrieve the number of CPU cores; default to 4 if not available.
        cpu_count = os.cpu_count() or 4
        # Get the available system memory.
        available_memory = psutil.virtual_memory().available
        # Calculate current CPU load as a fraction.
        current_load = psutil.cpu_percent(interval=0.1) / 100.0
        # Determine current memory usage as a fraction.
        current_memory_usage = memory_monitor.get_memory_usage() / 100.0
        # Compute the worker count based solely on CPU availability and current load.
        cpu_based_workers = max(1, int(cpu_count * (1 - current_load * 0.5)))
        # Check if a per-item memory requirement is provided.
        if memory_per_item is not None and memory_per_item > 0:
            # Compute the max number of workers permitted by available memory.
            memory_based_workers = max(
                1, min(int(available_memory * 0.8 / memory_per_item), cpu_based_workers)
            )
        else:
            # Adjust worker count based on memory usage if no memory_per_item is specified.
            memory_factor = 1.0 - (current_memory_usage * 1.5)
            # Ensure the memory factor does not drop below a set threshold.
            memory_factor = max(0.25, memory_factor)
            memory_based_workers = max(1, int(cpu_based_workers * memory_factor))
        # Determine the optimal worker count limited by items_count and max_workers.
        optimal_workers = min(memory_based_workers, items_count, max_workers)
        # Ensure that the optimal worker count is not below the minimum threshold.
        optimal_workers = max(optimal_workers, min_workers)
        # Log the calculated metrics and optimal worker count.
        log_info(
            f"Calculated optimal workers: {optimal_workers} (CPU: {cpu_count}, Load: {current_load:.2f}, Memory: {current_memory_usage:.2f})"
        )
        # Return the determined optimal number of workers.
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
        progress_callback: Optional[
            Callable[[int, int, float], Awaitable[None]]
        ] = None,
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
            operation_id: Optional unique identifier for the operation.
            adaptive: Whether to adjust worker count dynamically based on system load.
            progress_callback: Optional asynchronous callback for progress updates.
        Returns:
            A list of tuples (index, result) for each item, with None representing failures.
        """
        try:
            # Validate inputs and set default values; record the start time.
            operation_id, batch_timeout, item_timeout, start_time = (
                cls._validate_and_prepare_input(
                    items, batch_timeout, item_timeout, operation_id
                )
            )
            # Determine the optimal number of workers while considering adaptive settings.
            worker_count = await cls._acquire_worker_count(items, max_workers, adaptive)
            # Create a semaphore that limits the number of concurrently executing tasks.
            semaphore = cls._create_semaphore(worker_count, operation_id)
            # Initialize progress tracking data.
            progress_data = cls._init_progress_data(start_time, len(items))
            # Build a mapping of indices to asyncio tasks for each item.
            tasks_map = cls._create_tasks_map(
                items,
                semaphore,
                processor,
                item_timeout,
                operation_id,
                progress_data,
                progress_callback,
            )
            # Wait for the tasks to complete with the given batch timeout.
            results = await cls._gather_tasks_with_timeout(
                tasks_map, batch_timeout, operation_id, progress_data
            )
            # Log a final completion summary for the operation.
            cls._log_final_completion(results, progress_data, start_time, operation_id)
            # Return the collected processing results.
            return results
        except Exception as e:
            # Log any unexpected error encountered during parallel processing.
            log_error(
                f"Unexpected error in process_in_parallel: {e} [operation_id={operation_id}]"
            )
            # Raise the exception to propagate error state.
            raise

    @staticmethod
    def _validate_and_prepare_input(
        items: List[T],
        batch_timeout: Optional[float],
        item_timeout: Optional[float],
        operation_id: Optional[str],
    ) -> Tuple[str, float, float, float]:
        """
        Validate inputs and set defaults for timeouts and the operation ID.
        Args:
            items: List of items to process.
            batch_timeout: Overall batch processing timeout.
            item_timeout: Timeout for processing an individual item.
            operation_id: Optional operation identifier.
        Returns:
            A tuple containing (operation_id, batch_timeout, item_timeout, start_time).
        """
        # If the items list is empty, assign default values.
        if not items:
            return operation_id or "parallel_no_items", 0.0, 0.0, time.time()
        # If no operation ID is provided, generate one based on the current time.
        if operation_id is None:
            operation_id = f"parallel_{time.time():.0f}"
        # Set default batch timeout if not specified.
        batch_timeout = batch_timeout or DEFAULT_BATCH_TIMEOUT
        # Set default item timeout if not specified.
        item_timeout = item_timeout or DEFAULT_ITEM_TIMEOUT
        # Record the current time as the processing start time.
        start_time = time.time()
        # Return the prepared input parameters.
        return operation_id, batch_timeout, item_timeout, start_time

    @classmethod
    async def _acquire_worker_count(
        cls, items: List[T], max_workers: Optional[int], adaptive: bool
    ) -> int:
        """
        Determine the optimal worker count using a lock to prevent race conditions.

        This method uses a resource lock (created per event loop) to ensure that the worker
        count is computed consistently across concurrent invocations.

        Args:
            items: List of items to process.
            max_workers: Maximum number of workers allowed.
            adaptive: Whether to adjust worker count based on system load.
        Returns:
            The number of workers to utilize.
        """
        # If a maximum is specified and adaptive adjustment is off, use the minimum of max_workers and item count.
        if max_workers is not None and not adaptive:
            return min(max_workers, len(items))
        # Retrieve a lock associated with the current event loop.
        resource_lock = get_resource_lock()
        try:
            # Attempt to acquire the resource lock with a timeout.
            async with resource_lock.acquire_timeout(DEFAULT_LOCK_TIMEOUT):
                # Compute the optimal worker count based on system resources.
                worker_count = cls.get_optimal_workers(len(items))
                # If max_workers is specified, limit the worker count further.
                if max_workers is not None:
                    worker_count = min(worker_count, max_workers)
        except TimeoutError:
            # On timeout, fall back to a heuristic: a small number of workers.
            worker_count = max(2, min(4, len(items)))
            # Log a warning indicating the fallback was used.
            log_warning(
                f"Timeout acquiring resource lock, using {worker_count} workers"
            )
        # Return the determined worker count.
        return worker_count

    @staticmethod
    def _create_semaphore(
        worker_count: int, operation_id: str
    ) -> AsyncTimeoutSemaphore:
        """
        Create a semaphore limiting concurrency to the specified worker count.
        Args:
            worker_count: The number of concurrently allowed tasks.
            operation_id: Identifier for the current operation.
        Returns:
            An instance of AsyncTimeoutSemaphore.
        """
        # Log the semaphore creation with the specified worker count.
        log_info(
            f"Creating semaphore with {worker_count} workers [operation_id={operation_id}]"
        )
        # Create and return a new semaphore instance with the designated worker count.
        return AsyncTimeoutSemaphore(
            name=f"parallel_semaphore_{operation_id}",
            value=worker_count,
            priority=LockPriority.MEDIUM,
        )

    @staticmethod
    def _init_progress_data(start_time: float, total_items: int) -> Dict[str, Any]:
        """
        Initialize and return a dictionary to track progress of the batch.
        Args:
            start_time: Timestamp marking when processing started.
            total_items: Total number of items to be processed.
        Returns:
            A dictionary containing progress tracking data.
        """
        # Return a dictionary with initial progress values.
        return {
            "completed": 0,
            "failed": 0,
            "last_progress_log": start_time,
            "total_items": total_items,
            "start_time": start_time,
            "last_index": None,
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
        progress_callback: Optional[Callable[[int, int, float], Awaitable[None]]],
    ) -> Dict[int, asyncio.Task]:
        """
        Create a mapping from item indices to their asyncio processing tasks.
        Args:
            items: List of items to be processed.
            semaphore: Semaphore limiting concurrent task execution.
            processor: Asynchronous function to process each item.
            item_timeout: Timeout for processing an individual item.
            operation_id: Operation identifier.
            progress_data: Dictionary holding progress tracking data.
            progress_callback: Optional callback function for progress updates.
        Returns:
            A dictionary mapping item indices to their respective asyncio tasks.
        """
        # Initialize an empty dictionary for storing tasks.
        tasks_map = {}
        # Loop over each item with its associated index.
        for i, item in enumerate(items):
            # Create an asyncio task for processing the item with semaphore control.
            task = asyncio.create_task(
                cls._process_with_semaphore(
                    i,
                    item,
                    semaphore,
                    processor,
                    item_timeout,
                    operation_id,
                    progress_data,
                    progress_callback,
                ),
                name=str(i),
            )
            # Map the index to the created task.
            tasks_map[i] = task
        # Return the complete dictionary of tasks.
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
        progress_callback: Optional[Callable[[int, int, float], Awaitable[None]]],
    ) -> Tuple[int, Optional[R]]:
        """
        Process a single item under semaphore control and within a defined timeout.
        Args:
            index: The index of the item in the list.
            item: The item to be processed.
            semaphore: Semaphore used to limit concurrent processing.
            processor: Asynchronous function to process the item.
            item_timeout: Timeout for processing this item.
            operation_id: Operation identifier.
            progress_data: Dictionary for tracking progress.
            progress_callback: Optional callback for progress updates.
        Returns:
            A tuple containing the index and the result of processing, or None if failed.
        """
        # Acquire the semaphore with a timeout to control concurrency.
        async with semaphore.acquire_timeout(timeout=DEFAULT_LOCK_TIMEOUT):
            try:
                # Process the item asynchronously with an individual timeout.
                result = await asyncio.wait_for(processor(item), timeout=item_timeout)
                # Update progress statistics after successful processing.
                cls._update_progress(
                    index, operation_id, progress_data, progress_callback
                )
                # Return the index with its corresponding result.
                return index, result
            except asyncio.TimeoutError:
                # On item timeout, increment the failure count.
                progress_data["failed"] += 1
                # Log a warning indicating the timeout for this item.
                log_warning(
                    f"Item {index} processing timed out after {item_timeout}s [operation_id={operation_id}]"
                )
                # Return the index with a None result.
                return index, None
            except Exception as e:
                # On a generic exception, also increment the failure count.
                progress_data["failed"] += 1
                # Log the processing error using a security-aware error handler.
                error_id = SecurityAwareErrorHandler.log_processing_error(
                    e, "parallel_processing", f"item_{index}"
                )
                # Log detailed error information.
                log_error(
                    f"Error processing item {index}: {str(e)} [error_id={error_id}, operation_id={operation_id}]"
                )
                # Return the index with a None result.
                return index, None

    @classmethod
    def _update_progress(
        cls,
        index: int,
        operation_id: str,
        progress_data: Dict[str, Any],
        progress_callback: Optional[Callable[[int, int, float], Awaitable[None]]],
    ) -> None:
        """
        Update progress metrics and log progress updates if conditions are met.
        Args:
            index: Index of the last processed item.
            operation_id: Operation identifier.
            progress_data: Dictionary containing progress metrics.
            progress_callback: Optional asynchronous callback for progress reporting.
        """
        # Increment the count of completed items.
        progress_data["completed"] += 1
        # Record the index of the last processed item.
        progress_data["last_index"] = index
        # Get the current time.
        current_time = time.time()
        # Calculate elapsed time since processing began.
        elapsed = current_time - progress_data["start_time"]
        # Retrieve the total number of items.
        total_items = progress_data["total_items"]
        # Retrieve the time when progress was last logged.
        last_log_time = progress_data["last_progress_log"]
        # Check if sufficient time has passed or processing is complete to log progress.
        if (current_time - last_log_time > 5.0) or (
            progress_data["completed"] == total_items
        ):
            # Calculate the current progress percentage.
            progress = progress_data["completed"] / total_items
            # Estimate the total time required based on current progress.
            estimated_total = elapsed / max(progress, 0.01)
            # Determine the estimated remaining time.
            remaining = estimated_total - elapsed
            # Log the progress update.
            log_info(
                f"Progress: {progress_data['completed']}/{total_items} (Last processed index: {index}, {progress * 100:.1f}%), Elapsed: {elapsed:.1f}s, Remaining: {remaining:.1f}s [operation_id={operation_id}]"
            )
            # Update the last log timestamp to the current time.
            progress_data["last_progress_log"] = current_time
            # If a progress callback function is provided, call it asynchronously.
            if progress_callback:
                asyncio.create_task(
                    progress_callback(progress_data["completed"], total_items, elapsed)
                )

    @classmethod
    async def _gather_tasks_with_timeout(
        cls,
        tasks_map: Dict[int, asyncio.Task],
        batch_timeout: float,
        operation_id: str,
        progress_data: Dict[str, Any],
    ) -> List[Tuple[int, Optional[R]]]:
        """
        Await completion of all tasks with an overall batch timeout. If the timeout
        is reached, gather results only from completed tasks.

        Args:
            tasks_map: Mapping of item indices to asyncio tasks.
            batch_timeout: Overall timeout for the batch process.
            operation_id: Operation identifier.
            progress_data: Dictionary with progress tracking data.
        Returns:
            A sorted list of tuples (index, result), with None for tasks that did not complete.
        """
        try:
            # Attempt to gather all task results within the specified batch timeout.
            gathered_results = await asyncio.wait_for(
                asyncio.gather(*tasks_map.values()), timeout=batch_timeout
            )
            # Sort the gathered results by item index.
            sorted_results = sorted(gathered_results, key=lambda x: x[0])
            # Return the sorted list of results.
            return sorted_results
        except asyncio.TimeoutError:
            # Log an error if the batch processing exceeds the timeout.
            log_error(
                f"Batch processing timed out after {batch_timeout}s with progress: {progress_data['completed']}/{progress_data['total_items']} completed [operation_id={operation_id}]"
            )
            # In case of timeout, return the partial results.
            return cls._collect_partial_results(tasks_map)

    @staticmethod
    def _collect_partial_results(
        tasks_map: Dict[int, asyncio.Task],
    ) -> List[Tuple[int, Optional[R]]]:
        """
        Collect and return results from tasks that have completed; assign None for unfinished tasks.
        Args:
            tasks_map: Mapping of item indices to asyncio tasks.
        Returns:
            A list of (index, result) tuples for each task, sorted by index.
        """
        # Initialize a dictionary to collect partial results.
        partial_results = {}
        # Iterate over each task in the mapping.
        for i, task in tasks_map.items():
            # Check if the task has finished execution.
            if task.done():
                # If an exception occurred in the task, record None.
                if task.exception() is not None:
                    partial_results[i] = (i, None)
                else:
                    # Otherwise, record the task's result.
                    partial_results[i] = task.result()
            else:
                # For tasks that haven't finished, assign None.
                partial_results[i] = (i, None)
        # Return the list of results sorted by their index.
        return [partial_results[i] for i in sorted(partial_results.keys())]

    @staticmethod
    def _log_final_completion(
        results: List[Tuple[int, Optional[R]]],
        progress_data: Dict[str, Any],
        start_time: float,
        operation_id: str,
    ) -> None:
        """
        Log a final summary of the parallel processing operation, including total time,
        number of successes, and number of failures.

        Args:
            results: List of tuples (index, result) from processed tasks.
            progress_data: Dictionary of progress tracking metrics.
            start_time: Timestamp marking when processing began.
            operation_id: Operation identifier.
        """
        # Calculate the total time taken for processing.
        total_time = time.time() - start_time
        # Retrieve the total number of items processed.
        total_items = progress_data["total_items"]
        # Get the number of completed items.
        completed = progress_data["completed"]
        # Get the number of failed items.
        failed = progress_data["failed"]
        # Count the number of successful processing results.
        success_count = sum(1 for _, result in results if result is not None)
        # Calculate the success rate as a percentage.
        success_rate = (success_count / total_items * 100) if total_items else 100
        # Log a detailed summary of the processing outcome.
        log_info(
            f"Completed processing {total_items} items in {total_time:.2f}s: {success_count} succeeded ({success_rate:.1f}%), {failed} failed [operation_id={operation_id}]"
        )
        # Log the sensitive operation details with processing statistics.
        log_sensitive_operation(
            "Parallel Processing",
            total_items,
            total_time,
            completed=completed,
            failed=failed,
            operation_id=operation_id,
        )

    @staticmethod
    async def process_pages_in_parallel(
        pages: List[Dict[str, Any]],
        process_func: Callable[
            [Dict[str, Any]], Awaitable[Tuple[Dict[str, Any], List[Dict[str, Any]]]]
        ],
        max_workers: Optional[int] = None,
    ) -> List[Tuple[int, Tuple[Dict[str, Any], List[Dict[str, Any]]]]]:
        """
        Process multiple document pages concurrently using a provided asynchronous function.
        Args:
            pages: List of page data dictionaries.
            process_func: Asynchronous function that processes a single page.
            max_workers: Maximum number of pages to process concurrently (auto-calculated if None).
        Returns:
            A list of tuples, each containing the page number and its corresponding processing result.
        """
        # Check if the pages list is empty; if so, return an empty list.
        if not pages:
            return []
        # Determine the number of concurrent workers based on the number of pages if not explicitly provided.
        if max_workers is None:
            max_workers = ParallelProcessingCore.get_optimal_workers(len(pages))
        else:
            max_workers = min(max_workers, len(pages))
        # Create a semaphore based on the determined max_workers.
        semaphore = asyncio.Semaphore(max_workers)

        async def process_with_semaphore(
            page: Dict[str, Any],
        ) -> Tuple[int, Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
            # Extract the page number from the page dictionary; default to 0 if missing.
            page_number = page.get("page", 0)
            # Use the semaphore to limit concurrent execution.
            async with semaphore:
                try:
                    # Process the page using the provided asynchronous function.
                    page_result = await process_func(page)
                    # Return the page number along with its processing result.
                    return page_number, page_result
                except Exception as e:
                    # Log a warning if an error occurs during page processing.
                    log_warning(f"[PARALLEL] Error processing page {page_number}: {e}")
                    # Return default empty results if page processing fails.
                    return page_number, ({"page": page_number, "sensitive": []}, [])

        # Create a list of tasks for processing each page concurrently.
        tasks = [asyncio.create_task(process_with_semaphore(page)) for page in pages]
        # Gather results from all tasks.
        results = await asyncio.gather(*tasks)
        # Log the summary of processed pages.
        log_info(f"[PARALLEL] Processed {len(pages)} pages with {max_workers} workers")
        # Return the final results.
        return results

    @staticmethod
    async def process_entities_in_parallel(
        detector,
        full_text: str,
        mapping: List[Tuple[Dict[str, Any], int, int]],
        entities: List[Any],
        page_number: int,
        batch_size: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Process entities concurrently for a single page by dividing them into batches.
        Args:
            detector: An instance with an asynchronous method process_entities_for_page.
            full_text: The full text content of the page.
            mapping: List of tuples that map text positions.
            entities: List of entities to be processed.
            page_number: The current page number.
            batch_size: Optional batch size; if None, obtained from configuration.
        Returns:
            A tuple containing a list of processed entities and a dictionary with redaction details.
        """
        # If no entities are provided, return empty results.
        if not entities:
            return [], {"page": page_number, "sensitive": []}
        # Determine the batch size from configuration if not specified.
        if batch_size is None:
            batch_size = get_config("entity_batch_size", 10)
        # Log the initiation of entity processing for the given page.
        log_info(
            f"[PARALLEL] Starting entity processing for page {page_number} with batch size {batch_size} and {len(entities)} total entities"
        )
        # Divide the entities list into batches.
        entity_batches = [
            entities[i : i + batch_size] for i in range(0, len(entities), batch_size)
        ]
        # Prepare lists to collect batch results and their processing times.
        batch_results = []
        batch_times = []
        # Process each batch sequentially.
        for i, batch in enumerate(entity_batches):
            # Record the start time for the current batch.
            start_time = time.perf_counter()
            try:
                # Process the batch using the detector's asynchronous method.
                result = await detector.process_entities_for_page(
                    page_number, full_text, mapping, batch
                )
            except Exception as e:
                # Log an error if processing the batch fails and assign default results.
                log_error(
                    f"[PARALLEL] Error processing batch {i + 1}/{len(entity_batches)} on page {page_number}: {e}"
                )
                result = ([], {"page": page_number, "sensitive": []})
            # Record the end time for the current batch.
            end_time = time.perf_counter()
            # Calculate the elapsed time for the batch.
            elapsed = end_time - start_time
            # Append the result of the batch processing.
            batch_results.append(result)
            # Append the elapsed time.
            batch_times.append(elapsed)
            # Log the processing time for the current batch.
            log_info(
                f"[PARALLEL] Processed batch {i + 1}/{len(entity_batches)} with {len(batch)} entities in {elapsed:.2f}s"
            )
        # Sum the total processing time for all batches.
        total_time = sum(batch_times)
        # Log sensitive details of the batch operation.
        log_sensitive_operation(
            "Entity Batch Processing", len(entities), total_time, page=page_number
        )
        # Initialize lists for combining processed entities and redaction info.
        processed_entities = []
        page_redaction_info = {"page": page_number, "sensitive": []}
        # Merge results from all batches.
        for processed, redaction in batch_results:
            processed_entities.extend(processed)
            page_redaction_info["sensitive"].extend(redaction.get("sensitive", []))
        # Log the completion of entity processing for the page.
        log_info(
            f"[PARALLEL] Completed entity processing for page {page_number} in {total_time:.2f}s"
        )
        # Return the aggregated processed entities and redaction information.
        return processed_entities, page_redaction_info
