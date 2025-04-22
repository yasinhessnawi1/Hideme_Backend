import os
from unittest.mock import patch
import pymupdf
import pytest

from backend.app.document_processing.pdf_extractor import PDFTextExtractor


@pytest.fixture
def valid_pdf_bytes():
    """Generate a PDF with 15 pages (pages 3 and 7 empty) and add basic metadata."""

    doc = pymupdf.open()

    doc.metadata = {
        "title": "Sample PDF",
        "author": "Test Author",
        "subject": "Testing Metadata",
        "keywords": "PDF, Test, Metadata",
        "producer": "PyMuPDF",
        "creator": "PyMuPDF"
    }

    for i in range(15):

        page = doc.new_page()

        if i not in {2, 6}:
            page.insert_text((100, 100), f"Page {i + 1} content")

    return doc.tobytes()


@pytest.fixture
def empty_pdf_bytes():
    """Generate a PDF with no content (empty pages)"""

    doc = pymupdf.open()

    doc.new_page()

    return doc.tobytes()


@pytest.fixture
def corrupted_pdf_bytes():
    """Generate corrupted PDF bytes for testing."""

    return b"corrupted data"


@pytest.fixture
def image_pdf_bytes():
    test_dir = os.path.dirname(os.path.realpath(__file__))

    image_path = os.path.join(test_dir, "dummy_image.png")

    doc = pymupdf.open()

    page = doc.new_page()

    rect = (0, 0, 100, 100)

    page.insert_image(rect, filename=image_path)

    return doc.tobytes()


class TestPDFTextExtractor:

    # Test init with valid filepath
    def test_init_valid_filepath(self, tmp_path, valid_pdf_bytes):
        pdf_path = tmp_path / "test.pdf"

        pdf_path.write_bytes(valid_pdf_bytes)

        extractor = PDFTextExtractor(str(pdf_path))

        assert extractor.pdf_document is not None

        extractor.close()

    # Test init with valid bytes input
    def test_init_valid_bytes(self, valid_pdf_bytes):
        extractor = PDFTextExtractor(valid_pdf_bytes)

        assert extractor.pdf_document is not None

        extractor.close()

    # Test extracting text skips empty pages
    def test_extract_text_full_document(self, valid_pdf_bytes):
        extractor = PDFTextExtractor(valid_pdf_bytes)

        result = extractor.extract_text()

        assert len(result["pages"]) == 13

        assert result["empty_pages"] == [3, 7]

        assert result["content_pages"] == 13

        extractor.close()

    # Test extracting from completely empty PDF
    def test_extract_text_empty_pdf(self, empty_pdf_bytes):
        extractor = PDFTextExtractor(empty_pdf_bytes)

        result = extractor.extract_text()

        assert result["empty_pages"] == [1]

        extractor.close()

    # Test extracting images from a page
    def test_extract_images_on_page(self, image_pdf_bytes):
        doc = pymupdf.open("pdf", image_pdf_bytes)

        page = doc[0]

        images = PDFTextExtractor.extract_images_on_page(page)

        assert len(images) == 1

        assert images[0]["xref"] > 0

    # Test batch processing respects page_batch_size
    def test_batch_processing(self, valid_pdf_bytes):
        extractor = PDFTextExtractor(valid_pdf_bytes, page_batch_size=5)

        result = extractor.extract_text()

        assert len(result["pages"]) == 13

        extractor.close()

    # Test init raises ValueError for invalid input type
    def test_init_invalid_input_type(self):
        with pytest.raises(ValueError):
            PDFTextExtractor(12345)

    # Test init raises for nonexistent file path
    def test_init_nonexistent_file(self):
        with pytest.raises(Exception):
            PDFTextExtractor("/nonexistent/file.pdf")

    # Test extracting text from corrupted PDF
    def test_extract_text_corrupted_pdf(self):
        with pytest.raises(Exception):
            extractor = PDFTextExtractor(b"corrupted data")

            extractor.extract_text()

    # Test lock timeout yields timeout in result
    def test_lock_timeout(self, valid_pdf_bytes):
        extractor = PDFTextExtractor(valid_pdf_bytes)

        with patch.object(extractor._instance_lock, "acquire_timeout") as mock_lock:
            mock_lock.return_value.__enter__.return_value = False

            result = extractor.extract_text()

        assert "timeout" in result

    # Test close handles errors gracefully
    def test_close_error(self, valid_pdf_bytes):
        extractor = PDFTextExtractor(valid_pdf_bytes)

        with patch.object(extractor.pdf_document, "close", side_effect=Exception("Close error")):
            extractor.close()

    # Test single-page PDF extraction
    def test_single_page_pdf(self):
        doc = pymupdf.open()

        doc.new_page().insert_text((100, 100), "Single page")

        extractor = PDFTextExtractor(doc.tobytes())

        result = extractor.extract_text()

        assert result["content_pages"] == 1

    # Test large batch size still processes correctly
    def test_large_batch_size(self, valid_pdf_bytes):
        extractor = PDFTextExtractor(valid_pdf_bytes, page_batch_size=100)

        result = extractor.extract_text()

        assert len(result["pages"]) == 13

    # Test zero-byte PDF raises exception
    def test_zero_byte_pdf(self):
        with pytest.raises(Exception):
            PDFTextExtractor(b"")

    # Test batch text extraction on valid files
    @pytest.mark.asyncio
    @patch("backend.app.document_processing.pdf_extractor.log_info")
    async def test_batch_text_extraction_valid_files(self, mock_log, valid_pdf_bytes):
        result = await PDFTextExtractor.extract_batch_text([valid_pdf_bytes, valid_pdf_bytes])

        assert len(result) == 2

        assert "pages" in result[0][1]

        assert "pages" in result[1][1]

        assert any(
            call[0][0] == "[OK] Processing PDF extraction (operation_id: memory_buffer)"
            for call in mock_log.call_args_list
        )

    # Test batch text extraction handles corrupted PDF
    @pytest.mark.asyncio
    @patch("backend.app.document_processing.pdf_extractor.SecurityAwareErrorHandler.log_processing_error")
    async def test_batch_text_extraction_invalid_pdf(self, mock_log_error, corrupted_pdf_bytes):
        result = await PDFTextExtractor.extract_batch_text([corrupted_pdf_bytes])

        assert "error" in result[0][1]

        assert result[0][1]["error"] == "Failed to open stream"

        assert mock_log_error.call_count == 2

        call_args = mock_log_error.call_args_list[1][0]

        assert call_args[1] == 'batch_pdf_extraction'

        assert str(call_args[0]) == 'Failed to open stream'

    # Test batch text extraction for empty PDF
    @pytest.mark.asyncio
    async def test_batch_text_extraction_empty_pdf(self, empty_pdf_bytes):
        result = await PDFTextExtractor.extract_batch_text([empty_pdf_bytes])

        assert "empty_pages" in result[0][1]

        assert result[0][1]["empty_pages"] == [1]

        assert result[0][1]["content_pages"] == 0

    # Test processing page timeout logs error
    @pytest.mark.asyncio
    @patch("backend.app.document_processing.pdf_extractor.log_warning")
    @patch("backend.app.document_processing.pdf_extractor.log_error")
    @patch("backend.app.document_processing.pdf_extractor.log_info")
    async def test_process_page_timeout(self, mock_log_info, mock_log_error, mock_log_warning, valid_pdf_bytes):
        extractor = PDFTextExtractor(valid_pdf_bytes)

        extracted_data = {}

        empty_pages = []

        with patch.object(extractor, "_process_page", side_effect=Exception("Test error")):
            extractor._extract_pages_in_batches(extracted_data, empty_pages)

        mock_log_error.assert_called()

        assert "Error processing page" in str(mock_log_error.call_args[0][0])

    # Test batch page timeout logs specific message
    @patch("backend.app.document_processing.pdf_extractor.log_warning")
    @patch("backend.app.document_processing.pdf_extractor.log_error")
    @patch("backend.app.document_processing.pdf_extractor.log_info")
    def test_process_page_batch_timeout(self, mock_log_info, mock_log_error, mock_log_warning, valid_pdf_bytes):
        extractor = PDFTextExtractor(valid_pdf_bytes)

        extracted_data = {}

        empty_pages = []

        with patch.object(extractor, "_process_page", side_effect=TimeoutError("Batch timeout")):
            extractor.page_batch_size = 1

            extractor._extract_pages_in_batches(extracted_data, empty_pages)

        mock_log_error.assert_called()

        assert "[ERROR] Error processing page 14: Batch timeout" in str(mock_log_error.call_args[0][0])
