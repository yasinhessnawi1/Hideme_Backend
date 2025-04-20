import os

import unittest

from unittest.mock import patch, MagicMock, mock_open

from backend.app.configs.gdpr_config import TEMP_FILE_RETENTION_SECONDS

from backend.app.utils.security.retention_management import DocumentRetentionManager


# Ensure DocumentRetentionManager is a singleton and initializes properly
class TestDocumentRetentionManager(unittest.TestCase):
    """Unit tests for DocumentRetentionManager class."""

    # Set up patches and a fresh manager before each test
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

        self.mock_isfile.side_effect = lambda path: False if path == "/test/dir" else True

        self.isdir_patcher = patch('os.path.isdir')

        self.mock_isdir = self.isdir_patcher.start()

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

    # Stop all patches and threads after each test
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

    # Verify singleton behavior of DocumentRetentionManager
    def test_singleton_pattern(self):
        DocumentRetentionManager._instance = None

        manager1 = DocumentRetentionManager()

        manager2 = DocumentRetentionManager()

        self.assertIs(manager1, manager2)

    # Check that initialization sets defaults and logs info
    def test_init(self):
        self.assertEqual(self.retention_manager.processed_files, {})

        self.assertEqual(self.retention_manager.permanent_files, set())

        self.assertIsNone(self.retention_manager._cleanup_thread)

        self.assertFalse(self.retention_manager._thread_running)

        self.assertFalse(self.retention_manager._stop_event.is_set())

        self.mock_log_info.assert_called_with(
            "[GDPR] Document retention manager initialized"
        )

    # Ensure start spawns a cleanup thread and logs appropriately
    def test_start(self):
        self.retention_manager.start()

        self.mock_thread.assert_called_once()

        self.mock_thread.return_value.start.assert_called_once()

        self.assertTrue(self.retention_manager._thread_running)

        self.mock_log_info.assert_any_call("[GDPR] Retention manager service started")

        self.mock_log_info.assert_any_call("[GDPR] Retention cleanup thread started")

    # Starting when already running should be a no-op with log
    def test_start_already_running(self):
        self.retention_manager._thread_running = True

        self.retention_manager.start()

        self.mock_thread.assert_not_called()

        self.mock_log_info.assert_called_with(
            "[GDPR] Retention manager service already running"
        )

    # Registering a processed file schedules its deletion and logs the action
    def test_register_processed_file(self):
        self.retention_manager.register_processed_file("/test/file.txt", 3600)

        self.assertIn("/test/file.txt", self.retention_manager.processed_files)

        self.assertEqual(
            self.retention_manager.processed_files["/test/file.txt"],
            1617235678.0 + 3600
        )

        self.mock_log_info.assert_called_with(
            "[GDPR] Registered file for retention: file.txt"
        )

    # Default retention uses TEMP_FILE_RETENTION_SECONDS when none provided
    def test_register_processed_file_default_retention(self):
        self.retention_manager.register_processed_file("/test/file.txt")

        self.assertIn("/test/file.txt", self.retention_manager.processed_files)

        self.assertEqual(
            self.retention_manager.processed_files["/test/file.txt"],
            1617235678.0 + TEMP_FILE_RETENTION_SECONDS
        )

    # Unregistering removes file from tracking and logs the removal
    def test_unregister_file(self):
        self.retention_manager.processed_files["/test/file.txt"] = 1617235678.0 + 3600

        self.retention_manager.permanent_files.add("/test/file.txt")

        self.retention_manager.unregister_file("/test/file.txt")

        self.assertNotIn("/test/file.txt", self.retention_manager.processed_files)

        self.assertNotIn("/test/file.txt", self.retention_manager.permanent_files)

        self.mock_log_info.assert_called_with(
            "[GDPR] Unregistered file from retention management: file.txt"
        )

    # Unregistering a non-registered file still logs the attempt
    def test_unregister_file_not_registered(self):
        self.retention_manager.unregister_file("/test/nonexistent.txt")

        self.mock_log_info.assert_called_with(
            "[GDPR] Unregistered file from retention management: nonexistent.txt"
        )

    # Expired files are securely deleted; others retained
    def test_cleanup_expired_files(self):
        self.retention_manager.processed_files = {
            "/test/expired.txt": 1617235678.0 - 3600,
            "/test/not_expired.txt": 1617235678.0 + 3600
        }

        state = {"deleted": False}

        def exists_side_effect(path):
            if path == "/test/expired.txt":
                return not state["deleted"]
            return False

        self.mock_exists.side_effect = exists_side_effect

        def fake_secure_delete(path):
            os.unlink(path)
            state["deleted"] = True

        with patch.object(self.retention_manager, '_secure_delete_file', side_effect=fake_secure_delete):
            self.retention_manager.cleanup_expired_files()

        self.assertNotIn("/test/expired.txt", self.retention_manager.processed_files)

        self.assertIn("/test/not_expired.txt", self.retention_manager.processed_files)

        self.mock_unlink.assert_called_once_with("/test/expired.txt")

        self.mock_log_info.assert_any_call(
            "[GDPR] Successfully deleted file: expired.txt"
        )

    # Permanent files are removed from tracking without deletion
    def test_cleanup_expired_files_permanent(self):
        self.retention_manager.processed_files = {"/test/permanent.txt": 1617235678.0 - 3600}

        self.retention_manager.permanent_files.add("/test/permanent.txt")

        self.retention_manager.cleanup_expired_files()

        self.assertNotIn("/test/permanent.txt", self.retention_manager.processed_files)

        self.mock_unlink.assert_not_called()

    # Nonexistent files are skipped without errors
    def test_cleanup_expired_files_nonexistent(self):
        self.retention_manager.processed_files = {"/test/nonexistent.txt": 1617235678.0 - 3600}

        self.mock_exists.side_effect = lambda path: False

        self.retention_manager.cleanup_expired_files()

        self.assertNotIn("/test/nonexistent.txt", self.retention_manager.processed_files)

        self.mock_unlink.assert_not_called()

    # Errors during deletion are caught and logged as warnings
    def test_cleanup_expired_files_deletion_error(self):
        self.retention_manager.processed_files = {"/test/error.txt": 1617235678.0 - 3600}

        self.mock_unlink.side_effect = OSError("Test deletion error")

        self.retention_manager.cleanup_expired_files()

        self.assertNotIn("/test/error.txt", self.retention_manager.processed_files)

        self.mock_log_warning.assert_called()

    # Secure delete does nothing when the path doesn't exist
    def test_secure_delete_nonexistent_path(self):
        self.mock_exists.return_value = False

        self.retention_manager._secure_delete("/test/nonexistent.txt")

    # Secure delete erases file contents securely and removes it
    def test_secure_delete_file(self):
        self.mock_exists.return_value = True

        self.mock_isfile.side_effect = lambda path: True if path == "/test/file.txt" else False

        self.mock_isdir.side_effect = lambda path: False

        self.retention_manager._secure_delete("/test/file.txt")

        self.mock_getsize.assert_called_once_with("/test/file.txt")

        self.mock_open.assert_called_once_with("/test/file.txt", "wb")

        self.mock_unlink.assert_called_once_with("/test/file.txt")

    # Secure delete on directory walks and removes it
    def test_secure_delete_directory(self):
        self.mock_exists.return_value = True

        self.mock_isfile.side_effect = lambda path: False if path == "/test/dir" else True

        self.mock_isdir.side_effect = lambda path: True if path == "/test/dir" else False

        self.retention_manager._secure_delete("/test/dir")

        self.mock_walk.assert_called_once_with("/test/dir", topdown=False)

        self.mock_rmtree.assert_called_once_with("/test/dir", ignore_errors=False)

    # Large files are simply unlinked without zeroing
    def test_secure_delete_file_large(self):
        self.mock_getsize.return_value = 150 * 1024 * 1024  # 150MB

        DocumentRetentionManager._secure_delete_file("/test/large_file.txt")

        self.mock_unlink.assert_called_once_with("/test/large_file.txt")

        self.mock_open.assert_not_called()

    # Small files are overwritten multiple times before deletion
    def test_secure_delete_file_small(self):
        self.mock_getsize.return_value = 1024  # 1KB

        DocumentRetentionManager._secure_delete_file("/test/small_file.txt")

        self.mock_open.assert_called_once_with("/test/small_file.txt", "wb")

        file_handle = self.mock_open.return_value.__enter__.return_value

        self.assertEqual(file_handle.seek.call_count, 5)

        self.assertEqual(file_handle.write.call_count, 5)

        self.assertEqual(file_handle.flush.call_count, 5)

        self.assertEqual(self.mock_fsync.call_count, 5)

        self.mock_unlink.assert_called_once_with("/test/small_file.txt")

    # Errors zeroing or deleting file are caught and warned
    def test_secure_delete_file_error(self):
        self.mock_open.side_effect = OSError("Test open error")

        DocumentRetentionManager._secure_delete_file("/test/error_file.txt")

        self.mock_log_warning.assert_called()

    # Shutdown stops the cleanup thread and securely deletes pending files
    def test_shutdown(self):
        self.retention_manager.processed_files = {"/test/delete.txt": 1617235678.0 - 3600}

        self.mock_exists.return_value = True

        self.retention_manager._cleanup_thread = MagicMock()

        self.retention_manager._stop_event = MagicMock()

        self.retention_manager._stop_event.is_set.return_value = False

        self.retention_manager.shutdown()

        self.retention_manager._cleanup_thread.join.assert_called_once()

        self.assertFalse(self.retention_manager._thread_running)

        self.mock_unlink.assert_called_with("/test/delete.txt")

        self.mock_log_info.assert_any_call("[GDPR] Retention manager shutdown initiated")

        self.mock_log_info.assert_any_call("[GDPR] Retention manager shutdown complete")
