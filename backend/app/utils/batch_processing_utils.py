"""
Common utilities for batch processing routes to reduce code duplication.

This module provides shared utilities for batch processing endpoints, ensuring consistent
file validation, memory optimization, and error handling across different endpoints.
"""
import asyncio
import io
import json
import os
import time
import zipfile
from typing import List, Dict, Any, Tuple, Union

from fastapi import UploadFile, BackgroundTasks
from starlette.responses import JSONResponse, StreamingResponse

from backend.app.factory.document_processing_factory import EntityDetectionEngine
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.file_validation import validate_mime_type, sanitize_filename
from backend.app.utils.helpers.batch_processing_helper import validate_batch_files_optimized, BatchProcessingHelper
from backend.app.utils.logger import log_warning, log_info
from backend.app.utils.memory_management import memory_monitor
from backend.app.utils.processing_records import record_keeper
from backend.app.utils.secure_file_utils import SecureTempFileManager
from backend.app.utils.secure_logging import log_batch_operation

# Streaming configuration
CHUNK_SIZE = 64 * 1024  # 64KB for streaming responses


async def validate_detection_engine(detection_engine: str) -> Tuple[bool, Union[EntityDetectionEngine, Dict[str, Any]]]:
    """
    Validate the detection engine parameter and map it to the appropriate enum.

    Args:
        detection_engine: String identifier for detection engine

    Returns:
        Tuple of (is_valid, result). If valid, result is the engine enum, otherwise an error dict.
    """
    engine_map = {
        "presidio": EntityDetectionEngine.PRESIDIO,
        "gemini": EntityDetectionEngine.GEMINI,
        "gliner": EntityDetectionEngine.GLINER
    }

    if detection_engine not in engine_map:
        error = SecurityAwareErrorHandler.handle_detection_error(
            ValueError(f"Invalid detection engine. Must be one of: {', '.join(engine_map.keys())}"),
            "batch_detection_validation"
        )
        return False, error

    return True, engine_map[detection_engine]


def adjust_parallelism_based_on_memory(max_parallel_files: int) -> int:
    """
    Adjust maximum parallel files based on current memory pressure.

    Args:
        max_parallel_files: Requested maximum parallel files

    Returns:
        Adjusted maximum parallel files
    """
    current_memory_usage = memory_monitor.get_memory_usage()

    if current_memory_usage > 80:
        # High memory pressure, reduce parallelism
        adjusted = min(max_parallel_files, 2)
    elif current_memory_usage > 60:
        # Medium memory pressure, moderately reduce parallelism
        adjusted = min(max_parallel_files, 4)
    else:
        # Low memory pressure, use requested parallelism up to a max of 8
        adjusted = min(max_parallel_files, 8)

    log_info(f"Using {adjusted} parallel workers (memory: {current_memory_usage:.1f}%)")
    return adjusted


async def validate_redaction_mappings(redaction_mappings: str) -> Tuple[bool, Union[Dict[str, Any], Dict[str, Any]]]:
    """
    Validate and parse redaction mappings from JSON.

    Args:
        redaction_mappings: JSON string containing redaction mappings

    Returns:
        Tuple of (is_valid, result). If valid, result is the mappings dict, otherwise an error dict.
    """
    try:
        detection_results = json.loads(redaction_mappings)
        mappings_data = {}

        # Handle different redaction mapping formats
        if "redaction_mapping" in detection_results:
            if "file_info" in detection_results and "filename" in detection_results["file_info"]:
                filename = detection_results["file_info"]["filename"]
                mappings_data[filename] = detection_results["redaction_mapping"]
        elif "file_results" in detection_results:
            for file_result in detection_results["file_results"]:
                if file_result["status"] == "success" and "results" in file_result:
                    filename = file_result["file"]
                    if "redaction_mapping" in file_result["results"]:
                        mappings_data[filename] = file_result["results"]["redaction_mapping"]

        if not mappings_data:
            error = SecurityAwareErrorHandler.handle_detection_error(
                ValueError("Could not extract valid redaction mappings from provided JSON."),
                "batch_redaction_mapping_parsing"
            )
            return False, error

        return True, mappings_data

    except json.JSONDecodeError as e:
        error = SecurityAwareErrorHandler.handle_detection_error(e, "batch_redaction_json_parsing")
        return False, error


async def determine_processing_strategy(files: List[UploadFile]) -> Tuple[bool, int]:
    """
    Determine if in-memory processing can be used for batch processing based on file sizes.

    Args:
        files: List of uploaded files

    Returns:
        Tuple of (use_memory_buffer, total_size)
    """
    allowed_types = {"application/pdf", "text/plain",
                     "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    total_size = 0
    use_memory_buffer = True
    current_memory_usage = memory_monitor.get_memory_usage()

    # First pass: validate files and check total size for memory decision
    for file in files:
        try:
            await file.seek(0)
            content = await file.read(8192)  # Read just a chunk to check
            await file.seek(0)

            # Validate content type
            content_type = file.content_type or "application/octet-stream"
            if not validate_mime_type(content_type, allowed_types):
                continue

            # If any file exceeds 5MB, use disk-based approach
            if hasattr(file, 'size') and file.size and file.size > 5 * 1024 * 1024:
                use_memory_buffer = False
                break

            total_size += (file.size if hasattr(file, 'size') and file.size else len(content))

        except Exception as e:
            log_warning(f"Error checking file {file.filename}: {str(e)}")

    # Only use in-memory processing for smaller batches when memory pressure is low
    if use_memory_buffer and total_size < 20 * 1024 * 1024 and current_memory_usage < 70:
        return True, total_size
    else:
        return False, total_size


async def process_batch_in_memory(
        files: List[UploadFile],
        mappings_data: Dict[str, Any],
        max_parallel_files: int,
        start_time: float,
        background_tasks: BackgroundTasks
) -> StreamingResponse:
    """
    Process batch redaction entirely in memory to avoid temporary file creation.

    Args:
        files: List of uploaded files
        mappings_data: Mapping of redactions by filename
        max_parallel_files: Maximum parallel processing
        start_time: Processing start time
        background_tasks: Background tasks for cleanup

    Returns:
        StreamingResponse with the ZIP file
    """
    # Create in-memory ZIP buffer
    zip_buffer = io.BytesIO()

    # List to track processing results
    results = []
    batch_summary = {
        "total_files": len(files),
        "successful": 0,
        "failed": 0,
        "total_time": 0,
        "workers": max_parallel_files,
        "file_results": []
    }

    # Use semaphore to control concurrency
    semaphore = asyncio.Semaphore(max_parallel_files)

    async def process_file(file: UploadFile):
        """Process a single file for redaction in memory"""
        async with semaphore:
            file_start_time = time.time()
            filename = file.filename or "unnamed_file"
            safe_filename = sanitize_filename(filename)
            content_type = file.content_type or "application/octet-stream"

            try:
                # Check if we have redaction mapping for this file
                if filename not in mappings_data:
                    return {
                        "file": filename,
                        "status": "error",
                        "error": "No redaction mapping provided for this file"
                    }

                # Read file content
                await file.seek(0)
                content = await file.read()

                # Apply redactions
                if "pdf" in content_type.lower():
                    # Process PDF in memory
                    from backend.app.document_processing.pdf import PDFRedactionService

                    # Create redaction service and apply redactions
                    redaction_service = PDFRedactionService(content)
                    redacted_content = redaction_service.apply_redactions_to_memory(mappings_data[filename])

                    # Add to ZIP
                    with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED) as zipf:
                        zipf.writestr(f"redacted_{safe_filename}", redacted_content)

                    return {
                        "file": filename,
                        "status": "success",
                        "output_file": f"redacted_{safe_filename}",
                        "redaction_time": time.time() - file_start_time
                    }
                else:
                    # For other file types, we need temporary files
                    with SecureTempFileManager.create_temp_file(
                            suffix=os.path.splitext(filename)[1] or ".txt",
                            content=content
                    ) as tmp_path:
                        # Determine document format
                        from backend.app.factory.document_processing_factory import DocumentFormat, DocumentProcessingFactory

                        doc_format = None
                        if filename.lower().endswith('.pdf'):
                            doc_format = DocumentFormat.PDF
                        elif filename.lower().endswith(('.docx', '.doc')):
                            doc_format = DocumentFormat.DOCX
                        elif filename.lower().endswith('.txt'):
                            doc_format = DocumentFormat.TXT

                        # Create temporary output path
                        with SecureTempFileManager.create_temp_file(
                                suffix=os.path.splitext(filename)[1] or ".txt"
                        ) as output_path:
                            # Process with redactor
                            redactor = DocumentProcessingFactory.create_document_redactor(
                                tmp_path, doc_format
                            )
                            redactor.apply_redactions(mappings_data[filename], output_path)
                            redactor.close()

                            # Read redacted content and add to ZIP
                            with open(output_path, 'rb') as f:
                                redacted_content = f.read()

                            with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED) as zipf:
                                zipf.writestr(f"redacted_{safe_filename}", redacted_content)

                            return {
                                "file": filename,
                                "status": "success",
                                "output_file": f"redacted_{safe_filename}",
                                "redaction_time": time.time() - file_start_time
                            }
            except Exception as e:
                return SecurityAwareErrorHandler.handle_file_processing_error(
                    e, "redaction_processing", filename
                )

    # Process all files in parallel
    tasks = [process_file(file) for file in files]
    results = await asyncio.gather(*tasks)

    # Update batch summary
    batch_summary["successful"] = sum(1 for r in results if r.get("status") == "success")
    batch_summary["failed"] = len(results) - batch_summary["successful"]
    batch_summary["total_time"] = time.time() - start_time
    batch_summary["file_results"] = [
        {
            "file": r.get("file"),
            "status": r.get("status"),
            "output_file": r.get("output_file") if r.get("status") == "success" else None,
            "error": r.get("error") if r.get("status") == "error" else None
        }
        for r in results
    ]

    # Add batch summary to ZIP
    with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED) as zipf:
        zipf.writestr("batch_summary.json", json.dumps(batch_summary, indent=2))

    # Record processing for GDPR compliance
    record_keeper.record_processing(
        operation_type="batch_redaction_in_memory",
        document_type="multiple",
        entity_types_processed=[],
        processing_time=batch_summary["total_time"],
        file_count=len(files),
        entity_count=0,
    )

    # Log operation
    log_batch_operation(
        "Batch Redaction Completed (in memory)",
        len(files),
        batch_summary["successful"],
        batch_summary["total_time"]
    )

    # Prepare for streaming
    zip_buffer.seek(0)

    # Get memory stats
    mem_stats = memory_monitor.get_memory_stats()

    async def content_streamer():
        """Stream the ZIP file content in chunks"""
        while True:
            chunk = zip_buffer.read(CHUNK_SIZE)
            if not chunk:
                break
            yield chunk
            # Allow other tasks to run between chunks
            await asyncio.sleep(0)
        # Clean up buffer when done
        zip_buffer.close()

    return StreamingResponse(
        content_streamer(),
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=redacted_documents.zip",
            "X-Batch-Time": f"{batch_summary['total_time']:.3f}s",
            "X-Success-Count": str(batch_summary["successful"]),
            "X-Error-Count": str(batch_summary["failed"]),
            "X-Memory-Usage": f"{mem_stats['current_usage']:.1f}%",
            "X-Peak-Memory": f"{mem_stats['peak_usage']:.1f}%"
        }
    )


async def process_batch_with_temp_files(
        files: List[UploadFile],
        mappings_data: Dict[str, Any],
        max_parallel_files: int,
        start_time: float,
        background_tasks: BackgroundTasks
) -> JSONResponse | StreamingResponse:
    """
    Process batch redaction using temporary files for larger batches.

    Args:
        files: List of uploaded files
        mappings_data: Mapping of redactions by filename
        max_parallel_files: Maximum parallel processing
        start_time: Processing start time
        background_tasks: Background tasks for cleanup

    Returns:
        StreamingResponse with the ZIP file
    """
    # Create a secure temporary directory for redacted outputs
    output_dir_path = await SecureTempFileManager.create_secure_temp_dir_async("batch_output_")

    # Use the optimized batch processing helper
    allowed_types = {"application/pdf", "text/plain",
                     "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}

    file_metas = []
    valid_files = []

    # Validate and process files
    async for batch_files in validate_batch_files_optimized(files, allowed_types):
        for file_tuple in batch_files:
            file, tmp_path, content, safe_filename = file_tuple
            file_metas.append({
                "original_name": file.filename,
                "content_type": file.content_type or "application/octet-stream",
                "size": len(content),
                "safe_name": safe_filename,
                "output_path": os.path.join(output_dir_path, f"redacted_{safe_filename}")
            })
            valid_files.append(file_tuple)

    if not valid_files:
        error = SecurityAwareErrorHandler.handle_detection_error(
            ValueError("No valid files provided for processing"),
            "batch_redaction_file_validation"
        )
        return JSONResponse(status_code=400, content=error)

    # Get optimal batch size based on system resources
    optimal_workers = BatchProcessingHelper.get_optimal_batch_size(
        len(valid_files), sum(len(f[2]) for f in valid_files)
    )

    # Limit to max_parallel_files
    optimal_workers = min(optimal_workers, max_parallel_files)

    # Use semaphore to limit concurrent processing
    semaphore = asyncio.Semaphore(optimal_workers)

    async def redact_file(file_tuple, meta_index):
        async with semaphore:
            file_start_time = time.time()
            file, tmp_path, content, safe_filename = file_tuple
            file_meta = file_metas[meta_index]
            file_name = file.filename
            output_path = file_meta["output_path"]

            try:
                if file_name not in mappings_data:
                    return {
                        "file": file_name,
                        "status": "error",
                        "error": "No redaction mapping provided for this file"
                    }

                redaction_mapping = mappings_data[file_name]

                # Process using the appropriate method based on file type
                if file.content_type and "pdf" in file.content_type.lower():
                    # For PDFs, process in memory and write to output path
                    from backend.app.document_processing.pdf import PDFRedactionService
                    redaction_service = PDFRedactionService(content)
                    redacted_content = redaction_service.apply_redactions_to_memory(redaction_mapping)

                    with open(output_path, 'wb') as f:
                        f.write(redacted_content)
                else:
                    # For other types, use the DocumentProcessingFactory
                    from backend.app.factory.document_processing_factory import DocumentFormat, DocumentProcessingFactory

                    # Determine document format
                    doc_format = None
                    if file_name.lower().endswith('.pdf'):
                        doc_format = DocumentFormat.PDF
                    elif file_name.lower().endswith(('.docx', '.doc')):
                        doc_format = DocumentFormat.DOCX
                    elif file_name.lower().endswith('.txt'):
                        doc_format = DocumentFormat.TXT

                    # Process with temporary file as needed
                    if tmp_path:
                        # Use existing temp file
                        redactor = DocumentProcessingFactory.create_document_redactor(tmp_path, doc_format)
                        redactor.apply_redactions(redaction_mapping, output_path)
                        redactor.close()
                    else:
                        # Create temporary file for processing
                        with SecureTempFileManager.create_temp_file(
                                suffix=f".{doc_format.name.lower()}" if doc_format else ".txt",
                                content=content
                        ) as tmp_file_path:
                            redactor = DocumentProcessingFactory.create_document_redactor(tmp_file_path, doc_format)
                            redactor.apply_redactions(redaction_mapping, output_path)
                            redactor.close()

                redact_time = time.time() - file_start_time
                return {
                    "file": file_name,
                    "status": "success",
                    "output_file": os.path.basename(output_path),
                    "redaction_time": redact_time
                }
            except Exception as e:
                return SecurityAwareErrorHandler.handle_file_processing_error(e, "redaction_processing", file_name)

    tasks = [redact_file(file_tuple, i) for i, file_tuple in enumerate(valid_files)]
    results = await asyncio.gather(*tasks)

    # Create ZIP file with results
    zip_tmp_path = await SecureTempFileManager.create_secure_temp_file_async(
        suffix=".zip",
        prefix="batch_zip_"
    )

    # Create summary of processing results
    batch_summary = {
        "total_files": len(files),
        "successful": sum(1 for r in results if r.get("status") == "success"),
        "failed": sum(1 for r in results if r.get("status") != "success"),
        "total_time": time.time() - start_time,
        "workers": optimal_workers,
        "file_results": [
            {
                "file": r.get("file"),
                "status": r.get("status"),
                "output_file": r.get("output_file") if r.get("status") == "success" else None,
                "error": r.get("error") if r.get("status") == "error" else None
            }
            for r in results
        ]
    }

    # Write ZIP file to disk including the batch summary
    with zipfile.ZipFile(zip_tmp_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for result, file_meta in zip(results, file_metas):
            if result.get("status") == "success":
                output_path = file_meta["output_path"]
                if os.path.exists(output_path):
                    zipf.write(output_path, arcname=f"redacted_{file_meta['safe_name']}")

        # Add batch summary
        zipf.writestr("batch_summary.json", json.dumps(batch_summary, indent=2))

    # Record processing for GDPR compliance
    record_keeper.record_processing(
        operation_type="batch_redaction",
        document_type="multiple",
        entity_types_processed=[],
        processing_time=batch_summary["total_time"],
        file_count=len(files),
        entity_count=0,
    )

    # Log operation
    log_batch_operation(
        "Batch Redaction Completed",
        len(files),
        batch_summary["successful"],
        batch_summary["total_time"]
    )

    # Stream ZIP file in chunks
    async def zip_streamer():
        try:
            with open(zip_tmp_path, "rb") as f:
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    yield chunk
                    # Allow other tasks to run between chunks
                    await asyncio.sleep(0)
        finally:
            pass  # Let background tasks handle cleanup

    # Get memory stats
    mem_stats = memory_monitor.get_memory_stats()

    # Schedule cleanup using background tasks
    background_tasks.add_task(
        lambda: asyncio.to_thread(SecureTempFileManager.secure_delete_directory, output_dir_path))
    background_tasks.add_task(
        lambda: asyncio.to_thread(SecureTempFileManager.secure_delete_file, zip_tmp_path))

    return StreamingResponse(
        zip_streamer(),
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=redacted_documents.zip",
            "X-Batch-Time": f"{batch_summary['total_time']:.3f}s",
            "X-Success-Count": str(batch_summary["successful"]),
            "X-Error-Count": str(batch_summary["failed"]),
            "X-Memory-Usage": f"{mem_stats['current_usage']:.1f}%",
            "X-Peak-Memory": f"{mem_stats['peak_usage']:.1f}%"
        }
    )