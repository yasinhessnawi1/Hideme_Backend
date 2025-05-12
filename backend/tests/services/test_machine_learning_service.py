import json
import unittest
from unittest.mock import patch, AsyncMock
from fastapi.responses import JSONResponse
from fastapi import HTTPException

from backend.app.services.machine_learning_service import MashinLearningService


# Dummy upload file object for testing detection service
class DummyUploadFile:
    filename = "doc.pdf"

    content_type = "application/pdf"


# Dummy detector simulating async sensitive data detection
class DummyDetector:

    async def detect_sensitive_data_async(self, data, entities):
        return [{"text": "john"}], {"pages": []}


# Dummy initialization service providing detectors
class DummyInit:

    def get_presidio_detector(self):
        return DummyDetector()

    def get_gliner_detector(self, x):
        return DummyDetector()

    def get_hideme_detector(self, x):
        return DummyDetector()


# Test suite for MashinLearningService
class TestMashinLearningService(unittest.IsolatedAsyncioTestCase):

    # Test successful detection using Presidio engine
    @patch(
        "backend.app.services.machine_learning_service.BaseDetectionService.prepare_detection_context"
    )
    @patch(
        "backend.app.services.machine_learning_service.minimize_extracted_data",
        return_value="min",
    )
    @patch(
        "backend.app.services.machine_learning_service.initialization_service",
        new_callable=lambda: DummyInit(),
    )
    @patch(
        "backend.app.services.machine_learning_service.MashinLearningService.perform_detection",
        new_callable=AsyncMock,
    )
    @patch(
        "backend.app.services.machine_learning_service.BaseDetectionService.compute_statistics",
        return_value={},
    )
    @patch(
        "backend.app.services.machine_learning_service.replace_original_text_in_redaction",
        return_value={"pages": []},
    )
    @patch(
        "backend.app.services.machine_learning_service.BaseDetectionService.prepare_final_response",
        return_value=JSONResponse(content={"done": True}),
    )
    @patch(
        "backend.app.services.machine_learning_service.record_keeper.record_processing"
    )
    @patch("backend.app.services.machine_learning_service.log_info")
    async def test_detect_success_presidio(
        self,
        mock_log,
        mock_record,
        mock_response,
        mock_replace,
        mock_stats,
        mock_detect,
        mock_init,
        mock_minimize,
        mock_context,
    ):
        mock_context.return_value = (
            {"pages": [{"words": ["a"]}]},
            b"bytes",
            ["NAME"],
            {},
            None,
        )

        mock_detect.return_value = (([{"text": "john"}], {"pages": []}), None)

        svc = MashinLearningService("presidio")

        file = DummyUploadFile()

        res = await svc.detect(file, requested_entities='["NAME"]', operation_id="op")

        self.assertEqual(json.loads(res.body.decode()), {"done": True})

        mock_record.assert_called_once()

        mock_response.assert_called_once()

    # Test handling error in prepare_detection_context
    @patch(
        "backend.app.services.machine_learning_service.BaseDetectionService.prepare_detection_context",
        return_value=(
            None,
            None,
            None,
            None,
            HTTPException(status_code=500, detail={"err": True}),
        ),
    )
    async def test_detect_prepare_context_error(self, mock_context):
        svc = MashinLearningService("gliner")

        file = DummyUploadFile()

        with self.assertRaises(HTTPException) as ctx:
            await svc.detect(file, requested_entities='["EMAIL"]', operation_id="op")

        self.assertEqual(ctx.exception.status_code, 500)

        self.assertIn("err", str(ctx.exception.detail))

    # Test unsupported detector type returns bad request
    @patch(
        "backend.app.services.machine_learning_service.BaseDetectionService.prepare_detection_context",
        return_value=({"pages": [{"words": ["a"]}]}, b"bin", ["EMAIL"], {}, None),
    )
    async def test_detect_unsupported_detector_type(self, mock_ctx):
        svc = MashinLearningService("unsupported")

        file = DummyUploadFile()

        with self.assertRaises(HTTPException) as ctx:
            await svc.detect(file, requested_entities=None, operation_id="op")

        exc = ctx.exception

        self.assertEqual(exc.status_code, 500)

        self.assertIn("Missing required attribute", str(exc.detail))

    # Test detection returns 500 when perform_detection yields no result
    @patch(
        "backend.app.services.machine_learning_service.SecurityAwareErrorHandler.handle_safe_error",
        return_value={
            "error": "Detection returned no results",
            "error_type": "HTTPException",
        },
    )
    @patch(
        "backend.app.services.machine_learning_service.BaseDetectionService.prepare_detection_context"
    )
    @patch(
        "backend.app.services.machine_learning_service.minimize_extracted_data",
        return_value="min",
    )
    @patch(
        "backend.app.services.machine_learning_service.initialization_service",
        new_callable=lambda: DummyInit(),
    )
    @patch(
        "backend.app.services.machine_learning_service.MashinLearningService.perform_detection",
        new_callable=AsyncMock,
    )
    async def test_detect_none_result(
        self, mock_detect, mock_init, mock_min, mock_ctx, mock_safe_error
    ):
        mock_ctx.return_value = (
            {"pages": [{"words": ["a"]}]},
            b"bytes",
            ["EMAIL"],
            {},
            None,
        )
        mock_detect.return_value = (None, None)

        svc = MashinLearningService("presidio")
        file = DummyUploadFile()

        with self.assertRaises(HTTPException) as context:
            await svc.detect(file, '["EMAIL"]', "op")

        self.assertEqual(context.exception.status_code, 500)

        error_detail = context.exception.detail

        self.assertIsInstance(error_detail, dict)

        self.assertIn("Detection returned no results", error_detail.get("error", ""))

    # Test exception during minimize_extracted_data is caught
    @patch(
        "backend.app.services.machine_learning_service.BaseDetectionService.prepare_detection_context"
    )
    @patch(
        "backend.app.services.machine_learning_service.minimize_extracted_data",
        side_effect=Exception("fail"),
    )
    async def test_detect_exception_handling(self, mock_min, mock_ctx):
        svc = MashinLearningService("presidio")

        file = DummyUploadFile()

        mock_ctx.return_value = ({}, b"bytes", [], {}, None)

        with self.assertRaises(HTTPException) as context:
            await svc.detect(file, None, "op")

        self.assertEqual(context.exception.status_code, 500)

        self.assertIn("error_type", str(context.exception.detail))

    # Test statistics computation crash is handled and safe error returned
    @patch(
        "backend.app.services.machine_learning_service.SecurityAwareErrorHandler.handle_safe_error",
        return_value={"error": "mocked", "error_type": "Exception"},
    )
    @patch(
        "backend.app.services.machine_learning_service.BaseDetectionService.compute_statistics",
        side_effect=Exception("statistics failed"),
    )
    @patch(
        "backend.app.services.machine_learning_service.MashinLearningService.perform_detection",
        new_callable=AsyncMock,
    )
    @patch(
        "backend.app.services.machine_learning_service.initialization_service",
        new_callable=lambda: DummyInit(),
    )
    @patch(
        "backend.app.services.machine_learning_service.minimize_extracted_data",
        return_value="min",
    )
    @patch(
        "backend.app.services.machine_learning_service.BaseDetectionService.prepare_detection_context"
    )
    async def test_detect_statistics_crash_still_returns(
        self, mock_ctx, mock_min, mock_init, mock_detect, mock_stats, mock_safe_error
    ):
        mock_ctx.return_value = (
            {"pages": [{"words": ["x"]}]},
            b"bin",
            ["EMAIL"],
            {},
            None,
        )

        mock_detect.return_value = (([{"text": "john"}], {"pages": []}), None)

        svc = MashinLearningService("gliner")

        file = DummyUploadFile()

        with self.assertRaises(HTTPException) as ctx:
            await svc.detect(file, '["EMAIL"]', "op")

        exc = ctx.exception

        self.assertEqual(exc.status_code, 500)

        self.assertEqual(exc.detail["error"], "mocked")

        self.assertEqual(exc.detail["error_type"], "Exception")
