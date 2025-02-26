from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import logging
from tempfile import NamedTemporaryFile

from backend.app.services.presidio_service import PresidioService
from backend.app.services.pdf_text_extraction_service import PDFTextExtractor

router = APIRouter()

# Initialize our Presidio detection service
presidio_service = PresidioService()


@router.post("/presidio_detect_sensitive")
async def presidio_detect_sensitive(file: UploadFile = File(...)):
    """
    Endpoint that accepts an uploaded file (PDF or text), extracts its text (with positions if PDF)
    and uses the Presidio service to detect sensitive information.
    Returns the anonymized text, the detection results and the redaction mapping.
    """
    try:
        contents = await file.read()
        if file.content_type == "application/pdf":
            with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(contents)
                tmp_path = tmp.name

            extractor = PDFTextExtractor(tmp_path)
            extracted_data = extractor.extract_text_with_positions()
        else:
            text = contents.decode("utf-8")
            extracted_data = {
                "pages": [
                    {"page": 1, "words": [{"text": text, "x0": 0, "y0": 0, "x1": 100, "y1": 10}]}
                ]
            }

        anonymized_text, results_json, redaction_mapping = presidio_service.detect_sensitive_data(extracted_data)
        return JSONResponse(content={
            "anonymized_text": anonymized_text,
            "results": results_json,
            "redaction_mapping": redaction_mapping
        })
    except Exception as e:
        logging.error(f"Error in presidio_detect_sensitive: {e}")
        raise HTTPException(status_code=500, detail="Error processing file")
