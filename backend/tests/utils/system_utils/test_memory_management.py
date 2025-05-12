import asyncio
import gc
import threading
import time
import unittest
from unittest.mock import patch, MagicMock

from backend.app.utils.system_utils.memory_management import (
    AtomicCounter,
    AtomicFloat,
    MemoryStats,
    MemoryMonitor,
    calc_adaptive_threshold,
    _gc_lock,
    _gc_stats,
    should_run_gc,
    run_gc,
    memory_monitor,
    post_function_cleanup,
    memory_optimized,
)


# Tests for AtomicCounter
class TestAtomicCounter(unittest.TestCase):

    # Setup before each test
    def setUp(self):

        self.counter = AtomicCounter(initial=10)

    # Test initialization
    def test_init(self):

        self.assertEqual(self.counter.get(), 10)

        default_counter = AtomicCounter()

        self.assertEqual(default_counter.get(), 0)

    # Test increment functionality
    def test_increment(self):

        result = self.counter.increment()

        self.assertEqual(result, 11)

        self.assertEqual(self.counter.get(), 11)

        result = self.counter.increment(5)

        self.assertEqual(result, 16)

        self.assertEqual(self.counter.get(), 16)

        result = self.counter.increment(-3)

        self.assertEqual(result, 13)

        self.assertEqual(self.counter.get(), 13)

    # Test get method
    def test_get(self):

        self.assertEqual(self.counter.get(), 10)

        self.counter.increment(5)

        self.assertEqual(self.counter.get(), 15)

    # Test set method
    def test_set(self):

        self.counter.set(20)

        self.assertEqual(self.counter.get(), 20)

        self.counter.set(-5)

        self.assertEqual(self.counter.get(), -5)

        self.counter.set(0)

        self.assertEqual(self.counter.get(), 0)

    # Test thread safety
    def test_thread_safety(self):

        thread_counter = AtomicCounter(0)

        def increment_counter():

            for _ in range(100):
                thread_counter.increment()

        threads = []

        for _ in range(10):
            thread = threading.Thread(target=increment_counter)

            threads.append(thread)

            thread.start()

        for thread in threads:
            thread.join()

        self.assertEqual(thread_counter.get(), 1000)


# Tests for AtomicFloat
class TestAtomicFloat(unittest.TestCase):

    # Setup before each test
    def setUp(self):

        self.float_value = AtomicFloat(initial=10.5)

    # Test initialization
    def test_init(self):

        self.assertEqual(self.float_value.get(), 10.5)

        default_float = AtomicFloat()

        self.assertEqual(default_float.get(), 0.0)

    # Test add method
    def test_add(self):

        result = self.float_value.add(2.5)

        self.assertEqual(result, 13.0)

        self.assertEqual(self.float_value.get(), 13.0)

        result = self.float_value.add(-3.5)

        self.assertEqual(result, 9.5)

        self.assertEqual(self.float_value.get(), 9.5)

        result = self.float_value.add(0.0)

        self.assertEqual(result, 9.5)

        self.assertEqual(self.float_value.get(), 9.5)

    # Test get method
    def test_get(self):

        self.assertEqual(self.float_value.get(), 10.5)

        self.float_value.add(5.5)

        self.assertEqual(self.float_value.get(), 16.0)

    # Test set method
    def test_set(self):

        self.float_value.set(20.5)

        self.assertEqual(self.float_value.get(), 20.5)

        self.float_value.set(-5.5)

        self.assertEqual(self.float_value.get(), -5.5)

        self.float_value.set(0.0)

        self.assertEqual(self.float_value.get(), 0.0)

    # Test thread safety
    def test_thread_safety(self):

        thread_float = AtomicFloat(0.0)

        def add_to_float():

            for _ in range(100):
                thread_float.add(0.1)

        threads = []

        for _ in range(10):
            thread = threading.Thread(target=add_to_float)

            threads.append(thread)

            thread.start()

        for thread in threads:
            thread.join()

        self.assertAlmostEqual(thread_float.get(), 100.0, places=1)


# Tests for MemoryStats
class TestMemoryStats(unittest.TestCase):

    # Setup before each test
    def setUp(self):
        self.memory_stats = MemoryStats()

    # Test initialization
    def test_init(self):
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

    # Test peak_usage operations
    def test_peak_usage(self):
        self.memory_stats.peak_usage.set(50.0)

        self.assertEqual(self.memory_stats.peak_usage.get(), 50.0)

        self.memory_stats.peak_usage.add(10.0)

        self.assertEqual(self.memory_stats.peak_usage.get(), 60.0)

    # Test average_usage operations
    def test_average_usage(self):
        self.memory_stats.average_usage.set(30.0)

        self.assertEqual(self.memory_stats.average_usage.get(), 30.0)

        self.memory_stats.average_usage.add(5.0)

        self.assertEqual(self.memory_stats.average_usage.get(), 35.0)

    # Test checks_count operations
    def test_checks_count(self):
        self.memory_stats.checks_count.increment()

        self.assertEqual(self.memory_stats.checks_count.get(), 1)

        self.memory_stats.checks_count.increment(5)

        self.assertEqual(self.memory_stats.checks_count.get(), 6)

        self.memory_stats.checks_count.set(10)

        self.assertEqual(self.memory_stats.checks_count.get(), 10)

    # Test emergency_cleanups operations
    def test_emergency_cleanups(self):
        self.memory_stats.emergency_cleanups.increment()

        self.assertEqual(self.memory_stats.emergency_cleanups.get(), 1)

        self.memory_stats.emergency_cleanups.increment(3)

        self.assertEqual(self.memory_stats.emergency_cleanups.get(), 4)

        self.memory_stats.emergency_cleanups.set(0)

        self.assertEqual(self.memory_stats.emergency_cleanups.get(), 0)

    # Test last_check_time operations
    def test_last_check_time(self):
        current_time = time.time()

        self.memory_stats.last_check_time.set(current_time)

        self.assertEqual(self.memory_stats.last_check_time.get(), current_time)

    # Test current_usage operations
    def test_current_usage(self):
        self.memory_stats.current_usage.set(45.5)

        self.assertEqual(self.memory_stats.current_usage.get(), 45.5)

        self.memory_stats.current_usage.add(-5.5)

        self.assertEqual(self.memory_stats.current_usage.get(), 40.0)

    # Test available_memory_mb operations
    def test_available_memory_mb(self):
        self.memory_stats.available_memory_mb.set(1024.0)

        self.assertEqual(self.memory_stats.available_memory_mb.get(), 1024.0)

        self.memory_stats.available_memory_mb.add(-256.0)

        self.assertEqual(self.memory_stats.available_memory_mb.get(), 768.0)

    # Test system_threshold_adjustments operations
    def test_system_threshold_adjustments(self):
        self.memory_stats.system_threshold_adjustments.increment()

        self.assertEqual(self.memory_stats.system_threshold_adjustments.get(), 1)

        self.memory_stats.system_threshold_adjustments.set(5)

        self.assertEqual(self.memory_stats.system_threshold_adjustments.get(), 5)

    # Test batch_operations operations
    def test_batch_operations(self):
        self.memory_stats.batch_operations.increment()

        self.assertEqual(self.memory_stats.batch_operations.get(), 1)

        self.memory_stats.batch_operations.set(10)

        self.assertEqual(self.memory_stats.batch_operations.get(), 10)

    # Test batch_peak_memory operations
    def test_batch_peak_memory(self):
        self.memory_stats.batch_peak_memory.set(75.5)

        self.assertEqual(self.memory_stats.batch_peak_memory.get(), 75.5)

        self.memory_stats.batch_peak_memory.add(10.0)

        self.assertEqual(self.memory_stats.batch_peak_memory.get(), 85.5)


# Tests for MemoryMonitor
class TestMemoryMonitor(unittest.TestCase):

    # Setup before each test
    def setUp(self):
        self.lock_patcher = patch(
            "backend.app.utils.system_utils.memory_management.TimeoutLock"
        )

        self.mock_lock = self.lock_patcher.start()

        self.vm_patcher = patch("psutil.virtual_memory")

        self.mock_vm = self.vm_patcher.start()

        mock_vm_instance = MagicMock()

        mock_vm_instance.total = 8 * 1024 * 1024 * 1024

        mock_vm_instance.available = 4 * 1024 * 1024 * 1024

        mock_vm_instance.percent = 50.0

        self.mock_vm.return_value = mock_vm_instance

        self.process_patcher = patch("psutil.Process")

        self.mock_process = self.process_patcher.start()

        mock_process_instance = MagicMock()

        mock_memory_info = MagicMock()

        mock_memory_info.rss = 1 * 1024 * 1024 * 1024

        mock_process_instance.memory_info.return_value = mock_memory_info

        self.mock_process.return_value = mock_process_instance

        self.thread_patcher = patch("threading.Thread")

        self.mock_thread = self.thread_patcher.start()

        self.logger_patcher = patch(
            "backend.app.utils.system_utils.memory_management.logger"
        )

        self.mock_logger = self.logger_patcher.start()

        self.memory_monitor = MemoryMonitor(
            memory_threshold=80.0,
            critical_threshold=90.0,
            check_interval=5.0,
            enable_monitoring=False,
            adaptive_thresholds=True,
        )

    # Tear down after each test
    def tearDown(self):
        self.lock_patcher.stop()

        self.vm_patcher.stop()

        self.process_patcher.stop()

        self.thread_patcher.stop()

        self.logger_patcher.stop()

        if (
            hasattr(self.memory_monitor, "_monitor_thread")
            and self.memory_monitor._monitor_thread
        ):
            self.memory_monitor.stop_monitoring()

    # Test initialization
    def test_init(self):
        self.assertEqual(self.memory_monitor.base_memory_threshold, 80.0)

        self.assertEqual(self.memory_monitor.base_critical_threshold, 90.0)

        self.assertEqual(self.memory_monitor.memory_threshold, 80.0)

        self.assertEqual(self.memory_monitor.critical_threshold, 90.0)

        self.assertEqual(self.memory_monitor.check_interval, 5.0)

        self.assertFalse(self.memory_monitor.enable_monitoring)

        self.assertTrue(self.memory_monitor.adaptive_thresholds)

        self.assertIsInstance(self.memory_monitor.memory_stats, MemoryStats)

        self.assertEqual(self.memory_monitor.batch_memory_threshold, 70.0)

        self.assertEqual(self.memory_monitor.batch_max_memory_factor, 0.8)

        self.mock_vm.assert_called()

        self.assertGreater(self.mock_vm.call_count, 1)


# Tests for extra MemoryMonitor methods
class TestMemoryMonitorExtraMethods(unittest.TestCase):

    # Setup before each test
    def setUp(self):
        self.vm_patcher = patch("psutil.virtual_memory")

        self.mock_vm = self.vm_patcher.start()

        mock_vm_instance = MagicMock()

        mock_vm_instance.total = 8 * 1024 * 1024 * 1024

        mock_vm_instance.available = 4 * 1024 * 1024 * 1024

        mock_vm_instance.percent = 50.0

        self.mock_vm.return_value = mock_vm_instance

        self.process_patcher = patch("psutil.Process")

        self.mock_process = self.process_patcher.start()

        mock_process_instance = MagicMock()

        mock_memory_info = MagicMock(rss=1 * 1024 * 1024 * 1024)

        mock_process_instance.memory_info.return_value = mock_memory_info

        self.mock_process.return_value = mock_process_instance

        self.logger_patcher = patch(
            "backend.app.utils.system_utils.memory_management.logger"
        )

        self.mock_logger = self.logger_patcher.start()

        self.memory_monitor = MemoryMonitor(
            memory_threshold=80.0,
            critical_threshold=90.0,
            check_interval=1.0,
            enable_monitoring=False,
            adaptive_thresholds=True,
        )

    # Tear down after each test
    def tearDown(self):
        self.vm_patcher.stop()

        self.process_patcher.stop()

        self.logger_patcher.stop()

    # Test get_memory_usage
    def test_get_memory_usage(self):
        usage = self.memory_monitor.get_memory_usage()

        expected = (1 * 1024 * 1024 * 1024) / (8 * 1024 * 1024 * 1024) * 100.0

        self.assertAlmostEqual(usage, expected)

    # Test get_memory_stats
    def test_get_memory_stats(self):
        self.memory_monitor.memory_stats.peak_usage.set(55.0)

        stats = self.memory_monitor.get_memory_stats()

        self.assertEqual(stats["peak_usage"], 55.0)

    # Test update_memory_stats
    def test_update_memory_stats(self):
        self.memory_monitor._update_memory_stats(60.0)

        self.assertAlmostEqual(
            self.memory_monitor.memory_stats.current_usage.get(), 60.0
        )

        self.assertEqual(self.memory_monitor.memory_stats.checks_count.get(), 1)

        self.assertAlmostEqual(
            self.memory_monitor.memory_stats.average_usage.get(), 60.0
        )

    # Test perform_cleanup
    @patch("gc.collect")
    def test_perform_cleanup(self, mock_gc_collect):
        call_values = [80.0, 70.0]

        self.memory_monitor.get_memory_usage = MagicMock(
            side_effect=lambda: call_values.pop(0) if call_values else 70.0
        )

        self.memory_monitor._last_gc_time = time.time() - 100

        self.memory_monitor._perform_cleanup()

        mock_gc_collect.assert_called_with(generation=2)

        self.mock_logger.info.assert_called()

    # Test emergency_cleanup
    @patch("gc.collect")
    @patch(
        "backend.app.utils.system_utils.memory_management.MemoryMonitor._free_additional_memory"
    )
    def test_emergency_cleanup(self, mock_free_mem, mock_gc_collect):
        self.memory_monitor.memory_stats.current_usage.set(92.0)

        self.memory_monitor.get_memory_usage = MagicMock(return_value=80.0)

        self.memory_monitor._emergency_cleanup()

        mock_gc_collect.assert_called_with(generation=2)

        mock_free_mem.assert_called_once()

        self.mock_logger.error.assert_called()

    # Test clear_application_caches
    def test_clear_application_caches(self):
        from backend.app.utils.system_utils.memory_management import MemoryMonitor

        MemoryMonitor._clear_application_caches()

        self.assertTrue(True)

    # Test free_additional_memory
    @patch("backend.app.utils.system_utils.memory_management.gc.collect")
    @patch(
        "backend.app.utils.system_utils.memory_management.gc.malloc_trim", create=True
    )
    def test_free_additional_memory(self, mock_malloc_trim, mock_gc_collect):
        from backend.app.utils.system_utils.memory_management import MemoryMonitor

        MemoryMonitor._free_additional_memory()

        mock_gc_collect.assert_called()

        if hasattr(gc, "malloc_trim"):
            mock_malloc_trim.assert_called()

    # Test adjust_thresholds_based_on_system
    def test_adjust_thresholds_based_on_system(self):
        self.memory_monitor._adjust_thresholds_based_on_system()

        self.assertGreaterEqual(self.memory_monitor.memory_threshold, 70.0)

        self.assertGreaterEqual(self.memory_monitor.critical_threshold, 85.0)

        self.assertGreaterEqual(self.memory_monitor.batch_memory_threshold, 50.0)


# Tests for global helper functions
class TestGlobalMemoryFunctions(unittest.TestCase):

    # Setup before each test
    def setUp(self):
        self.vm_patcher = patch("psutil.virtual_memory")

        self.mock_vm = self.vm_patcher.start()

        mock_vm_instance = MagicMock(
            total=8 * 1024 * 1024 * 1024, available=4 * 1024 * 1024 * 1024, percent=50.0
        )

        self.mock_vm.return_value = mock_vm_instance

    # Tear down after each test
    def tearDown(self):
        self.vm_patcher.stop()

    # Test _default_threshold
    def test_default_threshold(self):
        from backend.app.utils.system_utils.memory_management import _default_threshold

        self.assertEqual(_default_threshold(25, 1500), 30)

        self.assertEqual(_default_threshold(25, 500), 15)

        self.assertEqual(_default_threshold(50, 600), 20)

        self.assertEqual(_default_threshold(50, 400), 10)

        self.assertEqual(_default_threshold(70, 400), 10)

        self.assertEqual(_default_threshold(70, 200), 5)

    # Test calc_adaptive_threshold with provided
    def test_calc_adaptive_threshold_with_provided(self):
        threshold, initial_mem = calc_adaptive_threshold("dummy_func", 25)

        self.assertEqual(threshold, 25)

        self.assertIsInstance(initial_mem, float)

    # Test should_run_gc
    def test_should_run_gc(self):
        func_name = "dummy_func"

        with _gc_lock:
            _gc_stats[func_name] = {
                "last_gc_time": time.time() - 100,
                "last_gc_effectiveness": 10,
                "gc_calls": 0,
                "memory_increases": [],
            }

        run_flag, gen = should_run_gc(95, 10, func_name)

        self.assertTrue(run_flag)

        self.assertEqual(gen, 2)

        run_flag, _ = should_run_gc(55, 10, func_name)

        self.assertIsInstance(run_flag, bool)

    # Test run_gc
    @patch("gc.collect")
    def test_run_gc(self, mock_gc_collect):
        func_name = "dummy_func"

        with _gc_lock:
            _gc_stats.setdefault(
                func_name,
                {
                    "last_gc_time": 0,
                    "last_gc_effectiveness": 0,
                    "gc_calls": 0,
                    "memory_increases": [],
                },
            )

        run_gc(1, func_name)

        mock_gc_collect.assert_called_with(generation=1)

        with _gc_lock:
            self.assertGreater(_gc_stats[func_name]["gc_calls"], 0)


# Tests for memory_optimized decorator
class TestMemoryOptimizedDecorator(unittest.TestCase):

    # Setup sample functions
    def setUp(self):
        @memory_optimized(threshold_mb=20, min_gc_interval=5.0)
        def sample_function(x, y):
            return x + y

        self.sample_function = sample_function

    # Test post_function_cleanup
    @patch("backend.app.utils.system_utils.memory_management.gc.collect")
    def test_post_function_cleanup(self, mock_gc_collect):
        func_name = "dummy_func_cleanup"

        with _gc_lock:
            _gc_stats[func_name] = {
                "last_gc_time": time.time() - 100,
                "last_gc_effectiveness": 0,
                "gc_calls": 0,
                "memory_increases": [],
            }

        original_get = memory_monitor.get_memory_usage

        memory_monitor.get_memory_usage = MagicMock(side_effect=[85.0, 70.0])

        post_function_cleanup(func_name, 10, 50.0)

        mock_gc_collect.assert_called_with(generation=1)

        memory_monitor.get_memory_usage = original_get

    # Test async decorator
    def test_async_decorator(self):
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

        memory_monitor.get_memory_usage = original_get

    # Test sync decorator
    def test_sync_decorator(self):
        original_get = memory_monitor.get_memory_usage

        memory_monitor.get_memory_usage = MagicMock(side_effect=[70.0, 85.0, 70.0])

        result = self.sample_function(5, 7)

        self.assertEqual(result, 12)

        memory_monitor.get_memory_usage = original_get


# Tests for additional module methods
class TestAdditionalMemoryMethods(unittest.TestCase):

    # Setup monitor and GC stats
    def setUp(self):
        self.monitor = MemoryMonitor(
            memory_threshold=80.0,
            critical_threshold=90.0,
            check_interval=1.0,
            enable_monitoring=False,
            adaptive_thresholds=True,
        )

        with _gc_lock:
            _gc_stats.clear()

    # Test low-memory adjustments
    @patch("psutil.virtual_memory")
    def test_adjust_thresholds_based_on_system_low_memory(self, mock_virtual_memory):
        mock_vm_instance = MagicMock()

        mock_vm_instance.total = 2 * 1024**3

        mock_vm_instance.available = 1 * 1024**3

        mock_vm_instance.percent = 80.0

        mock_virtual_memory.return_value = mock_vm_instance

        self.monitor._adjust_thresholds_based_on_system()

        self.assertEqual(self.monitor.memory_threshold, 60.0)

        self.assertEqual(self.monitor.critical_threshold, 75.0)

        self.assertEqual(self.monitor.batch_memory_threshold, 50.0)

        self.assertEqual(
            self.monitor.memory_stats.system_threshold_adjustments.get(), 2
        )

    # Test medium-memory adjustments
    @patch("psutil.virtual_memory")
    def test_adjust_thresholds_based_on_system_medium_usage(self, mock_virtual_memory):
        mock_vm_instance = MagicMock()

        mock_vm_instance.total = 6 * 1024**3

        mock_vm_instance.available = 3 * 1024**3

        mock_vm_instance.percent = 50.0

        mock_virtual_memory.return_value = mock_vm_instance

        self.monitor._adjust_thresholds_based_on_system()

        self.assertEqual(self.monitor.memory_threshold, 70.0)

        self.assertEqual(self.monitor.critical_threshold, 85.0)

        self.assertEqual(self.monitor.batch_memory_threshold, 60.0)

    # Test stopping monitor thread
    @patch("backend.app.utils.system_utils.memory_management.logger")
    def test_stop_monitoring(self, mock_logger):
        def dummy_monitor():
            while not self.monitor._stop_monitor.is_set():
                time.sleep(0.1)

        self.monitor._monitor_thread = unittest.mock.Mock()

        self.monitor._monitor_thread.is_alive = MagicMock(return_value=True)

        self.monitor._monitor_thread.join = MagicMock()

        self.monitor._stop_monitor.clear()

        self.monitor.stop_monitoring()

        self.monitor._monitor_thread.join

        self.assertTrue(
            any(
                "Memory monitoring stopped" in call_args[0][0]
                for call_args in mock_logger.info.call_args_list
            )
        )

    # Test adaptive threshold calculation
    @patch(
        "backend.app.utils.system_utils.memory_management.memory_monitor.get_memory_usage"
    )
    def test_calc_adaptive_threshold_with_prior_gc_stats(self, mock_get_memory_usage):
        func_name = "dummy_func"

        with _gc_lock:
            _gc_stats[func_name] = {
                "total_calls": 10,
                "last_gc_time": time.time() - 100,
                "last_gc_effectiveness": 5,
                "gc_calls": 2,
                "memory_increases": [10.0, 15.0, 20.0],
            }

        mock_get_memory_usage.return_value = 70.0

        self.monitor.memory_stats.available_memory_mb.set(1024.0)

        threshold, initial_memory = calc_adaptive_threshold(func_name, None)

        self.assertAlmostEqual(threshold, 22.5, places=1)

        self.assertEqual(initial_memory, 70.0)

    # Test calc_adaptive_threshold with provided value
    @patch(
        "backend.app.utils.system_utils.memory_management.memory_monitor.get_memory_usage"
    )
    def test_calc_adaptive_threshold_with_provided_value(self, mock_get_memory_usage):
        func_name = "dummy_func2"

        mock_get_memory_usage.return_value = 65.0

        threshold, initial_memory = calc_adaptive_threshold(func_name, 30)

        self.assertEqual(threshold, 30)

        self.assertEqual(initial_memory, 65.0)
