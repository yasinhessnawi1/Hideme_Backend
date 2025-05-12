"""
DocumentExtractService Module

This module provides the DocumentExtractService class which encapsulates all steps
for extracting text (with positions) from a PDF file. It validates the input file,
extracts the text using PDFTextExtractor, applies data minimization techniques,
records performance metrics and memory usage, and handles errors securely using
SecurityAwareErrorHandler.
"""

import time
from typing import Optional, Tuple, Any

from fastapi import UploadFile, HTTPException

# Import custom modules for PDF extraction, logging, error handling, memory monitoring, and data minimization.
from backend.app.document_processing.pdf_extractor import PDFTextExtractor
from backend.app.domain.models import (
    BatchDetectionResponse,
    BatchSummary,
    BatchDetectionDebugInfo,
    FileResult,
)
from backend.app.utils.logging.logger import log_info, log_error
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.system_utils.memory_management import memory_monitor
from backend.app.utils.validation.data_minimization import minimize_extracted_data
from backend.app.utils.validation.file_validation import read_and_validate_file


class DocumentExtractService:
    """
    DocumentExtractService Class

    This class provides a service for extracting text along with positional information
    from PDF documents. It reads and validates the uploaded file, extracts text using
    PDFTextExtractor, minimizes the extracted data to remove unnecessary details, and records
    performance and memory statistics. Errors during processing are handled securely using
    SecurityAwareErrorHandler.

    Methods:
        extract(file) -> JSONResponse:
            Extracts text from the provided PDF file and returns the extracted data along with performance metrics.
    """

    async def extract(self, file: UploadFile) -> BatchDetectionResponse:
        """
        Extract text with positional information from a PDF file.

        This method performs the following steps:
        1. Validates and reads the uploaded file.
        2. Extracts text from the file using PDFTextExtractor.
        3. Applies data minimization to the extracted data.
        4. Removes the actual text content from the extracted words for privacy.
        5. Records performance statistics and memory usage.
        6. Logs sensitive operations and records processing for compliance.
        7. Returns a BatchDetectionResponse containing the extracted data and performance metrics.

        Args:
            file: The PDF file to be processed for text extraction.

        Returns:
            BatchDetectionResponse: A response containing the extracted data along with performance and debug information,
            or an error response if any error occurs during processing.
        """
        # Record the start time for overall processing
        start_time = time.time()
        # Generate a unique operation ID using the current timestamp
        operation_id = f"pdf_extract_{time.time()}"
        log_info(f"[SECURITY] Starting PDF extraction [operation_id={operation_id}]")

        # Validate the file; measure file reading time along with validation
        content, error, _ = await read_and_validate_file(file, operation_id)
        file_read_time = time.time() - start_time
        if error:
            # Raise the error response immediately if file validation fails
            raise HTTPException(status_code=error.status_code, detail=error.body)

        # Extract text from the PDF using the helper method _extract_text
        extracted_data, extraction_error = self._extract_text(
            content, file.filename, operation_id
        )
        if extraction_error:
            # Raise the error response if text extraction fails
            raise extraction_error

        # Calculate extraction time excluding the file reading duration
        extract_time = time.time() - start_time - file_read_time

        # Apply data minimization to reduce the extracted data size
        extracted_data = minimize_extracted_data(extracted_data)

        # Remove the actual text from each word to further minimize sensitive data exposure
        extracted_data = self._remove_text_from_extracted_data(extracted_data)

        # Calculate total processing time
        total_time = time.time() - start_time
        # Count the total number of pages and words in the extracted data
        pages_count = len(extracted_data.get("pages", []))
        words_count = sum(
            len(page.get("words", [])) for page in extracted_data.get("pages", [])
        )

        # Append performance statistics to the extracted data
        extracted_data["performance"] = {
            "file_read_time": file_read_time,
            "extraction_time": extract_time,
            "total_time": total_time,
            "pages_count": pages_count,
            "words_count": words_count,
            "operation_id": operation_id,
        }
        # Append file information details to the extracted data
        extracted_data["file_info"] = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": f"{round(len(content) / (1024 * 1024), 2)} MB",
        }

        # Record processing details for compliance and auditing
        record_keeper.record_processing(
            operation_type="pdf_extraction",
            document_type="PDF",
            entity_types_processed=[],
            processing_time=total_time,
            entity_count=0,
            success=True,
        )

        # Log sensitive operation details with performance metrics
        log_sensitive_operation(
            "PDF Extraction",
            0,
            total_time,
            pages=pages_count,
            words=words_count,
            extraction_time=extract_time,
        )

        file_result = FileResult(
            file=file.filename, status="success", results=extracted_data
        )

        summary = BatchSummary(
            batch_id=operation_id,
            total_files=1,
            successful=1,
            failed=0,
            total_time=total_time,
        )

        # Retrieve current memory usage statistics after processing
        mem = memory_monitor.get_memory_stats()

        debug = BatchDetectionDebugInfo(
            memory_usage=mem.get("current_usage"),
            peak_memory=mem.get("peak_usage"),
            operation_id=operation_id,
        )

        log_info(
            f"[SECURITY] PDF extraction completed successfully [operation_id={operation_id}]"
        )
        return BatchDetectionResponse(
            batch_summary=summary, file_results=[file_result], debug=debug
        )

    @staticmethod
    def _extract_text(
        content: bytes, filename: str, operation_id: str
    ) -> Tuple[Optional[Any], Optional[HTTPException]]:
        """
        Extract text from the PDF file content using PDFTextExtractor.

        This method attempts to extract text from the provided file content.
        It initializes PDFTextExtractor, extracts text, and closes the extractor.
        If any error occurs during extraction, it handles the error securely using
        SecurityAwareErrorHandler.

        Args:
            content: The binary content of the PDF file.
            filename: The name of the PDF file.
            operation_id: Unique identifier for the current extraction operation.

        Returns:
            A tuple containing:
                - extracted_data: The extracted text data (or None if extraction fails).
                - error_response: A HTTPException containing an error message if extraction fails, otherwise None.
        """
        log_info(
            f"[SECURITY] Starting PDF text extraction [operation_id={operation_id}]"
        )
        try:
            # Initialize the PDFTextExtractor with the file content
            extractor = PDFTextExtractor(content)
            # Extract text data from the PDF
            extracted_data = extractor.extract_text()
            # Close the extractor to free up resources
            extractor.close()
            log_info(
                f"[SECURITY] PDF text extraction completed [operation_id={operation_id}]"
            )
            return extracted_data, None
        except Exception as e:
            # Log the error and create a secure error response if extraction fails
            log_error(
                f"[SECURITY] Error extracting text: {str(e)} [operation_id={operation_id}]"
            )
            error_response = SecurityAwareErrorHandler.handle_safe_error(
                e, "file_text_extraction", filename
            )
            return None, HTTPException(
                status_code=error_response.get("status_code", 500),
                detail=error_response,
            )

    @staticmethod
    def _remove_text_from_extracted_data(extracted_data: dict) -> dict:
        """
        Remove the actual text from each word in the extracted pages.

        This method iterates over the pages and words in the extracted data,
        and removes the "text" key from each word to minimize sensitive data exposure.

        Args:
            extracted_data: A dictionary containing extracted PDF data including pages and words.

        Returns:
            The modified extracted_data dictionary with the "text" key removed from each word.
        """
        # Loop through each page in the extracted data
        for page in extracted_data.get("pages", []):
            # Loop through each word in the current page
            for word in page.get("words", []):
                # Remove the "text" field if it exists
                word.pop("text", None)
        return extracted_data
