import json
import os
import time
import unittest
import uuid
from unittest.mock import patch, mock_open
from fastapi import HTTPException

from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler

# Define test constants.
TEST_ERROR_TYPE_MESSAGES = {
    'ValueError': 'Invalid value provided',
    'TypeError': 'Invalid type provided',
    'FileNotFoundError': 'File not found',
    'Exception': 'An unexpected error occurred'
}

TEST_SAFE_MESSAGE = 'Error details have been logged'

TEST_ERROR_LOG_PATH = '/var/log/app/errors.log'

TEST_SERVICE_NAME = 'test-service'

TEST_SENSITIVE_KEYWORDS = ['password', 'secret', 'token', 'key', 'credential']

TEST_URL_PATTERNS = [r'https?://[^\s]+', r'ftp://[^\s]+']

TEST_EMAIL_PATTERN = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'


class TestSecurityAwareErrorHandler(unittest.TestCase):
    """Unit tests for SecurityAwareErrorHandler."""

    def setUp(self):
        # Patch uuid.uuid4 to return a predictable UUID.
        self.uuid_patcher = patch(
            'uuid.uuid4',
            return_value=uuid.UUID('12345678-1234-5678-1234-567812345678')
        )

        self.mock_uuid = self.uuid_patcher.start()

        # Patch time.time to return a predictable timestamp.
        self.time_patcher = patch(
            'time.time',
            return_value=1617235678.0
        )

        self.mock_time = self.time_patcher.start()

        # Patch logging functions.
        self.log_error_patcher = patch(
            'backend.app.utils.system_utils.error_handling.log_error'
        )

        self.mock_log_error = self.log_error_patcher.start()

        self.log_warning_patcher = patch(
            'backend.app.utils.system_utils.error_handling.log_warning'
        )

        self.mock_log_warning = self.log_warning_patcher.start()

        # Patch os.makedirs so no actual directories are created.
        self.makedirs_patcher = patch('os.makedirs')

        self.mock_makedirs = self.makedirs_patcher.start()

        # Patch builtins.open (for file logging in _log_detailed_error).
        self.open_patcher = patch('builtins.open', mock_open())

        self.mock_open = self.open_patcher.start()

        # Patch traceback.format_exc to return a fixed string.
        self.format_exc_patcher = patch(
            'traceback.format_exc',
            return_value="Traceback: test stack trace"
        )

        self.mock_format_exc = self.format_exc_patcher.start()

        # Patch constants via patch.multiple using the module path.
        self.constants_patcher = patch.multiple(
            'backend.app.utils.system_utils.error_handling',
            ERROR_TYPE_MESSAGES=TEST_ERROR_TYPE_MESSAGES,
            SAFE_MESSAGE=TEST_SAFE_MESSAGE,
            ERROR_LOG_PATH=TEST_ERROR_LOG_PATH,
            SERVICE_NAME=TEST_SERVICE_NAME,
            USE_JSON_LOGGING=False,
            ENABLE_DISTRIBUTED_TRACING=False,
            SENSITIVE_KEYWORDS=TEST_SENSITIVE_KEYWORDS,
            URL_PATTERNS=TEST_URL_PATTERNS,
            EMAIL_PATTERN=TEST_EMAIL_PATTERN
        )

        self.constants = self.constants_patcher.__enter__()

        # Patch _sanitize_error_message to produce predictable output.
        self.sanitize_error_message_patcher = patch.object(
            SecurityAwareErrorHandler,
            '_sanitize_error_message',
            side_effect=lambda msg: f"sanitized: {msg}"
        )

        self.mock_sanitize_error_message = self.sanitize_error_message_patcher.start()

        # Patch is_error_sensitive to return False by default.
        self.is_error_sensitive_patcher = patch.object(
            SecurityAwareErrorHandler,
            'is_error_sensitive',
            return_value=False
        )

        self.mock_is_error_sensitive = self.is_error_sensitive_patcher.start()

        # Patch _log_detailed_error to record that it was called.
        self.log_detailed_error_patcher = patch.object(
            SecurityAwareErrorHandler,
            '_log_detailed_error'
        )

        self.mock_log_detailed_error = self.log_detailed_error_patcher.start()

    def tearDown(self):
        self.uuid_patcher.stop()

        self.time_patcher.stop()

        self.log_error_patcher.stop()

        self.log_warning_patcher.stop()

        self.makedirs_patcher.stop()

        self.open_patcher.stop()

        self.format_exc_patcher.stop()

        self.sanitize_error_message_patcher.stop()

        self.is_error_sensitive_patcher.stop()

        self.log_detailed_error_patcher.stop()

        self.constants_patcher.__exit__(None, None, None)

    # Tests for log_processing_error

    def test_log_processing_error_with_trace(self):
        test_exception = ValueError("Test error message")

        trace_id = "provided_trace"

        returned_trace = SecurityAwareErrorHandler.log_processing_error(
            test_exception,
            "op_type",
            "resource123",
            trace_id
        )

        self.assertEqual(returned_trace, trace_id)

        expected_log_message = (
            f"[ERROR] op_type error ("
            f"ID: 12345678-1234-5678-1234-567812345678, Trace: {trace_id}"
            f"): sanitized: Test error message"
        )

        self.mock_log_error.assert_called_with(expected_log_message)

        self.mock_log_detailed_error.assert_called()

    def test_log_processing_error_without_trace(self):
        test_exception = ValueError("Another test error")

        returned_trace = SecurityAwareErrorHandler.log_processing_error(
            test_exception,
            "op_type",
            "resource456"
        )

        self.assertTrue(returned_trace.startswith("trace_"))

        self.assertIn("1617235678", returned_trace)

        expected_log_message = (
            f"[ERROR] op_type error ("
            f"ID: 12345678-1234-5678-1234-567812345678, Trace: {returned_trace}"
            f"): sanitized: Another test error"
        )

        self.mock_log_error.assert_called_with(expected_log_message)

        self.mock_log_detailed_error.assert_called()

    # Tests for _sanitize_filename

    def test_sanitize_filename_empty(self):
        # Stop the patch so that the real method runs.
        self.sanitize_error_message_patcher.stop()

        result = SecurityAwareErrorHandler._sanitize_filename("")

        self.assertEqual(result, "unnamed_file")

        self.sanitize_error_message_patcher.start()

    def test_sanitize_filename_sensitive(self):
        input_filename = "user_password_data.docx"

        # Stop the patch so that the real logic runs.
        self.sanitize_error_message_patcher.stop()

        result = SecurityAwareErrorHandler._sanitize_filename(input_filename)

        self.assertTrue(result.startswith("redacted_"))

        self.assertTrue(result.endswith(".docx"))

        self.sanitize_error_message_patcher.start()

    def test_sanitize_filename_long(self):
        input_filename = "this_is_a_very_long_filename.txt"

        result = SecurityAwareErrorHandler._sanitize_filename(input_filename)

        self.assertIn("...", result)

        self.assertTrue(result.endswith(".txt"))

    def test_sanitize_filename_normal(self):
        input_filename = "report.pdf"

        result = SecurityAwareErrorHandler._sanitize_filename(input_filename)

        self.assertEqual(result, "report.pdf")

    # Tests for safe_execution

    def test_safe_execution_success(self):
        def add(x, y):
            return x + y

        success, result, err_msg = SecurityAwareErrorHandler.safe_execution(
            add,
            "test_operation",
            default=0,
            x=3,
            y=4
        )

        self.assertTrue(success)

        self.assertEqual(result, 7)

        self.assertIsNone(err_msg)

    def test_safe_execution_failure(self):
        def failing_func():
            raise ValueError("Failure occurred")

        success, result, err_msg = SecurityAwareErrorHandler.safe_execution(
            failing_func,
            "test_operation",
            default="default"
        )

        self.assertFalse(success)

        self.assertEqual(result, "default")

        self.assertIn(TEST_ERROR_TYPE_MESSAGES["ValueError"], err_msg)

        self.assertIn("Reference ID:", err_msg)

        self.assertIn("Trace ID:", err_msg)

        self.mock_log_detailed_error.assert_called()

    # Tests for _log_detailed_error

    def test_log_detailed_error_json_logging_disabled(self):
        # Unpatch _log_detailed_error so that the actual implementation is used.
        self.log_detailed_error_patcher.stop()

        # Reset open mock.
        self.mock_open.reset_mock()

        self.mock_open.side_effect = None  # Ensure open works normally.

        error_id = "error123"

        error_type = "ValueError"

        error_message = "Test detailed error"

        operation_type = "op_test"

        stack_trace = "Test stack trace"

        additional_info = {"key": "value"}

        # Call _log_detailed_error with JSON logging disabled.
        SecurityAwareErrorHandler._log_detailed_error(
            error_id,
            error_type,
            error_message,
            operation_type,
            stack_trace,
            additional_info
        )

        # Assert that open was called with the ERROR_LOG_PATH in append mode.
        self.mock_open.assert_called_with(TEST_ERROR_LOG_PATH, "a")

        handle = self.mock_open.return_value.__enter__.return_value

        # Check that at least one of the write calls contains the expected header.
        written_calls = [c[0][0] for c in handle.write.call_args_list]

        header_line = f"\n--- ERROR: {error_id} at {time.ctime(1617235678.0)} ---\n"

        self.assertTrue(
            any(header_line in s for s in written_calls),
            "Expected header line not found in written output."
        )

        # Re-patch _log_detailed_error.
        self.log_detailed_error_patcher = patch.object(
            SecurityAwareErrorHandler,
            '_log_detailed_error'
        )

        self.mock_log_detailed_error = self.log_detailed_error_patcher.start()

    def test_log_detailed_error_json_logging_enabled(self):
        # Enable JSON logging by patching USE_JSON_LOGGING to True.
        with patch.multiple(
                'backend.app.utils.system_utils.error_handling',
                USE_JSON_LOGGING=True
        ):

            # Unpatch _log_detailed_error so that the real implementation runs.
            self.log_detailed_error_patcher.stop()

            self.mock_open.reset_mock()

            self.mock_open.side_effect = None

            error_id = "error456"

            error_type = "TypeError"

            error_message = "Detailed type error"

            operation_type = "op_json"

            stack_trace = "Stack trace info"

            additional_info = {"extra": "info"}

            SecurityAwareErrorHandler._log_detailed_error(
                error_id,
                error_type,
                error_message,
                operation_type,
                stack_trace,
                additional_info
            )

            # Verify that open was called with the expected path and mode.
            self.mock_open.assert_called_with(TEST_ERROR_LOG_PATH, "a")

            handle = self.mock_open.return_value.__enter__.return_value

            # Concatenate all write calls.
            written = "".join(c[0][0] for c in handle.write.call_args_list)

            # The written output should be valid JSON. Attempt to load it.
            try:
                record = json.loads(written)
            except Exception as ex:
                self.fail(f"Output is not valid JSON: {ex}")

            # Verify that the JSON record contains the expected keys.
            self.assertEqual(record.get("error_id"), error_id)

            self.assertEqual(record.get("error_type"), error_type)

            self.assertEqual(record.get("operation_type"), operation_type)

            # Re-patch _log_detailed_error.
            self.log_detailed_error_patcher = patch.object(
                SecurityAwareErrorHandler,
                '_log_detailed_error'
            )

            self.mock_log_detailed_error = self.log_detailed_error_patcher.start()

    def test_log_detailed_error_failure(self):
        # Unpatch _log_detailed_error so that the actual implementation is used.
        self.log_detailed_error_patcher.stop()

        # Reset open mock and force it to raise an OSError.
        self.mock_open.reset_mock()

        self.mock_open.side_effect = OSError("Test OS error")

        error_id = "error789"

        # Call the method; it should catch the OSError and call log_warning.
        SecurityAwareErrorHandler._log_detailed_error(
            error_id,
            "Exception",
            "Error occurred",
            "op_fail",
            "Stack trace",
            {"foo": "bar"}
        )

        # Assert that log_warning was called at least once.
        self.assertTrue(
            self.mock_log_warning.called,
            "log_warning was not called on OSError"
        )

        last_call_msg = self.mock_log_warning.call_args[0][0]

        self.assertIn("Failed to log detailed error information", last_call_msg)

        # Re-patch _log_detailed_error so that subsequent tests are not affected.
        self.log_detailed_error_patcher = patch.object(
            SecurityAwareErrorHandler,
            '_log_detailed_error'
        )

        self.mock_log_detailed_error = self.log_detailed_error_patcher.start()

    # Tests for _sanitize_additional_info

    def test_sanitize_additional_info(self):
        additional_info = {"key1": "sensitive data", "key2": 123}

        sanitized = SecurityAwareErrorHandler._sanitize_additional_info(additional_info)

        self.assertEqual(sanitized["key1"], "sanitized: sensitive data")

        self.assertEqual(sanitized["key2"], 123)

    # Tests for _capture_env_info

    def test_capture_env_info(self):
        with patch.dict(
                os.environ,
                {"ENVIRONMENT": "production", "SERVICE_NAME": "myservice", "HOSTNAME": "host1"}
        ):
            env_info = SecurityAwareErrorHandler._capture_env_info()

            self.assertEqual(env_info.get("ENVIRONMENT"), "production")

            self.assertEqual(env_info.get("SERVICE_NAME"), "myservice")

            self.assertEqual(env_info.get("HOSTNAME"), "host1")

            self.assertNotIn("SERVICE_VERSION", env_info)

    # Tests for _send_to_distributed_tracing

    def test_send_to_distributed_tracing(self):
        try:
            SecurityAwareErrorHandler._send_to_distributed_tracing({"dummy": "data"})
        except Exception as e:
            self.fail(f"_send_to_distributed_tracing raised an exception: {e}")

    # Tests for _sanitize_error_message

    def test_sanitize_error_message_empty(self):
        # Stop the patch so the real function runs.
        self.sanitize_error_message_patcher.stop()

        result = SecurityAwareErrorHandler._sanitize_error_message("")

        self.assertEqual(result, "Error details not available")

        self.sanitize_error_message_patcher.start()

    def test_sanitize_error_message_sensitive(self):
        with patch.object(
                SecurityAwareErrorHandler,
                'is_error_sensitive',
                return_value=True
        ):
            self.sanitize_error_message_patcher.stop()

            result = SecurityAwareErrorHandler._sanitize_error_message(
                "This contains password=abc123"
            )

            self.assertEqual(result, "Error details redacted for security")

            self.sanitize_error_message_patcher.start()

    def test_sanitize_error_message_paths(self):
        message = "Error in /var/log/app.log occurred."

        with patch.object(
                SecurityAwareErrorHandler,
                'is_error_sensitive',
                return_value=False
        ):
            self.sanitize_error_message_patcher.stop()

            result = SecurityAwareErrorHandler._sanitize_error_message(message)

            self.assertIn("[PATH]/app.log", result)

            self.sanitize_error_message_patcher.start()

    # Tests for safe_execution

    def test_safe_execution_success_tow(self):
        def multiply(a, b):
            return a * b

        success, result, err = SecurityAwareErrorHandler.safe_execution(
            multiply,
            "multiply_op",
            default=0,
            a=5,
            b=6
        )

        self.assertTrue(success)

        self.assertEqual(result, 30)

        self.assertIsNone(err)

    def test_safe_execution_exception(self):
        def failing_func():
            raise ValueError("Failure occurred")

        success, result, err = SecurityAwareErrorHandler.safe_execution(
            failing_func,
            "divide_op",
            default="error"
        )

        self.assertFalse(success)

        self.assertEqual(result, "error")

        self.assertIn(TEST_ERROR_TYPE_MESSAGES["ValueError"], err)

        self.assertIn("Reference ID:", err)

        self.assertIn("Trace ID:", err)

        self.mock_log_detailed_error.assert_called()

    # Tests for handle_safe_error (generic dispatcher)

    def test_handle_safe_error_default_return(self):
        test_exception = ValueError("Test error")

        default_value = {"status": "default"}

        result = SecurityAwareErrorHandler.handle_safe_error(
            test_exception,
            "unknown_operation",
            default_return=default_value
        )

        self.assertEqual(result, default_value)

    def test_handle_safe_error_generic(self):
        test_exception = ValueError("Test generic error")

        result = SecurityAwareErrorHandler.handle_safe_error(
            test_exception,
            "generic_operation"
        )

        self.assertEqual(result["error_type"], "ValueError")

        self.assertIn("error", result)

    # Tests for handle_batch_processing_error (via safe_error for batch)

    def test_handle_batch_processing_error(self):
        test_exception = ValueError("Test batch error")

        result = SecurityAwareErrorHandler.handle_batch_processing_error(
            test_exception,
            "batch_process",
            10,
            {"test_key": "test_value"},
            "test_trace_id"
        )

        batch_summary = result.get("batch_summary")

        self.assertIsNotNone(batch_summary)

        self.assertEqual(batch_summary.get("total_files"), 10)

        self.assertEqual(batch_summary.get("failed"), 10)

        self.assertIn("test_key", batch_summary)

        self.assertIn(
            TEST_ERROR_TYPE_MESSAGES["ValueError"],
            batch_summary.get("error")
        )

        self.mock_log_detailed_error.assert_called()

    # Tests for handle_api_gateway_error

    def test_handle_api_gateway_error(self):
        test_exception = ValueError("Test API error")

        result = SecurityAwareErrorHandler.handle_api_gateway_error(
            test_exception,
            "api_call",
            "https://api.example.com/data",
            {"test_key": "test_value"},
            "test_trace_id"
        )

        self.assertEqual(result["error_type"], "ValueError")

        self.assertEqual(result["error_id"], "12345678-1234-5678-1234-567812345678")

        self.assertEqual(result["trace_id"], "test_trace_id")

        self.assertEqual(result["status_code"], 400)

        self.assertEqual(result["test_key"], "test_value")

        self.assertIn(
            TEST_ERROR_TYPE_MESSAGES["ValueError"],
            result["error"]
        )

        self.mock_log_detailed_error.assert_called()

    def test_handle_api_gateway_error_timeout(self):
        test_exception = TimeoutError("Request timed out")

        result = SecurityAwareErrorHandler.handle_api_gateway_error(
            test_exception,
            "api_call",
            "https://api.example.com/data"
        )

        self.assertEqual(result["status_code"], 504)

    def test_handle_api_gateway_error_connection_error(self):
        test_exception = ConnectionError("Failed to connect")

        result = SecurityAwareErrorHandler.handle_api_gateway_error(
            test_exception,
            "api_call",
            "https://api.example.com/data"
        )

        self.assertEqual(result["status_code"], 502)

    def test_handle_api_gateway_error_http_exception(self):
        test_exception = HTTPException(status_code=403, detail="Forbidden access")

        result = SecurityAwareErrorHandler.handle_api_gateway_error(
            test_exception,
            "api_call",
            "https://api.example.com/data"
        )

        self.assertEqual(result["status_code"], 403)

        self.assertIn("Forbidden access", result["error"])

    # Tests for handle_safe_error dispatcher

    def test_handle_safe_error_detection(self):
        test_exception = ValueError("Test detection error")

        result = SecurityAwareErrorHandler.handle_safe_error(
            test_exception,
            "detection_operation",
            resource_id="test_resource"
        )

        self.assertEqual(result["error_type"], "ValueError")

        self.assertIn("redaction_mapping", result)

        self.assertIn("entities_detected", result)

        self.mock_log_detailed_error.assert_called()

    def test_handle_safe_error_file(self):
        test_exception = ValueError("Test file error")

        result = SecurityAwareErrorHandler.handle_safe_error(
            test_exception,
            "file_operation",
            filename="test.pdf"
        )

        self.assertEqual(result["error_type"], "ValueError")

        self.assertEqual(result["file"], "test.pdf")

        self.assertEqual(result["status"], "error")

        self.mock_log_detailed_error.assert_called()

    def test_handle_safe_error_batch(self):
        test_exception = ValueError("Test batch error")

        result = SecurityAwareErrorHandler.handle_safe_error(
            test_exception,
            "batch_operation",
            additional_info={"files_count": 5}
        )

        batch_summary = result.get("batch_summary")

        self.assertIsNotNone(batch_summary)

        self.assertEqual(batch_summary.get("total_files"), 5)

        self.assertEqual(batch_summary.get("failed"), 5)

        self.mock_log_detailed_error.assert_called()

    def test_handle_safe_error_api(self):
        test_exception = ValueError("Test API error")

        result = SecurityAwareErrorHandler.handle_safe_error(
            test_exception,
            "api_operation",
            endpoint="https://api.example.com/data"
        )

        self.assertEqual(result["error_type"], "ValueError")

        self.assertEqual(result["status_code"], 400)

        self.mock_log_detailed_error.assert_called()
