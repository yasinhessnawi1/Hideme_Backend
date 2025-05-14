import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from fastapi import HTTPException, Response
from backend.app.api.main import create_app
from backend.app.utils.security.caching_middleware import response_cache

client = TestClient(create_app())


class TestPdfRoutes:

    @pytest.mark.asyncio
    @patch("backend.app.api.routes.pdf_routes.session_manager.prepare_inputs")
    @patch(
        "backend.app.services.document_redact_service.DocumentRedactionService.redact"
    )
    async def test_pdf_redact_success(self, mock_redact, mock_prepare_inputs):
        mock_redact.return_value = Response(
            content=b"Redacted PDF content", media_type="application/pdf"
        )

        mock_prepare_inputs.return_value = (
            [MagicMock()],
            {"redaction_mapping": '{"sensitive": "REDACTED"}'},
            None,
        )

        files = {"file": ("test_file.pdf", b"file content", "application/pdf")}

        headers = {"raw-api-key": "mock_key"}

        response = client.post(
            "/pdf/redact",
            files=files,
            data={"redaction_mapping": '{"sensitive": "REDACTED"}'},
            headers=headers,
        )
        assert response.status_code == 200

        assert response.content == b"Redacted PDF content"

        mock_redact.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.app.api.routes.pdf_routes.session_manager.prepare_inputs")
    @patch(
        "backend.app.services.document_redact_service.DocumentRedactionService.redact"
    )
    @patch(
        "backend.app.api.routes.pdf_routes.SecurityAwareErrorHandler.handle_safe_error"
    )
    async def test_pdf_redact_internal_error(
        self, mock_handle_safe_error, mock_redact, mock_prepare_inputs
    ):
        response_cache.clear()

        mock_prepare_inputs.return_value = (
            [MagicMock()],
            {"redaction_mapping": '{"sensitive": "REDACTED"}'},
            None,
        )

        mock_redact.side_effect = Exception("Internal error in redaction service")

        mock_handle_safe_error.side_effect = HTTPException(
            status_code=500,
            detail={
                "error": "Internal error in redaction service",
                "error_id": "mock_id",
                "error_type": "Exception",
                "status": "error",
            },
        )

        files = {"file": ("test_file.pdf", b"file content", "application/pdf")}

        headers = {"raw-api-key": "mock_key"}

        response = client.post(
            "/pdf/redact",
            files=files,
            data={"redaction_mapping": '{"sensitive": "REDACTED"}'},
            headers=headers,
        )

        assert response.status_code == 500

        assert response.json() == {
            "detail": {
                "error": "Internal error in redaction service",
                "error_id": "mock_id",
                "error_type": "Exception",
                "status": "error",
            }
        }

        mock_handle_safe_error.assert_called_once()

        mock_redact.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.app.api.routes.pdf_routes.session_manager.prepare_inputs")
    @patch(
        "backend.app.services.document_redact_service.DocumentRedactionService.redact"
    )
    async def test_pdf_redact_invalid_mapping(self, mock_redact, mock_prepare_inputs):
        response_cache.clear()

        mock_prepare_inputs.return_value = (
            [MagicMock()],
            {"redaction_mapping": "invalid"},
            None,
        )

        mock_redact.side_effect = HTTPException(
            status_code=400, detail="Invalid redaction mapping"
        )

        files = {"file": ("test_file.pdf", b"file content", "application/pdf")}

        headers = {"raw-api-key": "mock_key"}

        response = client.post(
            "/pdf/redact",
            files=files,
            data={"redaction_mapping": "invalid"},
            headers=headers,
        )

        assert response.status_code == 400

        assert "Invalid redaction mapping" in response.json().get(
            "detail", ""
        ) or response.json().get("error", "")

        mock_redact.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.app.api.routes.pdf_routes.session_manager.prepare_inputs")
    @patch(
        "backend.app.services.document_extract_service.DocumentExtractService.extract"
    )
    async def test_pdf_extract_success(self, mock_extract, mock_prepare_inputs):
        response_cache.clear()

        mock_prepare_inputs.return_value = ([MagicMock()], {}, None)

        mock_result = MagicMock()

        mock_result.model_dump.return_value = {
            "text": "Extracted text",
            "positions": [[0, 0], [10, 10]],
        }

        mock_extract.return_value = mock_result

        files = {"file": ("test_file.pdf", b"file content", "application/pdf")}

        headers = {"raw-api-key": "mock_key"}

        response = client.post("/pdf/extract", files=files, headers=headers)

        assert response.status_code == 200

        assert response.json() == {
            "text": "Extracted text",
            "positions": [[0, 0], [10, 10]],
        }

        mock_extract.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.app.api.routes.pdf_routes.session_manager.prepare_inputs")
    @patch(
        "backend.app.services.document_extract_service.DocumentExtractService.extract"
    )
    @patch(
        "backend.app.api.routes.pdf_routes.SecurityAwareErrorHandler.handle_safe_error"
    )
    async def test_pdf_extract_internal_error(
        self, mock_handle_safe_error, mock_extract, mock_prepare_inputs
    ):
        response_cache.clear()

        mock_prepare_inputs.return_value = ([MagicMock()], {}, None)

        mock_extract.side_effect = Exception("Internal error in extraction service")

        mock_handle_safe_error.side_effect = HTTPException(
            status_code=500,
            detail={
                "error": "Internal error in extraction service",
                "error_id": "mock_id",
                "error_type": "Exception",
                "status": "error",
            },
        )

        files = {"file": ("test_file.pdf", b"file content", "application/pdf")}

        headers = {"raw-api-key": "mock_key"}

        response = client.post("/pdf/extract", files=files, headers=headers)

        assert response.status_code == 500

        assert response.json() == {
            "detail": {
                "error": "Internal error in extraction service",
                "error_id": "mock_id",
                "error_type": "Exception",
                "status": "error",
            }
        }

        mock_handle_safe_error.assert_called_once()

        mock_extract.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.app.api.routes.pdf_routes.session_manager.prepare_inputs")
    @patch(
        "backend.app.services.document_extract_service.DocumentExtractService.extract"
    )
    async def test_pdf_extract_invalid_file(self, mock_extract, mock_prepare_inputs):
        response_cache.clear()

        mock_prepare_inputs.return_value = ([MagicMock()], {}, None)

        mock_extract.side_effect = HTTPException(
            status_code=400, detail="Invalid file format"
        )

        files = {"file": ("test_file.txt", b"file content", "text/plain")}

        headers = {"raw-api-key": "mock_key"}

        response = client.post("/pdf/extract", files=files, headers=headers)

        assert response.status_code == 400

        assert "Invalid file format" in response.json().get(
            "detail", ""
        ) or response.json().get("error", "")

        mock_extract.assert_called_once()
