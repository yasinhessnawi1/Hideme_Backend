import json
from typing import Optional

from fastapi import APIRouter, File, UploadFile, HTTPException, Form
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
        requested_entities: Optional[str] = Form(None)  # Accepting requested_entities as a form field.
):
    """
    Detects sensitive information in a PDF or text file using Presidio.
    """
    try:
        # Ensure `requested_entities` is a valid JSON string or set it to an empty list
        if requested_entities:
            requested_entities = json.loads(requested_entities)
        else:
            requested_entities = []  # Default to empty list if not provided

        # Validate requested entities
        for entity in requested_entities:
            if entity not in REQUESTED_ENTITIES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported entity: {entity}. Supported entities: {REQUESTED_ENTITIES}"
                )

        logging.info(f"Requested entities: {requested_entities}")

        # Read file contents
        contents = await file.read()

        # Extract text from PDF or text file
        if file.content_type == "application/pdf":
            with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(contents)
                tmp_path = tmp.name
            extractor = PDFTextExtractor(tmp_path)
            extracted_data = extractor.extract_text_with_positions()
        else:
            extracted_data = contents.decode("utf-8")  # Assume text files are UTF-8 encoded

        # Detect sensitive data using Presidio
        anonymized_text, results_json, redaction_mapping = presidio_service.detect_sensitive_data(
            extracted_data, requested_entities
        )

        return JSONResponse(content={
            "redaction_mapping": redaction_mapping
        })

    except json.JSONDecodeError:
        logging.error("Invalid JSON format in requested_entities")
        raise HTTPException(status_code=400, detail="Invalid JSON format in requested_entities")

    except Exception as e:
        logging.error(f"Error in presidio_detect_sensitive: {e}")
        raise HTTPException(status_code=500, detail="Error processing file")
