"""
Unit tests for caching_middleware.py module.

This test file covers the ResponseCache and CacheMiddleware classes and utility functions
with both positive and negative test cases to ensure proper functionality and error handling.
"""
import hashlib
import json
import time
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

from fastapi import Request, Response
from starlette.datastructures import Headers, QueryParams, URL

from backend.app.utils.security.caching_middleware import ResponseCache, CacheMiddleware, response_cache, \
    custom_file_cache_key_builder, get_cached_response, cache_response, clear_cached_response, invalidate_cache
from backend.app.utils.system_utils.synchronization_utils import LockPriority


class TestResponseCache(unittest.TestCase):
    """Test cases for ResponseCache class."""

    def setUp(self):
        # Patch log_info and log_warning using the correct path
        self.log_info_patcher = patch('backend.app.utils.security.caching_middleware.log_info')
        self.mock_log_info = self.log_info_patcher.start()

        self.log_warning_patcher = patch('backend.app.utils.security.caching_middleware.log_warning')
        self.mock_log_warning = self.log_warning_patcher.start()

        # Patch TimeoutLock with the correct import path
        self.timeout_lock_patcher = patch('backend.app.utils.security.caching_middleware.TimeoutLock')
        self.mock_timeout_lock = self.timeout_lock_patcher.start()
        self.mock_lock_instance = MagicMock()
        self.mock_timeout_lock.return_value = self.mock_lock_instance

        # Create a fresh instance of ResponseCache for each test
        self.cache = ResponseCache(max_size=10, default_ttl=60)

    def tearDown(self):
        """Tear down test fixtures after each test method."""
        self.log_info_patcher.stop()
        self.log_warning_patcher.stop()
        self.timeout_lock_patcher.stop()

    def test_init(self):
        """Test initialization of ResponseCache."""
        # Verify the cache was initialized with the correct parameters
        self.assertEqual(self.cache.max_size, 10)
        self.assertEqual(self.cache.default_ttl, 60)
        self.assertEqual(self.cache.cache, {})
        self.assertEqual(self.cache.access_times, {})
        self.assertEqual(self.cache.expiration_times, {})
        self.assertEqual(self.cache.etags, {})
        self.assertIsNone(self.cache._rwlock)

        # Verify log_info was called for initialization
        self.mock_log_info.assert_called_once_with("Response cache initialized with max_size=10, default_ttl=60s")

    def test_rwlock_property_lazy_initialization(self):
        """Test lazy initialization of rwlock property."""
        # Verify the lock is initially None
        self.assertIsNone(self.cache._rwlock)

        # Access the rwlock property to trigger initialization
        lock = self.cache.rwlock

        # Verify TimeoutLock was created with the correct parameters
        self.mock_timeout_lock.assert_called_once_with("response_cache_lock", priority=LockPriority.LOW)

        # Verify the lock was initialized
        self.assertIsNotNone(self.cache._rwlock)
        self.assertEqual(lock, self.mock_lock_instance)

    def test_get_with_valid_entry(self):
        """Test get method with a valid cache entry."""
        # Set up a test entry in the cache
        self.cache.cache["test_key"] = "test_value"
        current_time = time.time()
        self.cache.expiration_times["test_key"] = current_time + 60  # Expires in 60 seconds

        # Get the entry
        result = self.cache.get("test_key")

        # Verify the result
        self.assertEqual(result, "test_value")

        # Verify the access time was updated
        self.assertIn("test_key", self.cache.access_times)
        self.assertAlmostEqual(self.cache.access_times["test_key"], current_time, delta=1)

    def test_get_with_expired_entry(self):
        """Test get method with an expired cache entry."""
        # Set up an expired test entry in the cache
        self.cache.cache["test_key"] = "test_value"
        self.cache.expiration_times["test_key"] = time.time() - 10  # Expired 10 seconds ago

        # Get the entry
        result = self.cache.get("test_key")

        # Verify the result is None (expired entry)
        self.assertIsNone(result)

    def test_get_with_nonexistent_key(self):
        """Test get method with a nonexistent key."""
        # Get a nonexistent entry
        result = self.cache.get("nonexistent_key")

        # Verify the result is None
        self.assertIsNone(result)

    def test_get_with_access_time_error(self):
        """Test get method when updating access time raises an error."""
        # Set up a test entry in the cache
        self.cache.cache["test_key"] = "test_value"
        self.cache.expiration_times["test_key"] = time.time() + 60  # Expires in 60 seconds

        # Make access_times raise an exception when updated
        self.cache.access_times = MagicMock()
        self.cache.access_times.__getitem__ = MagicMock(side_effect=Exception("Test error"))
        self.cache.access_times.__setitem__ = MagicMock(side_effect=Exception("Test error"))

        # Get the entry
        result = self.cache.get("test_key")

        # Verify the result is still returned despite the error
        self.assertEqual(result, "test_value")

        # Verify the warning was logged
        self.mock_log_warning.assert_called_once()
        self.assertIn("Error updating access time", self.mock_log_warning.call_args[0][0])

    @patch('time.time')
    def test_set_success(self, mock_time):
        """Test set method with successful cache entry."""
        # Set up the current time
        mock_time.return_value = 1000.0

        # Set a cache entry
        result = self.cache.set("test_key", "test_value", ttl=120, content_hash="test_hash")

        # Verify the lock was acquired and released
        self.mock_lock_instance.acquire.assert_called_once_with(timeout=5.0)
        self.mock_lock_instance.release.assert_called_once()

        # Verify the result is True
        self.assertTrue(result)

        # Verify the cache entry was set correctly
        self.assertEqual(self.cache.cache["test_key"], "test_value")
        self.assertEqual(self.cache.access_times["test_key"], 1000.0)
        self.assertEqual(self.cache.expiration_times["test_key"], 1120.0)  # 1000 + 120
        self.assertEqual(self.cache.etags["test_key"], "test_hash")

    @patch('time.time')
    def test_set_with_default_ttl(self, mock_time):
        """Test set method with default TTL."""
        # Set up the current time
        mock_time.return_value = 1000.0

        # Set a cache entry without specifying TTL
        result = self.cache.set("test_key", "test_value")

        # Verify the result is True
        self.assertTrue(result)

        # Verify the expiration time uses the default TTL
        self.assertEqual(self.cache.expiration_times["test_key"], 1060.0)  # 1000 + 60 (default TTL)

    def test_set_lock_timeout(self):
        """Test set method when lock acquisition times out."""
        # Make the lock acquisition time out
        self.mock_lock_instance.acquire.side_effect = TimeoutError("Lock timeout")

        # Set a cache entry
        result = self.cache.set("test_key", "test_value")

        # Verify the result is False
        self.assertFalse(result)

        # Verify the warning was logged
        self.mock_log_warning.assert_called_once_with("Timeout acquiring write lock for cache key: test_key")

        # Verify the cache entry was not set
        self.assertNotIn("test_key", self.cache.cache)

    @patch('time.time')
    def test_set_with_cleanup_expired(self, mock_time):
        """Test set method when cache is full and expired entries are cleaned up."""
        # Set up the current time
        mock_time.return_value = 1000.0

        # Fill the cache with some expired entries
        for i in range(10):
            self.cache.cache[f"key{i}"] = f"value{i}"
            self.cache.access_times[f"key{i}"] = 900.0
            # Make half the entries expired
            if i < 5:
                self.cache.expiration_times[f"key{i}"] = 990.0  # Expired
            else:
                self.cache.expiration_times[f"key{i}"] = 1100.0  # Not expired

        # Set a new cache entry
        result = self.cache.set("new_key", "new_value")

        # Verify the result is True
        self.assertTrue(result)

        # Verify expired entries were removed
        for i in range(5):
            self.assertNotIn(f"key{i}", self.cache.cache)

        # Verify non-expired entries were kept
        for i in range(5, 10):
            self.assertIn(f"key{i}", self.cache.cache)

        # Verify the new entry was added
        self.assertEqual(self.cache.cache["new_key"], "new_value")

    @patch('time.time')
    def test_set_with_lru_removal(self, mock_time):
        """Test set method when cache is full and LRU entry is removed."""
        # Set up the current time
        mock_time.return_value = 1000.0

        # Fill the cache with non-expired entries
        for i in range(10):
            self.cache.cache[f"key{i}"] = f"value{i}"
            self.cache.access_times[f"key{i}"] = 900.0 + i  # Different access times
            self.cache.expiration_times[f"key{i}"] = 1100.0  # Not expired

        # Set a new cache entry
        result = self.cache.set("new_key", "new_value")

        # Verify the result is True
        self.assertTrue(result)

        # Verify the least recently used entry was removed (key0)
        self.assertNotIn("key0", self.cache.cache)

        # Verify other entries were kept
        for i in range(1, 10):
            self.assertIn(f"key{i}", self.cache.cache)

        # Verify the new entry was added
        self.assertEqual(self.cache.cache["new_key"], "new_value")

    def test_delete_success(self):
        """Test delete method with successful deletion."""
        # Set up a test entry in the cache
        self.cache.cache["test_key"] = "test_value"
        self.cache.access_times["test_key"] = time.time()
        self.cache.expiration_times["test_key"] = time.time() + 60
        self.cache.etags["test_key"] = "test_hash"

        # Delete the entry
        result = self.cache.delete("test_key")

        # Verify the lock was acquired and released
        self.mock_lock_instance.acquire.assert_called_once_with(timeout=3.0)
        self.mock_lock_instance.release.assert_called_once()

        # Verify the result is True
        self.assertTrue(result)

        # Verify the entry was removed from all dictionaries
        self.assertNotIn("test_key", self.cache.cache)
        self.assertNotIn("test_key", self.cache.access_times)
        self.assertNotIn("test_key", self.cache.expiration_times)
        self.assertNotIn("test_key", self.cache.etags)

    def test_delete_nonexistent_key(self):
        """Test delete method with a nonexistent key."""
        # Delete a nonexistent entry
        result = self.cache.delete("nonexistent_key")

        # Verify the result is False
        self.assertFalse(result)

    def test_delete_lock_timeout(self):
        """Test delete method when lock acquisition times out."""
        # Set up a test entry in the cache
        self.cache.cache["test_key"] = "test_value"

        # Make the lock acquisition time out
        self.mock_lock_instance.acquire.side_effect = TimeoutError("Lock timeout")

        # Delete the entry
        result = self.cache.delete("test_key")

        # Verify the result is False
        self.assertFalse(result)

        # Verify the warning was logged
        self.mock_log_warning.assert_called_once_with("Timeout acquiring write lock for deleting cache key: test_key")

        # Verify the entry was not removed
        self.assertIn("test_key", self.cache.cache)

    def test_clear_success(self):
        """Test clear method with successful clearing."""
        # Set up some test entries in the cache
        self.cache.cache = {"key1": "value1", "key2": "value2"}
        self.cache.access_times = {"key1": 1000.0, "key2": 1100.0}
        self.cache.expiration_times = {"key1": 2000.0, "key2": 2100.0}
        self.cache.etags = {"key1": "hash1", "key2": "hash2"}

        # Clear the cache
        result = self.cache.clear()

        # Verify the lock was acquired and released
        self.mock_lock_instance.acquire.assert_called_once_with(timeout=10.0)
        self.mock_lock_instance.release.assert_called_once()

        # Verify the result is True
        self.assertTrue(result)

        # Verify all dictionaries were cleared
        self.assertEqual(self.cache.cache, {})
        self.assertEqual(self.cache.access_times, {})
        self.assertEqual(self.cache.expiration_times, {})
        self.assertEqual(self.cache.etags, {})

        # Verify the log message
        self.mock_log_info.assert_called_with("Response cache cleared")

    def test_clear_lock_timeout(self):
        """Test clear method when lock acquisition times out."""
        # Set up some test entries in the cache
        self.cache.cache = {"key1": "value1", "key2": "value2"}

        # Make the lock acquisition time out
        self.mock_lock_instance.acquire.side_effect = TimeoutError("Lock timeout")

        # Clear the cache
        result = self.cache.clear()

        # Verify the result is False
        self.assertFalse(result)

        # Verify the warning was logged
        self.mock_log_warning.assert_called_once_with("Timeout acquiring write lock for clearing cache")

        # Verify the cache was not cleared
        self.assertEqual(self.cache.cache, {"key1": "value1", "key2": "value2"})

    @patch('time.time')
    def test_cleanup_expired_internal(self, mock_time):
        """Test _cleanup_expired internal method."""
        # Set up the current time
        mock_time.return_value = 1000.0

        # Set up some test entries in the cache with mixed expiration times
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
            "expired1": 990.0,  # Expired
            "expired2": 995.0,  # Expired
            "valid1": 1100.0,  # Not expired
            "valid2": 1200.0  # Not expired
        }
        self.cache.etags = {
            "expired1": "hash1",
            "expired2": "hash2",
            "valid1": "hash3",
            "valid2": "hash4"
        }

        # Call the internal cleanup method
        removed = self.cache._cleanup_expired()

        # Verify the correct number of entries were removed
        self.assertEqual(removed, 2)

        # Verify expired entries were removed
        self.assertNotIn("expired1", self.cache.cache)
        self.assertNotIn("expired1", self.cache.access_times)
        self.assertNotIn("expired1", self.cache.expiration_times)
        self.assertNotIn("expired1", self.cache.etags)

        self.assertNotIn("expired2", self.cache.cache)
        self.assertNotIn("expired2", self.cache.access_times)
        self.assertNotIn("expired2", self.cache.expiration_times)
        self.assertNotIn("expired2", self.cache.etags)


# A dummy ASGI app for the CacheMiddleware tests.

class DummyApp:
    async def __call__(self, scope, receive, send):
        # This dummy app does nothing.
        pass


class TestCacheMiddleware(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):

        # Create an instance of CacheMiddleware with test path prefixes.
        self.paths = ["/test", "/api"]
        self.middleware = CacheMiddleware(app=DummyApp(), paths=self.paths, ttl=300)

        # Make sure the global cache is empty before each test.
        response_cache.cache.clear()
        response_cache.access_times.clear()
        response_cache.expiration_times.clear()
        response_cache.etags.clear()

    async def test_should_cache_path_positive(self):
        """Positive test: _should_cache_path returns True for matching prefixes."""

        self.assertTrue(self.middleware._should_cache_path("/test/resource"))
        self.assertTrue(self.middleware._should_cache_path("/api/data"))

    async def test_should_cache_path_negative(self):
        """Negative test: _should_cache_path returns False for non-matching paths."""

        self.assertFalse(self.middleware._should_cache_path("/other/path"))
        self.assertFalse(self.middleware._should_cache_path("/static/image.png"))

    async def test_dispatch_non_cached_method(self):
        """Test that non-GET/POST methods bypass caching."""
        dummy_request = MagicMock(spec=Request)

        dummy_request.method = "PUT"
        dummy_request.url = URL("http://testserver/api/resource")
        dummy_request.headers = Headers({})

        # call_next returns a simple Response.
        dummy_response = Response(content=b"put response", status_code=200, headers={"Content-Type": "text/plain"})
        call_next = AsyncMock(return_value=dummy_response)

        response = await self.middleware.dispatch(dummy_request, call_next)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body, b"put response")
        call_next.assert_called_once_with(dummy_request)

    async def test_dispatch_key_builder_exception(self):
        """Negative test: if cache key generation fails, the request is forwarded."""

        dummy_request = MagicMock(spec=Request)
        dummy_request.method = "GET"
        dummy_request.url = URL("http://testserver/api/resource")
        dummy_request.headers = Headers({})

        # Simulate exception when building cache key.
        async def failing_builder(req):
            raise Exception("Key builder failure")

        self.middleware.cache_key_builder = failing_builder

        dummy_response = Response(content=b"default response", status_code=200, headers={"Content-Type": "text/plain"})
        call_next = AsyncMock(return_value=dummy_response)

        response = await self.middleware.dispatch(dummy_request, call_next)
        self.assertEqual(response.body, b"default response")
        call_next.assert_called_once_with(dummy_request)

    async def test_dispatch_etag_match(self):
        """Test that when the client ETag matches the cached one, a 304 response is returned."""

        dummy_request = MagicMock(spec=Request)
        dummy_request.method = "GET"
        dummy_request.url = URL("http://testserver/test/resource")
        dummy_request.headers = Headers({"If-None-Match": "dummyhash"})

        # Ensure the body returns concrete bytes to avoid serialization issues.
        dummy_request.body = AsyncMock(return_value=b"")

        # Prepare a cache entry with matching ETag.
        key = await self.middleware.cache_key_builder(dummy_request)
        cached_data = {
            "content": b"cached content",
            "status_code": 200,
            "headers": {"Content-Type": "text/plain"},
            "media_type": "text/plain"
        }
        response_cache.set(key, cached_data, ttl=300, content_hash="dummyhash")

        call_next = AsyncMock()  # This should not be called.
        response = await self.middleware.dispatch(dummy_request, call_next)

        self.assertEqual(response.status_code, 304)
        self.assertEqual(response.headers.get("ETag"), "dummyhash")
        call_next.assert_not_called()

    async def test_dispatch_cached_response(self):
        """Test that dispatch returns a cached response if available."""

        dummy_request = MagicMock(spec=Request)
        dummy_request.method = "GET"
        dummy_request.url = URL("http://testserver/test/resource")
        dummy_request.headers = Headers({})
        # Ensure request.body() returns concrete bytes.
        dummy_request.body = AsyncMock(return_value=b"")

        # First, compute a cache key.
        key = await self.middleware.cache_key_builder(dummy_request)
        cached_content = b"cached content"
        cached_data = {
            "content": cached_content,
            "status_code": 200,
            "headers": {"Content-Type": "text/plain"},
            "media_type": "text/plain"
        }
        # Set the entry in cache (expiration set internally by ResponseCache.set)
        response_cache.set(key, cached_data, ttl=300, content_hash="dummyhash")
        call_next = AsyncMock()  # Should not be called on cache hit.
        response = await self.middleware.dispatch(dummy_request, call_next)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body, cached_content)
        self.assertEqual(response.headers.get("ETag"), "dummyhash")
        call_next.assert_not_called()

    async def test_dispatch_new_response_caching(self):
        """Test that a non-cached request is processed, then the response is cached and returned."""

        dummy_request = MagicMock(spec=Request)
        dummy_request.method = "GET"
        dummy_request.url = URL("http://testserver/api/resource")
        dummy_request.headers = Headers({})
        dummy_request.body = AsyncMock(return_value=b"request body")

        # Prepare call_next to return a successful response.
        original_response = Response(
            content=b"fresh response",
            status_code=200,
            headers={"Content-Type": "text/plain"}
        )

        # Emulate an async iterator for response.body_iterator.
        async def fake_body_iterator():
            yield b"fresh response"

        original_response.body_iterator = fake_body_iterator()
        call_next = AsyncMock(return_value=original_response)

        response = await self.middleware.dispatch(dummy_request, call_next)

        # Verify the response matches the fresh response.
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body, b"fresh response")

        # Also, verify that after processing, a cache entry was set.
        key = await self.middleware.cache_key_builder(dummy_request)
        cached = response_cache.get(key)
        self.assertIsNotNone(cached)
        self.assertEqual(cached["content"], b"fresh response")
        self.assertEqual(cached["status_code"], 200)

    async def test_dispatch_non_cacheable_status(self):
        """Test that responses with failure/redirection status are not cached."""

        dummy_request = MagicMock(spec=Request)
        dummy_request.method = "GET"
        dummy_request.url = URL("http://testserver/test/fail")
        dummy_request.headers = Headers({})
        dummy_request.body = AsyncMock(return_value=b"")
        # Return a 404 response.
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

        # The cache should remain empty.
        key = await self.middleware.cache_key_builder(dummy_request)
        self.assertIsNone(response_cache.get(key))

    async def test_custom_file_cache_key_builder_post_positive(self):
        """Positive test for custom_file_cache_key_builder with multipart/form-data POST."""

        dummy_request = MagicMock(spec=Request)
        dummy_request.method = "POST"
        dummy_request.url = URL("http://testserver/test/upload")
        dummy_request.query_params = QueryParams({})
        # Set up headers indicating multipart/form-data.
        dummy_request.headers = Headers({
            "content-type": "multipart/form-data; boundary=---test",
            "Accept": "application/json",
            "Accept-Encoding": "gzip"
        })
        # Simulate a body that returns some bytes.
        dummy_request.body = AsyncMock(return_value=b"raw multipart data")
        # Simulate form data. For testing, we create a fake file-like object.
        fake_file = MagicMock()
        fake_file.filename = "test.txt"
        fake_file.read = AsyncMock(return_value=b"file content")
        fake_file.file = MagicMock()
        dummy_form = {"file": fake_file, "field": "value"}
        dummy_request.form = AsyncMock(return_value=dummy_form)

        key = await custom_file_cache_key_builder(dummy_request)
        # Verify that a SHA-256 hex digest is produced.
        self.assertEqual(len(key), 64)
        # Optionally, check that key_components contain our fields.
        # We cannot guarantee the exact string but can re-calculate manually:
        base_components = [
            "POST",
            "/test/upload",
            str(sorted(dummy_request.query_params.items())),
            "application/json",
            "gzip"
        ]
        # Process the file field.
        file_hash = hashlib.sha256(b"file content").hexdigest()
        field_component = f"file:{file_hash}"
        # And the normal field.
        normal_component = "field:value"
        # Append these as a sorted list.
        base_components.append(sorted([field_component, normal_component]))
        expected_key = hashlib.sha256(json.dumps(base_components, sort_keys=True).encode()).hexdigest()

        self.assertEqual(key, expected_key)

    async def test_custom_file_cache_key_builder_post_negative(self):
        """Negative test for custom_file_cache_key_builder when reading form data fails."""
        dummy_request = MagicMock(spec=Request)
        dummy_request.method = "POST"
        dummy_request.url = URL("http://testserver/test/upload")
        dummy_request.query_params = QueryParams({})
        dummy_request.headers = Headers({
            "content-type": "multipart/form-data; boundary=---test",
            "Accept": "application/json",
            "Accept-Encoding": "gzip"
        })

        # Force an exception when reading the body.
        dummy_request.body = AsyncMock(side_effect=Exception("read error"))
        # Set form() to return an empty dict.
        dummy_request.form = AsyncMock(return_value={})

        key = await custom_file_cache_key_builder(dummy_request)

        # In this error branch, key_components should have an empty string for the form data.
        # We still get a valid hash.
        self.assertEqual(len(key), 64)

    async def test_custom_file_cache_key_builder_get(self):
        """Test custom_file_cache_key_builder for a GET request (non-multipart)."""

        dummy_request = MagicMock(spec=Request)
        dummy_request.method = "GET"
        dummy_request.url = URL("http://testserver/api/data")
        dummy_request.query_params = QueryParams({"q": "value"})
        dummy_request.headers = Headers({
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "content-type": "application/json"
        })
        # Return some bytes on calling body().
        dummy_request.body = AsyncMock(return_value=b"get body")
        key = await custom_file_cache_key_builder(dummy_request)

        self.assertEqual(len(key), 64)
        # Optional: compute expected key.
        base_components = [
            "GET",
            "/api/data",
            str(sorted(dummy_request.query_params.items())),
            "application/json",
            "gzip",
            b"get body".hex()
        ]
        expected_key = hashlib.sha256(json.dumps(base_components, sort_keys=True).encode()).hexdigest()

        self.assertEqual(key, expected_key)


# Tests for Utility Functions

class TestUtilityFunctions(unittest.TestCase):

    def setUp(self):
        # Clear the global cache.
        response_cache.cache.clear()
        response_cache.access_times.clear()
        response_cache.expiration_times.clear()
        response_cache.etags.clear()

    def test_get_cached_response_util(self):
        """Test that get_cached_response returns the correct cached response."""

        data = {"content": b"util", "status_code": 200, "headers": {}, "media_type": "text/plain"}
        # Set an expiration in the future.
        response_cache.cache["test_util"] = data
        response_cache.expiration_times["test_util"] = time.time() + 60
        result = get_cached_response("test_util")

        self.assertEqual(result, data)

    def test_cache_response_util(self):
        """Test that cache_response correctly caches a response."""

        data = {"content": b"cached", "status_code": 200, "headers": {}, "media_type": "text/plain"}
        result = cache_response("test_key", data, ttl=120)

        self.assertTrue(result)
        self.assertEqual(response_cache.cache.get("test_key"), data)

    def test_clear_cached_response_util(self):
        """Test that clear_cached_response removes the given entry."""

        response_cache.cache["key_to_clear"] = "value"
        result = clear_cached_response("key_to_clear")

        self.assertTrue(result)
        self.assertNotIn("key_to_clear", response_cache.cache)

    def test_invalidate_cache_util(self):
        """Test that invalidate_cache removes keys by prefix and clears entire cache."""

        response_cache.cache["prefix_1"] = "val1"
        response_cache.cache["prefix_2"] = "val2"
        response_cache.cache["other"] = "val3"

        invalidate_cache("prefix_")

        self.assertNotIn("prefix_1", response_cache.cache)
        self.assertNotIn("prefix_2", response_cache.cache)
        self.assertIn("other", response_cache.cache)

        # Now clear entire cache.
        invalidate_cache()
        self.assertEqual(response_cache.cache, {})
