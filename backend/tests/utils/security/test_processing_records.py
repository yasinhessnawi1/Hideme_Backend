import os
import unittest
from datetime import timedelta, datetime
from unittest.mock import patch, MagicMock, mock_open

from backend.app.configs.gdpr_config import GDPR_DOCUMENTATION
from backend.app.utils.constant.constant import JSON_CONSTANT
from backend.app.utils.security.processing_records import ProcessingRecordKeeper


# Tests for ProcessingRecordKeeper functionality
class TestProcessingRecordKeeper(unittest.TestCase):
    """Test cases for ProcessingRecordKeeper singleton and methods."""

    # set up environment mocks for each test
    def setUp(self):
        self.log_info_patcher = patch(
            "backend.app.utils.security.processing_records.log_info"
        )

        self.mock_log_info = self.log_info_patcher.start()

        self.log_warning_patcher = patch(
            "backend.app.utils.security.processing_records.log_warning"
        )

        self.mock_log_warning = self.log_warning_patcher.start()

        self.dirname_patcher = patch("os.path.dirname")

        self.mock_dirname = self.dirname_patcher.start()

        self.mock_dirname.return_value = "/mock/path"

        self.abspath_patcher = patch("os.path.abspath")

        self.mock_abspath = self.abspath_patcher.start()

        self.mock_abspath.return_value = "/mock/path/file.py"

        self.makedirs_patcher = patch("os.makedirs")

        self.mock_makedirs = self.makedirs_patcher.start()

        self.listdir_patcher = patch("os.listdir")

        self.mock_listdir = self.listdir_patcher.start()

        self.mock_listdir.return_value = []

        self.unlink_patcher = patch("os.unlink")

        self.mock_unlink = self.unlink_patcher.start()

        self.open_patcher = patch("builtins.open", mock_open())

        self.mock_open = self.open_patcher.start()

        self.datetime_patcher = patch(
            "backend.app.utils.security.processing_records.datetime"
        )

        self.mock_datetime = self.datetime_patcher.start()

        fixed_now = datetime(2025, 4, 15, 12, 0, 0)

        self.mock_datetime.now.return_value = fixed_now

        self.mock_datetime.timedelta = timedelta

        self.sha256_patcher = patch("hashlib.sha256")

        self.mock_sha256 = self.sha256_patcher.start()

        mock_hash = MagicMock()

        mock_hash.hexdigest.return_value = "0123456789abcdef0123456789abcdef"

        self.mock_sha256.return_value = mock_hash

        self.json_dumps_patcher = patch("json.dumps")

        self.mock_json_dumps = self.json_dumps_patcher.start()

        self.mock_json_dumps.return_value = '{"mock": "json"}'

        ProcessingRecordKeeper._instance = None

        self.record_keeper = ProcessingRecordKeeper()

    # tear down environment mocks after each test
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

    # unsupported custom init args should raise TypeError
    def test_init_with_custom_records_dir(self):
        ProcessingRecordKeeper._instance = None

        with self.assertRaises(TypeError):
            ProcessingRecordKeeper(records_dir="/custom/path")

    # errors reading existing stats files should log warning
    def test_initialize_stats_file_error(self):
        self.mock_listdir.return_value = [
            f"processing_record_2025-04-15{JSON_CONSTANT}"
        ]

        self.mock_open.side_effect = OSError("Test file error")

        self.record_keeper._initialize_stats()

        self.mock_log_warning.assert_called()

        msg = self.mock_log_warning.call_args[0][0]

        self.assertIn(f"processing_record_2025-04-15{JSON_CONSTANT}", msg)

        self.assertIn("Test file error", msg)

    # existing record files counted correctly in stats
    def test_initialize_stats_with_records(self):
        self.mock_listdir.return_value = [
            f"processing_record_2025-04-14{JSON_CONSTANT}",
            f"processing_record_2025-04-15{JSON_CONSTANT}",
            "not_a_record_file.txt",
        ]

        dir_path = self.record_keeper.records_dir

        file1 = os.path.join(dir_path, f"processing_record_2025-04-14{JSON_CONSTANT}")

        file2 = os.path.join(dir_path, f"processing_record_2025-04-15{JSON_CONSTANT}")

        file_content = {file1: "record1\nrecord2", file2: "record1\nrecord2\nrecord3"}

        def mock_open_side_effect(file_path, *args, **kwargs):
            mock_file = MagicMock()

            content = file_content.get(file_path, "")

            mock_file.__enter__.return_value = content.splitlines()

            return mock_file

        self.mock_open.side_effect = mock_open_side_effect

        self.record_keeper._initialize_stats()

        self.assertEqual(self.record_keeper.stats["total_records"], 5)

        self.assertEqual(
            self.record_keeper.stats["records_by_day"],
            {"2025-04-14": 2, "2025-04-15": 3},
        )

        self.mock_log_info.assert_called_with(
            "[GDPR] Found 5 existing processing records"
        )

    # recording a new processing event writes to file and updates stats
    def test_record_processing(self):
        self.record_keeper.record_processing(
            operation_type="test_operation",
            document_type="test_document",
            entity_types_processed=["name", "email"],
            processing_time=1.5,
            file_count=2,
            entity_count=10,
            success=True,
        )

        self.mock_log_info.assert_called_with(
            "[GDPR_RECORD] Processing record created for test_operation"
        )

        expected_file_path = os.path.join(
            self.record_keeper.records_dir,
            f"processing_record_2025-04-15{JSON_CONSTANT}",
        )

        self.mock_open.assert_called_once_with(
            expected_file_path, "a", encoding="utf-8"
        )

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

        self.assertEqual(
            record["legal_basis"],
            GDPR_DOCUMENTATION.get("legal_basis", "legitimate_interests"),
        )

        self.assertEqual(record["operation_id"], "0123456789abcdef")

        file_handle = self.mock_open.return_value.__enter__.return_value

        file_handle.write.assert_called_once_with('{"mock": "json"}\n')

        self.assertEqual(self.record_keeper.stats["total_records"], 1)

        self.assertEqual(
            self.record_keeper.stats["last_record_time"], "2025-04-15T12:00:00"
        )

        self.assertEqual(
            self.record_keeper.stats["records_by_type"], {"test_operation": 1}
        )

        self.assertEqual(self.record_keeper.stats["records_by_day"], {"2025-04-15": 1})

    # singleton pattern ensures one instance
    def test_singleton_pattern(self):
        ProcessingRecordKeeper._instance = None

        keeper1 = ProcessingRecordKeeper()

        keeper2 = ProcessingRecordKeeper()

        self.assertIs(keeper1, keeper2)

    # cleanup with no old files leaves stats unchanged
    def test_cleanup_old_records_no_old_files(self):
        self.mock_listdir.return_value = [
            f"processing_record_2025-01-20{JSON_CONSTANT}",
            f"processing_record_2025-05-01{JSON_CONSTANT}",
        ]

        self.record_keeper.stats["total_records"] = 10

        self.record_keeper.stats["records_by_day"] = {"2025-01-20": 4, "2025-05-01": 6}

        self.record_keeper._cleanup_old_records()

        self.mock_unlink.assert_not_called()

        self.assertEqual(self.record_keeper.stats["total_records"], 10)

        self.assertEqual(
            self.record_keeper.stats["records_by_day"],
            {"2025-01-20": 4, "2025-05-01": 6},
        )

    # old files removed and stats updated accordingly
    def test_cleanup_old_records_with_old_files(self):
        self.mock_listdir.return_value = [
            f"processing_record_2024-12-31{JSON_CONSTANT}",
            f"processing_record_2025-04-10{JSON_CONSTANT}",
        ]

        self.record_keeper.stats["total_records"] = 10

        self.record_keeper.stats["records_by_day"] = {"2024-12-31": 3, "2025-04-10": 7}

        self.record_keeper._cleanup_old_records()

        old_file = os.path.join(
            self.record_keeper.records_dir,
            f"processing_record_2024-12-31{JSON_CONSTANT}",
        )

        self.mock_unlink.assert_called_once_with(old_file)

        self.assertEqual(self.record_keeper.stats["total_records"], 7)

        self.assertNotIn("2024-12-31", self.record_keeper.stats["records_by_day"])

        self.assertIn("2025-04-10", self.record_keeper.stats["records_by_day"])

        self.mock_log_info.assert_called()

        log_info_msg = self.mock_log_info.call_args[0][0]

        self.assertIn("Deleted 1 processing record files", log_info_msg)

    # errors listing files log a warning
    def test_cleanup_old_records_listdir_error(self):
        self.mock_listdir.side_effect = OSError("Listdir error")

        self.record_keeper._cleanup_old_records()

        self.mock_log_warning.assert_called()

        msg = self.mock_log_warning.call_args[0][0]

        self.assertIn("Error listing record directory for cleanup", msg)

    # errors computing cutoff date log a warning
    def test_cleanup_old_records_cutoff_error(self):
        self.mock_datetime.now.side_effect = Exception("Cutoff calc failure")

        self.record_keeper._cleanup_old_records()

        self.mock_log_warning.assert_called()

        msg = self.mock_log_warning.call_args[0][0]

        self.assertIn("Error computing cutoff date", msg)

    # retrieving record stats returns correct structure copy
    def test_get_record_stats(self):
        self.record_keeper.stats["total_records"] = 8

        self.record_keeper.stats["records_by_type"] = {"op1": 3, "op2": 5}

        self.record_keeper.stats["records_by_day"] = {"2025-04-15": 8}

        self.record_keeper.stats["last_record_time"] = "2025-04-15T12:00:00"

        stats = self.record_keeper.get_record_stats()

        self.assertIn("total_records", stats)

        self.assertIn("records_by_type", stats)

        self.assertIn("records_by_day", stats)

        self.assertIn("retention_policy", stats)

        self.assertIn("gdpr_documentation", stats)

        self.assertEqual(stats["total_records"], 8)

        self.assertEqual(stats["records_by_type"], {"op1": 3, "op2": 5})

        self.assertEqual(stats["records_by_day"], {"2025-04-15": 8})

        self.assertEqual(
            stats["retention_policy"]["retention_days"],
            self.record_keeper.record_retention_days,
        )

        expected_dir = os.path.basename(self.record_keeper.records_dir)

        self.assertEqual(stats["retention_policy"]["records_directory"], expected_dir)

        self.assertEqual(stats["gdpr_documentation"], GDPR_DOCUMENTATION)

        stats["records_by_day"]["2025-04-15"] = 100

        self.assertNotEqual(
            self.record_keeper.stats["records_by_day"]["2025-04-15"], 100
        )
