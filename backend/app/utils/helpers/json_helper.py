"""
JSON handling utilities for document processing.

This module provides functions to validate threshold scores, process JSON strings for various document processing
engines (Gemini, Presidio, GLiNER), and convert data to and from JSON format. It also includes functionality for
expanding shorthand entity options and ensuring that only valid entity types are processed. Detailed logging is
performed to facilitate debugging and error handling.
"""

import json
from typing import List, Optional, Any
from fastapi import HTTPException

from backend.app.configs.gemini_config import GEMINI_AVAILABLE_ENTITIES
from backend.app.configs.gliner_config import GLINER_AVAILABLE_ENTITIES
from backend.app.configs.presidio_config import PRESIDIO_AVAILABLE_ENTITIES
from backend.app.utils.logging.logger import log_info, log_warning, log_error


def validate_threshold_score(threshold: Optional[float]) -> Optional[float]:
    """
    Validate the threshold value.

    Args:
        threshold: The threshold score (expected between 0.00 and 1.00)

    Returns:
        The threshold score if valid.

    Raises:
        HTTPException: If the threshold is not between 0.00 and 1.00.
    """
    # Check if a threshold is provided and whether it falls outside the valid range.
    if threshold is not None and (threshold < 0.00 or threshold > 1.00):
        # If the threshold is invalid, raise an HTTPException with a 400 status.
        raise HTTPException(
            status_code=400,
            detail="Threshold must be between 0.00 and 1.00."
        )
    # Return the threshold if it is valid.
    return threshold


def check_all_option(entity_list):
    """
    Expand shorthand entity options within the given list into their full sets.

    If the list contains any of the special identifiers:
      - "ALL_PRESIDIO" is replaced with the complete list of available Presidio entities.
      - "ALL_GEMINI" is replaced with all available Gemini entity keys.
      - "ALL_GLINER" is replaced with the complete list of available GLiNER entities.

    Args:
        entity_list (List[str]): A list of entity identifiers or shorthand options.

    Returns:
        List[str]: A new list with all shorthand options expanded into complete entity lists.
    """
    # Initialize an empty list to store the expanded entities.
    new_list = []

    # Loop through each entity in the provided list.
    for entity in entity_list:
        # If the entity is "ALL_PRESIDIO", add all Presidio entities.
        if entity == "ALL_PRESIDIO":
            new_list.extend(PRESIDIO_AVAILABLE_ENTITIES)
        # If the entity is "ALL_GEMINI", add all keys from the Gemini entities dictionary.
        elif entity == "ALL_GEMINI":
            new_list.extend(list(GEMINI_AVAILABLE_ENTITIES.keys()))
        # If the entity is "ALL_GLINER", add all GLiNER entities.
        elif entity == "ALL_GLINER":
            new_list.extend(GLINER_AVAILABLE_ENTITIES)
        # Otherwise, add the entity as-is.
        else:
            new_list.append(entity)

    # Return the new list containing the fully expanded entity options.
    return new_list


def validate_all_engines_requested_entities(
        requested_entities: Optional[str],
        labels: Optional[List[str]] = None
) -> List[str]:
    """
    Validate and parse requested entities.

    Args:
        requested_entities: JSON string of entity types to detect.
        labels: Optional list of valid entity labels for validation.

    Returns:
        List of validated entity types.

    Raises:
        HTTPException: If validation fails.
    """
    # Check whether a JSON string of requested entities is provided.
    if not requested_entities:
        # Log a warning if none is provided and use default entity types.
        log_warning("[OK]No specific entities requested, using defaults")
        # Return a merged list of default entities from Gemini, Presidio, and GLINER.
        return list(GEMINI_AVAILABLE_ENTITIES.keys()) + PRESIDIO_AVAILABLE_ENTITIES + GLINER_AVAILABLE_ENTITIES

    try:
        # Parse the JSON string into a list of entities.
        entity_list = json.loads(requested_entities)
        # Expand any shorthand options like "ALL_PRESIDIO", "ALL_GEMINI", etc.
        entity_list = check_all_option(entity_list)

        # If a list of valid labels is provided, use it for validation.
        if labels:
            available_entities = labels
            # Validate each entity against the provided labels.
            for entity in entity_list:
                # Raise an exception if an entity is not valid.
                if entity not in available_entities:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid entity type: {entity}. Available entities: {available_entities}"
                    )
        else:
            # Otherwise, validate against standard defaults.
            available_entities = list(
                GEMINI_AVAILABLE_ENTITIES.keys()) + PRESIDIO_AVAILABLE_ENTITIES + GLINER_AVAILABLE_ENTITIES
            # Loop through each entity and validate its presence in the available entities list.
            for entity in entity_list:
                # Raise an exception if an invalid entity is encountered.
                if entity not in available_entities:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid entity type: {entity}. Available entities: {available_entities}"
                    )

        # Log a confirmation message with the validated entities.
        log_info(f"[OK] Validated entity list: {entity_list}")
        # Return the list of validated entities.
        return entity_list

    except json.JSONDecodeError:
        # Log an error if the JSON string is not properly formatted.
        log_error("[OK]Invalid JSON format in requested_entities")
        # Raise an HTTPException indicating an invalid JSON format.
        raise HTTPException(status_code=400, detail="Invalid JSON format in ALL_requested_entities")


def validate_gemini_requested_entities(requested_entities: Optional[str]) -> List[str]:
    """
    Validate and parse requested entities for the Gemini engine.

    Args:
        requested_entities: JSON string of entity types to detect.

    Returns:
        List of validated entity types for Gemini; invalid entities are removed.

    Raises:
        HTTPException: If JSON parsing fails.
    """
    # Check if the JSON string is provided.
    if not requested_entities:
        # Log a warning indicating that defaults will be used.
        log_warning("[Gemini] No specific entities requested, using defaults")
        # Return an empty list as defaults for Gemini.
        return []
    try:
        # Parse the JSON string into a list.
        entity_list = json.loads(requested_entities)
        # Initialize a list to store validated entities.
        validated_entities = []
        # Loop over each entity in the parsed list.
        for entity in entity_list:
            # If the entity equals "ALL_GEMINI", add all Gemini keys.
            if entity == "ALL_GEMINI":
                validated_entities.extend(list(GEMINI_AVAILABLE_ENTITIES.keys()))
            else:
                # Otherwise, simply add the entity.
                validated_entities.append(entity)

        # Filter the list to only retain valid Gemini entities.
        filtered_entities = [entity for entity in validated_entities if entity in GEMINI_AVAILABLE_ENTITIES]
        # Identify any entities that are not valid.
        invalid_entities = [entity for entity in validated_entities if entity not in GEMINI_AVAILABLE_ENTITIES]
        # Log a warning if there are invalid entities.
        if invalid_entities:
            log_warning(f"[Gemini] Removing invalid entities: {invalid_entities}")
        # Log an informational message with the validated list.
        log_info(f"[Gemini] Validated entity list: {filtered_entities}")
        # Return the validated list.
        return filtered_entities

    except json.JSONDecodeError:
        # Log an error if the JSON string format is invalid.
        log_error("[Gemini] Invalid JSON format in requested_entities")
        # Raise an HTTPException indicating the JSON format error.
        raise HTTPException(status_code=400, detail="Invalid JSON format in gemini requested_entities")


def validate_presidio_requested_entities(requested_entities: Optional[str]) -> List[str]:
    """
    Validate and parse requested entities for the Presidio engine.

    Args:
        requested_entities: JSON string of entity types to detect.

    Returns:
        List of validated entity types for Presidio; invalid entities are removed.

    Raises:
        HTTPException: If JSON parsing fails.
    """
    # Check if a JSON string was provided.
    if not requested_entities:
        # Log a warning that defaults are being used for Presidio.
        log_warning("[Presidio] No specific entities requested, using defaults")
        # Return an empty list as defaults for Presidio.
        return []
    try:
        # Parse the JSON string into a list.
        entity_list = json.loads(requested_entities)
        # Initialize an empty list for validated entities.
        validated_entities = []
        # Loop through each entity in the parsed list.
        for entity in entity_list:
            # If the entity equals "ALL_PRESIDIO", extend with all available Presidio entities.
            if entity == "ALL_PRESIDIO":
                validated_entities.extend(PRESIDIO_AVAILABLE_ENTITIES)
            else:
                # Otherwise, add the entity to the validated list.
                validated_entities.append(entity)
        # Filter the list to only include valid Presidio entities.
        filtered_entities = [entity for entity in validated_entities if entity in PRESIDIO_AVAILABLE_ENTITIES]
        # Identify any invalid entities.
        invalid_entities = [entity for entity in validated_entities if entity not in PRESIDIO_AVAILABLE_ENTITIES]
        # Log a warning if any invalid entities are found.
        if invalid_entities:
            log_warning(f"[Presidio] Removing invalid entities: {invalid_entities}")
        # Log an info message with the final validated list.
        log_info(f"[Presidio] Validated entity list: {filtered_entities}")
        # Return the validated list.
        return filtered_entities

    except json.JSONDecodeError:
        # Log an error if the JSON string is malformed.
        log_error("[Presidio] Invalid JSON format in requested_entities")
        # Raise an HTTPException to indicate the invalid format.
        raise HTTPException(status_code=400, detail="Invalid JSON format in presidio requested_entities")


def validate_gliner_requested_entities(requested_entities: Optional[str]) -> List[str]:
    """
    Validate and parse requested entities for the Gliner engine.

    Args:
        requested_entities: JSON string of entity types to detect.

    Returns:
        List of validated entity types for Gliner; invalid entities are removed.

    Raises:
        HTTPException: If JSON parsing fails.
    """
    # Check if any JSON string was provided.
    if not requested_entities:
        # Log a warning indicating that defaults are used for Gliner.
        log_warning("[Gliner] No specific entities requested, using defaults")
        # Return an empty list if no entities are specified.
        return []
    try:
        # Parse the JSON string into a list of entities.
        entity_list = json.loads(requested_entities)
        # Initialize a list to accumulate validated entities.
        validated_entities = []
        # Iterate over each entity.
        for entity in entity_list:
            # If the entity equals "ALL_GLINER", extend with all available GLINER entities.
            if entity == "ALL_GLINER":
                validated_entities.extend(GLINER_AVAILABLE_ENTITIES)
            else:
                # Otherwise, add the individual entity.
                validated_entities.append(entity)
        # Filter out only those entities that are valid for Gliner.
        filtered_entities = [entity for entity in validated_entities if entity in GLINER_AVAILABLE_ENTITIES]
        # Identify any invalid entities.
        invalid_entities = [entity for entity in validated_entities if entity not in GLINER_AVAILABLE_ENTITIES]
        # Log a warning if there are invalid entities.
        if invalid_entities:
            log_warning(f"[Gliner] Removing invalid entities: {invalid_entities}")
        # Log an informational message with the validated list.
        log_info(f"[Gliner] Validated entity list: {filtered_entities}")
        # Return the validated list.
        return filtered_entities

    except json.JSONDecodeError:
        # Log an error if JSON parsing fails.
        log_error("[Gliner] Invalid JSON format in requested_entities")
        # Raise an HTTPException to indicate the error.
        raise HTTPException(status_code=400, detail="Invalid JSON format in gliner requested_entities")


def convert_to_json(data: Any, indent: int = 2) -> str:
    """
    Convert data to a JSON string with custom converter for non-serializable objects.

    Args:
        data: Data to convert.
        indent: Indentation level.

    Returns:
        JSON string.

    Raises:
        ValueError: If conversion fails.
    """
    try:
        # Define a custom converter function for non-serializable objects.
        def custom_converter(obj):
            # If the object has a __dict__ attribute, return its dictionary representation.
            if hasattr(obj, '__dict__'):
                return obj.__dict__
            # If the object has a to_dict method, call it to retrieve a dictionary.
            elif hasattr(obj, 'to_dict'):
                return obj.to_dict()
            # Otherwise, raise a TypeError indicating the object is not serializable.
            raise TypeError(f"Type not serializable: {type(obj)}")
        # Use json.dumps with the custom converter to try to convert the data to a JSON string.
        json_str = json.dumps(
            data,
            indent=indent,
            ensure_ascii=False,
            default=custom_converter
        )
        # Return the resulting JSON string.
        return json_str

    except Exception as e:
        # Log an error if conversion fails.
        log_error(f"[OK]Error converting data to JSON: {e}")
        # Raise a ValueError with the error message.
        raise ValueError(f"Error converting data to JSON: {e}")


def parse_json(json_str: str) -> Any:
    """
    Parse a JSON string safely.

    Args:
        json_str: JSON string to parse.

    Returns:
        Parsed JSON data.

    Raises:
        ValueError: If parsing fails.
    """
    try:
        # Attempt to load the JSON string into a Python data structure.
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        # Log an error if the JSON string is not properly formatted.
        log_error(f"[OK]Invalid JSON format: {e}")
        # Raise a ValueError indicating the JSON string is invalid.
        raise ValueError(f"Invalid JSON format: {e}")
