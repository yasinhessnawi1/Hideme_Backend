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

# Create a rate limiter using the client's remote address.
limiter = Limiter(key_func=get_remote_address)

# Instantiate the API router.
router = APIRouter()

# Initialize an atomic status flag (if needed) for storing initialization status.
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
        response (Response): The outgoing HTTP response, used to set caching headers.

    Returns:
        JSONResponse: A JSON response containing status information, or a secure error response if an exception occurs.
    """
    try:
        # Set Cache-Control header for public caching with max-age from STATUS_CACHE_TTL.
        response.headers["Cache-Control"] = f"public, max-age={STATUS_CACHE_TTL}"
        # Set custom X-Cache-TTL header with STATUS_CACHE_TTL value.
        response.headers["X-Cache-TTL"] = str(STATUS_CACHE_TTL)
        # Define a cache key for the API status.
        cache_key = "api_status"
        # Attempt to retrieve a cached response using the cache key.
        cached_response = response_cache.get(cache_key)
        # If a cached response exists, return it immediately.
        if cached_response:
            return JSONResponse(content=cached_response)
        # Generate status data with current timestamp and API version.
        status_data = {
            "status": "success",
            "timestamp": time.time(),
            "api_version": os.environ.get("API_VERSION", "1.0.0")
        }
        # Cache the generated status data using the defined TTL.
        response_cache.set(cache_key, status_data, ttl=STATUS_CACHE_TTL)
        # Create a JSONResponse with the status data.
        resp = JSONResponse(content=status_data)
        # Set Cache-Control header on the response.
        resp.headers["Cache-Control"] = f"public, max-age={STATUS_CACHE_TTL}"
        # Set X-Cache-TTL header on the response.
        resp.headers["X-Cache-TTL"] = str(STATUS_CACHE_TTL)
        # Return the final JSONResponse.
        return resp
    except Exception as e:
        # Log the error encountered during status retrieval.
        log_info(f"[STATUS] Error retrieving status: {str(e)}")
        # Handle the exception securely using SecurityAwareErrorHandler.
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_status_router", resource_id=str(request.url)
        )
        # Retrieve the error status code, defaulting to 500 if not specified.
        status_code = error_response.get("status_code", 500)
        # Return a secure JSONResponse containing the error details.
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
        response (Response): The outgoing HTTP response for setting caching headers.

    Returns:
        JSONResponse: A JSON response with detailed health check information,
                      or a secure error response if an exception occurs.
    """
    try:
        # Set Cache-Control header for public caching with max-age from HEALTH_CACHE_TTL.
        response.headers["Cache-Control"] = f"public, max-age={HEALTH_CACHE_TTL}"
        # Set custom header X-Cache-TTL using HEALTH_CACHE_TTL.
        response.headers["X-Cache-TTL"] = str(HEALTH_CACHE_TTL)
        # Define a cache key for health check data.
        cache_key = "health_check"
        # Attempt to retrieve cached health check data.
        cached_response = response_cache.get(cache_key)
        # If cached health data exists, return it immediately.
        if cached_response:
            return JSONResponse(content=cached_response)
        # Gather process metrics using psutil.
        process = psutil.Process(os.getpid())
        process_info = {
            "cpu_percent": process.cpu_percent(),  # Get CPU usage percentage.
            "memory_percent": process.memory_percent(),  # Get memory usage percentage.
            "threads_count": threading.active_count(),  # Get count of active threads.
            "uptime": time.time() - process.create_time()  # Calculate process uptime.
        }
        # Retrieve memory statistics from the memory monitor.
        memory_stats = memory_monitor.get_memory_stats()
        # Retrieve cache statistics from response_cache.
        cache_stats = {
            "cache_size": len(response_cache.cache),
            "cached_endpoints": list(response_cache.cache.keys())[:5]  # Show up to first 5 keys.
        }
        # Build the health check data dictionary.
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
        # Optionally include debug information in non-production environments.
        environment = os.environ.get("ENVIRONMENT", "development")
        if environment != "production":
            health_data["debug"] = {
                "environment": environment,
                "python_version": os.environ.get("PYTHON_VERSION", "unknown"),
                "host": os.environ.get("HOSTNAME", "unknown")
            }
        # Cache the health check data using the defined TTL.
        response_cache.set(cache_key, health_data, ttl=HEALTH_CACHE_TTL)
        # Create a JSONResponse with the health data.
        resp = JSONResponse(content=jsonable_encoder(health_data))
        # Set Cache-Control header on the response.
        resp.headers["Cache-Control"] = f"public, max-age={HEALTH_CACHE_TTL}"
        # Set custom X-Cache-TTL header on the response.
        resp.headers["X-Cache-TTL"] = str(HEALTH_CACHE_TTL)
        # Return the final JSONResponse containing health check data.
        return resp
    except Exception as e:
        # Log any error encountered during the health check.
        log_info(f"[HEALTH] Error during health check: {str(e)}")
        # Securely handle the error using SecurityAwareErrorHandler.
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_health_router", resource_id=str(request.url)
        )
        # Retrieve the error status code, defaulting to 500.
        status_code = error_response.get("status_code", 500)
        # Return a JSONResponse containing the secure error response.
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
        response (Response): The outgoing HTTP response for setting caching headers.

    Returns:
        JSONResponse: A JSON response with performance metrics, or a secure error response if an exception occurs.
    """
    try:
        # Define a cache key for metrics data.
        cache_key = "api_metrics"
        # Set Cache-Control header for public caching with max-age from METRICS_CACHE_TTL.
        response.headers["Cache-Control"] = f"public, max-age={METRICS_CACHE_TTL}"
        # Set custom header X-Cache-TTL with METRICS_CACHE_TTL.
        response.headers["X-Cache-TTL"] = str(METRICS_CACHE_TTL)
        # Check for API key in request headers.
        api_key = request.headers.get("X-API-Key")
        # Retrieve the expected API key from environment variables.
        expected_key = os.environ.get("METRICS_API_KEY", "")
        # If an expected key is set and does not match the provided API key, return an error response.
        if expected_key and api_key != expected_key:
            return JSONResponse(
                status_code=403,
                content={"detail": "Unauthorized access to metrics endpoint"}
            )
        # Retrieve system memory statistics using psutil.
        system_memory = psutil.virtual_memory()
        # Retrieve system CPU usage percentage.
        system_cpu = psutil.cpu_percent(interval=0.1)
        # Retrieve process information using psutil.
        process = psutil.Process(os.getpid())
        process_info = {
            "cpu_percent": process.cpu_percent(),  # Get CPU usage of the process.
            "memory_rss": process.memory_info().rss,  # Get resident memory usage.
            "memory_percent": process.memory_percent(),  # Get memory percentage used by process.
            "threads_count": threading.active_count(),  # Count of active threads.
            "open_files": len(process.open_files()),  # Number of open files.
            "connections": len(process.connections())  # Number of open connections.
        }
        # Get additional memory monitoring statistics.
        memory_stats = memory_monitor.get_memory_stats()
        # Get cache statistics from the caching middleware.
        cache_stats = {
            "cache_size": len(response_cache.cache),
            "cache_keys": len(response_cache.access_times) if hasattr(response_cache, 'access_times') else 0
        }
        # Build the metrics data dictionary with timestamp, system metrics, process info, memory stats, and cache stats.
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
        # Cache the metrics data using the defined TTL.
        response_cache.set(cache_key, metrics_data, ttl=METRICS_CACHE_TTL)
        # Create a JSONResponse with the metrics data encoded as JSON.
        resp = JSONResponse(content=jsonable_encoder(metrics_data))
        # Set Cache-Control header on the response.
        resp.headers["Cache-Control"] = f"public, max-age={METRICS_CACHE_TTL}"
        # Set custom header X-Cache-TTL with the TTL value.
        resp.headers["X-Cache-TTL"] = str(METRICS_CACHE_TTL)
        # Log the metrics request along with the requesting client's IP address.
        log_info(f"[METRICS] Metrics requested by {request.client.host}")
        # Return the JSONResponse with performance metrics.
        return resp
    except Exception as e:
        # Log any error encountered during metrics retrieval.
        log_info(f"[METRICS] Error retrieving metrics: {str(e)}")
        # Securely handle the error using SecurityAwareErrorHandler.
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_metrics_router", resource_id=str(request.url)
        )
        # Retrieve the error status code from the error response.
        status_code = error_response.get("status_code", 500)
        # Return a JSONResponse with the secure error information.
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
        # Import the initialization service to check the current initialization status.
        from backend.app.services.initialization_service import initialization_service
        # Retrieve initialization status.
        init_status = initialization_service.get_initialization_status()
        # Determine if the Presidio service is initialized.
        is_ready = init_status.get("presidio", False)
        # Retrieve current memory usage percentage.
        memory_usage = memory_monitor.get_memory_usage()
        # Check whether memory usage is below the critical threshold.
        memory_ok = memory_usage < memory_monitor.critical_threshold
        # Set HTTP status code based on service readiness.
        status_code = 200 if is_ready and memory_ok else 503
        # Build the readiness check response data.
        readiness_data = {
            "ready": is_ready and memory_ok,
            "services": {
                "presidio_ready": init_status.get("presidio", False),
                "gemini_ready": init_status.get("gemini", False),
                "gliner_ready": init_status.get("gliner", False),
                "hideme_ready": init_status.get("hideme", False)
            },
            "memory": {
                "usage_percent": memory_usage,
                "status": "ok" if memory_ok else "critical"
            }
        }
        # Return a JSONResponse with the readiness data and corresponding status code.
        return JSONResponse(status_code=status_code, content=readiness_data)
    except Exception as e:
        # Log any error encountered during readiness check.
        log_info(f"[READINESS] Error during readiness check: {str(e)}")
        # Securely handle the error using SecurityAwareErrorHandler.
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_readiness_router", resource_id=str(request.url)
        )
        # Retrieve the error status code, defaulting to 500 if not specified.
        status_code = error_response.get("status_code", 500)
        # Return a JSONResponse with the secure error response.
        return JSONResponse(content=error_response, status_code=status_code)
