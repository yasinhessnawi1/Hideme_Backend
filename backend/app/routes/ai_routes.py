from typing import Optional

from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from fastapi.responses import JSONResponse
from tempfile import NamedTemporaryFile

from backend.app.services.gemini_service import GeminiService
from backend.app.services.pdf_text_extraction_service import PDFTextExtractor
from backend.app.utils.helpers.json_helper import validate_requested_entities
from backend.app.utils.logger import default_logger as logging

router = APIRouter()

# Initialize our Gemini detection service
gemini_service = GeminiService()


@router.post("/detect")
async def ai_detect_sensitive(
    file: UploadFile = File(...),
    requested_entities: Optional[str] = Form(None)
):
    """
    Endpoint for detecting sensitive data using AI (Gemini).
    """
    try:
        # ✅ Validate and filter requested entities
        requested_entities = validate_requested_entities(requested_entities)
        logging.info(f"✅ Filtered Requested Entities: {requested_entities}")

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
            text = contents.decode("utf-8")
            extracted_data = {
                "pages": [{"page": 1, "words": [{"text": text, "x0": 0, "y0": 0, "x1": 100, "y1": 10}]}]
            }

        # ✅ Detect all entities using Gemini
        anonymized_text, results_json, redaction_mapping = gemini_service.detect_sensitive_data(
            extracted_data, requested_entities
        )

        # ✅ Filter only requested entities
        filtered_redaction_mapping = {
            "pages": [
                {
                    "page": page["page"],
                    "sensitive": [
                        entity for entity in page["sensitive"] if entity["entity_type"] in requested_entities
                    ]
                }
                for page in redaction_mapping["pages"]
            ]
        }

        return JSONResponse(content={"redaction_mapping": filtered_redaction_mapping})

    except Exception as e:
        logging.error(f"❌ Error in ai_detect_sensitive: {e}")
        raise HTTPException(status_code=500, detail="Error processing file")