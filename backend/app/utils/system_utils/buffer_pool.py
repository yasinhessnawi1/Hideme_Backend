import time
import logging
import threading
from typing import Optional
from backend.app.utils.system_utils.synchronization_utils import AsyncTimeoutLock, LockPriority

# Configure logger
logger = logging.getLogger(__name__)

# Define a threshold (in bytes) below which buffers are considered "small"
SMALL_BUFFER_THRESHOLD = 64 * 1024  # 64 KB

class BufferPool:
    """
    A memory buffer pool that manages allocation and deallocation of memory buffers.
    Utilizes asynchronous timeout locks for thread-safe operations with timeout capabilities for large buffers.
    Small buffers are managed using thread-local storage to reduce locking overhead.

    Attributes:
        max_pool_size (int): Maximum pool size in bytes.
        total_size (int): Total size of allocated large buffers.
        buffers (dict): Global pool for large buffers, keyed by size.
        _thread_local (threading.local): Thread-local storage for small buffers.
        _lock (Optional[AsyncTimeoutLock]): Lazy initialized asynchronous timeout lock for global pool operations.
        last_cleanup (float): Timestamp of the last cleanup operation.
        cleanup_interval (int): Time interval in seconds between cleanup operations.
    """

    def __init__(self, max_pool_size_mb: int = 100):
        """
        Initialize the BufferPool instance.

        Args:
            max_pool_size_mb (int): Maximum pool size in megabytes. Defaults to 100 MB.
        """
        self.max_pool_size = max_pool_size_mb * 1024 * 1024
        self.buffers = {}       # Global pool for large buffers
        self.total_size = 0
        # Do not initialize the lock here; it will be lazily created when first needed.
        self._lock = None
        self.last_cleanup = time.time()
        self.cleanup_interval = 60  # seconds
        logger.info(f"BufferPool initialized with max size: {max_pool_size_mb}MB")
        # Initialize thread-local storage for small buffers
        self._thread_local = threading.local()
        if not hasattr(self._thread_local, 'buffers'):
            self._thread_local.buffers = {}

    @property
    def lock(self) -> AsyncTimeoutLock:
        """
        Lazy initialization of the asynchronous timeout lock.

        Returns:
            AsyncTimeoutLock: The lock for managing access to the global buffer pool.
        """
        if self._lock is None:
            try:
                self._lock = AsyncTimeoutLock("buffer_pool_lock", priority=LockPriority.MEDIUM)
                logger.debug("AsyncTimeoutLock lazily initialized")
            except Exception as e:
                logger.error(f"Failed to initialize AsyncTimeoutLock: {e}")
                raise
        return self._lock

    async def get_buffer(self, size: int) -> Optional[memoryview]:
        """
        Acquire a buffer of the specified size from the pool.

        For small buffers (below threshold), thread-local storage is used without global locking.
        For large buffers, the global pool is accessed with an asynchronous timeout lock.

        Args:
            size (int): The desired size of the buffer in bytes.

        Returns:
            Optional[memoryview]: A memoryview object if allocation is successful; otherwise, None.
        """
        if size < SMALL_BUFFER_THRESHOLD:
            return self._get_small_buffer(size)

        try:
            logger.debug(f"Attempting to acquire lock for get_buffer(size={size})")
            async with self.lock.acquire_timeout():
                logger.debug(f"Lock acquired for get_buffer(size={size})")
                await self._maybe_cleanup_buffers()
                # Reuse an existing large buffer if available.
                if size in self.buffers and self.buffers[size]:
                    buf = self.buffers[size].pop()
                    logger.debug(f"Reusing existing large buffer of size {size}")
                    return buf
                # Check pool capacity before allocating a new buffer.
                if self.total_size + size > self.max_pool_size:
                    logger.warning(f"Cannot allocate buffer of size {size}; pool limit reached (current total: {self.total_size})")
                    return None
                return self._allocate_large_buffer(size)
        except TimeoutError:
            logger.warning("Failed to acquire buffer pool lock within timeout in get_buffer")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in get_buffer for size {size}: {e}")
            return None

    def _get_small_buffer(self, size: int) -> Optional[memoryview]:
        """
        Allocate or reuse a small buffer (size below threshold) from thread-local storage.

        Args:
            size (int): The size of the buffer in bytes.

        Returns:
            Optional[memoryview]: A memoryview object if successful; otherwise, None.
        """
        try:
            local_buffers = self._thread_local.buffers
            if size in local_buffers and local_buffers[size]:
                buf = local_buffers[size].pop()
                logger.debug(f"Reusing small buffer of size {size} from thread-local storage")
                return buf
            new_buf = memoryview(bytearray(size))
            logger.debug(f"Allocated new small buffer of size {size} in thread-local storage")
            return new_buf
        except MemoryError as mem_err:
            logger.error(f"MemoryError while allocating small buffer of size {size}: {mem_err}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in _get_small_buffer for size {size}: {e}")
            return None

    def _allocate_large_buffer(self, size: int) -> Optional[memoryview]:
        """
        Allocate a new large buffer and update the pool's total size.

        Args:
            size (int): The size of the buffer in bytes.

        Returns:
            Optional[memoryview]: A memoryview object if successful; otherwise, None.
        """
        try:
            new_buf = memoryview(bytearray(size))
            self.total_size += size
            logger.debug(f"Allocated new large buffer of size {size}, updated pool size: {self.total_size}")
            return new_buf
        except MemoryError as mem_err:
            logger.error(f"MemoryError while allocating large buffer of size {size}: {mem_err}")
            return None
        except Exception as alloc_err:
            logger.error(f"Unexpected error while allocating large buffer of size {size}: {alloc_err}")
            return None

    async def _maybe_cleanup_buffers(self) -> None:
        """
        Check if cleanup is due and perform it if necessary.
        """
        current_time = time.time()
        if current_time - self.last_cleanup > self.cleanup_interval:
            try:
                await self._cleanup_unused_buffers()
            except Exception as cleanup_err:
                logger.error(f"Error during cleanup of buffers: {cleanup_err}")
            self.last_cleanup = current_time

    async def release_buffer(self, buffer: memoryview) -> bool:
        """
        Return a buffer to the pool for reuse.

        For small buffers, the buffer is returned to thread-local storage.
        For large buffers, the buffer is returned to the global pool under lock protection.

        Args:
            buffer (memoryview): The buffer to be released.

        Returns:
            bool: True if the buffer was successfully released; otherwise, False.
        """
        if buffer is None:
            logger.warning("Attempted to release a None buffer")
            return False

        size = buffer.nbytes

        if size < SMALL_BUFFER_THRESHOLD:
            try:
                local_buffers = self._thread_local.buffers
                if size not in local_buffers:
                    local_buffers[size] = []
                local_buffers[size].append(buffer)
                logger.debug(f"Buffer of size {size} stored in thread-local storage")
                return True
            except Exception as e:
                logger.error(f"Unexpected error in releasing small buffer of size {size}: {e}")
                return False

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
            logger.warning(f"Failed to acquire lock for releasing large buffer of size {size}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in release_buffer for size {size}: {e}")
            return False

    async def _cleanup_unused_buffers(self) -> None:
        """
        Clean up unused buffers when the pool is nearing its capacity.
        This method should be called with the lock already acquired.

        It attempts to free up at least 20% of the maximum pool size.
        """
        logger.info("Starting cleanup of unused buffers")
        target_reduction = int(self.max_pool_size * 0.2)
        freed_up = 0

        for size in sorted(list(self.buffers.keys()), reverse=True):
            buffer_list = self.buffers[size]
            while buffer_list and freed_up < target_reduction:
                discarded_buffer = buffer_list.pop()
                self.total_size -= size
                freed_up += size
                logger.debug(f"Cleaned up buffer: {discarded_buffer} of size {size}, freed so far: {freed_up}")

            if not buffer_list:
                del self.buffers[size]

        logger.info(f"Buffer cleanup completed. Freed up {freed_up} bytes, current pool size: {self.total_size}")

    async def clear_all_buffers(self) -> None:
        """
        Clear all buffers from the global pool.

        This operation is performed under the protection of the asynchronous timeout lock.
        """
        try:
            logger.debug("Attempting to acquire lock for clear_all_buffers")
            async with self.lock.acquire_timeout():
                logger.debug("Lock acquired for clear_all_buffers")
                self.buffers.clear()
                self.total_size = 0
                logger.info("All large buffers cleared from the pool")
        except TimeoutError:
            logger.warning("Failed to acquire lock for clearing all buffers")
        except Exception as e:
            logger.error(f"Unexpected error in clear_all_buffers: {e}")