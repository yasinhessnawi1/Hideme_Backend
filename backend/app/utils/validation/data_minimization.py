"""
Enhanced data minimization utilities with comprehensive GDPR compliance.

This module provides functions to implement the GDPR principle of data minimization by ensuring only
necessary data is processed and retained, with advanced anonymization, metadata removal, and audit logging capabilities.
"""

import hashlib
import logging
import re
import time
from typing import Dict, Any, List, Optional, Set, Union, Tuple

from backend.app.configs.gdpr_config import DATA_MINIMIZATION_RULES
from backend.app.utils.security.processing_records import record_keeper

# Configure module logger
_logger = logging.getLogger("data_minimization")

# Constants for sensitive fields and default metadata retention.
SENSITIVE_FIELDS = ["content", "meta", "original", "raw", "owner", "source"]
DEFAULT_METADATA_FIELDS: Set[str] = {"total_document_pages", "empty_pages", "content_pages"}

# Helper functions for minimize_extracted_data

def _get_trace_id(provided: Optional[str]) -> str:
    """Generate a trace ID if not provided."""
    if provided:
        return provided
    now = time.time()
    return f"minimize_{int(now)}_{hashlib.md5(str(now).encode()).hexdigest()[:6]}"


def _minimize_word(word: Dict[str, Any], required_fields_only: bool) -> Optional[Dict[str, Any]]:
    """
    Process a single word entry to minimize it.

    If required_fields_only is True, only a fixed set of fields is retained.
    Otherwise, a copy is made and sensitive fields are removed.
    """
    if not word.get("text", "").strip():
        return None
    if required_fields_only:
        return {
            "text": word.get("text", ""),
            "x0": word.get("x0"),
            "y0": word.get("y0"),
            "x1": word.get("x1"),
            "y1": word.get("y1")
        }
    minimized = word.copy()
    for field in SENSITIVE_FIELDS:
        if field in minimized:
            del minimized[field]
    return minimized


def _minimize_page(page: Dict[str, Any], required_fields_only: bool) -> Optional[Dict[str, Any]]:
    """
    Process a single page by minimizing all its word entries.

    Returns a page dictionary only if there are words retained.
    """
    minimized_words = []
    for word in page.get("words", []):
        try:
            mw = _minimize_word(word, required_fields_only)
            if mw is not None:
                minimized_words.append(mw)
        except Exception as e:
            _logger.warning("Error minimizing word: %s", e)
            continue
    if minimized_words:
        return {"page": page.get("page"), "words": minimized_words}
    return None


def _estimate_data_size(data: Any) -> int:
    """
    Estimate the size of a data structure in bytes using JSON serialization.

    Falls back to recursive estimation if serialization fails.
    """
    import sys, json
    try:
        serialized = json.dumps(data)
        return len(serialized)
    except (TypeError, OverflowError):
        if isinstance(data, dict):
            return sum(_estimate_data_size(k) + _estimate_data_size(v) for k, v in data.items())
        elif isinstance(data, (list, tuple, set)):
            return sum(_estimate_data_size(i) for i in data)
        else:
            return sys.getsizeof(data)


def _extract_valid_data(data: Union[Dict[str, Any], Tuple[int, Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Extract the dictionary from the input if valid.

    If the input is a tuple of (index, dict) or already a dict, return the dict.
    Otherwise, return an empty dict.
    """
    if isinstance(data, tuple) and len(data) == 2 and isinstance(data[1], dict):
        return data[1]
    if isinstance(data, dict):
        return data
    return {}


def _process_pages(pages: List[Dict[str, Any]], required_fields_only: bool) -> List[Dict[str, Any]]:
    """
    Process a list of pages by applying minimization to each page.

    Returns a list of minimized page dictionaries.
    """
    processed = []
    for page in pages:
        try:
            mp = _minimize_page(page, required_fields_only)
            if mp:
                processed.append(mp)
        except Exception as e:
            _logger.warning("Error processing page: %s", e)
    return processed


# Primary functions

def minimize_extracted_data(
        extracted_data: Union[Dict[str, Any], Tuple[int, Dict[str, Any]]],
        required_fields_only: Optional[bool] = None,
        metadata_fields: Optional[Set[str]] = None,
        trace_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Minimize extracted data according to GDPR data minimization principles.

    Processes input data (which may come as a tuple from batch processing) and returns a minimized version
    that retains only necessary fields. Logs the reduction in data size and records the operation for GDPR compliance.

    Args:
        extracted_data: Original extracted data as a dict or a tuple (index, dict).
        required_fields_only: If True, only required fields are retained (overrides config if provided).
        metadata_fields: Set of metadata fields to retain.
        trace_id: Optional trace ID for audit logging.

    Returns:
        A dictionary with minimized data.
    """
    data = _extract_valid_data(extracted_data)
    if not data:
        return {"pages": []}

    trace_id = _get_trace_id(trace_id)
    start_time = time.time()

    if required_fields_only is None:
        required_fields_only = DATA_MINIMIZATION_RULES.get("required_fields_only", True)
    metadata_fields = metadata_fields or DEFAULT_METADATA_FIELDS

    minimized_data: Dict[str, Any] = {"pages": []}
    # Copy permitted metadata fields.
    for field in metadata_fields:
        if field in data:
            minimized_data[field] = data[field]

    minimized_data["pages"] = _process_pages(data.get("pages", []), required_fields_only)

    original_size = _estimate_data_size(data)
    minimized_size = _estimate_data_size(minimized_data)
    reduction_percentage = ((original_size - minimized_size) / original_size * 100) if original_size > 0 else 0

    minimized_data["_minimization_meta"] = {
        "applied_at": time.time(),
        "required_fields_only": required_fields_only,
        "fields_retained": list(metadata_fields)
    }

    _logger.info(
        "[GDPR] Data minimized: %.1fKB → %.1fKB (%.1f%% reduction) [trace_id=%s]",
        original_size / 1024, minimized_size / 1024, reduction_percentage, trace_id
    )

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
        _logger.warning("Failed to record processing: %s", e)

    return minimized_data


# Helper functions for sanitize_document_metadata

def _remove_unwanted_fields(metadata: Dict[str, Any], fields_to_remove: List[str], preserve_fields: List[str]) -> None:
    """
    Remove fields from metadata that are not in the preserve list.
    """
    for field in fields_to_remove:
        if field in metadata and field not in preserve_fields:
            try:
                del metadata[field]
            except Exception as e:
                _logger.warning("Error removing field '%s': %s", field, e)


def _sanitize_specific_fields(metadata: Dict[str, Any], fields_to_sanitize: Dict[str, str], preserve_fields: List[str]) -> None:
    """
    Replace values of specific fields with predefined replacement values.
    """
    for field, replacement in fields_to_sanitize.items():
        if field in metadata and field not in preserve_fields:
            metadata[field] = replacement


def _apply_sensitive_patterns(value: str, patterns: List[Tuple[str, str]]) -> str:
    """
    Apply regex-based substitutions to a string value.
    """
    for pattern, replacement in patterns:
        try:
            value = re.sub(pattern, replacement, value)
        except Exception as e:
            _logger.warning("Error applying pattern '%s': %s", pattern, e)
    return value


def _sanitize_all_fields(metadata: Dict[str, Any], preserve_fields: List[str], patterns: List[Tuple[str, str]]) -> None:
    """
    Sanitize all string fields in metadata (except those preserved) using regex patterns.
    """
    for field, value in list(metadata.items()):
        if field not in preserve_fields and isinstance(value, str):
            metadata[field] = _apply_sensitive_patterns(value, patterns)


# Primary function for metadata sanitization

def sanitize_document_metadata(
        metadata: Dict[str, Any],
        sanitize_all: bool = False,
        preserve_fields: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Sanitize document metadata to remove potentially sensitive information.

    Applies comprehensive sanitization by removing unwanted fields, replacing values for certain fields,
    and, if requested, applying regex-based sanitization to all remaining fields.

    Args:
        metadata: Original document metadata.
        sanitize_all: If True, sanitize all fields except those explicitly preserved.
        preserve_fields: List of field names to preserve even during full sanitization.

    Returns:
        A dictionary with sanitized metadata.
    """
    if not metadata:
        return {}

    start_time = time.time()
    sanitized = metadata.copy()

    # Default fields to preserve.
    preserve_fields = preserve_fields or ["page_count", "version", "title", "subject"]

    # Define fields to remove and fields to replace.
    fields_to_remove = [
        "author", "creator", "producer", "keywords", "owner", "user", "email", "phone", "address",
        "location", "gps", "coordinates", "custom", "username", "computer", "device", "software",
        "revision", "person", "modified_by", "thumbnail", "last_modified_by", "comment", "category"
    ]
    fields_to_sanitize = {
        "title": "[Document Title]",
        "subject": "[Document Subject]",
        "producer": "[Software Producer]",
        "creator": "[Document Creator]",
        "creation_date": "[Creation Date Removed]",
        "mod_date": "[Modification Date Removed]",
        "last_modified": "[Last Modified Date Removed]"
    }
    sensitive_patterns = [
        (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]'),
        (r'\b(?:\+\d{1,3}[-\.\s]?)?(?:\d{1,4}[-\.\s]?){2,5}\d{1,4}\b', '[PHONE]'),
        (r'\b\d{6}\s?\d{5}\b', '[ID_NUMBER]'),
        (r'\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b', '[MAC_ADDRESS]'),
        (r'\b(?:\d{1,3}\.){3}\d{1,3}\b', '[IP_ADDRESS]')
    ]

    # Remove unwanted fields.
    _remove_unwanted_fields(sanitized, fields_to_remove, preserve_fields)
    # Replace values for specific fields.
    _sanitize_specific_fields(sanitized, fields_to_sanitize, preserve_fields)
    # If requested, sanitize all remaining string fields.
    if sanitize_all:
        _sanitize_all_fields(sanitized, preserve_fields, sensitive_patterns)

    # Mark metadata as sanitized.
    sanitized["_sanitized"] = True

    # Record processing for GDPR compliance.
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
        _logger.warning("Failed to record metadata sanitization: %s", e)

    return sanitized