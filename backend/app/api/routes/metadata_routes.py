"""
Metadata and configuration endpoints.
"""
from fastapi import APIRouter, HTTPException

from backend.app.configs.gliner_config import GLINER_ENTITIES
from backend.app.configs.presidio_config import REQUESTED_ENTITIES
from backend.app.configs.gemini_config import AVAILABLE_ENTITIES
from backend.app.factory.document_processing import EntityDetectionEngine
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.logger import log_error, log_info

router = APIRouter()


@router.get("/engines")
async def get_available_engines():
    """
    Get list of available entity detection engines.

    Returns:
        List of available entity detection engines
    """
    return {
        "engines": [e.name for e in EntityDetectionEngine]
    }


@router.get("/entities")
async def get_available_entities():
    """
    Get list of available entity types for detection.

    Returns:
        Dictionary of available entity types by detection engine
    """
    try:
        # Get GLiNER entities
        gliner_entities = GLINER_ENTITIES

        return {
            "presidio_entities": REQUESTED_ENTITIES,
            "gemini_entities": AVAILABLE_ENTITIES,
            "gliner_entities": gliner_entities
        }

    except Exception as e:
        log_error(f"[ERROR] Error retrieving available entities: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving entity information")


@router.get("/entity-examples")
async def get_entity_examples():
    """
    Get examples for different entity types.

    Returns:
        Dictionary of example text for each entity type
    """
    return {
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


@router.get("/detectors-status")
async def get_detectors_status():
    """
    Get status information for all cached entity detectors.

    Returns:
        Status information for all detector instances
    """
    try:
        # Get status from initialization service
        detector_health = initialization_service.check_health()
        detector_metrics = initialization_service.get_usage_metrics()

        # Try to get detailed status from each detector
        detectors_status = {
            "presidio": {},
            "gemini": {},
            "gliner": {}
        }

        # Get Presidio detector status
        presidio_detector = initialization_service.get_detector(EntityDetectionEngine.PRESIDIO)
        if presidio_detector and hasattr(presidio_detector, 'get_status'):
            detectors_status["presidio"] = presidio_detector.get_status()
        else:
            detectors_status["presidio"] = {
                "initialized": detector_health["detectors"]["presidio"],
                "uses": detector_metrics.get("presidio", {}).get("uses", 0)
            }

        # Get Gemini detector status
        gemini_detector = initialization_service.get_gemini_detector()
        if gemini_detector and hasattr(gemini_detector, 'get_status'):
            detectors_status["gemini"] = gemini_detector.get_status()
        else:
            detectors_status["gemini"] = {
                "initialized": detector_health["detectors"]["gemini"],
                "uses": detector_metrics.get("gemini", {}).get("uses", 0)
            }

        # Get GLiNER models status
        gliner_metrics = detector_metrics.get("gliner", {})
        detectors_status["gliner"] = {
            "models_count": len(gliner_metrics),
            "total_uses": sum(model.get("uses", 0) for model in gliner_metrics.values()),
            "models": {}
        }

        # Get detailed GLiNER model information
        for model_key, model_metrics in gliner_metrics.items():
            try:
                gliner_detector = initialization_service.get_gliner_detector(model_key.split("_"))
                if gliner_detector and hasattr(gliner_detector, 'get_status'):
                    detectors_status["gliner"]["models"][model_key] = {
                        **gliner_detector.get_status(),
                        "uses": model_metrics.get("uses", 0)
                    }
                else:
                    detectors_status["gliner"]["models"][model_key] = {
                        "initialized": True,
                        "uses": model_metrics.get("uses", 0)
                    }
            except Exception as e:
                log_error(f"[ERROR] Error getting status for GLiNER model {model_key}: {e}")

        return detectors_status

    except Exception as e:
        log_error(f"[ERROR] Error retrieving detector status: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving detector status")