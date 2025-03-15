"""
Gemini AI-based entity detection routes with parallel processing and output sanitization.
"""
import json
import time
import os
import asyncio
from typing import Optional
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, File, UploadFile, Form
from fastapi.responses import JSONResponse

from backend.app.factory.document_processing import (
    DocumentProcessingFactory,
    DocumentFormat,
)
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.logger import default_logger as logger, log_info, log_warning
from backend.app.utils.sanitize_utils import sanitize_detection_output

router = APIRouter()


@router.post("/detect")
async def ai_detect_sensitive(
    file: UploadFile = File(...),
    requested_entities: Optional[str] = Form(None)
):
    """
    Detect sensitive information in a document using Gemini AI with parallel processing.

    Args:
        file: Uploaded document file (PDF or text)
        requested_entities: JSON string of entity types to detect (optional)

    Returns:
        JSON response with sanitized redaction mapping
    """
    start_time = time.time()
    processing_times = {}

    try:
        # Process requested entities (can be None)
        entity_list = None
        if requested_entities:
            try:
                entity_list = json.loads(requested_entities)
                log_info(f"[OK] Validated entity list for Gemini: {entity_list}")
            except json.JSONDecodeError:
                log_warning("[WARNING] Invalid JSON format in requested_entities, using default Gemini entities")

        # Read file contents
        file_read_start = time.time()
        contents = await file.read()
        file_read_time = time.time() - file_read_start
        processing_times["file_read_time"] = file_read_time

        # Handle different file types
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
            # For non-PDF files assume a plain text file
            text = contents.decode("utf-8")
            # Create a dummy extracted_data with a single page and one "word"
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

        # Get the Gemini detector from initialization service
        detector = initialization_service.get_gemini_detector()

        # Detect sensitive data using async method
        detection_start = time.time()
        anonymized_text, entities, redaction_mapping = await detector.detect_sensitive_data_async(
            extracted_data, entity_list
        )
        detection_time = time.time() - detection_start
        processing_times["detection_time"] = detection_time

        # Calculate total time and word count metrics
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
        sanitized_response["model_info"] = {"engine": "gemini"}

        log_info(f"[PERF] Gemini detection completed in {total_time:.2f}s " 
                f"(Extract: {extract_time:.2f}s, Detect: {detection_time:.2f}s), "
                f"Found {sanitized_response['entities_detected']['total']} entities")

        return JSONResponse(content=sanitized_response)

    except Exception as e:
        logger.error(f"[ERROR] Error in ai_detect_sensitive: {str(e)}")
        # Return standardized error response
        error_response = {
            "redaction_mapping": {"pages": []},
            "entities_detected": {"total": 0, "by_type": {}, "by_page": {}},
            "error": str(e),
            "performance": {"total_time": time.time() - start_time},
            "model_info": {"engine": "gemini"}
        }
        return JSONResponse(status_code=500, content=error_response)