import unittest
from unittest.mock import patch, MagicMock
from backend.app.document_processing.detection_updater import DetectionResultUpdater


class TestDetectionResultUpdater(unittest.IsolatedAsyncioTestCase):

    # Setup dummy extracted data and detection result
    def setUp(self):
        self.extracted_data = {
            "pages": [{"page": 1, "words": [{"text": "test"}, {"text": "example"}]}]
        }

        self.detection_result = (
            [{"original_text": "test example", "start": 0, "end": 11}],
            {"pages": [{"page": 1, "sensitive": [{"entity_type": "TEST", "original_text": "test example"}]}]}
        )

        self.updater = DetectionResultUpdater(self.extracted_data, self.detection_result)

    # Empty entities yield zero total and no pages
    def test_update_result_empty_entities(self):
        self.updater.redaction_mapping = {"pages": []}

        result = self.updater.update_result(["test"])

        self.assertEqual(result["entities_detected"]["total"], 0)

        self.assertEqual(result["redaction_mapping"]["pages"], [])

    # Removing phrase splits out remaining text correctly
    @patch(
        "backend.app.entity_detection.glinerbase.TextUtils.reconstruct_text_and_mapping",
        return_value=("test example", [({}, 0, 4)])
    )
    def test_apply_removals_positive(self, mock_reconstruct):
        entity_text = "test example"

        remove_phrases = ["test"]

        result = self.updater.apply_removals(entity_text, remove_phrases)

        self.assertEqual(result, ["example"])

    # No matching phrase leaves text unchanged
    def test_apply_removals_no_changes(self):
        entity_text = "test example"

        remove_phrases = ["nonexistent"]

        result = self.updater.apply_removals(entity_text, remove_phrases)

        self.assertEqual(result, ["test example"])

    # Retrieve existing page data correctly
    def test_get_original_page_found(self):
        result = self.updater._get_original_page(1)

        self.assertEqual(
            result,
            {"page": 1, "words": [{"text": "test"}, {"text": "example"}]}
        )

    # Missing page returns empty dict
    def test_get_original_page_not_found(self):
        result = self.updater._get_original_page(999)

        self.assertEqual(result, {})

    # Reconstruct full text and mapping when words present
    @patch(
        "backend.app.document_processing.detection_updater.TextUtils.reconstruct_text_and_mapping",
        return_value=("test example", [({}, 0, 11)])
    )
    def test_reconstruct_page_text_positive(self, mock_reconstruct):
        page_data = {"words": [{"text": "test"}, {"text": "example"}]}

        page_num = 1

        full_text, mapping = self.updater._reconstruct_page_text(page_data, page_num)

        self.assertEqual(full_text, "test example")

        self.assertEqual(mapping, [({}, 0, 11)])

    # No words produces empty text and mapping
    def test_reconstruct_page_text_empty(self):
        page_data = {"words": []}

        page_num = 1

        full_text, mapping = self.updater._reconstruct_page_text(page_data, page_num)

        self.assertEqual(full_text, "")

        self.assertEqual(mapping, [])

    # Split sensitive entity on removal phrase
    def test_process_sensitive_entities_split_with_bbox(self):
        entities = [{"original_text": "Confidential Report 2023", "start": 0, "end": 20}]

        result = self.updater._process_sensitive_entities(
            entities, ["Report"], "Confidential Report 2023", [], 1, {}
        )

        assert len(result) == 2

    # Invalid entity yields default placeholder
    def test_process_sensitive_entities_invalid_entity(self):
        updater = DetectionResultUpdater({}, ([], {}))

        result = updater._process_sensitive_entities([{}], [], "", [], 1, {})

        assert result == [{'end': 0, 'original_text': '', 'start': 0}]

    # Appending updated entity adds correct offsets and bbox
    def test_append_updated_entities(self):
        updated_entities = []

        base_entity = {"original_text": "test", "start": 0, "end": 4}

        updated_text = "example"

        offsets = [(0, 4)]

        self.updater._build_updated_entity = MagicMock(return_value={

            "original_text": updated_text,

            "start": 0,

            "end": 7,

            "bbox": {"top": 0, "left": 0, "bottom": 0, "right": 0}

        })

        self.updater._append_updated_entities(

            updated_entities,

            base_entity,

            updated_text,

            offsets,

            "test example",

            [({}, 0, 4)],

            1,

            {}

        )

        self.assertEqual(len(updated_entities), 1)

        self.assertEqual(updated_entities[0]["original_text"], "example")

        self.assertEqual(updated_entities[0]["start"], 0)

        self.assertEqual(updated_entities[0]["end"], 7)

    # Static reconstruct of page text produces correct mapping
    def test_reconstruct_page_text_basic(self):
        page_data = {
            "words": [

                {"text": "Confidential", "bbox": [10, 20, 30, 40]},

                {"text": "Report", "bbox": [35, 20, 55, 40]},

                {"text": "2023", "bbox": [60, 20, 80, 40]}

            ]

        }

        page_num = 1

        full_text, mapping = DetectionResultUpdater._reconstruct_page_text(page_data, page_num)

        assert full_text == "Confidential Report 2023"

        assert len(mapping) == 3

        assert mapping[0][0]["text"] == "Confidential"

    # Handles missing 'text' key by using 'original_text'
    def test_reconstruct_page_text_missing_text(self):
        page_data = {
            "words": [

                {"original_text": "Confidential", "bbox": [10, 20, 30, 40]},

                {"original_text": "Report", "bbox": [35, 20, 55, 40]},

                {"text": "2023", "bbox": [60, 20, 80, 40]}

            ]

        }

        page_num = 1

        full_text, mapping = DetectionResultUpdater._reconstruct_page_text(page_data, page_num)

        assert full_text == "Confidential Report 2023"

        assert len(mapping) == 3

        assert mapping[0][0]["text"] == "Confidential"

        assert mapping[1][0]["text"] == "Report"

    # Next original page not in data returns empty
    def test_get_original_page_next_empty(self):
        self.updater.extracted_data = {"pages": [{"page": 2, "words": [{"text": "test"}]}]}

        page_data = self.updater._get_original_page(1)

        assert page_data == {}
