import json
import unittest
from unittest.mock import patch, AsyncMock
from fastapi.responses import JSONResponse
from fastapi import HTTPException

from backend.app.services.ai_detect_service import AIDetectService


class DummyUploadFile:
    def __init__(self, filename="doc.pdf", content_type="application/pdf"):
        self.filename = filename

        self.content_type = content_type


class DummyDetector:
    @staticmethod
    async def detect_sensitive_data_async(data, entities):
        return ([{"text": "John"}], {"pages": []})


class DummyInitializationService:
    def get_gemini_detector(self):
        return DummyDetector()


class TestAIDetectService(unittest.IsolatedAsyncioTestCase):

    @patch("backend.app.services.ai_detect_service.log_info")
    @patch(
        "backend.app.services.ai_detect_service.BaseDetectionService.prepare_detection_context"
    )
    @patch(
        "backend.app.services.ai_detect_service.minimize_extracted_data",
        return_value="minimized",
    )
    @patch(
        "backend.app.services.ai_detect_service.initialization_service",
        new_callable=lambda: DummyInitializationService(),
    )
    @patch(
        "backend.app.services.ai_detect_service.AIDetectService.perform_detection",
        new_callable=AsyncMock,
    )
    @patch(
        "backend.app.services.ai_detect_service.replace_original_text_in_redaction",
        return_value={"pages": []},
    )
    @patch(
        "backend.app.services.ai_detect_service.BaseDetectionService.prepare_final_response",
        return_value=JSONResponse(content={"result": "ok"}),
    )
    @patch("backend.app.services.ai_detect_service.record_keeper.record_processing")
    @patch(
        "backend.app.services.ai_detect_service.BaseDetectionService.compute_statistics",
        return_value={"entity_density": 50},
    )
    async def test_detect_success(
        self,
        mock_stats,
        mock_record,
        mock_response,
        mock_replace,
        mock_detect,
        mock_init,
        mock_minimize,
        mock_context,
        mock_log,
    ):
        # Test successful detection returns JSONResponse with result "ok"
        file = DummyUploadFile()

        mock_context.return_value = (
            {"pages": [{"words": ["a"]}]},
            b"binary",
            ["NAME"],
            {},
            None,
        )

        mock_detect.return_value = (([{"text": "John"}], {"pages": []}), None)

        response = await AIDetectService().detect(file, requested_entities='["NAME"]')

        self.assertIsInstance(response, JSONResponse)

        self.assertEqual(json.loads(response.body.decode()), {"result": "ok"})

        mock_record.assert_called_once()

        mock_response.assert_called_once()

    @patch(
        "backend.app.services.ai_detect_service.BaseDetectionService.prepare_detection_context"
    )
    @patch(
        "backend.app.services.ai_detect_service.SecurityAwareErrorHandler.handle_safe_error"
    )
    async def test_detect_preparation_error(self, mock_safe_error, mock_context):
        file = DummyUploadFile()

        prep_exception = HTTPException(status_code=400, detail="prep error")

        mock_context.return_value = (None, None, None, None, prep_exception)

        mock_safe_error.return_value = {
            "error": "prep error",
            "error_type": "HTTPException",
            "error_id": "mock-id",
            "trace_id": "mock-trace",
            "timestamp": 123,
        }

        with self.assertRaises(HTTPException) as cm:
            await AIDetectService().detect(file, requested_entities=None)

        assert cm.exception.status_code == 500

        assert cm.exception.detail["error"] == "prep error"

    @patch(
        "backend.app.services.ai_detect_service.BaseDetectionService.prepare_detection_context"
    )
    @patch(
        "backend.app.services.ai_detect_service.minimize_extracted_data",
        return_value="minimized",
    )
    @patch(
        "backend.app.services.ai_detect_service.initialization_service",
        new_callable=lambda: DummyInitializationService(),
    )
    @patch(
        "backend.app.services.ai_detect_service.AIDetectService.perform_detection",
        new_callable=AsyncMock,
    )
    @patch(
        "backend.app.services.ai_detect_service.SecurityAwareErrorHandler.handle_safe_error"
    )
    async def test_detect_detection_error(
        self, mock_safe_error, mock_detect, mock_init, mock_min, mock_context
    ):
        file = DummyUploadFile()

        mock_context.return_value = ({"pages": []}, b"b", ["EMAIL"], {}, None)

        detection_exception = HTTPException(status_code=500, detail="detection failed")

        mock_detect.return_value = (None, detection_exception)

        mock_safe_error.return_value = {
            "error": "detection failed",
            "error_type": "HTTPException",
            "error_id": "mock-id",
            "trace_id": "mock-trace",
            "timestamp": 123,
        }

        with self.assertRaises(HTTPException) as cm:
            await AIDetectService().detect(file, requested_entities=None)

        assert cm.exception.status_code == 500

        assert cm.exception.detail["error"] == "detection failed"

    @patch(
        "backend.app.services.ai_detect_service.BaseDetectionService.prepare_detection_context"
    )
    @patch(
        "backend.app.services.ai_detect_service.minimize_extracted_data",
        return_value="minimized",
    )
    @patch(
        "backend.app.services.ai_detect_service.initialization_service",
        new_callable=lambda: DummyInitializationService(),
    )
    @patch(
        "backend.app.services.ai_detect_service.AIDetectService.perform_detection",
        new_callable=AsyncMock,
    )
    async def test_detect_no_results(
        self, mock_detect, mock_init, mock_min, mock_context
    ):
        # Test detection returns 500 error if no results returned
        file = DummyUploadFile()

        mock_context.return_value = ({"pages": []}, b"b", ["EMAIL"], {}, None)

        mock_detect.return_value = (None, None)

        with self.assertRaises(HTTPException) as cm:
            await AIDetectService().detect(file, requested_entities=None)

        detail = cm.exception.detail

        assert "Detection returned no results" in str(detail) or "error" in detail

    @patch(
        "backend.app.services.ai_detect_service.BaseDetectionService.prepare_detection_context"
    )
    @patch(
        "backend.app.services.ai_detect_service.minimize_extracted_data",
        return_value="minimized",
    )
    @patch(
        "backend.app.services.ai_detect_service.initialization_service",
        new_callable=lambda: DummyInitializationService(),
    )
    @patch(
        "backend.app.services.ai_detect_service.AIDetectService.perform_detection",
        new_callable=AsyncMock,
    )
    @patch(
        "backend.app.services.ai_detect_service.BaseDetectionService.prepare_final_response"
    )
    @patch(
        "backend.app.services.ai_detect_service.BaseDetectionService.compute_statistics",
        side_effect=Exception("boom"),
    )
    @patch(
        "backend.app.services.ai_detect_service.SecurityAwareErrorHandler.handle_safe_error",
        return_value={
            "error": "An error occurred",
            "error_type": "Exception",
            "error_id": "fake-id",
            "trace_id": "trace_123",
            "timestamp": 1234567890,
        },
    )
    async def test_detect_stats_exception(
        self,
        mock_safe_error,
        mock_stats,
        mock_response,
        mock_detect,
        mock_init,
        mock_min,
        mock_context,
    ):
        # Test detection returns safe error HTTPException when statistics computation fails
        file = DummyUploadFile()

        mock_context.return_value = (
            {"pages": [{"words": []}]},
            b"b",
            ["EMAIL"],
            {},
            None,
        )

        mock_detect.return_value = (([{"text": "John"}], {"pages": []}), None)

        with self.assertRaises(HTTPException) as cm:
            await AIDetectService().detect(file, requested_entities='["EMAIL"]')

        self.assertEqual(cm.exception.status_code, 500)

        self.assertIn("error_type", cm.exception.detail)

        self.assertEqual(cm.exception.detail["error_id"], "fake-id")
