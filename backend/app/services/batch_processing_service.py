"""
Optimized batch processing service leveraging centralized PDF processing functionality.

This service handles batch document processing with enhanced performance through
unified parallel processing and memory optimization, utilizing the centralized PDF
processing and batch utilities for consistent results and optimized resource utilization.
"""
import asyncio
import json
import time
import uuid
import zipfile
from typing import List, Dict, Any, Optional, Tuple, Union

import os
from fastapi import UploadFile, BackgroundTasks
from starlette.responses import JSONResponse, StreamingResponse

from backend.app.factory.document_processing_factory import DocumentFormat, EntityDetectionEngine, \
    DocumentProcessingFactory
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.helpers.json_helper import validate_requested_entities
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.logging.secure_logging import log_batch_operation
from backend.app.utils.memory_management import memory_monitor
from backend.app.utils.parallel.batch import BatchProcessingUtils, CHUNK_SIZE
from backend.app.utils.parallel.core import ParallelProcessingCore
from backend.app.utils.secure_file_utils import SecureTempFileManager
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.validation.data_minimization import minimize_extracted_data
from backend.app.utils.validation.file_validation import validate_mime_type, sanitize_filename
from backend.app.utils.validation.sanitize_utils import sanitize_detection_output


class BatchProcessingService:
    """
    Optimized service for processing multiple files in a single request.

    This service handles:
    - Processing multiple files with different formats
    - Configurable parallel processing
    - Memory-efficient processing by streaming large files
    - Aggregated response formatting
    - Detailed performance tracking
    - Comprehensive GDPR compliance

    Key features:
    - Uses centralized PDF processing functionality for consistent results
    - Optimized parallel processing with dynamic resource allocation
    - Improved memory management with adaptive buffer sizing
    - Enhanced error handling and recovery
    """

    @staticmethod
    async def detect_entities_in_files(
            files: List[UploadFile],
            requested_entities: Optional[str] = None,
            detection_engine: EntityDetectionEngine = EntityDetectionEngine.PRESIDIO,
            max_parallel_files: Optional[int] = None,
            use_presidio: bool = True,
            use_gemini: bool = False,
            use_gliner: bool = False
    ) -> Dict[str, Any]:
        """
        Detect entities in multiple files in parallel with optimized resource utilization.

        Args:
            files: List of uploaded files to process
            requested_entities: JSON string of entity types to detect
            detection_engine: Entity detection engine to use
            max_parallel_files: Maximum number of files to process in parallel
            use_presidio: Whether to use Presidio detector (for hybrid engine)
            use_gemini: Whether to use Gemini detector (for hybrid engine)
            use_gliner: Whether to use GLiNER detector (for hybrid engine)

        Returns:
            Dict with batch processing results
        """
        start_time = time.time()
        batch_id = str(uuid.uuid4())
        log_info(f"Starting batch entity detection (Batch ID: {batch_id})")

        # Validate entity list
        try:
            entity_list = validate_requested_entities(requested_entities) if requested_entities else []
        except Exception as e:
            return SecurityAwareErrorHandler.handle_batch_processing_error(
                e, "entity_validation", len(files)
            )

        # Pre-initialize detector
        try:
            detector = await BatchProcessingService._get_initialized_detector(
                detection_engine,
                use_presidio,
                use_gemini,
                use_gliner,
                entity_list
            )
        except Exception as e:
            return SecurityAwareErrorHandler.handle_batch_processing_error(
                e, "detector_initialization", len(files)
            )

        # Determine optimal batch size and parallelism
        use_memory, total_size, optimal_workers = BatchProcessingUtils.determine_processing_strategy(files)

        # Adjust by user-specified max workers if provided
        if max_parallel_files is not None:
            optimal_workers = min(optimal_workers, max_parallel_files)

        log_info(f"Processing {len(files)} files with {optimal_workers} workers (Batch ID: {batch_id})")

        # Track file metadata for processing
        file_metadata = []
        valid_files = []

        # Validate and prepare files
        async for batch in BatchProcessingUtils.validate_files_in_batches(files):
            for file, content, safe_filename in batch:
                file_idx = len(file_metadata)
                file_metadata.append({
                    "original_name": file.filename,
                    "content_type": file.content_type or "application/octet-stream",
                    "size": len(content),
                    "safe_name": safe_filename
                })
                valid_files.append((file_idx, file, content))

        if not valid_files:
            return {
                "batch_summary": {
                    "batch_id": batch_id,
                    "total_files": len(files),
                    "successful": 0,
                    "failed": len(files),
                    "total_entities": 0,
                    "total_time": time.time() - start_time
                },
                "file_results": []
            }

        # Separate PDF files for optimized processing
        pdf_indices = []
        pdf_files = []
        other_indices = []
        other_files = []

        for idx, file, content in valid_files:
            content_type = file.content_type or "application/octet-stream"
            if "pdf" in content_type.lower():
                pdf_indices.append(idx)
                pdf_files.append(content)
            else:
                other_indices.append(idx)
                other_files.append((file, content))

        # Process PDF files with optimized batch processing
        extraction_results = []

        if pdf_files:
            log_info(f"Processing {len(pdf_files)} PDF files with optimized batch extraction (Batch ID: {batch_id})")

            try:
                pdf_extraction_results = await BatchProcessingUtils.extract_text_from_pdf_batch(
                    pdf_files,
                    max_workers=optimal_workers,
                )

                # Map back to original indices
                for i, (_, result) in enumerate(pdf_extraction_results):
                    if i < len(pdf_indices):
                        extraction_results.append((pdf_indices[i], result))
            except Exception as e:
                log_error(f"Error in PDF batch extraction: {str(e)}")
                # Continue with processing other files

        # Process non-PDF files individually
        if other_files:
            log_info(f"Processing {len(other_files)} non-PDF files (Batch ID: {batch_id})")

            # Define extraction function for non-PDF files
            async def extract_non_pdf(item: Tuple[int, Tuple[UploadFile, bytes]]) -> Tuple[int, Dict[str, Any]]:
                idx, (file, content) = item

                try:
                    # Determine document format
                    document_format = None
                    filename = file.filename or ""

                    if filename.lower().endswith('.pdf'):
                        document_format = DocumentFormat.PDF
                    elif filename.lower().endswith(('.docx', '.doc')):
                        document_format = DocumentFormat.DOCX
                    elif filename.lower().endswith('.txt'):
                        document_format = DocumentFormat.TXT

                    # Use DocumentProcessingFactory
                    extractor = DocumentProcessingFactory.create_document_extractor(
                        content, document_format
                    )
                    extracted_data = extractor.extract_text()
                    extractor.close()

                    return idx, extracted_data
                except Exception as e:
                    error_id = SecurityAwareErrorHandler.log_processing_error(
                        e, "non_pdf_extraction", file.filename or f"file_{idx}"
                    )
                    log_error(f"Error extracting text from non-PDF file at index {idx}: {str(e)} [error_id={error_id}]")
                    return idx, {"error": str(e), "pages": []}

            # Process non-PDF files in parallel
            other_indices_with_files = [(idx, file_tuple) for idx, file_tuple in zip(other_indices, other_files)]

            other_extraction_results = await ParallelProcessingCore.process_in_parallel(
                items=other_indices_with_files,
                processor=extract_non_pdf,
                max_workers=optimal_workers,
                operation_id=f"non_pdf_extraction_{batch_id}"
            )

            # Add to extraction results
            extraction_results.extend(other_extraction_results)

        # Sort extraction results by original index
        extraction_results.sort(key=lambda x: x[0])

        # Apply entity detection to extracted data
        detection_results = await BatchProcessingUtils.detect_entities_in_batch(
            extraction_results,
            detector,
            entity_list,
            optimal_workers
        )

        # Process results and prepare response
        file_results = []
        successful = 0
        failed = 0
        total_entities = 0
        log_warning(f"[OK] {detection_results}")
        # Map detection results
        detection_map = {}
        for idx, result in detection_results:
            detection_map[idx] = result

        # Create response for each file
        for idx, metadata in enumerate(file_metadata):
            # Check if we have extraction and detection results
            extraction_result = next((r[1] for r in extraction_results if r[0] == idx), None)
            detection_result = detection_map.get(idx)

            if extraction_result is None:
                # Missing extraction result
                file_results.append({
                    "file": metadata["original_name"],
                    "status": "error",
                    "error": "Text extraction failed"
                })
                failed += 1
                continue

            if "error" in extraction_result:
                # Extraction error
                file_results.append({
                    "file": metadata["original_name"],
                    "status": "error",
                    "error": extraction_result["error"]
                })
                failed += 1
                continue

            if detection_result is None:
                # Missing detection result
                file_results.append({
                    "file": metadata["original_name"],
                    "status": "error",
                    "error": "Entity detection failed"
                })
                failed += 1
                continue

            # Fix: Properly check and handle the detection result
            if isinstance(detection_result, tuple) and len(detection_result) == 3:
                anonymized_text, entities, redaction_mapping = detection_result

                # Calculate file-specific statistics
                total_words = sum(len(page.get("words", [])) for page in extraction_result.get("pages", []))
                pages_count = len(extraction_result.get("pages", []))
                entity_density = (len(entities) / total_words) * 1000 if total_words > 0 else 0

                processing_times = {
                    "words_count": total_words,
                    "pages_count": pages_count,
                    "entity_density": entity_density
                }

                # Create sanitized response
                sanitized_response = sanitize_detection_output(
                    anonymized_text, entities, redaction_mapping, processing_times
                )

                sanitized_response["file_info"] = {
                    "filename": metadata["original_name"],
                    "content_type": metadata["content_type"],
                    "size": metadata["size"]
                }

                # Add model info
                model_info = {"engine": detection_engine.name}
                if detection_engine == EntityDetectionEngine.HYBRID:
                    model_info = {
                        "engine": "hybrid",
                        "engines_used": {
                            "presidio": use_presidio,
                            "gemini": use_gemini,
                            "gliner": use_gliner
                        }
                    }
                sanitized_response["model_info"] = model_info

                # Add to file results
                file_results.append({
                    "file": metadata["original_name"],
                    "status": "success",
                    "results": sanitized_response
                })

                successful += 1
                total_entities += len(entities)

                # Record successful detection for GDPR compliance
                record_keeper.record_processing(
                    operation_type="batch_file_detection",
                    document_type=metadata["content_type"],
                    entity_types_processed=entity_list,
                    processing_time=0.0,  # We don't have per-file timing
                    file_count=1,
                    entity_count=len(entities),
                    success=True
                )
            else:
                # Invalid detection result format
                file_results.append({
                    "file": metadata["original_name"],
                    "status": "error",
                    "error": "Invalid detection result format"
                })
                failed += 1

        # Calculate batch summary
        total_time = time.time() - start_time

        batch_summary = {
            "batch_id": batch_id,
            "total_files": len(files),
            "successful": successful,
            "failed": failed,
            "total_entities": total_entities,
            "total_time": total_time,
            "workers": optimal_workers
        }

        # Log batch operation
        log_batch_operation(
            "Batch Entity Detection",
            len(files),
            successful,
            total_time
        )

        # Record batch processing for GDPR compliance
        record_keeper.record_processing(
            operation_type="batch_entity_detection",
            document_type="multiple_files",
            entity_types_processed=entity_list,
            processing_time=total_time,
            file_count=len(files),
            entity_count=total_entities,
            success=(successful > 0)
        )

        # Create final response
        response = {
            "batch_summary": batch_summary,
            "file_results": file_results
        }

        # Add memory statistics
        mem_stats = memory_monitor.get_memory_stats()
        response["_debug"] = {
            "memory_usage": mem_stats["current_usage"],
            "peak_memory": mem_stats["peak_usage"],
            "operation_id": batch_id
        }

        return response

    @staticmethod
    async def batch_redact_documents(
            files: List[UploadFile],
            redaction_mappings: str,
            max_parallel_files: Optional[int] = None,
            background_tasks: Optional[BackgroundTasks] = None
    ) -> Union[JSONResponse, StreamingResponse]:
        """
        Process multiple files for redaction in parallel with optimized resource utilization.
        """
        start_time = time.time()
        batch_id = str(uuid.uuid4())
        log_info(f"Starting batch redaction (Batch ID: {batch_id})")

        # Ensure we have a background tasks object
        if background_tasks is None:
            background_tasks = BackgroundTasks()

        # Validate and parse redaction mappings
        try:
            mapping_data = json.loads(redaction_mappings)
            file_mappings = {}

            # Extract mappings based on the structure
            if "redaction_mapping" in mapping_data and "file_info" in mapping_data and "filename" in mapping_data[
                "file_info"]:
                # Single file mapping format
                filename = mapping_data["file_info"]["filename"]
                file_mappings[filename] = mapping_data["redaction_mapping"]
            elif "file_results" in mapping_data:
                # Multiple file mapping format
                for file_result in mapping_data["file_results"]:
                    if file_result.get("status") == "success" and "results" in file_result:
                        filename = file_result["file"]
                        if "redaction_mapping" in file_result["results"]:
                            file_mappings[filename] = file_result["results"]["redaction_mapping"]

            if not file_mappings:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "No valid redaction mappings found in the provided JSON"}
                )
        except json.JSONDecodeError as e:
            return JSONResponse(
                status_code=400,
                content={"detail": f"Invalid JSON in redaction mappings: {str(e)}"}
            )

        # Create output directory for redacted files
        output_dir = await SecureTempFileManager.create_secure_temp_dir_async(f"batch_redact_{batch_id}_")
        background_tasks.add_task(SecureTempFileManager.secure_delete_directory, output_dir)

        # Validate and prepare files
        file_metadata = []
        valid_files = []

        # Process each file
        for i, file in enumerate(files):
            try:
                # Check if we have a mapping for this file
                if file.filename not in file_mappings:
                    log_warning(f"No redaction mapping for file: {file.filename}")
                    file_metadata.append({
                        "original_name": file.filename,
                        "content_type": file.content_type or "application/octet-stream",
                        "size": 0,
                        "status": "error",
                        "error": "No redaction mapping provided"
                    })
                    continue

                # Check file type
                content_type = file.content_type or "application/octet-stream"
                if not validate_mime_type(content_type, {"application/pdf"}):
                    log_warning(f"Skipping non-PDF file: {file.filename} ({content_type})")
                    file_metadata.append({
                        "original_name": file.filename,
                        "content_type": content_type,
                        "size": 0,
                        "status": "error",
                        "error": "Only PDF files are supported for redaction"
                    })
                    continue

                # Read file content
                await file.seek(0)
                content = await file.read()

                # Add to valid files
                file_idx = len(valid_files)
                valid_files.append((file_idx, content))

                # Add metadata
                file_metadata.append({
                    "original_name": file.filename,
                    "content_type": content_type,
                    "size": len(content),
                    "safe_name": sanitize_filename(file.filename or f"file_{file_idx}.pdf"),
                    "mapping": file_mappings[file.filename]
                })
            except Exception as e:
                error_id = SecurityAwareErrorHandler.log_processing_error(
                    e, "batch_redaction_preparation", file.filename or "unnamed_file"
                )
                log_error(f"Error preparing file for redaction: {str(e)} [error_id={error_id}]")
                file_metadata.append({
                    "original_name": getattr(file, "filename", f"file_{i}"),
                    "content_type": getattr(file, "content_type", "application/octet-stream"),
                    "size": 0,
                    "status": "error",
                    "error": f"Error preparing file: {str(e)}"
                })

        # Check if we have any valid files
        if not valid_files:
            return JSONResponse(
                status_code=400,
                content={
                    "detail": "No valid files to process",
                    "batch_summary": {
                        "batch_id": batch_id,
                        "total_files": len(files),
                        "successful": 0,
                        "failed": len(files),
                        "total_time": time.time() - start_time
                    }
                }
            )

        # Prepare redaction items
        redaction_items = []
        for idx, content in valid_files:
            if idx < len(file_metadata) and "mapping" in file_metadata[idx]:
                mapping = file_metadata[idx]["mapping"]
                safe_name = file_metadata[idx]["safe_name"]
                output_path = f"{output_dir}/redacted_{safe_name}"
                redaction_items.append((idx, content, mapping, output_path))

        # Create a robust wrapper function that handles the type issues
        async def process_redaction_wrapper(item):
            """Process redaction with robust error handling and logging"""
            try:
                idx = item[0]  # Extract index
                content = item[1]  # Extract content
                mapping = item[2]  # Extract mapping
                output_path = item[3]  # Extract output path

                log_info(f"Processing redaction for file idx={idx}, output={output_path}")

                # Use the centralized PDFRedactionService
                from backend.app.document_processing.pdf import PDFRedactionService

                redactor = PDFRedactionService(content)
                redacted_path = redactor.apply_redactions(mapping, output_path)
                redactor.close()

                # Count applied redactions
                redaction_count = sum(
                    len(page.get("sensitive", []))
                    for page in mapping.get("pages", [])
                )

                log_info(f"Successfully processed redactions for file idx={idx}, count={redaction_count}")

                # Return results in a consistent format
                return idx, {
                    "status": "success",
                    "output_path": redacted_path,
                    "redactions_applied": redaction_count
                }
            except Exception as e:
                idx = item[0] if len(item) > 0 else "unknown"
                error_id = SecurityAwareErrorHandler.log_processing_error(
                    e, "pdf_redaction", f"file_{idx}"
                )
                log_error(f"Error applying redactions: {str(e)} [error_id={error_id}]")

                return idx, {
                    "status": "error",
                    "error": str(e)
                }

        # Process in parallel with the wrapper
        redaction_results = await ParallelProcessingCore.process_in_parallel(
            items=redaction_items,
            processor=process_redaction_wrapper,
            max_workers=max_parallel_files or 4,  # Set a default if None
            operation_id=f"batch_redaction_{batch_id}"
        )

        # Log the results for debugging
        log_info(f"Redaction results: {redaction_results}")

        # Create ZIP file with results
        zip_path = await SecureTempFileManager.create_secure_temp_file_async(
            suffix=".zip",
            prefix=f"redaction_batch_{batch_id}_"
        )

        # Calculate batch summary with robust error handling
        successful = 0
        failed = 0
        total_redactions = 0
        result_mapping = {}

        # Process results with explicit format checking
        for result in redaction_results:
            try:
                # Extract information from result with robust checking
                if isinstance(result, tuple) and len(result) == 2:
                    idx, result_data = result

                    # Check if result_data is also a tuple (this is the issue)
                    if isinstance(result_data, tuple) and len(result_data) == 2:
                        # Extract the actual result data from the nested tuple
                        _, actual_result_data = result_data
                        result_data = actual_result_data

                    # Now process result_data as before
                    if isinstance(result_data, dict) and result_data.get("status") == "success":
                        result_mapping[idx] = result_data
                        successful += 1

                        # Only add redactions if present and numeric
                        redactions = result_data.get("redactions_applied", 0)
                        if isinstance(redactions, (int, float)):
                            total_redactions += redactions
                    else:
                        result_mapping[idx] = {
                            "status": "error",
                            "error": result_data.get("error", "Unknown error") if isinstance(result_data,
                                                                                             dict) else "Invalid result format"
                        }
                        failed += 1
                else:
                    # If the result format is completely unexpected
                    log_warning(f"Unexpected result format: {result}")
                    failed += 1
            except Exception as e:
                log_error(f"Error processing redaction result: {str(e)}")
                failed += 1

        # Create batch summary
        batch_summary = {
            "batch_id": batch_id,
            "total_files": len(file_metadata),
            "successful": successful,
            "failed": failed,
            "total_redactions": total_redactions,
            "total_time": time.time() - start_time,
            "timestamp": time.time(),
            "file_results": []
        }

        # Create ZIP file with clear error handling
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Process each file
            for idx, metadata in enumerate(file_metadata):
                file_result = {
                    "file": metadata.get("original_name", f"file_{idx}"),
                    "status": "error",
                    "redactions_applied": 0,
                    "error": "Processing not attempted"
                }

                # Check if we have a result for this file
                if idx in result_mapping:
                    result = result_mapping[idx]

                    # Handle successful redaction
                    if result.get("status") == "success":
                        file_result = {
                            "file": metadata.get("original_name", f"file_{idx}"),
                            "status": "success",
                            "redactions_applied": result.get("redactions_applied", 0)
                        }

                        # Add file to zip
                        output_path = result.get("output_path")
                        if output_path and os.path.exists(output_path):
                            orig_name = metadata.get("original_name", f"file_{idx}.pdf")
                            safe_name = sanitize_filename(orig_name)
                            zipf.write(output_path, arcname=f"redacted_{safe_name}")
                    else:
                        # Handle error case
                        file_result = {
                            "file": metadata.get("original_name", f"file_{idx}"),
                            "status": "error",
                            "redactions_applied": 0,
                            "error": result.get("error", "Unknown error")
                        }

                batch_summary["file_results"].append(file_result)

            # Add batch summary to ZIP
            zipf.writestr("batch_summary.json", json.dumps(batch_summary, indent=2))

        # Record batch processing for GDPR compliance
        record_keeper.record_processing(
            operation_type="batch_redaction",
            document_type="multiple",
            entity_types_processed=[],
            processing_time=batch_summary["total_time"],
            file_count=len(file_metadata),
            entity_count=total_redactions,
            success=(successful > 0)
        )

        # Log batch operation
        log_batch_operation(
            "Batch Redaction",
            len(file_metadata),
            successful,
            batch_summary["total_time"]
        )

        # Create streaming response
        async def stream_zip():
            try:
                with open(zip_path, "rb") as f:
                    while chunk := f.read(CHUNK_SIZE):
                        yield chunk
                        await asyncio.sleep(0)
            except Exception as e:
                log_error(f"Error streaming ZIP file: {str(e)}")

        # Get memory statistics
        mem_stats = memory_monitor.get_memory_stats()

        # Schedule cleanup tasks
        background_tasks.add_task(SecureTempFileManager.secure_delete_file, zip_path)

        # Create response
        return StreamingResponse(
            stream_zip(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename=redacted_batch_{batch_id}.zip",
                "X-Batch-ID": batch_id,
                "X-Batch-Time": f"{batch_summary['total_time']:.3f}s",
                "X-Successful-Count": str(successful),
                "X-Failed-Count": str(failed),
                "X-Total-Redactions": str(total_redactions),
                "X-Memory-Usage": f"{mem_stats['current_usage']:.1f}%",
                "X-Peak-Memory": f"{mem_stats['peak_usage']:.1f}%"
            }
        )

    @staticmethod
    async def batch_extract_text(
            files: List[UploadFile],
            max_parallel_files: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Extract text from multiple PDF files in parallel with optimized resource utilization.

        Args:
            files: List of uploaded files
            max_parallel_files: Maximum number of files to process in parallel

        Returns:
            Dict with batch extraction results
        """
        start_time = time.time()
        batch_id = str(uuid.uuid4())
        log_info(f"Starting batch text extraction (Batch ID: {batch_id})")

        # Determine processing strategy
        use_memory, total_size, optimal_workers = BatchProcessingUtils.determine_processing_strategy(files)

        # Adjust by user-specified max workers if provided
        if max_parallel_files is not None:
            optimal_workers = min(optimal_workers, max_parallel_files)

        # Validate and prepare files
        pdf_files = []
        pdf_indices = []
        file_metadata = []

        for i, file in enumerate(files):
            try:
                content_type = file.content_type or "application/octet-stream"
                if "pdf" in content_type.lower():
                    await file.seek(0)
                    content = await file.read()
                    pdf_files.append(content)
                    pdf_indices.append(i)

                    # Add metadata
                    file_metadata.append({
                        "original_name": file.filename or f"file_{i}.pdf",
                        "content_type": content_type,
                        "size": len(content)
                    })
                else:
                    # Add non-PDF metadata with error
                    file_metadata.append({
                        "original_name": file.filename or f"file_{i}",
                        "content_type": content_type,
                        "size": 0,
                        "status": "error",
                        "error": "Only PDF files are supported for text extraction"
                    })
            except Exception as e:
                log_error(f"Error preparing file for extraction: {str(e)}")
                file_metadata.append({
                    "original_name": getattr(file, "filename", f"file_{i}"),
                    "content_type": getattr(file, "content_type", "application/octet-stream"),
                    "size": 0,
                    "status": "error",
                    "error": f"Error preparing file: {str(e)}"
                })

        if not pdf_files:
            return {
                "batch_summary": {
                    "batch_id": batch_id,
                    "total_files": len(files),
                    "successful": 0,
                    "failed": len(files),
                    "total_pages": 0,
                    "total_words": 0,
                    "total_time": time.time() - start_time
                },
                "file_results": []
            }

        # Extract text from PDFs in parallel
        extraction_results = await BatchProcessingUtils.extract_text_from_pdf_batch(
            pdf_files,
            max_workers=optimal_workers,
        )

        # Process results
        file_results = []
        successful = 0
        failed = 0
        total_pages = 0
        total_words = 0

        # Create mapping for results
        result_mapping = {}
        for idx, result in extraction_results:
            result_mapping[idx] = result

        # Process each file
        for i, metadata in enumerate(file_metadata):
            # Skip non-PDF files that were already marked as errors
            if "status" in metadata and metadata["status"] == "error":
                file_results.append({
                    "file": metadata["original_name"],
                    "status": "error",
                    "error": metadata["error"]
                })
                failed += 1
                continue

            # For PDF files, check if we have extraction results
            pdf_index = pdf_indices[i] if i < len(pdf_indices) else None
            if pdf_index is not None and pdf_index in result_mapping:
                # We have extraction results
                result = result_mapping[pdf_index]

                if isinstance(result, dict) and "error" in result:
                    # Extraction failed
                    file_results.append({
                        "file": metadata["original_name"],
                        "status": "error",
                        "error": result["error"]
                    })
                    failed += 1
                else:
                    # Apply data minimization
                    minimized_data = minimize_extracted_data(result)

                    # Calculate statistics
                    pages_count = len(minimized_data.get("pages", []))
                    words_count = sum(len(page.get("words", [])) for page in minimized_data.get("pages", []))

                    total_pages += pages_count
                    total_words += words_count

                    # Add performance data
                    extraction_time = 0
                    if isinstance(result, dict) and "extraction_time" in result:
                        extraction_time = result["extraction_time"]

                    minimized_data["performance"] = {
                        "extraction_time": extraction_time,
                        "pages_count": pages_count,
                        "words_count": words_count
                    }

                    # Add file information
                    minimized_data["file_info"] = {
                        "filename": metadata["original_name"],
                        "content_type": metadata["content_type"],
                        "size": metadata["size"]
                    }

                    file_results.append({
                        "file": metadata["original_name"],
                        "status": "success",
                        "results": minimized_data
                    })

                    successful += 1
            else:
                # No extraction results for this file
                file_results.append({
                    "file": metadata["original_name"],
                    "status": "error",
                    "error": "Extraction failed or file not processed"
                })
                failed += 1

        # Calculate batch summary
        total_time = time.time() - start_time

        batch_summary = {
            "batch_id": batch_id,
            "total_files": len(files),
            "successful": successful,
            "failed": failed,
            "total_pages": total_pages,
            "total_words": total_words,
            "total_time": total_time,
            "workers": optimal_workers
        }

        # Log batch operation
        log_batch_operation(
            "Batch Text Extraction",
            len(files),
            successful,
            total_time
        )

        # Record batch processing for GDPR compliance
        record_keeper.record_processing(
            operation_type="batch_text_extraction",
            document_type="multiple_files",
            entity_types_processed=[],
            processing_time=total_time,
            file_count=len(files),
            entity_count=0,
            success=(successful > 0)
        )

        # Create final response
        response = {
            "batch_summary": batch_summary,
            "file_results": file_results
        }

        # Add memory statistics
        mem_stats = memory_monitor.get_memory_stats()
        response["_debug"] = {
            "memory_usage": mem_stats["current_usage"],
            "peak_memory": mem_stats["peak_usage"],
            "operation_id": batch_id
        }

        return response

    @staticmethod
    async def _get_initialized_detector(
            detection_engine: EntityDetectionEngine,
            use_presidio: bool = True,
            use_gemini: bool = False,
            use_gliner: bool = False,
            entity_list: Optional[List[str]] = None
    ) -> Any:
        """
        Get an initialized detector instance for entity detection.

        Args:
            detection_engine: Detection engine to use
            use_presidio: Whether to use Presidio (for hybrid engine)
            use_gemini: Whether to use Gemini (for hybrid engine)
            use_gliner: Whether to use GLiNER (for hybrid engine)
            entity_list: List of entity types to detect

        Returns:
            Detector instance
        """
        if detection_engine == EntityDetectionEngine.HYBRID:
            # Configure hybrid detector
            config = {
                "use_presidio": use_presidio,
                "use_gemini": use_gemini,
                "use_gliner": use_gliner
            }

            # Add entities to config if provided
            if entity_list:
                config["entities"] = entity_list

            # Get hybrid detector
            detector = initialization_service.get_detector(detection_engine, config)
        else:
            # For non-hybrid detectors, pass entity_list as a dictionary when needed
            if entity_list and detection_engine == EntityDetectionEngine.GLINER:
                config = {"entities": entity_list}
                detector = initialization_service.get_detector(detection_engine, config)
            else:
                # Get standard detector
                detector = initialization_service.get_detector(detection_engine, None)

        if detector is None:
            raise ValueError(f"Failed to initialize {detection_engine.name} detector")

        return detector
