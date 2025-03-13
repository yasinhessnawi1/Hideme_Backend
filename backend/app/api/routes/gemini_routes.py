"""
Gemini AI-based entity detection routes with parallel processing support.
"""
import json
import time
import os
import asyncio
from typing import Optional, List
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from fastapi.responses import JSONResponse

from backend.app.factory.document_processing import (
    DocumentProcessingFactory,
    DocumentFormat,
    EntityDetectionEngine
)
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.logger import default_logger as logger, log_info, log_warning

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
        JSON response with redaction mapping
    """
    start_time = time.time()
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
        contents = await file.read()

        # Handle different file types
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

        # Get the cached Gemini detector
        detector = initialization_service.get_gemini_detector()
        if not detector:
            log_warning("[WARNING] No cached Gemini detector found, creating a new one")
            detector = DocumentProcessingFactory.create_entity_detector(
                EntityDetectionEngine.GEMINI
            )

        # Detect sensitive data using async method
        extract_start = time.time()
        _, entities, redaction_mapping = await detector.detect_sensitive_data_async(
            extracted_data, entity_list
        )
        detection_time = time.time() - extract_start

        # Calculate total time
        total_time = time.time() - start_time

        # Build performance metrics
        performance = {
            "detection_time": detection_time,
            "total_time": total_time,
        }

        log_info(f"[PERF] Gemini detection completed in {total_time:.2f}s " 
                f"(Detect: {detection_time:.2f}s)")

        return JSONResponse(content={
            "redaction_mapping": redaction_mapping,
            "entities_detected": len(entities),
            "performance": performance
        })

    except Exception as e:
        logger.error(f"[ERROR] Error in ai_detect_sensitive: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")