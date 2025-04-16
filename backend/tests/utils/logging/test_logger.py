"""
Unit tests for logger.py module.

This test file covers the Utf8Formatter class and logging utility functions with both positive
and negative test cases to ensure proper functionality and error handling.
"""

import logging
import os
import sys
import unittest
from logging.handlers import RotatingFileHandler
from unittest.mock import patch, MagicMock

# Import the module to be tested
from backend.app.utils.logging.logger import (
    Utf8Formatter,
    default_logger,
    log_info,
    log_error,
    log_warning,
    log_debug,
    ERROR_WORD,
    WARNING_WORD
)


class TestUtf8Formatter(unittest.TestCase):
    """Test cases for Utf8Formatter class."""

    def test_format_message(self):
        """Test formatMessage method of Utf8Formatter."""

        # Create a formatter instance
        formatter = Utf8Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

        # Create a log record
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test_path",
            lineno=42,
            msg="Test message with special chars: ñ, é, ü",
            args=(),
            exc_info=None
        )

        # Manually set required attributes since formatMessage doesn't compute them automatically.
        record.asctime = "2022-01-01 00:00:00"

        # Ensure the record has a "message" attribute.
        record.message = record.getMessage()

        # Format the message
        formatted_message = formatter.formatMessage(record)

        # Verify the message is formatted correctly
        self.assertIn("test_logger", formatted_message)
        self.assertIn("Test message with special chars: ñ, é, ü", formatted_message)
        self.assertIn("2022-01-01 00:00:00", formatted_message)


class TestLoggingConfiguration(unittest.TestCase):
    """Test cases for logging configuration."""

    @patch('os.makedirs')
    def test_log_directory_creation(self, mock_makedirs):
        """Test that the log directory is created if it doesn't exist."""

        import importlib
        import sys
        importlib.reload(sys.modules['backend.app.utils.logging.logger'])
        mock_makedirs.assert_called_once_with("app/logs/app_log", exist_ok=True)

    @patch('logging.basicConfig')
    def test_logging_configuration(self, mock_basic_config):
        """Test that logging is configured correctly."""

        import importlib
        import sys
        importlib.reload(sys.modules['backend.app.utils.logging.logger'])
        mock_basic_config.assert_called_once()

        args, kwargs = mock_basic_config.call_args
        self.assertEqual(kwargs['level'], logging.INFO)
        self.assertEqual(kwargs['format'], "%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        self.assertEqual(len(kwargs['handlers']), 2)
        self.assertTrue(any(isinstance(h, logging.StreamHandler) for h in kwargs['handlers']))
        self.assertTrue(any(isinstance(h, RotatingFileHandler) for h in kwargs['handlers']))

        rotating_handler = next(h for h in kwargs['handlers'] if isinstance(h, RotatingFileHandler))
        self.assertEqual(rotating_handler.baseFilename, os.path.abspath("app/logs/app_log/app.log"))
        self.assertEqual(rotating_handler.maxBytes, 10485760)
        self.assertEqual(rotating_handler.backupCount, 5)
        self.assertEqual(rotating_handler.encoding, 'utf-8')

    def test_default_logger_configuration(self):
        """Test that the default logger is configured correctly."""

        self.assertEqual(default_logger.name, "document_processing")
        self.assertEqual(default_logger.level, logging.INFO)


class TestLogInfo(unittest.TestCase):
    """Test cases for log_info function."""

    @patch('backend.app.utils.logging.logger.default_logger')
    def test_log_info_basic(self, mock_logger):
        log_info("This is a test message")
        mock_logger.info.assert_called_once_with("This is a test message")

    @patch('backend.app.utils.logging.logger.default_logger')
    def test_log_info_with_unicode_replacements(self, mock_logger):
        log_info("Test with error symbol ❌ and warning symbol ⚠️")
        mock_logger.info.assert_called_once_with(
            f"Test with error symbol {ERROR_WORD} and warning symbol {WARNING_WORD}")

    @patch('backend.app.utils.logging.logger.default_logger')
    def test_log_info_with_args(self, mock_logger):
        log_info("Value: %s, Number: %d", "test", 42)
        mock_logger.info.assert_called_once_with("Value: %s, Number: %d", "test", 42)

    @patch('backend.app.utils.logging.logger.default_logger')
    def test_log_info_with_kwargs(self, mock_logger):
        log_info("Test message", extra={"key": "value"})
        mock_logger.info.assert_called_once_with("Test message", extra={"key": "value"})

    @patch('backend.app.utils.logging.logger.default_logger')
    def test_log_info_with_mixed_unicode(self, mock_logger):
        log_info("Success ✅, Error ❌, Warning ⚠️")
        mock_logger.info.assert_called_once_with(f"Success ✅, Error {ERROR_WORD}, Warning {WARNING_WORD}")


class TestLogError(unittest.TestCase):
    """Test cases for log_error function."""

    @patch('backend.app.utils.logging.logger.default_logger')
    def test_log_error_basic(self, mock_logger):
        log_error("This is an error message")
        mock_logger.error.assert_called_once_with("This is an error message")

    @patch('backend.app.utils.logging.logger.default_logger')
    def test_log_error_with_unicode_replacements(self, mock_logger):
        log_error("Error symbol ❌ and warning symbol ⚠️")
        mock_logger.error.assert_called_once_with(f"Error symbol {ERROR_WORD} and warning symbol {WARNING_WORD}")

    @patch('backend.app.utils.logging.logger.default_logger')
    def test_log_error_with_ok_replacement(self, mock_logger):
        log_error("Status: [OK]")
        mock_logger.error.assert_called_once_with(f"Status: {ERROR_WORD}")

    @patch('backend.app.utils.logging.logger.default_logger')
    def test_log_error_with_args(self, mock_logger):
        log_error("Error in %s: %d", "function", 42)
        mock_logger.error.assert_called_once_with("Error in %s: %d", "function", 42)

    @patch('backend.app.utils.logging.logger.default_logger')
    def test_log_error_with_kwargs(self, mock_logger):
        log_error("Error message", extra={"key": "value"})
        mock_logger.error.assert_called_once_with("Error message", extra={"key": "value"})

    @patch('backend.app.utils.logging.logger.default_logger')
    def test_log_error_with_multiple_replacements(self, mock_logger):
        log_error("Status: [OK], Error: ❌, Warning: ⚠️")
        expected_message = f"Status: {ERROR_WORD}, Error: {ERROR_WORD}, Warning: {WARNING_WORD}"
        mock_logger.error.assert_called_once_with(expected_message)


class TestLogWarning(unittest.TestCase):
    """Test cases for log_warning function."""

    @patch('backend.app.utils.logging.logger.default_logger')
    def test_log_warning_basic(self, mock_logger):
        log_warning("This is a warning message")
        mock_logger.warning.assert_called_once_with("This is a warning message")

    @patch('backend.app.utils.logging.logger.default_logger')
    def test_log_warning_with_unicode_replacements(self, mock_logger):
        log_warning("Error symbol ❌ and warning symbol ⚠️")
        mock_logger.warning.assert_called_once_with(f"Error symbol {ERROR_WORD} and warning symbol {WARNING_WORD}")

    @patch('backend.app.utils.logging.logger.default_logger')
    def test_log_warning_with_ok_replacement(self, mock_logger):
        log_warning("Status: [OK]")
        mock_logger.warning.assert_called_once_with(f"Status: {WARNING_WORD}")

    @patch('backend.app.utils.logging.logger.default_logger')
    def test_log_warning_with_args(self, mock_logger):
        log_warning("Warning in %s: %d", "function", 42)
        mock_logger.warning.assert_called_once_with("Warning in %s: %d", "function", 42)

    @patch('backend.app.utils.logging.logger.default_logger')
    def test_log_warning_with_kwargs(self, mock_logger):
        log_warning("Warning message", extra={"key": "value"})
        mock_logger.warning.assert_called_once_with("Warning message", extra={"key": "value"})

    @patch('backend.app.utils.logging.logger.default_logger')
    def test_log_warning_with_multiple_replacements(self, mock_logger):
        log_warning("Status: [OK], Error: ❌, Warning: ⚠️")
        expected_message = f"Status: {WARNING_WORD}, Error: {ERROR_WORD}, Warning: {WARNING_WORD}"
        mock_logger.warning.assert_called_once_with(expected_message)


class TestLogDebug(unittest.TestCase):
    """Test cases for log_debug function."""

    @patch('backend.app.utils.logging.logger.default_logger')
    def test_log_debug_basic(self, mock_logger):
        log_debug("This is a debug message")
        mock_logger.info.assert_called_once_with("This is a debug message")

    @patch('backend.app.utils.logging.logger.default_logger')
    def test_log_debug_with_unicode_replacements(self, mock_logger):
        log_debug("Error symbol ❌ and warning symbol ⚠️")
        mock_logger.info.assert_called_once_with(f"Error symbol {ERROR_WORD} and warning symbol {WARNING_WORD}")

    @patch('backend.app.utils.logging.logger.default_logger')
    def test_log_debug_with_ok_replacement(self, mock_logger):
        log_debug("Status: [OK]")
        mock_logger.info.assert_called_once_with("Status: [DEBUG]")

    @patch('backend.app.utils.logging.logger.default_logger')
    def test_log_debug_with_args(self, mock_logger):
        log_debug("Debug in %s: %d", "function", 42)
        mock_logger.info.assert_called_once_with("Debug in %s: %d", "function", 42)

    @patch('backend.app.utils.logging.logger.default_logger')
    def test_log_debug_with_kwargs(self, mock_logger):
        log_debug("Debug message", extra={"key": "value"})
        mock_logger.info.assert_called_once_with("Debug message", extra={"key": "value"})

    @patch('backend.app.utils.logging.logger.default_logger')
    def test_log_debug_with_multiple_replacements(self, mock_logger):
        log_debug("Status: [OK], Error: ❌, Warning: ⚠️")
        expected_message = f"Status: [DEBUG], Error: {ERROR_WORD}, Warning: {WARNING_WORD}"
        mock_logger.info.assert_called_once_with(expected_message)


class TestIntegration(unittest.TestCase):
    """Integration tests for logger module."""

    def setUp(self):
        # Create a temporary logger for testing
        self.test_logger = logging.getLogger("test_integration_logger")
        self.test_logger.setLevel(logging.INFO)

        # Create a mock handler and set its level to a concrete value.
        self.mock_handler = MagicMock()
        self.mock_handler.level = logging.INFO
        self.test_logger.addHandler(self.mock_handler)

        # Save original default_logger and replace it with our test logger
        self.original_logger = sys.modules['backend.app.utils.logging.logger'].default_logger
        sys.modules['backend.app.utils.logging.logger'].default_logger = self.test_logger

    def tearDown(self):
        # Restore original logger
        sys.modules['backend.app.utils.logging.logger'].default_logger = self.original_logger

    def test_integration_log_info(self):
        log_info("Integration test message")
        self.mock_handler.handle.assert_called_once()
