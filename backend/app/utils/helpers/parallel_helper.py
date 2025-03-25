"""
Enhanced helper functions for parallel processing with improved async support.
"""
import asyncio
import os
import time
from typing import Dict, Any, List, Callable, Tuple, TypeVar, Optional, Awaitable

from backend.app.configs.config_singleton import get_config
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.logging.secure_logging import log_sensitive_operation

# Type variables for generic functions
T = TypeVar('T')
R = TypeVar('R')
U = TypeVar('U')


class ParallelProcessingHelper:
    """
    Enhanced helper class for parallel processing tasks with async support.
    """

    @staticmethod
    def get_optimal_workers(
        items_count: int,
        min_workers: int = 2,
        max_workers: int = 8
    ) -> int:
        """
        Calculate the optimal number of worker threads based on CPU count and items.

        Args:
            items_count: Number of items to process
            min_workers: Minimum number of workers
            max_workers: Maximum number of workers

        Returns:
            Optimal number of worker threads
        """
        cpu_count = os.cpu_count() or 4

        # Start with CPU count minus 2 (leave one for the system)
        optimal = max(1, cpu_count - 2)

        # Cap at items count and the specified max
        optimal = min(optimal, items_count, max_workers)

        # Ensure at least min_workers
        optimal = max(optimal, min_workers)

        return optimal

    @staticmethod
    async def process_in_parallel(
            items: List[T],
            processor: Callable[[T], Awaitable[U]],
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

        # Set default timeouts
        DEFAULT_TIMEOUT = 300.0  # 5 minutes for overall batch
        DEFAULT_ITEM_TIMEOUT = 60.0  # 1 minute per item

        worker_count = max_workers or ParallelProcessingHelper.get_optimal_workers(len(items))
        batch_timeout = timeout or DEFAULT_TIMEOUT
        single_item_timeout = item_timeout or (batch_timeout / 2 if batch_timeout < DEFAULT_ITEM_TIMEOUT * 2
                                               else DEFAULT_ITEM_TIMEOUT)

        # Use semaphore to limit concurrent tasks
        semaphore = asyncio.Semaphore(worker_count)
        operation_id = f"parallel_{time.time():.0f}"

        log_info(
            f"[PARALLEL] Starting parallel processing of {len(items)} items with {worker_count} workers (operation: {operation_id})"
        )

        start_time = time.time()
        completed, failed = 0, 0

        async def process_with_semaphore(index: int, item: T):
            """Process a single item with semaphore and timeout protection."""
            nonlocal completed, failed

            async with semaphore:
                try:
                    # Apply timeout to individual item processing
                    result = await asyncio.wait_for(processor(item), timeout=single_item_timeout)
                    completed += 1
                    return index, result
                except asyncio.TimeoutError:
                    failed += 1
                    log_warning(f"[PARALLEL] Item {index} processing timed out after {single_item_timeout}s")
                    return index, None
                except Exception as e:
                    failed += 1
                    log_error(f"[PARALLEL] Error processing item {index}: {str(e)}")
                    return index, None

        # Create and gather tasks
        tasks = [process_with_semaphore(i, item) for i, item in enumerate(items)]

        try:
            # Apply overall batch timeout
            results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=batch_timeout)
            total_time = time.time() - start_time

            log_info(
                f"[PARALLEL] Completed processing {len(items)} items in {total_time:.2f}s: "
                f"{completed} completed, {failed} failed (operation: {operation_id})"
            )
            return results
        except asyncio.TimeoutError:
            log_error(f"[PARALLEL] Overall batch processing timed out after {batch_timeout}s (operation: {operation_id})")
            return []

    @staticmethod
    async def process_pages_in_parallel(
            pages: List[Dict[str, Any]],
            process_func: Callable[[Dict[str, Any]], Awaitable[Tuple[Dict[str, Any], List[Dict[str, Any]]]]],
            max_workers: Optional[int] = None
    ) -> List[Tuple[int, Tuple[Dict[str, Any], List[Dict[str, Any]]]]]:
        """
        Process multiple document pages in parallel with async support.

        Args:
            pages: List of page data dictionaries
            process_func: Async function to call for each page
            max_workers: Maximum number of parallel workers (None for auto)

        Returns:
            List of tuples (page_number, (page_redaction_info, processed_entities))
        """
        if not pages:
            return []

        # Autoconfigure max_workers if not specified
        if max_workers is None:
            max_workers = ParallelProcessingHelper.get_optimal_workers(len(pages))
        else:
            max_workers = min(max_workers, len(pages))

        # Use semaphore to limit concurrent tasks
        semaphore = asyncio.Semaphore(max_workers)

        # Wrapper function to acquire and release semaphore
        async def process_with_semaphore(page):
            async with semaphore:
                try:
                    # Call the processing function for the page
                    page_result = await process_func(page)
                    return page.get("page", 0), page_result
                except Exception as e:
                    log_warning(f"[PARALLEL] Error processing page {page.get('page', 'unknown')}: {e}")
                    return page.get("page", 0), ({"page": page.get("page", 0), "sensitive": []}, [])

        # Create and gather tasks
        tasks = [process_with_semaphore(page) for page in pages]

        # Wait for all tasks to complete
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
        Process entities in parallel for a single page with async support.
        Externalizes the batch size from the config and adds detailed logging.

        Args:
            detector: Entity detector instance.
            full_text: Full text of the page.
            mapping: Text-to-position mapping.
            entities: List of entities to process.
            page_number: Current page number.
            batch_size: Number of entities to process in each batch (optional).

        Returns:
            Tuple of (processed_entities, page_redaction_info).
        """
        if not entities:
            return [], {"page": page_number, "sensitive": []}

        # Use the config singleton to load the batch size if not explicitly provided.
        if batch_size is None:
            batch_size  = get_config("entity_batch_size", 10)

        log_info(
            f"[PARALLEL] Starting entity processing for page {page_number} with batch size {batch_size} and {len(entities)} total entities")

        # Split entities into batches based on the externalized batch size.
        entity_batches = [entities[i:i + batch_size] for i in range(0, len(entities), batch_size)]
        batch_results = []
        batch_times = []

        # Process each batch and log performance metrics.
        for i, batch in enumerate(entity_batches):
            start_time = time.perf_counter()
            result = await detector.process_entities_for_page(page_number, full_text, mapping, batch)
            end_time = time.perf_counter()
            elapsed = end_time - start_time
            batch_results.append(result)
            batch_times.append(elapsed)
            log_info(
                f"[PARALLEL] Processed batch {i + 1}/{len(entity_batches)} with {len(batch)} entities in {elapsed:.2f}s")

        total_time = sum(batch_times)
        log_sensitive_operation("Entity Batch Processing", len(entities), total_time, page=page_number)

        # Combine batch results.
        processed_entities = []
        page_redaction_info = {"page": page_number, "sensitive": []}
        for processed, redaction in batch_results:
            processed_entities.extend(processed)
            page_redaction_info["sensitive"].extend(redaction.get("sensitive", []))

        log_info(f"[PARALLEL] Completed entity processing for page {page_number} in {total_time:.2f}s")
        return processed_entities, page_redaction_info