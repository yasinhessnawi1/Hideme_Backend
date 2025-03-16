"""
Enhanced data minimization utilities with comprehensive GDPR compliance.

This module provides functions to implement the GDPR principle of data
minimization by ensuring only necessary data is processed and retained,
with advanced anonymization, metadata removal, and audit logging capabilities.
"""
import re
import time
import logging
import hashlib
from typing import Dict, Any, List, Optional, Set
from datetime import datetime

from backend.app.utils.processing_records import record_keeper
from backend.app.configs.gdpr_config import (
    DATA_MINIMIZATION_RULES,
    ANONYMIZATION_CONFIG
)

# Configure module logger
_logger = logging.getLogger("data_minimization")


def minimize_extracted_data(
    extracted_data: Dict[str, Any],
    required_fields_only: Optional[bool] = None,
    metadata_fields: Optional[Set[str]] = None,
    trace_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Minimize data according to GDPR principles of data minimization with audit logging.

    Only retains what's necessary for entity detection and redaction,
    applying additional filters based on configuration and keeping
    precise records for GDPR compliance.

    Args:
        extracted_data: Original extracted data
        required_fields_only: Whether to keep only required fields (overrides config)
        metadata_fields: Optional set of metadata fields to retain
        trace_id: Optional trace ID for audit logging

    Returns:
        Minimized version of the extracted data
    """
    if not extracted_data:
        return {"pages": []}

    # Generate trace ID if not provided
    if not trace_id:
        trace_id = f"minimize_{int(time.time())}_{hashlib.md5(str(time.time()).encode()).hexdigest()[:6]}"

    start_time = time.time()

    # Use configured setting if not explicitly provided
    if required_fields_only is None:
        required_fields_only = DATA_MINIMIZATION_RULES.get("required_fields_only", True)

    # Create a deep copy to avoid modifying the original
    minimized_data = {"pages": []}

    # Default metadata fields to retain
    if metadata_fields is None:
        metadata_fields = {
            "total_document_pages",
            "empty_pages",
            "content_pages"
        }

    # Copy permitted metadata fields
    for field in metadata_fields:
        if field in extracted_data:
            minimized_data[field] = extracted_data[field]

    # Calculate initial data size for audit
    original_size = _estimate_data_size(extracted_data)
    field_counts = {"total_words": 0, "removed_fields": 0, "retained_fields": 0}

    # Process each page
    for page in extracted_data.get("pages", []):
        minimized_page = {
            "page": page["page"],
            "words": []
        }

        # Process words in page
        for word in page.get("words", []):
            field_counts["total_words"] += 1

            # Skip empty words
            if not word.get("text", "").strip():
                continue

            # Only keep required fields for processing
            if required_fields_only:
                minimized_word = {
                    "text": word["text"],
                    "x0": word["x0"],
                    "y0": word["y0"],
                    "x1": word["x1"],
                    "y1": word["y1"]
                }
                field_counts["removed_fields"] += len(word) - len(minimized_word)
                field_counts["retained_fields"] += len(minimized_word)
            else:
                # Create a copy of the word to avoid modifying the original
                minimized_word = word.copy()

                # Remove any potentially sensitive fields not needed for processing
                sensitive_fields = ["content", "meta", "original", "raw", "owner", "source"]
                for sensitive_field in sensitive_fields:
                    if sensitive_field in minimized_word:
                        del minimized_word[sensitive_field]
                        field_counts["removed_fields"] += 1

            minimized_page["words"].append(minimized_word)

        # Only add pages with content
        if minimized_page["words"]:
            minimized_data["pages"].append(minimized_page)

    # Calculate final data size for audit
    minimized_size = _estimate_data_size(minimized_data)
    reduction_percentage = ((original_size - minimized_size) / original_size * 100) if original_size > 0 else 0

    # Add minimization metadata
    minimized_data["_minimization_meta"] = {
        "applied_at": datetime.now().isoformat(),
        "required_fields_only": required_fields_only,
        "fields_retained": list(metadata_fields) if metadata_fields else []
    }

    # Log minimization metrics
    _logger.info(
        f"[GDPR] Data minimized: {original_size/1024:.1f}KB → {minimized_size/1024:.1f}KB "
        f"({reduction_percentage:.1f}% reduction) [trace_id={trace_id}]"
    )

    # Record operation for GDPR compliance
    record_keeper.record_processing(
        operation_type="data_minimization",
        document_type="extracted_data",
        entity_types_processed=[],
        processing_time=time.time() - start_time,
        file_count=1,
        entity_count=0,
        success=True
    )

    return minimized_data


def sanitize_document_metadata(
    metadata: Dict[str, Any],
    sanitize_all: bool = False,
    preserve_fields: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Sanitize document metadata to remove potentially sensitive information.

    This function provides comprehensive metadata sanitization with configurable
    field preservation and sanitization strategies.

    Args:
        metadata: Original document metadata
        sanitize_all: Whether to sanitize all fields except preserved ones
        preserve_fields: List of fields to preserve even when sanitize_all is True

    Returns:
        Sanitized metadata with sensitive information removed
    """
    if not metadata:
        return {}

    start_time = time.time()

    # Create a copy to avoid modifying the original
    sanitized = metadata.copy()

    # Default fields to preserve
    if preserve_fields is None:
        preserve_fields = ["page_count", "version", "title", "subject"]

    # Fields to completely remove unless preserved
    fields_to_remove = [
        "author", "creator", "producer", "keywords",
        "owner", "user", "email", "phone", "address", "location",
        "gps", "coordinates", "custom", "username", "computer",
        "device", "software", "revision", "person", "modified_by",
        "thumbnail", "last_modified_by", "comment", "category"
    ]

    # Fields to sanitize with replacement values
    fields_to_sanitize = {
        "title": "[Document Title]",
        "subject": "[Document Subject]",
        "producer": "[Software Producer]",
        "creator": "[Document Creator]",
        "creation_date": "[Creation Date Removed]",
        "mod_date": "[Modification Date Removed]",
        "last_modified": "[Last Modified Date Removed]"
    }

    # Regular expressions to detect potentially sensitive information
    sensitive_patterns = [
        (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]'),
        (r'\b(?:\+\d{1,3}[-\.\s]?)?(?:\d{1,4}[-\.\s]?){2,5}\d{1,4}\b', '[PHONE]'),
        (r'\b\d{6}\s?\d{5}\b', '[ID_NUMBER]'),  # Generic ID number pattern
        (r'\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b', '[MAC_ADDRESS]'),
        (r'\b(?:\d{1,3}\.){3}\d{1,3}\b', '[IP_ADDRESS]')
    ]

    # Process removal of fields
    for field in fields_to_remove:
        if field in sanitized and field not in preserve_fields:
            del sanitized[field]

    # Process sanitization of specific fields
    for field, replacement in fields_to_sanitize.items():
        if field in sanitized and field not in preserve_fields:
            sanitized[field] = replacement

    # If sanitize_all is True, sanitize all remaining fields except preserved ones
    if sanitize_all:
        for field in list(sanitized.keys()):
            if field not in preserve_fields:
                # Apply pattern-based sanitization to string fields
                if isinstance(sanitized[field], str):
                    sanitized_value = sanitized[field]
                    for pattern, replacement in sensitive_patterns:
                        sanitized_value = re.sub(pattern, replacement, sanitized_value)
                    sanitized[field] = sanitized_value

    # Add sanitization metadata
    sanitized["_sanitized"] = True

    # Record operation for GDPR compliance
    record_keeper.record_processing(
        operation_type="metadata_sanitization",
        document_type="document_metadata",
        entity_types_processed=[],
        processing_time=time.time() - start_time,
        file_count=1,
        entity_count=0,
        success=True
    )

    return sanitized


def anonymize_entity(
    text: str,
    entity: Dict[str, Any],
    anonymization_strategy: Optional[str] = None
) -> str:
    """
    Anonymize a single entity in text with configurable strategy.

    Args:
        text: Original text containing the entity
        entity: Entity dictionary with start, end, and entity_type
        anonymization_strategy: Strategy to use (tag, hash, randomize)

    Returns:
        Text with the entity anonymized
    """
    # Default to tag strategy if not specified
    if not anonymization_strategy:
        anonymization_strategy = ANONYMIZATION_CONFIG.get("anonymization_strategy", "tag")

    start = entity.get("start", 0)
    end = entity.get("end", 0)
    entity_type = entity.get("entity_type", "UNKNOWN")

    # Ensure valid indices
    if not (0 <= start < end <= len(text)):
        return text

    # Get the entity text
    entity_text = text[start:end]

    # Apply the selected anonymization strategy
    if anonymization_strategy == "tag":
        replacement = f"<{entity_type}>"
    elif anonymization_strategy == "hash":
        # Create a consistent hash of the entity text
        hash_obj = hashlib.sha256(entity_text.encode())
        replacement = f"[{entity_type[:3]}:{hash_obj.hexdigest()[:8]}]"
    elif anonymization_strategy == "randomize":
        # Replace with random characters preserving length
        import random
        import string
        chars = string.ascii_letters + string.digits
        replacement = ''.join(random.choice(chars) for _ in range(len(entity_text)))
    else:
        # Default fallback
        replacement = f"[REDACTED:{entity_type}]"

    # Replace the entity in the text
    return text[:start] + replacement + text[end:]


def anonymize_text(
    text: str,
    entities: List[Dict[str, Any]],
    strategy: Optional[str] = None
) -> str:
    """
    Anonymize multiple entities in text.

    Args:
        text: Original text
        entities: List of entities to anonymize
        strategy: Anonymization strategy

    Returns:
        Anonymized text
    """
    if not text or not entities:
        return text

    # Sort entities by start position in reverse order to avoid changing offsets
    sorted_entities = sorted(entities, key=lambda e: e.get("start", 0), reverse=True)

    # Create a copy of the text to modify
    anonymized = text

    # Apply anonymization to each entity
    for entity in sorted_entities:
        anonymized = anonymize_entity(anonymized, entity, strategy)

    return anonymized


def _estimate_data_size(data: Any) -> int:
    """
    Estimate the size of data structure in bytes.

    Args:
        data: Data to estimate size for

    Returns:
        Estimated size in bytes
    """
    import sys
    import json

    try:
        # Fast estimation using JSON serialization
        serialized = json.dumps(data)
        return len(serialized)
    except (TypeError, OverflowError):
        # Fallback for objects that can't be serialized
        if isinstance(data, dict):
            return sum(_estimate_data_size(k) + _estimate_data_size(v) for k, v in data.items())
        elif isinstance(data, (list, tuple, set)):
            return sum(_estimate_data_size(i) for i in data)
        else:
            return sys.getsizeof(data)