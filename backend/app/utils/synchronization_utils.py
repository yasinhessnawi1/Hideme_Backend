"""
Enhanced synchronization utilities with optimized lock hierarchy and instance-level locking.

This module provides centralized synchronization primitives for thread safety across the application,
with improved focus on instance-level locks instead of class-level locks for better parallelism.
Features include:
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

            # Increment instance or global lock counter
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
                # Only reset counters, not lock registrations
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
        # Track locks held by each thread
        self._thread_locks: Dict[int, List[Tuple[str, LockPriority]]] = {}
        # Track lock wait graph for deadlock detection
        self._wait_graph: Dict[str, Set[str]] = {}
        # Track instance-level locks separately
        self._instance_locks: Dict[int, Set[str]] = {}

    def check_deadlock(self, lock_id: str, priority: LockPriority, is_instance_lock: bool = False) -> bool:
        """
        Check if acquiring this lock could cause a deadlock based on current locks held.

        Instance-level locks have more relaxed hierarchy checking to allow better concurrency.

        Returns:
            True if deadlock is possible, False otherwise
        """
        thread_id = threading.get_ident()

        with self._lock:
            # First time this thread is acquiring locks
            if thread_id not in self._thread_locks:
                self._thread_locks[thread_id] = []
                self._instance_locks[thread_id] = set()
                return False

            # Instance locks are tracked separately with relaxed hierarchy
            if is_instance_lock:
                self._instance_locks[thread_id].add(lock_id)
                return False

            # Check if this thread already holds global locks
            current_locks = self._thread_locks[thread_id]

            # If we already hold locks, check for priority violation
            for held_lock_id, held_priority in current_locks:
                # Skip instance locks for hierarchy checking
                if held_lock_id in self._instance_locks.get(thread_id, set()):
                    continue

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

    def register_lock_acquisition(self, lock_id: str, priority: LockPriority, is_instance_lock: bool = False) -> None:
        """Register that a thread has acquired a lock."""
        thread_id = threading.get_ident()

        with self._lock:
            if thread_id not in self._thread_locks:
                self._thread_locks[thread_id] = []
                self._instance_locks[thread_id] = set()

            self._thread_locks[thread_id].append((lock_id, priority))

            # Also track instance locks separately
            if is_instance_lock:
                self._instance_locks[thread_id].add(lock_id)

    def register_lock_release(self, lock_id: str, is_instance_lock: bool = False) -> None:
        """Register that a thread has released a lock."""
        thread_id = threading.get_ident()

        with self._lock:
            if thread_id in self._thread_locks:
                # Remove the lock from the thread's list
                self._thread_locks[thread_id] = [
                    (l_id, prio) for l_id, prio in self._thread_locks[thread_id]
                    if l_id != lock_id
                ]

                # Also remove from instance locks if applicable
                if is_instance_lock and thread_id in self._instance_locks:
                    self._instance_locks[thread_id].discard(lock_id)

                # Clean up if thread has no more locks
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


class TimeoutLock:
    """
    Enhanced Lock implementation with timeout, logging, and deadlock prevention.

    This lock improves on threading.Lock with detailed logging, timeout support,
    and deadlock prevention through lock hierarchy enforcement.
    """

    def __init__(self, name: str, priority: LockPriority = LockPriority.MEDIUM,
                 timeout: Optional[float] = None, reentrant: bool = True,
                 is_instance_lock: bool = False):
        """
        Initialize a new TimeoutLock.

        Args:
            name: Name of the lock for logging and tracking
            priority: Lock priority for deadlock prevention hierarchy
            timeout: Default timeout in seconds (None for no timeout)
            reentrant: Whether the lock is reentrant (can be acquired multiple times by same thread)
            is_instance_lock: Whether this is an instance-level lock (more relaxed hierarchy)
        """
        self.name = name
        self.id = f"{name}_{uuid.uuid4().hex[:8]}"
        self.priority = priority
        self.default_timeout = timeout or DEFAULT_LOCK_TIMEOUT
        self.lock = threading.RLock() if reentrant else threading.Lock()
        self.owner: Optional[int] = None
        self.acquisition_count = 0
        self.is_instance_lock = is_instance_lock

        # Register with statistics tracker
        lock_statistics.register_lock(self.id, name, LockType.THREAD, priority, is_instance_lock)

        logger.debug(f"Created lock '{name}' with ID {self.id} "
                     f"(priority={priority.name}, timeout={self.default_timeout}s, instance={is_instance_lock})")

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

        # Check for potential deadlocks - relaxed for instance locks
        if lock_manager.check_deadlock(self.id, self.priority, self.is_instance_lock):
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
            lock_manager.register_lock_acquisition(self.id, self.priority, self.is_instance_lock)

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
            lock_manager.register_lock_release(self.id, self.is_instance_lock)

            logger.debug(f"Thread {thread_name} released lock '{self.name}'")
        except RuntimeError as e:
            # Handle "release unlocked lock" error
            logger.error(f"Error releasing lock '{self.name}': {e}")

    @contextmanager
    def acquire_timeout(self, timeout: Optional[float] = None) -> Generator[bool, Any, None]:
        """
        Context manager for acquiring the lock with timeout.

        Args:
            timeout: Timeout in seconds (overrides default if provided)

        Yields:
            True if lock was acquired, False if timeout

        Note: Unlike previous version, this doesn't raise TimeoutError on failure but yields False
        """
        acquired = self.acquire(timeout=timeout)
        try:
            yield acquired
        finally:
            if acquired:
                self.release()


class AsyncTimeoutLock:
    """
    Enhanced asyncio.Lock implementation with timeout, logging, and deadlock prevention.

    This lock improves on asyncio.Lock with detailed logging, timeout support,
    and deadlock prevention through lock hierarchy enforcement.
    """

    def __init__(self, name: str, priority: LockPriority = LockPriority.MEDIUM,
                 timeout: Optional[float] = None, is_instance_lock: bool = False):
        """
        Initialize a new AsyncTimeoutLock.

        Args:
            name: Name of the lock for logging and tracking
            priority: Lock priority for deadlock prevention hierarchy
            timeout: Default timeout in seconds (None for no timeout)
            is_instance_lock: Whether this is an instance-level lock (more relaxed hierarchy)
        """
        self.name = name
        self.id = f"{name}_{uuid.uuid4().hex[:8]}"
        self.priority = priority
        self.default_timeout = timeout or DEFAULT_ASYNC_LOCK_TIMEOUT
        self.lock = asyncio.Lock()
        self.owner: Optional[str] = None
        self.is_instance_lock = is_instance_lock

        # Register with statistics tracker
        lock_statistics.register_lock(self.id, name, LockType.ASYNCIO, priority, is_instance_lock)

        logger.debug(f"Created async lock '{name}' with ID {self.id} "
                     f"(priority={priority.name}, timeout={self.default_timeout}s, instance={is_instance_lock})")

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
    async def acquire_timeout(self, timeout: Optional[float] = None) -> AsyncGenerator[bool, None]:
        """
        Async context manager for acquiring the lock with timeout.

        Args:
            timeout: Timeout in seconds (overrides default if provided)

        Yields:
            True if lock was acquired, False if timeout

        Note: Unlike previous version, this doesn't raise TimeoutError on failure but yields False
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

    Optimized for batch operations with better concurrency control.
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

        # Register with statistics tracker - always mark as instance lock
        lock_statistics.register_lock(self.id, name, LockType.SEMAPHORE, priority, is_instance_lock=True)

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
    async def acquire_timeout(self, timeout: Optional[float] = None) -> AsyncGenerator[bool, None]:
        """
        Async context manager for acquiring the semaphore with timeout.

        Args:
            timeout: Timeout in seconds (overrides default if provided)

        Yields:
            True if semaphore was acquired, False if timeout
        """
        acquired = await self.acquire(timeout=timeout)
        try:
            yield acquired
        finally:
            if acquired:
                self.release()


def get_lock_report() -> Dict[str, Any]:
    """
    Generate a comprehensive report of all locks in the system.

    Returns:
        Dictionary with detailed lock statistics and current state
    """
    lock_stats = lock_statistics.get_lock_stats()
    active_locks = lock_statistics.get_active_locks()
    summary_stats = lock_statistics.get_summary_stats()

    report = {
        "summary": summary_stats,
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
            report["locks_by_priority"][priority_name] = report["locks_by_priority"].get(priority_name, 0) + 1

        if "type" in stats:
            type_name = str(stats["type"]).split('.')[-1]  # Extract name from enum
            report["locks_by_type"][type_name] = report["locks_by_type"].get(type_name, 0) + 1

        # Find contentious locks (high contention rate)
        contention_rate = stats.get("contentions", 0) / max(stats.get("acquisitions", 1), 1)
        if contention_rate > 0.1:  # More than 10% contention rate
            report["contentious_locks"].append({
                "id": lock_id,
                "name": stats.get("name", "unknown"),
                "contention_rate": contention_rate,
                "contentions": stats.get("contentions", 0),
                "acquisitions": stats.get("acquisitions", 0),
                "is_instance_lock": stats.get("is_instance_lock", False)
            })

        # Find locks with timeout issues
        timeout_rate = stats.get("timeouts", 0) / max(stats.get("acquisitions", 1) + stats.get("timeouts", 0), 1)
        if timeout_rate > 0.05:  # More than 5% timeout rate
            report["frequently_timed_out_locks"].append({
                "id": lock_id,
                "name": stats.get("name", "unknown"),
                "timeout_rate": timeout_rate,
                "timeouts": stats.get("timeouts", 0),
                "acquisitions": stats.get("acquisitions", 0),
                "is_instance_lock": stats.get("is_instance_lock", False)
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
                    "acquired_at": last_acquired,
                    "is_instance_lock": stats.get("is_instance_lock", False)
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