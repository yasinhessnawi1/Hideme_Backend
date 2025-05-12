import asyncio
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

from backend.app.domain import EntityDetector
from backend.app.entity_detection.hybrid import HybridEntityDetector
from backend.app.utils.system_utils.synchronization_utils import (
    AsyncTimeoutLock,
    LockPriority,
)

import time


class TestHybridEntityDetector(unittest.IsolatedAsyncioTestCase):

    # Setup hybrid detector configuration
    def setUp(self):
        self.config = {
            "use_presidio": True,
            "use_gemini": True,
            "use_gliner": True,
            "use_hideme": True,
            "entities": ["email", "phone_number"],
        }

    # _get_detector_lock should create an AsyncTimeoutLock
    @patch("backend.app.entity_detection.hybrid.AsyncTimeoutLock")
    @patch("backend.app.entity_detection.hybrid.HybridEntityDetector.__init__")
    async def test_get_detector_lock(self, mock_init, mock_AsyncTimeoutLock):
        mock_init.return_value = None

        self.detector = HybridEntityDetector(self.config)

        mock_lock = AsyncMock(spec=AsyncTimeoutLock)

        mock_AsyncTimeoutLock.return_value = mock_lock

        self.detector._detector_lock = None

        lock = await self.detector._get_detector_lock()

        mock_AsyncTimeoutLock.assert_called_once_with(
            name="hybrid_detector_lock", priority=LockPriority.MEDIUM, timeout=30.0
        )

        self.assertEqual(lock, mock_lock)

    # _prepare_data_and_check_detectors returns False if no detectors
    @patch("backend.app.entity_detection.hybrid.HybridEntityDetector.__init__")
    async def test_prepare_data_and_check_detectors(self, mock_init):
        mock_init.return_value = None

        self.detector = HybridEntityDetector(self.config)

        self.detector.detectors = []

        result = self.detector._prepare_data_and_check_detectors()

        self.assertFalse(result)

        self.detector.detectors = [MagicMock()]

        result = self.detector._prepare_data_and_check_detectors()

        self.assertTrue(result)

    # _run_all_detectors_in_parallel should task each detector
    @patch("backend.app.entity_detection.hybrid.HybridEntityDetector.__init__")
    @patch(
        "backend.app.entity_detection.hybrid.HybridEntityDetector._process_single_detector"
    )
    @patch("backend.app.entity_detection.hybrid.asyncio.create_task")
    async def test_run_all_detectors_in_parallel(
        self, mock_create_task, mock_process_single_detector, mock_init
    ):
        mock_init.return_value = None

        self.detector = HybridEntityDetector(self.config)

        self.detector.detectors = [MagicMock(), MagicMock()]

        mock_process_single_detector.return_value = {
            "success": True,
            "entities": [],
            "mapping": {},
            "time": 1.0,
        }

        mock_task_1 = AsyncMock()

        mock_task_1.return_value = {
            "success": True,
            "entities": [],
            "mapping": {},
            "time": 1.0,
        }

        mock_task_2 = AsyncMock()

        mock_task_2.return_value = {
            "success": True,
            "entities": [],
            "mapping": {},
            "time": 1.0,
        }

        mock_create_task.side_effect = [mock_task_1(), mock_task_2()]

        results = await self.detector._run_all_detectors_in_parallel({}, [])

        mock_create_task.assert_called()

        self.assertEqual(len(results), 2)

    # _process_single_detector handles both async and sync detectors
    @patch("backend.app.entity_detection.hybrid.HybridEntityDetector.__init__")
    @patch(
        "backend.app.entity_detection.hybrid.HybridEntityDetector._run_async_detector"
    )
    @patch(
        "backend.app.entity_detection.hybrid.HybridEntityDetector._run_sync_detector"
    )
    async def test_process_single_detector(self, mock_sync, mock_async, mock_init):
        mock_init.return_value = None

        self.detector = HybridEntityDetector(self.config)

        mock_async.return_value = ([], {"pages": []})

        result = await self.detector._process_single_detector(MagicMock(), {}, [])

        self.assertTrue(result["success"])

        mock_sync.return_value = ([], {"pages": []})

        result = await self.detector._process_single_detector(MagicMock(), {}, [])

        self.assertTrue(result["success"])

        mock_async.side_effect = Exception("Detection failed")

        result = await self.detector._process_single_detector(MagicMock(), {}, [])

        self.assertFalse(result["success"])

    # detect_sensitive_data_async returns defaults on no results
    @patch("backend.app.entity_detection.hybrid.HybridEntityDetector.__init__")
    @patch(
        "backend.app.entity_detection.hybrid.HybridEntityDetector._run_all_detectors_in_parallel"
    )
    @patch(
        "backend.app.entity_detection.hybrid.HybridEntityDetector._process_detection_results"
    )
    async def test_detect_sensitive_data_async(
        self, mock_process_results, mock_run_all, mock_init
    ):
        mock_init.return_value = None

        self.detector = HybridEntityDetector(self.config)

        mock_run_all.return_value = [{"entities": [], "mapping": {}}]

        mock_process_results.return_value = ([], [], 1, 0)

        final_entities, final_mapping = await self.detector.detect_sensitive_data_async(
            {}, []
        )

        self.assertEqual(final_entities, [])

        self.assertEqual(final_mapping, {"pages": []})

        mock_run_all.return_value = []

        final_entities, final_mapping = await self.detector.detect_sensitive_data_async(
            {}, []
        )

        self.assertEqual(final_entities, [])

        self.assertEqual(final_mapping, {"pages": []})

    # detect_sensitive_data wraps async and handles timeout
    @patch("backend.app.entity_detection.hybrid.HybridEntityDetector.__init__")
    @patch(
        "backend.app.entity_detection.hybrid.HybridEntityDetector.detect_sensitive_data_async"
    )
    @patch("backend.app.entity_detection.hybrid.time.time")
    async def test_detect_sensitive_data(self, mock_time, mock_async, mock_init):
        mock_init.return_value = None

        self.detector = HybridEntityDetector(self.config)

        mock_async.return_value = ([], {"pages": []})

        mock_time.return_value = 1609459200

        result = self.detector.detect_sensitive_data({}, [])

        self.assertEqual(result[0], [])

        self.assertEqual(result[1], {"pages": []})

        mock_async.side_effect = asyncio.TimeoutError

        result = self.detector.detect_sensitive_data({}, [])

        self.assertEqual(result[0], [])

        self.assertEqual(result[1], {"pages": []})

    # Full async flow success logs and returns entities
    @patch("backend.app.entity_detection.hybrid.HybridEntityDetector.__init__")
    @patch(
        "backend.app.entity_detection.hybrid.HybridEntityDetector._prepare_data_and_check_detectors"
    )
    @patch(
        "backend.app.entity_detection.hybrid.HybridEntityDetector._increment_usage_metrics"
    )
    @patch(
        "backend.app.entity_detection.hybrid.HybridEntityDetector._run_all_detectors_in_parallel"
    )
    @patch(
        "backend.app.entity_detection.hybrid.HybridEntityDetector._process_detection_results"
    )
    @patch(
        "backend.app.entity_detection.hybrid.HybridEntityDetector._finalize_detection"
    )
    @patch("backend.app.entity_detection.hybrid.log_error")
    @patch("backend.app.entity_detection.hybrid.log_info")
    async def test_detect_sensitive_data_async_success(
        self,
        mock_info,
        mock_error,
        mock_finalize,
        mock_process_results,
        mock_run_all,
        mock_increment,
        mock_prepare,
        mock_init,
    ):
        mock_init.return_value = None

        self.detector = HybridEntityDetector(self.config)

        mock_prepare.return_value = True

        mock_increment.return_value = None

        mock_run_all.return_value = [
            {
                "success": True,
                "entities": [{"entity_type": "email"}],
                "mapping": {"pages": []},
            }
        ]

        mock_process_results.return_value = (
            [{"entity_type": "email"}],
            [{"pages": []}],
            1,
            0,
        )

        mock_finalize.return_value = ([{"entity_type": "email"}], {"pages": []})

        final_entities, final_mapping = await self.detector.detect_sensitive_data_async(
            {}, []
        )

        self.assertEqual(len(final_entities), 1)

        self.assertEqual(final_entities[0]["entity_type"], "email")

        self.assertEqual(final_mapping, {"pages": []})

    # Async detection exception logs and returns defaults
    @patch("backend.app.entity_detection.hybrid.HybridEntityDetector.__init__")
    @patch(
        "backend.app.entity_detection.hybrid.HybridEntityDetector._prepare_data_and_check_detectors"
    )
    @patch(
        "backend.app.entity_detection.hybrid.HybridEntityDetector._increment_usage_metrics"
    )
    @patch(
        "backend.app.entity_detection.hybrid.HybridEntityDetector._run_all_detectors_in_parallel"
    )
    @patch(
        "backend.app.entity_detection.hybrid.HybridEntityDetector._process_detection_results"
    )
    @patch(
        "backend.app.entity_detection.hybrid.HybridEntityDetector._finalize_detection"
    )
    @patch("backend.app.entity_detection.hybrid.log_error")
    async def test_detect_sensitive_data_async_exception(
        self,
        mock_error,
        mock_finalize,
        mock_process_results,
        mock_run_all,
        mock_increment,
        mock_prepare,
        mock_init,
    ):
        mock_init.return_value = None

        self.detector = HybridEntityDetector(self.config)

        mock_prepare.return_value = True

        mock_increment.return_value = None

        mock_run_all.side_effect = Exception("Unexpected error")

        final_entities, final_mapping = await self.detector.detect_sensitive_data_async(
            {}, []
        )

        self.assertEqual(final_entities, [])

        self.assertEqual(final_mapping, {"pages": []})

        mock_error.assert_called_with(
            "[ERROR] Unexpected error in hybrid detection: Unexpected error"
        )

    # _process_detection_results aggregates successes and failures
    @patch("backend.app.entity_detection.hybrid.log_sensitive_operation")
    def test_process_detection_results_success(self, mock_log):
        parallel_results = [
            {
                "success": True,
                "engine": "Presidio",
                "entities": [{"entity_type": "email"}],
                "mapping": {"pages": []},
                "time": 1.0,
            },
            {
                "success": True,
                "engine": "Gemini",
                "entities": [{"entity_type": "phone_number"}],
                "mapping": {"pages": []},
                "time": 1.2,
            },
        ]

        all_entities, all_mappings, success_count, failure_count = (
            HybridEntityDetector._process_detection_results(parallel_results)
        )

        self.assertEqual(len(all_entities), 2)

        self.assertEqual(len(all_mappings), 2)

        self.assertEqual(success_count, 2)

        self.assertEqual(failure_count, 0)

        mock_log.assert_called()

    # _process_detection_results counts failures properly
    @patch("backend.app.entity_detection.hybrid.log_sensitive_operation")
    def test_process_detection_results_failure(self, mock_log):
        parallel_results = [
            {
                "success": True,
                "engine": "Presidio",
                "entities": [{"entity_type": "email"}],
                "mapping": {"pages": []},
                "time": 1.0,
            },
            {
                "success": False,
                "engine": "Gemini",
                "entities": [],
                "mapping": {},
                "time": 1.2,
            },
            {
                "success": True,
                "engine": "GLiNER",
                "entities": [{"entity_type": "address"}],
                "mapping": {"pages": []},
                "time": 1.5,
            },
        ]

        all_entities, all_mappings, success_count, failure_count = (
            HybridEntityDetector._process_detection_results(parallel_results)
        )

        self.assertEqual(len(all_entities), 2)

        self.assertEqual(len(all_mappings), 2)

        self.assertEqual(success_count, 2)

        self.assertEqual(failure_count, 1)

        mock_log.assert_called()

    # _process_detection_results handles empty input without logging
    @patch("backend.app.entity_detection.hybrid.log_sensitive_operation")
    def test_process_detection_results_empty(self, mock_log):
        parallel_results = []

        all_entities, all_mappings, success_count, failure_count = (
            HybridEntityDetector._process_detection_results(parallel_results)
        )

        self.assertEqual(len(all_entities), 0)

        self.assertEqual(len(all_mappings), 0)

        self.assertEqual(success_count, 0)

        self.assertEqual(failure_count, 0)

        mock_log.assert_not_called()

    # _finalize_detection computes performance and logs summary
    @patch(
        "backend.app.entity_detection.hybrid.initialization_service.get_presidio_detector"
    )
    @patch(
        "backend.app.entity_detection.hybrid.initialization_service.get_gemini_detector"
    )
    @patch(
        "backend.app.entity_detection.hybrid.initialization_service.get_gliner_detector"
    )
    @patch(
        "backend.app.entity_detection.hybrid.initialization_service.get_hideme_detector"
    )
    @patch(
        "backend.app.entity_detection.hybrid.HybridEntityDetector._get_detector_lock"
    )
    @patch("backend.app.entity_detection.hybrid.log_info")
    @patch("backend.app.entity_detection.hybrid.time.time")
    async def test_finalize_detection_success(
        self,
        mock_time,
        mock_log_info,
        mock_lock,
        mock_hideme,
        mock_gliner,
        mock_gemini,
        mock_presidio,
    ):
        mock_time.return_value = 1609459200

        mock_presidio.return_value = MagicMock(spec=EntityDetector)

        mock_gemini.return_value = MagicMock(spec=EntityDetector)

        mock_gliner.return_value = MagicMock(spec=EntityDetector)

        mock_hideme.return_value = MagicMock(spec=EntityDetector)

        self.detector = HybridEntityDetector(self.config)

        mock_lock.return_value = AsyncMock(spec=AsyncTimeoutLock)

        combined_entities = [{"entity_type": "email"}]

        all_redactions = [{"pages": [{"page": 1, "sensitive": []}]}]

        final_entities, _ = await self.detector._finalize_detection(
            combined_entities, all_redactions, {}, [], time.time(), 1, 0
        )

        self.assertEqual(len(final_entities), 1)

        mock_log_info.assert_called_with(
            "[PERF] Total 1 entities detected across 0 pages"
        )

    # _finalize_detection handles absence of detectors gracefully
    @patch("backend.app.entity_detection.hybrid.HybridEntityDetector.__init__")
    @patch(
        "backend.app.entity_detection.hybrid.HybridEntityDetector._get_detector_lock"
    )
    async def test_finalize_detection_failure(self, mock_lock, mock_init):
        mock_init.return_value = None

        self.detector = HybridEntityDetector(self.config)

        self.detector.detectors = []

        self.detector.config = self.config

        self.detector._total_entities_detected = 0

        mock_lock.return_value = AsyncMock(spec=AsyncTimeoutLock)

        combined_entities = []

        all_redactions = []

        final_entities, final_mapping = await self.detector._finalize_detection(
            combined_entities, all_redactions, {}, [], time.time(), 0, 0
        )

        self.assertEqual(final_entities, [])

        self.assertEqual(final_mapping, {"pages": []})

    # get_status logs runtime error if lock fails
    @patch("backend.app.entity_detection.hybrid.HybridEntityDetector.__init__")
    @patch(
        "backend.app.entity_detection.hybrid.HybridEntityDetector._get_detector_lock"
    )
    @patch("backend.app.entity_detection.hybrid.log_warning")
    async def test_get_status_runtime_error(self, mock_warn, mock_lock, mock_init):
        mock_init.return_value = None

        self.detector = HybridEntityDetector(self.config)

        self.detector.detectors = [MagicMock(), MagicMock()]

        lock = MagicMock()

        lock.acquire_timeout.return_value.__aenter__.side_effect = RuntimeError(
            "Event loop error"
        )

        mock_lock.return_value = lock

        self.detector._initialization_time = 1234567890

        status = await self.detector.get_status()

        self.assertTrue(status["initialized"])

        self.assertIn("runtime_error", status)

        self.assertEqual(status["initialization_time"], 1234567890)

        self.assertEqual(status["detector_count"], 2)

    # detect_sensitive_data integrates minimization and async call
    @patch("backend.app.entity_detection.hybrid.HybridEntityDetector.__init__")
    @patch(
        "backend.app.entity_detection.hybrid.HybridEntityDetector.detect_sensitive_data_async"
    )
    @patch("backend.app.entity_detection.hybrid.minimize_extracted_data")
    async def test_detect_sensitive_data_success(self, mock_min, mock_async, mock_init):
        mock_init.return_value = None

        self.detector = HybridEntityDetector(self.config)

        mock_min.return_value = {"processed_data": "some_data"}

        mock_async.return_value = ([], {"pages": []})

        extracted_data = {"text": "This is a test"}

        result = self.detector.detect_sensitive_data(extracted_data)

        self.assertEqual(result[0], [])

        self.assertEqual(result[1], {"pages": []})

    # detect_sensitive_data handles runtime error from async
    @patch("backend.app.entity_detection.hybrid.HybridEntityDetector.__init__")
    @patch(
        "backend.app.entity_detection.hybrid.HybridEntityDetector.detect_sensitive_data_async"
    )
    @patch("backend.app.entity_detection.hybrid.minimize_extracted_data")
    @patch(
        "backend.app.entity_detection.hybrid.SecurityAwareErrorHandler.log_processing_error"
    )
    async def test_detect_sensitive_data_runtime_error(
        self, mock_log, mock_min, mock_async, mock_init
    ):
        mock_init.return_value = None

        self.detector = HybridEntityDetector(self.config)

        mock_min.return_value = {"processed_data": "some_data"}

        mock_async.side_effect = RuntimeError("Runtime error during detection")

        extracted_data = {"text": "This is a test"}

        result = self.detector.detect_sensitive_data(extracted_data)

        self.assertEqual(result, ([], {"pages": []}))

        mock_log.assert_called()

    # detect_sensitive_data handles generic exceptions
    @patch("backend.app.entity_detection.hybrid.HybridEntityDetector.__init__")
    @patch(
        "backend.app.entity_detection.hybrid.HybridEntityDetector.detect_sensitive_data_async"
    )
    @patch("backend.app.entity_detection.hybrid.minimize_extracted_data")
    @patch(
        "backend.app.entity_detection.hybrid.SecurityAwareErrorHandler.log_processing_error"
    )
    async def test_detect_sensitive_data_generic_error(
        self, mock_log, mock_min, mock_async, mock_init
    ):
        mock_init.return_value = None

        self.detector = HybridEntityDetector(self.config)

        mock_min.return_value = {"processed_data": "some_data"}

        mock_async.side_effect = Exception("Generic error during detection")

        extracted_data = {"text": "This is a test"}

        result = self.detector.detect_sensitive_data(extracted_data)

        self.assertEqual(result, ([], {"pages": []}))

        mock_log.assert_called()
