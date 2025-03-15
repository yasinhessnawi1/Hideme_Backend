"""
Presidio and GLiNER entity detection routes with robust async processing and output sanitization.
"""
import json
import time
import os
import asyncio
from typing import Optional
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, File, UploadFile, Form
from fastapi.responses import JSONResponse

from backend.app.configs.gliner_config import  GLINER_ENTITIES
from backend.app.factory.document_processing import (
    DocumentProcessingFactory,
    DocumentFormat,
)
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.helpers.json_helper import validate_requested_entities
from backend.app.utils.logger import default_logger as logger, log_info, log_warning, log_error
from backend.app.utils.sanitize_utils import sanitize_detection_output

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
        JSON response with sanitized redaction mapping and performance metrics
    """
    start_time = time.time()
    processing_times = {}

    try:
        # Validate requested entities
        entity_list = validate_requested_entities(requested_entities)
        log_info(f"[OK] Requested entities: {entity_list}")

        # Read file contents
        file_read_start = time.time()
        contents = await file.read()
        file_read_time = time.time() - file_read_start
        processing_times["file_read_time"] = file_read_time

        # Extract text from document
        extract_start = time.time()
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
        extract_time = time.time() - extract_start
        processing_times["extraction_time"] = extract_time

        # Get the Presidio detector from initialization service
        detector = initialization_service.get_presidio_detector()

        # Detect sensitive data
        detection_start = time.time()

        # Use async method directly
        detection_result = await detector.detect_sensitive_data_async(
            extracted_data, entity_list
        )

        # Check if detection_result is None
        if detection_result is None:
            log_error("[ERROR] Presidio detection returned None instead of expected results")
            error_response = {
                "redaction_mapping": {"pages": []},
                "entities_detected": {"total": 0, "by_type": {}, "by_page": {}},
                "error": "Detection failed to return results",
                "performance": {
                    "extraction_time": extract_time,
                    "detection_time": time.time() - detection_start,
                    "total_time": time.time() - start_time,
                },
                "model_info": {"engine": "presidio"}
            }
            return JSONResponse(content=error_response)

        # Safely unpack the detection results
        anonymized_text, entities, redaction_mapping = detection_result
        detection_time = time.time() - detection_start
        processing_times["detection_time"] = detection_time

        # Calculate total time and additional metrics
        total_time = time.time() - start_time
        processing_times["total_time"] = total_time

        # Calculate word count and entity density
        total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
        processing_times["words_count"] = total_words
        processing_times["pages_count"] = len(extracted_data.get("pages", []))

        if total_words > 0 and entities:
            entity_density = (len(entities) / total_words) * 1000  # Entities per 1000 words
            processing_times["entity_density"] = entity_density

        # Sanitize output for consistent response format
        sanitized_response = sanitize_detection_output(
            anonymized_text, entities, redaction_mapping, processing_times
        )

        # Add model information
        sanitized_response["model_info"] = {"engine": "presidio"}

        log_info(f"[PERF] Presidio detection completed in {total_time:.2f}s " 
                f"(Extract: {extract_time:.2f}s, Detect: {detection_time:.2f}s), "
                f"Found {sanitized_response['entities_detected']['total']} entities")

        return JSONResponse(content=sanitized_response)

    except Exception as e:
        log_error(f"[ERROR] Error in presidio_detect_sensitive: {str(e)}")
        # Standardized error response
        error_response = {
            "redaction_mapping": {"pages": []},
            "entities_detected": {"total": 0, "by_type": {}, "by_page": {}},
            "error": str(e),
            "performance": {"total_time": time.time() - start_time},
            "model_info": {"engine": "presidio"}
        }
        return JSONResponse(status_code=500, content=error_response)


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
        JSON response with sanitized redaction mapping and performance metrics
    """
    start_time = time.time()
    processing_times = {}

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
        file_read_start = time.time()
        contents = await file.read()
        file_read_time = time.time() - file_read_start
        processing_times["file_read_time"] = file_read_time

        # Extract text from document
        extract_start = time.time()
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
        extract_time = time.time() - extract_start
        processing_times["extraction_time"] = extract_time

        # Get GLiNER detector from initialization service with the requested entities
        detector = initialization_service.get_gliner_detector(entity_list)

        # Detect sensitive data
        detection_start = time.time()
        detection_result = await detector.detect_sensitive_data_async(
            extracted_data, entity_list
        )

        # Check if detection_result is None
        if detection_result is None:
            log_error("[ERROR] GLiNER detection returned None instead of expected results")
            error_response = {
                "redaction_mapping": {"pages": []},
                "entities_detected": {"total": 0, "by_type": {}, "by_page": {}},
                "error": "Detection failed to return results",
                "performance": {
                    "extraction_time": extract_time,
                    "detection_time": time.time() - detection_start,
                    "total_time": time.time() - start_time,
                },
                "model_info": {"engine": "gliner"}
            }
            return JSONResponse(content=error_response)

        # Safely unpack the detection results
        anonymized_text, entities, redaction_mapping = detection_result
        detection_time = time.time() - detection_start
        processing_times["detection_time"] = detection_time

        # Calculate total time and additional metrics
        total_time = time.time() - start_time
        processing_times["total_time"] = total_time

        # Calculate word count and entity density
        total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
        processing_times["words_count"] = total_words
        processing_times["pages_count"] = len(extracted_data.get("pages", []))

        if total_words > 0 and entities:
            entity_density = (len(entities) / total_words) * 1000  # Entities per 1000 words
            processing_times["entity_density"] = entity_density

        # Sanitize output for consistent response format
        sanitized_response = sanitize_detection_output(
            anonymized_text, entities, redaction_mapping, processing_times
        )

        # Add model information
        sanitized_response["model_info"] = {"engine": "gliner"}

        log_info(f"[PERF] GLiNER detection completed in {total_time:.2f}s " 
                f"(Extract: {extract_time:.2f}s, Detect: {detection_time:.2f}s), "
                f"Found {sanitized_response['entities_detected']['total']} entities")

        return JSONResponse(content=sanitized_response)

    except Exception as e:
        log_error(f"[ERROR] Error in gliner_detect_sensitive_entities: {str(e)}")
        # Standardized error response
        error_response = {
            "redaction_mapping": {"pages": []},
            "entities_detected": {"total": 0, "by_type": {}, "by_page": {}},
            "error": str(e),
            "performance": {"total_time": time.time() - start_time},
            "model_info": {"engine": "gliner"}
        }
        return JSONResponse(status_code=500, content=error_response)