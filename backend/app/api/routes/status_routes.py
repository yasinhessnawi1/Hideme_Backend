"""
Status endpoints for monitoring system health with simplified synchronization and improved performance.
"""
import os
import threading
import time

import psutil
from fastapi import APIRouter, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.api.models import StatusResponse
from backend.app.utils.security.caching_middleware import response_cache
from backend.app.utils.logging.logger import log_info
from backend.app.utils.memory_management import memory_monitor

# Configure rate limiter
limiter = Limiter(key_func=get_remote_address)

router = APIRouter()

# Cache TTL (in seconds)
STATUS_CACHE_TTL = 5
HEALTH_CACHE_TTL = 5
METRICS_CACHE_TTL = 10

# Atomic initialization status flag
_initialization_status = {"status": {}}


@router.get("/status", response_model=StatusResponse)
@limiter.limit("60/minute")
async def status(request: Request, response: Response):
    """
    Status endpoint to verify the API is running with optimized caching.

    Returns:
        JSON response with status information
    """
    # Set cache control header - short TTL for status
    response.headers["Cache-Control"] = f"public, max-age={STATUS_CACHE_TTL}"

    # Check cache first for quick response
    cache_key = "api_status"
    cached_response = response_cache.get(cache_key)
    if cached_response:
        return JSONResponse(content=cached_response)

    # No lock needed for simple status, just generate fresh data
    status_data = {
        "status": "success",
        "timestamp": time.time(),
        "api_version": os.environ.get("API_VERSION", "1.0.0")
    }

    # Cache the response
    response_cache.set(cache_key, status_data, ttl=STATUS_CACHE_TTL)

    return JSONResponse(content=status_data)


@router.get("/health")
@limiter.limit("30/minute")
async def health_check(request: Request, response: Response):
    """
    Health check endpoint for monitoring with enhanced metrics and simplified synchronization.

    Returns:
        JSON response with detailed health check information
    """
    # This endpoint should not be cached for too long as health status changes frequently
    response.headers["Cache-Control"] = f"public, max-age={HEALTH_CACHE_TTL}"

    # Check cache for recent health data
    cache_key = "health_check"
    cached_response = response_cache.get(cache_key)
    if cached_response:
        return JSONResponse(content=cached_response)

    # Get process info without locks - point-in-time data is acceptable
    process = psutil.Process(os.getpid())
    process_info = {
        "cpu_percent": process.cpu_percent(),
        "memory_percent": process.memory_percent(),
        "threads_count": threading.active_count(),
        "uptime": time.time() - process.create_time()
    }

    # Get memory stats - these access atomic counters
    memory_stats = memory_monitor.get_memory_stats()

    # Get cache stats
    cache_stats = {
        "cache_size": len(response_cache.cache),
        "cached_endpoints": list(response_cache.cache.keys())[:5]  # Limit to first 5 for brevity
    }

    # Build health response
    health_data = {
        "status": "healthy",
        "timestamp": time.time(),
        "services": {
            "api": "online",
            "document_processing": "online"
        },
        "process": process_info,
        "memory": memory_stats,
        "cache": cache_stats
    }

    # Add any environment-specific info
    environment = os.environ.get("ENVIRONMENT", "development")
    if environment != "production":
        # Include more debug info for non-production environments
        health_data["debug"] = {
            "environment": environment,
            "python_version": os.environ.get("PYTHON_VERSION", "unknown"),
            "host": os.environ.get("HOSTNAME", "unknown")
        }

    # Cache the response
    response_cache.set(cache_key, health_data, ttl=HEALTH_CACHE_TTL)

    return JSONResponse(content=jsonable_encoder(health_data))


@router.get("/metrics")
@limiter.limit("15/minute")
async def metrics(request: Request, response: Response):
    """
    Metrics endpoint for monitoring system performance with simplified synchronization.

    Returns:
        JSON response with performance metrics
    """
    # This endpoint should not be cached for too long as metrics change frequently
    response.headers["Cache-Control"] = "no-cache"

    # Check if requester is authorized (in the future, this would integrate with auth system)
    # For now, we use a simple API key check from environment
    api_key = request.headers.get("X-API-Key")
    expected_key = os.environ.get("METRICS_API_KEY", "")

    if expected_key and api_key != expected_key:
        return JSONResponse(
            status_code=403,
            content={"detail": "Unauthorized access to metrics endpoint"}
        )

    # No need for lock - point-in-time data is acceptable for metrics
    # Get system metrics
    system_memory = psutil.virtual_memory()
    system_cpu = psutil.cpu_percent(interval=0.1)

    # Get process metrics
    process = psutil.Process(os.getpid())
    process_info = {
        "cpu_percent": process.cpu_percent(),
        "memory_rss": process.memory_info().rss,
        "memory_percent": process.memory_percent(),
        "threads_count": threading.active_count(),
        "open_files": len(process.open_files()),
        "connections": len(process.connections())
    }

    # Get memory monitoring stats (these use atomic operations internally)
    memory_stats = memory_monitor.get_memory_stats()

    # Get cache stats
    cache_stats = {
        "cache_size": len(response_cache.cache),
        "cache_keys": len(response_cache.access_times) if hasattr(response_cache, 'access_times') else 0
    }

    # Build metrics response
    metrics_data = {
        "timestamp": time.time(),
        "system": {
            "cpu_percent": system_cpu,
            "memory_percent": system_memory.percent,
            "memory_available": system_memory.available,
            "memory_total": system_memory.total
        },
        "process": process_info,
        "memory_monitor": memory_stats,
        "cache": cache_stats
    }

    # Log metrics access for auditing (non-sensitive data)
    log_info(f"[METRICS] Metrics requested by {request.client.host}")

    return JSONResponse(content=jsonable_encoder(metrics_data))


@router.get("/readiness")
@limiter.limit("60/minute")
async def readiness_check(request: Request):
    """
    Readiness check endpoint for load balancers and orchestration with simplified synchronization.

    Returns:
        JSON response indicating if the service is ready to accept requests
    """
    # Use simple atomic access to initialization status - no locks needed
    # This assumes initialization_service updates the global status directly
    from backend.app.services.initialization_service import initialization_service
    init_status = initialization_service.get_initialization_status()

    # Check if essential services are initialized
    is_ready = init_status.get("presidio", False)

    # Check if memory usage is within acceptable limits
    memory_usage = memory_monitor.get_memory_usage()
    memory_ok = memory_usage < memory_monitor.critical_threshold

    status_code = 200 if is_ready and memory_ok else 503

    readiness_data = {
        "ready": is_ready and memory_ok,
        "services": {
            "presidio_ready": init_status.get("presidio", False),
            "gemini_ready": init_status.get("gemini", False),
            "gliner_ready": init_status.get("gliner", False)
        },
        "memory": {
            "usage_percent": memory_usage,
            "status": "ok" if memory_ok else "critical"
        }
    }

    return JSONResponse(
        status_code=status_code,
        content=readiness_data
    )