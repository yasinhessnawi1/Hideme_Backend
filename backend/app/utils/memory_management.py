"""
Memory management utilities for document processing with enhanced security and adaptive optimization.

This module provides functions for monitoring and optimizing memory usage
during document processing operations, ensuring efficient resource utilization
and preventing memory-related vulnerabilities with adaptive thresholds based on
system resources.
"""
import asyncio
import os
import gc
import psutil
import logging
import threading
import time
from typing import Optional, Dict, Any, Callable, List, TypeVar, Awaitable
from functools import wraps

# Configure logger
logger = logging.getLogger(__name__)

# Type variable for generic functions
T = TypeVar('T')


class MemoryMonitor:
    """
    Memory usage monitoring and management for high-throughput document processing.

    This class provides tools to monitor memory usage, enforce memory limits,
    and trigger cleanup when memory usage exceeds configured thresholds.
    Features include adaptive thresholds based on system resources and
    progressive cleanup strategies.
    """

    def __init__(
            self,
            memory_threshold: float = 80.0,  # 80% memory threshold
            critical_threshold: float = 90.0,  # 90% critical threshold
            check_interval: float = 5.0,       # 5 seconds check interval
            enable_monitoring: bool = True,
            adaptive_thresholds: bool = True
    ):
        """
        Initialize the memory monitor with configuration parameters.

        Args:
            memory_threshold: Memory usage threshold as percentage.
            critical_threshold: Critical memory threshold as percentage.
            check_interval: Memory check interval in seconds.
            enable_monitoring: Whether to enable background monitoring.
            adaptive_thresholds: Whether to adjust thresholds based on system resources.
        """
        self.base_memory_threshold = memory_threshold
        self.base_critical_threshold = critical_threshold
        self.memory_threshold = memory_threshold
        self.critical_threshold = critical_threshold
        self.check_interval = check_interval
        self.enable_monitoring = enable_monitoring
        self.adaptive_thresholds = adaptive_thresholds
        self._monitor_thread = None
        self._stop_monitor = threading.Event()
        self._lock = threading.Lock()
        self._last_gc_time = 0
        self._gc_interval = 60  # Minimum seconds between full garbage collections

        # Memory statistics
        self.memory_stats = {
            "peak_usage": 0.0,
            "average_usage": 0.0,
            "checks_count": 0,
            "emergency_cleanups": 0,
            "last_check_time": 0.0,
            "current_usage": 0.0,
            "available_memory_mb": 0,
            "system_threshold_adjustments": 0
        }

        # Initialize available memory stats
        self._update_available_memory()

        # Adapt thresholds based on available memory if enabled
        if adaptive_thresholds:
            self._adjust_thresholds_based_on_system()

        # Start background monitoring if enabled
        if self.enable_monitoring:
            self.start_monitoring()

    def _update_available_memory(self) -> None:
        """Update available memory statistics from the system."""
        try:
            system_memory = psutil.virtual_memory()
            self.memory_stats["available_memory_mb"] = system_memory.available / (1024 * 1024)
        except Exception as e:
            logger.error(f"Error updating available memory: {str(e)}")
            self.memory_stats["available_memory_mb"] = 0

    def _adjust_thresholds_based_on_system(self) -> None:
        """
        Adaptively adjust memory thresholds based on system resources.

        For systems with less memory, use more conservative thresholds.
        For systems with ample memory, use more relaxed thresholds.
        """
        try:
            system_memory = psutil.virtual_memory()
            total_memory_gb = system_memory.total / (1024 * 1024 * 1024)
            available_memory_gb = system_memory.available / (1024 * 1024 * 1024)
            usage_percent = system_memory.percent

            if total_memory_gb < 4:  # Low memory system (<4GB)
                self.memory_threshold = max(60.0, self.base_memory_threshold - 20)
                self.critical_threshold = max(75.0, self.base_critical_threshold - 15)
            elif total_memory_gb < 8:  # Medium memory system (4-8GB)
                self.memory_threshold = max(70.0, self.base_memory_threshold - 10)
                self.critical_threshold = max(85.0, self.base_critical_threshold - 5)
            elif total_memory_gb > 16:  # High memory system (>16GB)
                self.memory_threshold = min(85.0, self.base_memory_threshold + 5)
                self.critical_threshold = min(95.0, self.base_critical_threshold + 5)

            # Further adjust if system is already under pressure
            if usage_percent > 70:
                self.memory_threshold = max(60.0, self.memory_threshold - 10)
                self.critical_threshold = max(75.0, self.critical_threshold - 10)

            logger.info(
                f"Adjusted memory thresholds: memory_threshold={self.memory_threshold:.1f}%, "
                f"critical_threshold={self.critical_threshold:.1f}%, total_memory={total_memory_gb:.1f}GB, "
                f"available_memory={available_memory_gb:.1f}GB"
            )
            self.memory_stats["system_threshold_adjustments"] += 1

        except Exception as e:
            logger.error(f"Error adjusting thresholds: {str(e)}")
            self.memory_threshold = self.base_memory_threshold
            self.critical_threshold = self.base_critical_threshold

    def start_monitoring(self) -> None:
        """Start the background memory monitoring thread."""
        if self._monitor_thread is not None and self._monitor_thread.is_alive():
            return

        self._stop_monitor.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_memory, daemon=True)
        self._monitor_thread.start()
        logger.info("Memory monitoring started")

    def stop_monitoring(self) -> None:
        """Stop the background memory monitoring thread."""
        if self._monitor_thread is None or not self._monitor_thread.is_alive():
            return

        self._stop_monitor.set()
        self._monitor_thread.join(timeout=2.0)
        logger.info("Memory monitoring stopped")

    def _monitor_memory(self) -> None:
        """Background thread: periodically check memory usage and trigger cleanup if needed."""
        adaptive_counter = 0

        while not self._stop_monitor.is_set():
            try:
                self._update_available_memory()
                current_usage = self.get_memory_usage()

                with self._lock:
                    self.memory_stats["current_usage"] = current_usage
                    self.memory_stats["checks_count"] += 1
                    self.memory_stats["last_check_time"] = time.time()
                    if current_usage > self.memory_stats["peak_usage"]:
                        self.memory_stats["peak_usage"] = current_usage
                    self.memory_stats["average_usage"] = (
                        (self.memory_stats["average_usage"] * (self.memory_stats["checks_count"] - 1) + current_usage) /
                        self.memory_stats["checks_count"]
                    )

                adaptive_counter += 1
                if self.adaptive_thresholds and adaptive_counter >= 60:
                    self._adjust_thresholds_based_on_system()
                    adaptive_counter = 0

                if current_usage >= self.critical_threshold:
                    self._emergency_cleanup()
                elif current_usage >= self.memory_threshold:
                    self._perform_cleanup()

            except Exception as e:
                logger.error(f"Error in memory monitor: {str(e)}")

            self._stop_monitor.wait(self.check_interval)

    def get_memory_usage(self) -> float:
        """
        Get the current memory usage as a percentage of total system memory.

        Returns:
            Current memory usage percentage.
        """
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        system_memory = psutil.virtual_memory()
        usage_percent = (memory_info.rss / system_memory.total) * 100.0
        return usage_percent

    def get_memory_stats(self) -> Dict[str, Any]:
        """
        Retrieve the current memory statistics.

        Returns:
            A copy of the memory statistics dictionary.
        """
        self._update_available_memory()
        with self._lock:
            return self.memory_stats.copy()

    def should_use_memory_buffer(self, size_bytes: int) -> bool:
        """
        Decide whether to use an in-memory buffer based on the size and current memory pressure.

        Args:
            size_bytes: The size of the data in bytes.

        Returns:
            True if an in-memory buffer should be used, False if disk buffering is preferred.
        """
        current_usage = self.get_memory_usage()
        available_memory = self.memory_stats["available_memory_mb"] * 1024 * 1024

        if current_usage >= self.critical_threshold:
            max_buffer_size = min(1024 * 1024, int(available_memory * 0.01))
        elif current_usage >= self.memory_threshold:
            max_buffer_size = min(5 * 1024 * 1024, int(available_memory * 0.05))
        else:
            max_buffer_size = min(25 * 1024 * 1024, int(available_memory * 0.1))

        return size_bytes <= max_buffer_size

    def _perform_cleanup(self) -> None:
        """
        Perform a regular cleanup when memory usage exceeds the threshold.

        This method uses progressive garbage collection strategies:
         - If memory usage is significantly high, a full GC (generation 2) is triggered.
         - Otherwise, a partial GC (generation 1) may be performed.
         - Finally, application-specific caches are cleared.

        The method logs the estimated memory freed after cleanup.
        """
        current_time = time.time()
        current_usage = self.memory_stats["current_usage"]

        logger.warning(
            f"Memory usage ({current_usage:.1f}%) exceeded threshold {self.memory_threshold}%. Running cleanup..."
        )

        if current_usage > (self.memory_threshold + self.critical_threshold) / 2:
            logger.info("Performing aggressive cleanup due to high memory pressure")
            gc.collect(generation=2)
            self._last_gc_time = current_time
        elif current_time - self._last_gc_time > self._gc_interval:
            gc.collect(generation=2)
            self._last_gc_time = current_time
        else:
            gc.collect(generation=1)

        self._clear_application_caches()
        freed = self.memory_stats["current_usage"] - self.get_memory_usage()
        logger.info(f"Cleanup complete, freed {freed:.1f}% memory")

    def _emergency_cleanup(self) -> None:
        """
        Execute an emergency cleanup when critical memory thresholds are exceeded.

        This aggressive strategy includes full garbage collection, cache clearance,
        and additional memory freeing measures. It logs the outcome after cleanup.
        """
        logger.error(
            f"CRITICAL: Memory usage ({self.memory_stats['current_usage']:.1f}%) exceeded critical threshold {self.critical_threshold}%!"
        )
        with self._lock:
            self.memory_stats["emergency_cleanups"] += 1
        gc.collect(generation=2)
        self._clear_application_caches()
        self._free_additional_memory()
        new_usage = self.get_memory_usage()
        freed_percent = self.memory_stats["current_usage"] - new_usage
        logger.warning(
            f"Emergency cleanup completed: freed {freed_percent:.1f}% memory. New usage: {new_usage:.1f}%"
        )

    def _clear_application_caches(self) -> None:
        """Clear application-specific caches to free up memory."""
        try:
            try:
                from backend.app.utils.caching_middleware import invalidate_cache
                invalidate_cache()
                logger.info("Response cache cleared")
            except (ImportError, AttributeError):
                pass
        except Exception as e:
            logger.error(f"Error clearing application caches: {str(e)}")

    def _free_additional_memory(self) -> None:
        """
        Attempt to free extra memory using aggressive strategies.

        This includes clearing Python's internal caches, forcing extra garbage collection,
        and releasing unused memory back to the operating system if supported.
        """
        try:
            import sys
            if hasattr(sys, 'clear_type_cache'):
                sys.clear_type_cache()
            gc.collect()
            if hasattr(gc, 'malloc_trim'):
                gc.malloc_trim()
        except Exception as e:
            logger.error(f"Error in additional memory freeing: {str(e)}")


# Global memory monitor instance with adaptive thresholds
memory_monitor = MemoryMonitor(adaptive_thresholds=True)


def memory_optimized(threshold_mb: Optional[int] = None, adaptive: bool = True,
                     min_gc_interval: float = 10.0):
    """
    Decorator to optimize memory usage for functions processing large data.

    This improved version adapts garbage collection strategies based on current memory pressure,
    function characteristics, and recent GC effectiveness to minimize unnecessary GC cycles.

    Args:
        threshold_mb: Memory threshold in MB to trigger cleanup after function execution.
                      If None, an adaptive threshold is computed.
        adaptive: Whether to use adaptive thresholds based on system state.
        min_gc_interval: Minimum seconds between full GC runs for the same function.

    Returns:
        The decorated function.
    """
    # Track GC effectiveness and last GC time per function
    _gc_stats = {}
    _gc_lock = threading.RLock()

    def decorator(func):
        func_name = func.__name__

        # Initialize stats for this function
        with _gc_lock:
            if func_name not in _gc_stats:
                _gc_stats[func_name] = {
                    'last_gc_time': 0,
                    'last_gc_effectiveness': 0,
                    'total_calls': 0,
                    'gc_calls': 0,
                    'memory_increases': [],  # Track memory increases to predict future needs
                }

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            with _gc_lock:
                _gc_stats[func_name]['total_calls'] += 1

            initial_memory = memory_monitor.get_memory_usage()
            adaptive_threshold = threshold_mb

            # More intelligent adaptive threshold based on system state and function history
            if adaptive_threshold is None:
                available_memory_mb = memory_monitor.memory_stats["available_memory_mb"]

                # Consider function history
                with _gc_lock:
                    stats = _gc_stats[func_name]
                    avg_memory_increase = 0
                    if stats['memory_increases']:
                        avg_memory_increase = sum(stats['memory_increases']) / len(stats['memory_increases'])

                # Balance between history and current system state
                if avg_memory_increase > 0:
                    # Adjust threshold based on historical memory increase
                    adaptive_threshold = max(5, min(100, avg_memory_increase * 1.5))
                else:
                    # Use system-state based logic when no history available
                    if initial_memory < 30:
                        adaptive_threshold = 30 if available_memory_mb > 1000 else 15
                    elif initial_memory < 60:
                        adaptive_threshold = 20 if available_memory_mb > 500 else 10
                    else:
                        adaptive_threshold = 10 if available_memory_mb > 300 else 5

            logger.debug(f"[MEMORY] Running {func_name} with adaptive threshold {adaptive_threshold}MB")

            # Make pre-execution GC decision based on system state and function history
            current_time = time.time()
            run_gc = False
            gc_generation = 0

            with _gc_lock:
                stats = _gc_stats[func_name]
                time_since_last_gc = current_time - stats['last_gc_time']

                # Determine if we should run GC based on several factors
                if initial_memory > 90:
                    # Critical memory pressure - always run full GC
                    run_gc = True
                    gc_generation = 2
                elif initial_memory > 70:
                    # High memory pressure - run GC if not done recently
                    if time_since_last_gc > min_gc_interval / 2:
                        run_gc = True
                        gc_generation = 2
                elif initial_memory > 50:
                    # Medium memory pressure - selective GC based on effectiveness
                    if time_since_last_gc > min_gc_interval and stats['last_gc_effectiveness'] > 5:
                        run_gc = True
                        gc_generation = 1
                elif initial_memory > 30:
                    # Low memory pressure - only light GC if beneficial
                    if time_since_last_gc > min_gc_interval * 2 and stats['last_gc_effectiveness'] > 10:
                        run_gc = True
                        gc_generation = 0

            # Run pre-execution GC if needed
            if run_gc:
                gc.collect(generation=gc_generation)
                with _gc_lock:
                    _gc_stats[func_name]['last_gc_time'] = time.time()
                    _gc_stats[func_name]['gc_calls'] += 1

                logger.debug(
                    f"[MEMORY] Pre-function GC(gen={gc_generation}) for {func_name} - memory usage {initial_memory:.1f}%")

            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                # Post-execution GC decision making
                final_memory = memory_monitor.get_memory_usage()
                memory_diff = final_memory - initial_memory

                # Record memory difference for future predictions
                with _gc_lock:
                    _gc_stats[func_name]['memory_increases'].append(memory_diff)
                    # Keep only the last 10 records to adapt to changing patterns
                    if len(_gc_stats[func_name]['memory_increases']) > 10:
                        _gc_stats[func_name]['memory_increases'].pop(0)

                # Determine threshold for post-execution GC
                process = psutil.Process(os.getpid())
                system_memory = psutil.virtual_memory()
                threshold_percent = (adaptive_threshold * 1024 * 1024 / system_memory.total) * 100.0

                if memory_diff > threshold_percent or final_memory > 80:
                    logger.info(
                        f"Function {func_name} increased memory by {memory_diff:.1f}%. "
                        f"Running cleanup with adaptive threshold {adaptive_threshold}MB"
                    )

                    # Determine GC strategy based on memory pressure
                    pre_gc_time = time.time()

                    if final_memory > 90:  # Critical
                        gc.collect(generation=2)
                        logger.debug(
                            f"[MEMORY] Post-function full GC for {func_name} - critical memory usage {final_memory:.1f}%")
                    elif final_memory > 70 or memory_diff > threshold_percent * 2:  # High
                        gc.collect(generation=1)
                        logger.debug(
                            f"[MEMORY] Post-function partial GC for {func_name} - high memory usage {final_memory:.1f}%")
                    else:  # Moderate
                        gc.collect(generation=0)
                        logger.debug(
                            f"[MEMORY] Post-function light GC for {func_name} - memory usage {final_memory:.1f}%")

                    post_gc_memory = memory_monitor.get_memory_usage()
                    gc_effect = final_memory - post_gc_memory

                    # Record GC effectiveness for future decisions
                    with _gc_lock:
                        _gc_stats[func_name]['last_gc_time'] = time.time()
                        _gc_stats[func_name]['last_gc_effectiveness'] = gc_effect
                        _gc_stats[func_name]['gc_calls'] += 1

                    if gc_effect > 0:
                        logger.info(f"Garbage collection freed {gc_effect:.1f}% memory")
                    else:
                        logger.info(f"Garbage collection had minimal effect ({gc_effect:.1f}%)")

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Same logic as async_wrapper but for synchronous functions
            with _gc_lock:
                _gc_stats[func_name]['total_calls'] += 1

            initial_memory = memory_monitor.get_memory_usage()
            adaptive_threshold = threshold_mb

            # More intelligent adaptive threshold based on system state and function history
            if adaptive_threshold is None:
                available_memory_mb = memory_monitor.memory_stats["available_memory_mb"]

                # Consider function history
                with _gc_lock:
                    stats = _gc_stats[func_name]
                    avg_memory_increase = 0
                    if stats['memory_increases']:
                        avg_memory_increase = sum(stats['memory_increases']) / len(stats['memory_increases'])

                # Balance between history and current system state
                if avg_memory_increase > 0:
                    # Adjust threshold based on historical memory increase
                    adaptive_threshold = max(5, min(100, avg_memory_increase * 1.5))
                else:
                    # Use system-state based logic when no history available
                    if initial_memory < 30:
                        adaptive_threshold = 30 if available_memory_mb > 1000 else 15
                    elif initial_memory < 60:
                        adaptive_threshold = 20 if available_memory_mb > 500 else 10
                    else:
                        adaptive_threshold = 10 if available_memory_mb > 300 else 5

            logger.debug(f"[MEMORY] Running {func_name} with adaptive threshold {adaptive_threshold}MB")

            # Make pre-execution GC decision based on system state and function history
            current_time = time.time()
            run_gc = False
            gc_generation = 0

            with _gc_lock:
                stats = _gc_stats[func_name]
                time_since_last_gc = current_time - stats['last_gc_time']

                # Determine if we should run GC based on several factors
                if initial_memory > 90:
                    # Critical memory pressure - always run full GC
                    run_gc = True
                    gc_generation = 2
                elif initial_memory > 70:
                    # High memory pressure - run GC if not done recently
                    if time_since_last_gc > min_gc_interval / 2:
                        run_gc = True
                        gc_generation = 2
                elif initial_memory > 50:
                    # Medium memory pressure - selective GC based on effectiveness
                    if time_since_last_gc > min_gc_interval and stats['last_gc_effectiveness'] > 5:
                        run_gc = True
                        gc_generation = 1
                elif initial_memory > 30:
                    # Low memory pressure - only light GC if beneficial
                    if time_since_last_gc > min_gc_interval * 2 and stats['last_gc_effectiveness'] > 10:
                        run_gc = True
                        gc_generation = 0

            # Run pre-execution GC if needed
            if run_gc:
                gc.collect(generation=gc_generation)
                with _gc_lock:
                    _gc_stats[func_name]['last_gc_time'] = time.time()
                    _gc_stats[func_name]['gc_calls'] += 1

                logger.debug(
                    f"[MEMORY] Pre-function GC(gen={gc_generation}) for {func_name} - memory usage {initial_memory:.1f}%")

            try:
                result = func(*args, **kwargs)
                return result
            finally:
                # Post-execution GC decision making
                final_memory = memory_monitor.get_memory_usage()
                memory_diff = final_memory - initial_memory

                # Record memory difference for future predictions
                with _gc_lock:
                    _gc_stats[func_name]['memory_increases'].append(memory_diff)
                    # Keep only the last 10 records to adapt to changing patterns
                    if len(_gc_stats[func_name]['memory_increases']) > 10:
                        _gc_stats[func_name]['memory_increases'].pop(0)

                # Determine threshold for post-execution GC
                process = psutil.Process(os.getpid())
                system_memory = psutil.virtual_memory()
                threshold_percent = (adaptive_threshold * 1024 * 1024 / system_memory.total) * 100.0

                if memory_diff > threshold_percent or final_memory > 80:
                    logger.info(
                        f"Function {func_name} increased memory by {memory_diff:.1f}%. "
                        f"Running cleanup with adaptive threshold {adaptive_threshold}MB"
                    )

                    # Determine GC strategy based on memory pressure
                    pre_gc_time = time.time()

                    if final_memory > 90:  # Critical
                        gc.collect(generation=2)
                        logger.debug(
                            f"[MEMORY] Post-function full GC for {func_name} - critical memory usage {final_memory:.1f}%")
                    elif final_memory > 70 or memory_diff > threshold_percent * 2:  # High
                        gc.collect(generation=1)
                        logger.debug(
                            f"[MEMORY] Post-function partial GC for {func_name} - high memory usage {final_memory:.1f}%")
                    else:  # Moderate
                        gc.collect(generation=0)
                        logger.debug(
                            f"[MEMORY] Post-function light GC for {func_name} - memory usage {final_memory:.1f}%")

                    post_gc_memory = memory_monitor.get_memory_usage()
                    gc_effect = final_memory - post_gc_memory

                    # Record GC effectiveness for future decisions
                    with _gc_lock:
                        _gc_stats[func_name]['last_gc_time'] = time.time()
                        _gc_stats[func_name]['last_gc_effectiveness'] = gc_effect
                        _gc_stats[func_name]['gc_calls'] += 1

                    if gc_effect > 0:
                        logger.info(f"Garbage collection freed {gc_effect:.1f}% memory")
                    else:
                        logger.info(f"Garbage collection had minimal effect ({gc_effect:.1f}%)")

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator

class MemoryOptimizedReader:
    """
    Memory-optimized file reader for large document processing.

    This class provides utilities for reading and processing large files
    in chunks to minimize memory usage, with adaptive buffer sizing based
    on system resources.
    """

    @staticmethod
    async def read_file_chunks(file_path: str, chunk_size: Optional[int] = None) -> bytes:
        """
        Read a file in chunks and return the complete content.

        The chunk size is adaptively determined based on available memory if not specified.

        Args:
            file_path: Path to the file.
            chunk_size: Size of each chunk in bytes (if None, determined adaptively).

        Returns:
            The complete file content as bytes.
        """
        file_size = os.path.getsize(file_path)
        if chunk_size is None:
            available_memory_mb = memory_monitor.memory_stats["available_memory_mb"]
            current_usage = memory_monitor.get_memory_usage()
            if current_usage > 80:
                chunk_size = min(64 * 1024, max(4 * 1024, int(available_memory_mb * 1024 * 0.001)))
            elif current_usage > 60:
                chunk_size = min(256 * 1024, max(16 * 1024, int(available_memory_mb * 1024 * 0.005)))
            else:
                chunk_size = min(1024 * 1024, max(64 * 1024, int(available_memory_mb * 1024 * 0.01)))
        content = b""
        try:
            import aiofiles
            async with aiofiles.open(file_path, "rb") as f:
                while chunk := await f.read(chunk_size):
                    content += chunk
                    if len(content) % (10 * chunk_size) == 0:
                        await asyncio.sleep(0)
        except ImportError:
            with open(file_path, "rb") as f:
                while chunk := f.read(chunk_size):
                    content += chunk
                    if len(content) % (10 * chunk_size) == 0:
                        await asyncio.sleep(0)
        return content

    @staticmethod
    async def process_file_streamed(
            file_path: str,
            processor: Callable[[bytes], Any],
            chunk_size: Optional[int] = None
    ) -> List[Any]:
        """
        Process a file in streaming mode using the provided processor function.

        The chunk size is adaptively determined based on available memory if not specified.

        Args:
            file_path: Path to the file.
            processor: Function to process each chunk.
            chunk_size: Size of each chunk in bytes (if None, determined adaptively).

        Returns:
            A list of processing results.
        """
        file_size = os.path.getsize(file_path)
        if chunk_size is None:
            available_memory_mb = memory_monitor.memory_stats["available_memory_mb"]
            current_usage = memory_monitor.get_memory_usage()
            if current_usage > 80:
                chunk_size = min(64 * 1024, max(4 * 1024, int(available_memory_mb * 1024 * 0.001)))
            elif current_usage > 60:
                chunk_size = min(256 * 1024, max(16 * 1024, int(available_memory_mb * 1024 * 0.005)))
            else:
                chunk_size = min(1024 * 1024, max(64 * 1024, int(available_memory_mb * 1024 * 0.01)))
        results = []
        try:
            import aiofiles
            async with aiofiles.open(file_path, "rb") as f:
                while chunk := await f.read(chunk_size):
                    result = await asyncio.to_thread(processor, chunk)
                    results.append(result)
                    if len(results) % 10 == 0:
                        await asyncio.sleep(0)
        except ImportError:
            def read_chunks():
                chunk_results = []
                with open(file_path, "rb") as f:
                    while chunk := f.read(chunk_size):
                        chunk_results.append(processor(chunk))
                return chunk_results
            results = await asyncio.to_thread(read_chunks)
        return results

    @staticmethod
    async def stream_large_file(
            file_path: str,
            chunk_processor: Callable[[bytes, int], Awaitable[None]],
            chunk_size: Optional[int] = None
    ) -> int:
        """
        Stream a large file through an async processor function with optimal memory usage.

        Args:
            file_path: Path to the file.
            chunk_processor: Async function to process each chunk along with its position.
            chunk_size: Size of each chunk in bytes (if None, determined adaptively).

        Returns:
            The total number of chunks processed.
        """
        if chunk_size is None:
            file_size = os.path.getsize(file_path)
            available_memory_mb = memory_monitor.memory_stats["available_memory_mb"]
            current_usage = memory_monitor.get_memory_usage()
            if file_size < 1024 * 1024:
                chunk_size = file_size
            elif current_usage > 80:
                chunk_size = min(64 * 1024, max(4 * 1024, int(available_memory_mb * 1024 * 0.001)))
            elif current_usage > 60:
                chunk_size = min(256 * 1024, max(16 * 1024, int(available_memory_mb * 1024 * 0.005)))
            else:
                chunk_size = min(1024 * 1024, max(64 * 1024, int(available_memory_mb * 1024 * 0.01)))
        chunks_processed = 0
        position = 0
        try:
            import aiofiles
            async with aiofiles.open(file_path, "rb") as f:
                while chunk := await f.read(chunk_size):
                    await chunk_processor(chunk, position)
                    chunks_processed += 1
                    position += len(chunk)
                    if chunks_processed % 10 == 0:
                        await asyncio.sleep(0)
        except ImportError:
            with open(file_path, "rb") as f:
                while chunk := f.read(chunk_size):
                    await chunk_processor(chunk, position)
                    chunks_processed += 1
                    position += len(chunk)
                    if chunks_processed % 10 == 0:
                        await asyncio.sleep(0)
        return chunks_processed


def init_memory_monitor():
    """Initialize the memory monitor with configuration from environment variables."""
    global memory_monitor
    try:
        memory_threshold = float(os.environ.get("MEMORY_THRESHOLD", "80.0"))
        critical_threshold = float(os.environ.get("CRITICAL_MEMORY_THRESHOLD", "90.0"))
        check_interval = float(os.environ.get("MEMORY_CHECK_INTERVAL", "5.0"))
        enable_monitoring = os.environ.get("ENABLE_MEMORY_MONITORING", "true").lower() == "true"
        adaptive_thresholds = os.environ.get("ADAPTIVE_MEMORY_THRESHOLDS", "true").lower() == "true"
        memory_monitor = MemoryMonitor(
            memory_threshold=memory_threshold,
            critical_threshold=critical_threshold,
            check_interval=check_interval,
            enable_monitoring=enable_monitoring,
            adaptive_thresholds=adaptive_thresholds
        )
        logger.info(
            f"Memory monitor initialized with threshold={memory_threshold}%, "
            f"critical={critical_threshold}%, adaptive={adaptive_thresholds}"
        )
    except Exception as e:
        logger.error(f"Error initializing memory monitor: {str(e)}")
        memory_monitor = MemoryMonitor()


# Initialize the memory monitor when the module is imported
init_memory_monitor()
