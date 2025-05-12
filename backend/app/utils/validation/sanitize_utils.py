"""
Utility functions for sanitizing and standardizing API responses.
This module provides functions to sanitize and standardize the output from
entity detection engines by:
  - Removing duplicate entities.
  - Removing duplicate sensitive items in redaction mappings.
  - Organizing entities by type for easier consumption.
  - Counting entities per page.
  - Replacing keys in dictionaries while preserving order.
  - Processing individual items and lists of items to tag them with an engine name.
These functions ensure that API responses are consistent, minimized, and safe for consumption.
"""

import time
from collections import defaultdict
from typing import Dict, Any, List, Optional

from backend.app.utils.logging.logger import log_info


def sanitize_detection_output(
    entities: List[Dict[str, Any]],
    redaction_mapping: Dict[str, Any],
    processing_times: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Sanitize and standardize entity detection output for API responses.

    Processes the list of entities and redaction mapping by:
      1. Removing duplicate entities based on start/end positions and entity type.
      2. Removing duplicate sensitive items in the redaction mapping.
      3. Organizing entities by type.
      4. Counting entities per page.
      5. Adding performance metrics if available.
      6. Including the time taken for sanitization.

    Args:
        entities: List of detected entity dictionaries.
        redaction_mapping: Dictionary mapping sensitive items with their positions.
        processing_times: Optional dictionary containing processing time metrics.

    Returns:
        A standardized and sanitized API response dictionary.
    """
    # Record the start time for measuring sanitization duration.
    start_time = time.time()

    # Deduplicate the list of entities.
    unique_entities = deduplicate_entities(entities)

    # Deduplicate sensitive items in the redaction mapping.
    sanitized_mapping = deduplicate_redaction_mapping(redaction_mapping)

    # Organize unique entities by their type.
    entities_by_type = organize_entities_by_type(unique_entities)

    # Count the number of entities per page from the sanitized mapping.
    entities_per_page = count_entities_per_page(sanitized_mapping)

    # Prepare the structured response dictionary.
    response = {
        "redaction_mapping": sanitized_mapping,
        "entities_detected": {
            "total": len(unique_entities),
            "by_type": entities_by_type,
            "by_page": entities_per_page,
        },
    }

    # If processing time metrics are provided, add them into the response.
    if processing_times:
        response["performance"] = processing_times

    # Calculate the total time taken to sanitize the output.
    sanitize_time = time.time() - start_time
    # Record the sanitization time in the response under performance metrics.
    if "performance" in response:
        response["performance"]["sanitize_time"] = sanitize_time
    else:
        response["performance"] = {"sanitize_time": sanitize_time}

    # Log sanitization statistics including the number of entities reduced and elapsed time.
    log_info(
        f"[SANITIZE] Sanitized output: {len(entities)} → {len(unique_entities)} entities in {sanitize_time:.4f}s"
    )

    # Return the final standardized and sanitized response.
    return response


def deduplicate_entities(entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove duplicate entities based on entity type and start/end positions,
    retaining the one with the highest confidence score.

    Args:
        entities: List of entity dictionaries.

    Returns:
        List[Dict[str, Any]]: A list of unique entity dictionaries.
    """
    # Dictionary to track unique entities using a tuple as key.
    unique_entities = {}

    # Iterate over each entity in the list.
    for entity in entities:
        # Create a key from entity type, start and end positions.
        entity_key = (
            entity.get("entity_type", "UNKNOWN"),
            entity.get("start", 0),
            entity.get("end", 0),
        )

        # Get the confidence score of the current entity.
        score = float(entity.get("score", 0.0))

        # If the key exists, compare scores and keep the higher one.
        if entity_key in unique_entities:
            if score > unique_entities[entity_key].get("score", 0.0):
                unique_entities[entity_key] = entity
        else:
            # If the key is not present, add the entity.
            unique_entities[entity_key] = entity

    # Return a list of unique entities.
    return list(unique_entities.values())


def deduplicate_redaction_mapping(redaction_mapping: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove duplicate sensitive items in the redaction mapping.

    Considers items duplicates if they share the same entity_type, start, end,
    and bounding box coordinates.

    Args:
        redaction_mapping: A dictionary representing the redaction mapping.

    Returns:
        Dict[str, Any]: A deduplicated redaction mapping dictionary.
    """
    # Initialize the sanitized mapping with empty pages.
    sanitized_mapping = {"pages": []}

    # Iterate over each page info in the redaction mapping.
    for page_info in redaction_mapping.get("pages", []):
        # Get the page number.
        page_num = page_info.get("page")
        # Retrieve the list of sensitive items for the page.
        sensitive_items = page_info.get("sensitive", [])

        # Use a dictionary to track unique items.
        unique_items = {}

        # Iterate over each sensitive item.
        for item in sensitive_items:
            # Initialize bbox_key as None.
            bbox_key = None
            # If bounding box exists, create a key based on rounded coordinates.
            if "bbox" in item:
                bbox = item["bbox"]
                bbox_key = (
                    round(float(bbox.get("x0", 0)), 1),
                    round(float(bbox.get("y0", 0)), 1),
                    round(float(bbox.get("x1", 0)), 1),
                    round(float(bbox.get("y1", 0)), 1),
                )

            # Create a unique key for the item.
            item_key = (
                item.get("entity_type", "UNKNOWN"),
                item.get("start", 0),
                item.get("end", 0),
                bbox_key,
            )

            # Get the score for the sensitive item.
            score = float(item.get("score", 0.0))

            # If key exists, replace only if current score is higher.
            if item_key in unique_items:
                if score > unique_items[item_key].get("score", 0.0):
                    unique_items[item_key] = item
            else:
                unique_items[item_key] = item

        # Append the deduplicated items for this page into sanitized mapping.
        sanitized_mapping["pages"].append(
            {"page": page_num, "sensitive": list(unique_items.values())}
        )

    # Return the deduplicated redaction mapping.
    return sanitized_mapping


def deduplicate_bbox(
    search_results: List[Dict[str, Any]], precision: int = 1
) -> List[Dict[str, Any]]:
    """
    Remove duplicate search results based on bounding box coordinates.

    Two results are duplicates if their bounding boxes (x0, y0, x1, y1), rounded to a specified precision, are identical.

    Args:
        search_results (List[Dict[str, Any]]): List of dictionaries with a "bbox" key.
        precision (int): Decimal places for rounding bounding box coordinates.

    Returns:
        List[Dict[str, Any]]: List of deduplicated search result dictionaries.
    """
    # Dictionary to store unique results keyed by normalized bbox.
    unique_results = {}
    # Iterate over each search result.
    for result in search_results:
        # Retrieve the bounding box.
        bbox = result.get("bbox")
        if bbox:
            # Create a key by rounding each coordinate to the specified precision.
            bbox_key = (
                round(float(bbox.get("x0", 0)), precision),
                round(float(bbox.get("y0", 0)), precision),
                round(float(bbox.get("x1", 0)), precision),
                round(float(bbox.get("y1", 0)), precision),
            )
            # Add the result if it hasn't been seen before.
            if bbox_key not in unique_results:
                unique_results[bbox_key] = result
    # Return the list of unique search results.
    return list(unique_results.values())


def organize_entities_by_type(entities: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Organize entities by their type and count the occurrences of each type.

    Args:
        entities: List of entity dictionaries.

    Returns:
        Dict[str, int]: Dictionary mapping entity types to their occurrence counts.
    """
    # Create a defaultdict to count entities per type.
    entity_counts = defaultdict(int)
    # Iterate over each entity.
    for entity in entities:
        # Retrieve entity type; default to "UNKNOWN" if not present.
        entity_type = entity.get("entity_type", "UNKNOWN")
        # Increment the count for the entity type.
        entity_counts[entity_type] += 1
    # Convert defaultdict to a regular dictionary and return it.
    return dict(entity_counts)


def count_entities_per_page(redaction_mapping: Dict[str, Any]) -> Dict[str, int]:
    """
    Count entities per page based on the redaction mapping.

    Args:
        redaction_mapping: Dictionary representing the redaction mapping.

    Returns:
        Dict[str, int]: Dictionary mapping page identifiers (e.g., 'page_1') to entity counts.
    """
    # Initialize an empty dictionary to store counts per page.
    page_counts = {}
    # Iterate over each page in the redaction mapping.
    for page_info in redaction_mapping.get("pages", []):
        # Retrieve page number.
        page_num = page_info.get("page")
        # Get list of sensitive items for the page.
        sensitive_items = page_info.get("sensitive", [])
        # Record the count of sensitive items for the page with a key like 'page_1'.
        page_counts[f"page_{page_num}"] = len(sensitive_items)
    # Return the page counts dictionary.
    return page_counts


def replace_key_in_dict(d: dict, old_key: str, new_key: str, new_value: any) -> dict:
    """
    Create a new dictionary replacing a specified key with a new key and value while preserving key order.

    Args:
        d (dict): The original dictionary.
        old_key (str): The key to be replaced.
        new_key (str): The key to insert in place of the old key.
        new_value (any): The value to associate with the new key.

    Returns:
        dict: A new dictionary with the key replaced.
    """
    # Initialize a new dictionary.
    new_dict = {}
    # Iterate over each key-value pair in the original dictionary.
    for current_key, current_val in d.items():
        # If the current key matches the old key, insert the new key with new value.
        if current_key == old_key:
            new_dict[new_key] = new_value
        else:
            # Otherwise, copy the key-value pair as is.
            new_dict[current_key] = current_val
    # Return the modified dictionary.
    return new_dict


def process_item(item: dict, engine_name: str) -> dict:
    """
    Process an individual dictionary item.

    If the key 'original_text' exists in the item, replace it with a new key 'engine' and set its value to the provided engine name.
    Otherwise, simply add the 'engine' key with the engine name.

    Args:
        item (dict): The dictionary representing an entity or sensitive item.
        engine_name (str): The engine name to record.

    Returns:
        dict: The processed dictionary with standardized engine information.
    """
    # Check if the dictionary has the key 'original_text'.
    if "original_text" in item:
        # Replace the key using the helper function.
        return replace_key_in_dict(item, "original_text", "engine", engine_name)
    else:
        # Otherwise, create a copy and add the 'engine' key.
        new_item = dict(item)
        new_item["engine"] = engine_name
        return new_item


def process_items_list(items: list, engine_name: str) -> list:
    """
    Process a list of dictionary items by tagging each with the engine name.

    Args:
        items (list): A list of dictionaries representing entities or sensitive items.
        engine_name (str): The engine name to assign to each item.

    Returns:
        list: A list of processed dictionaries.
    """
    # Use list comprehension to process each item in the list.
    return [process_item(item, engine_name) for item in items]


def process_pages_list(pages: list, engine_name: str) -> list:
    """
    Process the pages in the redaction mapping by processing each sensitive item on each page.

    Args:
        pages (list): List of page dictionaries.
        engine_name (str): The engine name to assign to each sensitive item.

    Returns:
        list: A new list of page dictionaries with processed sensitive items.
    """
    # Initialize an empty list to store processed pages.
    new_pages = []
    # Iterate over each page in the input list.
    for page in pages:
        # Initialize a new dictionary for the page.
        new_page = {}
        # Iterate over each key-value pair in the page.
        for page_field, page_val in page.items():
            # If the field is "sensitive" and contains a list...
            if page_field == "sensitive" and isinstance(page_val, list):
                # Process the list of items.
                new_page[page_field] = process_items_list(page_val, engine_name)
            else:
                # Otherwise, copy the field as is.
                new_page[page_field] = page_val
        # Append the processed page to the list.
        new_pages.append(new_page)
    # Return the list of processed pages.
    return new_pages


def replace_original_text_in_redaction(
    redaction_mapping: dict, engine_name: str = "UNKNOWN"
) -> dict:
    """
    Replace the 'original_text' key in redaction mapping with 'engine' for each sensitive item.

    Args:
        redaction_mapping (dict): The original redaction mapping dictionary.
        engine_name (str): The engine name to set for the processed items.

    Returns:
        dict: The updated redaction mapping with replaced keys.
    """
    # If "pages" in redaction_mapping is a list, process each page.
    if isinstance(redaction_mapping.get("pages"), list):
        redaction_mapping["pages"] = process_pages_list(
            redaction_mapping["pages"], engine_name
        )
    # Return the updated redaction mapping.
    return redaction_mapping
