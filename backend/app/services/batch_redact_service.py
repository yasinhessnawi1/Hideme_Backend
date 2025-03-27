import asyncio
import json
import os
import time
import uuid
import zipfile
from typing import List, Optional, Union

from fastapi import UploadFile, BackgroundTasks
from starlette.responses import JSONResponse, StreamingResponse

from backend.app.document_processing.pdf import PDFRedactionService
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

class BatchRedactService:
    """
    Service for batch redaction.
    This service processes multiple PDF files for redaction in batch mode using the PDFRedactionService.
    """

    @staticmethod
    async def batch_redact_documents(
            files: List[UploadFile],
            redaction_mappings: str,
            max_parallel_files: Optional[int] = None,
            background_tasks: Optional[BackgroundTasks] = None
    ) -> Union[JSONResponse, StreamingResponse]:
        start_time = time.time()
        batch_id = str(uuid.uuid4())
        log_info(f"Starting batch redaction (Batch ID: {batch_id})")
        if background_tasks is None:
            background_tasks = BackgroundTasks()

        try:
            mapping_data = json.loads(redaction_mappings)
            file_mappings = {}
            if "redaction_mapping" in mapping_data and "file_info" in mapping_data and "filename" in mapping_data["file_info"]:
                filename = mapping_data["file_info"]["filename"]
                file_mappings[filename] = mapping_data["redaction_mapping"]
            elif "file_results" in mapping_data:
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

        output_dir = await SecureTempFileManager.create_secure_temp_dir_async(f"batch_redact_{batch_id}_")
        background_tasks.add_task(SecureTempFileManager.secure_delete_directory, output_dir)

        file_metadata = []
        valid_files = []
        for i, file in enumerate(files):
            try:
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

        redaction_items = []
        for idx, content in valid_files:
            if idx < len(file_metadata) and "mapping" in file_metadata[idx]:
                mapping = file_metadata[idx]["mapping"]
                safe_name = file_metadata[idx]["safe_name"]
                output_path = f"{output_dir}/redacted_{safe_name}"
                redaction_items.append((idx, content, mapping, output_path))

        async def process_redaction_wrapper(item):
            try:
                idx = item[0]
                content = item[1]
                mapping = item[2]
                output_path = item[3]
                log_info(f"Processing redaction for file idx={idx}, output={output_path}")
                redactor = PDFRedactionService(content)
                redacted_path = redactor.apply_redactions(mapping, output_path)
                redactor.close()
                redaction_count = sum(
                    len(page.get("sensitive", []))
                    for page in mapping.get("pages", [])
                )
                log_info(f"Successfully processed redactions for file idx={idx}, count={redaction_count}")
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

        redaction_results = await ParallelProcessingCore.process_in_parallel(
            items=redaction_items,
            processor=process_redaction_wrapper,
            max_workers=max_parallel_files or 4,
            operation_id=f"batch_redaction_{batch_id}"
        )
        log_info(f"Redaction results: {redaction_results}")

        zip_path = await SecureTempFileManager.create_secure_temp_file_async(
            suffix=".zip",
            prefix=f"redaction_batch_{batch_id}_"
        )

        successful = 0
        failed = 0
        total_redactions = 0
        result_mapping = {}
        for result in redaction_results:
            try:
                if isinstance(result, tuple) and len(result) == 2:
                    idx, result_data = result
                    if isinstance(result_data, tuple) and len(result_data) == 2:
                        _, actual_result_data = result_data
                        result_data = actual_result_data
                    if isinstance(result_data, dict) and result_data.get("status") == "success":
                        result_mapping[idx] = result_data
                        successful += 1
                        redactions = result_data.get("redactions_applied", 0)
                        if isinstance(redactions, (int, float)):
                            total_redactions += redactions
                    else:
                        result_mapping[idx] = {
                            "status": "error",
                            "error": result_data.get("error", "Unknown error") if isinstance(result_data, dict) else "Invalid result format"
                        }
                        failed += 1
                else:
                    log_warning(f"Unexpected result format: {result}")
                    failed += 1
            except Exception as e:
                log_error(f"Error processing redaction result: {str(e)}")
                failed += 1

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

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for idx, metadata in enumerate(file_metadata):
                file_result = {
                    "file": metadata.get("original_name", f"file_{idx}"),
                    "status": "error",
                    "redactions_applied": 0,
                    "error": "Processing not attempted"
                }
                if idx in result_mapping:
                    result = result_mapping[idx]
                    if result.get("status") == "success":
                        file_result = {
                            "file": metadata.get("original_name", f"file_{idx}"),
                            "status": "success",
                            "redactions_applied": result.get("redactions_applied", 0)
                        }
                        output_path = result.get("output_path")
                        if output_path and os.path.exists(output_path):
                            orig_name = metadata.get("original_name", f"file_{idx}.pdf")
                            safe_name = sanitize_filename(orig_name)
                            zipf.write(output_path, arcname=f"redacted_{safe_name}")
                    else:
                        file_result = {
                            "file": metadata.get("original_name", f"file_{idx}"),
                            "status": "error",
                            "redactions_applied": 0,
                            "error": result.get("error", "Unknown error")
                        }
                batch_summary["file_results"].append(file_result)
            zipf.writestr("batch_summary.json", json.dumps(batch_summary, indent=2))

        record_keeper.record_processing(
            operation_type="batch_redaction",
            document_type="multiple",
            entity_types_processed=[],
            processing_time=batch_summary["total_time"],
            file_count=len(file_metadata),
            entity_count=total_redactions,
            success=(successful > 0)
        )
        log_batch_operation(
            "Batch Redaction",
            len(file_metadata),
            successful,
            batch_summary["total_time"]
        )

        async def stream_zip():
            try:
                with open(zip_path, "rb") as f:
                    while chunk := f.read(CHUNK_SIZE):
                        yield chunk
                        await asyncio.sleep(0)
            except Exception as e:
                log_error(f"Error streaming ZIP file: {str(e)}")

        mem_stats = memory_monitor.get_memory_stats()
        background_tasks.add_task(SecureTempFileManager.secure_delete_file, zip_path)
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
