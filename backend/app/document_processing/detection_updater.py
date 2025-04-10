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
        extracted_data: The original extracted PDF data including pages and words.
        entities: The list of detected entity dictionaries.
        redaction_mapping: The redaction mapping that contains sensitive information per page.
    """

    def __init__(
            self,
            extracted_data: Dict[str, Any],
            detection_result: Tuple[List[Dict[str, Any]], Dict[str, Any]]
    ):
        """
        Initialize the DetectionResultUpdater.

        Args:
            extracted_data: Dictionary with PDF-extracted data (pages, words, etc.).
            detection_result: A tuple containing the entities list and the redaction_mapping,
                              as produced by the detection engine.
        """
        self.extracted_data = extracted_data
        # detection_result is a tuple: (entities, redaction_mapping)
        self.entities, self.redaction_mapping = detection_result

    def update_result(self, remove_words: List[str]) -> Dict[str, Any]:
        """
        Update the detection result by removing the specified phrases from each sensitive entity.

        This method iterates over each page's redaction mapping, reconstructs the page text,
        and processes sensitive entities by applying removal phrases. It recalculates offsets and
        bounding boxes for each updated entity. If any error occurs during processing, it is
        safely handled via the SecurityAwareErrorHandler.

        Args:
            remove_words: A list of strings where each string is a removal phrase which may contain multiple tokens.

        Returns:
            A dictionary with the updated detection result containing:
                {
                    "redaction_mapping": {"pages": [...]},
                    "entities_detected": {"total": int, "by_page": {...}}
                }
        """
        try:
            log_debug("✅ Starting update_result in DetectionResultUpdater")
            log_debug(f"✅ Remove phrases: {remove_words}")

            updated_pages: List[Dict[str, Any]] = []
            total_entities = 0
            entities_by_page: Dict[str, int] = {}

            # Process each page in the redaction mapping
            for red_page in self.redaction_mapping.get("pages", []):
                page_num = red_page.get("page")
                # Retrieve the original page data with safe error handling
                orig_page = self._get_original_page(page_num)
                if not orig_page:
                    continue

                # Reconstruct the full text and mapping for this page
                full_text, mapping = self._reconstruct_page_text(orig_page, page_num)

                # Process sensitive entities by applying removal phrases
                updated_sensitive = self._process_sensitive_entities(
                    red_page.get("sensitive", []),
                    remove_words,
                    full_text,
                    mapping,
                    page_num,
                    entities_by_page
                )
                updated_pages.append({"page": page_num, "sensitive": updated_sensitive})

                total_entities = sum(entities_by_page.values())

            # Build final detection result dictionary
            updated_result = {
                "redaction_mapping": {"pages": updated_pages},
                "entities_detected": {
                    "total": total_entities,
                    "by_page": entities_by_page
                }
            }
            return updated_result

        except Exception as e:
            # Handle any error during the update process using the security-aware error handler
            return SecurityAwareErrorHandler.handle_detection_error(
                e, "DetectionResultUpdater.update_result"
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
            entity_text: The original text of the entity (e.g., "Jeanett Lofthagen").
            remove_phrases: List of removal phrases (e.g., ["Jeanett", "Synnøve Ellingstad"]).

        Returns:
            A list of resulting entity texts after applying all removals. May be empty if all tokens are removed.
        """
        results = [entity_text]
        for phrase in remove_phrases:
            phrase_tokens = phrase.split()
            results = _remove_phrase_from_texts(results, phrase_tokens)

        # Deduplicate results to avoid duplicates in final output
        final: List[str] = []
        seen = set()
        for r in results:
            if r not in seen:
                seen.add(r)
                final.append(r)

        return final

    def _get_original_page(self, page_num: int) -> Dict[str, Any]:
        """
        Safely retrieve the original extracted page by page number.

        Args:
            page_num: The page number to look up.

        Returns:
            The dictionary representing that page, or an empty dict if not found or an error occurs.
        """
        try:
            page_data = next(
                (p for p in self.extracted_data.get("pages", []) if p.get("page") == page_num),
                {}
            )
            return page_data if page_data else {}
        except Exception as exc:
            log_debug(f"Error retrieving page {page_num}: {exc}")
            return {}

    @staticmethod
    def _reconstruct_page_text(
            page_data: Dict[str, Any], page_num: int
    ) -> Tuple[str, List[Tuple[Dict[str, Any], int, int]]]:
        """
        Rebuild the full text and mapping for a given page.

        Args:
            page_data: The dictionary containing the page's 'words' list.
            page_num: The page number (used for logging).

        Returns:
            A tuple (full_text, mapping) generated by TextUtils.reconstruct_text_and_mapping.
        """
        try:
            words = page_data.get("words", [])
            # Ensure every word has a text value, using 'original_text' as fallback
            for word in words:
                if not word.get("text"):
                    word["text"] = word.get("original_text", "")
            full_text, mapping = TextUtils.reconstruct_text_and_mapping(words)
            return full_text, mapping
        except Exception as exc:
            log_debug(f"Error reconstructing text for page {page_num}: {exc}")
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
            entities_list: List of sensitive entity dictionaries from the redaction mapping.
            remove_words: The phrases to be removed from each entity.
            full_text: The reconstructed full text of the page.
            mapping: The mapping list produced by TextUtils.reconstruct_text_and_mapping.
            page_num: The page number for logging and tracking.
            entities_by_page: A dictionary that counts entities per page (updated in-place).

        Returns:
            A list of updated sensitive entity dictionaries for the page.
        """
        try:
            updated_sensitive: List[Dict[str, Any]] = []

            for entity in entities_list:
                orig_entity_text = entity.get("original_text", "")

                # Apply removal phrases to the entity text
                updated_texts = self.apply_removals(orig_entity_text, remove_words)

                # Skip if removal leaves no text remaining
                if not updated_texts:
                    continue

                # For each updated text fragment, attempt to recompute offsets in the full page text
                for updated_text in updated_texts:
                    offsets = TextUtils.recompute_offsets(full_text, updated_text)
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
                        # Fallback: if no new offsets, retain the original offsets
                        updated_entity = self._build_updated_entity(
                            base_entity=entity,
                            updated_text=updated_text,
                            new_start=entity.get("start", 0),
                            new_end=entity.get("end", 0),
                            full_text=full_text,
                            mapping=mapping
                        )
                        updated_sensitive.append(updated_entity)
                        key = f"page_{page_num}"
                        entities_by_page[key] = entities_by_page.get(key, 0) + 1

            return updated_sensitive

        except Exception as e:
            # Safely handle errors in processing sensitive entities
            SecurityAwareErrorHandler.handle_detection_error(e, "DetectionResultUpdater._process_sensitive_entities")
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
            updated_sensitive: List where new updated entities will be appended.
            base_entity: The original entity dictionary.
            updated_text: The text after applying removal phrases.
            offsets: List of (start, end) tuples where the updated text occurs in the full page text.
            full_text: The full page text.
            mapping: The mapping produced from text reconstruction.
            page_num: The current page number.
            entities_by_page: A dictionary tracking the count of entities per page.
        """
        try:
            for new_start, new_end in offsets:
                updated_entity = self._build_updated_entity(
                    base_entity,
                    updated_text,
                    new_start,
                    new_end,
                    full_text,
                    mapping
                )
                updated_sensitive.append(updated_entity)
                key = f"page_{page_num}"
                entities_by_page[key] = entities_by_page.get(key, 0) + 1

        except Exception as e:
            SecurityAwareErrorHandler.handle_detection_error(e, "DetectionResultUpdater._append_updated_entities")

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
            base_entity: The original entity dictionary.
            updated_text: The new text after removal operations.
            new_start: The new starting offset in the full text.
            new_end: The new ending offset in the full text.
            full_text: The full page text.
            mapping: The word mapping generated during text reconstruction.

        Returns:
            A dictionary representing the updated entity with recalculated positions and bounding box.
        """
        # Calculate bounding box using the text mapping and new offsets
        bboxes = TextUtils.map_offsets_to_bboxes(full_text, mapping, (new_start, new_end))

        updated_entity = base_entity.copy()
        updated_entity["original_text"] = updated_text
        updated_entity["start"] = new_start
        updated_entity["end"] = new_end

        if bboxes:
            updated_entity["bbox"] = bboxes[0]
        else:
            log_debug("No bounding box calculated.")

        return updated_entity


def _remove_phrase_from_texts(texts: List[str], phrase_tokens: List[str]) -> List[str]:
    """
    Given a list of texts and a phrase (as tokens), apply the removal logic to each text.

    This helper function iterates over each text, applies the removal of the specified phrase,
    and returns a new list with the updated texts (empty results are filtered out).

    Args:
        texts: A list of current entity texts.
        phrase_tokens: A list of tokens representing the phrase to remove.

    Returns:
        A new list of texts after applying the phrase removal logic.
    """
    new_results = []
    for txt in texts:
        new_results.extend(_remove_phrase_from_text(txt, phrase_tokens))
    # Filter out any empty strings from the results
    return [r for r in new_results if r]


def _remove_phrase_from_text(text: str, phrase_tokens: List[str]) -> List[str]:
    """
    Remove a given phrase (provided as tokens) from a single text.

    The removal logic checks:
      1) If the text matches the phrase exactly.
      2) If the text starts and ends with the phrase tokens.
      3) If the phrase is found as a contiguous block within the text.

    Args:
        text: The original text.
        phrase_tokens: The phrase tokens to remove.

    Returns:
        A list of strings after removing the phrase. May be empty if the text is fully removed.
    """
    tokens = text.split()
    # If text is shorter than the phrase, no removal is performed
    if len(tokens) < len(phrase_tokens):
        return [text]

    # 1) If the entire text matches the phrase exactly, removal results in an empty string.
    if tokens == phrase_tokens:
        return []

    # 2) If the text starts and ends with the phrase tokens, remove the first and last tokens.
    if (tokens[0].lower() == phrase_tokens[0].lower() and
            tokens[-1].lower() == phrase_tokens[-1].lower() and
            len(tokens) >= len(phrase_tokens)):
        new_text = " ".join(tokens[1:-1])
        return [new_text] if new_text else []

    # 3) Search for the phrase as a contiguous block in the text.
    for i in range(len(tokens) - len(phrase_tokens) + 1):
        block = tokens[i:i + len(phrase_tokens)]
        if all(block[j].lower() == phrase_tokens[j].lower() for j in range(len(phrase_tokens))):
            # Remove the found block and join the remaining parts
            part1 = tokens[:i]
            part2 = tokens[i + len(phrase_tokens):]
            results = []
            if part1:
                results.append(" ".join(part1))
            if part2:
                results.append(" ".join(part2))
            return results

    # If no removal condition matches, return the original text
    return [text]
