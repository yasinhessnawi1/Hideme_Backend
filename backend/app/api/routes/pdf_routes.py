"""
PDF processing routes with parallel processing support.
"""
import os
import json
import time
import asyncio
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from fastapi.responses import FileResponse, JSONResponse

from backend.app.factory.document_processing import DocumentProcessingFactory, DocumentFormat
from backend.app.utils.logger import log_info, log_error, log_warning

router = APIRouter()


@router.post("/redact")
async def pdf_redact(
        file: UploadFile = File(...),
        redaction_mapping: str = Form(None)
):
    """
    Apply redactions to a PDF file using the provided redaction mapping.

    Args:
        file: Uploaded PDF file
        redaction_mapping: JSON string with redaction information

    Returns:
        The redacted PDF file
    """
    start_time = time.time()
    try:
        # Parse the redaction mapping
        if redaction_mapping:
            try:
                mapping_data = json.loads(redaction_mapping)
            except Exception as e:
                log_error(f"[ERROR] Error parsing redaction mapping: {e}")
                raise HTTPException(status_code=400, detail="Invalid redaction mapping format")
        else:
            mapping_data = {"pages": []}

        # Save the uploaded file to a temporary location
        contents = await file.read()
        with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(contents)
            tmp_input_path = tmp.name

        # Create output path
        output_path = os.path.join(
            os.path.dirname(tmp_input_path),
            f"redacted_{os.path.basename(tmp_input_path)}"
        )

        # Create document redactor and apply redactions
        redactor = DocumentProcessingFactory.create_document_redactor(
            tmp_input_path, DocumentFormat.PDF
        )

        # Apply redactions in a thread pool to avoid blocking
        redact_start = time.time()
        redacted_pdf_path = await asyncio.to_thread(
            redactor.apply_redactions,
            mapping_data,
            output_path
        )
        redact_time = time.time() - redact_start
        total_time = time.time() - start_time

        log_info(f"[PERF] PDF redaction completed in {total_time:.2f}s (redaction: {redact_time:.2f}s)")

        # Clean up temporary file
        try:
            os.remove(tmp_input_path)
            # We'll also clean up the redacted file after sending it
            # This is handled by FastAPI's FileResponse
        except Exception as e:
            log_warning(f"[WARNING] Failed to remove temporary file: {e}")

        # Add performance headers
        headers = {
            "X-Redaction-Time": f"{redact_time:.3f}s",
            "X-Total-Time": f"{total_time:.3f}s"
        }

        return FileResponse(
            redacted_pdf_path,
            media_type="application/pdf",
            filename="redacted.pdf",
            headers=headers
        )

    except Exception as e:
        log_error(f"[ERROR] Error in pdf_redact: {e}")
        raise HTTPException(status_code=500, detail=f"Error redacting PDF: {str(e)}")


@router.post("/extract")
async def pdf_extract(file: UploadFile = File(...)):
    """
    Extract text with positions from a PDF file with performance metrics.

    Args:
        file: Uploaded PDF file

    Returns:
        Extracted text with position information and performance metrics
    """
    start_time = time.time()
    try:
        # Save the uploaded file to a temporary location
        contents = await file.read()
        with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(contents)
            tmp_input_path = tmp.name

        # Create document extractor and extract text
        extractor = DocumentProcessingFactory.create_document_extractor(
            tmp_input_path, DocumentFormat.PDF
        )

        # Run extraction in a thread pool to avoid blocking
        extract_start = time.time()
        extracted_data = await asyncio.to_thread(
            extractor.extract_text_with_positions
        )
        extractor.close()
        extract_time = time.time() - extract_start
        total_time = time.time() - start_time

        # Add performance metrics
        extracted_data["performance"] = {
            "extraction_time": extract_time,
            "total_time": total_time,
            "pages_count": len(extracted_data.get("pages", [])),
            "words_count": sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
        }

        log_info(f"[PERF] PDF extraction completed in {total_time:.2f}s " 
                f"({extracted_data['performance']['pages_count']} pages, "
                f"{extracted_data['performance']['words_count']} words)")

        # Clean up temporary file
        try:
            os.remove(tmp_input_path)
        except Exception as e:
            log_warning(f"[WARNING] Error removing temporary file: {e}")

        return JSONResponse(content=extracted_data)

    except Exception as e:
        log_error(f"[ERROR] Error in pdf_extract: {e}")
        raise HTTPException(status_code=500, detail=f"Error extracting PDF text: {str(e)}")