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


# Test RateLimitConfig initialization defaults and custom values
class TestRateLimitConfig(unittest.TestCase):
    """Tests for RateLimitConfig initialization."""

    # default parameters should match expected defaults
    def test_init_with_defaults(self):
        config = RateLimitConfig()

        self.assertEqual(config.requests_per_minute, 60)

        self.assertEqual(config.admin_requests_per_minute, 120)

        self.assertEqual(config.anonymous_requests_per_minute, 30)

        self.assertEqual(config.burst_allowance, 30)

        self.assertEqual(config.redis_url, os.getenv("REDIS_URL"))

    # custom parameters override defaults
    def test_init_with_custom_values(self):
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


# Test get_rate_limit_config reading from environment and caching
class TestGetRateLimitConfig(unittest.TestCase):
    """Tests for get_rate_limit_config function."""

    @patch.dict(os.environ, {
        "RATE_LIMIT_RPM": "100",
        "ADMIN_RATE_LIMIT_RPM": "200",
        "ANON_RATE_LIMIT_RPM": "50",
        "RATE_LIMIT_BURST": "40",
        "REDIS_URL": "redis://test:6379"
    })
    # should read values from environment
    def test_get_rate_limit_config_from_env(self):
        get_rate_limit_config.cache_clear()

        config = get_rate_limit_config()

        self.assertEqual(config.requests_per_minute, 100)

        self.assertEqual(config.admin_requests_per_minute, 200)

        self.assertEqual(config.anonymous_requests_per_minute, 50)

        self.assertEqual(config.burst_allowance, 40)

        self.assertEqual(config.redis_url, "redis://test:6379")

    @patch.dict(os.environ, {}, clear=True)
    # should fall back to defaults if env vars unset
    def test_get_rate_limit_config_defaults(self):
        get_rate_limit_config.cache_clear()

        config = get_rate_limit_config()

        self.assertEqual(config.requests_per_minute, 60)

        self.assertEqual(config.admin_requests_per_minute, 120)

        self.assertEqual(config.anonymous_requests_per_minute, 30)

        self.assertEqual(config.burst_allowance, 30)

        self.assertIsNone(config.redis_url)

    # second call should return cached instance
    def test_get_rate_limit_config_cached(self):
        get_rate_limit_config.cache_clear()

        config1 = get_rate_limit_config()

        config2 = get_rate_limit_config()

        self.assertIs(config1, config2)


# Test client IP extraction from request
class TestGetClientIP(unittest.TestCase):
    """Tests for get_client_ip function."""

    # should parse X-Forwarded-For header
    def test_get_client_ip_from_forwarded_header(self):
        mock_request = MagicMock()

        mock_request.headers = {"X-Forwarded-For": "192.168.1.1, 10.0.0.1"}

        ip = get_client_ip(mock_request)

        self.assertEqual(ip, "192.168.1.1")

    # should use request.client.host when header missing
    def test_get_client_ip_from_client_host(self):
        mock_request = MagicMock()

        mock_request.headers = {}

        mock_request.client.host = "10.0.0.1"

        ip = get_client_ip(mock_request)

        self.assertEqual(ip, "10.0.0.1")

    # should return 'unknown' if no client info
    def test_get_client_ip_unknown(self):
        mock_request = MagicMock()

        mock_request.headers = {}

        mock_request.client = None

        ip = get_client_ip(mock_request)

        self.assertEqual(ip, "unknown")

    # invalid host should be treated as unknown
    def test_get_client_ip_invalid(self):
        mock_request = MagicMock()

        mock_request.headers = {}

        mock_request.client.host = None

        ip = get_client_ip(mock_request)

        self.assertEqual(ip, "unknown")

    # long IP strings should be truncated to 45 chars
    def test_get_client_ip_truncate(self):
        long_ip = "a" * 50

        mock_request = MagicMock()

        mock_request.headers = {"X-Forwarded-For": long_ip}

        ip = get_client_ip(mock_request)

        self.assertEqual(ip, "a" * 45)

        self.assertEqual(len(ip), 45)


# Test Redis-based rate limiter behavior
class TestRedisRateLimiter(unittest.TestCase):
    """Tests for RedisRateLimiter class."""

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

    # initialization should create Redis client and set window_size
    def test_init(self):
        self.mock_redis.assert_called_once_with("redis://test:6379")

        self.assertEqual(self.rate_limiter.window_size, 60)

    @patch('time.time')
    # under limit should not rate limit and set expire/incr
    def test_is_rate_limited_under_limit(self, mock_time):
        mock_time.return_value = 1617235678.0

        self.mock_pipeline.execute.return_value = [5, True]

        result = self.rate_limiter.is_rate_limited("test_key", 10)

        self.assertFalse(result)

        expected_key = f"test_key:{1617235678 // 60}"

        self.mock_pipeline.incr.assert_called_once_with(expected_key)

        self.mock_pipeline.expire.assert_called_once_with(expected_key, 120)

        self.mock_pipeline.execute.assert_called_once()

    @patch('time.time')
    # over limit should return True
    def test_is_rate_limited_over_limit(self, mock_time):
        mock_time.return_value = 1617235678.0

        self.mock_pipeline.execute.return_value = [11, True]

        result = self.rate_limiter.is_rate_limited("test_key", 10)

        self.assertTrue(result)

    @patch('time.time')
    # Redis errors should be caught and treated as no rate limit
    def test_is_rate_limited_redis_error(self, mock_time):
        mock_time.return_value = 1617235678.0

        self.mock_pipeline.execute.side_effect = redis.RedisError("Test Redis error")

        with patch('backend.app.utils.security.rate_limiting.logger') as mock_logger:
            result = self.rate_limiter.is_rate_limited("test_key", 10)

            self.assertFalse(result)

            mock_logger.error.assert_called_once_with(
                "Redis rate limiting error: Test Redis error"
            )


# Test in-memory rate limiter behavior
class TestLocalRateLimiter(unittest.TestCase):
    """Tests for LocalRateLimiter class."""

    def setUp(self):
        self.rate_limiter = LocalRateLimiter()

    # initial state should be empty with default window_size
    def test_init(self):
        self.assertEqual(self.rate_limiter.requests, {})

        self.assertEqual(self.rate_limiter.window_size, 60)

    @patch('time.time')
    # new client should get a counter of 1
    def test_is_rate_limited_new_client(self, mock_time):
        mock_time.return_value = 1617235678.0

        current_window = 1617235678 // 60

        result = self.rate_limiter.is_rate_limited("test_key", 10)

        self.assertFalse(result)

        self.assertEqual(
            self.rate_limiter.requests["test_key"][current_window],
            1
        )

    @patch('time.time')
    # existing client under limit should increment count
    def test_is_rate_limited_existing_client(self, mock_time):
        mock_time.return_value = 1617235678.0

        current_window = 1617235678 // 60

        self.rate_limiter.requests = {"test_key": {current_window: 5}}

        result = self.rate_limiter.is_rate_limited("test_key", 10)

        self.assertFalse(result)

        self.assertEqual(
            self.rate_limiter.requests["test_key"][current_window],
            6
        )

    @patch('time.time')
    # exceeding limit should return True and increment
    def test_is_rate_limited_over_limit(self, mock_time):
        mock_time.return_value = 1617235678.0

        current_window = 1617235678 // 60

        self.rate_limiter.requests = {"test_key": {current_window: 10}}

        result = self.rate_limiter.is_rate_limited("test_key", 10)

        self.assertTrue(result)

        self.assertEqual(
            self.rate_limiter.requests["test_key"][current_window],
            11
        )

    @patch('time.time')
    # old windows beyond burst_allowance should be cleaned up
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

        self.assertNotIn(
            current_window - 3,
            self.rate_limiter.requests["test_key"]
        )

        self.assertEqual(
            self.rate_limiter.requests["test_key"][current_window],
            1
        )


# Dummy ASGI app for middleware tests
class DummyApp:
    """A dummy ASGI app for RateLimitingMiddleware."""

    async def __call__(self, scope, receive, send):
        pass


# Test RateLimitingMiddleware dispatch logic
class TestRateLimitingMiddleware(IsolatedAsyncioTestCase):
    """Tests for RateLimitingMiddleware behavior."""

    async def asyncSetUp(self):
        self.get_config_patcher = patch(
            'backend.app.utils.security.rate_limiting.get_rate_limit_config'
        )

        self.mock_get_config = self.get_config_patcher.start()

        self.mock_config = MagicMock()

        self.mock_config.redis_url = None

        self.mock_config.requests_per_minute = 60

        self.mock_config.admin_requests_per_minute = 120

        self.mock_config.anonymous_requests_per_minute = 30

        self.mock_get_config.return_value = self.mock_config

        self.dummy_app = DummyApp()

        self.middleware = RateLimitingMiddleware(self.dummy_app)

        self.rate_limiter = self.middleware.rate_limiter

        self.rate_limiter.is_rate_limited = MagicMock(return_value=False)

    async def asyncTearDown(self):
        self.get_config_patcher.stop()

    # health and metrics endpoints bypass rate limiting
    async def test_dispatch_exempt_paths(self):
        for path in ["/health", "/metrics"]:
            mock_request = MagicMock(spec=Request)

            mock_request.url.path = path

            mock_request.headers = Headers({})

            async def call_next(req):
                return Response(content=b"OK", status_code=200)

            response = await self.middleware.dispatch(mock_request, call_next)

            self.assertEqual(response.status_code, 200)

            self.assertEqual(response.body, b"OK")

    # non-admin requests under limit should pass through
    async def test_dispatch_rate_limit_not_exceeded(self):
        mock_request = MagicMock(spec=Request)

        mock_request.url.path = "/api/resource"

        mock_request.headers = Headers({"authorization": "Bearer user_token"})

        mock_request.client = MagicMock(host="1.2.3.4")

        self.rate_limiter.is_rate_limited.return_value = False

        async def call_next(req):
            return Response(content=b"Good", status_code=200)

        response = await self.middleware.dispatch(mock_request, call_next)

        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.body, b"Good")

        self.rate_limiter.is_rate_limited.assert_called()

    # requests over limit should get 429 response
    async def test_dispatch_rate_limited(self):
        mock_request = MagicMock(spec=Request)

        mock_request.url.path = "/api/resource"

        mock_request.headers = Headers({"authorization": "Bearer user_token"})

        mock_request.client = MagicMock(host="1.2.3.4")

        self.rate_limiter.is_rate_limited.return_value = True

        async def call_next(req):
            return Response(content=b"Good", status_code=200)

        response = await self.middleware.dispatch(mock_request, call_next)

        self.assertEqual(response.status_code, 429)

        self.assertEqual(response.media_type, "application/json")

        self.assertIn("Rate limit exceeded", response.body.decode())

        self.rate_limiter.is_rate_limited.assert_called()

    # admin users should use the higher admin limit
    async def test_dispatch_admin_user(self):
        mock_request = MagicMock(spec=Request)

        mock_request.url.path = "/admin/dashboard"

        mock_request.headers = Headers({"authorization": "Bearer admin_token"})

        mock_request.client = MagicMock(host="5.6.7.8")

        with patch.object(RateLimitingMiddleware, "_is_admin_user", return_value=True) as mock_is_admin:
            self.rate_limiter.is_rate_limited.return_value = False

            async def call_next(req):
                return Response(content=b"Admin OK", status_code=200)

            response = await self.middleware.dispatch(mock_request, call_next)

            self.assertEqual(response.status_code, 200)

            self.assertEqual(response.body, b"Admin OK")

            mock_is_admin.assert_called_once_with(mock_request)

            self.rate_limiter.is_rate_limited.assert_called()

    # _is_admin_user should detect admin tokens
    def test_is_admin_user_positive(self):
        mock_request = MagicMock(spec=Request)

        mock_request.headers = {"authorization": "Bearer admin_xyz"}

        self.assertTrue(RateLimitingMiddleware._is_admin_user(mock_request))

    # non-admin tokens should not be considered admin
    def test_is_admin_user_negative(self):
        mock_request = MagicMock(spec=Request)

        mock_request.headers = {"authorization": "Bearer user_xyz"}

        self.assertFalse(RateLimitingMiddleware._is_admin_user(mock_request))


# Test check_rate_limit dependency raises or passes as appropriate
class TestCheckRateLimit(IsolatedAsyncioTestCase):
    """Tests for check_rate_limit dependency function."""

    async def asyncSetUp(self):
        self.get_config_patcher = patch(
            'backend.app.utils.security.rate_limiting.get_rate_limit_config'
        )

        self.mock_get_config = self.get_config_patcher.start()

        self.mock_config = MagicMock()

        self.mock_config.redis_url = None

        self.mock_config.requests_per_minute = 60

        self.mock_get_config.return_value = self.mock_config

        self.redis_limiter_patcher = patch(
            'backend.app.utils.security.rate_limiting.RedisRateLimiter'
        )

        self.mock_redis_limiter_class = self.redis_limiter_patcher.start()

        self.local_limiter_patcher = patch(
            'backend.app.utils.security.rate_limiting.LocalRateLimiter'
        )

        self.mock_local_limiter_class = self.local_limiter_patcher.start()

        self.mock_local_limiter = MagicMock()

        self.mock_local_limiter_class.return_value = self.mock_local_limiter

    async def asyncTearDown(self):
        self.get_config_patcher.stop()

        self.redis_limiter_patcher.stop()

        self.local_limiter_patcher.stop()

    # when under limit, should not raise
    async def test_check_rate_limit_not_exceeded(self):
        mock_request = MagicMock(spec=Request)

        mock_request.headers = {"authorization": "Bearer user_token"}

        mock_request.url.path = "/api/some_endpoint"

        mock_request.client = MagicMock(host="1.2.3.4")

        self.mock_local_limiter.is_rate_limited.return_value = False

        result = await check_rate_limit(mock_request)

        self.assertIsNone(result)

        self.mock_local_limiter.is_rate_limited.assert_called()

    # when over limit, should raise HTTPException 429
    async def test_check_rate_limit_exceeded(self):
        mock_request = MagicMock(spec=Request)

        mock_request.headers = {"authorization": "Bearer user_token"}

        mock_request.url.path = "/api/some_endpoint"

        mock_request.client = MagicMock(host="1.2.3.4")

        self.mock_local_limiter.is_rate_limited.return_value = True

        with self.assertRaises(HTTPException) as context:
            await check_rate_limit(mock_request)

        self.assertEqual(context.exception.status_code, 429)

        self.assertIn("Rate limit exceeded", context.exception.detail)
