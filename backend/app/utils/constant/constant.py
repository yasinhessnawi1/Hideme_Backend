"""
Constants for the document processing application.

This module defines configuration constants organized into several categories:
1. Environment and network settings (allowed origins).
2. Cache settings (TTL values for different caches).
3. Default timeouts for various operations.
4. Sensitive fields and metadata configuration.
5. File handling constants including chunk size, file size limits, MIME types,
   and file signatures.
6. Log and error handling constants, including patterns for detecting sensitive data
   and error messages.
"""

import os
from typing import Set

# Allowed origins for CORS, read from the environment or default values.
ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:8000,https://www.hidemeai.com,http://localhost:5173",
).split(",")

# Cache TTL configuration in seconds for different components.
CACHE_TTL = {
    "engines": 86400,  # 24 hours for static configuration.
    "entities": 3600,  # 1 hour for entity lists.
    "entity_examples": 86400,  # 24 hours for static examples.
    "detector_status": 60,  # 1 minute for detector status.
}

# Additional specific cache TTL values.
STATUS_CACHE_TTL = 60
HEALTH_CACHE_TTL = 60
METRICS_CACHE_TTL = 60


# Timeout for extraction operations.
DEFAULT_EXTRACTION_TIMEOUT = 60.0  # 60 seconds
# Timeout for acquiring thread locks.
DEFAULT_LOCK_TIMEOUT = 30.0  # 30 seconds
# Timeout for acquiring asyncio locks.
DEFAULT_ASYNC_LOCK_TIMEOUT = 30.0  # 30 seconds

# List of fields considered sensitive and to be minimized.
SENSITIVE_FIELDS = ["content", "meta", "original", "raw", "owner", "source"]
# Default metadata fields to retain.
DEFAULT_METADATA_FIELDS: Set[str] = {
    "total_document_pages",
    "empty_pages",
    "content_pages",
}

# Filename for the Gliner configuration.
GLINER_CONFIG_FILENAME = "gliner_config.json"
# Default content type for binary data.
DEFAULT_CONTENT_TYPE = "application/octet-stream"
# Media type for JSON responses.
JSON_MEDIA_TYPE = "application/json"

# File read chunk size.
CHUNK_SIZE = 64 * 1024  # 64KB
# Multi-file validation: maximum number of files allowed.
MAX_FILES_COUNT = 10
# Single file validation: maximum PDF file size (10 MB).
MAX_PDF_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
# MIME type for PDF files.
APPLICATION_WORD = "application/pdf"
# Allowed MIME types for PDF files.
ALLOWED_MIME_TYPES = {
    "pdf": {APPLICATION_WORD, "application/x-pdf", "application/octet-stream"}
}
# File signatures (magic bytes) for supported file types.
FILE_SIGNATURES = {"pdf": [(b"%PDF", 0)]}
# Mapping from file extension to MIME type.
EXTENSION_TO_MIME = {".pdf": APPLICATION_WORD}

# Text strings for log messages.
ERROR_WORD = "[ERROR]"
WARNING_WORD = "[WARNING]"
# Default timeout values for batch processing.
DEFAULT_BATCH_TIMEOUT = 1200.0
DEFAULT_ITEM_TIMEOUT = 1200.0

# File extension used for processing record files.
JSON_CONSTANT = ".jsonl"

# File path for detailed error logs, read from the environment.
ERROR_LOG_PATH = os.environ.get(
    "ERROR_LOG_PATH", "app/logs/error_logs/detailed_errors.log"
)
# Flag to indicate whether to use JSON logging for errors.
USE_JSON_LOGGING = os.environ.get("ERROR_JSON_LOGGING", "true").lower() == "true"
# Flag to enable or disable distributed tracing.
ENABLE_DISTRIBUTED_TRACING = (
    os.environ.get("ENABLE_DISTRIBUTED_TRACING", "false").lower() == "true"
)
# Service name, defaulting to 'document_processing' if not provided.
SERVICE_NAME = os.environ.get("SERVICE_NAME", "document_processing")
# Standard safe message to display when error details are redacted.
SAFE_MESSAGE = "Error details have been redacted for security."

# Regex pattern for detecting email addresses.
EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
# List of keywords considered sensitive.
SENSITIVE_KEYWORDS = [
    "password",
    "secret",
    "key",
    "token",
    "credential",
    "auth",
    "ssn",
    "social",
    "credit",
    "card",
    "cvv",
    "secure",
    "private",
    "passport",
    "license",
    "national",
    "health",
    "insurance",
    "bank",
    "fodselsnummer",
    "personnummer",
    "address",
    "phone",
    "email",
    "api",
    "access_token",
    "refresh_token",
    "bearer",
    "authorization",
    "admin",
    "username",
    "login",
    "signin",
    "certificate",
    "privkey",
]
# List of URL patterns for recognizing and redacting sensitive URLs.
URL_PATTERNS = [
    r"https?://[^\s/$.?#].[^\s]*",  # Standard URLs.
    r"redis://[^\s]*",  # Redis URLs.
    r"mongodb://[^\s]*",  # MongoDB URLs.
    r"postgresql://[^\s]*",  # PostgreSQL URLs.
    r"mysql://[^\s]*",  # MySQL URLs.
    r"jdbc:[^\s]*",  # JDBC URLs.
    r"file://[^\s]*",  # File URLs.
    r"ftp://[^\s]*",  # FTP URLs.
    r"s3://[^\s]*",  # S3 URLs.
]

# Mapping from exception types to user-friendly error messages.
ERROR_TYPE_MESSAGES = {
    "ValueError": "Invalid value provided",
    "TypeError": "Incorrect data type",
    "KeyError": "Required key not found",
    "IndexError": "Index out of range",
    "FileNotFoundError": "Required file not found",
    "PermissionError": "Permission denied",
    "IOError": "I/O operation failed",
    "OSError": "Operating system error",
    "ConnectionError": "Connection failed",
    "TimeoutError": "Operation timed out",
    "json.JSONDecodeError": "Invalid JSON format",
    "ZeroDivisionError": "Division by zero error",
    "AttributeError": "Missing required attribute",
    "ImportError": "Required module not available",
    "ModuleNotFoundError": "Required module not found",
    "MemoryError": "Insufficient memory to complete operation",
    "RuntimeError": "Runtime execution error",
    "asyncio.TimeoutError": "Asynchronous operation timed out",
    "UnicodeDecodeError": "Character encoding error",
    "UnicodeEncodeError": "Character encoding error",
    "NotImplementedError": "Feature not implemented",
    "Exception": "An error occurred",
}
