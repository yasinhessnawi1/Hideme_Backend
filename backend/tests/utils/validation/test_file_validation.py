"""
Unit tests for file_validation.py module.

This test file covers all functions in the file_validation module with both positive
and negative test cases to ensure proper functionality and error handling.
"""
import asyncio
import io
import unittest
from unittest.mock import patch
from fastapi.responses import JSONResponse

# Import the module to be tested
from backend.app.utils.validation.file_validation import (
    get_file_signature,
    get_mime_type_from_buffer,
    sanitize_filename,
    validate_mime_type,
    validate_pdf_file,
    _check_pdf_javascript,
    _check_pdf_acroform,
    validate_file_safety, validate_file_content, validate_file_content_async, read_and_validate_file
)


class TestFileValidation(unittest.IsolatedAsyncioTestCase):
    """Test cases for file_validation.py module."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        # Sample PDF content with valid header
        self.valid_pdf_content = b"%PDF-1.5\n% Some PDF content"

        # Sample PDF content with invalid header
        self.invalid_pdf_content = b"Not a PDF file"

        # Sample PDF content with JavaScript
        self.pdf_with_js = b"%PDF-1.5\n/JavaScript /JS Some JavaScript content"

        # Sample PDF content with AcroForm
        self.pdf_with_acroform = b"%PDF-1.5\n/AcroForm Some AcroForm content"

        # Mock file signatures for testing
        self.mock_file_signatures = {
            "pdf": [(b"%PDF", 0)],
            "jpg": [(b"\xFF\xD8\xFF", 0)],
            "png": [(b"\x89PNG\r\n\x1A\n", 0)]
        }

        # Mock MIME types for testing
        self.mock_allowed_mime_types = {
            "pdf": {"application/pdf", "application/x-pdf"}
        }

        # Mock extension to MIME mapping
        self.mock_extension_to_mime = {
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".png": "image/png"
        }

        # Mock application word constant
        self.mock_application_word = "application/pdf"

        # Mock max PDF size
        self.mock_max_pdf_size = 10 * 1024 * 1024  # 10 MB

    @patch('backend.app.utils.constant.constant.FILE_SIGNATURES', {"pdf": [(b"%PDF", 0)]})
    def test_get_file_signature_positive(self):
        """Test get_file_signature with valid PDF content."""
        # Test with valid PDF content
        result = get_file_signature(self.valid_pdf_content)
        self.assertEqual(result, "pdf")

    @patch('backend.app.utils.constant.constant.FILE_SIGNATURES', {"pdf": [(b"%PDF", 0)]})
    def test_get_file_signature_negative(self):
        """Test get_file_signature with invalid content."""
        # Test with invalid content
        result = get_file_signature(self.invalid_pdf_content)
        self.assertIsNone(result)

        # Test with empty content
        result = get_file_signature(b"")
        self.assertIsNone(result)

        # Test with content shorter than required
        result = get_file_signature(b"123")
        self.assertIsNone(result)

    @patch('backend.app.utils.constant.constant.EXTENSION_TO_MIME', {".pdf": "application/pdf"})
    @patch('backend.app.utils.constant.constant.APPLICATION_WORD', "application/pdf")
    @patch('backend.app.utils.validation.file_validation.get_file_signature')
    def test_get_mime_type_from_buffer_with_filename(self, mock_get_file_signature):
        """Test get_mime_type_from_buffer with filename."""
        # Setup mock
        mock_get_file_signature.return_value = "pdf"

        # Test with filename having known extension
        result = get_mime_type_from_buffer(self.valid_pdf_content, "document.pdf")
        self.assertEqual(result, "application/pdf")

        # Verify get_file_signature was not called when extension is known
        mock_get_file_signature.assert_not_called()

    @patch('backend.app.utils.validation.file_validation.EXTENSION_TO_MIME', {})
    @patch('mimetypes.guess_type')
    @patch('backend.app.utils.validation.file_validation.get_file_signature')
    def test_get_mime_type_from_buffer_with_mimetypes(self, mock_get_file_signature, mock_guess_type):
        """Test get_mime_type_from_buffer using mimetypes."""
        # Setup mocks
        mock_guess_type.return_value = ("application/pdf", None)
        mock_get_file_signature.return_value = None

        # Test with filename but extension not in EXTENSION_TO_MIME
        result = get_mime_type_from_buffer(self.valid_pdf_content, "document.pdf")
        self.assertEqual(result, "application/pdf")

        # Verify mimetypes.guess_type was called
        mock_guess_type.assert_called_once_with("document.pdf")

    @patch('backend.app.utils.constant.constant.EXTENSION_TO_MIME', {})
    @patch('mimetypes.guess_type')
    @patch('backend.app.utils.validation.file_validation.get_file_signature')
    @patch('backend.app.utils.constant.constant.APPLICATION_WORD', "application/pdf")
    def test_get_mime_type_from_buffer_with_content(self, mock_get_file_signature, mock_guess_type,
                                                    mock_application_word="application/pdf"):
        """Test get_mime_type_from_buffer using content."""
        # Setup mocks
        mock_guess_type.return_value = (None, None)
        mock_get_file_signature.return_value = "pdf"

        # Test with content only (bytes)
        result = get_mime_type_from_buffer(self.valid_pdf_content)
        self.assertEqual(result, "application/pdf")

        # Verify get_file_signature was called
        mock_get_file_signature.assert_called_once()

        # Reset mock
        mock_get_file_signature.reset_mock()

        # Test with file-like object
        file_obj = io.BytesIO(self.valid_pdf_content)
        result = get_mime_type_from_buffer(file_obj)
        self.assertEqual(result, "application/pdf")

        # Verify get_file_signature was called
        mock_get_file_signature.assert_called_once()

        # Verify file position was reset
        self.assertEqual(file_obj.tell(), 0)

    @patch('backend.app.utils.constant.constant.EXTENSION_TO_MIME', {})
    @patch('mimetypes.guess_type')
    @patch('backend.app.utils.validation.file_validation.get_file_signature')
    def test_get_mime_type_from_buffer_unknown(self, mock_get_file_signature, mock_guess_type):
        """Test get_mime_type_from_buffer with unknown content."""
        # Setup mocks
        mock_guess_type.return_value = (None, None)
        mock_get_file_signature.return_value = None

        # Test with unknown content
        result = get_mime_type_from_buffer(self.invalid_pdf_content)
        self.assertEqual(result, "application/octet-stream")

    def test_sanitize_filename_positive(self):
        """Test sanitize_filename with valid filenames."""
        # Test with normal filename
        result = sanitize_filename("document.pdf")
        self.assertEqual(result, "document.pdf")

        # Test with filename containing spaces
        result = sanitize_filename("my document.pdf")
        self.assertEqual(result, "my document.pdf")

    def test_sanitize_filename_negative(self):
        """Test sanitize_filename with problematic filenames."""
        # Test with empty filename
        result = sanitize_filename("")
        self.assertEqual(result, "unnamed_file")

        # Test with path traversal attempt
        result = sanitize_filename("../../../etc/passwd")
        # each "../" becomes "..", so we get "......etcpasswd"
        self.assertEqual(result, "......etcpasswd")

        # Test with null bytes
        result = sanitize_filename("malicious\x00.pdf")
        self.assertEqual(result, "malicious.pdf")

        # Test with control characters
        result = sanitize_filename("bad\x01file\x1F.pdf")
        self.assertEqual(result, "badfile.pdf")

        # Test with command injection characters
        result = sanitize_filename("file;rm -rf /.pdf")
        self.assertEqual(result, "filerm -rf .pdf")

        # Test with very long filename
        long_name = "a" * 300 + ".pdf"
        result = sanitize_filename(long_name)
        self.assertLessEqual(len(result), 255)

    @patch('os.environ.get')
    def test_sanitize_filename_with_randomization(self, mock_environ_get):
        """Test sanitize_filename with randomization enabled."""
        # Setup mock to enable randomization
        mock_environ_get.return_value = "true"

        # Test with randomization enabled
        result = sanitize_filename("document.pdf")

        # Verify result contains original name plus random suffix
        self.assertIn("document_", result)
        self.assertTrue(result.endswith(".pdf"))
        self.assertGreater(len(result), len("document.pdf"))

    @patch('backend.app.utils.constant.constant.ALLOWED_MIME_TYPES', {"pdf": {"application/pdf", "application/x-pdf"}})
    def test_validate_mime_type_positive(self):
        """Test validate_mime_type with valid MIME types."""
        # Test with valid MIME type
        result = validate_mime_type("application/pdf")
        self.assertTrue(result)

        # Test with valid MIME type with parameters
        result = validate_mime_type("application/pdf; charset=utf-8")
        self.assertTrue(result)

        # Test with custom allowed types
        result = validate_mime_type("image/jpeg", ["image/jpeg", "image/png"])
        self.assertTrue(result)

    @patch('backend.app.utils.constant.constant.ALLOWED_MIME_TYPES', {"pdf": {"application/pdf", "application/x-pdf"}})
    def test_validate_mime_type_negative(self):
        """Test validate_mime_type with invalid MIME types."""
        # Test with invalid MIME type
        result = validate_mime_type("image/jpeg")
        self.assertFalse(result)

        # Test with empty MIME type
        result = validate_mime_type("")
        self.assertFalse(result)

        # Test with None MIME type
        result = validate_mime_type(None)
        self.assertFalse(result)

    def test_validate_pdf_file_positive(self):
        """Test validate_pdf_file with valid PDF content."""
        # Test with valid PDF content
        result = validate_pdf_file(self.valid_pdf_content)
        self.assertTrue(result)

    def test_validate_pdf_file_negative(self):
        """Test validate_pdf_file with invalid PDF content."""
        # Test with invalid PDF content
        result = validate_pdf_file(self.invalid_pdf_content)
        self.assertFalse(result)

        # Test with empty content
        result = validate_pdf_file(b"")
        self.assertFalse(result)

        # Test with invalid PDF version
        result = validate_pdf_file(b"%PDF-10.0\n")
        self.assertFalse(result)

        # Test with malformed PDF header
        result = validate_pdf_file(b"%PDF-\n")
        self.assertFalse(result)

    @patch('os.environ.get')
    @patch('backend.app.utils.validation.file_validation._logger')
    def test_check_pdf_javascript_blocking_enabled(self, mock_logger, mock_environ_get):
        """Test _check_pdf_javascript with JavaScript blocking enabled."""
        # Setup mock to enable JavaScript blocking
        mock_environ_get.return_value = "true"

        # Test with PDF containing JavaScript
        is_safe, reason = _check_pdf_javascript(self.pdf_with_js, "test.pdf")

        # Verify result
        self.assertFalse(is_safe)
        self.assertEqual(reason, "PDF contains JavaScript, which is not allowed")

        # Verify logger was not called (blocking takes precedence)
        mock_logger.warning.assert_not_called()

    @patch('os.environ.get')
    @patch('backend.app.utils.validation.file_validation._logger')
    def test_check_pdf_javascript_blocking_disabled(self, mock_logger, mock_environ_get):
        """Test _check_pdf_javascript with JavaScript blocking disabled."""
        # Setup mock to disable JavaScript blocking
        mock_environ_get.return_value = "false"

        # Test with PDF containing JavaScript
        is_safe, reason = _check_pdf_javascript(self.pdf_with_js, "test.pdf")

        # Verify result
        self.assertTrue(is_safe)
        self.assertEqual(reason, "")

        # Verify logger was called with warning
        mock_logger.warning.assert_called_once_with("PDF contains JavaScript: %s", "test.pdf")

    @patch('backend.app.utils.validation.file_validation._logger')
    def test_check_pdf_acroform(self, mock_logger):
        """Test _check_pdf_acroform."""
        # Test with PDF containing AcroForm
        _check_pdf_acroform(self.pdf_with_acroform, "test.pdf")

        # Verify logger was called with warning
        mock_logger.warning.assert_called_once_with("PDF contains AcroForm: %s", "test.pdf")

        # Reset mock
        mock_logger.reset_mock()

        # Test with PDF not containing AcroForm
        _check_pdf_acroform(self.valid_pdf_content, "test.pdf")

        # Verify logger was not called
        mock_logger.warning.assert_not_called()

    @patch('backend.app.utils.validation.file_validation.get_file_signature')
    @patch('backend.app.utils.validation.file_validation._check_pdf_javascript')
    @patch('backend.app.utils.validation.file_validation._check_pdf_acroform')
    def test_validate_file_safety_positive(self, mock_check_acroform, mock_check_javascript, mock_get_file_signature):
        """Test validate_file_safety with safe PDF."""
        # Setup mocks
        mock_get_file_signature.return_value = "pdf"
        mock_check_javascript.return_value = (True, "")

        # Test with safe PDF
        is_safe, reason = validate_file_safety(self.valid_pdf_content, "test.pdf")

        # Verify result
        self.assertTrue(is_safe)
        self.assertEqual(reason, "")

        # Verify mocks were called
        mock_get_file_signature.assert_called_once()
        mock_check_javascript.assert_called_once()
        mock_check_acroform.assert_called_once()

    @patch('backend.app.utils.validation.file_validation.get_file_signature')
    @patch('backend.app.utils.validation.file_validation._check_pdf_javascript')
    def test_validate_file_safety_not_pdf(self, mock_check_javascript, mock_get_file_signature):
        """Test validate_file_safety with non-PDF file."""
        # Setup mock
        mock_get_file_signature.return_value = "jpg"

        # Test with non-PDF file
        is_safe, reason = validate_file_safety(self.invalid_pdf_content, "test.jpg")

        # Verify result
        self.assertFalse(is_safe)
        self.assertEqual(reason, "Only PDF files are allowed")

        # Verify JavaScript check was not called
        mock_check_javascript.assert_not_called()

    @patch('backend.app.utils.validation.file_validation.get_file_signature')
    @patch('backend.app.utils.validation.file_validation._check_pdf_javascript')
    @patch('backend.app.utils.validation.file_validation._check_pdf_acroform')
    @patch('backend.app.utils.validation.file_validation._logger')
    def test_validate_file_safety_acroform_exception(self, mock_logger, mock_check_acroform,
                                                     mock_check_javascript, mock_get_file_signature):
        """Test validate_file_safety with exception in _check_pdf_acroform."""
        # Setup mocks
        mock_get_file_signature.return_value = "pdf"
        mock_check_javascript.return_value = (True, "")
        mock_check_acroform.side_effect = Exception("Test exception")

        # Test with exception in _check_pdf_acroform
        is_safe, reason = validate_file_safety(self.valid_pdf_content, "test.pdf")

        # Verify result (should still be safe despite exception)
        self.assertTrue(is_safe)
        self.assertEqual(reason, "")

        # Verify logger was called with warning
        mock_logger.warning.assert_called_once()

    @patch('backend.app.utils.validation.file_validation.get_mime_type_from_buffer', return_value="application/pdf")
    @patch('backend.app.utils.validation.file_validation.ALLOWED_MIME_TYPES', {"pdf": {"application/pdf"}})
    @patch('backend.app.utils.validation.file_validation.validate_pdf_file', return_value=True)
    @patch('backend.app.utils.validation.file_validation.validate_file_safety', return_value=(True, ""))
    def test_validate_file_content_success(self,
                                           mock_safety,
                                           mock_pdf,
                                           mock_mime):
        """validate_file_content returns True for a perfectly valid PDF."""
        content = self.valid_pdf_content
        ok, reason, dm = validate_file_content(content, "foo.pdf", "application/pdf")

        self.assertTrue(ok)
        self.assertEqual(reason, "")
        self.assertEqual(dm, "application/pdf")

    def test_validate_file_content_empty(self):
        """validate_file_content should reject empty content."""
        ok, reason, dm = validate_file_content(b"", "foo.pdf", "application/pdf")

        self.assertFalse(ok)
        self.assertEqual(reason, "Empty file content")
        self.assertIsNone(dm)

    @patch('backend.app.utils.validation.file_validation.get_mime_type_from_buffer', return_value="application/pdf")
    def test_validate_file_content_mismatch(self, mock_mime):
        """validate_file_content should reject mismatched provided vs detected MIME."""
        ok, reason, dm = validate_file_content(self.valid_pdf_content, "foo.pdf", "image/png")

        self.assertFalse(ok)
        self.assertIn("Content type mismatch", reason)
        self.assertEqual(dm, "application/pdf")

    @patch('backend.app.utils.validation.file_validation.get_mime_type_from_buffer', return_value="application/zip")
    @patch('backend.app.utils.validation.file_validation.ALLOWED_MIME_TYPES', {"pdf": {"application/pdf"}})
    def test_validate_file_content_not_allowed(self, mock_get_mime):
        """validate_file_content should reject disallowed MIME types."""
        ok, reason, dm = validate_file_content(self.valid_pdf_content, "foo.zip", None)

        self.assertFalse(ok)
        self.assertIn("Only PDF files are allowed", reason)
        self.assertEqual(dm, "application/zip")

    @patch('backend.app.utils.validation.file_validation.get_mime_type_from_buffer', return_value="application/pdf")
    @patch('backend.app.utils.validation.file_validation.validate_pdf_file', return_value=False)
    def test_validate_file_content_bad_structure(self, mock_pdf, mock_mime):
        """validate_file_content should reject structurally invalid PDFs."""
        ok, reason, dm = validate_file_content(self.valid_pdf_content, None, None)
        self.assertFalse(ok)
        self.assertEqual(reason, "Invalid PDF file structure")

    @patch('backend.app.utils.validation.file_validation.get_mime_type_from_buffer', return_value="application/pdf")
    @patch('backend.app.utils.validation.file_validation.validate_pdf_file', return_value=True)
    @patch('backend.app.utils.validation.file_validation.validate_file_safety', return_value=(False, "Bad JS"))
    def test_validate_file_content_unsafe(self, mock_safety, mock_pdf, mock_mime):
        """validate_file_content should reject unsafe PDFs."""
        ok, reason, dm = validate_file_content(self.pdf_with_js, None, None)

        self.assertFalse(ok)
        self.assertEqual(reason, "Bad JS")
        self.assertEqual(dm, "application/pdf")

    def test_validate_file_content_async_success(self):
        """validate_file_content_async should mirror the sync result."""
        coro = validate_file_content_async(self.valid_pdf_content, "foo.pdf", "application/pdf")
        ok, reason, dm = asyncio.run(coro)

        self.assertTrue(ok)
        self.assertEqual(reason, "")
        self.assertEqual(dm, "application/pdf")

    @patch('backend.app.utils.validation.file_validation._logger')
    @patch('asyncio.to_thread', side_effect=Exception("fail"))
    def test_validate_file_content_async_error(self, mock_thread, mock_logger):
        """validate_file_content_async should catch exceptions and return the error tuple."""
        ok, reason, dm = asyncio.run(validate_file_content_async(self.valid_pdf_content, None, None))

        self.assertFalse(ok)
        self.assertEqual(reason, "Async validation error")
        self.assertIsNone(dm)
        mock_logger.warning.assert_called_once()

    class DummyUpload:
        def __init__(self, content, content_type, filename):
            self._content = content
            self.content_type = content_type
            self.filename = filename

        async def read(self):
            return self._content

    @patch('backend.app.utils.validation.file_validation.validate_mime_type', return_value=False)
    @patch('backend.app.utils.logging.logger.log_warning')
    async def test_read_and_validate_file_bad_mime(self, mock_validate_mime, mock_warn):
        """Unsupported MIME → 415 + warning."""
        dummy = self.DummyUpload(b"pdfdata", "image/png", "foo.png")
        content, resp, t = await read_and_validate_file(dummy, "op1")

        self.assertIsNone(content)
        self.assertIsInstance(resp, JSONResponse)
        self.assertEqual(resp.status_code, 415)
        self.assertEqual(t, 0)
        mock_warn.assert_called_once()

    @patch('backend.app.utils.validation.file_validation.validate_mime_type', return_value=True)
    @patch('backend.app.utils.validation.file_validation.validate_file_content_async',
           return_value=(True, "", "application/pdf"))
    @patch('backend.app.utils.validation.file_validation.MAX_PDF_SIZE_BYTES', 5)
    @patch('backend.app.utils.validation.file_validation.log_info')
    @patch('backend.app.utils.validation.file_validation.log_warning')
    async def test_read_and_validate_file_success_and_too_large(self,
                                                                mock_warn,
                                                                mock_info,
                                                                mock_validate_async,
                                                                mock_validate_mime):
        """Small file ok; oversize → 413 + warning."""
        # small is under 5 bytes, so first call returns content
        small = self.DummyUpload(b"a" * 3, "application/pdf", "foo.pdf")
        content, resp, t = await read_and_validate_file(small, "op2")
        self.assertEqual(content, b"a" * 3)
        self.assertIsNone(resp)
        self.assertGreaterEqual(t, 0)

        # now oversize
        large = self.DummyUpload(b"a" * 6, "application/pdf", "foo.pdf")
        content2, resp2, t2 = await read_and_validate_file(large, "op2")
        self.assertIsNone(content2)
        self.assertEqual(resp2.status_code, 413)
        mock_warn.assert_called()

    @patch('backend.app.utils.validation.file_validation.validate_mime_type', side_effect=Exception("boom"))
    @patch('backend.app.utils.logging.logger.log_warning')
    async def test_read_and_validate_file_exception(self, mock_validate_mime, mock_warn):
        """Exception in mime‐check → 500 + warning."""
        dummy = self.DummyUpload(b"", "application/pdf", "foo.pdf")
        content, resp, t = await read_and_validate_file(dummy, "op3")
        self.assertIsNone(content)
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(t, 0)
        mock_warn.assert_called_once()

    @patch('backend.app.utils.validation.file_validation.validate_mime_type', return_value=True)
    @patch('backend.app.utils.validation.file_validation.MAX_PDF_SIZE_BYTES', 1024 * 1024 * 10)
    @patch('backend.app.utils.validation.file_validation.validate_file_content_async',
           return_value=(False, "Bad PDF content", "application/pdf"))
    @patch('backend.app.utils.validation.file_validation.log_warning')
    async def test_read_and_validate_file_content_invalid(self,
                                                          mock_warn,
                                                          mock_validate_async,
                                                          mock_validate_mime):
        """Async content invalid → 415 + warning + reason in body."""
        dummy = self.DummyUpload(b"%PDF-1.5 dummy", "application/pdf", "doc.pdf")
        content, resp, read_time = await read_and_validate_file(dummy, "op_badcontent")

        self.assertIsNone(content)
        self.assertIsInstance(resp, JSONResponse)
        self.assertEqual(resp.status_code, 415)
        self.assertIn(b"Bad PDF content", resp.body)
        self.assertGreaterEqual(read_time, 0)

        # Now this will catch the call to the local log_warning
        mock_warn.assert_called_once()

    @patch('backend.app.utils.validation.file_validation.validate_mime_type', return_value=True)
    @patch('backend.app.utils.validation.file_validation.MAX_PDF_SIZE_BYTES', 1024 * 1024 * 10)
    @patch('backend.app.utils.validation.file_validation.validate_file_content_async',
           return_value=(True, "", "application/pdf"))
    @patch('backend.app.utils.validation.file_validation.log_info')
    async def test_read_and_validate_file_full_success(self,
                                                       mock_info,
                                                       mock_validate_async,
                                                       mock_validate_mime):
        """All checks pass → return bytes + log_info."""
        payload = b"%PDF-1.5 perfectly fine"
        dummy = self.DummyUpload(payload, "application/pdf", "ok.pdf")
        content, resp, read_time = await read_and_validate_file(dummy, "op_success")

        self.assertEqual(content, payload)
        self.assertIsNone(resp)
        self.assertGreaterEqual(read_time, 0)
        mock_info.assert_called()
