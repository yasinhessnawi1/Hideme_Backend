from flask import Blueprint, request, jsonify
from saved_code.api.handlers import process_pdf

# Define Flask Blueprint
api_blueprint = Blueprint('api', __name__)


@api_blueprint.route('/upload-pdf', methods=['POST'])
def upload_pdf():
    """
    API endpoint to handle PDF upload, process it with:
    1- Presidio + Kushtrim (First JSON)
    2- Gemini AI (Second JSON)
    3- Send Both JSONs to Frontend
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    # Call the handler
    return process_pdf(file)
