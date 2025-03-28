"""
BatchRedactService.py

Service for batch redaction.
This service processes multiple PDF files for redaction in batch mode using the PDFRedactionService.
It is divided into helper functions that:
  • Parse the redaction mappings.
  • Read and validate the uploaded files.
  • Prepare redaction items for processing.
  • Process redaction items concurrently.
  • Compute summary statistics and build a ZIP archive of redacted files.
  • Build and return the final streaming response.
"""

import asyncio
import json
import os
import time
import uuid
import zipfile
from typing import List, Dict, Any, Optional, Tuple, Union

from fastapi import UploadFile, BackgroundTasks
from starlette.responses import JSONResponse, StreamingResponse

from backend.app.document_processing.pdf_redactor import PDFRedactionService
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.logging.secure_logging import log_batch_operation
from backend.app.utils.memory_management import memory_monitor
from backend.app.utils.parallel.core import ParallelProcessingCore
from backend.app.utils.secure_file_utils import SecureTempFileManager
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.validation.file_validation import sanitize_filename, validate_mime_type

# Constants
CHUNK_SIZE = 64 * 1024  # 64KB for streaming responses
DEFAULT_CONTENT_TYPE = "application/octet-stream"


class BatchRedactService:
    """
    Service for batch redaction.
    This service processes multiple PDF files for redaction in batch mode using the PDFRedactionService.
    """

    @staticmethod
    async def batch_redact_documents(
        files: List[UploadFile],
        redaction_mappings: str,
        remove_images: bool = False,
        max_parallel_files: Optional[int] = None,
        background_tasks: Optional[BackgroundTasks] = None
    ) -> Union[JSONResponse, StreamingResponse]:
        """
        Main method for batch redaction.
        It parses redaction mappings, reads and validates files, processes redactions in parallel,
        computes summary statistics, builds a ZIP archive of redacted files, and returns a streaming response.

        Args:
            files: List of uploaded PDF files.
            redaction_mappings: JSON string containing redaction mappings.
            remove_images: If True, images will be detected and redacted on each file.
            max_parallel_files: Maximum number of files to process concurrently.
            background_tasks: BackgroundTasks instance for scheduling cleanup tasks.

        Returns:
            A StreamingResponse streaming the ZIP archive of redacted files, or a JSONResponse with errors.
        """
        start_time = time.time()
        batch_id = str(uuid.uuid4())
        log_info(f"Starting batch redaction (Batch ID: {batch_id})")

        if background_tasks is None:
            background_tasks = BackgroundTasks()

        # Parse the redaction mappings.
        file_mappings = BatchRedactService._parse_redaction_mappings(redaction_mappings)
        if not file_mappings:
            return JSONResponse(
                status_code=400,
                content={"detail": "No valid redaction mappings found in the provided JSON"}
            )

        # Prepare output directory and schedule its deletion.
        output_dir = await SecureTempFileManager.create_secure_temp_dir_async(f"batch_redact_{batch_id}_")
        background_tasks.add_task(SecureTempFileManager.secure_delete_directory, output_dir)

        # Read and validate files.
        file_metadata, valid_files = await BatchRedactService._prepare_files_for_redaction(files, file_mappings)
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

        # Prepare redaction items.
        redaction_items = BatchRedactService._prepare_redaction_items(valid_files, file_metadata, output_dir)

        # Process redaction items concurrently, passing the remove_images flag.
        result_mapping = await BatchRedactService._process_redaction_items(
            redaction_items, max_parallel_files or 4, remove_images
        )
        log_info(f"Redaction results: {result_mapping}")

        # Compute summary and build ZIP archive.
        successful, _, _, _, batch_summary = BatchRedactService._compute_redaction_summary(
            file_metadata, result_mapping, start_time, batch_id
        )
        batch_summary["file_results"] = BatchRedactService._build_file_results(file_metadata, result_mapping)

        # Create ZIP file.
        zip_path_future = SecureTempFileManager.create_secure_temp_file_async(
            suffix=".zip", prefix=f"redaction_batch_{batch_id}_"
        )
        zip_path = await zip_path_future
        BatchRedactService._create_zip_archive(batch_summary, file_metadata, result_mapping, zip_path)

        # Record processing and log the batch operation.
        record_keeper.record_processing(
            operation_type="batch_redaction",
            document_type="multiple",
            entity_types_processed=[],
            processing_time=batch_summary["total_time"],
            file_count=len(file_metadata),
            entity_count=batch_summary["total_redactions"],
            success=(successful > 0)
        )
        log_batch_operation("Batch Redaction", len(file_metadata), successful, batch_summary["total_time"])

        # Build streaming response.
        return BatchRedactService.build_streaming_response(zip_path, batch_summary, batch_id)

    @staticmethod
    def build_streaming_response(zip_path: str, batch_summary: Dict[str, Any], batch_id: str) -> StreamingResponse:
        """
        Builds and returns a StreamingResponse for the ZIP archive.
        """
        mem_stats = memory_monitor.get_memory_stats()

        return StreamingResponse(
            BatchRedactService._stream_zip(zip_path),
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename=redacted_batch_{batch_id}.zip",
                "X-Batch-ID": batch_id,
                "X-Batch-Time": f"{batch_summary['total_time']:.3f}s",
                "X-Successful-Count": str(batch_summary["successful"]),
                "X-Failed-Count": str(batch_summary["failed"]),
                "X-Total-Redactions": str(batch_summary["total_redactions"]),
                "X-Memory-Usage": f"{mem_stats['current_usage']:.1f}%",
                "X-Peak-Memory": f"{mem_stats['peak_usage']:.1f}%"
            }
        )

    @staticmethod
    def _parse_redaction_mappings(redaction_mappings: str) -> Dict[str, Any]:
        """
        Parses the provided JSON string of redaction mappings.
        Returns a dictionary mapping filenames to their redaction mappings.
        """
        try:
            mapping_data = json.loads(redaction_mappings)
            file_mappings = {}

            # Single file mapping format.
            if ("redaction_mapping" in mapping_data and
                    "file_info" in mapping_data and
                    "filename" in mapping_data["file_info"]):
                filename = mapping_data["file_info"]["filename"]
                file_mappings[filename] = mapping_data["redaction_mapping"]

            # Multiple file mapping format.
            elif "file_results" in mapping_data:
                for file_result in mapping_data["file_results"]:
                    if file_result.get("status") == "success" and "results" in file_result:
                        filename = file_result["file"]
                        if "redaction_mapping" in file_result["results"]:
                            file_mappings[filename] = file_result["results"]["redaction_mapping"]

            return file_mappings

        except json.JSONDecodeError:
            return {}

    @staticmethod
    async def _prepare_files_for_redaction(
        files: List[UploadFile],
        file_mappings: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], List[Tuple[int, bytes]]]:
        """
        Reads and validates each file.
        Returns a tuple containing:
          - A list of file metadata dictionaries.
          - A list of tuples (index, file content) for valid PDF files.
        """
        file_metadata = []
        valid_files = []
        for i, file in enumerate(files):
            try:
                if file.filename not in file_mappings:
                    log_warning(f"No redaction mapping for file: {file.filename}")
                    file_metadata.append({
                        "original_name": file.filename,
                        "content_type": file.content_type or DEFAULT_CONTENT_TYPE,
                        "size": 0,
                        "status": "error",
                        "error": "No redaction mapping provided"
                    })
                    continue

                content_type = file.content_type or DEFAULT_CONTENT_TYPE
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

                await file.seek(0)
                content = await file.read()
                file_idx = len(valid_files)

                valid_files.append((file_idx, content))
                file_metadata.append({
                    "original_name": file.filename,
                    "content_type": content_type,
                    "size": len(content),
                    "safe_name": sanitize_filename(file.filename or f"file_{file_idx}.pdf"),
                    "mapping": file_mappings[file.filename]
                })

            except Exception as exc:
                error_id = SecurityAwareErrorHandler.log_processing_error(
                    exc, "batch_redaction_preparation", file.filename or "unnamed_file"
                )
                log_error(f"Error preparing file for redaction: {str(exc)} [error_id={error_id}]")
                file_metadata.append({
                    "original_name": getattr(file, "filename", f"file_{i}"),
                    "content_type": getattr(file, "content_type", DEFAULT_CONTENT_TYPE),
                    "size": 0,
                    "status": "error",
                    "error": f"Error preparing file: {str(exc)}"
                })

        return file_metadata, valid_files

    @staticmethod
    def _prepare_redaction_items(
        valid_files: List[Tuple[int, bytes]],
        file_metadata: List[Dict[str, Any]],
        output_dir: str
    ) -> List[Tuple[int, bytes, Dict[str, Any], str]]:
        """
        Creates a list of redaction items from the valid files.
        Each item is a tuple containing:
          (file index, file content, file metadata mapping, output path for redacted file).
        """
        redaction_items = []
        for file_idx, content in valid_files:
            if file_idx < len(file_metadata) and "mapping" in file_metadata[file_idx]:
                mapping = file_metadata[file_idx]["mapping"]
                safe_name = file_metadata[file_idx]["safe_name"]
                output_path = f"{output_dir}/redacted_{safe_name}"
                redaction_items.append((file_idx, content, mapping, output_path))
        return redaction_items

    @staticmethod
    async def _process_redaction_items(
        redaction_items: List[Tuple[int, bytes, Dict[str, Any], str]],
        max_workers: int,
        remove_images: bool
    ) -> Dict[int, Dict[str, Any]]:
        """
        Processes the redaction items concurrently using ParallelProcessingCore.
        Returns a mapping from file index to the redaction result.

        Args:
            redaction_items: List of redaction items.
            max_workers: Maximum number of concurrent workers.
            remove_images: If True, images will be redacted in each file.
        """

        async def _process_redaction_item(item: Tuple[int, bytes, Dict[str, Any], str]) -> Tuple[int, Dict[str, Any]]:
            file_idx, content, mapping, output_path = item
            try:
                log_info(f"Processing redaction for file idx={file_idx}, output={output_path}")
                redactor = PDFRedactionService(content)
                # Pass the remove_images flag to the apply_redactions method.
                redacted_path = redactor.apply_redactions(mapping, output_path, remove_images)
                redactor.close()
                redaction_count = sum(len(page.get("sensitive", [])) for page in mapping.get("pages", []))
                log_info(f"Successfully processed redactions for file idx={file_idx}, count={redaction_count}")
                return file_idx, {
                    "status": "success",
                    "output_path": redacted_path,
                    "redactions_applied": redaction_count
                }
            except Exception as redact_item_error:
                err_id = SecurityAwareErrorHandler.log_processing_error(redact_item_error, "pdf_redaction", f"file_{file_idx}")
                log_error(f"Error applying redactions: {str(redact_item_error)} [error_id={err_id}]")
                return file_idx, {
                    "status": "error",
                    "error": str(redact_item_error)
                }

        results = await ParallelProcessingCore.process_in_parallel(
            items=redaction_items,
            processor=_process_redaction_item,
            max_workers=max_workers,
            operation_id=f"batch_redaction_{uuid.uuid4()}"
        )

        result_mapping: Dict[int, Dict[str, Any]] = {}
        for res in results:
            try:
                if isinstance(res, tuple) and len(res) == 2:
                    idx, res_data = res
                    if isinstance(res_data, tuple) and len(res_data) == 2:
                        _, actual_data = res_data
                        res_data = actual_data
                    result_mapping[idx] = res_data
                else:
                    log_warning(f"Unexpected result format: {res}")
            except Exception as exc:
                log_error(f"Error processing redaction result: {str(exc)}")
        return result_mapping

    @staticmethod
    def _compute_redaction_summary(
        file_metadata: List[Dict[str, Any]],
        result_mapping: Dict[int, Dict[str, Any]],
        start_time: float,
        batch_id: str
    ) -> Tuple[int, int, int, float, Dict[str, Any]]:
        """
        Computes summary statistics for the batch redaction.
        Returns a tuple (successful, failed, total_redactions, total_time, batch_summary dict).
        """
        successful = 0
        failed = 0
        total_redactions = 0
        for i, meta in enumerate(file_metadata):
            if i in result_mapping:
                res = result_mapping[i]
                if res.get("status") == "success":
                    successful += 1
                    redactions = res.get("redactions_applied", 0)
                    if isinstance(redactions, (int, float)):
                        total_redactions += redactions
                else:
                    failed += 1
            else:
                failed += 1

        total_time = time.time() - start_time
        batch_summary = {
            "batch_id": batch_id,
            "total_files": len(file_metadata),
            "successful": successful,
            "failed": failed,
            "total_redactions": total_redactions,
            "total_time": total_time,
            "timestamp": time.time(),
            "file_results": []
        }
        return successful, failed, total_redactions, total_time, batch_summary

    @staticmethod
    def _build_file_results(
        file_metadata: List[Dict[str, Any]],
        result_mapping: Dict[int, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Builds the file results list from file metadata and redaction result mapping.
        """
        file_results = []
        for i, meta in enumerate(file_metadata):
            res_entry = {
                "file": meta.get("original_name", f"file_{i}"),
                "status": "error",
                "redactions_applied": 0,
                "error": "Processing not attempted"
            }
            if i in result_mapping:
                res = result_mapping[i]
                if res.get("status") == "success":
                    res_entry = {
                        "file": meta.get("original_name", f"file_{i}"),
                        "status": "success",
                        "redactions_applied": res.get("redactions_applied", 0)
                    }
                    out_path = res.get("output_path")
                    if out_path and os.path.exists(out_path):
                        safe_name = sanitize_filename(meta.get("original_name", f"file_{i}.pdf"))
                        res_entry["arcname"] = f"redacted_{safe_name}"
                else:
                    res_entry = {
                        "file": meta.get("original_name", f"file_{i}"),
                        "status": "error",
                        "redactions_applied": 0,
                        "error": res.get("error", "Unknown error")
                    }
            file_results.append(res_entry)
        return file_results

    @staticmethod
    def _create_zip_archive(
        batch_summary: Dict[str, Any],
        file_metadata: List[Dict[str, Any]],
        result_mapping: Dict[int, Dict[str, Any]],
        zip_path: str
    ) -> None:
        """
        Creates a ZIP archive from the redacted output files based on file metadata and redaction results.
        Updates the batch_summary's file_results with arcname references if needed.
        """
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for res_entry in batch_summary["file_results"]:
                if res_entry.get("status") == "success" and "arcname" in res_entry:
                    matched_idx = next((idx for idx, meta in enumerate(file_metadata)
                                        if meta.get("original_name") == res_entry.get("file")), None)
                    if matched_idx is not None:
                        out_path = result_mapping.get(matched_idx, {}).get("output_path")
                        if out_path and os.path.exists(out_path):
                            zipf.write(out_path, arcname=res_entry["arcname"])
            zipf.writestr("batch_summary.json", json.dumps(batch_summary, indent=2))

    @staticmethod
    async def _stream_zip(zip_path: str):
        """
        Asynchronous generator to stream the ZIP file in chunks.
        """
        try:
            with open(zip_path, "rb") as f:
                while chunk := f.read(CHUNK_SIZE):
                    yield chunk
                    await asyncio.sleep(0)
        except Exception as exc:
            log_error(f"Error streaming ZIP file: {str(exc)}")
            yield b""