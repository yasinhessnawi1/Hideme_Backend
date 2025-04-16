"""
Unit tests for sanitize_utils.py module.

This test file covers all functions in the sanitize_utils module with both positive
and negative test cases to ensure proper functionality and error handling.
"""

import unittest
from unittest.mock import patch

# Import the module to be tested
from backend.app.utils.validation.sanitize_utils import (
    sanitize_detection_output,
    deduplicate_entities,
    deduplicate_redaction_mapping,
    deduplicate_bbox,
    organize_entities_by_type,
    count_entities_per_page,
    replace_key_in_dict,
    process_item,
    process_items_list
)


class TestSanitizeUtils(unittest.TestCase):
    """Test cases for sanitize_utils.py module."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        # Sample entities for testing
        self.sample_entities = [
            {"entity_type": "PERSON", "start": 0, "end": 10, "score": 0.9, "text": "John Doe"},
            {"entity_type": "PERSON", "start": 0, "end": 10, "score": 0.8, "text": "John Doe"},  # Duplicate with lower score
            {"entity_type": "EMAIL", "start": 20, "end": 40, "score": 0.95, "text": "john@example.com"},
            {"entity_type": "PHONE", "start": 50, "end": 60, "score": 0.85, "text": "123-456-7890"}
        ]
        
        # Sample redaction mapping for testing
        self.sample_redaction_mapping = {
            "pages": [
                {
                    "page": 1,
                    "sensitive": [
                        {"entity_type": "PERSON", "start": 0, "end": 10, "score": 0.9, "original_text": "John Doe"},
                        {"entity_type": "PERSON", "start": 0, "end": 10, "score": 0.8, "original_text": "John Doe"},  # Duplicate
                        {"entity_type": "EMAIL", "start": 20, "end": 40, "score": 0.95, "original_text": "john@example.com"}
                    ]
                },
                {
                    "page": 2,
                    "sensitive": [
                        {"entity_type": "PHONE", "start": 50, "end": 60, "score": 0.85, "original_text": "123-456-7890"},
                        {"entity_type": "PHONE", "start": 50, "end": 60, "score": 0.95, "original_text": "123-456-7890"}  # Duplicate with higher score
                    ]
                }
            ]
        }
        
        # Sample redaction mapping with bounding boxes
        self.sample_redaction_mapping_with_bbox = {
            "pages": [
                {
                    "page": 1,
                    "sensitive": [
                        {
                            "entity_type": "PERSON", 
                            "start": 0, 
                            "end": 10, 
                            "score": 0.9, 
                            "original_text": "John Doe",
                            "bbox": {"x0": 10.1, "y0": 20.2, "x1": 30.3, "y1": 40.4}
                        },
                        {
                            "entity_type": "PERSON", 
                            "start": 0, 
                            "end": 10, 
                            "score": 0.8, 
                            "original_text": "John Doe",
                            "bbox": {"x0": 10.1, "y0": 20.2, "x1": 30.3, "y1": 40.4}  # Duplicate bbox
                        }
                    ]
                }
            ]
        }
        
        # Sample search results with bounding boxes
        self.sample_search_results = [
            {"text": "John Doe", "bbox": {"x0": 10.1, "y0": 20.2, "x1": 30.3, "y1": 40.4}},
            {"text": "John Doe", "bbox": {"x0": 10.1, "y0": 20.2, "x1": 30.3, "y1": 40.4}},  # Duplicate
            {"text": "Jane Smith", "bbox": {"x0": 50.5, "y0": 60.6, "x1": 70.7, "y1": 80.8}}
        ]

    @patch('backend.app.utils.validation.sanitize_utils.log_info')
    @patch('time.time')
    def test_sanitize_detection_output_positive(self, mock_time, mock_log_info):
        """Test sanitize_detection_output with valid inputs."""
        # Mock time.time() to return predictable values
        mock_time.side_effect = [100.0, 100.5]  # Start time, end time
        
        # Call the function with sample data
        result = sanitize_detection_output(
            self.sample_entities,
            self.sample_redaction_mapping,
            {"detection_time": 1.5}
        )
        
        # Verify the result structure
        self.assertIn("redaction_mapping", result)
        self.assertIn("entities_detected", result)
        self.assertIn("performance", result)
        
        # Verify entity deduplication (should have 3 unique entities)
        self.assertEqual(result["entities_detected"]["total"], 3)
        
        # Verify performance metrics
        self.assertEqual(result["performance"]["detection_time"], 1.5)
        self.assertEqual(result["performance"]["sanitize_time"], 0.5)  # 100.5 - 100.0
        
        # Verify logging was called
        mock_log_info.assert_called_once()

    @patch('backend.app.utils.validation.sanitize_utils.log_info')
    @patch('time.time')
    def test_sanitize_detection_output_without_processing_times(self, mock_time, mock_log_info):
        """Test sanitize_detection_output without processing_times parameter."""
        # Mock time.time() to return predictable values
        mock_time.side_effect = [100.0, 100.5]  # Start time, end time
        
        # Call the function without processing_times
        result = sanitize_detection_output(
            self.sample_entities,
            self.sample_redaction_mapping
        )
        
        # Verify performance metrics only contains sanitize_time
        self.assertIn("performance", result)
        self.assertEqual(len(result["performance"]), 1)
        self.assertEqual(result["performance"]["sanitize_time"], 0.5)

    def test_sanitize_detection_output_empty_inputs(self):
        """Test sanitize_detection_output with empty inputs."""
        # Call the function with empty inputs
        result = sanitize_detection_output([], {"pages": []})
        
        # Verify the result structure
        self.assertIn("redaction_mapping", result)
        self.assertIn("entities_detected", result)
        self.assertEqual(result["entities_detected"]["total"], 0)
        self.assertEqual(result["entities_detected"]["by_type"], {})
        self.assertEqual(result["entities_detected"]["by_page"], {})

    def test_deduplicate_entities_positive(self):
        """Test deduplicate_entities with valid inputs."""
        # Call the function with sample entities
        result = deduplicate_entities(self.sample_entities)
        
        # Should have 3 unique entities (removing one duplicate PERSON)
        self.assertEqual(len(result), 3)
        
        # Verify the entity with higher score is kept
        person_entity = next(e for e in result if e["entity_type"] == "PERSON")
        self.assertEqual(person_entity["score"], 0.9)

    def test_deduplicate_entities_empty_list(self):
        """Test deduplicate_entities with an empty list."""
        result = deduplicate_entities([])
        self.assertEqual(result, [])

    def test_deduplicate_entities_missing_fields(self):
        """Test deduplicate_entities with entities missing fields."""
        entities = [
            {"entity_type": "PERSON"},  # Missing start/end
            {"start": 0, "end": 10},    # Missing entity_type
            {}                          # Empty dict
        ]
        
        result = deduplicate_entities(entities)
        # Should still process these entities with default values
        self.assertEqual(len(result), 3)

    def test_deduplicate_redaction_mapping_positive(self):
        """Test deduplicate_redaction_mapping with valid inputs."""
        # Call the function with sample redaction mapping
        result = deduplicate_redaction_mapping(self.sample_redaction_mapping)
        
        # Verify structure
        self.assertIn("pages", result)
        self.assertEqual(len(result["pages"]), 2)
        
        # Page 1 should have 2 sensitive items (removing one duplicate)
        self.assertEqual(len(result["pages"][0]["sensitive"]), 2)
        
        # Page 2 should have 1 sensitive item (removing one duplicate)
        self.assertEqual(len(result["pages"][1]["sensitive"]), 1)
        
        # Verify the item with higher score is kept for page 2
        phone_item = result["pages"][1]["sensitive"][0]
        self.assertEqual(phone_item["score"], 0.95)

    def test_deduplicate_redaction_mapping_with_bbox(self):
        """Test deduplicate_redaction_mapping with bounding boxes."""
        # Call the function with sample redaction mapping containing bboxes
        result = deduplicate_redaction_mapping(self.sample_redaction_mapping_with_bbox)
        
        # Page 1 should have 1 sensitive item (removing one duplicate based on bbox)
        self.assertEqual(len(result["pages"][0]["sensitive"]), 1)
        
        # Verify the item with higher score is kept
        person_item = result["pages"][0]["sensitive"][0]
        self.assertEqual(person_item["score"], 0.9)

    def test_deduplicate_redaction_mapping_empty_input(self):
        """Test deduplicate_redaction_mapping with empty input."""
        result = deduplicate_redaction_mapping({"pages": []})
        self.assertEqual(result, {"pages": []})

    def test_deduplicate_bbox_positive(self):
        """Test deduplicate_bbox with valid inputs."""
        # Call the function with sample search results
        result = deduplicate_bbox(self.sample_search_results)
        
        # Should have 2 unique results (removing one duplicate)
        self.assertEqual(len(result), 2)

    def test_deduplicate_bbox_different_precision(self):
        """Test deduplicate_bbox with different precision values."""
        # Create search results with slightly different coordinates
        search_results = [
            {"text": "John Doe", "bbox": {"x0": 10.11, "y0": 20.22, "x1": 30.33, "y1": 40.44}},
            {"text": "John Doe", "bbox": {"x0": 10.11, "y0": 20.22, "x1": 30.33, "y1": 40.44}}
        ]

        result_p1 = deduplicate_bbox(search_results, precision=1)
        self.assertEqual(len(result_p1), 1)

        result_p2 = deduplicate_bbox(search_results, precision=2)
        self.assertEqual(len(result_p2), 1)

    def test_deduplicate_bbox_missing_bbox(self):
        """Test deduplicate_bbox with items missing bbox."""
        search_results = [
            {"text": "John Doe"},  # No bbox
            {"text": "Jane Smith", "bbox": {"x0": 50.5, "y0": 60.6, "x1": 70.7, "y1": 80.8}}
        ]
        
        result = deduplicate_bbox(search_results)
        # Should only include the item with bbox
        self.assertEqual(len(result), 1)

    def test_organize_entities_by_type_positive(self):
        """Test organize_entities_by_type with valid inputs."""
        # Call the function with sample entities
        result = organize_entities_by_type(self.sample_entities)
        
        # Verify counts by type
        self.assertEqual(result["PERSON"], 2)  # Two PERSON entities (duplicates not yet removed)
        self.assertEqual(result["EMAIL"], 1)
        self.assertEqual(result["PHONE"], 1)

    def test_organize_entities_by_type_empty_list(self):
        """Test organize_entities_by_type with an empty list."""
        result = organize_entities_by_type([])
        self.assertEqual(result, {})

    def test_organize_entities_by_type_missing_entity_type(self):
        """Test organize_entities_by_type with entities missing entity_type."""
        entities = [
            {"start": 0, "end": 10},  # Missing entity_type
            {}                        # Empty dict
        ]
        
        result = organize_entities_by_type(entities)
        # Should use "UNKNOWN" as default entity_type
        self.assertEqual(result["UNKNOWN"], 2)

    def test_count_entities_per_page_positive(self):
        """Test count_entities_per_page with valid inputs."""
        # Call the function with sample redaction mapping
        result = count_entities_per_page(self.sample_redaction_mapping)
        
        # Verify counts by page
        self.assertEqual(result["page_1"], 3)  # Three sensitive items on page 1
        self.assertEqual(result["page_2"], 2)  # Two sensitive items on page 2

    def test_count_entities_per_page_empty_input(self):
        """Test count_entities_per_page with empty input."""
        result = count_entities_per_page({"pages": []})
        self.assertEqual(result, {})

    def test_replace_key_in_dict_positive(self):
        """Test replace_key_in_dict with valid inputs."""
        # Sample dictionary
        d = {"a": 1, "b": 2, "c": 3}
        
        # Replace key "b" with "new_b"
        result = replace_key_in_dict(d, "b", "new_b", 22)
        
        # Verify result
        self.assertEqual(result, {"a": 1, "new_b": 22, "c": 3})
        
        # Original dict should be unchanged
        self.assertEqual(d, {"a": 1, "b": 2, "c": 3})

    def test_replace_key_in_dict_key_not_found(self):
        """Test replace_key_in_dict when key is not found."""
        d = {"a": 1, "b": 2, "c": 3}
        
        # Try to replace non-existent key "d"
        result = replace_key_in_dict(d, "d", "new_d", 44)
        
        # Result should be same as original
        self.assertEqual(result, {"a": 1, "b": 2, "c": 3})

    def test_process_item_with_original_text(self):
        """Test process_item with item containing original_text."""
        item = {"entity_type": "PERSON", "start": 0, "end": 10, "original_text": "John Doe"}
        
        result = process_item(item, "ENGINE_X")
        
        # Verify original_text is replaced with engine
        self.assertNotIn("original_text", result)
        self.assertEqual(result["engine"], "ENGINE_X")
        
        # Other fields should be preserved
        self.assertEqual(result["entity_type"], "PERSON")
        self.assertEqual(result["start"], 0)
        self.assertEqual(result["end"], 10)

    def test_process_item_without_original_text(self):
        """Test process_item with item not containing original_text."""
        item = {"entity_type": "PERSON", "start": 0, "end": 10}
        
        result = process_item(item, "ENGINE_X")
        
        # engine field should be added
        self.assertEqual(result["engine"], "ENGINE_X")
        
        # Other fields should be preserved
        self.assertEqual(result["entity_type"], "PERSON")
        self.assertEqual(result["start"], 0)
        self.assertEqual(result["end"], 10)

    def test_process_items_list_positive(self):
        """Test process_items_list with valid inputs."""
        items = [
            {"entity_type": "PERSON", "original_text": "John Doe"},
            {"entity_type": "EMAIL", "text": "john@example.com"}
        ]
        
        result = process_items_list(items, "ENGINE_X")
        
        # Verify all items are processed
        self.assertEqual(len(result), 2)
        
        # First item should have original_text replaced with engine
        self.assertEqual(result[0]["engine"], "ENGINE_X")
        self.assertNotIn("original_text", result[0])
        
        # Second item should have engine added
        self.assertEqual(result[1]["engine"], "ENGINE_X")
        self.assertEqual(result[1]["text"], "john@example.com")

    def test_process_items_list_empty_list(self):
        """Test process_items_list with an empty list."""
        result = process_items_list([], "ENGINE_X")
        self.assertEqual(result, [])
