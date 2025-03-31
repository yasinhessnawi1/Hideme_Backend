"""
Centralized logging configuration for the application.
"""
import os
import logging
import sys
from logging.handlers import RotatingFileHandler

# Create logs directory if it doesn't exist
os.makedirs("app/logs/app_log", exist_ok=True)

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
        # check if the directory exists otherwise create it
        RotatingFileHandler(
            "app/logs/app_log/app.log",
            maxBytes=10485760,  # 10 MB
            backupCount=5,
            encoding='utf-8'
        )
    ]
)

# Create default logger
default_logger = logging.getLogger("document_processing")
default_logger.setLevel(logging.INFO)

ERROR_WORD = "[ERROR]"
WARNING_WORD = "[WARNING]"

# Replace checkmark emoji with text equivalent to avoid encoding issues
def log_info(message, *args, **kwargs):
    # Replace Unicode characters that might cause encoding issues
    safe_message = message.replace("❌", ERROR_WORD).replace("⚠️", WARNING_WORD)
    default_logger.info(safe_message, *args, **kwargs)

def log_error(message, *args, **kwargs):
    safe_message = message.replace("[OK]", ERROR_WORD).replace("❌", ERROR_WORD).replace("⚠️", WARNING_WORD)
    default_logger.error(safe_message, *args, **kwargs)

def log_warning(message, *args, **kwargs):
    safe_message = message.replace("[OK]", WARNING_WORD).replace("❌", ERROR_WORD).replace("⚠️", WARNING_WORD)
    default_logger.warning(safe_message, *args, **kwargs)

def log_debug(message, *args, **kwargs):
    safe_message = message.replace("[OK]", "[DEBUG]").replace("❌", ERROR_WORD).replace("⚠️", WARNING_WORD)
    default_logger.info(safe_message, *args, **kwargs)

# Export functions
__all__ = ["default_logger", "log_info", "log_error", "log_warning", "log_debug"]