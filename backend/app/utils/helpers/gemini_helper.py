"""
This module provides a helper class for interacting with the Google Gemini API.
It allows building prompts using template components, sending asynchronous requests with retry logic,
caching responses to minimize redundant calls, and parsing JSON responses from the Gemini API.
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
    SYSTEM_INSTRUCTION,
)
from backend.app.configs.config_singleton import get_config
from backend.app.utils.logging.logger import default_logger as logger

# Load environment variables from .env file with verbosity enabled.
load_dotenv(verbose=True)


class GeminiHelper:
    """
    GeminiHelper is a utility class to interact with the Google Gemini API.

    This class is responsible for:
    - Building dynamic prompts using a defined header, footer, and a list of available entities.
    - Sending asynchronous API requests with retry logic and exponential backoff.
    - Caching responses for previously processed texts to reduce redundant API calls.
    - Parsing the API responses and extracting valid JSON results.
    """

    def __init__(self):
        """Initialize the GeminiHelper class with necessary API credentials and caching."""
        # Retrieve the Gemini API key from configuration or environment.
        self.api_key = get_config("gemini_api_key") or os.getenv("GEMINI_API_KEY")
        # Check if the API key is present; if not, log an error and raise an exception.
        if not self.api_key:
            logger.error("❌ Gemini API Key is missing! Set GEMINI_API_KEY in .env")
            raise ValueError("GEMINI_API_KEY is not set in the environment")
        # Configure the Google Generative AI client with the API key.
        genai.configure(api_key=self.api_key)
        # Retrieve the model name from configuration or set the default model.
        self.model_name = get_config("gemini_model_name") or "gemini-2.0-flash"
        # Log the successful initialization and the model name being used.
        logger.info(f"✅ GeminiHelper initialized with model '{self.model_name}'")
        # Initialize an empty cache dictionary to store responses by cache key.
        self.cache = {}

    @staticmethod
    def _cache_key(text: str, requested_entities: Optional[List[str]] = None) -> str:
        """
        Generate a unique cache key based on the input text and requested entities.

        This method creates a unique MD5 hash to identify requests with the same text and entities,
        which is used to store and retrieve responses from the cache.

        Args:
            text (str): The input text for which the cache key is generated.
            requested_entities (Optional[List[str]]): A list of entity types considered in the request.

        Returns:
            str: A unique MD5 hash string serving as the cache key.
        """
        # Initialize the key data with the input text.
        key_data = text
        # If specific requested entities are provided, append their sorted, comma-separated string.
        if requested_entities:
            key_data += "|" + ",".join(sorted(requested_entities))
        # Generate the MD5 hash of the key data and return it as a hexadecimal string.
        return hashlib.md5(key_data.encode("utf-8")).hexdigest()

    @staticmethod
    def create_prompt(text: str, requested_entities: Optional[List[str]] = None) -> str:
        """
        Construct a prompt for the Gemini API dynamically.

        The prompt is built by including a header, the list of requested entities,
        the text to analyze, and a footer.

        Args:
            text (str): The text to analyze.
            requested_entities (Optional[List[str]]): List of entity types to detect. Defaults to all available entities.

        Returns:
            str: The formatted prompt string.
        """
        # Check if requested_entities is None; if so, use all available entities.
        if requested_entities is None:
            requested_entities = list(GEMINI_AVAILABLE_ENTITIES.values())
        # Create a string that lists each requested entity in a formatted bullet point.
        entities_str = "\n".join(f"- **{entity}**" for entity in requested_entities)
        # Combine the prompt header, entity list, the text to analyze, and the prompt footer, then return.
        return f"{GEMINI_PROMPT_HEADER}{entities_str}\n\n### **Text to Analyze:**\n{text}\n{GEMINI_PROMPT_FOOTER}"

    async def send_request(
        self,
        text: str,
        requested_entities: Optional[List[str]] = None,
        max_retries: int = 3,
        raw_prompt: bool = False,
        system_instruction_override: Optional[str] = None,
    ) -> Optional[str]:
        """
        Send a request to the Gemini API with retry logic and exponential backoff.

        This method constructs a prompt (unless raw_prompt is True), sends it via the Gemini API,
        and handles potential errors, including network issues and content restrictions.

        Args:
            text (str): The text to analyze.
            requested_entities (Optional[List[str]]): List of entity types to detect.
            max_retries (int): Maximum number of retry attempts.
            raw_prompt (bool): If True, the provided text is used as the prompt without modification.
            system_instruction_override (Optional[str]): If provided, overrides the default system instruction.

        Returns:
            Optional[str]: The cleaned and stripped response text from the API, an empty string for restricted responses, or None on failure.
        """
        # Determine the system instruction to use, preferring an override if provided.
        sys_inst = system_instruction_override or SYSTEM_INSTRUCTION
        # Create the prompt: use the raw text if raw_prompt is True; otherwise, build the dynamic prompt.
        prompt = text if raw_prompt else self.create_prompt(text, requested_entities)
        # Set the initial backoff delay to one second.
        backoff = 1
        # Loop through the maximum number of retry attempts.
        for attempt in range(max_retries):
            try:
                # Initialize a Gemini GenerativeModel instance with the selected model and system instruction.
                model = genai.GenerativeModel(
                    self.model_name, system_instruction=sys_inst
                )
                # Call the generate_content method in a separate thread to prevent blocking.
                response = await asyncio.to_thread(model.generate_content, prompt)
                # Check if the response is empty or contains only whitespace; if so, log error and return an empty string.
                if not response or not response.text.strip():
                    logger.error("❌ Empty response from Gemini API")
                    return ""
                # Log a successful API response.
                logger.info("✅ Successfully received response from Gemini API")
                # Return the stripped response text without any leading/trailing backticks or whitespace.
                return response.text.strip("`").strip()
            except Exception as e:
                # If a ConnectionError occurs, log a specific error message.
                if isinstance(e, ConnectionError):
                    logger.error(f"❌ Network Error communicating with Gemini API: {e}")
                # If the exception message suggests content was rejected due to copyright filtering, log a warning and return None.
                elif "finish_reason" in str(e) and "is 4" in str(e):
                    logger.warning(
                        "⚠️ Gemini refused content due to copyright filtering. Returning empty result."
                    )
                    return None
            # If not on the last retry attempt, log retry information and wait for the designated backoff period.
            if attempt < max_retries - 1:
                logger.info(
                    f"Retrying after {backoff} seconds (attempt {attempt + 2} of {max_retries})..."
                )
                time.sleep(backoff)
                # Double the backoff period for exponential backoff.
                backoff *= 2
        # If all retry attempts fail, return None.
        return None

    def parse_response(self, response: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Parse the raw response text from the Gemini API into a JSON object.

        This method cleans the response by removing extraneous backticks and prefixes,
        then attempts to parse it as JSON. If parsing fails, it extracts and attempts to parse
        potential JSON substrings.

        Args:
            response (Optional[str]): The raw response text from the API.

        Returns:
            Optional[Dict[str, Any]]: The parsed JSON object or None if parsing failed.
        """
        # Check if the response is empty; if so, log an error and return None.
        if not response:
            logger.error("❌ Error: Received empty response")
            return None
        # Remove leading/trailing backticks and whitespace from the response.
        cleaned_response = response.strip("`").strip()
        # If the cleaned response starts with the word "json" (case-insensitive), remove it.
        if cleaned_response.lower().startswith("json"):
            cleaned_response = cleaned_response[4:].strip()
        # Attempt to parse the cleaned response as JSON.
        parsed_json = self._try_json_parse(cleaned_response)
        # If parsing is successful, return the JSON object.
        if parsed_json:
            return parsed_json
        # If direct parsing fails, extract potential JSON candidates from the cleaned response.
        json_candidates = self._extract_json_candidates(cleaned_response)
        # Iterate over each candidate and attempt to parse them.
        for candidate in json_candidates:
            parsed_json = self._try_json_parse(candidate)
            # If successful parsing is achieved, return the parsed JSON.
            if parsed_json:
                return parsed_json
        # Log an error if no valid JSON object could be extracted.
        logger.error(
            "❌ Error: No valid JSON object could be extracted from the response"
        )
        # Return None if parsing fails completely.
        return None

    @staticmethod
    def _try_json_parse(text: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Attempt to safely parse a JSON string.

        Args:
            text (Optional[str]): The text to be parsed as JSON.

        Returns:
            Optional[Dict[str, Any]]: The parsed JSON object, or None if parsing fails.
        """
        # Check if the text is a string; if not, return None.
        if not isinstance(text, str):
            return None
        try:
            # Attempt to load the text as JSON and return the resulting object.
            return json.loads(text)
        except json.JSONDecodeError:
            # If a JSONDecodeError occurs, return None.
            return None

    @staticmethod
    def _process_json_character(
        char: str, index: int, stack: List[str], start: Optional[int]
    ) -> Optional[int]:
        """
        Process a single character to help identify JSON object boundaries.

        Args:
            char (str): The character being processed.
            index (int): The current index of the character in the text.
            stack (List[str]): A list serving as a stack to track open JSON brackets.
            start (Optional[int]): The starting index of a potential JSON object.

        Returns:
            Optional[int]: The updated start index if a new JSON block is detected; otherwise, the original start.
        """
        # If the character is an opening brace, check if this is the start of a JSON block.
        if char == "{":
            # If start is not set, mark this index as the start.
            if start is None:
                start = index
            # Push an opening brace onto the stack.
            stack.append("{")
        # If the character is a closing brace and there is an open block in the stack,
        elif char == "}" and stack:
            # Pop the last opening brace from the stack.
            stack.pop()
            # If the stack is empty, it means the JSON block has closed; return the start index.
            if not stack:
                return start
        # Return the current start index (could be unchanged).
        return start

    @staticmethod
    def _find_potential_json_candidates(text: Optional[str]) -> List[str]:
        """
        Identify potential JSON substrings from text without validating them.

        Args:
            text (Optional[str]): The text that might contain JSON.

        Returns:
            List[str]: A list of potential JSON substrings.
        """
        # If the text is None or empty, return an empty list.
        if not text:
            return []
        # Initialize an empty list to store JSON candidate substrings.
        json_candidates = []
        # Initialize an empty list to serve as a stack for bracket matching.
        stack = []
        # Initialize the start index of a JSON candidate as None.
        start = None
        # Loop through each character in the text with its index.
        for i, char in enumerate(text):
            # Process the current character and update the start index if needed.
            start = GeminiHelper._process_json_character(char, i, stack, start)
            # If a JSON candidate has been identified and the stack is empty, a candidate block has ended.
            if start is not None and not stack:
                # Extract the candidate substring from start index to current index (inclusive).
                candidate = text[start : i + 1]
                # Ensure the candidate is valid by checking its length or if it exactly equals "{}".
                if candidate == "{}" or len(candidate) > 2:
                    json_candidates.append(candidate)
                # Reset the start index for the next potential JSON candidate.
                start = None
        # Return the list of potential JSON candidate substrings.
        return json_candidates

    @staticmethod
    def _extract_json_candidates(text: Optional[str]) -> List[str]:
        """
        Extract valid JSON substrings from the provided text.

        Args:
            text (Optional[str]): The text that might contain JSON.

        Returns:
            List[str]: A list of JSON strings that can be successfully parsed.
        """
        # First, obtain potential JSON substrings from the text.
        potential_jsons = GeminiHelper._find_potential_json_candidates(text)
        # Filter the potential candidates, returning only those that are either "{}" or can be parsed as JSON.
        return [
            candidate
            for candidate in potential_jsons
            if candidate == "{}" or GeminiHelper._try_json_parse(candidate)
        ]

    async def process_text(
        self, text: str, requested_entities: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Process the provided text with the Gemini API and return the parsed JSON result.

        This method first checks for a cached response. If not found, it sends the text to the API,
        parses the response, caches it, and returns the result.

        Args:
            text (str): The text to be analyzed.
            requested_entities (Optional[List[str]]): List of entity types to detect.

        Returns:
            Optional[Dict[str, Any]]: Parsed JSON response from the API or None if processing fails.
        """
        # Generate a unique cache key based on the input text and requested entities.
        key = self._cache_key(text, requested_entities)
        # Check if the cache contains a response for this key; if so, log and return the cached response.
        if key in self.cache:
            logger.info("✅ Using cached response for Gemini API request")
            return self.cache[key]
        # Send the request to the Gemini API and await its response.
        response = await self.send_request(text, requested_entities)
        # Parse the response into JSON format if a response was received.
        result = self.parse_response(response) if response else None
        # If the result is valid, store it in the cache using the generated key.
        if result is not None:
            self.cache[key] = result
        # Return the parsed result (or None if the process failed).
        return result


# Instantiate a global GeminiHelper object for use elsewhere in the application.
gemini_helper = GeminiHelper()
