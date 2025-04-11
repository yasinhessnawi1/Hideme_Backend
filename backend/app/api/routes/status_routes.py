"""
Status endpoints for monitoring system health with simplified synchronization and improved performance.

This module provides endpoints to monitor system health, report API status, gather performance metrics,
and check service readiness. It employs caching for frequently requested endpoints and uses robust error
handling to ensure that sensitive information is not leaked in error messages.
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

from backend.app.utils.constant.constant import STATUS_CACHE_TTL, HEALTH_CACHE_TTL, METRICS_CACHE_TTL
from backend.app.utils.logging.logger import log_info
from backend.app.utils.security.caching_middleware import response_cache
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.system_utils.memory_management import memory_monitor

# Configure rate limiter using the client's remote address.
limiter = Limiter(key_func=get_remote_address)

# Create the API router.
router = APIRouter()

# Atomic initialization status flag (if needed).
_initialization_status = {"status": {}}


@router.get("/status")
@limiter.limit("60/minute")
async def status(request: Request, response: Response) -> JSONResponse:
    """
    Get a simple API status with current timestamp and version info.

    This endpoint returns a quick status response and leverages caching to improve response time.
    It sets cache control headers and caches the result for a short duration (5 seconds).

    Parameters:
        request (Request): The incoming HTTP request.
        response (Response): The outgoing HTTP response (for setting caching headers).

    Returns:
        JSONResponse: A JSON response containing status information, or a secure error response if an exception occurs.
    """
    try:
        # Set caching headers for the status endpoint.
        response.headers["Cache-Control"] = f"public, max-age={STATUS_CACHE_TTL}"
        response.headers["X-Cache-TTL"] = str(STATUS_CACHE_TTL)
        # Define a cache key and check if a cached response exists.
        cache_key = "api_status"
        cached_response = response_cache.get(cache_key)
        if cached_response:
            return JSONResponse(content=cached_response)
        # Generate the status data.
        status_data = {
            "status": "success",
            "timestamp": time.time(),
            "api_version": os.environ.get("API_VERSION", "1.0.0")
        }
        # Cache the status data.
        response_cache.set(cache_key, status_data, ttl=STATUS_CACHE_TTL)
        resp = JSONResponse(content=status_data)
        resp.headers["Cache-Control"] = f"public, max-age={STATUS_CACHE_TTL}"
        resp.headers["X-Cache-TTL"] = str(STATUS_CACHE_TTL)
        return resp
    except Exception as e:
        # Log the error and create a secure error response.
        log_info(f"[STATUS] Error retrieving status: {str(e)}")
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_status_router", resource_id=str(request.url)
        )
        status_code = error_response.get("status_code", 500)
        return JSONResponse(content=error_response, status_code=status_code)


@router.get("/health")
@limiter.limit("30/minute")
async def health_check(request: Request, response: Response) -> JSONResponse:
    """
    Perform a health check for the system with detailed metrics.

    This endpoint gathers process information, memory stats, and cache stats.
    The response is cached for a short duration (5 seconds) to improve performance.

    Parameters:
        request (Request): The incoming HTTP request.
        response (Response): The outgoing HTTP response (for setting caching headers).

    Returns:
        JSONResponse: A JSON response with detailed health check information, or a secure error response if an exception occurs.
    """
    try:
        # Set caching headers for health check.
        response.headers["Cache-Control"] = f"public, max-age={HEALTH_CACHE_TTL}"
        response.headers["X-Cache-TTL"] = str(HEALTH_CACHE_TTL)
        # Define a cache key and check if a cached health response exists.
        cache_key = "health_check"
        cached_response = response_cache.get(cache_key)
        if cached_response:
            return JSONResponse(content=cached_response)
        # Gather process metrics.
        process = psutil.Process(os.getpid())
        process_info = {
            "cpu_percent": process.cpu_percent(),
            "memory_percent": process.memory_percent(),
            "threads_count": threading.active_count(),
            "uptime": time.time() - process.create_time()
        }
        # Retrieve memory statistics.
        memory_stats = memory_monitor.get_memory_stats()
        # Get cache statistics.
        cache_stats = {
            "cache_size": len(response_cache.cache),
            "cached_endpoints": list(response_cache.cache.keys())[:5]  # Limit to first 5 keys.
        }
        # Build the health data dictionary.
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
        # Optionally include debug info in non-production environments.
        environment = os.environ.get("ENVIRONMENT", "development")
        if environment != "production":
            health_data["debug"] = {
                "environment": environment,
                "python_version": os.environ.get("PYTHON_VERSION", "unknown"),
                "host": os.environ.get("HOSTNAME", "unknown")
            }
        # Cache the health data.
        response_cache.set(cache_key, health_data, ttl=HEALTH_CACHE_TTL)
        resp = JSONResponse(content=jsonable_encoder(health_data))
        resp.headers["Cache-Control"] = f"public, max-age={HEALTH_CACHE_TTL}"
        resp.headers["X-Cache-TTL"] = str(HEALTH_CACHE_TTL)
        return resp
    except Exception as e:
        # Log error and return secure error response.
        log_info(f"[HEALTH] Error during health check: {str(e)}")
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_health_router", resource_id=str(request.url)
        )
        status_code = error_response.get("status_code", 500)
        return JSONResponse(content=error_response, status_code=status_code)


@router.get("/metrics")
@limiter.limit("15/minute")
async def metrics(request: Request, response: Response) -> JSONResponse:
    """
    Retrieve system and process performance metrics.

    This endpoint gathers and returns various metrics including system CPU, memory, process details,
    memory monitoring stats, and cache statistics. It enforces access control via an API key.

    Parameters:
        request (Request): The incoming HTTP request.
        response (Response): The outgoing HTTP response (for setting caching headers).

    Returns:
        JSONResponse: A JSON response with performance metrics, or a secure error response if an exception occurs.
    """
    try:
        # Set caching headers for metrics.
        cache_key = "api_metrics"
        response.headers["Cache-Control"] = f"public, max-age={METRICS_CACHE_TTL}"
        response.headers["X-Cache-TTL"] = str(METRICS_CACHE_TTL)
        # Check for API key in request headers.
        api_key = request.headers.get("X-API-Key")
        expected_key = os.environ.get("METRICS_API_KEY", "")
        if expected_key and api_key != expected_key:
            return JSONResponse(
                status_code=403,
                content={"detail": "Unauthorized access to metrics endpoint"}
            )
        # Get system metrics.
        system_memory = psutil.virtual_memory()
        system_cpu = psutil.cpu_percent(interval=0.1)
        # Get process metrics.
        process = psutil.Process(os.getpid())
        process_info = {
            "cpu_percent": process.cpu_percent(),
            "memory_rss": process.memory_info().rss,
            "memory_percent": process.memory_percent(),
            "threads_count": threading.active_count(),
            "open_files": len(process.open_files()),
            "connections": len(process.connections())
        }
        # Get memory monitoring statistics.
        memory_stats = memory_monitor.get_memory_stats()
        # Get cache statistics.
        cache_stats = {
            "cache_size": len(response_cache.cache),
            "cache_keys": len(response_cache.access_times) if hasattr(response_cache, 'access_times') else 0
        }
        # Build the metrics data dictionary.
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
        response_cache.set(cache_key, metrics_data, ttl=METRICS_CACHE_TTL)
        resp = JSONResponse(content=jsonable_encoder(metrics_data))
        resp.headers["Cache-Control"] = f"public, max-age={METRICS_CACHE_TTL}"
        resp.headers["X-Cache-TTL"] = str(METRICS_CACHE_TTL)
        log_info(f"[METRICS] Metrics requested by {request.client.host}")
        return resp
    except Exception as e:
        log_info(f"[METRICS] Error retrieving metrics: {str(e)}")
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_metrics_router", resource_id=str(request.url)
        )
        status_code = error_response.get("status_code", 500)
        return JSONResponse(content=error_response, status_code=status_code)


@router.get("/readiness")
@limiter.limit("60/minute")
async def readiness_check(request: Request) -> JSONResponse:
    """
    Perform a readiness check to determine if the service is ready to accept requests.

    This endpoint is used by load balancers and orchestration systems to verify that the service
    is properly initialized and that resource usage is within acceptable limits.

    Parameters:
        request (Request): The incoming HTTP request.

    Returns:
        JSONResponse: A JSON response indicating the readiness of the service, or a secure error response if an exception occurs.
    """
    try:
        # Get initialization status from the initialization service.
        from backend.app.services.initialization_service import initialization_service
        init_status = initialization_service.get_initialization_status()
        # Determine if essential services are initialized.
        is_ready = init_status.get("presidio", False)
        # Check current memory usage.
        memory_usage = memory_monitor.get_memory_usage()
        memory_ok = memory_usage < memory_monitor.critical_threshold
        # Set HTTP status code based on readiness.
        status_code = 200 if is_ready and memory_ok else 503
        # Build the readiness response.
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
        return JSONResponse(status_code=status_code, content=readiness_data)
    except Exception as e:
        log_info(f"[READINESS] Error during readiness check: {str(e)}")
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_readiness_router", resource_id=str(request.url)
        )
        status_code = error_response.get("status_code", 500)
        return JSONResponse(content=error_response, status_code=status_code)