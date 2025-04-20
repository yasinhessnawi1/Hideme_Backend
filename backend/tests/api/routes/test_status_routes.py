import pytest

from fastapi.testclient import TestClient

from unittest.mock import patch

from backend.app.api.main import create_app

from backend.app.utils.security.caching_middleware import response_cache

client = TestClient(create_app())


class TestStatusRouter:

    # /status returns 200 with status, timestamp, and api_version
    @pytest.mark.asyncio
    @patch("backend.app.api.routes.status_routes.response_cache.get", return_value=None)
    @patch("backend.app.api.routes.status_routes.response_cache.set")
    def test_status_success(self, mock_cache_set, mock_cache_get):
        response_cache.clear()

        response = client.get("/status")

        assert response.status_code == 200

        assert "status" in response.json()

        assert "timestamp" in response.json()

        assert "api_version" in response.json()

    # /status error in cache returns 500 with error payload
    @pytest.mark.asyncio
    @patch("backend.app.api.routes.status_routes.response_cache.get", return_value=None)
    @patch("backend.app.api.routes.status_routes.response_cache.set")
    @patch("backend.app.api.routes.status_routes.SecurityAwareErrorHandler.handle_safe_error")
    def test_status_error(self, mock_safe_error, mock_cache_set, mock_cache_get):
        response_cache.clear()

        mock_cache_get.side_effect = Exception("Status cache fail")

        mock_safe_error.return_value = {
            "error": "Internal error",
            "error_id": "mock_id",
            "error_type": "Exception",
            "status": "error"
        }

        response = client.get("/status")

        assert response.status_code == 500

        assert "error" in response.json()

        assert "error_id" in response.json()

        assert "status" in response.json()

        assert response.json()["error"] == "Internal error"

        assert response.json()["error_id"] == "mock_id"

        assert response.json()["status"] == "error"

        mock_safe_error.assert_called_once()

    # /health returns 200 with status, services, and process info
    @pytest.mark.asyncio
    @patch("backend.app.api.routes.status_routes.response_cache.get", return_value=None)
    @patch("backend.app.api.routes.status_routes.response_cache.set")
    def test_health_check_success(self, mock_cache_set, mock_cache_get):
        response_cache.clear()

        response = client.get("/health")

        assert response.status_code == 200

        assert "status" in response.json()

        assert "services" in response.json()

        assert "process" in response.json()

    # /health cache failure returns 500 via safe error
    @pytest.mark.asyncio
    @patch("backend.app.api.routes.status_routes.SecurityAwareErrorHandler.handle_safe_error")
    @patch("backend.app.api.routes.status_routes.response_cache.get", return_value=None)
    @patch("backend.app.api.routes.status_routes.response_cache.set")
    def test_health_check_error(self, mock_cache_set, mock_cache_get, mock_safe_error):
        response_cache.clear()

        mock_cache_get.side_effect = Exception("Health check cache fail")

        mock_safe_error.return_value = {"status": "error", "error": "fail", "status_code": 500}

        response = client.get("/health")

        assert response.status_code == 500

        mock_safe_error.assert_called_once()

    # /metrics returns 200 with system, process, memory_monitor, and cache data
    @pytest.mark.asyncio
    @patch("backend.app.api.routes.status_routes.response_cache.get", return_value=None)
    @patch("backend.app.api.routes.status_routes.response_cache.set")
    def test_metrics_success(self, mock_cache_set, mock_cache_get):
        response_cache.clear()

        response = client.get("/metrics", headers={"X-API-Key": "test_api_key"})

        assert response.status_code == 200

        assert "system" in response.json()

        assert "process" in response.json()

        assert "memory_monitor" in response.json()

        assert "cache" in response.json()

    # /metrics cache failure returns 500 via safe error
    @pytest.mark.asyncio
    @patch("backend.app.api.routes.status_routes.SecurityAwareErrorHandler.handle_safe_error")
    @patch("backend.app.api.routes.status_routes.response_cache.get", return_value=None)
    @patch("backend.app.api.routes.status_routes.response_cache.set")
    def test_metrics_error(self, mock_cache_set, mock_cache_get, mock_safe_error):
        response_cache.clear()

        mock_cache_get.side_effect = Exception("Metrics cache fail")

        mock_safe_error.return_value = {"status": "error", "error": "fail", "status_code": 500}

        response = client.get("/metrics", headers={"X-API-Key": "test_api_key"})

        assert response.status_code == 500

        mock_safe_error.assert_called_once()

    # /readiness returns 503 with ready, services, and memory
    @pytest.mark.asyncio
    @patch("backend.app.api.routes.status_routes.response_cache.get", return_value=None)
    @patch("backend.app.api.routes.status_routes.response_cache.set")
    def test_readiness_check_success(self, mock_cache_set, mock_cache_get):
        response_cache.clear()

        response = client.get("/readiness")

        assert response.status_code == 503

        assert "ready" in response.json()

        assert "services" in response.json()

        assert "memory" in response.json()

    # /readiness cache failure returns 500 via safe error
    @pytest.mark.asyncio
    @patch("backend.app.api.routes.status_routes.SecurityAwareErrorHandler.handle_safe_error")
    @patch("backend.app.api.routes.status_routes.response_cache.get", return_value=None)
    @patch("backend.app.api.routes.status_routes.response_cache.set")
    def test_readiness_check_error(self, mock_cache_set, mock_cache_get, mock_safe_error):
        response_cache.clear()

        mock_cache_get.side_effect = Exception("Readiness check cache fail")

        mock_safe_error.return_value = {"status": "error", "error": "fail", "status_code": 500}

        response = client.get("/readiness")

        assert response.status_code == 500

        mock_safe_error.assert_called_once()
