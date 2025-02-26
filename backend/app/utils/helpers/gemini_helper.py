import os

import json

from backend.app.utils.logger import default_logger as logging

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

    @staticmethod
    def create_prompt(text, requested_entities=None):
        """
        Constructs the Gemini API prompt dynamically using the provided text and requested entities.
        """
        requested_entities = requested_entities or AVAILABLE_ENTITIES
        entities_str = "\n".join(f"- **{entity}**" for entity in requested_entities)
        return f"{GEMINI_PROMPT_HEADER}{entities_str}\n\n### **Inspection Report Text:**\n{text}\n{GEMINI_PROMPT_FOOTER}"

    def send_request(self, text, requested_entities=None):
        """
        Sends a request to the Gemini API for the provided text.
        """
        prompt = self.create_prompt(text, requested_entities)
        try:
            model = genai.GenerativeModel(self.model_name, system_instruction=SYSTEM_INSTRUCTION)
            response = model.generate_content(prompt)

            if response and response.text.strip():
                logging.info("✅ Successfully received response from Gemini API.")
                return response.text.strip("`").strip()

            logging.error("❌ Empty response from Gemini API.")
            return None
        except ConnectionError as e:
            logging.error(f"❌ Network Error communicating with Gemini API: {e}")
            return None
        except Exception as e:
            logging.error(f"❌ Unexpected error communicating with Gemini API: {e}")
            return None

    def parse_response(self, response):
        """
        Parses the raw response text from Gemini API into a JSON object.
        """
        if not response:
            logging.error("❌ Error: Received empty response.")
            return None

        cleaned_response = response.strip("`").strip()
        if cleaned_response.lower().startswith("json"):
            cleaned_response = cleaned_response[4:].strip()

        parsed_json = self._try_json_parse(cleaned_response)
        if parsed_json:
            return parsed_json

        json_candidates = self._extract_json_candidates(cleaned_response)
        for candidate in json_candidates:
            parsed_json = self._try_json_parse(candidate)
            if parsed_json:
                return parsed_json

        logging.error("❌ Error: No valid JSON object could be extracted from the response.")
        return None

    @staticmethod
    def _try_json_parse(text):
        """
        Attempts to parse a JSON string safely.
        """
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _extract_json_candidates(text):
        """
        Extracts possible JSON substrings from the response.
        """
        json_candidates = []
        stack = []
        start = None

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

    def process_text(self, text, requested_entities=None):
        """
        Processes a given text: sends it to Gemini API and returns the parsed JSON response.
        """
        response = self.send_request(text, requested_entities)
        return self.parse_response(response) if response else None
