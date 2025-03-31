"""
Configuration for Presidio entity detection with Norwegian support.
"""
import os

# Base directory of the project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Default language - set to Norwegian
DEFAULT_LANGUAGE = "nb"

# Path to local Hugging Face model (if used)
LOCAL_HF_MODEL_PATH = os.path.join(BASE_DIR, "models", "local_kushtrim_norbert3_large_ner")

# Entity types to detect by default
# Only include entities supported in Norwegian (nb)
PRESIDIO_AVAILABLE_ENTITIES = [
    # Norwegian specific entities
    "NO_FODSELSNUMMER",  # Norwegian national identity number
    "NO_PHONE_NUMBER",   # Norwegian phone numbers
    "NO_ADDRESS",        # Norwegian home addresses
    "NO_BANK_ACCOUNT",   # Norwegian bank account numbers
    "NO_COMPANY_NUMBER", # Norwegian organization numbers
    "NO_LICENSE_PLATE",  # Norwegian license plates

    # General entities that work in any language
    "EMAIL_ADDRESS",     # Email addresses
    "CRYPTO",            # Cryptocurrency addresses
    "DATE_TIME",         # Dates and timestamps
    "IBAN_CODE",         # International Bank Account Number
    "IP_ADDRESS",        # IPv4 or IPv6 address
    "URL",               # Uniform Resource Locator
    "MEDICAL_LICENSE",   # Medical license numbers
    "PERSON",            # Person names (via spaCy/NER)
    "ORGANIZATION",      # Organization names (via spaCy/NER)
    "LOCATION"           # Locations (via spaCy/NER)
]
