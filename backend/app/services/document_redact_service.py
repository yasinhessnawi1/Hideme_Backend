"""
DocumentRedactionService Module

This module provides the DocumentRedactionService class which encapsulates all steps
for applying redactions to a PDF file. It validates the input file, parses a JSON redaction mapping,
applies redactions using an in-memory PDF redaction service, streams the redacted PDF,
and records performance metrics and memory usage. SecurityAwareErrorHandler is used throughout
to ensure that errors are handled securely without leaking sensitive information.
"""

import json
import time
from typing import Optional, Tuple, Union

from fastapi import UploadFile, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

# Import custom modules for PDF redaction, logging, error handling, etc.
from backend.app.document_processing.pdf_redactor import PDFRedactionService
from backend.app.domain.models import (
    RedactFileResult,
    RedactBatchSummary,
    BatchRedactResponse,
)
from backend.app.utils.constant.constant import CHUNK_SIZE
from backend.app.utils.logging.logger import log_info, log_error
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.system_utils.memory_management import memory_monitor
from backend.app.utils.validation.file_validation import read_and_validate_file


class DocumentRedactionService:
    """
    DocumentRedactionService Class

    This class provides a service for redacting PDF documents by applying redactions
    based on a specified mapping. It reads and validates the uploaded file, processes
    the redaction mapping (which can include text and image redaction instructions),
    and utilizes the PDFRedactionService to apply redactions in memory.
    The service also monitors processing time, logs sensitive operations,
    and handles errors securely using the SecurityAwareErrorHandler.

    Methods:
        redact(file, redaction_mapping, remove_images) -> Union[StreamingResponse, JSONResponse]
            Applies redactions to the provided PDF file and returns the redacted file
            as a streaming response, or an error response if an error occurs.
    """

    async def redact(
        self,
        file: UploadFile,
        redaction_mapping: Optional[str],
        remove_images: bool = False,
    ) -> Union[StreamingResponse, JSONResponse]:
        """
        Redact the provided PDF file using the specified redaction mapping and optional image removal.

        This method validates the uploaded file, parses the redaction mapping, applies redactions
        via PDFRedactionService, and streams the redacted PDF as a response. It also logs performance metrics,
        memory usage, and records the processing details for compliance. Errors are handled securely
        using SecurityAwareErrorHandler.

        Args:
            file: The PDF file to be redacted.
            redaction_mapping: A JSON string containing redaction details.
                Expected format: {"pages": [{"page": page_num, "sensitive": [items]}], "remove_images": false}
            remove_images: If True, images will be detected and redacted regardless of the mapping's content.

        Returns:
            StreamingResponse: Contains the redacted PDF streamed in chunks if redaction is successful.
            JSONResponse: Contains an error message if any error occurs during processing.
        """
        # Record the start time for performance measurement.
        start_time = time.time()
        # Generate a unique operation ID based on the current time.
        operation_id = f"pdf_redact_{time.time()}"
        log_info(
            f"[SECURITY] Starting PDF redaction processing [operation_id={operation_id}]"
        )

        try:
            # Validate and read the uploaded file using a utility function.
            contents, error, _ = await read_and_validate_file(file, operation_id)
            if error:
                # If file validation fails, return the error response immediately.
                return self._build_error_response(
                    filename=file.filename,
                    operation_id=operation_id,
                    http_status=error.status_code,
                )

            # Parse the redaction mapping JSON string to get the mapping data and count of redactions.
            mapping_data, total_redactions, mapping_error = (
                self._parse_redaction_mapping(
                    redaction_mapping, file.filename, operation_id
                )
            )
            if mapping_error:
                # If parsing the redaction mapping fails, return the error response.
                return self._build_error_response(
                    filename=file.filename,
                    operation_id=operation_id,
                    http_status=mapping_error.status_code,
                )

            # Override or set the remove_images flag in the mapping based on the provided parameter.
            mapping_data["remove_images"] = remove_images

            # Measure the time taken to apply redactions.
            redact_start = time.time()
            try:
                # Initialize the PDFRedactionService with the file contents.
                redaction_service = PDFRedactionService(contents)
                # Apply redactions in memory using the parsed mapping data.
                redacted_content = redaction_service.apply_redactions_to_memory(
                    mapping_data, remove_images
                )
                # Close the redaction service to free up resources.
                redaction_service.close()
                log_info(
                    f"[SECURITY] PDF redaction completed successfully: {total_redactions} redactions applied [operation_id={operation_id}]"
                )
            except Exception as e:
                # If an error occurs during the redaction process, log the error and return a secure error response.
                log_error(
                    f"[SECURITY] Error applying redactions: {str(e)} [operation_id={operation_id}]"
                )
                error_response = SecurityAwareErrorHandler.handle_safe_error(
                    e, "file_redaction_service", file.filename
                )
                return self._build_error_response(
                    filename=file.filename,
                    operation_id=operation_id,
                    http_status=error_response["status_code"],
                )

            # Calculate the elapsed time for redaction and the total processing time.
            redact_time = time.time() - redact_start
            total_time = time.time() - start_time

            # Record processing details for compliance and auditing purposes.
            record_keeper.record_processing(
                operation_type="pdf_redaction",
                document_type="PDF",
                entity_types_processed=[],
                processing_time=total_time,
                entity_count=total_redactions,
                success=True,
            )

            # Log sensitive operation details including redaction count and timing.
            log_sensitive_operation(
                "PDF Redaction",
                total_redactions,
                total_time,
                redact_time=redact_time,
                file_type="PDF",
            )

            # Retrieve current memory usage statistics after redaction.
            mem_stats = memory_monitor.get_memory_stats()
            log_info(
                f"[SECURITY] Memory usage after PDF redaction: current={mem_stats['current_usage']:.1f}%, peak={mem_stats['peak_usage']:.1f}% [operation_id={operation_id}]"
            )

            # Define an asynchronous generator to stream the redacted content in fixed-size chunks.
            async def content_streamer():
                # Loop through the redacted content by CHUNK_SIZE and yield each chunk.
                for i in range(0, len(redacted_content), CHUNK_SIZE):
                    yield redacted_content[i : i + CHUNK_SIZE]

            # Prepare HTTP response headers with detailed operation metrics.
            response_headers = {
                "Content-Disposition": "attachment; filename=redacted.pdf",
                "X-Redaction-Time": f"{redact_time:.3f}s",
                "X-Total-Time": f"{total_time:.3f}s",
                "X-Redactions-Applied": str(total_redactions),
                "X-Memory-Usage": f"{mem_stats['current_usage']:.1f}%",
                "X-Peak-Memory": f"{mem_stats['peak_usage']:.1f}%",
                "X-Operation-ID": operation_id,
            }
            # Return a StreamingResponse with the redacted PDF.
            return StreamingResponse(
                content_streamer(),
                media_type="application/pdf",
                headers=response_headers,
            )

        except Exception as e:
            # Catch any unexpected errors, log the error, and return a secure API error response.
            log_error(
                f"[SECURITY] Unhandled exception in PDF redaction: {str(e)} [operation_id={operation_id}]"
            )
            error_response = SecurityAwareErrorHandler.handle_safe_error(
                e, "file_redaction_service", file.filename
            )
            return JSONResponse(content=error_response)

    @staticmethod
    def _parse_redaction_mapping(
        redaction_mapping: Optional[str], filename: str, operation_id: str
    ) -> Tuple[dict, int, Optional[HTTPException]]:
        """
        Parse the redaction mapping JSON string.

        This method attempts to decode the provided JSON string containing redaction instructions.
        It calculates the total number of redactions specified and logs the outcome. If parsing fails,
        a secure error response is generated using SecurityAwareErrorHandler.

        Args:
            redaction_mapping: A JSON string with redaction details.
            filename: Name of the file being processed.
            operation_id: Unique identifier for the current operation.

        Returns:
            A tuple containing:
                - mapping_data: The parsed JSON object as a dictionary.
                - total_redactions: The total count of redactions specified in the mapping.
                - error_response: A HTTPException with error details if parsing fails, otherwise None.
        """
        if redaction_mapping:
            try:
                # Parse the redaction mapping JSON string into a dictionary.
                mapping_data = json.loads(redaction_mapping)
                # Compute the total number of redactions by summing the lengths of "sensitive" entries on each page.
                total_redactions = sum(
                    len(page.get("sensitive", []))
                    for page in mapping_data.get("pages", [])
                )
                log_info(
                    f"[SECURITY] Parsed redaction mapping with {total_redactions} redactions [operation_id={operation_id}]"
                )
                return mapping_data, total_redactions, None
            except Exception as e:
                # If parsing fails, log the error and generate a secure error response.
                log_error(
                    f"[SECURITY] Error parsing redaction mapping: {str(e)} [operation_id={operation_id}]"
                )
                error_response = SecurityAwareErrorHandler.handle_safe_error(
                    e, "file_mapping_parse", filename
                )
                return (
                    {},
                    0,
                    HTTPException(
                        status_code=error_response["status_code"],
                        detail=error_response["detail"],
                    ),
                )
        else:
            # If no redaction mapping is provided, log that an empty mapping will be used.
            log_info(
                f"[SECURITY] No redaction mapping provided; using empty mapping [operation_id={operation_id}]"
            )
            return {"pages": []}, 0, None

    @staticmethod
    def _build_error_response(
        filename: str, operation_id: str, http_status: int, total_redactions: int = 0
    ) -> JSONResponse:
        """
        Construct a standardized error response for a single-file redaction failure.

        This helper creates a `BatchRedactResponse` containing:
          - A `RedactFileResult` marking the file as an error.
          - A `RedactBatchSummary` summarizing the batch (always a single-file batch).
          - Wrapped in a FastAPI `JSONResponse` with the given HTTP status code.

        Parameters:
            filename (str): The original name of the file being redacted.
            operation_id (str): A unique identifier for this redaction operation (e.g. "pdf_redact_<timestamp>").
            http_status (int): The HTTP status code to return (e.g. 400, 500).
            total_redactions (int, optional): Number of redactions that had been applied before the failure occurred.
                Defaults to 0.

        Returns:
            JSONResponse:
                A FastAPI JSONResponse whose body is the serialized `BatchRedactResponse`.
        """
        # Build the per-file result indicating an error.
        file_result = RedactFileResult(file=filename, status="error")

        # Build the batch summary for a single-file batch.
        start_ts = float(operation_id.split("_", 1)[1])
        summary = RedactBatchSummary(
            batch_id=operation_id,
            total_files=1,
            successful=0,
            failed=1,
            total_redactions=total_redactions,
            total_time=time.time() - start_ts,
        )

        # Combine into the full batch response model.
        model = BatchRedactResponse(batch_summary=summary, file_results=[file_result])

        # Serialize the Pydantic model, dropping any None fields
        return JSONResponse(
            content=model.model_dump(exclude_none=True), status_code=http_status
        )
