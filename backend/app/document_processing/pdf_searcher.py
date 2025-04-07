"""
PDFSearcher is responsible for finding specific search terms within text extracted from PDFs.

It supports two search modes:
  1. AI Search Mode: Uses the Gemini API with a custom prompt to identify entities within the text.
     - It reconstructs each page's full text and builds a mapping of words to their character indices and bounding boxes.
     - It constructs a custom prompt and sends it to the Gemini API.
     - It processes the API's JSON response by splitting the returned original text into tokens.
     - It remaps each token using the page mapping so that each token match yields its bounding box.
  2. Fallback Word-based Matching: Performs direct word matching (case_sensitive or not) against the extracted text.
     - It iterates over each word on a page and checks for a match against the provided search terms.

Robust error handling is built-in to ensure that exceptions during the search process are caught, securely logged,
and do not crash the entire search operation.
"""

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
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler


class PDFSearcher:
    def __init__(self, extracted_data: Dict[str, Any]):
        """
        Initialize the PDFSearcher with extracted PDF data.

        Args:
            extracted_data (Dict[str, Any]): Extracted data containing pages, words, and metadata.
        """
        # Save the extracted PDF data (including pages, words, and metadata)
        self.extracted_data = extracted_data
        # Initialize the helper instance used for AI-based search via Gemini API.
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
        # Remove extra spaces from each term and conditionally adjust for case sensitivity.
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
        # Remove any punctuation from the word to ensure clean matching.
        cleaned = word_text.strip(string.punctuation)
        if ai_search:
            # In AI search mode, matching is handled by the Gemini API so bypass direct matching.
            return False
        # Compare words based on the case sensitivity flag.
        if case_sensitive:
            return cleaned in search_set
        return cleaned.lower() in search_set

    @staticmethod
    def _build_page_text_and_mapping(words: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
        """
        Reconstruct full page text and create a mapping of each word to its indices and bounding box.

        This method goes through each word in a page, determines its start and end indices in the full text,
        and collects its bounding box (if provided or built from coordinates). The mapping list is used later
        to remap detected tokens back to their location on the page.

        Args:
            words (List[Dict[str, Any]]): List of word dictionaries from a page.

        Returns:
            Tuple[List[Dict[str, Any]], str]: A tuple with a mapping list and the full page text.
        """
        mapping = []  # List to store mapping info for each word.
        page_text_parts = []  # List to accumulate text parts of the page.
        current_index = 0  # Start index for the first word.
        # Iterate over all words on the page.
        for word in words:
            text = word.get("text", "")
            start_idx = current_index
            end_idx = start_idx + len(text)
            # Retrieve bounding box from the word; if not found, use individual coordinate keys.
            bbox = word.get("bbox") or {
                "x0": word.get("x0"),
                "y0": word.get("y0"),
                "x1": word.get("x1"),
                "y1": word.get("y1")
            }
            # Append mapping information for this word.
            mapping.append({
                "start": start_idx,
                "end": end_idx,
                "bbox": bbox,
                "text": text
            })
            # Add the word's text to the page text parts.
            page_text_parts.append(text)
            # Update current index (adding one extra character for the space that will be inserted).
            current_index = end_idx + 1
        # Join all text parts with a space to form the full page text.
        page_text = " ".join(page_text_parts)
        return mapping, page_text

    @staticmethod
    def _build_ai_prompt(search_terms: List[str], page_text: str) -> str:
        """
        Construct a custom prompt for the Gemini API using AI search components.

        This prompt includes header and footer instructions, the available entity definitions, and the text to analyze.
        It also embeds the user's search query to provide context to the Gemini API.

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

        The method performs the following steps:
          - Retrieves the page number and its word list.
          - Reconstructs the full text of the page and creates a mapping for each word.
          - Combines the search terms into a single query and builds a custom prompt.
          - Sends the prompt to the Gemini API and awaits the response.
          - Parses the API response and extracts bounding boxes for matching tokens.
          - Deduplicates the matches based on their bounding boxes.

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
            # Build mapping from words to their positions and create the full text.
            mapping, page_text = self._build_page_text_and_mapping(words)
            # Combine individual search terms into one query string.
            combined_query = " ".join(search_terms)
            # Build the AI prompt for Gemini API using the combined query and page text.
            prompt = self._build_ai_prompt([combined_query], page_text)
            # Send the prompt to the Gemini API and await its response.
            response = await self.gemini_helper.send_request(
                prompt,
                requested_entities=[combined_query],
                raw_prompt=True,
                system_instruction_override=AI_SEARCH_SYSTEM_INSTRUCTION
            )
            # Parse the API response to retrieve the matched entities.
            parsed_response = self.gemini_helper.parse_response(response)
            page_matches = []
            if parsed_response and "pages" in parsed_response:
                # For each page in the response, iterate over text objects and their entities.
                page_matches = [
                    {
                        "bbox": token_entity["bbox"],
                    }
                    for page_data in parsed_response["pages"]
                    for text_obj in page_data.get("text", [])
                    for entity in text_obj.get("entities", [])
                    for token_entity in self._split_and_remap_entity(entity, mapping, case_sensitive)
                ]
                # Remove duplicate matches based on bounding box information.
                page_matches = deduplicate_bbox(page_matches)
            return {"page": page_number, "matches": page_matches}, len(page_matches)
        except Exception as e:
            # Log the error securely using SecurityAwareErrorHandler.
            SecurityAwareErrorHandler.log_processing_error(e, "PDFSearcher._process_ai_page",
                                                           f"page_{page.get('page')}")
            log_debug(f"Error processing AI page {page.get('page')}: {e}")
            # In case of an error, return an empty match set for the page.
            return {"page": page.get("page"), "matches": []}, 0

    def _process_fallback_page(self, page: Dict[str, Any], search_set: set, case_sensitive: bool) -> Tuple[
        Dict[str, Any], int]:
        """
        Process one page using fallback word-based matching.

        This method iterates over each word in the page and checks whether it matches any term in the search set.
        If a match is found, the word's bounding box is recorded.

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
            # Iterate through each word in the page.
            for word in page.get("words", []):
                word_text = (word.get("text") or "").strip()
                # Check if the word matches any of the search terms.
                if self._word_matches(word_text, search_set, case_sensitive, ai_search=False):
                    # Retrieve the bounding box for the word.
                    bbox = word.get("bbox") or {
                        "x0": word.get("x0"),
                        "y0": word.get("y0"),
                        "x1": word.get("x1"),
                        "y1": word.get("y1")
                    }
                    page_matches.append({"bbox": bbox})
            return {"page": page_number, "matches": page_matches}, len(page_matches)
        except Exception as e:
            # Log the error securely using SecurityAwareErrorHandler.
            SecurityAwareErrorHandler.log_processing_error(e, "PDFSearcher._process_fallback_page",
                                                           f"page_{page.get('page')}")
            log_debug(f"Error processing fallback page {page.get('page')}: {e}")
            # If an error occurs, return no matches for the page.
            return {"page": page.get("page"), "matches": []}, 0

    async def search_terms(self, search_terms: List[str], case_sensitive: bool = False, ai_search: bool = False) -> \
    Dict[str, Any]:
        """
        Search for the specified search terms in the extracted PDF data.

        Depending on the mode selected:
          - In AI search mode:
              * Each page is processed concurrently using the Gemini API.
              * A custom prompt is built and sent to the API.
              * The response is parsed and remapped to yield bounding boxes.
          - In fallback mode:
              * Each word is directly compared against the search terms using simple text matching.

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
                # Process each page concurrently using asynchronous tasks.
                tasks = [
                    self._process_ai_page(page, search_terms, case_sensitive)
                    for page in self.extracted_data.get("pages", [])
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                # Iterate over the results and accumulate matches.
                for result in results:
                    if isinstance(result, Exception):
                        # Log exception using SecurityAwareErrorHandler if an error occurred in a task.
                        SecurityAwareErrorHandler.log_processing_error(result, "PDFSearcher.search_terms", "ai_search")
                        continue
                    page_result, count = result
                    pages_results.append(page_result)
                    total_matches += count
            else:
                # For fallback mode, first build a set of search terms.
                search_set = self._build_search_set(search_terms, case_sensitive)
                for page in self.extracted_data.get("pages", []):
                    page_result, count = self._process_fallback_page(page, search_set, case_sensitive)
                    pages_results.append(page_result)
                    total_matches += count
            log_debug(f"✅ Total matches found: {total_matches}")
            return {"pages": pages_results, "match_count": total_matches}
        except Exception as e:
            # Log any errors that occur during the overall search process.
            SecurityAwareErrorHandler.log_processing_error(e, "PDFSearcher.search_terms", "global")
            log_debug(f"Error during search_terms: {e}")
            return {"pages": [], "match_count": 0}

    @staticmethod
    def _split_and_remap_entity(entity: Dict[str, Any], mapping: List[Dict[str, Any]], case_sensitive: bool) -> List[
        Dict[str, Any]]:
        """
        Split a Gemini entity's original text into tokens and remap each token to its corresponding location.

        For each token in the entity's text, this method checks against the mapping to determine its start/end indices
        and bounding box. The matching is done with consideration for case sensitivity.

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

        # Define a comparison function based on the case sensitivity flag.
        compare = (lambda a, b: a == b) if case_sensitive else (lambda a, b: a.lower() == b.lower())
        # Split the entity text into individual tokens.
        for token in entity_query.split():
            # Iterate over the mapping to find tokens that match.
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
