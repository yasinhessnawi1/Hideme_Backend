"""
Enhanced caching middleware with improved synchronization and cache management features.

This module provides a response caching mechanism with timeout management,
synchronization using a basic lock with lazy initialization,
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

"""
ResponseCache Class:
--------------------
This class implements a thread-safe response caching mechanism using a basic lock
for synchronization. It supports TTL-based expiration of cache entries, and each entry
may optionally include an ETag for cache validation.
"""


class ResponseCache:
    """
    Thread-safe response cache using a basic lock for synchronization.

    This cache allows lock-free reads for high-traffic paths and uses exclusive writes
    to ensure consistency. Each cache entry expires after a TTL and may include an ETag.
    """

    def __init__(self, max_size: int = 1000, default_ttl: int = 600):
        """
        Initialize the response cache.

        Args:
            max_size: Maximum number of items to store.
            default_ttl: Default time-to-live (in seconds) for each cache entry.
        """
        # Initialize the internal dictionary to store cached items.
        self.cache: Dict[str, Any] = {}
        # Set the maximum number of allowed cache entries.
        self.max_size = max_size
        # Set the default TTL (time-to-live) in seconds.
        self.default_ttl = default_ttl
        # Initialize a dictionary to track the last access time of each key.
        self.access_times: Dict[str, float] = {}
        # Initialize a dictionary to track expiration times for each cache entry.
        self.expiration_times: Dict[str, float] = {}
        # Initialize a dictionary to store ETag values for cache validation.
        self.etags: Dict[str, str] = {}
        # Initialize the read/write lock to None for lazy initialization.
        self._rwlock: Optional[TimeoutLock] = None
        # Log the successful initialization of the cache.
        log_info(f"Response cache initialized with max_size={max_size}, default_ttl={default_ttl}s")

    @property
    def rwlock(self) -> TimeoutLock:
        """
        Lazy-initialized lock for synchronizing cache access.

        Returns:
            An instance of TimeoutLock.
        """
        # Check if the lock has not been initialized.
        if self._rwlock is None:
            # Initialize the lock with a low priority.
            self._rwlock = TimeoutLock("response_cache_lock", priority=LockPriority.LOW)
        # Return the initialized lock.
        return self._rwlock

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a value from the cache via a lock-free read.

        Args:
            key: The cache key.

        Returns:
            The cached value if found and not expired; otherwise, None.
        """
        # Get the current time.
        current_time = time.time()
        # Retrieve the cached value using the key.
        value = self.cache.get(key)
        # Check if a value exists for the given key.
        if value is not None:
            # Retrieve the expiration timestamp for the key.
            expiry = self.expiration_times.get(key, 0)
            # Check if the current time is before the expiration time.
            if current_time < expiry:
                # Update the access time of the key.
                try:
                    self.access_times[key] = current_time
                except Exception as e:
                    # Log a warning if there is an error updating access time.
                    log_warning(f"Error updating access time for key {key}: {e}")
                # Return the cached value if still valid.
                return value
            else:
                # Return None if the cache entry has expired.
                return None
        # Return None if there is no cached value.
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
        # Attempt to acquire the write lock with a 5.0-second timeout.
        try:
            self.rwlock.acquire(timeout=5.0)
        except TimeoutError:
            # Log a warning and return False if acquiring the lock times out.
            log_warning(f"Timeout acquiring write lock for cache key: {key}")
            return False

        try:
            # Check if the number of cached items has reached the maximum allowed size.
            if len(self.cache) >= self.max_size:
                # Remove all expired cache entries.
                self._cleanup_expired()
            # If cache is still full, remove the least recently used entry.
            if len(self.cache) >= self.max_size:
                self._remove_lru()
            # Get the current time.
            current_time = time.time()
            # Store the value in the cache.
            self.cache[key] = value
            # Update the access time for the key.
            self.access_times[key] = current_time
            # Set the expiration time for the cache entry.
            self.expiration_times[key] = current_time + (ttl if ttl is not None else self.default_ttl)
            # If a content hash is provided, store it as the ETag for this key.
            if content_hash:
                self.etags[key] = content_hash
            # Return True indicating the value was cached successfully.
            return True
        finally:
            # Always release the write lock, even if an error occurs.
            self.rwlock.release()

    def delete(self, key: str) -> bool:
        """
        Remove a specific cache entry with exclusive write access.

        Args:
            key: The cache key.

        Returns:
            True if the entry was removed, False otherwise.
        """
        # Attempt to acquire the write lock with a 3.0-second timeout.
        try:
            self.rwlock.acquire(timeout=3.0)
        except TimeoutError:
            # Log a warning and return False if acquiring the lock times out.
            log_warning(f"Timeout acquiring write lock for deleting cache key: {key}")
            return False

        try:
            # Check if the key exists in the cache.
            if key in self.cache:
                # Remove the cache entry.
                del self.cache[key]
                # Remove the key from the access times dictionary.
                self.access_times.pop(key, None)
                # Remove the key from the expiration times dictionary.
                self.expiration_times.pop(key, None)
                # Remove the key from the ETag dictionary.
                self.etags.pop(key, None)
                # Return True to indicate successful deletion.
                return True
            # Return False if the key was not found.
            return False
        finally:
            # Release the write lock.
            self.rwlock.release()

    def clear(self) -> bool:
        """
        Clear the entire cache with exclusive write access.

        Returns:
            True if the cache was cleared successfully, False otherwise.
        """
        # Attempt to acquire the write lock with a 10.0-second timeout.
        try:
            self.rwlock.acquire(timeout=10.0)
        except TimeoutError:
            # Log a warning if acquiring the lock times out.
            log_warning("Timeout acquiring write lock for clearing cache")
            return False

        try:
            # Clear the main cache dictionary.
            self.cache.clear()
            # Clear the dictionary tracking access times.
            self.access_times.clear()
            # Clear the expiration times dictionary.
            self.expiration_times.clear()
            # Clear the ETag dictionary.
            self.etags.clear()
            # Log that the cache has been cleared.
            log_info("Response cache cleared")
            # Return True indicating the cache was successfully cleared.
            return True
        finally:
            # Release the write lock.
            self.rwlock.release()

    def _cleanup_expired(self) -> int:
        """
        Remove all expired cache entries.

        Note: Caller must hold the write lock.

        Returns:
            The number of entries removed.
        """
        # Get the current time.
        current_time = time.time()
        # Identify keys for which the expiration time has passed.
        expired_keys = [key for key, expiry in self.expiration_times.items() if current_time > expiry]
        # Iterate over each expired key.
        for key in expired_keys:
            # Remove the key from the main cache.
            self.cache.pop(key, None)
            # Remove the key from the access times dictionary.
            self.access_times.pop(key, None)
            # Remove the key from the expiration times dictionary.
            self.expiration_times.pop(key, None)
            # Remove the key from the ETag dictionary.
            self.etags.pop(key, None)
        # If any keys were removed, log the number of cleaned entries.
        if expired_keys:
            log_info(f"Cleaned up {len(expired_keys)} expired cache entries")
        # Return the count of removed entries.
        return len(expired_keys)

    def _remove_lru(self) -> bool:
        """
        Remove the least recently used (LRU) cache entry.

        Note: Caller must hold the write lock.

        Returns:
            True if an entry was removed; False if the cache is empty.
        """
        # Check if there are any entries in the access times dictionary.
        if not self.access_times:
            # Return False if no entries exist.
            return False
        # Identify the key with the minimum access time (LRU).
        lru_key = min(self.access_times, key=self.access_times.get)
        # Remove the LRU key from the cache.
        self.cache.pop(lru_key, None)
        # Remove the LRU key from the access times.
        self.access_times.pop(lru_key, None)
        # Remove the LRU key from the expiration times.
        self.expiration_times.pop(lru_key, None)
        # Remove the LRU key from the ETag dictionary.
        self.etags.pop(lru_key, None)
        # Log that the LRU cache entry was removed.
        log_info(f"Removed least recently used cache entry: {lru_key}")
        # Return True indicating an entry was removed.
        return True

    def cleanup_expired(self) -> int:
        """
        Clean up expired cache entries with exclusive write access.

        Returns:
            The number of entries removed.
        """
        # Attempt to acquire the write lock with a 5.0-second timeout.
        try:
            self.rwlock.acquire(timeout=5.0)
        except TimeoutError:
            # Log a warning if the lock acquisition times out.
            log_warning("Timeout acquiring write lock for cache cleanup")
            return 0

        try:
            # Call the internal cleanup method and return the number of removed entries.
            return self._cleanup_expired()
        finally:
            # Release the write lock.
            self.rwlock.release()

    def remove(self, key: str) -> bool:
        """
        Alias for the delete() method for backward compatibility.

        Args:
            key: The cache key.

        Returns:
            True if the entry was removed; otherwise, False.
        """
        # Call the delete method to remove the key.
        return self.delete(key)


"""
CacheMiddleware Class:
----------------------
This middleware intercepts GET and POST requests on specified URL path prefixes,
attempting to serve a cached response if available. It computes a unique cache key
for each request, supports ETag validation, and caches successful responses with a TTL.
It also schedules a periodic background cleanup of expired cache entries.
"""


class CacheMiddleware(BaseHTTPMiddleware):
    """
    Enhanced middleware for caching GET and POST responses with ETag support and optimized invalidation.

    This middleware intercepts requests whose URL paths start with specified prefixes (e.g., /ai, /ml, /batch, /pdf)
    and caches the corresponding responses. For POST requests, it builds an asynchronous cache key that normalizes
    the file content and text fields from multipart/form-data. The middleware supports both GET and POST methods,
    and caches responses that include content, status code, headers, and media type, all of which expire after a
    specified TTL (time-to-live).
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
        Initialize the CacheMiddleware.

        Args:
            app: The FastAPI/Starlette application.
            paths: List of URL path prefixes for which responses should be cached.
            ttl: Default time-to-live (in seconds) for cached responses.
            cache_key_builder: Optional function to build a custom cache key. If not provided, uses
                               custom_file_cache_key_builder.
            content_hashing: If True, computes a hash of the response content for ETag generation.
        """
        # Initialize the parent BaseHTTPMiddleware with the app.
        super().__init__(app)
        # Store the list of URL path prefixes to cache.
        self.paths = paths
        # Store the default TTL (time-to-live) for cached responses.
        self.ttl = ttl
        # Set the cache key builder; use a custom one if not provided.
        self.cache_key_builder = cache_key_builder or custom_file_cache_key_builder
        # Store whether to compute a content hash for ETag generation.
        self.content_hashing = content_hashing
        # Create a logger for the cache middleware.
        self._logger = logging.getLogger("cache_middleware")
        # Schedule the periodic cleanup for expired cache entries.
        self._schedule_cleanup()

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Intercept the request, attempt to serve a cached response if available, or cache the downstream response.

        For GET and POST requests on the configured path prefixes:
          - Uses the cache key builder to generate a unique key.
          - Checks if an ETag from the client matches a cached ETag; if so, returns a 304 Not Modified response.
          - If a cached response exists and is valid, returns it.
          - Otherwise, forwards the request to the next handler, caches the successful response,
            and returns it.

        Args:
            request: The incoming request.
            call_next: The next middleware/endpoint callable.

        Returns:
            A Response object, either from cache or freshly generated.
        """
        # If the request method is not GET or POST or the path should not be cached, bypass caching.
        if request.method not in ["GET", "POST"] or not self._should_cache_path(request.url.path):
            # Directly process the request without caching.
            return await call_next(request)

        # Try generating the cache key using the provided builder; if it fails, bypass caching.
        try:
            cache_key = await self.cache_key_builder(request)
        except Exception as e:
            self._logger.error(f"Error generating cache key: {e}")
            return await call_next(request)

        # Check for an ETag match in the client's headers; if it matches, return a 304 response.
        if_none_match = request.headers.get("If-None-Match")
        if if_none_match and response_cache.etags.get(cache_key) == if_none_match:
            self._logger.debug(f"ETag match for {cache_key}, returning 304 Not Modified")
            return Response(status_code=304, headers={"ETag": if_none_match})

        # If a valid cached response exists, return it.
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
            self._logger.info("✅ Cache hit")
            return response

        # Process the request normally by invoking the next handler.
        response = await call_next(request)

        # If the response status code indicates failure or redirection, return it directly.
        if not (200 <= response.status_code < 400):
            return response

        # Helper function to collect the full response body from the async iterator.
        async def _collect_response_body(resp: Response) -> bytes:
            # Initialize an empty byte string.
            body = b""
            # Iterate over the response body chunks.
            async for part in resp.body_iterator:
                # Append each chunk of bytes.
                body += part
            # Return the complete response body.
            return body

        # Retrieve the complete response body.
        response_body = await _collect_response_body(response)

        # Compute the content hash (ETag) if content hashing is enabled.
        content_hash = None
        if self.content_hashing:
            content_hash = hashlib.sha256(response_body).hexdigest()

        # Retrieve a custom TTL from the response headers (if provided), with fallback to default TTL.
        custom_ttl = response.headers.get("X-Cache-TTL")
        try:
            ttl_value = int(custom_ttl) if custom_ttl else self.ttl
        except ValueError:
            ttl_value = self.ttl

        # Cache the response details along with the computed TTL and content hash.
        response_cache.set(
            cache_key,
            {
                "content": response_body,
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "media_type": response.media_type
            },
            ttl=ttl_value,
            content_hash=content_hash
        )

        # Build a new Response object to return the fully cached response.
        new_response = Response(
            content=response_body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type
        )
        if content_hash:
            new_response.headers["ETag"] = content_hash

        # Log that a new response was cached along with its TTL.
        self._logger.info(f"✅ Cached new response with TTL: {ttl_value}")
        return new_response

    def _should_cache_path(self, path: str) -> bool:
        """
        Determine if the request path should be cached.

        Args:
            path: The request URL path.

        Returns:
            True if the path starts with any of the configured prefixes; otherwise, False.
        """
        # Return True if any configured prefix matches the start of the path.
        return any(path.startswith(prefix) for prefix in self.paths)

    def _schedule_cleanup(self) -> None:
        """
        Schedule periodic cleanup of expired cache entries in a background thread.

        This method starts a daemon thread that sleeps for 60 seconds between cleanups.
        """
        import threading

        # Define the cleanup loop function to be run in a separate thread.
        def cleanup_loop():
            # Continuously loop forever.
            while True:
                # Sleep for 60 seconds between cleanups.
                time.sleep(60)
                # Remove expired cache entries and get the count of removed items.
                removed = response_cache.cleanup_expired()
                # Log the number of expired items removed during cleanup.
                self._logger.debug(f"Cache cleanup removed {removed} expired items")

        # Create a new daemon thread to run the cleanup loop.
        cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
        # Start the cleanup thread.
        cleanup_thread.start()


async def custom_file_cache_key_builder(request: Request) -> str:
    """
    Custom asynchronous cache key builder that handles multipart/form-data.

    If the request is a POST with multipart/form-data, it extracts file fields and text fields,
    normalizes them, and computes a hash based on those values. It then resets the request body
    so that downstream processing can still access it.

    Args:
        request: The incoming request.

    Returns:
        A SHA-256 hex digest string representing the cache key.
    """
    # Obtain a logger instance for cache middleware.
    logger = logging.getLogger("cache_middleware")
    # Start with a list of base components for the cache key.
    key_components = [
        request.method,
        request.url.path,
        str(sorted(request.query_params.items())),
        request.headers.get("Accept", "*/*"),
        request.headers.get("Accept-Encoding", "identity")
    ]
    # Get the content type from the headers.
    content_type = request.headers.get("content-type", "")
    # Check if the request is a POST and contains multipart/form-data.
    if request.method == "POST" and "multipart/form-data" in content_type.lower():
        try:
            # Read the raw body bytes from the request.
            raw_body = await request.body()
            # Parse the form data from the request.
            form = await request.form()
            # Sort the form fields to ensure consistent order.
            fields = sorted(form.keys())
            # Initialize an empty list to hold field components.
            field_components = []
            # Process each field in the form.
            for field in fields:
                # Get the value corresponding to the current field.
                value = form.get(field)
                # Check if the value is a file upload (has a filename attribute).
                if hasattr(value, "filename"):
                    # Read the file content.
                    file_content = await value.read()
                    # Compute the SHA-256 hash of the file content.
                    file_hash = hashlib.sha256(file_content).hexdigest()
                    # Append the field name and file hash to field components.
                    field_components.append(f"{field}:{file_hash}")
                    # Reset the file pointer so downstream handlers can read the file.
                    value.file.seek(0)
                else:
                    # For normal fields, append the trimmed string value.
                    field_components.append(f"{field}:{str(value).strip()}")
            # Append the processed field components to the key components.
            key_components.append(field_components)
            # Reset the raw body on the request for downstream processing.
            request._body = raw_body
        except Exception as e:
            # Log any error encountered during multipart form processing.
            logger.error(f"Error processing multipart form for cache key: {e}")
            # Append an empty string to maintain key component structure.
            key_components.append("")
    else:
        try:
            # Read the request body.
            body = await request.body()
            # Append the hexadecimal representation of the body to key components.
            key_components.append(body.hex())
            # Reset the request body for downstream handlers.
            request._body = body
        except Exception as e:
            # Log any error encountered during request body reading.
            logger.error(f"Error reading request body for cache key: {e}")
            # Append an empty string to key components if there's an error.
            key_components.append("")
    # Serialize the key components into a JSON string with sorted keys.
    key_str = json.dumps(key_components, sort_keys=True)
    # Compute and return the SHA-256 hash of the JSON string as the cache key.
    key = hashlib.sha256(key_str.encode()).hexdigest()
    return key


def get_cached_response(key: str) -> Optional[Any]:
    """
    Retrieve a cached response.

    Args:
        key: The cache key.

    Returns:
        The cached response if present and not expired; otherwise, None.
    """
    # Return the cached response using the global response cache.
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
    # Store the response in the global response cache.
    return response_cache.set(key, response, ttl)


def clear_cached_response(key: str) -> bool:
    """
    Clear a specific cached response.

    Args:
        key: The cache key.

    Returns:
        True if the entry was cleared; otherwise, False.
    """
    # Delete the cached response from the global cache.
    return response_cache.delete(key)


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
    # Attempt to acquire the cache lock with the specified timeout.
    try:
        cache.rwlock.acquire(timeout=timeout)
    except TimeoutError:
        # Log a warning if acquiring the lock times out.
        log_warning(f"Timeout acquiring lock for invalidating path prefix: {prefix}")
        return []
    try:
        # Return all keys from the cache that start with the specified prefix.
        return [key for key in list(cache.cache.keys()) if key.startswith(prefix)]
    finally:
        # Release the cache lock.
        cache.rwlock.release()


def invalidate_cache(path_prefix: Optional[str] = None) -> None:
    """
    Invalidate (remove) cache entries by a path prefix or clear the entire cache if None.

    This function minimizes lock usage by retrieving matching keys in a single locked section.

    Args:
        path_prefix: The prefix of cache keys to remove. If None, the entire cache is cleared.
    """
    # Check if no specific prefix was provided.
    if path_prefix is None:
        # Clear the entire cache.
        response_cache.clear()
        return

    # Retrieve the keys that match the provided prefix.
    keys_to_remove = _get_keys_by_prefix(response_cache, path_prefix)
    # Iterate over the keys and remove each from the cache.
    for key in keys_to_remove:
        response_cache.remove(key)


# Global cache instance.
response_cache = ResponseCache()
