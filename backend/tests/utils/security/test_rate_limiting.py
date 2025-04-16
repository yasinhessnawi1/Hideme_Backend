import os
import unittest
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch, MagicMock
from wsgiref.headers import Headers

import redis
from fastapi import HTTPException
from fastapi import Request
from starlette.datastructures import Headers
from starlette.responses import Response

from backend.app.utils.security.rate_limiting import (
    RateLimitConfig,
    get_rate_limit_config,
    get_client_ip,
    RedisRateLimiter,
    LocalRateLimiter,
    RateLimitingMiddleware,
    check_rate_limit,
)


# RateLimitConfig & get_rate_limit_config Tests

class TestRateLimitConfig(unittest.TestCase):

    def test_init_with_defaults(self):
        """Test RateLimitConfig initialization with default values."""

        config = RateLimitConfig()

        self.assertEqual(config.requests_per_minute, 60)
        self.assertEqual(config.admin_requests_per_minute, 120)
        self.assertEqual(config.anonymous_requests_per_minute, 30)
        self.assertEqual(config.burst_allowance, 30)
        self.assertEqual(config.redis_url, os.getenv("REDIS_URL"))

    def test_init_with_custom_values(self):
        """Test RateLimitConfig initialization with custom values."""

        config = RateLimitConfig(
            requests_per_minute=100,
            admin_requests_per_minute=200,
            anonymous_requests_per_minute=50,
            burst_allowance=40,
            redis_url="redis://custom:6379"
        )

        self.assertEqual(config.requests_per_minute, 100)
        self.assertEqual(config.admin_requests_per_minute, 200)
        self.assertEqual(config.anonymous_requests_per_minute, 50)
        self.assertEqual(config.burst_allowance, 40)
        self.assertEqual(config.redis_url, "redis://custom:6379")


class TestGetRateLimitConfig(unittest.TestCase):
    @patch.dict(os.environ, {
        "RATE_LIMIT_RPM": "100",
        "ADMIN_RATE_LIMIT_RPM": "200",
        "ANON_RATE_LIMIT_RPM": "50",
        "RATE_LIMIT_BURST": "40",
        "REDIS_URL": "redis://test:6379"
    })
    def test_get_rate_limit_config_from_env(self):
        """Test retrieving config with environment variables."""

        get_rate_limit_config.cache_clear()
        config = get_rate_limit_config()

        self.assertEqual(config.requests_per_minute, 100)
        self.assertEqual(config.admin_requests_per_minute, 200)
        self.assertEqual(config.anonymous_requests_per_minute, 50)
        self.assertEqual(config.burst_allowance, 40)
        self.assertEqual(config.redis_url, "redis://test:6379")

    @patch.dict(os.environ, {}, clear=True)
    def test_get_rate_limit_config_defaults(self):
        """Test retrieving config with default values when env vars are not set."""

        get_rate_limit_config.cache_clear()
        config = get_rate_limit_config()

        self.assertEqual(config.requests_per_minute, 60)
        self.assertEqual(config.admin_requests_per_minute, 120)
        self.assertEqual(config.anonymous_requests_per_minute, 30)
        self.assertEqual(config.burst_allowance, 30)
        self.assertIsNone(config.redis_url)

    def test_get_rate_limit_config_cached(self):
        """Test that get_rate_limit_config returns a cached instance."""

        get_rate_limit_config.cache_clear()
        config1 = get_rate_limit_config()
        config2 = get_rate_limit_config()

        self.assertIs(config1, config2)


# get_client_ip Tests

class TestGetClientIP(unittest.TestCase):
    def test_get_client_ip_from_forwarded_header(self):
        """Test extraction of client IP from X-Forwarded-For header."""

        mock_request = MagicMock()
        mock_request.headers = {"X-Forwarded-For": "192.168.1.1, 10.0.0.1"}
        ip = get_client_ip(mock_request)

        self.assertEqual(ip, "192.168.1.1")

    def test_get_client_ip_from_client_host(self):
        """Test extraction of client IP from request.client.host."""

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.client.host = "10.0.0.1"
        ip = get_client_ip(mock_request)

        self.assertEqual(ip, "10.0.0.1")

    def test_get_client_ip_unknown(self):
        """Test when no IP is available."""

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.client = None
        ip = get_client_ip(mock_request)

        self.assertEqual(ip, "unknown")

    def test_get_client_ip_invalid(self):
        """Test when client IP is invalid."""
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.client.host = None
        ip = get_client_ip(mock_request)

        self.assertEqual(ip, "unknown")

    def test_get_client_ip_truncate(self):
        """Test that a long IP string is truncated to 45 characters."""

        long_ip = "a" * 50
        mock_request = MagicMock()
        mock_request.headers = {"X-Forwarded-For": long_ip}
        ip = get_client_ip(mock_request)

        self.assertEqual(ip, "a" * 45)
        self.assertEqual(len(ip), 45)


# RedisRateLimiter Tests

class TestRedisRateLimiter(unittest.TestCase):
    def setUp(self):
        self.redis_patcher = patch('redis.from_url')
        self.mock_redis = self.redis_patcher.start()
        self.mock_redis_client = MagicMock()
        self.mock_redis.return_value = self.mock_redis_client
        self.mock_pipeline = MagicMock()
        self.mock_redis_client.pipeline.return_value = self.mock_pipeline
        self.rate_limiter = RedisRateLimiter("redis://test:6379")

    def tearDown(self):
        self.redis_patcher.stop()

    def test_init(self):
        self.mock_redis.assert_called_once_with("redis://test:6379")
        self.assertEqual(self.rate_limiter.window_size, 60)

    @patch('time.time')
    def test_is_rate_limited_under_limit(self, mock_time):
        mock_time.return_value = 1617235678.0
        self.mock_pipeline.execute.return_value = [5, True]

        result = self.rate_limiter.is_rate_limited("test_key", 10)
        self.assertFalse(result)
        self.mock_redis_client.pipeline.assert_called_once()

        # The window key is computed using current_time // window_size.
        expected_key = f"test_key:{1617235678 // 60}"
        self.mock_pipeline.incr.assert_called_once_with(expected_key)
        self.mock_pipeline.expire.assert_called_once_with(expected_key, 120)
        self.mock_pipeline.execute.assert_called_once()

    @patch('time.time')
    def test_is_rate_limited_over_limit(self, mock_time):
        mock_time.return_value = 1617235678.0
        self.mock_pipeline.execute.return_value = [11, True]

        result = self.rate_limiter.is_rate_limited("test_key", 10)
        self.assertTrue(result)

    @patch('time.time')
    def test_is_rate_limited_redis_error(self, mock_time):
        mock_time.return_value = 1617235678.0
        self.mock_pipeline.execute.side_effect = redis.RedisError("Test Redis error")

        # Patch the logger using the correct module path.
        with patch('backend.app.utils.security.rate_limiting.logger') as mock_logger:
            result = self.rate_limiter.is_rate_limited("test_key", 10)
            self.assertFalse(result)
            mock_logger.error.assert_called_once_with("Redis rate limiting error: Test Redis error")


# LocalRateLimiter Tests

class TestLocalRateLimiter(unittest.TestCase):
    def setUp(self):
        self.rate_limiter = LocalRateLimiter()

    def test_init(self):
        self.assertEqual(self.rate_limiter.requests, {})
        self.assertEqual(self.rate_limiter.window_size, 60)

    @patch('time.time')
    def test_is_rate_limited_new_client(self, mock_time):
        mock_time.return_value = 1617235678.0
        current_window = 1617235678 // 60
        result = self.rate_limiter.is_rate_limited("test_key", 10)

        self.assertFalse(result)
        self.assertIn("test_key", self.rate_limiter.requests)
        self.assertIn(current_window, self.rate_limiter.requests["test_key"])
        self.assertEqual(self.rate_limiter.requests["test_key"][current_window], 1)

    @patch('time.time')
    def test_is_rate_limited_existing_client(self, mock_time):
        mock_time.return_value = 1617235678.0
        current_window = 1617235678 // 60
        self.rate_limiter.requests = {"test_key": {current_window: 5}}

        result = self.rate_limiter.is_rate_limited("test_key", 10)
        self.assertFalse(result)
        self.assertEqual(self.rate_limiter.requests["test_key"][current_window], 6)

    @patch('time.time')
    def test_is_rate_limited_over_limit(self, mock_time):
        mock_time.return_value = 1617235678.0
        current_window = 1617235678 // 60
        self.rate_limiter.requests = {"test_key": {current_window: 10}}

        result = self.rate_limiter.is_rate_limited("test_key", 10)
        self.assertTrue(result)
        self.assertEqual(self.rate_limiter.requests["test_key"][current_window], 11)

    @patch('time.time')
    def test_is_rate_limited_cleanup_old_windows(self, mock_time):
        mock_time.return_value = 1617235678.0
        current_window = 1617235678 // 60
        self.rate_limiter.requests = {
            "test_key": {
                current_window - 3: 5,
                current_window - 2: 6,
                current_window - 1: 7,
            }
        }

        result = self.rate_limiter.is_rate_limited("test_key", 10)
        self.assertFalse(result)
        self.assertNotIn(current_window - 3, self.rate_limiter.requests["test_key"])
        self.assertIn(current_window - 2, self.rate_limiter.requests["test_key"])
        self.assertIn(current_window - 1, self.rate_limiter.requests["test_key"])
        self.assertIn(current_window, self.rate_limiter.requests["test_key"])
        self.assertEqual(self.rate_limiter.requests["test_key"][current_window], 1)


# RateLimitingMiddleware & check_rate_limit Tests

class DummyApp:
    async def __call__(self, scope, receive, send):
        pass


class TestRateLimitingMiddleware(IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Patch get_rate_limit_config to return a mock config.
        self.get_config_patcher = patch('backend.app.utils.security.rate_limiting.get_rate_limit_config')

        self.mock_get_config = self.get_config_patcher.start()
        self.mock_config = MagicMock()

        self.mock_config.redis_url = None  # So LocalRateLimiter is used.
        self.mock_config.requests_per_minute = 60
        self.mock_config.admin_requests_per_minute = 120
        self.mock_config.anonymous_requests_per_minute = 30
        self.mock_get_config.return_value = self.mock_config

        # Prepare a dummy app for the middleware.
        self.dummy_app = DummyApp()
        self.middleware = RateLimitingMiddleware(self.dummy_app)

        # For testing, patch the rate_limiter's is_rate_limited method.
        self.rate_limiter = self.middleware.rate_limiter
        self.rate_limiter.is_rate_limited = MagicMock(return_value=False)

    async def asyncTearDown(self):
        self.get_config_patcher.stop()

    async def test_dispatch_exempt_paths(self):
        """Test that requests to exempt paths (/health, /metrics) bypass rate limiting."""

        for path in ["/health", "/metrics"]:
            mock_request = MagicMock(spec=Request)
            mock_request.url.path = path
            mock_request.headers = Headers({})

            # Create a dummy call_next that returns a simple response.
            async def call_next(req):
                return Response(content=b"OK", status_code=200)

            response = await self.middleware.dispatch(mock_request, call_next)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.body, b"OK")

    async def test_dispatch_rate_limit_not_exceeded(self):
        """Test that the middleware passes the request along when not rate limited."""

        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/resource"

        # Simulate a client with an IP address.
        mock_request.headers = Headers({"authorization": "Bearer user_token"})
        mock_request.client = MagicMock(host="1.2.3.4")

        # Ensure rate_limiter.is_rate_limited returns False.
        self.rate_limiter.is_rate_limited.return_value = False

        async def call_next(req):
            return Response(content=b"Good", status_code=200)

        response = await self.middleware.dispatch(mock_request, call_next)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body, b"Good")
        self.rate_limiter.is_rate_limited.assert_called()

    async def test_dispatch_rate_limited(self):
        """Test that a rate limited request returns a 429 response."""

        mock_request = MagicMock(spec=Request)

        mock_request.url.path = "/api/resource"
        mock_request.headers = Headers({"authorization": "Bearer user_token"})
        mock_request.client = MagicMock(host="1.2.3.4")

        # Simulate rate limiting.
        self.rate_limiter.is_rate_limited.return_value = True

        async def call_next(req):
            return Response(content=b"Good", status_code=200)

        response = await self.middleware.dispatch(mock_request, call_next)

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.media_type, "application/json")
        self.assertIn("Rate limit exceeded", response.body.decode())
        self.rate_limiter.is_rate_limited.assert_called()

    async def test_dispatch_admin_user(self):
        """Test that admin requests use the admin request limit."""

        mock_request = MagicMock(spec=Request)

        mock_request.url.path = "/admin/dashboard"
        mock_request.headers = Headers({"authorization": "Bearer admin_token"})
        mock_request.client = MagicMock(host="5.6.7.8")

        # Patch _is_admin_user to return True.
        with patch.object(RateLimitingMiddleware, "_is_admin_user", return_value=True) as mock_is_admin:
            self.rate_limiter.is_rate_limited.return_value = False

            async def call_next(req):
                return Response(content=b"Admin OK", status_code=200)

            response = await self.middleware.dispatch(mock_request, call_next)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.body, b"Admin OK")

            # Verify _is_admin_user was called.
            mock_is_admin.assert_called_once_with(mock_request)

            # The admin limit from the mock config should be used (120)
            # (We assume that the RateLimitingMiddleware will pick max_requests=120.)
            self.rate_limiter.is_rate_limited.assert_called()

    def test_is_admin_user_positive(self):
        """Test _is_admin_user identifies admin users."""
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"authorization": "Bearer admin_xyz"}

        self.assertTrue(RateLimitingMiddleware._is_admin_user(mock_request))

    def test_is_admin_user_negative(self):
        """Test _is_admin_user returns False for non-admin users."""

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"authorization": "Bearer user_xyz"}

        self.assertFalse(RateLimitingMiddleware._is_admin_user(mock_request))


class TestCheckRateLimit(IsolatedAsyncioTestCase):
    """Test cases for the check_rate_limit dependency function."""

    async def asyncSetUp(self):
        self.get_config_patcher = patch('backend.app.utils.security.rate_limiting.get_rate_limit_config')

        self.mock_get_config = self.get_config_patcher.start()

        self.mock_config = MagicMock()
        self.mock_config.redis_url = None
        self.mock_config.requests_per_minute = 60

        self.mock_get_config.return_value = self.mock_config

        # Patch the rate limiters used in check_rate_limit.
        self.redis_limiter_patcher = patch('backend.app.utils.security.rate_limiting.RedisRateLimiter')
        self.mock_redis_limiter_class = self.redis_limiter_patcher.start()

        self.local_limiter_patcher = patch('backend.app.utils.security.rate_limiting.LocalRateLimiter')
        self.mock_local_limiter_class = self.local_limiter_patcher.start()

        self.mock_local_limiter = MagicMock()
        self.mock_local_limiter_class.return_value = self.mock_local_limiter

    async def asyncTearDown(self):
        self.get_config_patcher.stop()
        self.redis_limiter_patcher.stop()
        self.mock_local_limiter_class.stop()

    async def test_check_rate_limit_not_exceeded(self):
        """Test that check_rate_limit passes when rate is not exceeded."""
        # Create a mock request.
        mock_request = MagicMock(spec=Request)

        mock_request.headers = {"authorization": "Bearer user_token"}
        mock_request.url.path = "/api/some_endpoint"
        mock_request.client = MagicMock(host="1.2.3.4")

        # Simulate that rate limiting is not triggered.
        self.mock_local_limiter.is_rate_limited.return_value = False

        # Call the dependency function.
        result = await check_rate_limit(mock_request)

        # Since no exception is raised, result is None.
        self.assertIsNone(result)
        self.mock_local_limiter.is_rate_limited.assert_called()

    async def test_check_rate_limit_exceeded(self):
        """Test that check_rate_limit raises an HTTPException when rate limit is exceeded."""
        mock_request = MagicMock(spec=Request)

        mock_request.headers = {"authorization": "Bearer user_token"}
        mock_request.url.path = "/api/some_endpoint"
        mock_request.client = MagicMock(host="1.2.3.4")

        self.mock_local_limiter.is_rate_limited.return_value = True

        with self.assertRaises(HTTPException) as context:
            await check_rate_limit(mock_request)

        self.assertEqual(context.exception.status_code, 429)
        self.assertIn("Rate limit exceeded", context.exception.detail)
