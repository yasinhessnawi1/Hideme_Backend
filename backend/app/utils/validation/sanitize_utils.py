"""
Utility functions for sanitizing and standardizing API responses.

This module provides functions to sanitize and standardize the output from
entity detection engines, removing duplicate entities and ensuring consistent
formatting for API responses.
"""
from typing import Dict, Any, List, Optional
import time
from collections import defaultdict

from backend.app.utils.logging.logger import log_info


def sanitize_detection_output(
        entities: List[Dict[str, Any]],
        redaction_mapping: Dict[str, Any],
        processing_times: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """
    Sanitize and standardize entity detection output for API responses.

    This function:
    1. Removes duplicate entities based on start/end positions and entity type
    2. Removes duplicate sensitive items in the redaction mapping
    3. Organizes entities by type for easier consumption
    4. Adds performance metrics if provided
    5. Formats the response consistently

    Args:
        entities: List of detected entities
        redaction_mapping: Mapping of sensitive items with their positions
        processing_times: Optional dictionary of processing time metrics

    Returns:
        Standardized and sanitized API response
    """
    start_time = time.time()

    # Deduplicate entities
    unique_entities = deduplicate_entities(entities)

    # Deduplicate sensitive items in redaction mapping
    sanitized_mapping = deduplicate_redaction_mapping(redaction_mapping)

    # Organize entities by type
    entities_by_type = organize_entities_by_type(unique_entities)

    # Count entities per page
    entities_per_page = count_entities_per_page(sanitized_mapping)

    # Prepare the response
    response = {
        "redaction_mapping": sanitized_mapping,
        "entities_detected": {
            "total": len(unique_entities),
            "by_type": entities_by_type,
            "by_page": entities_per_page
        }
    }

    # Add performance metrics if provided
    if processing_times:
        response["performance"] = processing_times

    # Add sanitization time
    sanitize_time = time.time() - start_time
    if "performance" in response:
        response["performance"]["sanitize_time"] = sanitize_time
    else:
        response["performance"] = {"sanitize_time": sanitize_time}

    # Log sanitization statistics
    log_info(f"[SANITIZE] Sanitized output: {len(entities)} → {len(unique_entities)} entities "
             f"in {sanitize_time:.4f}s")

    return response


def deduplicate_entities(entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove duplicate entities based on entity type, start, and end positions.

    When duplicates are found, the entity with the highest confidence score is kept.

    Args:
        entities: List of entity dictionaries

    Returns:
        List of unique entities
    """
    # Track unique entities based on type and position
    unique_entities = {}

    for entity in entities:
        # Create a key for entity deduplication
        entity_key = (
            entity.get("entity_type", "UNKNOWN"),
            entity.get("start", 0),
            entity.get("end", 0)
        )

        # Get the score
        score = float(entity.get("score", 0.0))

        # If we already have this entity, only keep the one with higher score
        if entity_key in unique_entities:
            if score > unique_entities[entity_key].get("score", 0.0):
                unique_entities[entity_key] = entity
        else:
            unique_entities[entity_key] = entity

    return list(unique_entities.values())


def deduplicate_redaction_mapping(redaction_mapping: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove duplicate sensitive items in the redaction mapping.

    Items are considered duplicates if they have the same entity_type, start, end,
    and bounding box coordinates.

    Args:
        redaction_mapping: Redaction mapping dictionary

    Returns:
        Deduplicated redaction mapping dictionary
    """
    sanitized_mapping = {"pages": []}

    for page_info in redaction_mapping.get("pages", []):
        page_num = page_info.get("page")
        sensitive_items = page_info.get("sensitive", [])

        # Create a set to track unique items
        unique_items = {}

        for item in sensitive_items:
            # Create a key for bbox (if present)
            bbox_key = None
            if "bbox" in item:
                bbox = item["bbox"]
                bbox_key = (
                    round(float(bbox.get("x0", 0)), 1),
                    round(float(bbox.get("y0", 0)), 1),
                    round(float(bbox.get("x1", 0)), 1),
                    round(float(bbox.get("y1", 0)), 1)
                )

            # Create a key for sensitive item deduplication
            item_key = (
                item.get("entity_type", "UNKNOWN"),
                item.get("start", 0),
                item.get("end", 0),
                bbox_key
            )

            # Get the score
            score = float(item.get("score", 0.0))

            # If we already have this item, only keep the one with higher score
            if item_key in unique_items:
                if score > unique_items[item_key].get("score", 0.0):
                    unique_items[item_key] = item
            else:
                unique_items[item_key] = item

        # Add deduplicated items to the result
        sanitized_mapping["pages"].append({
            "page": page_num,
            "sensitive": list(unique_items.values())
        })

    return sanitized_mapping


def organize_entities_by_type(entities: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Organize entities by their type and count occurrences.

    Args:
        entities: List of entities

    Returns:
        Dictionary mapping entity types to their counts
    """
    entity_counts = defaultdict(int)

    for entity in entities:
        entity_type = entity.get("entity_type", "UNKNOWN")
        entity_counts[entity_type] += 1

    return dict(entity_counts)


def count_entities_per_page(redaction_mapping: Dict[str, Any]) -> Dict[str, int]:
    """
    Count entities per page based on the redaction mapping.

    Args:
        redaction_mapping: Redaction mapping dictionary

    Returns:
        Dictionary mapping page numbers to entity counts
    """
    page_counts = {}

    for page_info in redaction_mapping.get("pages", []):
        page_num = page_info.get("page")
        sensitive_items = page_info.get("sensitive", [])
        page_counts[f"page_{page_num}"] = len(sensitive_items)

    return page_counts