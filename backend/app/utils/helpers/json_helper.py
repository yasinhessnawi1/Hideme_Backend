import json
from typing import List, Optional

from fastapi import HTTPException
from presidio_analyzer import RecognizerResult

from backend.app.configs.gemini_config import AVAILABLE_ENTITIES
from backend.app.configs.presidio_config import REQUESTED_ENTITIES
from backend.app.utils.logger import default_logger as logging


def presidiotojsonconverter(detected_entities):
    """
    Custom converter for non-serializable objects.
    If the object is a RecognizerResult, convert it to a dict.
    """
    # Format entity fisk_data
    return [
        {
            "entity_type": e.entity_type,
            "start": e.start,
            "end": e.end,
            "score": float(e.score)
        }
        for e in detected_entities if e.score > 0.5
    ]
    # Add more conversions if needed


def convert_to_json(data, indent=2):
    """
    Convert the provided fisk_data to a JSON string.

    :param data: The fisk_data to convert (typically a dict or list).
    :param indent: Indentation level for pretty-printing (default is 2).
    :return: A JSON-formatted string.
    :raises ValueError: If conversion fails.
    """
    try:
        json_str = json.dumps(data, indent=indent, ensure_ascii=False, default=presidiotojsonconverter)
        return json_str
    except Exception as e:
        raise ValueError(f"Error converting fisk_data to JSON: {e}")


# Helper method to print results nicely


def print_analyzer_results(results: List[RecognizerResult], text: str):
    """Print the results in a human-readable way."""

    for i, result in enumerate(results):
        print(f"Result {i}:")
        print(f" {result}, text: {text[result.start:result.end]}")

        if result.analysis_explanation is not None:
            print(f" {result.analysis_explanation.textual_explanation}")


def validate_requested_entities(requested_entities: Optional[str], labels: Optional[List[str]] = None):
    """
    Validates and filters requested entities.

    :param requested_entities: JSON string or Python list containing requested entities.
    :param labels: List of valid labels to compare against.
    :return: List of valid requested entities.
    :raises HTTPException: If none of the requested entities are valid.
    """
    if requested_entities:
        logging.info(f"🔍 Validating requested entities: {requested_entities}")

        # ✅ Ensure `requested_entities` is a Python list (handle JSON string case)
        if isinstance(requested_entities, str):
            try:
                requested_entities = json.loads(requested_entities)  # Convert JSON string to list
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid JSON format in requested_entities")

        if not isinstance(requested_entities, list):
            raise HTTPException(status_code=400, detail="requested_entities must be a list")

        # ✅ Define available entities based on provided labels or default to known entities
        available_entities = labels if labels else list(AVAILABLE_ENTITIES.keys()) + REQUESTED_ENTITIES

        # ✅ Filter out only valid requested entities
        valid_entities = [entity for entity in requested_entities if entity in available_entities]

        if not valid_entities:
            raise HTTPException(status_code=400, detail="No valid entities found in the request.")

        return valid_entities  # ✅ Return filtered valid entities