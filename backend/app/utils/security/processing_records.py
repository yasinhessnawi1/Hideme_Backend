"""
GDPR Processing Records Management with Enhanced Security Features.
This module provides functionality for maintaining GDPR Article 30 processing records.
It records only minimal metadata required for GDPR compliance (data minimization),
implements secure hashing, automatic file rotation and deletion after a specified retention period,
and provides detailed logging and statistics for auditing purposes.
"""

import json
import os
import threading
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from backend.app.utils.constant.constant import JSON_CONSTANT
from backend.app.utils.logging.logger import log_info, log_warning
from backend.app.configs.gdpr_config import (
    PROCESSING_RECORDS,
    GDPR_DOCUMENTATION
)


class ProcessingRecordKeeper:
    """
    Maintains records of processing activities as required by GDPR Article 30.

    GDPR Compliance Features:
    1. Data Minimization (Art. 5(1)(c)): Records only minimal essential metadata about
       processing operations, without storing any personal or sensitive data.

    2. Purpose Limitation (Art. 5(1)(b)): Records created solely for the purpose of
       demonstrating GDPR compliance and maintaining processing records.

    3. Storage Limitation (Art. 5(1)(e)): Implements automatic record rotation and
       deletion after a configurable retention period.

    4. Integrity and Confidentiality (Art. 5(1)(f)): Uses secure hashing for operation IDs
       to prevent reconstruction of original data.

    5. Accountability (Art. 5(2) and Art. 30): Provides comprehensive logging to
       demonstrate compliance with GDPR principles.

    6. Right to Erasure (Art. 17): Facilitates deletion of outdated records through
       automatic cleanup processes.

    7. Transparency (Art. 12-14): Captures legal basis for processing and maintains
       accessible documentation of processing activities.

    Implementation Notes:
    - Records are stored as JSONL files with one record per line for efficient append-only operations.
    - Records are organized by date to facilitate timely deletion when the retention period expires.
    - No direct correlation is maintained between records and processed data to enhance privacy.
    - Processing activities are hashed to prevent reconstruction of original content.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        # Acquire class-level lock to ensure thread-safe singleton instantiation.
        with cls._lock:
            # Check if instance is already created.
            if cls._instance is None:
                # Create a new instance.
                cls._instance = super(ProcessingRecordKeeper, cls).__new__(cls)
                # Mark instance as not yet initialized.
                cls._instance._initialized = False
        # Return the singleton instance.
        return cls._instance

    def __init__(self, records_dir: Optional[str] = None):
        """
        Initialize the record keeper.

        The instance-level lock is not created in __init__; instead, the class-level
        lock (_lock) is used to ensure thread safety.
        """
        with self.__class__._lock:
            # Check if the instance was already initialized.
            if not getattr(self, '_initialized', False):
                # Set records directory either from provided argument or create a default one.
                self.records_dir = records_dir or os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    "logs",
                    "processing_records"
                )
                # Ensure that the records directory exists.
                try:
                    # Create the directory if it does not exist.
                    os.makedirs(self.records_dir, exist_ok=True)
                except (OSError, IOError) as e:
                    # Log a warning if directory creation fails.
                    log_warning(f"[GDPR] Failed to create records directory: {e}")

                # Set retention period for records (default to 90 days from configuration).
                self.record_retention_days = PROCESSING_RECORDS.get('record_retention_days', 90)

                # Initialize statistics for record tracking.
                self.stats: Dict[str, Any] = {
                    "total_records": 0,
                    "records_by_type": {},
                    "records_by_day": {},
                    "last_record_time": "N/A"
                }

                # Initialize statistics based on any pre-existing record files.
                self._initialize_stats()

                # Remove old records that exceed the retention period.
                self._cleanup_old_records()

                # Mark instance as initialized.
                self._initialized = True
                # Log information about successful initialization.
                log_info("[GDPR] Processing record keeper initialized")

    def _initialize_stats(self) -> None:
        """
        Initialize statistics from existing record files.

        This method reads each record file, counts the number of records,
        and updates the statistics. Specific exceptions are caught to ensure
        robust operation without halting on individual file errors.
        """
        # Attempt to list record files in the directory.
        try:
            record_files = [
                f for f in os.listdir(self.records_dir)
                if f.startswith("processing_record_") and f.endswith(JSON_CONSTANT)
            ]
        except (OSError, IOError) as e:
            # Log a warning if listing the directory fails.
            log_warning(f"[GDPR] Error listing record directory: {e}")
            return

        # Initialize total record counter.
        total_count = 0
        # Iterate over each record file.
        for file_name in record_files:
            # Construct full file path.
            file_path = os.path.join(self.records_dir, file_name)
            try:
                # Open the record file in read mode.
                with open(file_path, 'r', encoding='utf-8') as f:
                    # Count the number of records (lines) in the file.
                    count = sum(1 for _ in f)
                # Add count to the total records.
                total_count += count
                # Extract the date from the filename.
                date_str = file_name.replace("processing_record_", "").replace(JSON_CONSTANT, "")
                # Update the stats dictionary with count for that day.
                self.stats["records_by_day"][date_str] = count
            except (OSError, IOError, ValueError) as e:
                # Log a warning if processing the file fails.
                log_warning(f"[GDPR] Error processing file '{file_name}': {e}")
                continue

        # Set the total records count in the stats.
        self.stats["total_records"] = total_count
        # Log information about the number of existing records.
        log_info(f"[GDPR] Found {total_count} existing processing records")

    def record_processing(
            self,
            operation_type: str,
            document_type: str,
            entity_types_processed: List[str],
            processing_time: float,
            file_count: int = 1,
            entity_count: int = 0,
            success: bool = True
    ) -> None:
        """
        Record a processing operation without storing personal data.

        Complies with GDPR Article 30 by storing minimal metadata.

        Args:
          operation_type: Type of operation (e.g., transformation, redaction).
          document_type: Category of document processed.
          entity_types_processed: List of processed entity types.
          processing_time: Duration taken to complete the operation (in seconds).
          file_count: Number of files processed during the operation.
          entity_count: Count of entities processed.
          success: Flag indicating success or failure of the operation.
        """
        # Get current timestamp.
        timestamp = datetime.now()
        # Build the record dictionary with operation details.
        record = {
            "timestamp": timestamp.isoformat(),
            "operation_type": operation_type,
            "document_type": document_type,
            "entity_types": entity_types_processed,
            "processing_time_seconds": round(processing_time, 3),
            "file_count": file_count,
            "entity_count": entity_count,
            "success": success,
            "legal_basis": GDPR_DOCUMENTATION.get('legal_basis', 'legitimate_interests'),
            "operation_id": hashlib.sha256(
                f"{timestamp.isoformat()}_{operation_type}_{document_type}".encode()
            ).hexdigest()[:16]
        }
        # Log the creation of a new processing record.
        log_info(f"[GDPR_RECORD] Processing record created for {operation_type}")

        # Format the record date as a string.
        record_date = timestamp.strftime("%Y-%m-%d")
        # Construct the record file path based on the date.
        record_file = os.path.join(self.records_dir, f"processing_record_{record_date}{JSON_CONSTANT}")

        # Attempt to write the record to the file.
        try:
            # Open the file in append mode.
            with open(record_file, 'a', encoding='utf-8') as f:
                # Write the JSON record and append a newline.
                f.write(json.dumps(record) + '\n')
        except (OSError, IOError) as e:
            # Log a warning if writing the record fails.
            log_warning(f"[GDPR_RECORD] Failed to write processing record /Check ANTIVIRUS/: {e}")
            return

        # Update in-memory statistics under a thread-safe lock.
        with self.__class__._lock:
            # Increment the total record count.
            self.stats["total_records"] += 1
            # Update the last record timestamp.
            self.stats["last_record_time"] = timestamp.isoformat()
            # Update the record count for the specific operation type.
            self.stats["records_by_type"][operation_type] = self.stats["records_by_type"].get(operation_type, 0) + 1
            # Update the record count for the specific day.
            self.stats["records_by_day"][record_date] = self.stats["records_by_day"].get(record_date, 0) + 1

    def get_gdpr_compliance_info(self) -> Dict[str, Any]:
        """
        Retrieve GDPR compliance details regarding the processing records.

        Returns:
            A dictionary containing compliance information such as processor details,
            controller details, processing purposes, subject categories, and retention policy.
        """
        # Build the compliance information dictionary.
        compliance_info = {
            "gdpr_article_30_compliance": {
                "record_keeping": "Maintains records of all processing activities as required by GDPR Art. 30",
                "processor_details": GDPR_DOCUMENTATION.get('processor_details', 'System processor details'),
                "controller_details": GDPR_DOCUMENTATION.get('controller_details', 'System controller details'),
                "processing_purposes": GDPR_DOCUMENTATION.get('processing_purposes',
                                                              'Entity detection and document redaction'),
                "data_subject_categories": GDPR_DOCUMENTATION.get('data_subject_categories',
                                                                  'Document subjects and mentioned individuals'),
                "recipient_categories": GDPR_DOCUMENTATION.get('recipient_categories',
                                                               'None - processed data remains with controller'),
                "retention_period": f"{self.record_retention_days} days",
                "security_measures": "Anonymization, secure hashing, minimal data collection"
            },
            "data_minimization": {
                "principle": "Only essential metadata about processing is stored, no personal data",
                "implementation": "Records contain operation type, timestamp, and performance metrics only",
                "identifiers": "Operation IDs are securely hashed to prevent reconstruction"
            },
            "storage_limitation": {
                "record_retention": f"{self.record_retention_days} days",
                "deletion_method": "Automatic file deletion after retention period",
                "deletion_frequency": "Daily check for expired records"
            },
            "legal_basis": {
                "basis": GDPR_DOCUMENTATION.get('legal_basis', 'legitimate_interests'),
                "documentation": GDPR_DOCUMENTATION.get('legal_basis_documentation',
                                                        'Processing necessary for enhancing document security and privacy')
            }
        }
        # Return the compiled compliance details.
        return compliance_info

    def _cleanup_old_records(self) -> None:
        """
        Clean up processing records older than the retention period.

        This method deletes record files whose dates are earlier than the cutoff date.
        Specific exceptions related to file operations are caught to ensure robust cleanup.
        """
        # Compute the cutoff date by subtracting the retention period from now.
        try:
            cutoff_date = datetime.now() - timedelta(days=self.record_retention_days)
            # Format the cutoff date as a string.
            cutoff_str = cutoff_date.strftime("%Y-%m-%d")
        except Exception as e:
            # Log a warning if the cutoff date calculation fails.
            log_warning(f"[GDPR] Error computing cutoff date: {e}")
            return

        # Attempt to list all processing record files in the records directory.
        try:
            record_files = [
                f for f in os.listdir(self.records_dir)
                if f.startswith("processing_record_") and f.endswith(JSON_CONSTANT)
            ]
        except (OSError, IOError) as e:
            # Log a warning if directory listing fails.
            log_warning(f"[GDPR] Error listing record directory for cleanup: {e}")
            return

        # Initialize a counter for the number of deleted files.
        deleted_count = 0
        # Iterate through each record file.
        for file_name in record_files:
            try:
                # Extract the date string from the file name.
                date_str = file_name.replace("processing_record_", "").replace(JSON_CONSTANT, "")
                # If the record date is older than the cutoff, delete the file.
                if date_str < cutoff_str:
                    # Build the full file path.
                    file_path = os.path.join(self.records_dir, file_name)
                    # Remove the file from the system.
                    os.unlink(file_path)
                    # Increment the deletion counter.
                    deleted_count += 1
                    # Update the in-memory statistics if the date exists.
                    if date_str in self.stats["records_by_day"]:
                        # Decrease the total record count by the number of records for that day.
                        self.stats["total_records"] -= self.stats["records_by_day"][date_str]
                        # Remove the day from the records-by-day dictionary.
                        del self.stats["records_by_day"][date_str]
            except (OSError, IOError) as e:
                # Log a warning if deletion of a file fails.
                log_warning(f"[GDPR] Error deleting file '{file_name}': {e}")
                continue

        # If any files were deleted, log the summary.
        if deleted_count > 0:
            log_info(
                f"[GDPR] Deleted {deleted_count} processing record files older than {self.record_retention_days} days")

    def get_record_stats(self) -> Dict[str, Any]:
        """
        Retrieve statistical data about recorded processing operations.

        Returns:
            A dictionary with statistics, including total records, records by type and day,
            retention policy details, and GDPR documentation.
        """
        # Acquire class-level lock to safely read the shared statistics.
        with self.__class__._lock:
            # Create a shallow copy of the stat's dictionary.
            stats_copy = self.stats.copy()
            # Create separate copies for nested dictionaries to avoid unintentional modification.
            stats_copy["records_by_type"] = self.stats["records_by_type"].copy()
            stats_copy["records_by_day"] = self.stats["records_by_day"].copy()
            # Add retention policy information.
            stats_copy["retention_policy"] = {
                "retention_days": self.record_retention_days,
                "records_directory": os.path.basename(self.records_dir)
            }
            # Include GDPR documentation details.
            stats_copy["gdpr_documentation"] = GDPR_DOCUMENTATION
            # Return the complete statistics.
            return stats_copy


# Create a singleton instance of the ProcessingRecordKeeper.
record_keeper = ProcessingRecordKeeper()
