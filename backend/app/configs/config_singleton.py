"""
Configuration singleton for document processing.

This module provides direct access to configuration values
without requiring service imports.
"""

import os
from typing import Any

from dotenv import load_dotenv

# Load environment variables
load_dotenv(verbose=True)

# Global configuration dictionary
_config = {}


def _load_config_from_env() -> None:
    """Load configuration from environment variables."""

    # API keys
    _config["gemini_api_key"] = os.getenv("GEMINI_API_KEY", "")

    # Entity detection configuration
    _config["default_language"] = os.getenv(
        "DEFAULT_LANGUAGE", "nb"
    )  # Changed default to Norwegian
    _config["spacy_model"] = os.getenv(
        "SPACY_MODEL", "nb_core_news_lg"
    )  # Norwegian model
    _config["hf_model_path"] = os.getenv("LOCAL_HF_MODEL_PATH", "")

    # Document processing configuration
    _config["default_detection_engine"] = os.getenv(
        "DEFAULT_DETECTION_ENGINE", "PRESIDIO"
    )
    _config["redaction_color"] = _parse_color(os.getenv("REDACTION_COLOR", "0,0,0"))

    # New configuration for entity batch size
    _config["entity_batch_size"] = int(os.getenv("ENTITY_BATCH_SIZE", "10"))

    # API configuration
    _config["api_port"] = int(os.getenv("API_PORT", "8000"))
    _config["api_host"] = os.getenv("API_HOST", "0.0.0.0")
    _config["debug"] = os.getenv("DEBUG", "false").lower() == "true"

    # Paths configuration
    _config["output_dir"] = os.getenv("OUTPUT_DIR", "output")
    _config["temp_dir"] = os.getenv("TEMP_DIR", "temp")


def _parse_color(color_str: str) -> tuple:
    """Parse color string into RGB tuple."""
    try:
        r, g, b = map(int, color_str.split(","))
        return r, g, b
    except ValueError:
        return 0, 0, 0  # Default to black


def get_config(key: str, default: Any = None) -> Any:
    """
    Get configuration value by key.

    Args:
        key: Configuration key
        default: Default value if key not found

    Returns:
        Configuration value
    """
    # Make sure config is loaded
    if not _config:
        _load_config_from_env()
    return _config.get(key, default)


def set_config(key: str, value: Any) -> None:
    """
    Set configuration value.

    Args:
        key: Configuration key
        value: Configuration value
    """
    _config[key] = value


# Initialize configuration
_load_config_from_env()
