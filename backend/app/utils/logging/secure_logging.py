"""
Secure logging utilities with GDPR considerations.

This module provides specialized logging functions to avoid inadvertently
logging sensitive information while still providing useful diagnostic data.
"""
import json

from backend.app.utils.logging.logger import log_info


def log_sensitive_operation(operation_name: str, entity_count: int, processing_time: float, **metadata) -> None:
    """
    Log sensitive operations without including actual sensitive content.

    Parameters:
        operation_name (str): Name of the operation being performed.
        entity_count (int): Number of entities processed.
        processing_time (float): Time taken for processing.
        **metadata: Additional metadata to log, excluding keys that could contain sensitive information.

    Returns:
        None
    """
    # Log the sensitive operation details with a [SENSITIVE] prefix
    log_info(f"[SENSITIVE] {operation_name}: processed {entity_count} entities in {processing_time:.2f}s")
    # Check if additional metadata is provided
    if metadata:
        # Define a list of keys that are considered sensitive and should not be logged
        sensitive_keys = ['text', 'content', 'entities', 'original_text', 'words', 'anonymized_text']
        # Create a sanitized dictionary by excluding keys that are sensitive
        sanitized_metadata = {k: v for k, v in metadata.items() if k not in sensitive_keys}
        # Iterate over keys in the sanitized metadata to further sanitize nested dictionaries
        for key in list(sanitized_metadata.keys()):
            # Check if the metadata value is a dictionary
            if isinstance(sanitized_metadata[key], dict):
                # Iterate through the inner keys of the dictionary
                for inner_key in list(sanitized_metadata[key].keys()):
                    # Delete inner key if it is in the sensitive keys list
                    if inner_key in sensitive_keys:
                        del sanitized_metadata[key][inner_key]
        # Log the sanitized metadata as a JSON string with a [METADATA] prefix
        log_info(f"[METADATA] {json.dumps(sanitized_metadata)}")


def log_batch_operation(operation_name: str, total_files: int, successful_files: int,
                        processing_time: float) -> None:
    """
    Log batch operations without details of individual files.

    Parameters:
        operation_name (str): Name of the operation being performed.
        total_files (int): Total number of files processed.
        successful_files (int): Number of successfully processed files.
        processing_time (float): Time taken for processing.

    Returns:
        None
    """
    # Log the batch operation details with a [BATCH] prefix showing successful/total files and processing time
    log_info(f"[BATCH] {operation_name}: {successful_files}/{total_files} files in {processing_time:.2f}s")
