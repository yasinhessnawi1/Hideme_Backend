"""
Hybrid entity detection routes combining multiple detection engines with improved
caching and output sanitization.
"""
import time
import asyncio
import os
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
from backend.app.utils.helpers.json_helper import validate_requested_entities
from backend.app.utils.logger import log_info, log_error, log_warning
from backend.app.utils.sanitize_utils import sanitize_detection_output

router = APIRouter()


@router.post("/detect")
async def hybrid_detect_sensitive(
        file: UploadFile = File(...),
        requested_entities: Optional[str] = Form(None),
        use_presidio: bool = Form(True),
        use_gemini: bool = Form(True),
        use_gliner: bool = Form(False)
):
    """
    Detect sensitive information using multiple detection engines with parallel processing.

    Args:
        file: Uploaded document file (PDF or text)
        requested_entities: JSON string of entity types to detect (optional)
        use_presidio: Whether to use Presidio for detection
        use_gemini: Whether to use Gemini for detection
        use_gliner: Whether to use GLiNER for detection

    Returns:
        JSON response with combined redaction mapping
    """
    start_time = time.time()
    processing_times = {}

    try:
        # Process and validate requested entities
        entity_list = validate_requested_entities(requested_entities)
        log_info(f"[OK] Requested entities for hybrid detection: {entity_list}")

        # Record file read time
        file_read_start = time.time()
        contents = await file.read()
        file_read_time = time.time() - file_read_start
        processing_times["file_read_time"] = file_read_time

        # Extract text from document
        extract_start = time.time()
        if file.content_type == "application/pdf":
            with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(contents)
                tmp_input_path = tmp.name

            # Extract text with positions
            extractor = DocumentProcessingFactory.create_document_extractor(
                tmp_input_path, DocumentFormat.PDF
            )
            extracted_data = await asyncio.to_thread(extractor.extract_text_with_positions)
            extractor.close()

            # Clean up temporary file
            try:
                os.remove(tmp_input_path)
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

        # Configure the hybrid detector
        config = {
            "use_presidio": use_presidio,
            "use_gemini": use_gemini,
            "use_gliner": use_gliner,
            "gliner_model_name": GLINER_MODEL_NAME,
            "entities": entity_list
        }

        # Create hybrid entity detector
        detector_create_start = time.time()
        detector = DocumentProcessingFactory.create_entity_detector(
            EntityDetectionEngine.HYBRID,
            config=config
        )
        detector_create_time = time.time() - detector_create_start
        processing_times["detector_init_time"] = detector_create_time

        # Detect sensitive data - use the async version directly
        detection_start = time.time()

        if hasattr(detector, 'detect_sensitive_data_async'):
            anonymized_text, entities, redaction_mapping = await detector.detect_sensitive_data_async(
                extracted_data, entity_list
            )
        else:
            # Fall back to synchronous version wrapped in asyncio.to_thread
            anonymized_text, entities, redaction_mapping = await asyncio.to_thread(
                detector.detect_sensitive_data,
                extracted_data, entity_list
            )

        detection_time = time.time() - detection_start
        processing_times["detection_time"] = detection_time

        # Calculate total time and entity density
        total_time = time.time() - start_time
        processing_times["total_time"] = total_time

        total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
        entity_density = (len(entities) / total_words) * 1000 if total_words > 0 else 0
        processing_times["entity_density"] = entity_density
        processing_times["pages_count"] = len(extracted_data.get("pages", []))
        processing_times["words_count"] = total_words

        # Add engine information
        engines_used = {
            "presidio": use_presidio,
            "gemini": use_gemini,
            "gliner": use_gliner
        }

        # Sanitize output using the utility function
        sanitized_response = sanitize_detection_output(
            anonymized_text, entities, redaction_mapping, processing_times
        )

        # Add engines used information to the response
        sanitized_response["model_info"] = {
            "engine": "hybrid",
            "engines_used": engines_used
        }

        log_info(f"[PERF] Hybrid detection completed in {total_time:.2f}s " 
                f"(Extract: {extract_time:.2f}s, Detect: {detection_time:.2f}s, "
                f"Entities: {sanitized_response['entities_detected']['total']})")

        return JSONResponse(content=sanitized_response)

    except Exception as e:
        log_error(f"[ERROR] Error in hybrid_detect_sensitive: {e}")
        # Create fallback response with error
        error_response = {
            "redaction_mapping": {"pages": []},
            "entities_detected": {"total": 0, "by_type": {}, "by_page": {}},
            "error": str(e),
            "performance": {"total_time": time.time() - start_time},
            "model_info": {"engine": "hybrid", "engines_used": {
                "presidio": use_presidio,
                "gemini": use_gemini,
                "gliner": use_gliner
            }}
        }
        return JSONResponse(status_code=500, content=error_response)