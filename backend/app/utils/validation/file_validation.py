"""
Enhanced utility functions for validating file types and content with comprehensive security.

This module provides advanced functions to validate uploaded PDF files by checking their headers,
content types, signatures, and sizes to prevent security issues related to malicious file uploads.
It implements in-depth content inspection and improved security checks.
"""

import asyncio
import logging
import mimetypes
import os
import re
from typing import Optional, Union, Tuple, BinaryIO

# Configure logging
_logger = logging.getLogger("file_validation")

# Maximum file size for PDFs (in bytes)
MAX_PDF_SIZE_BYTES = int(os.environ.get("MAX_PDF_SIZE_BYTES", 25 * 1024 * 1024))  # 25MB

APPLICATION_WORD = "application/pdf"

# Allowed MIME types (only PDFs are allowed)
ALLOWED_MIME_TYPES = {
    "pdf": {APPLICATION_WORD, "application/x-pdf"}
}

# File signatures (magic bytes) for PDF files
FILE_SIGNATURES = {
    "pdf": [(b"%PDF", 0)]
}

# Mapping from file extension to MIME type (only PDF is supported)
EXTENSION_TO_MIME = {
    ".pdf": APPLICATION_WORD
}

# Malicious content patterns to check for
MALICIOUS_PATTERNS = {
    "js_injection": rb"<script.*?>.*?</script>",
    "php_injection": rb"<\?php.*?\?>",
    "sql_injection": rb"(?i)(?:SELECT|INSERT|UPDATE|DELETE|DROP|UNION).*?(?:FROM|INTO|WHERE|TABLE)",
    "command_injection": rb"(?i)(?:\||;|`|&|\$\(|\$\{)",
    "xss": rb"(?i)(?:on\w+\s*=|javascript:)",
    "html_injection": rb"(?i)(?:<\s*(?:iframe|frame|embed|object|applet))",
    "path_traversal": rb"(?:\.\./|\.\.\\\|\.\.;)",
    "null_byte": rb"\x00"
}


# Utility Functions

def get_file_signature(content: bytes) -> Optional[str]:
    """
    Determine the file type from the content's signature (magic bytes).

    Args:
        content: First chunk of file content (at least first 16 bytes).

    Returns:
        File type string or None if the signature is not recognized.
    """
    if not content or len(content) < 4:
        return None
    for file_type, signatures in FILE_SIGNATURES.items():
        for signature, offset in signatures:
            if len(content) >= offset + len(signature):
                if content[offset:offset + len(signature)] == signature:
                    return file_type
    return None


def get_mime_type_from_buffer(
        buffer: Union[bytes, BinaryIO],
        filename: Optional[str] = None
) -> str:
    """
    Determine MIME type from file content and an optional filename.

    Args:
        buffer: File content as bytes or a file-like object.
        filename: Optional filename for extension-based guessing.

    Returns:
        MIME type string.
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
        filename: The filename to sanitize.

    Returns:
        A sanitized filename.
    """
    if not filename:
        return "unnamed_file"
    # Remove any path components.
    filename = re.sub(r"[/\\]", "", filename)
    # Replace null bytes using str.replace.
    filename = filename.replace("\x00", "")
    # Remove any control characters.
    filename = re.sub(r"[\x01-\x1F\x7F]", "", filename)
    # Remove potentially dangerous characters.
    filename = re.sub(r"[;&|`$><^]", "", filename)
    # Limit filename length.
    if len(filename) > 255:
        base, ext = os.path.splitext(filename)
        filename = base[:250] + ext
    if not filename:
        filename = "unnamed_file"
    # Optionally add a random suffix for extra safety.
    if os.environ.get("RANDOMIZE_FILENAMES", "false").lower() == "true":
        import random, string
        suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        base, ext = os.path.splitext(filename)
        filename = f"{base}_{suffix}{ext}"
    return filename


def is_valid_file_size(file_size: int, file_type: str) -> bool:
    """
    Check if the file size is within the allowed limit for PDF files.

    Args:
        file_size: Size of the file in bytes.
        file_type: Type of the file (only 'pdf' is supported).

    Returns:
        True if the file size is within limits, False otherwise.
    """
    max_size = MAX_PDF_SIZE_BYTES
    valid = file_size <= max_size
    if not valid:
        _logger.warning("File size %d exceeds maximum %d for type %s", file_size, max_size, file_type)
    return valid


def validate_mime_type(content_type: str, allowed_types: Optional[Union[list, set]] = None) -> bool:
    """
    Validate that the provided content type is allowed.

    Args:
        content_type: The MIME type to check.
        allowed_types: Optional list or set of allowed MIME types. Defaults to ALLOWED_MIME_TYPES["pdf"].

    Returns:
        True if the normalized content type is allowed, otherwise False.
    """
    if not content_type:
        return False
    normalized = content_type.split(';')[0].strip().lower()
    if allowed_types is None:
        allowed_types = ALLOWED_MIME_TYPES["pdf"]
    elif isinstance(allowed_types, list):
        allowed_types = set(allowed_types)
    return normalized in allowed_types


# PDF Validation Functions (Only PDFs are Supported)

def validate_pdf_file(content: bytes) -> bool:
    """
    Validate that a file is a genuine PDF by checking its header.

    Args:
        content: File content as bytes (first chunk should include the header).

    Returns:
        True if the file appears to be a valid PDF, False otherwise.
    """
    try:
        if not content.startswith(b"%PDF"):
            return False
        match = re.search(rb"%PDF-(\d+)\.(\d+)", content[:20])
        if not match:
            return False
        major, _ = int(match.group(1)), int(match.group(2))
        if major < 1 or major > 9:
            return False
        return True
    except (ValueError, re.error) as e:
        _logger.warning("PDF validation error: %s", e)
        return False


def _check_pdf_javascript(content: bytes, filename: Optional[str]) -> Tuple[bool, str]:
    """
    Check PDF content for JavaScript markers.

    Args:
        content: PDF content as bytes.
        filename: Optional filename.

    Returns:
        Tuple (is_safe, reason). If JavaScript is found and BLOCK_PDF_JAVASCRIPT is true,
        returns False with an appropriate reason.
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
        content: PDF content as bytes.
        filename: Optional filename.
    """
    if b"/AcroForm" in content:
        _logger.warning("PDF contains AcroForm: %s", filename or "")


def validate_file_safety(content: bytes, filename: Optional[str] = None) -> Tuple[bool, str]:
    """
    Validate the safety of a PDF file by checking for potentially malicious elements.

    This function only supports PDFs. It verifies the file signature and checks for JavaScript markers.

    Args:
        content: File content as bytes.
        filename: Optional filename for logging purposes.

    Returns:
        Tuple (is_safe, reason). If safety checks fail, is_safe is False and reason explains why.
    """
    file_type = get_file_signature(content)
    if file_type != "pdf":
        return False, "Only PDF files are allowed"
    is_safe, reason = _check_pdf_javascript(content, filename)
    if not is_safe:
        return False, reason
    try:
        _check_pdf_acroform(content, filename)
    except OSError as e:
        _logger.warning("Error checking PDF AcroForm: %s", e)
    return True, ""


def validate_file_content(
        content: bytes,
        filename: Optional[str] = None,
        content_type: Optional[str] = None
) -> Tuple[bool, str, Optional[str]]:
    """
    Perform comprehensive validation of a PDF file's content.

    This function only supports PDF files. It verifies the MIME type (allowing only PDFs),
    checks the PDF file structure, and then performs safety checks.

    Args:
        content: File content as bytes.
        filename: Optional filename for extension-based checks.
        content_type: Optional content type to validate against.

    Returns:
        Tuple (is_valid, reason, detected_mime_type). If validation fails, is_valid is False and
        reason provides the explanation.
    """
    if not content:
        return False, "Empty file content", None

    detected_mime = get_mime_type_from_buffer(content, filename)

    # Use content_type if provided to validate the detected MIME type.
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


async def validate_file_content_async(
        content: bytes,
        filename: Optional[str] = None,
        content_type: Optional[str] = None
) -> Tuple[bool, str, Optional[str]]:
    """
    Asynchronously perform comprehensive validation of a PDF file's content.

    Wraps the synchronous validate_file_content function in an asynchronous call.

    Args:
        content: File content as bytes.
        filename: Optional filename.
        content_type: Optional content type to validate against.

    Returns:
        Tuple (is_valid, reason, detected_mime_type).
    """
    try:
        result = await asyncio.to_thread(validate_file_content, content, filename, content_type)
        return result
    except Exception as e:
        _logger.warning("Error in async file content validation: %s", e)
        return False, "Async validation error", None