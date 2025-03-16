"""
Response caching middleware with memory-efficient implementation and optimized cache invalidation.

This module provides a response caching middleware for FastAPI to improve performance
for frequently accessed endpoints with content-based cache validation and distributed
cache invalidation support.
"""
import os
import time
import hashlib
import json
import logging
import sys
from typing import Dict, Any, Optional, Callable, List
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class ResponseCache:
    """
    Enhanced in-memory cache for response data with TTL support, content validation,
    and improved eviction strategies.
    """

    def __init__(self, max_size: int = 100, default_ttl: int = 300):
        """
        Initialize the response cache with configurable settings.

        Args:
            max_size: Maximum number of cached responses
            default_ttl: Default time-to-live in seconds
        """
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.access_times: Dict[str, float] = {}
        self.hit_counts: Dict[str, int] = {}  # Track hit frequency for better eviction
        self.etags: Dict[str, str] = {}  # Store etags for content validation
        self._logger = logging.getLogger("cache_middleware")
        self._memory_limit_mb = int(os.environ.get("CACHE_MEMORY_LIMIT_MB", "50"))  # 50MB default
        self._current_memory_usage = 0
        self._last_memory_check = time.time()
        self._memory_check_interval = 60  # Check memory usage every minute

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get a cached response by key with validation and metrics tracking.

        Args:
            key: Cache key

        Returns:
            Cached response or None if not found/expired
        """
        if key not in self.cache:
            return None

        cached_item = self.cache[key]

        # Check if expired
        if "expire_time" in cached_item and cached_item["expire_time"] < time.time():
            # Remove expired item
            self.remove(key)
            self._logger.debug(f"Cache item {key} expired and was removed")
            return None

        # Update access time and hit count
        self.access_times[key] = time.time()
        self.hit_counts[key] = self.hit_counts.get(key, 0) + 1

        self._logger.debug(f"Cache hit for {key}, hit count: {self.hit_counts[key]}")

        # Periodically check memory usage
        current_time = time.time()
        if current_time - self._last_memory_check > self._memory_check_interval:
            self._check_memory_usage()
            self._last_memory_check = current_time

        return cached_item

    def set(
            self,
            key: str,
            value: Dict[str, Any],
            ttl: Optional[int] = None,
            content_hash: Optional[str] = None
    ) -> None:
        """
        Set a cached response with improved cache management.

        Args:
            key: Cache key
            value: Response data to cache
            ttl: Time-to-live in seconds, or None for default (with content-based variant)
            content_hash: Optional hash of content for etag validation
        """
        # Check memory usage before adding
        item_size = self._estimate_item_size(key, value)
        if self._current_memory_usage + item_size > self._memory_limit_mb * 1024 * 1024:
            # Memory limit would be exceeded, evict items
            self._evict_for_memory(item_size)

        # Ensure we don't exceed max size
        if len(self.cache) >= self.max_size and key not in self.cache:
            # Evict item based on combined recency and frequency
            self._evict_optimal_item()

        # Adjust TTL based on content type if not explicitly provided
        if ttl is None:
            media_type = value.get("media_type", "").lower()
            if "json" in media_type:
                ttl = self.default_ttl * 2  # Longer TTL for JSON responses
            elif "html" in media_type:
                ttl = int(self.default_ttl * 1.5)  # Slightly longer for HTML
            else:
                ttl = self.default_ttl

        expire_time = time.time() + ttl if ttl > 0 else None

        # Store item
        if expire_time:
            value["expire_time"] = expire_time

        self.cache[key] = value
        self.access_times[key] = time.time()
        self.hit_counts[key] = 0  # Initialize hit count for new entries

        # Update memory usage
        self._current_memory_usage += item_size

        # Store content hash for etag validation if provided
        if content_hash:
            self.etags[key] = content_hash

        self._logger.debug(f"Cached response for {key} with TTL {ttl}s")

    def _check_memory_usage(self) -> None:
        """
        Check current memory usage and evict items if needed.
        """
        # Recalculate total memory usage periodically as estimation may drift
        total_size = 0
        for key, value in self.cache.items():
            total_size += self._estimate_item_size(key, value)

        self._current_memory_usage = total_size

        # If over limit, trigger eviction
        memory_limit_bytes = self._memory_limit_mb * 1024 * 1024
        if self._current_memory_usage > memory_limit_bytes:
            # Target 80% of limit to avoid frequent evictions
            target_size = int(memory_limit_bytes * 0.8)
            self._evict_for_memory(self._current_memory_usage - target_size)

    def _evict_for_memory(self, bytes_to_free: int) -> None:
        """
        Evict items to free up at least the specified amount of memory.

        Args:
            bytes_to_free: Amount of memory to free in bytes
        """
        if not self.cache:
            return

        # Calculate scores as in _evict_optimal_item, but continue evicting until
        # we've freed enough memory
        current_time = time.time()
        max_age = max((current_time - access_time) for access_time in self.access_times.values())
        max_hits = max(self.hit_counts.values()) if self.hit_counts else 1

        eviction_scores = {}
        item_sizes = {}

        for key in self.cache:
            age = current_time - self.access_times.get(key, 0)
            hits = self.hit_counts.get(key, 0)

            # Normalize values to 0-1 range
            normalized_age = age / max_age if max_age > 0 else 0
            normalized_hits = hits / max_hits if max_hits > 0 else 0

            # Calculate score (0.7 weight to recency, 0.3 to frequency)
            eviction_scores[key] = (0.7 * normalized_age) - (0.3 * normalized_hits)
            item_sizes[key] = self._estimate_item_size(key, self.cache[key])

        # Sort by eviction score (highest first)
        sorted_items = sorted(eviction_scores.items(), key=lambda x: x[1], reverse=True)

        # Evict items until we've freed enough memory
        freed_bytes = 0
        for key, _ in sorted_items:
            if freed_bytes >= bytes_to_free:
                break

            freed_bytes += item_sizes.get(key, 0)
            self.remove(key)
            self._logger.debug(f"Evicted cache entry {key} to free memory")

        self._current_memory_usage -= freed_bytes

    def _estimate_item_size(self, key: str, value: Dict[str, Any]) -> int:
        """
        Estimate the size of a cached item in bytes.

        Args:
            key: Cache key
            value: Cached value

        Returns:
            Estimated size in bytes
        """
        # Key size
        key_size = len(key) * 2  # Unicode characters are ~2 bytes each

        def deep_getsizeof(o, seen=None):
            """Recursively finds size of objects including contained objects."""
            size = sys.getsizeof(o)
            if seen is None:
                seen = set()
            obj_id = id(o)
            if obj_id in seen:
                return 0
            seen.add(obj_id)
            if isinstance(o, dict):
                size += sum(deep_getsizeof(k, seen) + deep_getsizeof(v, seen) for k, v in o.items())
            elif isinstance(o, (list, tuple, set, frozenset)):
                size += sum(deep_getsizeof(i, seen) for i in o)
            return size

        try:
            # Try to estimate using a deep size calculation
            value_size = deep_getsizeof(value)
        except Exception:
            # Fallback to a rough estimate if deep size calculation fails
            value_size = 1024

        # Dictionary overhead
        overhead = 24  # Rough estimate of dict entry overhead

        return key_size + value_size + overhead

    def remove(self, key: str) -> None:
        """
        Remove a cached item and update memory usage.

        Args:
            key: Cache key to remove
        """
        if key in self.cache:
            size = self._estimate_item_size(key, self.cache[key])
            del self.cache[key]
            self.access_times.pop(key, None)
            self.hit_counts.pop(key, None)
            self.etags.pop(key, None)
            self._current_memory_usage = max(0, self._current_memory_usage - size)

    def _evict_optimal_item(self) -> None:
        """
        Evict one item based on combined recency and frequency.
        """
        current_time = time.time()
        max_age = max((current_time - access_time) for access_time in self.access_times.values())
        max_hits = max(self.hit_counts.values()) if self.hit_counts else 1

        eviction_scores = {}
        for key in self.cache:
            age = current_time - self.access_times.get(key, 0)
            hits = self.hit_counts.get(key, 0)
            normalized_age = age / max_age if max_age > 0 else 0
            normalized_hits = hits / max_hits if max_hits > 0 else 0
            eviction_scores[key] = (0.7 * normalized_age) - (0.3 * normalized_hits)

        # Evict the item with the highest score
        key_to_evict = max(eviction_scores, key=eviction_scores.get)
        self.remove(key_to_evict)
        self._logger.debug(f"Evicted optimal cache entry {key_to_evict} based on score")

    def cleanup_expired(self) -> int:
        """
        Remove all expired cache items.

        Returns:
            Number of items removed.
        """
        removed = 0
        for key in list(self.cache.keys()):
            if "expire_time" in self.cache[key] and self.cache[key]["expire_time"] < time.time():
                self.remove(key)
                removed += 1
        return removed

    def clear(self) -> None:
        """
        Clear the entire cache.
        """
        self.cache.clear()
        self.access_times.clear()
        self.hit_counts.clear()
        self.etags.clear()
        self._current_memory_usage = 0


# Global cache instance (for efficiency, this should be shared)
response_cache = ResponseCache(max_size=200, default_ttl=300)  # 5 minutes default TTL


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
        for key in list(response_cache.cache.keys()):
            if key.startswith(path_prefix):
                keys_to_remove.append(key)

        for key in keys_to_remove:
            response_cache.remove(key)

        self._logger.info(f"Invalidated {len(keys_to_remove)} cache entries with prefix {path_prefix}")
        return len(keys_to_remove)


def get_cached_response(endpoint_name: str) -> Optional[Dict[str, Any]]:
    """
    Utility function to directly access the cache for testing/metrics.

    Args:
        endpoint_name: Name of the endpoint (cache key)

    Returns:
        Cached response or None
    """
    return response_cache.get(endpoint_name)


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
        for key in list(response_cache.cache.keys()):
            if key.startswith(path_prefix):
                keys_to_remove.append(key)
        for key in keys_to_remove:
            response_cache.remove(key)
