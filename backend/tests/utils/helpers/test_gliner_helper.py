import hashlib
import unittest

from backend.app.utils.helpers.gliner_helper import GLiNERHelper


# Test cases for GLiNERHelper.get_cache_key method
class TestGLiNERHelperGetCacheKey(unittest.TestCase):

    # Test get_cache_key with text only
    def test_get_cache_key_with_text_only(self):
        text = "This is a test text"

        key = GLiNERHelper.get_cache_key(text)

        expected_key = hashlib.md5(text.encode("utf-8")).hexdigest()

        self.assertEqual(key, expected_key)

        self.assertEqual(len(key), 32)

    # Test get_cache_key with text and requested entities
    def test_get_cache_key_with_text_and_entities(self):
        text = "This is a test text"

        entities = ["PERSON", "ORGANIZATION"]

        key = GLiNERHelper.get_cache_key(text, entities)

        expected_key_data = text + "|" + ",".join(sorted(entities))

        expected_key = hashlib.md5(expected_key_data.encode("utf-8")).hexdigest()

        self.assertEqual(key, expected_key)

    # Test get_cache_key with empty text
    def test_get_cache_key_with_empty_text(self):
        text = ""

        key = GLiNERHelper.get_cache_key(text)

        expected_key = hashlib.md5(b"").hexdigest()

        self.assertEqual(key, expected_key)

    # Test get_cache_key with empty entities list
    def test_get_cache_key_with_empty_entities(self):
        text = "This is a test text"

        entities = []

        key = GLiNERHelper.get_cache_key(text, entities)

        expected_key_data = text + "|"

        expected_key = hashlib.md5(expected_key_data.encode("utf-8")).hexdigest()

        self.assertEqual(key, expected_key)

    # Test get_cache_key with Unicode text
    def test_get_cache_key_with_unicode_text(self):
        text = "This is a test with Unicode characters: 你好, こんにちは"

        key = GLiNERHelper.get_cache_key(text)

        expected_key = hashlib.md5(text.encode("utf-8")).hexdigest()

        self.assertEqual(key, expected_key)

    # Test get_cache_key sorts entities for consistency
    def test_get_cache_key_with_unsorted_entities(self):
        text = "This is a test text"

        entities1 = ["ORGANIZATION", "PERSON"]

        entities2 = ["PERSON", "ORGANIZATION"]

        key1 = GLiNERHelper.get_cache_key(text, entities1)

        key2 = GLiNERHelper.get_cache_key(text, entities2)

        self.assertEqual(key1, key2)


# Test cases for GLiNERHelper cache operations
class TestGLiNERHelperCacheOperations(unittest.TestCase):

    # Clear caches before each test
    def setUp(self):
        GLiNERHelper._gliner_cache = {}

        GLiNERHelper._hideme_cache = {}

    # Test retrieving from gliner namespace cache
    def test_get_cached_result_gliner_namespace(self):
        key = "test_key"

        value = {"result": "test_value"}

        GLiNERHelper._gliner_cache[key] = value

        result = GLiNERHelper.get_cached_result(key, "gliner")

        self.assertEqual(result, value)

    # Test retrieving from hideme namespace cache
    def test_get_cached_result_hideme_namespace(self):
        key = "test_key"

        value = {"result": "test_value"}

        GLiNERHelper._hideme_cache[key] = value

        result = GLiNERHelper.get_cached_result(key, "hideme")

        self.assertEqual(result, value)

    # Test invalid namespace returns None
    def test_get_cached_result_invalid_namespace(self):
        key = "test_key"

        value = {"result": "test_value"}

        GLiNERHelper._gliner_cache[key] = value

        result = GLiNERHelper.get_cached_result(key, "invalid_namespace")

        self.assertIsNone(result)

    # Test nonexistent key returns None
    def test_get_cached_result_nonexistent_key(self):
        result = GLiNERHelper.get_cached_result("nonexistent_key", "gliner")

        self.assertIsNone(result)

    # Test setting value in gliner namespace
    def test_set_cached_result_gliner_namespace(self):
        key = "test_key"

        value = {"result": "test_value"}

        GLiNERHelper.set_cached_result(key, value, "gliner")

        self.assertEqual(GLiNERHelper._gliner_cache[key], value)

        self.assertNotIn(key, GLiNERHelper._hideme_cache)

    # Test setting value in hideme namespace
    def test_set_cached_result_hideme_namespace(self):
        key = "test_key"

        value = {"result": "test_value"}

        GLiNERHelper.set_cached_result(key, value, "hideme")

        self.assertEqual(GLiNERHelper._hideme_cache[key], value)

        self.assertNotIn(key, GLiNERHelper._gliner_cache)

    # Test setting in invalid namespace does nothing
    def test_set_cached_result_invalid_namespace(self):
        key = "test_key"

        value = {"result": "test_value"}

        GLiNERHelper.set_cached_result(key, value, "invalid_namespace")

        self.assertNotIn(key, GLiNERHelper._gliner_cache)

        self.assertNotIn(key, GLiNERHelper._hideme_cache)

    # Test set then get returns the same value
    def test_set_and_get_cached_result(self):
        key = "test_key"

        value = {"result": "test_value"}

        GLiNERHelper.set_cached_result(key, value, "gliner")

        result = GLiNERHelper.get_cached_result(key, "gliner")

        self.assertEqual(result, value)


# Test cases for GLiNERHelper.estimate_char_count method
class TestGLiNERHelperEstimateCharCount(unittest.TestCase):

    # Test count for normal text
    def test_estimate_char_count_normal_text(self):
        text = "This is a test text"

        count = GLiNERHelper.estimate_char_count(text)

        self.assertEqual(count, len(text))

        self.assertEqual(count, 19)

    # Test count for empty text
    def test_estimate_char_count_empty_text(self):
        text = ""

        count = GLiNERHelper.estimate_char_count(text)

        self.assertEqual(count, 0)

    # Test count for Unicode text
    def test_estimate_char_count_unicode_text(self):
        text = "This is a test with Unicode characters: 你好, こんにちは"

        count = GLiNERHelper.estimate_char_count(text)

        self.assertEqual(count, len(text))

        self.assertEqual(count, 49)

    # Test count includes whitespace characters
    def test_estimate_char_count_whitespace(self):
        text = "  \t\n  "

        count = GLiNERHelper.estimate_char_count(text)

        self.assertEqual(count, len(text))

        self.assertEqual(count, 6)


# Test cases for GLiNERHelper.chunk_large_sentence_by_char method
class TestGLiNERHelperChunkLargeSentenceByChar(unittest.TestCase):

    # Short sentences remain as a single chunk
    def test_chunk_large_sentence_by_char_short_sentence(self):

        sentence = "This is a short sentence."

        max_chars = 30

        chunks = GLiNERHelper.chunk_large_sentence_by_char(sentence, max_chars)

        self.assertEqual(len(chunks), 1)

        self.assertEqual(chunks[0], sentence)

    # Long sentences split into multiple chunks
    def test_chunk_large_sentence_by_char_long_sentence(self):

        sentence = (
            "This is a very long sentence that needs to be split into multiple chunks "
            "because it exceeds the maximum character limit."
        )

        max_chars = 30

        chunks = GLiNERHelper.chunk_large_sentence_by_char(sentence, max_chars)

        self.assertGreater(len(chunks), 1)

        for chunk in chunks:
            self.assertLessEqual(len(chunk), max_chars)

        self.assertEqual(" ".join(chunks), sentence)

    # Exact max_chars yields single chunk
    def test_chunk_large_sentence_by_char_exact_max_chars(self):

        sentence = "123456789012345678901234567890"

        max_chars = 30

        chunks = GLiNERHelper.chunk_large_sentence_by_char(sentence, max_chars)

        self.assertEqual(len(chunks), 1)

        self.assertEqual(chunks[0], sentence)

        self.assertEqual(len(chunks[0]), max_chars)

    # Single long word not split
    def test_chunk_large_sentence_by_char_single_long_word(self):

        sentence = "Supercalifragilisticexpialidocious"

        max_chars = 10

        chunks = GLiNERHelper.chunk_large_sentence_by_char(sentence, max_chars)

        self.assertEqual(len(chunks), 1)

        self.assertEqual(chunks[0], sentence)

        self.assertGreater(len(chunks[0]), max_chars)

    # Multiple sentences produce multiple chunks
    def test_chunk_large_sentence_by_char_multiple_chunks(self):

        sentence = (
            "This sentence will be split into three chunks because it exceeds the "
            "maximum character limit."
        )

        max_chars = 25

        chunks = GLiNERHelper.chunk_large_sentence_by_char(sentence, max_chars)

        self.assertEqual(len(chunks), 4)

        for chunk in chunks:
            self.assertLessEqual(len(chunk), max_chars)

        self.assertEqual(" ".join(chunks), sentence)

    # Empty sentence yields no chunks
    def test_chunk_large_sentence_by_char_empty_sentence(self):

        sentence = ""

        max_chars = 30

        chunks = GLiNERHelper.chunk_large_sentence_by_char(sentence, max_chars)

        self.assertEqual(len(chunks), 0)


# Test cases for GLiNERHelper.tokenize_sentences method
class TestGLiNERHelperTokenizeSentences(unittest.TestCase):

    # Basic sentence tokenization
    def test_tokenize_sentences_basic(self):
        text = (
            "This is the first sentence. This is the second sentence. "
            "This is the third sentence."
        )

        sentences = GLiNERHelper.tokenize_sentences(text)

        self.assertEqual(len(sentences), 3)

        self.assertEqual(sentences[0], "This is the first sentence.")

        self.assertEqual(sentences[1], "This is the second sentence.")

        self.assertEqual(sentences[2], "This is the third sentence.")

    # Tokenization with varied punctuation
    def test_tokenize_sentences_with_different_punctuation(self):
        text = "This is a statement. This is a question? This is an exclamation!"

        sentences = GLiNERHelper.tokenize_sentences(text)

        self.assertEqual(len(sentences), 3)

        self.assertEqual(sentences[0], "This is a statement.")

        self.assertEqual(sentences[1], "This is a question?")

        self.assertEqual(sentences[2], "This is an exclamation!")

    # Tokenization with extra whitespace
    def test_tokenize_sentences_with_extra_whitespace(self):
        text = "  This is the first sentence.  \n  This is the second sentence.  "

        sentences = GLiNERHelper.tokenize_sentences(text)

        self.assertEqual(len(sentences), 2)

        self.assertEqual(sentences[0], "This is the first sentence.")

        self.assertEqual(sentences[1], "This is the second sentence.")

    # Empty text yields no sentences
    def test_tokenize_sentences_with_empty_text(self):
        text = ""

        sentences = GLiNERHelper.tokenize_sentences(text)

        self.assertEqual(len(sentences), 0)

    # Single sentence remains one element
    def test_tokenize_sentences_with_single_sentence(self):
        text = "This is a single sentence."

        sentences = GLiNERHelper.tokenize_sentences(text)

        self.assertEqual(len(sentences), 1)

        self.assertEqual(sentences[0], "This is a single sentence.")

    # No punctuation yields the whole text as one sentence
    def test_tokenize_sentences_with_no_punctuation(self):
        text = "This text has no punctuation"

        sentences = GLiNERHelper.tokenize_sentences(text)

        self.assertEqual(len(sentences), 1)

        self.assertEqual(sentences[0], "This text has no punctuation")

    # Abbreviations may cause extra splits
    def test_tokenize_sentences_with_abbreviations(self):
        text = "Dr. Smith visited Mr. Jones. They discussed Mrs. Brown's case."

        sentences = GLiNERHelper.tokenize_sentences(text)

        self.assertEqual(len(sentences), 5)

        self.assertEqual(sentences[0], "Dr.")


# Tests for build_sentence_groups method
class TestBuildSentenceGroups(unittest.TestCase):

    # Group sentences into one if within limit
    def test_group_multiple_sentences_fit_in_one_group(self):

        sentences = ["This is a sentence.", "Second sentence.", "Third sentence."]

        max_chars = 100

        groups = GLiNERHelper.build_sentence_groups(sentences, max_chars)

        self.assertEqual(len(groups), 1)

        self.assertEqual(groups[0], " ".join(sentences))

        for group in groups:
            self.assertLessEqual(len(group), max_chars)

    # Split groups when sentences exceed limit
    def test_group_sentence_exceeding_max_chars(self):

        sentences = [
            "Short sentence.",
            "This is a very long sentence that definitely exceeds the limit.",
        ]

        max_chars = 30

        groups = GLiNERHelper.build_sentence_groups(sentences, max_chars)

        for group in groups:
            self.assertLessEqual(len(group), max_chars)

        self.assertEqual(" ".join(groups), " ".join(sentences))

    # Empty list returns empty groups
    def test_build_sentence_groups_empty_list(self):

        sentences = []

        groups = GLiNERHelper.build_sentence_groups(sentences, max_chars=50)

        self.assertEqual(groups, [])


# Tests for split_into_sentence_groups method
class TestSplitIntoSentenceGroups(unittest.TestCase):

    # Split text into groups respecting max_chars
    def test_split_text_into_groups(self):
        text = (
            "This is the first sentence. This is the second sentence? "
            "And this is the third sentence!"
        )

        max_chars = 50

        groups = GLiNERHelper.split_into_sentence_groups(text, max_chars)

        self.assertTrue(len(groups) > 0)

        for group in groups:
            self.assertLessEqual(len(group), max_chars)

        tokenized_text = " ".join(GLiNERHelper.tokenize_sentences(text))

        joined_groups = " ".join(groups)

        self.assertEqual(joined_groups, tokenized_text)

    # Empty text yields no groups
    def test_split_into_sentence_groups_empty_text(self):
        text = ""

        groups = GLiNERHelper.split_into_sentence_groups(text)

        self.assertEqual(groups, [])

    # Whitespace-only text yields no groups
    def test_split_into_sentence_groups_whitespace_text(self):
        text = "   "

        groups = GLiNERHelper.split_into_sentence_groups(text)

        self.assertEqual(groups, [])
