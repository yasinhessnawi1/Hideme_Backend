import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from backend.app.api.main import create_app

client = TestClient(create_app())


class TestMachineLearningRouter:

    # Presidio detection succeeds with valid threshold
    @pytest.mark.asyncio
    @patch("backend.app.services.machine_learning_service.MashinLearningService.detect")
    @patch("backend.app.api.routes.machine_learning.validate_threshold_score")
    async def test_presidio_detect_success(
        self, mock_validate_threshold_score, mock_detect
    ):
        mock_validate_threshold_score.return_value = None

        mock_result = MagicMock()

        mock_result.model_dump.return_value = {"status": "success", "data": "mock data"}

        mock_detect.return_value = mock_result

        files = {"file": ("test_file.pdf", b"file content", "application/pdf")}

        response = client.post("/ml/detect", files=files, data={"threshold": 0.5})

        mock_validate_threshold_score.assert_called_once_with(0.5)

        assert response.status_code == 200

        assert response.json() == {"status": "success", "data": "mock data"}

        mock_detect.assert_called_once()

    # Invalid threshold in Presidio detection returns 400
    @pytest.mark.asyncio
    @patch("backend.app.services.machine_learning_service.MashinLearningService.detect")
    @patch("backend.app.api.routes.machine_learning.validate_threshold_score")
    async def test_presidio_detect_invalid_threshold(
        self, mock_validate_threshold_score, mock_detect
    ):
        mock_validate_threshold_score.side_effect = HTTPException(
            status_code=400, detail="Invalid threshold"
        )

        files = {"file": ("test_file.pdf", b"file content", "application/pdf")}

        response = client.post("/ml/detect", files=files, data={"threshold": 2.0})

        assert response.status_code == 400

        assert "Invalid threshold" in response.text

        mock_validate_threshold_score.assert_called_once()

        mock_detect.assert_not_called()

    # Internal error in Presidio detection is handled and returns 500
    @pytest.mark.asyncio
    @patch("backend.app.services.machine_learning_service.MashinLearningService.detect")
    @patch(
        "backend.app.api.routes.machine_learning.SecurityAwareErrorHandler.handle_safe_error"
    )
    async def test_presidio_detect_internal_error(
        self, mock_handle_safe_error, mock_detect
    ):
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

        response = client.post("/ml/detect", files=files, data={"threshold": 0.7})

        assert response.status_code == 500

        assert response.json() == {
            "detail": {
                "error": "Internal error",
                "error_id": "mock_id",
                "error_type": "Exception",
                "status": "error",
            }
        }

        mock_handle_safe_error.assert_called_once()

        mock_detect.assert_called_once()

    # Default invalid threshold handling returns detailed error payload
    @pytest.mark.asyncio
    async def test_presidio_detect_invalid_threshold_error_handling(self):
        files = {"file": ("test_file.pdf", b"file content", "application/pdf")}

        response = client.post("/ml/detect", files=files, data={"threshold": -10})

        assert response.status_code == 400

        response_json = response.json()

        assert "Threshold must be between 0.00 and 1.00." in response_json.get(
            "error", ""
        )

        assert "error_id" in response_json

        assert "trace_id" in response_json

        assert "status" in response_json

        assert "error_type" in response_json

        assert "status_code" in response_json

    # GLiNER detection succeeds with valid threshold
    @pytest.mark.asyncio
    @patch("backend.app.services.machine_learning_service.MashinLearningService.detect")
    async def test_gliner_detect_success(self, mock_detect):
        mock_result = MagicMock()

        mock_result.model_dump.return_value = {"status": "success", "data": "mock data"}

        mock_detect.return_value = mock_result

        files = {"file": ("test_file.pdf", b"file content", "application/pdf")}

        response = client.post("/ml/gl_detect", files=files, data={"threshold": 0.5})

        assert response.status_code == 200

        assert response.json() == {"status": "success", "data": "mock data"}

        mock_detect.assert_called_once()

    # Invalid threshold in GLiNER detection returns 400
    @pytest.mark.asyncio
    @patch("backend.app.services.machine_learning_service.MashinLearningService.detect")
    @patch("backend.app.api.routes.machine_learning.validate_threshold_score")
    async def test_gliner_detect_invalid_threshold(
        self, mock_validate_threshold_score, mock_detect
    ):
        mock_validate_threshold_score.side_effect = HTTPException(
            status_code=400, detail="Invalid threshold"
        )

        files = {"file": ("test_file.pdf", b"file content", "application/pdf")}

        response = client.post("/ml/gl_detect", files=files, data={"threshold": 2.0})

        assert response.status_code == 400

        assert "Invalid threshold" in response.text

        mock_validate_threshold_score.assert_called_once()

        mock_detect.assert_not_called()

    # Internal error in GLiNER detection is handled and returns 500
    @pytest.mark.asyncio
    @patch("backend.app.services.machine_learning_service.MashinLearningService.detect")
    @patch(
        "backend.app.api.routes.machine_learning.SecurityAwareErrorHandler.handle_safe_error"
    )
    async def test_gliner_detect_internal_error(
        self, mock_handle_safe_error, mock_detect
    ):
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

        response = client.post("/ml/gl_detect", files=files, data={"threshold": 0.7})

        assert response.status_code == 500

        assert response.json() == {
            "detail": {
                "error": "Internal error",
                "error_id": "mock_id",
                "error_type": "Exception",
                "status": "error",
            }
        }

        mock_handle_safe_error.assert_called_once()

    # HIDEME detection succeeds with valid threshold
    @pytest.mark.asyncio
    @patch("backend.app.services.machine_learning_service.MashinLearningService.detect")
    async def test_hideme_detect_success(self, mock_detect):
        mock_result = MagicMock()

        mock_result.model_dump.return_value = {"status": "success", "data": "mock data"}

        mock_detect.return_value = mock_result

        files = {"file": ("test_file.pdf", b"file content", "application/pdf")}

        response = client.post("/ml/hm_detect", files=files, data={"threshold": 0.5})

        assert response.status_code == 200

        assert response.json() == {"status": "success", "data": "mock data"}

        mock_detect.assert_called_once()

    # Invalid threshold in HIDEME detection returns 400
    @pytest.mark.asyncio
    @patch("backend.app.services.machine_learning_service.MashinLearningService.detect")
    @patch("backend.app.api.routes.machine_learning.validate_threshold_score")
    async def test_hideme_detect_invalid_threshold(
        self, mock_validate_threshold_score, mock_detect
    ):
        mock_validate_threshold_score.side_effect = HTTPException(
            status_code=400, detail="Invalid threshold"
        )

        files = {"file": ("test_file.pdf", b"file content", "application/pdf")}

        response = client.post("/ml/hm_detect", files=files, data={"threshold": 2.0})

        assert response.status_code == 400

        assert "Invalid threshold" in response.text

        mock_validate_threshold_score.assert_called_once()

        mock_detect.assert_not_called()

    # Internal error in HIDEME detection is handled and returns 500
    @pytest.mark.asyncio
    @patch("backend.app.services.machine_learning_service.MashinLearningService.detect")
    @patch(
        "backend.app.api.routes.machine_learning.SecurityAwareErrorHandler.handle_safe_error"
    )
    async def test_hideme_detect_internal_error(
        self, mock_handle_safe_error, mock_detect
    ):
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

        response = client.post("/ml/hm_detect", files=files, data={"threshold": 0.7})

        assert response.status_code == 500

        assert response.json() == {
            "detail": {
                "error": "Internal error",
                "error_id": "mock_id",
                "error_type": "Exception",
                "status": "error",
            }
        }

        mock_handle_safe_error.assert_called_once()
