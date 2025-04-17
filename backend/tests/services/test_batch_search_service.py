import warnings
warnings.filterwarnings(
    "ignore",
    message=r"coroutine .* was never awaited",
    category=RuntimeWarning,
)
import unittest
from unittest.mock import patch, AsyncMock, MagicMock

from backend.app.services.batch_search_service import BatchSearchService


class DummyUploadFile:
    def __init__(self, filename="file.pdf", content_type="application/pdf"):
        self.filename = filename
        self.content_type = content_type


class TestBatchSearchService(unittest.IsolatedAsyncioTestCase):

    @patch("backend.app.services.batch_search_service.MAX_FILES_COUNT", 1)
    async def test_batch_search_too_many_files(self):
        files = [DummyUploadFile(), DummyUploadFile()]
        result = await BatchSearchService.batch_search_text(files, search_terms="test")
        self.assertIn("detail", result)
        self.assertEqual(result["detail"], "Too many files uploaded. Maximum allowed is 1.")

    @patch("backend.app.services.batch_search_service.read_and_validate_file", new_callable=AsyncMock)
    async def test_read_files_with_validation_error(self, mock_validate):
        mock_validate.return_value = (None, "Validation failed", 0.1)
        files = [DummyUploadFile()]
        contents, metadata = await BatchSearchService._read_files_for_extraction(files, "op123")
        self.assertIsNone(contents[0])
        self.assertEqual(metadata[0]["status"], "error")

    def test_parse_search_words_str(self):
        result = BatchSearchService._parse_search_words(" hello  world ")
        self.assertEqual(result, ["hello", "world"])

    def test_parse_search_words_list(self):
        result = BatchSearchService._parse_search_words(["  cat", "dog "])
        self.assertEqual(result, ["cat", "dog"])

    @patch("backend.app.services.batch_search_service.PDFSearcher.search_terms", new_callable=AsyncMock)
    async def test_process_single_file_result_success(self, mock_search):
        mock_search.return_value = {"match_count": 2}
        metadata = {"original_name": "file1"}
        extraction_result = {"pages": [{"words": ["word"]}]}
        result, success, fail, count = await BatchSearchService._process_single_file_result(
            metadata, extraction_result, ["word"], False, False
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(success, 1)
        self.assertEqual(count, 2)

    async def test_process_single_file_result_error(self):
        metadata = {"original_name": "file1"}
        extraction_result = {"error": "oops"}
        result, success, fail, count = await BatchSearchService._process_single_file_result(
            metadata, extraction_result, ["x"], False, False
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(fail, 1)

    @patch("backend.app.services.batch_search_service.PDFTextExtractor.extract_batch_text", new_callable=AsyncMock)
    @patch("backend.app.services.batch_search_service.BatchSearchService._read_files_for_extraction",
           new_callable=AsyncMock)
    @patch("backend.app.services.batch_search_service.BatchSearchService._process_single_file_result",
           new_callable=AsyncMock)
    async def test_batch_search_text_success(self, mock_process, mock_read, mock_extract):
        mock_read.return_value = ([b"%PDF"], [{"original_name": "f1", "status": "success"}])
        mock_extract.return_value = [(0, {"pages": [{"words": ["test"]}]})]
        mock_process.return_value = ({"file": "f1", "status": "success", "results": {"match_count": 1}}, 1, 0, 1)
        result = await BatchSearchService.batch_search_text([DummyUploadFile()], "test")
        self.assertEqual(result["batch_summary"]["successful"], 1)
        self.assertEqual(result["batch_summary"]["total_matches"], 1)

    @patch("backend.app.services.batch_search_service.PDFTextExtractor")
    @patch("backend.app.services.batch_search_service.PDFSearcher")
    @patch("backend.app.services.batch_search_service.read_and_validate_file", new_callable=AsyncMock)
    async def test_find_words_by_bbox_success(self, mock_validate, mock_searcher_cls, mock_extractor_cls):
        mock_validate.return_value = (b"%PDF", None, 0.1)
        dummy_extractor = MagicMock()
        dummy_extractor.extract_text.return_value = {"pages": [{"words": ["word"]}]}
        dummy_extractor.close = MagicMock()
        mock_extractor_cls.return_value = dummy_extractor

        dummy_searcher = MagicMock()
        dummy_searcher.find_target_phrase_occurrences.return_value = ({"pages": [1]}, 3)
        mock_searcher_cls.return_value = dummy_searcher

        files = [DummyUploadFile()]
        result = await BatchSearchService.find_words_by_bbox(files, {"x": 0, "y": 0, "w": 1, "h": 1}, "bbox-op")
        self.assertEqual(result["batch_summary"]["successful"], 1)
        self.assertEqual(result["batch_summary"]["total_matches"], 3)

    @patch("backend.app.services.batch_search_service.read_and_validate_file", new_callable=AsyncMock)
    async def test_find_words_by_bbox_validation_failure(self, mock_validate):
        mock_validate.return_value = (None, "err", 0.1)
        result = await BatchSearchService.find_words_by_bbox([DummyUploadFile()], {}, "op-id")
        self.assertEqual(result["file_results"][0]["status"], "error")
        self.assertIn("File validation failed", result["file_results"][0]["error"])
