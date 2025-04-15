"""
Document retention management with enhanced GDPR compliance.
This module provides functionality for managing document retention
in compliance with GDPR requirements, ensuring data is not kept longer than necessary
with additional security features.
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

    This class ensures that temporary documents are not retained beyond their allowed time.
    It tracks processed files with expiration times, registers files for deletion,
    and securely deletes expired files using multiple overwrite patterns.
    Additionally, it runs a background cleanup thread to perform periodic removal
    of expired files, and supports graceful shutdown of the cleanup operations.
    """

    _instance = None
    _lock = threading.Lock()  # Class-level lock for thread safety.

    def __new__(cls):
        # Ensure singleton pattern with thread safety.
        with cls._lock:
            # If an instance does not already exist, create one.
            if cls._instance is None:
                # Create a new instance.
                cls._instance = super(DocumentRetentionManager, cls).__new__(cls)
                # Mark the new instance as not yet initialized.
                cls._instance._initialized = False
        # Return the singleton instance.
        return cls._instance

    def __init__(self):
        # Use the class-level lock to ensure thread-safe initialization.
        with self.__class__._lock:
            # Initialize only if the instance has not yet been initialized.
            if not getattr(self, '_initialized', False):
                # Create a dictionary to track processed file paths with their expiration times.
                self.processed_files = {}
                # Create a set for files that should never be deleted automatically.
                self.permanent_files = set()
                # Initialize variables for controlling the background cleanup thread.
                self._cleanup_thread = None
                self._stop_event = threading.Event()
                self._thread_running = False
                # Mark the instance as initialized.
                self._initialized = True
                # Log the initialization of the retention manager.
                log_info("[GDPR] Document retention manager initialized")

    def start(self):
        """
        Start the retention manager service.

        This method launches the background cleanup thread if it is not already running.
        """
        # Acquire the class-level lock for thread-safe start process.
        with self.__class__._lock:
            # Check if the cleanup thread is not currently running.
            if not self._thread_running:
                # Start the background cleanup thread.
                self._start_cleanup_thread()
                # Log that the retention manager service has started.
                log_info("[GDPR] Retention manager service started")
            else:
                # Log that the service is already running.
                log_info("[GDPR] Retention manager service already running")

    def _start_cleanup_thread(self) -> None:
        """
        Start a background thread to periodically clean up expired files.

        The thread executes the cleanup worker function that deletes files
        which have exceeded their retention period.
        """

        # Define the cleanup worker function to run in the background.
        def cleanup_worker():
            # Continuously run until a stop event is signaled.
            while not self._stop_event.is_set():
                # Execute the cleanup of expired files.
                self.cleanup_expired_files()
                # Wait for 60 seconds or until the stop event is triggered.
                self._stop_event.wait(60)

        # Create and start the background thread with the cleanup worker function.
        self._cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        # Start the cleanup thread.
        self._cleanup_thread.start()
        # Mark the thread as running.
        self._thread_running = True
        # Log that the cleanup thread has started.
        log_info("[GDPR] Retention cleanup thread started")

    def register_processed_file(self, file_path: str, retention_seconds: int = TEMP_FILE_RETENTION_SECONDS) -> None:
        """
        Register a file for scheduled deletion.

        Args:
            file_path (str): The absolute path to the processed file.
            retention_seconds (int): Time in seconds for which the file should be retained.

        This method computes the expiration time and adds the file to the tracking dictionary.
        """
        # Acquire the lock to ensure thread-safe modification of processed_files.
        with self.__class__._lock:
            # Calculate the expiration time based on current time and retention period.
            expiration_time = time.time() + retention_seconds
            # Store the file path and its expiration time.
            self.processed_files[file_path] = expiration_time
            # Log the registration of the file for retention.
            log_info(f"[GDPR] Registered file for retention: {os.path.basename(file_path)}")

    def unregister_file(self, file_path: str) -> None:
        """
        Unregister a file from retention management.

        Args:
            file_path (str): The path to the file to unregister.

        This method removes the file from the processed files tracking and from permanent files.
        """
        # Acquire the lock to ensure thread-safe removal of the file.
        with self.__class__._lock:
            # Remove the file from the processed_files dictionary, if present.
            self.processed_files.pop(file_path, None)
            # Also remove the file from the permanent_files set.
            self.permanent_files.discard(file_path)
            # Log the unregistration of the file.
            log_info(f"[GDPR] Unregistered file from retention management: {os.path.basename(file_path)}")

    def cleanup_expired_files(self) -> None:
        """
        Remove files that have exceeded the retention period with secure deletion.

        This method identifies expired files, removes them from the tracking dictionary,
        and securely deletes them unless they are marked as permanent.
        """
        # Acquire the lock to obtain a thread-safe copy of the expiration data.
        with self.__class__._lock:
            # Get the current timestamp.
            current_time = time.time()
            # Create a list of file paths that have expired.
            expired_files = [
                file_path for file_path, exp in list(self.processed_files.items())
                if current_time > exp
            ]
            # Remove expired files from the tracking dictionary.
            for file_path in expired_files:
                self.processed_files.pop(file_path, None)
        # Iterate over the list of expired files to delete them securely.
        for file_path in expired_files:
            # Skip deletion for files marked as permanent.
            if file_path in self.permanent_files:
                continue
            # If the file does not exist in the filesystem, skip deletion.
            if not os.path.exists(file_path):
                continue
            # Attempt to securely delete the file.
            try:
                # Perform secure deletion (file or directory).
                self._secure_delete(file_path)
                # Check if the file has been successfully deleted.
                if not os.path.exists(file_path):
                    # Log successful deletion.
                    log_info(f"[GDPR] Successfully deleted file: {os.path.basename(file_path)}")
                else:
                    # Log a warning if the file still exists after attempted deletion.
                    log_warning(f"[GDPR] File still exists after deletion attempt: {os.path.basename(file_path)}")
            except (OSError, IOError) as e:
                # Log a warning if deletion fails.
                log_warning(f"[GDPR] Failed to remove expired file: {os.path.basename(file_path)}. Error: {e}")

    def _secure_delete(self, path: str) -> None:
        """
        Securely delete a file or directory with improved security.

        Args:
            path (str): The path to the file or directory to delete.

        This method uses multiple overwrite passes with different patterns to ensure
        data is irrecoverable, enhancing GDPR compliance. It delegates to file or directory
        specific secure deletion methods as appropriate.
        """
        # Check if the specified path exists.
        if not os.path.exists(path):
            # If path does not exist, nothing to delete.
            return
        # If the path is a file, call the secure file deletion method.
        if os.path.isfile(path):
            self._secure_delete_file(path)
        # If the path is a directory, call the secure directory deletion method.
        elif os.path.isdir(path):
            self._secure_delete_directory(path)

    @staticmethod
    def _secure_delete_file(path: str) -> None:
        """
        Securely delete a file by overwriting its content with multiple patterns.

        Args:
            path (str): The path to the file to securely delete.

        For large files (>100 MB), a regular deletion is performed for efficiency.
        If secure deletion fails, a fallback to regular deletion is attempted.
        """
        # Attempt the secure deletion process in a try block.
        try:
            # Get the size of the file in bytes.
            file_size = os.path.getsize(path)
            # Check if the file is larger than 100 MB.
            if file_size > 100 * 1024 * 1024:
                # For large files, perform a regular deletion.
                os.unlink(path)
                # Exit the function after regular deletion.
                return
            # Define multiple patterns for overwriting the file.
            patterns = [
                b'\x00' * 4096,  # Overwrite with zeros.
                b'\xFF' * 4096,  # Overwrite with ones.
                b'\xAA' * 4096,  # Overwrite with alternating bits 10101010.
                b'\x55' * 4096,  # Overwrite with alternating bits 01010101.
                os.urandom(4096)  # Overwrite with random data.
            ]
            # Open the file in binary write mode.
            with open(path, "wb") as f:
                # Iterate over each overwrite pattern.
                for pattern in patterns:
                    # Move the file pointer to the beginning.
                    f.seek(0)
                    # Initialize the counter for remaining bytes to overwrite.
                    remaining = file_size
                    # Continue writing until the entire file is overwritten.
                    while remaining > 0:
                        # Determine the number of bytes to write in this iteration.
                        write_size = min(4096, remaining)
                        # Write a slice of the current pattern.
                        f.write(pattern[:write_size])
                        # Decrement the remaining bytes.
                        remaining -= write_size
                    # Flush the file buffer.
                    f.flush()
                    # Force the file system to write the data to disk.
                    os.fsync(f.fileno())
            # After overwriting, delete the file.
            os.unlink(path)
        except (OSError, IOError) as e:
            # If secure deletion fails, log a warning.
            log_warning(
                f"[GDPR] Secure deletion failed for file: {os.path.basename(path)} with error: {e}. Attempting regular deletion.")
            # Attempt fallback regular deletion in a nested try block.
            try:
                # Check if the file still exists.
                if os.path.exists(path):
                    # Delete the file using standard unlink.
                    os.unlink(path)
                    # Log successful regular deletion.
                    log_info(f"[GDPR] Regular deletion succeeded for file: {os.path.basename(path)}")
            except (OSError, IOError) as e2:
                # Log a warning if fallback deletion also fails.
                log_warning(f"[GDPR] Regular deletion also failed for file: {os.path.basename(path)} with error: {e2}")

    def _secure_delete_directory(self, path: str) -> None:
        """
        Securely delete a directory by recursively securing deletion of its contents.

        Args:
            path (str): The path to the directory to delete.

        This method traverses the directory tree and applies secure deletion for each file,
        then removes the directory tree.
        """
        try:
            # Walk the directory tree from bottom up.
            for root, dirs, files in os.walk(path, topdown=False):
                # Iterate over all files in the current directory.
                for file in files:
                    # Construct the full path for the file.
                    file_path = os.path.join(root, file)
                    # Securely delete the file.
                    self._secure_delete(file_path)
            # Remove the entire directory tree.
            shutil.rmtree(path, ignore_errors=False)
        except (OSError, IOError) as e:
            # Log a warning if the directory deletion fails.
            log_warning(f"[GDPR] Failed to remove directory: {os.path.basename(path)} with error: {e}")

    def shutdown(self) -> None:
        """
        Clean up resources and stop the cleanup thread.

        This method signals the background cleanup thread to stop,
        waits for its termination, and then securely deletes any remaining tracked files.
        """
        # Signal the cleanup thread to stop by setting the stop event.
        self._stop_event.set()
        # If the cleanup thread exists and is alive, wait for its termination.
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            # Wait for up to 2 seconds for the thread to join.
            self._cleanup_thread.join(timeout=2)
            # Mark the cleanup thread as no longer running.
            self._thread_running = False

        # Log that the shutdown process for the retention manager has started.
        log_info("[GDPR] Retention manager shutdown initiated")

        # Acquire the lock to safely copy the list of files to clean.
        with self.__class__._lock:
            # Get a copy of all tracked file paths.
            files_to_clean = list(self.processed_files.keys())

        # Iterate over the files to attempt secure deletion.
        for file_path in files_to_clean:
            # Only proceed if the file still exists.
            if os.path.exists(file_path):
                try:
                    # Attempt to securely delete the file.
                    self._secure_delete(file_path)
                    # Log the successful deletion of the file during shutdown.
                    log_info(f"[GDPR] Removed file during shutdown: {os.path.basename(file_path)}")
                except (OSError, IOError) as e:
                    # Log a warning if deletion fails during shutdown.
                    log_warning(
                        f"[GDPR] Failed to remove file during shutdown: {os.path.basename(file_path)}. Error: {e}"
                    )

        # Log that the shutdown process for the retention manager is complete.
        log_info("[GDPR] Retention manager shutdown complete")


# Create a singleton instance of the DocumentRetentionManager.
retention_manager = DocumentRetentionManager()
