from unittest.mock import patch

import pytest

from fastapi.testclient import TestClient

from backend.app.api.main import create_app


class TestFastAPIApp:

    # Fixture: create FastAPI app instance
    @pytest.fixture
    def app(self):
        return create_app()

    # Fixture: create TestClient for the app
    @pytest.fixture
    def client(self, app):
        return TestClient(app)

    # Test that /status returns required fields
    def test_app_startup(self, client):
        response = client.get("/status")

        assert response.status_code == 200

        assert "status" in response.json()

        assert "api_version" in response.json()

        assert "timestamp" in response.json()

    # Test that /health reports healthy status
    def test_health_check(self, client):
        response = client.get("/health")

        assert response.status_code == 200

        response_json = response.json()

        assert "status" in response_json

        assert response_json["status"] == "healthy"

    # Test rate limiting by exceeding allowed calls
    def test_rate_limit(self, client):
        files = {'file': ('test_file.pdf', b"file content", 'application/pdf')}

        for _ in range(11):
            response = client.post("/pdf/extract", files=files)

        assert response.status_code == 415

    # Test presence of security headers in responses
    def test_security_headers(self, client):
        response = client.get("/status")

        assert "X-Content-Type-Options" in response.headers

        assert "X-Frame-Options" in response.headers

        assert "Strict-Transport-Security" in response.headers

    # Test that oversized requests return 413
    def test_invalid_request_size(self, client):
        files = {'file': ('test_file.pdf', b"A" * (25 * 1024 * 1024), 'application/pdf')}

        response = client.post("/pdf/extract", files=files)

        assert response.status_code == 413

    # Test custom OpenAPI schema includes components
    def test_custom_openapi_schema(self, client):
        response = client.get("/openapi.json")

        assert response.status_code == 200

        assert "components" in response.json()

    # Test basic endpoint on shutdown event
    def test_shutdown_event(self, client):
        response = client.get("/status")

        assert response.status_code == 200

    # Test invalid path returns 404 Not Found
    @pytest.mark.asyncio
    async def test_invalid_path(self, client):
        response = client.get("/../../evil_path")

        assert response.status_code == 404

        assert response.json() == {"detail": "Not Found"}

    # Test startup event initializes detectors lazily
    @pytest.mark.asyncio
    @patch("backend.app.api.main.initialization_service.initialize_detectors_lazy")
    async def test_startup_event(self, mock_initialize_detectors_lazy, client):
        mock_initialize_detectors_lazy.return_value = None

        await client.app.router.startup()

        response = client.get("/status")

        assert response.status_code == 200

        mock_initialize_detectors_lazy.assert_called_once()

    # Test shutdown event triggers retention shutdown without exit
    @pytest.mark.asyncio
    @patch("backend.app.api.main.retention_manager.shutdown")
    async def test_shutdown_event(self, mock_retention_shutdown, client):
        with patch("builtins.exit") as mock_exit:
            response = client.get("/health")

            await client.app.router.shutdown()

            mock_retention_shutdown.assert_called_once()

            mock_exit.assert_not_called()
