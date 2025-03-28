"""
Centralized PDF document processing with enhanced batch capabilities and optimized synchronization.

This module provides comprehensive implementations for PDF text extraction with:
- Unified batch processing for extraction
- Parallel processing support for improved performance
- Optimized synchronization using instance-level locks
- Enhanced memory management for large documents
- Comprehensive error handling and GDPR compliance
"""
import io
import os
import time
from typing import Dict, Any, List, Union, BinaryIO, Optional, Tuple

import pymupdf

from backend.app.domain.interfaces import DocumentExtractor
from backend.app.utils.error_handling import SecurityAwareErrorHandler
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
    DEFAULT_BATCH_TIMEOUT = 300.0        # 300 seconds for batch operations

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

    def extract_text(self) -> Dict[str, Any]:
        """
        Extract text from the PDF document, page by page, with positional information.

        Returns:
            A dictionary with page-wise extracted data, excluding empty pages.
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

    def _extract_pages_in_batches(self, extracted_data: Dict[str, Any], empty_pages: List[int]) -> None:
        """
        Extract text from pages in batches to reduce memory usage for large documents.

        Args:
            extracted_data: Dictionary to populate with extracted data.
            empty_pages: List to populate with empty page numbers.
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
                            f"[WARNING] Batch processing is taking too long ({elapsed_batch_time:.2f}s), skipping remaining pages"
                        )
                        break

                    try:
                        self._process_page(page_num, extracted_data, empty_pages)

                        # Check if page processing took too long
                        page_time = time.time() - page_start_time
                        if page_time > max_page_time:
                            log_warning(
                                f"[WARNING] Page {page_num} processing took {page_time:.2f}s (exceeded {max_page_time}s threshold)"
                            )
                    except Exception as e:
                        log_error(f"[ERROR] Error processing page {page_num}: {str(e)}")
                        # Continue with other pages despite error
            except TimeoutError:
                log_error(f"[ERROR] Timeout during batch processing pages {batch_start}-{batch_end - 1}")
                # Continue with next batch

            # Free memory after processing each batch
            import gc
            gc.collect()

    def _process_page(self, page_num: int, extracted_data: Dict[str, Any], empty_pages: List[int]) -> None:
        """
        Process a single page of the PDF.

        Args:
            page_num: Page number (0-based index)
            extracted_data: Dictionary to populate with extracted data.
            empty_pages: List to populate with empty page numbers.
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
    def extract_images_on_page(page: pymupdf.Page) -> List[Dict[str, Any]]:
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
            max_workers: Optional[int] = None
    ) -> List[Tuple[int, Dict[str, Any]]]:
        """
        Extract text from multiple PDF files in parallel.

        Args:
            pdf_files: List of PDF files (paths, bytes, or file-like objects)
            max_workers: Maximum number of parallel workers (None for auto)

        Returns:
            List of tuples (index, extraction_result)
        """
        # Calculate optimal worker count if not specified
        if max_workers is None:
            max_workers = ParallelProcessingCore.get_optimal_workers(len(pdf_files))

        log_info(f"[BATCH] Processing {len(pdf_files)} PDFs with {max_workers} workers")

        # Define a processing function for each PDF
        async def process_pdf(pdf_file: Union[str, bytes, BinaryIO]) -> Dict[str, Any]:
            try:
                extractor = PDFTextExtractor(pdf_file)
                result = extractor.extract_text()
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