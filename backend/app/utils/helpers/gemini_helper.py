"""
Helper functions for interacting with the Google Gemini API.
"""
import os
import json
import time
import hashlib
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
    - Sends requests to the Gemini API with retry logic and exponential backoff
    - Caches responses to avoid redundant API calls for similar text content
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
        self.model_name = get_config("gemini_model_name") or "gemini-1.5-flash"

        logger.info(f"✅ GeminiHelper initialized with model '{self.model_name}'")

        # Initialize cache for storing responses for similar text content
        self.cache = {}

    def _cache_key(self, text: str, requested_entities: Optional[List[str]] = None) -> str:
        """
        Generate a cache key based on text and requested entities.
        """
        key_data = text
        if requested_entities:
            key_data += '|' + ','.join(sorted(requested_entities))
        return hashlib.md5(key_data.encode('utf-8')).hexdigest()

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

    def send_request(self, text: str, requested_entities: Optional[List[str]] = None, max_retries: int = 3) -> Optional[str]:
        """
        Send a request to the Gemini API with retry logic and exponential backoff.

        Args:
            text: Text to analyze
            requested_entities: List of entity types to detect

        Returns:
            Raw response text or None if request failed
        """
        prompt = self.create_prompt(text, requested_entities)
        attempt = 0
        backoff = 1  # initial backoff in seconds

        while attempt < max_retries:
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
            except Exception as e:
                logger.error(f"❌ Unexpected error communicating with Gemini API: {e}")
            attempt += 1
            if attempt < max_retries:
                logger.info(f"Retrying after {backoff} seconds (attempt {attempt + 1} of {max_retries})...")
                time.sleep(backoff)
                backoff *= 2
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

    def process_text(self, text: str, requested_entities: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """
        Process text through Gemini API and return parsed results.
        Uses caching to avoid redundant API calls for similar text content.

        Args:
            text: Text to analyze
            requested_entities: List of entity types to detect

        Returns:
            Parsed JSON response or None if processing failed
        """
        key = self._cache_key(text, requested_entities)
        if key in self.cache:
            logger.info("✅ Using cached response for Gemini API request")
            return self.cache[key]

        response = self.send_request(text, requested_entities)
        result = self.parse_response(response) if response else None

        # Cache the result if successful
        if result is not None:
            self.cache[key] = result

        return result
