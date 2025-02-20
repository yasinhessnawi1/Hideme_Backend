import logging
import fitz
from flask import jsonify
from werkzeug.utils import secure_filename
from src.pdf_extractor import PDFExtractor
from src.gemini_api import GeminiAPI
from src.gemini_response_handler import ResponseHandler

# Initialize API clients
gemini_api = GeminiAPI()
response_handler = ResponseHandler(gemini_api)

# Allowed file types
ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename):
    """Check if the file has a valid extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def process_pdf(file):
    """
    Handles PDF processing:
    1️- Extract Raw Text from PDF
    2️- Process Raw Text with Presidio & Kushtrim (Anonymization)
    3- Process the SAME Raw Text with Gemini API
    Returns both JSON results.
    """
    filename = secure_filename(file.filename)
    logging.info(f"📂 Processing file: {filename}")

    if not allowed_file(filename):
        return jsonify({"error": "Invalid file type"}), 400

    try:
        # Extract text WITHOUT saving the file permanently
        pdf_extractor = PDFExtractor(fitz.open("pdf", file.read()))
        extracted_data = pdf_extractor.extract_data()

        # Process with Presidio & Kushtrim model
        anonymized_data = extracted_data

        # Process with Gemini API
        gemini_response = response_handler.save_responses_per_page(extracted_data["pages"])

        return jsonify({
            "presidio_result": anonymized_data,
            "gemini_result": gemini_response
        }), 200

    except Exception as e:
        logging.error(f"❌ Internal Server Error: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500
