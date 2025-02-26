ENTITIES_CONFIG = {
    # (Your custom recognizer configurations, if any, can be placed here)
    # Example:
    "NO_FODSELSNUMMER": {
        "patterns": [
            {"name": "Fodselsnummer Pattern", "regex": r"\b\d{6}\s?\d{5}\b", "score": 0.9}
        ]
    },
    "NO_PHONE_NUMBER": {
        "patterns": [
            {"name": "Norwegian Phone Number Pattern", "regex": r"\b(?:\+47\s?)?(\d{2}\s?\d{2}\s?\d{2}\s?\d{2})\b",
             "score": 0.95}
        ]
    },
    "NO_ADDRESS": {
        "patterns": [
            {"name": "Norwegian Address Pattern",
             "regex": (
                 r"(\b(?:[A-Za-zÆØÅæøå]+\s){1,4}\d{1,4}(?:,\s)?\d{4}\s[A-Za-zÆØÅæøå]+)|"
                 r"(\bPostboks\s?\d{1,5}(?:,\s)?\d{4}\s[A-Za-zÆØÅæøå]+)|"
                 r"(\b\d{4}\s[A-Za-zÆØÅæøå]+\b)|"
                 r"(\b[A-Za-zÆØÅæøå]+\s\d{1,4},?\s?\d{4}\s[A-Za-zÆØÅæøå]+\b)"
             ),
             "score": 0.98
             }
        ]
    }
}

DEFAULT_LANGUAGE = "nb"
SPACY_MODEL = "nb_core_news_lg"
NER_MODEL_DIR_NAME = "kushtrim_norbert3_large_ner"
NER_MODEL = "kushtrim/norbert3-large-ner"
# List of requested entity types based on your table.
REQUESTED_ENTITIES = [
    # General entities
    # "CREDIT_CARD",  # A credit card number between 12 and 19 digits.
    "CRYPTO",  # A crypto wallet (e.g. Bitcoin address).
    "DATE_TIME",  # Dates or time periods.
    "EMAIL_ADDRESS",  # An email address.
    "IBAN_CODE",  # International Bank Account Number.
    "IP_ADDRESS",  # IPv4 or IPv6 address.
    "NRP",  # Nationality, religious or political group.
    "LOCATION",  # Politically/geographically defined location.
    "PERSON",  # Full person name.
    "PHONE_NUMBER",  # Telephone number.
    "MEDICAL_LICENSE",  # Common medical license numbers.
    "URL",  # Uniform Resource Locator.

    # USA Entities
    # "US_BANK_NUMBER",  # 8 to 17 digits.
    # "US_DRIVER_LICENSE",
    # "US_ITIN",  # Nine digits starting with 9 and containing 7 or 8.
    # "US_PASSPORT",  # 9-digit US passport.
    # "US_SSN",  # 9-digit Social Security Number.

    # UK Entities
    # "UK_NHS",  # 10-digit NHS number.
    # "UK_NINO",  # National Insurance Number.

    # Spain Entities
    # "ES_NIF",  # Spanish NIF (Personal tax ID).
    # "ES_NIE",  # Spanish NIE (Foreigners ID).

    # Italy Entities
    # "IT_FISCAL_CODE",  # Italian fiscal code.
    # "IT_DRIVER_LICENSE",
    # "IT_VAT_CODE",
    # "IT_PASSPORT",
    # "IT_IDENTITY_CARD",

    # Poland Entities
    # "PL_PESEL",  # Polish PESEL number.

    # Singapore Entities
    # "SG_NRIC_FIN",  # National Registration ID card.
    # "SG_UEN",  # Unique Entity Number.

    # Australia Entities
    # "AU_ABN",  # Australian Business Number.
    # "AU_ACN",  # Australian Company Number.
    # "AU_TFN",  # Tax File Number.
    # "AU_MEDICARE",  # Medicare number.

    # India Entities
    # "IN_PAN",  # Permanent Account Number.
    # "IN_AADHAAR",  # 12-digit Aadhaar.
    # "IN_VEHICLE_REGISTRATION",
    # "IN_VOTER",  # Voter ID.
    # "IN_PASSPORT",

    # Finland Entity
    # "FI_PERSONAL_IDENTITY_CODE"  # Finnish Personal Identity Code.
]
