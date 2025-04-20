import time

import unittest

from unittest.mock import patch, MagicMock, AsyncMock

from backend.app.entity_detection.glinerbase import GenericEntityDetector


class TestGenericEntityDetector(unittest.IsolatedAsyncioTestCase):

    # Setup mock subclass and detector instance
    def setUp(self):
        class TestDetector(GenericEntityDetector):
            ENGINE_NAME = "TEST"
            MODEL_NAME = "test-model"
            DEFAULT_ENTITIES = ["TEST"]
            MODEL_DIR_PATH = "mock_dir"
            CACHE_NAMESPACE = "test_cache"
            CONFIG_FILE_NAME = "test_config.json"

            def __init__(self):
                super().__init__()
                self._total_calls = 0
                self.norwegian_pronouns = {"jeg", "du", "han", "hun", "det", "vi", "dere", "de"}
                self._is_initialized = True
                self._initialization_time = time.time()
                self._last_used = time.time()
                self.total_processing_time = 0
                self._model_name = "test-model"
                self.model = MagicMock()
                self._model_dir_path = "mock_dir"
                self._local_model_path = "mock_local_path"
                self._local_files_only = False
                self.CONFIG_FILE_NAME = "test_config.json"
                self._global_initializing = False
                self._global_initialization_time = 0
                self._model_analyzer_lock = MagicMock()

        with patch("backend.app.entity_detection.glinerbase.GenericEntityDetector.__init__") as mock_init:
            mock_init.return_value = None

            self.detector = TestDetector()

            self.detector.model = MagicMock()

    # Positive test: process text and cache result
    @patch("backend.app.utils.helpers.gliner_helper.GLiNERHelper.get_cache_key", return_value="mock_key")
    @patch("backend.app.utils.helpers.gliner_helper.GLiNERHelper.get_cached_result", return_value=None)
    @patch("backend.app.utils.helpers.gliner_helper.GLiNERHelper.set_cached_result")
    def test_process_text_positive(self, mock_set_cache, mock_get_cached, mock_key):
        self.detector.model.predict_entities = MagicMock(return_value=[

            {"label": "TEST", "start": 0, "end": 4, "score": 0.9, "text": "text"}

        ])

        result = self.detector._process_text("text example", ["TEST"])

        self.assertTrue(len(result) > 0)

        mock_set_cache.assert_called()

    # Model missing returns empty list
    def test_process_text_model_missing(self):
        self.detector.model = None

        self.detector._is_initialized = True

        result = self.detector._process_text("text example", ["TEST"])

        self.assertEqual(result, [])

    # Uninitialized model returns empty list
    def test_process_text_uninitialized_model(self):
        self.detector.model = MagicMock()

        self.detector._is_initialized = False

        result = self.detector._process_text("text example", ["TEST"])

        self.assertEqual(result, [])

    # Norwegian pronoun filter removes known pronouns
    def test_filter_norwegian_pronouns_removes_known(self):
        pronoun = {"entity_type": "PERSON-H", "original_text": "jeg"}

        result = self.detector._filter_norwegian_pronouns([pronoun])

        self.assertEqual(result, [])

    # Pronoun filter keeps valid entities
    def test_filter_norwegian_pronouns_keeps_valid(self):
        valid = {"entity_type": "EMAIL", "original_text": "rami@example.com"}

        result = self.detector._filter_norwegian_pronouns([valid])

        self.assertEqual(result, [valid])

    # Prepare page data for pages with text
    def test_prepare_page_data_with_words(self):
        pages = [{"page": 1, "words": [{"text": "hi"}]}]

        with patch("backend.app.utils.helpers.text_utils.TextUtils.reconstruct_text_and_mapping",
                   return_value=("hi", [({}, 0, 2)])):
            mapping, redaction = self.detector._prepare_page_data(pages)

            self.assertIn(1, mapping)

            self.assertEqual(redaction["pages"], [])

    # Prepare page data for pages without text
    def test_prepare_page_data_empty_words(self):
        pages = [{"page": 1, "words": []}]

        mapping, redaction = self.detector._prepare_page_data(pages)

        self.assertEqual(mapping, {})

        self.assertEqual(redaction["pages"], [{"page": 1, "sensitive": []}])

    # Extract entities for group when lock acquired
    def test_extract_entities_for_group_success(self):
        self.detector.model.predict_entities = MagicMock(return_value=[

            {"label": "TEST", "start": 0, "end": 4, "score": 0.9, "text": "test"}

        ])

        lock = MagicMock()

        lock.acquire.return_value = True

        self.detector._get_model_analyzer_lock = MagicMock(return_value=lock)

        result = self.detector._extract_entities_for_group("text", ["TEST"], 0)

        self.assertEqual(result[0]["entity_type"], "TEST")

    # Lock timeout in group extraction returns empty list
    def test_extract_entities_for_group_timeout_lock(self):
        lock = MagicMock()

        lock.acquire.return_value = False

        self.detector._get_model_analyzer_lock = MagicMock(return_value=lock)

        result = self.detector._extract_entities_for_group("text", ["TEST"], 0)

        self.assertEqual(result, [])

    # Async detection with empty pages returns empty mapping
    async def test_detect_sensitive_data_async_empty_pages(self):
        result, mapping = await self.detector.detect_sensitive_data_async({"pages": []}, ["TEST"])

        self.assertEqual(result, [])

        self.assertEqual(mapping, {"pages": []})

    # JSON validation returns list of entities
    def test_validate_requested_entities_json(self):
        json_data = '["email"]'

        result = self.detector.validate_requested_entities(json_data)

        self.assertEqual(result, ["email"])

    # get_status includes initialized and model_available
    def test_get_status_output(self):
        status = self.detector.get_status()

        self.assertIn("initialized", status)

        self.assertIn("model_available", status)

    # Async single-page processing uses parallel core
    @patch("backend.app.utils.parallel.core.ParallelProcessingCore.process_entities_in_parallel",
           new_callable=AsyncMock)
    async def test_process_single_page_async_positive(self, mock_parallel):
        def fake_process_text(text, entities):
            return [{"entity_type": "email", "start": 0, "end": 5, "original_text": "test"}]

        self.detector._process_text = fake_process_text

        self.detector.model = MagicMock()

        mock_parallel.return_value = (

            [{"entity_type": "email"}],

            {"page": 1, "sensitive": [{"entity_type": "email"}]}

        )

        page_data = {"page": 1, "words": [{"text": "test", "start": 0, "end": 4}]}

        mapping = {1: ("test", [({"text": "test"}, 0, 4)])}

        entities = ["email"]

        result = await self.detector._process_single_page_async(page_data, mapping, entities)

        self.assertEqual(result[0]["page"], 1)

        self.assertEqual(result[1][0]["entity_type"], "email")

        mock_parallel.assert_awaited()

    # Async detection validation failure yields empty lists
    @patch("backend.app.utils.helpers.gliner_helper.GLiNERHelper.get_cache_key", return_value="mock_key")
    @patch("backend.app.utils.helpers.gliner_helper.GLiNERHelper.get_cached_result", return_value=None)
    async def test_detect_sensitive_data_async_validation_failure(self, mock_get_cached, mock_key):
        self.detector.validate_requested_entities = MagicMock(side_effect=Exception("Validation failed"))

        extracted_data = {"pages": [{"page": 1, "words": [{"text": "test"}]}]}

        requested_entities = ["TEST"]

        result, mapping = await self.detector.detect_sensitive_data_async(extracted_data, requested_entities)

        self.assertEqual(result, [])

        self.assertEqual(mapping, {"pages": []})

    # Async detection returns empty when no valid entities
    @patch("backend.app.utils.helpers.gliner_helper.GLiNERHelper.get_cache_key", return_value="mock_key")
    @patch("backend.app.utils.helpers.gliner_helper.GLiNERHelper.get_cached_result", return_value=None)
    async def test_detect_sensitive_data_async_no_valid_entities(self, mock_get_cached, mock_key):
        self.detector.validate_requested_entities = MagicMock(return_value=[])

        extracted_data = {"pages": [{"page": 1, "words": [{"text": "test"}]}]}

        requested_entities = ["TEST"]

        result, mapping = await self.detector.detect_sensitive_data_async(extracted_data, requested_entities)

        self.assertEqual(result, [])

        self.assertEqual(mapping, {"pages": []})
