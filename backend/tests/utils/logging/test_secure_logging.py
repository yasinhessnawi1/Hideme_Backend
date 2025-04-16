"""
Unit tests for secure_logging.py module.

This test file covers the secure logging functions with both positive
and negative test cases to ensure proper functionality and error handling.
"""

import json
import unittest
from unittest.mock import patch

# Import the module to be tested
from backend.app.utils.logging.secure_logging import (
    log_sensitive_operation,
    log_batch_operation
)


class TestLogSensitiveOperation(unittest.TestCase):
    """Test cases for log_sensitive_operation function."""

    @patch('backend.app.utils.logging.secure_logging.log_info')
    def test_log_sensitive_operation_basic(self, mock_log_info):
        """Test log_sensitive_operation with basic parameters."""

        log_sensitive_operation(
            operation_name="Test Operation",
            entity_count=10,
            processing_time=5.5
        )
        # Expect one call for operation details (no metadata log)
        mock_log_info.assert_called_once_with(
            "[SENSITIVE] Test Operation: processed 10 entities in 5.50s"
        )

    @patch('backend.app.utils.logging.secure_logging.log_info')
    def test_log_sensitive_operation_with_safe_metadata(self, mock_log_info):
        """Test log_sensitive_operation with safe metadata."""

        log_sensitive_operation(
            operation_name="Test Operation",
            entity_count=10,
            processing_time=5.5,
            user_id="user123",
            status="completed",
            file_count=5
        )
        # Should log operation details and then metadata
        self.assertEqual(mock_log_info.call_count, 2)
        mock_log_info.assert_any_call("[SENSITIVE] Test Operation: processed 10 entities in 5.50s")
        second_call_args = mock_log_info.call_args_list[1][0][0]
        self.assertTrue(second_call_args.startswith("[METADATA] "))
        metadata_json = second_call_args.replace("[METADATA] ", "")
        metadata_dict = json.loads(metadata_json)

        self.assertEqual(metadata_dict["user_id"], "user123")
        self.assertEqual(metadata_dict["status"], "completed")
        self.assertEqual(metadata_dict["file_count"], 5)

    @patch('backend.app.utils.logging.secure_logging.log_info')
    def test_log_sensitive_operation_with_sensitive_metadata(self, mock_log_info):
        """Test log_sensitive_operation with sensitive metadata that should be filtered at first level."""

        log_sensitive_operation(
            operation_name="Test Operation",
            entity_count=10,
            processing_time=5.5,
            user_info={
                "id": "user123",
                "text": "This should be filtered",
                "preferences": {
                    "theme": "dark",
                    "content": "This should also be filtered"
                }
            },
            file_info={
                "name": "test.txt",
                "size": 1024,
                "entities": ["This should be filtered"]
            }
        )
        # Two calls: one for the [SENSITIVE] log and one for metadata log
        self.assertEqual(mock_log_info.call_count, 2)

        # First call is operation details:
        mock_log_info.assert_any_call("[SENSITIVE] Test Operation: processed 10 entities in 5.50s")

        # Second call: metadata log. Parse it.
        second_call_args = mock_log_info.call_args_list[1][0][0]
        metadata_json = second_call_args.replace("[METADATA] ", "")
        metadata_dict = json.loads(metadata_json)

        # In the top-level metadata, sensitive keys should be filtered out.
        self.assertIn("user_info", metadata_dict)
        self.assertIn("file_info", metadata_dict)
        self.assertEqual(metadata_dict["user_info"].get("id"), "user123")
        self.assertNotIn("text", metadata_dict["user_info"])  # Top-level sensitive key removed

        # However, nested dictionaries are not recursively sanitized;
        # so the preferences dictionary remains unchanged.
        self.assertIn("preferences", metadata_dict["user_info"])
        self.assertEqual(metadata_dict["user_info"]["preferences"]["theme"], "dark")

        # Here, since the implementation only goes one level deep,
        # the nested key "content" is still present.
        self.assertIn("content", metadata_dict["user_info"]["preferences"])

        # In file_info, "entities" should be removed.
        self.assertEqual(metadata_dict["file_info"].get("name"), "test.txt")
        self.assertEqual(metadata_dict["file_info"].get("size"), 1024)
        self.assertNotIn("entities", metadata_dict["file_info"])

    @patch('backend.app.utils.logging.secure_logging.log_info')
    def test_log_sensitive_operation_with_empty_metadata(self, mock_log_info):
        """Test log_sensitive_operation with no additional metadata."""

        log_sensitive_operation(
            operation_name="Test Operation",
            entity_count=10,
            processing_time=5.5
        )
        mock_log_info.assert_called_once_with(
            "[SENSITIVE] Test Operation: processed 10 entities in 5.50s"
        )

    @patch('backend.app.utils.logging.secure_logging.log_info')
    def test_log_sensitive_operation_with_zero_entities(self, mock_log_info):
        """Test log_sensitive_operation with zero entities."""

        log_sensitive_operation(
            operation_name="Empty Operation",
            entity_count=0,
            processing_time=0.1
        )
        mock_log_info.assert_called_once_with(
            "[SENSITIVE] Empty Operation: processed 0 entities in 0.10s"
        )

    @patch('backend.app.utils.logging.secure_logging.log_info')
    def test_log_sensitive_operation_with_json_serialization_error(self, mock_log_info):
        """Test log_sensitive_operation with metadata that triggers JSON serialization error.
        Expect a TypeError to be raised.
        """

        class UnserializableObject:
            def __repr__(self):
                return "UnserializableObject()"

        with patch('json.dumps', side_effect=TypeError("Object not serializable")):
            with self.assertRaises(TypeError) as context:
                log_sensitive_operation(
                    operation_name="Test Operation",
                    entity_count=10,
                    processing_time=5.5,
                    problematic_object=UnserializableObject()
                )

        # Since the error is raised during metadata logging, only the first log call would have occurred.
        mock_log_info.assert_called_once_with(
            "[SENSITIVE] Test Operation: processed 10 entities in 5.50s"
        )


class TestLogBatchOperation(unittest.TestCase):
    """Test cases for log_batch_operation function."""

    @patch('backend.app.utils.logging.secure_logging.log_info')
    def test_log_batch_operation_basic(self, mock_log_info):
        log_batch_operation(
            operation_name="Test Batch",
            total_files=20,
            successful_files=15,
            processing_time=10.5
        )
        mock_log_info.assert_called_once_with("[BATCH] Test Batch: 15/20 files in 10.50s")

    @patch('backend.app.utils.logging.secure_logging.log_info')
    def test_log_batch_operation_all_successful(self, mock_log_info):
        log_batch_operation(
            operation_name="Test Batch",
            total_files=20,
            successful_files=20,
            processing_time=10.5
        )
        mock_log_info.assert_called_once_with("[BATCH] Test Batch: 20/20 files in 10.50s")

    @patch('backend.app.utils.logging.secure_logging.log_info')
    def test_log_batch_operation_no_successful(self, mock_log_info):
        log_batch_operation(
            operation_name="Test Batch",
            total_files=20,
            successful_files=0,
            processing_time=5.0
        )
        mock_log_info.assert_called_once_with("[BATCH] Test Batch: 0/20 files in 5.00s")

    @patch('backend.app.utils.logging.secure_logging.log_info')
    def test_log_batch_operation_no_files(self, mock_log_info):
        log_batch_operation(
            operation_name="Empty Batch",
            total_files=0,
            successful_files=0,
            processing_time=0.1
        )
        mock_log_info.assert_called_once_with("[BATCH] Empty Batch: 0/0 files in 0.10s")

    @patch('backend.app.utils.logging.secure_logging.log_info')
    def test_log_batch_operation_long_operation_name(self, mock_log_info):
        log_batch_operation(
            operation_name="This is a very long operation name that tests the logging functionality with extended text",
            total_files=10,
            successful_files=8,
            processing_time=7.5
        )
        mock_log_info.assert_called_once_with(
            "[BATCH] This is a very long operation name that tests the logging functionality with extended text: 8/10 files in 7.50s")

    @patch('backend.app.utils.logging.secure_logging.log_info')
    def test_log_batch_operation_zero_processing_time(self, mock_log_info):
        log_batch_operation(
            operation_name="Fast Batch",
            total_files=5,
            successful_files=5,
            processing_time=0.0
        )
        mock_log_info.assert_called_once_with("[BATCH] Fast Batch: 5/5 files in 0.00s")
