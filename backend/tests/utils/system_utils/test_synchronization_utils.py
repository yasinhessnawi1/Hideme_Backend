"""
Unit tests for synchronization_utils.py module.

This test file covers all classes and functions in the synchronization_utils module with both positive
and negative test cases to ensure proper functionality and error handling.
"""

import asyncio
import threading
import unittest
from unittest.mock import patch

# Import the module to be tested.
from backend.app.utils.system_utils.synchronization_utils import (
    LockPriority,
    LockType,
    LockManager,
    TimeoutLock,
    AsyncTimeoutLock,
    AsyncTimeoutSemaphore,
    init  # global instance used by TimeoutLock etc.
)


# Tests for basic enums, LockStatistics, and LockManager (existing tests)

class TestLockPriority(unittest.TestCase):

    def test_lock_priority_values(self):
        self.assertTrue(hasattr(LockPriority, 'CRITICAL'))
        self.assertTrue(hasattr(LockPriority, 'HIGH'))
        self.assertTrue(hasattr(LockPriority, 'MEDIUM'))
        self.assertTrue(hasattr(LockPriority, 'LOW'))
        self.assertTrue(hasattr(LockPriority, 'BACKGROUND'))

        self.assertLess(LockPriority.CRITICAL.value, LockPriority.HIGH.value)
        self.assertLess(LockPriority.HIGH.value, LockPriority.MEDIUM.value)
        self.assertLess(LockPriority.MEDIUM.value, LockPriority.LOW.value)
        self.assertLess(LockPriority.LOW.value, LockPriority.BACKGROUND.value)


class TestLockType(unittest.TestCase):

    def test_lock_type_values(self):
        self.assertTrue(hasattr(LockType, 'THREAD'))
        self.assertTrue(hasattr(LockType, 'ASYNCIO'))
        self.assertTrue(hasattr(LockType, 'SEMAPHORE'))
        self.assertTrue(hasattr(LockType, 'RW_LOCK'))


class TestLockStatistics(unittest.TestCase):

    def setUp(self):
        from backend.app.utils.system_utils.synchronization_utils import LockStatistics
        self.lock_stats = LockStatistics()

        self.lock_id = "test_lock_1"
        self.lock_name = "TestLock"
        self.thread_id = "thread_1"

    def test_register_lock(self):
        self.lock_stats.register_lock(self.lock_id, self.lock_name, LockType.THREAD, LockPriority.MEDIUM, False)
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

        self.lock_stats.register_lock(instance_lock_id, "InstanceLock", LockType.THREAD, LockPriority.LOW, True)
        summary = self.lock_stats.get_summary_stats()
        self.assertEqual(summary["global_locks"], 1)
        self.assertEqual(summary["instance_locks"], 1)

    def test_record_acquisition(self):
        self.lock_stats.register_lock(self.lock_id, self.lock_name, LockType.THREAD, LockPriority.MEDIUM, False)
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

    def test_record_release(self):
        self.lock_stats.register_lock(self.lock_id, self.lock_name, LockType.THREAD, LockPriority.MEDIUM, False)
        self.lock_stats.record_acquisition(self.lock_id, self.thread_id, 0.1, 0.05)
        self.lock_stats.record_release(self.lock_id, self.thread_id)

        stats = self.lock_stats.get_lock_stats(self.lock_id)
        self.assertIsNotNone(stats["last_released"])

        active_locks = self.lock_stats.get_active_locks()
        self.assertEqual(len(active_locks), 0)

    def test_record_timeout(self):
        self.lock_stats.register_lock(self.lock_id, self.lock_name, LockType.THREAD, LockPriority.MEDIUM, False)
        self.lock_stats.record_timeout(self.lock_id)

        stats = self.lock_stats.get_lock_stats(self.lock_id)
        self.assertEqual(stats["timeouts"], 1)

        summary = self.lock_stats.get_summary_stats()
        self.assertEqual(summary["failed_acquisitions"], 1)
        self.assertEqual(summary["success_rate"], 0.0)

    def test_record_contention(self):
        self.lock_stats.register_lock(self.lock_id, self.lock_name, LockType.THREAD, LockPriority.MEDIUM, False)
        self.lock_stats.record_contention(self.lock_id)

        stats = self.lock_stats.get_lock_stats(self.lock_id)
        self.assertEqual(stats["contentions"], 1)

    def test_get_lock_stats(self):
        self.lock_stats.register_lock("lock1", "Lock1", LockType.THREAD, LockPriority.HIGH, False)
        self.lock_stats.register_lock("lock2", "Lock2", LockType.ASYNCIO, LockPriority.LOW, True)

        stats1 = self.lock_stats.get_lock_stats("lock1")
        self.assertEqual(stats1["name"], "Lock1")

        all_stats = self.lock_stats.get_lock_stats()
        self.assertEqual(len(all_stats), 2)
        self.assertIn("lock1", all_stats)
        self.assertIn("lock2", all_stats)

        non_existent_stats = self.lock_stats.get_lock_stats("non_existent")
        self.assertEqual(non_existent_stats, {})

    def test_get_active_locks(self):
        self.lock_stats.register_lock("lock1", "Lock1", LockType.THREAD, LockPriority.HIGH, False)
        self.lock_stats.register_lock("lock2", "Lock2", LockType.ASYNCIO, LockPriority.LOW, True)
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

    def test_get_summary_stats(self):
        self.lock_stats.register_lock("lock1", "Lock1", LockType.THREAD, LockPriority.HIGH, False)
        self.lock_stats.register_lock("lock2", "Lock2", LockType.ASYNCIO, LockPriority.LOW, True)
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

    def test_reset_stats(self):
        self.lock_stats.register_lock("lock1", "Lock1", LockType.THREAD, LockPriority.HIGH, False)
        self.lock_stats.register_lock("lock2", "Lock2", LockType.ASYNCIO, LockPriority.LOW, True)
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


# Tests for LockManager.

class TestLockManager(unittest.TestCase):

    def setUp(self):
        self.lock_manager = LockManager()

    def test_check_deadlock_no_locks_held(self):
        result = self.lock_manager.check_deadlock("lock1", LockPriority.MEDIUM, False)

        self.assertFalse(result)

    def test_check_deadlock_instance_lock(self):
        self.lock_manager.register_lock_acquisition("lock1", LockPriority.HIGH, False)

        result = self.lock_manager.check_deadlock("instance_lock", LockPriority.LOW, True)

        self.assertFalse(result)

    def test_check_deadlock_invalid_hierarchy(self):
        # Holding a HIGH priority lock, then acquiring a LOW priority should NOT be a violation.
        self.lock_manager.register_lock_acquisition("lock_high", LockPriority.HIGH, False)

        result = self.lock_manager.check_deadlock("lock_low", LockPriority.LOW, False)

        self.assertFalse(result)

    def test_check_deadlock_valid_hierarchy(self):
        # Holding a LOW priority lock and then attempting to acquire a HIGH priority lock should trigger a violation.
        self.lock_manager.register_lock_acquisition("lock_low", LockPriority.LOW, False)

        result = self.lock_manager.check_deadlock("lock_high", LockPriority.HIGH, False)

        self.assertTrue(result)

    def test_register_lock_acquisition(self):
        self.lock_manager.register_lock_acquisition("lock1", LockPriority.HIGH, False)

        self.lock_manager.register_lock_acquisition("instance_lock", LockPriority.LOW, True)

        # No explicit assert here; this is used by other functions.
        self.assertIsNotNone(self.lock_manager._thread_locks.get(threading.get_ident()))

    def test_register_lock_release(self):
        self.lock_manager.register_lock_acquisition("lock1", LockPriority.HIGH, False)

        self.lock_manager.register_lock_release("lock1", False)

        self.assertEqual(self.lock_manager._thread_locks.get(threading.get_ident(), []), [])

    def test_clear_thread_data(self):
        self.lock_manager.register_lock_acquisition("lock1", LockPriority.HIGH, False)

        self.lock_manager.clear_thread_data()

        self.assertNotIn(threading.get_ident(), self.lock_manager._thread_locks)


# Tests for TimeoutLock.

class TestTimeoutLock(unittest.TestCase):

    def setUp(self):

        self.lock = TimeoutLock("TestLock", priority=LockPriority.MEDIUM, timeout=1.0, reentrant=True,
                                is_instance_lock=False)

    def test_acquire_and_release(self):

        # Acquire lock using the context manager.
        with self.lock.acquire_timeout(timeout=0.5) as acquired:
            self.assertTrue(acquired)

        # After the with block, the lock is released (owner cleared).
        self.assertIsNone(self.lock.owner)

    def test_acquire_timeout_failure(self):

        # Create a non-reentrant TimeoutLock so that reentrancy is not allowed.
        non_reentrant_lock = TimeoutLock("TestLockNonReentrant",
                                         priority=LockPriority.MEDIUM,
                                         timeout=1.0,
                                         reentrant=False,
                                         is_instance_lock=False)

        # Pre-acquire the underlying lock.
        non_reentrant_lock.lock.acquire()
        try:
            with non_reentrant_lock.acquire_timeout(timeout=0.1) as acquired:

                # Since the lock is already held, acquiring should fail.
                self.assertFalse(acquired)
        finally:
            non_reentrant_lock.lock.release()


# Tests for AsyncTimeoutLock.

class TestAsyncTimeoutLock(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):

        self.async_lock = AsyncTimeoutLock("AsyncTestLock", priority=LockPriority.MEDIUM, timeout=1.0,
                                           is_instance_lock=False)

    async def test_async_acquire_and_release(self):

        acquired = await self.async_lock.acquire(timeout=0.5)

        self.assertTrue(acquired)
        self.assertEqual(self.async_lock.owner, f"{threading.get_ident()}:{id(asyncio.current_task())}")
        self.async_lock.release()
        self.assertIsNone(self.async_lock.owner)

    async def test_async_acquire_timeout(self):

        # Pre-acquire the asyncio lock.
        await self.async_lock.lock.acquire()
        try:
            acquired = await self.async_lock.acquire(timeout=0.1)

            self.assertFalse(acquired)
        finally:
            self.async_lock.lock.release()

    async def test_acquire_timeout_context_manager(self):

        async with self.async_lock.acquire_timeout(timeout=0.5) as acquired:
            self.assertTrue(acquired)

        self.assertIsNone(self.async_lock.owner)


# Tests for AsyncTimeoutSemaphore.

class TestAsyncTimeoutSemaphore(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.semaphore = AsyncTimeoutSemaphore("AsyncSemaphore", value=2, priority=LockPriority.MEDIUM, timeout=1.0)

    async def test_semaphore_acquire_release(self):
        # Acquire a permit.
        acquired = await self.semaphore.acquire(timeout=0.5)

        self.assertTrue(acquired)
        self.assertEqual(self.semaphore.current_value, 1)

        self.semaphore.release()
        self.assertEqual(self.semaphore.current_value, 2)

    async def test_semaphore_timeout(self):
        # Acquire both permits.
        acquired1 = await self.semaphore.acquire(timeout=0.5)
        acquired2 = await self.semaphore.acquire(timeout=0.5)

        self.assertTrue(acquired1)
        self.assertTrue(acquired2)

        # Try to acquire a third permit, expect timeout.
        acquired3 = await self.semaphore.acquire(timeout=0.1)
        self.assertFalse(acquired3)

        # Release one permit.
        self.semaphore.release()
        self.assertEqual(self.semaphore.current_value, 1)


# Test for module initialization function.

class TestInitFunction(unittest.TestCase):

    @patch('backend.app.utils.system_utils.synchronization_utils.logger')
    def test_init(self, mock_logger):
        # Remove handlers if any.
        module_logger = mock_logger
        module_logger.handlers = []
        init()

        # Expect an info log indicating initialization.
        mock_logger.info.assert_called_once_with("Synchronization utils initialized")
