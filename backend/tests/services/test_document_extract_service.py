import unittest

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.responses import JSONResponse

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

        response = await service.extract(DummyUploadFile())

        self.assertIsInstance(response, JSONResponse)

        self.assertEqual(response.status_code, 200)

        self.assertIn("error", response.body.decode())

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

        data = response.body.decode()

        self.assertIsInstance(response, JSONResponse)

        self.assertIn("performance", data)

        self.assertIn("file_info", data)

        self.assertIn("_debug", data)

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

            self.assertIsInstance(error, JSONResponse)

            self.assertIn("error", error.body.decode())

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
