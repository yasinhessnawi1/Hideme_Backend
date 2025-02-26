import json
from typing import List, Optional

from fastapi import APIRouter, File, UploadFile, HTTPException, Query, Form
from fastapi.responses import JSONResponse
from tempfile import NamedTemporaryFile

from backend.app.configs.presidio_config import REQUESTED_ENTITIES
from backend.app.services.presidio_service import PresidioService
from backend.app.services.pdf_text_extraction_service import PDFTextExtractor
from backend.app.utils.logger import default_logger as logging

router = APIRouter()

# Initialize our Presidio detection service
presidio_service = PresidioService()

@router.post("/detect")
async def presidio_detect_sensitive(
    file: UploadFile = File(...),
    # Accept the requested_entities as a form field.
    requested_entities: Optional[str] = Form(None)
):
    """
    Endpoint that accepts an uploaded file (PDF or text), extracts its text (with positions if PDF),
    and uses the Presidio service to detect sensitive information.
    The `requested_entities` should be a JSON string (e.g. '["PERSON", "PHONE_NUMBER"]').
    Returns the redaction mapping.
    """
    try:
        requested_entities = json.loads(requested_entities)
        for entity in requested_entities:
                print("entity", entity)
                if entity not in REQUESTED_ENTITIES:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Unsupported entity: {entity}. Supported entities: {REQUESTED_ENTITIES}"
                    )

        logging.info(f"requested_entities: {requested_entities}")
        contents = await file.read()
        if file.content_type == "application/pdf":
            with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(contents)
                tmp_path = tmp.name
            extractor = PDFTextExtractor(tmp_path)
            extracted_data = extractor.extract_text_with_positions()


        anonymized_text, results_json, redaction_mapping = presidio_service.detect_sensitive_data(
            extracted_data, requested_entities
        )
        logging.info(f"redaction_mapping: {redaction_mapping}")
        return JSONResponse(content={
            "redaction_mapping": redaction_mapping
        })
    except Exception as e:
        logging.error(f"Error in presidio_detect_sensitive: {e}")
        raise HTTPException(status_code=500, detail="Error processing file")
