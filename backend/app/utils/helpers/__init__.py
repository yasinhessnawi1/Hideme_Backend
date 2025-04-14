"""
Helper functions package.

This package contains various helper functions used throughout the
document processing system.
"""
from backend.app.utils.helpers.text_utils import TextUtils, EntityUtils
from backend.app.utils.helpers.json_helper import (
    validate_all_engines_requested_entities,
)
from backend.app.utils.helpers.ml_models_helper import (
    get_spacy_model,
    get_hf_ner_pipeline
)
from backend.app.utils.helpers.gemini_helper import GeminiHelper

# Export classes and functions
__all__ = [
    "TextUtils",
    "EntityUtils",
    "validate_all_engines_requested_entities",
    "get_spacy_model",
    "get_hf_ner_pipeline",
    "GeminiHelper"
]
