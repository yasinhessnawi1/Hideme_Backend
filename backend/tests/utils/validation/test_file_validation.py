import asyncio
import io
import unittest
from unittest.mock import patch
from fastapi.responses import JSONResponse

from backend.app.utils.validation.file_validation import (
    get_file_signature,
    get_mime_type_from_buffer,
    sanitize_filename,
    validate_mime_type,
    validate_pdf_file,
    _check_pdf_javascript,
    _check_pdf_acroform,
    validate_file_safety,
    validate_file_content,
    validate_file_content_async,
    read_and_validate_file,
)


# Tests for file validation utilities
class TestFileValidation(unittest.IsolatedAsyncioTestCase):

    # Setup sample PDF and configuration data
    def setUp(self):
        self.valid_pdf_content = b"%PDF-1.5\n% Some PDF content"

        self.invalid_pdf_content = b"Not a PDF file"

        self.pdf_with_js = b"%PDF-1.5\n/JavaScript /JS Some JavaScript content"

        self.pdf_with_acroform = b"%PDF-1.5\n/AcroForm Some AcroForm content"

        self.mock_file_signatures = {
            "pdf": [(b"%PDF", 0)],
            "jpg": [(b"\xff\xd8\xff", 0)],
            "png": [(b"\x89PNG\r\n\x1a\n", 0)],
        }

        self.mock_allowed_mime_types = {"pdf": {"application/pdf", "application/x-pdf"}}

        self.mock_extension_to_mime = {
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".png": "image/png",
        }

        self.mock_application_word = "application/pdf"

        self.mock_max_pdf_size = 10 * 1024 * 1024

    # Tear down any resources
    async def asyncTearDown(self):
        pass

    # Test get_file_signature with valid signature
    @patch(
        "backend.app.utils.constant.constant.FILE_SIGNATURES", {"pdf": [(b"%PDF", 0)]}
    )
    def test_get_file_signature_positive(self):
        result = get_file_signature(self.valid_pdf_content)

        self.assertEqual(result, "pdf")

    # Test get_file_signature returns None on invalid data
    @patch(
        "backend.app.utils.constant.constant.FILE_SIGNATURES", {"pdf": [(b"%PDF", 0)]}
    )
    def test_get_file_signature_negative(self):
        result = get_file_signature(self.invalid_pdf_content)

        self.assertIsNone(result)

        result = get_file_signature(b"")

        self.assertIsNone(result)

        result = get_file_signature(b"123")

        self.assertIsNone(result)

    # Test get_mime_type_from_buffer uses extension mapping
    @patch(
        "backend.app.utils.constant.constant.EXTENSION_TO_MIME",
        {".pdf": "application/pdf"},
    )
    @patch("backend.app.utils.constant.constant.APPLICATION_WORD", "application/pdf")
    @patch("backend.app.utils.validation.file_validation.get_file_signature")
    def test_get_mime_type_from_buffer_with_filename(self, mock_get_file_signature):
        mock_get_file_signature.return_value = "pdf"

        result = get_mime_type_from_buffer(self.valid_pdf_content, "document.pdf")

        self.assertEqual(result, "application/pdf")

        mock_get_file_signature.assert_not_called()

    @patch("backend.app.utils.validation.file_validation.EXTENSION_TO_MIME", {})
    @patch("mimetypes.guess_type")
    @patch("backend.app.utils.validation.file_validation.get_file_signature")
    def test_get_mime_type_from_buffer_with_mimetypes(
        self, mock_get_file_signature, mock_guess_type
    ):
        mock_guess_type.return_value = ("application/pdf", None)

        mock_get_file_signature.return_value = None

        result = get_mime_type_from_buffer(self.valid_pdf_content, "document.pdf")

        self.assertEqual(result, "application/pdf")

        mock_guess_type.assert_called_once_with("document.pdf")

    # Test get_mime_type_from_buffer inspects content when needed
    @patch("backend.app.utils.constant.constant.EXTENSION_TO_MIME", {})
    @patch("mimetypes.guess_type")
    @patch("backend.app.utils.validation.file_validation.get_file_signature")
    @patch("backend.app.utils.constant.constant.APPLICATION_WORD", "application/pdf")
    def test_get_mime_type_from_buffer_with_content(
        self, mock_get_file_signature, mock_guess_type
    ):
        mock_guess_type.return_value = (None, None)

        mock_get_file_signature.return_value = "pdf"

        result = get_mime_type_from_buffer(self.valid_pdf_content)

        self.assertEqual(result, "application/pdf")

        mock_get_file_signature.assert_called_once()

        mock_get_file_signature.reset_mock()

        file_obj = io.BytesIO(self.valid_pdf_content)

        result = get_mime_type_from_buffer(file_obj)

        self.assertEqual(result, "application/pdf")

        mock_get_file_signature.assert_called_once()

        self.assertEqual(file_obj.tell(), 0)

    # Test get_mime_type_from_buffer defaults unknown to octet-stream
    @patch("backend.app.utils.constant.constant.EXTENSION_TO_MIME", {})
    @patch("mimetypes.guess_type")
    @patch("backend.app.utils.validation.file_validation.get_file_signature")
    def test_get_mime_type_from_buffer_unknown(
        self, mock_get_file_signature, mock_guess_type
    ):
        mock_guess_type.return_value = (None, None)

        mock_get_file_signature.return_value = None

        result = get_mime_type_from_buffer(self.invalid_pdf_content)

        self.assertEqual(result, "application/octet-stream")

    # Test sanitize_filename returns safe names
    def test_sanitize_filename_positive(self):
        result = sanitize_filename("document.pdf")

        self.assertEqual(result, "document.pdf")

        result = sanitize_filename("my document.pdf")

        self.assertEqual(result, "my document.pdf")

    # Test sanitize_filename handles malicious inputs
    def test_sanitize_filename_negative(self):
        result = sanitize_filename("")

        self.assertEqual(result, "unnamed_file")

        result = sanitize_filename("../../../etc/passwd")

        self.assertEqual(result, "......etcpasswd")

        result = sanitize_filename("malicious\x00.pdf")

        self.assertEqual(result, "malicious.pdf")

        result = sanitize_filename("bad\x01file\x1f.pdf")

        self.assertEqual(result, "badfile.pdf")

        result = sanitize_filename("file;rm -rf /.pdf")

        self.assertEqual(result, "filerm -rf .pdf")

        long_name = "a" * 300 + ".pdf"

        result = sanitize_filename(long_name)

        self.assertLessEqual(len(result), 255)

    # Test sanitize_filename adds randomness when enabled
    @patch("os.environ.get")
    def test_sanitize_filename_with_randomization(self, mock_environ_get):
        mock_environ_get.return_value = "true"

        result = sanitize_filename("document.pdf")

        self.assertIn("document_", result)

        self.assertTrue(result.endswith(".pdf"))

        self.assertGreater(len(result), len("document.pdf"))

    # Test validate_mime_type accepts allowed types
    @patch(
        "backend.app.utils.constant.constant.ALLOWED_MIME_TYPES",
        {"pdf": {"application/pdf", "application/x-pdf"}},
    )
    def test_validate_mime_type_positive(self):
        result = validate_mime_type("application/pdf")

        self.assertTrue(result)

        result = validate_mime_type("application/pdf; charset=utf-8")

        self.assertTrue(result)

        result = validate_mime_type("image/jpeg", ["image/jpeg", "image/png"])

        self.assertTrue(result)

    # Test validate_mime_type rejects invalid types
    @patch(
        "backend.app.utils.constant.constant.ALLOWED_MIME_TYPES",
        {"pdf": {"application/pdf", "application/x-pdf"}},
    )
    def test_validate_mime_type_negative(self):
        result = validate_mime_type("image/jpeg")

        self.assertFalse(result)

        result = validate_mime_type("")

        self.assertFalse(result)

        result = validate_mime_type(None)

        self.assertFalse(result)

    # Test validate_pdf_file identifies valid PDFs
    def test_validate_pdf_file_positive(self):
        result = validate_pdf_file(self.valid_pdf_content)

        self.assertTrue(result)

    # Test validate_pdf_file rejects malformed PDFs
    def test_validate_pdf_file_negative(self):
        result = validate_pdf_file(self.invalid_pdf_content)

        self.assertFalse(result)

        result = validate_pdf_file(b"")

        self.assertFalse(result)

        result = validate_pdf_file(b"%PDF-10.0\n")

        self.assertFalse(result)

        result = validate_pdf_file(b"%PDF-\n")

        self.assertFalse(result)

    # Test _check_pdf_javascript blocks or warns based on config
    @patch("os.environ.get")
    @patch("backend.app.utils.validation.file_validation._logger")
    def test_check_pdf_javascript_blocking_enabled(self, mock_logger, mock_environ_get):
        mock_environ_get.return_value = "true"

        is_safe, reason = _check_pdf_javascript(self.pdf_with_js, "test.pdf")

        self.assertFalse(is_safe)

        self.assertEqual(reason, "PDF contains JavaScript, which is not allowed")

        mock_logger.warning.assert_not_called()

    # Test _check_pdf_javascript warns when blocking disabled
    @patch("os.environ.get")
    @patch("backend.app.utils.validation.file_validation._logger")
    def test_check_pdf_javascript_blocking_disabled(
        self, mock_logger, mock_environ_get
    ):
        mock_environ_get.return_value = "false"

        is_safe, reason = _check_pdf_javascript(self.pdf_with_js, "test.pdf")

        self.assertTrue(is_safe)

        self.assertEqual(reason, "")

        mock_logger.warning.assert_called_once_with(
            "PDF contains JavaScript: %s", "test.pdf"
        )

    # Test _check_pdf_acroform logs warning if present
    @patch("backend.app.utils.validation.file_validation._logger")
    def test_check_pdf_acroform(self, mock_logger):
        _check_pdf_acroform(self.pdf_with_acroform, "test.pdf")

        mock_logger.warning.assert_called_once_with(
            "PDF contains AcroForm: %s", "test.pdf"
        )

        mock_logger.reset_mock()

        _check_pdf_acroform(self.valid_pdf_content, "test.pdf")

        mock_logger.warning.assert_not_called()

    # Test validate_file_safety positive PDF case
    @patch("backend.app.utils.validation.file_validation.get_file_signature")
    @patch("backend.app.utils.validation.file_validation._check_pdf_javascript")
    @patch("backend.app.utils.validation.file_validation._check_pdf_acroform")
    def test_validate_file_safety_positive(
        self, mock_check_acroform, mock_check_javascript, mock_get_file_signature
    ):
        mock_get_file_signature.return_value = "pdf"

        mock_check_javascript.return_value = (True, "")

        is_safe, reason = validate_file_safety(self.valid_pdf_content, "test.pdf")

        self.assertTrue(is_safe)

        self.assertEqual(reason, "")

        mock_get_file_signature.assert_called_once()

        mock_check_javascript.assert_called_once()

        mock_check_acroform.assert_called_once()

    # Test validate_file_safety rejects non-PDF
    @patch("backend.app.utils.validation.file_validation.get_file_signature")
    @patch("backend.app.utils.validation.file_validation._check_pdf_javascript")
    def test_validate_file_safety_not_pdf(
        self, mock_check_javascript, mock_get_file_signature
    ):
        mock_get_file_signature.return_value = "jpg"

        is_safe, reason = validate_file_safety(self.invalid_pdf_content, "test.jpg")

        self.assertFalse(is_safe)

        self.assertEqual(reason, "Only PDF files are allowed")

        mock_check_javascript.assert_not_called()

    # Test validate_file_safety handles AcroForm exceptions
    @patch("backend.app.utils.validation.file_validation.get_file_signature")
    @patch("backend.app.utils.validation.file_validation._check_pdf_javascript")
    @patch("backend.app.utils.validation.file_validation._check_pdf_acroform")
    @patch("backend.app.utils.validation.file_validation._logger")
    def test_validate_file_safety_acroform_exception(
        self,
        mock_logger,
        mock_check_acroform,
        mock_check_javascript,
        mock_get_file_signature,
    ):
        mock_get_file_signature.return_value = "pdf"

        mock_check_javascript.return_value = (True, "")

        mock_check_acroform.side_effect = Exception("Test exception")

        is_safe, reason = validate_file_safety(self.valid_pdf_content, "test.pdf")

        self.assertTrue(is_safe)

        self.assertEqual(reason, "")

        mock_logger.warning.assert_called_once()

    # Test validate_file_content success path
    @patch(
        "backend.app.utils.validation.file_validation.get_mime_type_from_buffer",
        return_value="application/pdf",
    )
    @patch(
        "backend.app.utils.validation.file_validation.ALLOWED_MIME_TYPES",
        {"pdf": {"application/pdf"}},
    )
    @patch(
        "backend.app.utils.validation.file_validation.validate_pdf_file",
        return_value=True,
    )
    @patch(
        "backend.app.utils.validation.file_validation.validate_file_safety",
        return_value=(True, ""),
    )
    def test_validate_file_content_success(self, mock_safety, mock_pdf, mock_mime):
        content = self.valid_pdf_content

        ok, reason, dm = validate_file_content(content, "foo.pdf", "application/pdf")

        self.assertTrue(ok)

        self.assertEqual(reason, "")

        self.assertEqual(dm, "application/pdf")

    # Test validate_file_content rejects empty
    def test_validate_file_content_empty(self):
        ok, reason, dm = validate_file_content(b"", "foo.pdf", "application/pdf")

        self.assertFalse(ok)

        self.assertEqual(reason, "Empty file content")

        self.assertIsNone(dm)

    # Test validate_file_content detects MIME mismatch
    @patch(
        "backend.app.utils.validation.file_validation.get_mime_type_from_buffer",
        return_value="application/pdf",
    )
    def test_validate_file_content_mismatch(self, mock_mime):
        ok, reason, dm = validate_file_content(
            self.valid_pdf_content, "foo.pdf", "image/png"
        )

        self.assertFalse(ok)

        self.assertIn("Only PDF files are allowed", reason)

        self.assertIn("image/png", reason)

        self.assertIn("application/pdf", reason)

        self.assertEqual(dm, "application/pdf")

    # Test validate_file_content rejects disallowed MIME
    @patch(
        "backend.app.utils.validation.file_validation.get_mime_type_from_buffer",
        return_value="application/zip",
    )
    @patch(
        "backend.app.utils.validation.file_validation.ALLOWED_MIME_TYPES",
        {"pdf": {"application/pdf"}},
    )
    def test_validate_file_content_not_allowed(self, mock_get_mime):
        ok, reason, dm = validate_file_content(self.valid_pdf_content, "foo.zip", None)

        self.assertFalse(ok)

        self.assertIn("Only PDF files are allowed", reason)

        self.assertEqual(dm, "application/zip")

    # Test validate_file_content rejects structurally invalid PDFs
    @patch(
        "backend.app.utils.validation.file_validation.get_mime_type_from_buffer",
        return_value="application/pdf",
    )
    @patch(
        "backend.app.utils.validation.file_validation.validate_pdf_file",
        return_value=False,
    )
    def test_validate_file_content_bad_structure(self, mock_pdf, mock_mime):
        ok, reason, dm = validate_file_content(self.valid_pdf_content, None, None)

        self.assertFalse(ok)

        self.assertEqual(reason, "Invalid PDF file structure")

    # Test validate_file_content rejects unsafe PDFs
    @patch(
        "backend.app.utils.validation.file_validation.get_mime_type_from_buffer",
        return_value="application/pdf",
    )
    @patch(
        "backend.app.utils.validation.file_validation.validate_pdf_file",
        return_value=True,
    )
    @patch(
        "backend.app.utils.validation.file_validation.validate_file_safety",
        return_value=(False, "Bad JS"),
    )
    def test_validate_file_content_unsafe(self, mock_safety, mock_pdf, mock_mime):
        ok, reason, dm = validate_file_content(self.pdf_with_js, None, None)

        self.assertFalse(ok)

        self.assertEqual(reason, "Bad JS")

        self.assertEqual(dm, "application/pdf")

    # Test validate_file_content_async mirrors sync behavior
    def test_validate_file_content_async_success(self):
        coro = validate_file_content_async(
            self.valid_pdf_content, "foo.pdf", "application/pdf"
        )

        ok, reason, dm = asyncio.run(coro)

        self.assertTrue(ok)

        self.assertEqual(reason, "")

        self.assertEqual(dm, "application/pdf")

    # Test validate_file_content_async catches exceptions
    @patch("backend.app.utils.validation.file_validation._logger")
    @patch("asyncio.to_thread", side_effect=Exception("fail"))
    def test_validate_file_content_async_error(self, mock_thread, mock_logger):
        ok, reason, dm = asyncio.run(
            validate_file_content_async(self.valid_pdf_content, None, None)
        )

        self.assertFalse(ok)

        self.assertEqual(reason, "Async validation error")

        self.assertIsNone(dm)

        mock_logger.warning.assert_called_once()

    # Dummy upload class for testing read_and_validate_file
    class DummyUpload:

        def __init__(self, content, content_type, filename):
            self._content = content

            self.content_type = content_type

            self.filename = filename

        async def read(self):
            return self._content

    # Test read_and_validate_file rejects bad MIME
    @patch(
        "backend.app.utils.validation.file_validation.validate_mime_type",
        return_value=False,
    )
    @patch("backend.app.utils.logging.logger.log_warning")
    async def test_read_and_validate_file_bad_mime(self, mock_validate_mime, mock_warn):
        dummy = self.DummyUpload(b"pdfdata", "image/png", "foo.png")

        content, resp, t = await read_and_validate_file(dummy, "op1")

        self.assertIsNone(content)

        self.assertIsInstance(resp, JSONResponse)

        self.assertEqual(resp.status_code, 415)

        self.assertEqual(t, 0)

        mock_warn.assert_called_once()

    # Test read_and_validate_file handles size limits and success
    @patch(
        "backend.app.utils.validation.file_validation.validate_mime_type",
        return_value=True,
    )
    @patch(
        "backend.app.utils.validation.file_validation.validate_file_content_async",
        return_value=(True, "", "application/pdf"),
    )
    @patch("backend.app.utils.validation.file_validation.MAX_PDF_SIZE_BYTES", 5)
    @patch("backend.app.utils.validation.file_validation.log_info")
    @patch("backend.app.utils.validation.file_validation.log_warning")
    async def test_read_and_validate_file_success_and_too_large(
        self, mock_warn, mock_info, mock_validate_async, mock_validate_mime
    ):
        small = self.DummyUpload(b"a" * 3, "application/pdf", "foo.pdf")

        content, resp, t = await read_and_validate_file(small, "op2")

        self.assertEqual(content, b"a" * 3)

        self.assertIsNone(resp)

        self.assertGreaterEqual(t, 0)

        large = self.DummyUpload(b"a" * 6, "application/pdf", "foo.pdf")

        content2, resp2, t2 = await read_and_validate_file(large, "op2")

        self.assertIsNone(content2)

        self.assertEqual(resp2.status_code, 413)

        mock_warn.assert_called()

    # Test read_and_validate_file handles exceptions in mime check
    @patch(
        "backend.app.utils.validation.file_validation.validate_mime_type",
        side_effect=Exception("boom"),
    )
    @patch("backend.app.utils.logging.logger.log_warning")
    async def test_read_and_validate_file_exception(
        self, mock_validate_mime, mock_warn
    ):
        dummy = self.DummyUpload(b"", "application/pdf", "foo.pdf")

        content, resp, t = await read_and_validate_file(dummy, "op3")

        self.assertIsNone(content)

        self.assertEqual(resp.status_code, 500)

        self.assertEqual(t, 0)

        mock_warn.assert_called_once()

    # Test read_and_validate_file rejects invalid content
    @patch(
        "backend.app.utils.validation.file_validation.validate_mime_type",
        return_value=True,
    )
    @patch(
        "backend.app.utils.validation.file_validation.MAX_PDF_SIZE_BYTES",
        1024 * 1024 * 10,
    )
    @patch(
        "backend.app.utils.validation.file_validation.validate_file_content_async",
        return_value=(False, "Bad PDF content", "application/pdf"),
    )
    @patch("backend.app.utils.validation.file_validation.log_warning")
    async def test_read_and_validate_file_content_invalid(
        self, mock_warn, mock_validate_async, mock_validate_mime
    ):
        dummy = self.DummyUpload(b"%PDF-1.5 dummy", "application/pdf", "doc.pdf")

        content, resp, read_time = await read_and_validate_file(dummy, "op_badcontent")

        self.assertIsNone(content)

        self.assertIsInstance(resp, JSONResponse)

        self.assertEqual(resp.status_code, 415)

        self.assertIn(b"Bad PDF content", resp.body)

        self.assertGreaterEqual(read_time, 0)

        mock_warn.assert_called_once()

    # Test read_and_validate_file full success path
    @patch(
        "backend.app.utils.validation.file_validation.validate_mime_type",
        return_value=True,
    )
    @patch(
        "backend.app.utils.validation.file_validation.MAX_PDF_SIZE_BYTES",
        1024 * 1024 * 10,
    )
    @patch(
        "backend.app.utils.validation.file_validation.validate_file_content_async",
        return_value=(True, "", "application/pdf"),
    )
    @patch("backend.app.utils.validation.file_validation.log_info")
    async def test_read_and_validate_file_full_success(
        self, mock_info, mock_validate_async, mock_validate_mime
    ):
        payload = b"%PDF-1.5 perfectly fine"

        dummy = self.DummyUpload(payload, "application/pdf", "ok.pdf")

        content, resp, read_time = await read_and_validate_file(dummy, "op_success")

        self.assertEqual(content, payload)

        self.assertIsNone(resp)

        self.assertGreaterEqual(read_time, 0)

        mock_info.assert_called()
