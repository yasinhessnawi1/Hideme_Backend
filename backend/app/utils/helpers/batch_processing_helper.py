"""
Optimized batch processing utilities for document processing operations.

This module provides helpers for efficiently processing multiple files in batch operations,
optimizing for memory usage, security, and performance with enhanced in-memory processing.
"""
import asyncio
import os
from typing import List, Dict, Any, Tuple, Optional, Callable, Set, AsyncGenerator, Union

from fastapi import UploadFile

from backend.app.utils.document_processing_utils import extract_text_data_in_memory
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.file_validation import (
    validate_mime_type, validate_file_content_async,
    sanitize_filename, is_valid_file_size, MAX_BATCH_SIZE_BYTES
)
from backend.app.utils.logger import log_info, log_warning
from backend.app.utils.memory_management import memory_monitor
from backend.app.utils.secure_file_utils import SecureTempFileManager


class BatchProcessingHelper:
    """
    Helper for optimized batch document processing.

    Provides utilities for efficiently processing multiple files with:
    - Memory optimization
    - Parallel processing
    - In-memory operations when possible
    - Security validation
    """

    @staticmethod
    async def process_batch_files(
            files: List[UploadFile],
            max_parallel: int = 4,
            allowed_mime_types: Optional[Set[str]] = None,
            max_batch_size_bytes: int = MAX_BATCH_SIZE_BYTES
    ) -> AsyncGenerator[Tuple[UploadFile, Dict[str, Any], bytes, str, bool], None]:
        """
        Process multiple files in parallel with optimized memory usage.

        Args:
            files: List of uploaded files
            max_parallel: Maximum number of files to process concurrently
            allowed_mime_types: Set of allowed MIME types (if None, all types are allowed)
            max_batch_size_bytes: Maximum total batch size in bytes

        Yields:
            Tuples of (file, extracted_data, file_content, safe_filename, is_valid)
        """
        # Create a semaphore to limit concurrent processing
        semaphore = asyncio.Semaphore(max_parallel)

        # Track total batch size
        total_batch_size = 0

        async def process_single_file(file: UploadFile) -> Tuple[UploadFile, Dict[str, Any], bytes, str, bool]:
            """Process a single file in the batch."""
            nonlocal total_batch_size

            async with semaphore:
                try:
                    # Read file content
                    await file.seek(0)
                    content = await file.read()

                    # Update total batch size and check limit
                    file_size = len(content)
                    if total_batch_size + file_size > max_batch_size_bytes:
                        return file, {}, b"", sanitize_filename(file.filename or ""), False

                    total_batch_size += file_size

                    # Validate MIME type
                    content_type = file.content_type or "application/octet-stream"
                    if allowed_mime_types and not validate_mime_type(content_type, allowed_mime_types):
                        log_warning(f"Invalid MIME type: {content_type} for file {file.filename}")
                        return file, {}, content, sanitize_filename(file.filename or ""), False

                    # Get safe filename
                    safe_filename = sanitize_filename(file.filename) if file.filename else f"unnamed_file"

                    # Validate file content
                    is_valid, reason, detected_mime = await validate_file_content_async(
                        content, safe_filename, content_type
                    )

                    if not is_valid:
                        log_warning(f"Invalid file content: {reason} for file {safe_filename}")
                        return file, {}, content, safe_filename, False

                    # Check if we can process this file
                    file_type = "text"
                    if "pdf" in content_type:
                        file_type = "pdf"
                    elif "word" in content_type or "doc" in content_type:
                        file_type = "docx"

                    if not is_valid_file_size(file_size, file_type):
                        log_warning(f"File too large: {file_size} bytes for {file_type} file {safe_filename}")
                        return file, {}, content, safe_filename, False

                    # Extract text data in memory using centralized utility
                    extracted_data = await extract_text_data_in_memory(content_type, content)

                    # Log file processing
                    log_info(f"Processed file: {safe_filename} ({file_size / 1024:.1f}KB)")

                    return file, extracted_data, content, safe_filename, True
                except Exception as e:
                    # Handle errors but continue processing other files
                    SecurityAwareErrorHandler.log_processing_error(
                        e, "batch_file_processing", file.filename or "unknown_file"
                    )
                    return file, {"pages": []}, b"", sanitize_filename(file.filename or ""), False

        # Process files concurrently with semaphore control
        tasks = [process_single_file(file) for file in files]

        for future in asyncio.as_completed(tasks):
            result = await future
            yield result

    @staticmethod
    async def process_batch_content(
            file_contents: List[Tuple[bytes, str, str]],  # content, filename, content_type
            processor: Callable[[bytes, str, str], Union[Dict[str, Any], bytes, str]],
            max_parallel: int = 4,
            in_memory_threshold: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Process batch file content without creating temporary files when possible.
        Uses memory buffers for content under threshold size and only creates temporary
        files when necessary based on memory pressure and content size.

        Args:
            file_contents: List of tuples (content, filename, content_type)
            processor: Function to process each file's content
            max_parallel: Maximum number of parallel processing tasks
            in_memory_threshold: Optional custom threshold for in-memory processing

        Returns:
            List of processing results
        """
        # Adjust based on current memory pressure if threshold not specified
        if in_memory_threshold is None:
            current_memory_usage = memory_monitor.get_memory_usage()
            available_memory_mb = memory_monitor.memory_stats["available_memory_mb"]

            # Adaptive threshold based on memory pressure
            if current_memory_usage > 80:  # High memory pressure
                in_memory_threshold = min(1024 * 1024, int(available_memory_mb * 1024 * 0.01))  # 1% of available or 1MB
            elif current_memory_usage > 60:  # Medium memory pressure
                in_memory_threshold = min(5 * 1024 * 1024, int(available_memory_mb * 1024 * 0.05))  # 5% or 5MB
            else:  # Low memory pressure
                in_memory_threshold = min(20 * 1024 * 1024, int(available_memory_mb * 1024 * 0.1))  # 10% or 20MB

        # Create semaphore for parallel processing
        semaphore = asyncio.Semaphore(max_parallel)
        results = []

        async def process_content_item(content: bytes, filename: str, content_type: str) -> Dict[str, Any]:
            """Process a single content item with appropriate memory strategy"""
            async with semaphore:
                try:
                    safe_filename = sanitize_filename(filename)
                    file_size = len(content)

                    # Decide if we should process in memory
                    use_memory = file_size <= in_memory_threshold

                    if use_memory:
                        # Process entirely in memory
                        log_info(f"Processing {safe_filename} ({file_size/1024:.1f}KB) in memory")
                        processed_result = await asyncio.to_thread(processor, content, safe_filename, content_type)

                        if isinstance(processed_result, dict):
                            return {
                                "file": filename,
                                "status": "success",
                                "result": processed_result,
                                "safe_filename": safe_filename,
                                "size": file_size,
                                "processed_in_memory": True
                            }
                        elif isinstance(processed_result, (bytes, str)):
                            return {
                                "file": filename,
                                "status": "success",
                                "content": processed_result,
                                "safe_filename": safe_filename,
                                "size": file_size,
                                "processed_in_memory": True
                            }
                        else:
                            return {
                                "file": filename,
                                "status": "success",
                                "safe_filename": safe_filename,
                                "size": file_size,
                                "processed_in_memory": True
                            }
                    else:
                        # Fall back to temporary file for larger content
                        log_info(f"Processing {safe_filename} ({file_size/1024:.1f}KB) using temporary file")
                        tmp_path = await SecureTempFileManager.create_secure_temp_file_async(
                            suffix=os.path.splitext(safe_filename)[1] or ".tmp",
                            content=content
                        )

                        try:
                            # Process with temporary file
                            processed_result = await asyncio.to_thread(processor, tmp_path, safe_filename, content_type)

                            # Build result
                            if isinstance(processed_result, dict):
                                return {
                                    "file": filename,
                                    "status": "success",
                                    "result": processed_result,
                                    "safe_filename": safe_filename,
                                    "size": file_size,
                                    "processed_in_memory": False,
                                    "temp_path": tmp_path
                                }
                            elif isinstance(processed_result, (bytes, str)):
                                return {
                                    "file": filename,
                                    "status": "success",
                                    "content": processed_result,
                                    "safe_filename": safe_filename,
                                    "size": file_size,
                                    "processed_in_memory": False,
                                    "temp_path": tmp_path
                                }
                            else:
                                return {
                                    "file": filename,
                                    "status": "success",
                                    "safe_filename": safe_filename,
                                    "size": file_size,
                                    "processed_in_memory": False,
                                    "temp_path": tmp_path
                                }
                        finally:
                            # Clean up temporary file
                            await SecureTempFileManager.secure_delete_file_async(tmp_path)

                except Exception as e:
                    error_msg = str(e)
                    SecurityAwareErrorHandler.log_processing_error(e, "batch_content_processing", filename)
                    return {
                        "file": filename,
                        "status": "error",
                        "error": error_msg,
                        "safe_filename": sanitize_filename(filename)
                    }

        # Process all content items in parallel
        tasks = [
            process_content_item(content, filename, content_type)
            for content, filename, content_type in file_contents
        ]

        return await asyncio.gather(*tasks)

    @staticmethod
    async def write_batch_results(
            results: List[Dict[str, Any]],
            output_dir: Optional[str] = None,
            cleanup_temp_files: bool = True
    ) -> Dict[str, Any]:
        """
        Write batch processing results to files with optimized resource handling.
        Improved version that minimizes file creation by using the existing temporary
        files when available and only creating new files when necessary.

        Args:
            results: List of processing results
            output_dir: Optional directory to write output files (created if needed)
            cleanup_temp_files: Whether to clean up temporary files after processing

        Returns:
            Summary of write operations
        """
        # Create output directory if needed and specified
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
            created_dir = True
        else:
            created_dir = False

        summary = {
            "total": len(results),
            "success": 0,
            "error": 0,
            "output_files": [],
            "created_output_dir": created_dir and bool(output_dir)
        }

        for result in results:
            status = result.get("status", "error")
            filename = result.get("safe_filename", "unknown_file")

            if status == "success":
                summary["success"] += 1

                # If we're writing to a directory
                if output_dir:
                    output_path = os.path.join(output_dir, f"processed_{filename}")

                    # Check if we have content to write
                    if "content" in result:
                        content = result["content"]
                        if isinstance(content, str):
                            content = content.encode('utf-8')

                        # Write content to output file
                        with open(output_path, "wb") as f:
                            f.write(content)

                        summary["output_files"].append(output_path)

                    # Or if we already have a temp file, just move/copy it
                    elif "temp_path" in result and os.path.exists(result["temp_path"]):
                        import shutil

                        # Copy the file (move would delete original which might be needed)
                        shutil.copy2(result["temp_path"], output_path)
                        summary["output_files"].append(output_path)

                        # Cleanup temp file if requested
                        if cleanup_temp_files:
                            await SecureTempFileManager.secure_delete_file_async(result["temp_path"])
            else:
                summary["error"] += 1

        return summary

    @staticmethod
    def get_optimal_batch_size(file_count: int, total_size: int) -> int:
        """
        Determine optimal batch size based on system resources and input size.

        Args:
            file_count: Number of files to process
            total_size: Total size of all files in bytes

        Returns:
            Optimal batch size (number of files per batch)
        """
        # Get available memory
        available_memory = memory_monitor.memory_stats["available_memory_mb"] * 1024 * 1024
        current_usage = memory_monitor.get_memory_usage()

        # Base batch size on resource constraints
        if current_usage > 80:  # High memory pressure
            per_file_limit = min(available_memory * 0.1 / file_count, 10 * 1024 * 1024)  # 10MB max per file
            return max(1, min(int(per_file_limit * file_count / total_size), file_count // 4 or 1))
        elif current_usage > 60:  # Moderate memory pressure
            per_file_limit = min(available_memory * 0.2 / file_count, 20 * 1024 * 1024)  # 20MB max per file
            return max(2, min(int(per_file_limit * file_count / total_size), file_count // 3 or 2))
        else:  # Low memory pressure
            per_file_limit = min(available_memory * 0.3 / file_count, 30 * 1024 * 1024)  # 30MB max per file
            return max(4, min(int(per_file_limit * file_count / total_size), file_count // 2 or 4))


async def validate_batch_files_optimized(
        files: List[UploadFile],
        allowed_types: Optional[Set[str]] = None,
        max_batch_size: int = MAX_BATCH_SIZE_BYTES
) -> AsyncGenerator[List[Tuple[UploadFile, Optional[str], bytes, str]], None]:
    """
    Validate batch files and yield a list of valid files along with their content and safe filename.
    Uses in-memory processing where possible for improved security and performance.

    Args:
        files: List of uploaded files
        allowed_types: Set of allowed MIME types (if None, all types are allowed)
        max_batch_size: Maximum total batch size in bytes

    Yields:
        List of tuples: (file, tmp_path_or_None, file_content, safe_filename)
    """
    if not files:
        raise ValueError("No files provided")

    total_size = 0
    valid_files = []

    try:
        for file in files:
            try:
                # Read file content
                await file.seek(0)
                content = await file.read()

                # Update total size and check limit
                file_size = len(content)
                total_size += file_size
                if total_size > max_batch_size:
                    raise ValueError(f"Total batch size exceeds limit of {max_batch_size // (1024 * 1024)}MB")

                # Validate MIME type
                content_type = file.content_type or "application/octet-stream"
                if allowed_types and not validate_mime_type(content_type, allowed_types):
                    continue

                # Get safe filename
                safe_filename = sanitize_filename(file.filename) if file.filename else f"unnamed_file"

                # Determine if we should use in-memory processing or temporary file
                tmp_path = None
                if "pdf" not in content_type.lower():
                    # For non-PDFs, create a temporary file
                    tmp_path = await SecureTempFileManager.create_secure_temp_file_async(
                        suffix=os.path.splitext(safe_filename)[1] or ".tmp",
                        content=content
                    )

                valid_files.append((file, tmp_path, content, safe_filename))

                # Reset file position for potential reuse
                await file.seek(0)
            except Exception as e:
                SecurityAwareErrorHandler.log_processing_error(
                    e, "file_validation", file.filename or "unknown_file"
                )

        if not valid_files:
            raise ValueError("No valid files provided for processing")

        yield valid_files
    finally:
        # Clean up temporary files
        for _, tmp_path, _, _ in valid_files:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    await SecureTempFileManager.secure_delete_file_async(tmp_path)
                except Exception:
                    pass