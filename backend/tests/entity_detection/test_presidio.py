import unittest

from unittest import mock

from unittest.mock import patch, MagicMock, AsyncMock

import asyncio

from backend.app.entity_detection.presidio import PresidioEntityDetector

from backend.app.domain import EntityDetector

from presidio_analyzer import AnalyzerEngine

from presidio_anonymizer import AnonymizerEngine

from backend.app.utils.system_utils.synchronization_utils import TimeoutLock


class TestPresidioEntityDetector(unittest.TestCase):

    def setUp(self):
        # Prepare a mocked PresidioEntityDetector instance
        with patch("backend.app.entity_detection.presidio.PresidioEntityDetector.__init__") as mock_init:
            mock_init.return_value = None

            self.detector = PresidioEntityDetector()

            self.detector._analyzer_conf_file = "mock_analyzer_config.yml"

            self.detector._nlp_engine_conf_file = "mock_nlp_config.yml"

            self.detector._recognizer_registry_conf_file = "mock_recognizer_config.yml"

            self.detector._analyzer_lock = MagicMock()

    @patch("backend.app.entity_detection.presidio.log_error")
    def test_get_analyzer_lock_creation(self, mock_log_error):
        # _get_analyzer_lock returns a lock without logging errors
        lock = self.detector._get_analyzer_lock()

        self.assertIsNotNone(lock)

        mock_log_error.assert_not_called()

    @patch("backend.app.entity_detection.presidio.TimeoutLock")
    def test_get_analyzer_lock_creation_failure(self, MockTimeoutLock):
        # _get_analyzer_lock handles TimeoutLock construction failures
        MockTimeoutLock.side_effect = Exception("Lock creation failed")

        lock = self.detector._get_analyzer_lock()

        self.assertIsInstance(lock, MagicMock)

    @patch("backend.app.entity_detection.presidio.hashlib.md5")
    def test_cache_key_creation(self, mock_md5):
        # _cache_key generates an MD5-based cache key
        mock_md5.return_value.hexdigest.return_value = "mocked_hash"

        key = self.detector._cache_key("text_sample", ["email"])

        self.assertEqual(key, "mocked_hash")

    @patch("backend.app.entity_detection.presidio.AnalyzerEngine")
    @patch("backend.app.entity_detection.presidio.AnonymizerEngine")
    @patch("backend.app.entity_detection.presidio.log_error")
    def test_initialize_presidio_success(self, mock_log_error, MockAnonymizerEngine, MockAnalyzerEngine):
        # _initialize_presidio correctly sets up analyzer and anonymizer
        mock_analyzer_instance = MagicMock(spec=AnalyzerEngine)

        mock_anonymizer_instance = MagicMock(spec=AnonymizerEngine)

        MockAnalyzerEngine.return_value = mock_analyzer_instance

        MockAnonymizerEngine.return_value = mock_anonymizer_instance

        self.detector._initialize_presidio()

        self.assertIs(self.detector.analyzer, mock_analyzer_instance)

        self.assertIs(self.detector.anonymizer, mock_anonymizer_instance)

        mock_log_error.assert_not_called()

    @patch("backend.app.entity_detection.presidio.log_warning")
    @patch("backend.app.entity_detection.presidio.AnalyzerEngine")
    @patch("backend.app.entity_detection.presidio.AnonymizerEngine")
    def test_initialize_presidio_warning_missing_config(self, mock_anonymizer, mock_analyzer, mock_log_warning):
        # _initialize_presidio warns and uses defaults when config is missing
        mock_analyzer.return_value = None

        mock_anonymizer.return_value = None

        self.detector._initialize_presidio()

        mock_log_warning.assert_called_with("[WARNING] Using default configuration")

    @patch("backend.app.entity_detection.presidio.log_error")
    def test_presidio_entity_detector_init(self, mock_log_error):
        # __init__ invokes _initialize_presidio without error
        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = True

            with patch.object(self.detector, '_initialize_presidio') as mock_init_presidio:
                self.detector.__init__()

        mock_init_presidio.assert_called_once()

        mock_log_error.assert_not_called()

    @patch("backend.app.entity_detection.presidio.log_warning")
    def test_validate_entities_invalid(self, mock_log_warning):
        # detect_sensitive_data_async returns empty for invalid entities
        invalid_entities = ["invalid_entity"]

        result, redaction_mapping = asyncio.run(self.detector.detect_sensitive_data_async({}, invalid_entities))

        self.assertEqual(result, [])

        self.assertEqual(redaction_mapping, {"pages": []})

        mock_log_warning.assert_called_with(
            "[Presidio] No valid entities remain after filtering, returning empty results"
        )

    @patch("backend.app.entity_detection.presidio.log_warning")
    @patch("backend.app.entity_detection.presidio.PresidioEntityDetector._process_all_pages_async")
    def test_process_single_page_async_invalid(self, mock_process_all_pages, mock_log_warning):
        # detect_sensitive_data_async handles processing exceptions gracefully
        mock_process_all_pages.side_effect = Exception("Processing error")

        result = asyncio.run(
            self.detector.detect_sensitive_data_async({"page": 1, "words": ["test"]}, ["email"])
        )

        self.assertEqual(result, ([], {"pages": []}))

        mock_log_warning.assert_called_with(
            "[Presidio] No valid entities remain after filtering, returning empty results"
        )

    @patch("backend.app.entity_detection.presidio.log_info")
    async def test_run_async_detector_timeout(self, mock_log_info):
        # _run_async_detector returns empty on TimeoutError and logs a warning
        async def mock_async_detector(*args, **kwargs):
            raise asyncio.TimeoutError

        self.detector._run_async_detector = AsyncMock(side_effect=mock_async_detector)

        result = await self.detector._run_async_detector(MagicMock(spec=EntityDetector), {}, [])

        self.assertEqual(result, ([], {"pages": []}))

        mock_log_info.assert_called_with("[WARNING] Timeout in async detector")

    @patch("backend.app.entity_detection.presidio.validate_presidio_requested_entities")
    @patch("backend.app.entity_detection.presidio.minimize_extracted_data")
    @patch("backend.app.entity_detection.presidio.PresidioEntityDetector._process_all_pages_async")
    @patch("backend.app.entity_detection.presidio.record_keeper.record_processing")
    def test_detect_sensitive_data_async_validation_failure(
            self, mock_record_processing, mock_process_all_pages, mock_minimize_extracted_data, mock_validate_entities
    ):
        # detect_sensitive_data_async logs and records failure on validation exception
        mock_validate_entities.side_effect = Exception("Validation failed")

        result, redaction_mapping = asyncio.run(
            self.detector.detect_sensitive_data_async({"page": 1, "words": ["test"]}, ["email"])
        )

        self.assertEqual(result, [])

        self.assertEqual(redaction_mapping, {"pages": []})

        mock_record_processing.assert_called_once_with(
            operation_type="presidio_detection",
            document_type="document",
            entity_types_processed=["email"],
            processing_time=mock.ANY,
            entity_count=0,
            success=False
        )

    @patch("backend.app.entity_detection.presidio.validate_presidio_requested_entities")
    @patch("backend.app.entity_detection.presidio.minimize_extracted_data")
    @patch("backend.app.entity_detection.presidio.PresidioEntityDetector._process_all_pages_async")
    @patch("backend.app.entity_detection.presidio.record_keeper.record_processing")
    def test_detect_sensitive_data_async_no_valid_entities(
            self, mock_record_processing, mock_process_all_pages, mock_minimize_extracted_data, mock_validate_entities
    ):
        # detect_sensitive_data_async records failure when no entities after validation
        mock_validate_entities.return_value = []

        mock_minimize_extracted_data.return_value = {"pages": [{"page": 1, "words": ["test"]}]}

        mock_process_all_pages.return_value = [(1, ({}, []))]

        result, redaction_mapping = asyncio.run(
            self.detector.detect_sensitive_data_async({"page": 1, "words": ["test"]}, ["email"])
        )

        self.assertEqual(result, [])

        self.assertEqual(redaction_mapping, {"pages": []})

        mock_record_processing.assert_called_once_with(
            operation_type="presidio_detection",
            document_type="document",
            entity_types_processed=[],
            processing_time=mock.ANY,
            entity_count=0,
            success=False
        )

    @patch("backend.app.entity_detection.presidio.validate_presidio_requested_entities")
    @patch("backend.app.entity_detection.presidio.minimize_extracted_data")
    @patch("backend.app.entity_detection.presidio.PresidioEntityDetector._process_all_pages_async")
    @patch("backend.app.entity_detection.presidio.record_keeper.record_processing")
    def test_detect_sensitive_data_async_processing_error(
            self, mock_record_processing, mock_process_all_pages, mock_minimize_extracted_data, mock_validate_entities
    ):
        # detect_sensitive_data_async records failure when page processing raises
        mock_validate_entities.return_value = ['email', 'phone']

        mock_minimize_extracted_data.return_value = {"pages": [{"page": 1, "words": ["test"]}]}

        mock_process_all_pages.side_effect = Exception("Processing error")

        result, redaction_mapping = asyncio.run(
            self.detector.detect_sensitive_data_async({"page": 1, "words": ["test"]}, ["email"])
        )

        self.assertEqual(result, [])

        self.assertEqual(redaction_mapping, {"pages": []})

        mock_record_processing.assert_called_once_with(
            operation_type="presidio_detection",
            document_type="document",
            entity_types_processed=['email', 'phone'],
            processing_time=mock.ANY,
            entity_count=0,
            success=False
        )

    @patch("backend.app.entity_detection.presidio.log_info")
    @patch("backend.app.entity_detection.presidio.log_warning")
    @patch("backend.app.entity_detection.presidio.SecurityAwareErrorHandler.log_processing_error")
    @patch("backend.app.entity_detection.presidio.PresidioEntityDetector._get_analyzer_lock")
    def test_analyze_text_cache_hit(
            self, mock_get_lock, mock_log_processing_error, mock_log_warning, mock_log_info
    ):
        # _analyze_text returns cached data on cache hit
        cache_key = self.detector._cache_key("test text", ["email"])

        self.detector.cache = {cache_key: ["cached_result"]}

        mock_lock = MagicMock(spec=TimeoutLock)

        mock_get_lock.return_value = mock_lock

        mock_lock.acquire.return_value = True

        result = self.detector._analyze_text("test text", "en", ["email"])

        self.assertEqual(result, ["cached_result"])

        mock_log_info.assert_called_with("[Presidio] ✅ Using cached analysis result")

        mock_log_processing_error.assert_not_called()

        mock_log_warning.assert_not_called()

    @patch("backend.app.entity_detection.presidio.log_warning")
    @patch("backend.app.entity_detection.presidio.PresidioEntityDetector._get_analyzer_lock")
    def test_analyze_text_lock_acquisition_failure(self, mock_get_lock, mock_log_warning):
        # _analyze_text returns empty when lock acquisition fails
        mock_lock = MagicMock(spec=TimeoutLock)

        mock_get_lock.return_value = mock_lock

        mock_lock.acquire.return_value = False

        self.detector.cache = {}

        result = self.detector._analyze_text("test text", "en", ["email"])

        self.assertEqual(result, [])

        mock_log_warning.assert_called_with("[WARNING] Failed to acquire lock for Presidio analysis")

    @patch("backend.app.entity_detection.presidio.log_warning")
    @patch("backend.app.entity_detection.presidio.PresidioEntityDetector._get_analyzer_lock")
    def test_analyze_text_analyzer_not_initialized(self, mock_get_lock, mock_log_warning):
        # _analyze_text returns empty when analyzer is not initialized
        self.detector.analyzer = None

        self.detector.cache = {}

        mock_lock = MagicMock(spec=TimeoutLock)

        mock_get_lock.return_value = mock_lock

        mock_lock.acquire.return_value = True

        result = self.detector._analyze_text("test text", "en", ["email"])

        self.assertEqual(result, [])

        mock_log_warning.assert_called_with("[WARNING] Presidio analyzer not initialized, returning empty result")

    @patch("backend.app.entity_detection.presidio.SecurityAwareErrorHandler.log_processing_error")
    @patch("backend.app.entity_detection.presidio.PresidioEntityDetector._get_analyzer_lock")
    def test_analyze_text_successful_analysis(self, mock_get_lock, mock_log_processing_error):
        # _analyze_text performs analysis when initialized
        self.detector.analyzer = MagicMock(spec=AnalyzerEngine)

        self.detector.analyzer.analyze.return_value = ["detected_entity"]

        self.detector.cache = {}

        mock_lock = MagicMock(spec=TimeoutLock)

        mock_get_lock.return_value = mock_lock

        mock_lock.acquire.return_value = True

        result = self.detector._analyze_text("test text", "en", ["email"])

        self.assertEqual(result, ["detected_entity"])

        mock_log_processing_error.assert_not_called()

    @patch("backend.app.entity_detection.presidio.SecurityAwareErrorHandler.log_processing_error")
    @patch("backend.app.entity_detection.presidio.PresidioEntityDetector._get_analyzer_lock")
    def test_analyze_text_analysis_exception(self, mock_get_lock, mock_log_processing_error):
        # _analyze_text logs and returns empty on analyzer exceptions
        self.detector.analyzer = MagicMock(spec=AnalyzerEngine)

        self.detector.analyzer.analyze.side_effect = Exception("Analysis failed")

        self.detector.cache = {}

        mock_lock = MagicMock(spec=TimeoutLock)

        mock_get_lock.return_value = mock_lock

        mock_lock.acquire.return_value = True

        result = self.detector._analyze_text("test text", "en", ["email"])

        self.assertEqual(result, [])

        mock_log_processing_error.assert_called_once_with(
            mock.ANY,
            "presidio_analysis"
        )

        exception = mock_log_processing_error.call_args[0][0]

        self.assertEqual(str(exception), "Analysis failed")

    @patch("backend.app.entity_detection.presidio.ParallelProcessingCore.process_pages_in_parallel")
    @patch("backend.app.entity_detection.presidio.PresidioEntityDetector._process_single_page_async")
    async def test_process_all_pages_async_success(self, mock_process_single_page, mock_process_pages):
        # _process_all_pages_async returns results for each page
        mock_process_single_page.return_value = ({"page": 1, "sensitive": ["email"]}, ["email"])

        pages = [{"page": 1, "words": ["test text"]}]

        requested_entities = ["email"]

        result = await self.detector._process_all_pages_async(pages, requested_entities)

        self.assertEqual(result, [(1, ({"page": 1, "sensitive": ["email"]}, ["email"]))])

        mock_process_single_page.assert_called_once_with({"page": 1, "words": ["test text"]})

    @patch("backend.app.entity_detection.presidio.ParallelProcessingCore.process_pages_in_parallel")
    @patch("backend.app.entity_detection.presidio.PresidioEntityDetector._process_single_page_async")
    async def test_process_all_pages_async_timeout(self, mock_process_single_page, mock_process_pages):
        # _process_all_pages_async handles page-level timeouts gracefully
        mock_process_pages.side_effect = asyncio.TimeoutError("Timeout processing pages")

        pages = [{"page": 1, "words": ["test text"]}]

        requested_entities = ["email"]

        result = await self.detector._process_all_pages_async(pages, requested_entities)

        self.assertEqual(result, [])

        mock_process_pages.assert_called_once()

    @patch("backend.app.entity_detection.presidio.ParallelProcessingCore.process_pages_in_parallel")
    @patch("backend.app.entity_detection.presidio.PresidioEntityDetector._process_single_page_async")
    @patch("backend.app.entity_detection.presidio.SecurityAwareErrorHandler.log_processing_error")
    async def test_process_all_pages_async_exception(self, mock_log_processing_error, mock_process_single_page,
                                                     mock_process_pages):
        # _process_all_pages_async logs errors and returns empty on exceptions
        mock_process_single_page.side_effect = Exception("Processing error")

        pages = [{"page": 1, "words": ["test text"]}]

        requested_entities = ["email"]

        result = await self.detector._process_all_pages_async(pages, requested_entities)

        self.assertEqual(result, [])

        mock_log_processing_error.assert_called_with(
            mock.ANY,
            "presidio_page_processing",
            "page_1"
        )

    def test_aggregate_page_results_valid(self):
        # _aggregate_page_results merges entities and mappings correctly
        local_page_results = [
            (1, ({"page": 1, "sensitive": ["email"]}, ["email"])),
            (2, ({"page": 2, "sensitive": ["phone"]}, ["phone"])),
        ]

        combined_entities, redaction_mapping = PresidioEntityDetector._aggregate_page_results(local_page_results)

        self.assertEqual(combined_entities, ["email", "phone"])

        self.assertEqual(
            redaction_mapping,
            {"pages": [{"page": 1, "sensitive": ["email"]}, {"page": 2, "sensitive": ["phone"]}]}
        )

    def test_aggregate_page_results_empty(self):
        # _aggregate_page_results returns empty on no input
        local_page_results = []

        combined_entities, redaction_mapping = PresidioEntityDetector._aggregate_page_results(local_page_results)

        self.assertEqual(combined_entities, [])

        self.assertEqual(redaction_mapping, {"pages": []})

    def test_aggregate_page_results_missing_redaction_info(self):
        # _aggregate_page_results skips missing mapping entries
        local_page_results = [
            (1, (None, ["email"])),
            (2, (None, ["phone"])),
        ]

        combined_entities, redaction_mapping = PresidioEntityDetector._aggregate_page_results(local_page_results)

        self.assertEqual(combined_entities, ["email", "phone"])

        self.assertEqual(redaction_mapping, {"pages": []})

    def test_aggregate_page_results_missing_entities(self):
        # _aggregate_page_results skips missing entity lists
        local_page_results = [
            (1, ({"page": 1, "sensitive": ["email"]}, None)),
            (2, ({"page": 2, "sensitive": ["phone"]}, None)),
        ]

        combined_entities, redaction_mapping = PresidioEntityDetector._aggregate_page_results(local_page_results)

        self.assertEqual(combined_entities, [])

        self.assertEqual(
            redaction_mapping,
            {"pages": [{"page": 1, "sensitive": ["email"]}, {"page": 2, "sensitive": ["phone"]}]}
        )

    def test_aggregate_page_results_with_empty_entities_and_redaction_info(self):
        # _aggregate_page_results handles empty entity and mapping entries
        local_page_results = [
            (1, (None, [])),
            (2, (None, [])),
        ]

        combined_entities, redaction_mapping = PresidioEntityDetector._aggregate_page_results(local_page_results)

        self.assertEqual(combined_entities, [])

        self.assertEqual(redaction_mapping, {"pages": []})
