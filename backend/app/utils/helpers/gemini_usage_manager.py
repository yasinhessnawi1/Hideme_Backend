"""
This module provides the GeminiUsageManager class, an advanced tool for tracking and managing the usage of
the Google Gemini API. It implements rate limiting, concurrent request control, adaptive request spacing,
and comprehensive usage tracking. The manager intelligently handles daily quotas, handles API request delays,
and truncates large texts for efficient processing.
"""

import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List
from weakref import WeakKeyDictionary

from backend.app.utils.logging.logger import log_warning

# Global cache for Gemini locks, keyed by event loop.
_gemini_locks = WeakKeyDictionary()


class GeminiUsageManager:
    """
    GeminiUsageManager is a sophisticated manager for tracking and rate limiting
    usage of the Gemini API.

    It provides advanced controls for:
    - Monitoring and enforcing daily request quotas.
    - Controlling the number of concurrent API requests.
    - Implementing a minimum delay between requests.
    - Truncating texts to meet API call limits.
    - Maintaining a detailed history of API requests.
    """

    def __init__(
            self,
            max_daily_requests: int = 100000,  # Adjust based on Gemini API plan.
            max_concurrent_requests: int = 10,
            request_delay: float = 0.1,
            text_truncation_limit: int = 10000  # Maximum characters allowed per API call.
    ):
        """
        Initialize GeminiUsageManager with intelligent controls for API usage.

        Args:
            max_daily_requests: Maximum number of daily API calls.
            max_concurrent_requests: Maximum simultaneous API requests.
            request_delay: Minimum delay (in seconds) between API calls.
            text_truncation_limit: Maximum text length per API request.
        """
        # Initialize the number of requests made today.
        self.daily_requests = 0
        # Set the maximum allowed daily requests.
        self.max_daily_requests = max_daily_requests
        # Initialize the current number of concurrent requests.
        self.concurrent_requests = 0
        # Set the maximum allowed concurrent requests.
        self.max_concurrent_requests = max_concurrent_requests
        # Set the minimum delay required between API requests.
        self.request_delay = request_delay
        # Set the text character limit for each API call.
        self.text_truncation_limit = text_truncation_limit

        # Record the time when the daily counter was last reset.
        self.last_reset_time = datetime.now()
        # Record the time when the last API request was made.
        self._last_request_time = datetime.now()

        # Initialize an empty list to track the history of requests.
        self.request_history = []

    @property
    def request_lock(self) -> asyncio.Lock:
        """
        Lazily obtain an asyncio.Lock bound to the current event loop.

        Returns:
            asyncio.Lock: The lock for synchronizing API requests.
        """
        # Get the currently running event loop.
        loop = asyncio.get_running_loop()
        # If the lock for the current event loop is not already in the global cache, create one.
        if loop not in _gemini_locks:
            _gemini_locks[loop] = asyncio.Lock()
        # Return the lock associated with the current event loop.
        return _gemini_locks[loop]

    async def manage_page_processing(
            self,
            full_text: str,
            requested_entities: Optional[List[str]] = None,
            page_number: Optional[int] = None
    ) -> Optional[str]:
        """
        Intelligently manage the Gemini API request for processing a single page of text.

        Args:
            full_text (str): Complete text of the page.
            requested_entities (Optional[List[str]]): List of requested entities (unused in processing here).
            page_number (Optional[int]): Page number for logging and tracking purposes.

        Returns:
            Optional[str]: The truncated text for API processing or None if processing is blocked.
        """
        # If full_text is None, immediately return None.
        if full_text is None:
            return None
        # If full_text is empty, return an empty string.
        if not full_text:
            return ""
        try:
            # Attempt to check and acquire a request slot using the page number.
            await self._check_and_acquire_request_slot(page_number)
            # Truncate the full text according to the text truncation limit.
            processed_text = self._truncate_text(full_text)
            # Return the processed (truncated) text.
            return processed_text
        except ValueError as ve:
            # Log a warning if processing is blocked due to rate limits or invalid page number.
            log_warning(f"[GEMINI] Page {page_number} processing blocked: {ve}")
            # Return None in case of a ValueError.
            return None

    async def _check_and_acquire_request_slot(self, page_number: Optional[int] = None):
        """
        Check the current usage and acquire a request slot with rate limiting.

        This method enforces:
        - Daily request quota reset (if a day has passed).
        - Maximum daily and concurrent request limits.
        - Minimum delay between API calls.

        Args:
            page_number (Optional[int]): Page number for detailed logging.

        Raises:
            ValueError: If the page_number is None or rate limits are exceeded.
        """
        # Raise an error if the page_number is missing.
        if page_number is None:
            raise ValueError("Invalid request")
        # Acquire the lock to ensure exclusive access to usage counters.
        async with self.request_lock:
            # Capture the current time.
            current_time = datetime.now()
            # Check if a full day has passed since the last reset.
            if (current_time - self.last_reset_time).days >= 1:
                # Reset the daily request counter.
                self.daily_requests = 0
                # Update the last reset time to the current time.
                self.last_reset_time = current_time
                # Clear the request history since it is a new day.
                self.request_history = []
            # If the daily requests exceed or equal the allowed maximum, raise an error.
            if self.daily_requests >= self.max_daily_requests:
                raise ValueError(f"Daily Gemini API request quota ({self.max_daily_requests}) exceeded")
            # If the number of concurrent requests exceeds or equals the allowed maximum, raise an error.
            if self.concurrent_requests >= self.max_concurrent_requests:
                raise ValueError(f"Maximum concurrent Gemini requests ({self.max_concurrent_requests}) reached")
            # Calculate the time elapsed since the last API request.
            time_since_last_request = (current_time - self._last_request_time).total_seconds()
            # If the elapsed time is less than the required delay, wait for the remaining delay duration.
            if time_since_last_request < self.request_delay:
                await asyncio.sleep(self.request_delay - time_since_last_request)
            # Increment the daily requests counter.
            self.daily_requests += 1
            # Increment the concurrent requests counter.
            self.concurrent_requests += 1
            # Update the last request time to the current time.
            self._last_request_time = datetime.now()
            # Append the current request details to the request history.
            self.request_history.append({
                "timestamp": current_time,
                "page_number": page_number,
                "daily_requests": self.daily_requests
            })

    def _truncate_text(self, text: str) -> Optional[str]:
        """
        Intelligently truncate text to ensure it meets the API processing limits.

        Args:
            text (str): The full text to process.

        Returns:
            Optional[str]: The truncated text suitable for API processing.
        """
        # If the input text is None, return None immediately.
        if text is None:
            return None
        # If the length of the text is within the allowed truncation limit, return it as is.
        if len(text) <= self.text_truncation_limit:
            return text
        # Otherwise, truncate the text to the defined limit.
        truncated_text = text[:self.text_truncation_limit]
        # Find the last space in the truncated text to avoid cutting in the middle of a word.
        last_space = truncated_text.rfind(' ')
        # If a space is found, return the text up to that space; else, return the truncated text.
        return truncated_text[:last_space] if last_space != -1 else truncated_text

    def get_usage_summary(self) -> Dict[str, Any]:
        """
        Generate a comprehensive summary of the current Gemini API usage.

        Returns:
            Dict[str, Any]: A dictionary containing detailed usage statistics.
        """
        # Build and return a dictionary summarizing key usage metrics.
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
        Release a Gemini API request slot, reducing the concurrent request count.

        This method should be called after an API request is completed.
        """
        try:
            # Acquire the lock to safely update the concurrent requests counter.
            async with self.request_lock:
                # Decrement the concurrent requests counter ensuring it does not drop below zero.
                self.concurrent_requests = max(0, self.concurrent_requests - 1)
        except Exception as e:
            # Log a warning in case of an error while releasing a request slot.
            log_warning(f"[GEMINI] Error releasing request slot: {e}")
            # Reset concurrent_requests to 0 if an error occurs.
            self.concurrent_requests = 0


# Instantiate a global GeminiUsageManager object with default settings.
gemini_usage_manager = GeminiUsageManager()
