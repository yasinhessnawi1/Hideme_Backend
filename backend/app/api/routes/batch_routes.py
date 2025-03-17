import asyncio
import os
import time
from typing import List, Optional

from fastapi import APIRouter, File, UploadFile, Form, HTTPException, BackgroundTasks, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

from backend.app.configs.gdpr_config import TEMP_FILE_RETENTION_SECONDS
from backend.app.factory import DocumentFormat, EntityDetectionEngine, DocumentProcessingFactory
from backend.app.services.batch_processing_service import BatchProcessingService
from backend.app.utils.batch_processing_utils import (
    validate_detection_engine,
    adjust_parallelism_based_on_memory,
    validate_redaction_mappings,
    determine_processing_strategy,
    process_batch_in_memory,
    process_batch_with_temp_files
)
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.helpers.batch_processing_helper import validate_batch_files_optimized, BatchProcessingHelper
from backend.app.utils.memory_management import memory_optimized, memory_monitor
from backend.app.utils.processing_records import record_keeper
from backend.app.utils.retention_management import retention_manager
from backend.app.utils.secure_file_utils import SecureTempFileManager
from backend.app.utils.secure_logging import log_batch_operation

# Configure rate limiter
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


@router.post("/detect")
@limiter.limit("10/minute")
async def batch_detect_sensitive(
        request: Request,
        files: List[UploadFile] = File(...),
        requested_entities: Optional[str] = Form(None),
        detection_engine: Optional[str] = Form("presidio"),
        max_parallel_files: Optional[int] = Form(4)
):
    """
    Process multiple files for entity detection with enhanced memory efficiency.

    This optimized implementation:
    - Processes files in memory when possible to avoid temp file creation
    - Uses streaming for large files to reduce memory usage
    - Implements adaptive parallelism based on memory pressure
    - Ensures proper cleanup of any temporary resources
    """
    start_time = time.time()

    try:
        # Validate detection engine
        is_valid, engine_result = await validate_detection_engine(detection_engine)
        if not is_valid:
            return JSONResponse(status_code=400, content=engine_result)

        # Adjust parallelism based on memory pressure
        adjusted_parallel_files = adjust_parallelism_based_on_memory(max_parallel_files)

        # Use the optimized batch validation helper
        allowed_types = {"application/pdf", "text/plain", "text/csv", "text/markdown", "text/html"}
        async for valid_files in validate_batch_files_optimized(files, allowed_types):
            # Process files with optimized parallelization
            results = await BatchProcessingService.detect_entities_in_files(
                files=[f[0] for f in valid_files],  # Use original UploadFile objects
                requested_entities=requested_entities,
                detection_engine=engine_result,
                max_parallel_files=adjusted_parallel_files
            )

            # Add processing timing
            total_time = time.time() - start_time
            results["batch_summary"]["api_time"] = total_time

            # Add engine information
            results["model_info"] = {
                "engine": detection_engine,
                "max_parallel": adjusted_parallel_files,
                "actual_parallel": results["batch_summary"].get("workers", adjusted_parallel_files)
            }

            # Add memory statistics
            from backend.app.utils.memory_management import memory_monitor
            mem_stats = memory_monitor.get_memory_stats()
            results["_debug"] = {
                "memory_usage": mem_stats["current_usage"],
                "peak_memory": mem_stats["peak_usage"]
            }

            return JSONResponse(content=results)

    except HTTPException as e:
        # Re-raise HTTP exceptions
        raise e
    except Exception as e:
        error_response = SecurityAwareErrorHandler.handle_detection_error(e, "batch_detection")
        error_response.update({
            "batch_summary": {
                "total_files": len(files),
                "successful": 0,
                "failed": len(files),
                "total_time": time.time() - start_time
            }
        })
        return JSONResponse(status_code=500, content=error_response)


@router.post("/redact")
@limiter.limit("3/minute")
async def batch_redact_documents(
        request: Request,
        background_tasks: BackgroundTasks,
        files: List[UploadFile] = File(...),
        redaction_mappings: str = Form(...),
        max_parallel_files: Optional[int] = Form(4)
):
    """
    Apply redactions to multiple documents and return them as a ZIP file via streaming.

    This optimized implementation:
    - Avoids temporary directory creation when possible
    - Processes PDFs entirely in memory
    - Uses an in-memory ZIP buffer for smaller batches
    - Falls back to disk-based processing only for large files
    - Streams the output directly to the client
    """
    start_time = time.time()

    # Adjust parallelism based on memory pressure
    adjusted_parallel_files = adjust_parallelism_based_on_memory(max_parallel_files)

    try:
        # Validate and parse redaction mappings
        is_valid, mappings_result = await validate_redaction_mappings(redaction_mappings)
        if not is_valid:
            return JSONResponse(status_code=400, content=mappings_result)

        mappings_data = mappings_result

        # Determine processing strategy (in-memory vs. temp files)
        use_memory_buffer, total_size = await determine_processing_strategy(files)

        # Use appropriate processing strategy
        if use_memory_buffer:
            return await process_batch_in_memory(
                files, mappings_data, adjusted_parallel_files, start_time, background_tasks
            )
        else:
            return await process_batch_with_temp_files(
                files, mappings_data, adjusted_parallel_files, start_time, background_tasks
            )

    except Exception as e:
        error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
            e, "batch_redaction", 500
        )
        return JSONResponse(status_code=status_code, content=error_response)


@router.post("/hybrid_detect")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=200)
async def batch_hybrid_detect_sensitive(
        request: Request,
        files: List[UploadFile] = File(...),
        requested_entities: Optional[str] = Form(None),
        use_presidio: bool = Form(True),
        use_gemini: bool = Form(True),
        use_gliner: bool = Form(False),
        max_parallel_files: Optional[int] = Form(4)
):
    """
    Process multiple files using hybrid detection with enhanced security and memory optimization.

    Processes files under GDPR Article 6(1)(f) for legitimate interests of enhancing
    document security and privacy.
    """
    start_time = time.time()

    try:
        # Validate detection engines are selected
        if not any([use_presidio, use_gemini, use_gliner]):
            return JSONResponse(
                status_code=400,
                content={"detail": "At least one detection engine must be selected"}
            )

        # Adjust max parallel files with memory-aware constraint
        max_parallel_files = BatchProcessingHelper.get_optimal_batch_size(
            len(files),
            sum(file.size or 0 for file in files)
        )

        # Process files with hybrid detection
        results = await BatchProcessingService.detect_entities_in_files(
            files=files,
            requested_entities=requested_entities,
            use_presidio=use_presidio,
            use_gemini=use_gemini,
            use_gliner=use_gliner,
            max_parallel_files=max_parallel_files,
            detection_engine=EntityDetectionEngine.HYBRID
        )

        # Add processing timing
        total_time = time.time() - start_time
        results["batch_summary"]["api_time"] = total_time

        # Get total entities found
        total_entities = results["batch_summary"].get("total_entities", 0)

        # Record the processing operation
        record_keeper.record_processing(
            operation_type="batch_hybrid_detection",
            document_type="multiple",
            entity_types_processed=[],  # Entity types are handled per file
            processing_time=total_time,
            file_count=len(files),
            entity_count=total_entities,
        )

        # Log performance without sensitive details
        log_batch_operation(
            "Batch Hybrid Detection",
            len(files),
            results["batch_summary"]["successful"],
            total_time
        )

        # Add model information
        results["model_info"] = {
            "engine": "hybrid",
            "engines_used": {
                "presidio": use_presidio,
                "gemini": use_gemini,
                "gliner": use_gliner
            },
            "max_parallel": max_parallel_files,
            "actual_parallel": results["batch_summary"].get("workers", max_parallel_files)
        }

        # Add memory statistics
        mem_stats = memory_monitor.get_memory_stats()
        results["_debug"] = {
            "memory_usage": mem_stats["current_usage"],
            "peak_memory": mem_stats["peak_usage"]
        }

        return JSONResponse(content=results)

    except HTTPException as e:
        # Re-raise HTTP exceptions
        raise e
    except Exception as e:
        # Enhanced error handling
        error_response = SecurityAwareErrorHandler.handle_detection_error(e, "batch_hybrid_detection")
        error_response.update({
            "batch_summary": {
                "total_files": len(files),
                "successful": 0,
                "failed": len(files),
                "total_time": time.time() - start_time
            },
            "model_info": {
                "engine": "hybrid",
                "engines_used": {
                    "presidio": use_presidio,
                    "gemini": use_gemini,
                    "gliner": use_gliner
                }
            }
        })
        return JSONResponse(status_code=500, content=error_response)



@router.post("/extract")
@limiter.limit("15/minute")
@memory_optimized(threshold_mb=50)
async def batch_extract_text(
        request: Request,
        files: List[UploadFile] = File(...),
        max_parallel_files: Optional[int] = Form(4)
):
    """
    Extract text with positions from multiple files in parallel with enhanced security.

    Processes files under GDPR Article 6(1)(f) - legitimate interests of document
    security and privacy processing.

    Args:
        request: FastAPI request object for rate limiting
        files: List of uploaded files
        max_parallel_files: Maximum number of files to process in parallel

    Returns:
        JSON response with extracted text and positions for each file
    """
    start_time = time.time()

    # Optimize parallel files based on system resources
    max_parallel_files = BatchProcessingHelper.get_optimal_batch_size(
        len(files),
        sum(file.size or 0 for file in files)
    )

    try:
        # Process files using the optimized batch processing helper
        valid_files_list = []
        async for batch in validate_batch_files_optimized(files):
            valid_files_list.extend(batch)

        # Define text extraction function
        async def extract_file(file_tuple):
            """Extract text from a single file with enhanced security."""
            file_start_time = time.time()
            file, file_path, content, safe_filename = file_tuple
            file_name = file.filename or "unnamed_file"

            try:
                # Register with retention manager for automatic cleanup
                if file_path:
                    retention_manager.register_processed_file(file_path, TEMP_FILE_RETENTION_SECONDS)

                # Determine document format
                doc_format = None
                if file_name.lower().endswith('.pdf'):
                    doc_format = DocumentFormat.PDF
                elif file_name.lower().endswith(('.docx', '.doc')):
                    doc_format = DocumentFormat.DOCX
                elif file_name.lower().endswith('.txt'):
                    doc_format = DocumentFormat.TXT

                # Create extractor
                extractor = DocumentProcessingFactory.create_document_extractor(
                    file_path if file_path else content,
                    doc_format
                )

                # Extract text with performance tracking
                extracted_data = await asyncio.to_thread(extractor.extract_text)
                extractor.close()

                # Apply data minimization
                from backend.app.utils.data_minimization import minimize_extracted_data
                extracted_data = minimize_extracted_data(extracted_data)

                # Calculate statistics
                total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))

                # Add performance metrics
                extraction_time = time.time() - file_start_time
                extracted_data["performance"] = {
                    "extraction_time": extraction_time,
                    "pages_count": len(extracted_data.get("pages", [])),
                    "words_count": total_words
                }

                # Add file information (no sensitive content)
                extracted_data["file_info"] = {
                    "filename": file_name,
                    "content_type": file.content_type or "application/octet-stream",
                    "size": len(content)
                }

                return {
                    "file": file_name,
                    "status": "success",
                    "results": extracted_data
                }
            except Exception as e:
                return SecurityAwareErrorHandler.handle_file_processing_error(e, "text_extraction", file_name)
            finally:
                # Ensure temporary file is cleaned up
                if file_path and os.path.exists(file_path):
                    await SecureTempFileManager.secure_delete_file_async(file_path)

        # Log batch operation start
        log_batch_operation(
            "Batch Text Extraction Started",
            len(valid_files_list),
            len(valid_files_list),
            0
        )

        # Process files in parallel
        tasks = [extract_file(file_tuple) for file_tuple in valid_files_list]
        results = await asyncio.gather(*tasks)

        # Calculate batch statistics
        batch_time = time.time() - start_time
        success_count = sum(1 for r in results if r.get("status") == "success")
        error_count = len(results) - success_count
        total_words = sum(
            r.get("results", {}).get("performance", {}).get("words_count", 0)
            for r in results if r.get("status") == "success"
        )
        total_pages = sum(
            r.get("results", {}).get("performance", {}).get("pages_count", 0)
            for r in results if r.get("status") == "success"
        )

        # Record the processing operation
        record_keeper.record_processing(
            operation_type="batch_text_extraction",
            document_type="multiple",
            entity_types_processed=[],
            processing_time=batch_time,
            file_count=len(files),
            entity_count=0,
        )

        # Build response
        response = {
            "batch_summary": {
                "total_files": len(files),
                "successful": success_count,
                "failed": error_count,
                "total_pages": total_pages,
                "total_words": total_words,
                "total_time": batch_time,
                "workers": max_parallel_files
            },
            "file_results": results
        }

        # Log performance
        log_batch_operation(
            "Batch Text Extraction Completed",
            len(files),
            success_count,
            batch_time
        )

        # Add memory statistics
        mem_stats = memory_monitor.get_memory_stats()
        response["_debug"] = {
            "memory_usage": mem_stats["current_usage"],
            "peak_memory": mem_stats["peak_usage"]
        }

        return JSONResponse(content=response)

    except HTTPException as e:
        raise e
    except Exception as e:
        # Enhanced error handling
        error_response = SecurityAwareErrorHandler.handle_detection_error(e, "batch_extract")
        error_response.update({
            "batch_summary": {
                "total_files": len(files),
                "successful": 0,
                "failed": len(files),
                "total_time": time.time() - start_time
            }
        })
        return JSONResponse(status_code=500, content=error_response)
