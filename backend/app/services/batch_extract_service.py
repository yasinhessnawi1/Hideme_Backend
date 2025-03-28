"""
BatchExtractService.py

Service for batch text extraction.
This service extracts text from multiple PDF files in parallel using PDFTextExtractor.extract_batch_text.
The process is divided into helper functions:
  • _read_files_for_extraction: Reads and validates the content of UploadFile objects.
  • _process_extraction_results: Processes the extraction results, computes performance metrics, and builds file results.
The main function then creates a batch summary and returns a detailed response.
"""

import time
import uuid
from typing import List, Dict, Any, Optional, Tuple

from fastapi import UploadFile

from backend.app.document_processing.pdf_extractor import PDFTextExtractor
from backend.app.utils.logging.logger import log_info, log_error
from backend.app.utils.logging.secure_logging import log_batch_operation
from backend.app.utils.memory_management import memory_monitor
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.validation.data_minimization import minimize_extracted_data


class BatchExtractService:
    """
    Service for batch text extraction.
    This service uses PDFTextExtractor.extract_batch_text to extract text from multiple PDF files in parallel.
    """

    @staticmethod
    async def batch_extract_text(
            files: List[UploadFile],
            max_parallel_files: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Main method to perform batch text extraction.
        It reads files, extracts text in batch, processes results, and returns a detailed summary.
        """
        start_time = time.time()
        batch_id = str(uuid.uuid4())
        log_info(f"Starting batch text extraction (Batch ID: {batch_id})")
        optimal_workers = max_parallel_files if max_parallel_files is not None else 4

        # Read file contents and build metadata.
        pdf_files, pdf_indices, file_metadata = await BatchExtractService._read_files_for_extraction(files)
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

        # Perform batch extraction using the PDF module.
        extraction_results = await PDFTextExtractor.extract_batch_text(pdf_files, max_workers=optimal_workers)
        # Build a mapping from index to extraction result.
        extraction_map = {idx: result for idx, result in extraction_results}

        # Process extraction results and compute performance metrics.
        file_results, successful, failed, total_pages, total_words = BatchExtractService._process_extraction_results(
            file_metadata, pdf_indices, extraction_map
        )

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
        mem_stats = memory_monitor.get_memory_stats()
        response = {
            "batch_summary": batch_summary,
            "file_results": file_results,
            "_debug": {
                "memory_usage": mem_stats["current_usage"],
                "peak_memory": mem_stats["peak_usage"],
                "operation_id": batch_id
            }
        }
        return response

    @staticmethod
    async def _read_files_for_extraction(files: List[UploadFile]) -> Tuple[List[bytes], List[int], List[Dict[str, Any]]]:
        """
        Reads each file and builds metadata for extraction.
        Returns a tuple:
          - List of PDF file contents (only valid PDFs).
          - List of original indices for valid PDF files.
          - List of metadata dictionaries for all files.
        For non-PDF files or errors, metadata will include an error message.
        """
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
        return pdf_files, pdf_indices, file_metadata

    @staticmethod
    def _process_extraction_results(
            file_metadata: List[Dict[str, Any]],
            pdf_indices: List[int],
            extraction_map: Dict[int, Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], int, int, int, int]:
        """
        Processes the extraction results and computes performance metrics.
        Returns a tuple containing:
          - A list of file result dictionaries.
          - Count of successful extractions.
          - Count of failed extractions.
          - Total number of pages extracted.
          - Total number of words extracted.
        """
        file_results = []
        successful = 0
        failed = 0
        total_pages = 0
        total_words = 0

        for i, metadata in enumerate(file_metadata):
            # If the file metadata indicates an error, add an error result.
            if metadata.get("status") == "error":
                file_results.append({
                    "file": metadata["original_name"],
                    "status": "error",
                    "error": metadata["error"]
                })
                failed += 1
                continue
            # Map file index from original list to extraction result.
            pdf_index = pdf_indices[i] if i < len(pdf_indices) else None
            if pdf_index is not None and pdf_index in extraction_map:
                result = extraction_map[pdf_index]
                if isinstance(result, dict) and "error" in result:
                    file_results.append({
                        "file": metadata["original_name"],
                        "status": "error",
                        "error": result["error"]
                    })
                    failed += 1
                else:
                    # Apply data minimization and compute performance metrics.
                    minimized_data = minimize_extracted_data(result)
                    pages_count = len(minimized_data.get("pages", []))
                    words_count = sum(len(page.get("words", [])) for page in minimized_data.get("pages", []))
                    total_pages += pages_count
                    total_words += words_count
                    extraction_time = result.get("extraction_time", 0)
                    minimized_data["performance"] = {
                        "extraction_time": extraction_time,
                        "pages_count": pages_count,
                        "words_count": words_count
                    }
                    minimized_data["file_info"] = {
                        "filename": metadata["original_name"],
                        "content_type": metadata["content_type"],
                        "size": f"{round(metadata['size'] / (1024 * 1024), 2)} MB"
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

        return file_results, successful, failed, total_pages, total_words