"""
This module contains the GLiNERHelper class, a utility for processing text according to GLiNER's requirements.
The class provides static methods for generating cache keys, caching results, tokenizing text into sentences,
truncating overly long sentences into chunks, and grouping sentences into manageable clusters based on a character limit.
"""

import hashlib
from typing import List, Optional, Any, Dict


class GLiNERHelper:
    """
    GLiNERHelper is a helper class for GLiNER text processing tasks.

    It includes methods to:
    - Generate unique cache keys based on text and requested entities.
    - Retrieve and store cached results to optimize processing.
    - Estimate character counts.
    - Break long sentences into smaller chunks based on a character limit.
    - Tokenize text into sentences using regex-based splitting.
    - Build sentence groups that obey a maximum character limit.
    - Split an entire text into groups of sentences suitable for API processing.
    """
    # Protected cache to store processed text results.
    _gliner_cache: Dict[str, Any] = {}
    _hideme_cache: Dict[str, Any] = {}

    @staticmethod
    def get_cache_key(text: str, requested_entities: Optional[List[str]] = None) -> str:
        """
        Generate a unique cache key based on the input text and requested entities.

        Args:
            text (str): The input text.
            requested_entities (Optional[List[str]]): An optional list of requested entities.

        Returns:
            str: A unique MD5 hash string representing the cache key.
        """
        # Start with the provided text as base key data.
        key_data = text
        # If requested_entities is provided, sort them and append to the key data.
        if requested_entities:
            key_data += '|' + ','.join(sorted(requested_entities))
        # Generate an MD5 hash of the combined key data.
        return hashlib.md5(key_data.encode('utf-8')).hexdigest()

    @staticmethod
    def get_cached_result(key: str, cache_namespace: str = "gliner") -> Optional[Any]:
        """
        Retrieve a cached result from the specified namespace.
        """
        # retrieve cached results using the generated key with his own namespace.
        if cache_namespace == "gliner":
            return GLiNERHelper._gliner_cache.get(key)
        elif cache_namespace == "hideme":
            return GLiNERHelper._hideme_cache.get(key)
        else:
            return None

    @staticmethod
    def set_cached_result(key: str, value: Any, cache_namespace: str = "gliner") -> None:
        """
        Store a result in the cache under the specified namespace.
        """
        # Set cached results using the generated key with his own namespace.
        if cache_namespace == "gliner":
            GLiNERHelper._gliner_cache[key] = value
        elif cache_namespace == "hideme":
            GLiNERHelper._hideme_cache[key] = value

    @staticmethod
    def estimate_char_count(text: str) -> int:
        """
        Estimate the number of characters in the input text.

        Args:
            text (str): The input text.

        Returns:
            int: The number of characters in the text.
        """
        # Calculate and return the length of the text (character count).
        return len(text)

    @staticmethod
    def chunk_large_sentence_by_char(sentence: str, max_chars: int) -> List[str]:
        """
        Break an overly long sentence into smaller chunks, each containing at most max_chars characters.

        The method splits the sentence into words and accumulates words until the total character count
        (including spaces) would exceed max_chars.

        Args:
            sentence (str): The sentence to split.
            max_chars (int): Maximum number of characters allowed per chunk.

        Returns:
            List[str]: A list of text chunks, each with at most max_chars characters.
        """
        # Split the sentence into a list of words.
        words = sentence.split()
        # Initialize an empty list for holding the text chunks.
        chunks = []
        # Initialize a temporary list for the current chunk.
        current_chunk = []
        # Initialize the current character count to zero.
        current_length = 0
        # Loop through each word in the sentence.
        for word in words:
            # Calculate additional length including a preceding space if needed.
            additional = len(word) if not current_chunk else len(word) + 1
            # If adding this word exceeds the max_chars limit...
            if current_length + additional > max_chars:
                # Join current words into a chunk and add to chunks.
                chunks.append(" ".join(current_chunk))
                # Start a new chunk with the current word.
                current_chunk = [word]
                # Reset the current length based on the current word's length.
                current_length = len(word)
            else:
                # Otherwise, add the word to the current chunk.
                current_chunk.append(word)
                # Update the current length with the additional characters.
                current_length += additional
        # If there are any words left in the current chunk, join and append them.
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        # Return the list of chunks.
        return chunks

    @staticmethod
    def tokenize_sentences(text: str) -> List[str]:
        """
        Split the input text into sentences using a punctuation-based regular expression.

        Args:
            text (str): The input text.

        Returns:
            List[str]: A list of sentence strings.
        """
        # Import the regular expressions module.
        import re
        # Split the text based on punctuation marks followed by whitespace.
        raw_sentences = re.split(r'(?<=[.!?])\s+', text)
        # Remove any extra whitespace from each sentence and filter out empty strings.
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
        # Initialize an empty list to store groups.
        groups = []
        # Initialize an empty list for the current group of sentences.
        current_group = []
        # Track the current length of the group.
        current_length = 0

        # Loop through each sentence in the list.
        for sent in sentences:
            # Calculate the length of the current sentence.
            sent_length = len(sent)
            # If this sentence on its own exceeds the max_chars limit...
            if sent_length > max_chars:
                # If the current group is not empty, join the group and append to groups.
                if current_group:
                    groups.append(" ".join(current_group))
                    # Reset the current group and length.
                    current_group, current_length = [], 0
                # Split the long sentence into manageable chunks.
                groups.extend(GLiNERHelper.chunk_large_sentence_by_char(sent, max_chars))
                # Continue to the next sentence.
                continue

            # Calculate extra characters required, accounting for a space if current group is not empty.
            additional = sent_length if not current_group else sent_length + 1

            # If adding this sentence exceeds the max_chars limit...
            if current_length + additional > max_chars:
                # Append the current group as a single string to groups.
                groups.append(" ".join(current_group))
                # Start a new group with the current sentence.
                current_group = [sent]
                # Update the current length to the length of the current sentence.
                current_length = sent_length
            else:
                # Otherwise, add the sentence to the current group.
                current_group.append(sent)
                # Update the current length with the additional characters.
                current_length += additional

        # If there are any remaining sentences in the current group, add them to groups.
        if current_group:
            groups.append(" ".join(current_group))
        # Return the list of sentence groups.
        return groups

    @staticmethod
    def split_into_sentence_groups(text: str, max_chars: int = 800) -> List[str]:
        """
        Split the input text into groups of sentences such that each group contains at most max_chars characters.

        This method tokenizes the text into sentences using a punctuation-based regex,
        then groups the sentences using build_sentence_groups().

        Args:
            text (str): The input text.
            max_chars (int): The maximum number of characters allowed per group (default is 800).

        Returns:
            List[str]: A list of text groups.
        """
        # Tokenize the text into sentences.
        sentences = GLiNERHelper.tokenize_sentences(text)
        # Build groups of sentences with the specified maximum characters per group.
        groups = GLiNERHelper.build_sentence_groups(sentences, max_chars)
        # Return the list of sentence groups.
        return groups
