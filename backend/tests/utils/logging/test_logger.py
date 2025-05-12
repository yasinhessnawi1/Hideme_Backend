import logging
import os
import sys
import unittest

from logging.handlers import RotatingFileHandler
from unittest.mock import patch, MagicMock

from backend.app.utils.logging.logger import (
    Utf8Formatter,
    default_logger,
    log_info,
    log_error,
    log_warning,
    log_debug,
    ERROR_WORD,
    WARNING_WORD,
)


# Tests for Utf8Formatter class
class TestUtf8Formatter(unittest.TestCase):
    """Test cases for Utf8Formatter class."""

    # should format record message including special characters
    def test_format_message(
        self,
    ):
        formatter = Utf8Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test_path",
            lineno=42,
            msg="Test message with special chars: ñ, é, ü",
            args=(),
            exc_info=None,
        )

        record.asctime = "2022-01-01 00:00:00"

        record.message = record.getMessage()

        formatted_message = formatter.formatMessage(record)

        self.assertIn("test_logger", formatted_message)

        self.assertIn("Test message with special chars: ñ, é, ü", formatted_message)

        self.assertIn("2022-01-01 00:00:00", formatted_message)


# Tests for logging configuration
class TestLoggingConfiguration(unittest.TestCase):
    """Test cases for logging configuration."""

    # should create log directory if missing
    @patch("os.makedirs")
    def test_log_directory_creation(self, mock_makedirs):
        import importlib

        importlib.reload(sys.modules["backend.app.utils.logging.logger"])

        mock_makedirs.assert_called_once_with("app/logs/app_log", exist_ok=True)

    # should set up basicConfig with correct handlers
    @patch("logging.basicConfig")
    def test_logging_configuration(self, mock_basic_config):
        import importlib

        importlib.reload(sys.modules["backend.app.utils.logging.logger"])

        mock_basic_config.assert_called_once()

        args, kwargs = mock_basic_config.call_args

        self.assertEqual(kwargs["level"], logging.INFO)

        self.assertEqual(
            kwargs["format"], "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )

        self.assertEqual(len(kwargs["handlers"]), 2)

        self.assertTrue(
            any(isinstance(h, logging.StreamHandler) for h in kwargs["handlers"])
        )

        self.assertTrue(
            any(isinstance(h, RotatingFileHandler) for h in kwargs["handlers"])
        )

        rotating_handler = next(
            h for h in kwargs["handlers"] if isinstance(h, RotatingFileHandler)
        )

        self.assertEqual(
            rotating_handler.baseFilename, os.path.abspath("app/logs/app_log/app.log")
        )

        self.assertEqual(rotating_handler.maxBytes, 10485760)

        self.assertEqual(rotating_handler.backupCount, 5)

        self.assertEqual(rotating_handler.encoding, "utf-8")

    # should configure default_logger correctly
    def test_default_logger_configuration(
        self,
    ):
        self.assertEqual(default_logger.name, "document_processing")

        self.assertEqual(default_logger.level, logging.INFO)


# Tests for log_info function
class TestLogInfo(unittest.TestCase):
    """Test cases for log_info function."""

    # should call logger.info with simple message
    @patch("backend.app.utils.logging.logger.default_logger")
    def test_log_info_basic(self, mock_logger):
        log_info("This is a test message")

        mock_logger.info.assert_called_once_with("This is a test message")

    # should replace ❌ and ⚠️ in info messages
    @patch("backend.app.utils.logging.logger.default_logger")
    def test_log_info_with_unicode_replacements(self, mock_logger):
        log_info("Test with error symbol ❌ and warning symbol ⚠️")

        mock_logger.info.assert_called_once_with(
            f"Test with error symbol {ERROR_WORD} and warning symbol {WARNING_WORD}"
        )

    # should pass args through to logger.info
    @patch("backend.app.utils.logging.logger.default_logger")
    def test_log_info_with_args(self, mock_logger):
        log_info("Value: %s, Number: %d", "test", 42)

        mock_logger.info.assert_called_once_with("Value: %s, Number: %d", "test", 42)

    # should pass kwargs through to logger.info
    @patch("backend.app.utils.logging.logger.default_logger")
    def test_log_info_with_kwargs(self, mock_logger):
        log_info("Test message", extra={"key": "value"})

        mock_logger.info.assert_called_once_with("Test message", extra={"key": "value"})

    # should mix plain and replaced unicode symbols
    @patch("backend.app.utils.logging.logger.default_logger")
    def test_log_info_with_mixed_unicode(self, mock_logger):
        log_info("Success ✅, Error ❌, Warning ⚠️")

        mock_logger.info.assert_called_once_with(
            f"Success ✅, Error {ERROR_WORD}, Warning {WARNING_WORD}"
        )


# Tests for log_error function
class TestLogError(unittest.TestCase):
    """Test cases for log_error function."""

    # should call logger.error with simple message
    @patch("backend.app.utils.logging.logger.default_logger")
    def test_log_error_basic(self, mock_logger):
        log_error("This is an error message")

        mock_logger.error.assert_called_once_with("This is an error message")

    # should replace ❌ and ⚠️ in error messages
    @patch("backend.app.utils.logging.logger.default_logger")
    def test_log_error_with_unicode_replacements(self, mock_logger):
        log_error("Error symbol ❌ and warning symbol ⚠️")

        mock_logger.error.assert_called_once_with(
            f"Error symbol {ERROR_WORD} and warning symbol {WARNING_WORD}"
        )

    # should replace [OK] with ERROR_WORD
    @patch("backend.app.utils.logging.logger.default_logger")
    def test_log_error_with_ok_replacement(self, mock_logger):
        log_error("Status: [OK]")

        mock_logger.error.assert_called_once_with(f"Status: {ERROR_WORD}")

    # should pass args through to logger.error
    @patch("backend.app.utils.logging.logger.default_logger")
    def test_log_error_with_args(self, mock_logger):
        log_error("Error in %s: %d", "function", 42)

        mock_logger.error.assert_called_once_with("Error in %s: %d", "function", 42)

    # should pass kwargs through to logger.error
    @patch("backend.app.utils.logging.logger.default_logger")
    def test_log_error_with_kwargs(self, mock_logger):
        log_error("Error message", extra={"key": "value"})

        mock_logger.error.assert_called_once_with(
            "Error message", extra={"key": "value"}
        )

    # should replace multiple unicode symbols
    @patch("backend.app.utils.logging.logger.default_logger")
    def test_log_error_with_multiple_replacements(self, mock_logger):
        log_error("Status: [OK], Error: ❌, Warning: ⚠️")

        expected_message = (
            f"Status: {ERROR_WORD}, Error: {ERROR_WORD}, Warning: {WARNING_WORD}"
        )

        mock_logger.error.assert_called_once_with(expected_message)


# Tests for log_warning function
class TestLogWarning(unittest.TestCase):
    """Test cases for log_warning function."""

    # should call logger.warning with simple message
    @patch("backend.app.utils.logging.logger.default_logger")
    def test_log_warning_basic(self, mock_logger):
        log_warning("This is a warning message")

        mock_logger.warning.assert_called_once_with("This is a warning message")

    # should replace ❌ and ⚠️ in warning messages
    @patch("backend.app.utils.logging.logger.default_logger")
    def test_log_warning_with_unicode_replacements(self, mock_logger):
        log_warning("Error symbol ❌ and warning symbol ⚠️")

        mock_logger.warning.assert_called_once_with(
            f"Error symbol {ERROR_WORD} and warning symbol {WARNING_WORD}"
        )

    # should replace [OK] with WARNING_WORD
    @patch("backend.app.utils.logging.logger.default_logger")
    def test_log_warning_with_ok_replacement(self, mock_logger):
        log_warning("Status: [OK]")

        mock_logger.warning.assert_called_once_with(f"Status: {WARNING_WORD}")

    # should pass args through to logger.warning
    @patch("backend.app.utils.logging.logger.default_logger")
    def test_log_warning_with_args(self, mock_logger):
        log_warning("Warning in %s: %d", "function", 42)

        mock_logger.warning.assert_called_once_with("Warning in %s: %d", "function", 42)

    # should pass kwargs through to logger.warning
    @patch("backend.app.utils.logging.logger.default_logger")
    def test_log_warning_with_kwargs(self, mock_logger):
        log_warning("Warning message", extra={"key": "value"})

        mock_logger.warning.assert_called_once_with(
            "Warning message", extra={"key": "value"}
        )

    # should replace multiple unicode symbols
    @patch("backend.app.utils.logging.logger.default_logger")
    def test_log_warning_with_multiple_replacements(self, mock_logger):
        log_warning("Status: [OK], Error: ❌, Warning: ⚠️")

        expected_message = (
            f"Status: {WARNING_WORD}, Error: {ERROR_WORD}, Warning: {WARNING_WORD}"
        )

        mock_logger.warning.assert_called_once_with(expected_message)


# Tests for log_debug function
class TestLogDebug(unittest.TestCase):
    """Test cases for log_debug function."""

    # should log debug message via info
    @patch("backend.app.utils.logging.logger.default_logger")
    def test_log_debug_basic(self, mock_logger):
        log_debug("This is a debug message")

        mock_logger.info.assert_called_once_with("This is a debug message")

    # should replace ❌ and ⚠️ in debug messages
    @patch("backend.app.utils.logging.logger.default_logger")
    def test_log_debug_with_unicode_replacements(self, mock_logger):
        log_debug("Error symbol ❌ and warning symbol ⚠️")

        mock_logger.info.assert_called_once_with(
            f"Error symbol {ERROR_WORD} and warning symbol {WARNING_WORD}"
        )

    # should replace [OK] with [DEBUG]
    @patch("backend.app.utils.logging.logger.default_logger")
    def test_log_debug_with_ok_replacement(self, mock_logger):
        log_debug("Status: [OK]")

        mock_logger.info.assert_called_once_with("Status: [DEBUG]")

    # should pass args through to logger.info
    @patch("backend.app.utils.logging.logger.default_logger")
    def test_log_debug_with_args(self, mock_logger):
        log_debug("Debug in %s: %d", "function", 42)

        mock_logger.info.assert_called_once_with("Debug in %s: %d", "function", 42)

    # should pass kwargs through to logger.info
    @patch("backend.app.utils.logging.logger.default_logger")
    def test_log_debug_with_kwargs(self, mock_logger):
        log_debug("Debug message", extra={"key": "value"})

        mock_logger.info.assert_called_once_with(
            "Debug message", extra={"key": "value"}
        )

    # should replace multiple unicode and OK symbols
    @patch("backend.app.utils.logging.logger.default_logger")
    def test_log_debug_with_multiple_replacements(self, mock_logger):
        log_debug("Status: [OK], Error: ❌, Warning: ⚠️")

        expected_message = (
            f"Status: [DEBUG], Error: {ERROR_WORD}, Warning: {WARNING_WORD}"
        )

        mock_logger.info.assert_called_once_with(expected_message)


# Integration tests for logger module
class TestIntegration(unittest.TestCase):
    """Integration tests for logger module."""

    # set up a test logger and handler
    def setUp(
        self,
    ):
        self.test_logger = logging.getLogger("test_integration_logger")

        self.test_logger.setLevel(logging.INFO)

        self.mock_handler = MagicMock()

        self.mock_handler.level = logging.INFO

        self.test_logger.addHandler(self.mock_handler)

        self.original_logger = sys.modules[
            "backend.app.utils.logging.logger"
        ].default_logger

        sys.modules["backend.app.utils.logging.logger"].default_logger = (
            self.test_logger
        )

    # restore original default_logger
    def tearDown(
        self,
    ):
        sys.modules["backend.app.utils.logging.logger"].default_logger = (
            self.original_logger
        )

    # should route log_info through handler
    def test_integration_log_info(
        self,
    ):
        log_info("Integration test message")

        self.mock_handler.handle.assert_called_once()
