"""
PDFSearcher Service Module

This service module provides the PDFSearcher class, which is responsible for finding
specific search terms within text extracted from PDFs. It supports two search modes:

  1. AI Search Mode: Uses the Gemini API with a custom prompt to identify entities within the text.
     - It reconstructs each page's full text and builds a mapping of words to their character indices and bounding boxes.
     - It constructs a custom prompt (including header, available entity definitions, and footer instructions)
       and sends it to the Gemini API.
     - It processes the APIs JSON response by tokenizing the returned text and remapping each token using the page mapping,
       so that each token match yields its corresponding bounding box.

  2. Fallback Word-Based Matching: Performs direct word matching (considering case sensitivity if needed)
     against the extracted text.
     - It iterates through each word on a page and checks for a match against the provided search terms.
     - When a match is found, the word’s bounding box is recorded.

The PDFSearcher service includes robust error handling to ensure that exceptions during the search process
are securely logged and do not crash the overall search operation.

Additional helper methods:
  - _build_search_set processes input search terms.
  - build_page_text_and_mapping reconstructs page text and creates a mapping of words to their text indices and bounding boxes.
  - _build_ai_prompt constructs the custom prompt for AI search.
  - _process_ai_page and _process_fallback_page handle per-page processing for the respective search modes.
  - _split_and_remap_entity splits and remaps an entity’s tokens back to their locations.
  - _group_consecutive_indices groups word indices for candidate phrase formation.
  - _process_single_word_occurrences and _process_multiword_occurrences handle occurrences of candidate phrases based on word count.

This service forms a core part of the system’s capability to perform intelligent text extraction and entity detection within PDF documents,
supporting both conventional keyword searches and AI-enhanced searches for improved contextual accuracy.
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
from backend.app.utils.helpers import TextUtils
from backend.app.utils.helpers.gemini_helper import gemini_helper
from backend.app.utils.logging.logger import log_debug
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.validation.sanitize_utils import deduplicate_bbox


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
            case_sensitive (bool): Whether matching should be case-sensitive.

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
            case_sensitive (bool): Whether matching is case-sensitive.
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
    def build_page_text_and_mapping(words: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
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
            case_sensitive (bool): Whether matching should be case-sensitive.

        Returns:
            Tuple[Dict[str, Any], int]: A tuple where the first element is a dictionary with the page number and matches,
                                        and the second element is the count of matches on that page.
        """
        try:
            page_number = page.get("page")
            words = page.get("words", [])
            # Build mapping from words to their positions and create the full text.
            mapping, page_text = self.build_page_text_and_mapping(words)
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
            case_sensitive (bool): Whether matching should be case-sensitive.

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
                    page_matches.append({
                        "bbox": bbox
                    })
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
            case_sensitive (bool): Whether the search should be case-sensitive.
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
            case_sensitive (bool): Whether matching is case-sensitive.

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

    @staticmethod
    def _word_center_in_bbox(word_bbox: Dict[str, Any], target_bbox: Dict[str, Any]) -> bool:
        """
        Check if the center of a word's bounding box lies within the given target bounding box,
        using Python's chained comparison syntax for clarity.

        Args:
            word_bbox (Dict[str, Any]): Bounding box for a word with keys "x0", "y0", "x1", "y1".
            target_bbox (Dict[str, Any]): Target bounding box with similar keys.

        Returns:
            bool: True if the center of word_bbox lies within target_bbox, else False.
        """
        # Calculate the horizontal center (cx) of the word's bounding box.
        cx = (word_bbox["x0"] + word_bbox["x1"]) / 2.0
        # Calculate the vertical center (cy) of the word's bounding box.
        cy = (word_bbox["y0"] + word_bbox["y1"]) / 2.0
        # Return True if the center (cx, cy) lies within the target bounding box.
        return target_bbox["x0"] <= cx <= target_bbox["x1"] and target_bbox["y0"] <= cy <= target_bbox["y1"]

    @staticmethod
    def _group_consecutive_indices(indices: List[int]) -> List[List[int]]:
        """
        Group a list of indices into sublist of consecutive numbers.
        For example, [1, 2, 5, 6, 7] becomes [[1, 2], [5, 6, 7]].

        Args:
            indices (List[int]): A list of integer indices.

        Returns:
            List[List[int]]: A list of lists, where each inner list contains consecutive indices.
        """
        # If there are no indices, return an empty list.
        if not indices:
            return []
        groups = []  # Initialize an empty list to hold groups.
        current_group = [indices[0]]  # Start the first group with the first index.
        # Loop over the remaining indices.
        for index in indices[1:]:
            # If the index is consecutive with the last one in current_group, add it.
            if index == current_group[-1] + 1:
                current_group.append(index)
            else:
                # Otherwise, save the current group and start a new one.
                groups.append(current_group)
                current_group = [index]
        # Add the final group to the list of groups.
        groups.append(current_group)
        return groups

    def _process_single_word_occurrences(self, page: Dict[str, Any], candidate_phrase: str) -> Tuple[
        Dict[str, Any], int]:
        """
        Process a page when the candidate phrase consists of a single word.
        It searches for words that exactly match the candidate phrase and returns their bounding boxes and text.

        Args:
            page (Dict[str, Any]): A page dictionary containing "page" and "words".
            candidate_phrase (str): The candidate phrase (a single word).

        Returns:
            Tuple[Dict[str, Any], int]: A tuple with:
                - A dictionary with the page number and a list of matching results.
                - The count of matches found.
        """
        # Retrieve the page number from the page data; default to "unknown" if not available.
        page_number = page.get("page", "unknown")
        page_matches = []  # Initialize an empty list for collecting matches.
        # Build the mapping of words along with their positions and bounding boxes.
        mapping, _ = self.build_page_text_and_mapping(page.get("words", []))
        # Iterate over each mapped word.
        for m in mapping:
            # If the word matches the candidate phrase exactly...
            if m["text"] == candidate_phrase:
                # ...append its bounding box and text to the match list.
                page_matches.append({
                    "bbox": m["bbox"],
                })
                log_debug(f"Page {page_number}: Found occurrence with bbox: {m['bbox']}")
        # Return a dictionary that includes the page number and its matches, along with the match count.
        return {"page": page_number, "matches": page_matches}, len(page_matches)

    @staticmethod
    def _process_multiword_occurrences(page: Dict[str, Any], candidate_phrase: str) -> Tuple[Dict[str, Any], int]:
        """
        Process a page when the candidate phrase consists of multiple words.
        It rebuilds the full page text using TextUtils, finds the offsets for the candidate phrase,
        maps these offsets back to bounding boxes, and merges them if necessary.

        Args:
            page (Dict[str, Any]): A page dictionary containing "page" and "words".
            candidate_phrase (str): The candidate phrase (multiple words).

        Returns:
            Tuple[Dict[str, Any], int]: A tuple with:
                - A dictionary with the page number and list of matches (each includes a merged bounding box and the matched substring).
                - The count of matches found.
        """
        # Retrieve the page number.
        page_number = page.get("page", "unknown")
        page_matches = []  # Initialize the list for storing match results.
        # Reconstruct the full text and obtain a mapping of character offsets to word bounding boxes.
        full_text, text_mapping = TextUtils.reconstruct_text_and_mapping(page.get("words", []))
        log_debug(f"Page {page_number}: full_text: '{full_text}'")
        # Calculate the character offset positions where the candidate phrase occurs.
        matches = TextUtils.recompute_offsets(full_text, candidate_phrase)
        log_debug(f"Page {page_number}: Found candidate phrase offsets: {matches}")
        # Process each occurrence of the candidate phrase.
        for s, e in matches:
            try:
                # Map the start and end offsets back to bounding boxes.
                bboxes = TextUtils.map_offsets_to_bboxes(full_text, text_mapping, (s, e))
            except Exception as exc:
                log_debug(f"Page {page_number}: Error in map_offsets_to_bboxes: {exc}")
                continue
            # If no bounding boxes were returned, skip this occurrence.
            if not bboxes:
                log_debug(f"Page {page_number}: No bounding boxes found for offsets {s}-{e}")
                continue
            # Merge multiple bounding boxes into one using the provided utility.
            merged_bbox = TextUtils.merge_bounding_boxes(bboxes)
            # Append the occurrence as a dictionary.
            page_matches.append({"bbox": merged_bbox})
            log_debug(f"Page {page_number}: Merged bounding box for offsets {s}-{e}: {merged_bbox}")
        # Return the page result along with the count of matches.
        return {"page": page_number, "matches": page_matches}, len(page_matches)

    def find_target_phrase_occurrences(self, target_bbox: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """
        Find all occurrences of a candidate phrase across pages based on a target bounding box.
        The process consists of three steps:
          1. For each page, collect candidate phrases by checking which words have centers within target_bbox
             and grouping adjacent words into phrases.
          2. Select the longest candidate phrase from all pages as the target phrase.
          3. For each page, process occurrences:
             - If the candidate is a single word, use direct mapping (_process_single_word_occurrences).
             - If the candidate comprises multiple words, use the multi-word processing (_process_multiword_occurrences).
             Even pages with no matches are included in the results.

        Returns:
            Tuple[Dict[str, Any], int]: A tuple where the first element is a dictionary containing:
                - "pages": A list of dictionaries (one per page) with keys:
                    "page": page number,
                    "matches": list of match dictionaries (each containing "bbox" and "original_text").
            The second element is the total count of occurrences found across pages.
        """
        candidate_phrases = []  # List to accumulate candidate phrases from all pages.
        log_debug(f"Starting find_target_phrase_occurrences with target_bbox: {target_bbox}")

        # Step 1: Loop over each page to identify candidate phrases.
        for page in self.extracted_data.get("pages", []):
            # Build a mapping of word positions and text for the current page.
            mapping, _ = self.build_page_text_and_mapping(page.get("words", []))
            # Identify indices where the word center falls within the target bounding box.
            candidate_indices = [
                idx for idx, m in enumerate(mapping)
                if self._word_center_in_bbox(m["bbox"], target_bbox)
            ]
            log_debug(f"Page {page.get('page', 'unknown')}: candidate_indices: {candidate_indices}")
            if not candidate_indices:
                log_debug(f"Page {page.get('page', 'unknown')}: No words found in target_bbox.")
                continue  # Skip this page if no candidate indices are found.
            # Group consecutive indices to form candidate phrases.
            groups = self._group_consecutive_indices(candidate_indices)
            log_debug(f"Page {page.get('page', 'unknown')}: grouped candidate indices: {groups}")
            # For each group, join the words to form a candidate phrase.
            for group in groups:
                phrase = " ".join(mapping[i]["text"] for i in group)
                candidate_phrases.append(phrase)
                log_debug(f"Page {page.get('page', 'unknown')}: found candidate phrase: '{phrase}'")

        # If no candidate phrases were found across any page, return empty results.
        if not candidate_phrases:
            log_debug("No candidate phrases found in any page.")
            return {"pages": [], "target_phrase": None, "word_count": 0}, 0

        # Step 2: Select the candidate phrase to use (here we choose the longest candidate phrase).
        candidate_phrase = max(candidate_phrases, key=len)
        word_count = len(candidate_phrase.split())
        log_debug(
            f"Chosen candidate phrase: '{candidate_phrase}' with {word_count} words from candidate phrases: {candidate_phrases}"
        )

        total_occurrences = 0  # Counter for the total number of occurrences found.
        pages_results = []  # List to store results per page.
        # Step 3: Process each page to find occurrences of the candidate phrase.
        for page in self.extracted_data.get("pages", []):
            # For single-word candidate phrases.
            if word_count == 1:
                result, count = self._process_single_word_occurrences(page, candidate_phrase)
            else:
                # For multi-word candidate phrases.
                result, count = self._process_multiword_occurrences(page, candidate_phrase)
            pages_results.append(result)
            total_occurrences += count  # Sum the number of matches.

        log_debug(f"find_target_phrase_occurrences: Final occurrences: {total_occurrences}")
        # Return a dictionary containing the per-page results, the candidate phrase, its word count,
        # and the total number of occurrences across all pages.
        return {"pages": pages_results, }, total_occurrences
