import unittest
from unittest.mock import patch, MagicMock
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi import HTTPException

from backend.app.services.document_redact_service import DocumentRedactionService


# Dummy file object for filename and MIME tests
class DummyFile:

    def __init__(self, filename="test.pdf", content_type="application/pdf"):
        self.filename = filename

        self.content_type = content_type


# Test suite for DocumentRedactionService functionality
class TestDocumentRedactionService(unittest.IsolatedAsyncioTestCase):

    # Test successful redaction returns StreamingResponse with redaction header
    @patch("backend.app.services.document_redact_service.read_and_validate_file")
    @patch("backend.app.services.document_redact_service.PDFRedactionService")
    @patch(
        "backend.app.services.document_redact_service.memory_monitor.get_memory_stats",
        return_value={"current_usage": 50.0, "peak_usage": 75.0},
    )
    async def test_redact_success(
        self, mock_memory, mock_redactor_class, mock_validate
    ):
        mock_validate.return_value = (b"pdf-bytes", None, 0.1)

        mock_redactor = MagicMock()

        mock_redactor.apply_redactions_to_memory.return_value = b"redacted-bytes"

        mock_redactor_class.return_value = mock_redactor

        file = DummyFile()

        mapping = '{"pages": [{"page": 0, "sensitive": ["word"]}]}'

        response = await DocumentRedactionService().redact(file, mapping)

        self.assertIsInstance(response, StreamingResponse)

        self.assertEqual(response.headers["X-Redactions-Applied"], "1")

    # Test JSONResponse returned when file validation fails
    @patch(
        "backend.app.services.document_redact_service.read_and_validate_file",
        return_value=(None, JSONResponse(content={"error": "invalid"}), 0),
    )
    async def test_redact_file_validation_error(self, mock_validate):
        file = DummyFile()

        response = await DocumentRedactionService().redact(file, "{}")

        self.assertIsInstance(response, JSONResponse)

        self.assertIn("error", response.body.decode())

    # Test JSONResponse returned when internal redaction service fails
    @patch(
        "backend.app.services.document_redact_service.read_and_validate_file",
        return_value=(b"valid-bytes", None, 0),
    )
    @patch(
        "backend.app.services.document_redact_service.PDFRedactionService",
        side_effect=Exception("crash"),
    )
    async def test_redact_internal_redaction_failure(self, mock_redact, mock_validate):
        file = DummyFile()

        mapping = '{"pages": [{"page": 0, "sensitive": ["word"]}]}'

        response = await DocumentRedactionService().redact(file, mapping)

        self.assertIsInstance(response, JSONResponse)

        self.assertIn("error", response.body.decode())

    # Test parsing a valid redaction mapping returns count and no error
    def test_parse_redaction_mapping_valid(self):
        result, count, err = DocumentRedactionService._parse_redaction_mapping(
            '{"pages": [{"page": 1, "sensitive": ["a"]}]}', "file.pdf", "op1"
        )

        self.assertEqual(count, 1)

        self.assertIsNone(err)

    @patch(
        "backend.app.services.document_redact_service.SecurityAwareErrorHandler.handle_safe_error"
    )
    def test_parse_redaction_mapping_invalid(self, mock_safe_error):
        mock_safe_error.return_value = {"status_code": 400, "detail": "Invalid JSON"}

        result, count, err = DocumentRedactionService._parse_redaction_mapping(
            "not-json", "file.pdf", "op2"
        )

        self.assertEqual(count, 0)

        self.assertIsInstance(err, HTTPException)

        self.assertEqual(err.status_code, 400)

        self.assertIn("Invalid JSON", err.detail)

    # Test parsing None mapping returns empty pages and no error
    def test_parse_redaction_mapping_none(self):
        result, count, err = DocumentRedactionService._parse_redaction_mapping(
            None, "file.pdf", "op3"
        )

        self.assertEqual(count, 0)

        self.assertEqual(result["pages"], [])

        self.assertIsNone(err)

    # Test redact method handles unhandled exceptions and returns error JSONResponse
    @patch(
        "backend.app.services.document_redact_service.read_and_validate_file",
        return_value=(b"valid-bytes", None, 0),
    )
    async def test_redact_unhandled_exception(self, mock_validate):
        service = DocumentRedactionService()

        service._parse_redaction_mapping = MagicMock(side_effect=Exception("boom"))

        file = DummyFile()

        response = await service.redact(file, "{}")

        self.assertIsInstance(response, JSONResponse)

        self.assertIn("error", response.body.decode())
