import string
import re

from typing import List, Dict, Any
from backend.app.utils.logging.logger import log_debug

class PDFSearcher:
    """
    Class for searching specific terms within extracted PDF text.

    This implementation assumes the extracted data already provides word-level details,
    including coordinates (x0, y0, x1, y1). For each page, each word is examined.
    Depending on the parameters, it can perform:
      - Exact (case-sensitive) matching.
      - Case-insensitive matching.
      - Regex-based matching (placeholder implementation).
    The original text is always preserved in the output.

    """
    def __init__(self, extracted_data: Dict[str, Any]):
        self.extracted_data = extracted_data

    @staticmethod
    def _build_search_set(search_terms: List[str], case_sensitive: bool) -> set:
        """Builds the search set based on case sensitivity."""
        if case_sensitive:
            return {term.strip() for term in search_terms if term.strip()}
        return {term.strip().lower() for term in search_terms if term.strip()}

    @staticmethod
    def _word_matches(word_text: str, search_set: set, case_sensitive: bool, regex: bool) -> bool:
        """
        Determines if the given word matches any of the search terms.
        The word is stripped of leading/trailing punctuation before matching.
        """
        cleaned = word_text.strip(string.punctuation)
        if regex:
            # Placeholder: try each pattern in the set.
            for pattern in search_set:
                if re.search(pattern, cleaned):
                    return True
            return False
        if case_sensitive:
            return cleaned in search_set
        return cleaned.lower() in search_set

    def search_terms(self, search_terms: List[str], case_sensitive: bool = False, regex: bool = False) -> Dict[str, Any]:
        """
        Searches for the provided search_terms within the extracted data using exact (case-sensitive)
        matching (ignoring leading/trailing punctuation).

        If regex is False:
          - If case_sensitive is True, performs exact case-sensitive matching (ignoring surrounding punctuation).
          - If case_sensitive is False, performs a case-insensitive match by comparing lowercased strings.
        If regex is True:
          - A placeholder is used (currently logging that regex search is not implemented) and
            falls back to non-regex behavior.


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
            if regex:
                log_debug("Regex search is not implemented yet; falling back to non-regex search.")

            search_set = self._build_search_set(search_terms, case_sensitive)
            pages_results = []
            total_matches = 0


            for page in self.extracted_data.get("pages", []):
                page_number = page.get("page")
                page_matches = []
                for word in page.get("words", []):
                    word_text = (word.get("text") or "").strip()
                    if self._word_matches(word_text, search_set, case_sensitive, regex):
                        bbox = word.get("bbox") or {
                            "x0": word.get("x0"),
                            "y0": word.get("y0"),
                            "x1": word.get("x1"),
                            "y1": word.get("y1")
                        }
                        page_matches.append({
                            "bbox": bbox,
   })
                if page_matches:
                    pages_results.append({"page": page_number, "matches": page_matches})
                    total_matches += len(page_matches)

            log_debug(f"✅ Total matches found: {total_matches}")
            return {"pages": pages_results, "match_count": total_matches}
        except Exception as e:
            log_debug(f"Error in PDFSearcher.search_terms: {str(e)}")
            return {"pages": [], "match_count": 0}
