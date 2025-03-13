"""
Configuration service for document processing.

This module provides a centralized configuration service that loads
and manages configuration settings for document processing components.
"""
import os
import json
from typing import Dict, Any, List, Optional, Union
from dotenv import load_dotenv

from backend.app.utils.logger import default_logger as logger
from backend.app.configs.config_singleton import get_config, set_config


class ConfigurationService:
    """
    Service for managing configuration settings for document processing.
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the configuration service.

        Args:
            config_path: Path to configuration file (optional)
        """
        # Load configuration from file if provided
        if config_path and os.path.exists(config_path):
            self._load_config_from_file(config_path)

        logger.info("Configuration service initialized")

    def _load_config_from_file(self, config_path: str) -> None:
        """
        Load configuration from a JSON file.

        Args:
            config_path: Path to configuration file
        """
        try:
            with open(config_path, 'r') as f:
                file_config = json.load(f)
                # Update each config value
                for key, value in file_config.items():
                    set_config(key, value)
            logger.info(f"Loaded configuration from file: {config_path}")
        except Exception as e:
            logger.error(f"Error loading configuration from file: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by key.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value
        """
        return get_config(key, default)

    def set(self, key: str, value: Any) -> None:
        """
        Set configuration value.

        Args:
            key: Configuration key
            value: Configuration value
        """
        set_config(key, value)
        logger.debug(f"Set configuration {key} = {value}")

    def get_entity_config(self) -> Dict[str, Any]:
        """
        Get entity detection configuration.

        Returns:
            Dictionary with entity detection configuration
        """
        return {
            'default_language': self.get('default_language'),
            'spacy_model': self.get('spacy_model'),
            'hf_model_path': self.get('hf_model_path'),
            'requested_entities': self.get('requested_entities', [])
        }

    def get_redaction_config(self) -> Dict[str, Any]:
        """
        Get redaction configuration.

        Returns:
            Dictionary with redaction configuration
        """
        return {
            'color': self.get('redaction_color'),
            'add_labels': self.get('add_redaction_labels', True),
            'sanitize_metadata': self.get('sanitize_metadata', True)
        }

    def save_to_file(self, config_path: str) -> None:
        """
        Save current configuration to a file.

        Args:
            config_path: Path to save configuration file
        """
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(config_path), exist_ok=True)

            # Get all configuration values
            config_dict = {}
            # Add known keys (this isn't comprehensive but covers most used values)
            keys = [
                'gemini_api_key', 'default_language', 'spacy_model', 'hf_model_path',
                'default_detection_engine', 'redaction_color', 'api_port', 'api_host',
                'debug', 'output_dir', 'temp_dir'
            ]
            for key in keys:
                config_dict[key] = self.get(key)

            # Write configuration to file
            with open(config_path, 'w') as f:
                json.dump(config_dict, f, indent=2)

            logger.info(f"Saved configuration to file: {config_path}")
        except Exception as e:
            logger.error(f"Error saving configuration to file: {e}")


# Create a singleton instance for global access
config_service = ConfigurationService()