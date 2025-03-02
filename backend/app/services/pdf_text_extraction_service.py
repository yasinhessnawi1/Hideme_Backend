from backend.app.utils.logger import default_logger as logging
import pymupdf


class PDFTextExtractor:
    """
    A class dedicated to extracting text along with positional information from a PDF document.
    Accepts either a file path (str) or a PyMuPDF Document instance.
    """

    def __init__(self, pdf_input):
        """
        Initialize PDFTextExtractor.

        :param pdf_input: File path to a PDF (str) or a PyMuPDF Document instance.
        :raises ValueError: If pdf_input is neither a string nor a PyMuPDF Document.
        """
        if isinstance(pdf_input, str):
            self.pdf_document = pymupdf.open(pdf_input)
        elif isinstance(pdf_input, pymupdf.Document):
            self.pdf_document = pdf_input
        else:
            raise ValueError("Invalid input! Expected a file path or a PyMuPDF Document.")

    def extract_text_with_positions(self):
        """
        Extracts text from the PDF document, page by page, along with positional information.

        Uses PyMuPDF's "words" extraction method, which returns a list of tuples
        with coordinates and text. The output is a dictionary with one entry per page.

        :return: A dictionary with page-wise extracted fisk_data.
                 Example:
                 {
                   "pages": [
                     {
                       "page": 1,
                       "words": [
                         {"text": "Example", "x0": 50, "y0": 100, "x1": 100, "y1": 120},
                         ...
                       ]
                     },
                     ...
                   ]
                 }
        """
        extracted_data = {"pages": []}
        try:
            for page_num in range(len(self.pdf_document)):
                page = self.pdf_document[page_num]
                logging.info(f"Processing page {page_num + 1}")
                page_words = []
                # get_text("words") returns a list of tuples:
                # (x0, y0, x1, y1, word, block_no, line_no, word_no)
                words = page.get_text("words")
                for word in words:
                    x0, y0, x1, y1, text, *_ = word
                    if text.strip():
                        page_words.append({
                            "text": text.strip(),
                            "x0": x0,
                            "y0": y0,
                            "x1": x1,
                            "y1": y1
                        })
                extracted_data["pages"].append({
                    "page": page_num + 1,
                    "words": page_words
                })
        except Exception as e:
            logging.error(f"Failed to extract text with positions: {e}")
            return {}

        logging.info("Text extraction with positions completed successfully.")
        return extracted_data

    def close(self):
        """Close the PDF document."""
        self.pdf_document.close()
