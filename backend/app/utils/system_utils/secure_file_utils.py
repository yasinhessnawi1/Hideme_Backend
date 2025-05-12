"""
Enhanced secure file handling utilities with improved in-memory processing and batch support.
This module provides comprehensive utilities for securely handling files with a preference for in-memory operations when possible.
It ensures proper cleanup, secure deletion.
"""

import asyncio
import hashlib
import logging
import os
import shutil
import tempfile
import time
from typing import Optional, TypeVar

from backend.app.configs.gdpr_config import TEMP_FILE_RETENTION_SECONDS
from backend.app.utils.logging.logger import log_info, log_warning
from backend.app.utils.security.retention_management import retention_manager
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.system_utils.synchronization_utils import (
    TimeoutLock,
    LockPriority,
    logger,
)

# Configure module-specific logger.
_logger = logging.getLogger("secure_file_utils")
# Define a generic type variable.
T = TypeVar("T")


class SecureTempFileManager:
    """
    Provides secure temporary file and directory creation and deletion utilities.

    This class offers methods to create secure temporary files or directories, register them for cleanup
    using a retention manager, and securely delete them using random data overwrites when possible.
    Batch support is enhanced by asynchronous operations and centralized registry tracking.
    """

    # Registry for tracking created temporary files and directories.
    _temp_files_registry = set()
    # Lock for synchronizing access to the registry.
    _registry_lock = TimeoutLock(
        "temp_files_registry_lock", LockPriority.MEDIUM, 3.0, is_instance_lock=True
    )

    @staticmethod
    async def _register_temp_file(
        file_path: str, retention_seconds: Optional[int] = None
    ) -> None:
        """
        Register a temporary file for cleanup tracking.

        Args:
            file_path (str): Path to the temporary file or directory.
            retention_seconds (Optional[int]): Optional retention period in seconds.

        This method attempts to acquire a lock and, on success, adds the file path to a registry.
        It also registers the file with the retention manager for scheduled deletion.
        """
        # Attempt to acquire the registry lock with a timeout.
        try:
            with SecureTempFileManager._registry_lock.acquire_timeout(
                timeout=3.0
            ) as acquired:
                # Check if the lock was acquired successfully.
                if not acquired:
                    # Log a warning if unable to register within the timeout.
                    log_warning(
                        f"[SECURITY] Timeout registering temp file {os.path.basename(file_path)}, continuing without registry tracking"
                    )
                else:
                    # Add file_labeling_path to the temporary file's registry.
                    SecureTempFileManager._temp_files_registry.add(file_path)
        except Exception as e:
            # Log any exception that occurs during registration.
            log_warning(f"[SECURITY] Error registering temp file: {e}")

        # Register the file with the retention manager using provided retention_seconds if available.
        if retention_seconds is not None:
            retention_manager.register_processed_file(file_path, retention_seconds)
        else:
            # Otherwise, register with the default temporary file retention seconds.
            retention_manager.register_processed_file(
                file_path, TEMP_FILE_RETENTION_SECONDS
            )

    @staticmethod
    async def create_secure_temp_file_async(
        suffix: str = ".tmp",
        content: Optional[bytes] = None,
        prefix: str = "secure_",
        retention_seconds: Optional[int] = None,
    ) -> str:
        """
        Asynchronously create a secure temporary file with optional content and register it for cleanup.

        Args:
            suffix (str): File extension to use for the temporary file.
            content (Optional[bytes]): Optional file content to write into the file.
            prefix (str): Filename prefix for the temporary file.
            retention_seconds (Optional[int]): Optional retention period in seconds.

        Returns:
            str: The path to the created temporary file.

        This method creates a temporary file, writes content if provided, validates the file size,
        registers the file for automatic cleanup, and logs creation details.
        """
        # Create a trace identifier for logging purposes.
        trace_id = (
            f"secure_file_{time.time()}_{hashlib.md5(prefix.encode()).hexdigest()[:6]}"
        )
        # Initialize a variable to hold the temporary file object.
        temp_file = None
        try:
            # Create a temporary file that will not be deleted automatically.
            temp_file = tempfile.NamedTemporaryFile(
                delete=False, suffix=suffix, prefix=prefix
            )
            # Check if content is provided.
            if content:
                # Write provided content into the temporary file.
                temp_file.write(content)
                # Ensure content is flushed to disk.
                temp_file.flush()
            # Close the file to release the file handle.
            temp_file.close()

            # If content was provided and the file exists, validate file size.
            if content and os.path.exists(temp_file.name):
                # Get the actual file size.
                file_size = os.path.getsize(temp_file.name)
                # Raise an error if expected and actual sizes do not match.
                if file_size != len(content):
                    raise IOError(
                        f"File size mismatch: expected {len(content)}, got {file_size}"
                    )

            # Asynchronously register the file for cleanup.
            await SecureTempFileManager._register_temp_file(
                temp_file.name, retention_seconds or TEMP_FILE_RETENTION_SECONDS
            )

            # Log information about the successful creation of the file.
            log_info(
                f"[SECURITY] Created secure temporary file: {os.path.basename(temp_file.name)} "
                f"({len(content) / 1024 if content else 0:.1f}KB) [trace_id={trace_id}]"
            )
            # Return the path to the created temporary file.
            return temp_file.name
        except Exception as e:
            # If an error occurs and the temporary file exists, attempt to delete it securely.
            if temp_file and os.path.exists(temp_file.name):
                await asyncio.to_thread(
                    SecureTempFileManager.secure_delete_file, temp_file.name
                )
            # Log the processing error with the error handler.
            SecurityAwareErrorHandler.log_processing_error(
                e, "secure_temp_file_creation", trace_id=trace_id
            )
            # Re-raise the exception.
            raise e

    @staticmethod
    async def create_secure_temp_dir_async(
        prefix: str = "secure_dir_", retention_seconds: Optional[int] = None
    ) -> str:
        """
        Asynchronously create a secure temporary directory and register it for cleanup.

        Args:
            prefix (str): Directory name prefix for the temporary directory.
            retention_seconds (Optional[int]): Optional retention period in seconds.

        Returns:
            str: The path to the created temporary directory.

        This method creates a temporary directory using Python's tempfile module,
        registers it for cleanup, and logs the operation.
        """
        # Create a temporary directory with the specified prefix.
        temp_dir = tempfile.mkdtemp(prefix=prefix)

        # Asynchronously register the directory for cleanup tracking.
        await SecureTempFileManager._register_temp_file(
            temp_dir, retention_seconds or TEMP_FILE_RETENTION_SECONDS
        )

        # Log the creation of the temporary directory.
        log_info(
            f"[SECURITY] Created secure temporary directory: {os.path.basename(temp_dir)}"
        )
        # Return the path to the directory.
        return temp_dir

    @staticmethod
    def secure_delete_file(file_path: str) -> bool:
        """
        Securely delete a file by performing a single overwrite with random data before removal.

        Args:
            file_path (str): The path to the file to delete.

        Returns:
            bool: True if deletion was successful, False otherwise.

        This method verifies the file's existence, optionally overwrites its contents with random data for security,
        then deletes it. It also unregisters the file from internal tracking and the retention manager.
        """
        # Check if the file_labeling_path is valid and corresponds to an existing file.
        if (
            not file_path
            or not os.path.exists(file_path)
            or not os.path.isfile(file_path)
        ):
            # Return False immediately if file does not exist or is not a regular file.
            return False
        try:
            # Get the size of the file.
            file_size = os.path.getsize(file_path)
            # If the file is larger than 100 MB, skip overwriting to conserve resources.
            if file_size > 100 * 1024 * 1024:
                # Delete the file using regular deletion.
                os.unlink(file_path)
                # Return True indicating deletion was successful.
                return True
            # Open the file in read and write binary mode.
            with open(file_path, "r+b") as f:
                # Overwrite the entire file with random bytes.
                f.write(os.urandom(file_size))
                # Flush the written data.
                f.flush()
                # Ensure data is physically written to disk.
                os.fsync(f.fileno())
            # Delete the file after overwriting.
            os.unlink(file_path)

            # Attempt to acquire the registry lock to unregister the file.
            try:
                with SecureTempFileManager._registry_lock.acquire_timeout(
                    timeout=1.0
                ) as acquired:
                    # If lock was acquired and the file is tracked, remove it.
                    if (
                        acquired
                        and file_path in SecureTempFileManager._temp_files_registry
                    ):
                        SecureTempFileManager._temp_files_registry.remove(file_path)
            except TimeoutError:
                # Log a warning if the lock acquisition times out.
                logger.warning(
                    f"[SECURITY] Timeout while unregistering file: {os.path.basename(file_path)}"
                )

            # Unregister the file from the retention manager.
            retention_manager.unregister_file(file_path)

            # Log a debug message indicating successful secure deletion.
            _logger.debug(f"Securely deleted file: {os.path.basename(file_path)}")
            # Return True signaling success.
            return True
        except Exception as e:
            # Log a warning if secure deletion fails.
            log_warning(
                f"[SECURITY] Failed to securely delete file: {os.path.basename(file_path)} - {e}"
            )
            try:
                # As a fallback, attempt a regular deletion.
                if os.path.exists(file_path):
                    os.unlink(file_path)
                    # Log info about the fallback deletion.
                    log_info(
                        f"[SECURITY] Deleted file (regular deletion): {os.path.basename(file_path)}"
                    )
                    return True
            except Exception as fallback_ex:
                # Log a warning if the fallback deletion also fails.
                log_warning(
                    f"[SECURITY] Fallback deletion failed for file: {os.path.basename(file_path)} - {fallback_ex}"
                )
            # Return False if deletion ultimately failed.
            return False

    @staticmethod
    def secure_delete_directory(dir_path: str) -> bool:
        """
        Securely delete a directory and all its contents.

        Args:
            dir_path (str): The path to the directory to delete.

        Returns:
            bool: True if deletion was successful, False otherwise.

        This method recursively deletes all files within the directory using secure deletion,
        then removes the directory itself. It unregisters the directory from tracking systems.
        """
        # Verify that the directory exists and is indeed a directory.
        if not dir_path or not os.path.exists(dir_path) or not os.path.isdir(dir_path):
            # Return False if directory path is invalid.
            return False
        try:
            # Walk the directory tree from the bottom up.
            for root, dirs, files in os.walk(dir_path, topdown=False):
                # For each file in the directory, perform secure deletion.
                for file in files:
                    SecureTempFileManager.secure_delete_file(os.path.join(root, file))
            # Remove the entire directory tree.
            shutil.rmtree(dir_path, ignore_errors=True)

            # Attempt to acquire the registry lock to unregister the directory.
            try:
                with SecureTempFileManager._registry_lock.acquire_timeout(
                    timeout=1.0
                ) as acquired:
                    # If lock acquired and directory is tracked, remove it.
                    if (
                        acquired
                        and dir_path in SecureTempFileManager._temp_files_registry
                    ):
                        SecureTempFileManager._temp_files_registry.remove(dir_path)
            except TimeoutError:
                # Continue silently if unregistering fails due to timeout.
                pass

            # Unregister the directory from the retention manager.
            retention_manager.unregister_file(dir_path)

            # Log information about the successful secure deletion of the directory.
            log_info(
                f"[SECURITY] Securely deleted directory: {os.path.basename(dir_path)}"
            )
            # Return True indicating success.
            return True
        except Exception as e:
            # Log the error using the error handler for directory deletion.
            SecurityAwareErrorHandler.log_processing_error(
                e, "directory_secure_deletion", dir_path
            )
            # Return False upon failure.
            return False
