from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import time
import logging
import redis
import os
from typing import Dict, Optional, Callable, Any
from functools import lru_cache

logger = logging.getLogger(__name__)

class RateLimitConfig:
    """Configuration for rate limiting."""
    def __init__(
        self,
        requests_per_minute: int = 60,
        admin_requests_per_minute: int = 120,
        anonymous_requests_per_minute: int = 30,
        burst_allowance: int = 10,
        redis_url: Optional[str] = None
    ):
        self.requests_per_minute = requests_per_minute
        self.admin_requests_per_minute = admin_requests_per_minute
        self.anonymous_requests_per_minute = anonymous_requests_per_minute
        self.burst_allowance = burst_allowance
        self.redis_url = redis_url or os.getenv("REDIS_URL")
        

@lru_cache()
def get_rate_limit_config() -> RateLimitConfig:
    """Get rate limit configuration with caching."""
    return RateLimitConfig(
        requests_per_minute=int(os.getenv("RATE_LIMIT_RPM", "60")),
        admin_requests_per_minute=int(os.getenv("ADMIN_RATE_LIMIT_RPM", "120")),
        anonymous_requests_per_minute=int(os.getenv("ANON_RATE_LIMIT_RPM", "30")),
        burst_allowance=int(os.getenv("RATE_LIMIT_BURST", "10")),
        redis_url=os.getenv("REDIS_URL")
    )


def get_client_ip(request: Request) -> str:
    """
    Extract client IP address from request, considering proxy headers.
    
    Args:
        request: The FastAPI request object
        
    Returns:
        str: The client's IP address
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Get the first IP in case of multiple proxies
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"
    
    # Sanitize IP before logging or using in keys
    if not ip or not isinstance(ip, str):
        ip = "unknown"
    elif len(ip) > 45:  # Max length of IPv6
        ip = ip[:45]
        
    return ip


class RedisRateLimiter:
    """
    Distributed rate limiter using Redis for tracking requests across multiple instances.
    """
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)
        self.window_size = 60  # Window size in seconds (1 minute)
        
    def is_rate_limited(self, key: str, max_requests: int) -> bool:
        """
        Check if the request should be rate limited.
        
        Args:
            key: Unique key for the client (usually IP-based)
            max_requests: Maximum number of requests allowed in the window
            
        Returns:
            bool: True if request should be limited, False otherwise
        """
        pipe = self.redis.pipeline()
        current_time = int(time.time())
        window_key = f"{key}:{current_time // self.window_size}"
        
        # Clean up old keys and check current count
        try:
            # Increment counter for current window
            pipe.incr(window_key)
            # Set expiration if not already set
            pipe.expire(window_key, self.window_size * 2)  # 2x window to ensure cleanup
            result = pipe.execute()
            
            # Check if limit exceeded
            request_count = result[0]
            return request_count > max_requests
        except redis.RedisError as e:
            # Log error but don't block requests if Redis fails
            logger.error(f"Redis rate limiting error: {str(e)}")
            return False


class LocalRateLimiter:
    """
    In-memory rate limiter for single-instance deployments.
    """
    def __init__(self):
        self.requests: Dict[str, Dict[int, int]] = {}
        self.window_size = 60  # 1 minute window
        
    def is_rate_limited(self, key: str, max_requests: int) -> bool:
        """
        Check if the request should be rate limited.
        
        Args:
            key: Unique identifier for the client
            max_requests: Maximum requests allowed per window
            
        Returns:
            bool: True if request should be limited, False otherwise
        """
        current_time = int(time.time())
        current_window = current_time // self.window_size
        
        # Initialize if this is the first request for this key
        if key not in self.requests:
            self.requests[key] = {}
        
        # Clean up old windows (more than 2 minutes old)
        self.requests[key] = {
            window: count for window, count in self.requests[key].items()
            if window >= current_window - 2
        }
        
        # Increment counter for current window
        if current_window not in self.requests[key]:
            self.requests[key][current_window] = 0
        self.requests[key][current_window] += 1
        
        # Get total requests in current window
        total_requests = self.requests[key].get(current_window, 0)
        
        return total_requests > max_requests


class RateLimitingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for enforcing rate limits on API endpoints.
    Uses Redis for distributed environments if available, falls back to local.
    """
    def __init__(self, app, config: Optional[RateLimitConfig] = None):
        super().__init__(app)
        self.config = config or get_rate_limit_config()
        
        # Set up the appropriate rate limiter based on configuration
        if self.config.redis_url:
            logger.info("Initializing distributed rate limiter with Redis")
            self.rate_limiter = RedisRateLimiter(self.config.redis_url)
        else:
            logger.info("Initializing local in-memory rate limiter")
            self.rate_limiter = LocalRateLimiter()
    
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Any]
    ) -> Response:
        """
        Process the request and apply rate limiting.
        
        Args:
            request: The FastAPI request object
            call_next: Function to call the next middleware or endpoint
            
        Returns:
            Response: The API response
        """
        # Skip rate limiting for certain paths
        if request.url.path in ["/health", "/metrics"]:
            return await call_next(request)
        
        # Determine client identifier
        client_ip = get_client_ip(request)
        
        # Determine rate limit based on path and authentication
        max_requests = self.config.requests_per_minute
        
        # Apply stricter limits for anonymous users
        if "authorization" not in request.headers:
            max_requests = self.config.anonymous_requests_per_minute
        
        # Apply higher limits for admin endpoints with proper authentication
        if (
            request.url.path.startswith("/admin") and 
            "authorization" in request.headers and
            self._is_admin_user(request)
        ):
            max_requests = self.config.admin_requests_per_minute
        
        # Create unique key for the client
        rate_limit_key = f"rate_limit:{client_ip}:{request.url.path.split('/')[1]}"
        
        # Check if rate limited
        if self.rate_limiter.is_rate_limited(rate_limit_key, max_requests):
            logger.warning(f"Rate limit exceeded for {client_ip} on {request.url.path}")
            return Response(
                content={"error": "Rate limit exceeded. Please try again later."},
                status_code=429,
                media_type="application/json"
            )
        
        # Process the request if not rate limited
        return await call_next(request)
    
    def _is_admin_user(self, request: Request) -> bool:
        """
        Verify if the request is from an admin user.
        
        Args:
            request: The FastAPI request object
            
        Returns:
            bool: True if admin user, False otherwise
        """
        # This is a placeholder - implement proper admin validation
        # Preferably integrate with your authentication system
        auth_header = request.headers.get("authorization", "")
        # Example validation logic - replace with actual implementation
        return auth_header.startswith("Bearer admin_")


# Dependency for checking rate limits in specific endpoints
async def check_rate_limit(
    request: Request, 
    limit_key: Optional[str] = None,
    custom_limit: Optional[int] = None
):
    """
    Dependency function to check rate limits for specific endpoints.
    
    Args:
        request: The FastAPI request object
        limit_key: Optional custom key for rate limiting
        custom_limit: Optional custom request limit
        
    Raises:
        HTTPException: If rate limit is exceeded
    """
    config = get_rate_limit_config()
    
    # Get or create rate limiter
    if config.redis_url:
        rate_limiter = RedisRateLimiter(config.redis_url)
    else:
        # Create a new instance each time to avoid state conflicts
        rate_limiter = LocalRateLimiter()
    
    client_ip = get_client_ip(request)
    endpoint = request.url.path
    
    # Use custom key if provided, otherwise generate from IP and endpoint
    key = limit_key or f"rate_limit:{client_ip}:{endpoint}"
    
    # Use custom limit if provided, otherwise use default
    max_requests = custom_limit or config.requests_per_minute
    
    if rate_limiter.is_rate_limited(key, max_requests):
        logger.warning(f"Endpoint rate limit exceeded for {client_ip} on {endpoint}")
        raise HTTPException(
            status_code=429, 
            detail="Rate limit exceeded for this endpoint. Please try again later."
        )