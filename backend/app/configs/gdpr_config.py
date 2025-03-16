# backend/app/configs/gdpr_config.py
"""
GDPR configuration settings for document processing.

This module defines GDPR-related configuration settings for the document processing system,
including retention periods, processing purposes, and data minimization rules.
"""

# Retention periods (in seconds)
TEMP_FILE_RETENTION_SECONDS = 3600  # 1 hour
REDACTED_FILE_RETENTION_SECONDS = 86400  # 24 hours

# Legal basis for processing
LEGAL_BASIS = "legitimate_interest"
LEGITIMATE_INTEREST_PURPOSE = "Document security and sensitive information redaction"

# Data minimization configuration
DATA_MINIMIZATION_RULES = {
    "keep_metadata": False,  # Whether to keep document metadata
    "strip_document_authors": True,  # Whether to strip author information
    "strip_timestamp": True,  # Whether to strip creation/modification timestamps
    "required_fields_only": True,  # Whether to keep only required fields for processing
}

# Anonymization configuration
ANONYMIZATION_CONFIG = {
    "replace_with_tags": True,  # Replace sensitive information with type tags
    "redaction_color": (0, 0, 0),  # Black redaction boxes
    "add_labels": False,  # Don't add labels to redacted areas
}

# Processing record configuration
PROCESSING_RECORDS = {
    "keep_records": True,  # Whether to keep processing records
    "record_retention_days": 90,  # How long to keep processing records (for Article 30)
    "include_processing_stats": True,  # Whether to include processing statistics
}

# Data subject rights support
SUBJECT_RIGHTS_SUPPORT = {
    "right_to_access": True,
    "right_to_be_forgotten": True,
    "right_to_rectification": False,  # Not applicable for this system
    "right_to_portability": False,  # Not applicable for this system
}

# GDPR documentation
GDPR_DOCUMENTATION = {
    "data_controller": "Organization Name",
    "processing_purpose": "Detection and redaction of sensitive information in documents",
    "retention_period": "Temporary processing only, no long-term storage",
    "legal_basis": "Article 6(1)(f) - legitimate interests",
    "technical_measures": [
        "Data minimization",
        "Privacy by design",
        "Secure temporary file handling",
        "Processing records",
        "Proper data deletion"
    ]
}