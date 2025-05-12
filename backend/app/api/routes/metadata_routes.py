"""
This module defines several API routers for entity detection and related functionalities.
Each router endpoint provides access to different aspects of the entity detection system,
such as retrieving available detection engines, available entity types, entity examples,
detector health status, and an overview of all API routes. In addition to the existing functionality,
detailed inline documentation has been added for clarity, and caching and rate-limiting mechanisms
are applied to enhance performance. This documentation provides comprehensive information about
the parameters, return types, and the sequence of operations within each endpoint method.
"""

from datetime import datetime
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.configs.gemini_config import GEMINI_AVAILABLE_ENTITIES
from backend.app.configs.gliner_config import GLINER_AVAILABLE_ENTITIES
from backend.app.configs.presidio_config import PRESIDIO_AVAILABLE_ENTITIES
from backend.app.configs.hideme_config import HIDEME_AVAILABLE_ENTITIES

from backend.app.entity_detection import EntityDetectionEngine
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.constant.constant import CACHE_TTL
from backend.app.utils.logging.logger import log_error
from backend.app.utils.security.caching_middleware import (
    get_cached_response,
    response_cache,
)
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.system_utils.synchronization_utils import (
    AsyncTimeoutLock,
    LockPriority,
)

# Create a rate limiter using the client's remote address.
limiter = Limiter(key_func=get_remote_address)

# Instantiate the API router.
router = APIRouter()

# Create an asynchronous lock for safe access of detector status.
_status_lock = AsyncTimeoutLock("detector_status_lock", priority=LockPriority.MEDIUM)


@router.get("/engines")
@limiter.limit("30/minute")
async def get_available_engines(request: Request, response: Response) -> JSONResponse:
    """
    Get the list of available entity detection engines with improved response time.

    Parameters:
        request (Request): The incoming HTTP request.
        response (Response): The HTTP response object to modify with caching headers.

    Returns:
        JSONResponse: A JSON response containing a list of available detection engine names.
        In case of an error, returns a JSON error response with the appropriate status code.
    """
    try:
        # Set Cache-Control header for engines endpoint using TTL from CACHE_TTL.
        response.headers["Cache-Control"] = f"public, max-age={CACHE_TTL['engines']}"
        # Set custom header X-Cache-TTL with the TTL value.
        response.headers["X-Cache-TTL"] = str(CACHE_TTL["engines"])
        # Define the cache key for storing engine data.
        cache_key = "engines_list"
        # Retrieve cached response if available.
        cached = get_cached_response(cache_key)
        # Return cached response if it exists.
        if cached:
            return JSONResponse(content=cached)
        # Create a dictionary of engines by enumerating the names of EntityDetectionEngine.
        engines_data = {"engines": [e.name for e in EntityDetectionEngine]}
        # Set the response in the cache with appropriate TTL.
        response_cache.set(cache_key, engines_data, CACHE_TTL["engines"])
        # Create a JSONResponse with the engines data.
        resp = JSONResponse(content=engines_data)
        # Set Cache-Control header on the new response.
        resp.headers["Cache-Control"] = f"public, max-age={CACHE_TTL['engines']}"
        # Set custom header X-Cache-TTL on the new response.
        resp.headers["X-Cache-TTL"] = str(CACHE_TTL["engines"])
        # Return the final response.
        return resp
    except Exception as e:
        # Log any error encountered during processing.
        log_error(f"[ERROR] Error retrieving available engines: {str(e)}")
        # Process the error using the security-aware error handler.
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_engines_router", resource_id=str(request.url)
        )
        # Extract the status code from the error response, default to 500.
        status = error_response.get("status_code", 500)
        # Return a JSON error response with the status code.
        return JSONResponse(content=error_response, status_code=status)


@router.get("/entities")
@limiter.limit("20/minute")
async def get_available_entities(request: Request, response: Response) -> JSONResponse:
    """
    Get the list of available entity types for detection with improved response time.

    Parameters:
        request (Request): The HTTP request instance.
        response (Response): The HTTP response instance to add caching headers.

    Returns:
        JSONResponse: A JSON response containing a dictionary with available entity types for each detection engine.
        In case of failure, returns a secured error response with a status code.
    """
    try:
        # Set Cache-Control header for the entities endpoint.
        response.headers["Cache-Control"] = f"public, max-age={CACHE_TTL['entities']}"
        # Set X-Cache-TTL header with TTL value.
        response.headers["X-Cache-TTL"] = str(CACHE_TTL["entities"])
        # Define cache key for the entities list.
        cache_key = "entities_list"
        # Retrieve cached response if available.
        cached = get_cached_response(cache_key)
        # Return the cached response if it exists.
        if cached:
            return JSONResponse(content=cached)
        # Construct entities_data dictionary with available entities for each detection engine.
        entities_data = {
            "presidio_entities": PRESIDIO_AVAILABLE_ENTITIES,
            "gemini_entities": GEMINI_AVAILABLE_ENTITIES,
            "gliner_entities": GLINER_AVAILABLE_ENTITIES,
            "hideme_entities": HIDEME_AVAILABLE_ENTITIES,
        }
        # Cache the entities data with TTL.
        response_cache.set(cache_key, entities_data, CACHE_TTL["entities"])
        # Create a JSONResponse with the entities data.
        resp = JSONResponse(content=entities_data)
        # Set Cache-Control header on the response.
        resp.headers["Cache-Control"] = f"public, max-age={CACHE_TTL['entities']}"
        # Set X-Cache-TTL header on the response.
        resp.headers["X-Cache-TTL"] = str(CACHE_TTL["entities"])
        # Return the final response.
        return resp
    except Exception as e:
        # Log any encountered error during the entities retrieval.
        log_error(f"[ERROR] Error retrieving available entities: {str(e)}")
        # Handle the error in a security-aware fashion.
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_entities_router", resource_id=str(request.url)
        )
        # Get the status code from the error response, default to 500.
        status = error_response.get("status_code", 500)
        # Return a JSON error response with the proper status code.
        return JSONResponse(content=error_response, status_code=status)


@router.get("/entity-examples")
@limiter.limit("30/minute")
async def get_entity_examples(request: Request, response: Response) -> JSONResponse:
    """
    Get examples for different entity types with improved response time.

    Parameters:
        request (Request): The HTTP request object.
        response (Response): The HTTP response object to add caching headers.

    Returns:
        JSONResponse: A JSON response containing a dictionary of example values for each entity type.
        In case of an error, returns a secured error response with an appropriate status code.
    """
    try:
        # Set the Cache-Control header with TTL for entity examples.
        response.headers["Cache-Control"] = (
            f"public, max-age={CACHE_TTL['entity_examples']}"
        )
        # Set X-Cache-TTL header with TTL value for entity examples.
        response.headers["X-Cache-TTL"] = str(CACHE_TTL["entity_examples"])
        # Define cache key for entity examples.
        cache_key = "entity_examples"
        # Retrieve cached example data if available.
        cached = get_cached_response(cache_key)
        # Return cached data if it exists.
        if cached:
            return JSONResponse(content=cached)
        # Construct a dictionary of entity examples.
        examples_data = {
            "examples": {
                "PERSON": ["John Doe", "Jane Smith", "Dr. Robert Johnson"],
                "EMAIL_ADDRESS": ["john.doe@example.com", "contact@company.org"],
                "PHONE_NUMBER": ["+1 (555) 123-4567", "555-987-6543"],
                "CREDIT_CARD": ["4111 1111 1111 1111", "5500 0000 0000 0004"],
                "ADDRESS": [
                    "123 Main St, Anytown, CA 12345",
                    "456 Park Avenue, Suite 789",
                ],
                "DATE": ["January 15, 2023", "05/10/1985"],
                "US_SSN": ["123-45-6789", "987-65-4321"],
                "LOCATION": ["New York City", "Paris, France", "Tokyo"],
                "ORGANIZATION": [
                    "Acme Corporation",
                    "United Nations",
                    "Stanford University",
                ],
            }
        }
        # Cache the examples data with its TTL.
        response_cache.set(cache_key, examples_data, CACHE_TTL["entity_examples"])
        # Create a JSON response with the entity examples data.
        resp = JSONResponse(content=examples_data)
        # Set Cache-Control header on the response.
        resp.headers["Cache-Control"] = (
            f"public, max-age={CACHE_TTL['entity_examples']}"
        )
        # Set X-Cache-TTL header on the response.
        resp.headers["X-Cache-TTL"] = str(CACHE_TTL["entity_examples"])
        # Return the finalized JSON response.
        return resp
    except Exception as e:
        # Log the error if fetching examples fails.
        log_error(f"[ERROR] Error retrieving entity examples: {str(e)}")
        # Handle the error securely using the error handler.
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_entity_example_router", resource_id=str(request.url)
        )
        # Retrieve the status code from the error response.
        status = error_response.get("status_code", 500)
        # Return an error JSON response with the appropriate status code.
        return JSONResponse(content=error_response, status_code=status)


@router.get("/detectors-status")
@limiter.limit("10/minute")
async def get_detectors_status(request: Request, response: Response) -> JSONResponse:
    """
    Get status information for all cached entity detectors.

    Parameters:
        request (Request): The incoming HTTP request.
        response (Response): The response object that will have additional headers for caching.

    Returns:
        JSONResponse: A JSON response containing the status and usage metrics for each detection engine.
        In case of an error, returns a JSON error response with an appropriate status code.
    """
    try:
        # Set X-Cache-TTL header for the detector status endpoint.
        response.headers["X-Cache-TTL"] = str(CACHE_TTL["detector_status"])
        # Get the current date and time in ISO format.
        last_updated = datetime.isoformat(datetime.now())
        # Check the overall health of all detectors.
        detector_health = initialization_service.check_health()
        # Retrieve usage metrics for each detector.
        detector_metrics = initialization_service.get_usage_metrics()
        # Initialize detectors_status dictionary with placeholders for each detector.
        detectors_status = {
            "presidio": {},
            "gemini": {},
            "gliner": {},
            "hideme": {},
            "_meta": {
                "last_updated": last_updated,
                "cache_ttl": CACHE_TTL["detector_status"],
            },
        }
        # Acquire an asynchronous lock with a timeout to prevent race conditions.
        async with _status_lock.acquire_timeout(timeout=2.0):
            # Get the Presidio detector instance.
            presidio_detector = initialization_service.get_detector(
                EntityDetectionEngine.PRESIDIO
            )
            # Update detectors_status for Presidio using its get_status method if available.
            detectors_status["presidio"] = (
                presidio_detector.get_status()
                if hasattr(presidio_detector, "get_status")
                else {
                    "initialized": detector_health["detectors"]["presidio"],
                    "uses": detector_metrics.get("presidio", {}).get("uses", 0),
                }
            )
            # Get the Gemini detector instance.
            gemini_detector = initialization_service.get_gemini_detector()
            # Update detectors_status for Gemini using its get_status method if available.
            detectors_status["gemini"] = (
                gemini_detector.get_status()
                if hasattr(gemini_detector, "get_status")
                else {
                    "initialized": detector_health["detectors"]["gemini"],
                    "uses": detector_metrics.get("gemini", {}).get("uses", 0),
                }
            )
            # Get the GLiNER detector instance.
            gliner_detector = initialization_service.get_gliner_detector()
            # Update detectors_status for GLiNER using its get_status method if available.
            detectors_status["gliner"] = (
                gliner_detector.get_status()
                if hasattr(gliner_detector, "get_status")
                else {
                    "initialized": detector_health["detectors"]["gliner"],
                    "uses": detector_metrics.get("gliner", {}).get("uses", 0),
                }
            )
            # Get the HIDEME detector instance.
            hideme_detector = initialization_service.get_hideme_detector()
            # Update detectors_status for HIDEME using its get_status method if available.
            detectors_status["hideme"] = (
                hideme_detector.get_status()
                if hasattr(hideme_detector, "get_status")
                else {
                    "initialized": detector_health["detectors"]["hideme"],
                    "uses": detector_metrics.get("hideme", {}).get("uses", 0),
                }
            )
        # Cache the detectors status data.
        response_cache.set(
            "detectors_status", detectors_status, CACHE_TTL["detector_status"]
        )
        # Create a JSONResponse with the detectors status.
        resp = JSONResponse(content=detectors_status)
        # Set X-Cache-TTL header on the response.
        resp.headers["X-Cache-TTL"] = str(CACHE_TTL["detector_status"])
        # Return the final JSON response.
        return resp
    except Exception as e:
        # Log the error if fetching detectors status fails.
        log_error(f"[ERROR] Error retrieving detector status: {str(e)}")
        # Handle the error in a security-aware manner.
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_status_metadata_router", resource_id=str(request.url)
        )
        # Extract the status code from the error response.
        status = error_response.get("status_code", 500)
        # Return an error JSON response with the determined status.
        return JSONResponse(content=error_response, status_code=status)


@router.get("/routes")
async def get_api_routes(request: Request, response: Response) -> JSONResponse:
    """
    Provide a comprehensive overview of all available API routes.

    Parameters:
        request (Request): The incoming HTTP request instance.
        response (Response): The response instance to add caching headers.

    Returns:
        JSONResponse: A JSON response containing detailed information about each API route including path,
                      method, description, and the associated detection engine if applicable.
                      In case of failure, returns a secured JSON error response with an appropriate status code.
    """
    try:
        # Set Cache-Control header for the API routes endpoint.
        response.headers["Cache-Control"] = f"public, max-age={CACHE_TTL['engines']}"
        # Set X-Cache-TTL header using TTL for the engines.
        response.headers["X-Cache-TTL"] = str(CACHE_TTL["engines"])
        # Define the routes information with various sections.
        routes_info = {
            "entity_detection": [
                {
                    "path": "/ml/detect",
                    "method": "POST",
                    "description": "Presidio entity detection",
                    "engine": "Presidio",
                },
                {
                    "path": "/ml/gl_detect",
                    "method": "POST",
                    "description": "GLiNER entity detection",
                    "engine": "GLiNER",
                },
                {
                    "path": "/ai/detect",
                    "method": "POST",
                    "description": "Gemini AI entity detection",
                    "engine": "Gemini",
                },
                {
                    "path": "/ml/hm_detect",
                    "method": "POST",
                    "description": "HIDEME entity detection",
                    "engine": "HIDEME",
                },
            ],
            "batch_processing": [
                {
                    "path": "/batch/detect",
                    "method": "POST",
                    "description": "Batch sensitive data detection using one detection engine",
                },
                {
                    "path": "/batch/hybrid_detect",
                    "method": "POST",
                    "description": "Hybrid batch detection across multiple engines",
                },
                {
                    "path": "/batch/search",
                    "method": "POST",
                    "description": "Batch text search in multiple files",
                },
                {
                    "path": "/batch/find_words",
                    "method": "POST",
                    "description": "Batch find words in PDF files based on bounding box",
                },
                {
                    "path": "/batch/redact",
                    "method": "POST",
                    "description": "Batch document redaction returning a ZIP file",
                },
            ],
            "pdf_processing": [
                {
                    "path": "/pdf/redact",
                    "method": "POST",
                    "description": "PDF document redaction",
                },
                {
                    "path": "/pdf/extract",
                    "method": "POST",
                    "description": "PDF text extraction",
                },
            ],
            "metadata": [
                {
                    "path": "/help/engines",
                    "method": "GET",
                    "description": "List available detection engines",
                },
                {
                    "path": "/help/entities",
                    "method": "GET",
                    "description": "List available entity types",
                },
                {
                    "path": "/help/entity-examples",
                    "method": "GET",
                    "description": "Get examples of different entity types",
                },
                {
                    "path": "/help/detectors-status",
                    "method": "GET",
                    "description": "Get status of detection engines",
                },
                {
                    "path": "/help/routes",
                    "method": "GET",
                    "description": "Comprehensive overview of API routes",
                },
            ],
            "system": [
                {"path": "/status", "method": "GET", "description": "Basic API status"},
                {
                    "path": "/health",
                    "method": "GET",
                    "description": "Detailed health check",
                },
                {
                    "path": "/metrics",
                    "method": "GET",
                    "description": "Performance metrics",
                },
                {
                    "path": "/readiness",
                    "method": "GET",
                    "description": "Service readiness check",
                },
            ],
        }
        # Define the cache key for API routes information.
        cache_key = "api_routes"
        # Cache the routes info using TTL value.
        response_cache.set(cache_key, routes_info, CACHE_TTL["engines"])
        # Create a JSONResponse with the routes information.
        resp = JSONResponse(content=routes_info)
        # Set Cache-Control header on the response.
        resp.headers["Cache-Control"] = f"public, max-age={CACHE_TTL['engines']}"
        # Set X-Cache-TTL header on the response.
        resp.headers["X-Cache-TTL"] = str(CACHE_TTL["engines"])
        # Return the final JSON response containing API routes details.
        return resp
    except Exception as e:
        # Log any error encountered when retrieving API routes.
        log_error(f"[ERROR] Error retrieving API routes: {str(e)}")
        # Handle the error securely with the error handler.
        error_response = SecurityAwareErrorHandler.handle_safe_error(
            e, "api_routes", resource_id=str(request.url)
        )
        # Retrieve the status code from the error response.
        status = error_response.get("status_code", 500)
        # Return an error JSON response with the determined status code.
        return JSONResponse(content=error_response, status_code=status)
