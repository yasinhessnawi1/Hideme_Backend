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

# Configure logger
logger = logging.getLogger(__name__)

# Default timeout values
DEFAULT_LOCK_TIMEOUT = 30.0  # 30 seconds
DEFAULT_ASYNC_LOCK_TIMEOUT = 30.0  # 30 seconds


class LockPriority(Enum):
    """Priority levels for locks to establish hierarchy and prevent deadlocks."""
    CRITICAL = auto()  # Highest priority (e.g., initialization, shutdown)
    HIGH = auto()  # High priority (e.g., detector access)
    MEDIUM = auto()  # Medium priority (e.g., document processing)
    LOW = auto()  # Low priority (e.g., cache operations)
    BACKGROUND = auto()  # Lowest priority (e.g., cleanup tasks)


class LockType(Enum):
    """Types of locks for monitoring and logging purposes."""
    THREAD = auto()  # Threading lock
    ASYNCIO = auto()  # Asyncio lock
    SEMAPHORE = auto()  # Threading or asyncio semaphore
    RW_LOCK = auto()  # Read-write lock


class LockStatistics:
    """Track statistics for lock usage across the application."""

    def __init__(self):
        self._lock = threading.RLock()
        self.stats: Dict[str, Dict[str, Any]] = {}
        self.active_locks: Dict[str, Dict[str, Any]] = {}
        self.instance_locks_count = 0
        self.global_locks_count = 0
        self.successful_acquisitions = 0
        self.failed_acquisitions = 0

    def register_lock(self, lock_id: str, lock_name: str, lock_type: LockType,
                      priority: LockPriority, is_instance_lock: bool = False) -> None:
        """Register a new lock for statistics tracking."""
        with self._lock:
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
                "is_instance_lock": is_instance_lock
            }
            if is_instance_lock:
                self.instance_locks_count += 1
            else:
                self.global_locks_count += 1

    def record_acquisition(self, lock_id: str, thread_id: str, wait_time: float,
                           acquisition_time: float) -> None:
        """Record a successful lock acquisition."""
        with self._lock:
            self.successful_acquisitions += 1
            if lock_id in self.stats:
                stats = self.stats[lock_id]
                stats["acquisitions"] += 1
                stats["acquisition_time_total"] += acquisition_time
                stats["wait_time_total"] += wait_time
                stats["last_acquired"] = time.time()
                if wait_time > stats["wait_time_max"]:
                    stats["wait_time_max"] = wait_time
                self.active_locks[f"{lock_id}:{thread_id}"] = {
                    "acquired_at": time.time(),
                    "thread_id": thread_id
                }

    def record_release(self, lock_id: str, thread_id: str) -> None:
        """Record a lock release."""
        with self._lock:
            if lock_id in self.stats:
                self.stats[lock_id]["last_released"] = time.time()
                lock_key = f"{lock_id}:{thread_id}"
                if lock_key in self.active_locks:
                    del self.active_locks[lock_key]

    def record_timeout(self, lock_id: str) -> None:
        """Record a lock acquisition timeout."""
        with self._lock:
            self.failed_acquisitions += 1
            if lock_id in self.stats:
                self.stats[lock_id]["timeouts"] += 1

    def record_contention(self, lock_id: str) -> None:
        """Record a lock contention event (when a lock is already held)."""
        with self._lock:
            if lock_id in self.stats:
                self.stats[lock_id]["contentions"] += 1

    def get_lock_stats(self, lock_id: Optional[str] = None) -> Dict[str, Any]:
        """Get statistics for a specific lock or all locks."""
        with self._lock:
            if lock_id:
                return self.stats.get(lock_id, {}).copy()
            return {k: v.copy() for k, v in self.stats.items()}

    def get_active_locks(self) -> Dict[str, Dict[str, Any]]:
        """Get information about currently held locks."""
        with self._lock:
            return {k: v.copy() for k, v in self.active_locks.items()}

    def get_summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics about all locks."""
        with self._lock:
            return {
                "total_locks": len(self.stats),
                "instance_locks": self.instance_locks_count,
                "global_locks": self.global_locks_count,
                "active_locks": len(self.active_locks),
                "total_acquisitions": self.successful_acquisitions,
                "failed_acquisitions": self.failed_acquisitions,
                "success_rate": (self.successful_acquisitions /
                                 (self.successful_acquisitions + self.failed_acquisitions or 1)) * 100
            }

    def reset_stats(self, lock_id: Optional[str] = None) -> None:
        """Reset statistics for a specific lock or all locks."""
        with self._lock:
            if lock_id:
                if lock_id in self.stats:
                    created_at = self.stats[lock_id].get("created_at", time.time())
                    is_instance_lock = self.stats[lock_id].get("is_instance_lock", False)
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
                        "is_instance_lock": is_instance_lock
                    }
            else:
                self.successful_acquisitions = 0
                self.failed_acquisitions = 0
                for lock_id in self.stats:
                    self.reset_stats(lock_id)


# Global statistics tracker
lock_statistics = LockStatistics()


class LockManager:
    """
    Central lock manager to prevent deadlocks by enforcing lock hierarchy.

    Thread-specific lock acquisition order is tracked to detect potential deadlocks
    before they occur. The manager enforces that locks are acquired in order of
    decreasing priority to prevent circular wait conditions.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._thread_locks: Dict[int, List[Tuple[str, LockPriority]]] = {}
        self._wait_graph: Dict[str, Set[str]] = {}
        self._instance_locks: Dict[int, Set[str]] = {}

    def check_deadlock(self, lock_id: str, priority: LockPriority, is_instance_lock: bool = False) -> bool:
        """
        Check if acquiring this lock could cause a deadlock based on current locks held.

        Instance-level locks have a more relaxed hierarchy check to allow better concurrency.

        Returns:
            True if deadlock is possible, False otherwise.
        """
        thread_id = threading.get_ident()
        with self._lock:
            if thread_id not in self._thread_locks:
                self._thread_locks[thread_id] = []
                self._instance_locks[thread_id] = set()
                return False

            if is_instance_lock:
                self._instance_locks[thread_id].add(lock_id)
                return False

            current_locks = self._thread_locks[thread_id]
            for held_lock_id, held_priority in current_locks:
                if held_lock_id in self._instance_locks.get(thread_id, set()):
                    continue
                if priority.value < held_priority.value:
                    logger.warning(
                        f"Lock hierarchy violation detected: Attempting to acquire {lock_id} "
                        f"(priority {priority.name}) while holding {held_lock_id} "
                        f"(priority {held_priority.name})"
                    )
                    return True
            return False

    def register_lock_acquisition(self, lock_id: str, priority: LockPriority, is_instance_lock: bool = False) -> None:
        """Register that a thread has acquired a lock."""
        thread_id = threading.get_ident()
        with self._lock:
            if thread_id not in self._thread_locks:
                self._thread_locks[thread_id] = []
                self._instance_locks[thread_id] = set()
            self._thread_locks[thread_id].append((lock_id, priority))
            if is_instance_lock:
                self._instance_locks[thread_id].add(lock_id)

    def register_lock_release(self, lock_id: str, is_instance_lock: bool = False) -> None:
        """Register that a thread has released a lock."""
        thread_id = threading.get_ident()
        with self._lock:
            if thread_id in self._thread_locks:
                self._thread_locks[thread_id] = [
                    (l_id, prio) for l_id, prio in self._thread_locks[thread_id]
                    if l_id != lock_id
                ]
                if is_instance_lock and thread_id in self._instance_locks:
                    self._instance_locks[thread_id].discard(lock_id)
                if not self._thread_locks[thread_id]:
                    del self._thread_locks[thread_id]
                    if thread_id in self._instance_locks:
                        del self._instance_locks[thread_id]

    def clear_thread_data(self) -> None:
        """Clear lock data for the current thread (cleanup)."""
        thread_id = threading.get_ident()
        with self._lock:
            if thread_id in self._thread_locks:
                del self._thread_locks[thread_id]
            if thread_id in self._instance_locks:
                del self._instance_locks[thread_id]


# Global lock manager
lock_manager = LockManager()


def _prepare_lock_acquisition(timeout: Optional[float],
                              default_timeout: float,
                              lock,
                              owner,
                              lock_name: str,
                              identifier,
                              log,  # Renamed parameter to avoid shadowing outer logger
                              record_contention_callback,
                              use_locked: bool = False) -> Tuple[float, float]:
    """
    Prepare lock acquisition by determining the effective timeout and start time.
    Optionally logs contention if the lock is held by another thread or task.

    Args:
        timeout (Optional[float]): The provided timeout value.
        default_timeout (float): The default timeout to use if none is provided.
        lock: The lock object.
        owner: The current recorded owner of the lock.
        lock_name (str): Name of the lock.
        identifier: The current thread/task identifier.
        log: Logger instance for logging.
        record_contention_callback: Callback to record a contention event.
        use_locked (bool): If True, check using lock.locked(); otherwise rely on owner.

    Returns:
        Tuple containing the effective timeout and the wait start time.
    """
    effective_timeout = timeout if timeout is not None else default_timeout
    wait_start = time.time()
    if use_locked:
        if lock.locked() and owner != identifier:
            log.debug(f"Task {identifier} waiting for lock '{lock_name}' currently held by {owner}")
            record_contention_callback()
    else:
        if owner is not None and owner != identifier:
            log.debug(f"Thread {identifier} waiting for lock '{lock_name}' currently held by {owner}")
            record_contention_callback()
    return effective_timeout, wait_start


async def _async_acquire_with_timeout(acquire_coro, effective_timeout: float, type_str: str, name: str) -> Tuple[
    bool, float]:
    """
    Helper function to acquire an async lock or semaphore with a timeout.
    Returns a tuple of (acquired, wait_time).
    """
    start = time.time()
    try:
        await asyncio.wait_for(acquire_coro, timeout=effective_timeout)
        acquired = True
    except asyncio.TimeoutError:
        acquired = False
    except Exception as e:
        logger.error(f"Error acquiring {type_str} '{name}': {e}")
        acquired = False
    wait_time = time.time() - start
    return acquired, wait_time


class TimeoutLock:
    """
    Enhanced Lock implementation with timeout, detailed logging, and deadlock prevention.

    This lock builds on threading locks with timeout support and improved deadlock prevention via
    a lock hierarchy. It also records usage statistics.
    """

    def __init__(self, name: str, priority: LockPriority = LockPriority.MEDIUM,
                 timeout: Optional[float] = None, reentrant: bool = True,
                 is_instance_lock: bool = False):
        """
        Initialize a new TimeoutLock.

        Args:
            name (str): Name of the lock for logging and tracking.
            priority (LockPriority): Lock priority for deadlock prevention.
            timeout (Optional[float]): Timeout in seconds; if None, uses default.
            reentrant (bool): Whether the lock is reentrant.
            is_instance_lock (bool): Whether this is an instance-level lock.
        """
        self.name = name
        self.id = f"{name}_{uuid.uuid4().hex[:8]}"
        self.priority = priority
        self.default_timeout = timeout or DEFAULT_LOCK_TIMEOUT
        self.lock = threading.RLock() if reentrant else threading.Lock()
        self.owner: Optional[int] = None
        self.acquisition_count = 0
        self.is_instance_lock = is_instance_lock

        # Register this lock in the statistics tracker.
        lock_statistics.register_lock(self.id, name, LockType.THREAD, priority, is_instance_lock)

        logger.debug(f"Created lock '{name}' with ID {self.id} "
                     f"(priority={priority.name}, timeout={self.default_timeout}s, instance={is_instance_lock})")

    def acquire(self, blocking: bool = True, timeout: Optional[float] = None) -> bool:
        """
        Acquire the lock with a timeout and deadlock prevention.

        Args:
            blocking (bool): Whether to block until the lock is acquired.
            timeout (Optional[float]): Timeout override in seconds.

        Returns:
            bool: True if the lock was acquired; False otherwise.
        """
        thread_id = threading.get_ident()
        thread_name = threading.current_thread().name

        # Check for potential deadlock.
        if lock_manager.check_deadlock(self.id, self.priority, self.is_instance_lock):
            logger.warning(f"Thread {thread_name} avoiding potential deadlock; not acquiring lock '{self.name}'")
            lock_statistics.record_timeout(self.id)
            return False

        # Prepare acquisition: calculate effective timeout, record start time, and log contention.
        effective_timeout, wait_start = _prepare_lock_acquisition(
            timeout,
            self.default_timeout,
            self.lock,
            self.owner,
            self.name,
            thread_id,
            logger,
            lambda: lock_statistics.record_contention(self.id),
            use_locked=False
        )

        try:
            acquired = self.lock.acquire(blocking=blocking, timeout=effective_timeout if blocking else None)
        except Exception as e:
            logger.error(f"Error acquiring lock '{self.name}': {e}")
            lock_statistics.record_timeout(self.id)
            return False

        wait_time = time.time() - wait_start

        if acquired:
            self.owner = thread_id
            self.acquisition_count += 1
            lock_manager.register_lock_acquisition(self.id, self.priority, self.is_instance_lock)
            lock_statistics.record_acquisition(self.id, str(thread_id), wait_time, 0.0)
            logger.debug(f"Thread {thread_name} acquired lock '{self.name}' after {wait_time:.6f}s wait")
        else:
            lock_statistics.record_timeout(self.id)
            logger.warning(f"Thread {thread_name} failed to acquire lock '{self.name}' after {wait_time:.6f}s wait "
                           f"(timeout={effective_timeout}s)")

        return acquired

    def release(self) -> None:
        """
        Release the lock with logging. Errors during release are caught and logged.
        """
        thread_id = threading.get_ident()
        thread_name = threading.current_thread().name

        try:
            lock_statistics.record_release(self.id, str(thread_id))
            self.lock.release()
            # Use our owner tracking instead of accessing a protected member.
            if self.owner == thread_id:
                self.owner = None
            lock_manager.register_lock_release(self.id, self.is_instance_lock)
            logger.debug(f"Thread {thread_name} released lock '{self.name}'")
        except RuntimeError as e:
            logger.error(f"Error releasing lock '{self.name}': {e}")

    @contextmanager
    def acquire_timeout(self, timeout: Optional[float] = None) -> Generator[bool, Any, None]:
        """
        Context manager for acquiring the lock with a timeout.

        Args:
            timeout (Optional[float]): Timeout override in seconds.

        Yields:
            bool: True if the lock was acquired, False otherwise.
        """
        acquired = self.acquire(timeout=timeout)
        try:
            yield acquired
        finally:
            if acquired:
                self.release()


class AsyncTimeoutLock:
    """
    Enhanced asyncio.Lock implementation with timeout, detailed logging, and deadlock prevention.

    This asynchronous lock provides similar functionality to TimeoutLock but is designed for asyncio.
    """

    def __init__(self, name: str, priority: LockPriority = LockPriority.MEDIUM,
                 timeout: Optional[float] = None, is_instance_lock: bool = False):
        """
        Initialize a new AsyncTimeoutLock.

        Args:
            name (str): Name of the lock for logging and tracking.
            priority (LockPriority): Lock priority for deadlock prevention.
            timeout (Optional[float]): Timeout in seconds; if None, uses default.
            is_instance_lock (bool): Whether this is an instance-level lock.
        """
        self.name = name
        self.id = f"{name}_{uuid.uuid4().hex[:8]}"
        self.priority = priority
        self.default_timeout = timeout or DEFAULT_ASYNC_LOCK_TIMEOUT
        self.lock = asyncio.Lock()
        self.owner: Optional[str] = None
        self.is_instance_lock = is_instance_lock

        # Register this async lock in the statistics tracker.
        lock_statistics.register_lock(self.id, name, LockType.ASYNCIO, priority, is_instance_lock)

        logger.debug(f"Created async lock '{name}' with ID {self.id} "
                     f"(priority={priority.name}, timeout={self.default_timeout}s, instance={is_instance_lock})")

    async def acquire(self, timeout: Optional[float] = None) -> bool:
        """
        Acquire the async lock with timeout and deadlock prevention.

        Args:
            timeout (Optional[float]): Timeout override in seconds.

        Returns:
            bool: True if the lock was acquired, False otherwise.
        """
        # Build a unique identifier for the current async task.
        thread_id = f"{threading.get_ident()}:{id(asyncio.current_task())}"
        task_name = asyncio.current_task().get_name() if asyncio.current_task() else "unknown"

        effective_timeout, _ = _prepare_lock_acquisition(
            timeout,
            self.default_timeout,
            self.lock,
            self.owner,
            self.name,
            thread_id,
            logger,
            lambda: lock_statistics.record_contention(self.id),
            use_locked=True
        )

        acquired, wait_time = await _async_acquire_with_timeout(
            self.lock.acquire(), effective_timeout, "async lock", self.name
        )

        if acquired:
            self.owner = thread_id
            lock_statistics.record_acquisition(self.id, thread_id, wait_time, 0.0)
            logger.debug(f"Task {task_name} acquired async lock '{self.name}' after {wait_time:.6f}s wait")
        else:
            lock_statistics.record_timeout(self.id)
            logger.warning(f"Task {task_name} failed to acquire async lock '{self.name}' after {wait_time:.6f}s wait "
                           f"(timeout={effective_timeout}s)")

        return acquired

    def release(self) -> None:
        """
        Release the async lock with logging. Errors during release are caught and logged.
        """
        thread_id = f"{threading.get_ident()}:{id(asyncio.current_task())}"
        task_name = asyncio.current_task().get_name() if asyncio.current_task() else "unknown"

        try:
            lock_statistics.record_release(self.id, thread_id)
            self.lock.release()
            self.owner = None
            logger.debug(f"Task {task_name} released async lock '{self.name}'")
        except RuntimeError as e:
            logger.error(f"Error releasing async lock '{self.name}': {e}")

    @asynccontextmanager
    async def acquire_timeout(self, timeout: Optional[float] = None) -> AsyncGenerator[bool, None]:
        """
        Async context manager for acquiring the lock with a timeout.

        Args:
            timeout (Optional[float]): Timeout override in seconds.

        Yields:
            bool: True if the lock was acquired, False otherwise.
        """
        acquired = await self.acquire(timeout=timeout)
        try:
            yield acquired
        finally:
            if acquired:
                self.release()


class AsyncTimeoutSemaphore:
    """
    Enhanced asyncio.Semaphore implementation with timeout, logging, and deadlock prevention.

    This semaphore is optimized for batch operations with improved concurrency control.
    """

    def __init__(self, name: str, value: int = 1,
                 priority: LockPriority = LockPriority.MEDIUM,
                 timeout: Optional[float] = None):
        """
        Initialize a new AsyncTimeoutSemaphore.

        Args:
            name (str): Name of the semaphore for logging and tracking.
            value (int): Initial permit count.
            priority (LockPriority): Semaphore priority for deadlock prevention.
            timeout (Optional[float]): Timeout in seconds; if None, uses default.
        """
        self.name = name
        self.id = f"{name}_{uuid.uuid4().hex[:8]}"
        self.priority = priority
        self.default_timeout = timeout or DEFAULT_ASYNC_LOCK_TIMEOUT
        self.semaphore = asyncio.Semaphore(value)
        self.value = value
        self.current_value = value
        self._value_lock = asyncio.Lock()

        # Always mark semaphore as instance lock.
        lock_statistics.register_lock(self.id, name, LockType.SEMAPHORE, priority, is_instance_lock=True)

        logger.debug(f"Created async semaphore '{name}' with ID {self.id} and value {value} "
                     f"(priority={priority.name}, timeout={self.default_timeout}s)")

    async def acquire(self, timeout: Optional[float] = None) -> bool:
        """
        Acquire the semaphore with a timeout.

        Args:
            timeout (Optional[float]): Timeout override in seconds.

        Returns:
            bool: True if the semaphore was acquired; False otherwise.
        """
        thread_id = f"{threading.get_ident()}:{id(asyncio.current_task())}"
        task_name = asyncio.current_task().get_name() if asyncio.current_task() else "unknown"
        effective_timeout = timeout if timeout is not None else self.default_timeout

        acquired, wait_time = await _async_acquire_with_timeout(
            self.semaphore.acquire(), effective_timeout, "async semaphore", self.name
        )

        if acquired:
            async with self._value_lock:
                self.current_value -= 1
            lock_statistics.record_acquisition(self.id, thread_id, wait_time, 0.0)
            logger.debug(f"Task {task_name} acquired async semaphore '{self.name}' after {wait_time:.6f}s wait "
                         f"(remaining permits: {self.current_value})")
        else:
            lock_statistics.record_timeout(self.id)
            logger.warning(
                f"Task {task_name} failed to acquire async semaphore '{self.name}' after {wait_time:.6f}s wait "
                f"(timeout={effective_timeout}s)")

        return acquired

    def release(self) -> None:
        """
        Release the semaphore with logging. Errors during release are caught and logged.
        """
        thread_id = f"{threading.get_ident()}:{id(asyncio.current_task())}"
        task_name = asyncio.current_task().get_name() if asyncio.current_task() else "unknown"
        try:
            lock_statistics.record_release(self.id, thread_id)
            self.semaphore.release()
            self.current_value += 1
            if self.current_value > self.value:
                self.current_value = self.value
            logger.debug(f"Task {task_name} released async semaphore '{self.name}' "
                         f"(available permits: {self.current_value})")
        except Exception as e:
            logger.error(f"Error releasing async semaphore '{self.name}': {e}")

    @asynccontextmanager
    async def acquire_timeout(self, timeout: Optional[float] = None) -> AsyncGenerator[bool, None]:
        """
        Async context manager for acquiring the semaphore with a timeout.

        Args:
            timeout (Optional[float]): Timeout override in seconds.

        Yields:
            bool: True if the semaphore was acquired, False otherwise.
        """
        acquired = await self.acquire(timeout=timeout)
        try:
            yield acquired
        finally:
            if acquired:
                self.release()


def init():
    """Initialize the synchronization module (sets up logging)."""
    module_logger = logging.getLogger(__name__)
    if not module_logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        module_logger.addHandler(handler)
        module_logger.setLevel(logging.INFO)
    logger.info("Synchronization utils initialized")


# Initialize module when imported.
init()
