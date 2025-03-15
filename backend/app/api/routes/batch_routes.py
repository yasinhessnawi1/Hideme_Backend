"""
Batch processing routes for handling multiple files in a single request.
"""
import json

from backend.app.factory.document_processing import EntityDetectionEngine
from backend.app.services.batch_processing_service import BatchProcessingService
import os
import time
import asyncio
import uuid
from typing import List, Optional, Dict, Any
from tempfile import NamedTemporaryFile, TemporaryDirectory
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from zipfile import ZipFile, ZIP_DEFLATED

from backend.app.factory.document_processing import (
    DocumentProcessingFactory,
    DocumentFormat,
)
from backend.app.utils.helpers.parallel_helper import ParallelProcessingHelper
from backend.app.utils.logger import log_info, log_error, log_warning
router = APIRouter()


@router.post("/detect")
async def batch_detect_sensitive(
        files: List[UploadFile] = File(...),
        requested_entities: Optional[str] = Form(None),
        detection_engine: Optional[str] = Form("presidio"),
        max_parallel_files: Optional[int] = Form(4)
):
    """
    Process multiple files for entity detection using a single engine.

    Args:
        files: List of uploaded files
        requested_entities: JSON string of entity types to detect (optional)
        detection_engine: Entity detection engine to use (presidio, gemini, gliner)
        max_parallel_files: Maximum number of files to process in parallel

    Returns:
        JSON response with batch processing results
    """
    start_time = time.time()

    try:
        # Validate detection engine
        engine_map = {
            "presidio": EntityDetectionEngine.PRESIDIO,
            "gemini": EntityDetectionEngine.GEMINI,
            "gliner": EntityDetectionEngine.GLINER
        }

        if detection_engine not in engine_map:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid detection engine. Must be one of: {', '.join(engine_map.keys())}"
            )

        # Process files
        results = await BatchProcessingService.detect_entities_in_files(
            files=files,
            requested_entities=requested_entities,
            detection_engine=engine_map[detection_engine],
            max_parallel_files=max_parallel_files
        )

        # Add processing timing
        total_time = time.time() - start_time
        results["batch_summary"]["api_time"] = total_time

        log_info(f"[PERF] Batch detection API call completed in {total_time:.2f}s")

        return JSONResponse(content=results)

    except Exception as e:
        log_error(f"[ERROR] Error in batch_detect_sensitive: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "batch_summary": {
                    "total_files": len(files),
                    "successful": 0,
                    "failed": len(files),
                    "total_time": time.time() - start_time
                }
            }
        )


@router.post("/hybrid_detect")
async def batch_hybrid_detect_sensitive(
        files: List[UploadFile] = File(...),
        requested_entities: Optional[str] = Form(None),
        use_presidio: bool = Form(True),
        use_gemini: bool = Form(True),
        use_gliner: bool = Form(False),
        max_parallel_files: Optional[int] = Form(4)
):
    """
    Process multiple files for entity detection using hybrid detection.

    Args:
        files: List of uploaded files
        requested_entities: JSON string of entity types to detect (optional)
        use_presidio: Whether to use Presidio for detection
        use_gemini: Whether to use Gemini for detection
        use_gliner: Whether to use GLiNER for detection
        max_parallel_files: Maximum number of files to process in parallel

    Returns:
        JSON response with batch processing results
    """
    start_time = time.time()

    try:
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

        log_info(f"[PERF] Batch hybrid detection API call completed in {total_time:.2f}s")

        return JSONResponse(content=results)

    except Exception as e:
        log_error(f"[ERROR] Error in batch_hybrid_detect_sensitive: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "batch_summary": {
                    "total_files": len(files),
                    "successful": 0,
                    "failed": len(files),
                    "total_time": time.time() - start_time
                }
            }
        )


@router.post("/extract")
async def batch_extract_text(
        files: List[UploadFile] = File(...),
        max_parallel_files: Optional[int] = Form(4)
):
    """
    Extract text with positions from multiple PDF files in parallel.

    Args:
        files: List of uploaded PDF files
        max_parallel_files: Maximum number of files to process in parallel

    Returns:
        JSON response with extracted text and positions for each file
    """
    start_time = time.time()

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    # Use temporary directory for file processing
    with TemporaryDirectory() as temp_dir:
        # Save files to temporary directory
        file_paths = []
        file_meta = {}

        for file in files:
            try:
                # Generate unique filename
                file_uuid = str(uuid.uuid4())
                file_ext = os.path.splitext(file.filename)[1].lower() if file.filename else ".pdf"
                tmp_path = os.path.join(temp_dir, f"{file_uuid}{file_ext}")

                # Read and save file
                contents = await file.read()
                with open(tmp_path, "wb") as f:
                    f.write(contents)

                # Reset file cursor
                await file.seek(0)

                # Store metadata
                file_meta[tmp_path] = {
                    "original_name": file.filename,
                    "content_type": file.content_type,
                    "size": len(contents)
                }

                file_paths.append(tmp_path)
            except Exception as e:
                log_error(f"[ERROR] Failed to process file {file.filename}: {str(e)}")
                continue

        if not file_paths:
            raise HTTPException(status_code=400, detail="No valid files provided for processing")

        # Optimize worker count
        optimal_workers = ParallelProcessingHelper.get_optimal_workers(
            len(file_paths),
            min_workers=1,
            max_workers=max_parallel_files
        )

        # Define file extraction function
        async def extract_file(file_path: str) -> Dict[str, Any]:
            """Extract text from a single file."""
            file_start_time = time.time()
            file_name = file_meta[file_path]["original_name"]

            try:
                # Determine document format
                doc_format = None
                if file_path.lower().endswith('.pdf'):
                    doc_format = DocumentFormat.PDF
                elif file_path.lower().endswith(('.docx', '.doc')):
                    doc_format = DocumentFormat.DOCX
                elif file_path.lower().endswith('.txt'):
                    doc_format = DocumentFormat.TXT

                # Create extractor
                extractor = DocumentProcessingFactory.create_document_extractor(
                    file_path, doc_format
                )

                # Extract text
                extracted_data = await asyncio.to_thread(extractor.extract_text_with_positions)
                extractor.close()

                # Calculate statistics
                total_words = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))

                # Add performance metrics
                extracted_data["performance"] = {
                    "extraction_time": time.time() - file_start_time,
                    "pages_count": len(extracted_data.get("pages", [])),
                    "words_count": total_words
                }

                # Add file information
                extracted_data["file_info"] = {
                    "filename": file_name,
                    "content_type": file_meta[file_path]["content_type"],
                    "size": file_meta[file_path]["size"]
                }

                return {
                    "file": file_name,
                    "status": "success",
                    "results": extracted_data
                }
            except Exception as e:
                log_error(f"[ERROR] Error extracting text from {file_name}: {str(e)}")
                return {
                    "file": file_name,
                    "status": "error",
                    "error": str(e),
                    "processing_time": time.time() - file_start_time
                }

        # Process files in parallel
        log_info(f"[OK] Extracting text from {len(file_paths)} files with {optimal_workers} workers")
        tasks = [extract_file(file_path) for file_path in file_paths]
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

    # Build response
    response = {
        "batch_summary": {
            "total_files": len(files),
            "successful": success_count,
            "failed": error_count,
            "total_pages": total_pages,
            "total_words": total_words,
            "total_time": batch_time,
            "workers": optimal_workers
        },
        "file_results": results
    }

    log_info(f"[PERF] Batch extraction completed in {batch_time:.2f}s. "
             f"Successfully processed {success_count}/{len(files)} files. "
             f"Extracted {total_pages} pages and {total_words} words.")

    return JSONResponse(content=response)


@router.post("/redact")
async def batch_redact_documents(
        background_tasks: BackgroundTasks,
        files: List[UploadFile] = File(...),
        redaction_mappings: str = Form(...),
        max_parallel_files: Optional[int] = Form(4)
):
    """
    Apply redactions to multiple documents and return them as a zip file.

    This endpoint accepts the same output format as the batch/detect and
    batch/hybrid_detect endpoints, making it easy to pipe detection results
    directly to redaction.

    Args:
        background_tasks: FastAPI BackgroundTasks for cleanup
        files: List of uploaded documents
        redaction_mappings: JSON string with batch detection results
        max_parallel_files: Maximum number of files to process in parallel

    Returns:
        ZIP file containing all redacted documents
    """
    start_time = time.time()

    # Create temporary directories
    temp_input_dir = TemporaryDirectory()
    temp_output_dir = TemporaryDirectory()
    zip_output_path = NamedTemporaryFile(delete=False, suffix=".zip")
    zip_output_filename = zip_output_path.name

    try:
        # Parse redaction mappings from batch detection output
        try:
            detection_results = json.loads(redaction_mappings)

            # Extract redaction mappings from detection results
            mappings_data = {}

            # Handle direct redaction_mapping format
            if "redaction_mapping" in detection_results:
                # Single file format - convert to batch format
                if "file_info" in detection_results and "filename" in detection_results["file_info"]:
                    filename = detection_results["file_info"]["filename"]
                    mappings_data[filename] = detection_results["redaction_mapping"]
            # Handle batch detection output format
            elif "file_results" in detection_results:
                for file_result in detection_results["file_results"]:
                    if file_result["status"] == "success" and "results" in file_result:
                        filename = file_result["file"]
                        if "redaction_mapping" in file_result["results"]:
                            mappings_data[filename] = file_result["results"]["redaction_mapping"]

            if not mappings_data:
                raise HTTPException(
                    status_code=400,
                    detail="Could not extract valid redaction mappings from provided JSON."
                )

        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid redaction_mappings JSON format")

        # Register cleanup tasks for temp directories - NOT for the zip file yet
        background_tasks.add_task(lambda: temp_input_dir.cleanup())
        background_tasks.add_task(lambda: temp_output_dir.cleanup())

        # Save uploaded files to input directory
        file_paths = []
        file_meta = {}

        for file in files:
            try:
                # Use original filename for better mapping to redaction data
                safe_filename = file.filename
                input_path = os.path.join(temp_input_dir.name, safe_filename)

                # Read and save file
                contents = await file.read()
                with open(input_path, "wb") as f:
                    f.write(contents)

                # Reset file cursor
                await file.seek(0)

                # Store metadata
                file_meta[input_path] = {
                    "original_name": file.filename,
                    "content_type": file.content_type,
                    "size": len(contents),
                    "output_path": os.path.join(
                        temp_output_dir.name,
                        f"redacted_{safe_filename}"
                    )
                }

                file_paths.append(input_path)
            except Exception as e:
                log_error(f"[ERROR] Failed to process file {file.filename}: {str(e)}")
                continue

        if not file_paths:
            raise HTTPException(status_code=400, detail="No valid files provided for processing")

        # Optimize worker count
        optimal_workers = ParallelProcessingHelper.get_optimal_workers(
            len(file_paths),
            min_workers=1,
            max_workers=max_parallel_files
        )

        # Define file redaction function
        async def redact_file(file_path: str) -> Dict[str, Any]:
            """Apply redactions to a single file."""
            file_start_time = time.time()
            file_name = file_meta[file_path]["original_name"]
            output_path = file_meta[file_path]["output_path"]

            try:
                # Get redaction mapping for this file
                if file_name not in mappings_data:
                    return {
                        "file": file_name,
                        "status": "error",
                        "error": "No redaction mapping provided for this file"
                    }

                redaction_mapping = mappings_data[file_name]

                # Determine document format
                doc_format = None
                if file_path.lower().endswith('.pdf'):
                    doc_format = DocumentFormat.PDF
                elif file_path.lower().endswith(('.docx', '.doc')):
                    doc_format = DocumentFormat.DOCX
                elif file_path.lower().endswith('.txt'):
                    doc_format = DocumentFormat.TXT

                # Create redactor
                redactor = DocumentProcessingFactory.create_document_redactor(
                    file_path, doc_format
                )

                # Apply redactions
                await asyncio.to_thread(
                    redactor.apply_redactions,
                    redaction_mapping,
                    output_path
                )

                redact_time = time.time() - file_start_time

                return {
                    "file": file_name,
                    "status": "success",
                    "output_file": os.path.basename(output_path),
                    "redaction_time": redact_time
                }
            except Exception as e:
                log_error(f"[ERROR] Error redacting {file_name}: {str(e)}")
                return {
                    "file": file_name,
                    "status": "error",
                    "error": str(e),
                    "processing_time": time.time() - file_start_time
                }

        # Process files in parallel
        log_info(f"[OK] Redacting {len(file_paths)} files with {optimal_workers} workers")
        tasks = [redact_file(file_path) for file_path in file_paths]
        results = await asyncio.gather(*tasks)

        # Create ZIP file with redacted documents
        with ZipFile(zip_output_filename, 'w', ZIP_DEFLATED) as zipf:
            for result in results:
                if result["status"] == "success":
                    file_name = result["file"]
                    # Find original input path to get output path from metadata
                    for input_path, meta in file_meta.items():
                        if meta["original_name"] == file_name:
                            zipf.write(
                                meta["output_path"],
                                arcname=f"redacted_{os.path.basename(file_name)}"
                            )
                            break

        # Calculate batch statistics
        batch_time = time.time() - start_time
        success_count = sum(1 for r in results if r.get("status") == "success")
        error_count = len(results) - success_count

        # Add batch summary to metadata file in ZIP
        batch_summary = {
            "total_files": len(files),
            "successful": success_count,
            "failed": error_count,
            "total_time": batch_time,
            "workers": optimal_workers,
            "file_results": results
        }

        summary_file = os.path.join(temp_output_dir.name, "batch_summary.json")
        with open(summary_file, 'w') as f:
            json.dump(batch_summary, f, indent=2)

        # Add summary to ZIP
        with ZipFile(zip_output_filename, 'a', ZIP_DEFLATED) as zipf:
            zipf.write(summary_file, arcname="batch_summary.json")

        log_info(f"[PERF] Batch redaction completed in {batch_time:.2f}s. "
                 f"Successfully redacted {success_count}/{len(files)} files.")

        # Create a delayed cleanup function that will execute after the file has been sent
        def delayed_cleanup():
            try:
                # Sleep for a short time to ensure file is no longer in use
                time.sleep(1)
                if os.path.exists(zip_output_filename):
                    os.remove(zip_output_filename)
                log_info(f"[OK] Temporary zip file removed: {zip_output_filename}")
            except Exception as e:
                log_error(f"[ERROR] Failed to remove temporary zip file: {str(e)}")

        # Add delayed cleanup task
        background_tasks.add_task(delayed_cleanup)

        # Return the ZIP file
        return FileResponse(
            zip_output_filename,
            media_type="application/zip",
            filename="redacted_documents.zip",
            headers={
                "X-Batch-Time": f"{batch_time:.3f}s",
                "X-Success-Count": str(success_count),
                "X-Error-Count": str(error_count)
            }
        )

    except Exception as e:
        # Clean up the zip file in case of an error
        try:
            if os.path.exists(zip_output_filename):
                os.remove(zip_output_filename)
        except Exception as cleanup_error:
            log_error(f"[ERROR] Failed to clean up zip file after error: {str(cleanup_error)}")

        log_error(f"[ERROR] Error in batch_redact_documents: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))