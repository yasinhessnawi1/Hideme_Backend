import hashlib

import json

import time

import unittest

from unittest.mock import patch, MagicMock, AsyncMock

from fastapi import Request, Response

from starlette.datastructures import Headers, QueryParams, URL

from backend.app.utils.security.caching_middleware import (
    ResponseCache,
    CacheMiddleware,
    response_cache,
    custom_file_cache_key_builder,
    get_cached_response,
    cache_response,
    clear_cached_response,
    invalidate_cache
)

from backend.app.utils.system_utils.synchronization_utils import LockPriority


# Tests for ResponseCache class
class TestResponseCache(unittest.TestCase):
    """Test cases for ResponseCache class."""

    # set up logging and lock mocks for each test
    def setUp(self):

        self.log_info_patcher = patch(
            'backend.app.utils.security.caching_middleware.log_info'
        )

        self.mock_log_info = self.log_info_patcher.start()

        self.log_warning_patcher = patch(
            'backend.app.utils.security.caching_middleware.log_warning'
        )

        self.mock_log_warning = self.log_warning_patcher.start()

        self.timeout_lock_patcher = patch(
            'backend.app.utils.security.caching_middleware.TimeoutLock'
        )

        self.mock_timeout_lock = self.timeout_lock_patcher.start()

        self.mock_lock_instance = MagicMock()

        self.mock_timeout_lock.return_value = self.mock_lock_instance

        self.cache = ResponseCache(max_size=10, default_ttl=60)

    # tear down logging and lock mocks
    def tearDown(self):

        self.log_info_patcher.stop()

        self.log_warning_patcher.stop()

        self.timeout_lock_patcher.stop()

    # initialization parameters logged correctly
    def test_init(self):

        self.assertEqual(self.cache.max_size, 10)

        self.assertEqual(self.cache.default_ttl, 60)

        self.assertEqual(self.cache.cache, {})

        self.assertEqual(self.cache.access_times, {})

        self.assertEqual(self.cache.expiration_times, {})

        self.assertEqual(self.cache.etags, {})

        self.assertIsNone(self.cache._rwlock)

        self.mock_log_info.assert_called_once_with(
            "Response cache initialized with max_size=10, default_ttl=60s"
        )

    # lazy rwlock property initialization
    def test_rwlock_property_lazy_initialization(self):

        self.assertIsNone(self.cache._rwlock)

        lock = self.cache.rwlock

        self.mock_timeout_lock.assert_called_once_with(
            "response_cache_lock",
            priority=LockPriority.LOW
        )

        self.assertIsNotNone(self.cache._rwlock)

        self.assertEqual(lock, self.mock_lock_instance)

    # retrieving a valid, unexpired entry
    def test_get_with_valid_entry(self):

        self.cache.cache["test_key"] = "test_value"

        current_time = time.time()

        self.cache.expiration_times["test_key"] = current_time + 60

        result = self.cache.get("test_key")

        self.assertEqual(result, "test_value")

        self.assertIn("test_key", self.cache.access_times)

        self.assertAlmostEqual(
            self.cache.access_times["test_key"],
            current_time,
            delta=1
        )

    # retrieving an expired entry returns None
    def test_get_with_expired_entry(self):

        self.cache.cache["test_key"] = "test_value"

        self.cache.expiration_times["test_key"] = time.time() - 10

        result = self.cache.get("test_key")

        self.assertIsNone(result)

    # retrieving a nonexistent key returns None
    def test_get_with_nonexistent_key(self):

        result = self.cache.get("nonexistent_key")

        self.assertIsNone(result)

    # access time update errors are caught and warned
    def test_get_with_access_time_error(self):

        self.cache.cache["test_key"] = "test_value"

        self.cache.expiration_times["test_key"] = time.time() + 60

        self.cache.access_times = MagicMock()

        self.cache.access_times.__getitem__ = MagicMock(
            side_effect=Exception("Test error")
        )

        self.cache.access_times.__setitem__ = MagicMock(
            side_effect=Exception("Test error")
        )

        result = self.cache.get("test_key")

        self.assertEqual(result, "test_value")

        self.mock_log_warning.assert_called_once()

        self.assertIn(
            "Error updating access time",
            self.mock_log_warning.call_args[0][0]
        )

    # setting a key with custom TTL and hash acquires lock
    @patch('time.time')
    def test_set_success(self, mock_time):

        mock_time.return_value = 1000.0

        result = self.cache.set(
            "test_key",
            "test_value",
            ttl=120,
            content_hash="test_hash"
        )

        self.mock_lock_instance.acquire.assert_called_once_with(timeout=5.0)

        self.mock_lock_instance.release.assert_called_once()

        self.assertTrue(result)

        self.assertEqual(self.cache.cache["test_key"], "test_value")

        self.assertEqual(self.cache.access_times["test_key"], 1000.0)

        self.assertEqual(
            self.cache.expiration_times["test_key"],
            1120.0
        )

        self.assertEqual(self.cache.etags["test_key"], "test_hash")

    # setting a key without TTL uses default_ttl
    @patch('time.time')
    def test_set_with_default_ttl(self, mock_time):

        mock_time.return_value = 1000.0

        result = self.cache.set("test_key", "test_value")

        self.assertTrue(result)

        self.assertEqual(
            self.cache.expiration_times["test_key"],
            1060.0
        )

    # lock acquisition timeout returns False
    def test_set_lock_timeout(self):

        self.mock_lock_instance.acquire.side_effect = TimeoutError(
            "Lock timeout"
        )

        result = self.cache.set("test_key", "test_value")

        self.assertFalse(result)

        self.mock_log_warning.assert_called_once_with(
            "Timeout acquiring write lock for cache key: test_key"
        )

        self.assertNotIn("test_key", self.cache.cache)

    # expired entries cleaned when cache full
    @patch('time.time')
    def test_set_with_cleanup_expired(self, mock_time):

        mock_time.return_value = 1000.0

        for i in range(10):

            self.cache.cache[f"key{i}"] = f"value{i}"

            self.cache.access_times[f"key{i}"] = 900.0

            if i < 5:
                self.cache.expiration_times[f"key{i}"] = 990.0
            else:
                self.cache.expiration_times[f"key{i}"] = 1100.0

        result = self.cache.set("new_key", "new_value")

        self.assertTrue(result)

        for i in range(5):
            self.assertNotIn(f"key{i}", self.cache.cache)

        for i in range(5, 10):
            self.assertIn(f"key{i}", self.cache.cache)

        self.assertEqual(self.cache.cache["new_key"], "new_value")

    # LRU removal when cache still full after cleanup
    @patch('time.time')
    def test_set_with_lru_removal(self, mock_time):

        mock_time.return_value = 1000.0

        for i in range(10):
            self.cache.cache[f"key{i}"] = f"value{i}"

            self.cache.access_times[f"key{i}"] = 900.0 + i

            self.cache.expiration_times[f"key{i}"] = 1100.0

        result = self.cache.set("new_key", "new_value")

        self.assertTrue(result)

        self.assertNotIn("key0", self.cache.cache)

        for i in range(1, 10):
            self.assertIn(f"key{i}", self.cache.cache)

        self.assertEqual(self.cache.cache["new_key"], "new_value")

    # deleting an existing key acquires lock and removes it
    def test_delete_success(self):

        now = time.time()

        self.cache.cache["test_key"] = "test_value"

        self.cache.access_times["test_key"] = now

        self.cache.expiration_times["test_key"] = now + 60

        self.cache.etags["test_key"] = "test_hash"

        result = self.cache.delete("test_key")

        self.mock_lock_instance.acquire.assert_called_once_with(timeout=3.0)

        self.mock_lock_instance.release.assert_called_once()

        self.assertTrue(result)

        self.assertNotIn("test_key", self.cache.cache)

        self.assertNotIn("test_key", self.cache.access_times)

        self.assertNotIn("test_key", self.cache.expiration_times)

        self.assertNotIn("test_key", self.cache.etags)

    # deleting a nonexistent key returns False
    def test_delete_nonexistent_key(self):

        result = self.cache.delete("nonexistent_key")

        self.assertFalse(result)

    # delete lock timeout logs warning and returns False
    def test_delete_lock_timeout(self):

        self.cache.cache["test_key"] = "test_value"

        self.mock_lock_instance.acquire.side_effect = TimeoutError(
            "Lock timeout"
        )

        result = self.cache.delete("test_key")

        self.assertFalse(result)

        self.assertIn("test_key", self.cache.cache)

        self.mock_log_warning.assert_called_once_with(
            "Timeout acquiring write lock for deleting cache key: test_key"
        )

    # clearing cache acquires lock and removes all entries
    def test_clear_success(self):

        self.cache.cache = {"key1": "value1", "key2": "value2"}

        self.cache.access_times = {"key1": 1000.0, "key2": 1100.0}

        self.cache.expiration_times = {"key1": 2000.0, "key2": 2100.0}

        self.cache.etags = {"key1": "hash1", "key2": "hash2"}

        result = self.cache.clear()

        self.mock_lock_instance.acquire.assert_called_once_with(timeout=10.0)

        self.mock_lock_instance.release.assert_called_once()

        self.assertTrue(result)

        self.assertEqual(self.cache.cache, {})

        self.assertEqual(self.cache.access_times, {})

        self.assertEqual(self.cache.expiration_times, {})

        self.assertEqual(self.cache.etags, {})

        self.mock_log_info.assert_called_with("Response cache cleared")

    # clear lock timeout logs warning and fails
    def test_clear_lock_timeout(self):

        self.cache.cache = {"key1": "value1", "key2": "value2"}

        self.mock_lock_instance.acquire.side_effect = TimeoutError(
            "Lock timeout"
        )

        result = self.cache.clear()

        self.assertFalse(result)

        self.assertEqual(self.cache.cache, {"key1": "value1", "key2": "value2"})

        self.mock_log_warning.assert_called_once_with(
            "Timeout acquiring write lock for clearing cache"
        )

    # internal cleanup removes only expired entries
    @patch('time.time')
    def test_cleanup_expired_internal(self, mock_time):

        mock_time.return_value = 1000.0

        self.cache.cache = {
            "expired1": "value1",
            "expired2": "value2",
            "valid1": "value3",
            "valid2": "value4"
        }

        self.cache.access_times = {
            "expired1": 900.0,
            "expired2": 950.0,
            "valid1": 980.0,
            "valid2": 990.0
        }

        self.cache.expiration_times = {
            "expired1": 990.0,
            "expired2": 995.0,
            "valid1": 1100.0,
            "valid2": 1200.0
        }

        self.cache.etags = {
            "expired1": "hash1",
            "expired2": "hash2",
            "valid1": "hash3",
            "valid2": "hash4"
        }

        removed = self.cache._cleanup_expired()

        self.assertEqual(removed, 2)

        self.assertNotIn("expired1", self.cache.cache)

        self.assertNotIn("expired2", self.cache.cache)

        self.assertNotIn("expired1", self.cache.access_times)

        self.assertNotIn("expired2", self.cache.access_times)

        self.assertNotIn("expired1", self.cache.expiration_times)

        self.assertNotIn("expired2", self.cache.expiration_times)

        self.assertNotIn("expired1", self.cache.etags)

        self.assertNotIn("expired2", self.cache.etags)


# Dummy ASGI app for CacheMiddleware tests
class DummyApp:
    """A dummy ASGI application for testing."""

    # ASGI callable does nothing
    async def __call__(self, scope, receive, send):
        pass


# Tests for CacheMiddleware class
class TestCacheMiddleware(unittest.IsolatedAsyncioTestCase):
    """Test cases for CacheMiddleware dispatch logic."""

    # set up middleware and clear global cache
    async def asyncSetUp(self):
        self.paths = ["/test", "/api"]

        self.middleware = CacheMiddleware(
            app=DummyApp(),
            paths=self.paths,
            ttl=300
        )

        response_cache.cache.clear()

        response_cache.access_times.clear()

        response_cache.expiration_times.clear()

        response_cache.etags.clear()

    # path matching prefixes should be cached
    async def test_should_cache_path_positive(self):
        self.assertTrue(
            self.middleware._should_cache_path("/test/resource")
        )

        self.assertTrue(
            self.middleware._should_cache_path("/api/data")
        )

    # non-matching paths should not be cached
    async def test_should_cache_path_negative(self):
        self.assertFalse(
            self.middleware._should_cache_path("/other/path")
        )

        self.assertFalse(
            self.middleware._should_cache_path("/static/image.png")
        )

    # non-GET/POST methods bypass caching
    async def test_dispatch_non_cached_method(self):
        dummy_request = MagicMock(spec=Request)

        dummy_request.method = "PUT"

        dummy_request.url = URL("http://testserver/api/resource")

        dummy_request.headers = Headers({})

        dummy_response = Response(
            content=b"put response",
            status_code=200,
            headers={"Content-Type": "text/plain"}
        )

        call_next = AsyncMock(return_value=dummy_response)

        response = await self.middleware.dispatch(dummy_request, call_next)

        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.body, b"put response")

        call_next.assert_called_once_with(dummy_request)

    # key builder exceptions forward request
    async def test_dispatch_key_builder_exception(self):
        dummy_request = MagicMock(spec=Request)

        dummy_request.method = "GET"

        dummy_request.url = URL("http://testserver/api/resource")

        dummy_request.headers = Headers({})

        async def failing_builder(req):
            raise Exception("Key builder failure")

        self.middleware.cache_key_builder = failing_builder

        dummy_response = Response(
            content=b"default response",
            status_code=200,
            headers={"Content-Type": "text/plain"}
        )

        call_next = AsyncMock(return_value=dummy_response)

        response = await self.middleware.dispatch(dummy_request, call_next)

        self.assertEqual(response.body, b"default response")

        call_next.assert_called_once_with(dummy_request)

    # ETag match returns 304 without calling upstream
    async def test_dispatch_etag_match(self):
        dummy_request = MagicMock(spec=Request)

        dummy_request.method = "GET"

        dummy_request.url = URL("http://testserver/test/resource")

        dummy_request.headers = Headers({"If-None-Match": "dummyhash"})

        dummy_request.body = AsyncMock(return_value=b"")

        key = await self.middleware.cache_key_builder(dummy_request)

        cached_data = {

            "content": b"cached content",

            "status_code": 200,

            "headers": {"Content-Type": "text/plain"},

            "media_type": "text/plain"

        }

        response_cache.set(key, cached_data, ttl=300, content_hash="dummyhash")

        call_next = AsyncMock()

        response = await self.middleware.dispatch(dummy_request, call_next)

        self.assertEqual(response.status_code, 304)

        self.assertEqual(response.headers.get("ETag"), "dummyhash")

        call_next.assert_not_called()

    # returning a cached response bypasses upstream
    async def test_dispatch_cached_response(self):
        dummy_request = MagicMock(spec=Request)

        dummy_request.method = "GET"

        dummy_request.url = URL("http://testserver/test/resource")

        dummy_request.headers = Headers({})

        dummy_request.body = AsyncMock(return_value=b"")

        key = await self.middleware.cache_key_builder(dummy_request)

        cached_content = b"cached content"

        cached_data = {

            "content": cached_content,

            "status_code": 200,

            "headers": {"Content-Type": "text/plain"},

            "media_type": "text/plain"

        }

        response_cache.set(key, cached_data, ttl=300, content_hash="dummyhash")

        call_next = AsyncMock()

        response = await self.middleware.dispatch(dummy_request, call_next)

        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.body, cached_content)

        self.assertEqual(response.headers.get("ETag"), "dummyhash")

        call_next.assert_not_called()

    # non-cached request is forwarded and then cached
    async def test_dispatch_new_response_caching(self):
        dummy_request = MagicMock(spec=Request)

        dummy_request.method = "GET"

        dummy_request.url = URL("http://testserver/api/resource")

        dummy_request.headers = Headers({})

        dummy_request.body = AsyncMock(return_value=b"request body")

        original_response = Response(

            content=b"fresh response",

            status_code=200,

            headers={"Content-Type": "text/plain"}

        )

        async def fake_body_iterator():
            yield b"fresh response"

        original_response.body_iterator = fake_body_iterator()

        call_next = AsyncMock(return_value=original_response)

        response = await self.middleware.dispatch(dummy_request, call_next)

        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.body, b"fresh response")

        key = await self.middleware.cache_key_builder(dummy_request)

        cached = response_cache.get(key)

        self.assertIsNotNone(cached)

        self.assertEqual(cached["content"], b"fresh response")

        self.assertEqual(cached["status_code"], 200)

    # non-2xx/3xx status codes are not cached
    async def test_dispatch_non_cacheable_status(self):
        dummy_request = MagicMock(spec=Request)

        dummy_request.method = "GET"

        dummy_request.url = URL("http://testserver/test/fail")

        dummy_request.headers = Headers({})

        dummy_request.body = AsyncMock(return_value=b"")

        original_response = Response(

            content=b"not found",

            status_code=404,

            headers={"Content-Type": "text/plain"}

        )

        async def fake_body_iterator():
            yield b"not found"

        original_response.body_iterator = fake_body_iterator()

        call_next = AsyncMock(return_value=original_response)

        response = await self.middleware.dispatch(dummy_request, call_next)

        self.assertEqual(response.status_code, 404)

        key = await self.middleware.cache_key_builder(dummy_request)

        self.assertIsNone(response_cache.get(key))

    # building cache key for multipart POST includes form fields
    async def test_custom_file_cache_key_builder_post_positive(self):
        dummy_request = MagicMock(spec=Request)

        dummy_request.method = "POST"

        dummy_request.url = URL("http://testserver/test/upload")

        dummy_request.query_params = QueryParams({})

        dummy_request.headers = Headers({

            "content-type": "multipart/form-data; boundary=---test",

            "Accept": "application/json",

            "Accept-Encoding": "gzip"

        })

        dummy_request.body = AsyncMock(return_value=b"raw multipart data")

        fake_file = MagicMock()

        fake_file.filename = "test.txt"

        fake_file.read = AsyncMock(return_value=b"file content")

        fake_file.file = MagicMock()

        dummy_form = {"file": fake_file, "field": "value"}

        dummy_request.form = AsyncMock(return_value=dummy_form)

        key = await custom_file_cache_key_builder(dummy_request)

        self.assertEqual(len(key), 64)

        base_components = [

            "POST",

            "/test/upload",

            str(sorted(dummy_request.query_params.items())),

            "application/json",

            "gzip"

        ]

        file_hash = hashlib.sha256(b"file content").hexdigest()

        field_component = f"file:{file_hash}"

        normal_component = "field:value"

        base_components.append(sorted([field_component, normal_component]))

        expected_key = hashlib.sha256(

            json.dumps(base_components, sort_keys=True).encode()

        ).hexdigest()

        self.assertEqual(key, expected_key)

    # errors during form reading still return a valid hash
    async def test_custom_file_cache_key_builder_post_negative(self):
        dummy_request = MagicMock(spec=Request)

        dummy_request.method = "POST"

        dummy_request.url = URL("http://testserver/test/upload")

        dummy_request.query_params = QueryParams({})

        dummy_request.headers = Headers({

            "content-type": "multipart/form-data; boundary=---test",

            "Accept": "application/json",

            "Accept-Encoding": "gzip"

        })

        dummy_request.body = AsyncMock(side_effect=Exception("read error"))

        dummy_request.form = AsyncMock(return_value={})

        key = await custom_file_cache_key_builder(dummy_request)

        self.assertEqual(len(key), 64)

    # GET requests build key from method, path, query, headers, and body
    async def test_custom_file_cache_key_builder_get(self):
        dummy_request = MagicMock(spec=Request)

        dummy_request.method = "GET"

        dummy_request.url = URL("http://testserver/api/data")

        dummy_request.query_params = QueryParams({"q": "value"})

        dummy_request.headers = Headers({

            "Accept": "application/json",

            "Accept-Encoding": "gzip",

            "content-type": "application/json"

        })

        dummy_request.body = AsyncMock(return_value=b"get body")

        key = await custom_file_cache_key_builder(dummy_request)

        self.assertEqual(len(key), 64)

        base_components = [

            "GET",

            "/api/data",

            str(sorted(dummy_request.query_params.items())),

            "application/json",

            "gzip",

            b"get body".hex()

        ]

        expected_key = hashlib.sha256(

            json.dumps(base_components, sort_keys=True).encode()

        ).hexdigest()

        self.assertEqual(key, expected_key)


# Tests for cache utility functions
class TestUtilityFunctions(unittest.TestCase):
    """Test get_cached_response, cache_response, clear_cached_response, invalidate_cache."""

    # clear global cache before each
    def setUp(self):
        response_cache.cache.clear()

        response_cache.access_times.clear()

        response_cache.expiration_times.clear()

        response_cache.etags.clear()

    # retrieving via util returns stored data
    def test_get_cached_response_util(self):
        data = {

            "content": b"util",

            "status_code": 200,

            "headers": {},

            "media_type": "text/plain"

        }

        response_cache.cache["test_util"] = data

        response_cache.expiration_times["test_util"] = time.time() + 60

        result = get_cached_response("test_util")

        self.assertEqual(result, data)

    # cache_response utility stores data
    def test_cache_response_util(self):
        data = {

            "content": b"cached",

            "status_code": 200,

            "headers": {},

            "media_type": "text/plain"

        }

        result = cache_response("test_key", data, ttl=120)

        self.assertTrue(result)

        self.assertEqual(response_cache.cache.get("test_key"), data)

    # clear_cached_response utility deletes key
    def test_clear_cached_response_util(self):
        response_cache.cache["key_to_clear"] = "value"

        result = clear_cached_response("key_to_clear")

        self.assertTrue(result)

        self.assertNotIn("key_to_clear", response_cache.cache)

    # invalidate_cache utility removes by prefix or all
    def test_invalidate_cache_util(self):
        response_cache.cache["prefix_1"] = "val1"

        response_cache.cache["prefix_2"] = "val2"

        response_cache.cache["other"] = "val3"

        invalidate_cache("prefix_")

        self.assertNotIn("prefix_1", response_cache.cache)

        self.assertNotIn("prefix_2", response_cache.cache)

        self.assertIn("other", response_cache.cache)

        invalidate_cache()

        self.assertEqual(response_cache.cache, {})
