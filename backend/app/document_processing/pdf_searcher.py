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
    """
    PDFSearcher is responsible for finding specific search terms within text extracted from PDFs.

    It supports two search modes:
      1. AI Search Mode: Uses the Gemini API with a custom prompt to identify entities.
      2. Fallback Word-Based Matching: Performs direct matching against extracted text.

    The class includes helper methods for building search sets, reconstructing page text and its mapping, constructing
    AI prompts, processing pages with AI or fallback mode, splitting and remapping entity tokens back to locations,
    grouping consecutive indices, and processing single- or multi-word occurrences.
    """

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
        # Check if matching is case-sensitive.
        if case_sensitive:
            # Return a set with each term stripped of extra spaces.
            return {term.strip() for term in search_terms if term.strip()}
        # Otherwise, return a set with all terms converted to lowercase.
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
        # Strip punctuation from the word.
        cleaned = word_text.strip(string.punctuation)
        # If AI search mode is enabled, bypass direct matching.
        if ai_search:
            return False
        # If case-sensitive, check for an exact match.
        if case_sensitive:
            return cleaned in search_set
        # Otherwise, check match after converting to lowercase.
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
        # Initialize an empty list to hold mapping information.
        mapping = []
        # Initialize an empty list to accumulate parts of the page text.
        page_text_parts = []
        # Set current index to start at zero.
        current_index = 0
        # default padding exactly as in TextUtils.map_offsets_to_bboxes
        padding = {"top": 2, "right": 0, "bottom": 2, "left": 0}
        # Iterate over each word in the provided list.
        for word in words:
            # Get the text value of the word; default to an empty string.
            text = word.get("text", "")
            # Set the start index of the current word.
            start_idx = current_index
            # Calculate the end index as start index plus the length of the text.
            end_idx = start_idx + len(text)
            # Retrieve bounding box from the word if available; otherwise build one from coordinates.
            bbox = word.get("bbox") or {
                "x0": word.get("x0"),
                "y0": word.get("y0"),
                "x1": word.get("x1"),
                "y1": word.get("y1")
            }
            # apply padding exactly as base class does:
            padded = {
                "x0": bbox["x0"] - padding["left"],
                "y0": bbox["y0"] + padding["top"],
                "x1": bbox["x1"] + padding["right"],
                "y1": bbox["y1"] - padding["bottom"],
            }
            # Append the mapping information as a dictionary.
            mapping.append({
                "start": start_idx,
                "end": end_idx,
                "bbox": padded,
                "text": text
            })
            # Append the text to the list of page text parts.
            page_text_parts.append(text)
            # Update the current index, adding one for the space that will be inserted.
            current_index = end_idx + 1
        # Join all text parts with a space to form the full page text.
        page_text = " ".join(page_text_parts)
        # Return the mapping and the full page text.
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
        # Build and return the full prompt string by concatenating header, entity definitions, query, page text, and footer.
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
            # Retrieve the page number from the page data.
            page_number = page.get("page")
            # Retrieve the list of words from the page data.
            words = page.get("words", [])
            # Reconstruct the full page text and build a mapping of words to their indices and bounding boxes.
            mapping, page_text = self.build_page_text_and_mapping(words)
            # Combine search terms into a single query string.
            combined_query = " ".join(search_terms)
            # Build the custom AI prompt using the combined query and page text.
            prompt = self._build_ai_prompt([combined_query], page_text)
            # Send the prompt to the Gemini API asynchronously and wait for the response.
            response = await self.gemini_helper.send_request(
                prompt,
                requested_entities=[combined_query],
                raw_prompt=True,
                system_instruction_override=AI_SEARCH_SYSTEM_INSTRUCTION
            )
            # Parse the API response to retrieve matched entities.
            parsed_response = self.gemini_helper.parse_response(response)
            # Initialize an empty list to hold matches.
            page_matches = []
            # If the parsed response contains page data, iterate through it.
            if parsed_response and "pages" in parsed_response:
                # Build the list of matches by iterating over pages and their text objects and entities.
                page_matches = [
                    {
                        "bbox": token_entity["bbox"],
                    }
                    for page_data in parsed_response["pages"]
                    for text_obj in page_data.get("text", [])
                    for entity in text_obj.get("entities", [])
                    for token_entity in self._split_and_remap_entity(entity, mapping, case_sensitive)
                ]
                # Remove duplicate bounding boxes from the list of matches.
                page_matches = deduplicate_bbox(page_matches)
            # Return a dictionary of the page number and its matches along with the match count.
            return {"page": page_number, "matches": page_matches}, len(page_matches)
        except Exception as e:
            # Log any error that occurs during processing using the secure error handler.
            SecurityAwareErrorHandler.log_processing_error(e, "PDFSearcher._process_ai_page",
                                                           f"page_{page.get('page')}")
            # Log a debug message with error details.
            log_debug(f"Error processing AI page {page.get('page')}: {e}")
            # Return an empty match set for the page in case of error.
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
            # Retrieve the page number.
            page_number = page.get("page")
            # Initialize an empty list for matches.
            page_matches = []
            mapping, _ = self.build_page_text_and_mapping(page.get("words", []))
            # Iterate through each word in the page data.
            for word in mapping:
                # Retrieve the text of the word and strip extra spaces.
                word_text = (word.get("text") or "").strip()
                # Check whether the cleaned word matches any term in the search set.
                if self._word_matches(word_text, search_set, case_sensitive, ai_search=False):
                    # Retrieve the bounding box from the word, or construct it from coordinates.
                    bbox = word.get("bbox") or {
                        "x0": word.get("x0"),
                        "y0": word.get("y0"),
                        "x1": word.get("x1"),
                        "y1": word.get("y1")
                    }
                    # Append a dictionary of the matching word's bounding box.
                    page_matches.append({
                        "bbox": bbox,
                    })
            # Return a dictionary with the page number and match results, along with the match count.
            return {"page": page_number, "matches": page_matches}, len(page_matches)
        except Exception as e:
            # Log errors during fallback processing securely.
            SecurityAwareErrorHandler.log_processing_error(e, "PDFSearcher._process_fallback_page",
                                                           f"page_{page.get('page')}")
            # Log a debug message with error details.
            log_debug(f"Error processing fallback page {page.get('page')}: {e}")
            # Return no matches if an error occurs.
            return {"page": page.get("page"), "matches": []}, 0

    async def search_terms(self, search_terms: List[str], case_sensitive: bool = False, ai_search: bool = False) -> \
            Dict[str, Any]:
        """
        Search for the specified search terms in the extracted PDF data.

        Depending on the mode selected:
          - In AI search mode, each page is processed concurrently using the Gemini API.
          - In fallback mode, each word is directly compared using simple text matching.

        Args:
            search_terms (List[str]): List of search terms to locate.
            case_sensitive (bool): Whether the search should be case-sensitive.
            ai_search (bool): Whether to use AI search (via Gemini API) or fallback matching.

        Returns:
            Dict[str, Any]: A dictionary containing:
                - "pages": A list of pages with their matched entities (bounding boxes).
                - "match_count": Total number of matches found.
        """
        # Initialize an empty list to collect per-page results.
        pages_results = []
        # Set the total match count to zero.
        total_matches = 0
        try:
            # Check if AI search mode is enabled.
            if ai_search:
                # Log a debug message indicating that AI search mode is being used.
                log_debug("Using AI search with custom prompt for entity extraction.")
                # Create asynchronous tasks for processing each page with AI search.
                tasks = [
                    self._process_ai_page(page, search_terms, case_sensitive)
                    for page in self.extracted_data.get("pages", [])
                ]
                # Run all tasks concurrently and gather the results.
                results = await asyncio.gather(*tasks, return_exceptions=True)
                # Iterate over the gathered results.
                for result in results:
                    # If the result is an exception, log it and continue.
                    if isinstance(result, Exception):
                        SecurityAwareErrorHandler.log_processing_error(result, "PDFSearcher.search_terms", "ai_search")
                        continue
                    # Otherwise, unpack the page result and match count.
                    page_result, count = result
                    # Append the page result to the list.
                    pages_results.append(page_result)
                    # Add the count to the total number of matches.
                    total_matches += count
            else:
                # For fallback search mode, build a set of search terms.
                search_set = self._build_search_set(search_terms, case_sensitive)
                # Iterate through each page in the extracted data.
                for page in self.extracted_data.get("pages", []):
                    # Process the page using fallback matching.
                    page_result, count = self._process_fallback_page(page, search_set, case_sensitive)
                    # Append the result.
                    pages_results.append(page_result)
                    # Accumulate the match count.
                    total_matches += count
            # Log the total number of matches found.
            log_debug(f"✅ Total matches found: {total_matches}")
            # Return the dictionary containing pages and the total match count.
            return {"pages": pages_results, "match_count": total_matches}
        except Exception as e:
            # Log any errors during the overall search process.
            SecurityAwareErrorHandler.log_processing_error(e, "PDFSearcher.search_terms", "global")
            log_debug(f"Error during search_terms: {e}")
            # Return empty results if an error occurs.
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
        # Initialize an empty list to collect remapped token entities.
        token_entities = []
        # Retrieve the original text from the entity.
        entity_query = entity.get("original_text", "")
        # If the original text is empty, return the empty list.
        if not entity_query:
            return token_entities
        # Define a comparison function based on the case sensitivity flag.
        compare = (lambda a, b: a == b) if case_sensitive else (lambda a, b: a.lower() == b.lower())
        # Split the entity's text into individual tokens.
        for token in entity_query.split():
            # Iterate over each mapping entry.
            for m in mapping:
                # Retrieve the text from the mapping.
                mapping_text = m.get("text", "")
                # Compare the mapping text with the token.
                if compare(mapping_text, token):
                    # If they match, append a dictionary of token information.
                    token_entities.append({
                        "entity_type": entity.get("entity_type"),
                        "original_text": mapping_text,
                        "start": m.get("start"),
                        "end": m.get("end"),
                        "bbox": m.get("bbox"),
                        "score": entity.get("score"),
                        "case_sensitive": case_sensitive
                    })
        # Return the list of remapped token entities.
        return token_entities

    @staticmethod
    def _word_center_in_bbox(word_bbox: Dict[str, Any], target_bbox: Dict[str, Any]) -> bool:
        """
        Check if the center of a word's bounding box lies within the given target bounding box.

        Args:
            word_bbox (Dict[str, Any]): Bounding box for a word.
            target_bbox (Dict[str, Any]): Target bounding box.

        Returns:
            bool: True if the center of word_bbox lies within target_bbox, else False.
        """
        # Calculate the horizontal center (cx) of the word's bounding box.
        cx = (word_bbox["x0"] + word_bbox["x1"]) / 2.0
        # Calculate the vertical center (cy) of the word's bounding box.
        cy = (word_bbox["y0"] + word_bbox["y1"]) / 2.0
        # Return True if the center point lies within the target bounding box.
        return target_bbox["x0"] <= cx <= target_bbox["x1"] and target_bbox["y0"] <= cy <= target_bbox["y1"]

    @staticmethod
    def _group_consecutive_indices(indices: List[int]) -> List[List[int]]:
        """
        Group a list of indices into sublist of consecutive numbers.

        Args:
            indices (List[int]): A list of integer indices.

        Returns:
            List[List[int]]: A list of lists of consecutive indices.
        """
        # If the list of indices is empty, return an empty list.
        if not indices:
            return []
        # Initialize the list to hold groups.
        groups = []
        # Start with the first index in a new group.
        current_group = [indices[0]]
        # Iterate over the remaining indices.
        for index in indices[1:]:
            # If the current index is consecutive, add it to the current group.
            if index == current_group[-1] + 1:
                current_group.append(index)
            else:
                # Otherwise, append the current group and start a new one.
                groups.append(current_group)
                current_group = [index]
        # Append the final group to the groups list.
        groups.append(current_group)
        # Return the list of grouped consecutive indices.
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
            Tuple[Dict[str, Any], int]: A tuple with the page result and match count.
        """
        # Retrieve the page number; default to "unknown" if not provided.
        page_number = page.get("page", "unknown")
        # Initialize an empty list to store matches.
        page_matches = []
        # Build a mapping of words to their positions and bounding boxes.
        mapping, _ = self.build_page_text_and_mapping(page.get("words", []))
        # Iterate over each mapping entry.
        for m in mapping:
            # Check if the mapping text exactly matches the candidate phrase.
            if m["text"] == candidate_phrase:
                # Append the match information with its bounding box.
                page_matches.append({
                    "bbox": m["bbox"],
                })
                # Log a debug message showing the occurrence.
                log_debug(f"Page {page_number}: Found occurrence with bbox: {m['bbox']}")
        # Return a dictionary with page results and the count of matches.
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
            Tuple[Dict[str, Any], int]: A tuple with the page result and match count.
        """
        # Retrieve the page number; default to "unknown" if not provided.
        page_number = page.get("page", "unknown")
        # Initialize an empty list to store match results.
        page_matches = []
        # Reconstruct the full text and mapping using TextUtils helper.
        full_text, text_mapping = TextUtils.reconstruct_text_and_mapping(page.get("words", []))
        # Log the full text for debugging.
        log_debug(f"Page {page_number}: full_text: '{full_text}'")
        # Compute the offsets where the candidate phrase occurs.
        matches = TextUtils.recompute_offsets(full_text, candidate_phrase)
        # Log the offsets found.
        log_debug(f"Page {page_number}: Found candidate phrase offsets: {matches}")
        # Process each occurrence identified by its start and end offsets.
        for s, e in matches:
            try:
                # Map the character offsets back to bounding boxes.
                bboxes = TextUtils.map_offsets_to_bboxes(full_text, text_mapping, (s, e))
            except Exception as exc:
                # Log any error that occurs during mapping.
                log_debug(f"Page {page_number}: Error in map_offsets_to_bboxes: {exc}")
                continue
            # If no bounding boxes are found, skip this occurrence.
            if not bboxes:
                log_debug(f"Page {page_number}: No bounding boxes found for offsets {s}-{e}")
                continue
            # Merge the bounding boxes and get the merged data (which includes composite and per-line boxes).
            merged_data = TextUtils.merge_bounding_boxes(bboxes)
            # Here, choose the composite bounding box (that covers all lines).
            final_bbox = merged_data["composite"]
            # Append the composite bounding box to the match results.
            page_matches.append({"bbox": final_bbox})
            # Log the merged bounding box result.
            log_debug(f"Page {page_number}: Merged composite bounding box for offsets {s}-{e}: {final_bbox}")
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
            Tuple[Dict[str, Any], int]: A tuple with a dictionary of per-page results and the total occurrence count.
        """
        # Initialize an empty list to collect candidate phrases from all pages.
        candidate_phrases = []
        # Log the beginning of the process with the target bounding box.
        log_debug(f"Starting find_target_phrase_occurrences with target_bbox: {target_bbox}")
        # Step 1: Iterate over each page to identify candidate phrases.
        for page in self.extracted_data.get("pages", []):
            # Build the mapping of words for the current page.
            mapping, _ = self.build_page_text_and_mapping(page.get("words", []))
            # Identify the indices of words whose centers lie within the target bounding box.
            candidate_indices = [
                idx for idx, m in enumerate(mapping)
                if self._word_center_in_bbox(m["bbox"], target_bbox)
            ]
            # Log the indices found for the page.
            log_debug(f"Page {page.get('page', 'unknown')}: candidate_indices: {candidate_indices}")
            # If no candidate indices are found, log and skip this page.
            if not candidate_indices:
                log_debug(f"Page {page.get('page', 'unknown')}: No words found in target_bbox.")
                continue
            # Group the consecutive candidate indices.
            groups = self._group_consecutive_indices(candidate_indices)
            # Log the grouped indices.
            log_debug(f"Page {page.get('page', 'unknown')}: grouped candidate indices: {groups}")
            # For each group, join the corresponding words to form a candidate phrase.
            for group in groups:
                phrase = " ".join(mapping[i]["text"] for i in group)
                # Append the candidate phrase to the collection.
                candidate_phrases.append(phrase)
                # Log the candidate phrase found.
                log_debug(f"Page {page.get('page', 'unknown')}: found candidate phrase: '{phrase}'")
        # Check if any candidate phrases were found.
        if not candidate_phrases:
            # Log that no candidate phrases were found.
            log_debug("No candidate phrases found in any page.")
            # Return empty results.
            return {"pages": [], "target_phrase": None, "word_count": 0}, 0
        # Step 2: Select the candidate phrase with the greatest length.
        candidate_phrase = max(candidate_phrases, key=len)
        # Count the number of words in the selected candidate phrase.
        word_count = len(candidate_phrase.split())
        # Log the chosen candidate phrase and its word count.
        log_debug(
            f"Chosen candidate phrase: '{candidate_phrase}' with {word_count} words from candidate phrases: {candidate_phrases}")
        # Initialize a counter for total occurrences.
        total_occurrences = 0
        # Initialize a list to hold per-page results.
        pages_results = []
        # Step 3: Process each page for occurrences of the candidate phrase.
        for page in self.extracted_data.get("pages", []):
            # If the candidate phrase is a single word, process it accordingly.
            if word_count == 1:
                result, count = self._process_single_word_occurrences(page, candidate_phrase)
            else:
                # For multiple words, use the multi-word processing function.
                result, count = self._process_multiword_occurrences(page, candidate_phrase)
            # Append the result for the page.
            pages_results.append(result)
            # Increment the total occurrences by the count for this page.
            total_occurrences += count
        # Log the final count of occurrences.
        log_debug(f"find_target_phrase_occurrences: Final occurrences: {total_occurrences}")
        # Return the final results along with the total occurrence count.
        return {"pages": pages_results, "target_phrase": candidate_phrase, "word_count": word_count}, total_occurrences
