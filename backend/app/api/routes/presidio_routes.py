"""
Presidio and GLiNER entity detection routes with robust async processing support.
"""
import json
import time
import os
import asyncio
from typing import Optional, List
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from fastapi.responses import JSONResponse

from backend.app.configs.gliner_config import GLINER_MODEL_NAME, GLINER_ENTITIES
from backend.app.factory.document_processing import (
    DocumentProcessingFactory,
    DocumentFormat,
    EntityDetectionEngine
)
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.helpers.json_helper import validate_requested_entities
from backend.app.utils.logger import default_logger as logger, log_info, log_warning, log_error

router = APIRouter()


@router.post("/detect")
async def presidio_detect_sensitive(
    file: UploadFile = File(...),
    requested_entities: Optional[str] = Form(None)
):
    """
    Detect sensitive information in a document using Presidio with robust async processing.

    Args:
        file: Uploaded document file (PDF or text)
        requested_entities: JSON string of entity types to detect (optional)

    Returns:
        JSON response with redaction mapping and performance metrics
    """
    start_time = time.time()
    try:
        # Validate requested entities
        entity_list = validate_requested_entities(requested_entities)
        log_info(f"[OK] Requested entities: {entity_list}")

        # Read file contents
        contents = await file.read()

        # Extract text from document
        if file.content_type == "application/pdf":
            with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(contents)
                tmp_path = tmp.name

            try:
                # Extract text with positions (use asyncio.to_thread for blocking operations)
                extractor = DocumentProcessingFactory.create_document_extractor(
                    tmp_path, DocumentFormat.PDF
                )
                extracted_data = await asyncio.to_thread(extractor.extract_text_with_positions)
                extractor.close()
            finally:
                # Clean up temporary file
                try:
                    os.remove(tmp_path)
                except Exception as e:
                    log_warning(f"[WARNING] Failed to remove temporary file: {e}")
        else:
            # Handle as text file
            text = contents.decode("utf-8")
            extracted_data = {
                "pages": [
                    {
                        "page": 1,
                        "words": [{"text": text, "x0": 0, "y0": 0, "x1": 100, "y1": 10}]
                    }
                ]
            }
        extract_time = time.time() - start_time

        # Get the cached Presidio detector
        detector = initialization_service.get_presidio_detector()
        if not detector:
            log_warning("[WARNING] No cached Presidio detector found, creating a new one")
            detector = DocumentProcessingFactory.create_entity_detector(
                EntityDetectionEngine.PRESIDIO
            )

        # Detect sensitive data
        detection_start = time.time()

        # Use async method directly
        detection_result = await detector.detect_sensitive_data_async(
            extracted_data, entity_list
        )

        # Check if detection_result is None
        if detection_result is None:
            log_error("[ERROR] Presidio detection returned None instead of expected results")
            return JSONResponse(content={
                "redaction_mapping": {"pages": []},
                "entities_detected": 0,
                "error": "Detection failed to return results",
                "performance": {
                    "extraction_time": extract_time,
                    "detection_time": time.time() - detection_start,
                    "total_time": time.time() - start_time,
                }
            })

        # Safely unpack the detection results
        anonymized_text, entities, redaction_mapping = detection_result
        detection_time = time.time() - detection_start

        # Calculate total time
        total_time = time.time() - start_time

        # Build performance metrics
        performance = {
            "extraction_time": extract_time,
            "detection_time": detection_time,
            "total_time": total_time,
        }

        log_info(f"[PERF] Presidio detection completed in {total_time:.2f}s " 
                f"(Extract: {extract_time:.2f}s, Detect: {detection_time:.2f}s)")

        return JSONResponse(content={
            "redaction_mapping": redaction_mapping,
            "entities_detected": len(entities),
            "performance": performance
        })

    except Exception as e:
        log_error(f"[ERROR] Error in presidio_detect_sensitive: {str(e)}")
        return JSONResponse(status_code=500, content={
            "redaction_mapping": {"pages": []},
            "entities_detected": 0,
            "error": str(e),
            "performance": {
                "total_time": time.time() - start_time
            }
        })


@router.post("/gl_detect")
async def gliner_detect_sensitive_entities(
    file: UploadFile = File(...),
    requested_entities: Optional[str] = Form(None)
):
    """
    Detect sensitive information in a document using GLiNER with parallel processing.

    Args:
        file: Uploaded document file (PDF or text)
        requested_entities: JSON string of entity types to detect (optional)

    Returns:
        JSON response with redaction mapping and performance metrics
    """
    start_time = time.time()
    try:
        # GLiNER supported labels
        labels = GLINER_ENTITIES

        # Parse requested entities if provided
        if requested_entities:
            try:
                entity_list = json.loads(requested_entities)
            except json.JSONDecodeError:
                log_warning("[WARNING] Invalid JSON format in requested_entities, using default GLiNER entities")
                entity_list = labels
        else:
            entity_list = labels

        # Read file contents
        contents = await file.read()

        # Extract text from document
        if file.content_type == "application/pdf":
            with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(contents)
                tmp_path = tmp.name

            # Extract text with positions (use asyncio.to_thread for blocking operations)
            extractor = DocumentProcessingFactory.create_document_extractor(
                tmp_path, DocumentFormat.PDF
            )
            extracted_data = await asyncio.to_thread(extractor.extract_text_with_positions)
            extractor.close()

            # Clean up temporary file
            try:
                os.remove(tmp_path)
            except Exception as e:
                log_warning(f"[WARNING] Failed to remove temporary file: {e}")
        else:
            # Handle as text file
            text = contents.decode("utf-8")
            extracted_data = {
                "pages": [
                    {
                        "page": 1,
                        "words": [{"text": text, "x0": 0, "y0": 0, "x1": 100, "y1": 10}]
                    }
                ]
            }
        extract_time = time.time() - start_time

        # Get or create GLiNER detector with the requested entities
        detector = initialization_service.get_gliner_detector(entity_list)
        if not detector:
            log_warning("[WARNING] No cached GLiNER detector found, creating a new one")
            detector = DocumentProcessingFactory.create_entity_detector(
                EntityDetectionEngine.GLINER,
                config={
                    "model_name": GLINER_MODEL_NAME,
                    "entities": entity_list
                }
            )

        # Detect sensitive data
        detection_start = time.time()
        detection_result = await detector.detect_sensitive_data_async(
            extracted_data, entity_list
        )

        # Check if detection_result is None
        if detection_result is None:
            log_error("[ERROR] GLiNER detection returned None instead of expected results")
            return JSONResponse(content={
                "redaction_mapping": {"pages": []},
                "entities_detected": 0,
                "error": "Detection failed to return results",
                "performance": {
                    "extraction_time": extract_time,
                    "detection_time": time.time() - detection_start,
                    "total_time": time.time() - start_time,
                }
            })

        # Safely unpack the detection results
        anonymized_text, entities, redaction_mapping = detection_result
        detection_time = time.time() - detection_start

        # Calculate total time
        total_time = time.time() - start_time

        # Build performance metrics
        performance = {
            "extraction_time": extract_time,
            "detection_time": detection_time,
            "total_time": total_time,
        }

        log_info(f"[PERF] GLiNER detection completed in {total_time:.2f}s " 
                f"(Extract: {extract_time:.2f}s, Detect: {detection_time:.2f}s)")

        return JSONResponse(content={
            "redaction_mapping": redaction_mapping,
            "entities_detected": len(entities),
            "performance": performance
        })

    except Exception as e:
        log_error(f"[ERROR] Error in gliner_detect_sensitive_entities: {str(e)}")
        return JSONResponse(status_code=500, content={
            "redaction_mapping": {"pages": []},
            "entities_detected": 0,
            "error": str(e),
            "performance": {
                "total_time": time.time() - start_time
            }
        })