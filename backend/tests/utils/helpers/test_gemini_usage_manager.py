from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

from backend.app.utils.helpers.gemini_usage_manager import GeminiUsageManager


@pytest.mark.asyncio
async def test_manage_page_processing_valid_cases():
    """
    ✅ Test manage_page_processing with valid input.
    """
    manager = GeminiUsageManager(max_daily_requests=5)

    # Case 1: Process normal text without exceeding limits
    result = await manager.manage_page_processing("This is a test text.", page_number=1)
    assert result == "This is a test text.", f"Expected full text but got {result}"

    # Case 2: Truncate text if it exceeds limit
    long_text = "word " * 3000  # More than 10,000 characters
    result = await manager.manage_page_processing(long_text, page_number=2)
    assert len(result) <= manager.text_truncation_limit, "Text was not truncated correctly"

    # Case 3: Different page number should be processed separately
    result = await manager.manage_page_processing("Another test text.", page_number=3)
    assert result == "Another test text.", "Processing for different pages should work independently"

@pytest.mark.asyncio
async def test_manage_page_processing_invalid_cases():
    """
    ❌ Test manage_page_processing with invalid scenarios.
    """
    manager = GeminiUsageManager(max_daily_requests=1)

    # Case 1: Exceed daily quota
    await manager.manage_page_processing("First request", page_number=1)
    result = await manager.manage_page_processing("Second request", page_number=2)
    assert result is None, "Expected None due to exceeded daily quota"

    # Case 2: Exceed concurrent request limit
    manager.concurrent_requests = manager.max_concurrent_requests
    result = await manager.manage_page_processing("Another request", page_number=3)
    assert result is None, "Expected None due to concurrent request limit"

    # Case 3: Empty text should not be processed
    result = await manager.manage_page_processing("", page_number=4)
    assert result == "", "Empty text should return empty string"

    # Case 4: Handling None input
    result = await manager.manage_page_processing(None, page_number=5)
    assert result is None, "Expected None when processing None input"

@pytest.mark.asyncio
async def test_check_and_acquire_request_slot_valid_cases():
    """
    ✅ Test _check_and_acquire_request_slot with valid scenarios.
    """
    # Case 1: No quota or concurrency exceeded
    manager = GeminiUsageManager(max_daily_requests=2, max_concurrent_requests=2)

    # First request - should succeed
    await manager._check_and_acquire_request_slot(page_number=1)
    assert manager.daily_requests == 1
    assert manager.concurrent_requests == 1

    # Second request - should succeed
    await manager._check_and_acquire_request_slot(page_number=2)
    assert manager.daily_requests == 2
    assert manager.concurrent_requests == 2


@pytest.mark.asyncio
async def test_check_and_acquire_request_slot_exceeding_daily_quota():
    """
    ❌ Test _check_and_acquire_request_slot when daily quota is exceeded.
    """
    manager = GeminiUsageManager(max_daily_requests=1)

    # First request - should succeed
    await manager._check_and_acquire_request_slot(page_number=1)

    # Exceed daily limit - should raise ValueError
    with pytest.raises(ValueError, match="Daily Gemini API request quota"):
        await manager._check_and_acquire_request_slot(page_number=2)


@pytest.mark.asyncio
async def test_check_and_acquire_request_slot_exceeding_concurrent_limit():
    """
    ❌ Test _check_and_acquire_request_slot when concurrent requests exceed limit.
    """
    manager = GeminiUsageManager(max_concurrent_requests=1)

    # First request - should succeed
    await manager._check_and_acquire_request_slot(page_number=1)

    # Exceed concurrent limit - should raise ValueError
    with pytest.raises(ValueError, match="Maximum concurrent Gemini requests"):
        await manager._check_and_acquire_request_slot(page_number=2)


@pytest.mark.asyncio
async def test_check_and_acquire_request_slot_with_request_spacing():
    """
    ✅ Test _check_and_acquire_request_slot when there is adaptive spacing between requests.
    """
    manager = GeminiUsageManager(request_delay=0.5)  # 0.5 second delay between requests

    # First request - should succeed
    await manager._check_and_acquire_request_slot(page_number=1)
    assert manager.concurrent_requests == 1

    # Second request - should wait due to request delay
    with patch("asyncio.sleep", return_value=None) as mock_sleep:
        await manager._check_and_acquire_request_slot(page_number=2)

        # Check if the sleep duration is close to the expected request delay.
        # Use pytest.approx to allow for minor differences due to testing environment.
        mock_sleep.assert_called_once_with(pytest.approx(0.5, rel=0.1))


@pytest.mark.asyncio
async def test_check_and_acquire_request_slot_reset_daily_quota():
    """
    ✅ Test _check_and_acquire_request_slot with daily quota reset after 24 hours.
    """
    manager = GeminiUsageManager(max_daily_requests=1)

    # First request - should succeed
    await manager._check_and_acquire_request_slot(page_number=1)
    assert manager.daily_requests == 1

    # Simulate time passing for the next day
    manager.last_reset_time = datetime.now() - timedelta(days=1)

    # Second request after quota reset - should succeed
    await manager._check_and_acquire_request_slot(page_number=2)
    assert manager.daily_requests == 1  # Quota reset, should be able to make the second request


@pytest.mark.asyncio
async def test_check_and_acquire_request_slot_when_empty_request():
    """
    ❌ Test _check_and_acquire_request_slot with empty or invalid request input.
    """
    manager = GeminiUsageManager(max_daily_requests=1)

    # First request - should succeed
    await manager._check_and_acquire_request_slot(page_number=1)

    # Trying to make a request with no valid page number or empty request should raise an error
    with pytest.raises(ValueError, match="Invalid request"):
        await manager._check_and_acquire_request_slot(page_number=None)

@pytest.mark.parametrize("text, expected", [
    ("Short text", "Short text"),  # Text length is less than the truncation limit
    ("A " * 1000, "A " * 1000),  # No truncation needed, string is 2000 chars, smaller than the truncation limit
])
def test_truncate_text_valid_cases(text, expected):
    """
    ✅ Test _truncate_text when input text is within and exceeding the truncation limit.
    """
    manager = GeminiUsageManager()
    result = manager._truncate_text(text)
    assert result == expected, f"Expected {expected}, but got {result}"


@pytest.mark.parametrize("text, expected", [
    (None, None),  # Test with None, should return None
    ("", ""),  # Empty text, should return empty string
])
def test_truncate_text_invalid_cases(text, expected):
    """
    ❌ Test _truncate_text with invalid or edge case inputs.
    """
    manager = GeminiUsageManager()
    result = manager._truncate_text(text)
    assert result == expected, f"Expected {expected}, but got {result}"


@pytest.mark.parametrize("mock_data, expected", [
    (
            {"daily_requests": 100, "max_daily_requests": 100000, "concurrent_requests": 5,
             "max_concurrent_requests": 10},
            {
                "daily_requests": 100,
                "max_daily_requests": 100000,
                "concurrent_requests": 5,
                "max_concurrent_requests": 10,
                "request_history_length": 0,  # no history added yet in this case
                "last_reset_time": datetime.now().strftime('%Y-%m-%d')  # should match the current date
            }
    ),
])
def test_get_usage_summary_positive(mock_data, expected):
    """
    ✅ Test get_usage_summary with mock data and verify expected output.
    """
    manager = GeminiUsageManager()

    # Mock the internal data of the usage manager
    manager.daily_requests = mock_data['daily_requests']
    manager.max_daily_requests = mock_data['max_daily_requests']
    manager.concurrent_requests = mock_data['concurrent_requests']
    manager.max_concurrent_requests = mock_data['max_concurrent_requests']

    # Mock the request history (set it to an empty list)
    manager.request_history = []

    # Mock the last reset time to ensure that the current date is returned
    with patch.object(manager, 'last_reset_time', datetime.now()):
        result = manager.get_usage_summary()

    # Format the datetime object to a string for comparison
    result["last_reset_time"] = result["last_reset_time"].strftime('%Y-%m-%d')

    # Since we are checking the last reset time against the current date, we format the datetime
    expected["last_reset_time"] = datetime.now().strftime('%Y-%m-%d')

    assert result == expected, f"Expected {expected}, but got {result}"


@pytest.mark.parametrize("manager_state, expected", [
    (
            {"daily_requests": 0, "max_daily_requests": 100000, "concurrent_requests": 0,
             "max_concurrent_requests": 10},
            {
                "daily_requests": 0,
                "max_daily_requests": 100000,
                "concurrent_requests": 0,
                "max_concurrent_requests": 10,
                "request_history_length": 0,  # No history
                "last_reset_time": datetime.now().strftime('%Y-%m-%d')  # should match the current date
            }
    ),
])
def test_get_usage_summary_negative(manager_state, expected):
    """
    ❌ Test get_usage_summary with zero usage (no requests made yet).
    """
    manager = GeminiUsageManager()

    # Set the manager state to simulate a scenario where no requests have been made
    manager.daily_requests = manager_state['daily_requests']
    manager.max_daily_requests = manager_state['max_daily_requests']
    manager.concurrent_requests = manager_state['concurrent_requests']
    manager.max_concurrent_requests = manager_state['max_concurrent_requests']

    # Mock the request history (empty history since no requests have been made)
    manager.request_history = []

    # Mock the last reset time to ensure that the current date is returned
    with patch.object(manager, 'last_reset_time', datetime.now()):
        result = manager.get_usage_summary()

    # Format the datetime object to a string for comparison
    result["last_reset_time"] = result["last_reset_time"].strftime('%Y-%m-%d')

    # Since we are checking the last reset time against the current date, we format the datetime
    expected["last_reset_time"] = datetime.now().strftime('%Y-%m-%d')

    assert result == expected, f"Expected {expected}, but got {result}"


@pytest.mark.parametrize("manager_state, expected", [
    (
            {"daily_requests": 0, "max_daily_requests": 100000, "concurrent_requests": 0,
             "max_concurrent_requests": 10},
            {
                "daily_requests": 0,
                "max_daily_requests": 100000,
                "concurrent_requests": 0,
                "max_concurrent_requests": 10,
                "request_history_length": 0,  # No history
                "last_reset_time": datetime.now().strftime('%Y-%m-%d')  # should match the current date
            }
    ),
])
def test_get_usage_summary_with_reset(manager_state, expected):
    """
    ❌ Test get_usage_summary after the reset time.
    """
    manager = GeminiUsageManager()

    # Set the manager state to simulate a scenario where no requests have been made
    manager.daily_requests = manager_state['daily_requests']
    manager.max_daily_requests = manager_state['max_daily_requests']
    manager.concurrent_requests = manager_state['concurrent_requests']
    manager.max_concurrent_requests = manager_state['max_concurrent_requests']

    # Mock the request history (empty history since no requests have been made)
    manager.request_history = []

    # Mock the last reset time to simulate a reset
    reset_time = datetime(2025, 1, 1)  # A fixed past reset time
    with patch.object(manager, 'last_reset_time', reset_time):
        result = manager.get_usage_summary()

    # Format the datetime object to a string for comparison
    result["last_reset_time"] = result["last_reset_time"].strftime('%Y-%m-%d')

    # Since we are checking the last reset time against a fixed date, we use that date
    expected["last_reset_time"] = reset_time.strftime('%Y-%m-%d')

    assert result == expected, f"Expected {expected}, but got {result}"


@pytest.mark.asyncio
async def test_release_request_slot_success():
    """
    ✅ Test release_request_slot method when there are no errors.
    """
    # Initialize GeminiUsageManager with mock data
    manager = GeminiUsageManager()
    manager.concurrent_requests = 5  # Mock some concurrent requests

    # Mock the asyncio lock to not actually acquire it
    with patch.object(manager, '_request_lock', MagicMock()):
        # Call the release_request_slot method
        await manager.release_request_slot()

        # Check if concurrent_requests was decremented correctly
        assert manager.concurrent_requests == 4, f"Expected 4, but got {manager.concurrent_requests}"


@pytest.mark.asyncio
async def test_release_request_slot_error_handling():
    """
    Test release_request_slot method when an exception occurs.
    """
    manager = GeminiUsageManager()
    manager.concurrent_requests = 5  # Mock some concurrent requests

    # Patch the log_warning method to verify it gets called
    with patch('backend.app.utils.helpers.gemini_usage_manager.log_warning') as mock_log_warning:
        # Simulate an exception inside the _request_lock acquire method
        # Patch the acquire method to raise an exception
        with patch.object(manager._request_lock, 'acquire', side_effect=Exception("Test exception")):
            # Call the release_request_slot method which will trigger the exception
            await manager.release_request_slot()

        # Ensure the log_warning method was called to log the error
        mock_log_warning.assert_called_once_with("[GEMINI] Error releasing request slot: Test exception")

        # Check if concurrent_requests was reset to 0 after the exception
        assert manager.concurrent_requests == 0, f"Expected 0, but got {manager.concurrent_requests}"