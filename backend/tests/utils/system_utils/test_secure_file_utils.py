import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock, call

from backend.app.utils.system_utils.secure_file_utils import SecureTempFileManager


# Tests for SecureTempFileManager async methods
class TestSecureTempFileManagerAsync(unittest.IsolatedAsyncioTestCase):

    # Setup temporary directory and reset registry
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

        SecureTempFileManager._temp_files_registry = set()

    # Remove temporary directory after async tests
    async def asyncTearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    # Positive test for _register_temp_file when lock is acquired
    @patch(
        "backend.app.utils.system_utils.secure_file_utils.retention_manager.register_processed_file"
    )
    @patch("backend.app.utils.system_utils.secure_file_utils.log_warning")
    @patch("backend.app.utils.system_utils.secure_file_utils.TimeoutLock")
    async def test_register_temp_file_success(
        self, mock_timeout_lock, mock_log_warning, mock_register_processed_file
    ):
        mock_lock_instance = MagicMock()

        mock_lock_instance.acquire_timeout.return_value.__enter__.return_value = True

        mock_timeout_lock.return_value = mock_lock_instance

        file_path = os.path.join(self.test_dir, "temp.txt")

        retention = 3600

        await SecureTempFileManager._register_temp_file(file_path, retention)

        self.assertIn(file_path, SecureTempFileManager._temp_files_registry)

        mock_register_processed_file.assert_called_once_with(file_path, retention)

        mock_log_warning.assert_not_called()

    # Negative test for _register_temp_file when lock acquisition times out
    @patch(
        "backend.app.utils.system_utils.secure_file_utils.retention_manager.register_processed_file"
    )
    @patch("backend.app.utils.system_utils.secure_file_utils.log_warning")
    async def test_register_temp_file_lock_timeout(
        self, mock_log_warning, mock_register_processed_file
    ):
        mock_context = MagicMock()

        mock_context.__enter__.return_value = False

        with patch.object(
            SecureTempFileManager._registry_lock,
            "acquire_timeout",
            return_value=mock_context,
        ):
            file_path = os.path.join(self.test_dir, "temp.txt")

            retention = 3600

            await SecureTempFileManager._register_temp_file(file_path, retention)

            self.assertNotIn(file_path, SecureTempFileManager._temp_files_registry)

            mock_register_processed_file.assert_called_once_with(file_path, retention)

            mock_log_warning.assert_called_once()

    # Negative test for create_secure_temp_file_async when size mismatch occurs
    @patch("asyncio.to_thread")
    @patch("os.path.exists")
    @patch("os.path.getsize")
    @patch("tempfile.NamedTemporaryFile")
    @patch(
        "backend.app.utils.system_utils.secure_file_utils.SecureTempFileManager._register_temp_file"
    )
    @patch(
        "backend.app.utils.system_utils.secure_file_utils.SecurityAwareErrorHandler.log_processing_error"
    )
    async def test_create_secure_temp_file_async_size_mismatch(
        self,
        mock_log_error,
        mock_register_temp_file,
        mock_named_temp_file,
        mock_getsize,
        mock_exists,
        mock_to_thread,
    ):
        mock_temp_file = MagicMock()

        mock_temp_file.name = os.path.join(self.test_dir, "file.tmp")

        mock_temp_file.write = MagicMock()

        mock_temp_file.flush = MagicMock()

        mock_temp_file.close = MagicMock()

        mock_named_temp_file.return_value = mock_temp_file

        mock_exists.return_value = True

        mock_getsize.return_value = 5

        content = b"Test content"

        with self.assertRaises(IOError):
            await SecureTempFileManager.create_secure_temp_file_async(
                suffix=".tmp", content=content, prefix="secure_"
            )

        mock_to_thread.assert_called_once()

        mock_log_error.assert_called_once()

    # Negative test for _register_temp_file when exception during lock acquisition
    @patch(
        "backend.app.utils.system_utils.secure_file_utils.retention_manager.register_processed_file"
    )
    @patch("backend.app.utils.system_utils.secure_file_utils.log_warning")
    async def test_register_temp_file_exception(
        self, mock_log_warning, mock_register_processed_file
    ):
        with patch.object(
            SecureTempFileManager._registry_lock,
            "acquire_timeout",
            side_effect=Exception("Test exception"),
        ):
            file_path = os.path.join(self.test_dir, "temp.txt")

            retention = 3600

            await SecureTempFileManager._register_temp_file(file_path, retention)

            mock_register_processed_file.assert_called_once_with(file_path, retention)

            mock_log_warning.assert_called_once()

    # Positive test for _register_temp_file using default retention
    @patch(
        "backend.app.utils.system_utils.secure_file_utils.retention_manager.register_processed_file"
    )
    @patch("backend.app.utils.system_utils.secure_file_utils.TimeoutLock")
    async def test_register_temp_file_default_retention(
        self, mock_timeout_lock, mock_register_processed_file
    ):
        mock_lock_instance = MagicMock()

        mock_lock_instance.acquire_timeout.return_value.__enter__.return_value = True

        mock_timeout_lock.return_value = mock_lock_instance

        file_path = os.path.join(self.test_dir, "temp.txt")

        await SecureTempFileManager._register_temp_file(file_path)

        mock_register_processed_file.assert_called_once()

    # Positive test for create_secure_temp_file_async without content
    @patch(
        "backend.app.utils.system_utils.secure_file_utils.SecureTempFileManager._register_temp_file"
    )
    @patch("tempfile.NamedTemporaryFile")
    @patch("backend.app.utils.system_utils.secure_file_utils.log_info")
    async def test_create_secure_temp_file_async_without_content(
        self, mock_log_info, mock_named_temp_file, mock_register_temp_file
    ):
        mock_temp_file = MagicMock()

        mock_temp_file.name = os.path.join(self.test_dir, "file.tmp")

        mock_temp_file.write = MagicMock()

        mock_temp_file.flush = MagicMock()

        mock_temp_file.close = MagicMock()

        mock_named_temp_file.return_value = mock_temp_file

        mock_register_temp_file.return_value = None

        result = await SecureTempFileManager.create_secure_temp_file_async(
            suffix=".tmp", prefix="secure_"
        )

        self.assertEqual(result, mock_temp_file.name)

        mock_named_temp_file.assert_called_once_with(
            delete=False, suffix=".tmp", prefix="secure_"
        )

        mock_temp_file.write.assert_not_called()

        mock_temp_file.close.assert_called_once()

        mock_register_temp_file.assert_called_once()

        mock_log_info.assert_called_once()

    # Positive test for create_secure_temp_file_async with content
    @patch(
        "backend.app.utils.system_utils.secure_file_utils.SecureTempFileManager._register_temp_file"
    )
    @patch("tempfile.NamedTemporaryFile")
    @patch("os.path.exists")
    @patch("os.path.getsize")
    @patch("backend.app.utils.system_utils.secure_file_utils.log_info")
    async def test_create_secure_temp_file_async_with_content(
        self,
        mock_log_info,
        mock_getsize,
        mock_exists,
        mock_named_temp_file,
        mock_register_temp_file,
    ):
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

        result = await SecureTempFileManager.create_secure_temp_file_async(
            suffix=".tmp", content=content, prefix="secure_"
        )

        self.assertEqual(result, mock_temp_file.name)

        mock_named_temp_file.assert_called_once_with(
            delete=False, suffix=".tmp", prefix="secure_"
        )

        mock_temp_file.write.assert_called_once_with(content)

        mock_temp_file.flush.assert_called_once()

        mock_temp_file.close.assert_called_once()

        mock_exists.assert_called_once_with(mock_temp_file.name)

        mock_getsize.assert_called_once_with(mock_temp_file.name)

        mock_register_temp_file.assert_called_once()

        mock_log_info.assert_called_once()

    # Positive test for create_secure_temp_dir_async
    @patch("backend.app.utils.system_utils.secure_file_utils.log_info")
    @patch(
        "backend.app.utils.system_utils.secure_file_utils.SecureTempFileManager._register_temp_file"
    )
    @patch("tempfile.mkdtemp")
    async def test_create_secure_temp_dir_async(
        self, mock_mkdtemp, mock_register_temp_file, mock_log_info
    ):
        temp_dir = os.path.join(self.test_dir, "dir")

        mock_mkdtemp.return_value = temp_dir

        mock_register_temp_file.return_value = None

        result = await SecureTempFileManager.create_secure_temp_dir_async(
            prefix="secure_dir_"
        )

        self.assertEqual(result, temp_dir)

        mock_mkdtemp.assert_called_once_with(prefix="secure_dir_")

        mock_register_temp_file.assert_called_once()

        mock_log_info.assert_called_once()


# Tests for secure_delete_file
class TestSecureDeleteFile(unittest.TestCase):

    # Setup test file and registry
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

        self.test_file = os.path.join(self.test_dir, "file.txt")

        with open(self.test_file, "wb") as f:
            f.write(b"Short file")

        SecureTempFileManager._temp_files_registry = set()

    # Remove test directory after tests
    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    # Negative test for deletion of non-existent file
    @patch("os.path.exists")
    def test_secure_delete_file_nonexistent(self, mock_exists):
        mock_exists.return_value = False

        result = SecureTempFileManager.secure_delete_file("/nonexistent/file.txt")

        self.assertFalse(result)

    # Negative test when path is not a file
    @patch("os.path.exists")
    @patch("os.path.isfile")
    def test_secure_delete_file_not_a_file(self, mock_isfile, mock_exists):
        mock_exists.return_value = True

        mock_isfile.return_value = False

        result = SecureTempFileManager.secure_delete_file(self.test_dir)

        self.assertFalse(result)

    # Positive test for deletion of a large file
    @patch("os.path.exists")
    @patch("os.path.isfile")
    @patch("os.path.getsize")
    @patch("os.unlink")
    def test_secure_delete_large_file(
        self, mock_unlink, mock_getsize, mock_isfile, mock_exists
    ):
        mock_exists.return_value = True

        mock_isfile.return_value = True

        mock_getsize.return_value = 101 * 1024 * 1024

        result = SecureTempFileManager.secure_delete_file(self.test_file)

        self.assertTrue(result)

        mock_unlink.assert_called_once_with(self.test_file)

    # Positive test for deletion of a file with overwrite
    @patch("os.path.exists")
    @patch("os.path.isfile")
    @patch("os.path.getsize")
    @patch("os.urandom")
    @patch("os.fsync")
    @patch("os.unlink")
    @patch("backend.app.utils.system_utils.secure_file_utils.TimeoutLock")
    @patch(
        "backend.app.utils.system_utils.secure_file_utils.retention_manager.unregister_file"
    )
    def test_secure_delete_file_with_overwrite(
        self,
        mock_unregister_file,
        mock_timeout_lock,
        mock_unlink,
        mock_fsync,
        mock_urandom,
        mock_getsize,
        mock_isfile,
        mock_exists,
    ):
        mock_exists.return_value = True

        mock_isfile.return_value = True

        mock_getsize.return_value = 11

        mock_urandom.return_value = b"X" * 11

        mock_lock_instance = MagicMock()

        mock_lock_instance.acquire_timeout.return_value.__enter__.return_value = True

        mock_timeout_lock.return_value = mock_lock_instance

        SecureTempFileManager._temp_files_registry.add(self.test_file)

        with patch(
            "builtins.open", new_callable=lambda: unittest.mock.mock_open()
        ) as open_mock:
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


# Tests for secure_delete_directory
class TestSecureDeleteDirectory(unittest.TestCase):

    # Setup test directory
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    # Remove test directory after tests
    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    # Negative test for invalid directory path
    @patch("os.path.exists")
    @patch("os.path.isdir")
    def test_secure_delete_directory_invalid(self, mock_isdir, mock_exists):
        mock_exists.return_value = False

        result = SecureTempFileManager.secure_delete_directory("/nonexistent/dir")

        self.assertFalse(result)

    # Positive test for deletion of directory and contents
    @patch("os.walk")
    @patch("shutil.rmtree")
    @patch(
        "backend.app.utils.system_utils.secure_file_utils.retention_manager.unregister_file"
    )
    @patch("backend.app.utils.system_utils.secure_file_utils.log_info")
    def test_secure_delete_directory_success(
        self, mock_log_info, mock_unregister_file, mock_rmtree, mock_walk
    ):
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

        self.assertEqual(mock_unregister_file.call_count, 2)

        expected_calls = [call(os.path.join(fake_dir, "file.txt")), call(fake_dir)]

        mock_unregister_file.assert_has_calls(expected_calls, any_order=True)

        mock_log_info.assert_called_once()

    # Negative test for deletion when os.walk raises exception
    @patch("os.walk", side_effect=Exception("Walk failed"))
    @patch(
        "backend.app.utils.system_utils.secure_file_utils.SecurityAwareErrorHandler.log_processing_error"
    )
    def test_secure_delete_directory_exception(self, mock_log_error, mock_walk):
        result = SecureTempFileManager.secure_delete_directory(self.test_dir)

        self.assertFalse(result)

        mock_log_error.assert_called_once()
