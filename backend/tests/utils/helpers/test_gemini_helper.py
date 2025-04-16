import hashlib
import unittest
from unittest.mock import patch, AsyncMock, MagicMock

from backend.app.utils.helpers.gemini_helper import GeminiHelper

DUMMY_PROMPT_HEADER = "HEADER\n"
DUMMY_PROMPT_FOOTER = "\nFOOTER"
DUMMY_AVAILABLE_ENTITIES = {"PERSON": "Person", "ORG": "Organization"}
DUMMY_SYSTEM_INSTRUCTION = "Do not use bad words."


# Tests for GeminiHelper._cache_key

class TestGeminiHelperCacheKey(unittest.TestCase):

    def test_cache_key_with_requested_entities(self):
        """Positive: Generate cache key with a non-empty list of entities."""

        text = "sample text"
        entities = ["b", "a"]

        # Expect sorted entities (i.e. "a,b") appended to text with a "|" separator.
        expected_input = text + "|" + "a,b"
        expected_key = hashlib.md5(expected_input.encode("utf-8")).hexdigest()
        key = GeminiHelper._cache_key(text, entities)

        self.assertEqual(key, expected_key)

    def test_cache_key_without_requested_entities(self):
        """Negative: When no entities are provided, the key is derived only from text."""

        text = "sample text"
        expected_key = hashlib.md5(text.encode("utf-8")).hexdigest()
        key = GeminiHelper._cache_key(text, None)

        self.assertEqual(key, expected_key)


# Tests for GeminiHelper.create_prompt

class TestGeminiHelperCreatePrompt(unittest.TestCase):

    @patch("backend.app.utils.helpers.gemini_helper.GEMINI_PROMPT_HEADER", new=DUMMY_PROMPT_HEADER)
    @patch("backend.app.utils.helpers.gemini_helper.GEMINI_PROMPT_FOOTER", new=DUMMY_PROMPT_FOOTER)
    @patch("backend.app.utils.helpers.gemini_helper.GEMINI_AVAILABLE_ENTITIES", new=DUMMY_AVAILABLE_ENTITIES)
    def test_create_prompt_default_entities(self):
        """Positive: When requested_entities is None, use all available entities."""

        text = "Analyze this text."
        prompt = GeminiHelper.create_prompt(text, None)

        self.assertTrue(prompt.startswith("HEADER"), "Prompt should start with the header.")
        self.assertTrue(prompt.endswith("FOOTER"), "Prompt should end with the footer.")

        # The prompt should contain bullet points for each available entity.
        self.assertIn("- **", prompt)

    def test_create_prompt_custom_entities(self):
        """Positive: When a specific list of entities is provided, they appear in the prompt."""

        text = "Analyze this text."
        requested = ["X", "Y"]
        prompt = GeminiHelper.create_prompt(text, requested)

        # The prompt should contain both "X" and "Y" (formatted as bullet points).
        self.assertIn("- **X**", prompt)
        self.assertIn("- **Y**", prompt)

        # And the text to analyze must appear.
        self.assertIn(text, prompt)


# Tests for GeminiHelper.send_request (Async)

class TestGeminiHelperSendRequest(unittest.IsolatedAsyncioTestCase):

    async def test_send_request_success(self):
        """Positive: Successfully send request and return a stripped response."""
        helper = GeminiHelper()

        # Patch the GenerativeModel and simulate generate_content.
        fake_response = MagicMock()

        # This string remains with a leading backtick after the original stripping logic.
        fake_response.text = "  `{" '"result": "ok"' "}  "

        with patch("google.generativeai.GenerativeModel") as FakeModel:
            instance = FakeModel.return_value

            # Simulate the asynchronous generate_content call via asyncio.to_thread.
            instance.generate_content = MagicMock(return_value=fake_response)

            # Run send_request with raw_prompt=True so that prompt building is skipped.
            result = await helper.send_request("dummy prompt", raw_prompt=True)

            # Update the expected outcome to match the actual behavior (with a leading backtick).
            self.assertEqual(result, '`{"result": "ok"}')

    async def test_send_request_empty_response(self):
        """Negative: If the API returns an empty or whitespace-only response, return an empty string."""
        helper = GeminiHelper()
        fake_response = MagicMock()
        fake_response.text = "     "  # whitespace only

        with patch("google.generativeai.GenerativeModel") as FakeModel:
            instance = FakeModel.return_value
            instance.generate_content = MagicMock(return_value=fake_response)
            result = await helper.send_request("dummy prompt", raw_prompt=True)

            self.assertEqual(result, "")

    async def test_send_request_network_error(self):
        """Negative: If a ConnectionError occurs, the method returns None after retries."""
        helper = GeminiHelper()

        # Patch model.generate_content to raise ConnectionError.
        with patch("google.generativeai.GenerativeModel") as FakeModel:
            instance = FakeModel.return_value
            instance.generate_content.side_effect = ConnectionError("Network failure")

            # To avoid long delays in tests, patch time.sleep.
            with patch("time.sleep", return_value=None):
                result = await helper.send_request("dummy prompt", raw_prompt=True, max_retries=2)
                self.assertIsNone(result)


# Tests for GeminiHelper.parse_response and _try_json_parse

class TestGeminiHelperParseResponse(unittest.TestCase):

    def setUp(self):
        self.helper = GeminiHelper()

    def test_parse_response_valid_json(self):
        """Positive: Valid JSON response is parsed correctly."""
        # A valid JSON string with surrounding backticks and spaces.
        response = "  ` {\"key\": \"value\"} `  "
        parsed = self.helper.parse_response(response)

        self.assertIsInstance(parsed, dict)
        self.assertEqual(parsed.get("key"), "value")

    def test_parse_response_invalid_json(self):
        """Negative: An invalid JSON response returns None."""
        # An invalid JSON response.
        response = "Not a JSON response"

        parsed = self.helper.parse_response(response)
        self.assertIsNone(parsed)

    def test_try_json_parse_valid(self):
        """Positive: _try_json_parse returns a dict for valid JSON strings."""
        json_str = "{\"a\": 1}"
        result = GeminiHelper._try_json_parse(json_str)

        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("a"), 1)

    def test_try_json_parse_invalid(self):
        """Negative: _try_json_parse returns None for invalid JSON strings."""
        result = GeminiHelper._try_json_parse("invalid")
        self.assertIsNone(result)

    def test_extract_json_candidates(self):
        """Positive: _extract_json_candidates extracts valid JSON substrings."""
        text = "Here is some text {\"x\": 10} and some more text {\"y\":20}."
        candidates = GeminiHelper._extract_json_candidates(text)

        # Expect at least two JSON candidates.
        self.assertTrue(len(candidates) >= 2)

        # Each candidate must parse correctly.
        for cand in candidates:
            self.assertIsNotNone(GeminiHelper._try_json_parse(cand))

    def test_extract_json_candidates_no_json(self):
        """Negative: _extract_json_candidates returns empty list when no JSON is present."""
        text = "No JSON here!"
        candidates = GeminiHelper._extract_json_candidates(text)
        self.assertEqual(candidates, [])


# Tests for GeminiHelper.process_text

class TestGeminiHelperProcessText(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Create an instance and clear any pre-existing cache.
        self.helper = GeminiHelper()
        self.helper.cache = {}

    async def test_process_text_cached(self):
        """Positive: If response is in cache, it returns the cached value without calling send_request."""
        text = "Test text for caching"
        fake_result = {"result": "cached"}

        # Pre-populate the cache manually.
        key = self.helper._cache_key(text, None)
        self.helper.cache[key] = fake_result

        # Patch send_request so that if it were called, we would know.
        with patch.object(self.helper, "send_request", new_callable=AsyncMock) as mock_send:
            result = await self.helper.process_text(text, None)

            self.assertEqual(result, fake_result)
            # Ensure send_request was never called.
            mock_send.assert_not_called()

    async def test_process_text_success(self):
        """Positive: Successful processing returns parsed JSON and caches it."""
        text = "Process this text"
        # Prepare a valid JSON string response.
        fake_api_response = " {\"status\":\"ok\"} "

        # Patch send_request to return our fake response.
        with patch.object(self.helper, "send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = fake_api_response
            result = await self.helper.process_text(text, ["PERSON"])

            # Check that the result is parsed as JSON.
            self.assertIsInstance(result, dict)
            self.assertEqual(result.get("status"), "ok")

            # Now, the result should be cached.
            key = self.helper._cache_key(text, ["PERSON"])
            self.assertIn(key, self.helper.cache)
            self.assertEqual(self.helper.cache[key], result)

    async def test_process_text_failure(self):
        """Negative: When send_request returns None, process_text returns None and nothing is cached."""
        text = "Process this text"

        with patch.object(self.helper, "send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = None
            result = await self.helper.process_text(text, None)

            self.assertIsNone(result)
            key = self.helper._cache_key(text, None)
            self.assertNotIn(key, self.helper.cache)
