import hashlib

import unittest

from unittest import mock

from unittest.mock import patch

from backend.app.utils.validation.data_minimization import (
    _get_trace_id,
    _minimize_word,
    _minimize_page,
    _estimate_data_size,
    _extract_valid_data,
    _process_pages,
    minimize_extracted_data,
    sanitize_document_metadata,
    _sanitize_all_fields,
    _apply_sensitive_patterns,
    _sanitize_specific_fields,
    _remove_unwanted_fields
)


# Tests for data minimization functions
class TestDataMinimization(unittest.TestCase):

    # Setup sample data for tests
    def setUp(self):
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

        self.sample_page = {

            "page": 1,

            "words": [

                self.sample_word,

                {"text": "Text", "x0": 60.0, "y0": 20.0, "x1": 90.0, "y1": 30.0, "font": "Times"},

                {"text": "", "x0": 100.0, "y0": 20.0, "x1": 110.0, "y1": 30.0}

            ]

        }

        self.sample_extracted_data = {

            "document_id": "doc123",

            "filename": "test.pdf",

            "metadata": {"title": "Test Document", "author": "Test Author"},

            "pages": [self.sample_page]

        }

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

    # Test _get_trace_id returns provided ID
    def test_get_trace_id_with_provided_id(self):
        provided_id = "test-trace-id"

        result = _get_trace_id(provided_id)

        self.assertEqual(result, provided_id)

    # Test _get_trace_id generates new ID when none provided
    @patch('time.time')
    def test_get_trace_id_without_provided_id(self, mock_time):
        mock_time.return_value = 1609459200.0

        expected_hash = hashlib.md5(str(1609459200.0).encode()).hexdigest()[:6]

        expected_id = f"minimize_1609459200_{expected_hash}"

        result = _get_trace_id(None)

        self.assertEqual(result, expected_id)

    # Test _minimize_word required fields only
    @patch('backend.app.utils.constant.constant.SENSITIVE_FIELDS', ["sensitive", "confidence"])
    def test_minimize_word_required_fields_only(self):
        result = _minimize_word(self.sample_word, True)

        self.assertEqual(result["text"], "Sample")

        self.assertEqual(result["x0"], 10.0)

        self.assertEqual(result["y0"], 20.0)

        self.assertEqual(result["x1"], 50.0)

        self.assertEqual(result["y1"], 30.0)

        self.assertNotIn("font", result)

        self.assertNotIn("size", result)

        self.assertNotIn("sensitive", result)

        self.assertNotIn("confidence", result)

    # Test _minimize_word with all fields
    @patch('backend.app.utils.validation.data_minimization.SENSITIVE_FIELDS', ["sensitive", "confidence"])
    def test_minimize_word_not_required_fields_only(self):
        result = _minimize_word(self.sample_word, False)

        self.assertEqual(result["text"], "Sample")

        self.assertEqual(result["x0"], 10.0)

        self.assertEqual(result["y0"], 20.0)

        self.assertEqual(result["x1"], 50.0)

        self.assertEqual(result["y1"], 30.0)

        self.assertEqual(result["font"], "Arial")

        self.assertEqual(result["size"], 12)

        self.assertNotIn("sensitive", result)

        self.assertNotIn("confidence", result)

    # Test _minimize_word returns None for empty text
    def test_minimize_word_empty_text(self):
        word = {"text": "", "x0": 10.0, "y0": 20.0, "x1": 50.0, "y1": 30.0}

        result = _minimize_word(word, True)

        self.assertIsNone(result)

        word = {"text": "   ", "x0": 10.0, "y0": 20.0, "x1": 50.0, "y1": 30.0}

        result = _minimize_word(word, True)

        self.assertIsNone(result)

    # Test _minimize_page processes words correctly
    @patch('backend.app.utils.validation.data_minimization._minimize_word')
    def test_minimize_page_positive(self, mock_minimize_word):
        mock_minimize_word.side_effect = [

            {"text": "Sample", "x0": 10.0, "y0": 20.0, "x1": 50.0, "y1": 30.0},

            {"text": "Text", "x0": 60.0, "y0": 20.0, "x1": 90.0, "y1": 30.0},

            None

        ]

        result = _minimize_page(self.sample_page, True)

        self.assertEqual(result["page"], 1)

        self.assertEqual(len(result["words"]), 2)

        self.assertEqual(mock_minimize_word.call_count, 3)

    # Test _minimize_page logs exception and continues
    @patch('backend.app.utils.validation.data_minimization._minimize_word')
    @patch('backend.app.utils.validation.data_minimization._logger')
    def test_minimize_page_with_exception(self, mock_logger, mock_minimize_word):
        mock_minimize_word.side_effect = [

            {"text": "Sample", "x0": 10.0, "y0": 20.0, "x1": 50.0, "y1": 30.0},

            Exception("Test exception"),

            None

        ]

        result = _minimize_page(self.sample_page, True)

        self.assertEqual(result["page"], 1)

        self.assertEqual(len(result["words"]), 1)

        mock_logger.warning.assert_called_once()

    # Test _minimize_page returns None if no valid words
    def test_minimize_page_no_valid_words(self):
        page = {"page": 1, "words": [{"text": ""}, {"text": "  "}]}

        result = _minimize_page(page, True)

        self.assertIsNone(result)

    # Test _estimate_data_size simple types
    def test_estimate_data_size_simple_types(self):
        result = _estimate_data_size("test")

        self.assertGreater(result, 0)

        result = _estimate_data_size(123)

        self.assertGreater(result, 0)

        result = _estimate_data_size(True)

        self.assertGreater(result, 0)

    # Test _estimate_data_size complex types
    def test_estimate_data_size_complex_types(self):
        result = _estimate_data_size({"key": "value", "number": 123})

        self.assertGreater(result, 0)

        result = _estimate_data_size(["item1", "item2", 123])

        self.assertGreater(result, 0)

        result = _estimate_data_size({"key": ["item1", {"nested": "value"}]})

        self.assertGreater(result, 0)

    # Test _estimate_data_size non-serializable inputs
    def test_estimate_data_size_non_serializable(self):
        non_serializable = lambda x: x

        result = _estimate_data_size(non_serializable)

        self.assertIsInstance(result, int)

    # Test _extract_valid_data with dict
    def test_extract_valid_data_dict(self):
        data = {"key": "value"}

        result = _extract_valid_data(data)

        self.assertEqual(result, data)

    # Test _extract_valid_data with tuple
    def test_extract_valid_data_tuple(self):
        data = (1, {"key": "value"})

        result = _extract_valid_data(data)

        self.assertEqual(result, {"key": "value"})

    # Test _extract_valid_data invalid inputs
    def test_extract_valid_data_invalid(self):
        result = _extract_valid_data("string")

        self.assertEqual(result, {})

        result = _extract_valid_data((1, 2, 3))

        self.assertEqual(result, {})

        result = _extract_valid_data((1, "not a dict"))

        self.assertEqual(result, {})

    # Test _process_pages with valid pages
    @patch('backend.app.utils.validation.data_minimization._minimize_page')
    def test_process_pages_positive(self, mock_minimize_page):
        mock_minimize_page.side_effect = [

            {"page": 1, "words": [{"text": "Sample"}]},

            {"page": 2, "words": [{"text": "Text"}]}

        ]

        pages = [{"page": 1}, {"page": 2}]

        result = _process_pages(pages, True)

        self.assertEqual(len(result), 2)

        self.assertEqual(result[0]["page"], 1)

        self.assertEqual(result[1]["page"], 2)

        self.assertEqual(mock_minimize_page.call_count, 2)

    # Test _process_pages logs exception and continues
    @patch('backend.app.utils.validation.data_minimization._minimize_page')
    @patch('backend.app.utils.validation.data_minimization._logger')
    def test_process_pages_with_exception(self, mock_logger, mock_minimize_page):
        mock_minimize_page.side_effect = [

            {"page": 1, "words": [{"text": "Sample"}]},

            Exception("Test exception")

        ]

        pages = [{"page": 1}, {"page": 2}]

        result = _process_pages(pages, True)

        self.assertEqual(len(result), 1)

        self.assertEqual(result[0]["page"], 1)

        mock_logger.warning.assert_called_once()

    # Test _process_pages returns empty list if no pages
    @patch('backend.app.utils.validation.data_minimization._minimize_page')
    def test_process_pages_no_valid_pages(self, mock_minimize_page):
        mock_minimize_page.return_value = None

        pages = [{"page": 1}, {"page": 2}]

        result = _process_pages(pages, True)

        self.assertEqual(result, [])

    # Test minimize_extracted_data successful path
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
        mock_time.return_value = 100.0

        mock_extract_valid_data.return_value = self.sample_extracted_data

        mock_get_trace_id.return_value = "test-trace-id"

        mock_process_pages.return_value = [{"page": 1, "words": [{"text": "Sample"}]}]

        mock_estimate_data_size.side_effect = [10240, 5120]

        result = minimize_extracted_data(self.sample_extracted_data)

        self.assertIn("pages", result)

        self.assertEqual(len(result["pages"]), 1)

        self.assertIn("document_id", result)

        self.assertIn("filename", result)

        self.assertIn("_minimization_meta", result)

        mock_record_keeper.record_processing.assert_called_once()

        mock_logger.info.assert_called_once()

    # Test minimize_extracted_data with empty input
    @patch('backend.app.utils.validation.data_minimization._extract_valid_data')
    def test_minimize_extracted_data_empty(self, mock_extract_valid_data):
        mock_extract_valid_data.return_value = {}

        result = minimize_extracted_data({})

        self.assertEqual(result, {"pages": []})

    # Test _remove_unwanted_fields removes specified fields
    @patch('backend.app.utils.validation.data_minimization._logger')
    def test_remove_unwanted_fields_positive(self, mock_logger):
        metadata = {'keep': 1, 'remove1': 2, 'remove2': 3}

        fields_to_remove = ['remove1', 'remove2', 'no_such']

        preserve = ['keep']

        _remove_unwanted_fields(metadata, fields_to_remove, preserve)

        self.assertNotIn('remove1', metadata)

        self.assertNotIn('remove2', metadata)

        self.assertIn('keep', metadata)

        mock_logger.warning.assert_not_called()

    # Test _remove_unwanted_fields logs on failure
    @patch('backend.app.utils.validation.data_minimization._logger')
    def test_remove_unwanted_fields_exception(self, mock_logger):
        class BadDict(dict):

            def __delitem__(self, key):
                raise RuntimeError("boom")

        metadata = BadDict({'bad': 1})

        _remove_unwanted_fields(metadata, ['bad'], [])

        mock_logger.warning.assert_called_once_with("Error removing field '%s': %s", 'bad', mock.ANY)

    # Test _sanitize_specific_fields replaces specified fields
    def test_sanitize_specific_fields(self):
        metadata = {'f1': 'v1', 'f2': 'v2'}

        fields_to_sanitize = {'f1': 'X1', 'f2': 'X2'}

        preserve = ['f2']

        _sanitize_specific_fields(metadata, fields_to_sanitize, preserve)

        self.assertEqual(metadata['f1'], 'X1')

        self.assertEqual(metadata['f2'], 'v2')

    # Test _apply_sensitive_patterns substitues and logs bad regex
    @patch('backend.app.utils.validation.data_minimization._logger')
    def test_apply_sensitive_patterns(self, mock_logger):
        val = "email: john.doe@example.com"

        patterns = [(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', '[EMAIL]')]

        out = _apply_sensitive_patterns(val, patterns)

        self.assertEqual(out, "email: [EMAIL]")

        bad = _apply_sensitive_patterns("foo", [('(', 'x')])

        self.assertEqual(bad, "foo")

        self.assertTrue(mock_logger.warning.called)

    # Test _sanitize_all_fields applies patterns correctly
    @patch('backend.app.utils.validation.data_minimization._apply_sensitive_patterns', return_value='ZZZ')
    def test_sanitize_all_fields(self, mock_apply):
        metadata = {'a': 'one', 'b': 'two', 'c': 123}

        preserve = ['b']

        patterns = []

        _sanitize_all_fields(metadata, preserve, patterns)

        self.assertEqual(metadata['a'], 'ZZZ')

        self.assertEqual(metadata['b'], 'two')

        self.assertEqual(metadata['c'], 123)

        mock_apply.assert_called_once_with('one', patterns)

    # Test sanitize_document_metadata default behavior
    @patch('backend.app.utils.validation.data_minimization.record_keeper')
    @patch('backend.app.utils.validation.data_minimization._logger')
    def test_sanitize_document_metadata_default(self, mock_logger, mock_record_keeper):
        orig = {

            'title': "T", 'subject': "S",

            'author': "A", 'email': "e@x.com",

            'custom': "C", 'page_count': 5, 'version': 'v'

        }

        out = sanitize_document_metadata(orig.copy(), sanitize_all=False)

        for f in ('author', 'email', 'custom'):
            self.assertNotIn(f, out)

        self.assertEqual(out['title'], "T")

        self.assertEqual(out['subject'], "S")

        self.assertTrue(out.get('_sanitized', False))

        mock_record_keeper.record_processing.assert_called_once()

    # Test sanitize_document_metadata with full sanitization
    @patch('backend.app.utils.validation.data_minimization.record_keeper')
    def test_sanitize_document_metadata_full(self, mock_record_keeper):
        orig = {'page_count': 2, 'foo': 'user@example.com', 'bar': 'nochange'}

        out = sanitize_document_metadata(orig.copy(), sanitize_all=True, preserve_fields=['page_count'])

        self.assertEqual(out['foo'], '[EMAIL]')

        self.assertEqual(out['bar'], 'nochange')

        self.assertTrue(out['_sanitized'])

        mock_record_keeper.record_processing.assert_called_once()

    # Test sanitize_document_metadata on empty input
    def test_sanitize_document_metadata_empty(self):
        self.assertEqual(sanitize_document_metadata({}, sanitize_all=True), {})

        self.assertEqual(sanitize_document_metadata(None), {})
