"""
Memory management utilities for document processing with enhanced support for batch operations.

This module provides functions for monitoring and optimizing memory usage during document processing,
ensuring efficient resource utilization and preventing memory-related vulnerabilities with adaptive thresholds
based on system resources. It also includes specialized helpers for batch document processing.
"""

import asyncio
import gc
import logging
import os
import threading
import time
from functools import wraps
from typing import Optional, Dict, Any, TypeVar, Tuple

import psutil

# Import enhanced synchronization utilities
from backend.app.utils.system_utils.synchronization_utils import TimeoutLock, LockPriority

# Configure logger
logger = logging.getLogger(__name__)

# Generic type variable for functions
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

    This class uses a lazy-initialized TimeoutLock for complex operations and atomic operations for frequent
    stat updates. It also features adaptive thresholds for both regular and batch document processing.
    """
    def __init__(
            self,
            memory_threshold: float = 80.0,    # 80% memory threshold
            critical_threshold: float = 90.0,    # 90% critical threshold
            check_interval: float = 5.0,         # 5 seconds between checks
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
        self._lock_instance = None
        self._stop_monitor = threading.Event()
        # _lock is no longer created here; it is lazy-initialized (see property below)
        self._last_gc_time = 0
        self._gc_interval = 60  # Minimum seconds between full garbage collections

        # Memory statistics using atomic operations for frequent updates
        self.memory_stats = MemoryStats()

        # Batch processing specific settings
        self.batch_memory_threshold = 70.0  # Lower threshold for batch operations
        self.batch_max_memory_factor = 0.8    # Maximum memory factor for batch operations

        # Initialize available memory stats
        self._update_available_memory()

        # Adapt thresholds based on system resources if enabled
        if self.adaptive_thresholds:
            self._adjust_thresholds_based_on_system()

        # Start background monitoring if enabled
        if self.enable_monitoring:
            self.start_monitoring()

    @property
    def _lock(self) -> TimeoutLock:
        """
        Lazily initialize and return the TimeoutLock.
        This ensures that the lock is not instantiated during object construction.
        """
        if self._lock_instance is None:
            self._lock_instance = TimeoutLock("memory_monitor_lock", priority=LockPriority.MEDIUM,
                                              timeout=5.0, reentrant=True)
        return self._lock_instance

    def _update_available_memory(self) -> None:
        """
        Update available memory statistics from the system.
        """
        try:
            system_memory = psutil.virtual_memory()
            # Update available memory in MB atomically.
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
                        f"Adjusted thresholds: memory={self.memory_threshold:.1f}%, "
                        f"critical={self.critical_threshold:.1f}%, batch={self.batch_memory_threshold:.1f}%, "
                        f"total={total_memory_gb:.1f}GB, available={available_memory_gb:.1f}GB"
                    )
            except TimeoutError:
                logger.warning("Timeout acquiring lock to adjust thresholds - will retry later")

        except Exception as e:
            logger.error(f"Error adjusting thresholds: {str(e)}")
            try:
                with self._lock.acquire_timeout(timeout=1.0):
                    self.memory_threshold = self.base_memory_threshold
                    self.critical_threshold = self.base_critical_threshold
                    self.batch_memory_threshold = max(50.0, self.base_memory_threshold - 10)
            except TimeoutError:
                logger.warning("Timeout acquiring lock during fallback threshold adjustment")

    def start_monitoring(self) -> None:
        """
        Start the background memory monitoring thread.
        """
        if self._monitor_thread is not None and self._monitor_thread.is_alive():
            return

        self._stop_monitor.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_memory, daemon=True)
        self._monitor_thread.start()
        logger.info("Memory monitoring started")

    def stop_monitoring(self) -> None:
        """
        Stop the background memory monitoring thread.
        """
        if self._monitor_thread is None or not self._monitor_thread.is_alive():
            return

        self._stop_monitor.set()
        self._monitor_thread.join(timeout=2.0)
        logger.info("Memory monitoring stopped")

    def _update_memory_stats(self, current_usage: float) -> None:
        """
        Update memory statistics (usage, peak, average) atomically.

        This helper encapsulates the logic for updating the stats and reduces the
        cognitive complexity of the monitoring loop.
        """
        try:
            self._update_available_memory()
            self.memory_stats.current_usage.set(current_usage)
            self.memory_stats.checks_count.increment(1)
            self.memory_stats.last_check_time.set(time.time())
            if current_usage > self.memory_stats.peak_usage.get():
                self.memory_stats.peak_usage.set(current_usage)
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
            logger.error(f"Error updating memory stats: {str(e)}")

    def _monitor_memory(self) -> None:
        """
        Background thread: periodically check memory usage and trigger cleanup if needed.

        Refactored to delegate memory stat updates to a helper method, reducing cognitive complexity.
        """
        adaptive_counter = 0

        while not self._stop_monitor.is_set():
            current_usage = self.get_memory_usage()
            self._update_memory_stats(current_usage)

            adaptive_counter += 1
            if self.adaptive_thresholds and adaptive_counter >= 60:
                self._adjust_thresholds_based_on_system()
                adaptive_counter = 0

            # Trigger cleanup if thresholds are exceeded
            if current_usage >= self.critical_threshold:
                self._emergency_cleanup()
            elif current_usage >= self.memory_threshold:
                self._perform_cleanup()

            self._stop_monitor.wait(self.check_interval)

    @staticmethod
    def get_memory_usage() -> float:
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

    def _perform_cleanup(self) -> None:
        """
        Perform a regular cleanup when memory usage exceeds the set threshold.
        """
        current_time = time.time()
        current_usage = self.memory_stats.current_usage.get()
        logger.warning(f"Memory usage ({current_usage:.1f}%) exceeded threshold {self.memory_threshold}%. Running cleanup...")

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
        logger.error(f"CRITICAL: Memory usage ({current_usage:.1f}%) exceeded critical threshold {self.critical_threshold}%!")
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
        logger.warning(f"Emergency cleanup: freed {freed_percent:.1f}% memory. New usage: {new_usage:.1f}%")

    @staticmethod
    def _clear_application_caches() -> None:
        """
        Clear application-specific caches to free up memory.
        """
        try:
            try:
                from backend.app.utils.security.caching_middleware import invalidate_cache
                invalidate_cache()
                logger.info("Response cache cleared")
            except (ImportError, AttributeError):
                pass
        except Exception as e:
            logger.error(f"Error clearing caches: {str(e)}")

    @staticmethod
    def _free_additional_memory() -> None:
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
            logger.error(f"Error freeing additional memory: {str(e)}")


# Global memory monitor instance with adaptive thresholds
memory_monitor = MemoryMonitor(adaptive_thresholds=True)


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


_gc_stats = {}
_gc_lock = threading.RLock()

def init_gc_stats(func_name: str) -> None:
    """Ensure that GC statistics for a function are initialized."""
    with _gc_lock:
        if func_name not in _gc_stats:
            _gc_stats[func_name] = {
                'last_gc_time': 0,
                'last_gc_effectiveness': 0,
                'total_calls': 0,
                'gc_calls': 0,
                'memory_increases': [],
            }

def _default_threshold(initial_memory: float, available_memory_mb: float) -> int:
    """
    Determine the default threshold based on current memory usage and available memory.
    """
    if initial_memory < 30:
        return 30 if available_memory_mb > 1000 else 15
    elif initial_memory < 60:
        return 20 if available_memory_mb > 500 else 10
    else:
        return 10 if available_memory_mb > 300 else 5

def calc_adaptive_threshold(func_name: str, provided_threshold: Optional[int]) -> Tuple[int, float]:
    """
    Calculate the adaptive threshold and return it along with the initial memory usage.
    """
    initial_memory = memory_monitor.get_memory_usage()
    if provided_threshold is not None:
        return provided_threshold, initial_memory
    available_memory_mb = memory_monitor.memory_stats.available_memory_mb.get()
    with _gc_lock:
        stats = _gc_stats[func_name]
        mem_increases = stats.get('memory_increases', [])
        avg_increase = sum(mem_increases) / len(mem_increases) if mem_increases else 0
    threshold = max(5, min(100, avg_increase * 1.5)) if avg_increase > 0 else _default_threshold(initial_memory, available_memory_mb)
    return threshold, initial_memory

def should_run_gc(initial_memory: float, min_interval: float, func_name: str) -> Tuple[bool, int]:
    """
    Decide whether to run garbage collection before executing the function.
    Returns (run_gc, gc_generation).
    """
    current_time = time.time()
    with _gc_lock:
        stats = _gc_stats[func_name]
        time_since_gc = current_time - stats['last_gc_time']
        effectiveness = stats['last_gc_effectiveness']
    if initial_memory > 90:
        return True, 2
    elif initial_memory > 70 and time_since_gc > min_interval / 2:
        return True, 2
    elif initial_memory > 50 and time_since_gc > min_interval and effectiveness > 5:
        return True, 1
    elif initial_memory > 30 and time_since_gc > min_interval * 2 and effectiveness > 10:
        return True, 0
    return False, 0

def run_gc(gc_gen: int, func_name: str) -> None:
    """
    Run garbage collection for the specified generation and update GC stats.
    """
    gc.collect(generation=gc_gen)
    with _gc_lock:
        _gc_stats[func_name]['last_gc_time'] = time.time()
        _gc_stats[func_name]['gc_calls'] += 1
    logger.debug(f"[MEMORY] Pre-function GC(gen={gc_gen}) for {func_name}")

def post_function_cleanup(func_name: str, adaptive_threshold: int, initial_memory: float) -> None:
    """
    Perform post-function memory cleanup and log GC effectiveness.
    """
    final_memory = memory_monitor.get_memory_usage()
    memory_diff = final_memory - initial_memory
    with _gc_lock:
        stats = _gc_stats[func_name]
        stats['memory_increases'].append(memory_diff)
        if len(stats['memory_increases']) > 10:
            stats['memory_increases'].pop(0)
    system_memory = psutil.virtual_memory()
    threshold_percent = (adaptive_threshold * 1024 * 1024 / system_memory.total) * 100.0
    if memory_diff > threshold_percent or final_memory > 80:
        logger.info(f"Function {func_name} increased memory by {memory_diff:.1f}%. Running cleanup with adaptive threshold {adaptive_threshold}MB")
        if final_memory > 90:
            gc.collect(generation=2)
            logger.debug(f"[MEMORY] Post-function full GC for {func_name} - critical memory usage {final_memory:.1f}%")
        elif final_memory > 70 or memory_diff > threshold_percent * 2:
            gc.collect(generation=1)
            logger.debug(f"[MEMORY] Post-function partial GC for {func_name} - high memory usage {final_memory:.1f}%")
        else:
            gc.collect(generation=0)
            logger.debug(f"[MEMORY] Post-function light GC for {func_name} - memory usage {final_memory:.1f}%")
        post_gc_memory = memory_monitor.get_memory_usage()
        gc_effect = final_memory - post_gc_memory
        with _gc_lock:
            stats['last_gc_time'] = time.time()
            stats['last_gc_effectiveness'] = gc_effect
            stats['gc_calls'] += 1
        if gc_effect > 0:
            logger.info(f"Garbage collection freed {gc_effect:.1f}% memory")
        else:
            logger.info(f"Garbage collection had minimal effect ({gc_effect:.1f}%)")

def pre_exec(func_name: str, provided_threshold: Optional[int], min_interval: float) -> Tuple[int, float]:
    """
    Perform pre-execution memory management: update call count, compute adaptive threshold
    and initial memory, log threshold, and run GC if needed.
    """
    with _gc_lock:
        _gc_stats.setdefault(func_name, {
            'total_calls': 0,
            'last_gc_time': 0,
            'last_gc_effectiveness': 0,
            'gc_calls': 0,
            'memory_increases': [],
        })
        _gc_stats[func_name]['total_calls'] += 1
    adaptive_threshold, initial_memory = calc_adaptive_threshold(func_name, provided_threshold)
    logger.debug(f"[MEMORY] Running {func_name} with adaptive threshold {adaptive_threshold}MB")
    run_gc_flag, gc_gen = should_run_gc(initial_memory, min_interval, func_name)
    if run_gc_flag:
        run_gc(gc_gen, func_name)
    return adaptive_threshold, initial_memory

def memory_optimized(threshold_mb: Optional[int] = None, min_gc_interval: float = 10.0):
    """
    Decorator to optimize memory usage for functions processing large data.

    This decorator monitors memory usage before and after the wrapped function and
    triggers garbage collection if memory usage exceeds an adaptive threshold.
    """
    def decorator(func):
        func_name = func.__name__
        init_gc_stats(func_name)

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            adaptive_threshold, initial_memory = pre_exec(func_name, threshold_mb, min_gc_interval)
            try:
                return await func(*args, **kwargs)
            finally:
                post_function_cleanup(func_name, adaptive_threshold, initial_memory)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            adaptive_threshold, initial_memory = pre_exec(func_name, threshold_mb, min_gc_interval)
            try:
                return func(*args, **kwargs)
            finally:
                post_function_cleanup(func_name, adaptive_threshold, initial_memory)

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator

# Initialize the memory monitor when the module is imported
init_memory_monitor()