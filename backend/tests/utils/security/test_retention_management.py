import os
import unittest
from unittest.mock import patch, MagicMock, mock_open

from backend.app.configs.gdpr_config import TEMP_FILE_RETENTION_SECONDS
from backend.app.utils.security.retention_management import DocumentRetentionManager


class TestDocumentRetentionManager(unittest.TestCase):
    """Unit tests for DocumentRetentionManager class."""

    def setUp(self):
        # Patch logging functions.
        self.log_info_patcher = patch('backend.app.utils.security.retention_management.log_info')
        self.mock_log_info = self.log_info_patcher.start()

        self.log_warning_patcher = patch('backend.app.utils.security.retention_management.log_warning')
        self.mock_log_warning = self.log_warning_patcher.start()

        # Patch os.path.exists.
        self.exists_patcher = patch('os.path.exists')
        self.mock_exists = self.exists_patcher.start()
        self.mock_exists.return_value = True

        # Patch os.path.isfile and os.path.isdir.
        self.isfile_patcher = patch('os.path.isfile')
        self.mock_isfile = self.isfile_patcher.start()

        # For a directory itself, return False; for any file (not the directory) return True.
        self.mock_isfile.side_effect = lambda path: False if path == "/test/dir" else True

        self.isdir_patcher = patch('os.path.isdir')
        self.mock_isdir = self.isdir_patcher.start()

        # For the directory we are testing, return True; otherwise, False.
        self.mock_isdir.side_effect = lambda path: True if path == "/test/dir" else False

        # Patch os.path.getsize.
        self.getsize_patcher = patch('os.path.getsize')
        self.mock_getsize = self.getsize_patcher.start()
        self.mock_getsize.return_value = 1024  # 1KB file size

        # Patch os.fsync.
        self.fsync_patcher = patch('os.fsync')
        self.mock_fsync = self.fsync_patcher.start()

        # Patch os.listdir.
        self.listdir_patcher = patch('os.listdir')
        self.mock_listdir = self.listdir_patcher.start()
        self.mock_listdir.return_value = []

        # Patch os.unlink.
        self.unlink_patcher = patch('os.unlink')
        self.mock_unlink = self.unlink_patcher.start()

        # Patch open.
        self.open_patcher = patch('builtins.open', mock_open())
        self.mock_open = self.open_patcher.start()

        # Patch os.walk and shutil.rmtree.
        self.walk_patcher = patch('os.walk')
        self.mock_walk = self.walk_patcher.start()
        self.mock_walk.return_value = [("/test/dir", [], ["file1.txt", "file2.txt"])]
        self.rmtree_patcher = patch('shutil.rmtree')
        self.mock_rmtree = self.rmtree_patcher.start()

        # Patch threading.Thread.
        self.thread_patcher = patch('threading.Thread')
        self.mock_thread = self.thread_patcher.start()

        # Patch time.time.
        self.time_patcher = patch('time.time')
        self.mock_time = self.time_patcher.start()
        self.mock_time.return_value = 1617235678.0

        # Reset singleton.
        DocumentRetentionManager._instance = None
        self.retention_manager = DocumentRetentionManager()

    def tearDown(self):
        self.log_info_patcher.stop()
        self.log_warning_patcher.stop()
        self.exists_patcher.stop()
        self.isfile_patcher.stop()
        self.isdir_patcher.stop()
        self.getsize_patcher.stop()
        self.fsync_patcher.stop()
        self.listdir_patcher.stop()
        self.unlink_patcher.stop()
        self.open_patcher.stop()
        self.walk_patcher.stop()
        self.rmtree_patcher.stop()
        self.thread_patcher.stop()
        self.time_patcher.stop()
        # Stop any running cleanup thread.
        if hasattr(self.retention_manager, "_cleanup_thread") and self.retention_manager._cleanup_thread:
            self.retention_manager._stop_event.set()
            if hasattr(self.retention_manager._cleanup_thread, "join"):
                self.retention_manager._cleanup_thread.join(timeout=1)

    def test_singleton_pattern(self):
        """Test that DocumentRetentionManager follows the singleton pattern."""

        DocumentRetentionManager._instance = None
        manager1 = DocumentRetentionManager()
        manager2 = DocumentRetentionManager()

        self.assertIs(manager1, manager2)

    def test_init(self):
        """Test initialization of DocumentRetentionManager."""

        self.assertEqual(self.retention_manager.processed_files, {})
        self.assertEqual(self.retention_manager.permanent_files, set())
        self.assertIsNone(self.retention_manager._cleanup_thread)
        self.assertFalse(self.retention_manager._thread_running)
        self.assertFalse(self.retention_manager._stop_event.is_set())

        self.mock_log_info.assert_called_with("[GDPR] Document retention manager initialized")

    def test_start(self):
        """Test start method."""

        self.retention_manager.start()
        self.mock_thread.assert_called_once()
        self.mock_thread.return_value.start.assert_called_once()
        self.assertTrue(self.retention_manager._thread_running)

        self.mock_log_info.assert_any_call("[GDPR] Retention manager service started")
        self.mock_log_info.assert_any_call("[GDPR] Retention cleanup thread started")

    def test_start_already_running(self):
        """Test start when already running."""

        self.retention_manager._thread_running = True
        self.retention_manager.start()
        self.mock_thread.assert_not_called()

        self.mock_log_info.assert_called_with("[GDPR] Retention manager service already running")

    def test_register_processed_file(self):
        """Test register_processed_file method."""

        self.retention_manager.register_processed_file("/test/file.txt", 3600)
        self.assertIn("/test/file.txt", self.retention_manager.processed_files)
        self.assertEqual(
            self.retention_manager.processed_files["/test/file.txt"],
            1617235678.0 + 3600
        )
        self.mock_log_info.assert_called_with("[GDPR] Registered file for retention: file.txt")

    def test_register_processed_file_default_retention(self):
        """Test register_processed_file using default retention."""

        self.retention_manager.register_processed_file("/test/file.txt")
        self.assertIn("/test/file.txt", self.retention_manager.processed_files)
        self.assertEqual(
            self.retention_manager.processed_files["/test/file.txt"],
            1617235678.0 + TEMP_FILE_RETENTION_SECONDS
        )

    def test_unregister_file(self):
        """Test unregister_file method."""

        self.retention_manager.processed_files["/test/file.txt"] = 1617235678.0 + 3600
        self.retention_manager.permanent_files.add("/test/file.txt")
        self.retention_manager.unregister_file("/test/file.txt")
        self.assertNotIn("/test/file.txt", self.retention_manager.processed_files)
        self.assertNotIn("/test/file.txt", self.retention_manager.permanent_files)
        self.mock_log_info.assert_called_with("[GDPR] Unregistered file from retention management: file.txt")

    def test_unregister_file_not_registered(self):
        """Test unregister_file with a file not registered."""

        self.retention_manager.unregister_file("/test/nonexistent.txt")
        self.mock_log_info.assert_called_with("[GDPR] Unregistered file from retention management: nonexistent.txt")

    def test_cleanup_expired_files(self):
        """
        Test cleanup_expired_files:
          - Expired files are securely deleted if they exist.
          - Files not existing are skipped.
        """

        self.retention_manager.processed_files = {
            "/test/expired.txt": 1617235678.0 - 3600,  # expired
            "/test/not_expired.txt": 1617235678.0 + 3600  # not expired
        }
        # Use a mutable state to simulate deletion of the expired file.
        state = {"deleted": False}

        def exists_side_effect(path):
            if path == "/test/expired.txt":
                # Before deletion, return True; after deletion, return False.
                return not state["deleted"]
            return False

        self.mock_exists.side_effect = exists_side_effect

        # Patch _secure_delete_file so that it calls os.unlink and marks the file as deleted.
        def fake_secure_delete(path):
            os.unlink(path)
            state["deleted"] = True

        with patch.object(self.retention_manager, '_secure_delete_file',
                          side_effect=fake_secure_delete) as mock_secure_delete:
            self.retention_manager.cleanup_expired_files()

        # Verify that the expired file was removed from tracking.
        self.assertNotIn("/test/expired.txt", self.retention_manager.processed_files)
        self.assertIn("/test/not_expired.txt", self.retention_manager.processed_files)

        # Verify that os.unlink was called exactly once with the expired file.
        self.mock_unlink.assert_called_once_with("/test/expired.txt")

        # Verify that a log_info call was made indicating successful deletion.
        self.mock_log_info.assert_any_call("[GDPR] Successfully deleted file: expired.txt")

    def test_cleanup_expired_files_permanent(self):
        """Test cleanup_expired_files does not delete permanent files."""

        self.retention_manager.processed_files = {
            "/test/permanent.txt": 1617235678.0 - 3600
        }
        self.retention_manager.permanent_files.add("/test/permanent.txt")
        self.retention_manager.cleanup_expired_files()
        self.assertNotIn("/test/permanent.txt", self.retention_manager.processed_files)

        self.mock_unlink.assert_not_called()

    def test_cleanup_expired_files_nonexistent(self):
        """Test cleanup_expired_files when file does not exist."""

        self.retention_manager.processed_files = {
            "/test/nonexistent.txt": 1617235678.0 - 3600
        }

        self.mock_exists.side_effect = lambda path: False
        self.retention_manager.cleanup_expired_files()
        self.assertNotIn("/test/nonexistent.txt", self.retention_manager.processed_files)
        self.mock_unlink.assert_not_called()

    def test_cleanup_expired_files_deletion_error(self):
        """Test cleanup_expired_files when deletion raises an error."""

        self.retention_manager.processed_files = {
            "/test/error.txt": 1617235678.0 - 3600
        }

        self.mock_unlink.side_effect = OSError("Test deletion error")
        self.retention_manager.cleanup_expired_files()
        self.assertNotIn("/test/error.txt", self.retention_manager.processed_files)
        self.mock_log_warning.assert_called()

    def test_secure_delete_nonexistent_path(self):
        """Test _secure_delete with a nonexistent path."""

        self.mock_exists.return_value = False
        self.retention_manager._secure_delete("/test/nonexistent.txt")
        # Since the file doesn't exist, os.path.isfile and os.path.isdir should not be called.

    def test_secure_delete_file(self):
        """Test _secure_delete with a file."""

        self.mock_exists.return_value = True

        # For the file being deleted, os.path.isfile should return True.
        self.mock_isfile.side_effect = lambda path: True if path == "/test/file.txt" else False
        self.mock_isdir.side_effect = lambda path: False

        self.retention_manager._secure_delete("/test/file.txt")
        self.mock_getsize.assert_called_once_with("/test/file.txt")
        self.mock_open.assert_called_once_with("/test/file.txt", "wb")
        self.mock_unlink.assert_called_once_with("/test/file.txt")

    def test_secure_delete_directory(self):
        """Test _secure_delete with a directory."""

        # Configure mocks for directory.
        self.mock_exists.return_value = True

        # For the directory "/test/dir", os.path.isfile returns False and os.path.isdir returns True.
        self.mock_isfile.side_effect = lambda path: False if path == "/test/dir" else True
        self.mock_isdir.side_effect = lambda path: True if path == "/test/dir" else False

        # Call secure_delete on a directory.
        self.retention_manager._secure_delete("/test/dir")

        # Verify that os.walk is called on the directory.
        self.mock_walk.assert_called_once_with("/test/dir", topdown=False)

        # Verify that shutil.rmtree is called to remove the directory.
        self.mock_rmtree.assert_called_once_with("/test/dir", ignore_errors=False)

    def test_secure_delete_file_large(self):
        """Test _secure_delete_file with a large file (>100MB)."""

        self.mock_getsize.return_value = 150 * 1024 * 1024  # 150MB
        DocumentRetentionManager._secure_delete_file("/test/large_file.txt")
        self.mock_unlink.assert_called_once_with("/test/large_file.txt")
        self.mock_open.assert_not_called()

    def test_secure_delete_file_small(self):
        """Test _secure_delete_file with a small file."""

        self.mock_getsize.return_value = 1024  # 1KB
        DocumentRetentionManager._secure_delete_file("/test/small_file.txt")
        self.mock_open.assert_called_once_with("/test/small_file.txt", "wb")
        file_handle = self.mock_open.return_value.__enter__.return_value

        # Expect that for each of the 5 patterns, seek, write, flush, and fsync were called.
        self.assertEqual(file_handle.seek.call_count, 5)
        self.assertEqual(file_handle.write.call_count, 5)
        self.assertEqual(file_handle.flush.call_count, 5)
        self.assertEqual(self.mock_fsync.call_count, 5)
        self.mock_unlink.assert_called_once_with("/test/small_file.txt")

    def test_secure_delete_file_error(self):
        """Test _secure_delete_file when an error occurs during secure deletion."""

        self.mock_open.side_effect = OSError("Test open error")
        DocumentRetentionManager._secure_delete_file("/test/error_file.txt")
        self.mock_log_warning.assert_called()

    def test_shutdown(self):
        """Test shutdown stops the cleanup thread and deletes remaining files."""

        # Register a file that exists.
        self.retention_manager.processed_files = {"/test/delete.txt": 1617235678.0 - 3600}
        self.mock_exists.return_value = True

        # Simulate a running cleanup thread.
        self.retention_manager._cleanup_thread = MagicMock()
        self.retention_manager._stop_event = MagicMock()
        self.retention_manager._stop_event.is_set.return_value = False
        self.retention_manager.shutdown()
        self.retention_manager._cleanup_thread.join.assert_called_once()
        self.assertFalse(self.retention_manager._thread_running)

        self.mock_unlink.assert_called_with("/test/delete.txt")
        self.mock_log_info.assert_any_call("[GDPR] Retention manager shutdown initiated")
        self.mock_log_info.assert_any_call("[GDPR] Retention manager shutdown complete")
