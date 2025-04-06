import time
import uuid
from typing import List, Dict, Any, Optional, Tuple, Union

from fastapi import UploadFile

from backend.app.document_processing.pdf_extractor import PDFTextExtractor
from backend.app.document_processing.pdf_searcher import PDFSearcher
from backend.app.utils.logging.logger import log_info, log_error
from backend.app.utils.logging.secure_logging import log_batch_operation
from backend.app.utils.system_utils.memory_management import memory_monitor
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.validation.file_validation import read_and_validate_file, MAX_FILES_COUNT


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
            max_parallel_files: Optional[int] = None,
            case_sensitive: bool = False,
            ai_search: bool = False
    ) -> Dict[str, Any]:
        """
        Extracts text from provided PDF files and searches for the given terms.
        Returns a dictionary summarizing the batch and results per file.
        """
        start_time = time.time()
        batch_id = f"search-{str(uuid.uuid4())}"
        log_info(f"Starting batch text search (Batch ID: {batch_id})")

        if len(files) > MAX_FILES_COUNT:
            error_message = f"Too many files uploaded. Maximum allowed is {MAX_FILES_COUNT}."
            log_error(f"[SECURITY] {error_message} [operation_id={batch_id}]")
            return {"detail": error_message, "operation_id": batch_id}

        optimal_workers = max_parallel_files if max_parallel_files is not None else 4

        # Parse search terms.
        search_words = BatchSearchService._parse_search_words(search_terms)

        # Read and validate files.
        pdf_files, file_metadata = await BatchSearchService._read_files_for_extraction(files, batch_id)

        # Only extract text from valid PDF files.
        valid_pdf_files = [content for content in pdf_files if content is not None]
        if not valid_pdf_files:
            return {
                "batch_summary": {
                    "batch_id": batch_id,
                    "total_files": len(files),
                    "successful": 0,
                    "failed": len(files),
                    "total_matches": 0,
                    "search_term": ", ".join(search_words),
                    "query_time": round(time.time() - start_time, 2)
                },
                "file_results": [],
                "_debug": {
                    "memory_usage": memory_monitor.get_memory_stats().get("current_usage"),
                    "peak_memory": memory_monitor.get_memory_stats().get("peak_usage"),
                    "operation_id": batch_id
                }
            }

        extraction_results = await PDFTextExtractor.extract_batch_text(valid_pdf_files, max_workers=optimal_workers)
        # Build a mapping of valid file index to extraction result.
        extraction_map = {idx: result for idx, result in extraction_results}

        file_results: List[Dict[str, Any]] = []
        successful = 0
        failed = 0
        total_matches = 0
        valid_count = 0  # Counter to align valid files with extraction_map indices

        for i, metadata in enumerate(file_metadata):
            if metadata.get("status") == "error":
                file_results.append({
                    "file": metadata.get("original_name"),
                    "status": "error",
                    "error": metadata.get("error", "File validation failed.")
                })
                failed += 1
                continue

            extraction_result = extraction_map.get(valid_count)
            valid_count += 1

            try:
                result_data, success_flag, fail_flag, match_count = await BatchSearchService._process_single_file_result(
                    metadata, extraction_result, search_words, case_sensitive, ai_search
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

        # Register the batch search operation.
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
                "memory_usage": mem_stats.get("current_usage"),
                "peak_memory": mem_stats.get("peak_usage"),
                "operation_id": batch_id
            }
        }
        return response

    @staticmethod
    async def _read_files_for_extraction(files: List[UploadFile], operation_id: str) -> Tuple[
        List[Optional[bytes]], List[Dict[str, Any]]]:
        """
        Reads and validates files.
        Returns a tuple of (pdf_files, file_metadata).
        """
        pdf_files: List[Optional[bytes]] = []
        file_metadata: List[Dict[str, Any]] = []
        for i, file in enumerate(files):
            try:
                content, error_response, read_time = await read_and_validate_file(file, operation_id)
                if error_response:
                    log_error(f"Validation failed for file {file.filename} [operation_id={operation_id}]")
                    pdf_files.append(None)
                    file_metadata.append({
                        "original_name": file.filename or f"file_{i}",
                        "content_type": file.content_type or "application/octet-stream",
                        "size": 0,
                        "read_time": read_time,
                        "status": "error",
                        "error": error_response
                    })
                else:
                    pdf_files.append(content)
                    file_metadata.append({
                        "original_name": file.filename or f"file_{i}.pdf",
                        "content_type": file.content_type or "application/octet-stream",
                        "size": len(content),
                        "read_time": read_time,
                        "status": "success"
                    })
            except Exception as e:
                log_error(f"Exception reading file {file.filename}: {str(e)} [operation_id={operation_id}]")
                pdf_files.append(None)
                file_metadata.append({
                    "original_name": file.filename or f"file_{i}",
                    "content_type": "unknown",
                    "size": 0,
                    "read_time": 0,
                    "status": "error",
                    "error": str(e)
                })
        return pdf_files, file_metadata

    @staticmethod
    def _parse_search_words(search_words: Union[str, List[str]]) -> List[str]:
        """
        Parses the search_words parameter into a list of words/phrases.
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
    async def _process_single_file_result(
            metadata: Dict[str, Any],
            extraction_result: Any,
            search_words: List[str],
            case_sensitive: bool,
            ai_search: bool
    ) -> Tuple[Dict[str, Any], int, int, int]:
        """
        Processes a single file's extraction result for search.
        Returns a tuple containing:
          - The result dictionary,
          - A success flag (1 for success, 0 otherwise),
          - A failure flag (1 for failure, 0 otherwise),
          - The number of matches found.
        """
        if extraction_result is None or (isinstance(extraction_result, dict) and "error" in extraction_result):
            return ({
                        "file": metadata["original_name"],
                        "status": "error",
                        "error": extraction_result.get("error",
                                                       "Extraction failed") if extraction_result else "Extraction missing"
                    }, 0, 1, 0)
        try:
            searcher = PDFSearcher(extraction_result)
            search_result = await searcher.search_terms(search_words, case_sensitive=case_sensitive,
                                                        ai_search=ai_search)
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
