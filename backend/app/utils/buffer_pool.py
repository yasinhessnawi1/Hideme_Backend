import time
import logging
import threading
from typing import Optional
from backend.app.utils.synchronization_utils import AsyncTimeoutLock, LockPriority

# Configure logger
logger = logging.getLogger(__name__)

# Define a threshold (in bytes) below which buffers are considered "small"
SMALL_BUFFER_THRESHOLD = 64 * 1024  # 64 KB

class BufferPool:
    """
    A memory buffer pool that manages allocation and deallocation of memory buffers.
    Uses AsyncTimeoutLock for thread-safe operations with timeout capabilities for large buffers.
    Small buffers are managed using thread-local storage to reduce locking overhead.
    """

    def __init__(self, max_pool_size_mb: int = 100):
        self.max_pool_size = max_pool_size_mb * 1024 * 1024
        self.buffers = {}       # Global pool for large buffers
        self.total_size = 0
        self.lock = AsyncTimeoutLock("buffer_pool_lock", priority=LockPriority.MEDIUM)
        self.last_cleanup = time.time()
        self.cleanup_interval = 60
        logger.info(f"BufferPool initialized with max size: {max_pool_size_mb}MB")
        # Initialize thread-local storage for small buffers
        self._thread_local = threading.local()
        if not hasattr(self._thread_local, 'buffers'):
            self._thread_local.buffers = {}

    async def get_buffer(self, size: int) -> Optional[memoryview]:
        """
        Acquire a buffer of the specified size from the pool.

        Args:
            size: Size of the buffer in bytes

        Returns:
            A memoryview object or None if allocation failed
        """
        # For small buffers, bypass global locking and use thread-local storage
        if size < SMALL_BUFFER_THRESHOLD:
            local_buffers = self._thread_local.buffers
            if size in local_buffers and local_buffers[size]:
                buffer = local_buffers[size].pop()
                logger.debug(f"Reusing small buffer of size {size} from thread-local storage")
                return buffer
            try:
                new_buffer = memoryview(bytearray(size))
                logger.debug(f"Allocated new small buffer of size {size} in thread-local storage")
                return new_buffer
            except MemoryError:
                logger.error(f"Memory error while allocating small buffer of size {size}")
                return None

        # For large buffers, use the global pool with the async lock
        try:
            logger.debug(f"Attempting to acquire lock for get_buffer(size={size})")
            async with self.lock.acquire_timeout():
                logger.debug(f"Lock acquired for get_buffer(size={size})")
                current_time = time.time()
                if current_time - self.last_cleanup > self.cleanup_interval:
                    await self._cleanup_unused_buffers()
                    self.last_cleanup = current_time

                if size in self.buffers and self.buffers[size]:
                    buffer = self.buffers[size].pop()
                    logger.debug(f"Reusing existing large buffer of size {size}")
                    return buffer

                if self.total_size + size > self.max_pool_size:
                    logger.warning(f"Cannot allocate buffer of size {size}, pool limit reached")
                    return None

                try:
                    new_buffer = memoryview(bytearray(size))
                    self.total_size += size
                    logger.debug(f"Allocated new large buffer of size {size}, total pool size: {self.total_size}")
                    return new_buffer
                except MemoryError:
                    logger.error(f"Memory error while allocating buffer of size {size}")
                    return None
        except TimeoutError:
            logger.warning("Failed to acquire buffer pool lock within timeout")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in get_buffer: {str(e)}")
            return None

    async def release_buffer(self, buffer: memoryview) -> bool:
        """
        Return a buffer to the pool for reuse.

        Args:
            buffer: The buffer to release

        Returns:
            True if the buffer was successfully released, False otherwise
        """
        if buffer is None:
            logger.warning("Attempted to release None buffer")
            return False

        size = buffer.nbytes

        # For small buffers, return to thread-local storage
        if size < SMALL_BUFFER_THRESHOLD:
            local_buffers = self._thread_local.buffers
            if size not in local_buffers:
                local_buffers[size] = []
            local_buffers[size].append(buffer)
            logger.debug(f"Buffer of size {size} stored in thread-local storage")
            return True

        # For large buffers, use the global pool with locking
        try:
            logger.debug(f"Attempting to acquire lock for release_buffer(size={size})")
            async with self.lock.acquire_timeout():
                logger.debug(f"Lock acquired for release_buffer(size={size})")
                if size not in self.buffers:
                    self.buffers[size] = []
                self.buffers[size].append(buffer)
                logger.debug(f"Large buffer of size {size} returned to pool")
                return True
        except TimeoutError:
            logger.warning(f"Failed to acquire lock for releasing buffer of size {size}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in release_buffer: {str(e)}")
            return False

    async def _cleanup_unused_buffers(self) -> None:
        """
        Clean up unused buffers when the pool is getting full.
        This method should be called with the lock already acquired.
        """
        logger.info("Starting cleanup of unused buffers")
        target_reduction = int(self.max_pool_size * 0.2)
        freed_up = 0

        for size in sorted(self.buffers.keys(), reverse=True):
            buffer_list = self.buffers[size]
            while buffer_list and freed_up < target_reduction:
                buffer = buffer_list.pop()
                self.total_size -= size
                freed_up += size
                logger.debug(f"Cleaned up buffer of size {size}, freed so far: {freed_up}")

            if not buffer_list:
                del self.buffers[size]

        logger.info(f"Buffer cleanup completed. Freed up {freed_up} bytes, current pool size: {self.total_size}")

    async def clear_all_buffers(self) -> None:
        """
        Clear all buffers from the pool.
        """
        try:
            logger.debug("Attempting to acquire lock for clear_all_buffers()")
            async with self.lock.acquire_timeout():
                logger.debug("Lock acquired for clear_all_buffers()")
                self.buffers.clear()
                self.total_size = 0
                logger.info("All large buffers cleared from pool")
        except TimeoutError:
            logger.warning("Failed to acquire lock for clearing all buffers")
        except Exception as e:
            logger.error(f"Unexpected error in clear_all_buffers: {str(e)}")