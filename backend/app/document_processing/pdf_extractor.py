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
from backend.app.utils.system_utils.synchronization_utils import (
    TimeoutLock,
    LockPriority,
)
from backend.app.utils.validation.data_minimization import sanitize_document_metadata


class PDFTextExtractor(DocumentExtractor):
    """
    PDFTextExtractor is a centralized service for extracting text with positional information from PDF documents.

    It supports both single and batch processing, optimized memory usage, and synchronized access through an
    instance-level lock. In addition, this class leverages comprehensive error handling to ensure robust extraction
    even in adverse conditions. Among its key features are:
    - Flexible handling of various PDF input types (file paths, PyMuPDF Document objects, bytes, or file-like objects).
    - Batch processing to optimize performance and memory usage when dealing with large PDF documents.
    - Detailed logging and error reporting for GDPR compliance.
    """

    def __init__(
        self,
        pdf_input: Union[str, pymupdf.Document, bytes, BinaryIO],
        page_batch_size: int = 20,
    ):
        """
        Initialize a PDFTextExtractor instance using a flexible PDF input.

        The constructor supports various forms of PDF inputs including file paths, PyMuPDF Document instances,
        raw bytes, or file-like objects. It also sets up an instance-level timeout lock to ensure safe execution
        in multithreaded environments.

        Args:
            pdf_input: PDF input which can be:
                - A file path to a PDF (str)
                - A PyMuPDF Document instance
                - PDF content as bytes
                - A file-like object with PDF content
            page_batch_size: Number of pages to process in one batch for large documents
        """
        # Initialize file_labeling_path attribute to None.
        self.file_path = None
        # Set the batch size for page processing.
        self.page_batch_size = page_batch_size
        # Initialize the pdf_document attribute to None.
        self.pdf_document = None

        # Create an instance-level timeout lock for thread safety.
        self._instance_lock = TimeoutLock(
            f"pdf_extractor_instance_lock_{id(self)}",  # Unique lock name based on instance ID
            priority=LockPriority.MEDIUM,  # Set lock priority
            timeout=DEFAULT_EXTRACTION_TIMEOUT,  # Set extraction timeout as defined in constants
        )

        try:
            # Check if the pdf_input is a string (file path).
            if isinstance(pdf_input, str):
                # Open the PDF document using PyMuPDF with the file path.
                self.pdf_document = pymupdf.open(pdf_input)
                # Set file_labeling_path attribute with the file path.
                self.file_path = pdf_input
            # Check if the pdf_input is already a PyMuPDF Document instance.
            elif isinstance(pdf_input, pymupdf.Document):
                # Use the provided PyMuPDF document.
                self.pdf_document = pdf_input
                # Mark the file_labeling_path as a memory document.
                self.file_path = "memory_document"
            # Check if the pdf_input is of bytes type.
            elif isinstance(pdf_input, bytes):
                # Wrap the bytes in a BytesIO stream.
                buffer = io.BytesIO(pdf_input)
                # Open the PDF document using the stream.
                self.pdf_document = pymupdf.open(stream=buffer, filetype="pdf")
                # Set the file_labeling_path as memory_buffer.
                self.file_path = "memory_buffer"
            # Check if the pdf_input is a file-like object.
            elif hasattr(pdf_input, "read") and callable(pdf_input.read):
                # Open the PDF document using the file-like object.
                self.pdf_document = pymupdf.open(stream=pdf_input, filetype="pdf")
                # Get the name attribute from the file-like object if available.
                self.file_path = getattr(pdf_input, "name", "file_object")
            else:
                # Raise a ValueError if the input type is invalid.
                raise ValueError(
                    "Invalid input! Expected a file path, PyMuPDF Document, bytes, or file-like object."
                )
        except Exception as e:
            # Log the error using the SecurityAwareErrorHandler.
            SecurityAwareErrorHandler.log_processing_error(
                e,
                "pdf_extractor_init",
                str(pdf_input) if isinstance(pdf_input, str) else "memory_buffer",
            )
            # Re-raise the exception after logging.
            raise

    def extract_text(self) -> Dict[str, Any]:
        """
        Extract text from the PDF document page by page, including positional information.

        This method processes the PDF document, reconstructs text for each page, and gathers extraction statistics.
        It also sanitizes document metadata and logs performance metrics as part of GDPR compliance.

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
        # Initialize a dictionary to store extracted data.
        extracted_data = {"pages": []}
        # Initialize a list to record empty pages.
        empty_pages = []
        # Get the total number of pages from the PDF document.
        total_pages = len(self.pdf_document)
        # Determine the operation identifier based on file_labeling_path or default memory_document.
        operation_id = (
            os.path.basename(self.file_path)
            if isinstance(self.file_path, str)
            else "memory_document"
        )
        # Start the timer for performance tracking.
        start_time = time.time()

        try:
            # Acquire the instance-level lock to ensure synchronized extraction.
            with self._instance_lock.acquire_timeout() as acquired:
                # Check if the lock was successfully acquired.
                if not acquired:
                    # Log an error if lock acquisition fails.
                    log_error(
                        f"[ERROR] Failed to acquire lock for extraction: {operation_id}"
                    )
                    # Return an error dictionary with timeout information.
                    return {
                        "pages": [],
                        "error": "Lock acquisition timeout",
                        "timeout": True,
                    }

                # Log that PDF extraction is starting.
                log_info(
                    f"[OK] Processing PDF extraction (operation_id: {operation_id})"
                )

                # Determine if page batch processing should be used (for documents with more than 10 pages).
                use_paged_processing = total_pages > 10

                if use_paged_processing:
                    # If using batch processing, extract pages in batches.
                    self._extract_pages_in_batches(extracted_data, empty_pages)
                else:
                    # For smaller documents, process each page sequentially.
                    for page_num in range(total_pages):
                        # Process a single page.
                        self._process_page(page_num, extracted_data, empty_pages)

                # If there are empty pages, log the count.
                if empty_pages:
                    # Log the count of skipped empty pages.
                    log_info(f"[OK] Skipped {len(empty_pages)} empty pages")
                    # Log sensitive operation for empty page detection.
                    log_sensitive_operation(
                        "PDF Empty Page Detection",
                        len(empty_pages),
                        0.0,
                        total_pages=total_pages,
                        operation_id=operation_id,
                    )

                # Record document statistics: total pages.
                extracted_data["total_document_pages"] = total_pages
                # Record document statistics: list of empty pages.
                extracted_data["empty_pages"] = empty_pages
                # Record document statistics: count of pages with content.
                extracted_data["content_pages"] = total_pages - len(empty_pages)

                try:
                    # Attempt to extract metadata from the PDF document.
                    metadata = self.pdf_document.metadata
                    # Check if metadata exists.
                    if metadata:
                        # Sanitize the metadata.
                        extracted_data["metadata"] = sanitize_document_metadata(
                            metadata
                        )
                except Exception as meta_error:
                    # Log any error encountered during metadata extraction.
                    SecurityAwareErrorHandler.log_processing_error(
                        meta_error, "pdf_metadata_extraction", self.file_path
                    )

        except TimeoutError as te:
            # Calculate the processing time in case of a timeout.
            processing_time = time.time() - start_time
            # Record processing failure for GDPR compliance.
            record_keeper.record_processing(
                operation_type="pdf_text_extraction",
                document_type="PDF",
                entity_types_processed=[],
                processing_time=processing_time,
                file_count=1,
                entity_count=0,
                success=False,
            )
            # Log the timeout error.
            log_error(f"[ERROR] Timeout during PDF extraction: {str(te)}")
            # Return a dictionary indicating the timeout error.
            return {"pages": [], "error": "PDF extraction timed out", "timeout": True}
        except Exception as e:
            # Calculate the processing time in case of a general error.
            processing_time = time.time() - start_time
            # Record processing failure for GDPR compliance.
            record_keeper.record_processing(
                operation_type="pdf_text_extraction",
                document_type="PDF",
                entity_types_processed=[],
                processing_time=processing_time,
                file_count=1,
                entity_count=0,
                success=False,
            )
            # Log the processing error with details.
            SecurityAwareErrorHandler.log_processing_error(
                e, "pdf_text_extraction", self.file_path
            )
            # Return a dictionary indicating the error encountered.
            return {"pages": [], "error": str(e)}

        # Compute total processing time.
        processing_time = time.time() - start_time

        # Record successful processing for GDPR compliance.
        record_keeper.record_processing(
            operation_type="pdf_text_extraction",
            document_type="PDF",
            entity_types_processed=[],
            processing_time=processing_time,
            file_count=1,
            entity_count=0,
            success=True,
        )

        # Log the sensitive operation without exposing sensitive details.
        log_sensitive_operation(
            "PDF Text Extraction",
            0,  # No entities extracted in this process.
            processing_time,
            pages=len(extracted_data["pages"]),
            total_pages=total_pages,
            operation_id=operation_id,
        )

        # Log the completion of extraction.
        log_info(
            f"[OK] Text extraction completed successfully. Extracted {len(extracted_data['pages'])} pages with content."
        )
        # Return the dictionary containing all extracted data and metadata.
        return extracted_data

    def _extract_pages_in_batches(
        self, extracted_data: Dict[str, Any], empty_pages: List[int]
    ) -> None:
        """
        Extract text from pages in batches to reduce memory usage in large documents.

        This method processes pages in groups defined by page_batch_size and logs progress.
        It also enforces timeouts per batch and per page to prevent prolonged processing.

        Args:
            extracted_data: Dictionary to store the extracted page data.
            empty_pages: List to store the numbers of pages that were empty or encountered errors.
        """
        # Get the total number of pages from the PDF document.
        total_pages = len(self.pdf_document)

        # Process pages in sequential batches from start to end.
        for batch_start in range(0, total_pages, self.page_batch_size):
            # Determine the last page index for the current batch.
            batch_end = min(batch_start + self.page_batch_size, total_pages)
            # Log the details of the page batch being processed.
            log_info(
                f"[OK] Processing PDF page batch {batch_start}-{batch_end - 1} of {total_pages}"
            )

            # Start the timer for the current batch.
            batch_start_time = time.time()
            try:
                # Iterate over each page in the current batch.
                for page_num in range(batch_start, batch_end):
                    # Start timer for processing the individual page.
                    page_start_time = time.time()
                    # Set maximum allowed time per page.
                    max_page_time = 10.0

                    # Calculate elapsed time for the current batch.
                    elapsed_batch_time = time.time() - batch_start_time
                    # If the batch processing exceeds the timeout, log a warning and exit the loop.
                    if elapsed_batch_time > DEFAULT_EXTRACTION_TIMEOUT:
                        log_warning(
                            f"[WARNING] Batch processing is taking too long ({elapsed_batch_time:.2f}s), skipping remaining pages"
                        )
                        # Break out of the page processing loop if timeout is reached.
                        break

                    try:
                        # Process the individual page.
                        self._process_page(page_num, extracted_data, empty_pages)
                        # Calculate the time taken to process the page.
                        page_time = time.time() - page_start_time
                        # If processing time exceeds the per-page limit, log a warning.
                        if page_time > max_page_time:
                            log_warning(
                                f"[WARNING] Page {page_num} processing took {page_time:.2f}s (exceeded {max_page_time}s threshold)"
                            )
                    except Exception as e:
                        # Log any error that occurs during processing of a page.
                        log_error(f"[ERROR] Error processing page {page_num}: {str(e)}")
                        # Continue processing the next pages despite the error.
            except TimeoutError:
                # Log an error if a timeout occurs during batch processing.
                log_error(
                    f"[ERROR] Timeout during batch processing pages {batch_start}-{batch_end - 1}"
                )

            # Import the garbage collection module.
            import gc

            # Trigger garbage collection to free up memory after processing the current batch.
            gc.collect()

    def _process_page(
        self, page_num: int, extracted_data: Dict[str, Any], empty_pages: List[int]
    ) -> None:
        """
        Process an individual page by extracting text and its word positions.

        If the page contains no text, it is marked as empty. Any errors during processing are logged,
        and the page data will include an error message.

        Args:
            page_num: Zero-based index of the page.
            extracted_data: Dictionary to which the extracted page data will be appended.
            empty_pages: List to record page numbers that are empty.
        """
        try:
            # Access the page using the page number.
            page = self.pdf_document[page_num]
            # Log that processing for this page has started.
            log_info(f"[OK] Processing page {page_num + 1}")

            # Extract words and their positional information from the page.
            page_words = self._extract_page_words(page)

            # Check if any words were extracted (non-empty page).
            if not page_words:
                # If no words found, record this page as empty.
                empty_pages.append(page_num + 1)
                # Log that the page is empty and will be skipped.
                log_info(f"[OK] Skipping empty page {page_num + 1}")
                # Exit this method early.
                return

            # Create a dictionary for the page data.
            page_data = {"page": page_num + 1, "words": page_words}
            # Append the page data to the overall extracted data.
            extracted_data["pages"].append(page_data)

        except Exception as e:
            # Log any exceptions encountered during page processing.
            log_error(f"[ERROR] Error in page {page_num} processing: {str(e)}")
            # Append an error entry for the page in the extracted data.
            extracted_data["pages"].append(
                {
                    "page": page_num + 1,
                    "words": [],
                    "error": f"Error processing page: {str(e)}",
                }
            )

    @staticmethod
    def _extract_page_words(page: pymupdf.Page) -> List[Dict[str, Any]]:
        """
        Extract words and their coordinates from a PDF page.

        This method utilizes PyMuPDF's get_text("words") to retrieve word bounding boxes. It filters out any words
        that consist only of whitespace and returns a list of dictionaries containing the word text and positional data.

        Args:
            page: A PyMuPDF Page object.

        Returns:
            A list of dictionaries, each representing a word and its bounding box coordinates.
        """
        # Initialize an empty list to hold extracted word data.
        page_words = []
        try:
            # Retrieve word information from the page as a list of tuples.
            words = page.get_text("words")
            # Iterate over each word tuple.
            for word in words:
                # Unpack coordinates and text from the tuple.
                x0, y0, x1, y1, text, *_ = word
                # Check if the text is not empty after stripping whitespace.
                if text.strip():
                    # Append the word and its coordinates as a dictionary.
                    page_words.append(
                        {"text": text.strip(), "x0": x0, "y0": y0, "x1": x1, "y1": y1}
                    )
        except Exception as e:
            # Log any error encountered during word extraction using the SecurityAwareErrorHandler.
            SecurityAwareErrorHandler.log_processing_error(
                e, "pdf_page_word_extraction", f"page_{page.number}"
            )
        # Return the list of extracted words.
        return page_words

    @staticmethod
    def extract_images_on_page(page: pymupdf.Page) -> List[Dict[str, Any]]:
        """
        Detect and extract image bounding boxes from a PDF page.

        This method searches for images on the given page and retrieves their bounding boxes.
        Each image's bounding box and reference index are returned as a dictionary in a list.

        Args:
            page: A PyMuPDF Page object.

        Returns:
            A list of dictionaries, each containing the bounding box coordinates and the image reference index.
        """
        # Initialize an empty list to store image bounding box data.
        image_boxes = []
        try:
            # Retrieve information about all images on the page.
            images = page.get_images(full=True)
            # Iterate over each image found on the page.
            for img in images:
                # Get the image reference index.
                xref = img[0]
                # Get the bounding rectangles for the image using its reference.
                rects = page.get_image_rects(xref)
                # Iterate over each rectangle returned.
                for rect in rects:
                    # Append the image bounding box details as a dictionary.
                    image_boxes.append(
                        {
                            "x0": rect.x0,
                            "y0": rect.y0,
                            "x1": rect.x1,
                            "y1": rect.y1,
                            "xref": xref,
                        }
                    )
        except Exception as e:
            # Log any error that occurs during image extraction.
            SecurityAwareErrorHandler.log_processing_error(
                e, "pdf_image_extraction", f"page_{page.number}"
            )
        # Return the list of image bounding boxes.
        return image_boxes

    def close(self) -> None:
        """
        Close the PDF document and release associated resources.

        This method calls the close function on the PDF document and handles any exceptions that might occur,
        logging errors securely.
        """
        try:
            # Check if the PDF document is open.
            if self.pdf_document is not None:
                # Close the PDF document.
                self.pdf_document.close()
                # Reset the PDF document attribute to None.
                self.pdf_document = None
        except Exception as e:
            # Log any error encountered during the close operation.
            SecurityAwareErrorHandler.log_processing_error(
                e, "pdf_document_close", self.file_path
            )

    @staticmethod
    async def extract_batch_text(
        pdf_files: List[Union[str, bytes, BinaryIO]], max_workers: Optional[int] = None
    ) -> List[Tuple[int, Dict[str, Any]]]:
        """
        Extract text from multiple PDF files in parallel.

        This asynchronous method leverages parallel processing to extract text from multiple PDFs.
        Each file is processed independently, and any errors in processing are handled and logged securely.

        Args:
            pdf_files: A list of PDF files. Each file can be a file path (str), raw bytes, or a file-like object.
            max_workers: The maximum number of parallel workers. If None, an optimal worker count is calculated.

        Returns:
            A list of tuples, where each tuple contains an index and a dictionary of the extraction result.
        """
        # Determine the maximum number of workers if not provided.
        if max_workers is None:
            # Calculate optimal workers based on the number of PDF files.
            max_workers = ParallelProcessingCore.get_optimal_workers(len(pdf_files))

        # Log the initiation of the batch processing along with the worker count.
        log_info(f"[BATCH] Processing {len(pdf_files)} PDFs with {max_workers} workers")

        # Define an asynchronous inner function to process a single PDF file.
        async def process_pdf(pdf_file: Union[str, bytes, BinaryIO]) -> Dict[str, Any]:
            try:
                # Initialize a PDFTextExtractor instance for the pdf_file.
                extractor = PDFTextExtractor(pdf_file)
                # Extract text from the PDF.
                result = extractor.extract_text()
                # Close the extractor to free up resources.
                extractor.close()
                # Return the extraction result.
                return result
            except Exception as e:
                # Determine a file identifier based on input type.
                file_id = pdf_file if isinstance(pdf_file, str) else "memory_buffer"
                # Log any error encountered during PDF extraction.
                SecurityAwareErrorHandler.log_processing_error(
                    e, "batch_pdf_extraction", file_id
                )
                # Return a dictionary indicating the error.
                return {"pages": [], "error": str(e)}

        # Use ParallelProcessingCore to process all PDFs in parallel.
        results = await ParallelProcessingCore.process_in_parallel(
            pdf_files, lambda pdf: process_pdf(pdf), max_workers=max_workers
        )
        # Return the list of (index, result) tuples.
        return results
