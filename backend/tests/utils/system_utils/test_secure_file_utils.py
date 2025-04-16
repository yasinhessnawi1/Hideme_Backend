"""
Unit tests for secure_file_utils.py module.

This test file covers the following methods with both positive and negative test cases:
  - _register_temp_file
  - create_secure_temp_file_async
  - create_secure_temp_dir_async

Dependencies such as the retention manager, TimeoutLock, and logging functions are patched.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock, call

# Import the class to test.
from backend.app.utils.system_utils.secure_file_utils import (
    SecureTempFileManager
)


# Asynchronous tests for async methods.

class TestSecureTempFileManagerAsync(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Create a temporary directory for testing.
        self.test_dir = tempfile.mkdtemp()

        # Reset the registry.
        SecureTempFileManager._temp_files_registry = set()

    async def asyncTearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    # Tests for _register_temp_file

    # Use decorator order so that the first parameter is mock_log_warning,
    # then mock_register_processed_file, then mock_timeout_lock.

    @patch('backend.app.utils.system_utils.secure_file_utils.retention_manager.register_processed_file')
    @patch('backend.app.utils.system_utils.secure_file_utils.log_warning')
    @patch('backend.app.utils.system_utils.secure_file_utils.TimeoutLock')
    async def test_register_temp_file_success(self, mock_timeout_lock, mock_log_warning, mock_register_processed_file):
        """(Positive) Test _register_temp_file succeeds when lock is acquired."""

        mock_lock_instance = MagicMock()
        mock_lock_instance.acquire_timeout.return_value.__enter__.return_value = True
        mock_timeout_lock.return_value = mock_lock_instance

        file_path = os.path.join(self.test_dir, "temp.txt")
        retention = 3600

        await SecureTempFileManager._register_temp_file(file_path, retention)

        self.assertIn(file_path, SecureTempFileManager._temp_files_registry)
        mock_register_processed_file.assert_called_once_with(file_path, retention)
        mock_log_warning.assert_not_called()

    @patch('backend.app.utils.system_utils.secure_file_utils.retention_manager.register_processed_file')
    @patch('backend.app.utils.system_utils.secure_file_utils.log_warning')
    async def test_register_temp_file_lock_timeout(self, mock_log_warning, mock_register_processed_file):
        """(Negative) Test _register_temp_file when lock acquisition times out."""

        # Create a context mock that simulates a failed lock acquisition.
        mock_context = MagicMock()
        mock_context.__enter__.return_value = False

        # Patch the acquire_timeout method on the registry lock directly.
        with patch.object(SecureTempFileManager._registry_lock, 'acquire_timeout', return_value=mock_context):
            file_path = os.path.join(self.test_dir, "temp.txt")
            retention = 3600

            await SecureTempFileManager._register_temp_file(file_path, retention)

            # Expect the file NOT to be added to the registry.
            self.assertNotIn(file_path, SecureTempFileManager._temp_files_registry)

            # Retention manager should be called.
            mock_register_processed_file.assert_called_once_with(file_path, retention)

            # A warning should have been logged.
            mock_log_warning.assert_called_once()

    @patch('asyncio.to_thread')
    @patch('os.path.exists')
    @patch('os.path.getsize')
    @patch('tempfile.NamedTemporaryFile')
    @patch('backend.app.utils.system_utils.secure_file_utils.SecureTempFileManager._register_temp_file')
    @patch('backend.app.utils.system_utils.secure_file_utils.SecurityAwareErrorHandler.log_processing_error')
    async def test_create_secure_temp_file_async_size_mismatch(self, mock_log_error, mock_register_temp_file,
                                                               mock_named_temp_file, mock_getsize, mock_exists,
                                                               mock_to_thread):
        """(Negative) Test create_secure_temp_file_async when file size mismatch occurs."""

        # Create a proper mock file object with necessary methods.
        mock_temp_file = MagicMock()
        mock_temp_file.name = os.path.join(self.test_dir, "file.tmp")
        mock_temp_file.write = MagicMock()
        mock_temp_file.flush = MagicMock()
        mock_temp_file.close = MagicMock()
        mock_named_temp_file.return_value = mock_temp_file
        mock_exists.return_value = True

        # Return a size that does not match len(content) (should be 11).
        mock_getsize.return_value = 5
        content = b"Test content"

        with self.assertRaises(IOError):
            await SecureTempFileManager.create_secure_temp_file_async(suffix=".tmp", content=content, prefix="secure_")

        # Verify that secure_delete_file is triggered via asyncio.to_thread.
        mock_to_thread.assert_called_once()
        mock_log_error.assert_called_once()

    @patch('backend.app.utils.system_utils.secure_file_utils.retention_manager.register_processed_file')
    @patch('backend.app.utils.system_utils.secure_file_utils.log_warning')
    async def test_register_temp_file_exception(self, mock_log_warning, mock_register_processed_file):
        """(Negative) Test _register_temp_file when an exception is raised during lock acquisition."""

        # Instead of patching TimeoutLock, patch the acquire_timeout method on the registry lock.
        with patch.object(SecureTempFileManager._registry_lock, 'acquire_timeout',
                          side_effect=Exception("Test exception")):
            file_path = os.path.join(self.test_dir, "temp.txt")
            retention = 3600

            await SecureTempFileManager._register_temp_file(file_path, retention)
            mock_register_processed_file.assert_called_once_with(file_path, retention)

            # Now, log_warning should have been called.
            mock_log_warning.assert_called_once()

    @patch('backend.app.utils.system_utils.secure_file_utils.retention_manager.register_processed_file')
    @patch('backend.app.utils.system_utils.secure_file_utils.TimeoutLock')
    async def test_register_temp_file_default_retention(self, mock_timeout_lock, mock_register_processed_file):
        """(Positive) Test _register_temp_file using default retention when none provided."""
        mock_lock_instance = MagicMock()
        mock_lock_instance.acquire_timeout.return_value.__enter__.return_value = True
        mock_timeout_lock.return_value = mock_lock_instance

        file_path = os.path.join(self.test_dir, "temp.txt")
        await SecureTempFileManager._register_temp_file(file_path)

        mock_register_processed_file.assert_called_once()  # Exact retention value not checked here.

    # Tests for create_secure_temp_file_async

    @patch('backend.app.utils.system_utils.secure_file_utils.SecureTempFileManager._register_temp_file')
    @patch('tempfile.NamedTemporaryFile')
    @patch('backend.app.utils.system_utils.secure_file_utils.log_info')
    async def test_create_secure_temp_file_async_without_content(self, mock_log_info, mock_named_temp_file,
                                                                 mock_register_temp_file):
        """(Positive) Test create_secure_temp_file_async without content."""

        mock_temp_file = MagicMock()
        mock_temp_file.name = os.path.join(self.test_dir, "file.tmp")

        # Ensure the mock file has write/flush/close methods.
        mock_temp_file.write = MagicMock()
        mock_temp_file.flush = MagicMock()
        mock_temp_file.close = MagicMock()
        mock_named_temp_file.return_value = mock_temp_file
        mock_register_temp_file.return_value = None

        result = await SecureTempFileManager.create_secure_temp_file_async(suffix=".tmp", prefix="secure_")
        self.assertEqual(result, mock_temp_file.name)

        mock_named_temp_file.assert_called_once_with(delete=False, suffix=".tmp", prefix="secure_")
        mock_temp_file.write.assert_not_called()
        mock_temp_file.close.assert_called_once()
        mock_register_temp_file.assert_called_once()
        mock_log_info.assert_called_once()

    @patch('backend.app.utils.system_utils.secure_file_utils.SecureTempFileManager._register_temp_file')
    @patch('tempfile.NamedTemporaryFile')
    @patch('os.path.exists')
    @patch('os.path.getsize')
    @patch('backend.app.utils.system_utils.secure_file_utils.log_info')
    async def test_create_secure_temp_file_async_with_content(self, mock_log_info, mock_getsize, mock_exists,
                                                              mock_named_temp_file, mock_register_temp_file):
        """(Positive) Test create_secure_temp_file_async with content."""

        mock_temp_file = MagicMock()
        mock_temp_file.name = os.path.join(self.test_dir, "file.tmp")
        mock_temp_file.write = MagicMock()
        mock_temp_file.flush = MagicMock()
        mock_temp_file.close = MagicMock()
        mock_named_temp_file.return_value = mock_temp_file
        mock_exists.return_value = True
        content = b"Test content"
        mock_getsize.return_value = len(content)
        mock_register_temp_file.return_value = None

        result = await SecureTempFileManager.create_secure_temp_file_async(suffix=".tmp", content=content,
                                                                           prefix="secure_")

        self.assertEqual(result, mock_temp_file.name)
        mock_named_temp_file.assert_called_once_with(delete=False, suffix=".tmp", prefix="secure_")
        mock_temp_file.write.assert_called_once_with(content)
        mock_temp_file.flush.assert_called_once()
        mock_temp_file.close.assert_called_once()
        mock_exists.assert_called_once_with(mock_temp_file.name)
        mock_getsize.assert_called_once_with(mock_temp_file.name)
        mock_register_temp_file.assert_called_once()
        mock_log_info.assert_called_once()

    # Tests for create_secure_temp_dir_async

    @patch('backend.app.utils.system_utils.secure_file_utils.log_info')
    @patch('backend.app.utils.system_utils.secure_file_utils.SecureTempFileManager._register_temp_file')
    @patch('tempfile.mkdtemp')
    async def test_create_secure_temp_dir_async(self, mock_mkdtemp, mock_register_temp_file, mock_log_info):
        """(Positive) Test create_secure_temp_dir_async."""
        temp_dir = os.path.join(self.test_dir, "dir")

        # Ensure mkdtemp returns a valid directory path.
        mock_mkdtemp.return_value = temp_dir
        mock_register_temp_file.return_value = None

        result = await SecureTempFileManager.create_secure_temp_dir_async(prefix="secure_dir_")

        self.assertEqual(result, temp_dir)
        mock_mkdtemp.assert_called_once_with(prefix="secure_dir_")
        mock_register_temp_file.assert_called_once()
        mock_log_info.assert_called_once()


# Synchronous tests for secure_delete_file.

class TestSecureDeleteFile(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.test_dir, "file.txt")

        with open(self.test_file, "wb") as f:
            f.write(b"Short file")
        SecureTempFileManager._temp_files_registry = set()

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    @patch('os.path.exists')
    def test_secure_delete_file_nonexistent(self, mock_exists):
        """(Negative) Test deletion of non-existent file."""
        mock_exists.return_value = False
        result = SecureTempFileManager.secure_delete_file("/nonexistent/file.txt")

        self.assertFalse(result)

    @patch('os.path.exists')
    @patch('os.path.isfile')
    def test_secure_delete_file_not_a_file(self, mock_isfile, mock_exists):
        """(Negative) Test deletion when path is not a file."""
        mock_exists.return_value = True
        mock_isfile.return_value = False

        result = SecureTempFileManager.secure_delete_file(self.test_dir)

        self.assertFalse(result)

    @patch('os.path.exists')
    @patch('os.path.isfile')
    @patch('os.path.getsize')
    @patch('os.unlink')
    def test_secure_delete_large_file(self, mock_unlink, mock_getsize, mock_isfile, mock_exists):
        """(Positive) Test deletion of a large file (skip overwrite)."""
        mock_exists.return_value = True
        mock_isfile.return_value = True
        mock_getsize.return_value = 101 * 1024 * 1024  # > 100 MB.

        result = SecureTempFileManager.secure_delete_file(self.test_file)

        self.assertTrue(result)
        mock_unlink.assert_called_once_with(self.test_file)

    @patch('os.path.exists')
    @patch('os.path.isfile')
    @patch('os.path.getsize')
    @patch('os.urandom')
    @patch('os.fsync')
    @patch('os.unlink')
    @patch('backend.app.utils.system_utils.secure_file_utils.TimeoutLock')
    @patch('backend.app.utils.system_utils.secure_file_utils.retention_manager.unregister_file')
    def test_secure_delete_file_with_overwrite(self, mock_unregister_file, mock_timeout_lock, mock_unlink,
                                               mock_fsync, mock_urandom, mock_getsize, mock_isfile, mock_exists):
        """(Positive) Test deletion of a file with overwrite."""
        mock_exists.return_value = True
        mock_isfile.return_value = True
        mock_getsize.return_value = 11
        mock_urandom.return_value = b"X" * 11

        mock_lock_instance = MagicMock()
        mock_lock_instance.acquire_timeout.return_value.__enter__.return_value = True
        mock_timeout_lock.return_value = mock_lock_instance

        SecureTempFileManager._temp_files_registry.add(self.test_file)
        with patch('builtins.open', new_callable=lambda: unittest.mock.mock_open()) as open_mock:
            file_handle = open_mock.return_value.__enter__.return_value
            file_handle.fileno.return_value = 123
            result = SecureTempFileManager.secure_delete_file(self.test_file)

        self.assertTrue(result)
        open_mock.assert_called_once_with(self.test_file, "r+b")
        file_handle.write.assert_called_once_with(b"X" * 11)
        file_handle.flush.assert_called_once()
        mock_fsync.assert_called_once_with(123)
        mock_unlink.assert_called_once_with(self.test_file)
        self.assertNotIn(self.test_file, SecureTempFileManager._temp_files_registry)
        mock_unregister_file.assert_called_once_with(self.test_file)


# Synchronous tests for secure_delete_directory.

class TestSecureDeleteDirectory(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    @patch('os.path.exists')
    @patch('os.path.isdir')
    def test_secure_delete_directory_invalid(self, mock_isdir, mock_exists):
        """(Negative) Test deletion with invalid directory path."""
        mock_exists.return_value = False
        result = SecureTempFileManager.secure_delete_directory("/nonexistent/dir")

        self.assertFalse(result)

    @patch('os.walk')
    @patch('shutil.rmtree')
    @patch('backend.app.utils.system_utils.secure_file_utils.retention_manager.unregister_file')
    @patch('backend.app.utils.system_utils.secure_file_utils.log_info')
    def test_secure_delete_directory_success(self, mock_log_info, mock_unregister_file, mock_rmtree, mock_walk):
        """(Positive) Test deletion of a directory and its contents."""
        fake_dir = os.path.join(self.test_dir, "fake_dir")
        os.mkdir(fake_dir)
        fake_file = os.path.join(fake_dir, "file.txt")

        with open(fake_file, "wb") as f:
            f.write(b"data")
        mock_walk.return_value = [(fake_dir, [], ["file.txt"])]
        SecureTempFileManager._temp_files_registry.add(fake_dir)

        result = SecureTempFileManager.secure_delete_directory(fake_dir)

        self.assertTrue(result)

        mock_rmtree.assert_called_once_with(fake_dir, ignore_errors=True)
        self.assertNotIn(fake_dir, SecureTempFileManager._temp_files_registry)

        # Expect unregister_file to be called twice: one for the contained file and one for the directory.
        self.assertEqual(mock_unregister_file.call_count, 2)

        expected_calls = [call(os.path.join(fake_dir, "file.txt")), call(fake_dir)]
        mock_unregister_file.assert_has_calls(expected_calls, any_order=True)
        mock_log_info.assert_called_once()

    @patch('os.walk', side_effect=Exception("Walk failed"))
    @patch('backend.app.utils.system_utils.secure_file_utils.SecurityAwareErrorHandler.log_processing_error')
    def test_secure_delete_directory_exception(self, mock_log_error, mock_walk):
        """(Negative) Test deletion of a directory when os.walk raises an exception."""
        result = SecureTempFileManager.secure_delete_directory(self.test_dir)

        self.assertFalse(result)
        mock_log_error.assert_called_once()
