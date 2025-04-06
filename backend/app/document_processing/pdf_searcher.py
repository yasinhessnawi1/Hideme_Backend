import asyncio
import string
from typing import List, Dict, Any, Tuple

from backend.app.configs.gemini_config import (
    AI_SEARCH_PROMPT_HEADER,
    AI_SEARCH_PROMPT_FOOTER,
    AI_SEARCH_SYSTEM_INSTRUCTION,
    AI_SEARCH_GEMINI_AVAILABLE_ENTITIES
)
from backend.app.utils.helpers.gemini_helper import gemini_helper
from backend.app.utils.logging.logger import log_debug
from backend.app.utils.validation.sanitize_utils import deduplicate_bbox


class PDFSearcher:
    """
    PDFSearcher is responsible for finding specific search terms within text extracted from PDFs.

    It supports two search modes:
      1. AI Search Mode: Uses the Gemini API with a custom prompt to identify entities within the text.
         - Reconstructs each page's full text and builds a mapping of words to their character indices and bounding boxes.
         - Constructs a custom prompt and sends it to the Gemini API.
         - Processes the API's JSON response by splitting the returned original text into tokens.
         - Remaps each token using the page mapping so that each token match yields its bounding box.

      2. Fallback Word-based Matching: Performs direct word matching (case_sensitive or not) against the extracted text.
         - Iterates over each word on a page and checks for a match against the provided search terms.

    Robust error handling is built-in to ensure that exceptions during the search process are caught and logged.
    """

    def __init__(self, extracted_data: Dict[str, Any]):
        """
        Initialize the PDFSearcher with extracted PDF data.

        Args:
            extracted_data (Dict[str, Any]): Extracted data containing pages, words, and metadata.
        """
        self.extracted_data = extracted_data
        self.gemini_helper = gemini_helper

    @staticmethod
    def _build_search_set(search_terms: List[str], case_sensitive: bool) -> set:
        """
        Build a set of search terms with appropriate case adjustments.

        Args:
            search_terms (List[str]): List of search terms.
            case_sensitive (bool): Whether matching should be case_sensitive.

        Returns:
            set: Processed set of search terms.
        """
        if case_sensitive:
            return {term.strip() for term in search_terms if term.strip()}
        return {term.strip().lower() for term in search_terms if term.strip()}

    @staticmethod
    def _word_matches(word_text: str, search_set: set, case_sensitive: bool, ai_search: bool) -> bool:
        """
        Check if a given word matches any term in the search set.

        Args:
            word_text (str): The word text.
            search_set (set): The set of search terms.
            case_sensitive (bool): Whether matching is case_sensitive.
            ai_search (bool): Flag indicating AI search mode (which bypasses direct matching).

        Returns:
            bool: True if the word is a match, False otherwise.
        """
        cleaned = word_text.strip(string.punctuation)
        if ai_search:
            # In AI search mode, matching is handled by the Gemini API.
            return False
        if case_sensitive:
            return cleaned in search_set
        return cleaned.lower() in search_set

    @staticmethod
    def _build_page_text_and_mapping(words: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
        """
        Reconstruct full page text and create a mapping of each word to its indices and bounding box.

        Args:
            words (List[Dict[str, Any]]): List of word dictionaries from a page.

        Returns:
            Tuple[List[Dict[str, Any]], str]: A tuple with a mapping list and the full page text.
        """
        mapping = []
        page_text_parts = []
        current_index = 0
        for word in words:
            text = word.get("text", "")
            start_idx = current_index
            end_idx = start_idx + len(text)
            bbox = word.get("bbox") or {
                "x0": word.get("x0"),
                "y0": word.get("y0"),
                "x1": word.get("x1"),
                "y1": word.get("y1")
            }
            mapping.append({
                "start": start_idx,
                "end": end_idx,
                "bbox": bbox,
                "text": text
            })
            page_text_parts.append(text)
            current_index = end_idx + 1  # account for the space between words
        page_text = " ".join(page_text_parts)
        return mapping, page_text

    @staticmethod
    def _build_ai_prompt(search_terms: List[str], page_text: str) -> str:
        """
        Construct a custom prompt for the Gemini API using AI search components.

        Args:
            search_terms (List[str]): List of search terms.
            page_text (str): The full text of the page.

        Returns:
            str: The constructed prompt.
        """
        return (
            f"{AI_SEARCH_PROMPT_HEADER}\n"
            f"{AI_SEARCH_GEMINI_AVAILABLE_ENTITIES}\n"
            f"User Query: {' '.join(search_terms)}\n"
            f"### **Text to Analyze:**\n"
            f"{page_text}\n"
            f"{AI_SEARCH_PROMPT_FOOTER}"
        )

    async def _process_ai_page(self, page: Dict[str, Any], search_terms: List[str], case_sensitive: bool) -> Tuple[
        Dict[str, Any], int]:
        """
        Process one page using AI search mode.

        This method reconstructs the page text, builds a mapping, sends the custom prompt to the Gemini API,
        parses the response, and remaps detected entities into bounding box matches.

        Args:
            page (Dict[str, Any]): Data for a single page.
            search_terms (List[str]): List of search terms.
            case_sensitive (bool): Whether matching should be case_sensitive.

        Returns:
            Tuple[Dict[str, Any], int]: A tuple where the first element is a dictionary with the page number and matches,
                                        and the second element is the count of matches on that page.
        """
        try:
            page_number = page.get("page")
            words = page.get("words", [])
            mapping, page_text = self._build_page_text_and_mapping(words)
            # Combine individual search terms into one sentence.
            combined_query = " ".join(search_terms)

            # Build the prompt using the combined query.
            prompt = self._build_ai_prompt([combined_query], page_text)
            # Pass the combined query as a single-element list to requested_entities.
            response = await self.gemini_helper.send_request(
                prompt,
                requested_entities=[combined_query],
                raw_prompt=True,
                system_instruction_override=AI_SEARCH_SYSTEM_INSTRUCTION
            )
            parsed_response = self.gemini_helper.parse_response(response)
            page_matches = []
            if parsed_response and "pages" in parsed_response:
                page_matches = [
                    {
                        "bbox": token_entity["bbox"],
                        "original_text": token_entity.get("original_text", "")
                    }
                    for page_data in parsed_response["pages"]
                    for text_obj in page_data.get("text", [])
                    for entity in text_obj.get("entities", [])
                    for token_entity in self._split_and_remap_entity(entity, mapping, case_sensitive)
                ]
                # Deduplicate based on bbox.
                page_matches = deduplicate_bbox(page_matches)
            return {"page": page_number, "matches": page_matches}, len(page_matches)
        except Exception as e:
            log_debug(f"Error processing AI page {page.get('page')}: {e}")
            return {"page": page.get("page"), "matches": []}, 0

    def _process_fallback_page(self, page: Dict[str, Any], search_set: set, case_sensitive: bool) -> Tuple[
        Dict[str, Any], int]:
        """
        Process one page using fallback word-based matching.

        Iterates over each word in the page and checks for a match against the search set.

        Args:
            page (Dict[str, Any]): Data for a single page.
            search_set (set): Set of processed search terms.
            case_sensitive (bool): Whether matching should be case_sensitive.

        Returns:
            Tuple[Dict[str, Any], int]: A tuple where the first element is a dictionary with the page number and matches,
                                        and the second element is the count of matches on that page.
        """
        try:
            page_number = page.get("page")
            page_matches = []
            for word in page.get("words", []):
                word_text = (word.get("text") or "").strip()
                if self._word_matches(word_text, search_set, case_sensitive, ai_search=False):
                    bbox = word.get("bbox") or {
                        "x0": word.get("x0"),
                        "y0": word.get("y0"),
                        "x1": word.get("x1"),
                        "y1": word.get("y1")
                    }
                    page_matches.append({"bbox": bbox, "original_text": word_text,})
            return {"page": page_number, "matches": page_matches}, len(page_matches)
        except Exception as e:
            log_debug(f"Error processing fallback page {page.get('page')}: {e}")
            return {"page": page.get("page"), "matches": []}, 0

    async def search_terms(self, search_terms: List[str], case_sensitive: bool = False, ai_search: bool = False) -> \
    Dict[str, Any]:
        """
        Search for the specified search terms in the extracted PDF data.

        In AI search mode:
          - Reconstructs each page's text and builds a word mapping.
          - Constructs a custom Gemini prompt and sends it.
          - Processes the Gemini API response by splitting the returned text into tokens.
          - Remaps each token to its original location and extracts its bounding box.

        In fallback mode:
          - Directly matches words against the search terms using simple text matching.

        Args:
            search_terms (List[str]): List of search terms to locate.
            case_sensitive (bool): Whether the search should be case_sensitive.
            ai_search (bool): Whether to use AI search (via Gemini API) or fallback matching.

        Returns:
            Dict[str, Any]: A dictionary containing:
                - "pages": A list of pages with their matched entities (bounding boxes).
                - "match_count": Total number of matches found.
        """
        pages_results = []
        total_matches = 0
        try:
            if ai_search:
                log_debug("Using AI search with custom prompt for entity extraction.")
                # Process pages concurrently
                tasks = [
                    self._process_ai_page(page, search_terms, case_sensitive)
                    for page in self.extracted_data.get("pages", [])
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, Exception):
                        continue
                    page_result, count = result
                    pages_results.append(page_result)
                    total_matches += count
            else:
                search_set = self._build_search_set(search_terms, case_sensitive)
                for page in self.extracted_data.get("pages", []):
                    page_result, count = self._process_fallback_page(page, search_set, case_sensitive)
                    pages_results.append(page_result)
                    total_matches += count
            log_debug(f"✅ Total matches found: {total_matches}")
            return {"pages": pages_results, "match_count": total_matches}
        except Exception as e:
            log_debug(f"Error during search_terms: {e}")
            return {"pages": [], "match_count": 0}

    @staticmethod
    def _split_and_remap_entity(entity: Dict[str, Any], mapping: List[Dict[str, Any]], case_sensitive: bool) -> List[
        Dict[str, Any]]:
        """
        Split a Gemini entity's original text into tokens and remap each token to its corresponding location.

        Uses a comparison lambda to handle both case-sensitive and case-insensitive matching in a uniform manner.

        Args:
            entity (Dict[str, Any]): The entity from Gemini containing "original_text".
            mapping (List[Dict[str, Any]]): A list mapping tokens to their positions and bounding boxes.
            case_sensitive (bool): Whether matching is case_sensitive.

        Returns:
            List[Dict[str, Any]]: A list of remapped token entities, each with:
                - "entity_type": The original entity type.
                - "original_text": The token text.
                - "start": Start index of the token in the page text.
                - "end": End index of the token in the page text.
                - "bbox": The bounding box for the token.
                - "score": The confidence score from Gemini.
                - "case_sensitive": The case sensitivity flag.
        """
        token_entities = []
        entity_query = entity.get("original_text", "")
        if not entity_query:
            return token_entities

        compare = (lambda a, b: a == b) if case_sensitive else (lambda a, b: a.lower() == b.lower())
        for token in entity_query.split():
            for m in mapping:
                mapping_text = m.get("text", "")
                if compare(mapping_text, token):
                    token_entities.append({
                        "entity_type": entity.get("entity_type"),
                        "original_text": mapping_text,
                        "start": m.get("start"),
                        "end": m.get("end"),
                        "bbox": m.get("bbox"),
                        "score": entity.get("score"),
                        "case_sensitive": case_sensitive
                    })

        return token_entities