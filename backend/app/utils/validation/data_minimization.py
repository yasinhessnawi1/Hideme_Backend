"""
Enhanced data minimization utilities with comprehensive GDPR compliance.
This module provides functions to implement the GDPR principle of data minimization by ensuring only
necessary data is processed and retained. It includes advanced anonymization, metadata removal, and audit logging
capabilities to help safeguard sensitive information.
"""

import hashlib
import logging
import re
import time
from typing import Dict, Any, List, Optional, Set, Union, Tuple

from backend.app.configs.gdpr_config import DATA_MINIMIZATION_RULES
from backend.app.utils.constant.constant import SENSITIVE_FIELDS, DEFAULT_METADATA_FIELDS
from backend.app.utils.security.processing_records import record_keeper

# Configure module logger.
_logger = logging.getLogger("data_minimization")


def _get_trace_id(provided: Optional[str]) -> str:
    """
    Generate a trace ID if not provided.

    Args:
        provided (Optional[str]): Provided trace ID if available.

    Returns:
        str: The original trace ID if provided; otherwise, a newly generated trace ID based on current time.
    """
    # Check if a trace ID is provided.
    if provided:
        # Return the provided trace ID.
        return provided
    # Get the current time.
    now = time.time()
    # Generate a new trace ID using the integer part of the time and a short MD5 hash.
    return f"minimize_{int(now)}_{hashlib.md5(str(now).encode()).hexdigest()[:6]}"


def _minimize_word(word: Dict[str, Any], required_fields_only: bool) -> Optional[Dict[str, Any]]:
    """
    Process a single word entry to minimize it.

    Args:
        word (Dict[str, Any]): A dictionary representing a word with its properties.
        required_fields_only (bool): If True, only a fixed set of fields is retained.

    Returns:
        Optional[Dict[str, Any]]: A minimized dictionary of the word or None if the word has no text.
    """
    # Check if the word has non-empty "text" field.
    if not word.get("text", "").strip():
        # Return None if the text is empty.
        return None
    # If only required fields should be retained...
    if required_fields_only:
        # Return a dictionary with only a fixed set of fields.
        return {
            "text": word.get("text", ""),
            "x0": word.get("x0"),
            "y0": word.get("y0"),
            "x1": word.get("x1"),
            "y1": word.get("y1")
        }
    # Otherwise, make a full copy of the word.
    minimized = word.copy()
    # Remove any sensitive fields from the copied dictionary.
    for field in SENSITIVE_FIELDS:
        if field in minimized:
            del minimized[field]
    # Return the minimized word dictionary.
    return minimized


def _minimize_page(page: Dict[str, Any], required_fields_only: bool) -> Optional[Dict[str, Any]]:
    """
    Process a single page by minimizing all its word entries.

    Args:
        page (Dict[str, Any]): A dictionary representing a page with word entries.
        required_fields_only (bool): Flag to indicate if only required fields should be retained for words.

    Returns:
        Optional[Dict[str, Any]]: A dictionary with the page number and minimized words, or None if no words remain.
    """
    # Initialize a list to hold minimized word dictionaries.
    minimized_words = []
    # Iterate over each word in the page's "words" list.
    for word in page.get("words", []):
        try:
            # Process the word using _minimize_word.
            mw = _minimize_word(word, required_fields_only)
            # If a minimized word was returned, add it to the list.
            if mw is not None:
                minimized_words.append(mw)
        except Exception as e:
            # Log a warning if an error occurs while processing a word.
            _logger.warning("Error minimizing word: %s", e)
            continue
    # If there are any minimized words, return a dictionary with the page number and words.
    if minimized_words:
        return {"page": page.get("page"), "words": minimized_words}
    # Return None if no words are retained.
    return None


def _estimate_data_size(data: Any) -> int:
    """
    Estimate the size of a data structure in bytes using JSON serialization.

    Args:
        data (Any): The data structure to measure.

    Returns:
        int: The estimated size in bytes.

    If JSON serialization fails, the function recursively estimates the size.
    """
    import sys, json
    try:
        # Attempt to serialize the data into JSON.
        serialized = json.dumps(data)
        # Return the length of the JSON string.
        return len(serialized)
    except (TypeError, OverflowError):
        # If serialization fails and data is a dictionary, sum sizes of keys and values.
        if isinstance(data, dict):
            return sum(_estimate_data_size(k) + _estimate_data_size(v) for k, v in data.items())
        # If data is a list, tuple, or set, sum sizes of individual elements.
        elif isinstance(data, (list, tuple, set)):
            return sum(_estimate_data_size(i) for i in data)
        else:
            # Fallback to system's getsizeof function.
            return sys.getsizeof(data)


def _extract_valid_data(data: Union[Dict[str, Any], Tuple[int, Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Extract the dictionary from the input if valid.

    Args:
        data (Union[Dict[str, Any], Tuple[int, Dict[str, Any]]]): The input data which may be a dict or a tuple containing a dict.

    Returns:
        Dict[str, Any]: The extracted dictionary or an empty dictionary if input is invalid.
    """
    # If data is a tuple with two elements and the second element is a dictionary...
    if isinstance(data, tuple) and len(data) == 2 and isinstance(data[1], dict):
        # Return the dictionary part.
        return data[1]
    # If data is already a dictionary, return it.
    if isinstance(data, dict):
        return data
    # Otherwise, return an empty dictionary.
    return {}


def _process_pages(pages: List[Dict[str, Any]], required_fields_only: bool) -> List[Dict[str, Any]]:
    """
    Process a list of pages by applying minimization to each page.

    Args:
        pages (List[Dict[str, Any]]): A list of page dictionaries.
        required_fields_only (bool): If True, each page is processed to retain only the required fields.

    Returns:
        List[Dict[str, Any]]: A list of minimized page dictionaries.
    """
    # Initialize an empty list to store processed page data.
    processed = []
    # Iterate over each page in the list.
    for page in pages:
        try:
            # Minimize the page using _minimize_page.
            mp = _minimize_page(page, required_fields_only)
            # If the page contains minimized words, append it to the list.
            if mp:
                processed.append(mp)
        except Exception as e:
            # Log a warning if an error occurs while processing a page.
            _logger.warning("Error processing page: %s", e)
    # Return the list of processed (minimized) pages.
    return processed


def minimize_extracted_data(
        extracted_data: Union[Dict[str, Any], Tuple[int, Dict[str, Any]]],
        required_fields_only: Optional[bool] = None,
        metadata_fields: Optional[Set[str]] = None,
        trace_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Minimize extracted data according to GDPR data minimization principles.

    Processes input data (which may be a dictionary or a tuple from batch processing) and returns a minimized version
    that retains only the necessary fields as dictated by configuration and function arguments. It logs the reduction in data
    size and records the operation for GDPR compliance.

    Args:
        extracted_data (Union[Dict[str, Any], Tuple[int, Dict[str, Any]]]): Original extracted data.
        required_fields_only (Optional[bool]): If True, only required fields are retained (overrides config if provided).
        metadata_fields (Optional[Set[str]]): Set of metadata field names to preserve.
        trace_id (Optional[str]): Optional trace ID for audit logging.

    Returns:
        Dict[str, Any]: A dictionary containing minimized data.
    """
    # Extract a valid data dictionary from the input.
    data = _extract_valid_data(extracted_data)
    # If extracted data is empty, return a dictionary with an empty "pages" list.
    if not data:
        return {"pages": []}

    # Generate or retrieve the trace ID.
    trace_id = _get_trace_id(trace_id)
    # Record the starting time of data minimization.
    start_time = time.time()

    # Determine whether to retain only required fields based on configuration.
    if required_fields_only is None:
        required_fields_only = DATA_MINIMIZATION_RULES.get("required_fields_only", True)
    # Set the metadata fields to preserve, either from input or default.
    metadata_fields = metadata_fields or DEFAULT_METADATA_FIELDS

    # Initialize minimized data with an empty pages list.
    minimized_data: Dict[str, Any] = {"pages": []}
    # Copy over allowed metadata fields from the original data.
    for field in metadata_fields:
        if field in data:
            minimized_data[field] = data[field]

    # Process and minimize each page.
    minimized_data["pages"] = _process_pages(data.get("pages", []), required_fields_only)

    # Estimate the size of the original and minimized data for logging.
    original_size = _estimate_data_size(data)
    minimized_size = _estimate_data_size(minimized_data)
    # Calculate the percentage reduction in size.
    reduction_percentage = ((original_size - minimized_size) / original_size * 100) if original_size > 0 else 0

    # Append metadata about the minimization operation.
    minimized_data["_minimization_meta"] = {
        "applied_at": time.time(),
        "required_fields_only": required_fields_only,
        "fields_retained": list(metadata_fields)
    }

    # Log information about the data size reduction.
    _logger.info(
        "[GDPR] Data minimized: %.1fKB → %.1fKB (%.1f%% reduction) [trace_id=%s]",
        original_size / 1024, minimized_size / 1024, reduction_percentage, trace_id
    )

    # Record the processing event for auditing and GDPR compliance.
    try:
        record_keeper.record_processing(
            operation_type="data_minimization",
            document_type="extracted_data",
            entity_types_processed=[],
            processing_time=time.time() - start_time,
            file_count=1,
            entity_count=0,
            success=True
        )
    except Exception as e:
        # Log a warning if recording of processing fails.
        _logger.warning("Failed to record processing: %s", e)

    # Return the minimized data.
    return minimized_data


def _remove_unwanted_fields(metadata: Dict[str, Any], fields_to_remove: List[str], preserve_fields: List[str]) -> None:
    """
    Remove fields from metadata that are not in the preserve list.

    Args:
        metadata (Dict[str, Any]): The original metadata dictionary.
        fields_to_remove (List[str]): List of field names to remove.
        preserve_fields (List[str]): List of field names that should be preserved.

    This function iterates over the fields to remove and deletes them from the metadata
    if they are not in the preserve list.
    """
    # Iterate over each field that should be removed.
    for field in fields_to_remove:
        # Check if the field is present and is not marked to be preserved.
        if field in metadata and field not in preserve_fields:
            try:
                # Delete the field from the metadata.
                del metadata[field]
            except Exception as e:
                # Log a warning if an error occurs when removing the field.
                _logger.warning("Error removing field '%s': %s", field, e)


def _sanitize_specific_fields(metadata: Dict[str, Any], fields_to_sanitize: Dict[str, str],
                              preserve_fields: List[str]) -> None:
    """
    Replace values of specific fields with predefined replacement values.

    Args:
        metadata (Dict[str, Any]): The metadata dictionary.
        fields_to_sanitize (Dict[str, str]): Mapping of field names to their replacement values.
        preserve_fields (List[str]): List of fields to preserve without alteration.

    This function scans through specified fields and replaces their values if they are not in the preserve list.
    """
    # Iterate over the field and replacement pairs.
    for field, replacement in fields_to_sanitize.items():
        # If the field exists and is not preserved, replace its value.
        if field in metadata and field not in preserve_fields:
            metadata[field] = replacement


def _apply_sensitive_patterns(value: str, patterns: List[Tuple[str, str]]) -> str:
    """
    Apply regex-based substitutions to a string value.

    Args:
        value (str): The original string value.
        patterns (List[Tuple[str, str]]): List of tuples with regex patterns and their replacements.

    Returns:
        str: The sanitized string with sensitive information replaced.
    """
    # Iterate over each pattern and its replacement.
    for pattern, replacement in patterns:
        try:
            # Apply the regex substitution.
            value = re.sub(pattern, replacement, value)
        except Exception as e:
            # Log any errors that occur while applying the pattern.
            _logger.warning("Error applying pattern '%s': %s", pattern, e)
    # Return the updated string.
    return value


def _sanitize_all_fields(metadata: Dict[str, Any], preserve_fields: List[str], patterns: List[Tuple[str, str]]) -> None:
    """
    Sanitize all string fields in metadata (except those preserved) using regex patterns.

    Args:
        metadata (Dict[str, Any]): The metadata dictionary.
        preserve_fields (List[str]): List of field names that should not be sanitized.
        patterns (List[Tuple[str, str]]): List of regex patterns with their replacement values.

    This function iterates through all string fields in the metadata and applies regex-based sanitization
    to protect sensitive data.
    """
    # Iterate over each field and its value.
    for field, value in list(metadata.items()):
        # Check if the field is not preserved and the value is a string.
        if field not in preserve_fields and isinstance(value, str):
            # Apply sensitive patterns to the value.
            metadata[field] = _apply_sensitive_patterns(value, patterns)


def sanitize_document_metadata(
        metadata: Dict[str, Any],
        sanitize_all: bool = False,
        preserve_fields: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Sanitize document metadata to remove potentially sensitive information.

    This function applies a series of steps to the provided metadata:
      - Removing unwanted fields.
      - Replacing values for specific fields.
      - Optionally sanitizing all remaining string fields using regex patterns.
    It then records the operation and returns a sanitized metadata dictionary.

    Args:
        metadata (Dict[str, Any]): The original document metadata.
        sanitize_all (bool): If True, perform full sanitization on all fields except preserved ones.
        preserve_fields (Optional[List[str]]): List of field names to preserve during sanitization.

    Returns:
        Dict[str, Any]: The sanitized metadata dictionary.
    """
    # If metadata is empty or None, return an empty dictionary.
    if not metadata:
        return {}

    # Record the start time of the sanitization process.
    start_time = time.time()
    # Create a copy of the original metadata to avoid modifying it in place.
    sanitized = metadata.copy()

    # Set default fields to preserve if none are provided.
    preserve_fields = preserve_fields or ["page_count", "version", "title", "subject"]

    # List of fields to remove from metadata.
    fields_to_remove = [
        "author", "creator", "producer", "keywords", "owner", "user", "email", "phone", "address",
        "location", "gps", "coordinates", "custom", "username", "computer", "device", "software",
        "revision", "person", "modified_by", "thumbnail", "last_modified_by", "comment", "category"
    ]
    # Dictionary of fields to sanitize (replace their values).
    fields_to_sanitize = {
        "title": "[Document Title]",
        "subject": "[Document Subject]",
        "producer": "[Software Producer]",
        "creator": "[Document Creator]",
        "creation_date": "[Creation Date Removed]",
        "mod_date": "[Modification Date Removed]",
        "last_modified": "[Last Modified Date Removed]"
    }
    # Define sensitive patterns and their replacement strings.
    sensitive_patterns = [
        (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]'),
        (r'\b(?:\+\d{1,3}[-\.\s]?)?(?:\d{1,4}[-\.\s]?){2,5}\d{1,4}\b', '[PHONE]'),
        (r'\b\d{6}\s?\d{5}\b', '[ID_NUMBER]'),
        (r'\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b', '[MAC_ADDRESS]'),
        (r'\b(?:\d{1,3}\.){3}\d{1,3}\b', '[IP_ADDRESS]')
    ]

    # Remove unwanted metadata fields.
    _remove_unwanted_fields(sanitized, fields_to_remove, preserve_fields)
    # Replace values for specific fields with predefined replacements.
    _sanitize_specific_fields(sanitized, fields_to_sanitize, preserve_fields)
    # If full sanitization is requested, apply regex-based substitutions to all string fields.
    if sanitize_all:
        _sanitize_all_fields(sanitized, preserve_fields, sensitive_patterns)

    # Mark that sanitization has been applied.
    sanitized["_sanitized"] = True

    # Record processing for GDPR compliance via processing records.
    try:
        record_keeper.record_processing(
            operation_type="metadata_sanitization",
            document_type="document_metadata",
            entity_types_processed=[],
            processing_time=time.time() - start_time,
            file_count=1,
            entity_count=0,
            success=True
        )
    except Exception as e:
        # Log a warning if recording the processing event fails.
        _logger.warning("Failed to record metadata sanitization: %s", e)

    # Return the sanitized metadata.
    return sanitized
