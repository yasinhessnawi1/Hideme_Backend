"""
Unit tests for data_minimization.py module.

This test file covers all functions in the data_minimization module with both positive
and negative test cases to ensure proper functionality and error handling.
"""

import hashlib
import unittest
from unittest import mock
from unittest.mock import patch

# Import the module to be tested
from backend.app.utils.validation.data_minimization import (
    _get_trace_id,
    _minimize_word,
    _minimize_page,
    _estimate_data_size,
    _extract_valid_data,
    _process_pages,
    minimize_extracted_data, sanitize_document_metadata, _sanitize_all_fields, _apply_sensitive_patterns,
    _sanitize_specific_fields, _remove_unwanted_fields
)


class TestDataMinimization(unittest.TestCase):
    """Test cases for data_minimization.py module."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        # Sample word data for testing
        self.sample_word = {
            "text": "Sample",
            "x0": 10.0,
            "y0": 20.0,
            "x1": 50.0,
            "y1": 30.0,
            "font": "Arial",
            "size": 12,
            "sensitive": True,
            "confidence": 0.95
        }

        # Sample page data for testing
        self.sample_page = {
            "page": 1,
            "words": [
                self.sample_word,
                {"text": "Text", "x0": 60.0, "y0": 20.0, "x1": 90.0, "y1": 30.0, "font": "Times"},
                {"text": "", "x0": 100.0, "y0": 20.0, "x1": 110.0, "y1": 30.0}  # Empty text
            ]
        }

        # Sample extracted data for testing
        self.sample_extracted_data = {
            "document_id": "doc123",
            "filename": "test.pdf",
            "metadata": {"title": "Test Document", "author": "Test Author"},
            "pages": [self.sample_page]
        }

        # Sample metadata for testing
        self.sample_metadata = {
            "title": "Test Document",
            "author": "John Doe",
            "creator": "PDF Creator",
            "producer": "PDF Library",
            "creation_date": "2023-01-01",
            "mod_date": "2023-02-01",
            "page_count": 10,
            "version": "1.5",
            "subject": "Test Subject",
            "keywords": "test, document, sample",
            "email": "john.doe@example.com",
            "phone": "+1-123-456-7890"
        }

        # Mock constants
        self.mock_sensitive_fields = ["sensitive", "confidence"]
        self.mock_default_metadata_fields = {"document_id", "filename", "metadata"}
        self.mock_data_minimization_rules = {"required_fields_only": True}

    def test_get_trace_id_with_provided_id(self):
        """Test _get_trace_id with a provided trace ID."""
        provided_id = "test-trace-id"
        result = _get_trace_id(provided_id)
        self.assertEqual(result, provided_id)

    @patch('time.time')
    def test_get_trace_id_without_provided_id(self, mock_time):
        """Test _get_trace_id without a provided trace ID."""

        # Mock time.time() to return a predictable value
        mock_time.return_value = 1609459200.0  # 2021-01-01 00:00:00

        # Calculate expected hash
        expected_hash = hashlib.md5(str(1609459200.0).encode()).hexdigest()[:6]
        expected_id = f"minimize_1609459200_{expected_hash}"

        result = _get_trace_id(None)
        self.assertEqual(result, expected_id)

    @patch('backend.app.utils.constant.constant.SENSITIVE_FIELDS', ["sensitive", "confidence"])
    def test_minimize_word_required_fields_only(self):
        """Test _minimize_word with required_fields_only=True."""
        result = _minimize_word(self.sample_word, True)

        # Check that only required fields are present
        self.assertEqual(result["text"], "Sample")
        self.assertEqual(result["x0"], 10.0)
        self.assertEqual(result["y0"], 20.0)
        self.assertEqual(result["x1"], 50.0)
        self.assertEqual(result["y1"], 30.0)

        # Check that other fields are not present
        self.assertNotIn("font", result)
        self.assertNotIn("size", result)
        self.assertNotIn("sensitive", result)
        self.assertNotIn("confidence", result)

    @patch('backend.app.utils.validation.data_minimization.SENSITIVE_FIELDS', ["sensitive", "confidence"])
    def test_minimize_word_not_required_fields_only(self):
        """Test _minimize_word with required_fields_only=False."""
        result = _minimize_word(self.sample_word, False)

        # Check that non-sensitive fields are present
        self.assertEqual(result["text"], "Sample")
        self.assertEqual(result["x0"], 10.0)
        self.assertEqual(result["y0"], 20.0)
        self.assertEqual(result["x1"], 50.0)
        self.assertEqual(result["y1"], 30.0)
        self.assertEqual(result["font"], "Arial")
        self.assertEqual(result["size"], 12)

        # Check that sensitive fields have been removed
        self.assertNotIn("sensitive", result)
        self.assertNotIn("confidence", result)

    def test_minimize_word_empty_text(self):
        """Test _minimize_word with empty text."""
        word = {"text": "", "x0": 10.0, "y0": 20.0, "x1": 50.0, "y1": 30.0}
        result = _minimize_word(word, True)
        self.assertIsNone(result)

        word = {"text": "   ", "x0": 10.0, "y0": 20.0, "x1": 50.0, "y1": 30.0}
        result = _minimize_word(word, True)
        self.assertIsNone(result)

    @patch('backend.app.utils.validation.data_minimization._minimize_word')
    def test_minimize_page_positive(self, mock_minimize_word):
        """Test _minimize_page with valid input."""

        # Setup mock to return minimized words
        mock_minimize_word.side_effect = [
            {"text": "Sample", "x0": 10.0, "y0": 20.0, "x1": 50.0, "y1": 30.0},
            {"text": "Text", "x0": 60.0, "y0": 20.0, "x1": 90.0, "y1": 30.0},
            None  # For the empty text word
        ]

        result = _minimize_page(self.sample_page, True)

        # Check result structure
        self.assertEqual(result["page"], 1)
        self.assertEqual(len(result["words"]), 2)  # Only 2 words have text

        # Verify _minimize_word was called for each word
        self.assertEqual(mock_minimize_word.call_count, 3)

    @patch('backend.app.utils.validation.data_minimization._minimize_word')
    @patch('backend.app.utils.validation.data_minimization._logger')
    def test_minimize_page_with_exception(self, mock_logger, mock_minimize_word):
        """Test _minimize_page with an exception during word processing."""

        # Setup mock to raise an exception for the second word
        mock_minimize_word.side_effect = [
            {"text": "Sample", "x0": 10.0, "y0": 20.0, "x1": 50.0, "y1": 30.0},
            Exception("Test exception"),
            None  # For the empty text word
        ]

        result = _minimize_page(self.sample_page, True)

        # Check result structure
        self.assertEqual(result["page"], 1)
        self.assertEqual(len(result["words"]), 1)  # Only 1 word processed successfully

        # Verify logger was called for the exception
        mock_logger.warning.assert_called_once()

    def test_minimize_page_no_valid_words(self):
        """Test _minimize_page with no valid words."""
        page = {"page": 1, "words": [{"text": ""}, {"text": "  "}]}
        result = _minimize_page(page, True)
        self.assertIsNone(result)

    def test_estimate_data_size_simple_types(self):
        """Test _estimate_data_size with simple data types."""
        # Test with string
        result = _estimate_data_size("test")
        self.assertGreater(result, 0)

        # Test with number
        result = _estimate_data_size(123)
        self.assertGreater(result, 0)

        # Test with boolean
        result = _estimate_data_size(True)
        self.assertGreater(result, 0)

    def test_estimate_data_size_complex_types(self):
        """Test _estimate_data_size with complex data types."""
        # Test with dictionary
        result = _estimate_data_size({"key": "value", "number": 123})
        self.assertGreater(result, 0)

        # Test with list
        result = _estimate_data_size(["item1", "item2", 123])
        self.assertGreater(result, 0)

        # Test with nested structures
        result = _estimate_data_size({"key": ["item1", {"nested": "value"}]})
        self.assertGreater(result, 0)

    def test_estimate_data_size_non_serializable(self):
        """Test _estimate_data_size with non-JSON-serializable data."""
        # Use a lambda (functions are non-serializable) instead of a circular reference.
        non_serializable = lambda x: x
        result = _estimate_data_size(non_serializable)
        self.assertIsInstance(result, int)

    def test_extract_valid_data_dict(self):
        """Test _extract_valid_data with a dictionary input."""
        data = {"key": "value"}
        result = _extract_valid_data(data)
        self.assertEqual(result, data)

    def test_extract_valid_data_tuple(self):
        """Test _extract_valid_data with a tuple input."""
        data = (1, {"key": "value"})
        result = _extract_valid_data(data)
        self.assertEqual(result, {"key": "value"})

    def test_extract_valid_data_invalid(self):
        """Test _extract_valid_data with invalid inputs."""
        # Test with non-tuple, non-dict
        result = _extract_valid_data("string")
        self.assertEqual(result, {})

        # Test with tuple of wrong length
        result = _extract_valid_data((1, 2, 3))
        self.assertEqual(result, {})

        # Test with tuple where second element is not a dict
        result = _extract_valid_data((1, "not a dict"))
        self.assertEqual(result, {})

    @patch('backend.app.utils.validation.data_minimization._minimize_page')
    def test_process_pages_positive(self, mock_minimize_page):
        """Test _process_pages with valid input."""
        # Setup mock to return minimized pages
        mock_minimize_page.side_effect = [
            {"page": 1, "words": [{"text": "Sample"}]},
            {"page": 2, "words": [{"text": "Text"}]}
        ]

        pages = [{"page": 1}, {"page": 2}]
        result = _process_pages(pages, True)

        # Check result
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["page"], 1)
        self.assertEqual(result[1]["page"], 2)

        # Verify _minimize_page was called for each page
        self.assertEqual(mock_minimize_page.call_count, 2)

    @patch('backend.app.utils.validation.data_minimization._minimize_page')
    @patch('backend.app.utils.validation.data_minimization._logger')
    def test_process_pages_with_exception(self, mock_logger, mock_minimize_page):
        """Test _process_pages with an exception during page processing."""
        # Setup mock to raise an exception for the second page
        mock_minimize_page.side_effect = [
            {"page": 1, "words": [{"text": "Sample"}]},
            Exception("Test exception")
        ]

        pages = [{"page": 1}, {"page": 2}]
        result = _process_pages(pages, True)

        # Check result
        self.assertEqual(len(result), 1)  # Only 1 page processed successfully
        self.assertEqual(result[0]["page"], 1)

        # Verify logger was called for the exception
        mock_logger.warning.assert_called_once()

    @patch('backend.app.utils.validation.data_minimization._minimize_page')
    def test_process_pages_no_valid_pages(self, mock_minimize_page):
        """Test _process_pages with no valid pages."""
        # Setup mock to return None for all pages
        mock_minimize_page.return_value = None

        pages = [{"page": 1}, {"page": 2}]
        result = _process_pages(pages, True)

        # Check result
        self.assertEqual(result, [])

    @patch('time.time')
    @patch('backend.app.utils.validation.data_minimization._logger')
    @patch('backend.app.utils.validation.data_minimization.record_keeper')
    @patch('backend.app.utils.validation.data_minimization.DATA_MINIMIZATION_RULES', {"required_fields_only": True})
    @patch('backend.app.utils.validation.data_minimization.DEFAULT_METADATA_FIELDS', {"document_id", "filename"})
    @patch('backend.app.utils.validation.data_minimization._estimate_data_size')
    @patch('backend.app.utils.validation.data_minimization._process_pages')
    @patch('backend.app.utils.validation.data_minimization._get_trace_id')
    @patch('backend.app.utils.validation.data_minimization._extract_valid_data')
    def test_minimize_extracted_data_positive(self,
                                              mock_extract_valid_data,
                                              mock_get_trace_id,
                                              mock_process_pages,
                                              mock_estimate_data_size,
                                              mock_record_keeper,
                                              mock_logger,
                                              mock_time):
        """Test minimize_extracted_data with valid input."""
        # Have all time.time() calls return a constant so record_processing is reached
        mock_time.return_value = 100.0

        mock_extract_valid_data.return_value = self.sample_extracted_data
        mock_get_trace_id.return_value = "test-trace-id"
        mock_process_pages.return_value = [{"page": 1, "words": [{"text": "Sample"}]}]
        mock_estimate_data_size.side_effect = [10240, 5120]  # Original size, minimized size

        result = minimize_extracted_data(self.sample_extracted_data)

        # Check result structure
        self.assertIn("pages", result)
        self.assertEqual(len(result["pages"]), 1)
        self.assertIn("document_id", result)
        self.assertIn("filename", result)
        self.assertIn("_minimization_meta", result)

        # Verify record_keeper was called once
        mock_record_keeper.record_processing.assert_called_once()

        # Verify logger.info was called for the size reduction log
        mock_logger.info.assert_called_once()

    @patch('backend.app.utils.validation.data_minimization._extract_valid_data')
    def test_minimize_extracted_data_empty(self, mock_extract_valid_data):
        """Test minimize_extracted_data with empty input."""
        # Setup mock to return empty data
        mock_extract_valid_data.return_value = {}

        result = minimize_extracted_data({})

        # Check result
        self.assertEqual(result, {"pages": []})

    @patch('backend.app.utils.validation.data_minimization._logger')
    def test_remove_unwanted_fields_positive(self, mock_logger):
        """_remove_unwanted_fields should delete only non‑preserved fields."""
        metadata = {'keep': 1, 'remove1': 2, 'remove2': 3}
        fields_to_remove = ['remove1', 'remove2', 'no_such']
        preserve = ['keep']
        _remove_unwanted_fields(metadata, fields_to_remove, preserve)
        # removed fields gone
        self.assertNotIn('remove1', metadata)
        self.assertNotIn('remove2', metadata)
        # preserved field still there
        self.assertIn('keep', metadata)
        # no bogus warning
        mock_logger.warning.assert_not_called()

    @patch('backend.app.utils.validation.data_minimization._logger')
    def test_remove_unwanted_fields_exception(self, mock_logger):
        """_remove_unwanted_fields should log warning if deletion fails."""

        class BadDict(dict):
            def __delitem__(self, key):
                raise RuntimeError("boom")

        metadata = BadDict({'bad': 1})
        _remove_unwanted_fields(metadata, ['bad'], [])
        mock_logger.warning.assert_called_once_with("Error removing field '%s': %s", 'bad', mock.ANY)

    def test_sanitize_specific_fields(self):
        """_sanitize_specific_fields should replace non‑preserved fields."""
        metadata = {'f1': 'v1', 'f2': 'v2'}
        fields_to_sanitize = {'f1': 'X1', 'f2': 'X2'}
        preserve = ['f2']
        _sanitize_specific_fields(metadata, fields_to_sanitize, preserve)
        self.assertEqual(metadata['f1'], 'X1')
        # f2 was preserved
        self.assertEqual(metadata['f2'], 'v2')

    @patch('backend.app.utils.validation.data_minimization._logger')
    def test_apply_sensitive_patterns(self, mock_logger):
        """_apply_sensitive_patterns should substitute matches and swallow bad patterns."""
        val = "email: john.doe@example.com"
        patterns = [(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', '[EMAIL]')]
        out = _apply_sensitive_patterns(val, patterns)
        self.assertEqual(out, "email: [EMAIL]")

        # now a bad regex
        bad = _apply_sensitive_patterns("foo", [('(', 'x')])
        self.assertEqual(bad, "foo")
        self.assertTrue(mock_logger.warning.called)

    @patch('backend.app.utils.validation.data_minimization._apply_sensitive_patterns', return_value='ZZZ')
    def test_sanitize_all_fields(self, mock_apply):
        """_sanitize_all_fields should call _apply_sensitive_patterns on every non‑preserved string."""
        metadata = {'a': 'one', 'b': 'two', 'c': 123}
        preserve = ['b']
        patterns = []
        _sanitize_all_fields(metadata, preserve, patterns)

        # a was sanitized, b was preserved, c untouched
        self.assertEqual(metadata['a'], 'ZZZ')
        self.assertEqual(metadata['b'], 'two')
        self.assertEqual(metadata['c'], 123)
        mock_apply.assert_called_once_with('one', patterns)

    @patch('backend.app.utils.validation.data_minimization.record_keeper')
    @patch('backend.app.utils.validation.data_minimization._logger')
    def test_sanitize_document_metadata_default(self, mock_logger, mock_record_keeper):
        """sanitize_document_metadata removes unwanted, replaces specific, sets _sanitized."""
        orig = {
            'title': "T", 'subject': "S",
            'author': "A", 'email': "e@x.com",
            'custom': "C", 'page_count': 5, 'version': 'v'
        }
        out = sanitize_document_metadata(orig.copy(), sanitize_all=False)

        # author & email removed, custom removed
        for f in ('author', 'email', 'custom'):
            self.assertNotIn(f, out)

        # title & subject preserved (and not overwritten)
        self.assertEqual(out['title'], "T")
        self.assertEqual(out['subject'], "S")
        self.assertTrue(out.get('_sanitized', False))
        mock_record_keeper.record_processing.assert_called_once()

    @patch('backend.app.utils.validation.data_minimization.record_keeper')
    def test_sanitize_document_metadata_full(self, mock_record_keeper):
        """sanitize_document_metadata with sanitize_all=True applies patterns."""
        orig = {'page_count': 2, 'foo': 'user@example.com', 'bar': 'nochange'}
        out = sanitize_document_metadata(orig.copy(), sanitize_all=True, preserve_fields=['page_count'])

        # foo should be replaced by [EMAIL], bar also matches email pattern? no
        self.assertEqual(out['foo'], '[EMAIL]')
        self.assertEqual(out['bar'], 'nochange')
        self.assertTrue(out['_sanitized'])
        mock_record_keeper.record_processing.assert_called_once()

    def test_sanitize_document_metadata_empty(self):
        """sanitize_document_metadata on empty or None returns {}."""
        self.assertEqual(sanitize_document_metadata({}, sanitize_all=True), {})
        self.assertEqual(sanitize_document_metadata(None), {})
