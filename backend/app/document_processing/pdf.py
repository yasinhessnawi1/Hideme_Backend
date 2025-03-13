"""
PDF document processing implementations.
"""
"""
Updated PDF document processing implementation to filter empty pages.
"""
import os
from typing import Dict, Any, List, Union

import pymupdf

from backend.app.domain.interfaces import DocumentExtractor, DocumentRedactor
from backend.app.utils.logger import log_info, log_warning, log_error


class PDFTextExtractor(DocumentExtractor):
    """
    A service for extracting text with positional information from PDF documents,
    with improved handling for empty pages.
    """

    def __init__(self, pdf_input: Union[str, pymupdf.Document]):
        """
        Initialize PDFTextExtractor.

        Args:
            pdf_input: File path to a PDF (str) or a PyMuPDF Document instance
        """
        if isinstance(pdf_input, str):
            self.pdf_document = pymupdf.open(pdf_input)
        elif isinstance(pdf_input, pymupdf.Document):
            self.pdf_document = pdf_input
        else:
            raise ValueError("Invalid input! Expected a file path or a PyMuPDF Document.")

    def extract_text_with_positions(self) -> Dict[str, Any]:
        """
        Extract text from the PDF document, page by page, with positional information.
        Automatically filters out empty pages.

        Returns:
            A dictionary with page-wise extracted data, excluding empty pages
        """
        extracted_data = {"pages": []}
        empty_pages = []
        total_pages = len(self.pdf_document)

        try:
            for page_num in range(total_pages):
                page = self.pdf_document[page_num]
                log_info(f"[OK] Processing page {page_num + 1}")

                # Extract words with positions
                page_words = self._extract_page_words(page)

                # Check if page is empty (no words with content)
                if not page_words:
                    empty_pages.append(page_num + 1)
                    log_info(f"[OK] Skipping empty page {page_num + 1}")
                    continue

                # Add page data to result
                extracted_data["pages"].append({
                    "page": page_num + 1,
                    "words": page_words
                })

            # Log summary of empty pages
            if empty_pages:
                log_warning(f"[OK] Skipped {len(empty_pages)} empty pages: {empty_pages}")

            # Add metadata about empty pages and document statistics
            extracted_data["total_document_pages"] = total_pages
            extracted_data["empty_pages"] = empty_pages
            extracted_data["content_pages"] = total_pages - len(empty_pages)

        except Exception as e:
            log_error(f"[OK] Failed to extract text with positions: {e}")
            return {"pages": [], "error": str(e)}

        log_info(
            f"[OK] Text extraction completed successfully. Extracted {len(extracted_data['pages'])} pages with content.")
        return extracted_data

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

        return page_words

    def close(self) -> None:
        """Close the PDF document and free resources."""
        self.pdf_document.close()

class PDFRedactionService(DocumentRedactor):
    """
    A service for applying redactions to PDF documents.
    """

    def __init__(self, pdf_path: str):
        """
        Open the PDF document to be redacted.

        Args:
            pdf_path: Path to the PDF file
        """
        self.doc = pymupdf.open(pdf_path)
        log_info(f"[OK]Opened PDF file: {pdf_path}")

    def apply_redactions(self, redaction_mapping: Dict[str, Any], output_path: str) -> str:
        """
        Apply redactions to the PDF based on the provided redaction mapping.

        Args:
            redaction_mapping: Dictionary containing sensitive spans with bounding boxes
            output_path: Path to save the redacted PDF

        Returns:
            Path to the redacted document
        """
        # Apply redactions by drawing redaction boxes
        self._draw_redaction_boxes(redaction_mapping)

        # Apply additional security measures
        self._sanitize_document()

        # Save and close the document
        self.doc.save(output_path)
        self.doc.close()

        log_info(f"[OK]Redacted PDF saved as {output_path}")
        return output_path

    def _draw_redaction_boxes(self, redaction_mapping: Dict[str, Any]) -> None:
        """
        Draw redaction boxes on the PDF document based on the provided mapping.

        Args:
            redaction_mapping: Dictionary containing sensitive spans with bounding boxes
        """
        for page_info in redaction_mapping.get("pages", []):
            page_num = page_info.get("page")
            sensitive_items = page_info.get("sensitive", [])

            if not sensitive_items:
                log_info(f"[OK]No sensitive items found on page {page_num}.")
                continue

            # PyMuPDF pages are 0-indexed
            page = self.doc[page_num - 1]

            for item in sensitive_items:
                self._process_sensitive_item(page, item, page_num)

            # Apply redactions on the page
            page.apply_redactions()

    def _process_sensitive_item(self, page: pymupdf.Page, item: Dict[str, Any], page_num: int) -> None:
        """
        Process a single sensitive item and create redaction annotations.

        Args:
            page: PyMuPDF Page object
            item: Sensitive item dictionary
            page_num: Page number (1-indexed)
        """
        # If the item contains a list of boxes, process them all
        if "boxes" in item and isinstance(item["boxes"], list):
            for box in item["boxes"]:
                rect = pymupdf.Rect(box["x0"], box["y0"], box["x1"], box["y1"])
                # Add a redaction annotation with a black fill
                page.add_redact_annot(rect, fill=(0, 0, 0), text=item.get("entity_type"))
                log_info(f"[OK]Redacting entity {item.get('entity_type')} on page {page_num} at {rect}")

        # Handle single bbox case (fallback)
        elif "bbox" in item:
            bbox = item["bbox"]
            rect = pymupdf.Rect(bbox["x0"], bbox["y0"], bbox["x1"], bbox["y1"])
            page.add_redact_annot(rect, fill=(0, 0, 0))

    def _sanitize_document(self) -> None:
        """
        Apply additional security measures to the document:
        - Remove metadata
        - Remove hidden content and annotations
        - Remove embedded files, JavaScript, and extra objects
        """
        # Remove metadata
        self.doc.set_metadata({})

        # Remove hidden content and annotations
        for page in self.doc:
            page.clean_contents()
            for annot in page.annots() or []:
                page.delete_annot(annot)

        # Remove embedded files, JS, and extra objects
        self.doc.scrub()