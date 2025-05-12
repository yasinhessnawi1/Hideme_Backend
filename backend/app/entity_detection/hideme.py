"""
HIDEME Entity Detector Implementation

This module implements the HIDEME-specific entity detector by extending the GenericEntityDetector base class.
It sets engine-specific configuration attributes, such as ENGINE_NAME, MODEL_NAME, DEFAULT_ENTITIES, MODEL_DIR_PATH,
CACHE_NAMESPACE, and CONFIG_FILE_NAME. Additionally, it customizes the validate_requested_entities method to
leverage HIDEME's dedicated JSON validation helper for incoming entity requests.
"""

from typing import List

from backend.app.configs.hideme_config import (
    HIDEME_MODEL_NAME,
    HIDEME_AVAILABLE_ENTITIES,
    HIDEME_MODEL_PATH,
)
from backend.app.entity_detection.glinerbase import GenericEntityDetector
from backend.app.utils.constant.constant import GLINER_CONFIG_FILENAME

# Import HIDEME-specific JSON validation helper.
from backend.app.utils.helpers.json_helper import validate_hideme_requested_entities


class HidemeEntityDetector(GenericEntityDetector):
    """
    HidemeEntityDetector is the HIDEME-specific implementation of the GenericEntityDetector.

    It inherits common functionality from GenericEntityDetector and configures these engine-specific attributes:
        ENGINE_NAME:        "HIDEME"
        MODEL_NAME:         HIDEME_MODEL_NAME (the name or path of the HIDEME model)
        DEFAULT_ENTITIES:   HIDEME_AVAILABLE_ENTITIES (the list of default entity types for HIDEME)
        MODEL_DIR_PATH:     HIDEME_MODEL_PATH (the local directory path to store HIDEME model files)
        CACHE_NAMESPACE:    "hideme" (namespace string for caching HIDEME results)
        CONFIG_FILE_NAME:   GLINER_CONFIG_FILENAME (a distinct configuration file for HIDEME)
    """

    # Set the engine name to "HIDEME".
    ENGINE_NAME = "HIDEME"
    # Assign the model name or path using the HIDEME configuration.
    MODEL_NAME = HIDEME_MODEL_NAME
    # Define the default entity types for HIDEME.
    DEFAULT_ENTITIES = HIDEME_AVAILABLE_ENTITIES
    # Specify the local model directory path for the HIDEME model.
    MODEL_DIR_PATH = HIDEME_MODEL_PATH
    # Set the cache namespace to "hideme" for isolating HIDEME-cached results.
    CACHE_NAMESPACE = "hideme"
    # Use the configuration file name; note that a distinct configuration for HIDEME is handled via GLINER_CONFIG_FILENAME.
    CONFIG_FILE_NAME = GLINER_CONFIG_FILENAME

    def validate_requested_entities(self, requested_entities_json: str) -> List[str]:
        """
        Validate requested entities for HIDEME using its dedicated JSON validation function.

        Args:
            requested_entities_json: A JSON string representing the requested entity types.

        Returns:
            A list of validated HIDEME entity type strings.
        """
        # Invoke the HIDEME-specific JSON validation function and return the validated entity list.
        return validate_hideme_requested_entities(requested_entities_json)
