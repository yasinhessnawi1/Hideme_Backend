"""
Memory management utilities for document processing with enhanced support for batch operations.

This module provides functions for monitoring and optimizing memory usage during document processing operations,
ensuring efficient resource utilization and preventing memory-related vulnerabilities with adaptive thresholds
based on system resources. It now includes specialized helpers for batch document processing.
"""

import asyncio
import gc
import logging
import os
import threading
import time
from functools import wraps
from typing import Optional, Dict, Any, Callable, List, TypeVar, Awaitable, Tuple

import psutil

# Import enhanced synchronization utilities
from backend.app.utils.synchronization_utils import (
    TimeoutLock, LockPriority
)

# Configure logger
logger = logging.getLogger(__name__)

# Type variable for generic functions
T = TypeVar('T')


# --- Atomic helper classes for stat updates ---
class AtomicCounter:
    def __init__(self, initial: int = 0):
        self.value = initial
        self._lock = threading.Lock()

    def increment(self, amount: int = 1) -> int:
        with self._lock:
            self.value += amount
            return self.value

    def get(self) -> int:
        with self._lock:
            return self.value

    def set(self, new_value: int) -> None:
        with self._lock:
            self.value = new_value


class AtomicFloat:
    def __init__(self, initial: float = 0.0):
        self.value = initial
        self._lock = threading.Lock()

    def add(self, amount: float) -> float:
        with self._lock:
            self.value += amount
            return self.value

    def get(self) -> float:
        with self._lock:
            return self.value

    def set(self, new_value: float) -> None:
        with self._lock:
            self.value = new_value


class MemoryStats:
    def __init__(self):
        self.peak_usage = AtomicFloat(0.0)
        self.average_usage = AtomicFloat(0.0)
        self.checks_count = AtomicCounter(0)
        self.emergency_cleanups = AtomicCounter(0)
        self.last_check_time = AtomicFloat(0.0)
        self.current_usage = AtomicFloat(0.0)
        self.available_memory_mb = AtomicFloat(0.0)
        self.system_threshold_adjustments = AtomicCounter(0)
        self.batch_operations = AtomicCounter(0)
        self.batch_peak_memory = AtomicFloat(0.0)
# --- End of atomic helper classes ---


class MemoryMonitor:
    """
    Memory usage monitoring and management with enhanced thread safety and batch processing support.

    Uses a TimeoutLock for complex operations and atomic operations for frequent stat updates.
    Now includes specialized settings and helpers for batch document processing.
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

        # Enhanced TimeoutLock for complex operations
        self._lock = TimeoutLock("memory_monitor_lock", priority=LockPriority.MEDIUM,
                                  timeout=5.0, reentrant=True)

        self._last_gc_time = 0
        self._gc_interval = 60  # Minimum seconds between full garbage collections

        # Memory statistics using atomic operations for frequent updates
        self.memory_stats = MemoryStats()

        # Batch processing specific settings
        self.batch_memory_threshold = 70.0  # Lower threshold for batch operations
        self.batch_max_memory_factor = 0.8  # Maximum memory factor for batch operations

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
            # Update available memory atomically without acquiring the global lock
            self.memory_stats.available_memory_mb.set(system_memory.available / (1024 * 1024))
        except Exception as e:
            logger.error(f"Error updating available memory: {str(e)}")
            self.memory_stats.available_memory_mb.set(0)

    def _adjust_thresholds_based_on_system(self) -> None:
        """
        Adaptively adjust memory thresholds based on system resources.
        """
        try:
            system_memory = psutil.virtual_memory()
            total_memory_gb = system_memory.total / (1024 * 1024 * 1024)
            available_memory_gb = system_memory.available / (1024 * 1024 * 1024)
            usage_percent = system_memory.percent

            new_memory_threshold = self.memory_threshold
            new_critical_threshold = self.critical_threshold

            if total_memory_gb < 4:  # Low memory system (<4GB)
                new_memory_threshold = max(60.0, self.base_memory_threshold - 20)
                new_critical_threshold = max(75.0, self.base_critical_threshold - 15)
            elif total_memory_gb < 8:  # Medium memory system (4-8GB)
                new_memory_threshold = max(70.0, self.base_memory_threshold - 10)
                new_critical_threshold = max(85.0, self.base_critical_threshold - 5)
            elif total_memory_gb > 16:  # High memory system (>16GB)
                new_memory_threshold = min(85.0, self.base_memory_threshold + 5)
                new_critical_threshold = min(95.0, self.base_critical_threshold + 5)

            if usage_percent > 70:
                new_memory_threshold = max(60.0, new_memory_threshold - 10)
                new_critical_threshold = max(75.0, new_critical_threshold - 10)

            # Also adjust batch processing thresholds
            self.batch_memory_threshold = max(50.0, new_memory_threshold - 10)

            try:
                with self._lock.acquire_timeout(timeout=2.0):
                    self.memory_threshold = new_memory_threshold
                    self.critical_threshold = new_critical_threshold
                    self.memory_stats.system_threshold_adjustments.increment(1)
                    logger.info(
                        f"Adjusted memory thresholds: memory_threshold={self.memory_threshold:.1f}%, "
                        f"critical_threshold={self.critical_threshold:.1f}%, "
                        f"batch_threshold={self.batch_memory_threshold:.1f}%, "
                        f"total_memory={total_memory_gb:.1f}GB, "
                        f"available_memory={available_memory_gb:.1f}GB"
                    )
            except TimeoutError:
                logger.warning("Timeout acquiring lock to adjust thresholds - will retry later")

        except Exception as e:
            logger.error(f"Error adjusting thresholds: {str(e)}")
            with self._lock.acquire_timeout(timeout=1.0):
                self.memory_threshold = self.base_memory_threshold
                self.critical_threshold = self.base_critical_threshold
                self.batch_memory_threshold = max(50.0, self.base_memory_threshold - 10)

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
            current_usage = self.get_memory_usage()
            try:
                self._update_available_memory()

                # Atomically update simple counters and flags
                self.memory_stats.current_usage.set(current_usage)
                self.memory_stats.checks_count.increment(1)
                self.memory_stats.last_check_time.set(time.time())
                if current_usage > self.memory_stats.peak_usage.get():
                    self.memory_stats.peak_usage.set(current_usage)

                # Update average usage under lock protection (for read-modify-write cycle)
                try:
                    with self._lock.acquire_timeout(timeout=1.0):
                        cnt = self.memory_stats.checks_count.get()
                        if cnt > 1:
                            prev_avg = self.memory_stats.average_usage.get()
                            new_avg = (prev_avg * (cnt - 1) + current_usage) / cnt
                            self.memory_stats.average_usage.set(new_avg)
                        else:
                            self.memory_stats.average_usage.set(current_usage)
                except TimeoutError:
                    logger.warning("Timeout acquiring lock to update average memory usage")
            except Exception as e:
                logger.error(f"Error in memory monitor: {str(e)}")

            adaptive_counter += 1
            if self.adaptive_thresholds and adaptive_counter >= 60:
                self._adjust_thresholds_based_on_system()
                adaptive_counter = 0

            # Check if cleanup is needed
            if current_usage >= self.critical_threshold:
                self._emergency_cleanup()
            elif current_usage >= self.memory_threshold:
                self._perform_cleanup()

            self._stop_monitor.wait(self.check_interval)

    def get_memory_usage(self) -> float:
        """
        Get the current memory usage as a percentage of total system memory.
        """
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        system_memory = psutil.virtual_memory()
        usage_percent = (memory_info.rss / system_memory.total) * 100.0
        return usage_percent

    def get_memory_stats(self) -> Dict[str, Any]:
        """
        Retrieve a snapshot of the current memory statistics.
        """
        return {
            "peak_usage": self.memory_stats.peak_usage.get(),
            "average_usage": self.memory_stats.average_usage.get(),
            "checks_count": self.memory_stats.checks_count.get(),
            "emergency_cleanups": self.memory_stats.emergency_cleanups.get(),
            "last_check_time": self.memory_stats.last_check_time.get(),
            "current_usage": self.memory_stats.current_usage.get(),
            "available_memory_mb": self.memory_stats.available_memory_mb.get(),
            "system_threshold_adjustments": self.memory_stats.system_threshold_adjustments.get(),
            "batch_operations": self.memory_stats.batch_operations.get(),
            "batch_peak_memory": self.memory_stats.batch_peak_memory.get()
        }

    def should_use_memory_buffer(self, size_bytes: int) -> bool:
        """
        Decide whether to use an in-memory buffer based on the size and current memory pressure.
        """
        current_usage = self.get_memory_usage()

        try:
            with self._lock.acquire_timeout(timeout=0.5):
                available_memory = self.memory_stats.available_memory_mb.get() * 1024 * 1024
        except TimeoutError:
            system_memory = psutil.virtual_memory()
            available_memory = system_memory.available * 0.5

        if current_usage >= self.critical_threshold:
            max_buffer_size = min(1024 * 1024, int(available_memory * 0.01))
        elif current_usage >= self.memory_threshold:
            max_buffer_size = min(5 * 1024 * 1024, int(available_memory * 0.05))
        else:
            max_buffer_size = min(25 * 1024 * 1024, int(available_memory * 0.1))

        return size_bytes <= max_buffer_size

    def calculate_optimal_batch_size(self, file_count: int, total_bytes: int = 0) -> int:
        """
        Calculate the optimal batch size for document processing based on current memory conditions.

        This method is optimized for centralized batch document processing to ensure
        efficient resource utilization without causing memory pressure.

        Args:
            file_count: Number of files to process
            total_bytes: Total size of all files in bytes

        Returns:
            Optimal number of files to process in parallel
        """
        # Get current memory statistics
        current_usage = self.get_memory_usage()
        available_memory_mb = self.memory_stats.available_memory_mb.get()

        # Calculate base worker count based on CPU cores
        cpu_count = os.cpu_count() or 4
        base_workers = max(1, min(cpu_count - 1, 8))  # Leave at least one core free

        # Adjust based on memory pressure
        if current_usage >= self.critical_threshold:
            # Critical memory pressure - use minimal workers
            max_workers = 1
        elif current_usage >= self.memory_threshold:
            # High memory pressure - reduce workers significantly
            max_workers = max(1, base_workers // 3)
        elif current_usage >= self.batch_memory_threshold:
            # Moderate memory pressure - reduce workers moderately
            max_workers = max(1, base_workers // 2)
        else:
            # Low memory pressure - use optimal worker count
            max_workers = base_workers

        # Further adjust based on file size if provided
        if total_bytes > 0:
            avg_bytes_per_file = total_bytes / max(file_count, 1)

            # Calculate memory required per worker
            memory_per_worker_mb = (avg_bytes_per_file * 3) / (1024 * 1024)  # 3x multiplier for processing overhead

            # Calculate maximum number of workers based on available memory
            memory_based_workers = int(available_memory_mb * self.batch_max_memory_factor / max(memory_per_worker_mb, 1))

            # Use the more conservative estimate
            max_workers = min(max_workers, max(1, memory_based_workers))

        # Cap at file count
        max_workers = min(max_workers, file_count)

        # Update statistics
        self.memory_stats.batch_operations.increment(1)

        logger.info(f"Calculated optimal batch size: {max_workers} workers for {file_count} files "
                   f"(memory usage: {current_usage:.1f}%, available: {available_memory_mb:.1f}MB)")

        return max_workers

    def record_batch_memory_usage(self, peak_usage: float) -> None:
        """
        Record memory usage statistics from a batch processing operation.

        Args:
            peak_usage: Peak memory usage percentage during batch processing
        """
        # Update batch peak memory if this was higher
        current_peak = self.memory_stats.batch_peak_memory.get()
        if peak_usage > current_peak:
            self.memory_stats.batch_peak_memory.set(peak_usage)

        logger.info(f"Recorded batch operation peak memory usage: {peak_usage:.1f}%")

    def _perform_cleanup(self) -> None:
        """
        Perform a regular cleanup when memory usage exceeds the threshold.
        """
        current_time = time.time()
        current_usage = self.memory_stats.current_usage.get()

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
        new_usage = self.get_memory_usage()
        freed = current_usage - new_usage
        logger.info(f"Cleanup complete, freed {freed:.1f}% memory")

    def _emergency_cleanup(self) -> None:
        """
        Execute an emergency cleanup when critical memory thresholds are exceeded.
        """
        current_usage = self.memory_stats.current_usage.get()
        logger.error(
            f"CRITICAL: Memory usage ({current_usage:.1f}%) exceeded critical threshold {self.critical_threshold}%!"
        )
        try:
            with self._lock.acquire_timeout(timeout=1.0):
                self.memory_stats.emergency_cleanups.increment(1)
        except TimeoutError:
            logger.warning("Timeout acquiring lock to update emergency cleanup count")

        gc.collect(generation=2)
        self._clear_application_caches()
        self._free_additional_memory()
        new_usage = self.get_memory_usage()
        freed_percent = current_usage - new_usage
        logger.warning(
            f"Emergency cleanup completed: freed {freed_percent:.1f}% memory. New usage: {new_usage:.1f}%"
        )

    def _clear_application_caches(self) -> None:
        """Clear application-specific caches to free up memory."""
        try:
            try:
                from backend.app.utils.security.caching_middleware import invalidate_cache
                invalidate_cache()
                logger.info("Response cache cleared")
            except (ImportError, AttributeError):
                pass
        except Exception as e:
            logger.error(f"Error clearing application caches: {str(e)}")

    def _free_additional_memory(self) -> None:
        """
        Attempt to free extra memory using aggressive strategies.
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
    """
    _gc_stats = {}
    _gc_lock = threading.RLock()

    def decorator(func):
        func_name = func.__name__

        with _gc_lock:
            if func_name not in _gc_stats:
                _gc_stats[func_name] = {
                    'last_gc_time': 0,
                    'last_gc_effectiveness': 0,
                    'total_calls': 0,
                    'gc_calls': 0,
                    'memory_increases': [],
                }

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Record function call
            with _gc_lock:
                _gc_stats[func_name]['total_calls'] += 1

            # Check initial memory state
            initial_memory = memory_monitor.get_memory_usage()
            adaptive_threshold = threshold_mb

            # Calculate adaptive threshold if not provided
            if adaptive_threshold is None:
                available_memory_mb = memory_monitor.memory_stats.available_memory_mb.get()
                with _gc_lock:
                    stats = _gc_stats[func_name]
                    avg_memory_increase = (sum(stats['memory_increases']) / len(stats['memory_increases'])
                                           if stats['memory_increases'] else 0)

                # Adjust threshold based on historical memory usage
                if avg_memory_increase > 0:
                    adaptive_threshold = max(5, min(100, avg_memory_increase * 1.5))
                else:
                    # Default thresholds based on current memory pressure
                    if initial_memory < 30:
                        adaptive_threshold = 30 if available_memory_mb > 1000 else 15
                    elif initial_memory < 60:
                        adaptive_threshold = 20 if available_memory_mb > 500 else 10
                    else:
                        adaptive_threshold = 10 if available_memory_mb > 300 else 5

            # Log memory optimization information
            logger.debug(f"[MEMORY] Running {func_name} with adaptive threshold {adaptive_threshold}MB")

            # Check if garbage collection is needed before function execution
            current_time = time.time()
            run_gc = False
            gc_generation = 0

            with _gc_lock:
                stats = _gc_stats[func_name]
                time_since_last_gc = current_time - stats['last_gc_time']

                # Determine GC strategy based on current memory pressure
                if initial_memory > 90:
                    run_gc = True
                    gc_generation = 2
                elif initial_memory > 70:
                    if time_since_last_gc > min_gc_interval / 2:
                        run_gc = True
                        gc_generation = 2
                elif initial_memory > 50:
                    if time_since_last_gc > min_gc_interval and stats['last_gc_effectiveness'] > 5:
                        run_gc = True
                        gc_generation = 1
                elif initial_memory > 30:
                    if time_since_last_gc > min_gc_interval * 2 and stats['last_gc_effectiveness'] > 10:
                        run_gc = True
                        gc_generation = 0

            # Run garbage collection if needed
            if run_gc:
                gc.collect(generation=gc_generation)
                with _gc_lock:
                    _gc_stats[func_name]['last_gc_time'] = time.time()
                    _gc_stats[func_name]['gc_calls'] += 1
                logger.debug(
                    f"[MEMORY] Pre-function GC(gen={gc_generation}) for {func_name} - memory usage {initial_memory:.1f}%"
                )

            try:
                # Execute the function
                result = await func(*args, **kwargs)
                return result
            finally:
                # Perform post-function memory management
                final_memory = memory_monitor.get_memory_usage()
                memory_diff = final_memory - initial_memory

                # Update memory usage statistics
                with _gc_lock:
                    _gc_stats[func_name]['memory_increases'].append(memory_diff)
                    if len(_gc_stats[func_name]['memory_increases']) > 10:
                        _gc_stats[func_name]['memory_increases'].pop(0)

                # Calculate memory threshold for cleanup
                process = psutil.Process(os.getpid())
                system_memory = psutil.virtual_memory()
                threshold_percent = (adaptive_threshold * 1024 * 1024 / system_memory.total) * 100.0

                # Run cleanup if needed
                if memory_diff > threshold_percent or final_memory > 80:
                    logger.info(
                        f"Function {func_name} increased memory by {memory_diff:.1f}%. Running cleanup with adaptive threshold {adaptive_threshold}MB"
                    )

                    # Choose GC strategy based on memory pressure
                    if final_memory > 90:
                        gc.collect(generation=2)
                        logger.debug(
                            f"[MEMORY] Post-function full GC for {func_name} - critical memory usage {final_memory:.1f}%"
                        )
                    elif final_memory > 70 or memory_diff > threshold_percent * 2:
                        gc.collect(generation=1)
                        logger.debug(
                            f"[MEMORY] Post-function partial GC for {func_name} - high memory usage {final_memory:.1f}%"
                        )
                    else:
                        gc.collect(generation=0)
                        logger.debug(
                            f"[MEMORY] Post-function light GC for {func_name} - memory usage {final_memory:.1f}%"
                        )

                    # Record GC effectiveness
                    post_gc_memory = memory_monitor.get_memory_usage()
                    gc_effect = final_memory - post_gc_memory
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
            # Implementation for synchronous functions follows same pattern as async
            with _gc_lock:
                _gc_stats[func_name]['total_calls'] += 1

            initial_memory = memory_monitor.get_memory_usage()
            adaptive_threshold = threshold_mb

            if adaptive_threshold is None:
                available_memory_mb = memory_monitor.memory_stats.available_memory_mb.get()
                with _gc_lock:
                    stats = _gc_stats[func_name]
                    avg_memory_increase = (sum(stats['memory_increases']) / len(stats['memory_increases'])
                                           if stats['memory_increases'] else 0)
                if avg_memory_increase > 0:
                    adaptive_threshold = max(5, min(100, avg_memory_increase * 1.5))
                else:
                    if initial_memory < 30:
                        adaptive_threshold = 30 if available_memory_mb > 1000 else 15
                    elif initial_memory < 60:
                        adaptive_threshold = 20 if available_memory_mb > 500 else 10
                    else:
                        adaptive_threshold = 10 if available_memory_mb > 300 else 5

            logger.debug(f"[MEMORY] Running {func_name} with adaptive threshold {adaptive_threshold}MB")
            current_time = time.time()
            run_gc = False
            gc_generation = 0

            with _gc_lock:
                stats = _gc_stats[func_name]
                time_since_last_gc = current_time - stats['last_gc_time']
                if initial_memory > 90:
                    run_gc = True
                    gc_generation = 2
                elif initial_memory > 70:
                    if time_since_last_gc > min_gc_interval / 2:
                        run_gc = True
                        gc_generation = 2
                elif initial_memory > 50:
                    if time_since_last_gc > min_gc_interval and stats['last_gc_effectiveness'] > 5:
                        run_gc = True
                        gc_generation = 1
                elif initial_memory > 30:
                    if time_since_last_gc > min_gc_interval * 2 and stats['last_gc_effectiveness'] > 10:
                        run_gc = True
                        gc_generation = 0

            if run_gc:
                gc.collect(generation=gc_generation)
                with _gc_lock:
                    _gc_stats[func_name]['last_gc_time'] = time.time()
                    _gc_stats[func_name]['gc_calls'] += 1
                logger.debug(
                    f"[MEMORY] Pre-function GC(gen={gc_generation}) for {func_name} - memory usage {initial_memory:.1f}%"
                )
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                final_memory = memory_monitor.get_memory_usage()
                memory_diff = final_memory - initial_memory
                with _gc_lock:
                    _gc_stats[func_name]['memory_increases'].append(memory_diff)
                    if len(_gc_stats[func_name]['memory_increases']) > 10:
                        _gc_stats[func_name]['memory_increases'].pop(0)
                process = psutil.Process(os.getpid())
                system_memory = psutil.virtual_memory()
                threshold_percent = (adaptive_threshold * 1024 * 1024 / system_memory.total) * 100.0
                if memory_diff > threshold_percent or final_memory > 80:
                    logger.info(
                        f"Function {func_name} increased memory by {memory_diff:.1f}%. Running cleanup with adaptive threshold {adaptive_threshold}MB"
                    )
                    if final_memory > 90:
                        gc.collect(generation=2)
                        logger.debug(
                            f"[MEMORY] Post-function full GC for {func_name} - critical memory usage {final_memory:.1f}%"
                        )
                    elif final_memory > 70 or memory_diff > threshold_percent * 2:
                        gc.collect(generation=1)
                        logger.debug(
                            f"[MEMORY] Post-function partial GC for {func_name} - high memory usage {final_memory:.1f}%"
                        )
                    else:
                        gc.collect(generation=0)
                        logger.debug(
                            f"[MEMORY] Post-function light GC for {func_name} - memory usage {final_memory:.1f}%"
                        )
                    post_gc_memory = memory_monitor.get_memory_usage()
                    gc_effect = final_memory - post_gc_memory
                    with _gc_lock:
                        _gc_stats[func_name]['last_gc_time'] = time.time()
                        _gc_stats[func_name]['last_gc_effectiveness'] = gc_effect
                        _gc_stats[func_name]['gc_calls'] += 1
                    if gc_effect > 0:
                        logger.info(f"Garbage collection freed {gc_effect:.1f}% memory")
                    else:
                        logger.info(f"Garbage collection had minimal effect ({gc_effect:.1f}%)")

        # Choose appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


class MemoryOptimizedReader:
    """
    Memory-optimized file reader for large document processing.

    This class provides utilities for reading and processing large files in chunks to minimize memory usage,
    with adaptive buffer sizing based on system resources. Now supports batch processing optimization.
    """
    @staticmethod
    async def read_file_chunks(file_path: str, chunk_size: Optional[int] = None) -> bytes:
        file_size = os.path.getsize(file_path)
        if chunk_size is None:
            available_memory_mb = memory_monitor.memory_stats.available_memory_mb.get()
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
        file_size = os.path.getsize(file_path)
        if chunk_size is None:
            available_memory_mb = memory_monitor.memory_stats.available_memory_mb.get()
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
        if chunk_size is None:
            file_size = os.path.getsize(file_path)
            available_memory_mb = memory_monitor.memory_stats.available_memory_mb.get()
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

    @staticmethod
    async def batch_read_files(
            file_paths: List[str],
            max_workers: Optional[int] = None
    ) -> Dict[str, bytes]:
        """
        Read multiple files in parallel with memory optimization.

        Args:
            file_paths: List of file paths to read
            max_workers: Maximum number of parallel workers (None for auto)

        Returns:
            Dictionary mapping file paths to their contents
        """
        if not file_paths:
            return {}

        # Determine optimal number of workers
        if max_workers is None:
            max_workers = memory_monitor.calculate_optimal_batch_size(len(file_paths))

        # Create semaphore to limit concurrency
        semaphore = asyncio.Semaphore(max_workers)

        async def read_file(file_path: str) -> Tuple[str, bytes]:
            async with semaphore:
                try:
                    content = await MemoryOptimizedReader.read_file_chunks(file_path)
                    return file_path, content
                except Exception as e:
                    logger.error(f"Error reading file {file_path}: {str(e)}")
                    return file_path, b""

        # Create tasks for reading files
        tasks = [read_file(path) for path in file_paths]
        results = await asyncio.gather(*tasks)

        # Convert results to dictionary
        return {path: content for path, content in results if content}


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
