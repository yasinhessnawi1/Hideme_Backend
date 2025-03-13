"""
GLiNER model configuration with persistent storage settings.
"""
import os

# GLiNER model identification
GLINER_MODEL_NAME = "urchade/gliner_multi_pii-v1"

# Local storage for downloaded models
GLINER_MODEL_DIR = os.environ.get("GLINER_MODEL_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "gliner"))

# Create model directory if it doesn't exist
os.makedirs(GLINER_MODEL_DIR, exist_ok=True)

# Path to store model weights (we'll use a clean filename)
GLINER_MODEL_PATH = os.path.join(GLINER_MODEL_DIR, "gliner_multi_pii-v1.pt")

# GLiNER supported entity types
GLINER_ENTITIES = [
    "person", "book", "location", "date", "actor", "character", "organization", "phone number",
    "address", "passport number", "email", "credit card number", "social security number",
    "health insurance id number", "date of birth", "mobile phone number", "bank account number",
    "medication", "cpf", "tax identification number", "medical condition",
    "identity card number", "national id number", "ip address", "email address", "iban",
    "credit card expiration date", "username", "health insurance number", "registration number",
    "student id number", "insurance number", "flight number", "landline phone number", "blood type",
    "cvv", "reservation number", "digital signature", "social media handle", "license plate number",
    "cnpj", "postal code", "passport_number", "serial number", "vehicle registration number",
    "credit card brand", "fax number", "visa number", "insurance company", "identity document number",
    "transaction number", "national health insurance number", "cvc", "birth certificate number",
    "train ticket number", "passport expiration date", "social_security_number"
]

# Model initialization configuration
GLINER_CONFIG = {
    "model_name": GLINER_MODEL_NAME,
    "local_model_path": GLINER_MODEL_DIR,
    "model_file_path": GLINER_MODEL_PATH,
    "default_entities": GLINER_ENTITIES
}