"""
This module provides the BatchRedactService class for processing multiple PDF files for redaction in a batch mode.
The service uses the PDFRedactionService for applying redactions, performs file validation, prepares redaction items,
processes them concurrently, computes summary statistics, builds a ZIP archive of redacted files, and returns a streaming response.
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
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.logging.secure_logging import log_batch_operation
from backend.app.utils.system_utils.memory_management import memory_monitor
from backend.app.utils.parallel.core import ParallelProcessingCore
from backend.app.utils.system_utils.secure_file_utils import SecureTempFileManager
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.validation.file_validation import read_and_validate_file, sanitize_filename, MAX_FILES_COUNT

CHUNK_SIZE = 64 * 1024  # 64KB for streaming responses
DEFAULT_CONTENT_TYPE = "application/octet-stream"


class BatchRedactService:
    """
    Service for batch redaction.
    This class processes multiple PDF files in a batch operation, performing validation, redaction, and packaging
    of the output into a ZIP archive. The process includes parsing redaction mappings, reading and validating files,
    applying redactions concurrently using helper classes, and building a detailed response.
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
        It parses redaction mappings, reads and validates files, processes redactions in parallel, computes summary statistics,
        builds a ZIP archive of redacted files, and returns a streaming response.

        Args:
            files (List[UploadFile]): List of uploaded PDF files.
            redaction_mappings (str): JSON string containing redaction mappings.
            remove_images (bool): If True, images will be detected and redacted.
            max_parallel_files (Optional[int]): Maximum number of files to process concurrently.
            background_tasks (Optional[BackgroundTasks]): Instance for scheduling background cleanup tasks.

        Returns:
            Union[JSONResponse, StreamingResponse]: The streaming ZIP archive or an error JSON response.
        """
        # Record start time of the operation.
        start_time = time.time()
        # Generate a unique batch identifier.
        batch_id = str(uuid.uuid4())
        # Log the start of the batch redaction process.
        log_info(f"Starting batch redaction (Batch ID: {batch_id})")

        # Set up background tasks if none were provided.
        if background_tasks is None:
            background_tasks = BackgroundTasks()

        # Verify if the uploaded file count exceeds the maximum allowed.
        if len(files) > MAX_FILES_COUNT:
            # Return a JSON response indicating too many files.
            return JSONResponse(
                status_code=400,
                content={"detail": f"Too many files uploaded. Maximum allowed is {MAX_FILES_COUNT}."}
            )

        # Parse the provided redaction mappings from JSON string to dictionary.
        file_mappings = BatchRedactService._parse_redaction_mappings(redaction_mappings)
        # Check if valid mappings were parsed, else return an error.
        if not file_mappings:
            return JSONResponse(
                status_code=400,
                content={"detail": "No valid redaction mappings found in the provided JSON"}
            )

        # Create a secure temporary output directory for redacted files.
        output_dir = await SecureTempFileManager.create_secure_temp_dir_async(f"batch_redact_{batch_id}_")
        # Schedule the deletion of the temporary directory once processing is complete.
        background_tasks.add_task(SecureTempFileManager.secure_delete_directory, output_dir)

        # Read and validate files based on the redaction mappings.
        file_metadata, valid_files = await BatchRedactService._prepare_files_for_redaction(files, file_mappings,
                                                                                           batch_id)
        # If no valid files were found, return a detailed error response.
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

        # Prepare redaction items from the valid files and file metadata.
        redaction_items = BatchRedactService._prepare_redaction_items(valid_files, file_metadata, output_dir)

        # Process the redaction items concurrently with a specified max parallelism.
        result_mapping = await BatchRedactService._process_redaction_items(
            redaction_items, max_parallel_files or 4, remove_images
        )
        # Log the results of the redaction processing.
        log_info(f"Redaction results: {result_mapping}")

        # Compute summary statistics including success rate and total redactions.
        successful, _, _, _, batch_summary = BatchRedactService._compute_redaction_summary(
            file_metadata, result_mapping, start_time, batch_id
        )
        # Build detailed file-specific results.
        batch_summary["file_results"] = BatchRedactService._build_file_results(file_metadata, result_mapping)

        # Create a secure temporary file for the ZIP archive.
        zip_path_future = SecureTempFileManager.create_secure_temp_file_async(
            suffix=".zip", prefix=f"redaction_batch_{batch_id}_"
        )
        # Await the creation of the ZIP path.
        zip_path = await zip_path_future
        # Build the ZIP archive from redacted files and summary data.
        BatchRedactService._create_zip_archive(batch_summary, file_metadata, result_mapping, zip_path)

        # Record the processing results and log the batch operation.
        record_keeper.record_processing(
            operation_type="batch_redaction",
            document_type="multiple",
            entity_types_processed=[],
            processing_time=batch_summary["total_time"],
            file_count=len(file_metadata),
            entity_count=batch_summary["total_redactions"],
            success=(successful > 0)
        )
        # Log batch operation details for auditing purposes.
        log_batch_operation("Batch Redaction", len(file_metadata), successful, batch_summary["total_time"])

        # Build and return the final streaming response containing the ZIP archive.
        return BatchRedactService.build_streaming_response(zip_path, batch_summary, batch_id)

    @staticmethod
    def build_streaming_response(zip_path: str, batch_summary: Dict[str, Any], batch_id: str) -> StreamingResponse:
        """
        Builds and returns a StreamingResponse for the ZIP archive.

        Args:
            zip_path (str): Path to the ZIP archive.
            batch_summary (Dict[str, Any]): Summary information of batch processing.
            batch_id (str): Unique identifier of the batch.

        Returns:
            StreamingResponse: The streaming response wrapping the ZIP archive.
        """
        # Retrieve memory statistics for response headers.
        mem_stats = memory_monitor.get_memory_stats()

        # Return the StreamingResponse, configuring headers with batch and memory details.
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
        Returns a dictionary mapping filenames to their redaction instructions.

        Args:
            redaction_mappings (str): JSON string with redaction mappings.

        Returns:
            Dict[str, Any]: Mapping of filenames to redaction instructions.
        """
        try:
            # Load the JSON data from the string.
            mapping_data = json.loads(redaction_mappings)
            # Initialize an empty mapping dictionary.
            file_mappings = {}

            # Handle single file mapping format.
            if ("redaction_mapping" in mapping_data and
                    "file_info" in mapping_data and
                    "filename" in mapping_data["file_info"]):
                # Extract filename.
                filename = mapping_data["file_info"]["filename"]
                # Map the filename to its redaction mapping.
                file_mappings[filename] = mapping_data["redaction_mapping"]

            # Handle multiple file mapping format.
            elif "file_results" in mapping_data:
                # Iterate over each file result.
                for file_result in mapping_data["file_results"]:
                    # Process only successful file entries with available results.
                    if file_result.get("status") == "success" and "results" in file_result:
                        # Extract the filename.
                        filename = file_result["file"]
                        # Map the filename to its redaction mapping if available.
                        if "redaction_mapping" in file_result["results"]:
                            file_mappings[filename] = file_result["results"]["redaction_mapping"]

            # Return the mapping's dictionary.
            return file_mappings

        except json.JSONDecodeError:
            # Return an empty dictionary in case of JSON decoding error.
            return {}

    @staticmethod
    async def _prepare_files_for_redaction(
            files: List[UploadFile],
            file_mappings: Dict[str, Any],
            operation_id: str
    ) -> Tuple[List[Dict[str, Any]], List[Tuple[int, bytes]]]:
        """
        Reads and validates each file using the shared read_and_validate_file utility.
        Returns file metadata and valid file content as a tuple.

        Args:
            files (List[UploadFile]): List of uploaded file objects.
            file_mappings (Dict[str, Any]): Mapping of filenames to redaction mappings.
            operation_id (str): Unique identifier for the operation.

        Returns:
            Tuple[List[Dict[str, Any]], List[Tuple[int, bytes]]]: File metadata and valid file tuples.
        """
        # Initialize an empty list for file metadata.
        file_metadata = []
        # Initialize an empty list for valid files.
        valid_files = []
        # Iterate through the files with an index.
        for i, file in enumerate(files):
            # Check if a redaction mapping exists for the current file.
            if file.filename not in file_mappings:
                # Log a warning if mapping is missing.
                log_warning(f"No redaction mapping for file: {file.filename}")
                # Append metadata with an error status.
                file_metadata.append({
                    "original_name": file.filename,
                    "content_type": file.content_type or DEFAULT_CONTENT_TYPE,
                    "size": 0,
                    "status": "error",
                    "error": "No redaction mapping provided"
                })
                # Continue to the next file.
                continue

            try:
                # Validate the file and read its content.
                content, error_response, read_time = await read_and_validate_file(file, operation_id)
                # Check if the validation utility returned an error.
                if error_response:
                    # Log the error for the current file.
                    log_error(f"Validation failed for file {file.filename} [operation_id={operation_id}]")
                    # Append error metadata.
                    file_metadata.append({
                        "original_name": file.filename,
                        "content_type": file.content_type or DEFAULT_CONTENT_TYPE,
                        "size": 0,
                        "status": "error",
                        "error": error_response
                    })
                    # Skip further processing for this file.
                    continue

                # Determine the file index based on the list of valid files.
                file_idx = len(valid_files)
                # Add the valid file tuple (index and content) to the list.
                valid_files.append((file_idx, content))
                # Append the corresponding metadata for the valid file.
                file_metadata.append({
                    "original_name": file.filename,
                    "content_type": file.content_type or DEFAULT_CONTENT_TYPE,
                    "size": len(content),
                    "read_time": read_time,
                    "safe_name": sanitize_filename(file.filename or f"file_{file_idx}.pdf"),
                    "mapping": file_mappings[file.filename],
                    "status": "success"
                })
            except Exception as exc:
                # Log any exception that occurs during file preparation.
                error_id = SecurityAwareErrorHandler.log_processing_error(
                    exc, "batch_redaction_preparation", file.filename or "unnamed_file"
                )
                # Log the error with its unique error id.
                log_error(f"Error preparing file for redaction: {str(exc)} [error_id={error_id}]")
                # Append error metadata for the file.
                file_metadata.append({
                    "original_name": getattr(file, "filename", f"file_{i}"),
                    "content_type": getattr(file, "content_type", DEFAULT_CONTENT_TYPE),
                    "size": 0,
                    "status": "error",
                    "error": f"Error preparing file: {str(exc)}"
                })

        # Return metadata and the list of valid files.
        return file_metadata, valid_files

    @staticmethod
    def _prepare_redaction_items(
            valid_files: List[Tuple[int, bytes]],
            file_metadata: List[Dict[str, Any]],
            output_dir: str
    ) -> List[Tuple[int, bytes, Dict[str, Any], str]]:
        """
        Creates a list of redaction items from the valid files.
        Each item is a tuple with file index, file content, metadata mapping, and output path.

        Args:
            valid_files (List[Tuple[int, bytes]]): List of valid file tuples.
            file_metadata (List[Dict[str, Any]]): List containing metadata for each file.
            output_dir (str): Directory to store redacted files.

        Returns:
            List[Tuple[int, bytes, Dict[str, Any], str]]: List of redaction items.
        """
        # Initialize the list to hold redaction items.
        redaction_items = []
        # Iterate through each valid file.
        for file_idx, content in valid_files:
            # Check if metadata is available and contains a mapping.
            if file_idx < len(file_metadata) and "mapping" in file_metadata[file_idx]:
                # Retrieve the mapping from metadata.
                mapping = file_metadata[file_idx]["mapping"]
                # Retrieve the sanitized file name.
                safe_name = file_metadata[file_idx]["safe_name"]
                # Define the output path for the redacted file.
                output_path = f"{output_dir}/redacted_{safe_name}"
                # Append the redaction item tuple.
                redaction_items.append((file_idx, content, mapping, output_path))
        # Return the list of redaction items.
        return redaction_items

    @staticmethod
    async def _process_redaction_items(
            redaction_items: List[Tuple[int, bytes, Dict[str, Any], str]],
            max_workers: int,
            remove_images: bool
    ) -> Dict[int, Dict[str, Any]]:
        """
        Processes the redaction items concurrently using ParallelProcessingCore.
        Returns a dictionary mapping file index to redaction results.

        Args:
            redaction_items (List[Tuple[int, bytes, Dict[str, Any], str]]): List of redaction items.
            max_workers (int): Maximum number of parallel workers.
            remove_images (bool): Flag indicating whether to remove images during redaction.

        Returns:
            Dict[int, Dict[str, Any]]: Mapping from file index to redaction result.
        """

        # Define an asynchronous helper function to process a single redaction item.
        async def _process_redaction_item(item: Tuple[int, bytes, Dict[str, Any], str]) -> Tuple[int, Dict[str, Any]]:
            # Unpack the redaction item tuple.
            file_idx, content, mapping, output_path = item
            try:
                # Log the start of processing for the file.
                log_info(f"Processing redaction for file idx={file_idx}, output={output_path}")
                # Initialize the PDFRedactionService with file content.
                redactor = PDFRedactionService(content)
                # Apply redactions with the remove_images flag and capture output path.
                redacted_path = redactor.apply_redactions(mapping, output_path, remove_images)
                # Close the redactor resource.
                redactor.close()
                # Compute the redaction count based on mapping details.
                redaction_count = sum(len(page.get("sensitive", [])) for page in mapping.get("pages", []))
                # Log successful processing including the count of redactions applied.
                log_info(f"Successfully processed redactions for file idx={file_idx}, count={redaction_count}")
                # Return a tuple with file index and success result details.
                return file_idx, {
                    "status": "success",
                    "output_path": redacted_path,
                    "redactions_applied": redaction_count
                }
            except Exception as redact_item_error:
                # Log the exception using the security error handler.
                err_id = SecurityAwareErrorHandler.log_processing_error(
                    redact_item_error, "pdf_redaction", f"file_{file_idx}"
                )
                # Log the error details including error id.
                log_error(f"Error applying redactions: {str(redact_item_error)} [error_id={err_id}]")
                # Return a tuple with file index and error result details.
                return file_idx, {
                    "status": "error",
                    "error": str(redact_item_error)
                }

        # Process items in parallel using the ParallelProcessingCore utility.
        results = await ParallelProcessingCore.process_in_parallel(
            items=redaction_items,
            processor=_process_redaction_item,
            max_workers=max_workers,
            operation_id=f"batch_redaction_{uuid.uuid4()}"
        )

        # Initialize an empty dictionary to hold results.
        result_mapping: Dict[int, Dict[str, Any]] = {}
        # Iterate over the results from parallel processing.
        for res in results:
            try:
                # Check if the result is a tuple with exactly two elements.
                if isinstance(res, tuple) and len(res) == 2:
                    idx, res_data = res
                    # Handle nested tuple structure if present.
                    if isinstance(res_data, tuple) and len(res_data) == 2:
                        _, actual_data = res_data
                        res_data = actual_data
                    # Map the file index to its result data.
                    result_mapping[idx] = res_data
                else:
                    # Log a warning for any unexpected result format.
                    log_warning(f"Unexpected result format: {res}")
            except Exception as exc:
                # Log an error if there is an issue processing an individual result.
                log_error(f"Error processing redaction result: {str(exc)}")
        # Return the final mapping of results.
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
        Returns a tuple containing the counts of successful and failed files, total redactions, elapsed time,
        and a detailed batch summary dictionary.

        Args:
            file_metadata (List[Dict[str, Any]]): Metadata for each file.
            result_mapping (Dict[int, Dict[str, Any]]): Mapping from file index to redaction results.
            start_time (float): Timestamp marking the beginning of processing.
            batch_id (str): Unique identifier for the batch.

        Returns:
            Tuple[int, int, int, float, Dict[str, Any]]: A tuple with:
                - Count of successful redactions.
                - Count of failed redactions.
                - Total number of redactions applied.
                - Total processing time.
                - Batch summary details as a dictionary.
        """
        # Initialize counters for successful files, failed files, and total redactions.
        successful = 0
        failed = 0
        total_redactions = 0
        # Loop through each file metadata using its index.
        for i, meta in enumerate(file_metadata):
            # Check if the result for the current index is available in the mapping.
            if i in result_mapping:
                # Retrieve the result for the file.
                res = result_mapping[i]
                # If the file was processed successfully...
                if res.get("status") == "success":
                    successful += 1
                    # Retrieve and add the number of redactions applied for the file.
                    redactions = res.get("redactions_applied", 0)
                    if isinstance(redactions, (int, float)):
                        total_redactions += redactions
                else:
                    # Otherwise count the file as a failure.
                    failed += 1
            else:
                # Increment failure counter if there is no result.
                failed += 1

        # Calculate the total processing time.
        total_time = time.time() - start_time
        # Build the batch summary dictionary.
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
        # Return the computed summary values.
        return successful, failed, total_redactions, total_time, batch_summary

    @staticmethod
    def _build_file_results(
            file_metadata: List[Dict[str, Any]],
            result_mapping: Dict[int, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Builds the file results list using file metadata and redaction results.

        Args:
            file_metadata (List[Dict[str, Any]]): Metadata for each processed file.
            result_mapping (Dict[int, Dict[str, Any]]): Mapping of file index to its redaction result.

        Returns:
            List[Dict[str, Any]]: A list of results for each file.
        """
        # Initialize an empty list to collect file result entries.
        file_results = []
        # Iterate over file metadata with an index.
        for i, meta in enumerate(file_metadata):
            # Create a default result entry for the file.
            res_entry = {
                "file": meta.get("original_name", f"file_{i}"),
                "status": "error",
                "redactions_applied": 0,
                "error": "Processing not attempted"
            }
            # Check if the file index exists in the result mapping.
            if i in result_mapping:
                # Retrieve the result.
                res = result_mapping[i]
                # If the result indicates success...
                if res.get("status") == "success":
                    res_entry = {
                        "file": meta.get("original_name", f"file_{i}"),
                        "status": "success",
                        "redactions_applied": res.get("redactions_applied", 0)
                    }
                    # Check if the output path exists and update the result entry with a safe archive name.
                    out_path = res.get("output_path")
                    if out_path and os.path.exists(out_path):
                        safe_name = sanitize_filename(meta.get("original_name", f"file_{i}.pdf"))
                        res_entry["arcname"] = f"{safe_name}"
                else:
                    # Otherwise update the entry with the error message from the redaction process.
                    res_entry = {
                        "file": meta.get("original_name", f"file_{i}"),
                        "status": "error",
                        "redactions_applied": 0,
                        "error": res.get("error", "Unknown error")
                    }
            # Append the result entry to the list.
            file_results.append(res_entry)
        # Return the complete list of file results.
        return file_results

    @staticmethod
    def _create_zip_archive(
            batch_summary: Dict[str, Any],
            file_metadata: List[Dict[str, Any]],
            result_mapping: Dict[int, Dict[str, Any]],
            zip_path: str
    ) -> None:
        """
        Creates a ZIP archive including redacted output files and a summary JSON.

        Args:
            batch_summary (Dict[str, Any]): Summary information about the batch process.
            file_metadata (List[Dict[str, Any]]): Metadata for all processed files.
            result_mapping (Dict[int, Dict[str, Any]]): Mapping of file index to redaction result.
            zip_path (str): The file path where the ZIP archive is to be saved.
        """
        # Open a new ZIP file for writing using the provided path.
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Iterate over each file result in the batch summary.
            for res_entry in batch_summary["file_results"]:
                # Process only those results that were successful and have an archive name.
                if res_entry.get("status") == "success" and "arcname" in res_entry:
                    # Find the index of the file in metadata that matches the result.
                    matched_idx = next((idx for idx, meta in enumerate(file_metadata)
                                        if meta.get("original_name") == res_entry.get("file")), None)
                    # If a matching file index is found...
                    if matched_idx is not None:
                        # Retrieve the output path from the result mapping.
                        out_path = result_mapping.get(matched_idx, {}).get("output_path")
                        # Write the file into the ZIP archive if it exists.
                        if out_path and os.path.exists(out_path):
                            zipf.write(out_path, arcname=res_entry["arcname"])
            # Write the batch summary as a JSON file into the ZIP archive.
            zipf.writestr("batch_summary.json", json.dumps(batch_summary, indent=2))

    @staticmethod
    async def _stream_zip(zip_path: str):
        """
        Asynchronous generator to stream the ZIP file in chunks.

        Args:
            zip_path (str): Path to the ZIP archive.

        Yields:
            bytes: Chunks of data from the ZIP file.
        """
        try:
            # Open the ZIP file in binary read mode.
            with open(zip_path, "rb") as f:
                # Continue reading while there is data.
                while chunk := f.read(CHUNK_SIZE):
                    # Yield the current chunk.
                    yield chunk
                    # Allow other tasks to run.
                    await asyncio.sleep(0)
        except Exception as exc:
            # Log any exception encountered during streaming.
            log_error(f"Error streaming ZIP file: {str(exc)}")
            # Yield an empty byte string if an error occurs.
            yield b""
