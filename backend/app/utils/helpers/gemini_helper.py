"""
Helper functions for interacting with the Google Gemini API.
"""
import asyncio
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
    GEMINI_AVAILABLE_ENTITIES,
    SYSTEM_INSTRUCTION
)
from backend.app.configs.config_singleton import get_config
from backend.app.utils.logging.logger import default_logger as logger

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
        self.model_name = get_config("gemini_model_name") or "gemini-2.0-flash"

        logger.info(f"✅ GeminiHelper initialized with model '{self.model_name}'")

        # Initialize cache for storing responses for similar text content
        self.cache = {}

    @staticmethod
    def _cache_key(text: str, requested_entities: Optional[List[str]] = None) -> str:
        """
        Generate a unique cache key based on the input text and requested entities.

        This method creates a unique MD5 hash to identify requests with the same input text
        and entity filters. It helps avoid redundant API calls by retrieving results from
        the cache when the same request is made again.

        Args:
            text (str): The input text for which the cache key is generated.
            requested_entities (Optional[List[str]]): A list of entity types that should be
                                                     considered in the request. If None,
                                                     all available entities are included.

        Returns:
            str: A unique MD5 hash string that serves as a cache key.
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
            requested_entities = list(GEMINI_AVAILABLE_ENTITIES.values())

        entities_str = "\n".join(f"- **{entity}**" for entity in requested_entities)

        return f"{GEMINI_PROMPT_HEADER}{entities_str}\n\n### **Text to Analyze:**\n{text}\n{GEMINI_PROMPT_FOOTER}"

    async def send_request(
            self,
            text: str,
            requested_entities: Optional[List[str]] = None,
            max_retries: int = 3,
            raw_prompt: bool = False,
            system_instruction_override: Optional[str] = None
    ) -> Optional[str]:
        """
        Send a request to the Gemini API with retry logic and exponential backoff.

        Args:
            text: Text to analyze.
            requested_entities: List of entity types to detect.
            max_retries: Maximum number of retry attempts.
            raw_prompt: If True, use the provided text as the prompt without modification.
            system_instruction_override: If provided, use this system instruction instead of the default.

        Returns:
            Raw response text, an empty string for restricted responses, or None if request failed.
        """
        sys_inst = system_instruction_override or SYSTEM_INSTRUCTION
        prompt = text if raw_prompt else self.create_prompt(text, requested_entities)
        backoff = 1  # initial backoff in seconds

        for attempt in range(max_retries):
            try:
                model = genai.GenerativeModel(self.model_name, system_instruction=sys_inst)
                response = await asyncio.to_thread(model.generate_content, prompt)

                # Invert the logic for checking an empty response to reduce nesting
                if not response or not response.text.strip():
                    logger.error("❌ Empty response from Gemini API")
                    return ""

                logger.info("✅ Successfully received response from Gemini API")
                return response.text.strip("`").strip()

            except Exception as e:
                # Handle all exceptions here, then branch if needed
                if isinstance(e, ConnectionError):
                    logger.error(f"❌ Network Error communicating with Gemini API: {e}")
                elif "finish_reason" in str(e) and "is 4" in str(e):
                    logger.warning("⚠️ Gemini refused content due to copyright filtering. Returning empty result.")
                    return None

            if attempt < max_retries - 1:
                logger.info(f"Retrying after {backoff} seconds (attempt {attempt + 2} of {max_retries})...")
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
    def _try_json_parse(text: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Attempt to parse a JSON string safely.

        Args:
            text: Text to parse as JSON

        Returns:
            Parsed JSON object or None if parsing failed
        """
        if not isinstance(text, str):  # Ensure input is a valid string
            return None

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _process_json_character(char: str, index: int, stack: List[str], start: Optional[int]) -> Optional[int]:
        """
        Process a single character in text to identify JSON structures.

        Args:
            char: The character being processed
            index: The index of the character in the text
            stack: Stack tracking opening and closing brackets
            start: Start index of a JSON block

        Returns:
            Updated start index or None if unchanged
        """
        if char == '{':
            if start is None:
                start = index  # Mark the start of a JSON candidate
            stack.append('{')
        elif char == '}' and stack:
            stack.pop()
            if not stack:
                return start  # Return start index when JSON block closes

        return start

    @staticmethod
    def _find_potential_json_candidates(text: Optional[str]) -> List[str]:
        """
        Identify potential JSON substrings from text without validation.

        Args:
            text: Text that might contain JSON

        Returns:
            List of potential JSON substrings
        """
        if not text:  # Handle None or empty input
            return []

        json_candidates = []
        stack = []
        start = None

        # Loop through text to find JSON-like structures
        for i, char in enumerate(text):
            start = GeminiHelper._process_json_character(char, i, stack, start)

            # If a valid JSON candidate is found
            if start is not None and not stack:
                candidate = text[start:i + 1]

                # Ensure `{}` is detected correctly
                if candidate == "{}" or len(candidate) > 2:
                    json_candidates.append(candidate)

                start = None  # Reset for next JSON

        return json_candidates

    @staticmethod
    def _extract_json_candidates(text: Optional[str]) -> List[str]:
        """
        Extract only valid JSON substrings from text.

        Args:
            text: Text that might contain JSON

        Returns:
            List of valid JSON strings
        """
        potential_jsons = GeminiHelper._find_potential_json_candidates(text)

        # Allow `{}` as a valid JSON
        return [candidate for candidate in potential_jsons if
                candidate == "{}" or GeminiHelper._try_json_parse(candidate)]

    async def process_text(self, text: str, requested_entities: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
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

        response = await self.send_request(text, requested_entities)
        result = self.parse_response(response) if response else None

        # Cache the result if successful
        if result is not None:
            self.cache[key] = result

        return result
