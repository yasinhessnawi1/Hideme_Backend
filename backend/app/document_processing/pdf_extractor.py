"""
Centralized PDF Document Processing Module

This module provides comprehensive implementations for PDF text extraction with enhanced batch capabilities,
optimized synchronization using instance-level locks, and robust error handling for GDPR compliance. It supports:
- Unified batch processing for text extraction from PDF files
- Parallel processing support for improved performance in batch mode
- Instance-level locking for synchronized access to shared resources
- Optimized memory management for large documents
- Detailed error logging and standardized error reporting using SecurityAwareErrorHandler
"""

import io
import os
import time
from typing import Dict, Any, List, Union, BinaryIO, Optional, Tuple

import pymupdf

from backend.app.domain.interfaces import DocumentExtractor
from backend.app.utils.constant.constant import DEFAULT_EXTRACTION_TIMEOUT
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.parallel.core import ParallelProcessingCore
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.system_utils.synchronization_utils import TimeoutLock, LockPriority
from backend.app.utils.validation.data_minimization import sanitize_document_metadata


class PDFTextExtractor(DocumentExtractor):
    """
    PDFTextExtractor is a centralized service for extracting text with positional information from PDF documents.

    This class supports both single and batch processing, optimized memory usage, and synchronization through an
    instance-level lock. It leverages comprehensive error handling to ensure robust extraction even in adverse conditions.
    """

    def __init__(self, pdf_input: Union[str, pymupdf.Document, bytes, BinaryIO],
                 page_batch_size: int = 20):
        """
        Initialize PDFTextExtractor with flexible input types.

        The constructor supports various forms of PDF inputs including file paths, PyMuPDF Document instances,
        raw bytes, or file-like objects. It also sets up an instance-level lock for safe multithreaded operations.

        Args:
            pdf_input: PDF input which can be:
                - A file path to a PDF (str)
                - A PyMuPDF Document instance
                - PDF content as bytes
                - A file-like object with PDF content
            page_batch_size: Number of pages to process in one batch for large documents
        """
        self.file_path = None
        self.page_batch_size = page_batch_size
        self.pdf_document = None

        # Create an instance-level timeout lock for thread safety
        self._instance_lock = TimeoutLock(
            f"pdf_extractor_instance_lock_{id(self)}",
            priority=LockPriority.MEDIUM,
            timeout=DEFAULT_EXTRACTION_TIMEOUT
        )

        try:
            if isinstance(pdf_input, str):
                # If input is a file path, open the document using pymupdf
                self.pdf_document = pymupdf.open(pdf_input)
                self.file_path = pdf_input
            elif isinstance(pdf_input, pymupdf.Document):
                # If input is already a PyMuPDF Document, use it directly
                self.pdf_document = pdf_input
                self.file_path = "memory_document"
            elif isinstance(pdf_input, bytes):
                # If input is raw bytes, wrap them in a BytesIO stream
                buffer = io.BytesIO(pdf_input)
                self.pdf_document = pymupdf.open(stream=buffer, filetype="pdf")
                self.file_path = "memory_buffer"
            elif hasattr(pdf_input, 'read') and callable(pdf_input.read):
                # If input is a file-like object, open it as a PDF stream
                self.pdf_document = pymupdf.open(stream=pdf_input, filetype="pdf")
                self.file_path = getattr(pdf_input, 'name', "file_object")
            else:
                # Invalid input type encountered
                raise ValueError("Invalid input! Expected a file path, PyMuPDF Document, bytes, or file-like object.")
        except Exception as e:
            # Log error using SecurityAwareErrorHandler and re-raise the exception
            SecurityAwareErrorHandler.log_processing_error(
                e, "pdf_extractor_init", str(pdf_input) if isinstance(pdf_input, str) else "memory_buffer"
            )
            raise

    def extract_text(self) -> Dict[str, Any]:
        """
        Extract text from the PDF document page by page, including positional information.

        This method reconstructs text for each page, skips empty pages, and gathers extraction statistics.
        It also sanitizes document metadata and logs performance metrics.

        Returns:
            A dictionary containing extracted page data and document statistics:
                {
                    "pages": [...],
                    "total_document_pages": int,
                    "empty_pages": List[int],
                    "content_pages": int,
                    "metadata": Optional[Dict[str, Any]]
                }
        """
        extracted_data = {"pages": []}
        empty_pages = []
        total_pages = len(self.pdf_document)
        operation_id = os.path.basename(self.file_path) if isinstance(self.file_path, str) else "memory_document"
        start_time = time.time()  # Start timer for performance tracking

        try:
            # Use instance-level lock to synchronize extraction
            with self._instance_lock.acquire_timeout() as acquired:
                if not acquired:
                    log_error(f"[ERROR] Failed to acquire lock for extraction: {operation_id}")
                    return {"pages": [], "error": "Lock acquisition timeout", "timeout": True}

                log_info(f"[OK] Processing PDF extraction (operation_id: {operation_id})")

                # Decide between batch or single-page processing based on document size
                use_paged_processing = total_pages > 10

                if use_paged_processing:
                    # Process pages in batches for large documents
                    self._extract_pages_in_batches(extracted_data, empty_pages)
                else:
                    # Process all pages at once for smaller documents
                    for page_num in range(total_pages):
                        self._process_page(page_num, extracted_data, empty_pages)

                # Log information about any skipped empty pages using secure logging
                if empty_pages:
                    log_info(f"[OK] Skipped {len(empty_pages)} empty pages")
                    log_sensitive_operation(
                        "PDF Empty Page Detection",
                        len(empty_pages),
                        0.0,
                        total_pages=total_pages,
                        operation_id=operation_id
                    )

                # Record document statistics
                extracted_data["total_document_pages"] = total_pages
                extracted_data["empty_pages"] = empty_pages
                extracted_data["content_pages"] = total_pages - len(empty_pages)

                # Attempt to extract and sanitize metadata from the PDF
                try:
                    metadata = self.pdf_document.metadata
                    if metadata:
                        extracted_data["metadata"] = sanitize_document_metadata(metadata)
                except Exception as meta_error:
                    SecurityAwareErrorHandler.log_processing_error(
                        meta_error, "pdf_metadata_extraction", self.file_path
                    )

        except TimeoutError as te:
            # Record failed processing metrics for GDPR compliance
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
            # Record failed processing metrics for GDPR compliance
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
            SecurityAwareErrorHandler.log_processing_error(
                e, "pdf_text_extraction", self.file_path
            )
            return {"pages": [], "error": str(e)}

        processing_time = time.time() - start_time  # Compute total processing time

        # Record successful processing for GDPR compliance
        record_keeper.record_processing(
            operation_type="pdf_text_extraction",
            document_type="PDF",
            entity_types_processed=[],
            processing_time=processing_time,
            file_count=1,
            entity_count=0,
            success=True
        )

        # Log performance metrics without revealing sensitive information
        log_sensitive_operation(
            "PDF Text Extraction",
            0,  # No entities extracted in this process
            processing_time,
            pages=len(extracted_data["pages"]),
            total_pages=total_pages,
            operation_id=operation_id
        )

        log_info(f"[OK] Text extraction completed successfully. Extracted {len(extracted_data['pages'])} pages with content.")
        return extracted_data

    def _extract_pages_in_batches(self, extracted_data: Dict[str, Any], empty_pages: List[int]) -> None:
        """
        Extract text from pages in batches to reduce memory usage in large documents.

        Processes pages in groups defined by page_batch_size and logs progress. Implements a timeout
        per batch and per page to avoid hanging during extraction.

        Args:
            extracted_data: Dictionary to store extracted page data.
            empty_pages: List to collect page numbers that are empty or encountered errors.
        """
        total_pages = len(self.pdf_document)

        # Process pages in sequential batches
        for batch_start in range(0, total_pages, self.page_batch_size):
            batch_end = min(batch_start + self.page_batch_size, total_pages)
            log_info(f"[OK] Processing PDF page batch {batch_start}-{batch_end - 1} of {total_pages}")

            batch_start_time = time.time()  # Start timer for the batch
            try:
                for page_num in range(batch_start, batch_end):
                    page_start_time = time.time()
                    max_page_time = 10.0  # Maximum allowed time per page in seconds

                    # Check if the current batch is taking too long
                    elapsed_batch_time = time.time() - batch_start_time
                    if elapsed_batch_time > DEFAULT_EXTRACTION_TIMEOUT:
                        log_warning(f"[WARNING] Batch processing is taking too long ({elapsed_batch_time:.2f}s), skipping remaining pages")
                        break

                    try:
                        self._process_page(page_num, extracted_data, empty_pages)
                        page_time = time.time() - page_start_time
                        if page_time > max_page_time:
                            log_warning(f"[WARNING] Page {page_num} processing took {page_time:.2f}s (exceeded {max_page_time}s threshold)")
                    except Exception as e:
                        log_error(f"[ERROR] Error processing page {page_num}: {str(e)}")
                        # Continue processing remaining pages despite errors
            except TimeoutError:
                log_error(f"[ERROR] Timeout during batch processing pages {batch_start}-{batch_end - 1}")
                # Proceed with next batch even if current batch times out

            # Trigger garbage collection to free up memory after each batch
            import gc
            gc.collect()

    def _process_page(self, page_num: int, extracted_data: Dict[str, Any], empty_pages: List[int]) -> None:
        """
        Process an individual page from the PDF document by extracting text and word positions.

        If the page contains no text, it is marked as empty. Any errors encountered during page processing
        are logged and result in an empty page entry.

        Args:
            page_num: Zero-based index of the page.
            extracted_data: Dictionary to which the page's extracted data will be added.
            empty_pages: List to record page numbers that are empty.
        """
        try:
            page = self.pdf_document[page_num]
            log_info(f"[OK] Processing page {page_num + 1}")

            # Extract words along with their positional information
            page_words = self._extract_page_words(page)

            if not page_words:
                empty_pages.append(page_num + 1)
                log_info(f"[OK] Skipping empty page {page_num + 1}")
                return

            # Append page data to the extracted data dictionary
            page_data = {
                "page": page_num + 1,
                "words": page_words
            }
            extracted_data["pages"].append(page_data)

        except Exception as e:
            log_error(f"[ERROR] Error in page {page_num} processing: {str(e)}")
            extracted_data["pages"].append({
                "page": page_num + 1,
                "words": [],
                "error": f"Error processing page: {str(e)}"
            })

    @staticmethod
    def _extract_page_words(page: pymupdf.Page) -> List[Dict[str, Any]]:
        """
        Extract words and their positions from a given PDF page.

        Filters out any words that are only whitespace. Uses PyMuPDF's get_text("words") method to retrieve
        a list of tuples that contain the word text and its coordinates.

        Args:
            page: A PyMuPDF Page object.

        Returns:
            A list of dictionaries where each dictionary represents a word and its bounding coordinates.
        """
        page_words = []
        try:
            # Retrieve word information; each tuple includes coordinates and the word itself
            words = page.get_text("words")
            for word in words:
                x0, y0, x1, y1, text, *_ = word
                if text.strip():  # Include only words with non-whitespace content
                    page_words.append({
                        "text": text.strip(),
                        "x0": x0,
                        "y0": y0,
                        "x1": x1,
                        "y1": y1
                    })
        except Exception as e:
            # Log any errors encountered during word extraction using secure error handling
            SecurityAwareErrorHandler.log_processing_error(
                e, "pdf_page_word_extraction", f"page_{page.number}"
            )
        return page_words

    @staticmethod
    def extract_images_on_page(page: pymupdf.Page) -> List[Dict[str, Any]]:
        """
        Detect and extract image bounding boxes from a given PDF page.

        Iterates over images found on the page and retrieves their bounding box coordinates.

        Args:
            page: A PyMuPDF Page object.

        Returns:
            A list of dictionaries, each containing the bounding box coordinates and reference index for an image.
        """
        image_boxes = []
        try:
            images = page.get_images(full=True)
            for img in images:
                xref = img[0]  # Image reference index
                rects = page.get_image_rects(xref)  # Retrieve bounding boxes for the image
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
        """
        Close the PDF document and release associated resources.

        Uses enhanced error handling to log any exceptions during the close operation.
        """
        try:
            if self.pdf_document is not None:
                self.pdf_document.close()
                self.pdf_document = None
        except Exception as e:
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

        Leverages asynchronous parallel processing to extract text from a batch of PDF files. Each file is processed
        independently. Any errors during extraction for a file are handled and logged securely.

        Args:
            pdf_files: A list of PDF files, which can be paths, bytes, or file-like objects.
            max_workers: Maximum number of parallel workers; if None, an optimal count is calculated.

        Returns:
            A list of tuples, where each tuple contains an index and the corresponding extraction result dictionary.
        """
        if max_workers is None:
            max_workers = ParallelProcessingCore.get_optimal_workers(len(pdf_files))

        log_info(f"[BATCH] Processing {len(pdf_files)} PDFs with {max_workers} workers")

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

        results = await ParallelProcessingCore.process_in_parallel(
            pdf_files,
            lambda pdf: process_pdf(pdf),
            max_workers=max_workers
        )
        return results