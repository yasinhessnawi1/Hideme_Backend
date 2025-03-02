from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/status")
async def status():
    """
    Endpoint that accepts an uploaded file (PDF or text). If the file is a PDF, we extract its text with positions.
    Then we pass the extracted fisk_data to our Gemini service for sensitive fisk_data detection.
    Returns the anonymized text, the detection results, and the redaction mapping.
    """

    return JSONResponse(content={"status": "success"})
