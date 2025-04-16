import os
import unittest
from datetime import timedelta, datetime
from unittest.mock import patch, MagicMock, mock_open

from backend.app.configs.gdpr_config import GDPR_DOCUMENTATION
from backend.app.utils.constant.constant import JSON_CONSTANT
from backend.app.utils.security.processing_records import ProcessingRecordKeeper


class TestProcessingRecordKeeper(unittest.TestCase):

    def setUp(self):
        # Patch logging functions, os functions, etc.
        self.log_info_patcher = patch('backend.app.utils.security.processing_records.log_info')
        self.mock_log_info = self.log_info_patcher.start()

        self.log_warning_patcher = patch('backend.app.utils.security.processing_records.log_warning')
        self.mock_log_warning = self.log_warning_patcher.start()

        self.dirname_patcher = patch('os.path.dirname')
        self.mock_dirname = self.dirname_patcher.start()
        self.mock_dirname.return_value = '/mock/path'

        self.abspath_patcher = patch('os.path.abspath')
        self.mock_abspath = self.abspath_patcher.start()
        self.mock_abspath.return_value = '/mock/path/file.py'

        self.makedirs_patcher = patch('os.makedirs')
        self.mock_makedirs = self.makedirs_patcher.start()

        self.listdir_patcher = patch('os.listdir')
        self.mock_listdir = self.listdir_patcher.start()
        # Default: no files.
        self.mock_listdir.return_value = []

        self.unlink_patcher = patch('os.unlink')
        self.mock_unlink = self.unlink_patcher.start()

        self.open_patcher = patch('builtins.open', mock_open())
        self.mock_open = self.open_patcher.start()

        # Patch datetime in the module so that datetime.now returns a real datetime.
        self.datetime_patcher = patch('backend.app.utils.security.processing_records.datetime')
        self.mock_datetime = self.datetime_patcher.start()
        fixed_now = datetime(2025, 4, 15, 12, 0, 0)
        self.mock_datetime.now.return_value = fixed_now
        self.mock_datetime.timedelta = timedelta

        self.sha256_patcher = patch('hashlib.sha256')
        self.mock_sha256 = self.sha256_patcher.start()
        mock_hash = MagicMock()
        mock_hash.hexdigest.return_value = "0123456789abcdef0123456789abcdef"
        self.mock_sha256.return_value = mock_hash

        self.json_dumps_patcher = patch('json.dumps')
        self.mock_json_dumps = self.json_dumps_patcher.start()
        # Assume JSON_CONSTANT is ".jsonl"
        self.mock_json_dumps.return_value = '{"mock": "json"}'

        # Reset singleton and create a fresh instance.
        ProcessingRecordKeeper._instance = None
        self.record_keeper = ProcessingRecordKeeper()

    def tearDown(self):
        self.log_info_patcher.stop()
        self.log_warning_patcher.stop()
        self.dirname_patcher.stop()
        self.abspath_patcher.stop()
        self.makedirs_patcher.stop()
        self.listdir_patcher.stop()
        self.unlink_patcher.stop()
        self.open_patcher.stop()
        self.datetime_patcher.stop()
        self.sha256_patcher.stop()
        self.json_dumps_patcher.stop()

    def test_init_with_custom_records_dir(self):
        """Test initialization with custom records directory should raise TypeError as custom args are not supported."""

        ProcessingRecordKeeper._instance = None
        with self.assertRaises(TypeError):
            ProcessingRecordKeeper(records_dir="/custom/path")

    def test_initialize_stats_file_error(self):
        """Test _initialize_stats when file processing raises an error."""

        # Return a file with the proper extension.
        self.mock_listdir.return_value = [f"processing_record_2025-04-15{JSON_CONSTANT}"]
        self.mock_open.side_effect = OSError("Test file error")
        self.record_keeper._initialize_stats()

        # Instead of an exact call, verify that log_warning was called with a message containing expected substrings.
        self.mock_log_warning.assert_called()
        msg = self.mock_log_warning.call_args[0][0]
        self.assertIn(f"processing_record_2025-04-15{JSON_CONSTANT}", msg)
        self.assertIn("Test file error", msg)

    def test_initialize_stats_with_records(self):
        """Test _initialize_stats with existing record files."""

        # Use filenames with JSON_CONSTANT (e.g. ".jsonl")
        self.mock_listdir.return_value = [
            f"processing_record_2025-04-14{JSON_CONSTANT}",
            f"processing_record_2025-04-15{JSON_CONSTANT}",
            "not_a_record_file.txt"
        ]

        dir_path = self.record_keeper.records_dir
        file1 = os.path.join(dir_path, f"processing_record_2025-04-14{JSON_CONSTANT}")
        file2 = os.path.join(dir_path, f"processing_record_2025-04-15{JSON_CONSTANT}")
        file_content = {
            file1: "record1\nrecord2",
            file2: "record1\nrecord2\nrecord3"
        }

        def mock_open_side_effect(file_path, *args, **kwargs):
            mock_file = MagicMock()
            content = file_content.get(file_path, "")
            # Return an iterator over lines.
            mock_file.__enter__.return_value = content.splitlines()
            return mock_file

        self.mock_open.side_effect = mock_open_side_effect
        self.record_keeper._initialize_stats()
        self.assertEqual(self.record_keeper.stats["total_records"], 5)
        self.assertEqual(self.record_keeper.stats["records_by_day"], {
            "2025-04-14": 2,
            "2025-04-15": 3
        })

        self.mock_log_info.assert_called_with("[GDPR] Found 5 existing processing records")

    def test_record_processing(self):
        """Test record_processing method."""
        self.record_keeper.record_processing(
            operation_type="test_operation",
            document_type="test_document",
            entity_types_processed=["name", "email"],
            processing_time=1.5,
            file_count=2,
            entity_count=10,
            success=True
        )
        self.mock_log_info.assert_called_with("[GDPR_RECORD] Processing record created for test_operation")

        # The record file is built as: f"processing_record_{record_date}{JSON_CONSTANT}"
        expected_file_path = os.path.join(self.record_keeper.records_dir,
                                          f"processing_record_2025-04-15{JSON_CONSTANT}")
        self.mock_open.assert_called_once_with(expected_file_path, 'a', encoding='utf-8')
        self.mock_json_dumps.assert_called_once()
        args, _ = self.mock_json_dumps.call_args
        record = args[0]
        self.assertEqual(record["operation_type"], "test_operation")
        self.assertEqual(record["document_type"], "test_document")
        self.assertEqual(record["entity_types"], ["name", "email"])
        self.assertEqual(record["processing_time_seconds"], 1.5)
        self.assertEqual(record["file_count"], 2)
        self.assertEqual(record["entity_count"], 10)
        self.assertTrue(record["success"])
        self.assertEqual(record["legal_basis"], GDPR_DOCUMENTATION.get('legal_basis', 'legitimate_interests'))
        self.assertEqual(record["operation_id"], "0123456789abcdef")

        file_handle = self.mock_open.return_value.__enter__.return_value
        file_handle.write.assert_called_once_with('{"mock": "json"}\n')

        self.assertEqual(self.record_keeper.stats["total_records"], 1)
        self.assertEqual(self.record_keeper.stats["last_record_time"], "2025-04-15T12:00:00")
        self.assertEqual(self.record_keeper.stats["records_by_type"], {"test_operation": 1})
        self.assertEqual(self.record_keeper.stats["records_by_day"], {"2025-04-15": 1})

    def test_singleton_pattern(self):
        """Test that ProcessingRecordKeeper follows the singleton pattern."""

        ProcessingRecordKeeper._instance = None
        keeper1 = ProcessingRecordKeeper()
        keeper2 = ProcessingRecordKeeper()

        self.assertIs(keeper1, keeper2)
        # We do not compare against the pre-created global record_keeper

    def test_cleanup_old_records_no_old_files(self):
        """
        Test _cleanup_old_records when there are no files older than the cutoff date.

        With fixed_now = 2025-04-15 and retention = 90 days, cutoff ~ "2025-01-15".
        Use file dates on or after January 20, 2025, so no deletion should occur.
        """
        self.mock_listdir.return_value = [
            f"processing_record_2025-01-20{JSON_CONSTANT}",
            f"processing_record_2025-05-01{JSON_CONSTANT}"
        ]
        # Pre-set stats.
        self.record_keeper.stats["total_records"] = 10
        self.record_keeper.stats["records_by_day"] = {
            "2025-01-20": 4,
            "2025-05-01": 6
        }

        # Call cleanup; no file should be deleted.
        self.record_keeper._cleanup_old_records()

        # Verify os.unlink was not called.
        self.mock_unlink.assert_not_called()
        self.assertEqual(self.record_keeper.stats["total_records"], 10)
        self.assertEqual(self.record_keeper.stats["records_by_day"], {
            "2025-01-20": 4,
            "2025-05-01": 6
        })

    def test_cleanup_old_records_with_old_files(self):
        """
        Test _cleanup_old_records deletes files older than the retention period and updates stats.

        With fixed_now = 2025-04-15 and retention = 90 days, cutoff ~ "2025-01-15".
        A file dated "2024-12-31" should be deleted.
        """
        self.mock_listdir.return_value = [
            f"processing_record_2024-12-31{JSON_CONSTANT}",  # Old file: 2024-12-31 < 2025-01-15
            f"processing_record_2025-04-10{JSON_CONSTANT}"  # Recent file
        ]

        # Pre-populate stats.
        self.record_keeper.stats["total_records"] = 10
        self.record_keeper.stats["records_by_day"] = {
            "2024-12-31": 3,
            "2025-04-10": 7
        }

        # Call cleanup.
        self.record_keeper._cleanup_old_records()

        # The old file's full path.
        old_file = os.path.join(self.record_keeper.records_dir, f"processing_record_2024-12-31{JSON_CONSTANT}")
        self.mock_unlink.assert_called_once_with(old_file)

        # Verify that stats were updated: total_records reduces by 3 and the day entry is removed.
        self.assertEqual(self.record_keeper.stats["total_records"], 7)
        self.assertNotIn("2024-12-31", self.record_keeper.stats["records_by_day"])
        self.assertIn("2025-04-10", self.record_keeper.stats["records_by_day"])

        # Verify that a log_info call indicates deletion.
        self.mock_log_info.assert_called()
        log_info_msg = self.mock_log_info.call_args[0][0]
        self.assertIn("Deleted 1 processing record files", log_info_msg)

    def test_cleanup_old_records_listdir_error(self):
        """Test _cleanup_old_records when os.listdir raises an error."""

        self.mock_listdir.side_effect = OSError("Listdir error")
        self.record_keeper._cleanup_old_records()
        self.mock_log_warning.assert_called()

        msg = self.mock_log_warning.call_args[0][0]
        self.assertIn("Error listing record directory for cleanup", msg)

    def test_cleanup_old_records_cutoff_error(self):
        """Test _cleanup_old_records when cutoff date calculation fails."""

        # Force datetime.now() to raise an exception.
        self.mock_datetime.now.side_effect = Exception("Cutoff calc failure")
        self.record_keeper._cleanup_old_records()
        self.mock_log_warning.assert_called()

        msg = self.mock_log_warning.call_args[0][0]
        self.assertIn("Error computing cutoff date", msg)

    def test_get_record_stats(self):
        """Test get_record_stats returns a proper copy of the statistics with additional info."""

        # Manually update stats.
        self.record_keeper.stats["total_records"] = 8
        self.record_keeper.stats["records_by_type"] = {"op1": 3, "op2": 5}
        self.record_keeper.stats["records_by_day"] = {"2025-04-15": 8}
        self.record_keeper.stats["last_record_time"] = "2025-04-15T12:00:00"
        stats = self.record_keeper.get_record_stats()

        # Check that expected keys are present.
        self.assertIn("total_records", stats)
        self.assertIn("records_by_type", stats)
        self.assertIn("records_by_day", stats)
        self.assertIn("retention_policy", stats)
        self.assertIn("gdpr_documentation", stats)

        # Verify values.
        self.assertEqual(stats["total_records"], 8)
        self.assertEqual(stats["records_by_type"], {"op1": 3, "op2": 5})
        self.assertEqual(stats["records_by_day"], {"2025-04-15": 8})
        self.assertEqual(stats["retention_policy"]["retention_days"], self.record_keeper.record_retention_days)

        expected_dir = os.path.basename(self.record_keeper.records_dir)
        self.assertEqual(stats["retention_policy"]["records_directory"], expected_dir)
        self.assertEqual(stats["gdpr_documentation"], GDPR_DOCUMENTATION)

        # Check that modifying the returned nested dicts does not affect the original.
        stats["records_by_day"]["2025-04-15"] = 100
        self.assertNotEqual(self.record_keeper.stats["records_by_day"]["2025-04-15"], 100)
