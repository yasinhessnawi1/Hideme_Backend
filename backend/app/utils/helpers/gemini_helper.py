import logging
import os

import google.generativeai as genai
from dotenv import load_dotenv
from backend.app.configs.gemini_config import GEMINI_PROMPT_HEADER, GEMINI_PROMPT_FOOTER, AVAILABLE_ENTITIES, \
    SYSTEM_INSTRUCTION

# Load environment variables
load_dotenv(verbose=True)

class GeminiHelper:
    """
    Helper class to interact with the Google Gemini API:
      - Builds prompts based on a template.
      - Sends a request and retrieves the response.
      - Parses the JSON response.
    """
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            logging.error("❌ Gemini API Key is missing! Set GEMINI_API_KEY in .env")
            raise ValueError("GEMINI_API_KEY is not set in the environment.")
        genai.configure(api_key=self.api_key)
        self.model_name = "gemini-2.0-flash"
        logging.info("✅ GeminiHelper initialized with model '%s'.", self.model_name)

    def create_prompt(self, text, requested_entities=None):
        """
        Constructs the Gemini API prompt dynamically using the provided text and requested entities.
        """
        if requested_entities is None:
            requested_entities = AVAILABLE_ENTITIES
        # Create a bullet list of requested entities.
        entities_str = "\n".join(f"- **{entity}**" for entity in requested_entities)
        prompt = f"{GEMINI_PROMPT_HEADER}{entities_str}\n\n### **Inspection Report Text:**\n{text}\n{GEMINI_PROMPT_FOOTER}"
        return prompt

    def send_request(self, text, requested_entities=None):
        """
        Sends a request to the Gemini API for the provided text.
        :param text: The text to process.
        :param requested_entities: List of entity types to request.
        :return: The raw response text from the API, or None if an error occurred.
        """
        prompt = self.create_prompt(text, requested_entities)
        try:
            model = genai.GenerativeModel(self.model_name, system_instruction=SYSTEM_INSTRUCTION)
            response = model.generate_content(prompt)
            if not response or not response.text.strip():
                logging.error("❌ Empty response from Gemini API.")
                return None
            response_text = response.text.strip("`").strip()
            logging.info("✅ Successfully received response from Gemini API.")
            return response_text
        except Exception as e:
            logging.error(f"❌ Error communicating with Gemini API: {e}")
            return None

    def parse_response(self, response):
        """
        Parses the raw response text from Gemini API into a JSON object.

        First, it attempts to directly parse the response. If that fails,
        it uses a stack-based approach to extract all balanced JSON substrings,
        then tries each candidate and returns the one with maximum length that
        parses successfully.

        :param response: The raw response text from Gemini API.
        :return: Parsed JSON object or None if parsing fails.
        """
        import json
        import logging

        # First, try to parse the full response
        try:
            return json.loads(response)
        except json.JSONDecodeError as e:
            logging.warning("Direct JSON parsing failed: %s", e)

        # Helper: extract all balanced JSON substrings using a stack.
        def extract_json_candidates(s):
            candidates = []
            start = None
            stack = []
            for i, char in enumerate(s):
                if char == '{':
                    if start is None:
                        start = i
                    stack.append('{')
                elif char == '}':
                    if stack:
                        stack.pop()
                        if not stack and start is not None:
                            # Found a candidate substring with balanced braces.
                            candidates.append(s[start:i + 1])
                            start = None
            return candidates

        # Clean the response and extract candidates.
        cleaned_response = response.strip("`").strip()
        candidates = extract_json_candidates(cleaned_response)

        valid_candidate = None
        max_length = 0
        for candidate in candidates:
            try:
                obj = json.loads(candidate)
                # Choose the candidate with maximum length (assumed to be the full JSON)
                if len(candidate) > max_length:
                    max_length = len(candidate)
                    valid_candidate = obj
            except Exception:
                continue

        if valid_candidate is None:
            logging.error("❌ Error: No valid JSON object could be extracted from the response.")
        return valid_candidate

    def process_text(self, text, requested_entities=None):
        """
        Processes a given text: sends it to Gemini API and returns the parsed JSON response.
        """
        response = self.send_request(text, requested_entities)
        return self.parse_response(f'"{response}"')
