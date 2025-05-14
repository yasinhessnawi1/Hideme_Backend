import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException
from backend.app.api.main import create_app

client = TestClient(create_app())


class TestAIDetectRouter:

    # Test successful AI detection with valid threshold
    @pytest.mark.asyncio
    @patch("backend.app.api.routes.ai_routes.session_manager.prepare_inputs")
    @patch("backend.app.api.routes.ai_routes.validate_threshold_score")
    @patch(
        "backend.app.services.ai_detect_service.AIDetectService.detect",
        new_callable=AsyncMock,
    )
    async def test_ai_detect_sensitive_success(
        self, mock_detect, mock_validate, mock_prepare_inputs
    ):
        mock_validate.return_value = None

        file_mock = MagicMock()

        mock_prepare_inputs.return_value = (
            [file_mock],
            {"requested_entities": None, "remove_words": None},
            None,
        )

        result_mock = MagicMock()

        result_mock.model_dump.return_value = {"status": "success", "data": "mock data"}

        mock_detect.return_value = result_mock

        files = {"file": ("test_file.pdf", b"file content", "application/pdf")}

        headers = {"raw-api-key": "mock_raw_api_key"}

        response = client.post(
            "/ai/detect", files=files, data={"threshold": 0.5}, headers=headers
        )

        assert response.status_code == 200

        assert response.json() == {"status": "success", "data": "mock data"}

        mock_validate.assert_called_once_with(0.5)

        mock_detect.assert_called_once()

        mock_prepare_inputs.assert_called_once()

    # Test invalid threshold raises 400 and no detection call
    @pytest.mark.asyncio
    @patch("backend.app.api.routes.ai_routes.session_manager.prepare_inputs")
    @patch("backend.app.api.routes.ai_routes.validate_threshold_score")
    @patch("backend.app.services.ai_detect_service.AIDetectService.detect")
    async def test_ai_detect_sensitive_invalid_threshold(
        self, mock_detect, mock_validate_threshold_score, mock_prepare_inputs
    ):
        mock_prepare_inputs.return_value = (
            [MagicMock()],
            {"requested_entities": None, "remove_words": None},
            None,
        )

        mock_validate_threshold_score.side_effect = HTTPException(
            status_code=400, detail="Invalid threshold"
        )

        files = {"file": ("test_file.pdf", b"file content", "application/pdf")}

        headers = {"raw-api-key": "mock_raw_api_key"}

        response = client.post(
            "/ai/detect", files=files, data={"threshold": 2.0}, headers=headers
        )

        assert response.status_code == 400

        assert "Invalid threshold" in response.text

        mock_validate_threshold_score.assert_called_once()

        mock_detect.assert_not_called()

    # Test internal errors are handled and mapped to HTTPException
    @pytest.mark.asyncio
    @patch("backend.app.api.routes.ai_routes.session_manager.prepare_inputs")
    @patch(
        "backend.app.api.routes.ai_routes.SecurityAwareErrorHandler.handle_safe_error"
    )
    @patch("backend.app.api.routes.ai_routes.validate_threshold_score")
    @patch("backend.app.services.ai_detect_service.AIDetectService.detect")
    async def test_ai_detect_sensitive_internal_error(
        self, mock_detect, mock_validate, mock_handle_safe_error, mock_prepare_inputs
    ):
        mock_prepare_inputs.return_value = (
            [MagicMock()],
            {"requested_entities": None, "remove_words": None},
            None,
        )

        mock_validate.return_value = None

        mock_detect.side_effect = Exception("Internal error")

        mock_handle_safe_error.side_effect = HTTPException(
            status_code=500,
            detail={
                "error": "Internal error",
                "error_id": "mock_id",
                "error_type": "Exception",
                "status": "error",
            },
        )

        files = {"file": ("test_file.pdf", b"file content", "application/pdf")}

        headers = {"raw-api-key": "mock_raw_api_key"}

        response = client.post(
            "/ai/detect", files=files, data={"threshold": 0.7}, headers=headers
        )

        assert response.status_code == 500

        assert response.json() == {
            "detail": {
                "error": "Internal error",
                "error_id": "mock_id",
                "error_type": "Exception",
                "status": "error",
            }
        }

        mock_validate.assert_called_once()

        mock_detect.assert_called_once()

        mock_handle_safe_error.assert_called_once()

    # Test default threshold validation error handling
    @pytest.mark.asyncio
    @patch("backend.app.api.routes.ai_routes.session_manager.prepare_inputs")
    async def test_ai_detect_sensitive_invalid_threshold_error_handling(
        self, mock_prepare_inputs
    ):
        mock_prepare_inputs.return_value = (
            [MagicMock()],
            {"requested_entities": None, "remove_words": None},
            None,
        )

        files = {"file": ("test_file.pdf", b"file content", "application/pdf")}

        headers = {"raw-api-key": "mock_raw_api_key"}

        response = client.post(
            "/ai/detect", files=files, data={"threshold": -10}, headers=headers
        )

        assert response.status_code == 400

        json_data = response.json()

        assert "Threshold must be between 0.00 and 1.00" in json_data["error"]

        assert json_data["status"] == "error"
