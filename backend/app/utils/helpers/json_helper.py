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


# Utility functions for entity validation

def check_all_option(entity_list: List[str], entity_type: str) -> List[str]:
    """
    Expand ALL options for the specified entity type.

    Args:
        entity_list: List of entities that may contain ALL options
        entity_type: Type of entities ('presidio', 'gliner', or 'gemini')

    Returns:
        Expanded list with ALL options replaced by their respective entities
    """
    new_list = []
    for entity in entity_list:
        if entity == "ALL_PRESIDIO" and entity_type == "presidio":
            new_list.extend(PRESIDIO_AVAILABLE_ENTITIES)
        elif entity == "ALL_GEMINI" and entity_type == "gemini":
            new_list.extend(list(GEMINI_AVAILABLE_ENTITIES.keys()))
        elif entity == "ALL_GLINER" and entity_type == "gliner":
            new_list.extend(GLINER_AVAILABLE_ENTITIES)
        else:
            new_list.append(entity)
    return new_list


def validate_requested_entities(
        requested_entities: Optional[str]
) -> List[List[str]]:
    """
    Validate and parse requested entities for all detector types.

    Args:
        requested_entities: JSON string of entity types to detect
                           (combined for all detectors)

    Returns:
        List of three lists: [presidio_entities, gliner_entities, gemini_entities]

    Raises:
        HTTPException: If validation fails
    """
    if not requested_entities or len(requested_entities) == 0:
        log_warning("[OK] No specific entities requested, using defaults")
        return [[], [], []]

    try:
        entity_list = json.loads(requested_entities)

        # Initialize lists for each detector type
        presidio_entities = []
        gliner_entities = []
        gemini_entities = []

        # Process and validate each entity
        for entity in entity_list:
            if entity in PRESIDIO_AVAILABLE_ENTITIES or entity == "ALL_PRESIDIO":
                presidio_entities.append(entity)
            elif entity in GLINER_AVAILABLE_ENTITIES or entity == "ALL_GLINER":
                gliner_entities.append(entity)
            elif entity in GEMINI_AVAILABLE_ENTITIES.keys() or entity == "ALL_GEMINI":
                gemini_entities.append(entity)
            else:
                available_entities = (
                        list(GEMINI_AVAILABLE_ENTITIES.keys()) +
                        PRESIDIO_AVAILABLE_ENTITIES +
                        GLINER_AVAILABLE_ENTITIES +
                        ["ALL_PRESIDIO", "ALL_GLINER", "ALL_GEMINI"]
                )
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid entity type: {entity}. Available entities: {available_entities}"
                )

        # Expand ALL options for each detector type
        presidio_entities = check_all_option(presidio_entities, "presidio")
        gliner_entities = check_all_option(gliner_entities, "gliner")
        gemini_entities = check_all_option(gemini_entities, "gemini")

        log_info(
            f"[OK] Validated entity lists - Presidio: {presidio_entities}, GLiNER: {gliner_entities}, Gemini: {gemini_entities}")
        return [presidio_entities, gliner_entities, gemini_entities]

    except json.JSONDecodeError:
        log_error("[ERROR] Invalid JSON format in requested_entities")
        raise HTTPException(status_code=400, detail="Invalid JSON format in requested_entities")


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