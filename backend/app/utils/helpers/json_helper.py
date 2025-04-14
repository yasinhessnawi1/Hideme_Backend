"""
JSON handling utilities for document processing.

This module provides functions to:
    - Validate threshold scores.
    - Expand shorthand entity options (e.g. "ALL_PRESIDIO", "ALL_GEMINI", "ALL_GLINER", "ALL_HIDEME").

Detailed logging is performed for debugging and error handling.
"""

import json
from typing import List, Optional
from fastapi import HTTPException
from backend.app.configs.gemini_config import GEMINI_AVAILABLE_ENTITIES
from backend.app.configs.gliner_config import GLINER_AVAILABLE_ENTITIES
from backend.app.configs.hideme_config import HIDEME_AVAILABLE_ENTITIES
from backend.app.configs.presidio_config import PRESIDIO_AVAILABLE_ENTITIES
from backend.app.utils.logging.logger import log_info, log_warning, log_error


def validate_threshold_score(threshold: Optional[float]) -> Optional[float]:
    """
    Validate the threshold score.

    This function checks whether the provided threshold is between 0.00 and 1.00.

    Args:
        threshold (Optional[float]): The threshold value to be validated.

    Returns:
        Optional[float]: The validated threshold if within range, or None.
    """
    # Check if a threshold is provided.
    if threshold is not None:
        # Check whether the threshold is less than 0.00 or greater than 1.00.
        if threshold < 0.00 or threshold > 1.00:
            # Raise an HTTPException with status code 400 if threshold is invalid.
            raise HTTPException(
                status_code=400,
                detail="Threshold must be between 0.00 and 1.00."
            )
    # Return the provided threshold if valid.
    return threshold


def check_all_option(entity_list: List[str]) -> List[str]:
    """
    Expand shorthand entity options into their full sets.

    For each item in the list:
      - "ALL_PRESIDIO" is replaced with all available Presidio entities.
      - "ALL_GEMINI" is replaced with all available Gemini entity keys.
      - "ALL_GLINER" is replaced with all available GLiNER entities.
      - "ALL_HIDEME" is replaced with all available HIDEME entities.

    Args:
        entity_list (List[str]): List of entity strings.

    Returns:
        List[str]: Fully expanded list of entities.
    """
    # Initialize an empty list to hold expanded entity names.
    new_list = []
    # Iterate through each entity in the provided list.
    for entity in entity_list:
        # Check if the entity matches the shorthand "ALL_PRESIDIO".
        if entity == "ALL_PRESIDIO":
            # Extend new_list with all available Presidio entities.
            new_list.extend(PRESIDIO_AVAILABLE_ENTITIES)
        # Check if the entity matches the shorthand "ALL_GEMINI".
        elif entity == "ALL_GEMINI":
            # Extend new_list with all available Gemini entity keys.
            new_list.extend(list(GEMINI_AVAILABLE_ENTITIES.keys()))
        # Check if the entity matches the shorthand "ALL_GLINER".
        elif entity == "ALL_GLINER":
            # Extend new_list with all available GLiNER entities.
            new_list.extend(GLINER_AVAILABLE_ENTITIES)
        # Check if the entity matches the shorthand "ALL_HIDEME".
        elif entity == "ALL_HIDEME":
            # Extend new_list with all available HIDEME entities.
            new_list.extend(HIDEME_AVAILABLE_ENTITIES)
        else:
            # For any other entity, append it as-is to new_list.
            new_list.append(entity)
    # Return the expanded list of entities.
    return new_list


def validate_all_engines_requested_entities(
        requested_entities: Optional[str],
        labels: Optional[List[str]] = None
) -> List[str]:
    """
    Validate and parse the requested entities for all engines.

    This function parses a JSON string of requested entities and expands any shorthand
    options such as "ALL_PRESIDIO", "ALL_GEMINI", "ALL_GLINER", and "ALL_HIDEME". It then validates
    the resulting list against the provided valid labels, or the default merged entity list from all engines.

    Args:
        requested_entities (Optional[str]): A JSON string containing the requested entities.
        labels (Optional[List[str]]): Optional list of valid labels to validate against.

    Returns:
        List[str]: Validated and expanded list of requested entities.
    """
    # Check if no requested entities are provided.
    if not requested_entities:
        # Log a warning that no entities were requested.
        log_warning("[OK] No specific entities requested, using defaults")
        # Return the default merged list of entities from all engines.
        return list(
            GEMINI_AVAILABLE_ENTITIES.keys()) + PRESIDIO_AVAILABLE_ENTITIES + GLINER_AVAILABLE_ENTITIES + HIDEME_AVAILABLE_ENTITIES

    try:
        # Parse the JSON string to a Python list.
        entity_list = json.loads(requested_entities)
        # Expand any shorthand options in the entity list.
        entity_list = check_all_option(entity_list)
        # Check if custom labels are provided for validation.
        if labels:
            # Set available_entities to provided labels.
            available_entities = labels
            # Iterate through each entity in the expanded list.
            for entity in entity_list:
                # Check if the entity is not in the available entities.
                if entity not in available_entities:
                    # Raise an HTTPException for invalid entity type.
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid entity type: {entity}. Available entities: {available_entities}"
                    )
        else:
            # Merge default available entities for all engines.
            available_entities = list(
                GEMINI_AVAILABLE_ENTITIES.keys()) + PRESIDIO_AVAILABLE_ENTITIES + GLINER_AVAILABLE_ENTITIES + HIDEME_AVAILABLE_ENTITIES
            # Iterate through each entity to validate against the merged list.
            for entity in entity_list:
                # Check if entity is not in the merged available entities.
                if entity not in available_entities:
                    # Raise an HTTPException for invalid entity type.
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid entity type: {entity}. Available entities: {available_entities}"
                    )
        # Log the successfully validated entity list.
        log_info(f"[OK] Validated entity list: {entity_list}")
        # Return the validated entity list.
        return entity_list

    except json.JSONDecodeError:
        # Log an error for invalid JSON format.
        log_error("[OK] Invalid JSON format in requested_entities")
        # Raise an HTTPException indicating JSON format error.
        raise HTTPException(status_code=400, detail="Invalid JSON format in ALL_requested_entities")


def validate_gemini_requested_entities(requested_entities: Optional[str]) -> List[str]:
    """
    Validate and parse the requested entities for the Gemini engine.

    This function parses a JSON string and expands any "ALL_GEMINI" shorthand options,
    then filters out invalid entities based on available Gemini entities.

    Args:
        requested_entities (Optional[str]): JSON string of requested Gemini entities.

    Returns:
        List[str]: Validated list of Gemini entities.
    """
    # Check if no requested entities are provided.
    if not requested_entities:
        # Log a warning that no entities were provided for Gemini.
        log_warning("[Gemini] No specific entities requested, using defaults")
        # Return an empty list indicating defaults.
        return []
    try:
        # Parse the JSON string into a list.
        entity_list = json.loads(requested_entities)
        # Initialize an empty list for validated entities.
        validated_entities = []
        # Iterate through each entity in the parsed list.
        for entity in entity_list:
            # Check if the entity is the shorthand "ALL_GEMINI".
            if entity == "ALL_GEMINI":
                # Expand and extend validated_entities with all Gemini entity keys.
                validated_entities.extend(list(GEMINI_AVAILABLE_ENTITIES.keys()))
            else:
                # Otherwise, append the entity to the validated list.
                validated_entities.append(entity)
        # Filter the validated entities to only those in available Gemini entities.
        filtered_entities = [entity for entity in validated_entities if entity in GEMINI_AVAILABLE_ENTITIES]
        # Identify any invalid entities not present in Gemini available entities.
        invalid_entities = [entity for entity in validated_entities if entity not in GEMINI_AVAILABLE_ENTITIES]
        # If there are any invalid entities, log a warning.
        if invalid_entities:
            log_warning(f"[Gemini] Removing invalid entities: {invalid_entities}")
        # Log the final validated list of Gemini entities.
        log_info(f"[Gemini] Validated entity list: {filtered_entities}")
        # Return the filtered, validated entity list.
        return filtered_entities

    except json.JSONDecodeError:
        # Log an error if JSON parsing fails.
        log_error("[Gemini] Invalid JSON format in requested_entities")
        # Raise an HTTPException to indicate the malformed JSON.
        raise HTTPException(status_code=400, detail="Invalid JSON format in gemini requested_entities")


def validate_presidio_requested_entities(requested_entities: Optional[str]) -> List[str]:
    """
    Validate and parse the requested entities for the Presidio engine.

    This function parses a JSON string and expands the "ALL_PRESIDIO" shorthand,
    then filters the list for valid Presidio entities.

    Args:
        requested_entities (Optional[str]): JSON string of requested Presidio entities.

    Returns:
        List[str]: Validated list of Presidio entities.
    """
    # Check if requested_entities is empty or None.
    if not requested_entities:
        # Log a warning that no Presidio entities were provided.
        log_warning("[Presidio] No specific entities requested, using defaults")
        # Return an empty list indicating defaults.
        return []
    try:
        # Parse the JSON string into a list.
        entity_list = json.loads(requested_entities)
        # Initialize an empty list for validated Presidio entities.
        validated_entities = []
        # Iterate over each entity in the parsed list.
        for entity in entity_list:
            # Check if the entity equals the shorthand "ALL_PRESIDIO".
            if entity == "ALL_PRESIDIO":
                # Extend validated_entities with all available Presidio entities.
                validated_entities.extend(PRESIDIO_AVAILABLE_ENTITIES)
            else:
                # Otherwise, append the entity as-is.
                validated_entities.append(entity)
        # Filter the validated entities to include only valid Presidio entities.
        filtered_entities = [entity for entity in validated_entities if entity in PRESIDIO_AVAILABLE_ENTITIES]
        # Identify any entities that are invalid.
        invalid_entities = [entity for entity in validated_entities if entity not in PRESIDIO_AVAILABLE_ENTITIES]
        # Log a warning if any invalid entities are found.
        if invalid_entities:
            log_warning(f"[Presidio] Removing invalid entities: {invalid_entities}")
        # Log the validated Presidio entity list.
        log_info(f"[Presidio] Validated entity list: {filtered_entities}")
        # Return the filtered validated list.
        return filtered_entities

    except json.JSONDecodeError:
        # Log an error message for invalid JSON.
        log_error("[Presidio] Invalid JSON format in requested_entities")
        # Raise an HTTPException indicating invalid JSON.
        raise HTTPException(status_code=400, detail="Invalid JSON format in presidio requested_entities")


def validate_gliner_requested_entities(requested_entities: Optional[str]) -> List[str]:
    """
    Validate and parse the requested entities for the GLiNER engine.

    This function parses a JSON string and expands the "ALL_GLINER" shorthand,
    then filters the resulting list for valid GLiNER entities.

    Args:
        requested_entities (Optional[str]): JSON string of requested GLiNER entities.

    Returns:
        List[str]: Validated list of GLiNER entities.
    """
    # Check if requested_entities is empty.
    if not requested_entities:
        # Log a warning that no GLiNER entities were provided.
        log_warning("[Gliner] No specific entities requested, using defaults")
        # Return an empty list as default.
        return []
    try:
        # Parse the JSON string into a list.
        entity_list = json.loads(requested_entities)
        # Initialize an empty list for validated GLiNER entities.
        validated_entities = []
        # Iterate through each entity in the list.
        for entity in entity_list:
            # Check if the entity is the shorthand "ALL_GLINER".
            if entity == "ALL_GLINER":
                # Extend validated_entities with all available GLiNER entities.
                validated_entities.extend(GLINER_AVAILABLE_ENTITIES)
            else:
                # Otherwise, append the entity to the validated list.
                validated_entities.append(entity)
        # Filter the validated entities to include only GLiNER valid entities.
        filtered_entities = [entity for entity in validated_entities if entity in GLINER_AVAILABLE_ENTITIES]
        # Identify any entities that are invalid.
        invalid_entities = [entity for entity in validated_entities if entity not in GLINER_AVAILABLE_ENTITIES]
        # Log a warning if there are any invalid entities.
        if invalid_entities:
            log_warning(f"[Gliner] Removing invalid entities: {invalid_entities}")
        # Log the final validated GLiNER entity list.
        log_info(f"[Gliner] Validated entity list: {filtered_entities}")
        # Return the filtered validated list.
        return filtered_entities

    except json.JSONDecodeError:
        # Log an error for malformed JSON.
        log_error("[Gliner] Invalid JSON format in requested_entities")
        # Raise an HTTPException indicating the JSON format error.
        raise HTTPException(status_code=400, detail="Invalid JSON format in gliner requested_entities")


def validate_hideme_requested_entities(requested_entities: Optional[str]) -> List[str]:
    """
    Validate and parse the requested entities for the HIDEME engine.

    This function parses a JSON string and expands the "ALL_HIDEME" shorthand,
    then filters the list for valid HIDEME entity types.

    Args:
        requested_entities (Optional[str]): JSON string of requested HIDEME entities.

    Returns:
        List[str]: Validated list of HIDEME entities.
    """
    # Check if requested_entities is empty.
    if not requested_entities:
        # Log a warning that no HIDEME entities were provided.
        log_warning("[Hideme] No specific entities requested, using defaults")
        # Return an empty list as default.
        return []
    try:
        # Parse the JSON string to obtain a list.
        entity_list = json.loads(requested_entities)
        # Initialize an empty list to hold validated HIDEME entities.
        validated_entities = []
        # Iterate through each entity in the parsed list.
        for entity in entity_list:
            # Check if the entity equals the shorthand "ALL_HIDEME".
            if entity == "ALL_HIDEME":
                # Extend validated_entities with all available HIDEME entities.
                validated_entities.extend(HIDEME_AVAILABLE_ENTITIES)
            else:
                # Otherwise, append the entity as-is.
                validated_entities.append(entity)
        # Filter out entities not present in HIDEME available entities.
        filtered_entities = [entity for entity in validated_entities if entity in HIDEME_AVAILABLE_ENTITIES]
        # Determine any invalid HIDEME entities.
        invalid_entities = [entity for entity in validated_entities if entity not in HIDEME_AVAILABLE_ENTITIES]
        # Log a warning if any invalid entities are found.
        if invalid_entities:
            log_warning(f"[Hideme] Removing invalid entities: {invalid_entities}")
        # Log the final validated list for HIDEME.
        log_info(f"[Hideme] Validated entity list: {filtered_entities}")
        # Return the filtered validated list.
        return filtered_entities

    except json.JSONDecodeError:
        # Log an error if JSON parsing fails.
        log_error("[Hideme] Invalid JSON format in requested_entities")
        # Raise an HTTPException to indicate invalid JSON format.
        raise HTTPException(status_code=400, detail="Invalid JSON format in hideme requested_entities")
