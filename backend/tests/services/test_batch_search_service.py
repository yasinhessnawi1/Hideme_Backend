import unittest
from unittest.mock import patch, AsyncMock, MagicMock

from backend.app.services.batch_search_service import BatchSearchService


# Dummy upload file object for filename and MIME type tests
class DummyUploadFile:

    def __init__(self, filename="file.pdf", content_type="application/pdf"):
        self.filename = filename

        self.content_type = content_type


# Test suite for BatchSearchService functionality
class TestBatchSearchService(unittest.IsolatedAsyncioTestCase):

    # Test error when uploading more files than allowed
    @patch("backend.app.services.batch_search_service.MAX_FILES_COUNT", 1)
    async def test_batch_search_too_many_files(self):
        files = [DummyUploadFile(), DummyUploadFile()]

        result = await BatchSearchService.batch_search_text(files, search_terms="test")

        self.assertIn("detail", result)

        self.assertEqual(result["detail"], "Too many files uploaded. Maximum allowed is 1.")

    # Test handling validation error when reading files
    @patch("backend.app.services.batch_search_service.read_and_validate_file", new_callable=AsyncMock)
    async def test_read_files_with_validation_error(self, mock_validate):
        mock_validate.return_value = (None, "Validation failed", 0.1)

        files = [DummyUploadFile()]

        contents, metadata = await BatchSearchService._read_files_for_extraction(files, "op123")

        self.assertIsNone(contents[0])

        self.assertEqual(metadata[0]["status"], "error")

    # Test parsing search words from a whitespace string
    def test_parse_search_words_str(self):
        result = BatchSearchService._parse_search_words(" hello  world ")

        self.assertEqual(result, ["hello", "world"])

    # Test parsing search words from a list of strings
    def test_parse_search_words_list(self):
        result = BatchSearchService._parse_search_words(["  cat", "dog "])

        self.assertEqual(result, ["cat", "dog"])

    # Test successful processing of a single file search result
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

    # Test processing of a single file search result that contains an error
    async def test_process_single_file_result_error(self):
        metadata = {"original_name": "file1"}

        extraction_result = {"error": "oops"}

        result, success, fail, count = await BatchSearchService._process_single_file_result(

            metadata, extraction_result, ["x"], False, False

        )

        self.assertEqual(result["status"], "error")

        self.assertEqual(fail, 1)

    # Test successful batch text search across files
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

    # Test finding words by bounding box when extraction and search succeed
    @patch("backend.app.services.batch_search_service.read_and_validate_file", new_callable=AsyncMock)
    @patch("backend.app.services.batch_search_service.PDFTextExtractor.extract_batch_text", new_callable=AsyncMock)
    async def test_find_words_by_bbox_success(self,
                                              mock_extract_batch_text: AsyncMock,
                                              mock_validate: AsyncMock):
        mock_validate.return_value = (b"%PDF", None, 0.1)
        mock_extract_batch_text.return_value = [
            (0, {"pages": [{"words": ["word"]}]})
        ]

        # Return a proper page dict with a non‐empty "matches" list
        dummy_searcher = MagicMock(
            find_target_phrase_occurrences=MagicMock(
                return_value=(
                    {"pages": [
                        {"matches": [{"bbox": {"x0": 0, "y0": 0, "x1": 1, "y1": 1}}]}
                    ]},
                    3
                )
            )
        )
        with patch("backend.app.services.batch_search_service.PDFSearcher",
                   return_value=dummy_searcher):
            result = await BatchSearchService.find_words_by_bbox(
                [DummyUploadFile()],
                {"x": 0, "y": 0, "w": 1, "h": 1},
                "bbox-op"
            )

        self.assertEqual(result["batch_summary"]["successful"], 1)
        self.assertEqual(result["batch_summary"]["total_matches"], 3)

    # Test handling validation failure in bounding box search

    @patch("backend.app.services.batch_search_service.read_and_validate_file", new_callable=AsyncMock)
    async def test_find_words_by_bbox_validation_failure(self, mock_validate):
        # simulate validation failure
        mock_validate.return_value = (None, "err", 0.1)

        result = await BatchSearchService.find_words_by_bbox([DummyUploadFile()], {}, "op-id")

        # when all files fail validation, file_results is empty
        self.assertEqual(result["file_results"], [])

        # batch_summary should report 0 successful, 1 failed
        self.assertEqual(result["batch_summary"]["successful"], 0)
        self.assertEqual(result["batch_summary"]["failed"], 1)
