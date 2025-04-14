"""
Enhanced secure file handling utilities with improved in-memory processing and batch support.

This module provides comprehensive utilities for securely handling files with a preference for
in-memory operations when possible. It ensures proper cleanup, secure deletion, and optimized
buffer management (via buffer pooling) to reduce memory copying, now with enhanced support
for batch operations leveraging centralized document processing.
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
from backend.app.utils.system_utils.synchronization_utils import TimeoutLock, LockPriority, logger

_logger = logging.getLogger("secure_file_utils")
T = TypeVar('T')


class SecureTempFileManager:
    # Registry of all created temporary files for cleanup tracking
    _temp_files_registry = set()
    _registry_lock = TimeoutLock("temp_files_registry_lock", LockPriority.MEDIUM, 3.0, is_instance_lock=True)

    @staticmethod
    async def _register_temp_file(file_path: str, retention_seconds: Optional[int] = None) -> None:
        """
        Register a temporary file for cleanup tracking.

        Args:
            file_path: Path to the temporary file
            retention_seconds: Optional retention period in seconds
        """
        try:
            with SecureTempFileManager._registry_lock.acquire_timeout(timeout=3.0) as acquired:
                if not acquired:
                    log_warning(f"[SECURITY] Timeout registering temp file {os.path.basename(file_path)}, "
                                "continuing without registry tracking")
                else:
                    SecureTempFileManager._temp_files_registry.add(file_path)
        except Exception as e:
            log_warning(f"[SECURITY] Error registering temp file: {e}")

        # Register with retention manager if retention period specified
        if retention_seconds is not None:
            retention_manager.register_processed_file(file_path, retention_seconds)
        else:
            retention_manager.register_processed_file(file_path, TEMP_FILE_RETENTION_SECONDS)

    @staticmethod
    async def create_secure_temp_file_async(suffix: str = ".tmp", content: Optional[bytes] = None,
                                            prefix: str = "secure_", retention_seconds: Optional[int] = None) -> str:
        """
        Asynchronously create a secure temporary file with optional content and register it for cleanup.
        This is the primary method to use for temporary file creation.

        Args:
            suffix: File extension.
            content: Optional content.
            prefix: Filename prefix.
            retention_seconds: Optional retention period in seconds.

        Returns:
            Path to the created file.
        """
        trace_id = f"secure_file_{time.time()}_{hashlib.md5(prefix.encode()).hexdigest()[:6]}"
        temp_file = None
        try:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix=prefix)
            if content:
                temp_file.write(content)
                temp_file.flush()
            temp_file.close()

            if content and os.path.exists(temp_file.name):
                file_size = os.path.getsize(temp_file.name)
                if file_size != len(content):
                    raise IOError(f"File size mismatch: expected {len(content)}, got {file_size}")

            # Register file for cleanup tracking
            await SecureTempFileManager._register_temp_file(
                temp_file.name,
                retention_seconds or TEMP_FILE_RETENTION_SECONDS
            )

            log_info(f"[SECURITY] Created secure temporary file: {os.path.basename(temp_file.name)} "
                     f"({len(content) / 1024 if content else 0:.1f}KB) [trace_id={trace_id}]")
            return temp_file.name
        except Exception as e:
            if temp_file and os.path.exists(temp_file.name):
                await asyncio.to_thread(SecureTempFileManager.secure_delete_file, temp_file.name)
            SecurityAwareErrorHandler.log_processing_error(e, "secure_temp_file_creation", trace_id=trace_id)
            raise e

    @staticmethod
    async def create_secure_temp_dir_async(prefix: str = "secure_dir_", retention_seconds: Optional[int] = None) -> str:
        """
        Asynchronously create a secure temporary directory and register it for cleanup.

        Args:
            prefix: Directory name prefix.
            retention_seconds: Optional retention period in seconds.

        Returns:
            Path to the created directory.
        """
        temp_dir = tempfile.mkdtemp(prefix=prefix)

        # Register directory for cleanup tracking
        await SecureTempFileManager._register_temp_file(
            temp_dir,
            retention_seconds or TEMP_FILE_RETENTION_SECONDS
        )

        log_info(f"[SECURITY] Created secure temporary directory: {os.path.basename(temp_dir)}")
        return temp_dir

    @staticmethod
    def secure_delete_file(file_path: str) -> bool:
        """
        Securely delete a file by performing a single overwrite with random data before removal.
        This simplified approach is optimized for performance on modern journaling file systems.

        Args:
            file_path: Path to the file.

        Returns:
            True if deletion was successful, False otherwise.
        """
        if not file_path or not os.path.exists(file_path) or not os.path.isfile(file_path):
            return False
        try:
            file_size = os.path.getsize(file_path)
            # For large files, skip overwriting to reduce resource usage.
            if file_size > 100 * 1024 * 1024:
                os.unlink(file_path)
                return True
            with open(file_path, "r+b") as f:
                # Overwrite file once with random data.
                f.write(os.urandom(file_size))
                f.flush()
                os.fsync(f.fileno())
            os.unlink(file_path)

            # Unregister from our tracking and retention manager
            try:
                with SecureTempFileManager._registry_lock.acquire_timeout(timeout=1.0) as acquired:
                    if acquired and file_path in SecureTempFileManager._temp_files_registry:
                        SecureTempFileManager._temp_files_registry.remove(file_path)
            except TimeoutError:
                logger.warning(f"[SECURITY] Timeout while unregistering file: {os.path.basename(file_path)}")

            # Always unregister from retention manager
            retention_manager.unregister_file(file_path)

            _logger.debug(f"Securely deleted file: {os.path.basename(file_path)}")
            return True
        except Exception as e:
            log_warning(f"[SECURITY] Failed to securely delete file: {os.path.basename(file_path)} - {e}")
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
                    log_info(f"[SECURITY] Deleted file (regular deletion): {os.path.basename(file_path)}")
                    return True
            except Exception as fallback_ex:
                log_warning(
                    f"[SECURITY] Fallback deletion failed for file: {os.path.basename(file_path)} - {fallback_ex}")
            return False

    @staticmethod
    def secure_delete_directory(dir_path: str) -> bool:
        """
        Securely delete a directory and all its contents.

        Args:
            dir_path: Directory path.

        Returns:
            True if deletion was successful, False otherwise.
        """
        if not dir_path or not os.path.exists(dir_path) or not os.path.isdir(dir_path):
            return False
        try:
            for root, dirs, files in os.walk(dir_path, topdown=False):
                for file in files:
                    SecureTempFileManager.secure_delete_file(os.path.join(root, file))
            shutil.rmtree(dir_path, ignore_errors=True)

            # Unregister from our tracking and retention manager
            try:
                with SecureTempFileManager._registry_lock.acquire_timeout(timeout=1.0) as acquired:
                    if acquired and dir_path in SecureTempFileManager._temp_files_registry:
                        SecureTempFileManager._temp_files_registry.remove(dir_path)
            except TimeoutError:
                # Continue even if unregistering fails
                pass

            # Always unregister from retention manager
            retention_manager.unregister_file(dir_path)

            log_info(f"[SECURITY] Securely deleted directory: {os.path.basename(dir_path)}")
            return True
        except Exception as e:
            SecurityAwareErrorHandler.log_processing_error(e, "directory_secure_deletion", dir_path)
            return False
