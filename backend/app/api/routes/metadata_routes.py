"""
This module provides endpoints that return metadata and configuration data with response caching for improved performance.
It exposes endpoints to retrieve available detection engines, entity lists, sample entity examples, detector statuses,
and the API routes. Static responses are cached to improve response times, and all endpoints are secured with robust
error handling through SecurityAwareErrorHandler. This module is designed to aid developers by providing clear and
detailed information about the current state and configuration of the detection system.
"""

from datetime import datetime
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from backend.app.configs.gemini_config import GEMINI_AVAILABLE_ENTITIES
from backend.app.configs.gliner_config import GLINER_AVAILABLE_ENTITIES
from backend.app.configs.presidio_config import PRESIDIO_AVAILABLE_ENTITIES
from backend.app.entity_detection import EntityDetectionEngine
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.constant.constant import CACHE_TTL
from backend.app.utils.logging.logger import log_error
from backend.app.utils.security.caching_middleware import get_cached_response, response_cache
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.system_utils.synchronization_utils import AsyncTimeoutLock, LockPriority

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

    This endpoint returns a static list of available detection engines by enumerating the
    members of the EntityDetectionEngine enum. The response is cached for 24 hours to optimize performance.

    Parameters:
        request (Request): The incoming HTTP request.
        response (Response): The outgoing HTTP response, used to set caching headers.

    Returns:
        JSONResponse: A JSON response containing the list of available detection engines,
                      or a secure error response if an exception occurs.
    """
    try:
        # Set the Cache-Control header with a public caching policy and max-age based on CACHE_TTL.
        response.headers["Cache-Control"] = f"public, max-age={CACHE_TTL['engines']}"
        # Set a custom header 'X-Cache-TTL' with the TTL value.
        response.headers["X-Cache-TTL"] = str(CACHE_TTL["engines"])
        # Define a cache key for storing the engines list.
        cache_key = "engines_list"
        # Attempt to retrieve the engines list from the cache.
        cached = get_cached_response(cache_key)
        # If the cache contains data, return it immediately.
        if cached:
            return JSONResponse(content=cached)
        # Generate engines data by enumerating all available engines from the EntityDetectionEngine enum.
        engines_data = {"engines": [e.name for e in EntityDetectionEngine]}
        # Cache the generated engines data using the defined TTL.
        response_cache.set(cache_key, engines_data, CACHE_TTL["engines"])
        # Create a JSONResponse with the engine's data.
        resp = JSONResponse(content=engines_data)
        # Set the Cache-Control header in the response.
        resp.headers["Cache-Control"] = f"public, max-age={CACHE_TTL['engines']}"
        # Set the X-Cache-TTL header in the response.
        resp.headers["X-Cache-TTL"] = str(CACHE_TTL["engines"])
        # Return the JSON response.
        return resp
    except Exception as e:
        # Log the error if an exception is raised.
        log_error(f"[ERROR] Error retrieving available engines: {str(e)}")
        # Securely handle the error using SecurityAwareErrorHandler.
        error_response = SecurityAwareErrorHandler.handle_safe_error(e, "api_engines_router",
                                                                     resource_id=str(request.url))
        # Get the error status code, defaulting to 500 if not specified.
        status = error_response.get("status_code", 500)
        # Return a JSONResponse containing the secure error information.
        return JSONResponse(content=error_response, status_code=status)


@router.get("/entities")
@limiter.limit("20/minute")
async def get_available_entities(request: Request, response: Response) -> JSONResponse:
    """
    Get the list of available entity types for detection with improved response time.

    This endpoint returns a dictionary containing the available entity types for each detection engine.
    The response is cached for 1 hour to enhance performance. Any errors during retrieval are handled
    securely with a sanitized error response.

    Parameters:
        request (Request): The incoming HTTP request.
        response (Response): The outgoing HTTP response, used to set caching headers.

    Returns:
        JSONResponse: A JSON response with available entity types or a secure error response.
    """
    try:
        # Set Cache-Control header with a 1-hour max-age based on CACHE_TTL.
        response.headers["Cache-Control"] = f"public, max-age={CACHE_TTL['entities']}"
        # Set a custom header 'X-Cache-TTL' with the TTL for entities.
        response.headers["X-Cache-TTL"] = str(CACHE_TTL["entities"])
        # Define a cache key for the entities list.
        cache_key = "entities_list"
        # Retrieve cached entities if available.
        cached = get_cached_response(cache_key)
        # If cached data exists, return it immediately.
        if cached:
            return JSONResponse(content=cached)
        # Retrieve GLiNER entities from configuration.
        gliner_entities = GLINER_AVAILABLE_ENTITIES
        # Build a dictionary containing entity lists for Presidio, Gemini, and GLiNER.
        entities_data = {
            "presidio_entities": PRESIDIO_AVAILABLE_ENTITIES,
            "gemini_entities": GEMINI_AVAILABLE_ENTITIES,
            "gliner_entities": gliner_entities
        }
        # Cache the entities data with the defined TTL.
        response_cache.set(cache_key, entities_data, CACHE_TTL["entities"])
        # Create a JSONResponse with the entity's data.
        resp = JSONResponse(content=entities_data)
        # Set the Cache-Control header in the response.
        resp.headers["Cache-Control"] = f"public, max-age={CACHE_TTL['entities']}"
        # Set the X-Cache-TTL header in the response.
        resp.headers["X-Cache-TTL"] = str(CACHE_TTL["entities"])
        # Return the JSON response.
        return resp
    except Exception as e:
        # Log the error if an exception is raised.
        log_error(f"[ERROR] Error retrieving available entities: {str(e)}")
        # Securely handle the exception.
        error_response = SecurityAwareErrorHandler.handle_safe_error(e, "api_entities_router",
                                                                     resource_id=str(request.url))
        # Get the status code, defaulting to 500.
        status = error_response.get("status_code", 500)
        # Return a JSONResponse with the error information.
        return JSONResponse(content=error_response, status_code=status)


@router.get("/entity-examples")
@limiter.limit("30/minute")
async def get_entity_examples(request: Request, response: Response) -> JSONResponse:
    """
    Get examples for different entity types with improved response time.

    This endpoint returns a static dictionary of example values for each entity type.
    The data is cached for 24 hours, allowing for fast responses. If cached data exists,
    it is returned immediately.

    Parameters:
        request (Request): The incoming HTTP request.
        response (Response): The outgoing HTTP response, used to set caching headers.

    Returns:
        JSONResponse: A JSON response containing example texts for various entity types,
                      or a secure error response if an exception occurs.
    """
    try:
        # Set Cache-Control header for a 24-hour cache using CACHE_TTL.
        response.headers["Cache-Control"] = f"public, max-age={CACHE_TTL['entity_examples']}"
        # Set the custom header X-Cache-TTL with the TTL for entity examples.
        response.headers["X-Cache-TTL"] = str(CACHE_TTL["entity_examples"])
        # Define a cache key for the entity examples.
        cache_key = "entity_examples"
        # Attempt to retrieve cached examples.
        cached = get_cached_response(cache_key)
        # If cached examples exist, return them.
        if cached:
            return JSONResponse(content=cached)
        # Define static example data for various entity types.
        examples_data = {
            "examples": {
                "PERSON": ["John Doe", "Jane Smith", "Dr. Robert Johnson"],
                "EMAIL_ADDRESS": ["john.doe@example.com", "contact@company.org"],
                "PHONE_NUMBER": ["+1 (555) 123-4567", "555-987-6543"],
                "CREDIT_CARD": ["4111 1111 1111 1111", "5500 0000 0000 0004"],
                "ADDRESS": ["123 Main St, Anytown, CA 12345", "456 Park Avenue, Suite 789"],
                "DATE": ["January 15, 2023", "05/10/1985"],
                "US_SSN": ["123-45-6789", "987-65-4321"],
                "LOCATION": ["New York City", "Paris, France", "Tokyo"],
                "ORGANIZATION": ["Acme Corporation", "United Nations", "Stanford University"]
            }
        }
        # Cache the example's data.
        response_cache.set(cache_key, examples_data, CACHE_TTL["entity_examples"])
        # Create a JSONResponse with the example's data.
        resp = JSONResponse(content=examples_data)
        # Set the Cache-Control header for the response.
        resp.headers["Cache-Control"] = f"public, max-age={CACHE_TTL['entity_examples']}"
        # Set the X-Cache-TTL header for the response.
        resp.headers["X-Cache-TTL"] = str(CACHE_TTL["engines"])
        # Return the JSONResponse containing the entity examples.
        return resp
    except Exception as e:
        # Log any errors encountered.
        log_error(f"[ERROR] Error retrieving entity examples: {str(e)}")
        # Securely handle the exception.
        error_response = SecurityAwareErrorHandler.handle_safe_error(e, "api_entity_example_router",
                                                                     resource_id=str(request.url))
        # Get the status code, defaulting to 500 if necessary.
        status = error_response.get("status_code", 500)
        # Return a JSONResponse with the error details.
        return JSONResponse(content=error_response, status_code=status)


@router.get("/detectors-status")
@limiter.limit("10/minute")
async def get_detectors_status(request: Request, response: Response) -> JSONResponse:
    """
    Get status information for all cached entity detectors.

    This endpoint returns the current status and usage metrics for each detector instance.
    It uses an AsyncTimeoutLock to safely access active detector instances and sets a custom TTL header.
    In case of errors, a secure error response is returned.

    Parameters:
        request (Request): The incoming HTTP request.
        response (Response): The outgoing HTTP response, used to set custom TTL headers.

    Returns:
        JSONResponse: A JSON response containing status and metrics for each detector,
                      or a secure error response if an exception occurs.
    """
    try:
        # Set the custom header X-Cache-TTL with the detector status TTL.
        response.headers["X-Cache-TTL"] = str(CACHE_TTL["detector_status"])
        # Get the current time in ISO format.
        last_updated = datetime.isoformat(datetime.now())
        # Retrieve overall detector health status.
        detector_health = initialization_service.check_health()
        # Retrieve usage metrics for detectors.
        detector_metrics = initialization_service.get_usage_metrics()
        # Initialize a dictionary to store status for each detector and metadata.
        detectors_status = {
            "presidio": {},
            "gemini": {},
            "gliner": {},
            "_meta": {
                "last_updated": last_updated,
                "cache_ttl": CACHE_TTL["detector_status"]
            }
        }
        # Acquire the asynchronous lock to ensure safe access to detector instances.
        async with _status_lock.acquire_timeout(timeout=2.0):
            # Retrieve the Presidio detector.
            presidio_detector = initialization_service.get_detector(EntityDetectionEngine.PRESIDIO)
            # Set the Presidio detector status.
            detectors_status["presidio"] = (presidio_detector.get_status() if hasattr(presidio_detector, 'get_status')
                                            else {"initialized": detector_health["detectors"]["presidio"],
                                                  "uses": detector_metrics.get("presidio", {}).get("uses", 0)})
            # Retrieve the Gemini detector.
            gemini_detector = initialization_service.get_gemini_detector()
            # Set the Gemini detector status.
            detectors_status["gemini"] = (gemini_detector.get_status() if hasattr(gemini_detector, 'get_status')
                                          else {"initialized": detector_health["detectors"]["gemini"],
                                                "uses": detector_metrics.get("gemini", {}).get("uses", 0)})
            # Retrieve the GLiNER detector.
            gliner_detector = initialization_service.get_gliner_detector()
            # Set the GLiNER detector status.
            detectors_status["gliner"] = (gliner_detector.get_status() if hasattr(gliner_detector, 'get_status')
                                          else {"initialized": detector_health["detectors"]["gliner"],
                                                "uses": detector_metrics.get("gliner", {}).get("uses", 0)})
        # Cache the detectors status data with the defined TTL.
        response_cache.set("detectors_status", detectors_status, CACHE_TTL["detector_status"])
        # Create a JSONResponse with the detectors status data.
        resp = JSONResponse(content=detectors_status)
        # Set the X-Cache-TTL header for the response.
        resp.headers["X-Cache-TTL"] = str(CACHE_TTL["detector_status"])
        # Return the detectors status JSON response.
        return resp
    except Exception as e:
        # Log any exception encountered.
        log_error(f"[ERROR] Error retrieving detector status: {str(e)}")
        # Securely handle the error.
        error_response = SecurityAwareErrorHandler.handle_safe_error(e, "api_status_metadata_router",
                                                                     resource_id=str(request.url))
        # Get the status code.
        status = error_response.get("status_code", 500)
        # Return a JSONResponse with the error details.
        return JSONResponse(content=error_response, status_code=status)


@router.get("/routes")
async def get_api_routes(request: Request, response: Response) -> JSONResponse:
    """
    Provide a comprehensive overview of all available API routes.

    This endpoint returns detailed information on each API route, including path, method, description,
    and related detection engine if applicable. The response is cached for a period defined for engines.

    Parameters:
        request (Request): The incoming HTTP request.
        response (Response): The outgoing HTTP response, used to set caching headers.

    Returns:
        JSONResponse: A JSON response containing detailed API route information,
                      or a secure error response if an exception occurs.
    """
    try:
        # Set Cache-Control header to use public caching with a TTL based on CACHE_TTL for engines.
        response.headers["Cache-Control"] = f"public, max-age={CACHE_TTL['engines']}"
        # Set a custom header with the cache TTL.
        response.headers["X-Cache-TTL"] = str(CACHE_TTL["engines"])
        # Define a dictionary with detailed information for each API route category.
        routes_info = {
            "entity_detection": [
                {"path": "/ml/detect", "method": "POST", "description": "Presidio entity detection",
                 "engine": "Presidio"},
                {"path": "/ml/gl_detect", "method": "POST", "description": "GLiNER entity detection",
                 "engine": "GLiNER"},
                {"path": "/ai/detect", "method": "POST", "description": "Gemini AI entity detection",
                 "engine": "Gemini"}
            ],
            "batch_processing": [
                {"path": "/batch/detect", "method": "POST", "description": "Batch entity detection"},
                {"path": "/batch/redact", "method": "POST", "description": "Batch document redaction"},
                {"path": "/batch/hybrid_detect", "method": "POST",
                 "description": "Hybrid batch detection across multiple engines"},
                {"path": "/batch/extract", "method": "POST", "description": "Batch text extraction"}
            ],
            "pdf_processing": [
                {"path": "/pdf/redact", "method": "POST", "description": "PDF document redaction"},
                {"path": "/pdf/extract", "method": "POST", "description": "PDF text extraction"}
            ],
            "metadata": [
                {"path": "/help/engines", "method": "GET", "description": "List available detection engines"},
                {"path": "/help/entities", "method": "GET", "description": "List available entity types"},
                {"path": "/help/entity-examples", "method": "GET",
                 "description": "Get examples of different entity types"},
                {"path": "/help/detectors-status", "method": "GET", "description": "Get status of detection engines"},
                {"path": "/help/routes", "method": "GET", "description": "Comprehensive overview of API routes"}
            ],
            "system": [
                {"path": "/status", "method": "GET", "description": "Basic API status"},
                {"path": "/health", "method": "GET", "description": "Detailed health check"},
                {"path": "/metrics", "method": "GET", "description": "Performance metrics"},
                {"path": "/readiness", "method": "GET", "description": "Service readiness check"}
            ]
        }
        # Define a cache key for the API routes.
        cache_key = "api_routes"
        # Cache the routes information using the defined TTL.
        response_cache.set(cache_key, routes_info, CACHE_TTL["engines"])
        # Create a JSONResponse with the route's information.
        resp = JSONResponse(content=routes_info)
        # Set the Cache-Control header on the response.
        resp.headers["Cache-Control"] = f"public, max-age={CACHE_TTL['engines']}"
        # Set a custom X-Cache-TTL header on the response.
        resp.headers["X-Cache-TTL"] = str(CACHE_TTL["engines"])
        # Return the JSONResponse with the detailed API routes.
        return resp
    except Exception as e:
        # Log an error if an exception occurs while retrieving API routes.
        log_error(f"[ERROR] Error retrieving API routes: {str(e)}")
        # Securely handle the exception.
        error_response = SecurityAwareErrorHandler.handle_safe_error(e, "api_routes", resource_id=str(request.url))
        # Retrieve the status code from the error response.
        status = error_response.get("status_code", 500)
        # Return a JSONResponse with the secure error information.
        return JSONResponse(content=error_response, status_code=status)
