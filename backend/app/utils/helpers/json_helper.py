import json
from typing import List

from presidio_analyzer import RecognizerResult


def presidiotojsonconverter(detected_entities):
    """
    Custom converter for non-serializable objects.
    If the object is a RecognizerResult, convert it to a dict.
    """
    # Format entity data
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
    Convert the provided data to a JSON string.

    :param data: The data to convert (typically a dict or list).
    :param indent: Indentation level for pretty-printing (default is 2).
    :return: A JSON-formatted string.
    :raises ValueError: If conversion fails.
    """
    try:
        json_str = json.dumps(data, indent=indent, ensure_ascii=False, default=presidiotojsonconverter)
        return json_str
    except Exception as e:
        raise ValueError(f"Error converting data to JSON: {e}")


# Helper method to print results nicely


def print_analyzer_results(results: List[RecognizerResult], text: str):
    """Print the results in a human-readable way."""

    for i, result in enumerate(results):
        print(f"Result {i}:")
        print(f" {result}, text: {text[result.start:result.end]}")

        if result.analysis_explanation is not None:
            print(f" {result.analysis_explanation.textual_explanation}")
