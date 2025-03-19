from unittest.mock import AsyncMock, patch

import pytest

from backend.app.configs.gemini_config import GEMINI_PROMPT_HEADER, GEMINI_PROMPT_FOOTER
from backend.app.utils.helpers.gemini_helper import GeminiHelper


@pytest.mark.parametrize("text, requested_entities, expected_same", [
    ("Test text", ["Entity1", "Entity2"], True),  # Same input should return the same key
    ("Test text", ["Entity2", "Entity1"], True),  # Order of entities should not affect the key
    ("Different text", ["Entity1", "Entity2"], False),  # Different text should return a different key
    ("Test text", ["DifferentEntity"], False),  # Different entities should return a different key
    ("Test text", [], True),  # Empty entity list should be handled
    ("Test text", None, True),  # None entity list should be handled
])
def test_cache_key_positive_cases(text, requested_entities, expected_same):
    """
    ✅ Test that _cache_key generates consistent and unique keys for various valid inputs.
    """
    key1 = GeminiHelper._cache_key(text, requested_entities)
    key2 = GeminiHelper._cache_key(text, requested_entities)

    if expected_same:
        assert key1 == key2, f"Expected same cache key for identical input, but got {key1} and {key2}"
    else:
        assert key1 != GeminiHelper._cache_key("Test text", ["Entity1", "Entity2"]), \
            f"Expected different cache keys, but got {key1} and {key2}"


@pytest.mark.parametrize("text, requested_entities", [
    ("", ["Entity1"]),  # Empty text
    ("Test text", None),  # None as requested_entities
    ("Test text", []),  # Empty requested_entities list
    ("Text with special characters !@#$%^&*()", ["Entity1", "Entity2"]),  # Special characters in text
    ("Test text", ["Entity@#$%", "Entity123"]),  # Special characters in entities
    ("a" * 10000, ["Entity1"]),  # Extremely long input
])
def test_cache_key_negative_cases(text, requested_entities):
    """
    ❌ Test that _cache_key correctly handles edge cases and unexpected inputs.
    """
    try:
        key = GeminiHelper._cache_key(text, requested_entities)
        assert isinstance(key, str), f"Expected key to be a string, got {type(key)}"
        assert len(key) == 32, f"Expected MD5 hash length of 32, got {len(key)}"
    except Exception as e:
        pytest.fail(f"Unexpected exception occurred: {e}")

def test_cache_key_uniqueness():
    """
    ✅ Ensure that different entity lists result in different cache keys.
    """
    key1 = GeminiHelper._cache_key("Test text", ["Entity1", "Entity2"])
    key2 = GeminiHelper._cache_key("Test text", ["Entity3", "Entity4"])

    assert key1 != key2, f"Expected different keys, but got the same: {key1}"

@pytest.mark.parametrize("text, requested_entities, expected_entities", [
    ("Test text", ["Entity1", "Entity2"], ["Entity1", "Entity2"]),  # Normal case with multiple entities
    ("Test text", ["Entity2", "Entity1"], ["Entity2", "Entity1"]),  # Order should be preserved
    ("Test text", [], []),  # No entities should be handled
    ("Test text", None, None),  # None should default to all entities
])
def test_create_prompt_positive_cases(text, requested_entities, expected_entities):
    """
    ✅ Test that create_prompt generates the expected formatted string.
    """
    prompt = GeminiHelper.create_prompt(text, requested_entities)

    # Validate header and footer
    assert prompt.startswith(GEMINI_PROMPT_HEADER), "Prompt should start with the correct header."
    assert prompt.endswith(GEMINI_PROMPT_FOOTER), "Prompt should end with the correct footer."

    # Validate text inclusion
    assert f"### **Text to Analyze:**\n{text}" in prompt, "Prompt should include the input text."

    # Validate entity formatting
    if expected_entities is not None:
        for entity in expected_entities:
            assert f"- **{entity}**" in prompt, f"Expected entity '{entity}' to be present in the prompt."

@pytest.mark.parametrize("text, requested_entities", [
    ("", ["Entity1", "Entity2"]),  # Empty text should still generate a valid prompt
    ("Test text", ["Entity@#$%", "Entity123"]),  # Special characters in entities
    ("Test text", ["Entity1"] * 100),  # Extremely long entity list (handling duplicates)
    ("Test text", None),  # None should default to all available entities
])
def test_create_prompt_negative_cases(text, requested_entities):
    """
    ❌ Test that create_prompt correctly handles edge cases and unexpected inputs.
    """
    try:
        prompt = GeminiHelper.create_prompt(text, requested_entities)
        assert isinstance(prompt, str), "Prompt should always return a string."
        assert len(prompt) > 0, "Prompt should not be empty."
    except Exception as e:
        pytest.fail(f"Unexpected exception occurred: {e}")

@pytest.mark.asyncio
@patch("backend.app.utils.helpers.gemini_helper.genai.GenerativeModel")
@patch("asyncio.to_thread")  # Patching asyncio.to_thread directly
async def test_send_request_success(mock_to_thread, mock_model):
    """
    ✅ Test send_request when the API returns a valid response.
    """
    # Mock response object with text attribute
    mock_response = AsyncMock()
    mock_response.text = "Mocked API response"

    # Mock the model instance
    mock_model_instance = mock_model.return_value

    # Mock the async to_thread call to return our mocked response
    mock_to_thread.return_value = mock_response

    # Initialize the helper
    helper = GeminiHelper()

    # Call the method
    result = await helper.send_request("Test text", ["Entity1", "Entity2"])

    # Assertions
    assert result == "Mocked API response", f"Expected 'Mocked API response', but got {result}"
    mock_to_thread.assert_called_once_with(mock_model_instance.generate_content, helper.create_prompt("Test text", ["Entity1", "Entity2"]))

@pytest.mark.asyncio
@patch("backend.app.utils.helpers.gemini_helper.genai.GenerativeModel")
@patch("asyncio.to_thread")  # Patching asyncio.to_thread
async def test_send_request_failure(mock_to_thread, mock_model):
    """
    ❌ Test send_request when the API call fails due to various errors.
    """
    helper = GeminiHelper()

    # Test Case 1: Network Failure
    mock_to_thread.side_effect = ConnectionError("Network issue")
    result = await helper.send_request("Test text", ["Entity1", "Entity2"])
    assert result is None, "Expected None due to network failure, but got a response."

    # Reset mock
    mock_to_thread.reset_mock()

    # Test Case 2: Unexpected Exception
    mock_to_thread.side_effect = Exception("Unexpected error")
    result = await helper.send_request("Test text", ["Entity1", "Entity2"])
    assert result is None, "Expected None due to unexpected exception, but got a response."

    # Reset mock
    mock_to_thread.reset_mock()

    # Test Case 3: Empty Response
    mock_response = AsyncMock()
    mock_response.text = ""  # Simulate an empty response
    mock_to_thread.return_value = mock_response

    result = await helper.send_request("Test text", ["Entity1", "Entity2"])
    assert result is None, "Expected None due to empty response, but got a response."

@pytest.mark.parametrize("response, expected", [
    ('{"key": "value"}', {"key": "value"}),  # Simple valid JSON
    ('{"name": "Alice", "age": 25}', {"name": "Alice", "age": 25}),  # Nested JSON
    ('{"list": [1, 2, 3]}', {"list": [1, 2, 3]}),  # JSON with list
    ('json{"status": "ok"}', {"status": "ok"}),  # JSON prefixed with "json"
])
def test_parse_response_valid_cases(response, expected):
    """
    ✅ Test parse_response with valid JSON strings.
    """
    helper = GeminiHelper()
    result = helper.parse_response(response)
    assert result == expected, f"Expected {expected}, but got {result}"


@pytest.mark.parametrize("response, expected", [
    (None, None),  # Null response
    ("", None),  # Empty response
    ("Invalid text", None),  # Non-JSON response
    ("{status: ok}", None),  # Missing double quotes around keys
    ("{'key': 'value'}", None),  # Single quotes instead of double quotes
    ("Some text before {\"valid\": \"json\"} some text after", {"valid": "json"}),  # Extract JSON from text
    ('{"key": "value"', None),  # Missing closing bracket
])
def test_parse_response_invalid_cases(response, expected):
    """
    ❌ Test parse_response with invalid or malformed JSON.
    """
    helper = GeminiHelper()
    result = helper.parse_response(response)
    assert result == expected, f"Expected {expected}, but got {result}"

@pytest.mark.parametrize("json_text, expected", [
    ('{"key": "value"}', {"key": "value"}),  # Simple JSON
    ('{"number": 42}', {"number": 42}),  # Number values
    ('{"bool": true}', {"bool": True}),  # Boolean values
    ('{"list": [1, 2, 3]}', {"list": [1, 2, 3]}),  # List inside JSON
    ('{"nested": {"inner": "value"}}', {"nested": {"inner": "value"}}),  # Nested JSON
])
def test_try_json_parse_valid_cases(json_text, expected):
    """
    ✅ Test _try_json_parse with valid JSON strings.
    """
    result = GeminiHelper._try_json_parse(json_text)
    assert result == expected, f"Expected {expected}, but got {result}"

@pytest.mark.parametrize("json_text", [
    None,  # Null input
    "",  # Empty string
    "Invalid text",  # Random string
    "{key: value}",  # Missing quotes on keys
    "{'key': 'value'}",  # Single quotes instead of double
    '{"key": "value"',  # Missing closing bracket
    '{"number": 42,}',  # Trailing comma
    '["unclosed array", 1, 2',  # Unclosed array
    '{"key": undefined}',  # Undefined is not valid in JSON
])
def test_try_json_parse_invalid_cases(json_text):
    """
    ❌ Test _try_json_parse with invalid or malformed JSON.
    """
    result = GeminiHelper._try_json_parse(json_text)
    assert result is None, f"Expected None, but got {result}"

@pytest.mark.parametrize("char, index, stack, start, expected_stack, expected_start", [
    ("{", 0, [], None, ["{"], 0),  # Opening brace starts JSON
    ("}", 1, ["{"], 0, [], 0),  # Closing brace closes JSON
    ("{", 2, ["{"], 0, ["{", "{"], 0),  # Nested opening brace
    ("}", 3, ["{", "{"], 0, ["{"], 0),  # Nested closing brace
    ("a", 4, ["{"], 0, ["{"], 0),  # Non-brace character (ignored)
])
def test_process_json_character_valid_cases(char, index, stack, start, expected_stack, expected_start):
    """
    ✅ Test _process_json_character for correct stack & start index behavior (valid cases).
    """
    result_start = GeminiHelper._process_json_character(char, index, stack, start)

    assert stack == expected_stack, f"Expected stack {expected_stack}, but got {stack}"
    assert result_start == expected_start, f"Expected start {expected_start}, but got {result_start}"

@pytest.mark.parametrize("char, index, stack, start, expected_stack, expected_start", [
    ("}", 5, [], None, [], None),  # Extra closing brace without opening
    ("}", 6, ["{"], None, [], None),  # Closing brace but start is None
    ("a", 7, [], None, [], None),  # Non-brace character should do nothing
    ("{", 8, ["{"], None, ["{", "{"], 8),  # Nested opening brace should set start to index
])
def test_process_json_character_invalid_cases(char, index, stack, start, expected_stack, expected_start):
    """
    ❌ Test _process_json_character for incorrect handling of brackets and characters.
    """
    result_start = GeminiHelper._process_json_character(char, index, stack, start)

    assert stack == expected_stack, f"Expected stack {expected_stack}, but got {stack}"
    assert result_start == expected_start, f"Expected start {expected_start}, but got {result_start}"


@pytest.mark.parametrize("text, expected", [
    ("{}", ["{}"]),  # Simple empty JSON
    ('{"key": "value"}', ['{"key": "value"}']),  # Single valid JSON
    ('Some text before {"key": "value"} some text after', ['{"key": "value"}']),  # JSON inside text
    ('{"key": {"nested": "object"}}', ['{"key": {"nested": "object"}}']),  # Nested JSON
    ('{"a": 1} {"b": 2}', ['{"a": 1}', '{"b": 2}']),  # Multiple JSON objects
    ('Random text {"a": 1, "b": {"c": 3}} more text {"x": "y"}',
     ['{"a": 1, "b": {"c": 3}}', '{"x": "y"}']),  # Multiple nested JSONs
])
def test_find_potential_json_candidates_valid_cases(text, expected):
    """
    ✅ Test _find_potential_json_candidates with valid JSON structures.
    """
    result = GeminiHelper._find_potential_json_candidates(text)
    assert result == expected, f"Expected {expected}, but got {result}"

@pytest.mark.parametrize("text, expected", [
    (None, []),  # Null input should return an empty list
    ("", []),  # Empty string should return an empty list
    ("No JSON here!", []),  # No JSON at all should return an empty list
    ("{missing end", ["{missing end"]),  # Extracts JSON-like structure
    ("missing start}", []),  # No opening brace, should return an empty list
    ("{'invalid': 'json'}", ["{'invalid': 'json'}"]),  # Extracts JSON-like but invalid
    ("{key: value}", ["{key: value}"]),  # Extracts JSON-like but invalid
])
def test_find_potential_json_candidates_invalid_cases(text, expected):
    """
    ❌ Test _find_potential_json_candidates with invalid or no JSON.
    """
    result = GeminiHelper._find_potential_json_candidates(text)
    assert result == expected, f"Expected {expected}, but got {result}"


@pytest.mark.parametrize("text, expected", [
    (None, []),  # Null input should return an empty list
    ("", []),  # Empty string should return an empty list
    ("No JSON here!", []),  # No JSON at all should return an empty list
    ("{missing end", []),  # No closing brace, should return an empty list
    ("missing start}", []),  # No opening brace, should return an empty list
    ("{'invalid': 'json'}", ["{'invalid': 'json'}"]),  # Extracts JSON-like but invalid
    ("{key: value}", ["{key: value}"]),  # Extracts JSON-like but invalid
])
def test_find_potential_json_candidates_invalid_cases(text, expected):
    """
    ❌ Test _find_potential_json_candidates with invalid or no JSON.
    """
    result = GeminiHelper._find_potential_json_candidates(text)
    assert result == expected, f"Expected {expected}, but got {result}"


@pytest.mark.parametrize("text", [
    None,  # Null input
    "",  # Empty string
    "No JSON here!",  # No JSON at all
    "{missing end",  # Open brace, but missing closing
    "missing start}",  # Closing brace, but missing opening
    "{'invalid': 'json'}",  # Single quotes (not valid JSON)
    "{key: value}",  # Missing quotes around keys
])
def test_extract_json_candidates_invalid_cases(text):
    """
    ❌ Test _extract_json_candidates with invalid or no JSON.
    """
    result = GeminiHelper._extract_json_candidates(text)
    assert result == [], f"Expected [], but got {result}"

@pytest.mark.asyncio
@patch.object(GeminiHelper, "_cache_key", return_value="mocked_key")
@patch.object(GeminiHelper, "send_request", new_callable=AsyncMock)
@patch.object(GeminiHelper, "parse_response")
async def test_process_text_cached_response(mock_parse_response, mock_send_request, mock_cache_key):
    """
    ✅ Test process_text returns cached response if available.
    """
    helper = GeminiHelper()
    helper.cache["mocked_key"] = {"mocked": "data"}

    result = await helper.process_text("Test text", ["Entity1"])

    assert result == {"mocked": "data"}, f"Expected cached data, but got {result}"
    mock_send_request.assert_not_called()
    mock_parse_response.assert_not_called()


@pytest.mark.asyncio
@patch.object(GeminiHelper, "_cache_key", return_value="mocked_key")
@patch.object(GeminiHelper, "send_request", new_callable=AsyncMock, return_value='{"success": true}')
@patch.object(GeminiHelper, "parse_response", return_value={"success": True})
async def test_process_text_success(mock_parse_response, mock_send_request, mock_cache_key):
    """
    ✅ Test process_text when API request succeeds.
    """
    helper = GeminiHelper()

    result = await helper.process_text("Test text", ["Entity1"])

    assert result == {"success": True}, f"Expected {{'success': True}}, but got {result}"
    mock_send_request.assert_called_once()
    mock_parse_response.assert_called_once()
    assert "mocked_key" in helper.cache  # Ensure caching worked


@pytest.mark.asyncio
@patch.object(GeminiHelper, "_cache_key", return_value="mocked_key")
@patch.object(GeminiHelper, "send_request", new_callable=AsyncMock, return_value=None)
@patch.object(GeminiHelper, "parse_response")
async def test_process_text_api_failure(mock_parse_response, mock_send_request, mock_cache_key):
    """
    ❌ Test process_text when API returns None.
    """
    helper = GeminiHelper()

    result = await helper.process_text("Test text", ["Entity1"])

    assert result is None, f"Expected None, but got {result}"
    mock_parse_response.assert_not_called()
    assert "mocked_key" not in helper.cache  # Should not cache failed response


@pytest.mark.asyncio
@patch.object(GeminiHelper, "_cache_key", return_value="mocked_key")
@patch.object(GeminiHelper, "send_request", new_callable=AsyncMock, return_value="invalid json")
@patch.object(GeminiHelper, "parse_response", return_value=None)
async def test_process_text_invalid_json(mock_parse_response, mock_send_request, mock_cache_key):
    """
    ❌ Test process_text when API returns invalid JSON.
    """
    helper = GeminiHelper()

    result = await helper.process_text("Test text", ["Entity1"])

    assert result is None, f"Expected None, but got {result}"
    mock_send_request.assert_called_once()
    mock_parse_response.assert_called_once()
    assert "mocked_key" not in helper.cache  # Should not cache invalid response