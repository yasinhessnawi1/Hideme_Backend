import unittest
from unittest.mock import patch

from backend.app.utils.helpers.text_utils import TextUtils, EntityUtils


class MockRecognizerResult:
    """Mock class for presidio_analyzer.RecognizerResult."""

    def __init__(self, start, end, score=0.8, entity_type="PERSON"):
        self.start = start
        self.end = end
        self.score = score
        self.entity_type = entity_type

    def __repr__(self):
        return f"MR({self.start}-{self.end})"


# Tests for TextUtils.reconstruct_text_and_mapping
class TestTextUtilsReconstructTextAndMapping(unittest.TestCase):
    """Test cases for reconstruct_text_and_mapping method."""

    # basic reconstruction of text and mapping
    def test_reconstruct_text_and_mapping_basic(self):
        words = [
            {"text": "Hello", "x0": 10, "y0": 20, "x1": 50, "y1": 30},
            {"text": "world", "x0": 60, "y0": 20, "x1": 100, "y1": 30},
            {"text": "!", "x0": 110, "y0": 20, "x1": 120, "y1": 30},
        ]

        full_text, mapping = TextUtils.reconstruct_text_and_mapping(words)

        self.assertEqual(full_text, "Hello world !")

        self.assertEqual(len(mapping), 3)

        self.assertEqual(mapping[0][0], words[0])

        self.assertEqual(mapping[0][1], 0)

        self.assertEqual(mapping[0][2], 5)

        self.assertEqual(mapping[1][0], words[1])

        self.assertEqual(mapping[1][1], 6)

        self.assertEqual(mapping[1][2], 11)

        self.assertEqual(mapping[2][0], words[2])

        self.assertEqual(mapping[2][1], 12)

        self.assertEqual(mapping[2][2], 13)

    # reconstruction with empty word list
    def test_reconstruct_text_and_mapping_empty_list(self):
        full_text, mapping = TextUtils.reconstruct_text_and_mapping([])

        self.assertEqual(full_text, "")

        self.assertEqual(mapping, [])

    # skip words with empty text
    def test_reconstruct_text_and_mapping_with_empty_words(self):
        words = [
            {"text": "Hello", "x0": 10, "y0": 20, "x1": 50, "y1": 30},
            {"text": "", "x0": 60, "y0": 20, "x1": 100, "y1": 30},
            {"text": "world", "x0": 110, "y0": 20, "x1": 150, "y1": 30},
        ]

        full_text, mapping = TextUtils.reconstruct_text_and_mapping(words)

        self.assertEqual(full_text, "Hello world")

        self.assertEqual(len(mapping), 2)

        self.assertEqual(mapping[0][0], words[0])

        self.assertEqual(mapping[1][0], words[2])

    # trim whitespace around words
    def test_reconstruct_text_and_mapping_with_whitespace(self):
        words = [
            {"text": "  Hello  ", "x0": 10, "y0": 20, "x1": 50, "y1": 30},
            {"text": "  world  ", "x0": 60, "y0": 20, "x1": 100, "y1": 30},
        ]

        full_text, mapping = TextUtils.reconstruct_text_and_mapping(words)

        self.assertEqual(full_text, "Hello world")

        self.assertEqual(len(mapping), 2)

        self.assertEqual(mapping[0][1], 0)

        self.assertEqual(mapping[0][2], 5)

        self.assertEqual(mapping[1][1], 6)

        self.assertEqual(mapping[1][2], 11)

    # handle multiple words correctly
    def test_reconstruct_text_and_mapping_with_multiple_words(self):
        words = [
            {"text": "This", "x0": 10, "y0": 20, "x1": 40, "y1": 30},
            {"text": "is", "x0": 50, "y0": 20, "x1": 60, "y1": 30},
            {"text": "a", "x0": 70, "y0": 20, "x1": 80, "y1": 30},
            {"text": "test", "x0": 90, "y0": 20, "x1": 120, "y1": 30},
            {"text": "with", "x0": 130, "y0": 20, "x1": 160, "y1": 30},
            {"text": "multiple", "x0": 170, "y0": 20, "x1": 220, "y1": 30},
            {"text": "words", "x0": 230, "y0": 20, "x1": 270, "y1": 30},
        ]

        full_text, mapping = TextUtils.reconstruct_text_and_mapping(words)

        self.assertEqual(full_text, "This is a test with multiple words")

        self.assertEqual(len(mapping), 7)

        self.assertEqual(mapping[6][0], words[6])

        self.assertEqual(mapping[6][1], 29)

        self.assertEqual(mapping[6][2], 34)


# Tests for TextUtils.map_offsets_to_bboxes
class TestTextUtilsMapOffsetsToBboxes(unittest.TestCase):
    """Test cases for map_offsets_to_bboxes method."""

    def setUp(self):
        self.full_text = "This is a test sentence with some sensitive information."

        self.mapping = [
            ({"text": "This", "x0": 10, "y0": 20, "x1": 40, "y1": 30}, 0, 4),
            ({"text": "is", "x0": 50, "y0": 20, "x1": 60, "y1": 30}, 5, 7),
            ({"text": "a", "x0": 70, "y0": 20, "x1": 80, "y1": 30}, 8, 9),
            ({"text": "test", "x0": 90, "y0": 20, "x1": 120, "y1": 30}, 10, 14),
            ({"text": "sentence", "x0": 130, "y0": 20, "x1": 180, "y1": 30}, 15, 23),
            ({"text": "with", "x0": 190, "y0": 20, "x1": 220, "y1": 30}, 24, 28),
            ({"text": "some", "x0": 230, "y0": 20, "x1": 260, "y1": 30}, 29, 33),
            ({"text": "sensitive", "x0": 10, "y0": 40, "x1": 60, "y1": 50}, 34, 43),
            ({"text": "information", "x0": 70, "y0": 40, "x1": 140, "y1": 50}, 44, 55),
            ({"text": ".", "x0": 150, "y0": 40, "x1": 155, "y1": 50}, 55, 56),
        ]

    # single-line bounding box mapping
    @patch("backend.app.utils.helpers.text_utils.log_warning")
    def test_map_offsets_to_bboxes_basic(self, mock_log_warning):
        sensitive_offsets = (10, 23)

        bboxes = TextUtils.map_offsets_to_bboxes(
            self.full_text, self.mapping, sensitive_offsets
        )

        self.assertEqual(len(bboxes), 1)

        bbox = bboxes[0]

        self.assertEqual(bbox["x0"], 90)

        self.assertEqual(bbox["y0"], 22)

        self.assertEqual(bbox["x1"], 180)

        self.assertEqual(bbox["y1"], 28)

        mock_log_warning.assert_not_called()

    # entity spanning multiple lines
    @patch("backend.app.utils.helpers.text_utils.log_warning")
    def test_map_offsets_to_bboxes_multiple_lines(self, mock_log_warning):
        sensitive_offsets = (29, 55)

        bboxes = TextUtils.map_offsets_to_bboxes(
            self.full_text, self.mapping, sensitive_offsets
        )

        self.assertEqual(len(bboxes), 2)

        bbox1 = bboxes[0]

        self.assertEqual(bbox1["x0"], 230)

        self.assertEqual(bbox1["y0"], 22)

        self.assertEqual(bbox1["x1"], 260)

        self.assertEqual(bbox1["y1"], 28)

        bbox2 = bboxes[1]

        self.assertEqual(bbox2["x0"], 10)

        self.assertEqual(bbox2["y0"], 42)

        self.assertEqual(bbox2["x1"], 155)

        self.assertEqual(bbox2["y1"], 48)

        mock_log_warning.assert_not_called()

    # custom padding on bounding boxes
    @patch("backend.app.utils.helpers.text_utils.log_warning")
    def test_map_offsets_to_bboxes_custom_padding(self, mock_log_warning):
        sensitive_offsets = (10, 14)

        custom_padding = {"top": 5, "right": 10, "bottom": 5, "left": 10}

        bboxes = TextUtils.map_offsets_to_bboxes(
            self.full_text, self.mapping, sensitive_offsets, padding=custom_padding
        )

        self.assertEqual(len(bboxes), 1)

        bbox = bboxes[0]

        self.assertEqual(bbox["x0"], 80)

        self.assertEqual(bbox["y0"], 25)

        self.assertEqual(bbox["x1"], 130)

        self.assertEqual(bbox["y1"], 25)

        mock_log_warning.assert_not_called()

    # offsets with no matching words
    @patch("backend.app.utils.helpers.text_utils.log_warning")
    def test_map_offsets_to_bboxes_no_match(self, mock_log_warning):
        sensitive_offsets = (100, 110)

        bboxes = TextUtils.map_offsets_to_bboxes(
            self.full_text, self.mapping, sensitive_offsets
        )

        self.assertEqual(bboxes, [])

        mock_log_warning.assert_called_once()

        self.assertIn("No valid bounding box found", mock_log_warning.call_args[0][0])

    # bounding box height capped to maximum
    @patch("backend.app.utils.helpers.text_utils.log_warning")
    def test_map_offsets_to_bboxes_height_limit(self, mock_log_warning):
        tall_mapping = [
            ({"text": "tall", "x0": 10, "y0": 20, "x1": 40, "y1": 100}, 0, 4)
        ]

        sensitive_offsets = (0, 4)

        bboxes = TextUtils.map_offsets_to_bboxes(
            "tall", tall_mapping, sensitive_offsets
        )

        self.assertEqual(len(bboxes), 1)

        bbox = bboxes[0]

        self.assertEqual(bbox["y0"], 22)

        self.assertEqual(bbox["y1"], 62)

        mock_log_warning.assert_not_called()


# New Tests for _cap_height, _merge_group, and merge_bounding_boxes
class TestTextUtilsMergeMethods(unittest.TestCase):
    """Test cases for internal merge and cap methods."""

    # _cap_height should leave box unchanged if within limit
    def test_cap_height_no_change(self):
        box = {"x0": 0, "y0": 10, "x1": 50, "y1": 25}

        capped = TextUtils._cap_height(box.copy(), max_height=20)

        self.assertEqual(capped, box)

    # _cap_height should reduce height when exceeding limit
    def test_cap_height_capped(self):
        box = {"x0": 0, "y0": 10, "x1": 50, "y1": 50}

        expected = {"x0": 0, "y0": 10, "x1": 50, "y1": 35}

        capped = TextUtils._cap_height(box.copy(), max_height=25)

        self.assertEqual(capped, expected)

    # _merge_group should combine boxes and cap height
    def test_merge_group(self):
        boxes = [
            {"x0": 0, "y0": 10, "x1": 30, "y1": 30},
            {"x0": 5, "y0": 12, "x1": 35, "y1": 40},
        ]

        expected = {"x0": 0, "y0": 10, "x1": 35, "y1": 35}

        merged = TextUtils._merge_group(boxes, max_height=25)

        self.assertEqual(merged, expected)

    # merge_bounding_boxes should error on empty input
    def test_merge_bounding_boxes_empty_list(self):
        with self.assertRaises(ValueError):
            TextUtils.merge_bounding_boxes([])

    # merge_bounding_boxes should return single box unchanged
    def test_merge_bounding_boxes_single_box(self):
        box = {"x0": 10, "y0": 20, "x1": 40, "y1": 30}

        result = TextUtils.merge_bounding_boxes([box])

        self.assertEqual(result, {"composite": box, "lines": [box]})

    # merge_bounding_boxes should group lines and composite correctly
    def test_merge_bounding_boxes_multiple_boxes(self):
        boxes = [
            {"x0": 0, "y0": 10, "x1": 30, "y1": 30},
            {"x0": 35, "y0": 12, "x1": 50, "y1": 30},
            {"x0": 5, "y0": 50, "x1": 40, "y1": 70},
        ]

        expected_composite = {"x0": 0, "y0": 10, "x1": 50, "y1": 30}

        expected_lines = [
            {"x0": 0, "y0": 10, "x1": 50, "y1": 30},
            {"x0": 5, "y0": 50, "x1": 40, "y1": 70},
        ]

        result = TextUtils.merge_bounding_boxes(boxes)

        self.assertEqual(result["composite"], expected_composite)

        self.assertEqual(result["lines"], expected_lines)


# Tests for TextUtils.recompute_offsets
class TestTextUtilsRecomputeOffsets(unittest.TestCase):
    """Test cases for recompute_offsets method."""

    # basic offset recomputation
    @patch("backend.app.utils.helpers.text_utils.log_warning")
    def test_recompute_offsets_basic(self, mock_log_warning):
        full_text = "This is a test sentence with a test word."

        entity_text = "test"

        offsets = TextUtils.recompute_offsets(full_text, entity_text)

        self.assertEqual(len(offsets), 2)

        self.assertEqual(offsets[0], (10, 14))

        self.assertEqual(offsets[1], (31, 35))

        mock_log_warning.assert_not_called()

    # no matches should log warning
    @patch("backend.app.utils.helpers.text_utils.log_warning")
    def test_recompute_offsets_no_match(self, mock_log_warning):
        full_text = "This is a sample sentence."

        entity_text = "test"

        offsets = TextUtils.recompute_offsets(full_text, entity_text)

        self.assertEqual(offsets, [])

        mock_log_warning.assert_called_once()

        self.assertIn("No match found", mock_log_warning.call_args[0][0])

    # trim whitespace when searching
    @patch("backend.app.utils.helpers.text_utils.log_warning")
    def test_recompute_offsets_with_whitespace(self, mock_log_warning):
        full_text = "This is a test sentence."

        entity_text = "  test  "

        offsets = TextUtils.recompute_offsets(full_text, entity_text)

        self.assertEqual(len(offsets), 1)

        self.assertEqual(offsets[0], (10, 14))

        mock_log_warning.assert_not_called()

    # overlapping occurrences should all be returned
    @patch("backend.app.utils.helpers.text_utils.log_warning")
    def test_recompute_offsets_with_overlapping_matches(self, mock_log_warning):
        full_text = "abababa"

        entity_text = "aba"

        offsets = TextUtils.recompute_offsets(full_text, entity_text)

        self.assertEqual(len(offsets), 3)

        self.assertEqual(offsets[0], (0, 3))

        self.assertEqual(offsets[1], (2, 5))

        self.assertEqual(offsets[2], (4, 7))

        mock_log_warning.assert_not_called()

    # empty entity_text matches every position
    @patch("backend.app.utils.helpers.text_utils.log_warning")
    def test_recompute_offsets_with_empty_entity(self, mock_log_warning):
        full_text = "This is a test sentence."

        entity_text = ""

        offsets = TextUtils.recompute_offsets(full_text, entity_text)

        expected = [(i, i) for i in range(len(full_text))]

        self.assertEqual(offsets, expected)

        mock_log_warning.assert_not_called()


# Tests for EntityUtils.merge_overlapping_entities
class TestEntityUtilsMergeOverlappingEntities(unittest.TestCase):
    """Test cases for merge_overlapping_entities method."""

    # empty list returns empty
    def test_merge_overlapping_entities_empty(self):
        result = EntityUtils.merge_overlapping_entities([])

        self.assertEqual(result, [])

    # non overlapping entities unchanged
    def test_merge_overlapping_entities_non_overlapping(self):
        e1 = MockRecognizerResult(0, 5, 0.8, "PERSON")

        e2 = MockRecognizerResult(6, 10, 0.9, "PERSON")

        result = EntityUtils.merge_overlapping_entities([e1, e2])

        self.assertEqual(result, [e1, e2])

    # overlapping entities are merged by span and score
    def test_merge_overlapping_entities_overlapping(self):
        e1 = MockRecognizerResult(0, 5, 0.8, "PERSON")

        e2 = MockRecognizerResult(3, 8, 0.9, "PERSON")

        e3 = MockRecognizerResult(10, 15, 0.7, "PERSON")

        result = EntityUtils.merge_overlapping_entities([e1, e2, e3])

        self.assertEqual(len(result), 2)

        merged = result[0]

        self.assertEqual(merged.start, 0)

        self.assertEqual(merged.end, 8)

        self.assertEqual(merged.score, 0.9)

        self.assertEqual(result[1], e3)
