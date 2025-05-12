"""
Enhanced synchronization utilities with optimized lock hierarchy and instance-level locking.
This module provides centralized synchronization primitives for thread safety across the application,
with an improved focus on instance-level locks to maximize parallelism. Features include:
  - Lock timeouts with automatic recovery
  - Detailed logging of lock acquisition and release events
  - Lock hierarchy to prevent deadlock scenarios
  - Reentrant and non-reentrant lock variants
  - Async-friendly locking primitives
  - Lock usage statistics and monitoring
  - Optimized for centralized document processing
"""

import asyncio
import logging
import threading
import time
import uuid
from contextlib import contextmanager, asynccontextmanager
from enum import Enum, auto
from typing import Dict, List, Optional, Set, Any, Tuple, Generator, AsyncGenerator

from backend.app.utils.constant.constant import (
    DEFAULT_LOCK_TIMEOUT,
    DEFAULT_ASYNC_LOCK_TIMEOUT,
)

# Configure module logger (using default logger configuration).
logger = logging.getLogger(__name__)


class LockPriority(Enum):
    """
    Priority levels for locks to establish hierarchy and prevent deadlocks.

    This enumeration defines various priority levels that can be assigned to locks.
    Higher priority locks should be acquired before lower priority ones to prevent circular wait conditions.
    """

    CRITICAL = auto()  # Highest priority: e.g., initialization and shutdown tasks.
    HIGH = auto()  # High priority: e.g., detector access.
    MEDIUM = auto()  # Medium priority: e.g., document processing.
    LOW = auto()  # Low priority: e.g., cache operations.
    BACKGROUND = auto()  # Lowest priority: e.g., cleanup tasks.


class LockType(Enum):
    """
    Types of locks for monitoring and logging purposes.

    This enumeration categorizes locks into different types, such as thread-based locks,
    asyncio locks, semaphores, and read-write locks.
    """

    THREAD = auto()  # Represents a threading lock.
    ASYNCIO = auto()  # Represents an asyncio lock.
    SEMAPHORE = auto()  # Represents a semaphore.
    RW_LOCK = auto()  # Represents a read-write lock.


class LockStatistics:
    """
    Track statistics for lock usage across the application.

    This class maintains detailed statistics for each lock, including acquisition counts,
    wait times, timeouts, and active lock information. It uses an internal RLock to ensure thread safety.
    """

    def __init__(self):
        # Create an RLock to guard access to statistics.
        self._lock = threading.RLock()
        # Dictionary to store statistics for each lock keyed by lock ID.
        self.stats: Dict[str, Dict[str, Any]] = {}
        # Dictionary to store currently active (acquired) locks.
        self.active_locks: Dict[str, Dict[str, Any]] = {}
        # Counter for instance-level locks.
        self.instance_locks_count = 0
        # Counter for global locks.
        self.global_locks_count = 0
        # Count of successful lock acquisitions.
        self.successful_acquisitions = 0
        # Count of failed lock acquisitions due to timeouts.
        self.failed_acquisitions = 0

    def register_lock(
        self,
        lock_id: str,
        lock_name: str,
        lock_type: LockType,
        priority: LockPriority,
        is_instance_lock: bool = False,
    ) -> None:
        """
        Register a new lock for statistics tracking.

        Args:
            lock_id (str): Unique identifier for the lock.
            lock_name (str): Name of the lock.
            lock_type (LockType): Type of the lock (e.g., THREAD, ASYNCIO).
            priority (LockPriority): Priority assigned to the lock.
            is_instance_lock (bool): True if this is an instance-level lock.
        """
        # Acquire internal RLock to ensure thread safety.
        with self._lock:
            # Create a statistics entry for the new lock.
            self.stats[lock_id] = {
                "name": lock_name,
                "type": lock_type,
                "priority": priority,
                "created_at": time.time(),
                "acquisitions": 0,
                "acquisition_time_total": 0.0,
                "acquisition_time_max": 0.0,
                "wait_time_total": 0.0,
                "wait_time_max": 0.0,
                "timeouts": 0,
                "contentions": 0,
                "last_acquired": None,
                "last_released": None,
                "is_instance_lock": is_instance_lock,
            }
            # Increment instance or global lock counter based on the type.
            if is_instance_lock:
                self.instance_locks_count += 1
            else:
                self.global_locks_count += 1

    def record_acquisition(
        self, lock_id: str, thread_id: str, wait_time: float, acquisition_time: float
    ) -> None:
        """
        Record a successful lock acquisition.

        Args:
            lock_id (str): Unique identifier for the lock.
            thread_id (str): Identifier of the thread or task that acquired the lock.
            wait_time (float): Time spent waiting for the lock.
            acquisition_time (float): Time taken to acquire the lock.
        """
        # Acquire the internal lock to update statistics.
        with self._lock:
            # Increment total successful acquisitions.
            self.successful_acquisitions += 1
            # Update the specific lock's statistics if available.
            if lock_id in self.stats:
                stats = self.stats[lock_id]
                stats["acquisitions"] += 1
                stats["acquisition_time_total"] += acquisition_time
                stats["wait_time_total"] += wait_time
                stats["last_acquired"] = time.time()
                # Update maximum wait time if necessary.
                if wait_time > stats["wait_time_max"]:
                    stats["wait_time_max"] = wait_time
                # Register the lock as active with a composite key.
                self.active_locks[f"{lock_id}:{thread_id}"] = {
                    "acquired_at": time.time(),
                    "thread_id": thread_id,
                }

    def record_release(self, lock_id: str, thread_id: str) -> None:
        """
        Record a lock release.

        Args:
            lock_id (str): Unique identifier for the lock.
            thread_id (str): Identifier of the thread or task releasing the lock.
        """
        # Acquire the lock to update statistics.
        with self._lock:
            # Update the release timestamp for the lock.
            if lock_id in self.stats:
                self.stats[lock_id]["last_released"] = time.time()
            # Remove the active lock record.
            lock_key = f"{lock_id}:{thread_id}"
            if lock_key in self.active_locks:
                del self.active_locks[lock_key]

    def record_timeout(self, lock_id: str) -> None:
        """
        Record a lock acquisition timeout.

        Args:
            lock_id (str): Unique identifier for the lock.
        """
        # Update failure statistics under the internal lock.
        with self._lock:
            self.failed_acquisitions += 1
            if lock_id in self.stats:
                self.stats[lock_id]["timeouts"] += 1

    def record_contention(self, lock_id: str) -> None:
        """
        Record a lock contention event when a lock is already held.

        Args:
            lock_id (str): Unique identifier for the lock.
        """
        # Update contention count under the internal lock.
        with self._lock:
            if lock_id in self.stats:
                self.stats[lock_id]["contentions"] += 1

    def get_lock_stats(self, lock_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieve statistics for a specific lock or all locks.

        Args:
            lock_id (Optional[str]): Specific lock identifier. If None, return stats for all locks.

        Returns:
            Dict[str, Any]: A dictionary of lock statistics.
        """
        # Acquire internal lock to safely access stats.
        with self._lock:
            if lock_id:
                # Return a copy of the statistics for the specified lock.
                return self.stats.get(lock_id, {}).copy()
            # Otherwise, return copies of all lock statistics.
            return {k: v.copy() for k, v in self.stats.items()}

    def get_active_locks(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about currently held locks.

        Returns:
            Dict[str, Dict[str, Any]]: A dictionary mapping lock composite IDs to acquisition details.
        """
        # Acquire internal lock to safely access active locks.
        with self._lock:
            return {k: v.copy() for k, v in self.active_locks.items()}

    def get_summary_stats(self) -> Dict[str, Any]:
        """
        Get summary statistics about all locks.

        Returns:
            Dict[str, Any]: A summary including total locks, acquisition counts, and success rates.
        """
        # Acquire the lock to aggregate and return summary statistics.
        with self._lock:
            return {
                "total_locks": len(self.stats),
                "instance_locks": self.instance_locks_count,
                "global_locks": self.global_locks_count,
                "active_locks": len(self.active_locks),
                "total_acquisitions": self.successful_acquisitions,
                "failed_acquisitions": self.failed_acquisitions,
                "success_rate": (
                    self.successful_acquisitions
                    / (self.successful_acquisitions + self.failed_acquisitions or 1)
                )
                * 100,
            }

    def reset_stats(self, lock_id: Optional[str] = None) -> None:
        """
        Reset statistics for a specific lock or all locks.

        Args:
            lock_id (Optional[str]): Specific lock identifier. If None, resets stats for all locks.
        """
        # Acquire the internal lock to reset statistics.
        with self._lock:
            if lock_id:
                if lock_id in self.stats:
                    # Preserve creation time and instance lock flag while resetting numeric stats.
                    created_at = self.stats[lock_id].get("created_at", time.time())
                    is_instance_lock = self.stats[lock_id].get(
                        "is_instance_lock", False
                    )
                    self.stats[lock_id] = {
                        **self.stats[lock_id],
                        "acquisitions": 0,
                        "acquisition_time_total": 0.0,
                        "acquisition_time_max": 0.0,
                        "wait_time_total": 0.0,
                        "wait_time_max": 0.0,
                        "timeouts": 0,
                        "contentions": 0,
                        "created_at": created_at,
                        "is_instance_lock": is_instance_lock,
                    }
            else:
                self.successful_acquisitions = 0
                self.failed_acquisitions = 0
                # Reset statistics for all locks.
                for lock_id in self.stats:
                    self.reset_stats(lock_id)


# Global statistics tracker instance.
lock_statistics = LockStatistics()


class LockManager:
    """
    Central lock manager to prevent deadlocks by enforcing lock hierarchy.

    This manager tracks the order in which locks are acquired in each thread and ensures
    that locks are acquired in a consistent order (based on priority) to avoid deadlock
    scenarios. It also tracks instance-level locks separately.
    """

    def __init__(self):
        # Create an internal RLock to protect shared data structures.
        self._lock = threading.RLock()
        # Dictionary mapping thread IDs to lists of currently held locks with priority.
        self._thread_locks: Dict[int, List[Tuple[str, LockPriority]]] = {}
        # Wait graph for potential deadlock detection (lock dependency relationships).
        self._wait_graph: Dict[str, Set[str]] = {}
        # Dictionary mapping thread IDs to the set of instance-level locks held.
        self._instance_locks: Dict[int, Set[str]] = {}

    def check_deadlock(
        self, lock_id: str, priority: LockPriority, is_instance_lock: bool = False
    ) -> bool:
        """
        Check if acquiring this lock could cause a deadlock based on current locks held.

        Args:
            lock_id (str): The ID of the lock to be acquired.
            priority (LockPriority): The priority of the lock to be acquired.
            is_instance_lock (bool): Flag indicating if this is an instance-level lock.

        Returns:
            bool: True if a potential deadlock is detected, False otherwise.
        """
        # Get the current thread identifier.
        thread_id = threading.get_ident()
        # Acquire internal lock to access thread lock tracking.
        with self._lock:
            # If no locks are held by this thread, no deadlock is possible.
            if thread_id not in self._thread_locks:
                self._thread_locks[thread_id] = []
                self._instance_locks[thread_id] = set()
                return False

            # If it is an instance-level lock, add it and allow acquisition.
            if is_instance_lock:
                self._instance_locks[thread_id].add(lock_id)
                return False

            # Retrieve the list of locks currently held.
            current_locks = self._thread_locks[thread_id]
            # Check each held lock for hierarchy violations.
            for held_lock_id, held_priority in current_locks:
                # Skip instance locks as they have relaxed hierarchy.
                if held_lock_id in self._instance_locks.get(thread_id, set()):
                    continue
                # If the priority of the new lock is lower than a held lock, potential deadlock exists.
                if priority.value < held_priority.value:
                    logger.warning(
                        f"Lock hierarchy violation detected: Attempting to acquire {lock_id} "
                        f"(priority {priority.name}) while holding {held_lock_id} "
                        f"(priority {held_priority.name})"
                    )
                    return True
            # If no violation, return False.
            return False

    def register_lock_acquisition(
        self, lock_id: str, priority: LockPriority, is_instance_lock: bool = False
    ) -> None:
        """
        Register that a thread has acquired a lock.

        Args:
            lock_id (str): The ID of the acquired lock.
            priority (LockPriority): The priority of the lock.
            is_instance_lock (bool): Whether it is an instance-level lock.
        """
        # Get the current thread identifier.
        thread_id = threading.get_ident()
        # Acquire internal lock to update tracking structures.
        with self._lock:
            # Initialize the tracking lists if this thread is new.
            if thread_id not in self._thread_locks:
                self._thread_locks[thread_id] = []
                self._instance_locks[thread_id] = set()
            # Append the acquired lock information to the thread's list.
            self._thread_locks[thread_id].append((lock_id, priority))
            # If instance-level, record it separately.
            if is_instance_lock:
                self._instance_locks[thread_id].add(lock_id)

    def register_lock_release(
        self, lock_id: str, is_instance_lock: bool = False
    ) -> None:
        """
        Register that a thread has released a lock.

        Args:
            lock_id (str): The ID of the lock being released.
            is_instance_lock (bool): Whether it is an instance-level lock.
        """
        # Get the identifier for the current thread.
        thread_id = threading.get_ident()
        # Acquire the internal lock to update the tracking lists.
        with self._lock:
            # Filter out the released lock from the list.
            if thread_id in self._thread_locks:
                self._thread_locks[thread_id] = [
                    (l_id, prio)
                    for l_id, prio in self._thread_locks[thread_id]
                    if l_id != lock_id
                ]
            # If it is an instance lock, remove from instance-specific tracking.
            if is_instance_lock and thread_id in self._instance_locks:
                self._instance_locks[thread_id].discard(lock_id)
            # Clean up data if no locks remain for this thread.
            if thread_id in self._thread_locks and not self._thread_locks[thread_id]:
                del self._thread_locks[thread_id]
                if thread_id in self._instance_locks:
                    del self._instance_locks[thread_id]

    def clear_thread_data(self) -> None:
        """
        Clear lock data for the current thread (cleanup).

        This method removes all lock acquisition data for the current thread.
        """
        # Obtain the thread identifier.
        thread_id = threading.get_ident()
        # Acquire internal lock to safely clear data.
        with self._lock:
            if thread_id in self._thread_locks:
                del self._thread_locks[thread_id]
            if thread_id in self._instance_locks:
                del self._instance_locks[thread_id]


# Global lock manager instance.
lock_manager = LockManager()


def _prepare_lock_acquisition(
    timeout: Optional[float],
    default_timeout: float,
    lock,
    owner,
    lock_name: str,
    identifier,
    log,  # Logger used for logging messages.
    record_contention_callback,
    use_locked: bool = False,
) -> Tuple[float, float]:
    """
    Prepare lock acquisition by determining the effective timeout and start time.
    Optionally logs contention if the lock is held by another thread or task.

    Args:
        timeout (Optional[float]): Provided timeout value.
        default_timeout (float): Default timeout if none is provided.
        lock: The lock object.
        owner: The current recorded owner of the lock.
        lock_name (str): The name of the lock.
        identifier: Identifier of the current thread/task.
        log: Logger instance for logging.
        record_contention_callback: Callback to record a contention event.
        use_locked (bool): If True, check using lock.locked(); otherwise rely on owner.

    Returns:
        Tuple[float, float]: Effective timeout and wait start time.
    """
    # Determine effective timeout from provided value or default.
    effective_timeout = timeout if timeout is not None else default_timeout
    # Record the current time as the start of waiting.
    wait_start = time.time()
    # Check for contention based on mode.
    if use_locked:
        # If the lock is already acquired and the owner does not match, log wait.
        if lock.locked() and owner != identifier:
            log.debug(
                f"Task {identifier} waiting for lock '{lock_name}' currently held by {owner}"
            )
            record_contention_callback()
    else:
        # If an owner is recorded and is different, log wait.
        if owner is not None and owner != identifier:
            log.debug(
                f"Thread {identifier} waiting for lock '{lock_name}' currently held by {owner}"
            )
            record_contention_callback()
    # Return effective timeout and wait start time.
    return effective_timeout, wait_start


async def _async_acquire_with_timeout(
    acquire_coro, effective_timeout: float, type_str: str, name: str
) -> Tuple[bool, float]:
    """
    Helper function to acquire an async lock or semaphore with a timeout.

    Args:
        acquire_coro: The coroutine that attempts to acquire the lock.
        effective_timeout (float): The timeout value in seconds.
        type_str (str): String representing the type (e.g., "async lock").
        name (str): Name of the lock/semaphore.

    Returns:
        Tuple[bool, float]: A tuple containing a boolean indicating success and the wait time.
    """
    # Record the start time.
    start = time.time()
    try:
        # Await the acquisition coroutine with timeout.
        await asyncio.wait_for(acquire_coro, timeout=effective_timeout)
        acquired = True
    except asyncio.TimeoutError:
        # Set acquired flag to False on timeout.
        acquired = False
    except Exception as e:
        # Log any other exception that occurs during acquisition.
        logger.error(f"Error acquiring {type_str} '{name}': {e}")
        acquired = False
    # Calculate wait time.
    wait_time = time.time() - start
    # Return the acquisition result and wait time.
    return acquired, wait_time


class TimeoutLock:
    """
    Enhanced Lock implementation with timeout, detailed logging, and deadlock prevention.

    This lock extends standard threading locks with features such as timeouts,
    detailed statistics recording, and integration with a global lock manager for deadlock prevention.
    """

    def __init__(
        self,
        name: str,
        priority: LockPriority = LockPriority.MEDIUM,
        timeout: Optional[float] = None,
        reentrant: bool = True,
        is_instance_lock: bool = False,
    ):
        """
        Initialize a new TimeoutLock.

        Args:
            name (str): Name of the lock for logging and tracking.
            priority (LockPriority): Priority of the lock.
            timeout (Optional[float]): Timeout in seconds; uses default if None.
            reentrant (bool): True for a reentrant lock, False for non-reentrant.
            is_instance_lock (bool): True if this is an instance-level lock.
        """
        # Set the name of the lock.
        self.name = name
        # Generate a unique ID for the lock.
        self.id = f"{name}_{uuid.uuid4().hex[:8]}"
        # Set the priority.
        self.priority = priority
        # Determine the default timeout.
        self.default_timeout = timeout or DEFAULT_LOCK_TIMEOUT
        # Create a reentrant lock if specified; otherwise, a standard lock.
        self.lock = threading.RLock() if reentrant else threading.Lock()
        # Initialize owner information.
        self.owner: Optional[int] = None
        # Counter for how many times the lock has been acquired.
        self.acquisition_count = 0
        # Flag indicating if this is an instance-level lock.
        self.is_instance_lock = is_instance_lock

        # Register this lock in the global statistics tracker.
        lock_statistics.register_lock(
            self.id, name, LockType.THREAD, priority, is_instance_lock
        )

        # Log the creation of the lock.
        logger.debug(
            f"Created lock '{name}' with ID {self.id} (priority={priority.name}, timeout={self.default_timeout}s, instance={is_instance_lock})"
        )

    def acquire(self, blocking: bool = True, timeout: Optional[float] = None) -> bool:
        """
        Acquire the lock with timeout and deadlock prevention.

        Args:
            blocking (bool): Whether to block until the lock is acquired.
            timeout (Optional[float]): Timeout value in seconds; if None, uses default.

        Returns:
            bool: True if the lock was acquired, False otherwise.
        """
        # Get the identifier of the current thread.
        thread_id = threading.get_ident()
        # Get the current thread's name.
        thread_name = threading.current_thread().name

        # Check for potential deadlock using the global lock manager.
        if lock_manager.check_deadlock(self.id, self.priority, self.is_instance_lock):
            logger.warning(
                f"Thread {thread_name} avoiding potential deadlock; not acquiring lock '{self.name}'"
            )
            # Record a timeout event in the statistics.
            lock_statistics.record_timeout(self.id)
            # Return False indicating lock not acquired.
            return False

        # Prepare to acquire the lock by determining effective timeout and logging contention.
        effective_timeout, wait_start = _prepare_lock_acquisition(
            timeout,
            self.default_timeout,
            self.lock,
            self.owner,
            self.name,
            thread_id,
            logger,
            lambda: lock_statistics.record_contention(self.id),
            use_locked=False,
        )

        try:
            # Attempt to acquire the underlying lock with blocking and timeout.
            acquired = self.lock.acquire(
                blocking=blocking, timeout=effective_timeout if blocking else None
            )
        except Exception as e:
            # Log error if lock acquisition fails due to exception.
            logger.error(f"Error acquiring lock '{self.name}': {e}")
            lock_statistics.record_timeout(self.id)
            return False

        # Calculate wait time.
        wait_time = time.time() - wait_start

        if acquired:
            # Set the owner to the current thread.
            self.owner = thread_id
            # Increment acquisition count.
            self.acquisition_count += 1
            # Register the lock acquisition with the global manager.
            lock_manager.register_lock_acquisition(
                self.id, self.priority, self.is_instance_lock
            )
            # Record successful acquisition in lock statistics.
            lock_statistics.record_acquisition(self.id, str(thread_id), wait_time, 0.0)
            # Log successful acquisition.
            logger.debug(
                f"Thread {thread_name} acquired lock '{self.name}' after {wait_time:.6f}s wait"
            )
        else:
            # Record a timeout event if lock not acquired.
            lock_statistics.record_timeout(self.id)
            # Log a warning indicating failure to acquire lock within timeout.
            logger.warning(
                f"Thread {thread_name} failed to acquire lock '{self.name}' after {wait_time:.6f}s wait (timeout={effective_timeout}s)"
            )

        # Return the result of acquisition.
        return acquired

    def release(self) -> None:
        """
        Release the lock with logging.

        This method releases the lock and updates lock statistics. Errors during release are caught and logged.
        """
        # Get the current thread identifier.
        thread_id = threading.get_ident()
        # Get current thread name.
        thread_name = threading.current_thread().name

        try:
            # Record the lock release event in lock statistics.
            lock_statistics.record_release(self.id, str(thread_id))
            # Release the underlying lock.
            self.lock.release()
            # If the current owner is this thread, clear the owner.
            if self.owner == thread_id:
                self.owner = None
            # Register the lock release in the global lock manager.
            lock_manager.register_lock_release(self.id, self.is_instance_lock)
            # Log that the lock has been released.
            logger.debug(f"Thread {thread_name} released lock '{self.name}'")
        except RuntimeError as e:
            # Log errors encountered during lock release.
            logger.error(f"Error releasing lock '{self.name}': {e}")

    @contextmanager
    def acquire_timeout(
        self, timeout: Optional[float] = None
    ) -> Generator[bool, Any, None]:
        """
        Context manager for acquiring the lock with a timeout.

        Args:
            timeout (Optional[float]): Timeout override in seconds.

        Yields:
            bool: True if the lock was acquired, False otherwise.

        This context manager simplifies lock acquisition and ensures proper release of the lock.
        """
        # Attempt to acquire the lock with the specified timeout.
        acquired = self.acquire(timeout=timeout)
        try:
            # Yield the acquisition status to the context block.
            yield acquired
        finally:
            # Release the lock if it was successfully acquired.
            if acquired:
                self.release()


class AsyncTimeoutLock:
    """
    Enhanced asyncio.Lock implementation with timeout, detailed logging, and deadlock prevention.

    This class provides asynchronous lock functionality similar to TimeoutLock but for asyncio-based tasks.
    """

    def __init__(
        self,
        name: str,
        priority: LockPriority = LockPriority.MEDIUM,
        timeout: Optional[float] = None,
        is_instance_lock: bool = False,
    ):
        """
        Initialize a new AsyncTimeoutLock.

        Args:
            name (str): Name of the async lock.
            priority (LockPriority): Priority for deadlock prevention.
            timeout (Optional[float]): Timeout in seconds; uses default if None.
            is_instance_lock (bool): True if this is an instance-level lock.
        """
        # Set the lock name.
        self.name = name
        # Generate a unique lock identifier.
        self.id = f"{name}_{uuid.uuid4().hex[:8]}"
        # Set the priority.
        self.priority = priority
        # Determine the default timeout, using the provided or default async timeout.
        self.default_timeout = timeout or DEFAULT_ASYNC_LOCK_TIMEOUT
        # Create an asyncio.Lock.
        self.lock = asyncio.Lock()
        # Initialize owner information.
        self.owner: Optional[str] = None
        # Flag indicating if this is an instance-level lock.
        self.is_instance_lock = is_instance_lock

        # Register this async lock in the global statistics tracker.
        lock_statistics.register_lock(
            self.id, name, LockType.ASYNCIO, priority, is_instance_lock
        )

        # Log the creation of the async lock.
        logger.debug(
            f"Created async lock '{name}' with ID {self.id} (priority={priority.name}, timeout={self.default_timeout}s, instance={is_instance_lock})"
        )

    async def acquire(self, timeout: Optional[float] = None) -> bool:
        """
        Acquire the async lock with timeout and deadlock prevention.

        Args:
            timeout (Optional[float]): Timeout value override in seconds.

        Returns:
            bool: True if the lock was acquired, False otherwise.
        """
        # Construct a unique identifier for the current async task.
        thread_id = f"{threading.get_ident()}:{id(asyncio.current_task())}"
        # Retrieve the name of the current async task.
        task_name = (
            asyncio.current_task().get_name() if asyncio.current_task() else "unknown"
        )

        # Prepare lock acquisition by determining effective timeout and logging any contention.
        effective_timeout, _ = _prepare_lock_acquisition(
            timeout,
            self.default_timeout,
            self.lock,
            self.owner,
            self.name,
            thread_id,
            logger,
            lambda: lock_statistics.record_contention(self.id),
            use_locked=True,
        )

        # Attempt to acquire the lock using the helper function with timeout.
        acquired, wait_time = await _async_acquire_with_timeout(
            self.lock.acquire(), effective_timeout, "async lock", self.name
        )

        if acquired:
            # Set the owner upon successful acquisition.
            self.owner = thread_id
            # Record the acquisition event in statistics.
            lock_statistics.record_acquisition(self.id, thread_id, wait_time, 0.0)
            logger.debug(
                f"Task {task_name} acquired async lock '{self.name}' after {wait_time:.6f}s wait"
            )
        else:
            # Record a timeout event if acquisition failed.
            lock_statistics.record_timeout(self.id)
            logger.warning(
                f"Task {task_name} failed to acquire async lock '{self.name}' after {wait_time:.6f}s wait (timeout={effective_timeout}s)"
            )

        # Return the acquisition result.
        return acquired

    def release(self) -> None:
        """
        Release the async lock with logging.

        This method releases the lock and updates associated statistics.
        """
        # Build a unique identifier for the current task.
        thread_id = f"{threading.get_ident()}:{id(asyncio.current_task())}"
        # Get the name of the current async task.
        task_name = (
            asyncio.current_task().get_name() if asyncio.current_task() else "unknown"
        )

        try:
            # Record lock release in statistics.
            lock_statistics.record_release(self.id, thread_id)
            # Release the underlying asyncio lock.
            self.lock.release()
            # Clear the owner.
            self.owner = None
            logger.debug(f"Task {task_name} released async lock '{self.name}'")
        except RuntimeError as e:
            # Log any errors encountered during release.
            logger.error(f"Error releasing async lock '{self.name}': {e}")

    @asynccontextmanager
    async def acquire_timeout(
        self, timeout: Optional[float] = None
    ) -> AsyncGenerator[bool, None]:
        """
        Async context manager for acquiring the lock with a timeout.

        Args:
            timeout (Optional[float]): Timeout override in seconds.

        Yields:
            bool: True if the lock was acquired, False otherwise.

        This context manager ensures proper acquisition and release of the async lock.
        """
        # Attempt to acquire the lock.
        acquired = await self.acquire(timeout=timeout)
        try:
            # Yield the acquisition result to the context.
            yield acquired
        finally:
            # Release the lock if it was acquired.
            if acquired:
                self.release()


class AsyncTimeoutSemaphore:
    """
    Enhanced asyncio.Semaphore implementation with timeout, logging, and deadlock prevention.

    This semaphore provides asynchronous control over a fixed number of permits with timeout support,
    detailed logging, and is optimized for batch operations.
    """

    def __init__(
        self,
        name: str,
        value: int = 1,
        priority: LockPriority = LockPriority.MEDIUM,
        timeout: Optional[float] = None,
    ):
        """
        Initialize a new AsyncTimeoutSemaphore.

        Args:
            name (str): Name of the semaphore for tracking.
            value (int): Initial permit count.
            priority (LockPriority): Priority level for deadlock prevention.
            timeout (Optional[float]): Timeout in seconds; uses default if None.
        """
        # Set semaphore name.
        self.name = name
        # Generate a unique ID for the semaphore.
        self.id = f"{name}_{uuid.uuid4().hex[:8]}"
        # Set the priority.
        self.priority = priority
        # Determine the default timeout for acquisitions.
        self.default_timeout = timeout or DEFAULT_ASYNC_LOCK_TIMEOUT
        # Create the semaphore with the provided initial value.
        self.semaphore = asyncio.Semaphore(value)
        # Store the initial and current permit counts.
        self.value = value
        self.current_value = value
        # Create an asyncio lock to protect updates to current_value.
        self._value_lock = asyncio.Lock()

        # Register this semaphore in the global lock statistics (instance lock always true).
        lock_statistics.register_lock(
            self.id, name, LockType.SEMAPHORE, priority, is_instance_lock=True
        )

        # Log the creation of the async semaphore.
        logger.debug(
            f"Created async semaphore '{name}' with ID {self.id} and value {value} (priority={priority.name}, timeout={self.default_timeout}s)"
        )

    async def acquire(self, timeout: Optional[float] = None) -> bool:
        """
        Acquire the semaphore with a timeout.

        Args:
            timeout (Optional[float]): Timeout override in seconds.

        Returns:
            bool: True if a permit was acquired, False otherwise.
        """
        # Build a unique identifier for the current async task.
        thread_id = f"{threading.get_ident()}:{id(asyncio.current_task())}"
        # Get the current async task name.
        task_name = (
            asyncio.current_task().get_name() if asyncio.current_task() else "unknown"
        )
        # Determine the effective timeout.
        effective_timeout = timeout if timeout is not None else self.default_timeout

        # Attempt to acquire the semaphore with the helper function.
        acquired, wait_time = await _async_acquire_with_timeout(
            self.semaphore.acquire(), effective_timeout, "async semaphore", self.name
        )

        if acquired:
            # Once acquired, update the current available permits safely.
            async with self._value_lock:
                self.current_value -= 1
            # Record the acquisition event in statistics.
            lock_statistics.record_acquisition(self.id, thread_id, wait_time, 0.0)
            logger.debug(
                f"Task {task_name} acquired async semaphore '{self.name}' after {wait_time:.6f}s wait (remaining permits: {self.current_value})"
            )
        else:
            # Record timeout if acquisition fails.
            lock_statistics.record_timeout(self.id)
            logger.warning(
                f"Task {task_name} failed to acquire async semaphore '{self.name}' after {wait_time:.6f}s wait (timeout={effective_timeout}s)"
            )

        # Return the acquisition result.
        return acquired

    def release(self) -> None:
        """
        Release the semaphore with logging.

        This method releases one permit of the semaphore and updates tracking data.
        """
        # Build a unique identifier for the current async task.
        thread_id = f"{threading.get_ident()}:{id(asyncio.current_task())}"
        # Get the current task name.
        task_name = (
            asyncio.current_task().get_name() if asyncio.current_task() else "unknown"
        )
        try:
            # Record the release in lock statistics.
            lock_statistics.record_release(self.id, thread_id)
            # Release the semaphore.
            self.semaphore.release()
            # Update the current available permits safely.
            self.current_value += 1
            if self.current_value > self.value:
                self.current_value = self.value
            logger.debug(
                f"Task {task_name} released async semaphore '{self.name}' (available permits: {self.current_value})"
            )
        except Exception as e:
            # Log any errors encountered during release.
            logger.error(f"Error releasing async semaphore '{self.name}': {e}")

    @asynccontextmanager
    async def acquire_timeout(
        self, timeout: Optional[float] = None
    ) -> AsyncGenerator[bool, None]:
        """
        Async context manager for acquiring the semaphore with a timeout.

        Args:
            timeout (Optional[float]): Timeout override in seconds.

        Yields:
            bool: True if the semaphore was acquired, False otherwise.
        """
        # Acquire semaphore and yield acquisition result.
        acquired = await self.acquire(timeout=timeout)
        try:
            yield acquired
        finally:
            if acquired:
                self.release()


def init():
    """
    Initialize the synchronization module (sets up logging).

    This function configures the logger for the synchronization module if not already set up,
    ensuring that synchronization events are logged to the appropriate output.
    """
    # Retrieve the module-specific logger.
    module_logger = logging.getLogger(__name__)
    # Check if the logger has any handlers attached.
    if not module_logger.handlers:
        # Create a new stream handler.
        handler = logging.StreamHandler()
        # Define a formatter for log messages.
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        # Set the formatter for the handler.
        handler.setFormatter(formatter)
        # Add the handler to the logger.
        module_logger.addHandler(handler)
        # Set the logging level to INFO.
        module_logger.setLevel(logging.INFO)
    # Log that the synchronization utilities have been initialized.
    logger.info("Synchronization utils initialized")


# Initialize the synchronization module upon import.
init()
