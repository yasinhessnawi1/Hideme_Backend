"""
Unit tests for text_utils.py module.

This test file covers the TextUtils and EntityUtils classes and their methods
with both positive and negative test cases to ensure proper functionality
and error handling.
"""

import unittest
from unittest.mock import patch

# Import the module to be tested
from backend.app.utils.helpers.text_utils import (
    TextUtils,
    EntityUtils
)


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

    def test_reconstruct_text_and_mapping_basic(self):
        """Test reconstruct_text_and_mapping with basic input."""
        words = [
            {"text": "Hello", "x0": 10, "y0": 20, "x1": 50, "y1": 30},
            {"text": "world", "x0": 60, "y0": 20, "x1": 100, "y1": 30},
            {"text": "!", "x0": 110, "y0": 20, "x1": 120, "y1": 30}
        ]
        full_text, mapping = TextUtils.reconstruct_text_and_mapping(words)
        self.assertEqual(full_text, "Hello world !")
        self.assertEqual(len(mapping), 3)
        # First word
        self.assertEqual(mapping[0][0], words[0])
        self.assertEqual(mapping[0][1], 0)
        self.assertEqual(mapping[0][2], 5)
        # Second word
        self.assertEqual(mapping[1][0], words[1])
        self.assertEqual(mapping[1][1], 6)
        self.assertEqual(mapping[1][2], 11)
        # Third word
        self.assertEqual(mapping[2][0], words[2])
        self.assertEqual(mapping[2][1], 12)
        self.assertEqual(mapping[2][2], 13)

    def test_reconstruct_text_and_mapping_empty_list(self):
        """Test reconstruct_text_and_mapping with an empty list."""
        full_text, mapping = TextUtils.reconstruct_text_and_mapping([])
        self.assertEqual(full_text, "")
        self.assertEqual(mapping, [])

    def test_reconstruct_text_and_mapping_with_empty_words(self):
        """Test reconstruct_text_and_mapping with words containing empty text."""
        words = [
            {"text": "Hello", "x0": 10, "y0": 20, "x1": 50, "y1": 30},
            {"text": "", "x0": 60, "y0": 20, "x1": 100, "y1": 30},
            {"text": "world", "x0": 110, "y0": 20, "x1": 150, "y1": 30}
        ]
        full_text, mapping = TextUtils.reconstruct_text_and_mapping(words)
        self.assertEqual(full_text, "Hello world")
        self.assertEqual(len(mapping), 2)
        self.assertEqual(mapping[0][0], words[0])
        self.assertEqual(mapping[1][0], words[2])

    def test_reconstruct_text_and_mapping_with_whitespace(self):
        """Test reconstruct_text_and_mapping with words containing whitespace."""
        words = [
            {"text": "  Hello  ", "x0": 10, "y0": 20, "x1": 50, "y1": 30},
            {"text": "  world  ", "x0": 60, "y0": 20, "x1": 100, "y1": 30}
        ]
        full_text, mapping = TextUtils.reconstruct_text_and_mapping(words)
        self.assertEqual(full_text, "Hello world")
        self.assertEqual(len(mapping), 2)
        self.assertEqual(mapping[0][1], 0)
        self.assertEqual(mapping[0][2], 5)
        self.assertEqual(mapping[1][1], 6)
        self.assertEqual(mapping[1][2], 11)

    def test_reconstruct_text_and_mapping_with_multiple_words(self):
        """Test reconstruct_text_and_mapping with a larger number of words."""
        words = [
            {"text": "This", "x0": 10, "y0": 20, "x1": 40, "y1": 30},  # len=4, offsets: 0-4
            {"text": "is", "x0": 50, "y0": 20, "x1": 60, "y1": 30},  # len=2, offsets: 5-7
            {"text": "a", "x0": 70, "y0": 20, "x1": 80, "y1": 30},  # len=1, offsets: 8-9
            {"text": "test", "x0": 90, "y0": 20, "x1": 120, "y1": 30},  # len=4, offsets: 10-14
            {"text": "with", "x0": 130, "y0": 20, "x1": 160, "y1": 30},  # len=4, offsets: 15-19
            {"text": "multiple", "x0": 170, "y0": 20, "x1": 220, "y1": 30},  # len=8, offsets: 20-28
            {"text": "words", "x0": 230, "y0": 20, "x1": 270, "y1": 30}  # len=5, offsets: 29-34
        ]
        full_text, mapping = TextUtils.reconstruct_text_and_mapping(words)
        self.assertEqual(full_text, "This is a test with multiple words")
        self.assertEqual(len(mapping), 7)
        # Verify last word mapping: expected start offset = 29 and end offset = 34.
        self.assertEqual(mapping[6][0], words[6])
        self.assertEqual(mapping[6][1], 29)  # Updated expected start offset.
        self.assertEqual(mapping[6][2], 34)  # Updated expected end offset.



# Tests for TextUtils.map_offsets_to_bboxes

class TestTextUtilsMapOffsetsToBboxes(unittest.TestCase):

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
            ({"text": ".", "x0": 150, "y0": 40, "x1": 155, "y1": 50}, 55, 56)
        ]

    @patch('backend.app.utils.helpers.text_utils.log_warning')
    def test_map_offsets_to_bboxes_basic(self, mock_log_warning):
        """Test map_offsets_to_bboxes with basic input."""
        sensitive_offsets = (10, 23)
        bboxes = TextUtils.map_offsets_to_bboxes(self.full_text, self.mapping, sensitive_offsets)
        self.assertEqual(len(bboxes), 1)
        bbox = bboxes[0]
        self.assertEqual(bbox["x0"], 90)  # x0 of "test"
        self.assertEqual(bbox["y0"], 22)  # 20+2
        self.assertEqual(bbox["x1"], 180)  # x1 of "sentence"
        self.assertEqual(bbox["y1"], 28)  # 30-2
        mock_log_warning.assert_not_called()

    @patch('backend.app.utils.helpers.text_utils.log_warning')
    def test_map_offsets_to_bboxes_multiple_lines(self, mock_log_warning):
        """Test map_offsets_to_bboxes with entity spanning multiple lines."""
        sensitive_offsets = (29, 55)  # Should include "some" (line1) and "sensitive", "information", "." (line2)
        bboxes = TextUtils.map_offsets_to_bboxes(self.full_text, self.mapping, sensitive_offsets)
        self.assertEqual(len(bboxes), 2)
        # First line: from "some"
        bbox1 = bboxes[0]
        self.assertEqual(bbox1["x0"], 230)
        self.assertEqual(bbox1["y0"], 22)
        self.assertEqual(bbox1["x1"], 260)
        self.assertEqual(bbox1["y1"], 28)
        # Second line: from "sensitive", "information", and "."
        bbox2 = bboxes[1]
        self.assertEqual(bbox2["x0"], 10)
        self.assertEqual(bbox2["y0"], 42)
        # x1 should be max of 60, 140, and 155 => 155
        self.assertEqual(bbox2["x1"], 155)
        self.assertEqual(bbox2["y1"], 48)
        mock_log_warning.assert_not_called()

    @patch('backend.app.utils.helpers.text_utils.log_warning')
    def test_map_offsets_to_bboxes_custom_padding(self, mock_log_warning):
        """Test map_offsets_to_bboxes with custom padding."""
        sensitive_offsets = (10, 14)
        custom_padding = {"top": 5, "right": 10, "bottom": 5, "left": 10}
        bboxes = TextUtils.map_offsets_to_bboxes(self.full_text, self.mapping, sensitive_offsets,
                                                 padding=custom_padding)
        self.assertEqual(len(bboxes), 1)
        bbox = bboxes[0]
        # For word "test": original x0=90, y0=20, x1=120, y1=30
        # Custom padding: x0 becomes 90-10=80, y0 becomes 20+5=25, x1 becomes 120+10=130, y1 becomes 30-5=25.
        self.assertEqual(bbox["x0"], 80)
        self.assertEqual(bbox["y0"], 25)
        self.assertEqual(bbox["x1"], 130)
        self.assertEqual(bbox["y1"], 25)
        mock_log_warning.assert_not_called()

    @patch('backend.app.utils.helpers.text_utils.log_warning')
    def test_map_offsets_to_bboxes_no_match(self, mock_log_warning):
        """Test map_offsets_to_bboxes with offsets that don't match any words."""
        sensitive_offsets = (100, 110)
        bboxes = TextUtils.map_offsets_to_bboxes(self.full_text, self.mapping, sensitive_offsets)
        self.assertEqual(bboxes, [])
        mock_log_warning.assert_called_once()
        self.assertIn("No valid bounding box found", mock_log_warning.call_args[0][0])

    @patch('backend.app.utils.helpers.text_utils.log_warning')
    def test_map_offsets_to_bboxes_height_limit(self, mock_log_warning):
        """Test map_offsets_to_bboxes with a very tall bounding box that gets limited."""
        tall_mapping = [
            ({"text": "tall", "x0": 10, "y0": 20, "x1": 40, "y1": 100}, 0, 4)
        ]
        sensitive_offsets = (0, 4)
        bboxes = TextUtils.map_offsets_to_bboxes("tall", tall_mapping, sensitive_offsets)
        self.assertEqual(len(bboxes), 1)
        bbox = bboxes[0]
        self.assertEqual(bbox["y0"], 22)  # 20+2
        # Expected height: max height=40, so y1 should be y0+40 = 22+40 = 62
        self.assertEqual(bbox["y1"], 62)
        mock_log_warning.assert_not_called()


# New Tests for _cap_height, _merge_group, and merge_bounding_boxes

class TestTextUtilsMergeMethods(unittest.TestCase):

    def test_cap_height_no_change(self):
        """Test _cap_height returns the box unchanged if height is within limit."""
        # Box with height exactly 15 (within a max_height of 20)
        box = {"x0": 0, "y0": 10, "x1": 50, "y1": 25}  # Height = 15
        capped = TextUtils._cap_height(box.copy(), max_height=20)
        self.assertEqual(capped, box)  # Should remain unchanged

    def test_cap_height_capped(self):
        """Test _cap_height limits the height when it exceeds max_height."""
        # Box with height 40 (from y0=10 to y1=50) and max_height=25:
        box = {"x0": 0, "y0": 10, "x1": 50, "y1": 50}  # Height = 40
        # Expect y1 to be capped: new y1 = y0 + 25 = 35.
        expected = {"x0": 0, "y0": 10, "x1": 50, "y1": 35}
        capped = TextUtils._cap_height(box.copy(), max_height=25)
        self.assertEqual(capped, expected)

    def test_merge_group(self):
        """Test _merge_group merges a group of boxes and caps the height."""
        # Two boxes:
        boxes = [
            {"x0": 0, "y0": 10, "x1": 30, "y1": 30},
            {"x0": 5, "y0": 12, "x1": 35, "y1": 40}
        ]
        # Merged without cap would be:
        #   x0 = min(0,5)=0, y0 = min(10,12)=10,
        #   x1 = max(30,35)=35, y1 = max(30,40)=40.
        # With max_height=25, height exceeds (40-10=30 > 25) so y1 becomes 10 + 25 = 35.
        expected = {"x0": 0, "y0": 10, "x1": 35, "y1": 35}
        merged = TextUtils._merge_group(boxes, max_height=25)
        self.assertEqual(merged, expected)

    def test_merge_bounding_boxes_empty_list(self):
        """Test merge_bounding_boxes raises ValueError when input list is empty."""
        with self.assertRaises(ValueError):
            TextUtils.merge_bounding_boxes([])

    def test_merge_bounding_boxes_single_box(self):
        """Test merge_bounding_boxes returns the same box for single input."""
        box = {"x0": 10, "y0": 20, "x1": 40, "y1": 30}
        result = TextUtils.merge_bounding_boxes([box])
        self.assertEqual(result, {"composite": box, "lines": [box]})

    def test_merge_bounding_boxes_multiple_boxes(self):
        """Test merge_bounding_boxes merges boxes per line and composite correctly."""
        # Define three boxes:
        # Two boxes on the same line and one on a separate line.
        boxes = [
            {"x0": 0, "y0": 10, "x1": 30, "y1": 30},    # Box 1: line 1
            {"x0": 35, "y0": 12, "x1": 50, "y1": 30},    # Box 2: line 1
            {"x0": 5, "y0": 50, "x1": 40, "y1": 70}       # Box 3: line 2
        ]
        # Set line_threshold in implementation as 5.0 and max_height as 20.
        # Line 1 group: Boxes 1 and 2.
        #   Merged line 1: x0 = min(0,35)=0, y0 = min(10,12)=10, x1 = max(30,50)=50, y1 = max(30,30)=30.
        #   Height = 30 - 10 = 20, which is exactly the limit, so remains unchanged.
        # Line 2 group: Box 3 remains {"x0":5, "y0":50, "x1":40, "y1":70} with height 20.
        # Composite: Merge all three boxes:
        #   x0 = min(0,35,5)=0, y0 = min(10,12,50)=10, x1 = max(30,50,40)=50, y1 = max(30,30,70)=70.
        #   Height = 70-10 = 60 > 20 so composite y1 becomes 10+20=30.
        expected_composite = {"x0": 0, "y0": 10, "x1": 50, "y1": 30}
        expected_lines = [
            {"x0": 0, "y0": 10, "x1": 50, "y1": 30},  # Line 1 group
            {"x0": 5, "y0": 50, "x1": 40, "y1": 70}    # Line 2 group (height=20, remains)
        ]
        result = TextUtils.merge_bounding_boxes(boxes)

        self.assertEqual(result["composite"], expected_composite)
        self.assertEqual(result["lines"], expected_lines)

# Tests for TextUtils.recompute_offsets

class TestTextUtilsRecomputeOffsets(unittest.TestCase):
    @patch('backend.app.utils.helpers.text_utils.log_warning')
    def test_recompute_offsets_basic(self, mock_log_warning):
        """Test recompute_offsets with a basic match."""
        full_text = "This is a test sentence with a test word."
        entity_text = "test"
        offsets = TextUtils.recompute_offsets(full_text, entity_text)

        self.assertEqual(len(offsets), 2)
        self.assertEqual(offsets[0], (10, 14))  # "test" at indices 10-14
        self.assertEqual(offsets[1], (31, 35))  # Second occurrence: indices 31-35
        mock_log_warning.assert_not_called()

    @patch('backend.app.utils.helpers.text_utils.log_warning')
    def test_recompute_offsets_no_match(self, mock_log_warning):
        full_text = "This is a sample sentence."
        entity_text = "test"

        offsets = TextUtils.recompute_offsets(full_text, entity_text)
        self.assertEqual(offsets, [])

        mock_log_warning.assert_called_once()
        self.assertIn("No match found", mock_log_warning.call_args[0][0])

    @patch('backend.app.utils.helpers.text_utils.log_warning')
    def test_recompute_offsets_with_whitespace(self, mock_log_warning):
        full_text = "This is a test sentence."
        entity_text = "  test  "
        offsets = TextUtils.recompute_offsets(full_text, entity_text)

        self.assertEqual(len(offsets), 1)
        self.assertEqual(offsets[0], (10, 14))
        mock_log_warning.assert_not_called()

    @patch('backend.app.utils.helpers.text_utils.log_warning')
    def test_recompute_offsets_with_overlapping_matches(self, mock_log_warning):
        full_text = "abababa"  # Overlapping occurrences of "aba"
        entity_text = "aba"
        offsets = TextUtils.recompute_offsets(full_text, entity_text)

        self.assertEqual(len(offsets), 3)
        self.assertEqual(offsets[0], (0, 3))
        self.assertEqual(offsets[1], (2, 5))
        self.assertEqual(offsets[2], (4, 7))
        mock_log_warning.assert_not_called()

    @patch('backend.app.utils.helpers.text_utils.log_warning')
    def test_recompute_offsets_with_empty_entity(self, mock_log_warning):
        full_text = "This is a test sentence."
        entity_text = ""
        offsets = TextUtils.recompute_offsets(full_text, entity_text)

        # Since entity_text is empty, every position in full_text is a match.
        expected = [(i, i) for i in range(len(full_text))]
        self.assertEqual(offsets, expected)

        # Because matches are found, log_warning should not be called.
        mock_log_warning.assert_not_called()


# Tests for EntityUtils.merge_overlapping_entities

class TestEntityUtilsMergeOverlappingEntities(unittest.TestCase):
    def test_merge_overlapping_entities_empty(self):
        """Test merge_overlapping_entities with empty list."""
        result = EntityUtils.merge_overlapping_entities([])
        self.assertEqual(result, [])

    def test_merge_overlapping_entities_non_overlapping(self):
        """Test merge_overlapping_entities with non-overlapping entities."""
        e1 = MockRecognizerResult(0, 5, 0.8, "PERSON")
        e2 = MockRecognizerResult(6, 10, 0.9, "PERSON")
        result = EntityUtils.merge_overlapping_entities([e1, e2])
        self.assertEqual(result, [e1, e2])

    def test_merge_overlapping_entities_overlapping(self):
        """Test merge_overlapping_entities with overlapping entities, keeping longest span and highest score."""
        e1 = MockRecognizerResult(0, 5, 0.8, "PERSON")
        e2 = MockRecognizerResult(3, 8, 0.9, "PERSON")
        e3 = MockRecognizerResult(10, 15, 0.7, "PERSON")
        result = EntityUtils.merge_overlapping_entities([e1, e2, e3])

        # e1 and e2 overlap, so they should be merged into one with start=0, end=8, score=0.9, then e3 remains.
        self.assertEqual(len(result), 2)
        merged = result[0]
        self.assertEqual(merged.start, 0)
        self.assertEqual(merged.end, 8)
        self.assertEqual(merged.score, 0.9)
        self.assertEqual(result[1], e3)
