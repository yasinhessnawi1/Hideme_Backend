import json
import time
from typing import Optional, Tuple, Union

from fastapi import UploadFile
from fastapi.responses import StreamingResponse, JSONResponse

from backend.app.document_processing.pdf_redactor import PDFRedactionService
from backend.app.utils.logging.logger import log_info, log_error
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.system_utils.memory_management import memory_monitor
from backend.app.utils.validation.file_validation import (
    read_and_validate_file
)

CHUNK_SIZE = 64 * 1024  # 64KB

class DocumentRedactionService:
    """
    Service that encapsulates all steps for applying redactions to a PDF file.
    Uses the centralized PDFRedactionService for in-memory redaction,
    includes performance metrics, and streams the result to minimize memory footprint.

    The redaction mapping (a JSON string) may include details for text-based redactions.
    Additionally, the client can specify a boolean flag `remove_images` (default False) to
    indicate that images should also be detected and redacted.
    """

    async def redact(
            self,
            file: UploadFile,
            redaction_mapping: Optional[str],
            remove_images: bool = False
    ) -> Union[StreamingResponse, JSONResponse]:
        """
        Redact the provided PDF file using the specified redaction mapping and optional image removal.

        Args:
            file: The PDF file to be redacted.
            redaction_mapping: A JSON string with redaction details. Expected format:
                {"pages": [{"page": page_num, "sensitive": [items]}], "remove_images": false}
            remove_images: Boolean flag; if True, images will be detected and redacted.
                           This flag overrides any value in the mapping.

        Returns:
            A StreamingResponse containing the redacted PDF or a JSONResponse with an error.
        """
        start_time = time.time()
        operation_id = f"pdf_redact_{time.time()}"
        log_info(f"[SECURITY] Starting PDF redaction processing [operation_id={operation_id}]")

        try:
            # Validate and read the file.
            contents, error, _ = await read_and_validate_file(file, operation_id)
            if error:
                return error

            # Parse redaction mapping.
            mapping_data, total_redactions, mapping_error = self._parse_redaction_mapping(
                redaction_mapping, file.filename, operation_id
            )
            if mapping_error:
                return mapping_error

            # Override or set the remove_images flag in the mapping using the provided parameter.
            mapping_data["remove_images"] = remove_images

            # Apply redactions using the centralized PDFRedactionService.
            redact_start = time.time()
            try:
                redaction_service = PDFRedactionService(contents)
                redacted_content = redaction_service.apply_redactions_to_memory(mapping_data, remove_images)
                redaction_service.close()
                log_info(
                    f"[SECURITY] PDF redaction completed successfully: {total_redactions} redactions applied [operation_id={operation_id}]")
            except Exception as e:
                log_error(f"[SECURITY] Error applying redactions: {str(e)} [operation_id={operation_id}]")
                error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                    e, "pdf_redaction_service", 500, file.filename
                )
                return JSONResponse(status_code=status_code, content=error_response)

            redact_time = time.time() - redact_start
            total_time = time.time() - start_time

            # Record processing for compliance.
            record_keeper.record_processing(
                operation_type="pdf_redaction",
                document_type="PDF",
                entity_types_processed=[],
                processing_time=total_time,
                entity_count=total_redactions,
                success=True
            )

            # Log the sensitive operation.
            log_sensitive_operation(
                "PDF Redaction",
                total_redactions,
                total_time,
                redact_time=redact_time,
                file_type="PDF"
            )

            # Get memory statistics.
            mem_stats = memory_monitor.get_memory_stats()
            log_info(
                f"[SECURITY] Memory usage after PDF redaction: current={mem_stats['current_usage']:.1f}%, peak={mem_stats['peak_usage']:.1f}% [operation_id={operation_id}]")

            # Stream the redacted content in chunks.
            async def content_streamer():
                for i in range(0, len(redacted_content), CHUNK_SIZE):
                    yield redacted_content[i:i + CHUNK_SIZE]

            response_headers = {
                "Content-Disposition": "attachment; filename=redacted.pdf",
                "X-Redaction-Time": f"{redact_time:.3f}s",
                "X-Total-Time": f"{total_time:.3f}s",
                "X-Redactions-Applied": str(total_redactions),
                "X-Memory-Usage": f"{mem_stats['current_usage']:.1f}%",
                "X-Peak-Memory": f"{mem_stats['peak_usage']:.1f}%",
                "X-Operation-ID": operation_id
            }
            return StreamingResponse(content_streamer(), media_type="application/pdf", headers=response_headers)

        except Exception as e:
            log_error(f"[SECURITY] Unhandled exception in PDF redaction: {str(e)} [operation_id={operation_id}]")
            error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                e, "pdf_redaction", 500, file.filename
            )
            return JSONResponse(status_code=status_code, content=error_response)

    @staticmethod
    def _parse_redaction_mapping(redaction_mapping: Optional[str], filename: str, operation_id: str) -> Tuple[
        dict, int, Optional[JSONResponse]]:
        """
        Parse the redaction mapping JSON string.
        Returns a tuple of (mapping_data, total_redactions, error_response).
        If parsing is successful, error_response is None.
        """
        if redaction_mapping:
            try:
                mapping_data = json.loads(redaction_mapping)
                total_redactions = sum(len(page.get("sensitive", [])) for page in mapping_data.get("pages", []))
                log_info(
                    f"[SECURITY] Parsed redaction mapping with {total_redactions} redactions [operation_id={operation_id}]")
                return mapping_data, total_redactions, None
            except Exception as e:
                log_error(f"[SECURITY] Error parsing redaction mapping: {str(e)} [operation_id={operation_id}]")
                error_response, status_code = SecurityAwareErrorHandler.create_api_error_response(
                    e, "redaction_mapping_parse", 400, filename
                )
                return {}, 0, JSONResponse(status_code=status_code, content=error_response)
        else:
            log_info(f"[SECURITY] No redaction mapping provided; using empty mapping [operation_id={operation_id}]")
            return {"pages": []}, 0, None