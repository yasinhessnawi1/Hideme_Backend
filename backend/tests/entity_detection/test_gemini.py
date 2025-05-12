import time
import unittest
from unittest.mock import patch, AsyncMock, MagicMock

from backend.app.entity_detection.gemini import GeminiEntityDetector


class TestGeminiEntityDetector(unittest.IsolatedAsyncioTestCase):

    # Setup Gemini detector instance
    def setUp(self):
        self.detector = GeminiEntityDetector()

    # _get_api_lock creates a new AsyncTimeoutLock
    @patch(
        "backend.app.utils.system_utils.error_handling.SecurityAwareErrorHandler.log_processing_error"
    )
    async def test_get_api_lock_creates_new(self, mock_log):
        lock = await self.detector._get_api_lock()

        self.assertIsNotNone(lock)

        self.assertEqual(lock.name, "gemini_api_lock")

    # _get_api_lock logs error on exception
    @patch(
        "backend.app.utils.system_utils.error_handling.SecurityAwareErrorHandler.log_processing_error"
    )
    async def test_get_api_lock_handles_exception(self, mock_log):
        with patch(
            "backend.app.entity_detection.gemini.AsyncTimeoutLock",
            side_effect=Exception("fail"),
        ):
            self.detector._api_lock = None

            await self.detector._get_api_lock()

            mock_log.assert_called_once()

    # detect_sensitive_data_async returns empty on no requested_entities
    @patch(
        "backend.app.utils.security.processing_records.record_keeper.record_processing"
    )
    @patch("backend.app.entity_detection.gemini.log_warning")
    async def test_detect_sensitive_data_async_no_requested_entities(
        self, log_warn, record
    ):
        result = await self.detector.detect_sensitive_data_async({"pages": []}, None)

        self.assertEqual(result, ([], {"pages": []}))

        log_warn.assert_called_once()

        record.assert_called_once()

    # validation failure returns empty result
    @patch(
        "backend.app.utils.security.processing_records.record_keeper.record_processing"
    )
    @patch("backend.app.entity_detection.gemini.log_warning")
    @patch(
        "backend.app.utils.helpers.json_helper.validate_gemini_requested_entities",
        side_effect=Exception("bad"),
    )
    async def test_detect_sensitive_data_async_validation_fails(
        self, validate, log_war, record
    ):
        result = await self.detector.detect_sensitive_data_async(
            {"pages": []}, ["EMAIL"]
        )

        self.assertEqual(result, ([], {"pages": []}))

        log_war.assert_called_once()

        record.assert_called_once()

    # empty after validation returns empty result
    @patch("backend.app.entity_detection.gemini.log_warning")
    @patch(
        "backend.app.utils.security.processing_records.record_keeper.record_processing"
    )
    @patch(
        "backend.app.utils.helpers.json_helper.validate_gemini_requested_entities",
        return_value=[],
    )
    async def test_detect_sensitive_data_async_empty_after_validation(
        self, validate, record, warn
    ):
        result = await self.detector.detect_sensitive_data_async(
            {"pages": []}, ["EMAIL"]
        )

        self.assertEqual(result, ([], {"pages": []}))

        warn.assert_called_once()

        record.assert_called_once()

    # successful detection returns entities via parallel processing
    @patch(
        "backend.app.entity_detection.gemini.GeminiEntityDetector._finalize_detection_results"
    )
    @patch(
        "backend.app.entity_detection.gemini.GeminiEntityDetector._process_all_pages_in_parallel",
        new_callable=AsyncMock,
    )
    @patch(
        "backend.app.entity_detection.gemini.GeminiEntityDetector._prepare_pages_and_mappings"
    )
    @patch(
        "backend.app.utils.helpers.json_helper.validate_gemini_requested_entities",
        return_value=["EMAIL-G"],
    )
    async def test_detect_sensitive_data_async_success(
        self, mock_validate, mock_prepare, mock_process, mock_finalize
    ):
        mock_prepare.return_value = (
            [{"page": 1, "words": [{"text": "hello", "start": 0, "end": 5}]}],
            {1: ("hello", [({"text": "hello"}, 0, 5)])},
            {"pages": []},
        )

        mock_process.return_value = [{"entity_type": "EMAIL-G"}]

        mock_finalize.return_value = (
            [{"entity_type": "EMAIL-G"}],
            {"pages": [{"page": 1, "sensitive": []}]},
        )

        result = await self.detector.detect_sensitive_data_async(
            {
                "pages": [
                    {"page": 1, "words": [{"text": "hello", "start": 0, "end": 5}]}
                ]
            },
            ["EMAIL-G"],
        )

        self.assertIsInstance(result[0], list)

        self.assertGreater(len(result[0]), 0)

        self.assertEqual(result[0][0]["entity_type"], "EMAIL-G")

    # exception in validation returns empty result
    @patch("backend.app.entity_detection.gemini.log_warning")
    @patch(
        "backend.app.utils.security.processing_records.record_keeper.record_processing"
    )
    @patch(
        "backend.app.utils.helpers.json_helper.validate_gemini_requested_entities",
        side_effect=Exception("Forced validation failure"),
    )
    async def test_detect_sensitive_data_async_exception(
        self, mock_validate, mock_record, mock_log_warning
    ):
        result = await self.detector.detect_sensitive_data_async(
            {"pages": [{"page": 1, "words": [{"text": "test", "start": 0, "end": 4}]}]},
            ["EMAIL"],
        )

        self.assertEqual(result, ([], {"pages": []}))

        self.assertEqual(mock_log_warning.call_count, 1)

        self.assertEqual(mock_record.call_count, 1)

    # _prepare_pages_and_mappings handles valid and empty pages
    def test_prepare_pages_and_mappings_handles_empty_and_valid(self):
        data = {
            "pages": [
                {"page": 1, "words": [{"text": "hello", "start": 0, "end": 5}]},
                {"page": 2, "words": []},
            ]
        }

        with patch(
            "backend.app.utils.helpers.text_utils.TextUtils.reconstruct_text_and_mapping",
            return_value=("hello", []),
        ):
            pages, mapping, redactions = self.detector._prepare_pages_and_mappings(data)

            self.assertEqual(len(pages), 2)

            self.assertIn(1, mapping)

            self.assertEqual(redactions["pages"][0]["page"], 2)

    # error in _prepare_pages_and_mappings yields no redactions
    @patch(
        "backend.app.utils.helpers.text_utils.TextUtils.reconstruct_text_and_mapping",
        side_effect=Exception("fail"),
    )
    @patch(
        "backend.app.utils.system_utils.error_handling.SecurityAwareErrorHandler.log_processing_error"
    )
    def test_prepare_pages_and_mappings_error_path(self, log, recon):
        data = {"pages": [{"page": 1, "words": [{"text": "bad"}]}]}

        _, _, redactions = self.detector._prepare_pages_and_mappings(data)

        self.assertEqual(redactions["pages"], [])

    # parallel page processing returns results and updates redaction
    @patch(
        "backend.app.entity_detection.gemini.ParallelProcessingCore.process_pages_in_parallel",
        new_callable=AsyncMock,
    )
    async def test_process_all_pages_in_parallel_success(self, mock_core):
        mock_core.return_value = [
            (1, ({"page": 1, "sensitive": []}, [{"entity_type": "EMAIL"}]))
        ]

        redaction = {"pages": []}

        results = await self.detector._process_all_pages_in_parallel(
            [{"page": 1}], {1: ("text", [])}, ["EMAIL"], redaction
        )

        self.assertEqual(len(results), 1)

        self.assertEqual(redaction["pages"][0]["page"], 1)

    # _finalize_detection_results logs usage metrics
    def test_finalize_detection_results_logs_metrics(self):
        with patch("backend.app.entity_detection.gemini.log_info") as log:
            with patch(
                "backend.app.utils.security.processing_records.record_keeper.record_processing"
            ):
                with patch(
                    "backend.app.entity_detection.gemini.gemini_usage_manager.get_usage_summary",
                    return_value="summary",
                ):
                    result = self.detector._finalize_detection_results(
                        pages=[{"page": 1}],
                        combined_entities=[{"entity_type": "EMAIL"}],
                        redaction_mapping={"pages": [{"page": 1}]},
                        requested_entities=["EMAIL"],
                        operation_type="op",
                        document_type="doc",
                        start_time=time.time() - 0.5,
                    )

                    self.assertEqual(result[1]["pages"][0]["page"], 1)

                    log.assert_called()

    # extract entities from response returns list
    def test_extract_entities_from_response_success(self):
        response = {
            "pages": [
                {
                    "text": [
                        {"entities": [{"start": 0, "end": 5, "entity_type": "EMAIL"}]}
                    ]
                }
            ]
        }

        results = self.detector._extract_entities_from_response(response, "hello world")

        self.assertEqual(len(results), 1)

    # exception in extraction logs error and returns empty
    @patch(
        "backend.app.utils.system_utils.error_handling.SecurityAwareErrorHandler.log_processing_error"
    )
    def test_extract_entities_from_response_exception(self, mock_log):
        with patch.object(
            self.detector, "_gather_raw_entities", side_effect=Exception("fail")
        ):
            results = self.detector._extract_entities_from_response({}, "text")

            self.assertEqual(results, [])

            mock_log.assert_called_once()

    # _gather_raw_entities extracts list of entities
    def test_gather_raw_entities(self):
        response = {"pages": [{"text": [{"entities": [{"entity_type": "EMAIL"}]}]}]}

        result = self.detector._gather_raw_entities(response)

        self.assertEqual(result[0]["entity_type"], "EMAIL")

    # _maybe_add_original_text adds text when valid offsets
    def test_maybe_add_original_text_valid(self):
        ent = {"start": 0, "end": 5}

        result = self.detector._maybe_add_original_text(ent, "hello world")

        self.assertEqual(result["original_text"], "hello")

    # _maybe_add_original_text skips on invalid offsets
    def test_maybe_add_original_text_invalid(self):
        ent = {"start": 0, "end": 999}

        with patch("backend.app.utils.logging.logger.log_warning"):
            result = self.detector._maybe_add_original_text(ent, "short")

            self.assertNotIn("original_text", result)

    # _process_single_page succeeds and releases slot
    @patch(
        "backend.app.entity_detection.gemini.gemini_usage_manager.manage_page_processing",
        new_callable=AsyncMock,
    )
    @patch(
        "backend.app.entity_detection.gemini.gemini_usage_manager.release_request_slot",
        new_callable=AsyncMock,
    )
    @patch("backend.app.utils.logging.logger.log_info")
    @patch("backend.app.utils.logging.logger.log_warning")
    @patch(
        "backend.app.utils.system_utils.error_handling.SecurityAwareErrorHandler.log_processing_error"
    )
    async def test_process_single_page_success(
        self, mock_error_log, mock_warning, mock_info, mock_release, mock_manage
    ):
        mock_lock = MagicMock()

        mock_cm = AsyncMock()

        mock_cm.__aenter__.return_value = None

        mock_cm.__aexit__.return_value = None

        mock_lock.acquire_timeout.return_value = mock_cm

        self.detector._get_api_lock = AsyncMock(return_value=mock_lock)

        self.detector.gemini_helper.process_text = AsyncMock(
            return_value={"pages": [{"text": [{"entities": [{"start": 0, "end": 5}]}]}]}
        )

        self.detector._extract_entities_from_response = MagicMock(
            return_value=[{"start": 0, "end": 5}]
        )

        self.detector.process_entities_for_page = AsyncMock(
            return_value=(
                [{"entity_type": "EMAIL"}],
                {"page": 1, "sensitive": [{"entity_type": "EMAIL"}]},
            )
        )

        mock_manage.return_value = "processed text"

        page_data = {"page": 1, "words": [{"text": "hello", "start": 0, "end": 5}]}

        mapping = {1: ("hello", [({"text": "hello"}, 0, 5)])}

        result = await self.detector._process_single_page(page_data, mapping, ["EMAIL"])

        self.assertEqual(result[0]["page"], 1)

        self.assertEqual(result[1][0]["entity_type"], "EMAIL")

        mock_release.assert_awaited()

    # empty words returns empty result
    async def test_process_single_page_empty_words(self):
        result = await self.detector._process_single_page(
            {"page": 1, "words": []}, {}, ["EMAIL"]
        )

        self.assertEqual(result, ({"page": 1, "sensitive": []}, []))

    # blocked by usage manager returns empty
    @patch(
        "backend.app.entity_detection.gemini.gemini_usage_manager.manage_page_processing",
        new_callable=AsyncMock,
    )
    async def test_process_single_page_blocked_by_usage_manager(self, mock_manage):
        mock_manage.return_value = None

        result = await self.detector._process_single_page(
            {"page": 1, "words": [{"text": "hello", "start": 0, "end": 5}]},
            {1: ("hello", [({"text": "hello"}, 0, 5)])},
            ["EMAIL"],
        )

        self.assertEqual(result, ({"page": 1, "sensitive": []}, []))

    # no API response returns empty result and releases slot
    @patch(
        "backend.app.entity_detection.gemini.gemini_usage_manager.manage_page_processing",
        new_callable=AsyncMock,
    )
    @patch(
        "backend.app.entity_detection.gemini.gemini_usage_manager.release_request_slot",
        new_callable=AsyncMock,
    )
    async def test_process_single_page_no_api_response(self, mock_release, mock_manage):
        mock_acquire_cm = AsyncMock()

        mock_acquire_cm.__aenter__.return_value = None

        mock_acquire_cm.__aexit__.return_value = None

        mock_lock = MagicMock()

        mock_lock.acquire_timeout.return_value = mock_acquire_cm

        self.detector._get_api_lock = AsyncMock(return_value=mock_lock)

        self.detector.gemini_helper.process_text = AsyncMock(return_value=None)

        mock_manage.return_value = "processed text"

        result = await self.detector._process_single_page(
            {"page": 1, "words": [{"text": "hello", "start": 0, "end": 5}]},
            {1: ("hello", [({"text": "hello"}, 0, 5)])},
            ["EMAIL"],
        )

        self.assertEqual(result, ({"page": 1, "sensitive": []}, []))
