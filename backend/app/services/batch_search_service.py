import time
import uuid
from typing import List, Dict, Any, Optional, Tuple, Union

from fastapi import UploadFile

from backend.app.document_processing.pdf_extractor import PDFTextExtractor
from backend.app.document_processing.pdf_searcher import PDFSearcher
from backend.app.utils.logging.logger import log_info, log_error
from backend.app.utils.logging.secure_logging import log_batch_operation
from backend.app.utils.memory_management import memory_monitor
from backend.app.utils.security.processing_records import record_keeper  # Import record_keeper


class BatchSearchService:
    """
    Service for batch text search.
    This service extracts text from multiple PDF files in parallel using PDFTextExtractor.extract_batch_text,
    then searches for provided search terms within the extracted data and returns the matching results.
    """

    @staticmethod
    async def batch_search_text(
            files: List[UploadFile],
            search_terms: Union[str, List[str]],
            max_parallel_files: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Extracts text from provided PDF files and searches for the given terms.
        Returns a dictionary summarizing the batch and results per file.

        Args:
            files: List of UploadFile objects.
            search_terms: A string or list of strings with the search terms.
            max_parallel_files: Maximum number of files to process in parallel.

        Returns:
            A dictionary with batch_summary, file_results, and debug information.
        """
        start_time = time.time()
        batch_id = f"search-{str(uuid.uuid4())}"
        log_info(f"Starting batch text search (Batch ID: {batch_id})")
        optimal_workers = max_parallel_files if max_parallel_files is not None else 4

        # Parse the search terms into a list of individual words/phrases.
        search_words = BatchSearchService._parse_search_words(search_terms)

        # Read file contents and build metadata.
        pdf_files, pdf_indices, file_metadata = await BatchSearchService._read_files_for_extraction(files)
        if not pdf_files:
            return {
                "batch_summary": {
                    "batch_id": batch_id,
                    "total_files": len(files),
                    "successful": 0,
                    "failed": len(files),
                    "total_matches": 0,
                    "search_term": ", ".join(search_words),
                    "query_time": time.time() - start_time
                },
                "file_results": []
            }

        # Extract text from PDFs.
        extraction_results = await PDFTextExtractor.extract_batch_text(pdf_files, max_workers=optimal_workers)
        extraction_map = {idx: result for idx, result in extraction_results}

        file_results: List[Dict[str, Any]] = []
        successful = 0
        failed = 0
        total_matches = 0

        # Process each file's extraction result.
        for i, metadata in enumerate(file_metadata):
            try:
                result_data, success_flag, fail_flag, match_count = BatchSearchService._process_single_file_result(
                    i, metadata, pdf_indices, extraction_map, search_words
                )
                file_results.append(result_data)
                successful += success_flag
                failed += fail_flag
                total_matches += match_count
            except Exception as e:
                log_error(f"Error processing file {metadata.get('original_name')}: {str(e)}")
                file_results.append({
                    "file": metadata.get("original_name", f"file_{i}"),
                    "status": "error",
                    "error": f"Unhandled processing error: {str(e)}"
                })
                failed += 1

        query_time = time.time() - start_time
        batch_summary = {
            "batch_id": batch_id,
            "total_files": len(files),
            "successful": successful,
            "failed": failed,
            "total_matches": total_matches,
            "search_term": ", ".join(search_words),
            "query_time": round(query_time, 2)
        }
        log_batch_operation("Batch Text Search", len(files), successful, query_time)

        # Register the batch search operation for processing records.
        record_keeper.record_processing(
            operation_type="batch_text_search",
            document_type="multiple_files",
            entity_types_processed=search_words,
            processing_time=query_time,
            file_count=len(files),
            entity_count=total_matches,
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
    async def _read_files_for_extraction(files: List[UploadFile]) -> Tuple[
        List[bytes], List[int], List[Dict[str, Any]]]:
        """
        Reads files and builds metadata.

        Args:
            files: List of UploadFile objects.

        Returns:
            A tuple of (pdf_files, pdf_indices, file_metadata).
        """
        pdf_files: List[bytes] = []
        pdf_indices: List[int] = []
        file_metadata: List[Dict[str, Any]] = []
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
    def _parse_search_words(search_words: Union[str, List[str]]) -> List[str]:
        """
        Parses the search_words parameter into a list of words/phrases.

        If a string is provided, any surrounding quotes are removed and the string is split on whitespace.
        If a list is provided, each element trimmed.
        """

        def clean(word: str) -> str:
            return word.strip()

        if isinstance(search_words, list):
            return [clean(word) for word in search_words if clean(word)]
        s = search_words.strip()
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            s = s[1:-1].strip()
        return [w.strip() for w in s.split() if w.strip()]

    @staticmethod
    def _process_single_file_result(
            index: int,
            metadata: Dict[str, Any],
            pdf_indices: List[int],
            extraction_map: Dict[int, Any],
            search_words: List[str]
    ) -> Tuple[Dict[str, Any], int, int, int]:
        """
        Processes a single file's extraction result.

        Args:
            index: The index of the file in the metadata list.
            metadata: Metadata dictionary for the file.
            pdf_indices: List of indices for files that were successfully read.
            extraction_map: Mapping from file index to extraction result.
            search_words: List of search words to look for.

        Returns:
            A tuple containing:
              - The result dictionary for the file.
              - Success flag (1 if successful, 0 otherwise).
              - Failure flag (1 if failed, 0 otherwise).
              - Total matches found in the file.
        """
        if metadata.get("status") == "error":
            return ({
                        "file": metadata["original_name"],
                        "status": "error",
                        "error": metadata["error"]
                    }, 0, 1, 0)
        pdf_index = pdf_indices[index] if index < len(pdf_indices) else None
        if pdf_index is None or pdf_index not in extraction_map:
            return ({
                        "file": metadata["original_name"],
                        "status": "error",
                        "error": "Search failed or file not processed"
                    }, 0, 1, 0)
        result = extraction_map[pdf_index]
        if isinstance(result, dict) and "error" in result:
            return ({
                        "file": metadata["original_name"],
                        "status": "error",
                        "error": result["error"]
                    }, 0, 1, 0)
        try:
            searcher = PDFSearcher(result)
            search_result = searcher.search_terms(search_words)
            return ({
                        "file": metadata["original_name"],
                        "status": "success",
                        "results": search_result
                    }, 1, 0, search_result.get("match_count", 0))
        except Exception as e:
            log_error(f"Error searching file {metadata.get('original_name')}: {str(e)}")
            return ({
                        "file": metadata["original_name"],
                        "status": "error",
                        "error": f"Error during search: {str(e)}"
                    }, 0, 1, 0)