import os

from unittest.mock import patch

import pymupdf

import pytest

from backend.app.document_processing.pdf_extractor import PDFTextExtractor

from backend.app.document_processing.pdf_redactor import PDFRedactionService


@pytest.fixture
def valid_pdf_with_content():
    """Generate a PDF with text and image content."""

    doc = pymupdf.open()

    test_dir = os.path.dirname(os.path.realpath(__file__))

    image_path = os.path.join(test_dir, "dummy_image.png")

    text_bbox = pymupdf.Rect(100, 100, 250, 120)

    image_bbox = pymupdf.Rect(50, 150, 150, 250)

    for i in range(12):

        page = doc.new_page()

        page.insert_text((text_bbox.x0, text_bbox.y0), f"Sensitive data {i + 1}")

        if i == 1:
            page.insert_image(image_bbox, filename=image_path)

    return doc.tobytes()


@pytest.fixture
def redaction_mapping():
    """Generate redaction mapping for text and image."""

    return {
        "pages": [
                     {
                         "page": i + 1,
                         "sensitive": [
                             {
                                 "entity_type": "secret",
                                 "boxes": {"x0": 100, "y0": 100, "x1": 250, "y1": 120}
                             }
                         ]
                     }
                     for i in range(12)
                 ]
                 + [
                     {
                         "page": 2,
                         "sensitive": [
                             {
                                 "bbox": {"x0": 50, "y0": 150, "x1": 150, "y1": 250}
                             }
                         ]
                     }
                 ]
    }


@pytest.fixture
def empty_pdf():
    """Generate a PDF with empty pages."""

    doc = pymupdf.open()

    for _ in range(12):
        doc.new_page()

    return doc.tobytes()


class TestPDFRedactionService:
    """Comprehensive tests for PDFRedactionService."""

    # Test initialization with valid file path, bytes, and file-like object
    def test_init_valid_inputs(self, valid_pdf_with_content, tmp_path):

        pdf_path = tmp_path / "test.pdf"

        pdf_path.write_bytes(valid_pdf_with_content)

        instance = PDFRedactionService(str(pdf_path))

        assert instance.doc is not None

        instance.close()

        instance = PDFRedactionService(valid_pdf_with_content)

        assert instance.doc is not None

        instance.close()

        with open(pdf_path, "rb") as f:
            instance = PDFRedactionService(f)

            assert instance.doc is not None

            instance.close()

    # Test applying redactions to file output
    def test_apply_redactions_to_file(self, valid_pdf_with_content, redaction_mapping, tmp_path):

        output_path = tmp_path / "output.pdf"

        redactor = PDFRedactionService(valid_pdf_with_content)

        result = redactor.apply_redactions(redaction_mapping, str(output_path))

        assert os.path.exists(result)

        with pymupdf.open(result) as doc:

            assert len(doc) == 12

            cleared_metadata_fields = [
                'format', 'title', 'author', 'subject', 'keywords', 'creator',
                'producer', 'creationDate', 'modDate', 'trapped', 'encryption'
            ]

            for key, value in doc.metadata.items():

                if key not in cleared_metadata_fields:
                    assert value == "" or value is None

    # Test applying redactions in-memory returns bytes without sensitive text
    def test_apply_redactions_to_memory(self, valid_pdf_with_content, redaction_mapping):

        redactor = PDFRedactionService(valid_pdf_with_content)

        result = redactor.apply_redactions_to_memory(redaction_mapping)

        assert isinstance(result, bytes)

        with pymupdf.open("pdf", result) as doc:
            assert len(doc) == 12

            redacted_text = doc[0].get_text()

            assert "secret" not in redacted_text

    # Test image redaction removes images when requested
    def test_image_redaction(self, valid_pdf_with_content, tmp_path):

        output_path = tmp_path / "image_redacted.pdf"

        mapping = {
            "pages": [
                {
                    "page": 2,
                    "sensitive": [
                        {"bbox": {"x0": 50, "y0": 150, "x1": 150, "y1": 250}}
                    ]
                }
            ]
        }

        redactor = PDFRedactionService(valid_pdf_with_content)

        redactor.apply_redactions(mapping, str(output_path), remove_images=True)

        with pymupdf.open(output_path) as doc:
            images = PDFTextExtractor.extract_images_on_page(doc[1])

            assert len(images) == 0

    # Test batch processing invokes internal batch method
    def test_batch_processing(self, valid_pdf_with_content, redaction_mapping):

        redactor = PDFRedactionService(valid_pdf_with_content, page_batch_size=5)

        with patch.object(redactor, "_process_redaction_pages_batch") as mock_batch:
            redactor._draw_redaction_boxes(redaction_mapping, remove_images=False)

            assert mock_batch.called

    # Test initialization with invalid input raises ValueError
    def test_init_invalid_input(self):

        with pytest.raises(ValueError):
            PDFRedactionService(12345)

    # Test lock timeout in redaction raises TimeoutError
    def test_lock_timeout(self, valid_pdf_with_content):

        redactor = PDFRedactionService(valid_pdf_with_content)

        with patch.object(redactor._instance_lock, "acquire_timeout") as mock_lock:
            mock_lock.return_value.__enter__.return_value = False

            with pytest.raises(TimeoutError):
                redactor.apply_redactions({}, "dummy.pdf")

    # Test error during page processing raises Exception
    def test_page_processing_error(self, valid_pdf_with_content, redaction_mapping):

        redactor = PDFRedactionService(valid_pdf_with_content)

        with patch.object(redactor, "_process_redaction_page", side_effect=Exception("Test error")):
            with pytest.raises(Exception):
                redactor.apply_redactions(redaction_mapping, "dummy.pdf")

    # Test sanitization logs errors without raising
    def test_sanitization_error(self, valid_pdf_with_content):

        redactor = PDFRedactionService(valid_pdf_with_content)

        with patch(
                "backend.app.document_processing.pdf_redactor.SecurityAwareErrorHandler.log_processing_error"
        ) as mock_log_processing_error:
            with patch.object(redactor.doc, "set_metadata", side_effect=Exception("Sanitize error")):
                redactor._sanitize_document()

            called_args = mock_log_processing_error.call_args[0]

            assert str(called_args[0]) == "Sanitize error"

            assert called_args[1] == "pdf_document_sanitize"

            assert called_args[2] == redactor.file_path

    # Test empty redaction mapping returns valid PDF
    def test_empty_redaction_mapping(self, valid_pdf_with_content, tmp_path):

        output_path = tmp_path / "empty.pdf"

        redactor = PDFRedactionService(valid_pdf_with_content)

        result = redactor.apply_redactions({"pages": []}, str(output_path))

        assert os.path.exists(result)

    # Test zero-byte input raises Exception
    def test_zero_byte_input(self):

        with pytest.raises(Exception):
            PDFRedactionService(b"")

    # Test metadata removal clears sensitive fields
    def test_metadata_removal(self, valid_pdf_with_content, tmp_path):

        output_path = tmp_path / "meta.pdf"

        redactor = PDFRedactionService(valid_pdf_with_content)

        redactor.apply_redactions({}, str(output_path))

        with pymupdf.open(output_path) as doc:
            assert not doc.metadata.get("producer")

    # Test cleanup releases document resource
    def test_proper_cleanup(self, valid_pdf_with_content):

        redactor = PDFRedactionService(valid_pdf_with_content)

        redactor.close()

        assert redactor.doc is None

    # Test double close does not raise errors
    def test_double_close(self, valid_pdf_with_content):

        redactor = PDFRedactionService(valid_pdf_with_content)

        redactor.close()

        redactor.close()

    # Test thread-safe lock acquisition works
    def test_thread_safe_operations(self, valid_pdf_with_content):

        redactor = PDFRedactionService(valid_pdf_with_content)

        with redactor._instance_lock.acquire_timeout() as lock:
            assert lock is True

        redactor.close()

    # Test large batch processing triggers garbage collection
    def test_large_batch_processing(self, valid_pdf_with_content):

        mapping = {"pages": [{"page": i + 1, "sensitive": []} for i in range(20)]}

        redactor = PDFRedactionService(valid_pdf_with_content, page_batch_size=100)

        with patch("gc.collect") as mock_gc:
            redactor._draw_redaction_boxes(mapping, False)

            assert mock_gc.call_count == 1
