import json
from typing import Optional

from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from fastapi.responses import JSONResponse
from tempfile import NamedTemporaryFile

from backend.app.services.gliner_service import Gliner
from backend.app.services.presidio_service import PresidioService
from backend.app.services.pdf_text_extraction_service import PDFTextExtractor
from backend.app.utils.helpers.json_helper import validate_requested_entities
from backend.app.utils.logger import default_logger as logging

router = APIRouter()

# Initialize our Presidio detection service
presidio_service = PresidioService()
gliner_service = Gliner()


@router.post("/detect")
async def presidio_detect_sensitive(
    file: UploadFile = File(...),
    requested_entities: Optional[str] = Form(None)
):
    """
    Detects sensitive information in a PDF or text file using Presidio.
    """
    try:

        # Ensure `requested_entities` is a valid JSON string or set it to an empty list
        requested_entities = validate_requested_entities(requested_entities)

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

        # Detect sensitive fisk_data using Presidio
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


@router.post("/gl_detect")
async def gliner_detect_sensitive_entities(
    file: UploadFile = File(...),
    requested_entities: Optional[str] = Form(None)
):
    """
    Detects sensitive information using GLiNER.
    """
    try:
        labels = [
            "person", "book", "location", "date", "actor", "character", "organization", "phone number",
            "address", "passport number", "email", "credit card number", "social security number",
            "health insurance id number", "date of birth", "mobile phone number", "bank account number",
            "medication", "cpf", "driver's license number", "tax identification number", "medical condition",
            "identity card number", "national id number", "ip address", "email address", "iban",
            "credit card expiration date", "username", "health insurance number", "registration number",
            "student id number", "insurance number", "flight number", "landline phone number", "blood type",
            "cvv", "reservation number", "digital signature", "social media handle", "license plate number",
            "cnpj", "postal code", "passport_number", "serial number", "vehicle registration number",
            "credit card brand", "fax number", "visa number", "insurance company", "identity document number",
            "transaction number", "national health insurance number", "cvc", "birth certificate number",
            "train ticket number", "passport expiration date", "social_security_number"
        ]

        # ✅ Validate and filter requested entities
        requested_entities = validate_requested_entities(requested_entities, labels=labels)
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
            extracted_data = contents.decode("utf-8")

        # ✅ Detect all entities using GLiNER
        redaction_mapping = gliner_service.detect_entities(extracted_data, json.dumps(requested_entities))

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

    except json.JSONDecodeError:
        logging.error("❌ Invalid JSON format in requested_entities")
        raise HTTPException(status_code=400, detail="Invalid JSON format in requested_entities")

    except Exception as e:
        logging.error(f"❌ Error in gliner detect sensitive: {e}")
        raise HTTPException(status_code=500, detail="Error processing file")