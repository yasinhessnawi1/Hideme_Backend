"""
Enhanced secure file handling utilities with improved in-memory processing and GDPR compliance.

This module provides comprehensive utilities for securely handling files with a preference for
in-memory operations when possible. It ensures proper cleanup, secure deletion, and optimized
buffer management (via buffer pooling) to reduce memory copying.
"""
import asyncio
import hashlib
import io
import logging
import os
import shutil
import tempfile
import time
from contextlib import contextmanager, asynccontextmanager
from typing import Optional, Union, BinaryIO, Any, Callable, Generator, AsyncGenerator, TypeVar, Tuple, Awaitable

import aiofiles

from backend.app.configs.gdpr_config import TEMP_FILE_RETENTION_SECONDS
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.file_validation import calculate_file_hash, sanitize_filename
from backend.app.utils.logger import log_info, log_warning
from backend.app.utils.memory_management import memory_monitor
from backend.app.utils.retention_management import retention_manager

_logger = logging.getLogger("secure_file_utils")
T = TypeVar('T')


class SecureTempFileManager:
    """
    Enhanced secure file manager that prioritizes in-memory processing with disk fallback.

    This class provides comprehensive utilities for securely handling files with a preference for
    in-memory operations when possible, ensuring proper cleanup to comply with GDPR requirements.
    It implements optimized buffer pooling for improved memory efficiency and provides
    both synchronous and asynchronous interfaces.

    Key enhancements:
    - Integration with BufferPool for optimized memory management
    - Adaptive buffer sizing based on memory pressure
    - Support for streaming operations to reduce memory footprint
    - GDPR-compliant file handling with secure deletion
    - Consolidated temporary file creation methods
    - Automatic cleanup tracking for all created files
    """

    # Size threshold for in-memory processing instead of using disk (default 10MB)
    IN_MEMORY_THRESHOLD = int(os.environ.get("IN_MEMORY_THRESHOLD", "10485760"))
    # Maximum memory allowed for buffer pooling (default 50MB)
    MAX_BUFFER_POOL_SIZE = int(os.environ.get("MAX_BUFFER_POOL_SIZE", "52428800"))

    # Enable buffer pooling (true/false via env)
    _use_buffer_pool = os.environ.get("USE_BUFFER_POOL", "true").lower() == "true"
    _buffer_pool_lock = asyncio.Lock()  # Async lock for buffer pool operations

    # Initialize buffer pool using BufferPool class from buffer_pool.py
    _buffer_pool_instance = None

    # Registry of all created temporary files for cleanup tracking
    _temp_files_registry = set()
    _registry_lock = asyncio.Lock()

    @staticmethod
    async def _get_buffer_pool():
        """Get or initialize the buffer pool instance"""
        if SecureTempFileManager._buffer_pool_instance is None:
            # Import here to avoid circular imports
            from backend.app.utils.buffer_pool import BufferPool
            # Dynamically adjust max size based on available memory
            try:
                available_mb = memory_monitor.memory_stats["available_memory_mb"]
                # Use at most 10% of available memory for buffer pool, within limits
                max_pool_size_mb = min(int(available_mb * 0.1),
                                       SecureTempFileManager.MAX_BUFFER_POOL_SIZE // (1024 * 1024))
            except:
                max_pool_size_mb = SecureTempFileManager.MAX_BUFFER_POOL_SIZE // (1024 * 1024)

            SecureTempFileManager._buffer_pool_instance = BufferPool(max_pool_size_mb=max_pool_size_mb)
        return SecureTempFileManager._buffer_pool_instance

    @staticmethod
    async def get_buffer(size: int) -> io.BytesIO:
        """
        Get a buffer of appropriate size, using the BufferPool for efficient memory management.

        Args:
            size: Size of buffer needed in bytes

        Returns:
            BytesIO buffer of appropriate size
        """
        if not SecureTempFileManager._use_buffer_pool:
            return io.BytesIO()

        # Check if size is appropriate for buffer pooling
        if size > SecureTempFileManager.IN_MEMORY_THRESHOLD:
            # Too large for pooling, create a new buffer
            return io.BytesIO()

        try:
            # Get buffer from pool
            buffer_pool = await SecureTempFileManager._get_buffer_pool()
            memview = await buffer_pool.get_buffer(size)

            # Convert memoryview to BytesIO
            buffer = io.BytesIO()
            buffer.write(bytes(memview))
            buffer.seek(0)
            return buffer
        except Exception as e:
            # Fall back to creating a new buffer
            log_warning(f"[SECURITY] Buffer pool error: {e}, creating new buffer")
            return io.BytesIO()

    @staticmethod
    async def return_buffer(buffer: io.BytesIO) -> None:
        """
        Return a buffer to the pool for reuse.

        Args:
            buffer: BytesIO buffer to return
        """
        if not SecureTempFileManager._use_buffer_pool:
            buffer.close()
            return

        try:
            # Get buffer size
            buffer_size = buffer.getbuffer().nbytes

            # Only return appropriately sized buffers
            if buffer_size < 1024 or buffer_size > SecureTempFileManager.IN_MEMORY_THRESHOLD:
                buffer.close()
                return

            # Return to pool
            buffer_pool = await SecureTempFileManager._get_buffer_pool()
            buffer.seek(0)
            await buffer_pool.return_buffer(memoryview(buffer.getbuffer()))
        except Exception as e:
            # Just close if there's an error
            buffer.close()
            log_warning(f"[SECURITY] Error returning buffer to pool: {e}")

    @staticmethod
    async def _register_temp_file(file_path: str, retention_seconds: Optional[int] = None) -> None:
        """
        Register a temporary file for cleanup tracking.

        Args:
            file_path: Path to the temporary file
            retention_seconds: Optional retention period in seconds
        """
        async with SecureTempFileManager._registry_lock:
            SecureTempFileManager._temp_files_registry.add(file_path)

        # Register with retention manager if retention period specified
        if retention_seconds is not None:
            retention_manager.register_processed_file(file_path, retention_seconds)
        else:
            retention_manager.register_processed_file(file_path, TEMP_FILE_RETENTION_SECONDS)

    @staticmethod
    async def _unregister_temp_file(file_path: str) -> None:
        """
        Unregister a temporary file from cleanup tracking.

        Args:
            file_path: Path to the temporary file
        """
        async with SecureTempFileManager._registry_lock:
            if file_path in SecureTempFileManager._temp_files_registry:
                SecureTempFileManager._temp_files_registry.remove(file_path)

        # Unregister from retention manager
        retention_manager.unregister_file(file_path)

    @staticmethod
    @contextmanager
    def create_temp_file(suffix: str = ".tmp", content: Optional[bytes] = None, prefix: str = "secure_",
                         mode: str = "wb+", retention_seconds: Optional[int] = None
                         ) -> Generator[str, None, None]:
        """
        Create a temporary file and ensure it's deleted after use.

        Args:
            suffix: File extension.
            content: Optional content to write.
            prefix: Filename prefix.
            mode: File mode.
            retention_seconds: Optional retention period in seconds.

        Yields:
            Path to the temporary file.
        """
        loop = asyncio.get_event_loop() if asyncio.get_event_loop_policy().get_event_loop().is_running() else None
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix=prefix)

        try:
            if content:
                temp_file.write(content)
                temp_file.flush()
            temp_file.close()

            # Register file for cleanup tracking
            if loop and loop.is_running():
                asyncio.create_task(SecureTempFileManager._register_temp_file(
                    temp_file.name, retention_seconds
                ))
            else:
                retention_manager.register_processed_file(
                    temp_file.name,
                    retention_seconds or TEMP_FILE_RETENTION_SECONDS
                )

            trace_id = f"temp_file_{time.time()}_{hashlib.md5(temp_file.name.encode()).hexdigest()[:6]}"
            file_size = os.path.getsize(temp_file.name) if os.path.exists(temp_file.name) else 0
            log_info(f"[SECURITY] Created temporary file: {os.path.basename(temp_file.name)} "
                     f"({file_size / 1024:.1f}KB) [trace_id={trace_id}]")
            yield temp_file.name
        finally:
            if os.path.exists(temp_file.name):
                # Cleanup file and unregister
                SecureTempFileManager.secure_delete_file(temp_file.name)

                if loop and loop.is_running():
                    asyncio.create_task(SecureTempFileManager._unregister_temp_file(temp_file.name))
                else:
                    retention_manager.unregister_file(temp_file.name)

                log_info(f"[SECURITY] Removed temporary file: {os.path.basename(temp_file.name)}")

    @staticmethod
    @asynccontextmanager
    async def create_temp_file_async(suffix: str = ".tmp", content: Optional[bytes] = None, prefix: str = "secure_",
                                     mode: str = "wb+", retention_seconds: Optional[int] = None
                                     ) -> AsyncGenerator[str, None]:
        """
        Asynchronously create a temporary file and ensure deletion after use.

        Args:
            suffix: File extension.
            content: Optional content to write.
            prefix: Filename prefix.
            mode: File mode.
            retention_seconds: Optional retention period in seconds.

        Yields:
            Path to the temporary file.
        """
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix=prefix)
        try:
            if content:
                temp_file.write(content)
                temp_file.flush()
            temp_file.close()

            # Register file for cleanup tracking
            await SecureTempFileManager._register_temp_file(temp_file.name, retention_seconds)

            trace_id = f"temp_file_{time.time()}_{hashlib.md5(temp_file.name.encode()).hexdigest()[:6]}"
            file_size = os.path.getsize(temp_file.name) if os.path.exists(temp_file.name) else 0
            log_info(f"[SECURITY] Created temporary file: {os.path.basename(temp_file.name)} "
                     f"({file_size / 1024:.1f}KB) [trace_id={trace_id}]")
            yield temp_file.name
        finally:
            if os.path.exists(temp_file.name):
                # Cleanup file and unregister
                await asyncio.to_thread(SecureTempFileManager.secure_delete_file, temp_file.name)
                await SecureTempFileManager._unregister_temp_file(temp_file.name)
                log_info(f"[SECURITY] Removed temporary file: {os.path.basename(temp_file.name)}")

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
            if os.path.exists(temp_file.name):
                await asyncio.to_thread(SecureTempFileManager.secure_delete_file, temp_file.name)
            SecurityAwareErrorHandler.log_processing_error(e, "secure_temp_file_creation", trace_id=trace_id)
            raise e

    @staticmethod
    def create_secure_temp_file(suffix: str = ".tmp", content: Optional[bytes] = None,
                                prefix: str = "secure_", retention_seconds: Optional[int] = None) -> str:
        """
        Create a secure temporary file with optional content and register it for cleanup.
        This is the primary synchronous method to use for temporary file creation.

        Args:
            suffix: File extension.
            content: Optional content.
            prefix: Filename prefix.
            retention_seconds: Optional retention period in seconds.

        Returns:
            Path to the created file.
        """
        loop = asyncio.get_event_loop() if asyncio.get_event_loop_policy().get_event_loop().is_running() else None
        trace_id = f"secure_file_{time.time()}_{hashlib.md5(prefix.encode()).hexdigest()[:6]}"
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

            # Register with retention manager
            retention_manager.register_processed_file(
                temp_file.name,
                retention_seconds or TEMP_FILE_RETENTION_SECONDS
            )

            # Also register in our tracking
            if loop and loop.is_running():
                asyncio.create_task(SecureTempFileManager._register_temp_file(
                    temp_file.name, retention_seconds
                ))
            else:
                with asyncio.Runner() as runner:
                    runner.run(SecureTempFileManager._register_temp_file(
                        temp_file.name, retention_seconds
                    ))

            log_info(f"[SECURITY] Created secure temporary file: {os.path.basename(temp_file.name)} "
                     f"({len(content) / 1024 if content else 0:.1f}KB) [trace_id={trace_id}]")
            return temp_file.name
        except Exception as e:
            if os.path.exists(temp_file.name):
                SecureTempFileManager.secure_delete_file(temp_file.name)
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
    def create_secure_temp_dir(prefix: str = "secure_dir_", retention_seconds: Optional[int] = None) -> str:
        """
        Create a secure temporary directory and register it for cleanup.

        Args:
            prefix: Directory name prefix.
            retention_seconds: Optional retention period in seconds.

        Returns:
            Path to the created directory.
        """
        temp_dir = tempfile.mkdtemp(prefix=prefix)

        # Register with retention manager
        retention_manager.register_processed_file(
            temp_dir,
            retention_seconds or TEMP_FILE_RETENTION_SECONDS
        )

        # Also register in our tracking
        loop = asyncio.get_event_loop() if asyncio.get_event_loop_policy().get_event_loop().is_running() else None
        if loop and loop.is_running():
            asyncio.create_task(SecureTempFileManager._register_temp_file(
                temp_dir, retention_seconds
            ))
        else:
            # Use the Runner API to avoid "no running event loop" errors
            with asyncio.Runner() as runner:
                runner.run(SecureTempFileManager._register_temp_file(
                    temp_dir, retention_seconds
                ))

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
            loop = asyncio.get_event_loop() if asyncio.get_event_loop_policy().get_event_loop().is_running() else None
            if loop and loop.is_running():
                asyncio.create_task(SecureTempFileManager._unregister_temp_file(file_path))
            else:
                retention_manager.unregister_file(file_path)
                # Attempt to unregister from our tracking as well
                try:
                    with asyncio.Runner() as runner:
                        runner.run(SecureTempFileManager._unregister_temp_file(file_path))
                except Exception:
                    pass

            _logger.debug(f"Securely deleted file: {os.path.basename(file_path)}")
            return True
        except Exception as e:
            log_warning(f"[SECURITY] Failed to securely delete file: {os.path.basename(file_path)} - {e}")
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
                    log_info(f"[SECURITY] Deleted file (regular deletion): {os.path.basename(file_path)}")
                    return True
            except Exception:
                pass
            return False

    @staticmethod
    async def secure_delete_file_async(file_path: str) -> bool:
        """
        Asynchronously securely delete a file.

        Args:
            file_path: Path to the file.

        Returns:
            True if deletion was successful, False otherwise.
        """
        result = await asyncio.to_thread(SecureTempFileManager.secure_delete_file, file_path)
        if result:
            # Ensure it's unregistered from our tracking
            await SecureTempFileManager._unregister_temp_file(file_path)
        return result

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
            loop = asyncio.get_event_loop() if asyncio.get_event_loop_policy().get_event_loop().is_running() else None
            if loop and loop.is_running():
                asyncio.create_task(SecureTempFileManager._unregister_temp_file(dir_path))
            else:
                retention_manager.unregister_file(dir_path)
                # Attempt to unregister from our tracking as well
                try:
                    with asyncio.Runner() as runner:
                        runner.run(SecureTempFileManager._unregister_temp_file(dir_path))
                except Exception:
                    pass

            log_info(f"[SECURITY] Securely deleted directory: {os.path.basename(dir_path)}")
            return True
        except Exception as e:
            SecurityAwareErrorHandler.log_processing_error(e, "directory_secure_deletion", dir_path)
            return False

    @staticmethod
    async def secure_delete_directory_async(dir_path: str) -> bool:
        """
        Asynchronously securely delete a directory.

        Args:
            dir_path: Directory path.

        Returns:
            True if deletion was successful, False otherwise.
        """
        result = await asyncio.to_thread(SecureTempFileManager.secure_delete_directory, dir_path)
        if result:
            # Ensure it's unregistered from our tracking
            await SecureTempFileManager._unregister_temp_file(dir_path)
        return result

    @staticmethod
    def process_content_in_memory(
            content: bytes,
            processor: Callable[[Union[str, BinaryIO]], Any],
            use_path: bool = False,
            extension: str = ".tmp"
    ) -> Any:
        """
        Process content in memory if possible, with fallback to temporary file.
        Legacy synchronized version for backward compatibility.

        Args:
            content: Bytes to process.
            processor: Function to process the content.
            use_path: Whether processor needs a file path.
            extension: File extension if using temporary file.

        Returns:
            Result from the processor.
        """
        trace_id = f"mem_process_{time.time()}_{hashlib.md5(extension.encode()).hexdigest()[:6]}"
        content_size = len(content) / 1024  # in KB

        # For synchronous processing, use simple in-memory buffer if size permits
        if len(content) <= SecureTempFileManager.IN_MEMORY_THRESHOLD and not use_path:
            try:
                buffer = io.BytesIO(content)
                log_info(f"[SECURITY] Processing {content_size:.1f}KB in memory [trace_id={trace_id}]")
                result = processor(buffer)
                buffer.close()
                return result
            except Exception as e:
                log_warning(f"[SECURITY] In-memory processing failed: {e}, falling back to file [trace_id={trace_id}]")

        # Fall back to file-based processing
        with SecureTempFileManager.create_temp_file(suffix=extension, content=content) as tmp_path:
            if use_path:
                log_info(
                    f"[SECURITY] Processing {content_size:.1f}KB using temporary file (path) [trace_id={trace_id}]")
                result = processor(tmp_path)
            else:
                log_info(
                    f"[SECURITY] Processing {content_size:.1f}KB using temporary file (stream) [trace_id={trace_id}]")
                with open(tmp_path, "rb") as f:
                    result = processor(f)
            return result

    @staticmethod
    async def process_content_in_memory_async(
            content: bytes,
            processor: Callable[[Union[str, BinaryIO]], Awaitable[Any]],
            use_path: bool = False,
            extension: str = ".tmp"
    ) -> Any:
        """
        Process content in memory if possible with improved buffer management.

        This enhanced version uses the BufferPool for more efficient memory management
        and leverages asynchronous processing.

        Args:
            content: Bytes to process.
            processor: Async function to process the content.
            use_path: Whether processor needs a file path.
            extension: File extension if using temporary file.

        Returns:
            Result from the processor.
        """
        trace_id = f"mem_process_{time.time()}_{hashlib.md5(extension.encode()).hexdigest()[:6]}"
        content_size = len(content) / 1024  # in KB

        if len(content) <= SecureTempFileManager.IN_MEMORY_THRESHOLD and not use_path:
            try:
                # Get buffer from pool
                buffer = await SecureTempFileManager.get_buffer(len(content))
                buffer.write(content)
                buffer.seek(0)
                log_info(f"[SECURITY] Processing {content_size:.1f}KB in memory [trace_id={trace_id}]")

                # Process content
                result = await processor(buffer)

                # Return buffer to pool
                buffer.seek(0)
                await SecureTempFileManager.return_buffer(buffer)
                return result
            except Exception as e:
                log_warning(f"[SECURITY] In-memory processing failed: {e}, falling back to file [trace_id={trace_id}]")

        # Fall back to file-based processing for large content or if in-memory fails
        async with SecureTempFileManager.create_temp_file_async(suffix=extension, content=content) as tmp_path:
            if use_path:
                log_info(
                    f"[SECURITY] Processing {content_size:.1f}KB using temporary file (path) [trace_id={trace_id}]")
                result = await processor(tmp_path)
            else:
                log_info(
                    f"[SECURITY] Processing {content_size:.1f}KB using temporary file (stream) [trace_id={trace_id}]")
                with open(tmp_path, "rb") as f:
                    result = await processor(f)
            return result

    @staticmethod
    def get_memory_buffer_content(buffer: io.BytesIO, close_after: bool = False) -> bytes:
        """
        Get content from a memory buffer, resetting its position.

        Args:
            buffer: BytesIO buffer.
            close_after: Whether to close the buffer after reading.

        Returns:
            Buffer content as bytes.
        """
        try:
            buffer.seek(0)
            content = buffer.read()
            buffer.seek(0)
            if close_after:
                buffer.close()
            return content
        except Exception as e:
            SecurityAwareErrorHandler.log_processing_error(e, "buffer_content_reading", "")
            return b""

    @staticmethod
    def buffer_or_file_based_on_size(content: bytes) -> Union[io.BytesIO, str]:
        """
        Decide whether to use a memory buffer or a temporary file based on content size.

        Args:
            content: Data to process.

        Returns:
            A BytesIO buffer for small content or a file path for larger content.
        """
        if len(content) <= SecureTempFileManager.IN_MEMORY_THRESHOLD:
            buffer = io.BytesIO(content)
            return buffer
        else:
            # Use the unified temp file creation method
            temp_file_path = SecureTempFileManager.create_secure_temp_file(content=content)
            return temp_file_path

    @staticmethod
    async def buffer_or_file_based_on_size_async(content: bytes) -> Union[io.BytesIO, str]:
        """
        Decide whether to use a memory buffer or a temporary file based on content size
        with enhanced memory pressure awareness.

        Args:
            content: Data to process.

        Returns:
            A BytesIO buffer for small content or a file path for larger content.
        """
        # Check memory pressure first
        try:
            current_usage = memory_monitor.get_memory_usage()
            available_memory = memory_monitor.memory_stats["available_memory_mb"] * 1024 * 1024

            # Adjust threshold based on memory pressure
            if current_usage > 90:  # Critical memory pressure
                effective_threshold = min(1024 * 1024, int(available_memory * 0.01))  # 1% of available or 1MB max
            elif current_usage > 75:  # High memory pressure
                effective_threshold = min(2 * 1024 * 1024, int(available_memory * 0.02))  # 2% or 2MB max
            elif current_usage > 60:  # Medium memory pressure
                effective_threshold = min(5 * 1024 * 1024, int(available_memory * 0.05))  # 5% or 5MB max
            else:  # Low memory pressure
                effective_threshold = SecureTempFileManager.IN_MEMORY_THRESHOLD
        except:
            # If memory_monitor is unavailable, use default threshold
            effective_threshold = SecureTempFileManager.IN_MEMORY_THRESHOLD

        # Decide based on adjusted threshold
        if len(content) <= effective_threshold:
            # Use memory buffer
            buffer = await SecureTempFileManager.get_buffer(len(content))
            buffer.write(content)
            buffer.seek(0)
            return buffer
        else:
            # Use temporary file - use the consolidated async method
            temp_file_path = await SecureTempFileManager.create_secure_temp_file_async(
                content=content, suffix=".tmp"
            )
            return temp_file_path

    @staticmethod
    def validate_and_sanitize_file(content: bytes, filename: str, content_type: Optional[str] = None
                                   ) -> Tuple[bool, str, bytes, str]:
        """
        Validate and sanitize file content and filename.

        Args:
            content: File content.
            filename: Original filename.
            content_type: Claimed content type.

        Returns:
            Tuple: (is_valid, error_message, sanitized_content, sanitized_filename)
        """
        safe_filename = sanitize_filename(filename)
        from backend.app.utils.file_validation import validate_file_content
        is_valid, reason, detected_type = validate_file_content(content, safe_filename, content_type)
        if not is_valid:
            return False, reason, b"", safe_filename
        from backend.app.utils.file_validation import is_valid_file_size
        file_type = "text"
        if detected_type:
            if "pdf" in detected_type:
                file_type = "pdf"
            elif "word" in detected_type or "document" in detected_type:
                file_type = "docx"
            elif "image" in detected_type:
                file_type = "image"
        if not is_valid_file_size(len(content), file_type):
            max_size = {"pdf": "25MB", "docx": "20MB", "text": "10MB", "image": "5MB"}.get(file_type, "10MB")
            return False, f"File exceeds maximum size for {file_type} ({max_size})", b"", safe_filename
        file_hash = calculate_file_hash(content)
        log_info(
            f"[SECURITY] Validated file: {safe_filename}, type: {detected_type}, size: {len(content) / 1024:.1f}KB, hash: {file_hash[:8]}")
        return True, "", content, safe_filename

    @staticmethod
    async def validate_and_sanitize_file_async(content: bytes, filename: str, content_type: Optional[str] = None
                                               ) -> Tuple[bool, str, bytes, str]:
        """
        Asynchronously validate and sanitize file content and filename.

        Args:
            content: File content.
            filename: Original filename.
            content_type: Claimed content type.

        Returns:
            Tuple: (is_valid, error_message, sanitized_content, sanitized_filename)
        """
        return await asyncio.to_thread(SecureTempFileManager.validate_and_sanitize_file, content, filename,
                                       content_type)

    @staticmethod
    async def stream_file_processing(
            file_path: str,
            chunk_size: int = 64 * 1024,  # 64KB chunks
            processor: Callable[[bytes, int], Awaitable[Any]] = None
    ) -> Any:
        """
        Process a file in streaming mode to reduce memory footprint.

        Args:
            file_path: Path to the file
            chunk_size: Size of chunks to process
            processor: Async function to process each chunk with position

        Returns:
            Result from processor if provided, otherwise None
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        file_size = os.path.getsize(file_path)
        position = 0

        try:
            async with aiofiles.open(file_path, 'rb') as f:
                while position < file_size:
                    chunk = await f.read(chunk_size)
                    if not chunk:
                        break

                    if processor:
                        await processor(chunk, position)

                    position += len(chunk)
        except ImportError:
            # Fall back to regular file I/O if aiofiles is not available
            with open(file_path, 'rb') as f:
                while position < file_size:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break

                    if processor:
                        await processor(chunk, position)

                    position += len(chunk)

        return position

    @staticmethod
    async def cleanup_all_temporary_files() -> int:
        """
        Cleanup all tracked temporary files.

        Returns:
            Number of files cleaned up
        """
        cleaned_count = 0

        async with SecureTempFileManager._registry_lock:
            # Make a copy of the set to avoid modification during iteration
            files_to_clean = set(SecureTempFileManager._temp_files_registry)

        for file_path in files_to_clean:
            if os.path.exists(file_path):
                if os.path.isfile(file_path):
                    success = await SecureTempFileManager.secure_delete_file_async(file_path)
                elif os.path.isdir(file_path):
                    success = await SecureTempFileManager.secure_delete_directory_async(file_path)
                else:
                    success = False

                if success:
                    cleaned_count += 1

        log_info(f"[SECURITY] Cleaned up {cleaned_count} temporary files/directories")
        return cleaned_count