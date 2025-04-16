import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock

import pytest

# Import the module to be tested
from backend.app.utils.helpers.gemini_usage_manager import (
    GeminiUsageManager,
    _gemini_locks
)


# === GeminiUsageManager Initialization Tests === #
class TestGeminiUsageManagerInit(unittest.TestCase):
    """Test cases for GeminiUsageManager initialization."""

    def test_init_with_default_values(self):
        """Test initialization with default values."""
        manager = GeminiUsageManager()
        self.assertEqual(manager.daily_requests, 0)
        self.assertEqual(manager.max_daily_requests, 100000)
        self.assertEqual(manager.concurrent_requests, 0)
        self.assertEqual(manager.max_concurrent_requests, 10)
        self.assertEqual(manager.request_delay, 0.1)
        self.assertEqual(manager.text_truncation_limit, 10000)
        self.assertIsInstance(manager.last_reset_time, datetime)
        self.assertIsInstance(manager._last_request_time, datetime)
        self.assertEqual(manager.request_history, [])

    def test_init_with_custom_values(self):
        """Test initialization with custom values."""
        manager = GeminiUsageManager(
            max_daily_requests=5000,
            max_concurrent_requests=5,
            request_delay=0.2,
            text_truncation_limit=5000
        )
        self.assertEqual(manager.daily_requests, 0)
        self.assertEqual(manager.max_daily_requests, 5000)
        self.assertEqual(manager.concurrent_requests, 0)
        self.assertEqual(manager.max_concurrent_requests, 5)
        self.assertEqual(manager.request_delay, 0.2)
        self.assertEqual(manager.text_truncation_limit, 5000)
        self.assertIsInstance(manager.last_reset_time, datetime)
        self.assertIsInstance(manager._last_request_time, datetime)
        self.assertEqual(manager.request_history, [])


# GeminiUsageManager Request Lock Tests
class TestGeminiUsageManagerRequestLock(unittest.IsolatedAsyncioTestCase):

    async def test_request_lock_creates_new_lock(self):
        """Test that request_lock creates a new lock if one doesn't exist."""
        # Clear the global locks' dictionary.
        _gemini_locks.clear()

        manager = GeminiUsageManager()
        # Get the lock normally.
        lock = manager.request_lock

        # Check that the lock is an asyncio.Lock.
        self.assertIsInstance(lock, asyncio.Lock)

    async def test_request_lock_reuses_existing_lock(self):
        """Test that request_lock reuses an existing lock for the same event loop."""
        loop = asyncio.get_running_loop()

        # Create a lock and inject it into the global cache.
        existing_lock = asyncio.Lock()
        _gemini_locks[loop] = existing_lock
        manager = GeminiUsageManager()
        lock = manager.request_lock

        # Verify that the returned lock is exactly the same as the cached lock.
        self.assertIs(lock, existing_lock)


# GeminiUsageManager Manage Page Processing Tests
@pytest.mark.asyncio
class TestGeminiUsageManagerManagePageProcessing:
    """Test cases for GeminiUsageManager.manage_page_processing method."""

    async def test_manage_page_processing_with_none_text(self):
        """Test manage_page_processing with None text returns None."""
        manager = GeminiUsageManager()

        result = await manager.manage_page_processing(None, ["PERSON"], 1)
        assert result is None

    async def test_manage_page_processing_with_empty_text(self):
        """Test manage_page_processing with empty text returns empty string without acquiring slot."""
        manager = GeminiUsageManager()

        # For empty text, the method returns "" immediately.
        result = await manager.manage_page_processing("", ["PERSON"], 1)
        assert result == ""

    async def test_manage_page_processing_with_short_text(self):
        """Test manage_page_processing with text shorter than truncation limit."""
        manager = GeminiUsageManager(text_truncation_limit=100)

        # Replace _check_and_acquire_request_slot with a dummy async function.
        manager._check_and_acquire_request_slot = AsyncMock()
        text = "This is a short text."
        result = await manager.manage_page_processing(text, ["PERSON"], 1)

        # For short text, the result should be identical.
        assert result == text
        manager._check_and_acquire_request_slot.assert_called_once_with(1)

    async def test_manage_page_processing_with_long_text(self):
        """Test manage_page_processing with text longer than truncation limit."""

        # Create a manager with a low truncation limit.
        manager = GeminiUsageManager(text_truncation_limit=10)

        # Replace _check_and_acquire_request_slot with a dummy to avoid side effects.
        manager._check_and_acquire_request_slot = AsyncMock()
        text = "This is a long text that exceeds the truncation limit."
        result = await manager.manage_page_processing(text, ["PERSON"], 1)

        # Adjust expectation based on _truncate_text implementation:
        expected = "This is a"  # (if that's what _truncate_text returns)

        assert result == expected
        manager._check_and_acquire_request_slot.assert_called_once_with(1)

    async def test_manage_page_processing_with_acquisition_error(self):
        """Test manage_page_processing when _check_and_acquire_request_slot raises an error."""
        manager = GeminiUsageManager()

        # Set _check_and_acquire_request_slot to raise ValueError.
        manager._check_and_acquire_request_slot = AsyncMock(side_effect=ValueError("Rate limit exceeded"))

        with patch('backend.app.utils.helpers.gemini_usage_manager.log_warning') as mock_log_warning:
            result = await manager.manage_page_processing("Test text", ["PERSON"], 1)
            assert result is None

            mock_log_warning.assert_called_once()
            assert "Page 1 processing blocked" in mock_log_warning.call_args[0][0]


# GeminiUsageManager Check And Acquire Request Slot Tests
@pytest.mark.asyncio
class TestGeminiUsageManagerCheckAndAcquireRequestSlot:
    """Test cases for GeminiUsageManager._check_and_acquire_request_slot method."""

    async def test_check_and_acquire_request_slot_with_none_page_number(self):
        """Test _check_and_acquire_request_slot with None page number raises ValueError."""
        manager = GeminiUsageManager(request_delay=0)  # Avoid sleep delay.

        with pytest.raises(ValueError) as excinformation:
            await manager._check_and_acquire_request_slot(None)

        assert "Invalid request" in str(excinformation.value)

    async def test_check_and_acquire_request_slot_daily_reset(self):
        """Test _check_and_acquire_request_slot resets daily count if a day has passed."""
        manager = GeminiUsageManager(request_delay=0)
        manager.daily_requests = 50
        manager.last_reset_time = datetime.now() - timedelta(days=1, minutes=5)
        manager.request_history = [
            {"timestamp": datetime.now() - timedelta(days=1), "page_number": 1, "daily_requests": 50}]

        # Use the actual request_lock.
        await manager._check_and_acquire_request_slot(1)

        # After reset, daily_requests should be 1 (reset to 0 then incremented).
        assert manager.daily_requests == 1

        # Check last_reset_time is updated to a recent time.
        assert (datetime.now() - manager.last_reset_time).total_seconds() < 5

        # History should be cleared and then have 1 new record.
        assert len(manager.request_history) == 1

    async def test_check_and_acquire_request_slot_daily_limit_exceeded(self):
        """Test _check_and_acquire_request_slot raises error when daily limit is exceeded."""
        # Create a manager with a low daily limit and zero delay.
        manager = GeminiUsageManager(max_daily_requests=5, request_delay=0)
        manager.daily_requests = 5  # Already at limit.
        manager.last_reset_time = datetime.now()

        with pytest.raises(ValueError) as excinformation:
            await manager._check_and_acquire_request_slot(1)

        assert "Daily Gemini API request quota (5) exceeded" in str(excinformation.value)

    async def test_check_and_acquire_request_slot_concurrent_limit_exceeded(self):
        """Test _check_and_acquire_request_slot raises error when concurrent limit is exceeded."""
        manager = GeminiUsageManager(max_concurrent_requests=3, request_delay=0)
        manager.daily_requests = 10  # Below daily limit.
        manager.concurrent_requests = 3  # Already at concurrent limit.
        manager.last_reset_time = datetime.now()

        with pytest.raises(ValueError) as excinformation:
            await manager._check_and_acquire_request_slot(1)

        assert "Maximum concurrent Gemini requests (3) reached" in str(excinformation.value)

    async def test_check_and_acquire_request_slot_with_delay(self):
        """Test _check_and_acquire_request_slot awaits the required delay if needed."""
        delay = 0.2
        manager = GeminiUsageManager(request_delay=delay)
        manager.daily_requests = 10
        manager.concurrent_requests = 2
        manager.last_reset_time = datetime.now()
        manager._last_request_time = datetime.now()

        # Patch asyncio.sleep to capture the sleep time without actually waiting.
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            await manager._check_and_acquire_request_slot(1)
            mock_sleep.assert_called_once()
            sleep_time = mock_sleep.call_args[0][0]

            # Because _last_request_time is very recent, sleep_time may be between 0 and delay.
            assert 0 <= sleep_time <= delay

    async def test_check_and_acquire_request_slot_successful_acquisition(self):
        """Test _check_and_acquire_request_slot successfully increments counters."""
        manager = GeminiUsageManager(request_delay=0)
        initial_daily_requests = 10
        initial_concurrent_requests = 2
        manager.daily_requests = initial_daily_requests
        manager.concurrent_requests = initial_concurrent_requests
        manager.last_reset_time = datetime.now()
        manager._last_request_time = datetime.now() - timedelta(seconds=1)  # Ensure delay satisfied.
        initial_history_length = len(manager.request_history)

        await manager._check_and_acquire_request_slot(1)
        assert manager.daily_requests == initial_daily_requests + 1
        assert manager.concurrent_requests == initial_concurrent_requests + 1

        # _last_request_time should be updated recently.
        assert (datetime.now() - manager._last_request_time).total_seconds() < 1
        assert len(manager.request_history) == initial_history_length + 1
        latest_request = manager.request_history[-1]
        assert latest_request["page_number"] == 1
        assert latest_request["daily_requests"] == initial_daily_requests + 1


# === GeminiUsageManager Truncate Text Tests === #
class TestGeminiUsageManagerTruncateText(unittest.TestCase):
    """Test cases for GeminiUsageManager._truncate_text method."""

    def test_truncate_text_with_none_text(self):
        """Test _truncate_text with None text returns None."""
        manager = GeminiUsageManager()
        result = manager._truncate_text(None)

        self.assertIsNone(result)

    def test_truncate_text_within_limit(self):
        """Test _truncate_text returns text unchanged if within limit."""
        manager = GeminiUsageManager(text_truncation_limit=50)

        text = "Short text."
        result = manager._truncate_text(text)

        self.assertEqual(result, text)

    def test_truncate_text_exceeds_limit(self):
        """Test _truncate_text truncates text appropriately."""
        manager = GeminiUsageManager(text_truncation_limit=20)
        text = "This is a long text that should be truncated properly."
        result = manager._truncate_text(text)

        # The method truncates to 20 characters and then cuts at the last space.
        expected = text[:20]
        last_space = expected.rfind(' ')
        if last_space != -1:
            expected = expected[:last_space]

        self.assertEqual(result, expected)
