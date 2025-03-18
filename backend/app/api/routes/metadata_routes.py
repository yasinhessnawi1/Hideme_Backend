"""
Metadata and configuration endpoints with response caching for improved performance.
"""
from datetime import datetime

from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.configs.gemini_config import AVAILABLE_ENTITIES
from backend.app.configs.gliner_config import GLINER_ENTITIES
from backend.app.configs.presidio_config import REQUESTED_ENTITIES
from backend.app.factory.document_processing_factory import EntityDetectionEngine
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.caching_middleware import get_cached_response, response_cache
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.logger import log_error
from backend.app.utils.synchronization_utils import AsyncTimeoutLock, LockPriority

# Configure rate limiter
limiter = Limiter(key_func=get_remote_address)

# Cache TTL configuration (in seconds)
CACHE_TTL = {
    "engines": 86400,  # 24 hours for static configuration
    "entities": 3600,  # 1 hour for entity lists
    "entity_examples": 86400,  # 24 hours for static examples
    "detector_status": 60  # 1 minute for detector status
}

router = APIRouter()

# Keep only the AsyncTimeoutLock for detector status as it accesses active instances
_status_lock = AsyncTimeoutLock("detector_status_lock", priority=LockPriority.MEDIUM)


@router.get("/engines")
@limiter.limit("30/minute")
async def get_available_engines(request: Request, response: Response):
    """
    Get list of available entity detection engines with improved response time.

    Returns:
        List of available entity detection engines
    """
    # Set cache control header
    response.headers["Cache-Control"] = f"public, max-age={CACHE_TTL['engines']}"

    # This is a static response, so it's suitable for caching
    cache_key = "engines_list"
    cached = get_cached_response(cache_key)
    if cached:
        return JSONResponse(content=cached)

    # No need for locks with static data
    engines_data = {
        "engines": [e.name for e in EntityDetectionEngine]
    }

    # Cache the result
    response_cache.set(cache_key, engines_data, CACHE_TTL["engines"])

    return engines_data


@router.get("/entities")
@limiter.limit("20/minute")
async def get_available_entities(request: Request, response: Response):
    """
    Get list of available entity types for detection with improved response time.

    Returns:
        Dictionary of available entity types by detection engine
    """
    try:
        # Set cache control header
        response.headers["Cache-Control"] = f"public, max-age={CACHE_TTL['entities']}"

        # Check cache
        cache_key = "entities_list"
        cached = get_cached_response(cache_key)
        if cached:
            return JSONResponse(content=cached)

        # No need for locks with static configuration data
        # Get GLiNER entities
        gliner_entities = GLINER_ENTITIES

        entities_data = {
            "presidio_entities": REQUESTED_ENTITIES,
            "gemini_entities": AVAILABLE_ENTITIES,
            "gliner_entities": gliner_entities
        }

        # Cache the result
        response_cache.set(cache_key, entities_data, CACHE_TTL["entities"])

        return entities_data

    except Exception as e:
        # Use security-aware error handling
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "metadata_retrieval", 500
        )
        log_error(f"[ERROR] Error retrieving available entities: {str(e)}")
        return JSONResponse(status_code=status_code, content=error_response)


@router.get("/entity-examples")
@limiter.limit("30/minute")
async def get_entity_examples(request: Request, response: Response):
    """
    Get examples for different entity types with improved response time.

    Returns:
        Dictionary of example text for each entity type
    """
    # Set cache control header
    response.headers["Cache-Control"] = f"public, max-age={CACHE_TTL['entity_examples']}"

    # This is a static response, so it's suitable for caching
    cache_key = "entity_examples"
    cached = get_cached_response(cache_key)
    if cached:
        return JSONResponse(content=cached)

    # No need for locks with static example data
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

    # Cache the result
    response_cache.set(cache_key, examples_data, CACHE_TTL["entity_examples"])

    return examples_data


@router.get("/detectors-status")
@limiter.limit("10/minute")
async def get_detectors_status(request: Request):
    """
    Get status information for all cached entity detectors.

    Returns:
        Status information for all detector instances
    """
    try:
        # This endpoint should not be cached for too long as status changes frequently
        cache_key = "detectors_status"
        last_updated = datetime.isoformat(datetime.now())

        # Get status from initialization service
        detector_health = initialization_service.check_health()
        detector_metrics = initialization_service.get_usage_metrics()

        # Try to get detailed status from each detector
        detectors_status = {
            "presidio": {},
            "gemini": {},
            "gliner": {},
            "_meta": {
                "last_updated": last_updated,
                "cache_ttl": CACHE_TTL["detector_status"]
            }
        }

        # Keep the AsyncTimeoutLock for detector status as it accesses active instances
        async with _status_lock.acquire_timeout(timeout=2.0):
            # Presidio
            presidio_detector = initialization_service.get_detector(EntityDetectionEngine.PRESIDIO)
            detectors_status["presidio"] = (
                presidio_detector.get_status() if hasattr(presidio_detector, 'get_status')
                else {
                    "initialized": detector_health["detectors"]["presidio"],
                    "uses": detector_metrics.get("presidio", {}).get("uses", 0)
                }
            )

            # Gemini
            gemini_detector = initialization_service.get_gemini_detector()
            detectors_status["gemini"] = (
                gemini_detector.get_status() if hasattr(gemini_detector, 'get_status')
                else {
                    "initialized": detector_health["detectors"]["gemini"],
                    "uses": detector_metrics.get("gemini", {}).get("uses", 0)
                }
            )

            # GLiNER
            gliner_detector = initialization_service.get_gliner_detector()
            detectors_status["gliner"] = (
                gliner_detector.get_status() if hasattr(gliner_detector, 'get_status')
                else {
                    "initialized": detector_health["detectors"]["gliner"],
                    "uses": detector_metrics.get("gliner", {}).get("uses", 0)
                }
            )

        return detectors_status

    except Exception as e:
        log_error(f"[ERROR] Error retrieving detector status: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving detector status")


@router.get("/routes")
async def get_api_routes() -> JSONResponse:
    """
    Provide a comprehensive overview of all available API routes.

    Returns:
        JSON response with detailed route information
    """
    # No need for locks with static route information
    routes_info = {
        "entity_detection": [
            {
                "path": "/hybrid/detect",
                "method": "POST",
                "description": "Hybrid entity detection across multiple engines",
                "engines": ["Presidio", "Gemini", "GLiNER"]
            },
            {
                "path": "/ml/detect",
                "method": "POST",
                "description": "Presidio entity detection",
                "engine": "Presidio"
            },
            {
                "path": "/ml/gl_detect",
                "method": "POST",
                "description": "GLiNER entity detection",
                "engine": "GLiNER"
            },
            {
                "path": "/ai/detect",
                "method": "POST",
                "description": "Gemini AI entity detection",
                "engine": "Gemini"
            }
        ],
        "batch_processing": [
            {
                "path": "/batch/detect",
                "method": "POST",
                "description": "Batch entity detection"
            },
            {
                "path": "/batch/redact",
                "method": "POST",
                "description": "Batch document redaction"
            },
            {
                "path": "/batch/hybrid_detect",
                "method": "POST",
                "description": "Hybrid batch detection across multiple engines"
            },
            {
                "path": "/batch/extract",
                "method": "POST",
                "description": "Batch text extraction"
            }
        ],
        "pdf_processing": [
            {
                "path": "/pdf/redact",
                "method": "POST",
                "description": "PDF document redaction"
            },
            {
                "path": "/pdf/extract",
                "method": "POST",
                "description": "PDF text extraction"
            }
        ],
        "metadata": [
            {
                "path": "/help/engines",
                "method": "GET",
                "description": "List available detection engines"
            },
            {
                "path": "/help/entities",
                "method": "GET",
                "description": "List available entity types"
            },
            {
                "path": "/help/entity-examples",
                "method": "GET",
                "description": "Get examples of different entity types"
            },
            {
                "path": "/help/detectors-status",
                "method": "GET",
                "description": "Get status of detection engines"
            },
            {
                "path": "/help/routes",
                "method": "GET",
                "description": "Comprehensive overview of API routes"
            }
        ],
        "system": [
            {
                "path": "/status",
                "method": "GET",
                "description": "Basic API status"
            },
            {
                "path": "/health",
                "method": "GET",
                "description": "Detailed health check"
            },
            {
                "path": "/metrics",
                "method": "GET",
                "description": "Performance metrics"
            },
            {
                "path": "/readiness",
                "method": "GET",
                "description": "Service readiness check"
            }
        ]
    }

    # Cache the result - static content can be cached longer
    cache_key = "api_routes"
    response_cache.set(cache_key, routes_info, CACHE_TTL["engines"])

    return JSONResponse(content=routes_info)