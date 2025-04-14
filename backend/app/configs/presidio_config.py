"""
Configuration for Presidio entity detection with Norwegian support.
"""
import os

# Base directory of the project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Default language - set to Norwegian
DEFAULT_LANGUAGE = "nb"

# Entity types to detect by default
# Only include entities supported in Norwegian (nb)
PRESIDIO_AVAILABLE_ENTITIES = [
    # Norwegian specific entities
    "NO_FODSELSNUMMER_P",  # Norwegian national identity number
    "NO_PHONE_NUMBER_P",  # Norwegian phone numbers
    "NO_ADDRESS_P",  # Norwegian home addresses
    "NO_BANK_ACCOUNT_P",  # Norwegian bank account numbers
    "NO_COMPANY_NUMBER_P",  # Norwegian organization numbers
    "NO_LICENSE_PLATE_P",  # Norwegian license plates

    # General entities that work in any language
    "EMAIL_ADDRESS_P",  # Email addresses
    "CRYPTO_P",  # Cryptocurrency addresses
    "DATE_TIME_P",  # Dates and timestamps
    "IBAN_CODE_P",  # International Bank Account Number
    "IP_ADDRESS_P",  # IPv4 or IPv6 address
    "URL_P",  # Uniform Resource Locator
    "MEDICAL_LICENSE_P",  # Medical license numbers
    "PERSON_P",  # Person names (via spaCy/NER)
    "ORGANIZATION_P",  # Organization names (via spaCy/NER)
    "LOCATION_P"  # Locations (via spaCy/NER)
]
