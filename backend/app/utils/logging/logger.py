"""Centralized logging configuration for the application.
This module sets up application-wide logging using Python's logging module.
It configures both console and file logging with UTF-8 encoding.
It also provides helper functions to log messages, replacing special Unicode
characters with their textual equivalents to avoid encoding issues.
"""

import os
import logging
import sys
from logging.handlers import RotatingFileHandler

from backend.app.utils.constant.constant import ERROR_WORD, WARNING_WORD

# Create the logs directory if it does not exist
os.makedirs("app/logs/app_log", exist_ok=True)

"""This class extends the built-in logging.Formatter to ensure that
all log messages are properly encoded in UTF-8, handling any special characters that
might otherwise cause encoding issues.
"""


class Utf8Formatter(logging.Formatter):
    """
    A custom logging formatter that ensures log messages are encoded correctly.

    Methods:
        formatMessage(record)
            Formats the log record to a string while ensuring proper encoding.

    Parameters (for methods):
        record (logging.LogRecord): A log record instance containing logging information.

    Returns:
        str: The formatted log message.
    """

    def formatMessage(self, record):
        """
        Format the log message for the given log record.

        Parameters:
            record (logging.LogRecord): The log record containing all pertinent logging information.

        Returns:
            str: The formatted log message.
        """
        # Call the parent class's method to format the message correctly.
        return super().formatMessage(record)


"""The following configuration sets up logging for the application.
It configures both console logging (via sys.stdout) and file logging using a rotating file handler.
This ensures that log files do not exceed 10 MB and that up to 5 backup files are maintained.
"""
logging.basicConfig(
    level=logging.INFO,  # Set the logging level to INFO
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",  # Define the log format
    handlers=[
        logging.StreamHandler(stream=sys.stdout),  # Log to standard output
        RotatingFileHandler(
            "app/logs/app_log/app.log",  # Path to the log file
            maxBytes=10485760,  # Limit log file size to 10 MB
            backupCount=5,  # Keep up to 5 backup log files
            encoding='utf-8'  # Ensure UTF-8 encoding is used
        )
    ]
)

"""This creates a default logger for document processing within the application.
It ensures that any logs relating to document processing are tagged and handled using this logger.
"""
default_logger = logging.getLogger("document_processing")
default_logger.setLevel(logging.INFO)  # Set the default logger to handle INFO level messages and above

"""Logs an informational message after replacing specific Unicode characters
with their corresponding text equivalents. This prevents encoding issues during logging.

Parameters:
    message (str): The message to log.
    *args: Variable length argument list for logger formatting.
    **kwargs: Arbitrary keyword arguments for logger formatting.

Returns:
    None.
"""


def log_info(message, *args, **kwargs):
    # Replace special Unicode characters in the message with text equivalents for error and warning symbols.
    safe_message = message.replace("❌", ERROR_WORD).replace("⚠️", WARNING_WORD)
    # Log the processed (safe) message using the default logger at the INFO level.
    default_logger.info(safe_message, *args, **kwargs)


"""Logs an error message after replacing specific Unicode symbols with their
textual equivalent, ensuring that no encoding errors occur during logging.

Parameters:
    message (str): The message to log.
    *args: Variable length argument list for logger formatting.
    **kwargs: Arbitrary keyword arguments for logger formatting.

Returns:
    None.
"""


def log_error(message, *args, **kwargs):
    # Replace specific Unicode and text markers in the message with the defined error text.
    safe_message = message.replace("[OK]", ERROR_WORD).replace("❌", ERROR_WORD).replace("⚠️", WARNING_WORD)
    # Log the processed message using the default logger at the ERROR level.
    default_logger.error(safe_message, *args, **kwargs)


"""Logs a warning message after replacing specific Unicode symbols with
their textual equivalent to avoid encoding issues.

Parameters:
    message (str): The message to log.
    *args: Variable length argument list for logger formatting.
    **kwargs: Arbitrary keyword arguments for logger formatting.

Returns:
    None.
"""


def log_warning(message, *args, **kwargs):
    # Replace specific Unicode and text markers in the message with the defined warning text.
    safe_message = message.replace("[OK]", WARNING_WORD).replace("❌", ERROR_WORD).replace("⚠️", WARNING_WORD)
    # Log the processed message using the default logger at the WARNING level.
    default_logger.warning(safe_message, *args, **kwargs)


"""Logs a debug message after replacing specific markers with debug-specific text.
Note: Debug messages are logged at the INFO level in this configuration.

Parameters:
    message (str): The message to log.
    *args: Variable length argument list for logger formatting.
    **kwargs: Arbitrary keyword arguments for logger formatting.

Returns:
    None.
"""


def log_debug(message, *args, **kwargs):
    # Replace specific markers in the message with "[DEBUG]" for clarity.
    safe_message = message.replace("[OK]", "[DEBUG]").replace("❌", ERROR_WORD).replace("⚠️", WARNING_WORD)
    # Log the processed message using the default logger at the INFO level (used for debug messages).
    default_logger.info(safe_message, *args, **kwargs)


# Export only the specified names to be available when importing this module.
__all__ = ["default_logger", "log_info", "log_error", "log_warning", "log_debug"]
