"""
Document retention management with enhanced GDPR compliance.

This module provides functionality for managing document retention
in compliance with GDPR requirements, ensuring data is not kept
longer than necessary with additional security features.
"""
import os
import time
import threading
import shutil

from backend.app.utils.logging.logger import log_info, log_warning
from backend.app.configs.gdpr_config import TEMP_FILE_RETENTION_SECONDS


class DocumentRetentionManager:
    """
    Manages document retention according to GDPR requirements with enhanced security.

    Ensures data is not kept longer than necessary and provides secure deletion methods.
    """

    _instance = None
    _lock = threading.Lock()  # Class-level lock for thread safety.

    def __new__(cls):
        """Ensure singleton pattern with thread safety."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DocumentRetentionManager, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """
        Initialize the retention manager.

        Note: The instance-level lock is not created in the constructor.
        Instead, the class-level lock (_lock) is used to ensure thread safety.
        """
        with self.__class__._lock:
            if not getattr(self, '_initialized', False):
                # Dictionary to track processed files with their expiration times.
                self.processed_files = {}

                # Set of file paths that should never be deleted automatically.
                self.permanent_files = set()

                # Thread control for cleanup operations.
                self._cleanup_thread = None
                self._stop_event = threading.Event()
                self._thread_running = False

                self._initialized = True
                log_info("[GDPR] Document retention manager initialized")

    def start(self):
        """
        Start the retention manager service.

        This method starts the background cleanup thread if it's not already running.
        """
        with self.__class__._lock:
            if not self._thread_running:
                self._start_cleanup_thread()
                log_info("[GDPR] Retention manager service started")
            else:
                log_info("[GDPR] Retention manager service already running")

    def _start_cleanup_thread(self) -> None:
        """Start a background thread to periodically clean up expired files."""
        def cleanup_worker():
            while not self._stop_event.is_set():
                self.cleanup_expired_files()
                # Wait for 60 seconds or until the stop event is set.
                self._stop_event.wait(60)

        self._cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        self._cleanup_thread.start()
        self._thread_running = True
        log_info("[GDPR] Retention cleanup thread started")

    def register_processed_file(self, file_path: str, retention_seconds: int = TEMP_FILE_RETENTION_SECONDS) -> None:
        """
        Register a file for scheduled deletion.

        Args:
            file_path: Path to the processed file.
            retention_seconds: Time in seconds to retain the file.
        """
        with self.__class__._lock:
            expiration_time = time.time() + retention_seconds
            self.processed_files[file_path] = expiration_time
            log_info(f"[GDPR] Registered file for retention: {os.path.basename(file_path)}")

    def unregister_file(self, file_path: str) -> None:
        """
        Unregister a file from retention management.

        This does not delete the file, just removes it from tracking.

        Args:
            file_path: Path to the file to unregister.
        """
        with self.__class__._lock:
            self.processed_files.pop(file_path, None)
            self.permanent_files.discard(file_path)
            log_info(f"[GDPR] Unregistered file from retention management: {os.path.basename(file_path)}")

    def cleanup_expired_files(self) -> None:
        """
        Remove files that have exceeded the retention period with secure deletion.

        Uses secure deletion methods for better GDPR compliance.
        """
        with self.__class__._lock:
            current_time = time.time()
            expired_files = [
                file_path for file_path, exp in list(self.processed_files.items())
                if current_time > exp
            ]
            for file_path in expired_files:
                self.processed_files.pop(file_path, None)

        for file_path in expired_files:
            if file_path in self.permanent_files:
                continue  # Skip files marked as permanent.
            if not os.path.exists(file_path):
                continue
            try:
                self._secure_delete(file_path)
                log_info(f"[GDPR] Removed file after retention period: {os.path.basename(file_path)}")
            except (OSError, IOError) as e:
                log_warning(f"[GDPR] Failed to remove expired file: {os.path.basename(file_path)}. Error: {e}")

    def _secure_delete(self, path: str) -> None:
        """
        Securely delete a file or directory with improved security.

        Uses multiple passes with different patterns to make recovery more difficult,
        addressing limitations of single-pass zero overwrite on journaling filesystems.

        Args:
            path: Path to file or directory to delete.
        """
        if not os.path.exists(path):
            return
        if os.path.isfile(path):
            self._secure_delete_file(path)
        elif os.path.isdir(path):
            self._secure_delete_directory(path)

    @staticmethod
    def _secure_delete_file(path: str) -> None:
        """
        Securely delete a file by overwriting its content with multiple patterns.

        If the file is larger than 100 MB, a regular deletion is performed.
        In case of failure, attempts a fallback regular deletion.

        Args:
            path: Path to the file to delete.
        """
        try:
            file_size = os.path.getsize(path)
            if file_size > 100 * 1024 * 1024:  # If file > 100 MB, skip secure deletion.
                os.unlink(path)
                return
            patterns = [
                b'\x00' * 4096,  # zeros
                b'\xFF' * 4096,  # ones
                b'\xAA' * 4096,  # alternating 10101010
                b'\x55' * 4096,  # alternating 01010101
                os.urandom(4096)  # random data
            ]
            with open(path, "wb") as f:
                for pattern in patterns:
                    f.seek(0)
                    remaining = file_size
                    while remaining > 0:
                        write_size = min(4096, remaining)
                        f.write(pattern[:write_size])
                        remaining -= write_size
                    f.flush()
                    os.fsync(f.fileno())
            os.unlink(path)
        except (OSError, IOError) as e:
            log_warning(f"[GDPR] Secure deletion failed for file: {os.path.basename(path)} with error: {e}. Attempting regular deletion.")
            try:
                if os.path.exists(path):
                    os.unlink(path)
                    log_info(f"[GDPR] Regular deletion succeeded for file: {os.path.basename(path)}")
            except (OSError, IOError) as e2:
                log_warning(f"[GDPR] Regular deletion also failed for file: {os.path.basename(path)} with error: {e2}")

    def _secure_delete_directory(self, path: str) -> None:
        """
        Securely delete a directory by recursively securing deletion of its contents.

        Args:
            path: Path to the directory to delete.
        """
        try:
            for root, dirs, files in os.walk(path, topdown=False):
                for file in files:
                    file_path = os.path.join(root, file)
                    self._secure_delete(file_path)
            shutil.rmtree(path, ignore_errors=False)
        except (OSError, IOError) as e:
            log_warning(f"[GDPR] Failed to remove directory: {os.path.basename(path)} with error: {e}")

    def immediate_cleanup(self, path: str) -> bool:
        """
        Immediately clean up a file or directory regardless of its retention period.

        Args:
            path: Path to the file or directory to clean up.

        Returns:
            True if the cleanup was successful, False otherwise.
        """
        try:
            with self.__class__._lock:
                self.unregister_file(path)
            if os.path.exists(path):
                self._secure_delete(path)
                log_info(f"[GDPR] Immediate cleanup of: {os.path.basename(path)}")
                return True
            return False
        except (OSError, IOError) as e:
            log_warning(f"[GDPR] Failed immediate cleanup of: {os.path.basename(path)}. Error: {e}")
            return False

    def shutdown(self) -> None:
        """
        Clean up resources and stop the cleanup thread.

        Performs final cleanup of all tracked files for GDPR compliance.
        """
        self._stop_event.set()
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=2)
            self._thread_running = False

        log_info("[GDPR] Retention manager shutdown initiated")

        with self.__class__._lock:
            files_to_clean = list(self.processed_files.keys())

        for file_path in files_to_clean:
            if os.path.exists(file_path):
                try:
                    self._secure_delete(file_path)
                    log_info(f"[GDPR] Removed file during shutdown: {os.path.basename(file_path)}")
                except (OSError, IOError) as e:
                    log_warning(f"[GDPR] Failed to remove file during shutdown: {os.path.basename(file_path)}. Error: {e}")

        log_info("[GDPR] Retention manager shutdown complete")


# Create a singleton instance.
retention_manager = DocumentRetentionManager()