"""
Rate Limiting and Request Throttling Module with Comprehensive Documentation.
This module implements configuration classes, helper functions, and middleware to enforce
rate limiting on API endpoints using both distributed (Redis-based) and local (in-memory)
strategies. It ensures that clients do not exceed defined request quotas while providing
detailed logging and configurable limits for different user roles. The module includes:
  - RateLimitConfig: Configures limits for different categories (anonymous, admin, default users).
  - get_rate_limit_config: Cached function to retrieve the configuration.
  - get_client_ip: Utility to extract the client IP address from the request.
  - RedisRateLimiter: Distributed rate limiter using Redis for multi-instance environments.
  - LocalRateLimiter: In-memory rate limiter for single-instance deployments.
  - RateLimitingMiddleware: FastAPI middleware integrating rate limiting logic.
  - check_rate_limit: Dependency to enforce rate limits on specific endpoints.
"""

import os
import time
import logging
import redis
from functools import lru_cache
from typing import Dict, Optional, Callable, Any
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse

# Initialize a logger for the module.
logger = logging.getLogger(__name__)


class RateLimitConfig:
    """
    Configuration class for rate limiting settings.

    This class encapsulates rate limiting parameters such as:
      - requests_per_minute: Standard request limit per minute.
      - admin_requests_per_minute: Higher limit for admin users.
      - anonymous_requests_per_minute: Lower limit for users without authorization.
      - burst_allowance: Extra requests that can be temporarily allowed.
      - redis_url: URL for Redis server to enable distributed rate limiting.
    """

    def __init__(
        self,
        requests_per_minute: int = 30,
        admin_requests_per_minute: int = 60,
        anonymous_requests_per_minute: int = 15,
        burst_allowance: int = 15,
        redis_url: Optional[str] = None,
    ):
        # Set the standard requests per minute limit.
        self.requests_per_minute = requests_per_minute
        # Set the admin user requests per minute limit.
        self.admin_requests_per_minute = admin_requests_per_minute
        # Set the anonymous user requests per minute limit.
        self.anonymous_requests_per_minute = anonymous_requests_per_minute
        # Set the burst allowance limit.
        self.burst_allowance = burst_allowance
        # Set the Redis URL, using environment variable if not provided.
        self.redis_url = redis_url or os.getenv("REDIS_URL")


@lru_cache()
def get_rate_limit_config() -> RateLimitConfig:
    """
    Retrieve the cached rate limit configuration.

    Uses environment variables to define limits:
      - RATE_LIMIT_RPM: Standard requests per minute.
      - ADMIN_RATE_LIMIT_RPM: Requests per minute for admin users.
      - ANON_RATE_LIMIT_RPM: Requests per minute for anonymous users.
      - RATE_LIMIT_BURST: Allowed burst requests.
      - REDIS_URL: URL for the Redis instance.

    Returns:
        RateLimitConfig: An instance of the configuration with cached values.
    """
    # Create and return a RateLimitConfig object with parameters from environment variables.
    return RateLimitConfig(
        # Convert RATE_LIMIT_RPM environment variable to an integer (default 30).
        requests_per_minute=int(os.getenv("RATE_LIMIT_RPM", "30")),
        # Convert ADMIN_RATE_LIMIT_RPM environment variable to an integer (default 60).
        admin_requests_per_minute=int(os.getenv("ADMIN_RATE_LIMIT_RPM", "60")),
        # Convert ANON_RATE_LIMIT_RPM environment variable to an integer (default 15).
        anonymous_requests_per_minute=int(os.getenv("ANON_RATE_LIMIT_RPM", "15")),
        # Convert RATE_LIMIT_BURST environment variable to an integer (default 15).
        burst_allowance=int(os.getenv("RATE_LIMIT_BURST", "15")),
        # Retrieve the Redis URL from environment variables.
        redis_url=os.getenv("REDIS_URL"),
    )


def get_client_ip(request: Request) -> str:
    """
    Extract the client IP address from a FastAPI request, considering proxy headers.

    Args:
        request (Request): The FastAPI request object.

    Returns:
        str: The client's IP address, truncated to a maximum of 45 characters if needed.
    """
    # Retrieve the "X-Forwarded-For" header from the request.
    forwarded = request.headers.get("X-Forwarded-For")
    # If forwarded header is present, extract the first IP.
    if forwarded:
        # Split the forwarded string by commas and strip the first IP.
        ip = forwarded.split(",")[0].strip()
    else:
        # Otherwise, use the request client host if available.
        ip = request.client.host if request.client else "unknown"
    # Validate the extracted IP; if missing or not a string, default to "unknown".
    if not ip or not isinstance(ip, str):
        # Set IP to "unknown" if it's invalid.
        ip = "unknown"
    # Truncate the IP string if it is longer than 45 characters.
    elif len(ip) > 45:
        # Truncate to ensure a maximum of 45 characters.
        ip = ip[:45]
    # Return the processed client IP.
    return ip


class RedisRateLimiter:
    """
    Distributed rate limiter using Redis.

    This class employs Redis to track the number of requests made by a client
    within a fixed time window (default: 60 seconds). It supports distributed scenarios
    where multiple instances need to share rate limiting data.
    """

    def __init__(self, redis_url: str):
        # Initialize a Redis client using the provided URL.
        self.redis = redis.from_url(redis_url)
        # Define the time window for rate limiting in seconds.
        self.window_size = 60

    def is_rate_limited(self, key: str, max_requests: int) -> bool:
        """
        Determine whether the request should be rate limited.

        Args:
            key (str): A unique identifier (typically based on client IP and endpoint).
            max_requests (int): Maximum allowed requests in the current time window.

        Returns:
            bool: True if the client has exceeded the allowed number of requests, False otherwise.
        """
        # Create a Redis pipeline to execute multiple commands atomically.
        pipe = self.redis.pipeline()
        # Get the current time in seconds.
        current_time = int(time.time())
        # Compute a key that represents the current window.
        window_key = f"{key}:{current_time // self.window_size}"
        # Increment the count for the current window.
        pipe.incr(window_key)
        # Set an expiration on the window key (twice the window size for safety).
        pipe.expire(window_key, self.window_size * 2)
        # Execute the pipeline commands.
        try:
            # Run the pipeline commands and collect results.
            result = pipe.execute()
            # The first result is the incremented count.
            request_count = result[0]
            # Return True if the request count exceeds maximum allowed requests.
            return request_count > max_requests
        except redis.RedisError as e:
            # Log any Redis errors that occur during rate limiting.
            logger.error(f"Redis rate limiting error: {str(e)}")
            # On error, do not rate limit (fail open).
            return False


class LocalRateLimiter:
    """
    In-memory rate limiter for single-instance deployments.

    This class uses a dictionary to track request counts for each client over time windows,
    eliminating the need for external data storage. It is less suitable for distributed systems.
    """

    def __init__(self):
        # Initialize an empty dictionary to store request count per client per window.
        self.requests: Dict[str, Dict[int, int]] = {}
        # Define the time window in seconds.
        self.window_size = 60

    def is_rate_limited(self, key: str, max_requests: int) -> bool:
        """
        Check whether a client identified by a key has exceeded the request limit.

        Args:
            key (str): Unique identifier for the client.
            max_requests (int): Maximum allowed requests within a time window.

        Returns:
            bool: True if the request count is above the limit, False otherwise.
        """
        # Get the current time in seconds.
        current_time = int(time.time())
        # Determine the current time window.
        current_window = current_time // self.window_size
        # If the client key is not in the requests dictionary, initialize it.
        if key not in self.requests:
            # Create an empty dictionary for this client key.
            self.requests[key] = {}
        # Remove outdated windows (keep only windows that are within the last 2 windows).
        self.requests[key] = {
            window: count
            for window, count in self.requests[key].items()
            if window >= current_window - 2
        }
        # Initialize the count for the current window if it doesn't exist.
        if current_window not in self.requests[key]:
            # Set the count for the current window to zero.
            self.requests[key][current_window] = 0
        # Increment the count for the current window by 1.
        self.requests[key][current_window] += 1
        # Get the total requests for the current window.
        total_requests = self.requests[key].get(current_window, 0)
        # Check if the total requests exceed the maximum allowed and return the result.
        return total_requests > max_requests


class RateLimitingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for enforcing API rate limits.

    This middleware intercepts incoming requests and applies rate limiting based on client IP,
    request path, and user role (admin or anonymous). It utilizes a Redis-based rate limiter
    for distributed environments if available; otherwise, it falls back to an in-memory limiter.
    """

    def __init__(self, app, config: Optional[RateLimitConfig] = None):
        # Call the parent class initializer with the FastAPI app.
        super().__init__(app)
        # Set the configuration using the provided value or the cached configuration.
        self.config = config or get_rate_limit_config()
        # Check if Redis is available for distributed rate limiting.
        if self.config.redis_url:
            # Log that the Redis-based rate limiter is being initialized.
            logger.info("Initializing distributed rate limiter with Redis")
            # Initialize the RedisRateLimiter with the Redis URL.
            self.rate_limiter = RedisRateLimiter(self.config.redis_url)
        else:
            # Log that the in-memory local rate limiter is being used.
            logger.info("Initializing local in-memory rate limiter")
            # Initialize the LocalRateLimiter.
            self.rate_limiter = LocalRateLimiter()

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Any]
    ) -> Response:
        """
        Process the incoming request and enforce rate limiting.

        Args:
            request (Request): The incoming FastAPI request.
            call_next (Callable[[Request], Any]): A function to process the request and return a response.

        Returns:
            Response: The resulting API response after rate limiting is applied.
        """
        # Check if the request path is exempt from rate limiting (health or metrics endpoints).
        if request.url.path in ["/health", "/metrics"]:
            # Directly pass through the request if it is exempt.
            return await call_next(request)
        # Retrieve the client IP address from the request.
        client_ip = get_client_ip(request)
        # Set the default maximum requests per minute from configuration.
        max_requests = self.config.requests_per_minute
        # Determine if the request is anonymous (absence of authorization header).
        if "authorization" not in request.headers:
            # Use a lower request limit for anonymous users.
            max_requests = self.config.anonymous_requests_per_minute
        # Check if the request targets an admin endpoint and contains an admin authorization.
        if (
            request.url.path.startswith("/admin")
            and "authorization" in request.headers
            and self._is_admin_user(request)
        ):
            # Increase the request limit for admin users.
            max_requests = self.config.admin_requests_per_minute
        # Form a unique rate limit key using the client IP and a segment of the URL.
        rate_limit_key = f"rate_limit:{client_ip}:{request.url.path.split('/')[1]}"
        # Use the appropriate rate limiter to check if the client is rate limited.
        if self.rate_limiter.is_rate_limited(rate_limit_key, max_requests):
            # Log a warning indicating the rate limit has been exceeded.
            logger.warning(f"Rate limit exceeded for {client_ip} on {request.url.path}")
            # Return a JSON response with a 429 status code if the limit is exceeded.
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please try again later."},
            )
        # If not rate limited, pass the request to the next middleware or endpoint.
        return await call_next(request)

    @staticmethod
    def _is_admin_user(request: Request) -> bool:
        """
        Determine if the request comes from an admin user.

        Args:
            request (Request): The incoming FastAPI request.

        Returns:
            bool: True if the request has an admin authorization header, otherwise False.
        """
        # Retrieve the authorization header from the request.
        auth_header = request.headers.get("authorization", "")
        # Check if the authorization header starts with "Bearer admin_" to identify admin users.
        return auth_header.startswith("Bearer admin_")


async def check_rate_limit(
    request: Request,
    limit_key: Optional[str] = None,
    custom_limit: Optional[int] = None,
):
    """
    Dependency function to enforce rate limits on specific API endpoints.

    This function checks if the incoming request exceeds the allowed number of requests.
    It selects the appropriate rate limiter based on configuration (Redis or local), retrieves
    the client IP, constructs the rate limiting key, and raises an HTTPException if the limit is exceeded.

    Args:
        request (Request): The FastAPI request object.
        limit_key (Optional[str]): An optional custom key to override the default rate limit key.
        custom_limit (Optional[int]): An optional custom request limit.

    Raises:
        HTTPException: If the client's request rate exceeds the permitted limit.
    """
    # Retrieve the cached rate limit configuration.
    config = get_rate_limit_config()
    # Determine which rate limiter to use based on the configuration.
    if config.redis_url:
        # Use the Redis-based rate limiter if a Redis URL is provided.
        rate_limiter = RedisRateLimiter(config.redis_url)
    else:
        # Otherwise, use the in-memory local rate limiter.
        rate_limiter = LocalRateLimiter()
    # Extract the client IP address from the request.
    client_ip = get_client_ip(request)
    # Get the endpoint path from the request.
    endpoint = request.url.path
    # Construct the rate limiting key using the provided limit_key or a default combination.
    key = limit_key or f"rate_limit:{client_ip}:{endpoint}"
    # Determine the maximum allowed requests using the custom limit or the default configuration.
    max_requests = custom_limit or config.requests_per_minute
    # Check if the request exceeds the allowed number of requests.
    if rate_limiter.is_rate_limited(key, max_requests):
        # Log a warning if the endpoint rate limit has been exceeded.
        logger.warning(f"Endpoint rate limit exceeded for {client_ip} on {endpoint}")
        # Raise an HTTPException with a 429 status code if rate limited.
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded for this endpoint. Please try again later.",
        )
