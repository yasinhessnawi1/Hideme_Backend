"""
BatchProcessingService.py

This module implements three optimized services for processing multiple PDF files in batch mode:
  • BatchDetectService: for entity detection.
  • BatchExtractService: for text extraction.
  • BatchRedactService: for redaction.
It leverages the PDF module's batch methods:
  • PDFTextExtractor.extract_batch_text for extracting text from PDFs.
  • PDFRedactionService.redact_batch for applying redactions.
This refactored design removes the need for a separate batch-processing layer.
"""

import time
import uuid
from typing import List, Dict, Any, Optional

from fastapi import UploadFile

from backend.app.document_processing.pdf import PDFTextExtractor
from backend.app.utils.logging.logger import log_info, log_error
from backend.app.utils.logging.secure_logging import log_batch_operation
from backend.app.utils.memory_management import memory_monitor
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.validation.data_minimization import minimize_extracted_data

class BatchExtractService:
    """
    Service for batch text extraction.
    This service extracts text from multiple PDF files in parallel using PDFTextExtractor.extract_batch_text.
    """

    @staticmethod
    async def batch_extract_text(
            files: List[UploadFile],
            max_parallel_files: Optional[int] = None
    ) -> Dict[str, Any]:
        start_time = time.time()
        batch_id = str(uuid.uuid4())
        log_info(f"Starting batch text extraction (Batch ID: {batch_id})")
        optimal_workers = max_parallel_files if max_parallel_files is not None else 4
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
                    file_metadata.append({
                        "original_name": file.filename or f"file_{i}.pdf",
                        "content_type": content_type,
                        "size": len(content)
                    })
                else:
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
        extraction_results = await PDFTextExtractor.extract_batch_text(
            pdf_files,
            max_workers=optimal_workers
        )
        file_results = []
        successful = 0
        failed = 0
        total_pages = 0
        total_words = 0
        result_mapping = {}
        for idx, result in extraction_results:
            result_mapping[idx] = result
        for i, metadata in enumerate(file_metadata):
            if "status" in metadata and metadata["status"] == "error":
                file_results.append({
                    "file": metadata["original_name"],
                    "status": "error",
                    "error": metadata["error"]
                })
                failed += 1
                continue
            pdf_index = pdf_indices[i] if i < len(pdf_indices) else None
            if pdf_index is not None and pdf_index in result_mapping:
                result = result_mapping[pdf_index]
                if isinstance(result, dict) and "error" in result:
                    file_results.append({
                        "file": metadata["original_name"],
                        "status": "error",
                        "error": result["error"]
                    })
                    failed += 1
                else:
                    minimized_data = minimize_extracted_data(result)
                    pages_count = len(minimized_data.get("pages", []))
                    words_count = sum(len(page.get("words", [])) for page in minimized_data.get("pages", []))
                    total_pages += pages_count
                    total_words += words_count
                    extraction_time = 0
                    if isinstance(result, dict) and "extraction_time" in result:
                        extraction_time = result["extraction_time"]
                    minimized_data["performance"] = {
                        "extraction_time": extraction_time,
                        "pages_count": pages_count,
                        "words_count": words_count
                    }
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
                file_results.append({
                    "file": metadata["original_name"],
                    "status": "error",
                    "error": "Extraction failed or file not processed"
                })
                failed += 1
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
        log_batch_operation("Batch Text Extraction", len(files), successful, total_time)
        record_keeper.record_processing(
            operation_type="batch_text_extraction",
            document_type="multiple_files",
            entity_types_processed=[],
            processing_time=total_time,
            file_count=len(files),
            entity_count=0,
            success=(successful > 0)
        )
        response = {
            "batch_summary": batch_summary,
            "file_results": file_results
        }
        mem_stats = memory_monitor.get_memory_stats()
        response["_debug"] = {
            "memory_usage": mem_stats["current_usage"],
            "peak_memory": mem_stats["peak_usage"],
            "operation_id": batch_id
        }
        return response