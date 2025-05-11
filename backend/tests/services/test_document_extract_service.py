import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.responses import JSONResponse
from fastapi import HTTPException

from backend.app.services.document_extract_service import DocumentExtractService


# Dummy upload file for testing document extraction
class DummyUploadFile:

    def __init__(self, filename="doc.pdf", content_type="application/pdf", content=b"%PDF-1.4"):
        self.filename = filename

        self.content_type = content_type

        self.content = content


# Test suite for DocumentExtractService
class TestDocumentExtractService(unittest.IsolatedAsyncioTestCase):

    # Test extract method returns error response on validation failure
    @patch("backend.app.services.document_extract_service.read_and_validate_file", new_callable=AsyncMock)
    async def test_extract_validation_error(self, mock_validate):

        service = DocumentExtractService()

        mock_validate.return_value = (None, JSONResponse(content={"error": "Invalid file"}), 0.1)

        with self.assertRaises(HTTPException) as cm:
            await service.extract(DummyUploadFile())

        self.assertEqual(cm.exception.status_code, 200)

        self.assertIn("Invalid file", cm.exception.detail.decode())

    # Test extract method successful flow returns performance and debug info
    @patch("backend.app.services.document_extract_service.read_and_validate_file", new_callable=AsyncMock)
    @patch("backend.app.services.document_extract_service.DocumentExtractService._extract_text")
    @patch("backend.app.services.document_extract_service.minimize_extracted_data", side_effect=lambda x: x)
    @patch("backend.app.services.document_extract_service.memory_monitor.get_memory_stats",
           return_value={"current_usage": 12.5, "peak_usage": 18.0})
    async def test_extract_successful_flow(self, mock_mem, mock_min, mock_extract, mock_validate):

        service = DocumentExtractService()

        mock_validate.return_value = (b"binarycontent", None, 0.2)

        extracted_data = {"pages": [{"words": [{"text": "hello"}, {"text": "world"}]}]}

        mock_extract.return_value = (extracted_data, None)

        response = await service.extract(DummyUploadFile())

        parsed = response.model_dump()

        self.assertIn("performance", parsed["file_results"][0]["results"])

        self.assertIn("file_info", parsed["file_results"][0]["results"])

        self.assertIn("debug", parsed)

    # Test internal _extract_text returns data and no error on success
    def test_extract_text_success(self):

        with patch("backend.app.services.document_extract_service.PDFTextExtractor") as mock_ext:
            instance = mock_ext.return_value

            instance.extract_text.return_value = {"pages": []}

            instance.close = MagicMock()

            data, error = DocumentExtractService._extract_text(b"pdf", "doc.pdf", "op123")

            self.assertIsNone(error)

            self.assertIsInstance(data, dict)

    # Test internal _extract_text returns error response on exception
    def test_extract_text_failure(self):

        with patch("backend.app.services.document_extract_service.PDFTextExtractor", side_effect=Exception("failed")):
            data, error = DocumentExtractService._extract_text(b"pdf", "doc.pdf", "op123")

            self.assertIsNone(data)

            self.assertIsInstance(error, HTTPException)

            self.assertEqual(error.status_code, 500)

            self.assertIn("Reference ID", str(error.detail))

    # Test removing text fields leaves only position in words
    def test_remove_text_from_extracted_data(self):

        data = {

            "pages": [

                {"words": [{"text": "secret", "pos": [1, 2]}, {"text": "word", "pos": [3, 4]}]},

                {"words": [{"text": "another", "pos": [5, 6]}]}

            ]

        }

        result = DocumentExtractService._remove_text_from_extracted_data(data)

        for page in result["pages"]:

            for word in page["words"]:
                self.assertNotIn("text", word)

                self.assertIn("pos", word)
