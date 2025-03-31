import string
from typing import List, Dict, Any
from backend.app.utils.logging.logger import log_debug

class PDFSearcher:
    """
    Class for searching specific terms within extracted PDF text.

    This implementation assumes the extracted data already provides word-level details,
    including coordinates (x0, y0, x1, y1). For each page, each word is examined;
    if the word's text (after stripping punctuation) exactly matches any of the provided
    search terms (case-sensitive), its bounding box and original text are recorded.
    """
    def __init__(self, extracted_data: Dict[str, Any]):
        self.extracted_data = extracted_data

    def search_terms(self, search_terms: List[str]) -> Dict[str, Any]:
        """
        Searches for the provided search_terms within the extracted data using exact (case-sensitive)
        matching (ignoring leading/trailing punctuation).

        For each page, each word is checked against a precomputed set of search terms.
        Punctuation is stripped from the beginning and end of each word before comparison.
        If a match is found, the word's bounding box is retrieved (or constructed) and its
        original text is preserved in the output.

        Returns:
            A dictionary with:
            - "pages": A list where each item corresponds to a page containing matches.
              Each page item is a dictionary with:
                - "page": the page number.
                - "matches": a list of dictionaries each containing:
                    - "bbox": the bounding box of the matched word.
                    - "original_text": the matched word in its original form.
            - "match_count": Total number of matches found.
        """
        try:
            log_debug("✅ Starting search in PDFSearcher")
            log_debug(f"✅ Search terms: {search_terms}")

            pages_results = []
            total_matches = 0

            # Use search terms as provided (trimmed, but preserve case)
            search_set = {term.strip() for term in search_terms if term.strip()}

            # Iterate through each page.
            for page in self.extracted_data.get("pages", []):
                page_number = page.get("page")
                page_matches = []
                for word in page.get("words", []):
                    word_text = (word.get("text") or "").strip()
                    # Remove punctuation from the beginning and end.
                    cleaned_word_text = word_text.strip(string.punctuation)
                    if cleaned_word_text in search_set:
                        # Retrieve bounding box; if not available, construct one from coordinate fields.
                        bbox = word.get("bbox")
                        if not bbox:
                            bbox = {
                                "x0": word.get("x0"),
                                "y0": word.get("y0"),
                                "x1": word.get("x1"),
                                "y1": word.get("y1")
                            }
                        page_matches.append({
                            "bbox": bbox,
                        })
                if page_matches:
                    pages_results.append({
                        "page": page_number,
                        "matches": page_matches
                    })
                    total_matches += len(page_matches)

            log_debug(f"✅ Total matches found: {total_matches}")
            return {
                "pages": pages_results,
                "match_count": total_matches
            }
        except Exception as e:
            log_debug(f"Error in PDFSearcher.search_terms: {str(e)}")
            return {
                "pages": [],
                "match_count": 0
            }