import warnings
import asyncio
import json
import time
import unittest
from unittest.mock import patch, AsyncMock
from fastapi.responses import JSONResponse

from backend.app.services.base_detect_service import BaseDetectionService


# Dummy file object for MIME and filename tests
class DummyFile:

    def __init__(self, content_type, filename):
        self.content_type = content_type

        self.filename = filename


# Dummy detector simulating sync and async sensitive data detection
class DummyDetector:

    def __init__(self):
        self.detect_sensitive_data = lambda data, entities: {'res': 'sync'}

    async def detect_sensitive_data_async(self, data, entities):
        return {'res': 'async'}


# Test suite for BaseDetectionService functionality
class TestBaseDetectionService(unittest.IsolatedAsyncioTestCase):

    # Test parsing JSON list of words for removal
    def test_parse_remove_words_json_list(self):
        s = '["apple", " banana ", ""]'

        out = BaseDetectionService.parse_remove_words(s)

        self.assertEqual(out, ["apple", "banana"])

    # Test parsing single JSON string for removal
    def test_parse_remove_words_json_single(self):
        s = '"hello"'

        out = BaseDetectionService.parse_remove_words(s)

        self.assertEqual(out, ["hello"])

    # Test fallback parsing when JSON is invalid
    @patch('backend.app.services.base_detect_service.log_warning')
    def test_parse_remove_words_invalid_json(self, mock_warn):
        s = 'apple, banana,, cherry'

        out = BaseDetectionService.parse_remove_words(s)

        self.assertEqual(out, ['apple', 'banana', 'cherry'])

        mock_warn.assert_called_once()

    # Test successful text extraction from PDF
    @patch('backend.app.services.base_detect_service.PDFTextExtractor')
    def test_extract_text_success(self, mock_ext):
        inst = mock_ext.return_value

        inst.extract_text.return_value = {'data': 123}

        extracted, error = BaseDetectionService.extract_text(b'pdf', 'file.pdf', 'op1')

        inst.close.assert_called_once()

        self.assertEqual(extracted, {'data': 123})

        self.assertIsNone(error)

    # Test handling of exceptions during PDF text extraction
    @patch('backend.app.services.base_detect_service.PDFTextExtractor')
    @patch('backend.app.services.base_detect_service.log_error')
    @patch('backend.app.services.base_detect_service.SecurityAwareErrorHandler.handle_safe_error')
    def test_extract_text_failure(self, mock_handle, mock_log_error, mock_ext):
        inst = mock_ext.return_value

        inst.extract_text.side_effect = RuntimeError('fail')

        mock_handle.return_value = {'err': 'handled'}

        extracted, error = BaseDetectionService.extract_text(b'pdf', 'file.pdf', 'op2')

        mock_log_error.assert_called_once()

        self.assertIsNone(extracted)

        self.assertIsInstance(error, JSONResponse)

        self.assertIn(b'err', error.body)

    # Test successful processing of requested entities
    @patch('backend.app.services.base_detect_service.validate_all_engines_requested_entities')
    def test_process_requested_entities_success(self, mock_valid):
        mock_valid.return_value = ['a', 'b']

        out, err = BaseDetectionService.process_requested_entities('["a"]', 'op1')

        self.assertEqual(out, ['a', 'b'])

        self.assertIsNone(err)

    # Test handling failure when processing requested entities
    @patch('backend.app.services.base_detect_service.validate_all_engines_requested_entities')
    @patch('backend.app.services.base_detect_service.log_warning')
    @patch('backend.app.services.base_detect_service.SecurityAwareErrorHandler.handle_safe_error')
    def test_process_requested_entities_failure(self, mock_handle, mock_warn, mock_valid):
        mock_valid.side_effect = ValueError('bad')

        mock_handle.return_value = {'error': 'yes'}

        out, err = BaseDetectionService.process_requested_entities('bad', 'op2')

        mock_warn.assert_called_once()

        self.assertIsNone(out)

        self.assertIsInstance(err, JSONResponse)

    # Test MIME validation passes for supported type
    def test_validate_mime_valid(self):
        file = DummyFile('application/pdf', 'f')

        resp = BaseDetectionService.validate_mime(file, 'op1')

        self.assertIsNone(resp)

    # Test MIME validation fails for unsupported type
    def test_validate_mime_invalid(self):
        file = DummyFile('text/plain', 'f')

        resp = BaseDetectionService.validate_mime(file, 'op1')

        self.assertIsInstance(resp, JSONResponse)

        self.assertEqual(resp.status_code, 415)

    # Test MIME validation handles exceptions gracefully
    @patch('backend.app.services.base_detect_service.log_warning')
    def test_validate_mime_exception(self, mock_warn):
        file = DummyFile(None, 'f')

        file.content_type = property(lambda self: (_ for _ in ()).throw(RuntimeError()))

        resp = BaseDetectionService.validate_mime(file, 'opx')

        self.assertEqual(resp.status_code, 500)

        mock_warn.assert_called_once()

    # Test detection times out correctly
    @patch('asyncio.wait_for', new_callable=lambda: AsyncMock(side_effect=asyncio.TimeoutError()))
    async def test_perform_detection_timeout(self, mock_wait):
        det = DummyDetector()

        res, err = await BaseDetectionService.perform_detection(det, {}, [], 1, 'op')

        self.assertIsNone(res)

        self.assertEqual(err.status_code, 408)

    # Test timeout handling ignores unawaited warnings
    @patch('asyncio.wait_for', new_callable=lambda: AsyncMock(side_effect=asyncio.TimeoutError()))
    async def test_perform_detection_with_timeout(self, mock_wait):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)

            det = DummyDetector()

            res, err = await BaseDetectionService.perform_detection(det, {}, [], 1, 'op')

        self.assertIsNone(res)

        self.assertEqual(err.status_code, 408)

    # Test async detection returns correct result
    async def test_perform_detection_async(self):
        det = DummyDetector()

        res, err = await BaseDetectionService.perform_detection(det, {}, [], 1, 'op')

        self.assertEqual(res, {'res': 'async'})

        self.assertIsNone(err)

    # Test detection exception is logged and returned as error
    @patch('backend.app.services.base_detect_service.log_error')
    async def test_perform_detection_exception(self, mock_log):
        det = DummyDetector()

        det.detect_sensitive_data_async = AsyncMock(side_effect=RuntimeError('boom'))

        res, err = await BaseDetectionService.perform_detection(det, {}, [], 1, 'op')

        mock_log.assert_called_once()

        self.assertIsNone(res)

        self.assertIsInstance(err, JSONResponse)

    # Test detection context preparation fails on MIME error
    @patch.object(BaseDetectionService, 'validate_mime', return_value=JSONResponse(status_code=415, content={}))
    async def test_prepare_detection_context_mime_error(self, mock_mime):
        file = DummyFile('x', 'f')

        out = await BaseDetectionService.prepare_detection_context(file, None, 'op', time.time())

        self.assertIsInstance(out[4], JSONResponse)

    # Test detection context preparation fails on entity processing error
    @patch.object(BaseDetectionService, 'validate_mime', return_value=None)
    @patch.object(BaseDetectionService, 'process_requested_entities',
                  return_value=(None, JSONResponse(status_code=400, content={})))
    async def test_prepare_detection_context_entity_error(self, mock_entities, mock_mime):
        file = DummyFile('a', 'b')

        out = await BaseDetectionService.prepare_detection_context(file, None, 'op', time.time())

        self.assertIsInstance(out[4], JSONResponse)

    # Test detection context preparation fails on file read error
    @patch.object(BaseDetectionService, 'validate_mime', return_value=None)
    @patch.object(BaseDetectionService, 'process_requested_entities', return_value=([], None))
    @patch('backend.app.services.base_detect_service.read_and_validate_file', new_callable=AsyncMock,
           return_value=(None, JSONResponse(status_code=500, content={}), 0))
    async def test_prepare_detection_context_read_error(self, mock_read, mock_proc, mock_mime):
        file = DummyFile('a', 'b')

        out = await BaseDetectionService.prepare_detection_context(file, None, 'op', time.time())

        self.assertIsInstance(out[4], JSONResponse)

    # Test detection context preparation fails on invalid file content
    @patch.object(BaseDetectionService, 'validate_mime', return_value=None)
    @patch.object(BaseDetectionService, 'process_requested_entities', return_value=([], None))
    @patch('backend.app.services.base_detect_service.read_and_validate_file', new_callable=AsyncMock,
           return_value=(b'c', None, 0))
    @patch('backend.app.services.base_detect_service.validate_file_content_async', new_callable=AsyncMock,
           return_value=(False, 'reason', None))
    async def test_prepare_detection_context_invalid_content(self, mock_validate_async, mock_read, mock_entities,
                                                             mock_mime):
        file = DummyFile('a', 'b')

        out = await BaseDetectionService.prepare_detection_context(file, None, 'op', time.time())

        self.assertIsInstance(out[4], JSONResponse)

    # Test successful preparation of detection context
    @patch.object(BaseDetectionService, 'validate_mime', return_value=None)
    @patch.object(BaseDetectionService, 'process_requested_entities', return_value=([], None))
    @patch('backend.app.services.base_detect_service.read_and_validate_file', new_callable=AsyncMock,
           return_value=(b'c', None, 0))
    @patch('backend.app.services.base_detect_service.validate_file_content_async', new_callable=AsyncMock,
           return_value=(True, '', None))
    @patch('backend.app.services.base_detect_service.BaseDetectionService.extract_text',
           return_value=({'pages': [{'words': ['w']}]}, None))
    async def test_prepare_detection_context_success(self, mock_extract, mock_validate_async, mock_read, mock_entities,
                                                     mock_mime):
        file = DummyFile('a', 'b')

        start = time.time()

        out = await BaseDetectionService.prepare_detection_context(file, None, 'op', start)

        self.assertIsNone(out[4])

        self.assertEqual(out[3]['file_read_time'], 0)

    # Test removal words are applied successfully
    @patch('backend.app.services.base_detect_service.BaseDetectionService.parse_remove_words', return_value=['x'])
    @patch('backend.app.services.base_detect_service.DetectionResultUpdater')
    def test_apply_removal_words_success(self, mock_upd, mock_parse):
        extracted = {'p': 1}

        det = ({'ent': 1}, {'map': 2})

        inst = mock_upd.return_value

        inst.update_result.return_value = {'redaction_mapping': {'m': 3}}

        ents, mapping = BaseDetectionService.apply_removal_words(extracted, det, 'a')

        self.assertEqual(mapping, {'m': 3})

    # Test handling errors in removal words parsing
    @patch('backend.app.services.base_detect_service.BaseDetectionService.parse_remove_words', side_effect=Exception())
    @patch('backend.app.services.base_detect_service.log_warning')
    def test_apply_removal_words_error(self, mock_warn, mock_parse):
        extracted = {}

        det = ({'ent': 1}, {'map': 2})

        ents, mapping = BaseDetectionService.apply_removal_words(extracted, det, 'a')

        mock_warn.assert_called_once()

        self.assertEqual(mapping, {'map': 2})

    # Test statistics computation when entities are present
    def test_compute_statistics_success_with_entities(self):
        data = {'pages': [{'words': [1, 2, 3]}, {'words': [4]}]}

        stats = BaseDetectionService.compute_statistics(data, [1, 2])

        self.assertIn('entity_density', stats)

        self.assertEqual(stats['pages_count'], 2)

    # Test statistics computation when no entities
    def test_compute_statistics_no_entities(self):
        data = {'pages': [{'words': [1, 2]}, {'words': []}]}

        stats = BaseDetectionService.compute_statistics(data, [])

        self.assertNotIn('entity_density', stats)

    # Test handling of failure in statistics computation
    @patch('backend.app.services.base_detect_service.log_warning')
    def test_compute_statistics_failure(self, mock_warn):
        stats = BaseDetectionService.compute_statistics(None, None)

        mock_warn.assert_called_once()

        self.assertEqual(stats, {})

    # Test applying score threshold filter to entities
    @patch('backend.app.services.base_detect_service.BaseEntityDetector.filter_by_score', return_value=[{'s': 1}])
    def test_apply_threshold_filter(self, mock_filter):
        ents, mapping = BaseDetectionService.apply_threshold_filter([{'s': 0.9}], {'pages': []}, 0.5)

        self.assertEqual(ents, [{'s': 1}])

    # Test final JSON response preparation with debug info
    @patch('backend.app.services.base_detect_service.BaseDetectionService.apply_threshold_filter',
           return_value=([1], {'pages': []}))
    @patch('backend.app.services.base_detect_service.sanitize_detection_output', return_value={'out': 1})
    @patch('backend.app.services.base_detect_service.memory_monitor.get_memory_stats',
           return_value={'current_usage': 10, 'peak_usage': 20})
    def test_prepare_final_response(self, mock_mem, mock_sanitize, mock_filter):
        file = DummyFile('application/pdf', 'f.pdf')

        content = b'data'

        resp = BaseDetectionService.prepare_final_response(file, content, [], {'pages': []}, {'t': 1}, 0.5, 'ENG')

        parsed = json.loads(resp.body.decode())

        self.assertIn('file_info', parsed)

        self.assertEqual(parsed['file_info']['filename'], 'f.pdf')

        self.assertEqual(parsed['model_info']['engine'], 'ENG')

        self.assertIn('memory_usage', parsed['_debug'])

        self.assertEqual(parsed['_debug']['memory_usage'], 10)
