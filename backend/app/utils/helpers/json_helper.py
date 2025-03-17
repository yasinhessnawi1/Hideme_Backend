"""
JSON handling utilities for document processing.
"""
import json
from typing import List, Optional, Any, Union

from fastapi import HTTPException

from backend.app.configs.gemini_config import AVAILABLE_ENTITIES
from backend.app.configs.gliner_config import GLINER_ENTITIES
from backend.app.configs.presidio_config import REQUESTED_ENTITIES
from backend.app.utils.logger import log_info, log_warning, log_error


def validate_requested_entities(
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
        log_warning(f"[OK]No specific entities requested, using defaults")
        return []

    try:
        entity_list = json.loads(requested_entities)

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
            available_entities = list(AVAILABLE_ENTITIES.keys()) + REQUESTED_ENTITIES + GLINER_ENTITIES
            for entity in entity_list:
                if entity not in available_entities:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid entity type: {entity}. Available entities: {available_entities}"
                    )

        log_info(f"[OK] Validated entity list: {entity_list}")
        return entity_list

    except json.JSONDecodeError:
        log_error(f"[OK]Invalid JSON format in requested_entities")
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