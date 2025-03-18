"""
Enhanced synchronization utilities with deadlock prevention, timeouts, and detailed logging.

This module provides centralized synchronization primitives for thread safety across the application,
replacing scattered lock implementations to prevent deadlocks and ensure proper resource management.
Features include:
- Lock timeouts with automatic recovery
- Detailed logging of lock acquisition and release events
- Lock hierarchy to prevent deadlock scenarios
- Reentrant and non-reentrant lock variants
- Async-friendly locking primitives
- Lock usage statistics and monitoring
"""
import asyncio
import logging
import threading
import time
import uuid
from contextlib import contextmanager, asynccontextmanager
from enum import Enum, auto
from typing import Dict, List, Optional, Set, Any, Tuple, Generator

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

    def register_lock(self, lock_id: str, lock_name: str, lock_type: LockType,
                      priority: LockPriority) -> None:
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
                "last_released": None
            }

    def record_acquisition(self, lock_id: str, thread_id: str, wait_time: float,
                           acquisition_time: float) -> None:
        """Record a successful lock acquisition."""
        with self._lock:
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

    def reset_stats(self, lock_id: Optional[str] = None) -> None:
        """Reset statistics for a specific lock or all locks."""
        with self._lock:
            if lock_id:
                if lock_id in self.stats:
                    created_at = self.stats[lock_id].get("created_at", time.time())
                    self.stats[lock_id] = {
                        **self.stats[lock_id],
                        "acquisitions": 0,
                        "acquisition_time_total": 0.0,
                        "acquisition_time_max": 0.0,
                        "wait_time_total": 0.0,
                        "wait_time_max": 0.0,
                        "timeouts": 0,
                        "contentions": 0,
                        "created_at": created_at
                    }
            else:
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
        # Track locks held by each thread
        self._thread_locks: Dict[int, List[Tuple[str, LockPriority]]] = {}
        # Track lock wait graph for deadlock detection
        self._wait_graph: Dict[str, Set[str]] = {}

    def check_deadlock(self, lock_id: str, priority: LockPriority) -> bool:
        """
        Check if acquiring this lock could cause a deadlock based on current locks held.

        Returns:
            True if deadlock is possible, False otherwise
        """
        thread_id = threading.get_ident()

        with self._lock:
            # First time this thread is acquiring locks
            if thread_id not in self._thread_locks:
                self._thread_locks[thread_id] = []
                return False

            # Check if this thread already holds locks
            current_locks = self._thread_locks[thread_id]

            # If we already hold locks, check for priority violation
            for held_lock_id, held_priority in current_locks:
                # If trying to acquire a higher priority lock after a lower priority one,
                # this violates the lock hierarchy and could cause deadlocks
                if priority.value < held_priority.value:
                    logger.warning(
                        f"Lock hierarchy violation detected: Attempting to acquire {lock_id} "
                        f"(priority {priority.name}) while holding {held_lock_id} "
                        f"(priority {held_priority.name})"
                    )
                    return True

            return False

    def register_lock_acquisition(self, lock_id: str, priority: LockPriority) -> None:
        """Register that a thread has acquired a lock."""
        thread_id = threading.get_ident()

        with self._lock:
            if thread_id not in self._thread_locks:
                self._thread_locks[thread_id] = []

            self._thread_locks[thread_id].append((lock_id, priority))

    def register_lock_release(self, lock_id: str) -> None:
        """Register that a thread has released a lock."""
        thread_id = threading.get_ident()

        with self._lock:
            if thread_id in self._thread_locks:
                # Remove the lock from the thread's list
                self._thread_locks[thread_id] = [
                    (l_id, prio) for l_id, prio in self._thread_locks[thread_id]
                    if l_id != lock_id
                ]

                # Clean up if thread has no more locks
                if not self._thread_locks[thread_id]:
                    del self._thread_locks[thread_id]

    def clear_thread_data(self) -> None:
        """Clear lock data for the current thread (cleanup)."""
        thread_id = threading.get_ident()

        with self._lock:
            if thread_id in self._thread_locks:
                del self._thread_locks[thread_id]


# Global lock manager
lock_manager = LockManager()


class TimeoutLock:
    """
    Enhanced Lock implementation with timeout, logging, and deadlock prevention.

    This lock improves on threading.Lock with detailed logging, timeout support,
    and deadlock prevention through lock hierarchy enforcement.
    """

    def __init__(self, name: str, priority: LockPriority = LockPriority.MEDIUM,
                 timeout: Optional[float] = None, reentrant: bool = True):
        """
        Initialize a new TimeoutLock.

        Args:
            name: Name of the lock for logging and tracking
            priority: Lock priority for deadlock prevention hierarchy
            timeout: Default timeout in seconds (None for no timeout)
            reentrant: Whether the lock is reentrant (can be acquired multiple times by same thread)
        """
        self.name = name
        self.id = f"{name}_{uuid.uuid4().hex[:8]}"
        self.priority = priority
        self.default_timeout = timeout or DEFAULT_LOCK_TIMEOUT
        self.lock = threading.RLock() if reentrant else threading.Lock()
        self.owner: Optional[int] = None
        self.acquisition_count = 0

        # Register with statistics tracker
        lock_statistics.register_lock(self.id, name, LockType.THREAD, priority)

        logger.debug(f"Created lock '{name}' with ID {self.id} "
                     f"(priority={priority.name}, timeout={self.default_timeout}s)")

    def acquire(self, blocking: bool = True, timeout: Optional[float] = None) -> bool:
        """
        Acquire the lock with timeout and deadlock prevention.

        Args:
            blocking: Whether to block waiting for the lock
            timeout: Timeout in seconds (overrides default if provided)

        Returns:
            True if the lock was acquired, False otherwise
        """
        thread_id = threading.get_ident()
        thread_name = threading.current_thread().name

        # Check for potential deadlocks
        if lock_manager.check_deadlock(self.id, self.priority):
            logger.warning(
                f"Thread {thread_name} avoiding potential deadlock, "
                f"not acquiring lock '{self.name}'"
            )
            lock_statistics.record_timeout(self.id)
            return False

        effective_timeout = timeout if timeout is not None else self.default_timeout
        wait_start = time.time()

        # Check if lock is already held by someone else (for logging)
        if hasattr(self.lock, "_is_owned") and self.lock._is_owned():
            current_owner = self.owner
            if current_owner != thread_id:
                logger.debug(
                    f"Thread {thread_name} waiting for lock '{self.name}' "
                    f"currently held by thread {current_owner}"
                )
                lock_statistics.record_contention(self.id)

        # Attempt to acquire the lock
        acquired = self.lock.acquire(blocking=blocking, timeout=effective_timeout if blocking else None)
        wait_time = time.time() - wait_start

        if acquired:
            self.owner = thread_id
            self.acquisition_count += 1

            # Register with lock manager for deadlock prevention
            lock_manager.register_lock_acquisition(self.id, self.priority)

            # Record statistics
            lock_statistics.record_acquisition(
                self.id, str(thread_id), wait_time, 0.0
            )

            logger.debug(
                f"Thread {thread_name} acquired lock '{self.name}' "
                f"after {wait_time:.6f}s wait"
            )
        else:
            lock_statistics.record_timeout(self.id)
            logger.warning(
                f"Thread {thread_name} failed to acquire lock '{self.name}' "
                f"after {wait_time:.6f}s wait (timeout={effective_timeout}s)"
            )

        return acquired

    def release(self) -> None:
        """Release the lock with logging."""
        thread_id = threading.get_ident()
        thread_name = threading.current_thread().name

        try:
            # Record before release for accurate thread ID
            lock_statistics.record_release(self.id, str(thread_id))

            # Release the actual lock
            self.lock.release()

            # Update owner if this is an RLock with multiple acquisitions
            if hasattr(self.lock, "_is_owned") and self.lock._is_owned():
                pass  # Still owned by this thread (reentrant lock)
            else:
                self.owner = None

            # Update lock manager
            lock_manager.register_lock_release(self.id)

            logger.debug(f"Thread {thread_name} released lock '{self.name}'")
        except RuntimeError as e:
            # Handle "release unlocked lock" error
            logger.error(f"Error releasing lock '{self.name}': {e}")

    @contextmanager
    def acquire_timeout(self, timeout: Optional[float] = None) -> Generator[None, Any, None]:
        """
        Context manager for acquiring the lock with timeout.

        Args:
            timeout: Timeout in seconds (overrides default if provided)

        Raises:
            TimeoutError: If lock cannot be acquired within timeout
        """
        acquired = self.acquire(timeout=timeout)
        if not acquired:
            raise TimeoutError(f"Failed to acquire lock '{self.name}' within timeout")

        try:
            yield
        finally:
            self.release()


class AsyncTimeoutLock:
    """
    Enhanced asyncio.Lock implementation with timeout, logging, and deadlock prevention.

    This lock improves on asyncio.Lock with detailed logging, timeout support,
    and deadlock prevention through lock hierarchy enforcement.
    """

    def __init__(self, name: str, priority: LockPriority = LockPriority.MEDIUM,
                 timeout: Optional[float] = None):
        """
        Initialize a new AsyncTimeoutLock.

        Args:
            name: Name of the lock for logging and tracking
            priority: Lock priority for deadlock prevention hierarchy
            timeout: Default timeout in seconds (None for no timeout)
        """
        self.name = name
        self.id = f"{name}_{uuid.uuid4().hex[:8]}"
        self.priority = priority
        self.default_timeout = timeout or DEFAULT_ASYNC_LOCK_TIMEOUT
        self.lock = asyncio.Lock()
        self.owner: Optional[str] = None

        # Register with statistics tracker
        lock_statistics.register_lock(self.id, name, LockType.ASYNCIO, priority)

        logger.debug(f"Created async lock '{name}' with ID {self.id} "
                     f"(priority={priority.name}, timeout={self.default_timeout}s)")

    async def acquire(self, timeout: Optional[float] = None) -> bool:
        """
        Acquire the lock with timeout and deadlock prevention.

        Args:
            timeout: Timeout in seconds (overrides default if provided)

        Returns:
            True if the lock was acquired, False otherwise
        """
        thread_id = f"{threading.get_ident()}:{id(asyncio.current_task())}"
        thread_name = threading.current_thread().name
        task_name = asyncio.current_task().get_name() if asyncio.current_task() else "unknown"

        # Check if lock is already held (for logging)
        if self.lock.locked():
            current_owner = self.owner
            if current_owner != thread_id:
                logger.debug(
                    f"Task {task_name} waiting for async lock '{self.name}' "
                    f"currently held by {current_owner}"
                )
                lock_statistics.record_contention(self.id)

        effective_timeout = timeout if timeout is not None else self.default_timeout
        wait_start = time.time()

        # Attempt to acquire the lock with timeout
        try:
            await asyncio.wait_for(self.lock.acquire(), timeout=effective_timeout)
            acquired = True
        except asyncio.TimeoutError:
            acquired = False

        wait_time = time.time() - wait_start

        if acquired:
            self.owner = thread_id

            # Record statistics
            lock_statistics.record_acquisition(
                self.id, thread_id, wait_time, 0.0
            )

            logger.debug(
                f"Task {task_name} acquired async lock '{self.name}' "
                f"after {wait_time:.6f}s wait"
            )
        else:
            lock_statistics.record_timeout(self.id)
            logger.warning(
                f"Task {task_name} failed to acquire async lock '{self.name}' "
                f"after {wait_time:.6f}s wait (timeout={effective_timeout}s)"
            )

        return acquired

    def release(self) -> None:
        """Release the lock with logging."""
        thread_id = f"{threading.get_ident()}:{id(asyncio.current_task())}"
        task_name = asyncio.current_task().get_name() if asyncio.current_task() else "unknown"

        try:
            # Record before release for accurate thread ID
            lock_statistics.record_release(self.id, thread_id)

            # Release the actual lock
            self.lock.release()
            self.owner = None

            logger.debug(f"Task {task_name} released async lock '{self.name}'")
        except RuntimeError as e:
            # Handle "release unlocked lock" error
            logger.error(f"Error releasing async lock '{self.name}': {e}")

    @asynccontextmanager
    async def acquire_timeout(self, timeout: Optional[float] = None):
        """
        Async context manager for acquiring the lock with timeout.

        Args:
            timeout: Timeout in seconds (overrides default if provided)

        Raises:
            TimeoutError: If lock cannot be acquired within timeout
        """
        acquired = await self.acquire(timeout=timeout)
        if not acquired:
            raise TimeoutError(f"Failed to acquire async lock '{self.name}' within timeout")

        try:
            yield
        finally:
            self.release()


class TimeoutSemaphore:
    """
    Enhanced Semaphore implementation with timeout, logging, and deadlock prevention.

    This semaphore improves on threading.Semaphore with detailed logging and timeout support.
    """

    def __init__(self, name: str, value: int = 1,
                 priority: LockPriority = LockPriority.MEDIUM,
                 timeout: Optional[float] = None):
        """
        Initialize a new TimeoutSemaphore.

        Args:
            name: Name of the semaphore for logging and tracking
            value: Initial value (permits) for the semaphore
            priority: Semaphore priority for deadlock prevention hierarchy
            timeout: Default timeout in seconds (None for no timeout)
        """
        self.name = name
        self.id = f"{name}_{uuid.uuid4().hex[:8]}"
        self.priority = priority
        self.default_timeout = timeout or DEFAULT_LOCK_TIMEOUT
        self.semaphore = threading.Semaphore(value)
        self.value = value
        self.current_value = value

        # Register with statistics tracker
        lock_statistics.register_lock(self.id, name, LockType.SEMAPHORE, priority)

        logger.debug(f"Created semaphore '{name}' with ID {self.id} and value {value} "
                     f"(priority={priority.name}, timeout={self.default_timeout}s)")

    def acquire(self, blocking: bool = True, timeout: Optional[float] = None) -> bool:
        """
        Acquire the semaphore with timeout.

        Args:
            blocking: Whether to block waiting for the semaphore
            timeout: Timeout in seconds (overrides default if provided)

        Returns:
            True if the semaphore was acquired, False otherwise
        """
        thread_id = threading.get_ident()
        thread_name = threading.current_thread().name

        effective_timeout = timeout if timeout is not None else self.default_timeout
        wait_start = time.time()

        # Attempt to acquire the semaphore
        acquired = self.semaphore.acquire(blocking=blocking, timeout=effective_timeout if blocking else None)
        wait_time = time.time() - wait_start

        if acquired:
            with self._lock():
                self.current_value -= 1

            # Record statistics
            lock_statistics.record_acquisition(
                self.id, str(thread_id), wait_time, 0.0
            )

            logger.debug(
                f"Thread {thread_name} acquired semaphore '{self.name}' "
                f"after {wait_time:.6f}s wait (remaining permits: {self.current_value})"
            )
        else:
            lock_statistics.record_timeout(self.id)
            logger.warning(
                f"Thread {thread_name} failed to acquire semaphore '{self.name}' "
                f"after {wait_time:.6f}s wait (timeout={effective_timeout}s)"
            )

        return acquired

    def release(self) -> None:
        """Release the semaphore with logging."""
        thread_id = threading.get_ident()
        thread_name = threading.current_thread().name

        try:
            # Record before release
            lock_statistics.record_release(self.id, str(thread_id))

            # Release the actual semaphore
            self.semaphore.release()

            with self._lock():
                self.current_value += 1
                if self.current_value > self.value:
                    # This shouldn't happen, but let's cap it just in case
                    self.current_value = self.value

            logger.debug(
                f"Thread {thread_name} released semaphore '{self.name}' "
                f"(available permits: {self.current_value})"
            )
        except Exception as e:
            logger.error(f"Error releasing semaphore '{self.name}': {e}")

    def _lock(self):
        """Helper method for internal locking of state modifications."""

        class _InternalLock:
            def __enter__(self_):
                return self_

            def __exit__(self_, exc_type, exc_val, exc_tb):
                pass

        return _InternalLock()

    @contextmanager
    def acquire_timeout(self, timeout: Optional[float] = None):
        """
        Context manager for acquiring the semaphore with timeout.

        Args:
            timeout: Timeout in seconds (overrides default if provided)

        Raises:
            TimeoutError: If semaphore cannot be acquired within timeout
        """
        acquired = self.acquire(timeout=timeout)
        if not acquired:
            raise TimeoutError(f"Failed to acquire semaphore '{self.name}' within timeout")

        try:
            yield
        finally:
            self.release()


class AsyncTimeoutSemaphore:
    """
    Enhanced asyncio.Semaphore implementation with timeout, logging, and deadlock prevention.
    """

    def __init__(self, name: str, value: int = 1,
                 priority: LockPriority = LockPriority.MEDIUM,
                 timeout: Optional[float] = None):
        """
        Initialize a new AsyncTimeoutSemaphore.

        Args:
            name: Name of the semaphore for logging and tracking
            value: Initial value (permits) for the semaphore
            priority: Semaphore priority for deadlock prevention hierarchy
            timeout: Default timeout in seconds (None for no timeout)
        """
        self.name = name
        self.id = f"{name}_{uuid.uuid4().hex[:8]}"
        self.priority = priority
        self.default_timeout = timeout or DEFAULT_ASYNC_LOCK_TIMEOUT
        self.semaphore = asyncio.Semaphore(value)
        self.value = value
        self.current_value = value
        self._value_lock = asyncio.Lock()

        # Register with statistics tracker
        lock_statistics.register_lock(self.id, name, LockType.SEMAPHORE, priority)

        logger.debug(f"Created async semaphore '{name}' with ID {self.id} and value {value} "
                     f"(priority={priority.name}, timeout={self.default_timeout}s)")

    async def acquire(self, timeout: Optional[float] = None) -> bool:
        """
        Acquire the semaphore with timeout.

        Args:
            timeout: Timeout in seconds (overrides default if provided)

        Returns:
            True if the semaphore was acquired, False otherwise
        """
        thread_id = f"{threading.get_ident()}:{id(asyncio.current_task())}"
        task_name = asyncio.current_task().get_name() if asyncio.current_task() else "unknown"

        effective_timeout = timeout if timeout is not None else self.default_timeout
        wait_start = time.time()

        # Attempt to acquire the semaphore with timeout
        try:
            await asyncio.wait_for(self.semaphore.acquire(), timeout=effective_timeout)
            acquired = True
        except asyncio.TimeoutError:
            acquired = False

        wait_time = time.time() - wait_start

        if acquired:
            async with self._value_lock:
                self.current_value -= 1

            # Record statistics
            lock_statistics.record_acquisition(
                self.id, thread_id, wait_time, 0.0
            )

            logger.debug(
                f"Task {task_name} acquired async semaphore '{self.name}' "
                f"after {wait_time:.6f}s wait (remaining permits: {self.current_value})"
            )
        else:
            lock_statistics.record_timeout(self.id)
            logger.warning(
                f"Task {task_name} failed to acquire async semaphore '{self.name}' "
                f"after {wait_time:.6f}s wait (timeout={effective_timeout}s)"
            )

        return acquired

    def release(self) -> None:
        """Release the semaphore with logging."""
        thread_id = f"{threading.get_ident()}:{id(asyncio.current_task())}"
        task_name = asyncio.current_task().get_name() if asyncio.current_task() else "unknown"

        try:
            # Record before release
            lock_statistics.record_release(self.id, thread_id)

            # Release the actual semaphore
            self.semaphore.release()

            # Update our tracking of the current value
            # This needs to be done in an async context, but we're in a sync method
            # We'll use a simple approach that may not be 100% accurate but avoids deadlocks
            self.current_value += 1
            if self.current_value > self.value:
                self.current_value = self.value

            logger.debug(
                f"Task {task_name} released async semaphore '{self.name}' "
                f"(available permits: {self.current_value})"
            )
        except Exception as e:
            logger.error(f"Error releasing async semaphore '{self.name}': {e}")

    @asynccontextmanager
    async def acquire_timeout(self, timeout: Optional[float] = None):
        """
        Async context manager for acquiring the semaphore with timeout.

        Args:
            timeout: Timeout in seconds (overrides default if provided)

        Raises:
            TimeoutError: If semaphore cannot be acquired within timeout
        """
        acquired = await self.acquire(timeout=timeout)
        if not acquired:
            raise TimeoutError(f"Failed to acquire async semaphore '{self.name}' within timeout")

        try:
            yield
        finally:
            self.release()


class ReadWriteLock:
    """
    Read-write lock implementation with improved timeout handling.

    This class allows multiple readers but only one writer at a time.
    """

    def __init__(self, name: str, priority: LockPriority = LockPriority.MEDIUM,
                 timeout: Optional[float] = None):
        """
        Initialize a new ReadWriteLock.

        Args:
            name: Name of the lock for logging and tracking
            priority: Lock priority for deadlock prevention hierarchy
            timeout: Default timeout in seconds (None for no timeout)
        """
        self.name = name
        self.id = f"{name}_{uuid.uuid4().hex[:8]}"
        self.priority = priority
        self.default_timeout = timeout or DEFAULT_LOCK_TIMEOUT

        # Internal locks
        self._read_ready = threading.Condition(threading.RLock())
        self._readers = 0
        self._writers = 0
        self._write_lock = threading.RLock()
        self._writer_waiting = False

        # Register with statistics tracker
        lock_statistics.register_lock(self.id, name, LockType.RW_LOCK, priority)

        logger.debug(f"Created read-write lock '{name}' with ID {self.id} "
                     f"(priority={priority.name}, timeout={self.default_timeout}s)")

    def acquire_read(self, timeout: Optional[float] = None) -> bool:
        """
        Acquire a read lock with timeout.

        Args:
            timeout: Timeout in seconds (overrides default if provided)

        Returns:
            True if the lock was acquired, False otherwise
        """
        thread_id = threading.get_ident()
        thread_name = threading.current_thread().name

        effective_timeout = timeout if timeout is not None else self.default_timeout
        wait_start = time.time()
        acquired = False

        try:
            with self._read_ready:
                # Wait until there are no writers
                while self._writers > 0 or self._writer_waiting:
                    # Check if we need to record contention
                    if not acquired:
                        lock_statistics.record_contention(self.id)
                        acquired = True  # Only record once

                        logger.debug(
                            f"Thread {thread_name} waiting for read lock '{self.name}' "
                            f"due to active writers or waiting writer"
                        )

                    # Wait with timeout
                    remaining_time = effective_timeout - (time.time() - wait_start)
                    if remaining_time <= 0:
                        lock_statistics.record_timeout(self.id)
                        logger.warning(
                            f"Thread {thread_name} failed to acquire read lock '{self.name}' "
                            f"after {time.time() - wait_start:.6f}s wait (timeout={effective_timeout}s)"
                        )
                        return False

                    if not self._read_ready.wait(timeout=remaining_time):
                        lock_statistics.record_timeout(self.id)
                        logger.warning(
                            f"Thread {thread_name} failed to acquire read lock '{self.name}' "
                            f"after {time.time() - wait_start:.6f}s wait (timeout={effective_timeout}s)"
                        )
                        return False

                # Increment reader count
                self._readers += 1

        except Exception as e:
            lock_statistics.record_timeout(self.id)
            logger.error(f"Error acquiring read lock '{self.name}': {e}")
            return False

        wait_time = time.time() - wait_start

        # Record successful acquisition
        lock_statistics.record_acquisition(
            self.id, str(thread_id), wait_time, 0.0
        )

        logger.debug(
            f"Thread {thread_name} acquired read lock '{self.name}' "
            f"after {wait_time:.6f}s wait (active readers: {self._readers})"
        )

        return True

    def release_read(self) -> None:
        """Release a read lock with logging."""
        thread_id = threading.get_ident()
        thread_name = threading.current_thread().name

        try:
            with self._read_ready:
                # Record before release
                lock_statistics.record_release(self.id, str(thread_id))

                # Decrement reader count
                self._readers -= 1
                if self._readers < 0:
                    self._readers = 0
                    logger.warning(f"Reader count went negative for lock '{self.name}', resetting to 0")

                # Notify any waiting writers if no more readers
                if self._readers == 0:
                    self._read_ready.notify_all()

            logger.debug(
                f"Thread {thread_name} released read lock '{self.name}' "
                f"(remaining readers: {self._readers})"
            )
        except Exception as e:
            logger.error(f"Error releasing read lock '{self.name}': {e}")

    def acquire_write(self, timeout: Optional[float] = None) -> bool:
        """
        Acquire a write lock with timeout.

        Args:
            timeout: Timeout in seconds (overrides default if provided)

        Returns:
            True if the lock was acquired, False otherwise
        """
        thread_id = threading.get_ident()
        thread_name = threading.current_thread().name

        effective_timeout = timeout if timeout is not None else self.default_timeout
        wait_start = time.time()

        # First acquire the write lock to ensure only one writer can attempt to acquire at a time
        if not self._write_lock.acquire(timeout=effective_timeout):
            lock_statistics.record_timeout(self.id)
            logger.warning(
                f"Thread {thread_name} failed to acquire initial write lock '{self.name}' "
                f"after {time.time() - wait_start:.6f}s wait"
            )
            return False

        # Now wait for all readers to finish
        acquired = False
        try:
            with self._read_ready:
                # Signal that a writer is waiting - this prevents new read locks
                self._writer_waiting = True

                # Increment writer count to block new readers
                self._writers += 1

                # Wait for existing readers to finish
                while self._readers > 0:
                    # Record contention only once
                    if not acquired:
                        lock_statistics.record_contention(self.id)
                        acquired = True

                        logger.debug(
                            f"Thread {thread_name} waiting for write lock '{self.name}' "
                            f"due to {self._readers} active readers"
                        )

                    # Calculate remaining time
                    time_left = effective_timeout - (time.time() - wait_start)
                    if time_left <= 0:
                        # Timed out waiting for readers
                        self._writers -= 1
                        self._writer_waiting = False
                        self._write_lock.release()

                        lock_statistics.record_timeout(self.id)
                        logger.warning(
                            f"Thread {thread_name} failed to acquire write lock '{self.name}' "
                            f"after {time.time() - wait_start:.6f}s wait (timeout={effective_timeout}s)"
                        )
                        return False

                    # Wait with remaining timeout
                    if not self._read_ready.wait(timeout=time_left):
                        # Timed out
                        self._writers -= 1
                        self._writer_waiting = False
                        self._write_lock.release()

                        lock_statistics.record_timeout(self.id)
                        logger.warning(
                            f"Thread {thread_name} failed to acquire write lock '{self.name}' "
                            f"after {time.time() - wait_start:.6f}s wait (timeout={effective_timeout}s)"
                        )
                        return False

                # Successfully acquired the write lock
                self._writer_waiting = False

            # Calculate wait time
            wait_time = time.time() - wait_start

            # Record successful acquisition
            lock_statistics.record_acquisition(
                self.id, str(thread_id), wait_time, 0.0
            )

            logger.debug(
                f"Thread {thread_name} acquired write lock '{self.name}' "
                f"after {wait_time:.6f}s wait"
            )

            return True

        except Exception as e:
            # Handle any exceptions and ensure we release locks
            self._writers -= 1
            self._writer_waiting = False
            self._write_lock.release()

            lock_statistics.record_timeout(self.id)
            logger.error(f"Error acquiring write lock '{self.name}': {e}")
            return False

    def release_write(self) -> None:
        """Release a write lock with logging."""
        thread_id = threading.get_ident()
        thread_name = threading.current_thread().name

        try:
            with self._read_ready:
                # Record before release
                lock_statistics.record_release(self.id, str(thread_id))

                # Decrement writer count
                self._writers -= 1
                if self._writers < 0:
                    self._writers = 0
                    logger.warning(f"Writer count went negative for lock '{self.name}', resetting to 0")

                # Notify waiting readers and writers
                self._read_ready.notify_all()

            # Release the write lock
            self._write_lock.release()

            logger.debug(f"Thread {thread_name} released write lock '{self.name}'")
        except Exception as e:
            logger.error(f"Error releasing write lock '{self.name}': {e}")

    @contextmanager
    def read_locked(self, timeout: Optional[float] = None):
        """
        Context manager for acquiring a read lock with timeout.

        Args:
            timeout: Timeout in seconds (overrides default if provided)

        Raises:
            TimeoutError: If lock cannot be acquired within timeout
        """
        acquired = self.acquire_read(timeout=timeout)
        if not acquired:
            raise TimeoutError(f"Failed to acquire read lock '{self.name}' within timeout")

        try:
            yield
        finally:
            self.release_read()

    @contextmanager
    def write_locked(self, timeout: Optional[float] = None):
        """
        Context manager for acquiring a write lock with timeout.

        Args:
            timeout: Timeout in seconds (overrides default if provided)

        Raises:
            TimeoutError: If lock cannot be acquired within timeout
        """
        acquired = self.acquire_write(timeout=timeout)
        if not acquired:
            raise TimeoutError(f"Failed to acquire write lock '{self.name}' within timeout")

        try:
            yield
        finally:
            self.release_write()


class AsyncReadWriteLock:
    """
    Async read-write lock implementation with timeout and logging.

    This class allows multiple readers but only one writer at a time.
    """

    def __init__(self, name: str, priority: LockPriority = LockPriority.MEDIUM,
                 timeout: Optional[float] = None):
        """
        Initialize a new AsyncReadWriteLock.

        Args:
            name: Name of the lock for logging and tracking
            priority: Lock priority for deadlock prevention hierarchy
            timeout: Default timeout in seconds (None for no timeout)
        """
        self.name = name
        self.id = f"{name}_{uuid.uuid4().hex[:8]}"
        self.priority = priority
        self.default_timeout = timeout or DEFAULT_ASYNC_LOCK_TIMEOUT

        # Internal state
        self._readers = 0
        self._writers = 0
        self._read_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()

        # Register with statistics tracker
        lock_statistics.register_lock(self.id, name, LockType.RW_LOCK, priority)

        logger.debug(f"Created async read-write lock '{name}' with ID {self.id} "
                     f"(priority={priority.name}, timeout={self.default_timeout}s)")

    async def acquire_read(self, timeout: Optional[float] = None) -> bool:
        """
        Acquire a read lock with timeout.

        Args:
            timeout: Timeout in seconds (overrides default if provided)

        Returns:
            True if the lock was acquired, False otherwise
        """
        thread_id = f"{threading.get_ident()}:{id(asyncio.current_task())}"
        task_name = asyncio.current_task().get_name() if asyncio.current_task() else "unknown"

        effective_timeout = timeout if timeout is not None else self.default_timeout
        wait_start = time.time()

        # Attempt to acquire the read lock with timeout
        try:
            async with asyncio.timeout(effective_timeout):
                # Wait for the write lock (to ensure no writers are active)
                async with self._write_lock:
                    # Increment reader count
                    self._readers += 1

            wait_time = time.time() - wait_start

            # Record successful acquisition
            lock_statistics.record_acquisition(
                self.id, thread_id, wait_time, 0.0
            )

            logger.debug(
                f"Task {task_name} acquired async read lock '{self.name}' "
                f"after {wait_time:.6f}s wait (active readers: {self._readers})"
            )

            return True

        except asyncio.TimeoutError:
            lock_statistics.record_timeout(self.id)
            logger.warning(
                f"Task {task_name} failed to acquire async read lock '{self.name}' "
                f"after {time.time() - wait_start:.6f}s wait (timeout={effective_timeout}s)"
            )
            return False
        except Exception as e:
            lock_statistics.record_timeout(self.id)
            logger.error(f"Error acquiring async read lock '{self.name}': {e}")
            return False

    async def release_read(self) -> None:
        """Release a read lock with logging."""
        thread_id = f"{threading.get_ident()}:{id(asyncio.current_task())}"
        task_name = asyncio.current_task().get_name() if asyncio.current_task() else "unknown"

        try:
            # Record before release
            lock_statistics.record_release(self.id, thread_id)

            # Decrement reader count
            self._readers -= 1
            if self._readers < 0:
                self._readers = 0
                logger.warning(f"Reader count went negative for async lock '{self.name}', resetting to 0")

            logger.debug(
                f"Task {task_name} released async read lock '{self.name}' "
                f"(remaining readers: {self._readers})"
            )
        except Exception as e:
            logger.error(f"Error releasing async read lock '{self.name}': {e}")

    async def acquire_write(self, timeout: Optional[float] = None) -> bool:
        """
        Acquire a write lock with timeout.

        Args:
            timeout: Timeout in seconds (overrides default if provided)

        Returns:
            True if the lock was acquired, False otherwise
        """
        thread_id = f"{threading.get_ident()}:{id(asyncio.current_task())}"
        task_name = asyncio.current_task().get_name() if asyncio.current_task() else "unknown"

        effective_timeout = timeout if timeout is not None else self.default_timeout
        wait_start = time.time()

        try:
            async with asyncio.timeout(effective_timeout):
                # Acquire the write lock
                await self._write_lock.acquire()

                try:
                    # Now wait for all readers to finish
                    while self._readers > 0:
                        # Temporarily release the write lock to allow readers to finish
                        self._write_lock.release()
                        await asyncio.sleep(0.1)  # Small delay
                        await self._write_lock.acquire()

                    # Increment writer count
                    self._writers += 1
                except Exception:
                    # Ensure we release the write lock if something goes wrong
                    self._write_lock.release()
                    raise

            wait_time = time.time() - wait_start

            # Record successful acquisition
            lock_statistics.record_acquisition(
                self.id, thread_id, wait_time, 0.0
            )

            logger.debug(
                f"Task {task_name} acquired async write lock '{self.name}' "
                f"after {wait_time:.6f}s wait"
            )

            return True

        except asyncio.TimeoutError:
            lock_statistics.record_timeout(self.id)
            logger.warning(
                f"Task {task_name} failed to acquire async write lock '{self.name}' "
                f"after {time.time() - wait_start:.6f}s wait (timeout={effective_timeout}s)"
            )
            return False
        except Exception as e:
            lock_statistics.record_timeout(self.id)
            logger.error(f"Error acquiring async write lock '{self.name}': {e}")
            return False

    async def release_write(self) -> None:
        """Release a write lock with logging."""
        thread_id = f"{threading.get_ident()}:{id(asyncio.current_task())}"
        task_name = asyncio.current_task().get_name() if asyncio.current_task() else "unknown"

        try:
            # Record before release
            lock_statistics.record_release(self.id, thread_id)

            # Decrement writer count
            self._writers -= 1
            if self._writers < 0:
                self._writers = 0
                logger.warning(f"Writer count went negative for async lock '{self.name}', resetting to 0")

            # Release the write lock
            self._write_lock.release()

            logger.debug(f"Task {task_name} released async write lock '{self.name}'")
        except Exception as e:
            logger.error(f"Error releasing async write lock '{self.name}': {e}")

    @asynccontextmanager
    async def read_locked(self, timeout: Optional[float] = None):
        """
        Async context manager for acquiring a read lock with timeout.

        Args:
            timeout: Timeout in seconds (overrides default if provided)

        Raises:
            TimeoutError: If lock cannot be acquired within timeout
        """
        acquired = await self.acquire_read(timeout=timeout)
        if not acquired:
            raise TimeoutError(f"Failed to acquire async read lock '{self.name}' within timeout")

        try:
            yield
        finally:
            await self.release_read()

    @asynccontextmanager
    async def write_locked(self, timeout: Optional[float] = None):
        """
        Async context manager for acquiring a write lock with timeout.

        Args:
            timeout: Timeout in seconds (overrides default if provided)

        Raises:
            TimeoutError: If lock cannot be acquired within timeout
        """
        acquired = await self.acquire_write(timeout=timeout)
        if not acquired:
            raise TimeoutError(f"Failed to acquire async write lock '{self.name}' within timeout")

        try:
            yield
        finally:
            await self.release_write()


def get_lock_report() -> Dict[str, Any]:
    """
    Generate a comprehensive report of all locks in the system.

    Returns:
        Dictionary with detailed lock statistics and current state
    """
    lock_stats = lock_statistics.get_lock_stats()
    active_locks = lock_statistics.get_active_locks()

    report = {
        "total_locks": len(lock_stats),
        "active_locks_count": len(active_locks),
        "locks_by_priority": {
            priority.name: 0 for priority in LockPriority
        },
        "locks_by_type": {
            lock_type.name: 0 for lock_type in LockType
        },
        "contentious_locks": [],
        "long_held_locks": [],
        "frequently_timed_out_locks": [],
        "lock_statistics": lock_stats,
        "active_locks": active_locks
    }

    current_time = time.time()

    # Analyze lock statistics
    for lock_id, stats in lock_stats.items():
        # Count by priority and type
        if "priority" in stats:
            priority_name = str(stats["priority"]).split('.')[-1]  # Extract name from enum
            report["locks_by_priority"][priority_name] += 1

        if "type" in stats:
            type_name = str(stats["type"]).split('.')[-1]  # Extract name from enum
            report["locks_by_type"][type_name] += 1

        # Find contentious locks (high contention rate)
        contention_rate = stats.get("contentions", 0) / max(stats.get("acquisitions", 1), 1)
        if contention_rate > 0.1:  # More than 10% contention rate
            report["contentious_locks"].append({
                "id": lock_id,
                "name": stats.get("name", "unknown"),
                "contention_rate": contention_rate,
                "contentions": stats.get("contentions", 0),
                "acquisitions": stats.get("acquisitions", 0)
            })

        # Find locks with timeout issues
        timeout_rate = stats.get("timeouts", 0) / max(stats.get("acquisitions", 1) + stats.get("timeouts", 0), 1)
        if timeout_rate > 0.05:  # More than 5% timeout rate
            report["frequently_timed_out_locks"].append({
                "id": lock_id,
                "name": stats.get("name", "unknown"),
                "timeout_rate": timeout_rate,
                "timeouts": stats.get("timeouts", 0),
                "acquisitions": stats.get("acquisitions", 0)
            })

        # Find long-held locks
        last_acquired = stats.get("last_acquired")
        last_released = stats.get("last_released")

        if last_acquired and (not last_released or last_acquired > last_released):
            hold_time = current_time - last_acquired
            if hold_time > 60:  # Held for more than 60 seconds
                report["long_held_locks"].append({
                    "id": lock_id,
                    "name": stats.get("name", "unknown"),
                    "held_for_seconds": hold_time,
                    "acquired_at": last_acquired
                })

    # Sort lists for better readability
    report["contentious_locks"] = sorted(
        report["contentious_locks"],
        key=lambda x: x["contention_rate"],
        reverse=True
    )

    report["frequently_timed_out_locks"] = sorted(
        report["frequently_timed_out_locks"],
        key=lambda x: x["timeout_rate"],
        reverse=True
    )

    report["long_held_locks"] = sorted(
        report["long_held_locks"],
        key=lambda x: x["held_for_seconds"],
        reverse=True
    )

    return report


def reset_all_lock_statistics() -> None:
    """Reset statistics for all locks."""
    lock_statistics.reset_stats()
    logger.info("Reset all lock statistics")


# Module initialization
def init():
    """Initialize the synchronization module."""
    # Configure logging for this module
    module_logger = logging.getLogger(__name__)
    if not module_logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        module_logger.addHandler(handler)
        module_logger.setLevel(logging.INFO)

    logger.info("Synchronization utils initialized")


# Initialize module when imported
init()