"""
Refactored machine learning entity detection routes that utilize shared code and utilities.

This module provides API endpoints for detecting sensitive information in uploaded files
using different machine learning models. It implements consistent error handling and
leverages shared processing logic to maintain code quality and reliability.
"""
from typing import Optional

from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse

from backend.app.services.initialization_service import initialization_service
from backend.app.utils.common_detection import process_common_detection
from backend.app.utils.error_handling import SecurityAwareErrorHandler

router = APIRouter()


@router.post("/detect")
async def presidio_detect_sensitive(
        file: UploadFile = File(...),
        requested_entities: Optional[str] = Form(None)
):
    """
    Detect sensitive information using Microsoft Presidio NER with enhanced security.

    This endpoint processes documents using Presidio's named entity recognition system,
    which is optimized for identifying standard PII entities like names, emails, and
    identification numbers with high precision. Presidio excels at detecting structured
    PII patterns using a combination of regex patterns and machine learning models.

    Args:
        file: The uploaded document file (PDF or text-based formats)
        requested_entities: Optional comma-separated list of entity types to detect
                           (if not provided, all supported entity types will be used)

    Returns:
        JSON with detected entities, anonymized text, and redaction mapping

    Raises:
        HTTPException: For invalid file formats, size limits, or processing errors
    """
    try:
        return await process_common_detection(
            file=file,
            requested_entities=requested_entities,
            detector_type="presidio",
            get_detector_func=lambda entity_list: initialization_service.get_presidio_detector()
        )
    except HTTPException as e:
        # Pass through HTTP exceptions directly
        raise e
    except Exception as e:
        # Use security-aware error handling for generic exceptions
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "presidio_detection", 500, file.filename if file else None
        )
        return JSONResponse(status_code=status_code, content=error_response)


@router.post("/gl_detect")
async def gliner_detect_sensitive_entities(
        file: UploadFile = File(...),
        requested_entities: Optional[str] = Form(None)
):
    """
    Detect sensitive information using GLiNER with enhanced security and specialized entity recognition.

    This endpoint processes documents using the GLiNER (Generalized Language-Independent Named Entity
    Recognition) model, which is particularly effective at detecting domain-specific or custom
    entity types that traditional NER systems might miss. GLiNER leverages transfer learning
    techniques to identify complex entities like medical conditions, financial instruments,
    and specialized identifiers.

    Args:
        file: The uploaded document file (PDF or text-based formats)
        requested_entities: Optional comma-separated list of entity types to detect
                           (if not provided, default GLiNER entities will be used)

    Returns:
        JSON with detected entities, anonymized text, and redaction mapping

    Raises:
        HTTPException: For invalid file formats, size limits, or processing errors
    """
    try:
        return await process_common_detection(
            file=file,
            requested_entities=requested_entities,
            detector_type="gliner",
            get_detector_func=lambda entity_list: initialization_service.get_gliner_detector()
        )
    except HTTPException as e:
        # Pass through HTTP exceptions directly
        raise e
    except Exception as e:
        # Use security-aware error handling for generic exceptions
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "gliner_detection", 500, file.filename if file else None
        )
        return JSONResponse(status_code=status_code, content=error_response)