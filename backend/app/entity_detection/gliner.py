"""
GLiNER Entity Detector Implementation

This module implements the GLiNER-specific entity detector by extending the GenericEntityDetector base class.
It sets engine-specific configuration attributes such as ENGINE_NAME, MODEL_NAME, DEFAULT_ENTITIES, MODEL_DIR_PATH,
CACHE_NAMESPACE, and CONFIG_FILE_NAME. It also customizes the validate_requested_entities method to use GLiNER's
dedicated JSON validation helper.
"""

from typing import List

from backend.app.entity_detection.glinerbase import GenericEntityDetector
from backend.app.utils.constant.constant import GLINER_CONFIG_FILENAME
from backend.app.utils.helpers.json_helper import validate_gliner_requested_entities
from backend.app.configs.gliner_config import (
    GLINER_MODEL_PATH,
    GLINER_MODEL_NAME,
    GLINER_AVAILABLE_ENTITIES,
)


class GlinerEntityDetector(GenericEntityDetector):
    """
    GlinerEntityDetector is the GLiNER-specific implementation of the GenericEntityDetector.

    It inherits common functionalities from the base class and sets the following engine-specific
    configuration attributes:
        ENGINE_NAME:        "GLiNER"
        MODEL_NAME:         GLINER_MODEL_NAME (the name or path of the GLiNER model)
        DEFAULT_ENTITIES:   GLINER_AVAILABLE_ENTITIES (the list of default entities available in GLiNER)
        MODEL_DIR_PATH:     GLINER_MODEL_PATH (local directory path to store the GLiNER model files)
        CACHE_NAMESPACE:    "gliner" (namespace string used for caching GLiNER results)
        CONFIG_FILE_NAME:   GLINER_CONFIG_FILENAME (name of the engine-specific configuration file)
    """

    # Set the engine name for GLiNER.
    ENGINE_NAME = "GLiNER"
    # Set the GLiNER model name or path from configuration.
    MODEL_NAME = GLINER_MODEL_NAME
    # Define the default entities available for GLiNER.
    DEFAULT_ENTITIES = GLINER_AVAILABLE_ENTITIES
    # Specify the local model directory path for GLiNER.
    MODEL_DIR_PATH = GLINER_MODEL_PATH
    # Set the cache namespace to "gliner".
    CACHE_NAMESPACE = "gliner"
    # Define the configuration file name used specifically for GLiNER.
    CONFIG_FILE_NAME = GLINER_CONFIG_FILENAME

    def validate_requested_entities(self, requested_entities_json: str) -> List[str]:
        """
        Validate requested entities specifically for GLiNER using its dedicated validation function.

        Args:
            requested_entities_json: A JSON string representing the requested entity types.

        Returns:
            A list of validated GLiNER entity type strings.
        """
        # Call the GLiNER-specific validation helper and return the result.
        return validate_gliner_requested_entities(requested_entities_json)
