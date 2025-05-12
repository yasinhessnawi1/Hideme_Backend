import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock
import pytest

from backend.app.utils.helpers.gemini_usage_manager import (
    GeminiUsageManager,
    _gemini_locks,
)


# Test initialization of GeminiUsageManager default and custom settings
class TestGeminiUsageManagerInit(unittest.TestCase):

    # Test default constructor values
    def test_init_with_default_values(self):
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

    # Test constructor accepts custom parameters
    def test_init_with_custom_values(self):
        manager = GeminiUsageManager(
            max_daily_requests=5000,
            max_concurrent_requests=5,
            request_delay=0.2,
            text_truncation_limit=5000,
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


# Test that request_lock property creates or reuses asyncio.Lock per loop
class TestGeminiUsageManagerRequestLock(unittest.IsolatedAsyncioTestCase):

    # Test new lock is created when none exists
    async def test_request_lock_creates_new_lock(self):
        _gemini_locks.clear()

        manager = GeminiUsageManager()

        lock = manager.request_lock

        self.assertIsInstance(lock, asyncio.Lock)

    # Test existing lock is returned for same loop
    async def test_request_lock_reuses_existing_lock(self):
        loop = asyncio.get_running_loop()

        existing_lock = asyncio.Lock()

        _gemini_locks[loop] = existing_lock

        manager = GeminiUsageManager()

        lock = manager.request_lock

        self.assertIs(lock, existing_lock)


# Test manage_page_processing behavior under various text conditions
@pytest.mark.asyncio
class TestGeminiUsageManagerManagePageProcessing:

    # Test returns None if text is None
    async def test_manage_page_processing_with_none_text(self):
        manager = GeminiUsageManager()

        result = await manager.manage_page_processing(None, ["PERSON"], 1)

        assert result is None

    # Test returns empty string immediately when text is empty
    async def test_manage_page_processing_with_empty_text(self):
        manager = GeminiUsageManager()

        result = await manager.manage_page_processing("", ["PERSON"], 1)

        assert result == ""

    # Test short text bypasses truncation and acquires slot
    async def test_manage_page_processing_with_short_text(self):
        manager = GeminiUsageManager(text_truncation_limit=100)

        manager._check_and_acquire_request_slot = AsyncMock()

        text = "Short text."

        result = await manager.manage_page_processing(text, ["PERSON"], 1)

        assert result == text

        manager._check_and_acquire_request_slot.assert_called_once_with(1)

    # Test long text is truncated then acquires slot
    async def test_manage_page_processing_with_long_text(self):
        manager = GeminiUsageManager(text_truncation_limit=10)

        manager._check_and_acquire_request_slot = AsyncMock()

        text = "This is a long text that exceeds the truncation limit."

        result = await manager.manage_page_processing(text, ["PERSON"], 1)

        expected = manager._truncate_text(text)

        assert result == expected

        manager._check_and_acquire_request_slot.assert_called_once_with(1)

    # Test errors in slot acquisition are logged and return None
    async def test_manage_page_processing_with_acquisition_error(self):
        manager = GeminiUsageManager()

        manager._check_and_acquire_request_slot = AsyncMock(
            side_effect=ValueError("Rate limit exceeded")
        )

        with patch(
            "backend.app.utils.helpers.gemini_usage_manager.log_warning"
        ) as mock_log_warning:
            result = await manager.manage_page_processing("Test text", ["PERSON"], 1)

            assert result is None

            mock_log_warning.assert_called_once()

            assert "Page 1 processing blocked" in mock_log_warning.call_args[0][0]


# Test slot acquisition logic for daily and concurrent limits
@pytest.mark.asyncio
class TestGeminiUsageManagerCheckAndAcquireRequestSlot:

    # Test None page number raises ValueError
    async def test_check_and_acquire_request_slot_with_none_page_number(self):
        manager = GeminiUsageManager(request_delay=0)

        with pytest.raises(ValueError) as exc:
            await manager._check_and_acquire_request_slot(None)

        assert "Invalid request" in str(exc.value)

    # Test daily counters reset after 24 hours
    async def test_check_and_acquire_request_slot_daily_reset(self):
        manager = GeminiUsageManager(request_delay=0)

        manager.daily_requests = 50

        manager.last_reset_time = datetime.now() - timedelta(days=1, minutes=5)

        manager.request_history = [
            {
                "timestamp": datetime.now() - timedelta(days=1),
                "page_number": 1,
                "daily_requests": 50,
            }
        ]

        await manager._check_and_acquire_request_slot(1)

        assert manager.daily_requests == 1

        assert (datetime.now() - manager.last_reset_time).total_seconds() < 5

        assert len(manager.request_history) == 1

    # Test exceeding daily limit raises ValueError
    async def test_check_and_acquire_request_slot_daily_limit_exceeded(self):
        manager = GeminiUsageManager(max_daily_requests=5, request_delay=0)

        manager.daily_requests = 5

        manager.last_reset_time = datetime.now()

        with pytest.raises(ValueError) as exc:
            await manager._check_and_acquire_request_slot(1)

        assert "Daily Gemini API request quota (5) exceeded" in str(exc.value)

    # Test exceeding concurrent limit raises ValueError
    async def test_check_and_acquire_request_slot_concurrent_limit_exceeded(self):
        manager = GeminiUsageManager(max_concurrent_requests=3, request_delay=0)

        manager.daily_requests = 10

        manager.concurrent_requests = 3

        manager.last_reset_time = datetime.now()

        with pytest.raises(ValueError) as exc:
            await manager._check_and_acquire_request_slot(1)

        assert "Maximum concurrent Gemini requests (3) reached" in str(exc.value)

    # Test sleep delay is enforced appropriately
    async def test_check_and_acquire_request_slot_with_delay(self):
        delay = 0.2

        manager = GeminiUsageManager(request_delay=delay)

        manager.daily_requests = 10

        manager.concurrent_requests = 2

        manager.last_reset_time = datetime.now()

        manager._last_request_time = datetime.now()

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await manager._check_and_acquire_request_slot(1)

            mock_sleep.assert_called_once()

            sleep_time = mock_sleep.call_args[0][0]

            assert 0 <= sleep_time <= delay

    # Test successful slot acquisition increments counters
    async def test_check_and_acquire_request_slot_successful_acquisition(self):
        manager = GeminiUsageManager(request_delay=0)

        manager.daily_requests = 10

        manager.concurrent_requests = 2

        manager.last_reset_time = datetime.now()

        manager._last_request_time = datetime.now() - timedelta(seconds=1)

        initial_history_length = len(manager.request_history)

        await manager._check_and_acquire_request_slot(1)

        assert manager.daily_requests == 11

        assert manager.concurrent_requests == 3

        assert (datetime.now() - manager._last_request_time).total_seconds() < 1

        assert len(manager.request_history) == initial_history_length + 1

        latest_request = manager.request_history[-1]

        assert latest_request["page_number"] == 1

        assert latest_request["daily_requests"] == 11


# Test text truncation helper method
class TestGeminiUsageManagerTruncateText(unittest.TestCase):

    # Test None input returns None
    def test_truncate_text_with_none_text(self):
        manager = GeminiUsageManager()

        result = manager._truncate_text(None)

        self.assertIsNone(result)

    # Test text under limit remains unchanged
    def test_truncate_text_within_limit(self):
        manager = GeminiUsageManager(text_truncation_limit=50)

        text = "Short text."

        result = manager._truncate_text(text)

        self.assertEqual(result, text)

    # Test text over limit is truncated at last space
    def test_truncate_text_exceeds_limit(self):
        manager = GeminiUsageManager(text_truncation_limit=20)

        text = "This is a long text that should be truncated properly."

        result = manager._truncate_text(text)

        expected = text[:20]

        last_space = expected.rfind(" ")

        if last_space != -1:
            expected = expected[:last_space]

        self.assertEqual(result, expected)
