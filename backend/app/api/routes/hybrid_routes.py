"""
Hybrid entity detection routes combining multiple detection engines with parallel processing support.
"""
import time
import asyncio
import os
import json
from typing import Optional
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from fastapi.responses import JSONResponse

from backend.app.factory.document_processing import (
    DocumentProcessingFactory,
    DocumentFormat,
    EntityDetectionEngine
)
from backend.app.utils.helpers.json_helper import validate_requested_entities
from backend.app.utils.logger import log_info, log_error, log_warning

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
    try:
        # Validate requested entities
        entity_list = validate_requested_entities(requested_entities)

        # Read file contents
        contents = await file.read()

        # Extract text from document
        if file.content_type == "application/pdf":
            with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(contents)
                tmp_input_path = tmp.name

            # Extract text with positions (use asyncio.to_thread for blocking operations)
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
        extract_time = time.time() - start_time

        # Create hybrid entity detector with configuration
        config = {
            "use_presidio": use_presidio,
            "use_gemini": use_gemini,
            "use_gliner": use_gliner,
            "gliner_model_name": "urchade/gliner_multi_pii-v1"
        }

        detector = DocumentProcessingFactory.create_entity_detector(
            EntityDetectionEngine.HYBRID,
            config=config
        )

        # Detect sensitive data
        detection_start = time.time()
        anonymized_text, entities, redaction_mapping = await detector.detect_sensitive_data_async(
            extracted_data, entity_list
        )
        detection_time = time.time() - detection_start

        # Calculate total time and entity density
        total_time = time.time() - start_time
        total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
        entity_density = (len(entities) / total_words) * 1000 if total_words > 0 else 0

        # Build performance metrics
        performance = {
            "extraction_time": extract_time,
            "detection_time": detection_time,
            "total_time": total_time,
            "entity_density": entity_density,
            "pages_count": len(extracted_data.get("pages", [])),
            "words_count": total_words
        }

        log_info(f"[PERF] Hybrid detection completed in {total_time:.2f}s " 
                f"(Extract: {extract_time:.2f}s, Detect: {detection_time:.2f}s, "
                f"Entities: {len(entities)})")

        return JSONResponse(content={
            "redaction_mapping": redaction_mapping,
            "engines_used": {
                "presidio": use_presidio,
                "gemini": use_gemini,
                "gliner": use_gliner
            },
            "entities_detected": len(entities),
            "performance": performance
        })

    except Exception as e:
        log_error(f"[ERROR] Error in hybrid_detect_sensitive: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")