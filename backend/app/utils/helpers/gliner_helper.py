import hashlib
from typing import List, Optional, Any, Dict


class GLiNERHelper:
    """
    A helper class for GLiNER text processing tasks.

    This class provides a set of static methods to tokenize text, split it into sentence groups,
    and chunk overly long sentences based on a maximum character limit. All methods are designed
    to work with character counts (e.g. maximum group length of 800 characters) rather than word counts.
    """
    # Global cache for processed text results (module-level)
    _cache: Dict[str, Any] = {}  # protected cache

    @staticmethod
    def get_cache_key(text: str, requested_entities: Optional[List[str]] = None) -> str:
        """
        Generate a unique cache key based on the input text and requested entities.
        """
        key_data = text
        if requested_entities:
            key_data += '|' + ','.join(sorted(requested_entities))
        return hashlib.md5(key_data.encode('utf-8')).hexdigest()

    @staticmethod
    def get_cached_result(key: str) -> Optional[Any]:
        """
        Retrieve a cached result by key.
        """
        return GLiNERHelper._cache.get(key)

    @staticmethod
    def set_cached_result(key: str, value: Any) -> None:
        """
        Store a result in the cache with the given key.
        """
        GLiNERHelper._cache[key] = value

    @staticmethod
    def estimate_char_count(text: str) -> int:
        """
        Estimate the number of characters in the input text.

        Args:
            text (str): The input text.

        Returns:
            int: The number of characters.
        """
        return len(text)

    @staticmethod
    def chunk_large_sentence_by_char(sentence: str, max_chars: int) -> List[str]:
        """
        Break an overly long sentence into smaller chunks, each containing at most max_chars characters.

        The method splits the sentence into words and accumulates words until the total character
        count (including spaces) would exceed max_chars.

        Args:
            sentence (str): The sentence to split.
            max_chars (int): Maximum number of characters allowed per chunk.

        Returns:
            List[str]: A list of text chunks, each with at most max_chars characters.
        """
        words = sentence.split()
        chunks = []
        current_chunk = []
        current_length = 0
        for word in words:
            # Include a space if current_chunk is not empty.
            additional = len(word) if not current_chunk else len(word) + 1
            if current_length + additional > max_chars:
                chunks.append(" ".join(current_chunk))
                current_chunk = [word]
                current_length = len(word)
            else:
                current_chunk.append(word)
                current_length += additional
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        return chunks

    @staticmethod
    def tokenize_sentences(text: str) -> List[str]:
        """
        Split the input text into sentences using a punctuation-based regular expression.

        Args:
            text (str): The input text.

        Returns:
            List[str]: A list of sentences.
        """
        import re
        raw_sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in raw_sentences if s.strip()]

    @staticmethod
    def build_sentence_groups(sentences: List[str], max_chars: int) -> List[str]:
        """
        Build groups of sentences so that each group contains at most max_chars characters.

        The method accumulates sentences until adding another sentence would exceed the character limit.
        If a single sentence is longer than max_chars, it is split into smaller chunks using
        chunk_large_sentence_by_char().

        Args:
            sentences (List[str]): A list of sentence strings.
            max_chars (int): Maximum characters allowed per group (e.g., 800).

        Returns:
            List[str]: A list of sentence groups, each containing at most max_chars characters.
        """
        groups = []
        current_group = []
        current_length = 0

        for sent in sentences:
            sent_length = len(sent)
            # If this sentence is too long on its own, flush the current group and chunk the sentence.
            if sent_length > max_chars:
                if current_group:
                    groups.append(" ".join(current_group))
                    current_group, current_length = [], 0
                groups.extend(GLiNERHelper.chunk_large_sentence_by_char(sent, max_chars))
                continue

            # Calculate the additional length required if we add this sentence.
            additional = sent_length if not current_group else sent_length + 1

            if current_length + additional > max_chars:
                groups.append(" ".join(current_group))
                current_group = [sent]
                current_length = sent_length
            else:
                current_group.append(sent)
                current_length += additional

        if current_group:
            groups.append(" ".join(current_group))
        return groups

    @staticmethod
    def split_into_sentence_groups(text: str, max_chars: int = 800) -> List[str]:
        """
        Split the input text into groups of sentences such that each group contains at most max_chars characters.

        This method tokenizes the text into sentences using a punctuation-based regex, then groups the sentences
        using build_sentence_groups().

        Args:
            text (str): The input text.
            max_chars (int): The maximum number of characters allowed per group (default is 800).

        Returns:
            List[str]: A list of text groups.
        """
        sentences = GLiNERHelper.tokenize_sentences(text)
        groups = GLiNERHelper.build_sentence_groups(sentences, max_chars)
        return groups