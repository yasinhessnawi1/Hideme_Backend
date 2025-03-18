# backend/app/utils/processing_records.py
"""
GDPR processing records management with enhanced security features.

This module provides functionality for maintaining records of processing
activities as required by GDPR Article 30, without storing actual personal data.
"""
import json
import os
import threading
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from backend.app.utils.logger import log_info
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
       deletion after configurable retention period.

    4. Integrity and Confidentiality (Art. 5(1)(f)): Uses secure hashing for operation IDs
       to prevent reconstruction of original data.

    5. Accountability (Art. 5(2) and Art. 30): Provides comprehensive logging to
       demonstrate compliance with GDPR principles.

    6. Right to Erasure (Art. 17): Facilitates deletion of outdated records through
       automatic cleanup processes.

    7. Transparency (Art. 12-14): Captures legal basis for processing and maintains
       accessible documentation of processing activities.

    Implementation Notes:
    - Records are stored as JSONL files with one record per line for efficient append-only operation
    - Records are organized by date to facilitate timely deletion when retention period expires
    - No direct correlation is maintained between records and processed data to enhance privacy
    - Processing activities are hashed to prevent reconstruction of original content
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Ensure singleton pattern with thread safety."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ProcessingRecordKeeper, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self, records_dir: Optional[str] = None):
        """Initialize the record keeper."""
        with self._lock:
            if not getattr(self, '_initialized', False):
                self.records_dir = records_dir or os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "logs",
                    "processing_records"
                )

                # Ensure directory exists
                os.makedirs(self.records_dir, exist_ok=True)

                # Set up record retention
                self.record_retention_days = PROCESSING_RECORDS.get('record_retention_days', 90)

                # Track stats for reporting
                self.stats = {
                    "total_records": 0,
                    "records_by_type": {},
                    "records_by_day": {},
                    "last_record_time": "N/A"
                }

                # Initialize with existing records stats
                self._initialize_stats()

                # Start with cleanup to remove outdated records
                self._cleanup_old_records()

                self._initialized = True
                log_info("[GDPR] Processing record keeper initialized")

    def _initialize_stats(self) -> None:
        """Initialize statistics from existing record files."""
        try:
            # Get list of record files
            record_files = [
                f for f in os.listdir(self.records_dir)
                if f.startswith("processing_record_") and f.endswith(".jsonl")
            ]

            # Calculate total records
            total_count = 0
            for file_name in record_files:
                try:
                    file_path = os.path.join(self.records_dir, file_name)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        for i, _ in enumerate(f):
                            pass
                        count = i + 1
                        total_count += count

                        # Extract date from filename
                        date_str = file_name.replace("processing_record_", "").replace(".jsonl", "")
                        self.stats["records_by_day"][date_str] = count
                except:
                    continue

            self.stats["total_records"] = total_count
            log_info(f"[GDPR] Found {total_count} existing processing records")
        except Exception as e:
            log_info("[GDPR] Error initializing record stats")

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
        Complies with GDPR Article 30 requirements for Records of Processing Activities.
        """
        timestamp = datetime.now()
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
                f"{timestamp.isoformat()}_{operation_type}_{document_type}".encode()).hexdigest()[:16]
        }

        log_info(f"[GDPR_RECORD] Processing record created for {operation_type}")

        record_date = timestamp.strftime("%Y-%m-%d")
        record_file = os.path.join(self.records_dir, f"processing_record_{record_date}.jsonl")

        try:
            with open(record_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(record) + '\n')

            with self._lock:
                self.stats["total_records"] += 1
                self.stats["last_record_time"] = timestamp.isoformat()

                if operation_type not in self.stats["records_by_type"]:
                    self.stats["records_by_type"][operation_type] = 0
                self.stats["records_by_type"][operation_type] += 1

                if record_date not in self.stats["records_by_day"]:
                    self.stats["records_by_day"][record_date] = 0
                self.stats["records_by_day"][record_date] += 1

        except Exception as e:
            log_info(f"[GDPR_RECORD] Failed to write processing record: {type(e).__name__}")

    def get_gdpr_compliance_info(self) -> Dict[str, Any]:
        """
        Get detailed information about GDPR compliance mechanisms implemented in the record keeper.
        """
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

        return compliance_info

    def _cleanup_old_records(self) -> None:
        """
        Clean up processing records older than the retention period.
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=self.record_retention_days)
            cutoff_str = cutoff_date.strftime("%Y-%m-%d")

            record_files = [
                f for f in os.listdir(self.records_dir)
                if f.startswith("processing_record_") and f.endswith(".jsonl")
            ]

            deleted_count = 0
            for file_name in record_files:
                try:
                    date_str = file_name.replace("processing_record_", "").replace(".jsonl", "")
                    if date_str < cutoff_str:
                        file_path = os.path.join(self.records_dir, file_name)
                        os.unlink(file_path)
                        deleted_count += 1

                        if date_str in self.stats["records_by_day"]:
                            self.stats["total_records"] -= self.stats["records_by_day"][date_str]
                            del self.stats["records_by_day"][date_str]
                except:
                    continue

            if deleted_count > 0:
                log_info(
                    f"[GDPR] Deleted {deleted_count} processing record files older than {self.record_retention_days} days")
        except Exception as e:
            log_info("[GDPR] Error cleaning up old records")

    def get_record_stats(self) -> Dict[str, Any]:
        """
        Get statistics about processing records without exposing actual records.
        """
        with self._lock:
            stats_copy = self.stats.copy()
            stats_copy["records_by_type"] = self.stats["records_by_type"].copy()
            stats_copy["records_by_day"] = self.stats["records_by_day"].copy()
            stats_copy["retention_policy"] = {
                "retention_days": self.record_retention_days,
                "records_directory": os.path.basename(self.records_dir)
            }
            stats_copy["gdpr_documentation"] = GDPR_DOCUMENTATION
            return stats_copy


# Create a singleton instance
record_keeper = ProcessingRecordKeeper()
