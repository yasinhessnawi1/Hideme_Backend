import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List
from weakref import WeakKeyDictionary

from backend.app.utils.logging.logger import log_warning

# Global cache for Gemini locks, keyed by event loop
_gemini_locks = WeakKeyDictionary()

class GeminiUsageManager:
    """
    Sophisticated manager for Gemini API usage tracking and rate limiting.

    Provides advanced controls for:
    - Daily request quotas
    - Concurrent request management
    - Adaptive request spacing
    - Comprehensive usage tracking
    """

    def __init__(
        self,
        max_daily_requests: int = 100000,  # Adjust based on Gemini API plan
        max_concurrent_requests: int = 10,
        request_delay: float = 0.1,  # Minimum delay between API calls
        text_truncation_limit: int = 10000  # Max characters per API call
    ):
        """
        Initialize Gemini API usage tracking with intelligent controls.

        Args:
            max_daily_requests: Maximum number of daily API calls.
            max_concurrent_requests: Maximum simultaneous API requests.
            request_delay: Minimum delay between API calls.
            text_truncation_limit: Maximum text length per API request.
        """
        self.daily_requests = 0
        self.max_daily_requests = max_daily_requests
        self.concurrent_requests = 0
        self.max_concurrent_requests = max_concurrent_requests
        self.request_delay = request_delay
        self.text_truncation_limit = text_truncation_limit

        self.last_reset_time = datetime.now()
        self._last_request_time = datetime.now()

        # Usage tracking
        self.request_history = []

    @property
    def request_lock(self) -> asyncio.Lock:
        """
        Lazily obtain an asyncio.Lock bound to the current event loop.
        """
        loop = asyncio.get_running_loop()
        if loop not in _gemini_locks:
            _gemini_locks[loop] = asyncio.Lock()
        return _gemini_locks[loop]

    async def manage_page_processing(
        self,
        full_text: str,
        requested_entities: Optional[List[str]] = None,
        page_number: Optional[int] = None
    ) -> Optional[str]:
        """
        Intelligently manage Gemini API request for a single page of text.

        Args:
            full_text: Complete text of the page.
            requested_entities: (Optional) List of requested entities.
            page_number: Page number for logging and tracking.

        Returns:
            Truncated text for API processing or None if processing is blocked.
        """
        if full_text is None:
            return None
        if not full_text:
            return ""
        try:
            await self._check_and_acquire_request_slot(page_number)
            processed_text = self._truncate_text(full_text)
            return processed_text
        except ValueError as ve:
            log_warning(f"[GEMINI] Page {page_number} processing blocked: {ve}")
            return None

    async def _check_and_acquire_request_slot(self, page_number: Optional[int] = None):
        """
        Check and acquire a request slot with rate limiting.

        Args:
            page_number: Page number for detailed logging.

        Raises:
            ValueError: if page_number is None or rate limits are exceeded.
        """
        if page_number is None:
            raise ValueError("Invalid request")
        async with self.request_lock:
            current_time = datetime.now()
            # Reset daily counter if a day has passed.
            if (current_time - self.last_reset_time).days >= 1:
                self.daily_requests = 0
                self.last_reset_time = current_time
                self.request_history = []

            if self.daily_requests >= self.max_daily_requests:
                raise ValueError(f"Daily Gemini API request quota ({self.max_daily_requests}) exceeded")
            if self.concurrent_requests >= self.max_concurrent_requests:
                raise ValueError(f"Maximum concurrent Gemini requests ({self.max_concurrent_requests}) reached")

            # Enforce minimum delay between requests.
            time_since_last_request = (current_time - self._last_request_time).total_seconds()
            if time_since_last_request < self.request_delay:
                await asyncio.sleep(self.request_delay - time_since_last_request)

            # Update tracking metrics.
            self.daily_requests += 1
            self.concurrent_requests += 1
            self._last_request_time = datetime.now()
            self.request_history.append({
                "timestamp": current_time,
                "page_number": page_number,
                "daily_requests": self.daily_requests
            })

    def _truncate_text(self, text: str) -> Optional[str]:
        """
        Intelligently truncate text for API processing.

        Args:
            text: Full text to process.

        Returns:
            Truncated text suitable for API processing.
        """
        if text is None:
            return None
        if len(text) <= self.text_truncation_limit:
            return text
        truncated_text = text[:self.text_truncation_limit]
        last_space = truncated_text.rfind(' ')
        return truncated_text[:last_space] if last_space != -1 else truncated_text

    def get_usage_summary(self) -> Dict[str, Any]:
        """
        Generate a comprehensive summary of Gemini API usage.

        Returns:
            Dictionary with detailed usage statistics.
        """
        return {
            "daily_requests": self.daily_requests,
            "max_daily_requests": self.max_daily_requests,
            "concurrent_requests": self.concurrent_requests,
            "max_concurrent_requests": self.max_concurrent_requests,
            "request_history_length": len(self.request_history),
            "last_reset_time": self.last_reset_time
        }

    async def release_request_slot(self):
        """
        Release a Gemini API request slot.
        """
        try:
            async with self.request_lock:
                self.concurrent_requests = max(0, self.concurrent_requests - 1)
        except Exception as e:
            log_warning(f"[GEMINI] Error releasing request slot: {e}")
            self.concurrent_requests = 0

# Global usage manager with default configuration.
gemini_usage_manager = GeminiUsageManager()
