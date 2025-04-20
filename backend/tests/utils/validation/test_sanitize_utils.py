import unittest

from unittest.mock import patch

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


# Tests for sanitize_utils module
class TestSanitizeUtils(unittest.TestCase):

    # Setup sample data for sanitize_utils tests
    def setUp(self):
        self.sample_entities = [

            {"entity_type": "PERSON", "start": 0, "end": 10, "score": 0.9, "text": "John Doe"},

            {"entity_type": "PERSON", "start": 0, "end": 10, "score": 0.8, "text": "John Doe"},

            {"entity_type": "EMAIL", "start": 20, "end": 40, "score": 0.95, "text": "john@example.com"},

            {"entity_type": "PHONE", "start": 50, "end": 60, "score": 0.85, "text": "123-456-7890"}

        ]

        self.sample_redaction_mapping = {

            "pages": [

                {

                    "page": 1,

                    "sensitive": [

                        {"entity_type": "PERSON", "start": 0, "end": 10, "score": 0.9, "original_text": "John Doe"},

                        {"entity_type": "PERSON", "start": 0, "end": 10, "score": 0.8, "original_text": "John Doe"},

                        {"entity_type": "EMAIL", "start": 20, "end": 40, "score": 0.95,
                         "original_text": "john@example.com"}

                    ]

                },

                {

                    "page": 2,

                    "sensitive": [

                        {"entity_type": "PHONE", "start": 50, "end": 60, "score": 0.85,
                         "original_text": "123-456-7890"},

                        {"entity_type": "PHONE", "start": 50, "end": 60, "score": 0.95, "original_text": "123-456-7890"}

                    ]

                }

            ]

        }

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

                            "bbox": {"x0": 10.1, "y0": 20.2, "x1": 30.3, "y1": 40.4}

                        }

                    ]

                }

            ]

        }

        self.sample_search_results = [

            {"text": "John Doe", "bbox": {"x0": 10.1, "y0": 20.2, "x1": 30.3, "y1": 40.4}},

            {"text": "John Doe", "bbox": {"x0": 10.1, "y0": 20.2, "x1": 30.3, "y1": 40.4}},

            {"text": "Jane Smith", "bbox": {"x0": 50.5, "y0": 60.6, "x1": 70.7, "y1": 80.8}}

        ]

    # Test sanitize_detection_output with valid inputs
    @patch('backend.app.utils.validation.sanitize_utils.log_info')
    @patch('time.time')
    def test_sanitize_detection_output_positive(self, mock_time, mock_log_info):
        mock_time.side_effect = [100.0, 100.5]

        result = sanitize_detection_output(

            self.sample_entities,

            self.sample_redaction_mapping,

            {"detection_time": 1.5}

        )

        self.assertIn("redaction_mapping", result)

        self.assertIn("entities_detected", result)

        self.assertIn("performance", result)

        self.assertEqual(result["entities_detected"]["total"], 3)

        self.assertEqual(result["performance"]["detection_time"], 1.5)

        self.assertEqual(result["performance"]["sanitize_time"], 0.5)

        mock_log_info.assert_called_once()

    # Test sanitize_detection_output without processing_times
    @patch('backend.app.utils.validation.sanitize_utils.log_info')
    @patch('time.time')
    def test_sanitize_detection_output_without_processing_times(self, mock_time, mock_log_info):
        mock_time.side_effect = [100.0, 100.5]

        result = sanitize_detection_output(

            self.sample_entities,

            self.sample_redaction_mapping

        )

        self.assertIn("performance", result)

        self.assertEqual(len(result["performance"]), 1)

        self.assertEqual(result["performance"]["sanitize_time"], 0.5)

    # Test sanitize_detection_output with empty inputs
    def test_sanitize_detection_output_empty_inputs(self):
        result = sanitize_detection_output([], {"pages": []})

        self.assertIn("redaction_mapping", result)

        self.assertIn("entities_detected", result)

        self.assertEqual(result["entities_detected"]["total"], 0)

        self.assertEqual(result["entities_detected"]["by_type"], {})

        self.assertEqual(result["entities_detected"]["by_page"], {})

    # Test deduplicate_entities removes duplicates and keeps highest score
    def test_deduplicate_entities_positive(self):
        result = deduplicate_entities(self.sample_entities)

        self.assertEqual(len(result), 3)

        person_entity = next(e for e in result if e["entity_type"] == "PERSON")

        self.assertEqual(person_entity["score"], 0.9)

    # Test deduplicate_entities with empty list
    def test_deduplicate_entities_empty_list(self):
        result = deduplicate_entities([])

        self.assertEqual(result, [])

    # Test deduplicate_entities handles missing fields
    def test_deduplicate_entities_missing_fields(self):
        entities = [

            {"entity_type": "PERSON"},

            {"start": 0, "end": 10},

            {}

        ]

        result = deduplicate_entities(entities)

        self.assertEqual(len(result), 3)

    # Test deduplicate_redaction_mapping removes duplicates per page
    def test_deduplicate_redaction_mapping_positive(self):
        result = deduplicate_redaction_mapping(self.sample_redaction_mapping)

        self.assertIn("pages", result)

        self.assertEqual(len(result["pages"]), 2)

        self.assertEqual(len(result["pages"][0]["sensitive"]), 2)

        self.assertEqual(len(result["pages"][1]["sensitive"]), 1)

        phone_item = result["pages"][1]["sensitive"][0]

        self.assertEqual(phone_item["score"], 0.95)

    # Test deduplicate_redaction_mapping with bounding boxes
    def test_deduplicate_redaction_mapping_with_bbox(self):
        result = deduplicate_redaction_mapping(self.sample_redaction_mapping_with_bbox)

        self.assertEqual(len(result["pages"][0]["sensitive"]), 1)

        person_item = result["pages"][0]["sensitive"][0]

        self.assertEqual(person_item["score"], 0.9)

    # Test deduplicate_redaction_mapping with empty input
    def test_deduplicate_redaction_mapping_empty_input(self):
        result = deduplicate_redaction_mapping({"pages": []})

        self.assertEqual(result, {"pages": []})

    # Test deduplicate_bbox removes duplicate boxes
    def test_deduplicate_bbox_positive(self):
        result = deduplicate_bbox(self.sample_search_results)

        self.assertEqual(len(result), 2)

    # Test deduplicate_bbox with different precision
    def test_deduplicate_bbox_different_precision(self):
        search_results = [

            {"text": "John Doe", "bbox": {"x0": 10.11, "y0": 20.22, "x1": 30.33, "y1": 40.44}},

            {"text": "John Doe", "bbox": {"x0": 10.11, "y0": 20.22, "x1": 30.33, "y1": 40.44}}

        ]

        result_p1 = deduplicate_bbox(search_results, precision=1)

        self.assertEqual(len(result_p1), 1)

        result_p2 = deduplicate_bbox(search_results, precision=2)

        self.assertEqual(len(result_p2), 1)

    # Test deduplicate_bbox ignores items missing bbox
    def test_deduplicate_bbox_missing_bbox(self):
        search_results = [

            {"text": "John Doe"},

            {"text": "Jane Smith", "bbox": {"x0": 50.5, "y0": 60.6, "x1": 70.7, "y1": 80.8}}

        ]

        result = deduplicate_bbox(search_results)

        self.assertEqual(len(result), 1)

    # Test organize_entities_by_type counts correctly
    def test_organize_entities_by_type_positive(self):
        result = organize_entities_by_type(self.sample_entities)

        self.assertEqual(result["PERSON"], 2)

        self.assertEqual(result["EMAIL"], 1)

        self.assertEqual(result["PHONE"], 1)

    # Test organize_entities_by_type with empty list
    def test_organize_entities_by_type_empty_list(self):
        result = organize_entities_by_type([])

        self.assertEqual(result, {})

    # Test organize_entities_by_type handles missing entity_type
    def test_organize_entities_by_type_missing_entity_type(self):
        entities = [

            {"start": 0, "end": 10},

            {}

        ]

        result = organize_entities_by_type(entities)

        self.assertEqual(result["UNKNOWN"], 2)

    # Test count_entities_per_page counts properly
    def test_count_entities_per_page_positive(self):
        result = count_entities_per_page(self.sample_redaction_mapping)

        self.assertEqual(result["page_1"], 3)

        self.assertEqual(result["page_2"], 2)

    # Test count_entities_per_page with empty input
    def test_count_entities_per_page_empty_input(self):
        result = count_entities_per_page({"pages": []})

        self.assertEqual(result, {})

    # Test replace_key_in_dict replaces and preserves original
    def test_replace_key_in_dict_positive(self):
        d = {"a": 1, "b": 2, "c": 3}

        result = replace_key_in_dict(d, "b", "new_b", 22)

        self.assertEqual(result, {"a": 1, "new_b": 22, "c": 3})

        self.assertEqual(d, {"a": 1, "b": 2, "c": 3})

    # Test replace_key_in_dict no-op when key absent
    def test_replace_key_in_dict_key_not_found(self):
        d = {"a": 1, "b": 2, "c": 3}

        result = replace_key_in_dict(d, "d", "new_d", 44)

        self.assertEqual(result, {"a": 1, "b": 2, "c": 3})

    # Test process_item replaces original_text with engine
    def test_process_item_with_original_text(self):
        item = {"entity_type": "PERSON", "start": 0, "end": 10, "original_text": "John Doe"}

        result = process_item(item, "ENGINE_X")

        self.assertNotIn("original_text", result)

        self.assertEqual(result["engine"], "ENGINE_X")

        self.assertEqual(result["entity_type"], "PERSON")

        self.assertEqual(result["start"], 0)

        self.assertEqual(result["end"], 10)

    # Test process_item adds engine when no original_text
    def test_process_item_without_original_text(self):
        item = {"entity_type": "PERSON", "start": 0, "end": 10}

        result = process_item(item, "ENGINE_X")

        self.assertEqual(result["engine"], "ENGINE_X")

        self.assertEqual(result["entity_type"], "PERSON")

        self.assertEqual(result["start"], 0)

        self.assertEqual(result["end"], 10)

    # Test process_items_list processes all items
    def test_process_items_list_positive(self):
        items = [

            {"entity_type": "PERSON", "original_text": "John Doe"},

            {"entity_type": "EMAIL", "text": "john@example.com"}

        ]

        result = process_items_list(items, "ENGINE_X")

        self.assertEqual(len(result), 2)

        self.assertEqual(result[0]["engine"], "ENGINE_X")

        self.assertNotIn("original_text", result[0])

        self.assertEqual(result[1]["engine"], "ENGINE_X")

        self.assertEqual(result[1]["text"], "john@example.com")

    # Test process_items_list with empty list
    def test_process_items_list_empty_list(self):
        result = process_items_list([], "ENGINE_X")

        self.assertEqual(result, [])
