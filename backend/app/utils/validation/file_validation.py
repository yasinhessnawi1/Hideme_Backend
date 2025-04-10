"""
Enhanced utility functions for validating file types, sizes, and content with comprehensive security.

This module provides advanced functions to:
  - Validate uploaded PDF files by checking their headers (magic bytes), MIME types, sizes, and safety.
  - Perform asynchronous content validation.
  - Read and validate a single PDF file ensuring that its size does not exceed MAX_PDF_SIZE_BYTES (10 MB).
  - Validate multiple uploaded PDF files by ensuring that:
      * No more than MAX_FILES_COUNT files are uploaded.
      * Each file meets the per-file requirements.
      * The total size of all files does not exceed TOTAL_MAX_SIZE_BYTES (25 MB).

Comprehensive logging and error handling (try/except) are implemented throughout.
"""

import asyncio
import logging
import mimetypes
import os
import re
import time
from typing import Optional, Union, Tuple, BinaryIO, List

from fastapi import UploadFile
from fastapi.responses import JSONResponse

from backend.app.utils.logging.logger import log_info, log_warning

MAX_PDF_SIZE_BYTES =  10 * 1024 * 1024 # 10 MB per file
# Constants for multi-file validation
TOTAL_MAX_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB total
MAX_FILES_COUNT = 10

APPLICATION_WORD = "application/pdf"
ALLOWED_MIME_TYPES = {
    "pdf": {APPLICATION_WORD, "application/x-pdf"}
}

# File signatures (magic bytes) for PDF files.
FILE_SIGNATURES = {
    "pdf": [(b"%PDF", 0)]
}

# Mapping from file extension to MIME type.
EXTENSION_TO_MIME = {
    ".pdf": APPLICATION_WORD
}

# Configure module-level logger
_logger = logging.getLogger("file_validation_utils")


def get_file_signature(content: bytes) -> Optional[str]:
    """
    Determine the file type from the content's signature (magic bytes).

    Args:
        content (bytes): The first chunk of file content.

    Returns:
        Optional[str]: The file type if recognized (e.g., 'pdf'), otherwise None.
    """
    if not content or len(content) < 4:
        return None
    for file_type, signatures in FILE_SIGNATURES.items():
        for signature, offset in signatures:
            if len(content) >= offset + len(signature):
                if content[offset:offset + len(signature)] == signature:
                    return file_type
    return None


def get_mime_type_from_buffer(buffer: Union[bytes, BinaryIO], filename: Optional[str] = None) -> str:
    """
    Determine the MIME type from file content and optional filename.

    Args:
        buffer (Union[bytes, BinaryIO]): File content as bytes or a file-like object.
        filename (Optional[str]): Optional filename for extension-based guessing.

    Returns:
        str: The MIME type string.
    """
    if filename:
        ext = os.path.splitext(filename)[1].lower()
        if ext in EXTENSION_TO_MIME:
            return EXTENSION_TO_MIME[ext]
        mime_type, _ = mimetypes.guess_type(filename)
        if mime_type:
            return mime_type
    if isinstance(buffer, bytes):
        content = buffer[:4096]
    else:
        pos = buffer.tell()
        content = buffer.read(4096)
        buffer.seek(pos)
    file_type = get_file_signature(content)
    if file_type == "pdf":
        return APPLICATION_WORD
    return "application/octet-stream"


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to prevent path traversal and other security issues.

    Args:
        filename (str): The original filename.

    Returns:
        str: A sanitized filename.
    """
    if not filename:
        return "unnamed_file"
    # Remove path components.
    filename = re.sub(r"[/\\]", "", filename)
    # Remove null bytes.
    filename = filename.replace("\x00", "")
    # Remove control characters.
    filename = re.sub(r"[\x01-\x1F\x7F]", "", filename)
    # Remove potentially dangerous characters.
    filename = re.sub(r"[;&|`$><^]", "", filename)
    # Limit filename length.
    if len(filename) > 255:
        base, ext = os.path.splitext(filename)
        filename = base[:250] + ext
    if not filename:
        filename = "unnamed_file"
    # Optionally randomize filename.
    if os.environ.get("RANDOMIZE_FILENAMES", "false").lower() == "true":
        import random, string
        suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        base, ext = os.path.splitext(filename)
        filename = f"{base}_{suffix}{ext}"
    return filename


def validate_mime_type(content_type: str, allowed_types: Optional[Union[List[str], set]] = None) -> bool:
    """
    Validate that the provided MIME type is allowed.

    Args:
        content_type (str): The MIME type to validate.
        allowed_types (Optional[Union[List[str], set]]): Allowed MIME types; defaults to ALLOWED_MIME_TYPES["pdf"].

    Returns:
        bool: True if the MIME type is allowed, otherwise False.
    """
    if not content_type:
        return False
    normalized = content_type.split(';')[0].strip().lower()
    if allowed_types is None:
        allowed_types = ALLOWED_MIME_TYPES["pdf"]
    elif isinstance(allowed_types, list):
        allowed_types = set(allowed_types)
    return normalized in allowed_types


def validate_pdf_file(content: bytes) -> bool:
    """
    Validate that a file is a genuine PDF by checking its header.

    Args:
        content (bytes): The file content.

    Returns:
        bool: True if content appears to be a valid PDF, False otherwise.
    """
    try:
        if not content.startswith(b"%PDF"):
            return False
        match = re.search(rb"%PDF-(\d+)\.(\d+)", content[:20])
        if not match:
            return False
        major = int(match.group(1))
        if major < 1 or major > 9:
            return False
        return True
    except Exception as e:
        _logger.warning("PDF validation error: %s", e)
        return False


def _check_pdf_javascript(content: bytes, filename: Optional[str]) -> Tuple[bool, str]:
    """
    Check PDF content for JavaScript markers.

    Args:
        content (bytes): The PDF file content.
        filename (Optional[str]): Filename for logging.

    Returns:
        Tuple[bool, str]: (is_safe, reason). If JavaScript is detected and blocking is enabled,
                          returns False with a reason.
    """
    if b"/JavaScript" in content or b"/JS" in content:
        if os.environ.get("BLOCK_PDF_JAVASCRIPT", "false").lower() == "true":
            return False, "PDF contains JavaScript, which is not allowed"
        else:
            _logger.warning("PDF contains JavaScript: %s", filename or "")
    return True, ""


def _check_pdf_acroform(content: bytes, filename: Optional[str]) -> None:
    """
    Check for the presence of AcroForm in the PDF and log a warning if found.

    Args:
        content (bytes): The PDF file content.
        filename (Optional[str]): Filename for logging.
    """
    if b"/AcroForm" in content:
        _logger.warning("PDF contains AcroForm: %s", filename or "")


def validate_file_safety(content: bytes, filename: Optional[str] = None) -> Tuple[bool, str]:
    """
    Validate the safety of a PDF file by checking for potentially malicious elements.

    Args:
        content (bytes): The file content.
        filename (Optional[str]): Filename for logging.

    Returns:
        Tuple[bool, str]: (is_safe, reason). If unsafe, reason explains why.
    """
    file_type = get_file_signature(content)
    if file_type != "pdf":
        return False, "Only PDF files are allowed"
    is_safe, reason = _check_pdf_javascript(content, filename)
    if not is_safe:
        return False, reason
    try:
        _check_pdf_acroform(content, filename)
    except Exception as e:
        _logger.warning("Error checking PDF AcroForm: %s", e)
    return True, ""


def validate_file_content(content: bytes, filename: Optional[str] = None, content_type: Optional[str] = None) -> Tuple[bool, str, Optional[str]]:
    """
    Perform comprehensive validation of a PDF file's content.

    Args:
        content (bytes): The file content.
        filename (Optional[str]): Filename for extension-based checks.
        content_type (Optional[str]): Provided MIME type.

    Returns:
        Tuple[bool, str, Optional[str]]: (is_valid, reason, detected_mime_type).
    """
    if not content:
        return False, "Empty file content", None

    detected_mime = get_mime_type_from_buffer(content, filename)

    if content_type:
        normalized_content_type = content_type.split(';')[0].strip().lower()
        if normalized_content_type != detected_mime:
            return False, f"Content type mismatch: provided {normalized_content_type}, detected {detected_mime}", detected_mime

    if detected_mime not in ALLOWED_MIME_TYPES["pdf"]:
        return False, f"Only PDF files are allowed, detected: {detected_mime}", detected_mime

    if not validate_pdf_file(content):
        return False, "Invalid PDF file structure", detected_mime

    is_safe, reason = validate_file_safety(content, filename)
    if not is_safe:
        return False, reason, detected_mime

    return True, "", detected_mime


async def validate_file_content_async(content: bytes, filename: Optional[str] = None, content_type: Optional[str] = None) -> Tuple[bool, str, Optional[str]]:
    """
    Asynchronously validate a PDF file's content.

    Args:
        content (bytes): The file content.
        filename (Optional[str]): Filename.
        content_type (Optional[str]): Provided MIME type.

    Returns:
        Tuple[bool, str, Optional[str]]: (is_valid, reason, detected_mime_type).
    """
    try:
        result = await asyncio.to_thread(validate_file_content, content, filename, content_type)
        return result
    except Exception as e:
        _logger.warning("Error in async file content validation: %s", e)
        return False, "Async validation error", None


async def read_and_validate_file(file: UploadFile, operation_id: str) -> Tuple[Optional[bytes], Optional[JSONResponse], float]:
    """
    Reads and validates a single PDF file.

    The function checks:
      - The file's MIME type (only PDFs allowed).
      - Reads the file content.
      - Verifies that the file size does not exceed MAX_PDF_SIZE_BYTES (10 MB).
      - Validates the file content asynchronously.

    Args:
        file (UploadFile): The uploaded file.
        operation_id (str): Operation identifier for logging.

    Returns:
        Tuple[Optional[bytes], Optional[JSONResponse], float]:
          - The file content as bytes if valid; otherwise, None.
          - A JSONResponse error if validation fails; otherwise, None.
          - The elapsed time for reading the file.
    """

    try:
        if not validate_mime_type(file.content_type, list(ALLOWED_MIME_TYPES["pdf"])):
            log_warning(f"[SECURITY] Unsupported file type: {file.content_type} [operation_id={operation_id}]")
            return None, JSONResponse(status_code=415, content={"detail": "Only PDF files are supported", "operation_id": operation_id}), 0

        file_read_start = time.time()
        content = await file.read()
        file_read_time = time.time() - file_read_start
        log_info(f"[SECURITY] File read completed in {file_read_time:.3f}s. Size: {len(content) / 1024:.1f}KB [operation_id={operation_id}]")

        if len(content) > MAX_PDF_SIZE_BYTES:
            log_warning(f"[SECURITY] PDF size exceeds limit: {len(content)/(1024*1024):.2f}MB > {MAX_PDF_SIZE_BYTES/(1024*1024):.2f}MB [operation_id={operation_id}]")
            return None, JSONResponse(
                status_code=413,
                content={"detail": f"PDF file size exceeds maximum allowed ({MAX_PDF_SIZE_BYTES // (1024*1024)}MB)", "operation_id": operation_id}
            ), file_read_time

        is_valid, reason, _ = await validate_file_content_async(content, file.filename, file.content_type)
        if not is_valid:
            log_warning(f"[SECURITY] Invalid PDF content: {reason} [operation_id={operation_id}]")
            return None, JSONResponse(status_code=415, content={"detail": reason, "operation_id": operation_id}), file_read_time

        return content, None, file_read_time

    except Exception as e:
        log_warning(f"[SECURITY] Exception in read_and_validate_file: {str(e)} [operation_id={operation_id}]")
        return None, JSONResponse(status_code=500, content={"detail": "Internal Server Error", "operation_id": operation_id}), 0
