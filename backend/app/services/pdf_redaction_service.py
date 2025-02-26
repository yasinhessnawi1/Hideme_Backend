
import pymupdf


from backend.app.utils.logger import default_logger as logger


class PDFRedactionService:
    def __init__(self, pdf_path):
        """
        Opens the PDF document to be redacted.
        """
        self.doc = pymupdf.open(pdf_path)
        logger.info(f"Opened PDF file: {pdf_path}")

    def apply_redactions(self, redaction_mapping, output_path):
        """
        Applies redactions to the PDF based on the provided redaction mapping.

        :param redaction_mapping: Dictionary containing sensitive spans with bounding boxes.
                                  Expected structure:
                                  {
                                    "pages": [
                                      {
                                        "page": <page_number>,
                                        "sensitive": [
                                          {
                                            "entity_type": ...,
                                            "start": ...,
                                            "end": ...,
                                            "score": ...,
                                            "boxes": [ { "x0": ..., "y0": ..., "x1": ..., "y1": ... }, ... ]
                                          }
                                        ]
                                      },
                                      ...
                                    ]
                                  }
        :param output_path: Path to save the redacted PDF.
        :return: output_path if redaction is successful.
        """
        for page_info in redaction_mapping.get("pages", []):
            page_num = page_info.get("page")
            sensitive_items = page_info.get("sensitive", [])
            if not sensitive_items:
                logger.info(f"No sensitive items found on page {page_num}.")
                continue

            # PyMuPDF pages are 0-indexed.
            page = self.doc[page_num - 1]
            for item in sensitive_items:
                # If the item contains a list of boxes (from our updated mapping), process them all.
                if "boxes" in item and isinstance(item["boxes"], list):
                    for box in item["boxes"]:
                        rect = pymupdf.Rect(box["x0"], box["y0"], box["x1"], box["y1"])
                        # Add a redaction annotation with a black fill.
                        page.add_redact_annot(rect, fill=(0, 0, 0), text=item.get("entity_type"))
                        logger.info("Redacting entity %s on page %d at %s", item.get("entity_type"), page_num, rect)
                # Fallback: if a single "bbox" key exists
                elif "bbox" in item:
                    bbox = item["bbox"]
                    rect = pymupdf.Rect(bbox["x0"], bbox["y0"], bbox["x1"], bbox["y1"])
                    page.add_redact_annot(rect, fill=(0, 0, 0), text=item.get("entity_type"), text_color=(1, 1, 1))
                    # logger.info("Redacting entity %s on page %d at %s", item.get("entity_type"), page_num, rect)

            # Apply redactions on the page.
            page.apply_redactions()

        self.doc.save(output_path)
        self.doc.close()
        logger.info(f"Redacted PDF saved as {output_path}")
        return output_path
