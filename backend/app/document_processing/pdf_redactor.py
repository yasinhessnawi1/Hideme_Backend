"""
Centralized PDF Redaction Service Module

This module provides a comprehensive implementation for applying redactions to PDF documents.
It supports both single and batch redaction operations with optimized memory usage, instance-level
synchronization, and enhanced security measures such as metadata removal, hidden content cleaning,
and image redaction. The redaction mapping (a dictionary with sensitive spans and bounding boxes)
guides the redaction process, and secure logging is used for GDPR compliance and auditing.
"""

import io
import os
import time
from typing import Dict, Any, List, Union, BinaryIO

import pymupdf

from backend.app.domain.interfaces import DocumentRedactor
from backend.app.utils.constant.constant import DEFAULT_LOCK_TIMEOUT
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.system_utils.synchronization_utils import TimeoutLock, LockPriority
from backend.app.document_processing.pdf_extractor import PDFTextExtractor


class PDFRedactionService(DocumentRedactor):
    """
    PDFRedactionService is a centralized service for applying redactions to PDF documents.

    This service supports single and batch redaction operations with optimized memory usage and
    thread-safe execution via an instance-level lock. It removes sensitive text and images based
    on a provided redaction mapping, cleans the document metadata and hidden content, and ensures
    security through standardized error handling and audit logging.
    """

    def __init__(self, pdf_input: Union[str, pymupdf.Document, bytes, BinaryIO],
                 page_batch_size: int = 5):
        """
        Initialize PDFRedactionService with flexible PDF input types.

        The constructor accepts a PDF file as a file path, a PyMuPDF Document, raw bytes, or a file-like object.
        It also initializes an instance-level lock to ensure thread safety during redaction operations.

        Args:
            pdf_input: PDF input, which can be one of the following:
                - File path (str)
                - PyMuPDF Document instance
                - PDF content as bytes
                - File-like object with PDF content
            page_batch_size: Number of pages to process per batch for redaction (helps optimize memory usage)
        """
        # Begin initialization process.
        try:
            # Initialize file_labeling_path attribute.
            self.file_path = None
            # Store the page batch size.
            self.page_batch_size = page_batch_size
            # Initialize the document attribute.
            self.doc = None

            # Create an instance-level timeout lock for thread-safe redaction operations.
            self._instance_lock = TimeoutLock(
                f"pdf_redactor_instance_lock_{id(self)}",  # Unique name based on the instance id.
                priority=LockPriority.MEDIUM,  # Set lock priority.
                timeout=DEFAULT_LOCK_TIMEOUT  # Set the timeout threshold.
            )

            # Check if pdf_input is a string (assumed to be a file path).
            if isinstance(pdf_input, str):
                # Open the PDF file using pymupdf.
                self.doc = pymupdf.open(pdf_input)
                # Save the file path.
                self.file_path = pdf_input
            # Check if pdf_input is already a PyMuPDF Document.
            elif isinstance(pdf_input, pymupdf.Document):
                # Use the document directly.
                self.doc = pdf_input
                # Set a default identifier for in-memory documents.
                self.file_path = "memory_document"
            # Check if pdf_input is raw bytes.
            elif isinstance(pdf_input, bytes):
                # Wrap the bytes in a BytesIO buffer.
                buffer = io.BytesIO(pdf_input)
                # Open the PDF from the buffer.
                self.doc = pymupdf.open(stream=buffer, filetype="pdf")
                # Set file identifier to memory_buffer.
                self.file_path = "memory_buffer"
            # Check if pdf_input is an instance of io.BufferedReader.
            elif isinstance(pdf_input, io.BufferedReader):
                # Read the entire content from the buffered reader.
                content = pdf_input.read()
                # Close the buffered reader.
                pdf_input.close()
                # Wrap the content in a BytesIO buffer.
                buffer = io.BytesIO(content)
                # Open the PDF document from the buffer.
                self.doc = pymupdf.open(stream=buffer, filetype="pdf")
                # Save the name attribute if available.
                self.file_path = getattr(pdf_input, 'name', "buffered_reader")
            # Check if pdf_input is a file-like object.
            elif hasattr(pdf_input, 'read') and callable(pdf_input.read):
                # Open the PDF using the file-like object.
                self.doc = pymupdf.open(stream=pdf_input, filetype="pdf")
                # Save the name attribute if available.
                self.file_path = getattr(pdf_input, 'name', "file_object")
            else:
                # Raise an exception for invalid input types.
                raise ValueError(
                    "Invalid input! Expected a file path, PyMuPDF Document, bytes, BufferedReader, or file-like object."
                )

            # Log a successful PDF open operation.
            log_info(f"[OK] Opened PDF file: {self.file_path}")
        except Exception as e:
            # Log any error that occurs during initialization securely.
            SecurityAwareErrorHandler.log_processing_error(
                e,
                "pdf_redaction_init",
                str(pdf_input) if isinstance(pdf_input, str) else "memory_buffer"
            )
            # Re-raise the exception to halt the process.
            raise

    def apply_redactions(self, redaction_mapping: Dict[str, Any], output_path: str, remove_images: bool = False) -> str:
        """
        Apply redactions to the PDF based on the provided redaction mapping and save the result.

        The mapping should follow the format: {"pages": [{"page": page_num, "sensitive": [items]}]}.
        If remove_images is True, image redaction is also applied.

        Args:
            redaction_mapping: Dictionary with redaction information.
            output_path: Path to save the redacted PDF.
            remove_images: Flag indicating whether to detect and redact images.

        Returns:
            The file path of the saved redacted PDF.
        """
        # Record the start time of the redaction process.
        start_time = time.time()
        # Determine an operation identifier based on the file path.
        operation_id = os.path.basename(self.file_path) if isinstance(self.file_path, str) else "memory_document"
        # Count all sensitive items across pages from the mapping.
        sensitive_items_count = sum(
            len(page.get("sensitive", []))  # Count sensitive items on each page.
            for page in redaction_mapping.get("pages", [])  # Iterate over pages in the mapping.
        )

        try:
            # Acquire the instance lock to perform thread-safe redaction operations.
            with self._instance_lock.acquire_timeout(timeout=DEFAULT_LOCK_TIMEOUT) as acquired:
                # Check if the lock was successfully acquired.
                if not acquired:
                    # Log an error and raise TimeoutError if lock acquisition fails.
                    log_error(f"[ERROR] Failed to acquire lock for redaction: {operation_id}")
                    raise TimeoutError(f"Failed to acquire redaction lock after {DEFAULT_LOCK_TIMEOUT}s")

                # Log the start of the redaction process.
                log_info(f"[OK] Processing PDF redaction (operation_id: {operation_id})")

                # Draw redaction boxes using the provided mapping.
                self._draw_redaction_boxes(redaction_mapping, remove_images)
                # Sanitize the document by removing metadata and cleaning hidden content.
                self._sanitize_document()

                # Save the redacted PDF to the given output path.
                self.doc.save(output_path)
                # Close the document to free resources.
                self.doc.close()

                # Compute the total processing time.
                processing_time = time.time() - start_time

                # Record processing metrics for auditing and GDPR compliance.
                record_keeper.record_processing(
                    operation_type="pdf_redaction",
                    document_type="PDF",
                    entity_types_processed=[],
                    processing_time=processing_time,
                    file_count=1,
                    entity_count=sensitive_items_count,
                    success=True
                )

                # Log a secure operation for redaction.
                log_sensitive_operation(
                    "PDF Redaction",
                    sensitive_items_count,
                    processing_time,
                    file_path=self.file_path,
                    operation_id=operation_id
                )

                # Log the success message and return the output path.
                log_info(f"[OK] Redacted PDF saved as {output_path}")
                return output_path

        except TimeoutError as te:
            # Calculate processing time upon timeout.
            processing_time = time.time() - start_time
            # Record failed processing metrics for a timeout event.
            record_keeper.record_processing(
                operation_type="pdf_redaction_timeout",
                document_type="PDF",
                entity_types_processed=[],
                processing_time=processing_time,
                file_count=1,
                entity_count=0,
                success=False
            )
            # Log the redaction timeout error.
            log_error(f"[ERROR] Redaction timeout: {str(te)}")
            # Re-raise the timeout error.
            raise
        except Exception as e:
            # Calculate processing time upon a general error.
            processing_time = time.time() - start_time
            # Record failed processing metrics for a general redaction error.
            record_keeper.record_processing(
                operation_type="pdf_redaction",
                document_type="PDF",
                entity_types_processed=[],
                processing_time=processing_time,
                file_count=1,
                entity_count=0,
                success=False
            )
            # Log any error encountered using the secure error handler.
            SecurityAwareErrorHandler.log_processing_error(e, "pdf_redaction", self.file_path)
            # Re-raise the exception.
            raise

    def apply_redactions_to_memory(self, redaction_mapping: Dict[str, Any], remove_images: bool = False) -> bytes:
        """
        Apply redactions to the PDF and return the redacted document as bytes.

        The operation is performed entirely in memory to avoid disk I/O. The redaction mapping
        must follow the expected format.

        Args:
            redaction_mapping: Dictionary with redaction details.
            remove_images: Flag indicating whether to redact images.

        Returns:
            Redacted PDF content as bytes.
        """
        # Record the starting time of in-memory redaction.
        start_time = time.time()
        # Create a unique operation identifier using the current time.
        operation_id = f"memory_redaction_{time.time()}"
        # Count the total number of sensitive items to be redacted.
        sensitive_items_count = sum(
            len(page.get("sensitive", []))  # Count sensitive items on a page.
            for page in redaction_mapping.get("pages", [])  # Iterate over all pages.
        )

        try:
            # Acquire the instance lock for thread-safe in-memory redaction.
            with self._instance_lock.acquire_timeout(timeout=DEFAULT_LOCK_TIMEOUT) as acquired:
                # Check if the lock acquisition succeeded.
                if not acquired:
                    # Log the error and raise TimeoutError if the lock cannot be acquired.
                    log_error(f"[ERROR] Failed to acquire lock for memory redaction: {operation_id}")
                    raise TimeoutError(f"Failed to acquire memory redaction lock after {DEFAULT_LOCK_TIMEOUT}s")

                # Log the start of the in-memory redaction process.
                log_info(f"[OK] Processing PDF memory redaction (operation_id: {operation_id})")

                # Draw redaction boxes based on the mapping.
                self._draw_redaction_boxes(redaction_mapping, remove_images)
                # Sanitize the document (remove metadata, hidden content, etc.).
                self._sanitize_document()

                # Create an in-memory BytesIO buffer to save the redacted document.
                output_buffer = io.BytesIO()
                # Save the document content to the in-memory buffer.
                self.doc.save(output_buffer)
                # Close the document to free up resources.
                self.doc.close()

                # Move the buffer pointer to the start.
                output_buffer.seek(0)
                # Retrieve the redacted PDF content as bytes.
                redacted_content = output_buffer.getvalue()

                # Calculate the processing time.
                processing_time = time.time() - start_time

                # Record successful in-memory redaction processing metrics.
                record_keeper.record_processing(
                    operation_type="pdf_memory_redaction",
                    document_type="PDF",
                    entity_types_processed=[],
                    processing_time=processing_time,
                    file_count=1,
                    entity_count=sensitive_items_count,
                    success=True
                )

                # Log the sensitive operation for auditing.
                log_sensitive_operation(
                    "PDF Memory Redaction",
                    sensitive_items_count,
                    processing_time,
                    operation_id=operation_id
                )

                # Return the redacted PDF content.
                return redacted_content

        except TimeoutError as te:
            # Calculate the processing time upon a timeout.
            processing_time = time.time() - start_time
            # Record the timeout event metrics.
            record_keeper.record_processing(
                operation_type="pdf_memory_redaction_timeout",
                document_type="PDF",
                entity_types_processed=[],
                processing_time=processing_time,
                file_count=1,
                entity_count=0,
                success=False
            )
            # Log the timeout error.
            log_error(f"[ERROR] Memory redaction timeout: {str(te)}")
            # Re-raise the TimeoutError.
            raise
        except Exception as e:
            # Calculate the processing time upon a general exception.
            processing_time = time.time() - start_time
            # Record failure metrics for the error.
            record_keeper.record_processing(
                operation_type="pdf_memory_redaction",
                document_type="PDF",
                entity_types_processed=[],
                processing_time=processing_time,
                file_count=1,
                entity_count=0,
                success=False
            )
            # Log the error securely.
            SecurityAwareErrorHandler.log_processing_error(e, "pdf_memory_redaction", self.file_path)
            # Re-raise the exception.
            raise

    def _draw_redaction_boxes(self, redaction_mapping: Dict[str, Any], remove_images: bool) -> None:
        """
        Process the redaction mapping and apply redaction boxes to the specified pages.

        For large documents, redaction is applied in batches to optimize memory usage.

        Args:
            redaction_mapping: Dictionary with redaction information.
            remove_images: Flag to enable image redaction on each page.
        """
        # Get the total number of pages in the PDF document.
        total_pages = len(self.doc)
        # Extract a sorted list of unique page numbers from the mapping.
        page_numbers = {page_info.get("page") for page_info in redaction_mapping.get("pages", [])
                        if page_info.get("page") is not None}
        page_numbers = sorted(page_numbers)

        try:
            # Check if the number of pages exceeds 10 for batching.
            if len(page_numbers) > 10:
                # Iterate through page numbers in batches.
                for batch_start in range(0, len(page_numbers), self.page_batch_size):
                    # Determine the end index for the current batch.
                    batch_end = min(batch_start + self.page_batch_size, len(page_numbers))
                    # Get the list of page numbers in the current batch.
                    batch_page_numbers = page_numbers[batch_start:batch_end]
                    # Log the batch processing of redaction.
                    log_info(f"[OK] Processing redaction batch for pages {batch_page_numbers}")
                    # Process the current batch of pages.
                    self._process_redaction_pages_batch(redaction_mapping, batch_page_numbers, total_pages,
                                                        remove_images)
                    # Import and invoke garbage collection to free memory.
                    import gc
                    gc.collect()
            else:
                # If few pages, process them all at once.
                self._process_all_redaction_pages(redaction_mapping, total_pages, remove_images)
        except Exception as e:
            # Log any error encountered during the drawing of redaction boxes.
            log_error(f"[ERROR] Error while drawing redaction boxes: {str(e)}")
            # Re-raise the exception.
            raise

    def _process_redaction_page(self, page_num: int, page_info: Dict[str, Any], total_pages: int,
                                remove_images: bool = False) -> None:
        """
        Process redaction for a single page based on the mapping.

        This method handles redaction for both text-based sensitive items and images (if enabled).
        It adds redaction annotations and applies the redactions on the page.

        Args:
            page_num: The page number (1-indexed) to process.
            page_info: Redaction mapping details for this page.
            total_pages: Total number of pages in the document.
            remove_images: Flag to enable image redaction.
        """
        # Extract the list of sensitive items for the page.
        sensitive_items = page_info.get("sensitive", [])
        # Check if there are no sensitive items.
        if not sensitive_items:
            # Log that no redaction is required on this page.
            log_info(f"[OK] No sensitive items found on page {page_num}.")
            # Return early.
            return

        # Check if the page number is within the valid range.
        if page_num < 1 or page_num > total_pages:
            # Log a warning if the page number is out of range.
            log_warning(
                f"[WARNING] Page number {page_num} is out of range for document with {total_pages} pages. Skipping.")
            # Return early.
            return

        try:
            # Retrieve the page object (adjusting for zero-based index).
            page = self.doc[page_num - 1]
            # Process each sensitive item on the page.
            for item in sensitive_items:
                self._process_sensitive_item(page, item, page_num)

            # If image redaction is enabled, detect and redact images.
            if remove_images:
                # Extract image bounding boxes from the page.
                image_boxes = PDFTextExtractor.extract_images_on_page(page)
                # Check if any images were found.
                if image_boxes:
                    # For each detected image, process redaction.
                    for img in image_boxes:
                        # Create a rectangle from the image coordinates.
                        rect = pymupdf.Rect(img["x0"], img["y0"], img["x1"], img["y1"])
                        # Add a redaction annotation with a black fill.
                        page.add_redact_annot(rect, fill=(0, 0, 0))
                    # Log the number of redacted images.
                    log_info(f"[OK] ✅ Detected and redacted {len(image_boxes)} image(s) on page {page_num}")

            # Apply all redaction annotations on the page.
            page.apply_redactions()
        except Exception as e:
            # Log any error during the redaction of this page.
            SecurityAwareErrorHandler.log_processing_error(e, "pdf_redaction_page", f"{self.file_path}:page_{page_num}")

    def _process_all_redaction_pages(self, redaction_mapping: Dict[str, Any], total_pages: int,
                                     remove_images: bool) -> None:
        """
        Process redactions for all pages specified in the mapping sequentially.

        Args:
            redaction_mapping: Dictionary with redaction information.
            total_pages: Total number of pages in the document.
            remove_images: Flag to enable image redaction.
        """
        # Iterate through each page info in the redaction mapping.
        for page_info in redaction_mapping.get("pages", []):
            # Extract the page number from the mapping.
            page_num = page_info.get("page")
            # Skip if no page number is specified.
            if page_num is None:
                continue
            # Process redaction for the specific page.
            self._process_redaction_page(page_num, page_info, total_pages, remove_images)

    def _process_redaction_pages_batch(self, redaction_mapping: Dict[str, Any],
                                       page_numbers: List[int], total_pages: int, remove_images: bool) -> None:
        """
        Process a batch of pages for redaction to optimize memory usage.

        Args:
            redaction_mapping: Dictionary with redaction information.
            page_numbers: List of page numbers (1-indexed) to process in this batch.
            total_pages: Total number of pages in the document.
            remove_images: Flag to enable image redaction.
        """
        # Build a lookup mapping keyed by page number for easy access.
        page_mapping = {page_info.get("page"): page_info
                        for page_info in redaction_mapping.get("pages", [])
                        if page_info.get("page") in page_numbers}

        # Start the timer for the batch processing.
        batch_start_time = time.time()
        # Define the maximum allowed time for a batch.
        max_batch_time = 300.0

        # Iterate over each page number in the batch.
        for page_num in page_numbers:
            # Check if the batch processing time has exceeded the limit.
            if time.time() - batch_start_time > max_batch_time:
                # Log a warning and break out of the loop.
                log_warning(
                    f"[WARNING] Batch processing timeout reached after {(time.time() - batch_start_time):.2f}s, skipping remaining pages")
                break

            # Retrieve the corresponding page information.
            page_info = page_mapping.get(page_num)
            # If information exists, process the redaction for the page.
            if page_info:
                self._process_redaction_page(page_num, page_info, total_pages, remove_images)

    def _process_sensitive_item(self, page: pymupdf.Page, item: Dict[str, Any], page_num: int) -> None:
        """
        Process a single sensitive item to create a redaction annotation on the page.

        The method handles items that specify either multiple redaction boxes or a single bounding box.
        An annotation is added to the page for each redaction area.

        Args:
            page: The PyMuPDF Page object.
            item: Dictionary describing the sensitive item.
            page_num: The page number (1-indexed) where the item is located.
        """
        try:
            # Check if the item contains multiple boxes.
            if "boxes" in item and isinstance(item["boxes"], list):
                # Iterate over each box in the list.
                for box in item["boxes"]:
                    # Create a rectangle using the box coordinates.
                    rect = pymupdf.Rect(box["x0"], box["y0"], box["x1"], box["y1"])
                    # Add a redaction annotation with an optional entity type label.
                    page.add_redact_annot(rect, fill=(0, 0, 0), text=item.get("entity_type"))
                    # Log the redaction of the sensitive item.
                    log_info(f"[OK] Redacting entity {item.get('entity_type')} on page {page_num}")
            # Otherwise, check if a single bounding box is provided.
            elif "bbox" in item:
                # Extract the bounding box.
                bbox = item["bbox"]
                # Create a rectangle from the bounding box coordinates.
                rect = pymupdf.Rect(bbox["x0"], bbox["y0"], bbox["x1"], bbox["y1"])
                # Add a redaction annotation.
                page.add_redact_annot(rect, fill=(0, 0, 0))
        except Exception as e:
            # Log any error during sensitive item processing.
            SecurityAwareErrorHandler.log_processing_error(e, "pdf_process_sensitive_item",
                                                           f"{self.file_path}:page_{page_num}")

    def _sanitize_document(self) -> None:
        """
        Apply additional security measures to the document.

        This includes:
            - Removing all metadata.
            - Cleaning hidden content and deleting non-redaction annotations.
            - Scrubbing embedded files, JavaScript, and extra objects.
        """
        try:
            # Clear all metadata from the document.
            self.doc.set_metadata({})
            # Iterate over each page in the document.
            for page in self.doc:
                # Clean the page contents to remove hidden data.
                page.clean_contents()
                # Iterate over all annotations on the page (if any).
                for annot in page.annots() or []:
                    # Delete all annotations that are not redaction annotations (type 8).
                    if annot.type[0] != 8:
                        page.delete_annot(annot)
            # Perform a comprehensive scrub of the document.
            self.doc.scrub()
        except Exception as e:
            # Log any error encountered during the document sanitization.
            SecurityAwareErrorHandler.log_processing_error(e, "pdf_document_sanitize", self.file_path)

    def close(self) -> None:
        """
        Close the PDF document and free-associated resources.

        Uses robust error handling to log any exceptions during the close operation.
        """
        try:
            # Check if the document is not already None.
            if self.doc is not None:
                # If the document is still open, then close it.
                if not self.doc.is_closed:
                    self.doc.close()
                # Set the document reference to None.
                self.doc = None
        except Exception as e:
            # Log any error during the document close operation.
            SecurityAwareErrorHandler.log_processing_error(e, "pdf_document_close", self.file_path)
