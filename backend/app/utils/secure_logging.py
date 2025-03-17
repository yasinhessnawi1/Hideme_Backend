"""
Secure logging utilities with GDPR considerations.

This module provides specialized logging functions to avoid inadvertently
logging sensitive information while still providing useful diagnostic data.
"""
import json

from backend.app.utils.logger import log_info


def log_sensitive_operation(
        operation_name: str,
        entity_count: int,
        processing_time: float,
        **metadata
) -> None:
    """
    Log sensitive operations without including actual sensitive content.

    Args:
        operation_name: Name of the operation being performed
        entity_count: Number of entities processed
        processing_time: Time taken for processing
        **metadata: Additional metadata to log
    """
    log_info(f"[SENSITIVE] {operation_name}: processed {entity_count} entities in {processing_time:.2f}s")
    if metadata:
        # Filter out keys that might contain sensitive information
        sensitive_keys = ['text', 'content', 'entities', 'original_text', 'words', 'anonymized_text']
        sanitized_metadata = {k: v for k, v in metadata.items() if k not in sensitive_keys}

        # Additional sanitization for nested dictionaries
        for key in list(sanitized_metadata.keys()):
            if isinstance(sanitized_metadata[key], dict):
                for inner_key in list(sanitized_metadata[key].keys()):
                    if inner_key in sensitive_keys:
                        del sanitized_metadata[key][inner_key]

        log_info(f"[METADATA] {json.dumps(sanitized_metadata)}")


def log_batch_operation(
        operation_name: str,
        total_files: int,
        successful_files: int,
        processing_time: float
) -> None:
    """
    Log batch operations without details of individual files.

    Args:
        operation_name: Name of the operation being performed
        total_files: Total number of files processed
        successful_files: Number of successfully processed files
        processing_time: Time taken for processing
    """
    log_info(f"[BATCH] {operation_name}: {successful_files}/{total_files} files in {processing_time:.2f}s")