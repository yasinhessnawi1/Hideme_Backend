import asyncio
import threading
import unittest
from unittest.mock import patch

from backend.app.utils.system_utils.synchronization_utils import (
    LockPriority,
    LockType,
    LockManager,
    TimeoutLock,
    AsyncTimeoutLock,
    AsyncTimeoutSemaphore,
    init,
)


# Tests for LockPriority enum values
class TestLockPriority(unittest.TestCase):

    # Test LockPriority value ordering
    def test_lock_priority_values(self):
        self.assertTrue(hasattr(LockPriority, "CRITICAL"))

        self.assertTrue(hasattr(LockPriority, "HIGH"))

        self.assertTrue(hasattr(LockPriority, "MEDIUM"))

        self.assertTrue(hasattr(LockPriority, "LOW"))

        self.assertTrue(hasattr(LockPriority, "BACKGROUND"))

        self.assertLess(LockPriority.CRITICAL.value, LockPriority.HIGH.value)

        self.assertLess(LockPriority.HIGH.value, LockPriority.MEDIUM.value)

        self.assertLess(LockPriority.MEDIUM.value, LockPriority.LOW.value)

        self.assertLess(LockPriority.LOW.value, LockPriority.BACKGROUND.value)


# Tests for LockType enum values
class TestLockType(unittest.TestCase):

    # Test LockType attributes
    def test_lock_type_values(self):
        self.assertTrue(hasattr(LockType, "THREAD"))

        self.assertTrue(hasattr(LockType, "ASYNCIO"))

        self.assertTrue(hasattr(LockType, "SEMAPHORE"))

        self.assertTrue(hasattr(LockType, "RW_LOCK"))


# Tests for LockStatistics behavior
class TestLockStatistics(unittest.TestCase):

    # Setup LockStatistics instance
    def setUp(self):
        from backend.app.utils.system_utils.synchronization_utils import LockStatistics

        self.lock_stats = LockStatistics()

        self.lock_id = "test_lock_1"

        self.lock_name = "TestLock"

        self.thread_id = "thread_1"

    # Test registering locks and summary counts
    def test_register_lock(self):
        self.lock_stats.register_lock(
            self.lock_id, self.lock_name, LockType.THREAD, LockPriority.MEDIUM, False
        )

        stats = self.lock_stats.get_lock_stats(self.lock_id)

        self.assertEqual(stats["name"], self.lock_name)

        self.assertEqual(stats["type"], LockType.THREAD)

        self.assertEqual(stats["priority"], LockPriority.MEDIUM)

        self.assertEqual(stats["acquisitions"], 0)

        self.assertFalse(stats["is_instance_lock"])

        summary = self.lock_stats.get_summary_stats()

        self.assertEqual(summary["global_locks"], 1)

        self.assertEqual(summary["instance_locks"], 0)

        instance_lock_id = "test_instance_lock"

        self.lock_stats.register_lock(
            instance_lock_id, "InstanceLock", LockType.THREAD, LockPriority.LOW, True
        )

        summary = self.lock_stats.get_summary_stats()

        self.assertEqual(summary["global_locks"], 1)

        self.assertEqual(summary["instance_locks"], 1)

    # Test recording acquisitions and stats
    def test_record_acquisition(self):
        self.lock_stats.register_lock(
            self.lock_id, self.lock_name, LockType.THREAD, LockPriority.MEDIUM, False
        )

        self.lock_stats.record_acquisition(self.lock_id, self.thread_id, 0.1, 0.05)

        stats = self.lock_stats.get_lock_stats(self.lock_id)

        self.assertEqual(stats["acquisitions"], 1)

        self.assertEqual(stats["wait_time_total"], 0.1)

        self.assertEqual(stats["wait_time_max"], 0.1)

        self.assertEqual(stats["acquisition_time_total"], 0.05)

        active_locks = self.lock_stats.get_active_locks()

        lock_key = f"{self.lock_id}:{self.thread_id}"

        self.assertIn(lock_key, active_locks)

        summary = self.lock_stats.get_summary_stats()

        self.assertEqual(summary["total_acquisitions"], 1)

        self.assertEqual(summary["failed_acquisitions"], 0)

        self.assertEqual(summary["success_rate"], 100.0)

    # Test recording releases clears active locks
    def test_record_release(self):
        self.lock_stats.register_lock(
            self.lock_id, self.lock_name, LockType.THREAD, LockPriority.MEDIUM, False
        )

        self.lock_stats.record_acquisition(self.lock_id, self.thread_id, 0.1, 0.05)

        self.lock_stats.record_release(self.lock_id, self.thread_id)

        stats = self.lock_stats.get_lock_stats(self.lock_id)

        self.assertIsNotNone(stats["last_released"])

        active_locks = self.lock_stats.get_active_locks()

        self.assertEqual(len(active_locks), 0)

    # Test recording timeouts increments counter
    def test_record_timeout(self):
        self.lock_stats.register_lock(
            self.lock_id, self.lock_name, LockType.THREAD, LockPriority.MEDIUM, False
        )

        self.lock_stats.record_timeout(self.lock_id)

        stats = self.lock_stats.get_lock_stats(self.lock_id)

        self.assertEqual(stats["timeouts"], 1)

        summary = self.lock_stats.get_summary_stats()

        self.assertEqual(summary["failed_acquisitions"], 1)

        self.assertEqual(summary["success_rate"], 0.0)

    # Test recording contention increments counter
    def test_record_contention(self):
        self.lock_stats.register_lock(
            self.lock_id, self.lock_name, LockType.THREAD, LockPriority.MEDIUM, False
        )

        self.lock_stats.record_contention(self.lock_id)

        stats = self.lock_stats.get_lock_stats(self.lock_id)

        self.assertEqual(stats["contentions"], 1)

    # Test retrieving single and all lock stats
    def test_get_lock_stats(self):
        self.lock_stats.register_lock(
            "lock1", "Lock1", LockType.THREAD, LockPriority.HIGH, False
        )

        self.lock_stats.register_lock(
            "lock2", "Lock2", LockType.ASYNCIO, LockPriority.LOW, True
        )

        stats1 = self.lock_stats.get_lock_stats("lock1")

        self.assertEqual(stats1["name"], "Lock1")

        all_stats = self.lock_stats.get_lock_stats()

        self.assertEqual(len(all_stats), 2)

        self.assertIn("lock1", all_stats)

        self.assertIn("lock2", all_stats)

        non_existent_stats = self.lock_stats.get_lock_stats("non_existent")

        self.assertEqual(non_existent_stats, {})

    # Test active locks tracking
    def test_get_active_locks(self):
        self.lock_stats.register_lock(
            "lock1", "Lock1", LockType.THREAD, LockPriority.HIGH, False
        )

        self.lock_stats.register_lock(
            "lock2", "Lock2", LockType.ASYNCIO, LockPriority.LOW, True
        )

        self.lock_stats.record_acquisition("lock1", "thread1", 0.1, 0.05)

        self.lock_stats.record_acquisition("lock2", "thread2", 0.2, 0.1)

        active_locks = self.lock_stats.get_active_locks()

        self.assertEqual(len(active_locks), 2)

        self.assertIn("lock1:thread1", active_locks)

        self.assertIn("lock2:thread2", active_locks)

        self.lock_stats.record_release("lock1", "thread1")

        active_locks = self.lock_stats.get_active_locks()

        self.assertEqual(len(active_locks), 1)

        self.assertIn("lock2:thread2", active_locks)

    # Test summary statistics calculation
    def test_get_summary_stats(self):
        self.lock_stats.register_lock(
            "lock1", "Lock1", LockType.THREAD, LockPriority.HIGH, False
        )

        self.lock_stats.register_lock(
            "lock2", "Lock2", LockType.ASYNCIO, LockPriority.LOW, True
        )

        self.lock_stats.record_acquisition("lock1", "thread1", 0.1, 0.05)

        self.lock_stats.record_timeout("lock2")

        summary = self.lock_stats.get_summary_stats()

        self.assertEqual(summary["total_locks"], 2)

        self.assertEqual(summary["global_locks"], 1)

        self.assertEqual(summary["instance_locks"], 1)

        self.assertEqual(summary["active_locks"], 1)

        self.assertEqual(summary["total_acquisitions"], 1)

        self.assertEqual(summary["failed_acquisitions"], 1)

        self.assertEqual(summary["success_rate"], 50.0)

    # Test resetting stats for specific and all locks
    def test_reset_stats(self):
        self.lock_stats.register_lock(
            "lock1", "Lock1", LockType.THREAD, LockPriority.HIGH, False
        )

        self.lock_stats.register_lock(
            "lock2", "Lock2", LockType.ASYNCIO, LockPriority.LOW, True
        )

        self.lock_stats.record_acquisition("lock1", "thread1", 0.1, 0.05)

        self.lock_stats.record_timeout("lock2")

        self.lock_stats.record_contention("lock1")

        self.lock_stats.reset_stats("lock1")

        stats1 = self.lock_stats.get_lock_stats("lock1")

        stats2 = self.lock_stats.get_lock_stats("lock2")

        self.assertEqual(stats1["acquisitions"], 0)

        self.assertEqual(stats1["contentions"], 0)

        self.assertEqual(stats2["timeouts"], 1)

        summary = self.lock_stats.get_summary_stats()

        self.assertEqual(summary["total_acquisitions"], 1)

        self.assertEqual(summary["failed_acquisitions"], 1)

        self.lock_stats.reset_stats()

        stats1 = self.lock_stats.get_lock_stats("lock1")

        stats2 = self.lock_stats.get_lock_stats("lock2")

        self.assertEqual(stats1["acquisitions"], 0)

        self.assertEqual(stats2["timeouts"], 0)

        summary = self.lock_stats.get_summary_stats()

        self.assertEqual(summary["total_acquisitions"], 0)

        self.assertEqual(summary["failed_acquisitions"], 0)


# Tests for LockManager behavior
class TestLockManager(unittest.TestCase):

    # Setup LockManager instance
    def setUp(self):
        self.lock_manager = LockManager()

    # Test deadlock check with no locks held
    def test_check_deadlock_no_locks_held(self):
        result = self.lock_manager.check_deadlock("lock1", LockPriority.MEDIUM, False)

        self.assertFalse(result)

    # Test deadlock check for instance lock
    def test_check_deadlock_instance_lock(self):
        self.lock_manager.register_lock_acquisition("lock1", LockPriority.HIGH, False)

        result = self.lock_manager.check_deadlock(
            "instance_lock", LockPriority.LOW, True
        )

        self.assertFalse(result)

    # Test deadlock check when hierarchy is invalid but allowed
    def test_check_deadlock_invalid_hierarchy(self):
        self.lock_manager.register_lock_acquisition(
            "lock_high", LockPriority.HIGH, False
        )

        result = self.lock_manager.check_deadlock("lock_low", LockPriority.LOW, False)

        self.assertFalse(result)

    # Test deadlock check when hierarchy violation occurs
    def test_check_deadlock_valid_hierarchy(self):
        self.lock_manager.register_lock_acquisition("lock_low", LockPriority.LOW, False)

        result = self.lock_manager.check_deadlock("lock_high", LockPriority.HIGH, False)

        self.assertTrue(result)

    # Test registering lock acquisition
    def test_register_lock_acquisition(self):
        self.lock_manager.register_lock_acquisition("lock1", LockPriority.HIGH, False)

        self.lock_manager.register_lock_acquisition(
            "instance_lock", LockPriority.LOW, True
        )

        self.assertIsNotNone(self.lock_manager._thread_locks.get(threading.get_ident()))

    # Test registering lock release
    def test_register_lock_release(self):
        self.lock_manager.register_lock_acquisition("lock1", LockPriority.HIGH, False)

        self.lock_manager.register_lock_release("lock1", False)

        self.assertEqual(
            self.lock_manager._thread_locks.get(threading.get_ident(), []), []
        )

    # Test clearing thread data
    def test_clear_thread_data(self):
        self.lock_manager.register_lock_acquisition("lock1", LockPriority.HIGH, False)

        self.lock_manager.clear_thread_data()

        self.assertNotIn(threading.get_ident(), self.lock_manager._thread_locks)


# Tests for TimeoutLock synchronous behavior
class TestTimeoutLock(unittest.TestCase):

    # Setup TimeoutLock instance
    def setUp(self):
        self.lock = TimeoutLock(
            "TestLock",
            priority=LockPriority.MEDIUM,
            timeout=1.0,
            reentrant=True,
            is_instance_lock=False,
        )

    # Test acquiring and releasing via context manager
    def test_acquire_and_release(self):
        with self.lock.acquire_timeout(timeout=0.5) as acquired:
            self.assertTrue(acquired)

        self.assertIsNone(self.lock.owner)

    # Test acquisition failure when lock already held
    def test_acquire_timeout_failure(self):
        non_reentrant_lock = TimeoutLock(
            "TestLockNonReentrant",
            priority=LockPriority.MEDIUM,
            timeout=1.0,
            reentrant=False,
            is_instance_lock=False,
        )

        non_reentrant_lock.lock.acquire()

        try:
            with non_reentrant_lock.acquire_timeout(timeout=0.1) as acquired:
                self.assertFalse(acquired)
        finally:
            non_reentrant_lock.lock.release()


# Tests for AsyncTimeoutLock behavior
class TestAsyncTimeoutLock(unittest.IsolatedAsyncioTestCase):

    # Setup AsyncTimeoutLock instance
    async def asyncSetUp(self):
        self.async_lock = AsyncTimeoutLock(
            "AsyncTestLock",
            priority=LockPriority.MEDIUM,
            timeout=1.0,
            is_instance_lock=False,
        )

    # Test async acquire and release
    async def test_async_acquire_and_release(self):
        acquired = await self.async_lock.acquire(timeout=0.5)

        self.assertTrue(acquired)

        self.assertEqual(
            self.async_lock.owner,
            f"{threading.get_ident()}:{id(asyncio.current_task())}",
        )

        self.async_lock.release()

        self.assertIsNone(self.async_lock.owner)

    # Test async acquisition timeout
    async def test_async_acquire_timeout(self):
        await self.async_lock.lock.acquire()

        try:
            acquired = await self.async_lock.acquire(timeout=0.1)

            self.assertFalse(acquired)
        finally:
            self.async_lock.lock.release()

    # Test async context manager for acquire_timeout
    async def test_acquire_timeout_context_manager(self):
        async with self.async_lock.acquire_timeout(timeout=0.5) as acquired:
            self.assertTrue(acquired)

        self.assertIsNone(self.async_lock.owner)


# Tests for AsyncTimeoutSemaphore behavior
class TestAsyncTimeoutSemaphore(unittest.IsolatedAsyncioTestCase):

    # Setup AsyncTimeoutSemaphore instance
    async def asyncSetUp(self):
        self.semaphore = AsyncTimeoutSemaphore(
            "AsyncSemaphore", value=2, priority=LockPriority.MEDIUM, timeout=1.0
        )

    # Test semaphore acquire and release
    async def test_semaphore_acquire_release(self):
        acquired = await self.semaphore.acquire(timeout=0.5)

        self.assertTrue(acquired)

        self.assertEqual(self.semaphore.current_value, 1)

        self.semaphore.release()

        self.assertEqual(self.semaphore.current_value, 2)

    # Test semaphore timeout on exhaustion
    async def test_semaphore_timeout(self):
        acquired1 = await self.semaphore.acquire(timeout=0.5)

        acquired2 = await self.semaphore.acquire(timeout=0.5)

        self.assertTrue(acquired1)

        self.assertTrue(acquired2)

        acquired3 = await self.semaphore.acquire(timeout=0.1)

        self.assertFalse(acquired3)

        self.semaphore.release()

        self.assertEqual(self.semaphore.current_value, 1)


# Tests for init function logging
class TestInitFunction(unittest.TestCase):

    # Test init logs initialization message
    @patch("backend.app.utils.system_utils.synchronization_utils.logger")
    def test_init(self, mock_logger):
        module_logger = mock_logger

        module_logger.handlers = []

        init()

        mock_logger.info.assert_called_once_with("Synchronization utils initialized")
