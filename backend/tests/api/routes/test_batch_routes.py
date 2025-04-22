import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from fastapi import HTTPException
from backend.app.api.main import create_app

client = TestClient(create_app())


class TestBatchRoutes:

    # Successful batch detect with valid threshold
    @pytest.mark.asyncio
    @patch("backend.app.services.batch_detect_service.BatchDetectService.detect_entities_in_files")
    async def test_batch_detect_success(self, mock_detect):
        mock_detect.return_value = {"status": "success", "data": "mock data"}

        files = {
            'files': ('test_file.pdf', b"file content", 'application/pdf')
        }

        data = {
            'threshold': '0.5'
        }

        response = client.post("/batch/detect", files=files, data=data)

        assert response.status_code == 200

        assert response.json() == {"status": "success", "data": "mock data"}

        mock_detect.assert_called_once()

    # Invalid threshold returns 400 and no detect call
    @pytest.mark.asyncio
    @patch("backend.app.services.batch_detect_service.BatchDetectService.detect_entities_in_files")
    @patch("backend.app.api.routes.batch_routes.validate_threshold_score")
    async def test_batch_detect_invalid_threshold(self, mock_validate_threshold_score, mock_detect):
        mock_validate_threshold_score.side_effect = HTTPException(status_code=400, detail="Invalid threshold")

        files = {
            'files': ('test_file.pdf', b"file content", 'application/pdf')
        }

        response = client.post("/batch/detect", files=files, data={'threshold': 2.0})

        assert response.status_code == 400

        assert "Invalid threshold" in response.text

        mock_validate_threshold_score.assert_called_once()

        mock_detect.assert_not_called()

    # Internal service error is handled and returns 500
    @pytest.mark.asyncio
    @patch("backend.app.services.batch_detect_service.BatchDetectService.detect_entities_in_files")
    @patch("backend.app.api.routes.batch_routes.SecurityAwareErrorHandler.handle_safe_error")
    async def test_batch_detect_internal_error(self, mock_handle_safe_error, mock_detect):
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

        files = {
            'files': ('test_file.pdf', b"file content", 'application/pdf')
        }

        response = client.post("/batch/detect", files=files, data={'threshold': 0.7})

        assert response.status_code == 500

        assert response.json() == {
            "detail": {
                "error": "Internal error",
                "error_id": "mock_id",
                "error_type": "Exception",
                "status": "error"
            }
        }

        mock_handle_safe_error.assert_called_once()

        mock_detect.assert_called_once()

    # Default threshold validation error returns detailed payload
    @pytest.mark.asyncio
    async def test_batch_detect_invalid_threshold_error_handling(self):
        files = {
            'files': ('test_file.pdf', b"file content", 'application/pdf')
        }

        response = client.post("/batch/detect", files=files, data={'threshold': -10})

        assert response.status_code == 400

        response_json = response.json()

        assert "Threshold must be between 0.00 and 1.00." in response_json.get("error", "")

        assert "error_id" in response_json

        assert "trace_id" in response_json

        assert "status" in response_json

        assert "error_type" in response_json

        assert "status_code" in response_json

    # Successful batch hybrid detect with valid threshold
    @pytest.mark.asyncio
    @patch("backend.app.services.batch_detect_service.BatchDetectService.detect_entities_in_files")
    async def test_batch_hybrid_detect_success(self, mock_detect):
        mock_detect.return_value = {"status": "success", "data": "mock data"}

        files = {
            'files': ('test_file.pdf', b"file content", 'application/pdf')
        }

        response = client.post("/batch/hybrid_detect", files=files, data={'threshold': 0.5})

        assert response.status_code == 200

        assert response.json() == {"status": "success", "data": "mock data"}

        mock_detect.assert_called_once()

    # Invalid threshold for hybrid detect returns 400
    @pytest.mark.asyncio
    @patch("backend.app.services.batch_detect_service.BatchDetectService.detect_entities_in_files")
    @patch("backend.app.api.routes.batch_routes.validate_threshold_score")
    async def test_batch_hybrid_detect_invalid_threshold(self, mock_validate_threshold_score, mock_detect):
        mock_validate_threshold_score.side_effect = HTTPException(status_code=400, detail="Invalid threshold")

        files = {
            'files': ('test_file.pdf', b"file content", 'application/pdf')
        }

        response = client.post("/batch/hybrid_detect", files=files, data={'threshold': 2.0})

        assert response.status_code == 400

        assert "Invalid threshold" in response.text

        mock_validate_threshold_score.assert_called_once()

        mock_detect.assert_not_called()

    # Internal error in hybrid detect returns 500
    @pytest.mark.asyncio
    @patch("backend.app.services.batch_detect_service.BatchDetectService.detect_entities_in_files")
    @patch("backend.app.api.routes.batch_routes.SecurityAwareErrorHandler.handle_safe_error")
    async def test_batch_hybrid_detect_internal_error(self, mock_handle_safe_error, mock_detect):
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

        files = {
            'files': ('test_file.pdf', b"file content", 'application/pdf')
        }

        response = client.post("/batch/hybrid_detect", files=files, data={'threshold': 0.7})

        assert response.status_code == 500

        assert response.json() == {
            "detail": {
                "error": "Internal error",
                "error_id": "mock_id",
                "error_type": "Exception",
                "status": "error"
            }
        }

        mock_handle_safe_error.assert_called_once()

    # Successful batch search with search terms
    @pytest.mark.asyncio
    @patch("backend.app.services.batch_search_service.BatchSearchService.batch_search_text")
    async def test_batch_search_success(self, mock_search):
        mock_search.return_value = {"status": "success", "data": "mock data"}

        files = {
            'files': ('test_file.pdf', b"file content", 'application/pdf')
        }

        response = client.post("/batch/search", files=files, data={'search_terms': 'test'})

        assert response.status_code == 200

        assert response.json() == {"status": "success", "data": "mock data"}

        mock_search.assert_called_once()

    # Successful find words by bounding box
    @pytest.mark.asyncio
    @patch("backend.app.services.batch_search_service.BatchSearchService.find_words_by_bbox")
    async def test_batch_find_words_success(self, mock_find):
        mock_find.return_value = {"status": "success", "data": "mock data"}

        files = {
            'files': ('test_file.pdf', b"file content", 'application/pdf')
        }

        response = client.post(
            "/batch/find_words",
            files=files,
            data={'bounding_box': '{"x0": 0, "y0": 0, "x1": 10, "y1": 10}'}
        )

        assert response.status_code == 200

        assert response.json() == {"status": "success", "data": "mock data"}

        mock_find.assert_called_once()

    # Invalid bounding box returns 400 detail error
    @pytest.mark.asyncio
    async def test_batch_find_words_invalid_bbox(self):
        files = {
            'files': ('test_file.pdf', b"file content", 'application/pdf')
        }

        response = client.post(
            "/batch/find_words",
            files=files,
            data={'bounding_box': '{"x0": 0, "y0": 0, "x1": 10}'}
        )

        assert response.status_code == 400

        assert response.json() == {'detail': 'Invalid bounding box format.'}

    # Successful batch redaction with mappings
    @pytest.mark.asyncio
    @patch("backend.app.services.batch_redact_service.BatchRedactService.batch_redact_documents")
    async def test_batch_redact_success(self, mock_redact):
        mock_redact.return_value = {"status": "success", "data": "mock data"}

        files = {
            'files': ('test_file.pdf', b"file content", 'application/pdf')
        }

        response = client.post(
            "/batch/redact",
            files=files,
            data={'redaction_mappings': '{"sensitive": "redacted"}'}
        )

        assert response.status_code == 200

        assert response.json() == {"status": "success", "data": "mock data"}

        mock_redact.assert_called_once()

    # Internal error in batch search returns 500 with details
    @pytest.mark.asyncio
    @patch("backend.app.services.batch_search_service.BatchSearchService.batch_search_text")
    @patch("backend.app.api.routes.batch_routes.SecurityAwareErrorHandler.handle_safe_error")
    async def test_batch_search_text_internal_error(self, mock_handle_safe_error, mock_batch_search_text):
        mock_batch_search_text.side_effect = Exception("Internal error in batch search")

        mock_handle_safe_error.side_effect = HTTPException(
            status_code=500,
            detail={
                "error": "Internal error",
                "error_id": "mock_id",
                "error_type": "Exception",
                "status": "error"
            }
        )

        files = {
            'files': ('test_file.pdf', b"file content", 'application/pdf')
        }

        response = client.post("/batch/search", files=files, data={'search_terms': 'sensitive'})

        assert response.status_code == 500

        assert response.json() == {
            "detail": {
                "error": "Internal error",
                "error_id": "mock_id",
                "error_type": "Exception",
                "status": "error"
            }
        }

        mock_handle_safe_error.assert_called_once()

        mock_batch_search_text.assert_called_once()

    # Internal error in find words returns 500 with details
    @pytest.mark.asyncio
    @patch("backend.app.services.batch_search_service.BatchSearchService.find_words_by_bbox")
    @patch("backend.app.api.routes.batch_routes.SecurityAwareErrorHandler.handle_safe_error")
    async def test_batch_find_words_internal_error(self, mock_handle_safe_error, mock_find_words_by_bbox):
        mock_find_words_by_bbox.side_effect = Exception("Error in find words by bounding box")

        mock_handle_safe_error.side_effect = HTTPException(
            status_code=500,
            detail={
                "error": "Error in find words by bounding box",
                "error_id": "mock_id",
                "error_type": "Exception",
                "status": "error"
            }
        )

        files = {
            'files': ('test_file.pdf', b"file content", 'application/pdf')
        }

        response = client.post(
            "/batch/find_words",
            files=files,
            data={'bounding_box': '{"x0": 0, "y0": 0, "x1": 100, "y1": 100}'}
        )

        assert response.status_code == 500

        assert response.json() == {
            "detail": {
                "error": "Error in find words by bounding box",
                "error_id": "mock_id",
                "error_type": "Exception",
                "status": "error"
            }
        }

        mock_handle_safe_error.assert_called_once()

        mock_find_words_by_bbox.assert_called_once()

    # Internal error in batch redaction returns 500 with details
    @pytest.mark.asyncio
    @patch("backend.app.services.batch_redact_service.BatchRedactService.batch_redact_documents")
    @patch("backend.app.api.routes.batch_routes.SecurityAwareErrorHandler.handle_safe_error")
    async def test_batch_redact_documents_internal_error(self, mock_handle_safe_error, mock_batch_redact_documents):
        mock_batch_redact_documents.side_effect = Exception("Error in batch redaction")

        mock_handle_safe_error.side_effect = HTTPException(
            status_code=500,
            detail={
                "error": "Error in batch redaction",
                "error_id": "mock_id",
                "error_type": "Exception",
                "status": "error"
            }
        )

        files = {
            'files': ('test_file.pdf', b"file content", 'application/pdf')
        }

        response = client.post(
            "/batch/redact",
            files=files,
            data={'redaction_mappings': '{"sensitive": "REDACTED"}'}
        )

        assert response.status_code == 500

        assert response.json() == {
            "detail": {
                "error": "Error in batch redaction",
                "error_id": "mock_id",
                "error_type": "Exception",
                "status": "error"
            }
        }

        mock_handle_safe_error.assert_called_once()

        mock_batch_redact_documents.assert_called_once()
