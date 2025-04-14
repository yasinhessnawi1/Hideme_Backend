"""
HIDEME model configuration with persistent storage settings.
"""

import os

# HIDEME model identification
HIDEME_MODEL_NAME = "yasin9999/gliner_finetuned_v1"

# Local storage for downloaded HIDEME model
HIDEME_MODEL_DIR = os.environ.get("HIDEME_MODEL_DIR",
                                  os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                               "models", "hideme"))

# Create model directory if it doesn't exist
os.makedirs(HIDEME_MODEL_DIR, exist_ok=True)

# Path to store model weights (we'll use a clean filename)
HIDEME_MODEL_PATH = os.path.join(HIDEME_MODEL_DIR, "gliner_finetuned_v1")

# HIDEME supported entity types
HIDEME_AVAILABLE_ENTITIES = [
    'AGE-H', 'AGE_INFO-H', 'ANIMAL_INFO-H', 'BEHAVIORAL_PATTERN-H', 'CONTEXT_SENSITIVE-H',
    'CRIMINAL_RECORD-H', 'DATE_TIME-H', 'ECONOMIC_STATUS-H', 'EMAIL_ADDRESS-H', 'EMPLOYMENT_INFO-H',
    'FAMILY_RELATION-H', 'FINANCIAL_INFO-H', 'GOV_ID-H', 'HEALTH_INFO-H', 'IDENTIFIABLE_IMAGE-H',
    'NO_ADDRESS-H', 'NO_PHONE_NUMBER-H', 'PERSON-H', 'POLITICAL_CASE-H', 'POSTAL_CODE-H',
    'SEXUAL_ORIENTATION-H'
]

# HIDEME model initialization configuration
HIDEME_CONFIG = {
    "model_name": HIDEME_MODEL_NAME,
    "local_model_path": HIDEME_MODEL_DIR,
    "model_file_path": HIDEME_MODEL_PATH,
    "default_entities": HIDEME_AVAILABLE_ENTITIES
}
