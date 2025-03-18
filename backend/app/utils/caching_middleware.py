"""
Enhanced caching middleware with improved synchronization and cache management features.

This module provides a response caching mechanism with timeout management,
synchronization using ReadWriteLock, and TTL-based cache expiration to
improve API performance while ensuring thread safety.
"""
import time
import hashlib
import json
import logging
from typing import Dict, Any, Optional, List, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from backend.app.utils.logger import log_info, log_warning, log_error
from backend.app.utils.synchronization_utils import ReadWriteLock, LockPriority

# In-memory cache store with TTL
class ResponseCache:
    """
    Thread-safe response cache using ReadWriteLock for synchronization.

    Allows concurrent reads but exclusive writes to maximize throughput
    while maintaining data consistency.
    """
    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        """
        Initialize the response cache.

        Args:
            max_size: Maximum number of items to store in the cache
            default_ttl: Default time-to-live in seconds for cached responses
        """
        self.cache: Dict[str, Any] = {}
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.access_times: Dict[str, float] = {}
        self.expiration_times: Dict[str, float] = {}
        self.etags: Dict[str, str] = {}  # Store ETags for cache entries

        # Use ReadWriteLock with appropriate priority
        self.rwlock = ReadWriteLock(
            "response_cache_lock",
            priority=LockPriority.LOW  # Low priority as caching is not critical
        )

        log_info(f"Response cache initialized with max_size={max_size}, default_ttl={default_ttl}s")

    def get(self, key: str) -> Optional[Any]:
        """
        Get a value from the cache with read-write lock synchronization.

        Args:
            key: Cache key to retrieve

        Returns:
            Cached value or None if not found or expired
        """
        # Use read lock for cache lookup (allows concurrent reads)
        try:
            with self.rwlock.read_locked(timeout=2.0):
                current_time = time.time()

                # Check if key exists and hasn't expired
                if key in self.cache and current_time < self.expiration_times.get(key, 0):
                    # Update access time
                    self.access_times[key] = current_time
                    return self.cache[key]
                elif key in self.cache:
                    # Item exists but has expired - will be cleaned up later
                    return None
                return None
        except TimeoutError:
            log_warning(f"Timeout acquiring read lock for cache key: {key}")
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None, content_hash: Optional[str] = None) -> bool:
        """
        Set a value in the cache with read-write lock synchronization.

        Args:
            key: Cache key to set
            value: Value to store
            ttl: Time-to-live in seconds (uses default if None)
            content_hash: Optional content hash for ETag

        Returns:
            True if set successfully, False otherwise
        """
        # Use write lock for cache updates (exclusive access)
        try:
            with self.rwlock.write_locked(timeout=5.0):
                # Clean expired entries if cache is getting full
                if len(self.cache) >= self.max_size:
                    self._cleanup_expired()

                # If still full after cleanup, remove least recently used
                if len(self.cache) >= self.max_size:
                    self._remove_lru()

                # Set the cache entry
                current_time = time.time()
                self.cache[key] = value
                self.access_times[key] = current_time
                self.expiration_times[key] = current_time + (ttl if ttl is not None else self.default_ttl)

                # Store ETag if provided
                if content_hash:
                    self.etags[key] = content_hash

                return True
        except TimeoutError:
            log_warning(f"Timeout acquiring write lock for cache key: {key}")
            return False

    def delete(self, key: str) -> bool:
        """
        Delete a value from the cache with read-write lock synchronization.

        Args:
            key: Cache key to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        # Use write lock for cache deletion (exclusive access)
        try:
            with self.rwlock.write_locked(timeout=3.0):
                if key in self.cache:
                    del self.cache[key]

                    # Clean up related metadata
                    if key in self.access_times:
                        del self.access_times[key]
                    if key in self.expiration_times:
                        del self.expiration_times[key]
                    if key in self.etags:
                        del self.etags[key]
                    return True
                return False
        except TimeoutError:
            log_warning(f"Timeout acquiring write lock for deleting cache key: {key}")
            return False

    def clear(self) -> bool:
        """
        Clear the entire cache with read-write lock synchronization.

        Returns:
            True if cleared successfully, False otherwise
        """
        # Use write lock for cache clearing (exclusive access)
        try:
            with self.rwlock.write_locked(timeout=10.0):
                self.cache.clear()
                self.access_times.clear()
                self.expiration_times.clear()
                self.etags.clear()
                log_info("Response cache cleared")
                return True
        except TimeoutError:
            log_warning("Timeout acquiring write lock for clearing cache")
            return False

    def _cleanup_expired(self) -> int:
        """
        Remove expired items from the cache.

        Returns:
            Number of items removed
        """
        current_time = time.time()
        expired_keys = [
            key for key, expiry_time in self.expiration_times.items()
            if current_time > expiry_time
        ]

        # Remove expired items
        for key in expired_keys:
            if key in self.cache:
                del self.cache[key]
            if key in self.access_times:
                del self.access_times[key]
            if key in self.expiration_times:
                del self.expiration_times[key]
            if key in self.etags:
                del self.etags[key]

        if expired_keys:
            log_info(f"Cleaned up {len(expired_keys)} expired cache entries")

        return len(expired_keys)

    def _remove_lru(self) -> bool:
        """
        Remove the least recently used item from the cache.

        Returns:
            True if an item was removed, False if the cache is empty
        """
        if not self.access_times:
            return False

        # Find the least recently used key
        lru_key = min(self.access_times, key=self.access_times.get)

        # Remove it from the cache and related metadata
        if lru_key in self.cache:
            del self.cache[lru_key]
        if lru_key in self.access_times:
            del self.access_times[lru_key]
        if lru_key in self.expiration_times:
            del self.expiration_times[lru_key]
        if lru_key in self.etags:
            del self.etags[lru_key]

        log_info(f"Removed least recently used cache entry: {lru_key}")
        return True

    def cleanup_expired(self) -> int:
        """
        Clean up expired cache entries with write lock.

        Returns:
            Number of entries removed
        """
        try:
            with self.rwlock.write_locked(timeout=5.0):
                return self._cleanup_expired()
        except TimeoutError:
            log_warning("Timeout acquiring write lock for cache cleanup")
            return 0

    def remove(self, key: str) -> bool:
        """
        Alias for delete method for backward compatibility.

        Args:
            key: Cache key to remove

        Returns:
            True if removed successfully, False otherwise
        """
        return self.delete(key)


# Global cache instance
response_cache = ResponseCache()

def get_cached_response(key: str) -> Optional[Any]:
    """
    Get a response from the cache.

    Args:
        key: Cache key to retrieve

    Returns:
        Cached response or None
    """
    return response_cache.get(key)

def cache_response(key: str, response: Any, ttl: Optional[int] = None) -> bool:
    """
    Cache a response with the given key and TTL.

    Args:
        key: Cache key to set
        response: Response to cache
        ttl: Time-to-live in seconds

    Returns:
        True if cached successfully, False otherwise
    """
    return response_cache.set(key, response, ttl)

def clear_cached_response(key: str) -> bool:
    """
    Clear a specific cached response.

    Args:
        key: Cache key to clear

    Returns:
        True if cleared successfully, False otherwise
    """
    return response_cache.delete(key)


class CacheMiddleware(BaseHTTPMiddleware):
    """
    Enhanced middleware for caching responses with etag support and optimized invalidation.
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
        Initialize the cache middleware with enhanced features.

        Args:
            app: FastAPI application
            paths: List of path prefixes to cache
            ttl: Time-to-live in seconds
            cache_key_builder: Optional function to build cache keys
            content_hashing: Whether to use content-based hashing for ETags
        """
        super().__init__(app)
        self.paths = paths
        self.ttl = ttl
        self.cache_key_builder = cache_key_builder or self._default_cache_key_builder
        self.content_hashing = content_hashing
        self._logger = logging.getLogger("cache_middleware")

        # Schedule periodic cleanup (only for long-running servers)
        self._schedule_cleanup()

    async def dispatch(self, request: Request, call_next):
        """
        Process the request, caching responses for configured paths with etag validation.

        Args:
            request: FastAPI request
            call_next: Next middleware in chain

        Returns:
            Response
        """
        # Only cache GET requests to specified paths
        if request.method != "GET" or not self._should_cache_path(request.url.path):
            return await call_next(request)

        # Generate cache key
        cache_key = self.cache_key_builder(request)

        # Check for If-None-Match header for etag validation
        if_none_match = request.headers.get("If-None-Match")
        if if_none_match and response_cache.etags.get(cache_key) == if_none_match:
            # Return 304 Not Modified if etag matches
            self._logger.debug(f"ETag match for {cache_key}, returning 304 Not Modified")
            return Response(
                status_code=304,
                headers={"ETag": if_none_match}
            )

        # Try to get from cache
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

        # Get fresh response
        response = await call_next(request)

        # Cache only successful responses
        if 200 <= response.status_code < 400:
            # Read response body
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
        Check if the path should be cached.

        Args:
            path: Request path

        Returns:
            True if should be cached, False otherwise
        """
        return any(path.startswith(prefix) for prefix in self.paths)

    def _default_cache_key_builder(self, request: Request) -> str:
        """
        Build a default cache key from the request.

        Args:
            request: FastAPI request

        Returns:
            Cache key string
        """
        key_components = [
            request.method,
            request.url.path,
            str(sorted(request.query_params.items())),
            request.headers.get("Accept", "*/*"),
            request.headers.get("Accept-Encoding", "identity")
        ]
        key = hashlib.sha256(json.dumps(key_components).encode()).hexdigest()
        return key

    def _schedule_cleanup(self) -> None:
        """Schedule periodic cleanup of expired cache items."""
        import threading

        def cleanup():
            while True:
                time.sleep(60)  # Run every minute
                removed = response_cache.cleanup_expired()
                self._logger.debug(f"Cache cleanup removed {removed} expired items")

        cleanup_thread = threading.Thread(target=cleanup, daemon=True)
        cleanup_thread.start()

    def invalidate_path_prefix(self, path_prefix: str) -> int:
        """
        Invalidate all cache entries for a given path prefix.

        Args:
            path_prefix: Path prefix to invalidate

        Returns:
            Number of invalidated entries
        """
        keys_to_remove = []
        try:
            with response_cache.rwlock.read_locked(timeout=3.0):
                for key in list(response_cache.cache.keys()):
                    if key.startswith(path_prefix):
                        keys_to_remove.append(key)
        except TimeoutError:
            self._logger.warning(f"Timeout acquiring read lock for invalidating path prefix: {path_prefix}")
            return 0

        invalidated = 0
        for key in keys_to_remove:
            if response_cache.remove(key):
                invalidated += 1

        self._logger.info(f"Invalidated {invalidated} cache entries with prefix {path_prefix}")
        return invalidated


def invalidate_cache(path_prefix: Optional[str] = None) -> None:
    """
    Utility function to invalidate cache entries.

    Args:
        path_prefix: Optional path prefix to invalidate, or None for all
    """
    if path_prefix is None:
        response_cache.clear()
    else:
        keys_to_remove = []
        try:
            with response_cache.rwlock.read_locked(timeout=3.0):
                for key in list(response_cache.cache.keys()):
                    if key.startswith(path_prefix):
                        keys_to_remove.append(key)
        except TimeoutError:
            log_warning(f"Timeout acquiring read lock for invalidating path prefix: {path_prefix}")
            return

        for key in keys_to_remove:
            response_cache.remove(key)