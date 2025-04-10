"""
JSON handling utilities for document processing.
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
    if threshold is not None and (threshold < 0.00 or threshold > 1.00):
        raise HTTPException(
            status_code=400,
            detail="Threshold must be between 0.00 and 1.00."
        )
    return threshold


def check_all_option(entity_list):
    new_list = []
    for entity in entity_list:
        if entity == "ALL_PRESIDIO":
            new_list.extend(PRESIDIO_AVAILABLE_ENTITIES)
        elif entity == "ALL_GEMINI":
            new_list.extend(list(GEMINI_AVAILABLE_ENTITIES.keys()))
        elif entity == "ALL_GLINER":
            new_list.extend(GLINER_AVAILABLE_ENTITIES)
        else:
            new_list.append(entity)
    return new_list


def validate_all_engines_requested_entities(
        requested_entities: Optional[str],
        labels: Optional[List[str]] = None
) -> List[str]:
    """
    Validate and parse requested entities.

    Args:
        requested_entities: JSON string of entity types to detect
        labels: Optional list of valid entity labels for validation

    Returns:
        List of validated entity types

    Raises:
        HTTPException: If validation fails
    """
    if not requested_entities:
        log_warning("[OK]No specific entities requested, using defaults")
        return list(GEMINI_AVAILABLE_ENTITIES.keys()) + PRESIDIO_AVAILABLE_ENTITIES + GLINER_AVAILABLE_ENTITIES

    try:
        entity_list = json.loads(requested_entities)
        entity_list = check_all_option(entity_list)

        # If specific labels are provided, validate against them
        if labels:
            available_entities = labels
            for entity in entity_list:
                if entity not in available_entities:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid entity type: {entity}. Available entities: {available_entities}"
                    )
        # Otherwise validate against standard entity lists
        else:
            available_entities = list(
                GEMINI_AVAILABLE_ENTITIES.keys()) + PRESIDIO_AVAILABLE_ENTITIES + GLINER_AVAILABLE_ENTITIES
            for entity in entity_list:
                if entity not in available_entities:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid entity type: {entity}. Available entities: {available_entities}"
                    )

        log_info(f"[OK] Validated entity list: {entity_list}")
        return entity_list

    except json.JSONDecodeError:
        log_error("[OK]Invalid JSON format in requested_entities")
        raise HTTPException(status_code=400, detail="Invalid JSON format in ALL_requested_entities")


def validate_gemini_requested_entities(requested_entities: Optional[str]) -> List[str]:
    """
    Validate and parse requested entities for the Gemini engine.

    Args:
        requested_entities: JSON string of entity types to detect

    Returns:
        List of validated entity types for Gemini; invalid entities are removed.

    Raises:
        HTTPException: If JSON parsing fails
    """
    if not requested_entities:
        log_warning("[Gemini] No specific entities requested, using defaults")
        return []

    try:
        entity_list = json.loads(requested_entities)
        validated_entities = []
        for entity in entity_list:
            if entity == "ALL_GEMINI":
                validated_entities.extend(list(GEMINI_AVAILABLE_ENTITIES.keys()))
            else:
                validated_entities.append(entity)

        # Filter out only Gemini-valid entities
        filtered_entities = [entity for entity in validated_entities if entity in GEMINI_AVAILABLE_ENTITIES]
        invalid_entities = [entity for entity in validated_entities if entity not in GEMINI_AVAILABLE_ENTITIES]
        if invalid_entities:
            log_warning(f"[Gemini] Removing invalid entities: {invalid_entities}")
        log_info(f"[Gemini] Validated entity list: {filtered_entities}")
        return filtered_entities

    except json.JSONDecodeError:
        log_error("[Gemini] Invalid JSON format in requested_entities")
        raise HTTPException(status_code=400, detail="Invalid JSON format in gemini requested_entities")


def validate_presidio_requested_entities(requested_entities: Optional[str]) -> List[str]:
    """
    Validate and parse requested entities for the Presidio engine.

    Args:
        requested_entities: JSON string of entity types to detect

    Returns:
        List of validated entity types for Presidio; invalid entities are removed.

    Raises:
        HTTPException: If JSON parsing fails
    """
    if not requested_entities:
        log_warning("[Presidio] No specific entities requested, using defaults")
        return []

    try:
        entity_list = json.loads(requested_entities)
        validated_entities = []
        for entity in entity_list:
            if entity == "ALL_PRESIDIO":
                validated_entities.extend(PRESIDIO_AVAILABLE_ENTITIES)
            else:
                validated_entities.append(entity)

        # Filter out only Presidio-valid entities
        filtered_entities = [entity for entity in validated_entities if entity in PRESIDIO_AVAILABLE_ENTITIES]
        invalid_entities = [entity for entity in validated_entities if entity not in PRESIDIO_AVAILABLE_ENTITIES]
        if invalid_entities:
            log_warning(f"[Presidio] Removing invalid entities: {invalid_entities}")
        log_info(f"[Presidio] Validated entity list: {filtered_entities}")
        return filtered_entities

    except json.JSONDecodeError:
        log_error("[Presidio] Invalid JSON format in requested_entities")
        raise HTTPException(status_code=400, detail="Invalid JSON format in presidio requested_entities")


def validate_gliner_requested_entities(requested_entities: Optional[str]) -> List[str]:
    """
    Validate and parse requested entities for the Gliner engine.

    Args:
        requested_entities: JSON string of entity types to detect

    Returns:
        List of validated entity types for Gliner; invalid entities are removed.

    Raises:
        HTTPException: If JSON parsing fails
    """
    if not requested_entities:
        log_warning("[Gliner] No specific entities requested, using defaults")
        return []

    try:
        entity_list = json.loads(requested_entities)
        validated_entities = []
        for entity in entity_list:
            if entity == "ALL_GLINER":
                validated_entities.extend(GLINER_AVAILABLE_ENTITIES)
            else:
                validated_entities.append(entity)

        # Filter out only Gliner-valid entities
        filtered_entities = [entity for entity in validated_entities if entity in GLINER_AVAILABLE_ENTITIES]
        invalid_entities = [entity for entity in validated_entities if entity not in GLINER_AVAILABLE_ENTITIES]
        if invalid_entities:
            log_warning(f"[Gliner] Removing invalid entities: {invalid_entities}")
        log_info(f"[Gliner] Validated entity list: {filtered_entities}")
        return filtered_entities

    except json.JSONDecodeError:
        log_error("[Gliner] Invalid JSON format in requested_entities")
        raise HTTPException(status_code=400, detail="Invalid JSON format in gliner requested_entities")


def convert_to_json(data: Any, indent: int = 2) -> str:
    """
    Convert data to a JSON string with custom converter for non-serializable objects.

    Args:
        data: Data to convert
        indent: Indentation level

    Returns:
        JSON string

    Raises:
        ValueError: If conversion fails
    """
    try:
        def custom_converter(obj):
            """Custom converter for non-serializable objects."""
            if hasattr(obj, '__dict__'):
                return obj.__dict__
            elif hasattr(obj, 'to_dict'):
                return obj.to_dict()
            raise TypeError(f"Type not serializable: {type(obj)}")

        json_str = json.dumps(
            data,
            indent=indent,
            ensure_ascii=False,
            default=custom_converter
        )
        return json_str

    except Exception as e:
        log_error(f"[OK]Error converting data to JSON: {e}")
        raise ValueError(f"Error converting data to JSON: {e}")


def parse_json(json_str: str) -> Any:
    """
    Parse a JSON string safely.

    Args:
        json_str: JSON string to parse

    Returns:
        Parsed JSON data

    Raises:
        ValueError: If parsing fails
    """
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        log_error(f"[OK]Invalid JSON format: {e}")
        raise ValueError(f"Invalid JSON format: {e}")
