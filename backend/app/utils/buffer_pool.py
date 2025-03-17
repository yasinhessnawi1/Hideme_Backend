import math
import time
import asyncio

class BufferPool:
    def __init__(self, max_pool_size_mb: int = 100):
        """
        Enhanced buffer pool with intelligent allocation and recycling.

        Args:
            max_pool_size_mb: Maximum memory allocated for the buffer pool in MB.
        """
        self.max_pool_size = max_pool_size_mb * 1024 * 1024  # Convert MB to bytes
        self.buffers = {}  # Mapping: buffer size -> list of available buffers
        self.total_size = 0  # Total size of buffers currently in pool (in bytes)
        self.lock = asyncio.Lock()
        self.last_cleanup = time.time()
        self.cleanup_interval = 60  # Cleanup every 60 seconds

    async def get_buffer(self, size: int) -> memoryview:
        """
        Retrieve an appropriately sized buffer from the pool or create a new one if needed.

        Args:
            size: The minimum required size of the buffer in bytes.

        Returns:
            A memoryview of a bytearray sized to the next power of 2 greater than or equal to 'size'.
        """
        async with self.lock:
            # Determine optimal buffer size (power of 2) for efficient reuse
            buffer_size = 2 ** (math.ceil(math.log2(size)))
            if buffer_size in self.buffers and self.buffers[buffer_size]:
                buffer = self.buffers[buffer_size].pop()
                if not self.buffers[buffer_size]:
                    del self.buffers[buffer_size]
                self.total_size -= buffer_size
                return buffer
            # No suitable buffer available; create a new one
            return memoryview(bytearray(buffer_size))

    async def return_buffer(self, buffer: memoryview) -> None:
        """
        Return a used buffer back to the pool for future reuse.

        Args:
            buffer: The buffer to be returned.
        """
        async with self.lock:
            buffer_size = len(buffer)
            # Ensure pool does not exceed the maximum allocated memory
            if self.total_size + buffer_size > self.max_pool_size:
                return
            if buffer_size not in self.buffers:
                self.buffers[buffer_size] = []
            self.buffers[buffer_size].append(buffer)
            self.total_size += buffer_size
            # Trigger periodic cleanup of unused buffers
            current_time = time.time()
            if current_time - self.last_cleanup > self.cleanup_interval:
                await self.cleanup_unused()
                self.last_cleanup = current_time

    async def cleanup_unused(self) -> int:
        """
        Clean up unused buffers from the pool to free memory.

        Returns:
            The total number of bytes freed during cleanup.
        """
        async with self.lock:
            target_size = int(self.max_pool_size * 0.8)  # Aim to reduce usage to 80% of max
            freed_bytes = 0
            if self.total_size <= target_size:
                return 0
            # Evict buffers starting from the largest size category
            for size in sorted(self.buffers.keys(), reverse=True):
                while self.buffers[size] and self.total_size > target_size:
                    self.buffers[size].pop()
                    self.total_size -= size
                    freed_bytes += size
                if not self.buffers.get(size):
                    self.buffers.pop(size, None)
                if self.total_size <= target_size:
                    break
            return freed_bytes
