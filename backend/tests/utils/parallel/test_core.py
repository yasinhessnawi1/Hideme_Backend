import asyncio
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

from backend.app.utils.constant.constant import (
    DEFAULT_BATCH_TIMEOUT,
    DEFAULT_ITEM_TIMEOUT,
)
from backend.app.utils.parallel.core import (
    get_resource_lock,
    _loop_locks,
    ParallelProcessingCore,
)
from backend.app.utils.system_utils.synchronization_utils import LockPriority


# Helper to build patch targets for module functions
def module_target(name: str) -> str:
    return f"{ParallelProcessingCore.__module__}.{name}"


# Dummy async context manager for lock acquisition
class DummyAsyncCM:
    """Dummy async context manager for acquire_timeout."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass


# Tests for get_resource_lock function
class TestGetResourceLock(unittest.TestCase):
    """Test get_resource_lock for new and existing locks."""

    # new lock should be created and stored in loop map
    @patch("asyncio.get_running_loop")
    @patch(module_target("AsyncTimeoutLock"))
    def test_get_resource_lock_new(self, mock_lock_class, mock_get_loop):
        loop = asyncio.new_event_loop()

        mock_get_loop.return_value = loop

        mock_lock = MagicMock()

        mock_lock_class.return_value = mock_lock

        _loop_locks.clear()

        result = get_resource_lock()

        mock_lock_class.assert_called_once_with(
            "parallel_core_lock", priority=LockPriority.MEDIUM
        )

        self.assertIn(loop, _loop_locks)

        self.assertEqual(_loop_locks[loop], mock_lock)

        self.assertEqual(result, mock_lock)

    # existing lock should be returned without creating a new one
    @patch("asyncio.get_running_loop")
    @patch(module_target("AsyncTimeoutLock"))
    def test_get_resource_lock_existing(self, mock_lock_class, mock_get_loop):
        loop = asyncio.new_event_loop()

        mock_get_loop.return_value = loop

        existing_lock = MagicMock()

        _loop_locks[loop] = existing_lock

        result = get_resource_lock()

        mock_lock_class.assert_not_called()

        self.assertEqual(result, existing_lock)


# Tests for get_optimal_workers method
class TestParallelProcessingCoreGetOptimalWorkers(unittest.TestCase):
    """Test get_optimal_workers under various system loads."""

    def setUp(self):
        _loop_locks.clear()

    # basic scenario: moderate CPU and memory usage
    @patch("os.cpu_count")
    @patch("psutil.virtual_memory")
    @patch("psutil.cpu_percent")
    @patch(module_target("memory_monitor"))
    @patch(module_target("log_info"))
    def test_get_optimal_workers_basic(
        self, mock_log_info, mock_memmon, mock_cpu_percent, mock_vmem, mock_cpu_count
    ):
        mock_cpu_count.return_value = 8

        mock_vmem.return_value.available = 8 * 1024**3

        mock_cpu_percent.return_value = 50.0

        mock_memmon.get_memory_usage.return_value = 40.0

        result = ParallelProcessingCore.get_optimal_workers(items_count=10)

        self.assertGreaterEqual(result, 2)

        self.assertLessEqual(result, 8)

        mock_log_info.assert_called_once()

        self.assertIn("Calculated optimal workers", mock_log_info.call_args[0][0])

    # limit workers by memory per item
    @patch("os.cpu_count")
    @patch("psutil.virtual_memory")
    @patch("psutil.cpu_percent")
    @patch(module_target("memory_monitor"))
    @patch(module_target("log_info"))
    def test_get_optimal_workers_with_memory_per_item(
        self, mock_log_info, mock_memmon, mock_cpu_percent, mock_vmem, mock_cpu_count
    ):
        mock_cpu_count.return_value = 8

        mock_vmem.return_value.available = 1 * 1024**3

        mock_cpu_percent.return_value = 20.0

        mock_memmon.get_memory_usage.return_value = 30.0

        result = ParallelProcessingCore.get_optimal_workers(
            items_count=20, memory_per_item=100 * 1024**2
        )

        self.assertLessEqual(result, 8)

        mock_log_info.assert_called_once()

    # enforce custom min and max worker limits
    @patch("os.cpu_count")
    @patch("psutil.virtual_memory")
    @patch("psutil.cpu_percent")
    @patch(module_target("memory_monitor"))
    @patch(module_target("log_info"))
    def test_get_optimal_workers_with_custom_limits(
        self, mock_log_info, mock_memmon, mock_cpu_percent, mock_vmem, mock_cpu_count
    ):
        mock_cpu_count.return_value = 16

        mock_vmem.return_value.available = 16 * 1024**3

        mock_cpu_percent.return_value = 10.0

        mock_memmon.get_memory_usage.return_value = 20.0

        result = ParallelProcessingCore.get_optimal_workers(
            items_count=100, min_workers=4, max_workers=12
        )

        self.assertGreaterEqual(result, 4)

        self.assertLessEqual(result, 12)

        mock_log_info.assert_called_once()

    # if items count is small, result equals items_count
    @patch("os.cpu_count")
    @patch("psutil.virtual_memory")
    @patch("psutil.cpu_percent")
    @patch(module_target("memory_monitor"))
    @patch(module_target("log_info"))
    def test_get_optimal_workers_limited_by_items_count(
        self, mock_log_info, mock_memmon, mock_cpu_percent, mock_vmem, mock_cpu_count
    ):
        mock_cpu_count.return_value = 8

        mock_vmem.return_value.available = 8 * 1024**3

        mock_cpu_percent.return_value = 10.0

        mock_memmon.get_memory_usage.return_value = 20.0

        result = ParallelProcessingCore.get_optimal_workers(items_count=3)

        self.assertEqual(result, 3)

        mock_log_info.assert_called_once()

    # high system load still yields minimum workers
    @patch("os.cpu_count")
    @patch("psutil.virtual_memory")
    @patch("psutil.cpu_percent")
    @patch(module_target("memory_monitor"))
    @patch(module_target("log_info"))
    def test_get_optimal_workers_high_load(
        self, mock_log_info, mock_memmon, mock_cpu_percent, mock_vmem, mock_cpu_count
    ):
        mock_cpu_count.return_value = 8

        mock_vmem.return_value.available = 8 * 1024**3

        mock_cpu_percent.return_value = 90.0

        mock_memmon.get_memory_usage.return_value = 80.0

        result = ParallelProcessingCore.get_optimal_workers(items_count=10)

        self.assertGreaterEqual(result, 2)

        mock_log_info.assert_called_once()

    # fallback behavior when cpu_count returns None
    @patch("os.cpu_count")
    @patch("psutil.virtual_memory")
    @patch("psutil.cpu_percent")
    @patch(module_target("memory_monitor"))
    @patch(module_target("log_info"))
    def test_get_optimal_workers_cpu_count_none(
        self, mock_log_info, mock_memmon, mock_cpu_percent, mock_vmem, mock_cpu_count
    ):
        mock_cpu_count.return_value = None

        mock_vmem.return_value.available = 8 * 1024**3

        mock_cpu_percent.return_value = 50.0

        mock_memmon.get_memory_usage.return_value = 40.0

        result = ParallelProcessingCore.get_optimal_workers(items_count=10)

        self.assertGreaterEqual(result, 2)

        mock_log_info.assert_called_once()


# Tests for _validate_and_prepare_input method
class TestValidateAndPrepareInput(unittest.TestCase):
    """Test input validation and default timeout assignment."""

    # non-empty items use default timeouts
    def test_non_empty_items(self):
        items = [1, 2, 3]

        with patch("time.time", return_value=1000.0):
            op_id, batch_timeout, item_timeout, start_time = (
                ParallelProcessingCore._validate_and_prepare_input(
                    items, None, None, None
                )
            )

        self.assertTrue(op_id.startswith("parallel_"))

        self.assertEqual(batch_timeout, DEFAULT_BATCH_TIMEOUT)

        self.assertEqual(item_timeout, DEFAULT_ITEM_TIMEOUT)

        self.assertEqual(start_time, 1000.0)

    # empty items zero out timeouts and use provided op_id
    def test_empty_items(self):
        items = []

        with patch("time.time", return_value=2000.0):
            op_id, batch_timeout, item_timeout, start_time = (
                ParallelProcessingCore._validate_and_prepare_input(
                    items, None, None, "custom_op"
                )
            )

        self.assertEqual(op_id, "custom_op")

        self.assertEqual(batch_timeout, 0.0)

        self.assertEqual(item_timeout, 0.0)

        self.assertEqual(start_time, 2000.0)


# Tests for _acquire_worker_count method
class TestAcquireWorkerCount(unittest.IsolatedAsyncioTestCase):
    """Test adaptive lock-based worker acquisition."""

    # adaptive disabled returns max_workers directly
    async def test_acquire_worker_count_adaptive_off(self):
        items = [1, 2, 3, 4]

        result = await ParallelProcessingCore._acquire_worker_count(
            items, max_workers=2, adaptive=False
        )

        self.assertEqual(result, 2)

    # lock timeout triggers fallback heuristic
    async def test_acquire_worker_count_timeout(self):
        items = [1, 2, 3]

        dummy_lock = MagicMock()

        dummy_lock.acquire_timeout.side_effect = TimeoutError("Timeout")

        with patch(module_target("get_resource_lock"), return_value=dummy_lock):
            result = await ParallelProcessingCore._acquire_worker_count(
                items, max_workers=None, adaptive=True
            )

        self.assertEqual(result, 3)


# Tests for semaphore creation and progress data init
class TestCreateSemaphoreAndInitProgressData(unittest.TestCase):
    """Test internal helpers for semaphore and progress data."""

    # semaphore name and properties should match op_id
    def test_create_semaphore(self):
        op_id = "op_test"

        sem = ParallelProcessingCore._create_semaphore(5, op_id)

        self.assertEqual(sem.name, f"parallel_semaphore_{op_id}")

        self.assertEqual(sem.value, 5)

        self.assertEqual(sem.priority, LockPriority.MEDIUM)

    # progress data fields initialized correctly
    def test_init_progress_data(self):
        start = 1000.0

        total = 10

        progress = ParallelProcessingCore._init_progress_data(start, total)

        self.assertEqual(progress["completed"], 0)

        self.assertEqual(progress["failed"], 0)

        self.assertEqual(progress["total_items"], total)

        self.assertEqual(progress["start_time"], start)

        self.assertEqual(progress["last_progress_log"], start)

        self.assertIsNone(progress["last_index"])


# Tests for _create_tasks_map method
class TestCreateTasksMap(unittest.IsolatedAsyncioTestCase):
    """Test task mapping to asyncio.Tasks."""

    # tasks should be created with names equal to their index
    async def test_create_tasks_map(self):
        items = ["a", "b", "c"]

        semaphore = MagicMock()

        processor = AsyncMock(side_effect=lambda x: f"result_{x}")

        item_timeout = 5.0

        op_id = "op123"

        progress_data = {
            "completed": 0,
            "failed": 0,
            "total_items": 3,
            "start_time": 1000.0,
            "last_progress_log": 1000.0,
            "last_index": None,
        }

        progress_callback = None

        tasks_map = ParallelProcessingCore._create_tasks_map(
            items,
            semaphore,
            processor,
            item_timeout,
            op_id,
            progress_data,
            progress_callback,
        )

        self.assertEqual(len(tasks_map), 3)

        for i, task in tasks_map.items():
            self.assertIsInstance(task, asyncio.Task)

            self.assertEqual(task.get_name(), str(i))


# Tests for _process_with_semaphore method
class TestProcessWithSemaphore(unittest.IsolatedAsyncioTestCase):
    """Test processing items under semaphore lock."""

    # successful processing increments completed
    async def test_process_with_semaphore_success(self):
        semaphore = AsyncMock()

        semaphore.acquire_timeout = lambda timeout: DummyAsyncCM()

        processor = AsyncMock(return_value="success")

        progress_data = {
            "completed": 0,
            "failed": 0,
            "total_items": 1,
            "start_time": 1000.0,
            "last_progress_log": 1000.0,
            "last_index": None,
        }

        with patch.object(ParallelProcessingCore, "_update_progress") as mock_update:
            result = await ParallelProcessingCore._process_with_semaphore(
                index=0,
                item="test_item",
                semaphore=semaphore,
                processor=processor,
                item_timeout=5.0,
                operation_id="op_test",
                progress_data=progress_data,
                progress_callback=None,
            )

        self.assertEqual(result, (0, "success"))

        mock_update.assert_called_once_with(0, "op_test", progress_data, None)

    # timeout counts as failure
    async def test_process_with_semaphore_timeout(self):
        semaphore = AsyncMock()

        semaphore.acquire_timeout = lambda timeout: DummyAsyncCM()

        processor = AsyncMock(side_effect=asyncio.TimeoutError)

        progress_data = {
            "completed": 0,
            "failed": 0,
            "total_items": 1,
            "start_time": 1000.0,
            "last_progress_log": 1000.0,
            "last_index": None,
        }

        result = await ParallelProcessingCore._process_with_semaphore(
            index=0,
            item="test_item",
            semaphore=semaphore,
            processor=processor,
            item_timeout=0.1,
            operation_id="op_test",
            progress_data=progress_data,
            progress_callback=None,
        )

        self.assertEqual(result, (0, None))

        self.assertEqual(progress_data["failed"], 1)

    # exceptions trigger error handler and count failure
    async def test_process_with_semaphore_exception(self):
        semaphore = AsyncMock()

        semaphore.acquire_timeout = lambda timeout: DummyAsyncCM()

        processor = AsyncMock(side_effect=Exception("error"))

        progress_data = {
            "completed": 0,
            "failed": 0,
            "total_items": 1,
            "start_time": 1000.0,
            "last_progress_log": 1000.0,
            "last_index": None,
        }

        with patch(
            module_target("SecurityAwareErrorHandler") + ".log_processing_error",
            return_value="error_id_123",
        ):
            result = await ParallelProcessingCore._process_with_semaphore(
                index=0,
                item="test_item",
                semaphore=semaphore,
                processor=processor,
                item_timeout=5.0,
                operation_id="op_test",
                progress_data=progress_data,
                progress_callback=None,
            )

        self.assertEqual(result, (0, None))

        self.assertEqual(progress_data["failed"], 1)


# Tests for _update_progress method
class TestUpdateProgress(unittest.TestCase):
    """Test updating and logging progress."""

    # progress_data should update and log info
    def test_update_progress_logs_and_updates(self):
        progress_data = {
            "completed": 0,
            "total_items": 10,
            "start_time": 1000.0,
            "last_progress_log": 990.0,
            "last_index": None,
        }

        with patch(module_target("log_info")) as mock_log_info:
            ParallelProcessingCore._update_progress(5, "op_test", progress_data, None)

        self.assertEqual(progress_data["completed"], 1)

        self.assertEqual(progress_data["last_index"], 5)

        mock_log_info.assert_called()


# Tests for task gathering and partial collection
class TestGatherAndCollectResults(unittest.IsolatedAsyncioTestCase):
    """Test gathering tasks with timeout and collecting partial results."""

    # completed tasks should be returned in order
    async def test_gather_tasks_with_timeout_completed(self):
        async def dummy(i):
            return (i, "dummy_result")

        tasks_map = {i: asyncio.create_task(dummy(i), name=str(i)) for i in range(3)}

        for t in tasks_map.values():
            await t

        result = await ParallelProcessingCore._gather_tasks_with_timeout(
            tasks_map,
            batch_timeout=5.0,
            operation_id="op",
            progress_data={"total_items": 3, "completed": 3},
        )

        expected = [(0, "dummy_result"), (1, "dummy_result"), (2, "dummy_result")]

        self.assertEqual(result, expected)

    # pending tasks yield None results in collection
    async def test_collect_partial_results(self):
        async def dummy_success():
            return (0, "ok")

        async def dummy_never():
            await asyncio.sleep(1)

        done_task = asyncio.create_task(dummy_success())

        await done_task

        pending_task = asyncio.create_task(dummy_never())

        tasks_map = {0: done_task, 1: pending_task}

        partial = ParallelProcessingCore._collect_partial_results(tasks_map)

        self.assertEqual(partial, [done_task.result(), (1, None)])

        pending_task.cancel()


# Tests for _log_final_completion method
class TestLogFinalCompletion(unittest.TestCase):
    """Test final logging and sensitive summary at end."""

    # should log final completion and sensitive operation summary
    def test_log_final_completion(self):
        with patch(module_target("log_info")) as mock_log_info, patch(
            module_target("log_sensitive_operation")
        ) as mock_sensitive:
            results = [(0, "res1"), (1, None)]

            progress_data = {
                "completed": 1,
                "failed": 1,
                "total_items": 2,
                "start_time": 1000.0,
            }

            with patch("time.time", return_value=1010.0):
                ParallelProcessingCore._log_final_completion(
                    results, progress_data, 1000.0, "op_test"
                )

        calls = mock_log_info.call_args_list

        self.assertTrue(any("Completed processing 2 items" in c[0][0] for c in calls))

        mock_sensitive.assert_called_once_with(
            "Parallel Processing",
            2,
            10.0,
            completed=1,
            failed=1,
            operation_id="op_test",
        )


# Tests for process_pages_in_parallel method
class TestProcessPagesInParallel(unittest.IsolatedAsyncioTestCase):
    """Test high-level parallel page processing."""

    # successful page processing returns page data
    async def test_process_pages_in_parallel_success(self):
        async def dummy_process(page):
            return ({"page": page.get("page", 0), "data": "processed"}, [])

        pages = [{"page": 1}, {"page": 2}]

        result = await ParallelProcessingCore.process_pages_in_parallel(
            pages, dummy_process, max_workers=2
        )

        self.assertEqual(
            result,
            [
                (1, ({"page": 1, "data": "processed"}, [])),
                (2, ({"page": 2, "data": "processed"}, [])),
            ],
        )

    # failures in processing should be caught and warning logged
    async def test_process_pages_in_parallel_failure(self):
        async def dummy_process(page):
            raise Exception("fail")

        pages = [{"page": 1}]

        with patch(module_target("log_warning")) as mock_log_warning:
            result = await ParallelProcessingCore.process_pages_in_parallel(
                pages, dummy_process
            )

        self.assertEqual(result, [(1, ({"page": 1, "sensitive": []}, []))])

        mock_log_warning.assert_called_once()


# Tests for process_entities_in_parallel method
class TestProcessEntitiesInParallel(unittest.IsolatedAsyncioTestCase):
    """Test per-page entity detection parallel processing."""

    # no entities yields empty result and redaction
    async def test_process_entities_in_parallel_no_entities(self):
        detector = AsyncMock()

        result = await ParallelProcessingCore.process_entities_in_parallel(
            detector, "full text", [], [], page_number=1
        )

        self.assertEqual(result, ([], {"page": 1, "sensitive": []}))

    # detector failure logs error and returns empty
    async def test_process_entities_in_parallel_failure(self):
        async def dummy_detector(page, full_text, mapping, batch):
            raise Exception("fail")

        detector = MagicMock()

        detector.process_entities_for_page = AsyncMock(side_effect=dummy_detector)

        with patch(module_target("log_error")) as mock_log_error:
            result = await ParallelProcessingCore.process_entities_in_parallel(
                detector, "text", [], ["ent1"], page_number=1
            )

        processed_entities, redaction = result

        self.assertEqual(processed_entities, [])

        self.assertEqual(redaction, {"page": 1, "sensitive": []})

        mock_log_error.assert_called()


# Tests for process_in_parallel method
class TestProcessInParallel(unittest.IsolatedAsyncioTestCase):
    """Test end-to-end parallel processing orchestration."""

    # empty items list does nothing
    async def test_process_in_parallel_empty_items(self):
        mock_processor = AsyncMock()

        result = await ParallelProcessingCore.process_in_parallel(
            items=[], processor=mock_processor
        )

        self.assertEqual(result, [])

        mock_processor.assert_not_called()

    # successful end-to-end processing uses all steps
    async def test_process_in_parallel_success(self):
        async def dummy_processor(item):
            return f"processed_{item}"

        with patch.object(
            ParallelProcessingCore,
            "_validate_and_prepare_input",
            return_value=("test_op_id", 60.0, 10.0, 1000.0),
        ) as mock_validate, patch.object(
            ParallelProcessingCore, "_acquire_worker_count", return_value=4
        ) as mock_acquire_worker, patch.object(
            ParallelProcessingCore,
            "_init_progress_data",
            return_value={
                "completed": 0,
                "failed": 0,
                "total_items": 3,
                "start_time": 1000.0,
                "last_progress_log": 1000.0,
                "last_index": None,
            },
        ) as mock_init_progress, patch(
            module_target("AsyncTimeoutSemaphore"), return_value=DummyAsyncCM()
        ), patch.object(
            ParallelProcessingCore,
            "_gather_tasks_with_timeout",
            return_value=[
                (0, "processed_item1"),
                (1, "processed_item2"),
                (2, "processed_item3"),
            ],
        ):
            result = await ParallelProcessingCore.process_in_parallel(
                items=["item1", "item2", "item3"], processor=dummy_processor
            )

        self.assertEqual(
            result,
            [(0, "processed_item1"), (1, "processed_item2"), (2, "processed_item3")],
        )

        mock_validate.assert_called_once_with(
            ["item1", "item2", "item3"], None, None, None
        )

        mock_acquire_worker.assert_called_once_with(
            ["item1", "item2", "item3"], None, True
        )

        mock_init_progress.assert_called_once_with(1000.0, 3)
