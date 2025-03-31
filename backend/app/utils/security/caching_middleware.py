"""
Enhanced caching middleware with improved synchronization and cache management features.

This module provides a response caching mechanism with timeout management,
synchronization using a basic lock (acquire/release) with lazy initialization,
and TTL-based cache expiration to improve API performance while ensuring thread safety.
"""

import hashlib
import json
import logging
import time
from typing import Dict, Any, Optional, List, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from backend.app.utils.logging.logger import log_info, log_warning
from backend.app.utils.system_utils.synchronization_utils import TimeoutLock, LockPriority


class ResponseCache:
    """
    Thread-safe response cache using a basic lock for synchronization.

    This cache allows lock-free reads for high-traffic paths and uses exclusive writes
    to ensure consistency. Each cache entry expires after a TTL and may include an ETag.
    """

    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        """
        Initialize the response cache.

        Args:
            max_size: Maximum number of items to store.
            default_ttl: Default time-to-live (in seconds) for each cache entry.
        """
        self.cache: Dict[str, Any] = {}
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.access_times: Dict[str, float] = {}
        self.expiration_times: Dict[str, float] = {}
        self.etags: Dict[str, str] = {}
        self._rwlock: Optional[TimeoutLock] = None

        # Do not initialize the lock in the constructor.
        # Instead, use lazy initialization via the property below.
        log_info(f"Response cache initialized with max_size={max_size}, default_ttl={default_ttl}s")

    @property
    def rwlock(self) -> TimeoutLock:
        """
        Lazy-initialized lock for synchronizing cache access.

        Returns:
            An instance of TimeoutLock.
        """
        if self._rwlock is None:
            self._rwlock = TimeoutLock("response_cache_lock", priority=LockPriority.LOW)
        return self._rwlock

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a value from the cache via a lock-free read.

        Args:
            key: The cache key.

        Returns:
            The cached value if found and not expired; otherwise, None.
        """
        current_time = time.time()
        value = self.cache.get(key)
        if value is not None:
            expiry = self.expiration_times.get(key, 0)
            if current_time < expiry:
                # Update access time (minor race conditions are acceptable)
                try:
                    self.access_times[key] = current_time
                except Exception as e:
                    log_warning(f"Error updating access time for key {key}: {e}")
                return value
            else:
                # Entry has expired; cleanup will remove it later.
                return None
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None, content_hash: Optional[str] = None) -> bool:
        """
        Set a cache entry with exclusive write access.

        If the cache is full, expired entries are first removed; if still full,
        the least recently used (LRU) entry is removed.

        Args:
            key: The cache key.
            value: The data to cache.
            ttl: Optional TTL in seconds (default used if None).
            content_hash: Optional hash to store as an ETag.

        Returns:
            True if the entry was successfully cached, False otherwise.
        """
        try:
            self.rwlock.acquire(timeout=5.0)
        except TimeoutError:
            log_warning(f"Timeout acquiring write lock for cache key: {key}")
            return False

        try:
            if len(self.cache) >= self.max_size:
                self._cleanup_expired()
            if len(self.cache) >= self.max_size:
                self._remove_lru()
            current_time = time.time()
            self.cache[key] = value
            self.access_times[key] = current_time
            self.expiration_times[key] = current_time + (ttl if ttl is not None else self.default_ttl)
            if content_hash:
                self.etags[key] = content_hash
            return True
        finally:
            self.rwlock.release()

    def delete(self, key: str) -> bool:
        """
        Remove a specific cache entry with exclusive write access.

        Args:
            key: The cache key.

        Returns:
            True if the entry was removed, False otherwise.
        """
        try:
            self.rwlock.acquire(timeout=3.0)
        except TimeoutError:
            log_warning(f"Timeout acquiring write lock for deleting cache key: {key}")
            return False

        try:
            if key in self.cache:
                del self.cache[key]
                self.access_times.pop(key, None)
                self.expiration_times.pop(key, None)
                self.etags.pop(key, None)
                return True
            return False
        finally:
            self.rwlock.release()

    def clear(self) -> bool:
        """
        Clear the entire cache with exclusive write access.

        Returns:
            True if the cache was cleared successfully, False otherwise.
        """
        try:
            self.rwlock.acquire(timeout=10.0)
        except TimeoutError:
            log_warning("Timeout acquiring write lock for clearing cache")
            return False

        try:
            self.cache.clear()
            self.access_times.clear()
            self.expiration_times.clear()
            self.etags.clear()
            log_info("Response cache cleared")
            return True
        finally:
            self.rwlock.release()

    def _cleanup_expired(self) -> int:
        """
        Remove all expired cache entries.

        Note: Caller must hold the write lock.

        Returns:
            The number of entries removed.
        """
        current_time = time.time()
        expired_keys = [key for key, expiry in self.expiration_times.items() if current_time > expiry]
        for key in expired_keys:
            self.cache.pop(key, None)
            self.access_times.pop(key, None)
            self.expiration_times.pop(key, None)
            self.etags.pop(key, None)
        if expired_keys:
            log_info(f"Cleaned up {len(expired_keys)} expired cache entries")
        return len(expired_keys)

    def _remove_lru(self) -> bool:
        """
        Remove the least recently used (LRU) cache entry.

        Note: Caller must hold the write lock.

        Returns:
            True if an entry was removed; False if the cache is empty.
        """
        if not self.access_times:
            return False
        lru_key = min(self.access_times, key=self.access_times.get)
        self.cache.pop(lru_key, None)
        self.access_times.pop(lru_key, None)
        self.expiration_times.pop(lru_key, None)
        self.etags.pop(lru_key, None)
        log_info(f"Removed least recently used cache entry: {lru_key}")
        return True

    def cleanup_expired(self) -> int:
        """
        Clean up expired cache entries with exclusive write access.

        Returns:
            The number of entries removed.
        """
        try:
            self.rwlock.acquire(timeout=5.0)
        except TimeoutError:
            log_warning("Timeout acquiring write lock for cache cleanup")
            return 0

        try:
            return self._cleanup_expired()
        finally:
            self.rwlock.release()

    def remove(self, key: str) -> bool:
        """
        Alias for the delete() method for backward compatibility.

        Args:
            key: The cache key.

        Returns:
            True if the entry was removed; otherwise, False.
        """
        return self.delete(key)


def get_cached_response(key: str) -> Optional[Any]:
    """
    Retrieve a cached response.

    Args:
        key: The cache key.

    Returns:
        The cached response if present and not expired; otherwise, None.
    """
    return response_cache.get(key)


def cache_response(key: str, response: Any, ttl: Optional[int] = None) -> bool:
    """
    Cache a response.

    Args:
        key: The cache key.
        response: The response data.
        ttl: Optional TTL in seconds (uses default if None).

    Returns:
        True if caching was successful; otherwise, False.
    """
    return response_cache.set(key, response, ttl)


def clear_cached_response(key: str) -> bool:
    """
    Clear a specific cached response.

    Args:
        key: The cache key.

    Returns:
        True if the entry was cleared; otherwise, False.
    """
    return response_cache.delete(key)


class CacheMiddleware(BaseHTTPMiddleware):
    """
    Enhanced middleware for caching GET responses with ETag support and optimized invalidation.
    """

    def __init__(
        self,
        app: ASGIApp,
        paths: List[str],
        ttl: int = 300,
        cache_key_builder: Optional[Callable[[Request], str]] = None,
        content_hashing: bool = True
    ):
        """
        Initialize the cache middleware.

        Args:
            app: The FastAPI/Starlette application.
            paths: List of path prefixes to apply caching.
            ttl: Default TTL in seconds for cached responses.
            cache_key_builder: Optional function to build custom cache keys.
            content_hashing: If True, compute a content-based hash for ETag generation.
        """
        super().__init__(app)
        self.paths = paths
        self.ttl = ttl
        self.cache_key_builder = cache_key_builder or self._default_cache_key_builder
        self.content_hashing = content_hashing
        self._logger = logging.getLogger("cache_middleware")
        self._schedule_cleanup()

    async def dispatch(self, request: Request, call_next):
        """
        Process the request and serve from cache when appropriate.

        For GET requests on configured paths:
          - If the "If-None-Match" header matches the cached ETag, return 304.
          - Otherwise, return the cached response if available.
          - If not cached, call the downstream handler, cache the response if successful, and return it.

        Args:
            request: The incoming request.
            call_next: The next middleware/endpoint callable.

        Returns:
            A Response object.
        """
        if request.method != "GET" or not self._should_cache_path(request.url.path):
            return await call_next(request)

        cache_key = self.cache_key_builder(request)
        # ETag check: return 304 if client cache is valid.
        if_none_match = request.headers.get("If-None-Match")
        if if_none_match and response_cache.etags.get(cache_key) == if_none_match:
            self._logger.debug(f"ETag match for {cache_key}, returning 304 Not Modified")
            return Response(status_code=304, headers={"ETag": if_none_match})

        cached_response = response_cache.get(cache_key)
        if cached_response:
            etag = response_cache.etags.get(cache_key)
            response = Response(
                content=cached_response["content"],
                status_code=cached_response["status_code"],
                headers=cached_response["headers"],
                media_type=cached_response["media_type"]
            )
            if etag:
                response.headers["ETag"] = etag
            self._logger.debug(f"Cache hit for {cache_key}")
            return response

        response = await call_next(request)
        if 200 <= response.status_code < 400:
            response_body = b""
            async for chunk in response.body_iterator:
                response_body += chunk

            content_hash = None
            if self.content_hashing:
                content_hash = hashlib.sha256(response_body).hexdigest()

            response_cache.set(
                cache_key,
                {
                    "content": response_body,
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "media_type": response.media_type
                },
                ttl=self.ttl,
                content_hash=content_hash
            )

            new_response = Response(
                content=response_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type
            )
            if content_hash:
                new_response.headers["ETag"] = content_hash

            self._logger.debug(f"Cached new response for {cache_key}")
            return new_response

        return response

    def _should_cache_path(self, path: str) -> bool:
        """
        Determine if the given request path should be cached.

        Args:
            path: The request path.

        Returns:
            True if the path starts with any of the configured prefixes; otherwise, False.
        """
        return any(path.startswith(prefix) for prefix in self.paths)

    @staticmethod
    def _default_cache_key_builder(request: Request) -> str:
        """
        Build a default cache key from a request.

        Uses the method, path, sorted query parameters, Accept header, and Accept-Encoding header.

        Args:
            request: The incoming request.

        Returns:
            A SHA-256 hex digest string representing the cache key.
        """
        key_components = [
            request.method,
            request.url.path,
            str(sorted(request.query_params.items())),
            request.headers.get("Accept", "*/*"),
            request.headers.get("Accept-Encoding", "identity")
        ]
        return hashlib.sha256(json.dumps(key_components).encode()).hexdigest()

    def _schedule_cleanup(self) -> None:
        """
        Schedule periodic cleanup of expired cache entries in a background thread.
        """
        import threading

        def cleanup_loop():
            while True:
                time.sleep(60)  # Run cleanup every minute.
                removed = response_cache.cleanup_expired()
                self._logger.debug(f"Cache cleanup removed {removed} expired items")

        cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
        cleanup_thread.start()


def _get_keys_by_prefix(cache: ResponseCache, prefix: str, timeout: float = 3.0) -> List[str]:
    """
    Helper function to retrieve all keys in the cache that start with the given prefix.

    This function acquires the cache's lock to ensure a consistent snapshot.

    Args:
        cache: The ResponseCache instance.
        prefix: The prefix to filter keys.
        timeout: Timeout in seconds for acquiring the lock.

    Returns:
        A list of keys that begin with the specified prefix.
        Returns an empty list if the lock cannot be acquired.
    """
    try:
        cache.rwlock.acquire(timeout=timeout)
    except TimeoutError:
        log_warning(f"Timeout acquiring lock for invalidating path prefix: {prefix}")
        return []
    try:
        return [key for key in list(cache.cache.keys()) if key.startswith(prefix)]
    finally:
        cache.rwlock.release()


def invalidate_cache(path_prefix: Optional[str] = None) -> None:
    """
    Invalidate (remove) cache entries by a path prefix or clear the entire cache if None.

    This function minimizes lock usage by retrieving matching keys in a single locked section.

    Args:
        path_prefix: The prefix of cache keys to remove. If None, the entire cache is cleared.
    """
    if path_prefix is None:
        response_cache.clear()
        return

    keys_to_remove = _get_keys_by_prefix(response_cache, path_prefix)
    for key in keys_to_remove:
        response_cache.remove(key)


# Global cache instance.
response_cache = ResponseCache()