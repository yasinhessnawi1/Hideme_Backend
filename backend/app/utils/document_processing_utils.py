"""
Centralized utility functions for document processing with optimized in-memory handling.

This module provides common utilities for processing documents in memory,
eliminating duplication across route handlers and ensuring consistent handling
with extended optimizations for all document formats.
"""
import io
import os
from typing import Dict, Any, Union

import pymupdf

from backend.app.utils.data_minimization import sanitize_document_metadata
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.factory.document_processing_factory import DocumentProcessingFactory, DocumentFormat
from backend.app.utils.logger import log_info, log_warning
from backend.app.utils.memory_management import memory_monitor


async def extract_text_data_in_memory(content_type: str, content: bytes) -> Dict[str, Any]:
    """
    Extract text and positional information from file content entirely in memory.
    Supports PDF, DOCX, and various text-based file formats with optimized processing.

    Args:
        content_type: MIME type of the file
        content: Raw file content as bytes

    Returns:
        Extracted data structure with text and positions
    """
    try:
        extraction_start = os.environ.get("EXTRACTION_DEBUG", "false").lower() == "true"
        if extraction_start:
            log_info(f"[EXTRACT] Starting extraction for {content_type}, size: {len(content)/1024:.1f}KB")

        # Apply memory pressure-aware processing approach
        current_memory_usage = memory_monitor.get_memory_usage()
        memory_efficient = current_memory_usage > 70  # Use more memory-efficient approach if usage is high

        if "pdf" in content_type.lower():
            # Process PDF directly in memory using BytesIO
            buffer = io.BytesIO(content)
            return await extract_pdf_in_memory(buffer, memory_efficient)

        elif "word" in content_type.lower() or "docx" in content_type.lower() or "doc" in content_type.lower():
            # Handle Word documents with optimized processing
            return await extract_docx_in_memory(content, memory_efficient)

        elif "text" in content_type.lower() or "csv" in content_type.lower() or "json" in content_type.lower():
            # Optimized text file handling
            return await extract_text_in_memory(content, content_type)

        elif "html" in content_type.lower() or "xml" in content_type.lower():
            # Specialized handling for markup documents
            return await extract_markup_in_memory(content, content_type)

        else:
            # Generic fallback for other formats
            return await extract_generic_in_memory(content, content_type)

    except Exception as e:
        # Enhanced error handling with specific error types
        error_type = f"{content_type}_extraction_error"
        SecurityAwareErrorHandler.log_processing_error(e, error_type, f"in_memory_extraction")

        # Return a structured error response instead of empty structure
        return {
            "pages": [],
            "error": {
                "type": error_type,
                "message": str(e),
                "content_type": content_type,
                "extractable": False
            }
        }


async def extract_pdf_in_memory(buffer: Union[io.BytesIO, bytes], memory_efficient: bool = False) -> Dict[str, Any]:
    """
    Extract text and positions from a PDF buffer with optimized memory usage.

    Args:
        buffer: PDF content as BytesIO buffer or bytes
        memory_efficient: Whether to use more memory-efficient approach

    Returns:
        Dictionary with extracted text and positions
    """
    if isinstance(buffer, bytes):
        buffer = io.BytesIO(buffer)

    extracted_data = {"pages": []}

    try:
        # Open PDF document from buffer
        pdf_document = pymupdf.open(stream=buffer, filetype="pdf")
        total_pages = len(pdf_document)

        # Process the document
        if memory_efficient and total_pages > 10:
            # Memory-efficient approach for large documents
            # Process pages in batches to reduce memory usage
            batch_size = 5
            for start_page in range(0, total_pages, batch_size):
                end_page = min(start_page + batch_size, total_pages)
                for page_num in range(start_page, end_page):
                    page = pdf_document[page_num]
                    page_data = extract_pdf_page(page, page_num)
                    if page_data["words"]:
                        extracted_data["pages"].append(page_data)

                # Force garbage collection between batches
                import gc
                gc.collect(0)
        else:
            # Standard approach for smaller documents
            for page_num in range(total_pages):
                page = pdf_document[page_num]
                page_data = extract_pdf_page(page, page_num)
                if page_data["words"]:
                    extracted_data["pages"].append(page_data)

        # Extract and sanitize metadata
        try:
            metadata = pdf_document.metadata
            if metadata:
                extracted_data["metadata"] = sanitize_document_metadata(metadata)

            # Add document statistics
            extracted_data["total_document_pages"] = total_pages
            extracted_data["content_pages"] = len(extracted_data["pages"])
            extracted_data["empty_pages"] = total_pages - len(extracted_data["pages"])
        except Exception as meta_error:
            SecurityAwareErrorHandler.log_processing_error(
                meta_error, "pdf_metadata_extraction", "in_memory"
            )

        pdf_document.close()

    except Exception as e:
        SecurityAwareErrorHandler.log_processing_error(e, "pdf_extraction", "in_memory")
        # Add error information to the result
        extracted_data["error"] = {
            "type": "pdf_extraction_error",
            "message": str(e)
        }

    return extracted_data


def extract_pdf_page(page: pymupdf.Page, page_num: int) -> Dict[str, Any]:
    """
    Extract text and positions from a single PDF page.

    Args:
        page: PyMuPDF page object
        page_num: Page number (0-based)

    Returns:
        Dictionary with page data
    """
    page_data = {
        "page": page_num + 1,  # Convert to 1-based page numbers
        "words": []
    }

    try:
        words = page.get_text("words")
        for word in words:
            x0, y0, x1, y1, text, *_ = word
            if text.strip():
                page_data["words"].append({
                    "text": text.strip(),
                    "x0": x0,
                    "y0": y0,
                    "x1": x1,
                    "y1": y1
                })
    except Exception as e:
        log_warning(f"Error extracting words from page {page_num + 1}: {str(e)}")

    return page_data


async def extract_docx_in_memory(content: bytes, memory_efficient: bool = False) -> Dict[str, Any]:
    """
    Extract text and positions from a DOCX document with optimized memory usage.

    Args:
        content: DOCX content as bytes
        memory_efficient: Whether to use more memory-efficient approach

    Returns:
        Dictionary with extracted text and positions
    """
    extracted_data = {"pages": []}

    try:
        # Handle Word documents
        # Since we don't have direct in-memory extraction for DOCX,
        # we'll use a temporary file approach with the DocumentProcessingFactory
        from backend.app.utils.secure_file_utils import SecureTempFileManager

        def process_docx(temp_path):
            # Create document extractor
            extractor = DocumentProcessingFactory.create_document_extractor(
                temp_path, DocumentFormat.DOCX
            )
            # Extract text
            result = extractor.extract_text()
            extractor.close()
            return result

        # Process with temp file
        extracted_data = await SecureTempFileManager.process_content_in_memory_async(
            content,
            processor=process_docx,
            use_path=True,
            extension=".docx"
        )

        # Add document format information
        if "metadata" not in extracted_data:
            extracted_data["metadata"] = {}
        extracted_data["metadata"]["document_format"] = "DOCX"

    except Exception as e:
        SecurityAwareErrorHandler.log_processing_error(e, "docx_extraction", "in_memory")
        # Add error information
        extracted_data["error"] = {
            "type": "docx_extraction_error",
            "message": str(e)
        }

    return extracted_data


async def extract_text_in_memory(content: bytes, content_type: str) -> Dict[str, Any]:
    """
    Extract text from plain text formats with position information.

    Args:
        content: Text content as bytes
        content_type: MIME type of the content

    Returns:
        Dictionary with extracted text and positions
    """
    extracted_data = {"pages": []}

    try:
        # Decode text content
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("latin-1", errors="replace")

        # Split into lines
        lines = text.split("\n")
        words = []

        y_position = 10.0  # Starting Y position
        x_position = 10.0  # Starting X position
        line_height = 15.0  # Line height

        # Process text with line breaks and position information
        for line_num, line in enumerate(lines):
            if not line.strip():
                y_position += line_height
                continue

            # Split line into words
            line_words = line.split()
            for word in line_words:
                if not word:
                    continue

                # Estimate word width (roughly 8 pixels per character)
                word_width = len(word) * 8

                words.append({
                    "text": word,
                    "x0": x_position,
                    "y0": y_position,
                    "x1": x_position + word_width,
                    "y1": y_position + line_height
                })

                # Move X position for next word
                x_position += word_width + 8  # Add space between words

            # Move to next line
            y_position += line_height
            x_position = 10.0  # Reset X position

        # Add page with words
        extracted_data["pages"].append({
            "page": 1,
            "words": words
        })

        # Add metadata
        extracted_data["metadata"] = {
            "document_format": content_type,
            "line_count": len(lines),
            "word_count": len(words)
        }

        # Add document statistics
        extracted_data["total_document_pages"] = 1
        extracted_data["content_pages"] = 1
        extracted_data["empty_pages"] = 0

    except Exception as e:
        SecurityAwareErrorHandler.log_processing_error(e, "text_extraction", "in_memory")
        # Add error information
        extracted_data["error"] = {
            "type": "text_extraction_error",
            "message": str(e),
            "content_type": content_type
        }

    return extracted_data


async def extract_markup_in_memory(content: bytes, content_type: str) -> Dict[str, Any]:
    """
    Extract text from HTML or XML with position information.

    Args:
        content: Markup content as bytes
        content_type: MIME type of the content

    Returns:
        Dictionary with extracted text and positions
    """
    extracted_data = {"pages": []}

    try:
        # Decode content
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("latin-1", errors="replace")

        # Strip HTML/XML tags
        import re
        text_content = re.sub(r'<[^>]+>', ' ', text)
        text_content = re.sub(r'\s+', ' ', text_content).strip()

        # Process extracted text
        words = []
        x_position = 10.0
        y_position = 10.0
        line_height = 15.0
        line_width = 800.0  # Assuming a standard page width

        # Split into words and add position information
        for word in text_content.split():
            if not word:
                continue

            # Estimate word width (roughly 8 pixels per character)
            word_width = len(word) * 8

            # Check if we need to wrap to next line
            if x_position + word_width > line_width:
                x_position = 10.0
                y_position += line_height

            words.append({
                "text": word,
                "x0": x_position,
                "y0": y_position,
                "x1": x_position + word_width,
                "y1": y_position + line_height
            })

            # Move X position for next word
            x_position += word_width + 8

        # Add page with words
        if words:
            extracted_data["pages"].append({
                "page": 1,
                "words": words
            })

        # Add metadata
        extracted_data["metadata"] = {
            "document_format": content_type,
            "word_count": len(words)
        }

        # Add document statistics
        extracted_data["total_document_pages"] = 1
        extracted_data["content_pages"] = len(extracted_data["pages"])
        extracted_data["empty_pages"] = 1 - len(extracted_data["pages"])

    except Exception as e:
        SecurityAwareErrorHandler.log_processing_error(e, "markup_extraction", "in_memory")
        # Add error information
        extracted_data["error"] = {
            "type": "markup_extraction_error",
            "message": str(e),
            "content_type": content_type
        }

    return extracted_data


async def extract_generic_in_memory(content: bytes, content_type: str) -> Dict[str, Any]:
    """
    Generic fallback for extracting text from unknown formats.

    Args:
        content: File content as bytes
        content_type: MIME type of the content

    Returns:
        Dictionary with extracted text and positions (if possible)
    """
    extracted_data = {"pages": []}

    try:
        # Try to decode as text first
        try:
            text = content.decode("utf-8", errors="ignore")
            # Check if it looks like text (high percentage of printable chars)
            printable_chars = sum(c.isprintable() for c in text)
            if printable_chars / len(text) > 0.8:
                # Process as text
                return await extract_text_in_memory(content, content_type)
        except Exception:
            pass

        # If we can't process as text, provide a placeholder
        extracted_data["pages"].append({
            "page": 1,
            "words": [{
                "text": f"[Content of type {content_type} cannot be processed as text]",
                "x0": 10,
                "y0": 10,
                "x1": 400,
                "y1": 30
            }]
        })

        # Add error information for unprocessable content
        extracted_data["error"] = {
            "type": "unsupported_format",
            "message": f"Content type {content_type} is not supported for text extraction",
            "content_type": content_type,
            "extractable": "False"
        }

    except Exception as e:
        SecurityAwareErrorHandler.log_processing_error(e, "generic_extraction", "in_memory")
        # Add error information
        extracted_data["error"] = {
            "type": "extraction_error",
            "message": str(e),
            "content_type": content_type
        }

    return extracted_data


async def process_file_content(file_content: bytes, content_type: str) -> Dict[str, Any]:
    """
    Process file content to extract text and position data with optimized memory usage.

    Args:
        file_content: Raw bytes of the file
        content_type: MIME type of the file

    Returns:
        Extracted text data with position information
    """
    return await extract_text_data_in_memory(content_type, file_content)


async def get_document_structure(content: bytes, content_type: str) -> Dict[str, Any]:
    """
    Analyze document structure without full text extraction.

    This is useful for quickly determining document properties
    without the overhead of full text extraction.

    Args:
        content: Raw bytes of the file
        content_type: MIME type of the file

    Returns:
        Document structure information
    """
    structure = {
        "content_type": content_type,
        "size_bytes": len(content),
        "extractable": True,
        "estimated_pages": 1,
        "format_details": {}
    }

    try:
        if "pdf" in content_type.lower():
            buffer = io.BytesIO(content)
            pdf_document = pymupdf.open(stream=buffer, filetype="pdf")
            structure["estimated_pages"] = len(pdf_document)
            structure["format_details"]["version"] = pdf_document.pdf_version
            structure["format_details"]["is_encrypted"] = pdf_document.is_encrypted
            structure["format_details"]["has_forms"] = pdf_document.is_form

            # Get basic metadata without extraction
            try:
                metadata = pdf_document.metadata
                structure["metadata"] = sanitize_document_metadata(metadata)
            except Exception:
                pass

            pdf_document.close()

        elif "docx" in content_type.lower() or "word" in content_type.lower():
            structure["format_details"]["type"] = "Microsoft Word Document"
            # We'd need python-docx for more details, but don't want to add dependencies

        elif "text" in content_type.lower():
            try:
                text = content.decode("utf-8", errors="ignore")
                lines = text.splitlines()
                structure["format_details"]["line_count"] = len(lines)
                structure["format_details"]["estimated_word_count"] = sum(len(line.split()) for line in lines)
            except Exception:
                pass

    except Exception as e:
        SecurityAwareErrorHandler.log_processing_error(e, "document_structure_analysis", content_type)
        structure["extractable"] = False
        structure["error"] = str(e)

    return structure


