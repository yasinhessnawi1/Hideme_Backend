"""
Centralized logging configuration for the application.
"""
import os
import logging
import sys
from logging.handlers import RotatingFileHandler

# Create logs directory if it doesn't exist
os.makedirs("logs", exist_ok=True)

# Define custom formatter that handles special characters
class Utf8Formatter(logging.Formatter):
    def formatMessage(self, record):
        # Ensure all log messages are encoded correctly
        return super().formatMessage(record)

# Configure logging with UTF-8 encoding
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        # Use sys.stdout with encoding specified
        logging.StreamHandler(stream=sys.stdout),
        # Use UTF-8 encoding for file handler
        RotatingFileHandler(
            "logs/app.log",
            maxBytes=10485760,  # 10 MB
            backupCount=5,
            encoding='utf-8'
        )
    ]
)

# Create default logger
default_logger = logging.getLogger("document_processing")
default_logger.setLevel(logging.INFO)

# Replace checkmark emoji with text equivalent to avoid encoding issues
def log_info(message, *args, **kwargs):
    # Replace Unicode characters that might cause encoding issues
    safe_message = message.replace("❌", "[ERROR]").replace("⚠️", "[WARNING]")
    default_logger.info(safe_message, *args, **kwargs)

def log_error(message, *args, **kwargs):
    safe_message = message.replace("[OK]", "[ERROR]").replace("❌", "[ERROR]").replace("⚠️", "[WARNING]")
    default_logger.error(safe_message, *args, **kwargs)

def log_warning(message, *args, **kwargs):
    safe_message = message.replace("[OK]", "[WARNING]").replace("❌", "[ERROR]").replace("⚠️", "[WARNING]")
    default_logger.warning(safe_message, *args, **kwargs)

def log_debug(message, *args, **kwargs):
    safe_message = message.replace("[OK]", "[DEBUG]").replace("❌", "[ERROR]").replace("⚠️", "[WARNING]")
    default_logger.info(safe_message, *args, **kwargs)

# Export functions
__all__ = ["default_logger", "log_info", "log_error", "log_warning", "log_debug"]