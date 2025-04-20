import pytest

from fastapi.testclient import TestClient

from unittest.mock import patch

from fastapi import HTTPException

from backend.app.api.main import create_app

client = TestClient(create_app())


class TestAIDetectRouter:

    # Test successful AI detection with valid threshold
    @pytest.mark.asyncio
    @patch("backend.app.services.ai_detect_service.AIDetectService.detect")
    @patch("backend.app.api.routes.ai_routes.validate_threshold_score")
    async def test_ai_detect_sensitive_success(self, mock_validate_threshold_score, mock_detect):
        mock_validate_threshold_score.return_value = None
        mock_detect.return_value = {"status": "success", "data": "mock data"}

        files = {'file': ('test_file.pdf', b"file content", 'application/pdf')}

        response = client.post("/ai/detect", files=files, data={'threshold': 0.5})

        # Ensure the threshold validation was called
        mock_validate_threshold_score.assert_called_once_with(0.5)

        assert response.status_code == 200

        assert response.json() == {"status": "success", "data": "mock data"}

        mock_detect.assert_called_once()

    # Test invalid threshold raises 400 and no detection call
    @pytest.mark.asyncio
    @patch("backend.app.services.ai_detect_service.AIDetectService.detect")
    @patch("backend.app.api.routes.ai_routes.validate_threshold_score")
    async def test_ai_detect_sensitive_invalid_threshold(self, mock_validate_threshold_score, mock_detect):
        mock_validate_threshold_score.side_effect = HTTPException(status_code=400, detail="Invalid threshold")

        files = {'file': ('test_file.pdf', b"file content", 'application/pdf')}

        response = client.post("/ai/detect", files=files, data={'threshold': 2.0})

        assert response.status_code == 400

        assert "Invalid threshold" in response.text

        mock_validate_threshold_score.assert_called_once()

        mock_detect.assert_not_called()

    # Test internal errors are handled and mapped to HTTPException
    @pytest.mark.asyncio
    @patch("backend.app.services.ai_detect_service.AIDetectService.detect")
    @patch("backend.app.api.routes.ai_routes.validate_threshold_score")
    @patch("backend.app.api.routes.ai_routes.SecurityAwareErrorHandler.handle_safe_error")
    async def test_ai_detect_sensitive_internal_error(self, mock_handle_safe_error, mock_validate_threshold_score,
                                                      mock_detect):
        mock_validate_threshold_score.return_value = None
        mock_detect.side_effect = Exception("Internal error")

        mock_handle_safe_error.side_effect = HTTPException(
            status_code=500,
            detail={
                "error": "Internal error",
                "error_id": "mock_id",
                "error_type": "Exception",
                "status": "error"
            }
        )

        files = {'file': ('test_file.pdf', b"file content", 'application/pdf')}

        response = client.post("/ai/detect", files=files, data={'threshold': 0.7})

        assert response.status_code == 500

        assert response.json() == {
            "detail": {
                "error": "Internal error",
                "error_id": "mock_id",
                "error_type": "Exception",
                "status": "error"
            }
        }

        mock_validate_threshold_score.assert_called_once()

        mock_detect.assert_called_once()

        mock_handle_safe_error.assert_called_once()

    # Test default threshold validation error handling
    @pytest.mark.asyncio
    async def test_ai_detect_sensitive_invalid_threshold_error_handling(self):
        files = {'file': ('test_file.pdf', b"file content", 'application/pdf')}

        response = client.post("/ai/detect", files=files, data={'threshold': -10})

        assert response.status_code == 400

        assert response.json() == {
            'detail': 'Threshold must be between 0.00 and 1.00.'
        }
