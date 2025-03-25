"""
Centralized PDF document processing with enhanced batch capabilities and optimized synchronization.

This module provides comprehensive implementations for PDF text extraction and redaction with:
- Unified batch processing for both extraction and redaction
- Parallel processing support for improved performance
- Optimized synchronization using instance-level locks
- Enhanced memory management for large documents
- Consolidated image handling across operations
- Comprehensive error handling and GDPR compliance
"""
import io
import os
import time
from typing import Dict, Any, List, Union, BinaryIO, Iterator, Optional, Tuple

import pymupdf

from backend.app.domain.interfaces import DocumentExtractor, DocumentRedactor
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.helpers.parallel_helper import ParallelProcessingHelper
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.parallel.core import ParallelProcessingCore
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.synchronization_utils import TimeoutLock, LockPriority
from backend.app.utils.validation.data_minimization import sanitize_document_metadata


class PDFTextExtractor(DocumentExtractor):
    """
    Centralized service for extracting text with positional information from PDF documents.
    Supports both single and batch processing with optimized memory usage and synchronization.
    """
    # Timeouts
    DEFAULT_EXTRACTION_TIMEOUT = 60.0  # 60 seconds for extraction operations
    DEFAULT_BATCH_TIMEOUT = 300.0  # 300 seconds for batch operations

    def __init__(self, pdf_input: Union[str, pymupdf.Document, bytes, BinaryIO],
                 page_batch_size: int = 20):
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
        self.pdf_document = None

        # Instance-level lock for thread safety
        self._instance_lock = TimeoutLock(
            f"pdf_extractor_instance_lock_{id(self)}",
            priority=LockPriority.MEDIUM,
            timeout=self.DEFAULT_EXTRACTION_TIMEOUT
        )

        try:
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
        except Exception as e:
            # Use standardized error handling
            SecurityAwareErrorHandler.log_processing_error(
                e, "pdf_extractor_init", str(pdf_input) if isinstance(pdf_input, str) else "memory_buffer"
            )
            raise

    def extract_text(self, detect_images: bool = False, remove_images: bool = False) -> Dict[str, Any]:
        """
        Extract text from the PDF document, page by page, with positional information.

        Args:
            detect_images: Whether to detect and include image information
            remove_images: Whether to remove images from the document (only if detect_images is True)

        Returns:
            A dictionary with page-wise extracted data, excluding empty pages
        """
        extracted_data = {"pages": []}
        empty_pages = []
        total_pages = len(self.pdf_document)
        operation_id = os.path.basename(self.file_path) if isinstance(self.file_path, str) else "memory_document"

        # Track start time for performance metrics and GDPR compliance
        start_time = time.time()

        try:
            # Process with instance lock
            with self._instance_lock.acquire_timeout() as acquired:
                if not acquired:
                    log_error(f"[ERROR] Failed to acquire lock for extraction: {operation_id}")
                    return {"pages": [], "error": "Lock acquisition timeout", "timeout": True}

                log_info(f"[OK] Processing PDF extraction (operation_id: {operation_id})")

                # Determine if this is a large document and should use paged processing
                use_paged_processing = total_pages > 10

                if use_paged_processing:
                    # Process pages in batches
                    self._extract_pages_in_batches(extracted_data, empty_pages, detect_images, remove_images)
                else:
                    # Process all pages at once for smaller documents
                    for page_num in range(total_pages):
                        self._process_page(page_num, extracted_data, empty_pages, detect_images, remove_images)

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

        except TimeoutError as te:
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

            log_error(f"[ERROR] Timeout during PDF extraction: {str(te)}")
            return {"pages": [], "error": "PDF extraction timed out", "timeout": True}
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

        log_info(
            f"[OK] Text extraction completed successfully. Extracted {len(extracted_data['pages'])} pages with content."
        )
        return extracted_data

    def _extract_pages_in_batches(self, extracted_data: Dict[str, Any], empty_pages: List[int],
                                  detect_images: bool = False, remove_images: bool = False) -> None:
        """
        Extract text from pages in batches to reduce memory usage for large documents.

        Args:
            extracted_data: Dictionary to populate with extracted data
            empty_pages: List to populate with empty page numbers
            detect_images: Whether to detect and include image information
            remove_images: Whether to remove images from the document
        """
        total_pages = len(self.pdf_document)

        # Process pages in batches
        for batch_start in range(0, total_pages, self.page_batch_size):
            batch_end = min(batch_start + self.page_batch_size, total_pages)

            log_info(f"[OK] Processing PDF page batch {batch_start}-{batch_end - 1} of {total_pages}")

            # Process each page in the current batch with timeout handling
            batch_start_time = time.time()
            try:
                for page_num in range(batch_start, batch_end):
                    page_start_time = time.time()
                    max_page_time = 10.0  # 10 seconds timeout per page

                    # Check if we're spending too much time on this batch
                    elapsed_batch_time = time.time() - batch_start_time
                    if elapsed_batch_time > self.DEFAULT_EXTRACTION_TIMEOUT:
                        log_warning(
                            f"[WARNING] Batch processing is taking too long ({elapsed_batch_time:.2f}s), skipping remaining pages")
                        break

                    try:
                        self._process_page(page_num, extracted_data, empty_pages, detect_images, remove_images)

                        # Check if page processing took too long
                        page_time = time.time() - page_start_time
                        if page_time > max_page_time:
                            log_warning(
                                f"[WARNING] Page {page_num} processing took {page_time:.2f}s (exceeded {max_page_time}s threshold)")
                    except Exception as e:
                        log_error(f"[ERROR] Error processing page {page_num}: {str(e)}")
                        # Continue with other pages despite error
            except TimeoutError:
                log_error(f"[ERROR] Timeout during batch processing pages {batch_start}-{batch_end - 1}")
                # Continue with next batch

            # Free memory after processing each batch
            import gc
            gc.collect()

    def _process_page(self, page_num: int, extracted_data: Dict[str, Any], empty_pages: List[int],
                      detect_images: bool = False, remove_images: bool = False) -> None:
        """
        Process a single page of the PDF.

        Args:
            page_num: Page number (0-based index)
            extracted_data: Dictionary to populate with extracted data
            empty_pages: List to populate with empty page numbers
            detect_images: Whether to detect and include image information
            remove_images: Whether to remove images from the document
        """
        try:
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
            page_data = {
                "page": page_num + 1,
                "words": page_words
            }

            # Add image information if requested
            if detect_images:
                image_boxes = self._detect_images_on_page(page)

                if image_boxes:
                    page_data["images"] = image_boxes

                    # Remove images if requested
                    if remove_images:
                        self._remove_images_from_page(page, image_boxes)

            extracted_data["pages"].append(page_data)

        except Exception as e:
            log_error(f"[ERROR] Error in page {page_num} processing: {str(e)}")
            # Add empty page data to indicate error
            extracted_data["pages"].append({
                "page": page_num + 1,
                "words": [],
                "error": f"Error processing page: {str(e)}"
            })

    @staticmethod
    def _extract_page_words(page: pymupdf.Page) -> List[Dict[str, Any]]:
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

    @staticmethod
    def _detect_images_on_page(page: pymupdf.Page) -> List[Dict[str, Any]]:
        """
        Detects images in a given PDF page and returns their bounding boxes.

        Args:
            page: PyMuPDF Page object

        Returns:
            A list of dictionaries containing image bounding boxes.
        """
        image_boxes = []
        try:
            images = page.get_images(full=True)
            for img in images:
                xref = img[0]  # Image reference index
                rects = page.get_image_rects(xref)  # Get image bounding boxes

                for rect in rects:
                    image_boxes.append({
                        "x0": rect.x0,
                        "y0": rect.y0,
                        "x1": rect.x1,
                        "y1": rect.y1,
                        "xref": xref
                    })
        except Exception as e:
            SecurityAwareErrorHandler.log_processing_error(e, "pdf_image_extraction", f"page_{page.number}")
        return image_boxes

    @staticmethod
    def _remove_images_from_page(page: pymupdf.Page, image_boxes: List[Dict[str, Any]]) -> None:
        """
        Remove images from a page by adding redaction annotations and applying them.

        Args:
            page: PyMuPDF Page object
            image_boxes: List of image bounding boxes
        """
        try:
            for img in image_boxes:
                rect = pymupdf.Rect(img["x0"], img["y0"], img["x1"], img["y1"])
                page.add_redact_annot(rect, fill=(1, 1, 1))  # White box over image

            # Apply redactions to remove the images
            page.apply_redactions()

        except Exception as e:
            SecurityAwareErrorHandler.log_processing_error(e, "pdf_image_removal", f"page_{page.number}")

    def extract_pages_iterator(self) -> Iterator[Dict[str, Any]]:
        """
        Iterator for extracting pages one by one to minimize memory usage.
        Useful for streaming large documents.

        Yields:
            Dictionary with page data
        """
        total_pages = len(self.pdf_document)

        for page_num in range(total_pages):
            # Use timeout for each page extraction
            try:
                with self._instance_lock.acquire_timeout(timeout=10.0) as acquired:
                    if not acquired:
                        log_warning(f"[WARNING] Page iterator lock acquisition timed out for page {page_num}")
                        # Skip this page on timeout
                        continue

                    page = self.pdf_document[page_num]
                    page_words = self._extract_page_words(page)

                    if page_words:
                        yield {
                            "page": page_num + 1,
                            "words": page_words
                        }
            except Exception as e:
                log_error(f"[ERROR] Error in page iterator for page {page_num}: {str(e)}")
                # Yield empty page data to indicate error
                yield {
                    "page": page_num + 1,
                    "words": [],
                    "error": f"Error processing page: {str(e)}"
                }

    def extract_metadata(self) -> Dict[str, Any]:
        """
        Extract metadata from the PDF document with sanitization.

        Returns:
            Dictionary with sanitized document metadata
        """
        try:
            with self._instance_lock.acquire_timeout(timeout=10.0) as acquired:
                if not acquired:
                    log_warning("[WARNING] Metadata extraction lock acquisition timed out")
                    return {"error": "Metadata extraction timed out"}

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
        """Close the PDF document and free resources with improved error handling."""
        try:
            if self.pdf_document is not None:
                self.pdf_document.close()
                self.pdf_document = None
        except Exception as e:
            # Use standardized error handling but don't re-raise
            SecurityAwareErrorHandler.log_processing_error(
                e, "pdf_document_close", self.file_path
            )

    @staticmethod
    async def extract_batch_text(
            pdf_files: List[Union[str, bytes, BinaryIO]],
            max_workers: Optional[int] = None,
            detect_images: bool = False,
            remove_images: bool = False
    ) -> List[Tuple[int, Dict[str, Any]]]:
        """
        Extract text from multiple PDF files in parallel.

        Args:
            pdf_files: List of PDF files (paths, bytes, or file-like objects)
            max_workers: Maximum number of parallel workers (None for auto)
            detect_images: Whether to detect and include image information
            remove_images: Whether to remove images from the document

        Returns:
            List of tuples (index, extraction_result)
        """
        # Calculate optimal worker count if not specified
        if max_workers is None:
            max_workers = ParallelProcessingHelper.get_optimal_workers(len(pdf_files))

        log_info(f"[BATCH] Processing {len(pdf_files)} PDFs with {max_workers} workers")

        # Define a processing function for each PDF
        async def process_pdf(pdf_file: Union[str, bytes, BinaryIO]) -> Dict[str, Any]:
            try:
                extractor = PDFTextExtractor(pdf_file)
                result = extractor.extract_text(detect_images=detect_images, remove_images=remove_images)
                extractor.close()
                return result
            except Exception as e:
                file_id = pdf_file if isinstance(pdf_file, str) else "memory_buffer"
                SecurityAwareErrorHandler.log_processing_error(e, "batch_pdf_extraction", file_id)
                return {"pages": [], "error": str(e)}

        # Use parallel processing helper to process the batch
        results = await ParallelProcessingCore.process_in_parallel(
            pdf_files,
            lambda pdf: process_pdf(pdf),
            max_workers=max_workers
        )

        return results


class PDFRedactionService(DocumentRedactor):
    """
    Centralized service for applying redactions to PDF documents.
    Supports both single and batch redaction with optimized memory usage and synchronization.
    """
    # Enhanced timeout configuration
    DEFAULT_REDACTION_TIMEOUT = 120.0  # 2 minutes for redaction operations
    DEFAULT_BATCH_TIMEOUT = 600.0  # 10 minutes for batch operations
    DEFAULT_LOCK_TIMEOUT = 30.0  # 30 seconds for lock acquisition

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
            self.doc = None

            # Instance-level lock for thread safety
            self._instance_lock = TimeoutLock(
                f"pdf_redactor_instance_lock_{id(self)}",
                priority=LockPriority.MEDIUM,
                timeout=self.DEFAULT_LOCK_TIMEOUT
            )

            # Enhanced input type handling
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
            elif isinstance(pdf_input, io.BufferedReader):
                content = pdf_input.read()
                pdf_input.close()
                buffer = io.BytesIO(content)
                self.doc = pymupdf.open(stream=buffer, filetype="pdf")
                self.file_path = getattr(pdf_input, 'name', "buffered_reader")
            elif hasattr(pdf_input, 'read') and callable(pdf_input.read):
                # Input is a file-like object
                self.doc = pymupdf.open(stream=pdf_input, filetype="pdf")
                self.file_path = getattr(pdf_input, 'name', "file_object")
            else:
                raise ValueError(
                    "Invalid input! Expected a file path, PyMuPDF Document, bytes, BufferedReader, or file-like object."
                )

            log_info(f"[OK] Opened PDF file: {self.file_path}")
        except Exception as e:
            SecurityAwareErrorHandler.log_processing_error(
                e, "pdf_redaction_init", str(pdf_input) if isinstance(pdf_input, str) else "memory_buffer"
            )
            raise

    def apply_redactions(self, redaction_mapping: Dict[str, Any], output_path: str) -> str:
        """
        Apply redactions to the PDF based on the provided redaction mapping and save to a file.

        Args:
            redaction_mapping: Dictionary containing sensitive spans with bounding boxes.
            output_path: Path to save the redacted PDF.

        Returns:
            Path to the redacted document.
        """
        start_time = time.time()
        operation_id = os.path.basename(self.file_path) if isinstance(self.file_path, str) else "memory_document"
        sensitive_items_count = 0

        try:
            # Use instance lock with timeout
            with self._instance_lock.acquire_timeout(timeout=self.DEFAULT_LOCK_TIMEOUT) as acquired:
                if not acquired:
                    log_error(f"[ERROR] Failed to acquire lock for redaction: {operation_id}")
                    raise TimeoutError(f"Failed to acquire redaction lock after {self.DEFAULT_LOCK_TIMEOUT}s")

                log_info(f"[OK] Processing PDF redaction (operation_id: {operation_id})")

                # Count sensitive items for statistics
                sensitive_items_count = sum(
                    len(page.get("sensitive", []))
                    for page in redaction_mapping.get("pages", [])
                )

                # Apply redactions
                self._draw_redaction_boxes(redaction_mapping)

                # Apply additional security measures
                self._sanitize_document()

                # Save to output path
                self.doc.save(output_path)
                self.doc.close()

                processing_time = time.time() - start_time

                # Record processing for GDPR compliance
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
                return output_path

        except TimeoutError as te:
            processing_time = time.time() - start_time
            record_keeper.record_processing(
                operation_type="pdf_redaction_timeout",
                document_type="PDF",
                entity_types_processed=[],
                processing_time=processing_time,
                file_count=1,
                entity_count=0,
                success=False
            )
            log_error(f"[ERROR] Redaction timeout: {str(te)}")
            raise
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
        start_time = time.time()
        operation_id = f"memory_redaction_{time.time()}"
        sensitive_items_count = 0

        try:
            # Use instance lock with timeout
            with self._instance_lock.acquire_timeout(timeout=self.DEFAULT_LOCK_TIMEOUT) as acquired:
                if not acquired:
                    log_error(f"[ERROR] Failed to acquire lock for memory redaction: {operation_id}")
                    raise TimeoutError(f"Failed to acquire memory redaction lock after {self.DEFAULT_LOCK_TIMEOUT}s")

                log_info(f"[OK] Processing PDF memory redaction (operation_id: {operation_id})")

                # Count sensitive items for statistics
                sensitive_items_count = sum(
                    len(page.get("sensitive", []))
                    for page in redaction_mapping.get("pages", [])
                )

                # Apply redactions
                self._draw_redaction_boxes(redaction_mapping)

                # Apply additional security measures
                self._sanitize_document()

                # Save to memory buffer
                output_buffer = io.BytesIO()
                self.doc.save(output_buffer)
                self.doc.close()

                # Get bytes from buffer
                output_buffer.seek(0)
                redacted_content = output_buffer.getvalue()

                processing_time = time.time() - start_time

                # Record processing for GDPR compliance
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

                return redacted_content

        except TimeoutError as te:
            processing_time = time.time() - start_time
            record_keeper.record_processing(
                operation_type="pdf_memory_redaction_timeout",
                document_type="PDF",
                entity_types_processed=[],
                processing_time=processing_time,
                file_count=1,
                entity_count=0,
                success=False
            )
            log_error(f"[ERROR] Memory redaction timeout: {str(te)}")
            raise
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
        use_batched_processing = len(page_numbers) > 10  # Arbitrary threshold

        # Process the mapping
        try:
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
                self._process_all_redaction_pages(redaction_mapping, total_pages)
        except Exception as e:
            log_error(f"[ERROR] Error while drawing redaction boxes: {str(e)}")
            raise

    def _process_all_redaction_pages(self, redaction_mapping: Dict[str, Any], total_pages: int) -> None:
        """
        Process all pages for redaction at once.

        Args:
            redaction_mapping: Dictionary with redaction information
            total_pages: Total number of pages in the document
        """
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

                # Detect and redact images if requested
                if page_info.get("redact_images", False):
                    image_boxes = PDFTextExtractor._detect_images_on_page(page)
                    if image_boxes:
                        for img in image_boxes:
                            rect = pymupdf.Rect(img["x0"], img["y0"], img["x1"], img["y1"])
                            page.add_redact_annot(rect, fill=(0, 0, 0))  # Black box over image

                # Apply redactions (both text and images)
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
        batch_start_time = time.time()
        max_batch_time = 60.0  # 60 seconds max per batch

        for page_num in page_numbers:
            # Check if we're exceeding batch timeout
            current_batch_time = time.time() - batch_start_time
            if current_batch_time > max_batch_time:
                log_warning(
                    f"[WARNING] Batch processing timeout reached after {current_batch_time:.2f}s, skipping remaining pages")
                break

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

                # Detect and redact images if requested
                if page_info.get("redact_images", False):
                    image_boxes = PDFTextExtractor._detect_images_on_page(page)
                    if image_boxes:
                        for img in image_boxes:
                            rect = pymupdf.Rect(img["x0"], img["y0"], img["x1"], img["y1"])
                            page.add_redact_annot(rect, fill=(0, 0, 0))  # Black box over image

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
                    if annot.type[0] != 8:  # Don't delete redaction annotations (type 8)
                        page.delete_annot(annot)

            # Remove embedded files, JS, and extra objects
            self.doc.scrub()

        except Exception as e:
            SecurityAwareErrorHandler.log_processing_error(
                e, "pdf_document_sanitize", self.file_path
            )

    def close(self) -> None:
        """Close the document and free resources with improved error handling."""
        try:
            if self.doc is not None:
                self.doc.close() if not self.doc.is_closed else None
                self.doc = None
        except Exception as e:
            # Use standardized error handling but don't re-raise
            SecurityAwareErrorHandler.log_processing_error(
                e, "pdf_document_close", self.file_path
            )

    @staticmethod
    async def redact_batch(
            pdf_files: List[Union[str, bytes, BinaryIO]],
            redaction_mappings: List[Dict[str, Any]],
            output_paths: List[str],
            max_workers: Optional[int] = None
    ) -> List[Tuple[int, Dict[str, Any]]]:
        """
        Apply redactions to multiple PDF files in parallel.

        Args:
            pdf_files: List of PDF files (paths, bytes, or file-like objects)
            redaction_mappings: List of redaction mappings corresponding to the files
            output_paths: List of output paths for the redacted files
            max_workers: Maximum number of parallel workers (None for auto)

        Returns:
            List of tuples (index, result_dict)
        """
        if len(pdf_files) != len(redaction_mappings) or len(pdf_files) != len(output_paths):
            raise ValueError("The lengths of pdf_files, redaction_mappings, and output_paths must be the same")

        # Calculate optimal worker count if not specified
        if max_workers is None:
            max_workers = ParallelProcessingHelper.get_optimal_workers(len(pdf_files))

        log_info(f"[BATCH] Redacting {len(pdf_files)} PDFs with {max_workers} workers")

        # Create a list of processing items
        process_items = [
            (pdf_files[i], redaction_mappings[i], output_paths[i])
            for i in range(len(pdf_files))
        ]

        # Define a processing function for each PDF
        async def process_redaction(item: Tuple[Union[str, bytes, BinaryIO], Dict[str, Any], str]) -> Dict[str, Any]:
            pdf_file, redaction_mapping, output_path = item
            try:
                redactor = PDFRedactionService(pdf_file)
                result_path = redactor.apply_redactions(redaction_mapping, output_path)
                redactor.close()
                return {
                    "status": "success",
                    "output_path": result_path,
                    "entities_redacted": sum(
                        len(page.get("sensitive", []))
                        for page in redaction_mapping.get("pages", [])
                    )
                }
            except Exception as e:
                file_id = pdf_file if isinstance(pdf_file, str) else "memory_buffer"
                SecurityAwareErrorHandler.log_processing_error(e, "batch_pdf_redaction", file_id)
                return {
                    "status": "error",
                    "error": str(e)
                }

        # Use parallel processing helper to process the batch
        results = await ParallelProcessingCore.process_in_parallel(
            process_items,
            lambda item: process_redaction(item),
            max_workers=max_workers
        )

        return results


async def extraction_processor(content):
    # Check if content is a file-like object or bytes
    if hasattr(content, 'read'):
        # It's a file-like object, use it directly
        extractor = PDFTextExtractor(content)
        extracted_data = extractor.extract_text()
        extractor.close()
    else:
        # It's bytes, create a buffer
        buffer = io.BytesIO(content)
        extractor = PDFTextExtractor(buffer)
        extracted_data = extractor.extract_text()
        extractor.close()
    return extracted_data

