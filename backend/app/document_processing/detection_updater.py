from typing import Dict, Any, List, Tuple

from backend.app.utils.helpers.text_utils import TextUtils
from backend.app.utils.logging.logger import log_debug


class DetectionResultUpdater:
    """
    A class for updating a detection result (entities, redaction mapping)
    based on a list of remove-phrases. Each sensitive entity in the redaction mapping is
    processed such that any matching phrases (possibly multi-token) are removed from
    its original_text.

    If removing a phrase causes the entity text to split into multiple parts, separate
    entity entries are created. If no text remains, the entity is dropped. Offsets and
    bounding boxes are recalculated for each updated text.

    Attributes:
        extracted_data: The original extracted PDF data, containing pages with word info.
        entities: The list of detected entity dictionaries (unused directly, but preserved).
        redaction_mapping: The dictionary containing the redaction info with "pages" and "sensitive" keys.
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
            detection_result: A tuple of (entities, redaction_mapping),
                              as produced by the detection engine.
        """
        self.extracted_data = extracted_data
        # detection_result is a tuple: (entities, redaction_mapping)
        self.entities, self.redaction_mapping = detection_result

    def update_result(self, remove_words: List[str]) -> Dict[str, Any]:
        """
        Update the detection result by removing the specified phrases from each entity.

        Args:
            remove_words: A list of strings, each possibly containing multiple tokens to remove.

        Returns:
            A dictionary with updated detection results:
                {
                    "redaction_mapping": {"pages": [...]},
                    "entities_detected": {"total": int, "by_page": {...}}
                }
        """
        log_debug("✅ Starting update_result in DetectionResultUpdater")
        log_debug(f"✅ Remove phrases: {remove_words}")

        updated_pages: List[Dict[str, Any]] = []
        total_entities = 0
        entities_by_page: Dict[str, int] = {}

        # Process each page in the redaction mapping
        for red_page in self.redaction_mapping.get("pages", []):
            page_num = red_page.get("page")

            # Retrieve the original page data
            orig_page = self._get_original_page(page_num)
            if not orig_page:
                continue

            # Reconstruct the text and mapping for this page
            full_text, mapping = self._reconstruct_page_text(orig_page, page_num)

            # Process the sensitive entities for this page
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

        # Build final detection result
        updated_result = {
            "redaction_mapping": {"pages": updated_pages},
            "entities_detected": {
                "total": total_entities,
                "by_page": entities_by_page
            }
        }
        return updated_result

    @staticmethod
    def apply_removals(entity_text: str, remove_phrases: List[str]) -> List[str]:
        """
        Apply a list of removal phrases (possibly multi-token) to a single entity text.

        For each phrase:
          1) If the entire text matches the phrase exactly, remove it (entity becomes empty).
          2) Else if the text starts and ends with the phrase tokens, remove those boundary tokens.
          3) Else if the phrase appears as a contiguous block in the middle, split the text
             around that block.

        Multiple phrases are applied in sequence. If a removal leaves the text empty, it is dropped.

        Args:
            entity_text: The original text of the entity (e.g., "Jeanett Lofthagen").
            remove_phrases: List of removal phrases (e.g. ["Jeanett", "Synnøve Ellingstad"]).

        Returns:
            A list of resulting entity text(s) after all removals. Could be empty if
            all tokens are removed.
        """
        results = [entity_text]
        for phrase in remove_phrases:
            phrase_tokens = phrase.split()
            results = _remove_phrase_from_texts(results, phrase_tokens)

        # Deduplicate results
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
        If not found or an error occurs, returns an empty dict.

        Args:
            page_num: The page number to look up.

        Returns:
            The dictionary representing that page, or an empty dict if not found.
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
            page_num: The page number (for logging).

        Returns:
            A tuple of (full_text, mapping) from TextUtils.reconstruct_text_and_mapping.
        """
        try:
            words = page_data.get("words", [])
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
        Process each entity on a page by removing the specified phrases, recalculating
        offsets and bounding boxes, and possibly splitting into multiple entities.

        Args:
            entities_list: The list of entity dictionaries from the redaction mapping.
            remove_words: The phrases to remove.
            full_text: The reconstructed page text.
            mapping: The list of (word_dict, start_offset, end_offset) from the page.
            page_num: The current page number (for logging).
            entities_by_page: A dictionary counting entities by page, updated in-place.

        Returns:
            A list of updated entity dictionaries for this page.
        """
        updated_sensitive: List[Dict[str, Any]] = []

        for entity in entities_list:
            orig_entity_text = entity.get("original_text", "")

            # 1) Apply removal phrases
            updated_texts = self.apply_removals(orig_entity_text, remove_words)

            if not updated_texts:
                continue

            # 2) For each updated text, find offsets in the full page text
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
                    # Fallback: use original offsets
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
        Append new entity entries for each offset occurrence of `updated_text`.

        Args:
            updated_sensitive: The list to which new entities are appended.
            base_entity: The original entity dictionary.
            updated_text: The text after removal phrases.
            offsets: List of (start, end) offsets where updated_text is found in full_text.
            full_text: The full page text.
            mapping: The list of (word_dict, start_offset, end_offset).
            page_num: The page number for logging and indexing.
            entities_by_page: Dictionary counting entities by page, updated in-place.
        """
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

        Args:
            base_entity: The original entity dictionary.
            updated_text: The new text after removals.
            new_start: The start offset in the full text.
            new_end: The end offset in the full text.
            full_text: The full page text.
            mapping: The word mapping from text reconstruction.

        Returns:
            A copy of base_entity with updated "original_text", "start", "end", and "bbox" if found.
        """
        from_start_end = (new_start, new_end)
        bboxes = TextUtils.map_offsets_to_bboxes(full_text, mapping, from_start_end)

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
    Given a list of texts and a single phrase (as tokens), apply the removal logic
    to each text and combine the results.

    Args:
        texts: The current list of entity texts (e.g. after prior removals).
        phrase_tokens: The tokens representing the phrase to remove.

    Returns:
        A new list of texts after applying removal of the phrase to each input text.
    """
    new_results = []
    for txt in texts:
        new_results.extend(_remove_phrase_from_text(txt, phrase_tokens))
    # Filter out empty results
    return [r for r in new_results if r]


def _remove_phrase_from_text(text: str, phrase_tokens: List[str]) -> List[str]:
    """
    Remove the given phrase (already split into tokens) from a single text.

    The removal logic checks:
      1) If text matches the phrase exactly (same length/tokens).
      2) If text starts and ends with the phrase tokens.
      3) If phrase is found as a contiguous block in the middle.

    Args:
        text: The original entity text.
        phrase_tokens: The phrase tokens to remove.

    Returns:
        A list of zero, one, or more resulting strings after removal.
    """
    tokens = text.split()
    # If text is shorter than the phrase, no removal
    if len(tokens) < len(phrase_tokens):
        return [text]

    # 1) If entire text matches the phrase exactly
    if tokens == phrase_tokens:
        # Removing them yields empty => no text
        return []

    # 2) If text starts and ends with phrase tokens
    if (tokens[0].lower() == phrase_tokens[0].lower() and
        tokens[-1].lower() == phrase_tokens[-1].lower() and
        len(tokens) >= len(phrase_tokens)):
        # Remove the first and last tokens
        new_text = " ".join(tokens[1:-1])
        # If that empties the text, remove it
        return [new_text] if new_text else []

    # 3) Search for the phrase in the middle
    for i in range(len(tokens) - len(phrase_tokens) + 1):
        block = tokens[i:i + len(phrase_tokens)]
        if all(block[j].lower() == phrase_tokens[j].lower()
               for j in range(len(phrase_tokens))):
            # Found the block to remove
            part1 = tokens[:i]
            part2 = tokens[i + len(phrase_tokens):]
            results = []
            if part1:
                results.append(" ".join(part1))
            if part2:
                results.append(" ".join(part2))
            # Return combined results
            return results

    # No removal matched
    return [text]