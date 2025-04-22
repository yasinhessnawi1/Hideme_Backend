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

from backend.app.utils.system_utils.synchronization_utils import TimeoutLock, LockPriority

# Configure logger for the module.
logger = logging.getLogger(__name__)

# Define a generic type variable for function wrappers.
T = TypeVar('T')


# --- Atomic helper classes for stat updates ---

class AtomicCounter:
    """
    Thread-safe atomic counter.

    This class provides atomic increment, get, and set operations on an integer value,
    using an internal lock for thread safety.
    """

    def __init__(self, initial: int = 0):
        # Initialize the counter with the provided initial value.
        self.value = initial
        # Create a lock for synchronization.
        self._lock = threading.Lock()

    def increment(self, amount: int = 1) -> int:
        """
        Atomically increment the counter by a specified amount.

        Args:
            amount (int): The value to add to the counter (default is 1).

        Returns:
            int: The new value of the counter after increment.
        """
        # Acquire the lock before updating the counter.
        with self._lock:
            # Increment the counter value.
            self.value += amount
            # Return the updated counter value.
            return self.value

    def get(self) -> int:
        """
        Retrieve the current counter value atomically.

        Returns:
            int: The current counter value.
        """
        # Acquire the lock to ensure thread-safe access.
        with self._lock:
            # Return the current value.
            return self.value

    def set(self, new_value: int) -> None:
        """
        Atomically set the counter to a new value.

        Args:
            new_value (int): The new value to set.
        """
        # Acquire the lock before updating the counter.
        with self._lock:
            # Set the counter to the new value.
            self.value = new_value


class AtomicFloat:
    """
    Thread-safe atomic float.

    This class provides atomic addition, get, and set operations on a float value,
    using an internal lock for thread safety.
    """

    def __init__(self, initial: float = 0.0):
        # Initialize the float value with the provided initial value.
        self.value = initial
        # Create a lock for synchronization.
        self._lock = threading.Lock()

    def add(self, amount: float) -> float:
        """
        Atomically add a specified amount to the float value.

        Args:
            amount (float): The value to add.

        Returns:
            float: The new float value after addition.
        """
        # Acquire the lock before updating the float value.
        with self._lock:
            # Add the specified amount to the float value.
            self.value += amount
            # Return the updated float value.
            return self.value

    def get(self) -> float:
        """
        Retrieve the current float value atomically.

        Returns:
            float: The current float value.
        """
        # Acquire the lock to access the float value safely.
        with self._lock:
            # Return the current float value.
            return self.value

    def set(self, new_value: float) -> None:
        """
        Atomically set the float value to a new value.

        Args:
            new_value (float): The new float value.
        """
        # Acquire the lock before updating the float value.
        with self._lock:
            # Set the float value to the new value.
            self.value = new_value


class MemoryStats:
    """
    Collection of memory usage statistics with atomic operations.

    This class encapsulates various memory statistics, such as peak usage, average usage,
    number of checks, emergency cleanup counts, and batch processing metrics using atomic helpers.
    """

    def __init__(self):
        # Initialize peak memory usage using an atomic float.
        self.peak_usage = AtomicFloat(0.0)
        # Initialize average memory usage using an atomic float.
        self.average_usage = AtomicFloat(0.0)
        # Initialize a counter for the number of memory checks.
        self.checks_count = AtomicCounter(0)
        # Initialize a counter for the number of emergency cleanups.
        self.emergency_cleanups = AtomicCounter(0)
        # Initialize last check time using an atomic float.
        self.last_check_time = AtomicFloat(0.0)
        # Initialize current memory usage using an atomic float.
        self.current_usage = AtomicFloat(0.0)
        # Initialize available memory in MB using an atomic float.
        self.available_memory_mb = AtomicFloat(0.0)
        # Initialize counter for system threshold adjustments.
        self.system_threshold_adjustments = AtomicCounter(0)
        # Initialize counter for batch operations.
        self.batch_operations = AtomicCounter(0)
        # Initialize batch peak memory usage using an atomic float.
        self.batch_peak_memory = AtomicFloat(0.0)


# --- End of atomic helper classes ---


class MemoryMonitor:
    """
    Memory usage monitoring and management with enhanced thread safety and batch processing support.

    This class monitors memory usage continuously using a background thread.
    It updates statistics using atomic operations and adjusts memory thresholds adaptively
    based on system resources. It also supports emergency and regular cleanup operations.
    """

    def __init__(
            self,
            memory_threshold: float = 80.0,  # Base memory usage threshold (in percentage).
            critical_threshold: float = 90.0,  # Critical memory usage threshold (in percentage).
            check_interval: float = 5.0,  # Interval in seconds between memory checks.
            enable_monitoring: bool = True,  # Flag to enable background monitoring.
            adaptive_thresholds: bool = True  # Flag to adjust thresholds adaptively.
    ):
        """
        Initialize the memory monitor with configuration parameters.

        Args:
            memory_threshold (float): Base memory usage threshold percentage.
            critical_threshold (float): Critical memory usage threshold percentage.
            check_interval (float): Time interval in seconds between memory checks.
            enable_monitoring (bool): Whether to start monitoring immediately.
            adaptive_thresholds (bool): Whether to adapt thresholds based on system resources.
        """
        # Set the base memory threshold.
        self.base_memory_threshold = memory_threshold
        # Set the base critical threshold.
        self.base_critical_threshold = critical_threshold
        # Initialize current memory threshold with the base value.
        self.memory_threshold = memory_threshold
        # Initialize current critical threshold with the base value.
        self.critical_threshold = critical_threshold
        # Set the interval between memory checks.
        self.check_interval = check_interval
        # Enable or disable monitoring based on configuration.
        self.enable_monitoring = enable_monitoring
        # Enable or disable adaptive threshold adjustments.
        self.adaptive_thresholds = adaptive_thresholds
        # Initialize the background monitor thread as None.
        self._monitor_thread = None
        # Lazy-initialized lock instance for critical operations.
        self._lock_instance = None
        # Create an event flag to signal stopping of the monitor.
        self._stop_monitor = threading.Event()
        # Record the time of the last full garbage collection.
        self._last_gc_time = 0
        # Define the minimum interval (in seconds) between full garbage collections.
        self._gc_interval = 60

        # Initialize memory statistics using the MemoryStats class.
        self.memory_stats = MemoryStats()

        # Set thresholds specific for batch processing.
        self.batch_memory_threshold = 70.0  # Lower threshold for batch operations.
        self.batch_max_memory_factor = 0.8  # Maximum memory factor allowed for batch operations.

        # Update available system memory into memory stats.
        self._update_available_memory()

        # Adjust thresholds based on system resources if adaptive thresholds are enabled.
        if self.adaptive_thresholds:
            self._adjust_thresholds_based_on_system()

        # Start the background monitoring thread if monitoring is enabled.
        if self.enable_monitoring:
            self.start_monitoring()

    @property
    def _lock(self) -> TimeoutLock:
        """
        Lazily initialize and return the TimeoutLock.

        Returns:
            TimeoutLock: A lock instance used for synchronizing complex operations.
        """
        # Check if the lock instance is not initialized.
        if self._lock_instance is None:
            # Create a TimeoutLock with a specific name, priority, timeout, and reentrant flag.
            self._lock_instance = TimeoutLock("memory_monitor_lock", priority=LockPriority.MEDIUM, timeout=5.0,
                                              reentrant=True)
        # Return the lock instance.
        return self._lock_instance

    def _update_available_memory(self) -> None:
        """
        Update available memory statistics from the system.

        This method retrieves system memory details and updates the available memory (in MB)
        in the atomic memory statistics.
        """
        try:
            # Retrieve virtual memory details using psutil.
            system_memory = psutil.virtual_memory()
            # Update available memory in MB by dividing bytes by (1024*1024).
            self.memory_stats.available_memory_mb.set(system_memory.available / (1024 * 1024))
        except Exception as e:
            # Log an error if updating available memory fails.
            logger.error(f"Error updating available memory: {str(e)}")
            # On failure, set available memory to 0.
            self.memory_stats.available_memory_mb.set(0)

    def _adjust_thresholds_based_on_system(self) -> None:
        """
        Adaptively adjust memory thresholds based on system resources.

        This method analyzes total and available system memory, usage percentage, and adjusts
        both regular and batch memory thresholds accordingly.
        """
        try:
            # Retrieve system memory details.
            system_memory = psutil.virtual_memory()
            # Calculate total memory in GB.
            total_memory_gb = system_memory.total / (1024 * 1024 * 1024)
            # Calculate available memory in GB.
            available_memory_gb = system_memory.available / (1024 * 1024 * 1024)
            # Get current memory usage percentage.
            usage_percent = system_memory.percent

            # Initialize new thresholds with current values.
            new_memory_threshold = self.memory_threshold
            new_critical_threshold = self.critical_threshold

            # Adjust thresholds for low memory systems (<4GB).
            if total_memory_gb < 4:
                new_memory_threshold = max(60.0, self.base_memory_threshold - 20)
                new_critical_threshold = max(75.0, self.base_critical_threshold - 15)
            # Adjust thresholds for medium memory systems (4-8GB).
            elif total_memory_gb < 8:
                new_memory_threshold = max(70.0, self.base_memory_threshold - 10)
                new_critical_threshold = max(85.0, self.base_critical_threshold - 5)
            # Adjust thresholds for high memory systems (>16GB).
            elif total_memory_gb > 16:
                new_memory_threshold = min(85.0, self.base_memory_threshold + 5)
                new_critical_threshold = min(95.0, self.base_critical_threshold + 5)

            # Further adjust thresholds based on current usage percentage.
            if usage_percent > 70:
                new_memory_threshold = max(60.0, new_memory_threshold - 10)
                new_critical_threshold = max(75.0, new_critical_threshold - 10)

            # Adjust batch processing threshold based on new memory threshold.
            self.batch_memory_threshold = max(50.0, new_memory_threshold - 10)

            # Acquire the lock with a timeout to update thresholds atomically.
            try:
                with self._lock.acquire_timeout(timeout=2.0):
                    # Set the memory thresholds to the new calculated values.
                    self.memory_threshold = new_memory_threshold
                    self.critical_threshold = new_critical_threshold
                    # Increment the system threshold adjustment counter.
                    self.memory_stats.system_threshold_adjustments.increment(1)
                    # Log the adjusted thresholds with system memory info.
                    logger.info(
                        f"Adjusted thresholds: memory={self.memory_threshold:.1f}%, "
                        f"critical={self.critical_threshold:.1f}%, batch={self.batch_memory_threshold:.1f}%, "
                        f"total={total_memory_gb:.1f}GB, available={available_memory_gb:.1f}GB"
                    )
            except TimeoutError:
                # Log a warning if unable to acquire the lock in time.
                logger.warning("Timeout acquiring lock to adjust thresholds - will retry later")

        except Exception as e:
            # Log an error if threshold adjustment fails.
            logger.error(f"Error adjusting thresholds: {str(e)}")
            # Fallback: Reset thresholds to their base values if lock can be acquired.
            try:
                with self._lock.acquire_timeout(timeout=1.0):
                    self.memory_threshold = self.base_memory_threshold
                    self.critical_threshold = self.base_critical_threshold
                    self.batch_memory_threshold = max(50.0, self.base_memory_threshold - 10)
            except TimeoutError:
                # Log a warning if even fallback lock acquisition fails.
                logger.warning("Timeout acquiring lock during fallback threshold adjustment")

    def start_monitoring(self) -> None:
        """
        Start the background memory monitoring thread.

        This method initializes and starts a daemon thread that periodically
        checks memory usage and triggers cleanup operations if needed.
        """
        # Check if the monitor thread is already running.
        if self._monitor_thread is not None and self._monitor_thread.is_alive():
            # If running, return immediately.
            return

        # Clear the stop event to ensure the thread runs.
        self._stop_monitor.clear()
        # Create the monitor thread targeting the _monitor_memory method.
        self._monitor_thread = threading.Thread(target=self._monitor_memory, daemon=True)
        # Start the thread.
        self._monitor_thread.start()
        # Log that monitoring has started.
        logger.info("Memory monitoring started")

    def stop_monitoring(self) -> None:
        """
        Stop the background memory monitoring thread.

        This method signals the monitoring thread to stop and waits for it to terminate.
        """
        # Check if the monitor thread is not running.
        if self._monitor_thread is None or not self._monitor_thread.is_alive():
            # Return if there is no active monitoring thread.
            return

        # Signal the thread to stop by setting the stop event.
        self._stop_monitor.set()
        # Wait for the thread to join with a timeout.
        self._monitor_thread.join(timeout=2.0)
        # Log that monitoring has been stopped.
        logger.info("Memory monitoring stopped")

    def _update_memory_stats(self, current_usage: float) -> None:
        """
        Update memory statistics (usage, peak, average) atomically.

        Args:
            current_usage (float): The current memory usage percentage.

        This helper updates available memory, current usage, check count, and computes average usage.
        """
        try:
            # Update available memory statistics.
            self._update_available_memory()
            # Set the current memory usage in the stats.
            self.memory_stats.current_usage.set(current_usage)
            # Increment the count of memory checks.
            self.memory_stats.checks_count.increment(1)
            # Update the last check time with the current timestamp.
            self.memory_stats.last_check_time.set(time.time())
            # Update peak usage if current usage is higher.
            if current_usage > self.memory_stats.peak_usage.get():
                self.memory_stats.peak_usage.set(current_usage)
            # Acquire lock to update average usage.
            try:
                with self._lock.acquire_timeout(timeout=1.0):
                    # Get the total number of memory checks.
                    cnt = self.memory_stats.checks_count.get()
                    # If more than one check has been done, update the average.
                    if cnt > 1:
                        # Calculate new average based on previous average and current usage.
                        prev_avg = self.memory_stats.average_usage.get()
                        new_avg = (prev_avg * (cnt - 1) + current_usage) / cnt
                        # Set the updated average usage.
                        self.memory_stats.average_usage.set(new_avg)
                    else:
                        # For the first check, set average equal to current usage.
                        self.memory_stats.average_usage.set(current_usage)
            except TimeoutError:
                # Log a warning if unable to acquire the lock for average update.
                logger.warning("Timeout acquiring lock to update average memory usage")
        except Exception as e:
            # Log an error if updating memory stats fails.
            logger.error(f"Error updating memory stats: {str(e)}")

    def _monitor_memory(self) -> None:
        """
        Background thread: periodically check memory usage and trigger cleanup if needed.

        This method runs in a continuous loop until signaled to stop. It updates memory stats,
        adjusts thresholds adaptively, and invokes cleanup routines if usage exceeds defined thresholds.
        """
        # Initialize a counter to determine when to adjust thresholds adaptively.
        adaptive_counter = 0

        # Loop continuously until the stop event is set.
        while not self._stop_monitor.is_set():
            # Get current memory usage as a percentage.
            current_usage = self.get_memory_usage()
            # Update memory statistics based on the current usage.
            self._update_memory_stats(current_usage)

            # Increment adaptive counter.
            adaptive_counter += 1
            # Every 60 iterations, adjust thresholds if adaptive mode is enabled.
            if self.adaptive_thresholds and adaptive_counter >= 60:
                self._adjust_thresholds_based_on_system()
                adaptive_counter = 0

            # If current usage exceeds the critical threshold, perform an emergency cleanup.
            if current_usage >= self.critical_threshold:
                self._emergency_cleanup()
            # Else if usage exceeds the regular memory threshold, perform a regular cleanup.
            elif current_usage >= self.memory_threshold:
                self._perform_cleanup()

            # Wait for the check interval or until stop event is set.
            self._stop_monitor.wait(self.check_interval)

    @staticmethod
    def get_memory_usage() -> float:
        """
        Get the current memory usage as a percentage of total system memory.

        Returns:
            float: The current memory usage percentage.
        """
        # Obtain the current process information.
        process = psutil.Process(os.getpid())
        # Get memory usage (RSS) of the current process.
        memory_info = process.memory_info()
        # Retrieve total system memory.
        system_memory = psutil.virtual_memory()
        # Calculate usage percentage based on current RSS and total system memory.
        usage_percent = (memory_info.rss / system_memory.total) * 100.0
        # Return the computed memory usage percentage.
        return usage_percent

    def get_memory_stats(self) -> Dict[str, Any]:
        """
        Retrieve a snapshot of the current memory statistics.

        Returns:
            Dict[str, Any]: A dictionary containing peak usage, average usage, counts, and other memory metrics.
        """
        # Construct and return a dictionary of current memory statistics using atomic get operations.
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

        This method triggers garbage collection and clears application caches. It then
        logs the amount of memory freed after cleanup.
        """
        # Capture the current time.
        current_time = time.time()
        # Retrieve the current memory usage from stats.
        current_usage = self.memory_stats.current_usage.get()
        # Log a warning indicating cleanup is starting due to high memory usage.
        logger.warning(
            f"Memory usage ({current_usage:.1f}%) exceeded threshold {self.memory_threshold}%. Running cleanup...")

        # Check if memory usage is above the midpoint between memory and critical thresholds.
        if current_usage > (self.memory_threshold + self.critical_threshold) / 2:
            # Log that an aggressive cleanup is being performed.
            logger.info("Performing aggressive cleanup due to high memory pressure")
            # Perform garbage collection for generation 2.
            gc.collect(generation=2)
            # Update last garbage collection time.
            self._last_gc_time = current_time
        # Else if sufficient time has elapsed since last full GC, perform full collection.
        elif current_time - self._last_gc_time > self._gc_interval:
            # Perform full garbage collection for generation 2.
            gc.collect(generation=2)
            # Update the last GC time.
            self._last_gc_time = current_time
        else:
            # Otherwise, perform a less aggressive garbage collection (generation 1).
            gc.collect(generation=1)

        # Clear any application-specific caches.
        self._clear_application_caches()
        # Get new memory usage after cleanup.
        new_usage = self.get_memory_usage()
        # Calculate the percentage of memory freed.
        freed = current_usage - new_usage
        # Log the result of the cleanup.
        logger.info(f"Cleanup complete, freed {freed:.1f}% memory")

    def _emergency_cleanup(self) -> None:
        """
        Execute an emergency cleanup when critical memory thresholds are exceeded.

        This method performs a full garbage collection and clears caches in an emergency
        situation to rapidly reduce memory usage.
        """
        # Retrieve current memory usage.
        current_usage = self.memory_stats.current_usage.get()
        # Log a critical error indicating memory usage is above the critical threshold.
        logger.error(
            f"CRITICAL: Memory usage ({current_usage:.1f}%) exceeded critical threshold {self.critical_threshold}%!")
        # Attempt to update emergency cleanup count using the lock.
        try:
            with self._lock.acquire_timeout(timeout=1.0):
                self.memory_stats.emergency_cleanups.increment(1)
        except TimeoutError:
            # Log a warning if unable to acquire the lock in time.
            logger.warning("Timeout acquiring lock to update emergency cleanup count")
        # Perform full garbage collection for generation 2.
        gc.collect(generation=2)
        # Clear application caches.
        self._clear_application_caches()
        # Free additional memory aggressively.
        self._free_additional_memory()
        # Get updated memory usage after cleanup.
        new_usage = self.get_memory_usage()
        # Compute the percentage of memory freed.
        freed_percent = current_usage - new_usage
        # Log the result of the emergency cleanup.
        logger.warning(f"Emergency cleanup: freed {freed_percent:.1f}% memory. New usage: {new_usage:.1f}%")

    @staticmethod
    def _clear_application_caches() -> None:
        """
        Clear application-specific caches to free up memory.

        This method attempts to invalidate cached responses or other temporary data that
        can be cleared to reduce memory usage.
        """
        try:
            # Attempt to import the cache invalidation function.
            try:
                from backend.app.utils.security.caching_middleware import invalidate_cache
                # Call the function to clear the cache.
                invalidate_cache()
                # Log that the response cache was cleared.
                logger.info("Response cache cleared")
            except (ImportError, AttributeError):
                # If the module or function is not found, silently pass.
                pass
        except Exception as e:
            # Log any errors encountered while clearing caches.
            logger.error(f"Error clearing caches: {str(e)}")

    @staticmethod
    def _free_additional_memory() -> None:
        """
        Attempt to free extra memory using aggressive strategies.

        This method attempts to clear internal caches and trim the memory allocator buffers.
        """
        try:
            # Import the sys module for accessing cache functions.
            import sys
            # If the function to clear type cache exists, call it.
            if hasattr(sys, 'clear_type_cache'):
                sys.clear_type_cache()
            # Perform garbage collection.
            gc.collect()
            # If available, trim the memory allocator's buffers.
            if hasattr(gc, 'malloc_trim'):
                gc.malloc_trim()
        except Exception as e:
            # Log any errors during additional memory freeing.
            logger.error(f"Error freeing additional memory: {str(e)}")


# Global memory monitor instance with adaptive thresholds.
memory_monitor = MemoryMonitor(adaptive_thresholds=True)


def init_memory_monitor():
    """
    Initialize the memory monitor with configuration from environment variables.

    This function reads environment variables for memory thresholds and monitoring settings,
    creates a new MemoryMonitor instance, and logs the initialization parameters.
    """
    global memory_monitor
    try:
        # Read memory threshold from environment variable.
        memory_threshold = float(os.environ.get("MEMORY_THRESHOLD", "80.0"))
        # Read critical memory threshold from environment variable.
        critical_threshold = float(os.environ.get("CRITICAL_MEMORY_THRESHOLD", "90.0"))
        # Read check interval from environment variable.
        check_interval = float(os.environ.get("MEMORY_CHECK_INTERVAL", "5.0"))
        # Determine if monitoring should be enabled.
        enable_monitoring = os.environ.get("ENABLE_MEMORY_MONITORING", "true").lower() == "true"
        # Determine if thresholds should be adaptive.
        adaptive_thresholds = os.environ.get("ADAPTIVE_MEMORY_THRESHOLDS", "true").lower() == "true"
        # Create a new MemoryMonitor instance with the retrieved configuration.
        memory_monitor = MemoryMonitor(
            memory_threshold=memory_threshold,
            critical_threshold=critical_threshold,
            check_interval=check_interval,
            enable_monitoring=enable_monitoring,
            adaptive_thresholds=adaptive_thresholds
        )
        # Log successful initialization with parameter details.
        logger.info(
            f"Memory monitor initialized with threshold={memory_threshold}%, critical={critical_threshold}%, adaptive={adaptive_thresholds}"
        )
    except Exception as e:
        # Log any errors during initialization.
        logger.error(f"Error initializing memory monitor: {str(e)}")
        # Fallback: Create a default MemoryMonitor instance.
        memory_monitor = MemoryMonitor()


_gc_stats = {}  # Dictionary for tracking garbage collection statistics.
_gc_lock = threading.RLock()  # Reentrant lock for synchronizing GC stats access.


def init_gc_stats(func_name: str) -> None:
    """
    Ensure that GC statistics for a function are initialized.

    Args:
        func_name (str): The name of the function.

    This function initializes the GC stats dictionary entry for the specified function if it does not exist.
    """
    # Acquire the GC lock.
    with _gc_lock:
        # If function stats are not present, initialize them.
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

    Args:
        initial_memory (float): The initial memory usage percentage.
        available_memory_mb (float): Available memory in MB.

    Returns:
        int: The default adaptive threshold.
    """
    # For very low initial memory, return 30MB if sufficient memory is available, else 15MB.
    if initial_memory < 30:
        return 30 if available_memory_mb > 1000 else 15
    # For moderate memory usage, return 20MB or 10MB based on available memory.
    elif initial_memory < 60:
        return 20 if available_memory_mb > 500 else 10
    # For higher memory usage, return 10MB or 5MB based on available memory.
    else:
        return 10 if available_memory_mb > 300 else 5


def calc_adaptive_threshold(func_name: str, provided_threshold: Optional[int]) -> Tuple[int, float]:
    """
    Calculate the adaptive threshold and return it along with the initial memory usage.

    Args:
        func_name (str): The name of the function.
        provided_threshold (Optional[int]): A provided threshold value.

    Returns:
        Tuple[int, float]: A tuple containing the adaptive threshold and the initial memory usage.
    """
    # Obtain the current memory usage percentage.
    initial_memory = memory_monitor.get_memory_usage()
    # If a threshold is provided, return it along with the initial memory usage.
    if provided_threshold is not None:
        return provided_threshold, initial_memory
    # Retrieve available memory from the memory stats.
    available_memory_mb = memory_monitor.memory_stats.available_memory_mb.get()
    # Acquire the GC lock to safely access GC stats.
    with _gc_lock:
        # Get the memory increase history for the function.
        stats = _gc_stats[func_name]
        mem_increases = stats.get('memory_increases', [])
        # Calculate the average memory increase if available.
        avg_increase = sum(mem_increases) / len(mem_increases) if mem_increases else 0
    # Determine threshold based on average increase or fallback to default.
    threshold = max(5, min(100, avg_increase * 1.5)) if avg_increase > 0 else _default_threshold(initial_memory,
                                                                                                 available_memory_mb)
    # Return the computed threshold and the initial memory usage.
    return threshold, initial_memory


def should_run_gc(initial_memory: float, min_interval: float, func_name: str) -> Tuple[bool, int]:
    """
    Decide whether to run garbage collection before executing the function.

    Args:
        initial_memory (float): The initial memory usage percentage.
        min_interval (float): Minimum interval between GC calls.
        func_name (str): The name of the function.

    Returns:
        Tuple[bool, int]: A tuple where the first element indicates whether to run GC,
                          and the second element is the generation to collect.
    """
    # Get the current time.
    current_time = time.time()
    # Acquire the GC lock to safely read stats.
    with _gc_lock:
        stats = _gc_stats[func_name]
        # Calculate time elapsed since last GC.
        time_since_gc = current_time - stats['last_gc_time']
        # Get the effectiveness of the last GC.
        effectiveness = stats['last_gc_effectiveness']
    # Decide to run full GC if memory usage is very high.
    if initial_memory > 90:
        return True, 2
    # For moderately high usage and sufficient time, run full GC.
    elif initial_memory > 70 and time_since_gc > min_interval / 2:
        return True, 2
    # For lower usage but effective previous GC, run partial GC.
    elif initial_memory > 50 and time_since_gc > min_interval and effectiveness > 5:
        return True, 1
    # For low usage and long interval with effective GC, run light GC.
    elif initial_memory > 30 and time_since_gc > min_interval * 2 and effectiveness > 10:
        return True, 0
    # Otherwise, do not run GC.
    return False, 0


def run_gc(gc_gen: int, func_name: str) -> None:
    """
    Run garbage collection for the specified generation and update GC stats.

    Args:
        gc_gen (int): The generation of garbage collection to run.
        func_name (str): The name of the function triggering GC.
    """
    # Run garbage collection for the specified generation.
    gc.collect(generation=gc_gen)
    # Acquire the GC lock to update stats.
    with _gc_lock:
        # Update the last GC time.
        _gc_stats[func_name]['last_gc_time'] = time.time()
        # Increment the count of GC calls.
        _gc_stats[func_name]['gc_calls'] += 1
    # Log that GC was run before the function execution.
    logger.debug(f"[MEMORY] Pre-function GC(gen={gc_gen}) for {func_name}")


def post_function_cleanup(func_name: str, adaptive_threshold: int, initial_memory: float) -> None:
    """
    Perform post-function memory cleanup and log GC effectiveness.

    Args:
        func_name (str): The name of the function.
        adaptive_threshold (int): The adaptive threshold determined before function execution.
        initial_memory (float): The memory usage before function execution.
    """
    # Get the final memory usage after function execution.
    final_memory = memory_monitor.get_memory_usage()
    # Calculate the memory difference.
    memory_diff = final_memory - initial_memory
    # Acquire the GC lock to update the memory increase history.
    with _gc_lock:
        stats = _gc_stats[func_name]
        # Append the memory increase.
        stats['memory_increases'].append(memory_diff)
        # Keep only the last 10 memory increase records.
        if len(stats['memory_increases']) > 10:
            stats['memory_increases'].pop(0)
    # Get system memory details.
    system_memory = psutil.virtual_memory()
    # Calculate threshold percent based on adaptive threshold in MB converted to percentage.
    threshold_percent = (adaptive_threshold * 1024 * 1024 / system_memory.total) * 100.0
    # If the memory difference is larger than threshold percent or final usage is high, trigger cleanup.
    if memory_diff > threshold_percent or final_memory > 80:
        # Log information about the memory increase and cleanup trigger.
        logger.info(
            f"Function {func_name} increased memory by {memory_diff:.1f}%. Running cleanup with adaptive threshold {adaptive_threshold}MB")
        # If final memory is critical, run full GC.
        if final_memory > 90:
            gc.collect(generation=2)
            logger.debug(f"[MEMORY] Post-function full GC for {func_name} - critical memory usage {final_memory:.1f}%")
        # If final memory is high or increase is very large, run partial GC.
        elif final_memory > 70 or memory_diff > threshold_percent * 2:
            gc.collect(generation=1)
            logger.debug(f"[MEMORY] Post-function partial GC for {func_name} - high memory usage {final_memory:.1f}%")
        else:
            # Otherwise, run light GC.
            gc.collect(generation=0)
            logger.debug(f"[MEMORY] Post-function light GC for {func_name} - memory usage {final_memory:.1f}%")
        # Get memory usage after GC.
        post_gc_memory = memory_monitor.get_memory_usage()
        # Calculate effectiveness of GC.
        gc_effect = final_memory - post_gc_memory
        # Acquire GC lock to update effectiveness stats.
        with _gc_lock:
            stats['last_gc_time'] = time.time()
            stats['last_gc_effectiveness'] = gc_effect
            stats['gc_calls'] += 1
        # Log the amount of memory freed by GC.
        if gc_effect > 0:
            logger.info(f"Garbage collection freed {gc_effect:.1f}% memory")
        else:
            logger.info(f"Garbage collection had minimal effect ({gc_effect:.1f}%)")


def pre_exec(func_name: str, provided_threshold: Optional[int], min_interval: float) -> Tuple[int, float]:
    """
    Perform pre-execution memory management: update call count, compute adaptive threshold
    and initial memory, log threshold, and run GC if needed.

    Args:
        func_name (str): The name of the function.
        provided_threshold (Optional[int]): A threshold provided externally.
        min_interval (float): Minimum interval between GC calls.

    Returns:
        Tuple[int, float]: A tuple containing the adaptive threshold and the initial memory usage.
    """
    # Acquire GC lock and initialize stats if not present.
    with _gc_lock:
        _gc_stats.setdefault(func_name, {
            'total_calls': 0,
            'last_gc_time': 0,
            'last_gc_effectiveness': 0,
            'gc_calls': 0,
            'memory_increases': [],
        })
        # Increment total calls for the function.
        _gc_stats[func_name]['total_calls'] += 1
    # Calculate the adaptive threshold and initial memory.
    adaptive_threshold, initial_memory = calc_adaptive_threshold(func_name, provided_threshold)
    # Log the adaptive threshold being used.
    logger.debug(f"[MEMORY] Running {func_name} with adaptive threshold {adaptive_threshold}MB")
    # Determine if GC should run before the function executes.
    run_gc_flag, gc_gen = should_run_gc(initial_memory, min_interval, func_name)
    if run_gc_flag:
        # If GC is required, run it with the computed generation.
        run_gc(gc_gen, func_name)
    # Return the adaptive threshold and initial memory usage.
    return adaptive_threshold, initial_memory


def memory_optimized(threshold_mb: Optional[int] = None, min_gc_interval: float = 10.0):
    """
    Decorator to optimize memory usage for functions processing large data.

    This decorator monitors memory usage before and after the wrapped function and
    triggers garbage collection if memory usage exceeds an adaptive threshold.

    Args:
        threshold_mb (Optional[int]): An optional threshold in MB to override adaptive threshold.
        min_gc_interval (float): The minimum interval between GC calls in seconds.

    Returns:
        Callable: A decorator function that wraps the target function with memory optimization logic.
    """

    def decorator(func):
        # Get the function's name.
        func_name = func.__name__
        # Initialize GC statistics for this function.
        init_gc_stats(func_name)

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Perform pre-execution memory management.
            adaptive_threshold, initial_memory = pre_exec(func_name, threshold_mb, min_gc_interval)
            try:
                # Execute the asynchronous function.
                return await func(*args, **kwargs)
            finally:
                # Perform post-execution cleanup and GC.
                post_function_cleanup(func_name, adaptive_threshold, initial_memory)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Perform pre-execution memory management.
            adaptive_threshold, initial_memory = pre_exec(func_name, threshold_mb, min_gc_interval)
            try:
                # Execute the synchronous function.
                return func(*args, **kwargs)
            finally:
                # Perform post-execution cleanup and GC.
                post_function_cleanup(func_name, adaptive_threshold, initial_memory)

        # Return the appropriate wrapper based on whether the function is asynchronous.
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    # Return the actual decorator.
    return decorator


# Initialize the memory monitor when the module is imported.
init_memory_monitor()
