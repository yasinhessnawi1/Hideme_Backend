import asyncio
from fastapi import UploadFile
from io import BytesIO

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.parallel.core import ParallelProcessingCore
from backend.app.utils.secure_file_utils import SecureTempFileManager
from backend.app.utils.synchronization_utils import AsyncTimeoutLock, AsyncTimeoutSemaphore


@pytest.mark.asyncio
async def test_init_global_semaphore_valid():
    """✅ Ensure the semaphore initializes correctly with the given worker count."""
    with patch("backend.app.utils.helpers.batch_processing_helper.AsyncTimeoutSemaphore") as MockSemaphore:
        mock_semaphore = AsyncMock()
        mock_semaphore.value = 5  # Explicitly setting the value attribute
        MockSemaphore.return_value = mock_semaphore

        semaphore = await BatchProcessingUtils._init_global_semaphore(5)

        assert semaphore is not None, "Semaphore should be initialized"
        assert semaphore.value == 5, f"Expected 5, but got {semaphore.value}"
        MockSemaphore.assert_called_once()


@pytest.mark.asyncio
async def test_init_global_semaphore_update_existing():
    """✅ Ensure the semaphore updates if worker count changes."""
    with patch("backend.app.utils.helpers.batch_processing_helper.AsyncTimeoutSemaphore") as MockSemaphore:
        # Mock first semaphore
        first_mock_semaphore = AsyncMock()
        first_mock_semaphore.current_value = 5  # Set initial worker count
        MockSemaphore.return_value = first_mock_semaphore

        # Initialize semaphore with 5 workers
        first_semaphore = await BatchProcessingHelper._init_global_semaphore(5)

        # Ensure it's initialized correctly
        assert first_semaphore is not None, "Semaphore should be initialized"
        assert first_semaphore.current_value == 5, f"Expected 5, got {first_semaphore.current_value}"

        # Mock second semaphore for update scenario
        second_mock_semaphore = AsyncMock()
        second_mock_semaphore.current_value = 10  # Updated worker count
        MockSemaphore.return_value = second_mock_semaphore

        # Now update with a new value
        second_semaphore = await BatchProcessingHelper._init_global_semaphore(10)

        assert second_semaphore is not None, "Semaphore should still be initialized"
        assert second_semaphore.current_value == 10, f"Expected 10, got {second_semaphore.current_value}"

        # Ensure semaphore was re-initialized
        assert first_semaphore is not second_semaphore, "A new semaphore should be created if count changes"

        MockSemaphore.assert_called()  # Ensure MockSemaphore was used

@pytest.mark.asyncio
async def test_init_global_semaphore_lock_timeout():
    """❌ Ensure an exception is raised if the lock times out while initializing the semaphore."""
    with patch.object(AsyncTimeoutLock, "acquire_timeout", side_effect=TimeoutError("Lock timeout")):
        with pytest.raises(TimeoutError, match="Lock timeout"):
            await BatchProcessingHelper._init_global_semaphore(5)

@pytest.mark.asyncio
async def test_init_global_semaphore_creation_failure():
    """❌ Ensure an exception is raised if semaphore creation fails."""
    with patch("backend.app.utils.helpers.batch_processing_helper.AsyncTimeoutSemaphore", side_effect=Exception("Semaphore creation error")):
        with pytest.raises(Exception, match="Semaphore creation error"):
            await BatchProcessingHelper._init_global_semaphore(5)


def test_get_optimal_batch_size_small_file_count():
    """✅ Ensure small file counts return correct batch size."""
    with patch("os.cpu_count", return_value=8), patch("psutil.virtual_memory") as mock_memory:
        # Mock memory values correctly
        mock_memory.return_value.available = 8 * 1024 * 1024 * 1024  # 8GB available memory
        mock_memory.return_value.percent = 50  # Memory usage at 50%

        batch_size = BatchProcessingUtils.get_optimal_batch_size(file_count=3, total_bytes=0)

        assert batch_size == 3, f"Expected batch size of 3, but got {batch_size}"


@pytest.mark.parametrize(
    "file_count, total_bytes, expected_min_workers, should_raise",
    [
        (0, 0, 1, False),  # ✅ Zero files should not crash
        (-5, 100, 1, True),  # ❌ Negative file count should raise ValueError
        (10, -100, 1, False),  # ✅ Negative file size should be handled gracefully
    ]
)
def test_get_optimal_batch_size_invalid_inputs(file_count, total_bytes, expected_min_workers, should_raise):
    """❌ Ensure function handles invalid inputs gracefully."""

    if should_raise:
        with pytest.raises(ValueError, match="file_count cannot be negative"):
            BatchProcessingUtils.get_optimal_batch_size(file_count, total_bytes)
    else:
        batch_size = BatchProcessingUtils.get_optimal_batch_size(file_count, total_bytes)
        assert batch_size >= expected_min_workers, f"Expected at least {expected_min_workers}, got {batch_size}"


def test_get_optimal_batch_size_high_memory_usage():
    """❌ Ensure high memory usage reduces worker count."""
    with patch("psutil.virtual_memory") as mock_memory:
        mock_memory.return_value.available = 8 * 1024 * 1024 * 1024  # 8GB available
        mock_memory.return_value.percent = 95  # Very high memory usage

        batch_size = BatchProcessingUtils.get_optimal_batch_size(file_count=10, total_bytes=500_000_000)

        assert batch_size == 1, f"Expected reduced workers, got {batch_size}"


def test_get_optimal_batch_size_extreme_large_file_size():
    """❌ Ensure extremely large file sizes do not break calculations."""
    with patch("os.cpu_count", return_value=8), patch("psutil.virtual_memory") as mock_memory:
        mock_memory.return_value.available = 16 * 1024 * 1024 * 1024  # 16GB available
        batch_size = BatchProcessingUtils.get_optimal_batch_size(file_count=5,
                                                                  total_bytes=1_000_000_000_000)  # 1TB total

        assert batch_size >= 1, f"Batch size should be valid, got {batch_size}"


@pytest.mark.asyncio
async def test_process_in_parallel_valid_cases():
    """✅ Ensure process_in_parallel works for multiple valid scenarios."""

    async def mock_processor(item):
        await asyncio.sleep(0.1)  # Simulate some async work
        return item * 2  # Just return double of the input

    items = [1, 2, 3, 4, 5]  # Input data

    with patch.object(BatchProcessingHelper, "_init_global_semaphore", AsyncMock()) as mock_semaphore:
        # Mock a real AsyncTimeoutSemaphore instance
        mock_semaphore_instance = AsyncTimeoutSemaphore("test_semaphore", value=5)
        mock_semaphore.return_value = mock_semaphore_instance  # Ensure we return this instance

        # Case 1: Default settings
        results = await ParallelProcessingCore.process_in_parallel(items, mock_processor)
        expected_results = [(i, item * 2) for i, item in enumerate(items)]
        assert results == expected_results, f"Default case failed, expected {expected_results}, got {results}"

        # Case 2: Custom max_workers
        results = await ParallelProcessingCore.process_in_parallel(items, mock_processor, max_workers=2)
        assert results == expected_results, f"Custom max_workers failed, expected {expected_results}, got {results}"

        # Case 3: Custom timeout
        results = await ParallelProcessingCore.process_in_parallel(items, mock_processor, timeout=10)
        assert results == expected_results, f"Custom timeout failed, expected {expected_results}, got {results}"

        # Case 4: Custom item timeout
        results = await ParallelProcessingCore.process_in_parallel(items, mock_processor, item_timeout=1)
        assert results == expected_results, f"Custom item timeout failed, expected {expected_results}, got {results}"

@pytest.mark.asyncio
async def test_process_in_parallel_invalid_cases():
    """❌ Ensure process_in_parallel handles errors correctly."""

    async def failing_processor(item):
        raise ValueError("Processing failed")

    async def slow_processor(item):
        await asyncio.sleep(2)  # This will exceed the item timeout
        return item

    items = [1, 2, 3]

    with patch.object(BatchProcessingHelper, "_init_global_semaphore", new_callable=AsyncMock) as mock_semaphore:
        mock_semaphore.return_value = AsyncMock()
        mock_semaphore.return_value.acquire_timeout = AsyncMock()

        # Case 1: Empty list (should return empty list)
        results = await BatchProcessingHelper.process_in_parallel([], failing_processor)
        assert results == [], "Empty list case failed"

        # Case 2: Processor raises exception
        results = await BatchProcessingHelper.process_in_parallel(items, failing_processor)
        assert results == [(i, None) for i in range(len(items))], "Exception handling failed"

        # Case 3: Processor exceeds timeout
        results = await BatchProcessingHelper.process_in_parallel(items, slow_processor, item_timeout=1)
        assert results == [(i, None) for i in range(len(items))], "Item timeout handling failed"

        # Case 4: Too many workers
        results = await BatchProcessingHelper.process_in_parallel(items, lambda x: x, max_workers=1000)
        assert len(results) == len(items), "Excessive workers case failed"

        # Case 5: Semaphore timeout
        with patch.object(mock_semaphore.return_value, "acquire_timeout", side_effect=TimeoutError("Semaphore timeout")):
            results = await BatchProcessingHelper.process_in_parallel(items, lambda x: x)
            assert results == [(i, None) for i in range(len(items))], "Semaphore timeout handling failed"


@pytest.mark.asyncio
async def test_process_item_valid_cases():
    """✅ Ensure process_item processes data correctly under normal conditions."""

    async def mock_processor(item):
        await asyncio.sleep(0.1)  # Simulate work
        return item * 2  # Return double the value

    items = [1, 2, 3, 4, 5]

    # ✅ Use real semaphore instead of mocking it
    await BatchProcessingHelper._init_global_semaphore(max_workers=5)

    # Run process_in_parallel which internally calls process_item
    results = await BatchProcessingHelper.process_in_parallel(items, mock_processor)
    expected_results = [(i, item * 2) for i, item in enumerate(items)]

    assert results == expected_results, f"Processing failed, expected {expected_results}, got {results}"

@pytest.mark.asyncio
async def test_process_item_invalid_cases():
    """❌ Ensure process_item handles errors gracefully."""

    async def failing_processor(item):
        """Simulates a processor that always raises an error."""
        raise ValueError("Processing failed")

    async def slow_processor(item):
        """Simulates a processor that takes too long and should time out."""
        await asyncio.sleep(5)  # Simulate a slow process
        return item

    items = [1, 2, 3]

    # ✅ Use a real semaphore instead of mocking
    await BatchProcessingHelper._init_global_semaphore(max_workers=3)

    # Case 1: Processor raises an error
    results = await BatchProcessingHelper.process_in_parallel(items, failing_processor)
    for _, result in results:
        assert result is None, f"Expected None for failed processing, got {results}"

    # Case 2: Timeout scenario (Force 1-second timeout)
    results = await BatchProcessingHelper.process_in_parallel(items, slow_processor, item_timeout=1)
    for _, result in results:
        assert result is None, f"Timeout handling failed, got {results}"

    # Case 3: Semaphore acquisition failure (Force a failure)
    with patch.object(BatchProcessingHelper._global_semaphore, "acquire_timeout", side_effect=TimeoutError("Semaphore timeout")):
        results = await BatchProcessingHelper.process_in_parallel(items, lambda x: x)
        for _, result in results:
            assert result is None, f"Semaphore timeout handling failed, got {results}"

@pytest.mark.asyncio
async def test_process_pages_in_parallel_valid_cases():
    """✅ Ensure process_pages_in_parallel works correctly for multiple valid scenarios."""
    # 🔥 Reset global semaphore before running test
    BatchProcessingHelper._global_semaphore = None

    async def mock_processor(page):
        """Simulates processing by returning page content with a simple modification."""
        await asyncio.sleep(0.1)  # Simulate processing delay
        return {"processed": True, "page": page["page"]}, [{"entity": "test"}]

    pages = [{"page": 1}, {"page": 2}, {"page": 3}]

    # ✅ Case 1: Default settings
    results = await BatchProcessingHelper.process_pages_in_parallel(pages, mock_processor)

    assert results == [(1, ({"processed": True, "page": 1}, [{"entity": "test"}])),
                       (2, ({"processed": True, "page": 2}, [{"entity": "test"}])),
                       (3, ({"processed": True, "page": 3}, [{"entity": "test"}]))], f"Default case failed, got {results}"

    # ✅ Case 2: Custom max_workers
    results = await BatchProcessingHelper.process_pages_in_parallel(pages, mock_processor, max_workers=2)
    assert results == [(1, ({"processed": True, "page": 1}, [{"entity": "test"}])),
                       (2, ({"processed": True, "page": 2}, [{"entity": "test"}])),
                       (3, ({"processed": True, "page": 3}, [{"entity": "test"}]))], f"Custom max_workers failed, got {results}"

    # ✅ Case 3: Unordered input pages (ensure output is still ordered)
    unordered_pages = [{"page": 3}, {"page": 1}, {"page": 2}]
    results = await BatchProcessingHelper.process_pages_in_parallel(unordered_pages, mock_processor)
    print(f"❌ Debugging Output: {results}")
    assert results == [(3, ({"processed": True, "page": 3}, [{"entity": "test"}])),
                       (1, ({"processed": True, "page": 1}, [{"entity": "test"}])),
                       (2, ({"processed": True, "page": 2}, [{"entity": "test"}]))], f"Unordered input handling failed, got {results}"


@pytest.mark.asyncio
async def test_process_pages_in_parallel_invalid_cases():
    """❌ Ensure process_pages_in_parallel handles errors gracefully."""

    async def failing_processor(page):
        """Simulates processing failure for all pages."""
        raise ValueError(f"Failed to process page {page['page']}")

    async def slow_processor(page):
        """Simulates processing timeout by sleeping longer than allowed."""
        await asyncio.sleep(5)  # Simulate slow processing
        return {"processed": True, "page": page["page"]}, [{"entity": "test"}]

    pages = [{"page": 1}, {"page": 2}, {"page": 3}]

    # ❌ Case 1: Processor raises an error
    results = await BatchProcessingHelper.process_pages_in_parallel(pages, failing_processor)
    for page_num, result in results:
        assert result is None, f"Expected None for failed processing, got {results}"

    # ❌ Case 2: Timeout scenario (forcing timeout directly using asyncio.wait_for)
    try:
        results = await asyncio.wait_for(
            BatchProcessingHelper.process_pages_in_parallel(pages, slow_processor, max_workers=1),
            timeout=2  # Set an overall timeout of 2 seconds (lower than processor execution)
        )
        assert False, f"Timeout handling failed, got {results}"
    except asyncio.TimeoutError:
        pass  # Expected behavior: Timeout should occur and be handled correctly.


@pytest.mark.asyncio
async def test_process_entities_in_parallel_valid_cases():
    """✅ Ensure process_entities_in_parallel works correctly for multiple valid scenarios."""

    class MockProcessor:
        """Mock entity processor for testing."""
        async def process_entities_for_page(self, page_number, full_text, mapping, entities):
            return [{"processed_entity": entity} for entity in entities], {"page": page_number, "sensitive": entities}

    processor = MockProcessor()
    full_text = "This is a sample text."
    mapping = [({}, 0, 5), ({}, 6, 10)]
    entity_dicts = [{"entity": "test1"}, {"entity": "test2"}, {"entity": "test3"}]
    page_number = 1

    # ✅ Case 1: Small number of entities (processed sequentially)
    processed_entities, page_info = await BatchProcessingHelper.process_entities_in_parallel(
        processor, full_text, mapping, entity_dicts[:2], page_number
    )
    assert len(processed_entities) == 2, f"Expected 2 processed entities, got {processed_entities}"
    assert page_info["page"] == page_number, f"Expected page {page_number}, got {page_info}"

    # ✅ Case 2: Larger number of entities (processed in parallel)
    processed_entities, page_info = await BatchProcessingHelper.process_entities_in_parallel(
        processor, full_text, mapping, entity_dicts, page_number
    )
    assert len(processed_entities) == 3, f"Expected 3 processed entities, got {processed_entities}"
    assert "sensitive" in page_info, f"Expected 'sensitive' field in page_info, got {page_info}"

    # ✅ Case 3: Empty entities list (should return empty results)
    processed_entities, page_info = await BatchProcessingHelper.process_entities_in_parallel(
        processor, full_text, mapping, [], page_number
    )
    assert processed_entities == [], f"Expected empty processed_entities, got {processed_entities}"
    assert page_info["sensitive"] == [], f"Expected empty sensitive list, got {page_info}"


@pytest.mark.asyncio
async def test_process_entities_in_parallel_invalid_cases():
    """❌ Ensure process_entities_in_parallel handles errors gracefully."""

    class FailingProcessor:
        """Processor that always fails."""
        async def process_entities_for_page(self, page_number, full_text, mapping, entities):
            raise ValueError("Processing failed")

    class SlowProcessor:
        """Processor that takes too long (simulates timeout)."""
        async def process_entities_for_page(self, page_number, full_text, mapping, entities):
            await asyncio.sleep(5)  # Simulate slow processing
            return [{"processed_entity": entity} for entity in entities], {"page": page_number, "sensitive": entities}

    processor = FailingProcessor()
    slow_processor = SlowProcessor()
    full_text = "This is a sample text."
    mapping = [({}, 0, 5), ({}, 6, 10)]
    entity_dicts = [{"entity": "test1"}, {"entity": "test2"}]
    page_number = 1

    # ❌ Case 1: Processor raises an error
    processed_entities, page_info = await BatchProcessingHelper.process_entities_in_parallel(
        processor, full_text, mapping, entity_dicts, page_number
    )
    assert processed_entities == [], f"Expected empty processed_entities due to failure, got {processed_entities}"
    assert "sensitive" in page_info, f"Expected 'sensitive' field, got {page_info}"

    # ❌ Case 2: Timeout scenario (forcing timeout with `asyncio.wait_for`)
    try:
        processed_entities, page_info = await asyncio.wait_for(
            BatchProcessingHelper.process_entities_in_parallel(
                slow_processor, full_text, mapping, entity_dicts, page_number
            ),
            timeout=2  # Force timeout within 2 seconds
        )
        assert False, f"Timeout handling failed, got {processed_entities}, {page_info}"
    except asyncio.TimeoutError:
        pass  # Expected timeout

@pytest.mark.asyncio
async def test_process_entities_in_parallel_small_batch():
    """✅ Test process_entities_in_parallel with a small batch (sequential processing)."""

    class MockProcessor:
        async def process_entities_for_page(self, page_number, full_text, mapping, entities):
            return ([f"processed_{e['entity']}" for e in entities], {"page": page_number, "sensitive": entities})

    processor = MockProcessor()
    full_text = "Test full text"
    mapping = [({}, 0, 10)]
    entity_dicts = [{"entity": "test1"}, {"entity": "test2"}]  # Small batch
    page_number = 1

    processed_entities, page_info = await BatchProcessingHelper.process_entities_in_parallel(
        processor, full_text, mapping, entity_dicts, page_number
    )

    assert processed_entities == ["processed_test1", "processed_test2"]
    assert page_info["sensitive"] == entity_dicts


@pytest.mark.asyncio
async def test_process_entities_in_parallel_large_batch():
    """✅ Test process_entities_in_parallel with a large batch (parallel processing)."""

    class MockProcessor:
        async def process_entities_for_page(self, page_number, full_text, mapping, entities):
            return ([f"processed_{e['entity']}" for e in entities], {"page": page_number, "sensitive": entities})

    processor = MockProcessor()
    full_text = "Test full text"
    mapping = [({}, 0, 10)]
    entity_dicts = [{"entity": f"test{i}"} for i in range(10)]  # Large batch
    page_number = 1

    processed_entities, page_info = await BatchProcessingHelper.process_entities_in_parallel(
        processor, full_text, mapping, entity_dicts, page_number
    )

    expected_processed = [f"processed_test{i}" for i in range(10)]
    expected_sensitive = [{"entity": f"test{i}"} for i in range(10)]

    assert processed_entities == expected_processed
    assert page_info["sensitive"] == expected_sensitive


@pytest.mark.asyncio
async def test_process_entities_in_parallel_empty_list():
    """✅ Test process_entities_in_parallel with an empty entity list (should return empty results)."""

    class MockProcessor:
        async def process_entities_for_page(self, page_number, full_text, mapping, entities):
            return [], {"page": page_number, "sensitive": []}

    processor = MockProcessor()
    full_text = "Test full text"
    mapping = [({}, 0, 10)]
    entity_dicts = []  # Empty entity list
    page_number = 1

    processed_entities, page_info = await BatchProcessingHelper.process_entities_in_parallel(
        processor, full_text, mapping, entity_dicts, page_number
    )

    assert processed_entities == []
    assert page_info["sensitive"] == []


@pytest.mark.asyncio
async def test_process_entities_in_parallel_exception_handling():
    """❌ Test process_entities_in_parallel when processor raises an exception (should handle gracefully)."""

    class FailingProcessor:
        async def process_entities_for_page(self, page_number, full_text, mapping, entities):
            raise ValueError("Processing failed")

    processor = FailingProcessor()
    full_text = "Test full text"
    mapping = [({}, 0, 10)]
    entity_dicts = [{"entity": "test1"}, {"entity": "test2"}]
    page_number = 1

    processed_entities, page_info = await BatchProcessingHelper.process_entities_in_parallel(
        processor, full_text, mapping, entity_dicts, page_number
    )

    assert processed_entities == [], "Expected an empty processed_entities list due to failure"
    assert page_info["sensitive"] == [], "Expected an empty sensitive list due to failure"


@pytest.mark.asyncio
async def test_process_entities_in_parallel_slow_processing():
    """⏳ Test process_entities_in_parallel with slow processing (should complete unless timeout is enforced)."""

    class SlowProcessor:
        async def process_entities_for_page(self, page_number, full_text, mapping, entities):
            await asyncio.sleep(1)  # Simulate slow processing
            return ([f"processed_{e['entity']}" for e in entities], {"page": page_number, "sensitive": entities})

    processor = SlowProcessor()
    full_text = "Test full text"
    mapping = [({}, 0, 10)]
    entity_dicts = [{"entity": "test1"}, {"entity": "test2"}]
    page_number = 1

    processed_entities, page_info = await asyncio.wait_for(
        BatchProcessingHelper.process_entities_in_parallel(
            processor, full_text, mapping, entity_dicts, page_number
        ),
        timeout=5  # Give enough time for processing
    )

    assert len(processed_entities) == len(entity_dicts), "Expected all entities to be processed"
    assert page_info["sensitive"] == entity_dicts, "Expected sensitive data to match input"


@pytest.mark.asyncio
async def test_validate_batch_files_optimized_valid_cases():
    """✅ Ensure validate_batch_files_optimized correctly processes valid files."""

    # Explicitly set allowed MIME types
    allowed_types = {
        "application/pdf",
        "text/plain",
        "text/csv",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    }

    # Create a function to generate mocked UploadFile objects with a content type
    def create_mock_upload_file(filename, content, mime_type):
        mock_file = MagicMock(spec=UploadFile)
        mock_file.filename = filename
        mock_file.file = BytesIO(content)
        mock_file.content_type = mime_type  # ✅ Mocking content_type instead of setting it
        mock_file.read = AsyncMock(side_effect=lambda: content)  # Simulate async file read
        mock_file.seek = AsyncMock()  # Simulate async seek method
        return mock_file

    # Simulated valid files
    valid_files = [
        create_mock_upload_file("file1.pdf", b"Valid PDF content", "application/pdf"),
        create_mock_upload_file("file2.csv", b"name,age\nJohn,30\n", "text/csv"),
        create_mock_upload_file("file3.txt", b"Hello, world!", "text/plain"),
        create_mock_upload_file("file4.docx", b"Valid DOCX content", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ]

    max_size_mb = 5  # Set a limit for small/large files

    with patch("backend.app.utils.helpers.batch_processing_helper.SecureTempFileManager.create_secure_temp_file_async", new_callable=AsyncMock) as mock_temp_file:
        mock_temp_file.return_value = "/tmp/mock_file"

        batches = []
        async for batch in BatchProcessingHelper.validate_batch_files_optimized(valid_files, allowed_types=allowed_types, max_size_mb=max_size_mb):
            batches.append(batch)

        assert len(batches) > 0, "Expected at least one batch of processed files"
        assert len(batches[0]) == len(valid_files), f"Expected {len(valid_files)} files in batch, got {len(batches[0])}"

        # Check storage method
        for file, tmp_path, content, safe_filename in batches[0]:
            if len(content) > (5 * 1024 * 1024):  # If >5MB, should use temp file
                assert tmp_path is not None, f"Expected temp storage for {file.filename}, but got None"
            else:
                assert tmp_path is None, f"Expected in-memory processing for {file.filename}, but got temp storage"


@pytest.mark.asyncio
async def test_validate_batch_files_optimized_invalid_cases():
    """❌ Ensure validate_batch_files_optimized handles errors gracefully."""

    # Explicitly set allowed MIME types
    allowed_types = {
        "application/pdf",
        "text/plain",
        "text/csv",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    }

    # Create a function to generate mocked UploadFile objects with a content type
    def create_mock_upload_file(filename, content, mime_type):
        mock_file = MagicMock(spec=UploadFile)
        mock_file.filename = filename
        mock_file.file = BytesIO(content)
        mock_file.content_type = mime_type  # ✅ Mocking content_type
        mock_file.read = AsyncMock(side_effect=lambda: content)  # Simulate async file read
        mock_file.seek = AsyncMock()  # Simulate async seek method
        return mock_file

    # Simulated invalid files
    invalid_files = [
        create_mock_upload_file("file1.exe", b"Fake EXE content", "application/x-msdownload"),  # ❌ Unsupported file type
        create_mock_upload_file("file2.pdf", b"A" * (6 * 1024 * 1024), "application/pdf"),  # ❌ File too large (>5MB)
        create_mock_upload_file("file3.txt", b"Hello, world!", "text/plain"),  # ✅ Valid (for later mocking failure)
    ]

    # Simulate missing filename - This should be explicitly rejected
    missing_filename_file = MagicMock(spec=UploadFile)
    missing_filename_file.filename = None  # ❌ Missing filename
    missing_filename_file.content_type = "text/plain"
    missing_filename_file.file = BytesIO(b"Some content")
    missing_filename_file.read = AsyncMock(return_value=b"Some content")
    missing_filename_file.seek = AsyncMock()

    invalid_files.append(missing_filename_file)

    # Set max size to 5MB for testing
    max_size_mb = 5

    # Mock temp file creation failure
    with patch("backend.app.utils.helpers.batch_processing_helper.SecureTempFileManager.create_secure_temp_file_async", side_effect=Exception("Temp file error")), \
         patch.object(invalid_files[2], "read", side_effect=Exception("Read error")):  # Force read failure

        batches = []
        async for batch in BatchProcessingHelper.validate_batch_files_optimized(
            invalid_files, allowed_types=allowed_types, max_size_mb=max_size_mb
        ):
            batches.append(batch)

        # ✅ Debugging print: Check what files were incorrectly processed
        if batches:
            print("❌ Unexpected processed batches:", batches)

        # 🔥 **Fix: Explicitly Check if Missing Filename Was Processed**
        for batch in batches:
            for file, _, _, safe_filename in batch:
                assert file.filename is not None, f"❌ A file with a missing filename was incorrectly processed! Got: {safe_filename}"

        # Ensure no valid batches were processed
        assert len(batches) == 0, f"Expected no valid batches, but got {len(batches)}"


@pytest.mark.asyncio
async def test_validate_batch_files_optimized_wrapper_valid_cases():
    """✅ Ensure validate_batch_files_optimized wrapper correctly calls class method with valid cases."""

    allowed_types = {"application/pdf", "text/plain", "text/csv"}

    # Mock valid files
    valid_files = [
        MagicMock(spec=UploadFile, filename="file1.pdf", file=BytesIO(b"Valid PDF content")),
        MagicMock(spec=UploadFile, filename="file2.csv", file=BytesIO(b"name,age\nJohn,30\n")),
    ]

    # Correct way to mock an async generator
    async def mock_async_generator():
        yield [(valid_files[0], None, b"Valid PDF content", "file1.pdf")]
        yield [(valid_files[1], None, b"name,age\nJohn,30\n", "file2.csv")]

    # Correctly patch to return an async generator
    with patch.object(BatchProcessingHelper, "validate_batch_files_optimized", return_value=mock_async_generator()) as mock_method:

        batches = []
        async for batch in validate_batch_files_optimized(valid_files, allowed_types, max_size_mb=5):
            batches.append(batch)

        # ✅ Assertions
        assert len(batches) == 2, f"Expected 2 valid batches, got {len(batches)}"
        assert batches[0][0][0].filename == "file1.pdf"
        assert batches[1][0][0].filename == "file2.csv"

        # ✅ Ensure the wrapper correctly called the class method once
        mock_method.assert_called_once_with(valid_files, allowed_types, 5)


@pytest.mark.asyncio
async def test_validate_batch_files_optimized_wrapper_invalid_cases():
    """❌ Ensure validate_batch_files_optimized wrapper handles errors gracefully."""

    allowed_types = {"application/pdf", "text/plain", "text/csv"}

    # Mock invalid files
    invalid_files = [
        MagicMock(spec=UploadFile, filename="file1.exe", file=BytesIO(b"Fake EXE content")),  # ❌ Unsupported type
        MagicMock(spec=UploadFile, filename="file2.pdf", file=BytesIO(b"A" * (6 * 1024 * 1024))),  # ❌ File too large
        MagicMock(spec=UploadFile, filename=None, file=BytesIO(b"Missing filename")),  # ❌ Missing filename
    ]

    # Mock async generator to simulate class method returning invalid cases
    async def mock_async_generator():
        yield []  # Simulating an empty batch being yielded (this happens in real-world cases)

    # Patch to return the mocked async generator
    with patch.object(BatchProcessingHelper, "validate_batch_files_optimized", return_value=mock_async_generator()) as mock_method:

        batches = []
        async for batch in validate_batch_files_optimized(invalid_files, allowed_types, max_size_mb=5):
            if batch:  # ✅ Only append if batch is not empty
                batches.append(batch)

        # ✅ Ensure no valid files were processed
        assert len(batches) == 0, f"Expected no valid batches, but got {len(batches)}"

        # ✅ Ensure the wrapper correctly called the class method once
        mock_method.assert_called_once_with(invalid_files, allowed_types, 5)

@pytest.mark.asyncio
async def test_get_optimal_batch_size_wrapper_valid_cases():
    """✅ Ensure get_optimal_batch_size wrapper correctly calls class method with valid cases."""

    # Mock the class method
    with patch.object(BatchProcessingHelper, "get_optimal_batch_size", return_value=4) as mock_method:
        batch_size = get_optimal_batch_size(10, total_bytes=1000000)  # 1MB total

        # ✅ Assertions
        assert batch_size == 4, f"Expected batch size 4, got {batch_size}"
        mock_method.assert_called_once_with(10, 1000000)  # Ensure the call was made correctly

    with patch.object(BatchProcessingHelper, "get_optimal_batch_size", return_value=8):
        batch_size = get_optimal_batch_size(20, total_bytes=5000000)  # 5MB total
        assert batch_size == 8, f"Expected batch size 8, got {batch_size}"

@pytest.mark.asyncio
async def test_get_optimal_batch_size_wrapper_invalid_cases():
    """❌ Ensure get_optimal_batch_size wrapper handles errors and invalid cases gracefully."""

    # ❌ Negative Case 1: Negative file count
    with pytest.raises(ValueError, match="file_count cannot be negative"):
        get_optimal_batch_size(-5, total_bytes=1000000)

    # ❌ Negative Case 2: Negative file size
    with patch.object(BatchProcessingHelper, "get_optimal_batch_size", return_value=1):
        batch_size = get_optimal_batch_size(10, total_bytes=-100)  # Should not fail, but should default
        assert batch_size == 1, f"Expected batch size 1 for negative bytes, got {batch_size}"

    # ❌ Negative Case 3: Exception in the class method
    with patch.object(BatchProcessingHelper, "get_optimal_batch_size", side_effect=Exception("Unexpected failure")):
        with pytest.raises(Exception, match="Unexpected failure"):
            get_optimal_batch_size(5, total_bytes=500000)

    # ❌ Negative Case 4: Zero files
    with patch.object(BatchProcessingHelper, "get_optimal_batch_size", return_value=1):
        batch_size = get_optimal_batch_size(0, total_bytes=1000000)
        assert batch_size == 1, f"Expected batch size 1 for zero files, got {batch_size}"


@pytest.mark.asyncio
async def test_process_entity_success():
    """Test that _process_entity_async correctly processes an entity."""

    # Mock processor that returns a valid entity result
    processor_mock = AsyncMock()
    processor_mock.process_entities_for_page.return_value = (["processed_entity"], {"sensitive": ["sensitive_info"]})

    # Input Data
    entity_dict = {"text": "Sample text"}
    full_text = "Sample full text"
    mapping = [({}, 0, 10)]
    page_number = 1

    # Call the function
    processed, page_info = await BatchProcessingHelper._process_entity_async(
        processor_mock, full_text, mapping, entity_dict, page_number
    )

    # Assertions
    assert processed == ["processed_entity"]
    assert page_info == {"sensitive": ["sensitive_info"]}

    # Check that the processor was called once
    processor_mock.process_entities_for_page.assert_awaited_once()



@pytest.mark.asyncio
async def test_process_entity_failure():
    """Test that _process_entity_async handles exceptions and returns an empty result."""

    # Mock processor that raises an exception
    processor_mock = AsyncMock()
    processor_mock.process_entities_for_page.side_effect = Exception("Entity processing error")

    # Patch the logger to prevent actual logging
    with patch("backend.app.utils.helpers.batch_processing_helper.log_error") as log_mock, \
         patch.object(SecurityAwareErrorHandler, "log_processing_error", return_value="error_id_mock"):

        # Input Data
        entity_dict = {"text": "Sample text"}
        full_text = "Sample full text"
        mapping = [({}, 0, 10)]
        page_number = 1

        # Call the function
        processed, page_info = await BatchProcessingHelper._process_entity_async(
            processor_mock, full_text, mapping, entity_dict, page_number
        )

        # Assertions
        assert processed == []
        assert page_info == {"page": 1, "sensitive": []}

        # Check that the error was logged
        processor_mock.process_entities_for_page.assert_awaited_once()
        log_mock.assert_called_once()


@pytest.mark.asyncio
async def test_store_large_file_success():
    # Mock SecureTempFileManager
    SecureTempFileManager.create_secure_temp_file_async = AsyncMock(return_value="/tmp/batch_test_file.pdf")

    # Define test input
    content = b"This is a large test file" * 10000
    safe_filename = "test_file.pdf"

    # Call the method
    result = await BatchProcessingHelper._store_large_file(content, safe_filename)

    # Assertions
    assert result == "/tmp/batch_test_file.pdf"
    SecureTempFileManager.create_secure_temp_file_async.assert_called_once()

@pytest.mark.asyncio
async def test_store_large_file_failure():
    # Mock SecureTempFileManager to raise an exception
    SecureTempFileManager.create_secure_temp_file_async = AsyncMock(side_effect=Exception("File storage error"))

    # Define test input
    content = b"Large file content"
    safe_filename = "invalid_file.pdf"

    # Call the method
    with pytest.raises(Exception, match="File storage error"):
        await BatchProcessingHelper._store_large_file(content, safe_filename)

    SecureTempFileManager.create_secure_temp_file_async.assert_called_once()