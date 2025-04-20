import asyncio

import unittest

from unittest import mock

from unittest.mock import patch, MagicMock

from backend.app.entity_detection.base import BaseEntityDetector

from backend.app.utils.security.processing_records import record_keeper

from backend.app.utils.system_utils.synchronization_utils import TimeoutLock


class DummyDetector(BaseEntityDetector):

    # Dummy async detector implementation
    async def detect_sensitive_data_async(self, extracted_data, requested_entities=None):
        return [{"entity_type": "EMAIL", "start": 0, "end": 5, "score": 0.95}], {"pages": [{"sensitive": []}]}


class TestBaseEntityDetector(unittest.TestCase):

    # Setup a dummy detector instance
    def setUp(self):
        self.detector = DummyDetector()

    # Lazy initialization returns a TimeoutLock
    def test_lock_lazy_initialization(self):
        self.detector._lock = None

        lock = self.detector._get_access_lock()

        self.assertIsInstance(lock, TimeoutLock)

    # get_status returns a dict containing total_calls
    def test_get_status_success(self):
        status = self.detector.get_status()

        self.assertTrue("total_calls" in status)

    # filter_by_score filters list of dicts correctly
    def test_filter_by_score_list(self):
        data = [{"score": 0.9}, {"score": 0.5}]

        filtered = BaseEntityDetector.filter_by_score(data, 0.85)

        self.assertEqual(len(filtered), 1)

    # filter_by_score filters nested dict structure correctly
    def test_filter_by_score_dict(self):
        data = {"pages": [{"sensitive": [{"score": 0.9}, {"score": 0.5}]}]}

        filtered = BaseEntityDetector.filter_by_score(data, 0.85)

        self.assertEqual(len(filtered["pages"][0]["sensitive"]), 1)

    # filter_by_score raises ValueError on invalid input
    def test_filter_by_score_invalid(self):
        with self.assertRaises(ValueError):
            BaseEntityDetector.filter_by_score("not_valid")

    # _convert_to_entity_dict handles dict input
    def test_convert_to_entity_dict_dict_input(self):
        entity = {"entity_type": "EMAIL", "start": 0, "end": 5, "score": 0.99}

        result = BaseEntityDetector._convert_to_entity_dict(entity)

        self.assertEqual(result["entity_type"], "EMAIL")

    # _convert_to_entity_dict handles object input
    def test_convert_to_entity_dict_object_input(self):
        class DummyEntity:
            entity_type = "PERSON"

            start = 1

            end = 4

            score = 0.8

        result = BaseEntityDetector._convert_to_entity_dict(DummyEntity())

        self.assertEqual(result["entity_type"], "PERSON")

    # _get_entity_text returns original_text when present
    def test_get_entity_text_original_text(self):
        entity = {"original_text": "test"}

        self.assertEqual(self.detector._get_entity_text(entity, "text"), "test")

    # _get_entity_text extracts substring by offsets
    def test_get_entity_text_by_offset(self):
        entity = {"start": 0, "end": 4}

        self.assertEqual(self.detector._get_entity_text(entity, "text more"), "text")

    # _get_entity_text returns None on invalid offsets
    def test_get_entity_text_invalid_offset(self):
        entity = {"start": "a", "end": "b"}

        self.assertIsNone(self.detector._get_entity_text(entity, "text"))

    # detect_sensitive_data returns tuple of list and dict
    def test_detect_sensitive_data_success(self):
        extracted = {"text": "hello email@example.com"}

        result = self.detector.detect_sensitive_data(extracted)

        self.assertIsInstance(result, tuple)

        self.assertIsInstance(result[0], list)

    # detect_sensitive_data falls back on async failure
    def test_detect_sensitive_data_async_failure(self):
        class BrokenDetector(BaseEntityDetector):

            async def detect_sensitive_data_async(self, data, requested_entities=None):
                raise Exception("Boom")

        broken = BrokenDetector()

        result = broken.detect_sensitive_data({"text": "data"})

        self.assertEqual(result, ([], {"pages": []}))

    # _update_entity_metrics releases lock on success
    @patch.object(BaseEntityDetector, '_get_access_lock')
    def test_update_entity_metrics_success(self, mock_lock):
        lock = MagicMock()

        lock.acquire.return_value = True

        mock_lock.return_value = lock

        self.detector._update_entity_metrics([{"entity_type": "EMAIL"}], 1.23)

        lock.release.assert_called_once()

    # _update_entity_metrics logs warning when lock not acquired
    @patch.object(BaseEntityDetector, '_get_access_lock')
    @patch("backend.app.entity_detection.base.log_warning")
    def test_update_entity_metrics_fail_to_acquire_lock(self, mock_log, mock_lock):
        lock = MagicMock()

        lock.acquire.return_value = False

        mock_lock.return_value = lock

        self.detector._update_entity_metrics([], 0.0)

        mock_log.assert_called_once_with("Failed to acquire lock for updating entity statistics")

    # _record_entity_processing invokes record_keeper
    @patch.object(record_keeper, "record_processing")
    def test_record_entity_processing(self, mock_record):
        BaseEntityDetector._record_entity_processing([{"entity_type": "EMAIL"}], 0.5)

        mock_record.assert_called_once()

    # get_status logs flag when lock acquisition fails
    def test_get_status_lock_fail(self):
        self.detector._lock = MagicMock()

        self.detector._lock.acquire.return_value = False

        result = self.detector.get_status()

        self.assertTrue("lock_acquisition_failed" in result)

    # update_usage_metrics increments counters when lock acquired
    @patch.object(BaseEntityDetector, '_get_access_lock')
    def test_update_usage_metrics_success(self, mock_lock):
        lock = MagicMock()

        lock.acquire.return_value = True

        mock_lock.return_value = lock

        self.detector.update_usage_metrics(3, 1.5)

        self.assertEqual(self.detector._total_calls, 1)

        self.assertEqual(self.detector._total_entities_detected, 3)

    # update_usage_metrics logs warning when lock not acquired
    @patch.object(BaseEntityDetector, '_get_access_lock')
    @patch("backend.app.entity_detection.base.log_warning")
    def test_update_usage_metrics_lock_fail(self, mock_log, mock_lock):
        lock = MagicMock()

        lock.acquire.return_value = False

        mock_lock.return_value = lock

        self.detector.update_usage_metrics(1, 0.1)

        mock_log.assert_called_once_with("Failed to acquire lock for updating entity metrics")

    # process_entities_for_page returns correct structure on success
    @patch.object(DummyDetector, '_standardize_raw_entities',
                  return_value=[{"entity_type": "EMAIL", "start": 0, "end": 5, "score": 0.95}])
    @patch.object(DummyDetector, '_process_sanitized_entities',
                  return_value=(
                          [{"entity_type": "EMAIL", "start": 0, "end": 5, "score": 0.95}], [{"entity_type": "EMAIL"}]))
    @patch.object(DummyDetector, '_update_entity_metrics')
    @patch.object(DummyDetector, '_record_entity_processing')
    def test_process_entities_for_page_success(self, mock_record, mock_update, mock_process, mock_standardize):
        result = asyncio.run(self.detector.process_entities_for_page(

            page_number=1,

            full_text="hello@example.com",

            mapping=[({}, 0, 5)],

            entities=[{"dummy": "data"}]

        ))

        self.assertEqual(result[0][0]["entity_type"], "EMAIL")

        self.assertEqual(result[1]["page"], 1)

        self.assertTrue("sensitive" in result[1])

    # process_entities handles standardization failure gracefully
    @patch("backend.app.utils.system_utils.error_handling.SecurityAwareErrorHandler.log_processing_error")
    @patch.object(DummyDetector, '_standardize_raw_entities', side_effect=Exception("Standardization Error"))
    @patch.object(DummyDetector, '_process_sanitized_entities', return_value=([], []))
    def test_process_entities_standardize_failure(self, mock_process, mock_standardize, mock_error_log):
        result = asyncio.run(self.detector.process_entities_for_page(

            1, "text", [], ["bad_entity"]

        ))

        self.assertEqual(result[0], [])

        self.assertEqual(result[1]["sensitive"], [])

        mock_error_log.assert_any_call(mock.ANY, "standardize_entities")

    # process_entities handles sanitized processing failure gracefully
    @patch("backend.app.utils.system_utils.error_handling.SecurityAwareErrorHandler.log_processing_error")
    @patch.object(DummyDetector, '_standardize_raw_entities', return_value=[])
    @patch.object(DummyDetector, '_process_sanitized_entities', side_effect=Exception("Sanitized Error"))
    def test_process_entities_sanitized_processing_failure(self, mock_process, mock_standardize, mock_error_log):
        result = asyncio.run(self.detector.process_entities_for_page(

            1, "text", [], ["entity"]

        ))

        self.assertEqual(result[0], [])

        self.assertEqual(result[1]["sensitive"], [])

        mock_error_log.assert_any_call(mock.ANY, "process_sanitized_entities")

    # process_entities logs error on metrics update failure
    @patch("backend.app.utils.system_utils.error_handling.SecurityAwareErrorHandler.log_processing_error")
    @patch.object(DummyDetector, '_standardize_raw_entities', return_value=[])
    @patch.object(DummyDetector, '_process_sanitized_entities', return_value=([], []))
    @patch.object(DummyDetector, '_update_entity_metrics', side_effect=Exception("Update Error"))
    def test_process_entities_metric_update_failure(self, mock_update, mock_process, mock_standardize, mock_error_log):
        result = asyncio.run(self.detector.process_entities_for_page(

            1, "text", [], []

        ))

        self.assertEqual(result[0], [])

        self.assertEqual(result[1]["sensitive"], [])

        mock_error_log.assert_any_call(mock.ANY, "update_metrics")

    # _standardize_raw_entities covers all error and skip paths
    @patch("backend.app.entity_detection.base.logger")
    @patch("backend.app.entity_detection.base.log_warning")
    def test_standardize_raw_entities_all_paths(self, mock_warning, mock_logger):
        valid_entity = {"entity_type": "EMAIL", "start": 0, "end": 5, "score": 0.9, "original_text": "hello"}

        result = self.detector._standardize_raw_entities([valid_entity], "hello world")

        self.assertEqual(len(result), 1)

        with patch.object(DummyDetector, "_convert_to_entity_dict", return_value=None):
            result = self.detector._standardize_raw_entities(["broken"], "text")

            self.assertEqual(result, [])

            mock_warning.assert_any_call("[WARNING] _convert_to_entity_dict returned None. Skipping entity.")

        no_text_entity = {"entity_type": "EMAIL", "start": 1000, "end": 1005, "score": 0.9}

        result = self.detector._standardize_raw_entities([no_text_entity], "short text")

        self.assertEqual(result, [])

        mock_warning.assert_any_call("[WARNING] Could not determine entity text, skipping entity.")

        with patch.object(DummyDetector, "_convert_to_entity_dict", side_effect=Exception("boom")):
            with patch(
                    "backend.app.utils.system_utils.error_handling.SecurityAwareErrorHandler.log_processing_error") as mock_log:
                result = self.detector._standardize_raw_entities(["err"], "text")

                self.assertEqual(result, [])

                mock_log.assert_any_call(mock.ANY, "entity_processing")

    # _process_sanitized_entities handles positive path correctly
    @patch("backend.app.entity_detection.base.TextUtils")
    def test_process_sanitized_entities_positive(self, mock_text_utils):
        mock_text_utils.recompute_offsets.return_value = [(0, 5)]

        mock_text_utils.map_offsets_to_bboxes.return_value = ["bbox1", "bbox2"]

        mock_text_utils.merge_bounding_boxes.return_value = {"composite": "merged_box"}

        entity = {"entity_type": "EMAIL", "start": 0, "end": 5, "score": 0.9, "original_text": "hello"}

        sanitized = [entity]

        processed, sensitive = self.detector._process_sanitized_entities(sanitized, "hello world", [("dummy", 0, 5)])

        self.assertEqual(len(processed), 1)

        self.assertEqual(len(sensitive), 1)

        self.assertEqual(sensitive[0]["bbox"], "merged_box")

    # _process_sanitized_entities logs and skips on exception
    @patch("backend.app.utils.system_utils.error_handling.SecurityAwareErrorHandler.log_processing_error")
    @patch("backend.app.entity_detection.base.TextUtils", autospec=True)
    def test_process_sanitized_entities_exception(self, mock_text_utils, mock_log):
        mock_text_utils.recompute_offsets.side_effect = Exception("offset fail")

        entity = {"entity_type": "EMAIL", "start": 0, "end": 5, "score": 0.9, "original_text": "hello"}

        sanitized = [entity]

        with patch.object(self.detector, "_process_single_entity", side_effect=Exception("boom")):
            processed, sensitive = self.detector._process_sanitized_entities(sanitized, "hello world",
                                                                             [("dummy", 0, 5)])

        self.assertEqual(processed, [])

        self.assertEqual(sensitive, [])

        mock_log.assert_any_call(mock.ANY, "entity_processing")

    # _process_single_entity returns processed and sensitive entities correctly
    @patch("backend.app.entity_detection.base.TextUtils")
    def test_process_single_entity_success(self, mock_text_utils):
        mock_text_utils.recompute_offsets.return_value = [(0, 5)]

        mock_text_utils.map_offsets_to_bboxes.return_value = [{"x": 0, "y": 0, "w": 5, "h": 5}]

        mock_text_utils.merge_bounding_boxes.return_value = {"composite": {"x": 0, "y": 0, "w": 5, "h": 5}}

        entity = {"entity_type": "EMAIL", "start": 0, "end": 5, "score": 0.9, "original_text": "hello"}

        processed, sensitive = self.detector._process_single_entity(entity, "hello world", [("dummy", 0, 5)])

        self.assertEqual(len(processed), 1)

        self.assertEqual(len(sensitive), 1)

        self.assertEqual(sensitive[0]["bbox"], {"x": 0, "y": 0, "w": 5, "h": 5})

    # _process_single_entity logs and skips on offset exception
    @patch("backend.app.utils.system_utils.error_handling.SecurityAwareErrorHandler.log_processing_error")
    @patch("backend.app.entity_detection.base.TextUtils.recompute_offsets", side_effect=Exception("fail"))
    def test_process_single_entity_offset_exception(self, mock_recompute, mock_log):
        entity = {"entity_type": "EMAIL", "start": 0, "end": 5, "score": 0.9, "original_text": "hello"}

        processed, sensitive = self.detector._process_single_entity(entity, "hello world", [("dummy", 0, 5)])

        self.assertEqual(processed, [])

        self.assertEqual(sensitive, [])

        mock_log.assert_called_once()

    # _process_single_entity warns when no text available
    @patch("backend.app.entity_detection.base.log_warning")
    def test_process_single_entity_no_text(self, mock_warn):
        entity = {"entity_type": "EMAIL", "start": 0, "end": 5, "score": 0.9}

        processed, sensitive = self.detector._process_single_entity(entity, "", [])

        self.assertEqual(processed, [])

        self.assertEqual(sensitive, [])

        mock_warn.assert_any_call("[WARNING] Could not determine entity text after sanitization. Skipping entity.")
