from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from fastapi.responses import FileResponse
import logging
import os
import json
from tempfile import NamedTemporaryFile

from backend.app.services.pdf_redaction_service import PDFRedactionService

router = APIRouter()

@router.post("/pdf-redact")
async def pdf_redact(
    file: UploadFile = File(...),
    redaction_mapping: str = Form(None)
):
    """
    Endpoint that accepts a PDF file and a redaction mapping (as a JSON string) via form-data.
    The PDF file is processed by the PDFRedactionService to apply redactions based on the provided mapping.
    Returns the redacted PDF file.
    """
    print(redaction_mapping)
    try:
        # Parse the redaction mapping from the form data if provided.
        if redaction_mapping:
            try:
                mapping_data = json.loads(redaction_mapping)
            except Exception as e:
                logging.error(f"Error parsing redaction mapping: {e}")
                raise HTTPException(status_code=400, detail="Invalid redaction mapping format.")
        else:
            mapping_data = {}

        # Save the uploaded file to a temporary location.
        contents = await file.read()
        with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(contents)
            tmp_input_path = tmp.name

        # Initialize the PDF redaction service.
        pdf_redactor = PDFRedactionService(tmp_input_path)
        output_path = os.path.join(os.path.dirname(tmp_input_path), "redacted_" + os.path.basename(tmp_input_path))
        redacted_pdf_path = pdf_redactor.apply_redactions(mapping_data, output_path)

        return FileResponse(
            redacted_pdf_path,
            media_type="application/pdf",
            filename="redacted.pdf"
        )
    except Exception as e:
        logging.error(f"Error in pdf_redact: {e}")
        raise HTTPException(status_code=500, detail="Error redacting PDF")
