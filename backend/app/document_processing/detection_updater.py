"""
DetectionResultUpdater Module

This module provides the DetectionResultUpdater class which is responsible for updating
a detection result by processing sensitive entities extracted from PDF pages. It removes
specified phrases from entity texts and, if necessary, splits entities into multiple entries.
Offsets and bounding boxes are recalculated based on the updated text. Comprehensive inline
documentation and error handling have been added using the SecurityAwareErrorHandler class,
ensuring that any exceptions are handled securely and logged appropriately.
"""

from typing import Dict, Any, List, Tuple

from backend.app.utils.helpers.text_utils import TextUtils
from backend.app.utils.logging.logger import log_debug
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler


class DetectionResultUpdater:
    """
    The DetectionResultUpdater class is designed to update detection results for PDF documents.

    It takes extracted PDF data and a detection result (comprising entities and a redaction mapping)
    and applies removal operations based on provided phrases. When phrases are removed from sensitive
    entity texts, the class recalculates offsets and bounding boxes. It also supports splitting a
    single entity into multiple ones if the removal results in separate text fragments. Robust error
    handling is applied throughout to maintain security and traceability.

    Attributes:
        extracted_data (Dict[str, Any]): The original extracted PDF data including pages and words.
        entities (List[Dict[str, Any]]): The list of detected entity dictionaries.
        redaction_mapping (Dict[str, Any]): The redaction mapping that contains sensitive information per page.
    """

    def __init__(
            self,
            extracted_data: Dict[str, Any],
            detection_result: Tuple[List[Dict[str, Any]], Dict[str, Any]]
    ):
        """
        Initialize the DetectionResultUpdater.

        Args:
            extracted_data (Dict[str, Any]): Dictionary with PDF-extracted data (pages, words, etc.).
            detection_result (Tuple[List[Dict[str, Any]], Dict[str, Any]]): A tuple containing the entities list and the redaction_mapping.
        """
        # Set the extracted PDF data.
        self.extracted_data = extracted_data
        # Unpack the detection_result tuple into entities and redaction_mapping.
        self.entities, self.redaction_mapping = detection_result

    def update_result(self, remove_words: List[str]) -> Dict[str, Any]:
        """
        Update the detection result by removing the specified phrases from each sensitive entity.

        This method iterates over each page's redaction mapping, reconstructs the page text,
        and processes sensitive entities by applying removal phrases. It recalculates offsets and
        bounding boxes for each updated entity. If any error occurs during processing, it is
        safely handled via the SecurityAwareErrorHandler.

        Args:
            remove_words (List[str]): A list of strings where each string is a removal phrase.

        Returns:
            Dict[str, Any]: A dictionary with the updated detection result containing:
                {
                    "redaction_mapping": {"pages": [...]},
                    "entities_detected": {"total": int, "by_page": {...}}
                }
        """
        try:
            # Log the start of update_result.
            log_debug("✅ Starting update_result in DetectionResultUpdater")

            # Initialize a list to hold updated page redaction mappings.
            updated_pages: List[Dict[str, Any]] = []
            # Initialize a counter for the total number of entities updated.
            total_entities = 0
            # Initialize a dictionary to track the count of entities per page.
            entities_by_page: Dict[str, int] = {}

            # Loop over each page in the redaction mapping.
            for red_page in self.redaction_mapping.get("pages", []):
                # Get the current page number.
                page_num = red_page.get("page")
                # Safely get the original page data.
                orig_page = self._get_original_page(page_num)
                # If original page data is not found, skip the current page.
                if not orig_page:
                    continue

                # Reconstruct the full text and mapping for the current page.
                full_text, mapping = self._reconstruct_page_text(orig_page, page_num)

                # Process sensitive entities by applying removal phrases.
                updated_sensitive = self._process_sensitive_entities(
                    red_page.get("sensitive", []),  # Get the sensitive entities list.
                    remove_words,  # Provide removal phrases.
                    full_text,  # Provide reconstructed full text.
                    mapping,  # Provide text-to-word mapping.
                    page_num,  # Provide current page number.
                    entities_by_page  # Provide dictionary to update entity counts.
                )
                # Append the updated redaction mapping for the current page.
                updated_pages.append({"page": page_num, "sensitive": updated_sensitive})

                # Update the total entities count by summing values from entities_by_page.
                total_entities = sum(entities_by_page.values())

            # Build the final updated result dictionary.
            updated_result = {
                "redaction_mapping": {"pages": updated_pages},
                "entities_detected": {
                    "total": total_entities,
                    "by_page": entities_by_page
                }
            }
            # Return the updated result dictionary.
            return updated_result

        except Exception as e:
            # If an exception occurs, handle it securely using SecurityAwareErrorHandler.
            return SecurityAwareErrorHandler.handle_safe_error(
                e, "detection_update_result"
            )

    @staticmethod
    def apply_removals(entity_text: str, remove_phrases: List[str]) -> List[str]:
        """
        Apply a list of removal phrases to a single entity text.

        For each phrase:
          1) If the entire text matches the phrase exactly, remove it.
          2) Else if the text starts and ends with the phrase tokens, remove those boundary tokens.
          3) Else if the phrase appears as a contiguous block in the middle, split the text around that block.

        Args:
            entity_text (str): The original text of the entity.
            remove_phrases (List[str]): List of removal phrases.

        Returns:
            List[str]: A list of resulting entity texts after applying all removals.
        """
        # Initialize results with the original entity text.
        results = [entity_text]
        # Loop over each removal phrase.
        for phrase in remove_phrases:
            # Split the removal phrase into tokens.
            phrase_tokens = phrase.split()
            # Update the results by removing phrase tokens from each text.
            results = _remove_phrase_from_texts(results, phrase_tokens)
        # Initialize a list to hold deduplicated final results.
        final: List[str] = []
        # Initialize a set to track seen texts.
        seen = set()
        # Loop over each result in results.
        for r in results:
            # If the result has not been seen before, add it to final.
            if r not in seen:
                seen.add(r)
                final.append(r)
        # Return the deduplicated list of updated texts.
        return final

    def _get_original_page(self, page_num: int) -> Dict[str, Any]:
        """
        Safely retrieve the original extracted page by page number.

        Args:
            page_num (int): The page number to retrieve.

        Returns:
            Dict[str, Any]: The page data dictionary or an empty dict if not found.
        """
        try:
            # Find the page in the extracted data matching the page number.
            page_data = next(
                (p for p in self.extracted_data.get("pages", []) if p.get("page") == page_num),
                {}
            )
            # Return page_data if found, else return an empty dict.
            return page_data if page_data else {}
        except Exception as exc:
            # Log a debug message if an error occurs.
            log_debug(f"Error retrieving page {page_num}: {exc}")
            # Return an empty dict on exception.
            return {}

    @staticmethod
    def _reconstruct_page_text(
            page_data: Dict[str, Any], page_num: int
    ) -> Tuple[str, List[Tuple[Dict[str, Any], int, int]]]:
        """
        Rebuild the full text and mapping for a given page.

        Args:
            page_data (Dict[str, Any]): The page data containing a 'words' list.
            page_num (int): The current page number.

        Returns:
            Tuple[str, List[Tuple[Dict[str, Any], int, int]]]: A tuple of (full_text, mapping).
        """
        try:
            # Retrieve the list of words from the page data.
            words = page_data.get("words", [])
            # Loop over each word to ensure 'text' key exists, using 'original_text' as fallback.
            for word in words:
                # If 'text' is missing, set it to 'original_text' or an empty string.
                if not word.get("text"):
                    word["text"] = word.get("original_text", "")
            # Reconstruct full text and mapping using TextUtils.
            full_text, mapping = TextUtils.reconstruct_text_and_mapping(words)
            # Return the full_text and mapping.
            return full_text, mapping
        except Exception as exc:
            # Log debug message if an error occurs.
            log_debug(f"Error reconstructing text for page {page_num}: {exc}")
            # Return an empty string and empty list if exception occurs.
            return "", []

    def _process_sensitive_entities(
            self,
            entities_list: List[Dict[str, Any]],
            remove_words: List[str],
            full_text: str,
            mapping: List[Tuple[Dict[str, Any], int, int]],
            page_num: int,
            entities_by_page: Dict[str, int]
    ) -> List[Dict[str, Any]]:
        """
        Process each sensitive entity on a page by applying removal phrases and recalculating offsets.

        For every entity, the method updates the text by removing the specified phrases and then
        recalculates its position (offsets) within the full page text. If the updated text is found
        in the page text, new entity entries with updated bounding boxes are created. If offsets are not
        recalculated, the original offsets are preserved.

        Args:
            entities_list (List[Dict[str, Any]]): Sensitive entity dictionaries.
            remove_words (List[str]): List of removal phrases.
            full_text (str): The reconstructed full text of the page.
            mapping (List[Tuple[Dict[str, Any], int, int]]): Mapping of words to character offsets.
            page_num (int): The page number.
            entities_by_page (Dict[str, int]): Dictionary tracking entity counts per page.

        Returns:
            List[Dict[str, Any]]: A list of updated sensitive entity dictionaries for the page.
        """
        try:
            # Initialize list to hold updated sensitive entities.
            updated_sensitive: List[Dict[str, Any]] = []
            # Loop through each entity in the provided entities list.
            for entity in entities_list:
                # Get the original entity text from the entity dictionary.
                orig_entity_text = entity.get("original_text", "")
                # Apply removal phrases to the original entity text.
                updated_texts = self.apply_removals(orig_entity_text, remove_words)
                # If removal results in no text, skip this entity.
                if not updated_texts:
                    continue
                # Loop through each updated text fragment.
                for updated_text in updated_texts:
                    # Compute new offsets for the updated text in the full page text.
                    offsets = TextUtils.recompute_offsets(full_text, updated_text)
                    # If new offsets are found, append updated entities.
                    if offsets:
                        self._append_updated_entities(
                            updated_sensitive,
                            entity,
                            updated_text,
                            offsets,
                            full_text,
                            mapping,
                            page_num,
                            entities_by_page
                        )
                    else:
                        # If no offsets found, build an updated entity using original offsets.
                        updated_entity = self._build_updated_entity(
                            base_entity=entity,
                            updated_text=updated_text,
                            new_start=entity.get("start", 0),
                            new_end=entity.get("end", 0),
                            full_text=full_text,
                            mapping=mapping
                        )
                        # Append the fallback updated entity to the list.
                        updated_sensitive.append(updated_entity)
                        # Update entity count for the page.
                        key = f"page_{page_num}"
                        entities_by_page[key] = entities_by_page.get(key, 0) + 1
            # Return the list of updated sensitive entities.
            return updated_sensitive
        except Exception as e:
            # Handle exceptions securely and return an empty list.
            SecurityAwareErrorHandler.handle_safe_error(e, "detection._process_sensitive_entities")
            return []

    def _append_updated_entities(
            self,
            updated_sensitive: List[Dict[str, Any]],
            base_entity: Dict[str, Any],
            updated_text: str,
            offsets: List[Tuple[int, int]],
            full_text: str,
            mapping: List[Tuple[Dict[str, Any], int, int]],
            page_num: int,
            entities_by_page: Dict[str, int]
    ) -> None:
        """
        Append new entity entries based on each occurrence (offset) of the updated text.

        For each pair of (start, end) offsets where the updated text is found in the full page text,
        this method builds a new entity entry with recalculated bounding boxes and updates the entity count.

        Args:
            updated_sensitive (List[Dict[str, Any]]): List to which updated entities will be added.
            base_entity (Dict[str, Any]): The original entity dictionary.
            updated_text (str): The updated entity text after removals.
            offsets (List[Tuple[int, int]]): List of (start, end) offsets where updated_text occurs.
            full_text (str): The full text of the page.
            mapping (List[Tuple[Dict[str, Any], int, int]]): Text-to-word mapping.
            page_num (int): Current page number.
            entities_by_page (Dict[str, int]): Dictionary tracking entity counts per page.
        """
        try:
            # Loop over each (start, end) offset in the offsets list.
            for new_start, new_end in offsets:
                # Build an updated entity for the current offset.
                updated_entity = self._build_updated_entity(
                    base_entity,
                    updated_text,
                    new_start,
                    new_end,
                    full_text,
                    mapping
                )
                # Append the updated entity to the list.
                updated_sensitive.append(updated_entity)
                # Update the entity count for the current page.
                key = f"page_{page_num}"
                entities_by_page[key] = entities_by_page.get(key, 0) + 1
        except Exception as e:
            # Handle exceptions securely during entity appending.
            SecurityAwareErrorHandler.handle_safe_error(e, "detection._append_updated_entities")

    @staticmethod
    def _build_updated_entity(
            base_entity: Dict[str, Any],
            updated_text: str,
            new_start: int,
            new_end: int,
            full_text: str,
            mapping: List[Tuple[Dict[str, Any], int, int]]
    ) -> Dict[str, Any]:
        """
        Build a new entity dictionary with updated text, offsets, and bounding box.

        This method creates a copy of the base entity, updates its text and positional information,
        and recalculates the bounding box using the provided text mapping.

        Args:
            base_entity (Dict[str, Any]): The original entity dictionary.
            updated_text (str): The updated text after removals.
            new_start (int): The new starting character offset.
            new_end (int): The new ending character offset.
            full_text (str): The full page text.
            mapping (List[Tuple[Dict[str, Any], int, int]]): Mapping of words to their character offsets.

        Returns:
            Dict[str, Any]: A dictionary representing the updated entity.
        """
        # Calculate new bounding boxes using the text mapping.
        bboxes = TextUtils.map_offsets_to_bboxes(full_text, mapping, (new_start, new_end))
        # Make a copy of the base entity dictionary.
        updated_entity = base_entity.copy()
        # Update the entity's text.
        updated_entity["original_text"] = updated_text
        # Update the starting offset.
        updated_entity["start"] = new_start
        # Update the ending offset.
        updated_entity["end"] = new_end
        # If bounding boxes are computed, set the first one as the entity's bounding box.
        if bboxes:
            updated_entity["bbox"] = bboxes[0]
        else:
            # Log debug information if no bounding box is calculated.
            log_debug("No bounding box calculated.")
        # Return the updated entity dictionary.
        return updated_entity


def _remove_phrase_from_texts(texts: List[str], phrase_tokens: List[str]) -> List[str]:
    """
    Apply the removal logic for a given phrase to a list of texts.

    This function iterates over each text in the input list, applies removal logic by using _remove_phrase_from_text,
    and returns a new list of updated texts, filtering out empty strings.

    Args:
        texts (List[str]): A list of current entity texts.
        phrase_tokens (List[str]): Tokens representing the phrase to be removed.

    Returns:
        List[str]: A new list of texts after phrase removal.
    """
    # Initialize a new results list.
    new_results = []
    # Iterate over each text in the input list.
    for txt in texts:
        # Extend the results by applying phrase removal on the text.
        new_results.extend(_remove_phrase_from_text(txt, phrase_tokens))
    # Filter out and return only non-empty strings.
    return [r for r in new_results if r]


def _remove_phrase_from_text(text: str, phrase_tokens: List[str]) -> List[str]:
    """
    Remove a given phrase (as tokens) from a single text according to specific rules.

    The removal logic is as follows:
      1) If the text exactly matches the phrase tokens, return an empty list.
      2) If the text starts and ends with the phrase tokens, remove these boundary tokens.
      3) Otherwise, if the phrase is found as a contiguous block in the text, split the text around that block.

    Args:
        text (str): The original text.
        phrase_tokens (List[str]): The tokens of the phrase to remove.

    Returns:
        List[str]: A list of resulting texts after removal, which may be empty if fully removed.
    """
    # Split the original text into tokens.
    tokens = text.split()
    # If the text has fewer tokens than the phrase, return the original text as a list.
    if len(tokens) < len(phrase_tokens):
        return [text]
    # Check if the text exactly matches the phrase tokens.
    if tokens == phrase_tokens:
        return []
    # If the text starts and ends with the phrase tokens, remove the first and last token.
    if (tokens[0].lower() == phrase_tokens[0].lower() and
            tokens[-1].lower() == phrase_tokens[-1].lower() and
            len(tokens) >= len(phrase_tokens)):
        new_text = " ".join(tokens[1:-1])
        return [new_text] if new_text else []
    # Iterate through the tokens to find the phrase as a contiguous block.
    for i in range(len(tokens) - len(phrase_tokens) + 1):
        # Extract a block of tokens from the text.
        block = tokens[i:i + len(phrase_tokens)]
        # Compare the block tokens to the phrase tokens ignoring case.
        if all(block[j].lower() == phrase_tokens[j].lower() for j in range(len(phrase_tokens))):
            # Remove the block from the text by splitting into two parts.
            part1 = tokens[:i]
            part2 = tokens[i + len(phrase_tokens):]
            results = []
            # If part1 exists, join tokens and append to results.
            if part1:
                results.append(" ".join(part1))
            # If part2 exists, join tokens and append to results.
            if part2:
                results.append(" ".join(part2))
            return results
    # If no removal condition applies, return the original text as a list.
    return [text]
