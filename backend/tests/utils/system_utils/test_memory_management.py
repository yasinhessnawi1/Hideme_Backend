"""
Unit tests for memory_management.py module.

This test file covers all classes and functions in the memory_management module with both positive
and negative test cases to ensure proper functionality and error handling.
"""
import asyncio
import gc
import threading
import time
import unittest
from unittest.mock import patch, MagicMock

# Import the module to be tested
from backend.app.utils.system_utils.memory_management import (
    AtomicCounter,
    AtomicFloat,
    MemoryStats,
    MemoryMonitor, calc_adaptive_threshold, _gc_lock, _gc_stats, should_run_gc, run_gc, memory_monitor,
    post_function_cleanup, memory_optimized, )


class TestAtomicCounter(unittest.TestCase):
    """Test cases for AtomicCounter class."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        self.counter = AtomicCounter(initial=10)

    def test_init(self):
        """Test initialization with a specific value."""
        # Verify initial value
        self.assertEqual(self.counter.get(), 10)

        # Test default initialization
        default_counter = AtomicCounter()
        self.assertEqual(default_counter.get(), 0)

    def test_increment(self):
        """Test incrementing the counter."""
        # Increment by default amount (1)
        result = self.counter.increment()
        self.assertEqual(result, 11)
        self.assertEqual(self.counter.get(), 11)

        # Increment by specific amount
        result = self.counter.increment(5)
        self.assertEqual(result, 16)
        self.assertEqual(self.counter.get(), 16)

        # Increment by negative amount (decrement)
        result = self.counter.increment(-3)
        self.assertEqual(result, 13)
        self.assertEqual(self.counter.get(), 13)

    def test_get(self):
        """Test getting the counter value."""
        self.assertEqual(self.counter.get(), 10)

        # Modify value and verify get returns updated value
        self.counter.increment(5)
        self.assertEqual(self.counter.get(), 15)

    def test_set(self):
        """Test setting the counter to a new value."""
        self.counter.set(20)
        self.assertEqual(self.counter.get(), 20)

        # Set to negative value
        self.counter.set(-5)
        self.assertEqual(self.counter.get(), -5)

        # Set to zero
        self.counter.set(0)
        self.assertEqual(self.counter.get(), 0)

    def test_thread_safety(self):
        """Test thread safety of the counter operations."""
        # Create a counter starting at 0
        thread_counter = AtomicCounter(0)

        # Define a function that increments the counter multiple times
        def increment_counter():
            for _ in range(100):
                thread_counter.increment()

        # Create and start multiple threads
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=increment_counter)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify the counter has been incremented correctly
        self.assertEqual(thread_counter.get(), 1000)


class TestAtomicFloat(unittest.TestCase):
    """Test cases for AtomicFloat class."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        self.float_value = AtomicFloat(initial=10.5)

    def test_init(self):
        """Test initialization with a specific value."""
        # Verify initial value
        self.assertEqual(self.float_value.get(), 10.5)

        # Test default initialization
        default_float = AtomicFloat()
        self.assertEqual(default_float.get(), 0.0)

    def test_add(self):
        """Test adding to the float value."""
        # Add positive value
        result = self.float_value.add(2.5)
        self.assertEqual(result, 13.0)
        self.assertEqual(self.float_value.get(), 13.0)

        # Add negative value (subtract)
        result = self.float_value.add(-3.5)
        self.assertEqual(result, 9.5)
        self.assertEqual(self.float_value.get(), 9.5)

        # Add zero
        result = self.float_value.add(0.0)
        self.assertEqual(result, 9.5)
        self.assertEqual(self.float_value.get(), 9.5)

    def test_get(self):
        """Test getting the float value."""
        self.assertEqual(self.float_value.get(), 10.5)

        # Modify value and verify get returns updated value
        self.float_value.add(5.5)
        self.assertEqual(self.float_value.get(), 16.0)

    def test_set(self):
        """Test setting the float to a new value."""
        self.float_value.set(20.5)
        self.assertEqual(self.float_value.get(), 20.5)

        # Set to negative value
        self.float_value.set(-5.5)
        self.assertEqual(self.float_value.get(), -5.5)

        # Set to zero
        self.float_value.set(0.0)
        self.assertEqual(self.float_value.get(), 0.0)

    def test_thread_safety(self):
        """Test thread safety of the float operations."""
        # Create a float starting at 0.0
        thread_float = AtomicFloat(0.0)

        # Define a function that adds to the float multiple times
        def add_to_float():
            for _ in range(100):
                thread_float.add(0.1)

        # Create and start multiple threads
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=add_to_float)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify the float has been incremented correctly (allowing for floating point imprecision)
        self.assertAlmostEqual(thread_float.get(), 100.0, places=1)


class TestMemoryStats(unittest.TestCase):
    """Test cases for MemoryStats class."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        self.memory_stats = MemoryStats()

    def test_init(self):
        """Test initialization of MemoryStats."""
        # Verify all atomic values are initialized to 0
        self.assertEqual(self.memory_stats.peak_usage.get(), 0.0)
        self.assertEqual(self.memory_stats.average_usage.get(), 0.0)
        self.assertEqual(self.memory_stats.checks_count.get(), 0)
        self.assertEqual(self.memory_stats.emergency_cleanups.get(), 0)
        self.assertEqual(self.memory_stats.last_check_time.get(), 0.0)
        self.assertEqual(self.memory_stats.current_usage.get(), 0.0)
        self.assertEqual(self.memory_stats.available_memory_mb.get(), 0.0)
        self.assertEqual(self.memory_stats.system_threshold_adjustments.get(), 0)
        self.assertEqual(self.memory_stats.batch_operations.get(), 0)
        self.assertEqual(self.memory_stats.batch_peak_memory.get(), 0.0)

    def test_peak_usage(self):
        """Test peak_usage atomic float operations."""
        # Set and get peak usage
        self.memory_stats.peak_usage.set(50.0)
        self.assertEqual(self.memory_stats.peak_usage.get(), 50.0)

        # Add to peak usage
        self.memory_stats.peak_usage.add(10.0)
        self.assertEqual(self.memory_stats.peak_usage.get(), 60.0)

    def test_average_usage(self):
        """Test average_usage atomic float operations."""
        # Set and get average usage
        self.memory_stats.average_usage.set(30.0)
        self.assertEqual(self.memory_stats.average_usage.get(), 30.0)

        # Add to average usage
        self.memory_stats.average_usage.add(5.0)
        self.assertEqual(self.memory_stats.average_usage.get(), 35.0)

    def test_checks_count(self):
        """Test checks_count atomic counter operations."""
        # Increment checks count
        self.memory_stats.checks_count.increment()
        self.assertEqual(self.memory_stats.checks_count.get(), 1)

        # Increment by specific amount
        self.memory_stats.checks_count.increment(5)
        self.assertEqual(self.memory_stats.checks_count.get(), 6)

        # Set checks count
        self.memory_stats.checks_count.set(10)
        self.assertEqual(self.memory_stats.checks_count.get(), 10)

    def test_emergency_cleanups(self):
        """Test emergency_cleanups atomic counter operations."""
        # Increment emergency cleanups
        self.memory_stats.emergency_cleanups.increment()
        self.assertEqual(self.memory_stats.emergency_cleanups.get(), 1)

        # Increment by specific amount
        self.memory_stats.emergency_cleanups.increment(3)
        self.assertEqual(self.memory_stats.emergency_cleanups.get(), 4)

        # Set emergency cleanups
        self.memory_stats.emergency_cleanups.set(0)
        self.assertEqual(self.memory_stats.emergency_cleanups.get(), 0)

    def test_last_check_time(self):
        """Test last_check_time atomic float operations."""
        # Set last check time
        current_time = time.time()
        self.memory_stats.last_check_time.set(current_time)
        self.assertEqual(self.memory_stats.last_check_time.get(), current_time)

    def test_current_usage(self):
        """Test current_usage atomic float operations."""
        # Set current usage
        self.memory_stats.current_usage.set(45.5)
        self.assertEqual(self.memory_stats.current_usage.get(), 45.5)

        # Add to current usage
        self.memory_stats.current_usage.add(-5.5)
        self.assertEqual(self.memory_stats.current_usage.get(), 40.0)

    def test_available_memory_mb(self):
        """Test available_memory_mb atomic float operations."""
        # Set available memory
        self.memory_stats.available_memory_mb.set(1024.0)
        self.assertEqual(self.memory_stats.available_memory_mb.get(), 1024.0)

        # Add to available memory
        self.memory_stats.available_memory_mb.add(-256.0)
        self.assertEqual(self.memory_stats.available_memory_mb.get(), 768.0)

    def test_system_threshold_adjustments(self):
        """Test system_threshold_adjustments atomic counter operations."""
        # Increment system threshold adjustments
        self.memory_stats.system_threshold_adjustments.increment()
        self.assertEqual(self.memory_stats.system_threshold_adjustments.get(), 1)

        # Set system threshold adjustments
        self.memory_stats.system_threshold_adjustments.set(5)
        self.assertEqual(self.memory_stats.system_threshold_adjustments.get(), 5)

    def test_batch_operations(self):
        """Test batch_operations atomic counter operations."""
        # Increment batch operations
        self.memory_stats.batch_operations.increment()
        self.assertEqual(self.memory_stats.batch_operations.get(), 1)

        # Set batch operations
        self.memory_stats.batch_operations.set(10)
        self.assertEqual(self.memory_stats.batch_operations.get(), 10)

    def test_batch_peak_memory(self):
        """Test batch_peak_memory atomic float operations."""
        # Set batch peak memory
        self.memory_stats.batch_peak_memory.set(75.5)
        self.assertEqual(self.memory_stats.batch_peak_memory.get(), 75.5)

        # Add to batch peak memory
        self.memory_stats.batch_peak_memory.add(10.0)
        self.assertEqual(self.memory_stats.batch_peak_memory.get(), 85.5)


class TestMemoryMonitor(unittest.TestCase):
    """Test cases for MemoryMonitor class."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        # Patch the TimeoutLock to avoid actual lock creation
        self.lock_patcher = patch('backend.app.utils.system_utils.memory_management.TimeoutLock')
        self.mock_lock = self.lock_patcher.start()

        # Patch psutil.virtual_memory to avoid actual system calls
        self.vm_patcher = patch('psutil.virtual_memory')
        self.mock_vm = self.vm_patcher.start()

        # Configure mock virtual memory
        mock_vm_instance = MagicMock()
        mock_vm_instance.total = 8 * 1024 * 1024 * 1024  # 8 GB
        mock_vm_instance.available = 4 * 1024 * 1024 * 1024  # 4 GB
        mock_vm_instance.percent = 50.0
        self.mock_vm.return_value = mock_vm_instance

        # Patch psutil.Process to avoid actual process info retrieval
        self.process_patcher = patch('psutil.Process')
        self.mock_process = self.process_patcher.start()

        # Configure mock process
        mock_process_instance = MagicMock()
        mock_memory_info = MagicMock()
        mock_memory_info.rss = 1 * 1024 * 1024 * 1024  # 1 GB
        mock_process_instance.memory_info.return_value = mock_memory_info
        self.mock_process.return_value = mock_process_instance

        # Patch threading.Thread to avoid actual thread creation
        self.thread_patcher = patch('threading.Thread')
        self.mock_thread = self.thread_patcher.start()

        # Patch logger to avoid actual logging
        self.logger_patcher = patch('backend.app.utils.system_utils.memory_management.logger')
        self.mock_logger = self.logger_patcher.start()

        # Create a MemoryMonitor instance with monitoring disabled
        self.memory_monitor = MemoryMonitor(
            memory_threshold=80.0,
            critical_threshold=90.0,
            check_interval=5.0,
            enable_monitoring=False,
            adaptive_thresholds=True
        )

    def tearDown(self):
        """Tear down test fixtures after each test method."""
        # Stop all patchers
        self.lock_patcher.stop()
        self.vm_patcher.stop()
        self.process_patcher.stop()
        self.thread_patcher.stop()
        self.logger_patcher.stop()

        # Ensure monitor is stopped
        if hasattr(self.memory_monitor, '_monitor_thread') and self.memory_monitor._monitor_thread:
            self.memory_monitor.stop_monitoring()

    def test_init(self):
        """Test initialization of MemoryMonitor."""
        # Verify initialization parameters
        self.assertEqual(self.memory_monitor.base_memory_threshold, 80.0)
        self.assertEqual(self.memory_monitor.base_critical_threshold, 90.0)
        self.assertEqual(self.memory_monitor.memory_threshold, 80.0)
        self.assertEqual(self.memory_monitor.critical_threshold, 90.0)
        self.assertEqual(self.memory_monitor.check_interval, 5.0)
        self.assertFalse(self.memory_monitor.enable_monitoring)
        self.assertTrue(self.memory_monitor.adaptive_thresholds)

        # Verify memory stats was initialized
        self.assertIsInstance(self.memory_monitor.memory_stats, MemoryStats)

        # Verify batch thresholds were set
        self.assertEqual(self.memory_monitor.batch_memory_threshold, 70.0)
        self.assertEqual(self.memory_monitor.batch_max_memory_factor, 0.8)

        # Verify _update_available_memory was called
        self.mock_vm.assert_called()

        # Verify _adjust_thresholds_based_on_system was called
        self.assertGreater(self.mock_vm.call_count, 1)


class TestMemoryMonitorExtraMethods(unittest.TestCase):
    """Tests additional methods of MemoryMonitor and related helper functions."""

    def setUp(self):
        # Patch psutil.virtual_memory to simulate system memory values.
        self.vm_patcher = patch('psutil.virtual_memory')
        self.mock_vm = self.vm_patcher.start()
        mock_vm_instance = MagicMock()
        # 8GB total, 4GB available, and 50% usage.
        mock_vm_instance.total = 8 * 1024 * 1024 * 1024
        mock_vm_instance.available = 4 * 1024 * 1024 * 1024
        mock_vm_instance.percent = 50.0
        self.mock_vm.return_value = mock_vm_instance

        # Patch psutil.Process to simulate process memory usage.
        self.process_patcher = patch('psutil.Process')
        self.mock_process = self.process_patcher.start()
        mock_process_instance = MagicMock()
        # Set RSS (Resident Set Size) to simulate 1GB usage.
        mock_memory_info = MagicMock(rss=1 * 1024 * 1024 * 1024)
        mock_process_instance.memory_info.return_value = mock_memory_info
        self.mock_process.return_value = mock_process_instance

        # Patch logger to intercept log calls.
        self.logger_patcher = patch('backend.app.utils.system_utils.memory_management.logger')
        self.mock_logger = self.logger_patcher.start()

        # Create a MemoryMonitor instance with monitoring disabled (for testing method calls).
        self.memory_monitor = MemoryMonitor(
            memory_threshold=80.0,
            critical_threshold=90.0,
            check_interval=1.0,
            enable_monitoring=False,
            adaptive_thresholds=True
        )

    def tearDown(self):
        self.vm_patcher.stop()
        self.process_patcher.stop()
        self.logger_patcher.stop()

    def test_get_memory_usage(self):
        """Test that get_memory_usage computes the expected percentage."""
        # Expected: (1GB / 8GB)*100 = 12.5%
        usage = self.memory_monitor.get_memory_usage()
        expected = (1 * 1024 * 1024 * 1024) / (8 * 1024 * 1024 * 1024) * 100.0
        self.assertAlmostEqual(usage, expected)

    def test_get_memory_stats(self):
        """Test that get_memory_stats returns the atomic values correctly."""
        # Manually set one of the stats.
        self.memory_monitor.memory_stats.peak_usage.set(55.0)
        stats = self.memory_monitor.get_memory_stats()
        self.assertEqual(stats['peak_usage'], 55.0)

    def test_update_memory_stats(self):
        """Test _update_memory_stats updates current usage, check count and average usage."""
        self.memory_monitor._update_memory_stats(60.0)
        self.assertAlmostEqual(self.memory_monitor.memory_stats.current_usage.get(), 60.0)
        # After one update, the count should be 1 and average equals current value.
        self.assertEqual(self.memory_monitor.memory_stats.checks_count.get(), 1)
        self.assertAlmostEqual(self.memory_monitor.memory_stats.average_usage.get(), 60.0)

    @patch('gc.collect')
    def test_perform_cleanup(self, mock_gc_collect):
        """Test _perform_cleanup calls garbage collection and logs cleanup info."""

        # Simulate memory usage before cleanup and then after cleanup.
        # First call to get_memory_usage returns 80.0, then 70.0 after cleanup.
        call_values = [80.0, 70.0]
        self.memory_monitor.get_memory_usage = MagicMock(
            side_effect=lambda: call_values.pop(0) if call_values else 70.0)

        # Force a full GC by setting last_gc_time far in the past.
        self.memory_monitor._last_gc_time = time.time() - 100
        self.memory_monitor._perform_cleanup()

        # Check that gc.collect was called with generation=2.
        mock_gc_collect.assert_called_with(generation=2)

        # Verify that logging has been used.
        self.mock_logger.info.assert_called()

    @patch('gc.collect')
    @patch('backend.app.utils.system_utils.memory_management.MemoryMonitor._free_additional_memory')
    def test_emergency_cleanup(self, mock_free_mem, mock_gc_collect):
        """Test that _emergency_cleanup performs a full GC and calls additional memory freeing."""

        # Set critical memory usage.
        self.memory_monitor.memory_stats.current_usage.set(92.0)

        # Patch get_memory_usage to simulate a drop (e.g., to 80% after cleanup).
        self.memory_monitor.get_memory_usage = MagicMock(return_value=80.0)
        self.memory_monitor._emergency_cleanup()
        mock_gc_collect.assert_called_with(generation=2)
        mock_free_mem.assert_called_once()
        self.mock_logger.error.assert_called()

    def test_clear_application_caches(self):
        """Test _clear_application_caches does not raise errors if cache import fails."""

        # Since the function has nested try/except blocks, simply call it.
        # It will try to import invalidate_cache which may not exist in our test environment.
        from backend.app.utils.system_utils.memory_management import MemoryMonitor
        MemoryMonitor._clear_application_caches()

        # If no exception is raised, the test passes.
        self.assertTrue(True)

    @patch('backend.app.utils.system_utils.memory_management.gc.collect')
    @patch('backend.app.utils.system_utils.memory_management.gc.malloc_trim', create=True)
    def test_free_additional_memory(self, mock_malloc_trim, mock_gc_collect):

        """Test that _free_additional_memory calls gc.collect and (if available) malloc_trim."""
        from backend.app.utils.system_utils.memory_management import MemoryMonitor
        MemoryMonitor._free_additional_memory()
        mock_gc_collect.assert_called()

        # If gc.malloc_trim exists, it should have been called.
        if hasattr(gc, 'malloc_trim'):
            mock_malloc_trim.assert_called()

    def test_adjust_thresholds_based_on_system(self):
        """Test that _adjust_thresholds_based_on_system updates memory and batch thresholds."""

        # Call adjustment to update thresholds based on the simulated system memory.
        self.memory_monitor._adjust_thresholds_based_on_system()

        # With 8GB total memory and 50% usage, thresholds should not be extremely lowered or raised.
        self.assertGreaterEqual(self.memory_monitor.memory_threshold, 70.0)
        self.assertGreaterEqual(self.memory_monitor.critical_threshold, 85.0)
        self.assertGreaterEqual(self.memory_monitor.batch_memory_threshold, 50.0)


class TestGlobalMemoryFunctions(unittest.TestCase):
    """Tests for the global helper functions defined in the module."""

    def setUp(self):
        # Patch psutil.virtual_memory for consistent results.
        self.vm_patcher = patch('psutil.virtual_memory')
        self.mock_vm = self.vm_patcher.start()
        mock_vm_instance = MagicMock(total=8 * 1024 * 1024 * 1024,
                                     available=4 * 1024 * 1024 * 1024,
                                     percent=50.0)
        self.mock_vm.return_value = mock_vm_instance

    def tearDown(self):
        self.vm_patcher.stop()

    def test_default_threshold(self):
        """Test that _default_threshold returns expected values based on inputs."""
        from backend.app.utils.system_utils.memory_management import _default_threshold
        self.assertEqual(_default_threshold(25, 1500), 30)
        self.assertEqual(_default_threshold(25, 500), 15)
        self.assertEqual(_default_threshold(50, 600), 20)
        self.assertEqual(_default_threshold(50, 400), 10)
        self.assertEqual(_default_threshold(70, 400), 10)
        self.assertEqual(_default_threshold(70, 200), 5)

    def test_calc_adaptive_threshold_with_provided(self):
        """Test calc_adaptive_threshold when a threshold is provided."""
        threshold, initial_mem = calc_adaptive_threshold("dummy_func", 25)

        self.assertEqual(threshold, 25)
        self.assertIsInstance(initial_mem, float)

    def test_should_run_gc(self):
        """Test should_run_gc returns proper flag and generation based on input conditions."""
        func_name = "dummy_func"

        # Initialize GC stats for this function.
        with _gc_lock:
            _gc_stats[func_name] = {
                'last_gc_time': time.time() - 100,
                'last_gc_effectiveness': 10,
                'gc_calls': 0,
                'memory_increases': []
            }

        # If initial memory is very high, should run GC with generation 2.
        run_flag, gen = should_run_gc(95, 10, func_name)
        self.assertTrue(run_flag)
        self.assertEqual(gen, 2)

        # For moderate memory usage, conditions may differ.
        run_flag, _ = should_run_gc(55, 10, func_name)

        # We do a loose check because the exact generation depends on prior stats.
        self.assertIsInstance(run_flag, bool)

    @patch('gc.collect')
    def test_run_gc(self, mock_gc_collect):
        """Test run_gc calls gc.collect with the right generation and updates GC stats."""
        func_name = "dummy_func"
        with _gc_lock:
            _gc_stats.setdefault(func_name, {
                'last_gc_time': 0,
                'last_gc_effectiveness': 0,
                'gc_calls': 0,
                'memory_increases': []
            })
        run_gc(1, func_name)
        mock_gc_collect.assert_called_with(generation=1)

        with _gc_lock:
            self.assertGreater(_gc_stats[func_name]['gc_calls'], 0)


class TestMemoryOptimizedDecorator(unittest.TestCase):
    """Tests for the memory_optimized decorator covering both sync and async functions."""

    def setUp(self):

        # Create a sample decorated synchronous function and assign it for testing.
        @memory_optimized(threshold_mb=20, min_gc_interval=5.0)
        def sample_function(x, y):
            return x + y

        self.sample_function = sample_function

    @patch("backend.app.utils.system_utils.memory_management.gc.collect")
    def test_post_function_cleanup(self, mock_gc_collect):
        """Test that post_function_cleanup executes garbage collection when needed."""
        func_name = "dummy_func_cleanup"
        with _gc_lock:
            _gc_stats[func_name] = {
                'last_gc_time': time.time() - 100,
                'last_gc_effectiveness': 0,
                'gc_calls': 0,
                'memory_increases': []
            }

        # Simulate get_memory_usage:
        #   - In post_function_cleanup, the first call returns the final memory (85.0),
        #     and the second call returns the memory after cleanup (70.0).
        original_get = memory_monitor.get_memory_usage
        memory_monitor.get_memory_usage = MagicMock(side_effect=[85.0, 70.0])

        # Call the cleanup function with an initial memory of 50.0.
        post_function_cleanup(func_name, 10, 50.0)

        # Since final_memory=85.0 > 70.0, the cleanup branch will be taken
        # and since 85.0 > 70, it should call gc.collect with generation=1.
        mock_gc_collect.assert_called_with(generation=1)

        # Restore the original get_memory_usage method.
        memory_monitor.get_memory_usage = original_get

    def test_async_decorator(self):
        """Test that the decorated asynchronous function returns correct result."""
        # Patch get_memory_usage to provide enough return values:
        #   - First value for pre_exec initial memory (70.0),
        #   - Second for post_function_cleanup final memory (85.0),
        #   - Third for post_function_cleanup after cleanup (70.0)
        original_get = memory_monitor.get_memory_usage
        memory_monitor.get_memory_usage = MagicMock(side_effect=[70.0, 85.0, 70.0])

        @memory_optimized(threshold_mb=20, min_gc_interval=5.0)
        async def async_function(x, y):
            return x * y

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(async_function(3, 4))
        self.assertEqual(result, 12)
        loop.close()

        # Restore the original get_memory_usage method.
        memory_monitor.get_memory_usage = original_get

    def test_sync_decorator(self):
        """Test that the decorated synchronous function returns correct result."""
        # Patch get_memory_usage to supply three values:
        #   - First for pre_exec (initial memory: 70.0),
        #   - Second for post_function_cleanup final memory (85.0),
        #   - Third for post_function_cleanup after cleanup (70.0)
        original_get = memory_monitor.get_memory_usage
        memory_monitor.get_memory_usage = MagicMock(side_effect=[70.0, 85.0, 70.0])

        result = self.sample_function(5, 7)
        self.assertEqual(result, 12)

        # Restore the original get_memory_usage method.
        memory_monitor.get_memory_usage = original_get


class TestAdditionalMemoryMethods(unittest.TestCase):
    """Tests for additional methods of the memory_management module."""

    def setUp(self):

        # Create a MemoryMonitor instance with monitoring disabled to test non-threaded methods.
        self.monitor = MemoryMonitor(
            memory_threshold=80.0,
            critical_threshold=90.0,
            check_interval=1.0,
            enable_monitoring=False,
            adaptive_thresholds=True
        )

        # Reset the global GC stats for predictable behavior.
        with _gc_lock:
            _gc_stats.clear()

    @patch("psutil.virtual_memory")
    def test_adjust_thresholds_based_on_system_low_memory(self, mock_virtual_memory):
        """
        Test _adjust_thresholds_based_on_system for a low-memory system (<4GB).
        Expected: memory_threshold and critical_threshold are lowered.
        """

        # Simulate a system with total memory = 2GB, available = 1GB, percent usage 80%
        mock_vm_instance = MagicMock()
        mock_vm_instance.total = 2 * 1024 ** 3
        mock_vm_instance.available = 1 * 1024 ** 3
        mock_vm_instance.percent = 80.0
        mock_virtual_memory.return_value = mock_vm_instance

        # Call the method to adjust thresholds.
        self.monitor._adjust_thresholds_based_on_system()

        # For low memory systems:
        #   new_memory_threshold = max(60.0, base_memory_threshold - 20)
        #   with base_memory_threshold=80, this is max(60, 60)=60.
        #   new_critical_threshold = max(75.0, base_critical_threshold - 15)
        #   with base_critical_threshold=90, this is max(75, 75)=75.
        self.assertEqual(self.monitor.memory_threshold, 60.0)
        self.assertEqual(self.monitor.critical_threshold, 75.0)

        # And the batch threshold should be max(50.0, new_memory_threshold - 10) = max(50, 60-10)=50.
        self.assertEqual(self.monitor.batch_memory_threshold, 50.0)

        # Note: The system threshold adjustment counter is already incremented once during __init__
        # and again now, so we expect a value of 2.
        self.assertEqual(self.monitor.memory_stats.system_threshold_adjustments.get(), 2)

    @patch("psutil.virtual_memory")
    def test_adjust_thresholds_based_on_system_medium_usage(self, mock_virtual_memory):
        """
        Test _adjust_thresholds_based_on_system for a medium-memory system (4-8GB)
        with usage percent under 70.
        Expected: thresholds adjusted for medium systems.
        """

        # Simulate 6GB system, available 3GB, usage at 50%
        mock_vm_instance = MagicMock()
        mock_vm_instance.total = 6 * 1024 ** 3
        mock_vm_instance.available = 3 * 1024 ** 3
        mock_vm_instance.percent = 50.0
        mock_virtual_memory.return_value = mock_vm_instance

        self.monitor._adjust_thresholds_based_on_system()

        # For a medium system:
        #   new_memory_threshold = max(70.0, base_memory_threshold - 10) = max(70, 80-10)=70.
        #   new_critical_threshold = max(85.0, base_critical_threshold - 5) = max(85, 90-5)=85.
        self.assertEqual(self.monitor.memory_threshold, 70.0)
        self.assertEqual(self.monitor.critical_threshold, 85.0)

        # Batch threshold: max(50.0, new_memory_threshold - 10) = max(50, 70-10)=60.
        self.assertEqual(self.monitor.batch_memory_threshold, 60.0)

    @patch("backend.app.utils.system_utils.memory_management.logger")
    def test_stop_monitoring(self, mock_logger):
        """
        Test that stop_monitoring correctly stops a running monitor thread.
        We'll simulate a long-running thread by overriding the _monitor_memory method.
        """

        # Define a dummy _monitor_memory that simply waits on the event.
        def dummy_monitor():
            while not self.monitor._stop_monitor.is_set():
                time.sleep(0.1)

        # Replace the monitor thread with one running dummy_monitor using a Mock.
        self.monitor._monitor_thread = unittest.mock.Mock()
        self.monitor._monitor_thread.is_alive = MagicMock(return_value=True)

        # Simulate the join method.
        self.monitor._monitor_thread.join = MagicMock()

        # Ensure the stop event is not set, then call stop_monitoring.
        self.monitor._stop_monitor.clear()
        self.monitor.stop_monitoring()

        # Assert that join was called with timeout.
        self.monitor._monitor_thread.join.assert_called_with(timeout=2.0)

        # Assert that logger.info was called with a message that contains "Memory monitoring stopped".
        self.assertTrue(any("Memory monitoring stopped" in call_args[0][0]
                            for call_args in mock_logger.info.call_args_list))

    @patch("backend.app.utils.system_utils.memory_management.memory_monitor.get_memory_usage")
    def test_calc_adaptive_threshold_with_prior_gc_stats(self, mock_get_memory_usage):
        """
        Test calc_adaptive_threshold without a provided threshold.
        It should compute an adaptive threshold based on prior GC stats.
        """
        # Set up dummy GC stats for a function "dummy_func"
        func_name = "dummy_func"
        with _gc_lock:
            _gc_stats[func_name] = {
                'total_calls': 10,
                'last_gc_time': time.time() - 100,
                'last_gc_effectiveness': 5,
                'gc_calls': 2,
                'memory_increases': [10.0, 15.0, 20.0]  # Average increase = 15.0
            }

        # Simulate current memory usage (say 70%)
        mock_get_memory_usage.return_value = 70.0

        # Also, set available_memory_mb in memory_stats (simulate 1024MB available)
        self.monitor.memory_stats.available_memory_mb.set(1024.0)

        # Now call calc_adaptive_threshold without a provided threshold.
        threshold, initial_memory = calc_adaptive_threshold(func_name, None)

        # Since avg_increase = 15, we expect threshold = max(5, min(100, 15*1.5)) = 22.5 (float)
        self.assertAlmostEqual(threshold, 22.5, places=1)
        self.assertEqual(initial_memory, 70.0)

    @patch("backend.app.utils.system_utils.memory_management.memory_monitor.get_memory_usage")
    def test_calc_adaptive_threshold_with_provided_value(self, mock_get_memory_usage):
        """
        Test calc_adaptive_threshold when a provided threshold is not None.
        It should simply return the provided threshold.
        """
        func_name = "dummy_func2"

        # Set a dummy value for get_memory_usage.
        mock_get_memory_usage.return_value = 65.0
        threshold, initial_memory = calc_adaptive_threshold(func_name, 30)
        self.assertEqual(threshold, 30)
        self.assertEqual(initial_memory, 65.0)
