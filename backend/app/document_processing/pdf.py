"""
Optimized PDF document processing implementation that eliminates unnecessary file operations.

This module provides implementations for PDF text extraction and redaction with
improved memory efficiency by supporting direct memory buffer processing,
eliminating unnecessary temporary files, and adding pagination support for large documents.
"""
import os
import io
from typing import Dict, Any, List, Union, BinaryIO, Iterator

import pymupdf

from backend.app.domain.interfaces import DocumentExtractor, DocumentRedactor
from backend.app.utils.logger import log_info, log_warning
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.data_minimization import sanitize_document_metadata
from backend.app.utils.processing_records import record_keeper
from backend.app.utils.secure_logging import log_sensitive_operation


class PDFTextExtractor(DocumentExtractor):
    """
    Optimized service for extracting text with positional information from PDF documents,
    with support for in-memory processing to eliminate unnecessary file operations and
    pagination support for large documents.
    """

    def __init__(self, pdf_input: Union[str, pymupdf.Document, bytes, BinaryIO],
                 page_batch_size: int = 5):
        """
        Initialize PDFTextExtractor with enhanced flexibility for input types.

        Args:
            pdf_input: Input PDF as one of:
                - File path to a PDF (str)
                - PyMuPDF Document instance
                - PDF content as bytes
                - File-like object with PDF content
            page_batch_size: Number of pages to process in a batch for large documents
        """
        self.file_path = None
        self.page_batch_size = page_batch_size

        if isinstance(pdf_input, str):
            # Input is a file path
            self.pdf_document = pymupdf.open(pdf_input)
            self.file_path = pdf_input
        elif isinstance(pdf_input, pymupdf.Document):
            # Input is already a PyMuPDF Document
            self.pdf_document = pdf_input
            self.file_path = "memory_document"
        elif isinstance(pdf_input, bytes):
            # Input is PDF content as bytes
            buffer = io.BytesIO(pdf_input)
            self.pdf_document = pymupdf.open(stream=buffer, filetype="pdf")
            self.file_path = "memory_buffer"
        elif hasattr(pdf_input, 'read') and callable(pdf_input.read):
            # Input is a file-like object
            self.pdf_document = pymupdf.open(stream=pdf_input, filetype="pdf")
            self.file_path = getattr(pdf_input, 'name', "file_object")
        else:
            raise ValueError("Invalid input! Expected a file path, PyMuPDF Document, bytes, or file-like object.")

    def extract_text_with_positions(self) -> Dict[str, Any]:
        """
        Extract text from the PDF document, page by page, with positional information.
        Automatically filters out empty pages and applies GDPR compliance measures.

        For large documents, processes pages in batches to reduce memory usage.

        Returns:
            A dictionary with page-wise extracted data, excluding empty pages
        """
        extracted_data = {"pages": []}
        empty_pages = []
        total_pages = len(self.pdf_document)
        operation_id = os.path.basename(self.file_path) if isinstance(self.file_path, str) else "memory_document"

        # Track start time for performance metrics and GDPR compliance
        import time
        start_time = time.time()

        try:
            # Determine if this is a large document and should use paged processing
            use_paged_processing = total_pages > 20  # Arbitrary threshold for demonstration

            if use_paged_processing:
                # Process pages in batches
                self._extract_pages_in_batches(extracted_data, empty_pages)
            else:
                # Process all pages at once for smaller documents
                for page_num in range(total_pages):
                    self._process_page(page_num, extracted_data, empty_pages)

            # Log summary of empty pages using secure logging
            if empty_pages:
                log_info(f"[OK] Skipped {len(empty_pages)} empty pages")
                log_sensitive_operation(
                    "PDF Empty Page Detection",
                    len(empty_pages),
                    0.0,
                    total_pages=total_pages,
                    operation_id=operation_id
                )

            # Add metadata about empty pages and document statistics
            extracted_data["total_document_pages"] = total_pages
            extracted_data["empty_pages"] = empty_pages
            extracted_data["content_pages"] = total_pages - len(empty_pages)

            # Add document metadata (with sanitization)
            try:
                metadata = self.pdf_document.metadata
                if metadata:
                    extracted_data["metadata"] = sanitize_document_metadata(metadata)
            except Exception as meta_error:
                # Use standardized error handling
                SecurityAwareErrorHandler.log_processing_error(
                    meta_error, "pdf_metadata_extraction", self.file_path
                )

            # Calculate process time for GDPR compliance
            processing_time = time.time() - start_time

            # Record processing for GDPR compliance
            record_keeper.record_processing(
                operation_type="pdf_text_extraction",
                document_type="PDF",
                entity_types_processed=[],
                processing_time=processing_time,
                file_count=1,
                entity_count=0,
                success=True
            )

            # Log performance metrics without sensitive information
            log_sensitive_operation(
                "PDF Text Extraction",
                0,  # No entities for extraction
                processing_time,
                pages=len(extracted_data["pages"]),
                total_pages=total_pages,
                operation_id=operation_id
            )

        except Exception as e:
            # Record failed processing for GDPR compliance
            processing_time = time.time() - start_time
            record_keeper.record_processing(
                operation_type="pdf_text_extraction",
                document_type="PDF",
                entity_types_processed=[],
                processing_time=processing_time,
                file_count=1,
                entity_count=0,
                success=False
            )

            # Use standardized error handling
            SecurityAwareErrorHandler.log_processing_error(
                e, "pdf_text_extraction", self.file_path
            )
            return {"pages": [], "error": str(e)}

        log_info(
            f"[OK] Text extraction completed successfully. Extracted {len(extracted_data['pages'])} pages with content."
        )
        return extracted_data

    def _extract_pages_in_batches(self, extracted_data: Dict[str, Any], empty_pages: List[int]) -> None:
        """
        Extract text from pages in batches to reduce memory usage for large documents.

        Args:
            extracted_data: Dictionary to populate with extracted data
            empty_pages: List to populate with empty page numbers
        """
        total_pages = len(self.pdf_document)

        # Process pages in batches
        for batch_start in range(0, total_pages, self.page_batch_size):
            batch_end = min(batch_start + self.page_batch_size, total_pages)

            log_info(f"[OK] Processing PDF page batch {batch_start}-{batch_end-1} of {total_pages}")

            # Process each page in the current batch
            for page_num in range(batch_start, batch_end):
                self._process_page(page_num, extracted_data, empty_pages)

            # Free memory after processing each batch
            import gc
            gc.collect()

    def _process_page(self, page_num: int, extracted_data: Dict[str, Any], empty_pages: List[int]) -> None:
        """
        Process a single page of the PDF.

        Args:
            page_num: Page number (0-based index)
            extracted_data: Dictionary to populate with extracted data
            empty_pages: List to populate with empty page numbers
        """
        page = self.pdf_document[page_num]
        log_info(f"[OK] Processing page {page_num + 1}")

        # Extract words with positions
        page_words = self._extract_page_words(page)

        # Check if page is empty (no words with content)
        if not page_words:
            empty_pages.append(page_num + 1)
            log_info(f"[OK] Skipping empty page {page_num + 1}")
            return

        # Add page data to result
        extracted_data["pages"].append({
            "page": page_num + 1,
            "words": page_words
        })

    def _extract_page_words(self, page: pymupdf.Page) -> List[Dict[str, Any]]:
        """
        Extract words with their positions from a PDF page.
        Filters out words that contain only whitespace.

        Args:
            page: PyMuPDF Page object

        Returns:
            List of word dictionaries with text and position information
        """
        page_words = []
        try:
            # get_text("words") returns a list of tuples:
            # (x0, y0, x1, y1, word, block_no, line_no, word_no)
            words = page.get_text("words")

            for word in words:
                x0, y0, x1, y1, text, *_ = word
                if text.strip():  # Only include words with non-whitespace content
                    page_words.append({
                        "text": text.strip(),
                        "x0": x0,
                        "y0": y0,
                        "x1": x1,
                        "y1": y1
                    })
        except Exception as e:
            # Use standardized error handling
            SecurityAwareErrorHandler.log_processing_error(
                e, "pdf_page_word_extraction", f"page_{page.number}"
            )

        return page_words

    def extract_pages_iterator(self) -> Iterator[Dict[str, Any]]:
        """
        Iterator for extracting pages one by one to minimize memory usage.
        Useful for streaming large documents.

        Yields:
            Dictionary with page data
        """
        total_pages = len(self.pdf_document)

        for page_num in range(total_pages):
            page = self.pdf_document[page_num]
            page_words = self._extract_page_words(page)

            if page_words:
                yield {
                    "page": page_num + 1,
                    "words": page_words
                }

    def extract_metadata(self) -> Dict[str, Any]:
        """
        Extract metadata from the PDF document with sanitization.

        Returns:
            Dictionary with sanitized document metadata
        """
        try:
            metadata = self.pdf_document.metadata
            if metadata:
                # Apply sanitization to remove potentially sensitive information
                sanitized = sanitize_document_metadata(metadata)

                # Add additional safe metadata
                sanitized.update({
                    "page_count": len(self.pdf_document),
                    "version": self.pdf_document.pdf_version,
                    "is_encrypted": self.pdf_document.is_encrypted,
                    "is_form": self.pdf_document.is_form,
                    "has_xml_metadata": self.pdf_document.has_xml_metadata(),
                })

                return sanitized
            return {}
        except Exception as e:
            # Use standardized error handling
            SecurityAwareErrorHandler.log_processing_error(
                e, "pdf_metadata_extraction", self.file_path
            )
            return {}

    def close(self) -> None:
        """Close the PDF document and free resources."""
        try:
            self.pdf_document.close()
        except Exception as e:
            # Use standardized error handling
            SecurityAwareErrorHandler.log_processing_error(
                e, "pdf_document_close", self.file_path
            )


class PDFRedactionService(DocumentRedactor):
    """
    Optimized service for applying redactions to PDF documents with support
    for in-memory processing to eliminate unnecessary file operations.
    """

    def __init__(self, pdf_input: Union[str, pymupdf.Document, bytes, BinaryIO],
                 page_batch_size: int = 5):
        """
        Initialize PDFRedactionService with enhanced flexibility for input types.

        Args:
            pdf_input: Input PDF as one of:
                - File path to a PDF (str)
                - PyMuPDF Document instance
                - PDF content as bytes
                - File-like object with PDF content
            page_batch_size: Number of pages to process in a batch for large documents
        """
        try:
            self.file_path = None
            self.page_batch_size = page_batch_size

            if isinstance(pdf_input, str):
                # Input is a file path
                self.doc = pymupdf.open(pdf_input)
                self.file_path = pdf_input
            elif isinstance(pdf_input, pymupdf.Document):
                # Input is already a PyMuPDF Document
                self.doc = pdf_input
                self.file_path = "memory_document"
            elif isinstance(pdf_input, bytes):
                # Input is PDF content as bytes
                buffer = io.BytesIO(pdf_input)
                self.doc = pymupdf.open(stream=buffer, filetype="pdf")
                self.file_path = "memory_buffer"
            elif hasattr(pdf_input, 'read') and callable(pdf_input.read):
                # Input is a file-like object
                self.doc = pymupdf.open(stream=pdf_input, filetype="pdf")
                self.file_path = getattr(pdf_input, 'name', "file_object")
            else:
                raise ValueError("Invalid input! Expected a file path, PyMuPDF Document, bytes, or file-like object.")

            log_info(f"[OK] Opened PDF file: {self.file_path}")
        except Exception as e:
            # Use standardized error handling
            SecurityAwareErrorHandler.log_processing_error(
                e, "pdf_redaction_init", str(pdf_input) if isinstance(pdf_input, str) else "memory_buffer"
            )
            raise

    def _apply_redactions_common(self, redaction_mapping: Dict[str, Any], save_callback, start_time: float) -> (Any, int, float):
        """
        Common redaction logic that applies redaction boxes and security sanitization,
        then saves the document via the provided callback.

        Args:
            redaction_mapping: Dictionary containing sensitive spans with bounding boxes.
            save_callback: A callback function that handles saving the document and returns the result.
            start_time: The starting time of the operation for processing time calculation.

        Returns:
            A tuple of (result, sensitive_items_count, processing_time).
        """
        import time
        # Apply redactions by drawing redaction boxes and additional security measures
        self._draw_redaction_boxes(redaction_mapping)
        self._sanitize_document()

        # Save the document using the provided callback (could be to file or memory)
        result = save_callback()
        self.doc.close()

        # Count sensitive items based on the mapping provided
        sensitive_items_count = sum(
            len(page.get("sensitive", []))
            for page in redaction_mapping.get("pages", [])
        )
        processing_time = time.time() - start_time

        return result, sensitive_items_count, processing_time

    def apply_redactions(self, redaction_mapping: Dict[str, Any], output_path: str) -> str:
        """
        Apply redactions to the PDF based on the provided redaction mapping and save to a file.

        Args:
            redaction_mapping: Dictionary containing sensitive spans with bounding boxes.
            output_path: Path to save the redacted PDF.

        Returns:
            Path to the redacted document.
        """
        import time
        start_time = time.time()
        operation_id = os.path.basename(self.file_path) if isinstance(self.file_path, str) else "memory_document"

        try:
            def save_to_file():
                self.doc.save(output_path)
                return output_path

            result, sensitive_items_count, processing_time = self._apply_redactions_common(
                redaction_mapping, save_to_file, start_time
            )

            record_keeper.record_processing(
                operation_type="pdf_redaction",
                document_type="PDF",
                entity_types_processed=[],
                processing_time=processing_time,
                file_count=1,
                entity_count=sensitive_items_count,
                success=True
            )

            log_sensitive_operation(
                "PDF Redaction",
                sensitive_items_count,
                processing_time,
                file_path=self.file_path,
                operation_id=operation_id
            )

            log_info(f"[OK] Redacted PDF saved as {output_path}")
            return result

        except Exception as e:
            processing_time = time.time() - start_time
            record_keeper.record_processing(
                operation_type="pdf_redaction",
                document_type="PDF",
                entity_types_processed=[],
                processing_time=processing_time,
                file_count=1,
                entity_count=0,
                success=False
            )
            SecurityAwareErrorHandler.log_processing_error(
                e, "pdf_redaction", self.file_path
            )
            raise

    def apply_redactions_to_memory(self, redaction_mapping: Dict[str, Any]) -> bytes:
        """
        Apply redactions to the PDF and return the result as bytes without saving to a file.

        This method processes the PDF entirely in memory, eliminating disk I/O for improved
        performance and security. It applies redactions and sanitization to the document
        and returns the modified PDF as bytes.

        Performance characteristics:
        - Memory usage: Scales with PDF size (roughly 1-5x the original size during processing)
        - CPU usage: Increases with the number of redactions
        - Time complexity: O(p + r) where p is page count and r is redaction count
        - Space complexity: O(n) where n is the PDF file size

        GDPR considerations:
        - No temporary files are created, reducing potential data exposure
        - Document metadata is sanitized to remove potential PII
        - Processing is tracked for compliance reporting

        Args:
            redaction_mapping: Dictionary containing sensitive spans with bounding boxes.
                               Format: {"pages": [{"page": page_num, "sensitive": [items]}]}

        Returns:
            Redacted PDF content as bytes.
        """
        import time
        start_time = time.time()
        operation_id = f"memory_redaction_{time.time()}"

        try:
            def save_to_memory():
                output_buffer = io.BytesIO()
                self.doc.save(output_buffer)
                output_buffer.seek(0)
                return output_buffer.getvalue()

            result, sensitive_items_count, processing_time = self._apply_redactions_common(
                redaction_mapping, save_to_memory, start_time
            )

            record_keeper.record_processing(
                operation_type="pdf_memory_redaction",
                document_type="PDF",
                entity_types_processed=[],
                processing_time=processing_time,
                file_count=1,
                entity_count=sensitive_items_count,
                success=True
            )

            log_sensitive_operation(
                "PDF Memory Redaction",
                sensitive_items_count,
                processing_time,
                operation_id=operation_id
            )

            return result

        except Exception as e:
            processing_time = time.time() - start_time
            record_keeper.record_processing(
                operation_type="pdf_memory_redaction",
                document_type="PDF",
                entity_types_processed=[],
                processing_time=processing_time,
                file_count=1,
                entity_count=0,
                success=False
            )
            SecurityAwareErrorHandler.log_processing_error(
                e, "pdf_memory_redaction", self.file_path
            )
            raise

    def _draw_redaction_boxes(self, redaction_mapping: Dict[str, Any]) -> None:
        """
        Draw redaction boxes on the PDF document based on the provided mapping.
        For large documents, processes in batches to reduce memory usage.

        Args:
            redaction_mapping: Dictionary containing sensitive spans with bounding boxes.
        """
        total_pages = len(self.doc)

        # Get all page numbers that need processing
        page_numbers = set()
        for page_info in redaction_mapping.get("pages", []):
            page_num = page_info.get("page")
            if page_num is not None:
                page_numbers.add(page_num)

        # Convert to sorted list
        page_numbers = sorted(list(page_numbers))

        # Determine if this is a large document and should use batched processing
        use_batched_processing = len(page_numbers) > 10  # Arbitrary threshold for demonstration

        if use_batched_processing:
            # Process pages in batches
            for batch_start in range(0, len(page_numbers), self.page_batch_size):
                batch_end = min(batch_start + self.page_batch_size, len(page_numbers))
                batch_page_numbers = page_numbers[batch_start:batch_end]

                log_info(f"[OK] Processing redaction batch for pages {batch_page_numbers}")

                # Process each page in the current batch
                self._process_redaction_pages_batch(redaction_mapping, batch_page_numbers, total_pages)

                # Free memory after processing each batch
                import gc
                gc.collect()
        else:
            # Process all pages at once
            for page_info in redaction_mapping.get("pages", []):
                page_num = page_info.get("page")
                sensitive_items = page_info.get("sensitive", [])

                if not sensitive_items:
                    log_info(f"[OK] No sensitive items found on page {page_num}.")
                    continue

                # Check that the page number exists in the document
                if page_num < 1 or page_num > total_pages:
                    log_warning(
                        f"[WARNING] Page number {page_num} is out of range for document with {total_pages} pages. Skipping."
                    )
                    continue

                try:
                    # PyMuPDF pages are 0-indexed
                    page = self.doc[page_num - 1]

                    for item in sensitive_items:
                        self._process_sensitive_item(page, item, page_num)

                    # Apply redactions on the page
                    page.apply_redactions()

                except Exception as e:
                    SecurityAwareErrorHandler.log_processing_error(
                        e, "pdf_redaction_page", f"{self.file_path}:page_{page_num}"
                    )
                    continue

    def _process_redaction_pages_batch(self, redaction_mapping: Dict[str, Any],
                                      page_numbers: List[int], total_pages: int) -> None:
        """
        Process a batch of pages for redaction to optimize memory usage.

        Args:
            redaction_mapping: Dictionary with redaction information
            page_numbers: List of page numbers to process in this batch
            total_pages: Total number of pages in the document
        """
        # Create a page mapping for quick lookup
        page_mapping = {}
        for page_info in redaction_mapping.get("pages", []):
            page_num = page_info.get("page")
            if page_num in page_numbers:
                page_mapping[page_num] = page_info

        # Process each page in the batch
        for page_num in page_numbers:
            page_info = page_mapping.get(page_num)
            if page_info is None:
                continue

            sensitive_items = page_info.get("sensitive", [])
            if not sensitive_items:
                log_info(f"[OK] No sensitive items found on page {page_num}.")
                continue

            # Check page number is valid
            if page_num < 1 or page_num > total_pages:
                log_warning(
                    f"[WARNING] Page number {page_num} is out of range for document with {total_pages} pages. Skipping."
                )
                continue

            try:
                # PyMuPDF pages are 0-indexed
                page = self.doc[page_num - 1]

                for item in sensitive_items:
                    self._process_sensitive_item(page, item, page_num)

                # Apply redactions on the page
                page.apply_redactions()

            except Exception as e:
                SecurityAwareErrorHandler.log_processing_error(
                    e, "pdf_redaction_page", f"{self.file_path}:page_{page_num}"
                )

    def _process_sensitive_item(self, page: pymupdf.Page, item: Dict[str, Any], page_num: int) -> None:
        """
        Process a single sensitive item and create redaction annotations.

        Args:
            page: PyMuPDF Page object.
            item: Sensitive item dictionary.
            page_num: Page number (1-indexed).
        """
        try:
            # If the item contains a list of boxes, process them all
            if "boxes" in item and isinstance(item["boxes"], list):
                for box in item["boxes"]:
                    rect = pymupdf.Rect(box["x0"], box["y0"], box["x1"], box["y1"])
                    # Add a redaction annotation with a black fill
                    page.add_redact_annot(rect, fill=(0, 0, 0), text=item.get("entity_type"))
                    log_info(f"[OK] Redacting entity {item.get('entity_type')} on page {page_num}")

            # Handle single bbox case (fallback)
            elif "bbox" in item:
                bbox = item["bbox"]
                rect = pymupdf.Rect(bbox["x0"], bbox["y0"], bbox["x1"], bbox["y1"])
                page.add_redact_annot(rect, fill=(0, 0, 0))

        except Exception as e:
            SecurityAwareErrorHandler.log_processing_error(
                e, "pdf_process_sensitive_item", f"{self.file_path}:page_{page_num}"
            )

    def _sanitize_document(self) -> None:
        """
        Apply additional security measures to the document:
        - Remove metadata
        - Remove hidden content and annotations
        - Remove embedded files, JavaScript, and extra objects
        """
        try:
            # Remove metadata
            self.doc.set_metadata({})

            # Remove hidden content and annotations
            for page in self.doc:
                page.clean_contents()
                for annot in page.annots() or []:
                    page.delete_annot(annot)

            # Remove embedded files, JS, and extra objects
            self.doc.scrub()

        except Exception as e:
            SecurityAwareErrorHandler.log_processing_error(
                e, "pdf_document_sanitize", self.file_path
            )