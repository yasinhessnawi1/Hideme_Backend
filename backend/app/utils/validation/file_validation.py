"""
Enhanced utility functions for validating file types, sizes, and content with comprehensive security.
This module provides advanced functions to:
  - Validate uploaded PDF files by checking their headers (magic bytes), MIME types, sizes, and safety.
  - Perform asynchronous content validation.
  - Read and validate a single PDF file ensuring that its size does not exceed MAX_PDF_SIZE_BYTES (10 MB).
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

from backend.app.utils.constant.constant import FILE_SIGNATURES, EXTENSION_TO_MIME, APPLICATION_WORD, \
    ALLOWED_MIME_TYPES, MAX_PDF_SIZE_BYTES
from backend.app.utils.logging.logger import log_info, log_warning

# Configure module-level logger.
_logger = logging.getLogger("file_validation_utils")


def get_file_signature(content: bytes) -> Optional[str]:
    """
    Determine the file type from the content's signature (magic bytes).

    Args:
        content (bytes): The first chunk of file content.

    Returns:
        Optional[str]: The file type if recognized (e.g., 'pdf'), otherwise None.
    """
    # Check if content is not empty and has at least 4 bytes.
    if not content or len(content) < 4:
        return None
    # Iterate over each file type and its associated signatures.
    for file_type, signatures in FILE_SIGNATURES.items():
        # For each signature and offset pair.
        for signature, offset in signatures:
            # Check if content length is sufficient for the signature match.
            if len(content) >= offset + len(signature):
                # Compare the specific segment of content with the signature.
                if content[offset:offset + len(signature)] == signature:
                    # Return the matching file type.
                    return file_type
    # If no match is found, return None.
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
    # If a filename is provided, attempt extension-based MIME type detection.
    if filename:
        # Extract the file extension in lower case.
        ext = os.path.splitext(filename)[1].lower()
        # If the extension is in our mapping, return its MIME type.
        if ext in EXTENSION_TO_MIME:
            return EXTENSION_TO_MIME[ext]
        # Otherwise, attempt to guess MIME type using mimetypes.
        mime_type, _ = mimetypes.guess_type(filename)
        if mime_type:
            return mime_type
    # If buffer is of type bytes, slice the first 4096 bytes.
    if isinstance(buffer, bytes):
        content = buffer[:4096]
    else:
        # Save current stream position.
        pos = buffer.tell()
        # Read up to 4096 bytes from the file-like object.
        content = buffer.read(4096)
        # Reset stream position.
        buffer.seek(pos)
    # Use get_file_signature to determine file type from content.
    file_type = get_file_signature(content)
    # If file type is identified as PDF, return the predefined MIME type.
    if file_type == "pdf":
        return APPLICATION_WORD
    # Otherwise, return a generic binary MIME type.
    return "application/octet-stream"


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to prevent path traversal and other security issues.

    Args:
        filename (str): The original filename.

    Returns:
        str: A sanitized filename.
    """
    # If filename is empty, return a default name.
    if not filename:
        return "unnamed_file"
    # Remove any directory paths by eliminating forward and backward slashes.
    filename = re.sub(r"[/\\]", "", filename)
    # Remove null bytes from the filename.
    filename = filename.replace("\x00", "")
    # Remove control characters from the filename.
    filename = re.sub(r"[\x01-\x1F\x7F]", "", filename)
    # Remove special characters that could be used in command injection.
    filename = re.sub(r"[;&|`$><^]", "", filename)
    # If the filename exceeds 255 characters, truncate it.
    if len(filename) > 255:
        base, ext = os.path.splitext(filename)
        filename = base[:250] + ext
    # If after sanitization the filename is empty, set a default name.
    if not filename:
        filename = "unnamed_file"
    # Check environment variable to see if filenames should be randomized.
    if os.environ.get("RANDOMIZE_FILENAMES", "false").lower() == "true":
        import random, string
        # Generate a random 8-character suffix.
        suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        base, ext = os.path.splitext(filename)
        # Append the random suffix to the base name.
        filename = f"{base}_{suffix}{ext}"
    # Return the sanitized filename.
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
    # Check if content_type is provided.
    if not content_type:
        return False
    # Normalize the content type by splitting and stripping extra parameters.
    normalized = content_type.split(';')[0].strip().lower()
    # Use default allowed types if none provided.
    if allowed_types is None:
        allowed_types = ALLOWED_MIME_TYPES["pdf"]
    # If allowed_types is a list, convert it to a set for faster lookup.
    elif isinstance(allowed_types, list):
        allowed_types = set(allowed_types)
    # Check if the normalized content type is in the allowed set.
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
        # Check if content starts with the PDF magic bytes.
        if not content.startswith(b"%PDF"):
            return False
        # Use regex to search for the PDF version in the header.
        match = re.search(rb"%PDF-(\d+)\.(\d+)", content[:20])
        if not match:
            return False
        # Convert the major version from the match to an integer.
        major = int(match.group(1))
        # Validate that the major version is within a plausible range.
        if major < 1 or major > 9:
            return False
        # If all checks pass, return True.
        return True
    except Exception as e:
        # Log any exception that occurs during PDF validation.
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
    # If JavaScript markers are found in the content...
    if b"/JavaScript" in content or b"/JS" in content:
        # Check environment variable to determine if JavaScript in PDFs should be blocked.
        if os.environ.get("BLOCK_PDF_JAVASCRIPT", "false").lower() == "true":
            return False, "PDF contains JavaScript, which is not allowed"
        else:
            # Log a warning that JavaScript was found but not blocked.
            _logger.warning("PDF contains JavaScript: %s", filename or "")
    # Return True if file is deemed safe.
    return True, ""


def _check_pdf_acroform(content: bytes, filename: Optional[str]) -> None:
    """
    Check for the presence of AcroForm in the PDF and log a warning if found.

    Args:
        content (bytes): The PDF file content.
        filename (Optional[str]): Filename for logging.
    """
    # If the AcroForm marker is found in the content...
    if b"/AcroForm" in content:
        # Log a warning that AcroForm was found.
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
    # Determine the file type from content signature.
    file_type = get_file_signature(content)
    # If the file type is not PDF, it's unsafe.
    if file_type != "pdf":
        return False, "Only PDF files are allowed"
    # Check for JavaScript elements in the PDF.
    is_safe, reason = _check_pdf_javascript(content, filename)
    if not is_safe:
        return False, reason
    # Attempt to check for AcroForm and log any warnings.
    try:
        _check_pdf_acroform(content, filename)
    except Exception as e:
        _logger.warning("Error checking PDF AcroForm: %s", e)
    # Return True if all safety checks pass.
    return True, ""


def validate_file_content(content: bytes, filename: Optional[str] = None, content_type: Optional[str] = None) -> Tuple[
    bool, str, Optional[str]]:
    """
    Perform comprehensive validation of a PDF file's content.

    Args:
        content (bytes): The file content.
        filename (Optional[str]): Filename for extension-based checks.
        content_type (Optional[str]): Provided MIME type.

    Returns:
        Tuple[bool, str, Optional[str]]: (is_valid, reason, detected_mime_type).
    """
    # Check if content is empty.
    if not content:
        return False, "Empty file content", None

    # Detect MIME type from the buffer and filename.
    detected_mime = get_mime_type_from_buffer(content, filename)

    # If a content_type is provided...
    if content_type:
        # Normalize content type.
        normalized_content_type = content_type.split(';')[0].strip().lower()
        # Compare with the detected MIME type.
        if normalized_content_type != detected_mime:
            return False, f"Content type mismatch: provided {normalized_content_type}, detected {detected_mime}", detected_mime

    # Check if the detected MIME type is allowed for PDFs.
    if detected_mime not in ALLOWED_MIME_TYPES["pdf"]:
        return False, f"Only PDF files are allowed, detected: {detected_mime}", detected_mime

    # Validate the PDF file structure.
    if not validate_pdf_file(content):
        return False, "Invalid PDF file structure", detected_mime

    # Validate the file safety (e.g., absence of malicious scripts).
    is_safe, reason = validate_file_safety(content, filename)
    if not is_safe:
        return False, reason, detected_mime

    # If all validations pass, return True.
    return True, "", detected_mime


async def validate_file_content_async(content: bytes, filename: Optional[str] = None,
                                      content_type: Optional[str] = None) -> Tuple[bool, str, Optional[str]]:
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
        # Offload synchronous validation to a separate thread.
        result = await asyncio.to_thread(validate_file_content, content, filename, content_type)
        # Return the result from the synchronous function.
        return result
    except Exception as e:
        # Log any errors that occur during async validation.
        _logger.warning("Error in async file content validation: %s", e)
        return False, "Async validation error", None


async def read_and_validate_file(file: UploadFile, operation_id: str) -> Tuple[
    Optional[bytes], Optional[JSONResponse], float]:
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
        # Validate the MIME type of the file against allowed PDF types.
        if not validate_mime_type(file.content_type, list(ALLOWED_MIME_TYPES["pdf"])):
            log_warning(f"[SECURITY] Unsupported file type: {file.content_type} [operation_id={operation_id}]")
            # Return an HTTP 415 error response if MIME type is not supported.
            return None, JSONResponse(status_code=415, content={"detail": "Only PDF files are supported",
                                                                "operation_id": operation_id}), 0

        # Record the start time for reading the file.
        file_read_start = time.time()
        # Read the entire file content asynchronously.
        content = await file.read()
        # Compute the elapsed time for the file read.
        file_read_time = time.time() - file_read_start
        # Log the file read completion with timing and size information.
        log_info(
            f"[SECURITY] File read completed in {file_read_time:.3f}s. Size: {len(content) / 1024:.1f}KB [operation_id={operation_id}]")

        # Check if the file size exceeds the maximum allowed PDF size.
        if len(content) > MAX_PDF_SIZE_BYTES:
            log_warning(
                f"[SECURITY] PDF size exceeds limit: {len(content) / (1024 * 1024):.2f}MB > {MAX_PDF_SIZE_BYTES / (1024 * 1024):.2f}MB [operation_id={operation_id}]")
            # Return an HTTP 413 error response if file is too large.
            return None, JSONResponse(status_code=413,
                                      content={
                                          "detail": f"PDF file size exceeds maximum allowed ({MAX_PDF_SIZE_BYTES // (1024 * 1024)}MB)",
                                          "operation_id": operation_id}), file_read_time

        # Asynchronously validate the file content.
        is_valid, reason, _ = await validate_file_content_async(content, file.filename, file.content_type)
        if not is_valid:
            log_warning(f"[SECURITY] Invalid PDF content: {reason} [operation_id={operation_id}]")
            # Return an HTTP 415 error response if content validation fails.
            return None, JSONResponse(status_code=415,
                                      content={"detail": reason, "operation_id": operation_id}), file_read_time

        # Return the valid file content, no error response, and the elapsed read time.
        return content, None, file_read_time

    except Exception as e:
        # Log any exception encountered during reading and validation.
        log_warning(f"[SECURITY] Exception in read_and_validate_file: {str(e)} [operation_id={operation_id}]")
        # Return an HTTP 500 error response in case of server error.
        return None, JSONResponse(status_code=500,
                                  content={"detail": "Internal Server Error", "operation_id": operation_id}), 0
