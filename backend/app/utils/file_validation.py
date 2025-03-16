"""
Enhanced utility functions for validating file types and content with comprehensive security.

This module provides advanced functions to validate uploaded files by checking their headers,
content types, signatures, and sizes to prevent security issues related to malicious file uploads.
It implements in-depth content inspection, additional file type support, and improved security checks.
"""
import re
import os
import logging
import mimetypes
import hashlib
import asyncio
from typing import Dict, List, Optional, Union, Set, Tuple, BinaryIO, Any

# Configure logging
_logger = logging.getLogger("file_validation")

# Configure maximum file sizes (in bytes) with environment variable overrides
MAX_PDF_SIZE_BYTES = int(os.environ.get("MAX_PDF_SIZE_BYTES", 25 * 1024 * 1024))  # 25MB
MAX_TEXT_SIZE_BYTES = int(os.environ.get("MAX_TEXT_SIZE_BYTES", 10 * 1024 * 1024))  # 10MB
MAX_DOCX_SIZE_BYTES = int(os.environ.get("MAX_DOCX_SIZE_BYTES", 20 * 1024 * 1024))  # 20MB
MAX_BATCH_SIZE_BYTES = int(os.environ.get("MAX_BATCH_SIZE_BYTES", 50 * 1024 * 1024))  # 50MB
MAX_FILE_COUNT = int(os.environ.get("MAX_FILE_COUNT", 20))  # Maximum number of files in a batch

# Define allowed mime types by operation
ALLOWED_MIME_TYPES = {
    "pdf": {"application/pdf"},
    "text": {"text/plain", "text/csv", "text/markdown", "text/html", "text/xml"},
    "docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
             "application/msword", "application/vnd.oasis.opendocument.text"},
    "image": {"image/jpeg", "image/png", "image/gif", "image/svg+xml", "image/webp"},
    "all": {"application/pdf", "text/plain", "text/csv", "text/markdown", "text/html", "text/xml",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword", "application/vnd.oasis.opendocument.text",
            "image/jpeg", "image/png", "image/gif", "image/svg+xml", "image/webp"}
}

# File signatures (magic bytes) for common file formats
FILE_SIGNATURES = {
    "pdf": [(b"%PDF", 0)],  # PDF starts with %PDF
    "docx": [(b"PK\x03\x04", 0)],  # DOCX is a ZIP file, starts with PK
    "doc": [(b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1", 0)],  # DOC file header
    "jpg": [(b"\xFF\xD8\xFF", 0)],  # JPEG file header
    "png": [(b"\x89PNG\r\n\x1A\n", 0)],  # PNG file header
    "gif": [(b"GIF87a", 0), (b"GIF89a", 0)],  # GIF file headers
    "zip": [(b"PK\x03\x04", 0)],  # ZIP file header
    "odt": [(b"PK\x03\x04", 0)],  # ODT is also a ZIP file
    "xml": [(b"<?xml", 0)],  # XML declaration
    "html": [(b"<!DOCTYPE html", 0), (b"<html", 0)]  # HTML file headers
}

# File extension to MIME type mapping (supplementing mimetypes module)
EXTENSION_TO_MIME = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".md": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".xml": "text/xml"
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


async def validate_pdf_file_async(content: bytes) -> bool:
    """
    Asynchronously validate that a file is a genuine PDF by checking its header and structure.

    Args:
        content: First chunk of file content (at least first 1024 bytes)

    Returns:
        True if the file appears to be a valid PDF, False otherwise
    """
    return await asyncio.to_thread(validate_pdf_file, content)


def validate_pdf_file(content: bytes) -> bool:
    """
    Validate that a file is a genuine PDF by checking its header.
    This is a more lenient version that only checks essential markers.

    Args:
        content: First chunk of file content (at least first 1024 bytes)

    Returns:
        True if the file appears to be a valid PDF, False otherwise
    """
    # Check for PDF signature at beginning of file
    if not content.startswith(b"%PDF"):
        return False

    # Additional PDF validation checks
    try:
        # Check for PDF version (must be between 1.0 and 9.9)
        match = re.search(rb"%PDF-(\d+)\.(\d+)", content[:20])
        if not match:
            return False

        major, minor = int(match.group(1)), int(match.group(2))
        if major < 1 or major > 9:
            return False

        # More lenient approach - don't require EOF marker or xref table
        # as these might not be in the first chunk we're checking
        return True
    except Exception as e:
        _logger.warning(f"PDF validation error: {str(e)}")
        return False


async def validate_docx_file_async(content: bytes) -> bool:
    """
    Asynchronously validate that a file is a genuine DOCX by checking its header and structure.

    Args:
        content: First chunk of file content (at least first 4096 bytes)

    Returns:
        True if the file appears to be a valid DOCX, False otherwise
    """
    return await asyncio.to_thread(validate_docx_file, content)


def validate_docx_file(content: bytes) -> bool:
    """
    Validate that a file is a genuine DOCX by checking its header and structure.

    Args:
        content: First chunk of file content (at least first 4096 bytes)

    Returns:
        True if the file appears to be a valid DOCX, False otherwise
    """
    # DOCX files are ZIP files, so they start with PK
    if not content.startswith(b"PK\x03\x04"):
        return False

    # Additional DOCX validation checks
    try:
        # Check for required DOCX content signatures
        required_markers = [
            b"[Content_Types].xml",  # Content types definition
            b"word/",  # Word directory
            b"docProps/"  # Document properties
        ]

        # Check for at least one of the markers
        return any(marker in content for marker in required_markers)
    except Exception as e:
        _logger.warning(f"DOCX validation error: {str(e)}")
        return False


async def validate_mime_type_async(
        content_type: str,
        allowed_types: Optional[Union[List[str], Set[str]]] = None
) -> bool:
    """
    Asynchronously validate that a content type is in the list of allowed types with improved normalization.

    Args:
        content_type: The content type to validate
        allowed_types: List of allowed content types. If None, all configured types are allowed.

    Returns:
        True if the content type is allowed, False otherwise
    """
    return await asyncio.to_thread(validate_mime_type, content_type, allowed_types)


def validate_mime_type(
        content_type: str,
        allowed_types: Optional[Union[List[str], Set[str]]] = None
) -> bool:
    """
    Validate that a content type is in the list of allowed types with improved normalization.

    Args:
        content_type: The content type to validate
        allowed_types: List of allowed content types. If None, all configured types are allowed.

    Returns:
        True if the content type is allowed, False otherwise
    """
    if not content_type:
        return False

    if allowed_types is None:
        allowed_types = ALLOWED_MIME_TYPES["all"]
    elif isinstance(allowed_types, list):
        allowed_types = set(allowed_types)

    # Normalize content type (remove parameters, charset, etc.)
    content_type = content_type.split(';')[0].strip().lower()

    # Handle aliases (e.g., text/x-markdown -> text/markdown)
    # Some clients use non-standard MIME types
    content_type_aliases = {
        "text/x-markdown": "text/markdown",
        "application/x-pdf": "application/pdf",
        "text/x-csv": "text/csv",
        "application/csv": "text/csv",
        "application/excel": "text/csv",
        "application/vnd.ms-excel": "text/csv",
        "application/msword": "application/msword",
        "application/doc": "application/msword",
        "application/ms-doc": "application/msword",
        "application/vnd.ms-word": "application/msword"
    }

    # If we have an alias, use it
    if content_type in content_type_aliases:
        content_type = content_type_aliases[content_type]

    # Perform the actual check
    result = content_type in allowed_types
    if not result:
        _logger.warning(f"Invalid content type: {content_type}, allowed types: {allowed_types}")

    return result


async def get_file_signature_async(content: bytes) -> Optional[str]:
    """
    Asynchronously determine the file type from the content's signature (magic bytes).

    Args:
        content: First chunk of file content (at least first 16 bytes)

    Returns:
        File type string or None if the signature is not recognized
    """
    return await asyncio.to_thread(get_file_signature, content)


def get_file_signature(content: bytes) -> Optional[str]:
    """
    Determine the file type from the content's signature (magic bytes).

    Args:
        content: First chunk of file content (at least first 16 bytes)

    Returns:
        File type string or None if the signature is not recognized
    """
    if not content or len(content) < 8:
        return None

    for file_type, signatures in FILE_SIGNATURES.items():
        for signature, offset in signatures:
            if len(content) >= offset + len(signature):
                if content[offset:offset + len(signature)] == signature:
                    return file_type
    return None


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to prevent path traversal and other security issues.

    Args:
        filename: The filename to sanitize

    Returns:
        Sanitized filename
    """
    if not filename:
        return "unnamed_file"

    # Remove any path components
    filename = re.sub(r"[/\\]", "", filename)

    # Remove any null bytes
    filename = re.sub(r"\x00", "", filename)

    # Remove any control characters
    filename = re.sub(r"[\x01-\x1F\x7F]", "", filename)

    # Remove potentially dangerous characters
    filename = re.sub(r"[;&|`$><^]", "", filename)

    # Limit length
    if len(filename) > 255:
        base, ext = os.path.splitext(filename)
        filename = base[:250] + ext

    # Ensure filename is not empty
    if not filename:
        filename = "unnamed_file"

    # Add a random suffix for additional safety
    if os.environ.get("RANDOMIZE_FILENAMES", "false").lower() == "true":
        import random
        import string
        suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        base, ext = os.path.splitext(filename)
        filename = f"{base}_{suffix}{ext}"

    return filename


async def is_valid_file_size_async(file_size: int, file_type: str) -> bool:
    """
    Asynchronously check if the file size is within the allowed limit for the given file type.

    Args:
        file_size: Size of the file in bytes
        file_type: Type of the file (pdf, text, docx, batch)

    Returns:
        True if the file size is within limits, False otherwise
    """
    return await asyncio.to_thread(is_valid_file_size, file_size, file_type)


def is_valid_file_size(file_size: int, file_type: str) -> bool:
    """
    Check if the file size is within the allowed limit for the given file type.

    Args:
        file_size: Size of the file in bytes
        file_type: Type of the file (pdf, text, docx, batch)

    Returns:
        True if the file size is within limits, False otherwise
    """
    max_sizes = {
        "pdf": MAX_PDF_SIZE_BYTES,
        "text": MAX_TEXT_SIZE_BYTES,
        "docx": MAX_DOCX_SIZE_BYTES,
        "batch": MAX_BATCH_SIZE_BYTES,
        "image": 5 * 1024 * 1024  # 5MB
    }

    # Get the max size for this file type, defaulting to the most restrictive limit
    max_size = max_sizes.get(file_type, MAX_TEXT_SIZE_BYTES)

    # Check if the file size is within the limit
    is_valid = file_size <= max_size

    if not is_valid:
        _logger.warning(f"File size {file_size} exceeds maximum {max_size} for type {file_type}")

    return is_valid


async def get_mime_type_from_buffer_async(
        buffer: Union[bytes, BinaryIO],
        filename: Optional[str] = None
) -> str:
    """
    Asynchronously determine MIME type from file content and optional filename.

    Args:
        buffer: File content as bytes or file-like object
        filename: Optional filename for extension-based guessing

    Returns:
        MIME type string
    """
    return await asyncio.to_thread(get_mime_type_from_buffer, buffer, filename)


def get_mime_type_from_buffer(
        buffer: Union[bytes, BinaryIO],
        filename: Optional[str] = None
) -> str:
    """
    Determine MIME type from file content and optional filename.

    Args:
        buffer: File content as bytes or file-like object
        filename: Optional filename for extension-based guessing

    Returns:
        MIME type string
    """
    # First, try to guess from filename if provided
    if filename:
        # Try our custom mapping first
        ext = os.path.splitext(filename)[1].lower()
        if ext in EXTENSION_TO_MIME:
            return EXTENSION_TO_MIME[ext]

        # Then try using mimetypes module
        mime_type, _ = mimetypes.guess_type(filename)
        if mime_type:
            return mime_type

    # If filename doesn't help, check file signature
    if isinstance(buffer, bytes):
        content = buffer[:4096]  # First 4KB should be enough for signatures
    else:
        # Save position, read content, and restore position
        pos = buffer.tell()
        content = buffer.read(4096)
        buffer.seek(pos)

    # Get file type from signature
    file_type = get_file_signature(content)
    if file_type:
        # Map file type to MIME type
        mime_map = {
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "doc": "application/msword",
            "jpg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "zip": "application/zip",
            "xml": "text/xml",
            "html": "text/html"
        }
        return mime_map.get(file_type, "application/octet-stream")

    # If we can't determine from signature, check for text content
    try:
        # Try to decode as text
        text_sample = content.decode('utf-8', errors='ignore')
        # Heuristic: if >80% of characters are printable, it's probably text
        printable_chars = sum(c.isprintable() for c in text_sample)
        if printable_chars / len(text_sample) > 0.8:
            # Try to detect if it's HTML
            if re.search(r'<!DOCTYPE html|<html|<body', text_sample, re.IGNORECASE):
                return "text/html"
            # Try to detect if it's XML
            elif re.search(r'<\?xml|<[a-zA-Z0-9]+\s+xmlns', text_sample):
                return "text/xml"
            # Try to detect if it's CSV
            elif re.search(r'([^,]+,){3,}[^,]+', text_sample):
                return "text/csv"
            # Default to plain text
            return "text/plain"
    except:
        pass

    # If nothing else works, return default
    return "application/octet-stream"


async def validate_file_safety_async(content: bytes, filename: Optional[str] = None) -> Tuple[bool, str]:
    """
    Asynchronously validate file content for potentially malicious patterns.

    Args:
        content: File content as bytes
        filename: Optional filename for extension-based checks

    Returns:
        Tuple of (is_safe, reason) where reason is empty string if safe
    """
    return await asyncio.to_thread(validate_file_safety, content, filename)



def validate_file_safety(content: bytes, filename: Optional[str] = None) -> Tuple[bool, str]:
    """
    Validate file content for potentially malicious patterns.

    Args:
        content: File content as bytes
        filename: Optional filename for extension-based checks

    Returns:
        Tuple of (is_safe, reason) where reason is empty string if safe
    """
    # Remove the size limitation that creates a security gap
    # BEFORE: if len(content) > 10 * 1024 * 1024:  # 10MB
    #    return True, ""

    # Get file type from signature
    file_type = get_file_signature(content)

    # For text-based formats, check for malicious patterns
    text_formats = {"html", "xml", "text", None}
    if file_type in text_formats or (filename and any(filename.endswith(ext) for ext in
                                                      ['.txt', '.html', '.htm', '.xml', '.csv', '.md'])):
        # Check for malicious patterns
        for pattern_name, pattern in MALICIOUS_PATTERNS.items():
            if re.search(pattern, content):
                return False, f"Potential security issue: {pattern_name}"

    # For document formats like PDF, check for JavaScript or malicious elements
    if file_type == "pdf":
        # Check for JavaScript in PDF
        if b"/JavaScript" in content or b"/JS" in content:
            # This is a heuristic - not all PDFs with JavaScript are malicious
            # but many malicious PDFs contain JavaScript
            if os.environ.get("BLOCK_PDF_JAVASCRIPT", "false").lower() == "true":
                return False, "PDF contains JavaScript, which is not allowed"
            else:
                _logger.warning(f"PDF contains JavaScript: {filename}")

        # Check for AcroForm which could contain malicious elements
        if b"/AcroForm" in content:
            _logger.warning(f"PDF contains AcroForm: {filename}")

    # For docx/Office formats, check for macros
    if file_type in {"docx", "doc"} and b"VBA" in content:
        if os.environ.get("BLOCK_OFFICE_MACROS", "true").lower() == "true":
            return False, "Office document contains macros, which are not allowed"
        else:
            _logger.warning(f"Office document contains macros: {filename}")

    # For uploaded zip files, validate that they don't contain too many files
    # (potential zip bomb)
    if file_type == "zip" and os.environ.get("VALIDATE_ZIP_CONTENTS", "true").lower() == "true":
        try:
            import zipfile
            from io import BytesIO

            with zipfile.ZipFile(BytesIO(content)) as zf:
                if len(zf.namelist()) > MAX_FILE_COUNT:
                    return False, f"Zip contains too many files (max: {MAX_FILE_COUNT})"

                # Check for nested zips - potential zip bomb
                for file_info in zf.infolist():
                    # Check compressed vs uncompressed size ratio
                    if file_info.compress_size > 0 and file_info.file_size / file_info.compress_size > 100:
                        return False, "Suspicious compression ratio detected"

        except Exception as e:
            _logger.warning(f"Error checking zip file: {str(e)}")
            return False, "Invalid zip file structure"

    # File passed all safety checks
    return True, ""

async def validate_file_content_async(
        content: bytes,
        filename: Optional[str] = None,
        content_type: Optional[str] = None
) -> Tuple[bool, str, Optional[str]]:
    """
    Asynchronously perform comprehensive file validation checking signatures, content, and safety.

    Args:
        content: File content as bytes
        filename: Optional filename for extension-based checks
        content_type: Optional content type to validate

    Returns:
        Tuple of (is_valid, reason, detected_mime_type)
    """
    return await asyncio.to_thread(validate_file_content, content, filename, content_type)


def validate_file_content(
        content: bytes,
        filename: Optional[str] = None,
        content_type: Optional[str] = None
) -> Tuple[bool, str, Optional[str]]:
    """
    Comprehensive file validation checking signatures, content, and safety.

    Args:
        content: File content as bytes
        filename: Optional filename for extension-based checks
        content_type: Optional content type to validate

    Returns:
        Tuple of (is_valid, reason, detected_mime_type)
    """
    if not content:
        return False, "Empty file content", None

    # First, detect the MIME type from the content
    detected_mime = get_mime_type_from_buffer(content, filename)

    # If content_type was provided, validate it matches the detected type
    if content_type:
        normalized_content_type = content_type.split(';')[0].strip().lower()

        # Check if content type and detected type are compatible
        # We use "compatible" rather than equal because some types have aliases
        compatible = False

        # Exact match
        if normalized_content_type == detected_mime:
            compatible = True
        # Special cases for common text formats
        elif normalized_content_type.startswith("text/") and detected_mime.startswith("text/"):
            compatible = True
        # PDF specific check
        elif (normalized_content_type == "application/pdf" and
              (detected_mime == "application/pdf" or detected_mime == "application/x-pdf")):
            compatible = True
        # Office document checks
        elif (normalized_content_type in ALLOWED_MIME_TYPES["docx"] and
              detected_mime in ALLOWED_MIME_TYPES["docx"]):
            compatible = True

        if not compatible:
            return False, f"Content type mismatch: {normalized_content_type} vs {detected_mime}", detected_mime

    # Validate file integrity and structure according to claimed type
    if detected_mime == "application/pdf":
        if not validate_pdf_file(content):
            return False, "Invalid PDF file structure", detected_mime
    elif detected_mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        if not validate_docx_file(content):
            return False, "Invalid DOCX file structure", detected_mime

    # Validate file safety
    is_safe, reason = validate_file_safety(content, filename)
    if not is_safe:
        return False, reason, detected_mime

    # All validations passed
    return True, "", detected_mime


async def is_valid_batch_async(
        files: List[Dict[str, Any]],
        max_files: int = MAX_FILE_COUNT,
        max_batch_size: int = MAX_BATCH_SIZE_BYTES
) -> Tuple[bool, str, List[str]]:
    """
    Asynchronously validate a batch of files for total size and count limits.

    Args:
        files: List of file dictionaries with content and metadata
        max_files: Maximum number of files allowed in a batch
        max_batch_size: Maximum total batch size in bytes

    Returns:
        Tuple of (is_valid, reason, valid_file_ids)
    """
    return await asyncio.to_thread(is_valid_batch, files, max_files, max_batch_size)


def is_valid_batch(
        files: List[Dict[str, Any]],
        max_files: int = MAX_FILE_COUNT,
        max_batch_size: int = MAX_BATCH_SIZE_BYTES
) -> Tuple[bool, str, List[str]]:
    """
    Validate a batch of files for total size and count limits.

    Args:
        files: List of file dictionaries with content and metadata
        max_files: Maximum number of files allowed in a batch
        max_batch_size: Maximum total batch size in bytes

    Returns:
        Tuple of (is_valid, reason, valid_file_ids)
    """
    if not files:
        return False, "No files provided", []

    if len(files) > max_files:
        return False, f"Too many files. Maximum allowed: {max_files}", []

    total_size = 0
    valid_file_ids = []

    for file_info in files:
        file_size = file_info.get("size", 0)
        file_id = file_info.get("id", "unknown")

        # Validate individual file size
        file_type = file_info.get("type", "text")
        if not is_valid_file_size(file_size, file_type):
            continue

        total_size += file_size
        valid_file_ids.append(file_id)

        # Check batch size limit
        if total_size > max_batch_size:
            return False, f"Batch exceeds maximum size of {max_batch_size // (1024 * 1024)}MB", []

    if not valid_file_ids:
        return False, "No valid files in batch", []

    return True, "", valid_file_ids


def calculate_file_hash(file_content: bytes) -> str:
    """
    Calculate a secure hash of file content for deduplication or verification.

    Args:
        file_content: File content as bytes

    Returns:
        SHA-256 hash of the file content
    """
    hash_obj = hashlib.sha256()
    hash_obj.update(file_content)
    return hash_obj.hexdigest()


async def calculate_file_hash_async(file_content: bytes) -> str:
    """
    Asynchronously calculate a secure hash of file content for deduplication or verification.

    Args:
        file_content: File content as bytes

    Returns:
        SHA-256 hash of the file content
    """
    return await asyncio.to_thread(calculate_file_hash, file_content)


def get_file_extension(filename: str, content_type: Optional[str] = None) -> str:
    """
    Get the appropriate file extension based on filename and content type.

    Args:
        filename: Original filename
        content_type: Optional content type

    Returns:
        File extension including the dot (e.g., ".pdf")
    """
    # First, try to get extension from filename
    ext = os.path.splitext(filename)[1].lower()
    if ext:
        return ext

    # If no extension in filename, try to derive from content type
    if content_type:
        # Normalize content type
        mime_type = content_type.split(';')[0].strip().lower()

        # Reverse mapping from MIME type to extension
        mime_to_ext = {
            "application/pdf": ".pdf",
            "text/plain": ".txt",
            "text/csv": ".csv",
            "text/markdown": ".md",
            "text/html": ".html",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/msword": ".doc",
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/svg+xml": ".svg",
            "application/vnd.oasis.opendocument.text": ".odt",
            "text/xml": ".xml"
        }

        if mime_type in mime_to_ext:
            return mime_to_ext[mime_type]

    # Default to text extension if nothing else matches
    return ".txt"


async def get_file_extension_async(filename: str, content_type: Optional[str] = None) -> str:
    """
    Asynchronously get the appropriate file extension based on filename and content type.

    Args:
        filename: Original filename
        content_type: Optional content type

    Returns:
        File extension including the dot (e.g., ".pdf")
    """
    return await asyncio.to_thread(get_file_extension, filename, content_type)