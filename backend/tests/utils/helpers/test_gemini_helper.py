import hashlib
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

from backend.app.utils.helpers.gemini_helper import GeminiHelper

# Constants for prompt header, footer, available entities, and system instruction
DUMMY_PROMPT_HEADER = "HEADER\n"

DUMMY_PROMPT_FOOTER = "\nFOOTER"

DUMMY_AVAILABLE_ENTITIES = {"PERSON": "Person", "ORG": "Organization"}

DUMMY_SYSTEM_INSTRUCTION = "Do not use bad words."


# Tests for the cache key generation logic of GeminiHelper
class TestGeminiHelperCacheKey(unittest.TestCase):

    # Test cache key includes sorted entities when provided
    def test_cache_key_with_requested_entities(self):
        text = "sample text"

        entities = ["b", "a"]

        expected_input = text + "|" + "a,b"

        expected_key = hashlib.md5(expected_input.encode("utf-8")).hexdigest()

        key = GeminiHelper._cache_key(text, entities)

        self.assertEqual(key, expected_key)

    # Test cache key is just text hash when no entities
    def test_cache_key_without_requested_entities(self):
        text = "sample text"

        expected_key = hashlib.md5(text.encode("utf-8")).hexdigest()

        key = GeminiHelper._cache_key(text, None)

        self.assertEqual(key, expected_key)


# Tests for prompt creation in GeminiHelper
class TestGeminiHelperCreatePrompt(unittest.TestCase):

    # Test default prompt uses all available entities
    @patch(
        "backend.app.utils.helpers.gemini_helper.GEMINI_PROMPT_HEADER",
        new=DUMMY_PROMPT_HEADER,
    )
    @patch(
        "backend.app.utils.helpers.gemini_helper.GEMINI_PROMPT_FOOTER",
        new=DUMMY_PROMPT_FOOTER,
    )
    @patch(
        "backend.app.utils.helpers.gemini_helper.GEMINI_AVAILABLE_ENTITIES",
        new=DUMMY_AVAILABLE_ENTITIES,
    )
    def test_create_prompt_default_entities(self):
        text = "Analyze this text."

        prompt = GeminiHelper.create_prompt(text, None)

        self.assertTrue(prompt.startswith("HEADER"))

        self.assertTrue(prompt.endswith("FOOTER"))

        self.assertIn("- **", prompt)

    # Test prompt includes only specified entities
    def test_create_prompt_custom_entities(self):
        text = "Analyze this text."

        requested = ["X", "Y"]

        prompt = GeminiHelper.create_prompt(text, requested)

        self.assertIn("- **X**", prompt)

        self.assertIn("- **Y**", prompt)

        self.assertIn(text, prompt)


# Tests for the asynchronous send_request method
class TestGeminiHelperSendRequest(unittest.IsolatedAsyncioTestCase):

    # Test successful API call returns stripped response
    async def test_send_request_success(self):
        helper = GeminiHelper()

        fake_response = MagicMock()

        fake_response.text = '  `{"result": "ok"}  '

        with patch("google.generativeai.GenerativeModel") as FakeModel:
            instance = FakeModel.return_value

            instance.generate_content = MagicMock(return_value=fake_response)

            result = await helper.send_request("dummy prompt", raw_prompt=True)

        self.assertEqual(result, '`{"result": "ok"}')

    # Test empty or whitespace-only response returns empty string
    async def test_send_request_empty_response(self):
        helper = GeminiHelper()

        fake_response = MagicMock()

        fake_response.text = "     "

        with patch("google.generativeai.GenerativeModel") as FakeModel:
            instance = FakeModel.return_value

            instance.generate_content = MagicMock(return_value=fake_response)

            result = await helper.send_request("dummy prompt", raw_prompt=True)

        self.assertEqual(result, "")

    # Test network error leads to None after retries
    async def test_send_request_network_error(self):
        helper = GeminiHelper()

        with patch("google.generativeai.GenerativeModel") as FakeModel:
            instance = FakeModel.return_value

            instance.generate_content.side_effect = ConnectionError("Network failure")

            with patch("time.sleep", return_value=None):
                result = await helper.send_request(
                    "dummy prompt", raw_prompt=True, max_retries=2
                )

        self.assertIsNone(result)


# Tests for response parsing and JSON extraction
class TestGeminiHelperParseResponse(unittest.TestCase):

    # Setup a helper instance
    def setUp(self):
        self.helper = GeminiHelper()

    # Test valid JSON response is parsed correctly
    def test_parse_response_valid_json(self):
        response = '  ` {"key": "value"} `  '

        parsed = self.helper.parse_response(response)

        self.assertIsInstance(parsed, dict)

        self.assertEqual(parsed.get("key"), "value")

    # Test invalid JSON response returns None
    def test_parse_response_invalid_json(self):
        response = "Not a JSON response"

        parsed = self.helper.parse_response(response)

        self.assertIsNone(parsed)

    # Test _try_json_parse returns dict on valid JSON
    def test_try_json_parse_valid(self):
        json_str = '{"a": 1}'

        result = GeminiHelper._try_json_parse(json_str)

        self.assertIsInstance(result, dict)

        self.assertEqual(result.get("a"), 1)

    # Test _try_json_parse returns None on invalid JSON
    def test_try_json_parse_invalid(self):
        result = GeminiHelper._try_json_parse("invalid")

        self.assertIsNone(result)

    # Test extraction of JSON substrings from text
    def test_extract_json_candidates(self):
        text = 'Here is some text {"x": 10} and some more text {"y":20}.'

        candidates = GeminiHelper._extract_json_candidates(text)

        self.assertTrue(len(candidates) >= 2)

        for cand in candidates:
            self.assertIsNotNone(GeminiHelper._try_json_parse(cand))

    # Test no JSON yields empty candidate list
    def test_extract_json_candidates_no_json(self):
        text = "No JSON here!"

        candidates = GeminiHelper._extract_json_candidates(text)

        self.assertEqual(candidates, [])


# Tests for the process_text method with caching
class TestGeminiHelperProcessText(unittest.IsolatedAsyncioTestCase):

    # Async setup clears cache
    async def asyncSetUp(self):
        self.helper = GeminiHelper()

        self.helper.cache = {}

    # Test cached response is returned without API call
    async def test_process_text_cached(self):
        text = "Test text for caching"

        fake_result = {"result": "cached"}

        key = self.helper._cache_key(text, None)

        self.helper.cache[key] = fake_result

        with patch.object(
            self.helper, "send_request", new_callable=AsyncMock
        ) as mock_send:
            result = await self.helper.process_text(text, None)

        self.assertEqual(result, fake_result)

        mock_send.assert_not_called()

    # Test successful processing caches and returns parsed JSON
    async def test_process_text_success(self):
        text = "Process this text"

        fake_api_response = ' {"status":"ok"} '

        with patch.object(
            self.helper, "send_request", new_callable=AsyncMock
        ) as mock_send:
            mock_send.return_value = fake_api_response

            result = await self.helper.process_text(text, ["PERSON"])

        self.assertIsInstance(result, dict)

        self.assertEqual(result.get("status"), "ok")

        key = self.helper._cache_key(text, ["PERSON"])

        self.assertIn(key, self.helper.cache)

        self.assertEqual(self.helper.cache[key], result)

    # Test failure (None response) yields None and no cache entry
    async def test_process_text_failure(self):
        text = "Process this text"

        with patch.object(
            self.helper, "send_request", new_callable=AsyncMock
        ) as mock_send:
            mock_send.return_value = None

            result = await self.helper.process_text(text, None)

        self.assertIsNone(result)

        key = self.helper._cache_key(text, None)

        self.assertNotIn(key, self.helper.cache)
