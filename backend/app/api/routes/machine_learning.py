"""
Refactored machine learning entity detection routes that utilize shared code and utilities.
"""
from typing import Optional

from fastapi import APIRouter, File, UploadFile, Form

from backend.app.services.initialization_service import initialization_service
from backend.app.utils.common_detection import process_common_detection


router = APIRouter()


@router.post("/detect")
async def presidio_detect_sensitive(
        file: UploadFile = File(...),
        requested_entities: Optional[str] = Form(None)
):
    """
    Detect sensitive information using Presidio with enhanced security and size validation.

    Leverages shared processing logic for improved maintainability and consistency.
    """
    return await process_common_detection(
        file=file,
        requested_entities=requested_entities,
        detector_type="presidio",
        get_detector_func=lambda entity_list: initialization_service.get_presidio_detector()
    )


@router.post("/gl_detect")
async def gliner_detect_sensitive_entities(
        file: UploadFile = File(...),
        requested_entities: Optional[str] = Form(None)
):
    """
    Detect sensitive information using GLiNER with enhanced security and size validation.

    Leverages shared processing logic for improved maintainability and consistency.
    """

    return await process_common_detection(
        file=file,
        requested_entities=requested_entities,
        detector_type="gliner",
        get_detector_func=lambda entity_list: initialization_service.get_gliner_detector()

    )
