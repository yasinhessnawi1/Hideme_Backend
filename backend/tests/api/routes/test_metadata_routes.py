import pytest

from fastapi.testclient import TestClient

from unittest.mock import patch, MagicMock

from backend.app.api.main import create_app

from backend.app.utils.security.caching_middleware import response_cache

client = TestClient(create_app())


class TestHelpMetadataRouter:

    # Successful retrieval of available engines
    @pytest.mark.asyncio
    @patch("backend.app.api.routes.metadata_routes.get_cached_response", return_value=None)
    def test_get_available_engines_success(self, mock_cache):
        response_cache.clear()

        response = client.get("/help/engines")

        assert response.status_code == 200

        assert "engines" in response.json()

        assert isinstance(response.json()["engines"], list)

    # Error while retrieving engines returns 500
    @pytest.mark.asyncio
    @patch("backend.app.api.routes.metadata_routes.SecurityAwareErrorHandler.handle_safe_error")
    @patch("backend.app.api.routes.metadata_routes.get_cached_response", return_value=None)
    def test_get_available_engines_error(self, mock_cache, mock_safe_error):
        response_cache.clear()

        mock_cache.side_effect = Exception("Engine fail")

        mock_safe_error.return_value = {"status": "error", "error": "fail", "status_code": 500}

        response = client.get("/help/engines")

        assert response.status_code == 500

        assert response.json()["status"] == "error"

        mock_safe_error.assert_called_once()

    # Successful retrieval of available entities
    @pytest.mark.asyncio
    @patch("backend.app.api.routes.metadata_routes.get_cached_response", return_value=None)
    def test_get_available_entities_success(self, mock_cache):
        response_cache.clear()

        response = client.get("/help/entities")

        assert response.status_code == 200

        assert "presidio_entities" in response.json()

        assert "gemini_entities" in response.json()

    # Error while retrieving entities returns 500
    @pytest.mark.asyncio
    @patch("backend.app.api.routes.metadata_routes.SecurityAwareErrorHandler.handle_safe_error")
    @patch("backend.app.api.routes.metadata_routes.get_cached_response", return_value=None)
    def test_get_available_entities_error(self, mock_cache, mock_safe_error):
        response_cache.clear()

        mock_cache.side_effect = Exception("Entities fail")

        mock_safe_error.return_value = {"status": "error", "error": "fail", "status_code": 500}

        response = client.get("/help/entities")

        assert response.status_code == 500

        assert response.json()["status"] == "error"

        mock_safe_error.assert_called_once()

    # Successful retrieval of entity examples
    @pytest.mark.asyncio
    @patch("backend.app.api.routes.metadata_routes.get_cached_response", return_value=None)
    def test_get_entity_examples_success(self, mock_cache):
        response_cache.clear()

        response = client.get("/help/entity-examples")

        assert response.status_code == 200

        assert "examples" in response.json()

        assert isinstance(response.json()["examples"], dict)

    # Error while retrieving entity examples returns 500
    @pytest.mark.asyncio
    @patch("backend.app.api.routes.metadata_routes.SecurityAwareErrorHandler.handle_safe_error")
    @patch("backend.app.api.routes.metadata_routes.get_cached_response", return_value=None)
    def test_get_entity_examples_error(self, mock_cache, mock_safe_error):
        response_cache.clear()

        mock_cache.side_effect = Exception("Examples fail")

        mock_safe_error.return_value = {"status": "error", "error": "fail", "status_code": 500}

        response = client.get("/help/entity-examples")

        assert response.status_code == 500

        mock_safe_error.assert_called_once()

    # Successful retrieval of API routes
    @pytest.mark.asyncio
    @patch("backend.app.api.routes.metadata_routes.get_cached_response", return_value=None)
    def test_get_api_routes_success(self, mock_cache):
        response_cache.clear()

        response = client.get("/help/routes")

        assert response.status_code == 200

        assert "entity_detection" in response.json()

        assert "batch_processing" in response.json()

    # Error while retrieving API routes returns 500
    @pytest.mark.asyncio
    @patch("backend.app.api.routes.metadata_routes.SecurityAwareErrorHandler.handle_safe_error")
    def test_get_api_routes_error(self, mock_safe_error):
        response_cache.clear()

        with patch("backend.app.api.routes.metadata_routes.response_cache.set", side_effect=Exception("Route fail")):
            mock_safe_error.return_value = {"status": "error", "error": "fail", "status_code": 500}

            response = client.get("/help/routes")

            assert response.status_code == 500

            mock_safe_error.assert_called_once()

    # Successful retrieval of detectors status and metrics
    @pytest.mark.asyncio
    @patch("backend.app.api.routes.metadata_routes.initialization_service")
    def test_get_detectors_status_success(self, mock_init_service):
        response_cache.clear()

        mock_init_service.check_health.return_value = {

            "detectors": {"presidio": True, "gemini": True, "gliner": True, "hideme": True}

        }

        mock_init_service.get_usage_metrics.return_value = {

            "presidio": {"uses": 1}, "gemini": {"uses": 2}, "gliner": {"uses": 3}, "hideme": {"uses": 4}

        }

        mock_init_service.get_detector.return_value = MagicMock(get_status=lambda: {"initialized": True, "uses": 1})

        mock_init_service.get_gemini_detector.return_value = MagicMock(
            get_status=lambda: {"initialized": True, "uses": 2})

        mock_init_service.get_gliner_detector.return_value = MagicMock(
            get_status=lambda: {"initialized": True, "uses": 3})

        mock_init_service.get_hideme_detector.return_value = MagicMock(
            get_status=lambda: {"initialized": True, "uses": 4})

        response = client.get("/help/detectors-status")

        assert response.status_code == 200

        assert "_meta" in response.json()

    # Error while retrieving detectors status returns 500
    @pytest.mark.asyncio
    @patch("backend.app.api.routes.metadata_routes.SecurityAwareErrorHandler.handle_safe_error")
    @patch("backend.app.api.routes.metadata_routes.initialization_service")
    def test_get_detectors_status_error(self, mock_init_service, mock_safe_error):
        response_cache.clear()

        mock_init_service.check_health.side_effect = Exception("Boom")

        mock_safe_error.return_value = {"status": "error", "error": "fail", "status_code": 500}

        response = client.get("/help/detectors-status")

        assert response.status_code == 500

        assert response.json()["status"] == "error"

        mock_safe_error.assert_called_once()
