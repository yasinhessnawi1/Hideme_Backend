from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from tempfile import NamedTemporaryFile

from backend.app.services.gemini_service import GeminiService
from backend.app.services.pdf_text_extraction_service import PDFTextExtractor
from backend.app.utils.logger import default_logger as logging

router = APIRouter()

# Initialize our Gemini detection service
gemini_service = GeminiService()



@router.post("/detect")
async def ai_detect_sensitive(file: UploadFile = File(...)):
    """
    Endpoint that accepts an uploaded file (PDF or text). If the file is a PDF, we extract its text with positions.
    Then we pass the extracted data to our Gemini service for sensitive data detection.
    Returns the anonymized text, the detection results, and the redaction mapping.
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
            # For non-PDF files assume a plain text file
            text = contents.decode("utf-8")
            # Create a dummy extracted_data with a single page and one “word”
            extracted_data = {
                "pages": [
                    {"page": 1, "words": [{"text": text, "x0": 0, "y0": 0, "x1": 100, "y1": 10}]}
                ]
            }

        anonymized_text, results_json, redaction_mapping = gemini_service.detect_sensitive_data(extracted_data)
        return JSONResponse(content={
            "anonymized_text": anonymized_text,
            "results": results_json,
            "redaction_mapping": redaction_mapping
        })
    except Exception as e:
        logging.error(f"Error in ai_detect_sensitive: {e}")
        raise HTTPException(status_code=500, detail="Error processing file")
