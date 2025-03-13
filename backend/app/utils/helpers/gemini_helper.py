"""
Helper functions for interacting with the Google Gemini API.
"""
import os
import json
from typing import Dict, Any, List, Optional

import google.generativeai as genai
from dotenv import load_dotenv

from backend.app.configs.gemini_config import (
    GEMINI_PROMPT_HEADER,
    GEMINI_PROMPT_FOOTER,
    AVAILABLE_ENTITIES,
    SYSTEM_INSTRUCTION
)
from backend.app.configs.config_singleton import get_config
from backend.app.utils.logger import default_logger as logger

# Load environment variables
load_dotenv(verbose=True)


class GeminiHelper:
    """
    Helper class to interact with the Google Gemini API.

    This class:
    - Builds prompts based on a template
    - Sends requests to the Gemini API
    - Parses JSON responses
    """

    def __init__(self):
        """Initialize the Gemini helper with API key and model configuration."""
        # Get API key from configuration
        self.api_key = get_config("gemini_api_key") or os.getenv("GEMINI_API_KEY")

        if not self.api_key:
            logger.error("❌ Gemini API Key is missing! Set GEMINI_API_KEY in .env")
            raise ValueError("GEMINI_API_KEY is not set in the environment")

        # Configure Gemini API
        genai.configure(api_key=self.api_key)

        # Set model name from configuration or use default
        self.model_name = get_config("gemini_model_name") or "gemini-2.0-flash"

        logger.info(f"✅ GeminiHelper initialized with model '{self.model_name}'")

    @staticmethod
    def create_prompt(text: str, requested_entities: Optional[List[str]] = None) -> str:
        """
        Construct a prompt for Gemini API dynamically.

        Args:
            text: Text to analyze
            requested_entities: List of entity types to detect

        Returns:
            Formatted prompt string
        """
        if requested_entities is None:
            requested_entities = list(AVAILABLE_ENTITIES.values())

        entities_str = "\n".join(f"- **{entity}**" for entity in requested_entities)

        return f"{GEMINI_PROMPT_HEADER}{entities_str}\n\n### **Text to Analyze:**\n{text}\n{GEMINI_PROMPT_FOOTER}"

    def send_request(self, text: str, requested_entities: Optional[List[str]] = None) -> Optional[str]:
        """
        Send a request to the Gemini API.

        Args:
            text: Text to analyze
            requested_entities: List of entity types to detect

        Returns:
            Raw response text or None if request failed
        """
        prompt = self.create_prompt(text, requested_entities)

        try:
            model = genai.GenerativeModel(
                self.model_name,
                system_instruction=SYSTEM_INSTRUCTION
            )

            response = model.generate_content(prompt)

            if response and response.text.strip():
                logger.info("✅ Successfully received response from Gemini API")
                return response.text.strip("`").strip()

            logger.error("❌ Empty response from Gemini API")
            return None

        except ConnectionError as e:
            logger.error(f"❌ Network Error communicating with Gemini API: {e}")
            return None

        except Exception as e:
            logger.error(f"❌ Unexpected error communicating with Gemini API: {e}")
            return None

    def parse_response(self, response: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Parse the raw response text from Gemini API into a JSON object.

        Args:
            response: Raw response text

        Returns:
            Parsed JSON object or None if parsing failed
        """
        if not response:
            logger.error("❌ Error: Received empty response")
            return None

        # Clean up response
        cleaned_response = response.strip("`").strip()
        if cleaned_response.lower().startswith("json"):
            cleaned_response = cleaned_response[4:].strip()

        # Try to parse JSON
        parsed_json = self._try_json_parse(cleaned_response)
        if parsed_json:
            return parsed_json

        # Try to extract JSON from text
        json_candidates = self._extract_json_candidates(cleaned_response)
        for candidate in json_candidates:
            parsed_json = self._try_json_parse(candidate)
            if parsed_json:
                return parsed_json

        logger.error("❌ Error: No valid JSON object could be extracted from the response")
        return None

    @staticmethod
    def _try_json_parse(text: str) -> Optional[Dict[str, Any]]:
        """
        Attempt to parse a JSON string safely.

        Args:
            text: Text to parse as JSON

        Returns:
            Parsed JSON object or None if parsing failed
        """
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _extract_json_candidates(text: str) -> List[str]:
        """
        Extract possible JSON substrings from text.

        Args:
            text: Text that might contain JSON

        Returns:
            List of potential JSON strings
        """
        json_candidates = []
        stack = []
        start = None

        # Loop through each character
        for i, char in enumerate(text):
            if char == '{':
                if start is None:
                    start = i
                stack.append('{')
            elif char == '}' and stack:
                stack.pop()
                if not stack and start is not None:
                    json_candidates.append(text[start:i + 1])
                    start = None

        return json_candidates

    def process_text(
        self,
        text: str,
        requested_entities: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Process text through Gemini API and return parsed results.

        Args:
            text: Text to analyze
            requested_entities: List of entity types to detect

        Returns:
            Parsed JSON response or None if processing failed
        """
        response = self.send_request(text, requested_entities)
        return self.parse_response(response) if response else None