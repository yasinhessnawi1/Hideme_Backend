"""
Unit tests for gliner_helper.py module.

This test file covers the GLiNERHelper class and its methods with both positive
and negative test cases to ensure proper functionality and error handling.
"""

import hashlib
import unittest

# Import the module to be tested
from backend.app.utils.helpers.gliner_helper import GLiNERHelper


class TestGLiNERHelperGetCacheKey(unittest.TestCase):
    """Test cases for GLiNERHelper.get_cache_key method."""

    def test_get_cache_key_with_text_only(self):
        """Test get_cache_key with text only."""
        # Test with text only
        text = "This is a test text"
        key = GLiNERHelper.get_cache_key(text)

        # Verify the key is an MD5 hash
        expected_key = hashlib.md5(text.encode('utf-8')).hexdigest()
        self.assertEqual(key, expected_key)
        self.assertEqual(len(key), 32)  # MD5 hash is 32 characters

    def test_get_cache_key_with_text_and_entities(self):
        """Test get_cache_key with text and requested entities."""
        # Test with text and entities
        text = "This is a test text"
        entities = ["PERSON", "ORGANIZATION"]
        key = GLiNERHelper.get_cache_key(text, entities)

        # Verify the key includes both text and sorted entities
        expected_key_data = text + '|' + ','.join(sorted(entities))
        expected_key = hashlib.md5(expected_key_data.encode('utf-8')).hexdigest()
        self.assertEqual(key, expected_key)

    def test_get_cache_key_with_empty_text(self):
        """Test get_cache_key with empty text."""
        # Test with empty text
        text = ""
        key = GLiNERHelper.get_cache_key(text)

        # Verify the key is an MD5 hash of empty string
        expected_key = hashlib.md5(b'').hexdigest()
        self.assertEqual(key, expected_key)

    def test_get_cache_key_with_empty_entities(self):
        """Test get_cache_key with empty entities list."""
        text = "This is a test text"
        entities = []
        key = GLiNERHelper.get_cache_key(text, entities)

        # Expected key data: text + '|' (empty joined sorted empty list)
        expected_key_data = text + '|'
        expected_key = hashlib.md5(expected_key_data.encode('utf-8')).hexdigest()
        self.assertEqual(key, expected_key)

    def test_get_cache_key_with_unicode_text(self):
        """Test get_cache_key with Unicode text."""
        # Test with Unicode text
        text = "This is a test with Unicode characters: 你好, こんにちは"
        key = GLiNERHelper.get_cache_key(text)

        # Verify the key is an MD5 hash of the Unicode text
        expected_key = hashlib.md5(text.encode('utf-8')).hexdigest()
        self.assertEqual(key, expected_key)

    def test_get_cache_key_with_unsorted_entities(self):
        """Test get_cache_key with unsorted entities list."""
        # Test with unsorted entities
        text = "This is a test text"
        entities1 = ["ORGANIZATION", "PERSON"]
        entities2 = ["PERSON", "ORGANIZATION"]

        key1 = GLiNERHelper.get_cache_key(text, entities1)
        key2 = GLiNERHelper.get_cache_key(text, entities2)

        # Verify both keys are the same (entities are sorted)
        self.assertEqual(key1, key2)


class TestGLiNERHelperCacheOperations(unittest.TestCase):
    """Test cases for GLiNERHelper cache operations."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        # Clear the cache before each test
        GLiNERHelper._gliner_cache = {}
        GLiNERHelper._hideme_cache = {}

    def test_get_cached_result_gliner_namespace(self):
        """Test get_cached_result with gliner namespace."""
        # Set up test data
        key = "test_key"
        value = {"result": "test_value"}
        GLiNERHelper._gliner_cache[key] = value

        # Test retrieving from gliner namespace
        result = GLiNERHelper.get_cached_result(key, "gliner")

        # Verify the result
        self.assertEqual(result, value)

    def test_get_cached_result_hideme_namespace(self):
        """Test get_cached_result with hideme namespace."""
        # Set up test data
        key = "test_key"
        value = {"result": "test_value"}
        GLiNERHelper._hideme_cache[key] = value

        # Test retrieving from hideme namespace
        result = GLiNERHelper.get_cached_result(key, "hideme")

        # Verify the result
        self.assertEqual(result, value)

    def test_get_cached_result_invalid_namespace(self):
        """Test get_cached_result with invalid namespace."""
        # Set up test data
        key = "test_key"
        value = {"result": "test_value"}
        GLiNERHelper._gliner_cache[key] = value

        # Test retrieving from invalid namespace
        result = GLiNERHelper.get_cached_result(key, "invalid_namespace")

        # Verify the result is None
        self.assertIsNone(result)

    def test_get_cached_result_nonexistent_key(self):
        """Test get_cached_result with nonexistent key."""
        # Test retrieving nonexistent key
        result = GLiNERHelper.get_cached_result("nonexistent_key", "gliner")

        # Verify the result is None
        self.assertIsNone(result)

    def test_set_cached_result_gliner_namespace(self):
        """Test set_cached_result with gliner namespace."""
        # Set up test data
        key = "test_key"
        value = {"result": "test_value"}

        # Set the value in gliner namespace
        GLiNERHelper.set_cached_result(key, value, "gliner")

        # Verify the value was set
        self.assertEqual(GLiNERHelper._gliner_cache[key], value)
        self.assertNotIn(key, GLiNERHelper._hideme_cache)

    def test_set_cached_result_hideme_namespace(self):
        """Test set_cached_result with hideme namespace."""
        # Set up test data
        key = "test_key"
        value = {"result": "test_value"}

        # Set the value in hideme namespace
        GLiNERHelper.set_cached_result(key, value, "hideme")

        # Verify the value was set
        self.assertEqual(GLiNERHelper._hideme_cache[key], value)
        self.assertNotIn(key, GLiNERHelper._gliner_cache)

    def test_set_cached_result_invalid_namespace(self):
        """Test set_cached_result with invalid namespace."""
        # Set up test data
        key = "test_key"
        value = {"result": "test_value"}

        # Set the value in invalid namespace
        GLiNERHelper.set_cached_result(key, value, "invalid_namespace")

        # Verify the value was not set in either namespace
        self.assertNotIn(key, GLiNERHelper._gliner_cache)
        self.assertNotIn(key, GLiNERHelper._hideme_cache)

    def test_set_and_get_cached_result(self):
        """Test setting and then getting a cached result."""
        # Set up test data
        key = "test_key"
        value = {"result": "test_value"}

        # Set the value
        GLiNERHelper.set_cached_result(key, value, "gliner")

        # Get the value
        result = GLiNERHelper.get_cached_result(key, "gliner")

        # Verify the result
        self.assertEqual(result, value)


class TestGLiNERHelperEstimateCharCount(unittest.TestCase):
    """Test cases for GLiNERHelper.estimate_char_count method."""

    def test_estimate_char_count_normal_text(self):
        """Test estimate_char_count with normal text."""
        # Test with normal text
        text = "This is a test text"
        count = GLiNERHelper.estimate_char_count(text)

        # Verify the count
        self.assertEqual(count, len(text))
        self.assertEqual(count, 19)

    def test_estimate_char_count_empty_text(self):
        """Test estimate_char_count with empty text."""
        # Test with empty text
        text = ""
        count = GLiNERHelper.estimate_char_count(text)

        # Verify the count
        self.assertEqual(count, 0)

    def test_estimate_char_count_unicode_text(self):
        """Test estimate_char_count with Unicode text."""
        # Test with Unicode text
        text = "This is a test with Unicode characters: 你好, こんにちは"
        count = GLiNERHelper.estimate_char_count(text)

        # Verify the count
        self.assertEqual(count, len(text))
        self.assertEqual(count, 49)

    def test_estimate_char_count_whitespace(self):
        """Test estimate_char_count with whitespace."""
        # Test with whitespace
        text = "  \t\n  "
        count = GLiNERHelper.estimate_char_count(text)

        # Verify the count
        self.assertEqual(count, len(text))
        self.assertEqual(count, 6)


class TestGLiNERHelperChunkLargeSentenceByChar(unittest.TestCase):
    """Test cases for GLiNERHelper.chunk_large_sentence_by_char method."""

    def test_chunk_large_sentence_by_char_short_sentence(self):
        """Test chunk_large_sentence_by_char with a sentence shorter than max_chars."""
        # Test with short sentence
        sentence = "This is a short sentence."
        max_chars = 30
        chunks = GLiNERHelper.chunk_large_sentence_by_char(sentence, max_chars)

        # Verify the chunks
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], sentence)

    def test_chunk_large_sentence_by_char_long_sentence(self):
        """Test chunk_large_sentence_by_char with a sentence longer than max_chars."""
        # Test with long sentence
        sentence = "This is a very long sentence that needs to be split into multiple chunks because it exceeds the maximum character limit."
        max_chars = 30
        chunks = GLiNERHelper.chunk_large_sentence_by_char(sentence, max_chars)

        # Verify the chunks
        self.assertGreater(len(chunks), 1)

        # Verify each chunk is within the max_chars limit
        for chunk in chunks:
            self.assertLessEqual(len(chunk), max_chars)

        # Verify the combined chunks equal the original sentence
        self.assertEqual(' '.join(chunks), sentence)

    def test_chunk_large_sentence_by_char_exact_max_chars(self):
        """Test chunk_large_sentence_by_char with a sentence exactly at max_chars."""
        # Use a sentence of exactly 30 characters.
        sentence = "123456789012345678901234567890"  # exactly 30 characters
        max_chars = 30
        chunks = GLiNERHelper.chunk_large_sentence_by_char(sentence, max_chars)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], sentence)
        self.assertEqual(len(chunks[0]), max_chars)

    def test_chunk_large_sentence_by_char_single_long_word(self):
        """Test chunk_large_sentence_by_char with a single word longer than max_chars."""
        sentence = "Supercalifragilisticexpialidocious"
        max_chars = 10
        chunks = GLiNERHelper.chunk_large_sentence_by_char(sentence, max_chars)

        # Since the word itself is longer than max_chars,
        # it should not be split and should be returned as a single chunk.
        self.assertEqual(len(chunks), 1,
                         f"Expected 1 chunk, but got {len(chunks)} chunks.")
        self.assertEqual(chunks[0], sentence)
        self.assertGreater(len(chunks[0]), max_chars)

    def test_chunk_large_sentence_by_char_multiple_chunks(self):
        """Test chunk_large_sentence_by_char with a sentence that splits into multiple chunks."""
        # Test with sentence that splits into multiple chunks
        sentence = "This sentence will be split into three chunks because it exceeds the maximum character limit."
        max_chars = 25
        chunks = GLiNERHelper.chunk_large_sentence_by_char(sentence, max_chars)

        # The algorithm returns 4 chunks.
        self.assertEqual(len(chunks), 4)

        # Verify each chunk is within the max_chars limit.
        for chunk in chunks:
            self.assertLessEqual(len(chunk), max_chars)

        # Verify the combined chunks equal the original sentence.
        self.assertEqual(' '.join(chunks), sentence)

    def test_chunk_large_sentence_by_char_empty_sentence(self):
        """Test chunk_large_sentence_by_char with an empty sentence."""
        # Test with empty sentence
        sentence = ""
        max_chars = 30
        chunks = GLiNERHelper.chunk_large_sentence_by_char(sentence, max_chars)

        # Verify the chunks
        self.assertEqual(len(chunks), 0)


class TestGLiNERHelperTokenizeSentences(unittest.TestCase):
    """Test cases for GLiNERHelper.tokenize_sentences method."""

    def test_tokenize_sentences_basic(self):
        """Test tokenize_sentences with basic sentences."""
        # Test with basic sentences
        text = "This is the first sentence. This is the second sentence. This is the third sentence."
        sentences = GLiNERHelper.tokenize_sentences(text)

        # Verify the sentences
        self.assertEqual(len(sentences), 3)
        self.assertEqual(sentences[0], "This is the first sentence.")
        self.assertEqual(sentences[1], "This is the second sentence.")
        self.assertEqual(sentences[2], "This is the third sentence.")

    def test_tokenize_sentences_with_different_punctuation(self):
        """Test tokenize_sentences with different punctuation marks."""
        # Test with different punctuation
        text = "This is a statement. This is a question? This is an exclamation!"
        sentences = GLiNERHelper.tokenize_sentences(text)

        # Verify the sentences
        self.assertEqual(len(sentences), 3)
        self.assertEqual(sentences[0], "This is a statement.")
        self.assertEqual(sentences[1], "This is a question?")
        self.assertEqual(sentences[2], "This is an exclamation!")

    def test_tokenize_sentences_with_extra_whitespace(self):
        """Test tokenize_sentences with extra whitespace."""
        # Test with extra whitespace
        text = "  This is the first sentence.  \n  This is the second sentence.  "
        sentences = GLiNERHelper.tokenize_sentences(text)

        # Verify the sentences
        self.assertEqual(len(sentences), 2)
        self.assertEqual(sentences[0], "This is the first sentence.")
        self.assertEqual(sentences[1], "This is the second sentence.")

    def test_tokenize_sentences_with_empty_text(self):
        """Test tokenize_sentences with empty text."""
        # Test with empty text
        text = ""
        sentences = GLiNERHelper.tokenize_sentences(text)

        # Verify the sentences
        self.assertEqual(len(sentences), 0)

    def test_tokenize_sentences_with_single_sentence(self):
        """Test tokenize_sentences with a single sentence."""
        # Test with single sentence
        text = "This is a single sentence."
        sentences = GLiNERHelper.tokenize_sentences(text)

        # Verify the sentences
        self.assertEqual(len(sentences), 1)
        self.assertEqual(sentences[0], "This is a single sentence.")

    def test_tokenize_sentences_with_no_punctuation(self):
        """Test tokenize_sentences with text that has no punctuation."""
        # Test with no punctuation
        text = "This text has no punctuation"
        sentences = GLiNERHelper.tokenize_sentences(text)

        # Verify the sentences
        self.assertEqual(len(sentences), 1)
        self.assertEqual(sentences[0], "This text has no punctuation")

    def test_tokenize_sentences_with_abbreviations(self):
        """Test tokenize_sentences with text containing abbreviations."""
        # Test with abbreviations
        text = "Dr. Smith visited Mr. Jones. They discussed Mrs. Brown's case."
        sentences = GLiNERHelper.tokenize_sentences(text)

        # Verify the sentences (note: this may split on abbreviations)
        self.assertEqual(len(sentences), 5)
        self.assertEqual(sentences[0], "Dr.")


class TestBuildSentenceGroups(unittest.TestCase):
    """Tests for the build_sentence_groups method."""

    def test_group_multiple_sentences_fit_in_one_group(self):
        """Positive: All sentences can fit into one group."""
        sentences = [
            "This is a sentence.",
            "Second sentence.",
            "Third sentence."
        ]
        max_chars = 100  # Big enough to hold all sentences in one group
        groups = GLiNERHelper.build_sentence_groups(sentences, max_chars)

        # Expect a single group
        self.assertEqual(len(groups), 1)
        # The group should be exactly the sentences joined with a space
        self.assertEqual(groups[0], " ".join(sentences))
        # Each group should not exceed max_chars
        for group in groups:
            self.assertLessEqual(len(group), max_chars)

    def test_group_sentence_exceeding_max_chars(self):
        """Positive: A sentence longer than max_chars gets split."""
        sentences = [
            "Short sentence.",
            "This is a very long sentence that definitely exceeds the limit."
        ]
        max_chars = 30
        groups = GLiNERHelper.build_sentence_groups(sentences, max_chars)

        # Each group should be less than or equal to max_chars
        for group in groups:
            self.assertLessEqual(len(group), max_chars)

        # When rejoining the groups, the full string should match the sentences joined by space.
        self.assertEqual(" ".join(groups), " ".join(sentences))

    def test_build_sentence_groups_empty_list(self):
        """Negative: An empty list of sentences returns an empty list."""
        sentences = []
        groups = GLiNERHelper.build_sentence_groups(sentences, max_chars=50)
        self.assertEqual(groups, [])


class TestSplitIntoSentenceGroups(unittest.TestCase):
    """Tests for the split_into_sentence_groups method."""

    def test_split_text_into_groups(self):
        """Positive: A multi-sentence text gets split into valid groups within max_chars limit."""
        text = "This is the first sentence. This is the second sentence? And this is the third sentence!"
        max_chars = 50
        groups = GLiNERHelper.split_into_sentence_groups(text, max_chars)

        # There should be at least one group returned
        self.assertTrue(len(groups) > 0)
        # Each group must not exceed max_chars
        for group in groups:
            self.assertLessEqual(len(group), max_chars)

        # Reconstruct the tokenized text and compare (join with a single space)
        tokenized_text = " ".join(GLiNERHelper.tokenize_sentences(text))
        joined_groups = " ".join(groups)
        self.assertEqual(joined_groups, tokenized_text)

    def test_split_into_sentence_groups_empty_text(self):
        """Negative: Passing empty text returns an empty list."""
        text = ""
        groups = GLiNERHelper.split_into_sentence_groups(text)
        self.assertEqual(groups, [])

    def test_split_into_sentence_groups_whitespace_text(self):
        """Negative: Passing text with only whitespace returns an empty list."""
        text = "   "
        groups = GLiNERHelper.split_into_sentence_groups(text)
        self.assertEqual(groups, [])
