# Allowed origins from environment or default
import os

ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:8000,https://www.hidemeai.com,http://localhost:5173"
).split(",")

# Constant for JSON media type
JSON_MEDIA_TYPE = "application/json"

# Cache TTL configuration (in seconds).
CACHE_TTL = {
    "engines": 86400,  # 24 hours for static configuration.
    "entities": 3600,  # 1 hour for entity lists.
    "entity_examples": 86400,  # 24 hours for static examples.
    "detector_status": 60  # 1 minute for detector status.
}

# Define cache TTL values (in seconds).
STATUS_CACHE_TTL = 60
HEALTH_CACHE_TTL = 60
METRICS_CACHE_TTL = 60

DEFAULT_EXTRACTION_TIMEOUT = 60.0  # 60 seconds for extraction operations
DEFAULT_LOCK_TIMEOUT = 30.0  # 30 seconds for lock acquisition

# Constants for configuration filenames to avoid duplicating literals
GLINER_CONFIG_FILENAME = "gliner_config.json"

CHUNK_SIZE = 64 * 1024  # 64KB

# Define constants for text replacements to handle Unicode issues in log messages.
ERROR_WORD = "[ERROR]"
WARNING_WORD = "[WARNING]"

DEFAULT_BATCH_TIMEOUT = 600.0
DEFAULT_ITEM_TIMEOUT = 600.0
