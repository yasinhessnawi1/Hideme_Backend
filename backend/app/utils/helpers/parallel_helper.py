"""
Enhanced helper functions for parallel processing with improved async support.
"""
import asyncio
import concurrent.futures
import os
import time
from typing import Dict, Any, List, Callable, Tuple, TypeVar, Generic, Optional, Awaitable

from backend.app.utils.logger import log_info, log_warning, default_logger as logger

# Type variables for generic functions
T = TypeVar('T')
R = TypeVar('R')


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

        # Start with CPU count minus 1 (leave one for the system)
        optimal = max(1, cpu_count - 1)

        # Cap at items count and the specified max
        optimal = min(optimal, items_count, max_workers)

        # Ensure at least min_workers
        optimal = max(optimal, min_workers)

        return optimal

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

        # Auto-configure max_workers if not specified
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
                    return (page.get("page", 0), page_result)
                except Exception as e:
                    log_warning(f"[PARALLEL] Error processing page {page.get('page', 'unknown')}: {e}")
                    return (page.get("page", 0), ({"page": page.get("page", 0), "sensitive": []}, []))

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
            max_workers: Optional[int] = None,
            batch_size: int = 10
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Process entities in parallel for a single page with async support.

        Args:
            detector: Entity detector instance
            full_text: Full text of the page
            mapping: Text-to-position mapping
            entities: List of entities to process
            page_number: Current page number
            max_workers: Maximum number of parallel workers (None for auto)
            batch_size: Number of entities to process in each batch

        Returns:
            Tuple of (processed_entities, page_redaction_info)
        """
        if not entities:
            return [], {"page": page_number, "sensitive": []}

        # For small numbers of entities, process sequentially
        if len(entities) < 5:
            return detector.process_entities_for_page(
                page_number, full_text, mapping, entities
            )

        # Split entities into batches
        entity_batches = [entities[i:i + batch_size] for i in range(0, len(entities), batch_size)]

        # Process batches of entities
        async def process_batch(batch):
            return await asyncio.to_thread(
                detector.process_entities_for_page,
                page_number, full_text, mapping, batch
            )

        # Use semaphore to limit concurrent processing
        max_workers = max_workers or ParallelProcessingHelper.get_optimal_workers(len(entity_batches))
        semaphore = asyncio.Semaphore(max_workers)

        # Wrapper to handle semaphore
        async def process_with_semaphore(batch):
            async with semaphore:
                return await process_batch(batch)

        # Process batches
        batch_results = await asyncio.gather(
            *[process_with_semaphore(batch) for batch in entity_batches],
            return_exceptions=True
        )

        # Combine results, handling potential exceptions
        all_processed_entities = []
        all_sensitive_items = []
        error_count = 0

        for result in batch_results:
            if isinstance(result, Exception):
                error_count += 1
                log_warning(f"[PARALLEL] Error processing entity batch: {result}")
            else:
                processed_entities, page_info = result
                all_processed_entities.extend(processed_entities)
                all_sensitive_items.extend(page_info.get("sensitive", []))

        # Create combined page redaction info
        page_redaction_info = {
            "page": page_number,
            "sensitive": all_sensitive_items
        }

        if error_count > 0:
            log_warning(f"[PARALLEL] {error_count} entity batches failed processing")

        return all_processed_entities, page_redaction_info