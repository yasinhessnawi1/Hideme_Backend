import time
from typing import Optional, Tuple, Any

from fastapi import UploadFile
from fastapi.responses import JSONResponse

from backend.app.document_processing.pdf_extractor import PDFTextExtractor
from backend.app.utils.logging.logger import log_info, log_error
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.system_utils.memory_management import memory_monitor
from backend.app.utils.validation.data_minimization import minimize_extracted_data
from backend.app.utils.validation.file_validation import read_and_validate_file


class DocumentExtractService:
    """
    Service that encapsulates all steps for extracting text with positions from a PDF file.
    Includes performance metrics, memory optimization, and enhanced error handling.
    """

    async def extract(self, file: UploadFile) -> JSONResponse:
        start_time = time.time()
        operation_id = f"pdf_extract_{time.time()}"
        log_info(f"[SECURITY] Starting PDF extraction [operation_id={operation_id}]")

        content, error, file_read_time = await read_and_validate_file(file, operation_id)
        if error:
            return error

        # Step 5: Extract text.
        extracted_data, extraction_error = self._extract_text(content, file.filename, operation_id)
        if extraction_error:
            return extraction_error
        extract_time = time.time() - start_time - file_read_time

        # Step 6: Apply data minimization.
        extracted_data = minimize_extracted_data(extracted_data)

        # Step 6.5: Remove the actual text from the extracted data.
        extracted_data = self._remove_text_from_extracted_data(extracted_data)

        # Step 7: Add performance statistics.
        total_time = time.time() - start_time
        pages_count = len(extracted_data.get("pages", []))
        words_count = sum(len(page.get("words", [])) for page in extracted_data.get("pages", []))
        extracted_data["performance"] = {
            "file_read_time": file_read_time,
            "extraction_time": extract_time,
            "total_time": total_time,
            "pages_count": pages_count,
            "words_count": words_count,
            "operation_id": operation_id
        }
        extracted_data["file_info"] = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": f"{round(len(content) / (1024 * 1024), 2)} MB"
        }

        # Step 8: Record processing for compliance.
        record_keeper.record_processing(
            operation_type="pdf_extraction",
            document_type="PDF",
            entity_types_processed=[],
            processing_time=total_time,
            entity_count=0,
            success=True
        )

        # Step 9: Log the sensitive operation.
        log_sensitive_operation(
            "PDF Extraction",
            0,
            total_time,
            pages=pages_count,
            words=words_count,
            extraction_time=extract_time
        )

        # Step 10: Add memory statistics.
        mem_stats = memory_monitor.get_memory_stats()
        extracted_data["_debug"] = {
            "memory_usage": mem_stats["current_usage"],
            "peak_memory": mem_stats["peak_usage"]
        }

        log_info(f"[SECURITY] PDF extraction completed successfully [operation_id={operation_id}]")
        return JSONResponse(content=extracted_data)

    @staticmethod
    def _extract_text(content: bytes, filename: str, operation_id: str) -> Tuple[Optional[Any], Optional[JSONResponse]]:
        log_info(f"[SECURITY] Starting PDF text extraction [operation_id={operation_id}]")
        try:
            extractor = PDFTextExtractor(content)
            extracted_data = extractor.extract_text()
            extractor.close()
            log_info(f"[SECURITY] PDF text extraction completed [operation_id={operation_id}]")
            return extracted_data, None
        except Exception as e:
            log_error(f"[SECURITY] Error extracting text: {str(e)} [operation_id={operation_id}]")
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(e, "pdf_text_extraction",
                                                                                              500, filename)
            return None, JSONResponse(status_code=status_code, content=error_response)

    @staticmethod
    def _remove_text_from_extracted_data(extracted_data: dict) -> dict:
        """
        Remove the actual text from each word in the extracted pages.
        """
        for page in extracted_data.get("pages", []):
            for word in page.get("words", []):
                word.pop("text", None)
        return extracted_data