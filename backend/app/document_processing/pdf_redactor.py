import io
import os
import time
from typing import Dict, Any, List, Union, BinaryIO

import pymupdf

from backend.app.domain.interfaces import DocumentRedactor
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.system_utils.synchronization_utils import TimeoutLock, LockPriority
from backend.app.document_processing.pdf_extractor import PDFTextExtractor


class PDFRedactionService(DocumentRedactor):
    """
    Centralized service for applying redactions to PDF documents.

    This service supports both single and batch redaction operations with optimized memory usage,
    synchronization via instance-level locks, and additional security measures (metadata removal,
    cleaning hidden content, and scrubbing extra objects). The redaction mapping (a dict containing
    sensitive spans and bounding boxes) is used to determine which regions to redact. Optionally,
    image redaction can be applied if the `remove_images` flag is True.
    """
    # Timeout and batch configuration (in seconds)
    DEFAULT_REDACTION_TIMEOUT = 120.0  # 2 minutes for redaction operations
    DEFAULT_BATCH_TIMEOUT = 600.0      # 10 minutes for batch operations
    DEFAULT_LOCK_TIMEOUT = 30.0        # 30 seconds for lock acquisition

    def __init__(self, pdf_input: Union[str, pymupdf.Document, bytes, BinaryIO],
                 page_batch_size: int = 5):
        """
        Initialize PDFRedactionService with support for various PDF input types.

        Args:
            pdf_input: PDF input as one of:
                - File path (str)
                - PyMuPDF Document instance
                - PDF content as bytes
                - File-like object with PDF content
            page_batch_size: Number of pages to process in each batch (for large documents)
        """
        try:
            self.file_path = None
            self.page_batch_size = page_batch_size
            self.doc = None

            # Instance-level lock ensures thread-safe operations.
            self._instance_lock = TimeoutLock(
                f"pdf_redactor_instance_lock_{id(self)}",
                priority=LockPriority.MEDIUM,
                timeout=self.DEFAULT_LOCK_TIMEOUT
            )

            # Handle different input types.
            if isinstance(pdf_input, str):
                self.doc = pymupdf.open(pdf_input)
                self.file_path = pdf_input
            elif isinstance(pdf_input, pymupdf.Document):
                self.doc = pdf_input
                self.file_path = "memory_document"
            elif isinstance(pdf_input, bytes):
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
                self.doc = pymupdf.open(stream=pdf_input, filetype="pdf")
                self.file_path = getattr(pdf_input, 'name', "file_object")
            else:
                raise ValueError(
                    "Invalid input! Expected a file path, PyMuPDF Document, bytes, BufferedReader, or file-like object."
                )

            log_info(f"[OK] Opened PDF file: {self.file_path}")
        except Exception as e:
            SecurityAwareErrorHandler.log_processing_error(
                e,
                "pdf_redaction_init",
                str(pdf_input) if isinstance(pdf_input, str) else "memory_buffer"
            )
            raise

    def apply_redactions(self, redaction_mapping: Dict[str, Any], output_path: str, remove_images: bool = False) -> str:
        """
        Apply redactions to the PDF based on the provided mapping and save the result to a file.

        Args:
            redaction_mapping: Dictionary with redaction information. Expected format:
                {"pages": [{"page": page_num, "sensitive": [items]}]}
            output_path: File path to save the redacted PDF.
            remove_images: If True, detect and redact images on each page.

        Returns:
            The output path of the redacted PDF.
        """
        start_time = time.time()
        operation_id = os.path.basename(self.file_path) if isinstance(self.file_path, str) else "memory_document"
        # Count total redactions for logging and compliance.
        sensitive_items_count = sum(
            len(page.get("sensitive", []))
            for page in redaction_mapping.get("pages", [])
        )

        try:
            with self._instance_lock.acquire_timeout(timeout=self.DEFAULT_LOCK_TIMEOUT) as acquired:
                if not acquired:
                    log_error(f"[ERROR] Failed to acquire lock for redaction: {operation_id}")
                    raise TimeoutError(f"Failed to acquire redaction lock after {self.DEFAULT_LOCK_TIMEOUT}s")

                log_info(f"[OK] Processing PDF redaction (operation_id: {operation_id})")

                # Process redaction mapping on all pages; pass remove_images flag.
                self._draw_redaction_boxes(redaction_mapping, remove_images)
                self._sanitize_document()

                # Save the modified document.
                self.doc.save(output_path)
                self.doc.close()

                processing_time = time.time() - start_time

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
            SecurityAwareErrorHandler.log_processing_error(e, "pdf_redaction", self.file_path)
            raise

    def apply_redactions_to_memory(self, redaction_mapping: Dict[str, Any], remove_images: bool = False) -> bytes:
        """
        Apply redactions to the PDF and return the modified document as bytes.

        The entire operation is performed in memory to avoid disk I/O. The mapping should be in the
        format: {"pages": [{"page": page_num, "sensitive": [items]}]}.

        Args:
            redaction_mapping: Dictionary with redaction details.
            remove_images: If True, detect and redact images on each page.

        Returns:
            The redacted PDF content as bytes.
        """
        start_time = time.time()
        operation_id = f"memory_redaction_{time.time()}"
        sensitive_items_count = sum(
            len(page.get("sensitive", []))
            for page in redaction_mapping.get("pages", [])
        )

        try:
            with self._instance_lock.acquire_timeout(timeout=self.DEFAULT_LOCK_TIMEOUT) as acquired:
                if not acquired:
                    log_error(f"[ERROR] Failed to acquire lock for memory redaction: {operation_id}")
                    raise TimeoutError(f"Failed to acquire memory redaction lock after {self.DEFAULT_LOCK_TIMEOUT}s")

                log_info(f"[OK] Processing PDF memory redaction (operation_id: {operation_id})")

                self._draw_redaction_boxes(redaction_mapping, remove_images)
                self._sanitize_document()

                output_buffer = io.BytesIO()
                self.doc.save(output_buffer)
                self.doc.close()

                output_buffer.seek(0)
                redacted_content = output_buffer.getvalue()

                processing_time = time.time() - start_time

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
            SecurityAwareErrorHandler.log_processing_error(e, "pdf_memory_redaction", self.file_path)
            raise

    def _draw_redaction_boxes(self, redaction_mapping: Dict[str, Any], remove_images: bool) -> None:
        """
        Process the redaction mapping and apply redaction boxes on all specified pages.

        For large documents, pages are processed in batches to reduce memory usage.

        Args:
            redaction_mapping: Dictionary with redaction information.
            remove_images: If True, detect and redact images on each page.
        """
        total_pages = len(self.doc)

        # Gather unique page numbers from the mapping.
        page_numbers = {page_info.get("page") for page_info in redaction_mapping.get("pages", [])
                        if page_info.get("page") is not None}
        page_numbers = sorted(page_numbers)

        try:
            if len(page_numbers) > 10:
                # Process pages in batches.
                for batch_start in range(0, len(page_numbers), self.page_batch_size):
                    batch_end = min(batch_start + self.page_batch_size, len(page_numbers))
                    batch_page_numbers = page_numbers[batch_start:batch_end]
                    log_info(f"[OK] Processing redaction batch for pages {batch_page_numbers}")
                    self._process_redaction_pages_batch(redaction_mapping, batch_page_numbers, total_pages, remove_images)
                    import gc
                    gc.collect()
            else:
                self._process_all_redaction_pages(redaction_mapping, total_pages, remove_images)
        except Exception as e:
            log_error(f"[ERROR] Error while drawing redaction boxes: {str(e)}")
            raise

    def _process_redaction_page(self, page_num: int, page_info: Dict[str, Any], total_pages: int, remove_images: bool = False) -> None:
        """
        Process a single page for redaction based on the mapping.

        This method handles both text-based sensitive items and, if enabled, image redaction.
        If remove_images is True, it uses the PDFTextExtractor.extract_images_on_page method to detect
        images on the page and adds a black redaction annotation over each detected image. A log
        message is recorded to notify that the image(s) were detected and redacted.

        Args:
            page_num: The page number (1-indexed).
            page_info: The redaction mapping for this page.
            total_pages: Total number of pages in the document.
            remove_images: If True, detect and redact images on the page.
        """
        sensitive_items = page_info.get("sensitive", [])
        if not sensitive_items:
            log_info(f"[OK] No sensitive items found on page {page_num}.")
            return

        if page_num < 1 or page_num > total_pages:
            log_warning(f"[WARNING] Page number {page_num} is out of range for document with {total_pages} pages. Skipping.")
            return

        try:
            page = self.doc[page_num - 1]
            # Process text-based sensitive items.
            for item in sensitive_items:
                self._process_sensitive_item(page, item, page_num)

            # If image redaction is enabled, detect images and add redaction annotations.
            if remove_images:
                image_boxes = PDFTextExtractor.extract_images_on_page(page)
                if image_boxes:
                    for img in image_boxes:
                        rect = pymupdf.Rect(img["x0"], img["y0"], img["x1"], img["y1"])
                        page.add_redact_annot(rect, fill=(0, 0, 0))
                    log_info(f"[OK] ✅ Detected and redacted {len(image_boxes)} image(s) on page {page_num}")

            # Apply all redactions on the page.
            page.apply_redactions()
        except Exception as e:
            SecurityAwareErrorHandler.log_processing_error(e, "pdf_redaction_page", f"{self.file_path}:page_{page_num}")

    def _process_all_redaction_pages(self, redaction_mapping: Dict[str, Any], total_pages: int, remove_images: bool) -> None:
        """
        Process redactions for all pages specified in the mapping.

        Args:
            redaction_mapping: Dictionary with redaction information.
            total_pages: Total number of pages in the document.
            remove_images: If True, detect and redact images on each page.
        """
        for page_info in redaction_mapping.get("pages", []):
            page_num = page_info.get("page")
            if page_num is None:
                continue
            self._process_redaction_page(page_num, page_info, total_pages, remove_images)

    def _process_redaction_pages_batch(self, redaction_mapping: Dict[str, Any],
                                       page_numbers: List[int], total_pages: int, remove_images: bool) -> None:
        """
        Process a batch of pages for redaction to optimize memory usage.

        This method reduces cognitive complexity by delegating per-page processing to
        the helper method _process_redaction_page.

        Args:
            redaction_mapping: Dictionary with redaction information.
            page_numbers: List of page numbers (1-indexed) in the current batch.
            total_pages: Total number of pages in the document.
            remove_images: If True, detect and redact images on each page.
        """
        # Build a mapping for quick lookup.
        page_mapping = {page_info.get("page"): page_info
                        for page_info in redaction_mapping.get("pages", [])
                        if page_info.get("page") in page_numbers}

        batch_start_time = time.time()
        max_batch_time = 300.0  # 300 seconds max per batch

        for page_num in page_numbers:
            if time.time() - batch_start_time > max_batch_time:
                log_warning(f"[WARNING] Batch processing timeout reached after {(time.time()-batch_start_time):.2f}s, skipping remaining pages")
                break

            page_info = page_mapping.get(page_num)
            if page_info:
                self._process_redaction_page(page_num, page_info, total_pages, remove_images)

    def _process_sensitive_item(self, page: pymupdf.Page, item: Dict[str, Any], page_num: int) -> None:
        """
        Process a single sensitive item and create redaction annotations on the page.

        Args:
            page: The PyMuPDF Page object.
            item: Dictionary describing the sensitive item.
            page_num: The page number (1-indexed) where the item is located.
        """
        try:
            if "boxes" in item and isinstance(item["boxes"], list):
                for box in item["boxes"]:
                    rect = pymupdf.Rect(box["x0"], box["y0"], box["x1"], box["y1"])
                    page.add_redact_annot(rect, fill=(0, 0, 0), text=item.get("entity_type"))
                    log_info(f"[OK] Redacting entity {item.get('entity_type')} on page {page_num}")
            elif "bbox" in item:
                bbox = item["bbox"]
                rect = pymupdf.Rect(bbox["x0"], bbox["y0"], bbox["x1"], bbox["y1"])
                page.add_redact_annot(rect, fill=(0, 0, 0))
        except Exception as e:
            SecurityAwareErrorHandler.log_processing_error(e, "pdf_process_sensitive_item", f"{self.file_path}:page_{page_num}")

    def _sanitize_document(self) -> None:
        """
        Apply additional security measures to the document:
            - Remove metadata
            - Clean hidden content and delete non-redaction annotations
            - Scrub embedded files, JavaScript, and extra objects
        """
        try:
            self.doc.set_metadata({})
            for page in self.doc:
                page.clean_contents()
                for annot in page.annots() or []:
                    if annot.type[0] != 8:  # Preserve redaction annotations (type 8)
                        page.delete_annot(annot)
            self.doc.scrub()
        except Exception as e:
            SecurityAwareErrorHandler.log_processing_error(e, "pdf_document_sanitize", self.file_path)

    def close(self) -> None:
        """Close the document and free resources."""
        try:
            if self.doc is not None:
                if not self.doc.is_closed:
                    self.doc.close()
                self.doc = None
        except Exception as e:
            SecurityAwareErrorHandler.log_processing_error(e, "pdf_document_close", self.file_path)