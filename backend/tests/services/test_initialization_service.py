import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import pytest

from backend.app.configs.gliner_config import GLINER_MODEL_NAME, GLINER_AVAILABLE_ENTITIES
from backend.app.entity_detection import EntityDetectionEngine
from backend.app.services.initialization_service import InitializationService


# Asynchronous dummy shutdown function for detectors
async def dummy_shutdown():
    return True


# Test suite for InitializationService functionality
class TestInitializationService(unittest.IsolatedAsyncioTestCase):

    # Setup service before each test
    def setUp(self):
        self.service = InitializationService(max_cache_size=2)

    # Async setup service before each async test
    async def asyncSetUp(self):
        self.service = InitializationService(max_cache_size=2)

    # Test incrementing usage metrics for non-dynamic key
    @patch("backend.app.services.initialization_service.time.time", return_value=1000.0)
    def test_increment_usage_metrics_regular(self, _):
        self.service._increment_usage_metrics("presidio", 1000.0)

        self.assertEqual(self.service._usage_metrics["presidio"]["uses"], 1)

    # Test incrementing usage metrics for dynamic gliner key
    @patch("backend.app.services.initialization_service.time.time", return_value=1000.0)
    def test_increment_usage_metrics_dynamic(self, _):
        key = "gliner_key1"

        self.service._increment_usage_metrics(f"gliner_{key}", 1000.0)

        self.assertIn(f"gliner_{key}", self.service._usage_metrics["gliner"])

    # Test evict least recently used with empty metrics does nothing
    def test_evict_least_recently_used_empty(self):
        self.service._usage_metrics["gliner"] = {}

        self.service._evict_least_recently_used("gliner")

        self.assertTrue(True)  # no exception

    # Test get_detector falls back when cache miss and lock unavailable
    def test_get_detector_fallback(self):
        with patch.object(self.service, "_quick_check_cache", return_value=None), \
                patch.object(self.service, "_try_acquire_lock", return_value=False), \
                patch.object(self.service, "_fallback_init", return_value="fallback"):
            result = self.service.get_detector(EntityDetectionEngine.PRESIDIO)

            self.assertEqual(result, "fallback")

    # Test initializing and storing detector raises on invalid engine
    def test_initialize_and_store_detector_invalid(self):
        with self.assertRaises(ValueError):
            self.service._initialize_and_store_detector("INVALID_ENGINE", {})

    # Test fallback_init raises on invalid engine
    def test_fallback_init_invalid_engine(self):
        with self.assertRaises(ValueError):
            self.service._fallback_init("INVALID_ENGINE", {})

    # Test caching of hybrid detector returns stored instance
    def test_get_hybrid_detector_caching(self):
        config = {

            "use_presidio": True,

            "use_gemini": False,

            "use_gliner": False,

            "use_hideme": False,

            "entities": []

        }

        key = self.service._get_hybrid_cache_key(config)

        self.service._hybrid_detectors[key] = "hybrid_mock"

        result = self.service.get_hybrid_detector(config)

        self.assertEqual(result, "hybrid_mock")

    # Test shutdown_async handles exceptions in detectors
    async def test_shutdown_async_raises(self):
        mock = AsyncMock()

        mock.shutdown_async = AsyncMock(side_effect=Exception("shutdown fail"))

        self.service._gliner_detectors["x"] = mock

        await self.service.shutdown_async()

        self.assertTrue(True)  # handled

    # Test get_detector with repeated lock failures falls back
    def test_get_detector_with_lock_timeout(self):
        with patch.object(self.service, "_try_acquire_lock", side_effect=[False, False]), \
                patch.object(self.service, "_fallback_init", return_value="fallback"):
            result = self.service.get_detector(EntityDetectionEngine.PRESIDIO)

            self.assertEqual(result, "fallback")

    # Test get_detector returns cached detector immediately
    def test_get_detector_with_cache_hit(self):
        self.service._presidio_detector = "presidio_mock"

        result = self.service.get_detector(EntityDetectionEngine.PRESIDIO)

        self.assertEqual(result, "presidio_mock")

    # Test _initialize_presidio_or_gemini returns existing cache hit
    def test_initialize_presidio_or_gemini_cache_hit(self):
        self.service._presidio_detector = "presidio_mock"

        result = self.service._initialize_presidio_or_gemini(EntityDetectionEngine.PRESIDIO)

        self.assertEqual(result, "presidio_mock")

    # Test lazy initialization of Presidio detector succeeds
    @patch("backend.app.services.initialization_service.InitializationService._initialize_presidio_detector")
    async def test_lazy_init_presidio_success(self, mock_init):
        mock_init.return_value = "presidio_mock"

        await self.service._lazy_init_presidio()

        self.assertEqual(self.service._presidio_detector, "presidio_mock")

        self.assertTrue(self.service._initialization_status["presidio"])

    # Test lazy initialization of Gemini detector succeeds
    @patch("backend.app.services.initialization_service.InitializationService._initialize_gemini_detector")
    async def test_lazy_init_gemini_success(self, mock_init):
        mock_init.return_value = "gemini_mock"

        await self.service._lazy_init_gemini()

        self.assertEqual(self.service._gemini_detector, "gemini_mock")

        self.assertTrue(self.service._initialization_status["gemini"])

    # Test lazy initialization of GLiNER detector succeeds
    @patch("backend.app.services.initialization_service.GLINER_AVAILABLE_ENTITIES", new=[])
    @patch("backend.app.services.initialization_service.memory_monitor.get_memory_usage", return_value=10)
    @patch("backend.app.services.initialization_service.InitializationService._initialize_gliner_detector")
    async def test_lazy_init_gliner_success(self, mock_init, mock_memory):
        mock_init.return_value = "gliner_mock"

        await self.service._maybe_lazy_init_gliner()

        key = self.service._get_gliner_cache_key([])

        self.assertEqual(self.service._gliner_detectors[key], "gliner_mock")

    # Test lazy initialization of HideMe detector succeeds
    @patch("backend.app.services.initialization_service.HIDEME_AVAILABLE_ENTITIES", new=[])
    @patch("backend.app.services.initialization_service.memory_monitor.get_memory_usage", return_value=10)
    @patch("backend.app.services.initialization_service.InitializationService._initialize_hideme_detector")
    async def test_lazy_init_hideme_success(self, mock_init, mock_memory):
        mock_init.return_value = "hideme_mock"

        await self.service._maybe_lazy_init_hideme()

        key = self.service._get_hideme_cache_key([])

        self.assertEqual(self.service._hideme_detectors[key], "hideme_mock")

    # Test generation of GLiNER cache key from entities
    def test_get_gliner_cache_key(self):
        key = self.service._get_gliner_cache_key(["ssn", "name"])

        self.assertEqual(key, "name_ssn")

    # Test generation of HideMe cache key when no entities yields default
    def test_get_hideme_cache_key_empty(self):
        key = self.service._get_hideme_cache_key([])

        self.assertEqual(key, "default")

    # Test generation of hybrid cache key includes flags and sorted entities
    def test_get_hybrid_cache_key(self):
        config = {

            "use_presidio": True,

            "use_gemini": False,

            "use_gliner": True,

            "use_hideme": False,

            "entities": ["ssn", "name"]

        }

        key = self.service._get_hybrid_cache_key(config)

        self.assertTrue(key.startswith("p1_g0_gl1_h0_"))

    # Test get_initialization_status returns even when lock fails
    def test_get_initialization_status_lock_fail(self):
        self.service._lock.acquire = MagicMock(return_value=False)

        result = self.service.get_initialization_status()

        self.assertIn("presidio", result)

    # Test get_usage_metrics returns even when lock fails
    def test_get_usage_metrics_lock_fail(self):
        self.service._lock.acquire = MagicMock(return_value=False)

        result = self.service.get_usage_metrics()

        self.assertIn("presidio", result)

    # Test check_health returns limited when lock fails
    def test_check_health_lock_fail(self):
        self.service._lock.acquire = MagicMock(return_value=False)

        result = self.service.check_health()

        self.assertEqual(result["health"], "limited")

    # Test quick cache check returns Presidio detector and updates metrics
    def test_quick_check_cache_presidio(self):
        self.service._presidio_detector = "presidio_cached"

        result = self.service._quick_check_cache(EntityDetectionEngine.PRESIDIO, {})

        self.assertEqual(result, "presidio_cached")

    # Test fallback_init for Presidio uses initialize_presidio_detector
    @patch.object(InitializationService, "_initialize_presidio_detector", return_value="presidio_fallback")
    def test_fallback_init_presidio(self, _):
        result = self.service._fallback_init(EntityDetectionEngine.PRESIDIO, {})

        self.assertEqual(result, "presidio_fallback")

    # Test lock acquisition timeout returns False
    def test_try_acquire_lock_timeout(self):
        self.service._lock.acquire = MagicMock(side_effect=TimeoutError())

        result = self.service._try_acquire_lock(0.1)

        self.assertFalse(result)

    # Test lazy initialization of all detectors triggers each
    @patch.object(InitializationService, "_lazy_init_presidio")
    @patch.object(InitializationService, "_lazy_init_gemini")
    @patch.object(InitializationService, "_maybe_lazy_init_gliner")
    @patch.object(InitializationService, "_maybe_lazy_init_hideme")
    async def test_initialize_detectors_lazy(self, mock_hideme, mock_gliner, mock_gemini, mock_presidio):
        await self.service.initialize_detectors_lazy()

        mock_presidio.assert_called_once()

        mock_gemini.assert_called_once()

        mock_gliner.assert_called_once()

        mock_hideme.assert_called_once()

    # Test GLiNER eviction logic when cache size exceeded
    @patch.object(InitializationService, "_initialize_gliner_detector", return_value="new_gliner")
    def test_initialize_and_store_gliner_eviction(self, mock_init):
        self.service._gliner_detectors = {"existing1": "det1", "existing2": "det2"}

        self.service._usage_metrics["gliner"] = {

            "gliner_existing1": {"uses": 1, "last_used": 10},

            "gliner_existing2": {"uses": 2, "last_used": 20},

        }

        config = {"entities": ["ssn"]}

        det = self.service._initialize_and_store_detector(EntityDetectionEngine.GLINER, config)

        self.assertEqual(det, "new_gliner")

    # Test HideMe eviction logic when cache size exceeded
    @patch.object(InitializationService, "_initialize_hideme_detector", return_value="hideme_det")
    def test_initialize_and_store_hideme_eviction(self, mock_init):
        self.service._hideme_detectors = {"old1": "h1", "old2": "h2"}

        self.service._usage_metrics["hideme"] = {

            "hideme_old1": {"uses": 3, "last_used": 1},

            "hideme_old2": {"uses": 5, "last_used": 2}

        }

        config = {"entities": ["email"]}

        det = self.service._initialize_and_store_detector(EntityDetectionEngine.HIDEME, config)

        self.assertEqual(det, "hideme_det")

    # Test update_usage_metrics_no_lock does not raise on exception
    @patch.object(InitializationService, "_increment_usage_metrics", side_effect=Exception("fail"))
    def test_update_usage_metrics_no_lock_fail(self, _):
        self.service._update_usage_metrics_no_lock("presidio")

    # Test fallback_get_detector follows fallback path when no cache and lock fails
    @patch.object(InitializationService, "_quick_check_cache", return_value=None)
    @patch.object(InitializationService, "_try_acquire_lock", return_value=False)
    @patch.object(InitializationService, "_fallback_init", return_value="fallback")
    def test_get_detector_fallback_path(self, mock_fallback, *_):
        result = self.service.get_detector(EntityDetectionEngine.PRESIDIO)

        self.assertEqual(result, "fallback")

    # Test eviction with empty GLiNER metrics does not raise
    def test_evict_gliner_lru_empty_metrics(self):
        self.service._usage_metrics["gliner"] = {}

        self.service._gliner_detectors = {}

        self.service._evict_least_recently_used("gliner")  # should not raise

    # Test eviction of hybrid detectors clears cache
    def test_evict_hybrid_lru(self):
        self.service._hybrid_detectors = {"key1": "hyb"}

        self.service._evict_least_recently_used("hybrid")

        self.assertEqual(self.service._hybrid_detectors, {})

    # Test shutdown logic for synchronous detectors
    async def test_shutdown_async_logic(self):
        det = MagicMock()

        det.shutdown_async = dummy_shutdown

        self.service._presidio_detector = det

        self.service._gemini_detector = det

        self.service._gliner_detectors = {"key": det}

        self.service._hideme_detectors = {"key": det}

        self.service._hybrid_detectors = {"key": det}

        await self.service.shutdown_async()

    # Test lazy initialization handles exceptions and logs errors
    @patch("backend.app.services.initialization_service.log_error")
    @patch("backend.app.services.initialization_service.SecurityAwareErrorHandler.log_processing_error")
    @patch.object(InitializationService, "_lazy_init_presidio", new_callable=AsyncMock)
    @patch.object(InitializationService, "_lazy_init_gemini", new_callable=AsyncMock)
    @patch.object(InitializationService, "_maybe_lazy_init_gliner", new_callable=AsyncMock)
    @patch.object(InitializationService, "_maybe_lazy_init_hideme", new_callable=AsyncMock)
    async def test_initialize_detectors_lazy_with_exception(
            self,
            mock_hideme,
            mock_gliner,
            mock_gemini,
            mock_presidio,
            mock_error_log,
            mock_log_error,
    ):
        mock_gemini.side_effect = Exception("Simulated Gemini failure")

        await self.service.initialize_detectors_lazy()

        mock_error_log.assert_called()

        mock_log_error.assert_called()

        self.assertIn("Simulated Gemini failure", mock_log_error.call_args[0][0])

    # Test exception handling in lazy GLiNER initialization
    @patch("backend.app.services.initialization_service.asyncio.to_thread",
           side_effect=Exception("Failed to load GLiNER"))
    @patch("backend.app.services.initialization_service.SecurityAwareErrorHandler.log_processing_error")
    @patch("backend.app.services.initialization_service.log_error")
    @patch("backend.app.services.initialization_service.memory_monitor.get_memory_usage", return_value=30.0)
    async def test_lazy_init_gliner_exception_handling(self, mock_mem, mock_log_error, mock_process_error,
                                                       mock_to_thread):
        await self.service._maybe_lazy_init_gliner()

        mock_process_error.assert_called()

        mock_log_error.assert_called()

        self.assertIn("Failed to load GLiNER", str(mock_log_error.call_args[0][0]))

    # Test exception handling in lazy HideMe initialization
    @patch("backend.app.entity_detection.hideme.HidemeEntityDetector", side_effect=Exception("Failed to load HIDEME"))
    @patch("backend.app.services.initialization_service.SecurityAwareErrorHandler.log_processing_error")
    @patch("backend.app.services.initialization_service.log_error")
    @patch("backend.app.services.initialization_service.memory_monitor.get_memory_usage", return_value=30.0)
    async def test_lazy_init_hideme_exception_handling(self, mock_mem, mock_log, mock_err_log, mock_hideme):
        await self.service._maybe_lazy_init_hideme()

        mock_err_log.assert_called()

        self.assertIn("Failed to load HIDEME", str(mock_err_log.call_args[0][0]))

    # Test exception in Presidio detector initialization is logged and propagated
    @patch("backend.app.entity_detection.presidio.PresidioEntityDetector", side_effect=Exception("Presidio init error"))
    @patch("backend.app.services.initialization_service.SecurityAwareErrorHandler.log_processing_error")
    @patch("backend.app.services.initialization_service.log_error")
    def test_initialize_presidio_detector_exception(self, mock_log_error, mock_error_handler, mock_presidio):
        with self.assertRaises(Exception) as ctx:
            self.service._initialize_presidio_detector()

        self.assertEqual(str(ctx.exception), "Presidio init error")

        mock_error_handler.assert_called()

        mock_log_error.assert_called()

    # Test exception in Gemini detector initialization is handled and status updated
    @patch("backend.app.entity_detection.gemini.GeminiEntityDetector", side_effect=Exception("Gemini init error"))
    @patch("backend.app.services.initialization_service.log_error")
    @patch("backend.app.services.initialization_service.SecurityAwareErrorHandler.log_processing_error")
    def test_initialize_gemini_detector_exception(self, mock_log_processing_error, mock_log_error, mock_gemini_cls):
        service = InitializationService()

        with pytest.raises(Exception) as exc_info:
            service._initialize_gemini_detector()

        assert str(exc_info.value) == "Gemini init error"

        assert service._initialization_status["gemini"] is False

        mock_log_processing_error.assert_called_once()

        mock_log_error.assert_called_once()

        assert "Gemini init error" in mock_log_error.call_args[0][0]

    # Test successful GLiNER detector initialization
    @patch("backend.app.services.initialization_service.GlinerEntityDetector")
    @patch("backend.app.services.initialization_service.log_info")
    def test_initialize_gliner_detector_success(self, mock_log_info, mock_gliner_cls):
        service = InitializationService()

        mock_detector = MagicMock()

        mock_gliner_cls.return_value = mock_detector

        result = service._initialize_gliner_detector(GLINER_MODEL_NAME, GLINER_AVAILABLE_ENTITIES)

        assert result == mock_detector

        assert service._initialization_status["gliner"] is True

        mock_log_info.assert_any_call(

            f"Initializing GLiNER detector with model {GLINER_MODEL_NAME}"

        )

    # Test failure in GLiNER detector initialization logs and propagates
    @patch("backend.app.services.initialization_service.GlinerEntityDetector",
           side_effect=Exception("GLiNER init failed"))
    @patch("backend.app.services.initialization_service.SecurityAwareErrorHandler.log_processing_error")
    @patch("backend.app.services.initialization_service.log_error")
    def test_initialize_gliner_detector_failure(self, mock_log_error, mock_log_processing_error, mock_gliner_cls):
        service = InitializationService()

        with pytest.raises(Exception) as exc_info:
            service._initialize_gliner_detector(GLINER_MODEL_NAME, GLINER_AVAILABLE_ENTITIES)

        assert str(exc_info.value) == "GLiNER init failed"

        assert service._initialization_status["gliner"] is False

        mock_log_processing_error.assert_called_once()

        mock_log_error.assert_called_once()

        assert "GLiNER init failed" in mock_log_error.call_args[0][0]

    # Test successful hybrid detector initialization
    @patch("backend.app.entity_detection.hybrid.HybridEntityDetector")
    @patch("backend.app.services.initialization_service.log_info")
    def test_initialize_hybrid_detector_success(self, mock_log_info, mock_hybrid_cls):
        service = InitializationService()

        mock_detector = MagicMock()

        mock_hybrid_cls.return_value = mock_detector

        config = {"mode": "standard"}

        result = service._initialize_hybrid_detector(config)

        assert result == mock_detector

        assert service._initialization_status["hybrid"] is True

        mock_log_info.assert_any_call("Hybrid detector initialized in 0.00s")

    # Test failure in hybrid detector initialization logs and propagates
    @patch("backend.app.entity_detection.hybrid.HybridEntityDetector", side_effect=Exception("Hybrid init error"))
    @patch("backend.app.services.initialization_service.SecurityAwareErrorHandler.log_processing_error")
    @patch("backend.app.services.initialization_service.log_error")
    def test_initialize_hybrid_detector_exception(self, mock_log_error, mock_log_processing_error, mock_hybrid_cls):
        service = InitializationService()

        config = {"mode": "fail"}

        with self.assertRaises(Exception) as exc_info:
            service._initialize_hybrid_detector(config)

        self.assertEqual(str(exc_info.exception), "Hybrid init error")

        self.assertFalse(service._initialization_status["hybrid"])

        mock_log_processing_error.assert_called_once()

        mock_log_error.assert_called_once()

        self.assertIn("Hybrid init error", mock_log_error.call_args[0][0])

    # Test get_presidio_detector calls get_detector with PRESIDIO engine
    def test_get_presidio_detector_calls_get_detector_with_presidio(self):
        service = InitializationService()

        with patch.object(service, "get_detector", return_value="presidio_instance") as mock_get:
            result = service.get_presidio_detector()

            mock_get.assert_called_once_with(EntityDetectionEngine.PRESIDIO)

            assert result == "presidio_instance"

    # Test get_gemini_detector calls get_detector with GEMINI engine
    def test_get_gemini_detector_calls_get_detector_with_gemini(self):
        service = InitializationService()

        with patch.object(service, "get_detector", return_value="gemini_instance") as mock_get:
            result = service.get_gemini_detector()

            mock_get.assert_called_once_with(EntityDetectionEngine.GEMINI)

            assert result == "gemini_instance"

    # Test get_gliner_detector calls get_detector with correct config
    def test_get_gliner_detector_calls_get_detector_with_config(self):
        service = InitializationService()

        test_entities = ["EMAIL", "NAME"]

        expected_config = {"entities": test_entities}

        with patch.object(service, "get_detector", return_value="gliner_instance") as mock_get:
            result = service.get_gliner_detector(test_entities)

            mock_get.assert_called_once_with(EntityDetectionEngine.GLINER, expected_config)

            assert result == "gliner_instance"

    # Test get_hideme_detector calls get_detector with correct config
    def test_get_hideme_detector_calls_get_detector_with_config(self):
        service = InitializationService()

        test_entities = ["ADDRESS", "IP"]

        expected_config = {"entities": test_entities}

        with patch.object(service, "get_detector", return_value="hideme_instance") as mock_get:
            result = service.get_hideme_detector(test_entities)

            mock_get.assert_called_once_with(EntityDetectionEngine.HIDEME, expected_config)

            assert result == "hideme_instance"

    # Test quick cache hits for basic engines update usage metrics
    def test_quick_check_cache_basic_engines(self):
        test_cases = [

            (EntityDetectionEngine.PRESIDIO, "_presidio_detector", "presidio"),

            (EntityDetectionEngine.GEMINI, "_gemini_detector", "gemini"),

        ]

        for engine, attr_name, usage_key in test_cases:
            service = InitializationService()

            fake_detector = MagicMock()

            setattr(service, attr_name, fake_detector)

            with patch.object(service, "_update_usage_metrics_no_lock") as mock_usage:
                result = service._quick_check_cache(engine, {})

                self.assertEqual(result, fake_detector)

                mock_usage.assert_called_once_with(usage_key)

    # Test quick cache hit for GLiNER updates metrics
    def test_quick_check_cache_gliner_hit(self):
        service = InitializationService()

        entities = ["EMAIL"]

        key = "gliner:EMAIL"

        fake_detector = MagicMock()

        service._gliner_detectors[key] = fake_detector

        with patch.object(service, "_get_gliner_cache_key", return_value=key), \
                patch.object(service, "_update_usage_metrics_no_lock") as mock_usage:
            result = service._quick_check_cache(EntityDetectionEngine.GLINER, {"entities": entities})

            assert result == fake_detector

            mock_usage.assert_called_once_with(f"gliner_{key}")

    # Test quick cache hit for HideMe updates metrics
    def test_quick_check_cache_hideme_hit(self):
        service = InitializationService()

        entities = ["ADDRESS"]

        key = "hideme:ADDRESS"

        fake_detector = MagicMock()

        service._hideme_detectors[key] = fake_detector

        with patch.object(service, "_get_hideme_cache_key", return_value=key), \
                patch.object(service, "_update_usage_metrics_no_lock") as mock_usage:
            result = service._quick_check_cache(EntityDetectionEngine.HIDEME, {"entities": entities})

            assert result == fake_detector

            mock_usage.assert_called_once_with(f"hideme_{key}")

    # Test quick cache hit for hybrid detectors
    def test_quick_check_cache_hybrid_hit(self):
        service = InitializationService()

        config = {"mode": "standard"}

        key = "hybrid:standard"

        fake_detector = MagicMock()

        service._hybrid_detectors[key] = fake_detector

        with patch.object(service, "_get_hybrid_cache_key", return_value=key):
            result = service._quick_check_cache(EntityDetectionEngine.HYBRID, config)

            assert result == fake_detector

    # Test quick cache miss returns None
    def test_quick_check_cache_miss(self):
        service = InitializationService()

        result = service._quick_check_cache(EntityDetectionEngine.PRESIDIO, {})

        assert result is None

    # Test initialize_hybrid adds to cache and evicts if necessary
    def test_initialize_hybrid_detector_with_cache_handling(self):
        service = InitializationService()

        config = {"mode": "test"}

        fake_key = "hybrid::test"

        fake_detector = MagicMock()

        service.max_cache_size = 1

        with patch.object(service, "_get_hybrid_cache_key", return_value=fake_key), \
                patch.object(service, "_initialize_hybrid_detector", return_value=fake_detector), \
                patch.object(service, "_evict_least_recently_used") as mock_evict:
            # Case 1: cache miss, not full

            service._hybrid_detectors = {}

            result = service._initialize_hybrid(config)

            self.assertEqual(result, fake_detector)

            self.assertIn(fake_key, service._hybrid_detectors)

            mock_evict.assert_not_called()

            # Case 2: cache hit

            result_cached = service._initialize_hybrid(config)

            self.assertEqual(result_cached, fake_detector)

            self.assertEqual(service._initialize_hybrid_detector.call_count, 1)

            # Case 3: cache full triggers eviction

            service._hybrid_detectors = {"hybrid::old": MagicMock()}

            result_new = service._initialize_hybrid(config)

            self.assertEqual(result_new, fake_detector)

            mock_evict.assert_called_once_with("hybrid")

    # Test get_initialization_status returns when lock acquired
    def test_get_initialization_status_lock_success(self):
        service = InitializationService()

        service._initialization_status = {"presidio": True, "gemini": False}

        service._lock = MagicMock()

        service._lock.acquire.return_value = True

        result = service.get_initialization_status()

        assert result == {"presidio": True, "gemini": False}

        service._lock.release.assert_called_once()

    # Test get_initialization_status logs on exception
    @patch("backend.app.services.initialization_service.log_warning")
    @patch("backend.app.services.initialization_service.SecurityAwareErrorHandler.log_processing_error")
    def test_get_initialization_status_exception(self, mock_error_log, mock_log):
        service = InitializationService()

        service._initialization_status = {"gemini": True}

        service._lock = MagicMock()

        service._lock.acquire.side_effect = RuntimeError("boom")

        result = service.get_initialization_status()

        assert result == {"gemini": True}

        mock_error_log.assert_called_once()

        mock_log.assert_called_once()

    # Test get_usage_metrics returns data when lock acquired
    @patch("backend.app.services.initialization_service.SecurityAwareErrorHandler.log_processing_error")
    @patch("backend.app.services.initialization_service.log_error")
    def test_get_usage_metrics_lock_success(self, mock_err_log, mock_log):
        service = InitializationService()

        service._lock = MagicMock()

        service._lock.acquire.return_value = True

        service._usage_metrics = {

            "presidio": {"count": 10},

            "gemini": {"count": 5},

            "gliner": {"key1": {"c": 1}},

            "hideme": {"key2": {"c": 2}},

        }

        result = service.get_usage_metrics()

        assert result == service._usage_metrics

        service._lock.release.assert_called_once()

        mock_log.assert_not_called()

        mock_err_log.assert_not_called()

    # Test get_usage_metrics logs on exception
    @patch("backend.app.services.initialization_service.log_error")
    @patch("backend.app.services.initialization_service.SecurityAwareErrorHandler.log_processing_error")
    def test_get_usage_metrics_exception(self, mock_error_log, mock_log):
        service = InitializationService()

        service._lock = MagicMock()

        service._lock.acquire.side_effect = Exception("Crash")

        result = service.get_usage_metrics()

        assert result == {"presidio": {}, "gemini": {}, "gliner": {}, "hideme": {}}

        mock_log.assert_called_once()

        mock_error_log.assert_called_once()

    # Test fallback_init returns cached Presidio detector if exists
    @patch("backend.app.services.initialization_service.log_warning")
    def test_fallback_init_presidio_cached(self, _):
        detector = MagicMock()

        self.service._presidio_detector = detector

        result = self.service._fallback_init(EntityDetectionEngine.PRESIDIO, {})

        self.assertEqual(result, detector)

    # Test fallback_init initializes Presidio when cache miss
    @patch("backend.app.services.initialization_service.log_warning")
    def test_fallback_init_presidio_init(self, _):
        self.service._presidio_detector = None

        self.service._initialize_presidio_detector = MagicMock()

        result = self.service._fallback_init(EntityDetectionEngine.PRESIDIO, {})

        self.service._initialize_presidio_detector.assert_called_once()

        self.assertEqual(result, self.service._initialize_presidio_detector())

    # Test fallback_init returns cached Gemini detector if exists
    @patch("backend.app.services.initialization_service.log_warning")
    def test_fallback_init_gemini_cached(self, _):
        detector = MagicMock()

        self.service._gemini_detector = detector

        result = self.service._fallback_init(EntityDetectionEngine.GEMINI, {})

        self.assertEqual(result, detector)

    # Test fallback_init initializes Gemini when cache miss
    @patch("backend.app.services.initialization_service.log_warning")
    def test_fallback_init_gemini_init(self, _):
        self.service._gemini_detector = None

        self.service._initialize_gemini_detector = MagicMock()

        result = self.service._fallback_init(EntityDetectionEngine.GEMINI, {})

        self.service._initialize_gemini_detector.assert_called_once()

        self.assertEqual(result, self.service._initialize_gemini_detector())

    # Test fallback_init initializes GLiNER with correct args
    @patch("backend.app.services.initialization_service.log_warning")
    def test_fallback_init_gliner_init(self, _):
        key = "gliner_key"

        self.service._get_gliner_cache_key = MagicMock(return_value=key)

        self.service._gliner_detectors = {}

        self.service._initialize_gliner_detector = MagicMock()

        config = {"entities": ["email"], "model_name": "gliner_model"}

        self.service._fallback_init(EntityDetectionEngine.GLINER, config)

        self.service._initialize_gliner_detector.assert_called_with("gliner_model", ["email"])

    # Test fallback_init returns cached HideMe detector if exists
    @patch("backend.app.services.initialization_service.log_warning")
    def test_fallback_init_hideme_cached(self, _):
        key = "hideme_key"

        self.service._get_hideme_cache_key = MagicMock(return_value=key)

        detector = MagicMock()

        self.service._hideme_detectors = {key: detector}

        config = {"entities": []}

        result = self.service._fallback_init(EntityDetectionEngine.HIDEME, config)

        self.assertEqual(result, detector)

    # Test fallback_init initializes HideMe with correct args
    @patch("backend.app.services.initialization_service.log_warning")
    def test_fallback_init_hideme_init(self, _):
        key = "hideme_key"

        self.service._get_hideme_cache_key = MagicMock(return_value=key)

        self.service._hideme_detectors = {}

        self.service._initialize_hideme_detector = MagicMock()

        config = {"entities": ["phone"], "model_name": "hideme_model"}

        self.service._fallback_init(EntityDetectionEngine.HIDEME, config)

        self.service._initialize_hideme_detector.assert_called_with("hideme_model", ["phone"])

    # Test fallback_init returns cached hybrid detector if exists
    @patch("backend.app.services.initialization_service.log_warning")
    def test_fallback_init_hybrid_cached(self, _):
        key = "hybrid_key"

        config = {"mode": "standard"}

        self.service._get_hybrid_cache_key = MagicMock(return_value=key)

        detector = MagicMock()

        self.service._hybrid_detectors = {key: detector}

        result = self.service._fallback_init(EntityDetectionEngine.HYBRID, config)

        self.assertEqual(result, detector)

    # Test fallback_init initializes hybrid with correct args
    @patch("backend.app.services.initialization_service.log_warning")
    def test_fallback_init_hybrid_init(self, _):
        key = "hybrid_key"

        config = {"mode": "standard"}

        self.service._get_hybrid_cache_key = MagicMock(return_value=key)

        self.service._hybrid_detectors = {}

        self.service._initialize_hybrid_detector = MagicMock()

        self.service._fallback_init(EntityDetectionEngine.HYBRID, config)

        self.service._initialize_hybrid_detector.assert_called_with(config)

    # Test get_detector returns cached immediately without lock
    @patch.object(InitializationService, '_quick_check_cache', return_value='cached-detector')
    def test_get_detector_returns_cached_immediately(self, mock_cache):
        result = self.service.get_detector(EntityDetectionEngine.PRESIDIO)

        self.assertEqual(result, 'cached-detector')

        mock_cache.assert_called_once()

    # Test get_detector returns after short lock acquisition
    @patch.object(InitializationService, '_quick_check_cache', side_effect=[None, 'rechecked-detector'])
    @patch.object(InitializationService, '_try_acquire_lock', return_value=True)
    def test_get_detector_returns_after_short_lock(self, mock_lock, mock_cache):
        self.service._lock = MagicMock()

        result = self.service.get_detector(EntityDetectionEngine.PRESIDIO)

        self.assertEqual(result, 'rechecked-detector')

        self.assertEqual(mock_lock.call_count, 1)

        self.assertEqual(mock_cache.call_count, 2)

        self.service._lock.release.assert_called_once()

    # Test get_detector returns after long lock acquisition and initialization
    @patch.object(InitializationService, '_quick_check_cache', side_effect=[None, 'final-detector'])
    @patch.object(InitializationService, '_try_acquire_lock', side_effect=[False, True])
    @patch.object(InitializationService, '_initialize_and_store_detector', return_value='final-detector')
    def test_get_detector_returns_after_long_lock(self, mock_init, mock_lock, mock_cache):
        self.service._lock = MagicMock()

        result = self.service.get_detector(EntityDetectionEngine.GEMINI)

        self.assertEqual(result, 'final-detector')

        self.assertEqual(mock_lock.call_count, 2)

        self.assertEqual(mock_cache.call_count, 2)

        self.service._lock.release.assert_called_once()
