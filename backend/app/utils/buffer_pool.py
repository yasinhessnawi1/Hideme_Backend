import time
import logging
from typing import Optional
from backend.app.utils.synchronization_utils import AsyncTimeoutLock, LockPriority

# Configure logger
logger = logging.getLogger(__name__)


class BufferPool:
    """
    A memory buffer pool that manages allocation and deallocation of memory buffers.
    Uses AsyncTimeoutLock for thread-safe operations with timeout capabilities.
    """

    def __init__(self, max_pool_size_mb: int = 100):
        self.max_pool_size = max_pool_size_mb * 1024 * 1024
        self.buffers = {}
        self.total_size = 0
        # Replace simple lock with enhanced AsyncTimeoutLock
        self.lock = AsyncTimeoutLock("buffer_pool_lock", priority=LockPriority.MEDIUM)
        self.last_cleanup = time.time()
        self.cleanup_interval = 60
        logger.info(f"BufferPool initialized with max size: {max_pool_size_mb}MB")

    async def get_buffer(self, size: int) -> Optional[memoryview]:
        """
        Acquire a buffer of the specified size from the pool.

        Args:
            size: Size of the buffer in bytes

        Returns:
            A memoryview object or None if allocation failed
        """
        try:
            logger.debug(f"Attempting to acquire lock for get_buffer(size={size})")

            # Fixed lock acquisition pattern
            async with self.lock.acquire_timeout():
                logger.debug(f"Lock acquired for get_buffer(size={size})")

                # Check if we need to run cleanup
                current_time = time.time()
                if current_time - self.last_cleanup > self.cleanup_interval:
                    await self._cleanup_unused_buffers()
                    self.last_cleanup = current_time

                # Check if buffer of required size exists
                if size in self.buffers and self.buffers[size]:
                    buffer = self.buffers[size].pop()
                    logger.debug(f"Reusing existing buffer of size {size}")
                    return buffer

                # Check if we have enough space for a new buffer
                if self.total_size + size > self.max_pool_size:
                    logger.warning(f"Cannot allocate buffer of size {size}, pool limit reached")
                    return None

                # Allocate new buffer
                try:
                    new_buffer = memoryview(bytearray(size))
                    self.total_size += size
                    logger.debug(f"Allocated new buffer of size {size}, total pool size: {self.total_size}")
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

        try:
            logger.debug(f"Attempting to acquire lock for release_buffer(size={size})")

            # Fixed lock acquisition pattern
            async with self.lock.acquire_timeout():
                logger.debug(f"Lock acquired for release_buffer(size={size})")

                if size not in self.buffers:
                    self.buffers[size] = []

                self.buffers[size].append(buffer)
                logger.debug(f"Buffer of size {size} returned to pool")
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

        # Calculate how much we need to free up (target: free up 20% of the pool)
        target_reduction = int(self.max_pool_size * 0.2)
        freed_up = 0

        # Sort buffer sizes from largest to smallest for efficient cleanup
        for size in sorted(self.buffers.keys(), reverse=True):
            buffer_list = self.buffers[size]

            while buffer_list and freed_up < target_reduction:
                buffer = buffer_list.pop()
                self.total_size -= size
                freed_up += size
                logger.debug(f"Cleaned up buffer of size {size}, freed so far: {freed_up}")

            # Remove empty lists
            if not buffer_list:
                del self.buffers[size]

        logger.info(f"Buffer cleanup completed. Freed up {freed_up} bytes, current pool size: {self.total_size}")

    async def clear_all_buffers(self) -> None:
        """
        Clear all buffers from the pool.
        """
        try:
            logger.debug("Attempting to acquire lock for clear_all_buffers()")

            # Fixed lock acquisition pattern
            async with self.lock.acquire_timeout():
                logger.debug("Lock acquired for clear_all_buffers()")
                self.buffers.clear()
                self.total_size = 0
                logger.info("All buffers cleared from pool")
        except TimeoutError:
            logger.warning("Failed to acquire lock for clearing all buffers")
        except Exception as e:
            logger.error(f"Unexpected error in clear_all_buffers: {str(e)}")