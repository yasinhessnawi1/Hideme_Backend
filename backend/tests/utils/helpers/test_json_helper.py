import unittest
from unittest.mock import patch
from fastapi import HTTPException

from backend.app.utils.helpers.json_helper import (
    validate_threshold_score,
    check_all_option,
    validate_all_engines_requested_entities,
    validate_gemini_requested_entities,
    validate_presidio_requested_entities,
    validate_gliner_requested_entities,
    validate_hideme_requested_entities,
)


# Tests for validate_threshold_score


# Test class for validate_threshold_score function
class TestValidateThresholdScore(unittest.TestCase):

    # should accept valid thresholds unchanged
    def test_validate_threshold_score_valid(self):
        self.assertEqual(validate_threshold_score(0.0), 0.0)

        self.assertEqual(validate_threshold_score(0.5), 0.5)

        self.assertEqual(validate_threshold_score(1.0), 1.0)

        self.assertEqual(validate_threshold_score(0.75), 0.75)

    # should return None when threshold is None
    def test_validate_threshold_score_none(self):
        self.assertIsNone(validate_threshold_score(None))

    # should raise HTTPException for thresholds below 0.0
    def test_validate_threshold_score_below_range(self):
        with self.assertRaises(HTTPException) as context:
            validate_threshold_score(-0.1)

        self.assertEqual(context.exception.status_code, 400)

        self.assertEqual(
            context.exception.detail, "Threshold must be between 0.00 and 1.00."
        )

    # should raise HTTPException for thresholds above 1.0
    def test_validate_threshold_score_above_range(self):
        with self.assertRaises(HTTPException) as context:
            validate_threshold_score(1.1)

        self.assertEqual(context.exception.status_code, 400)

        self.assertEqual(
            context.exception.detail, "Threshold must be between 0.00 and 1.00."
        )

    # should accept edge-case thresholds 0.0 and 1.0
    def test_validate_threshold_score_edge_cases(self):
        self.assertEqual(validate_threshold_score(0.0), 0.0)

        self.assertEqual(validate_threshold_score(1.0), 1.0)


# Tests for check_all_option


# Test class for check_all_option function
class TestCheckAllOption(unittest.TestCase):

    @patch(
        "backend.app.utils.helpers.json_helper.PRESIDIO_AVAILABLE_ENTITIES",
        ["PERSON", "EMAIL_ADDRESS"],
    )
    @patch(
        "backend.app.utils.helpers.json_helper.GEMINI_AVAILABLE_ENTITIES",
        {"PERSON": "person", "EMAIL": "email"},
    )
    @patch(
        "backend.app.utils.helpers.json_helper.GLINER_AVAILABLE_ENTITIES",
        ["PERSON", "ORGANIZATION"],
    )
    @patch(
        "backend.app.utils.helpers.json_helper.HIDEME_AVAILABLE_ENTITIES",
        ["PERSON", "PHONE_NUMBER"],
    )
    # should expand ALL_PRESIDIO to all Presidio entities
    def test_check_all_option_with_all_presidio(self, *mocks):
        result = check_all_option(["ALL_PRESIDIO"])

        self.assertEqual(result, ["PERSON", "EMAIL_ADDRESS"])

    @patch(
        "backend.app.utils.helpers.json_helper.PRESIDIO_AVAILABLE_ENTITIES",
        ["PERSON", "EMAIL_ADDRESS"],
    )
    @patch(
        "backend.app.utils.helpers.json_helper.GEMINI_AVAILABLE_ENTITIES",
        {"PERSON": "person", "EMAIL": "email"},
    )
    @patch(
        "backend.app.utils.helpers.json_helper.GLINER_AVAILABLE_ENTITIES",
        ["PERSON", "ORGANIZATION"],
    )
    @patch(
        "backend.app.utils.helpers.json_helper.HIDEME_AVAILABLE_ENTITIES",
        ["PERSON", "PHONE_NUMBER"],
    )
    # should expand ALL_GEMINI to all Gemini entities
    def test_check_all_option_with_all_gemini(self, *mocks):
        result = check_all_option(["ALL_GEMINI"])

        self.assertEqual(result, ["PERSON", "EMAIL"])

    @patch(
        "backend.app.utils.helpers.json_helper.PRESIDIO_AVAILABLE_ENTITIES",
        ["PERSON", "EMAIL_ADDRESS"],
    )
    @patch(
        "backend.app.utils.helpers.json_helper.GEMINI_AVAILABLE_ENTITIES",
        {"PERSON": "person", "EMAIL": "email"},
    )
    @patch(
        "backend.app.utils.helpers.json_helper.GLINER_AVAILABLE_ENTITIES",
        ["PERSON", "ORGANIZATION"],
    )
    @patch(
        "backend.app.utils.helpers.json_helper.HIDEME_AVAILABLE_ENTITIES",
        ["PERSON", "PHONE_NUMBER"],
    )
    # should expand ALL_GLINER to all Gliner entities
    def test_check_all_option_with_all_gliner(self, *mocks):
        result = check_all_option(["ALL_GLINER"])

        self.assertEqual(result, ["PERSON", "ORGANIZATION"])

    @patch(
        "backend.app.utils.helpers.json_helper.PRESIDIO_AVAILABLE_ENTITIES",
        ["PERSON", "EMAIL_ADDRESS"],
    )
    @patch(
        "backend.app.utils.helpers.json_helper.GEMINI_AVAILABLE_ENTITIES",
        {"PERSON": "person", "EMAIL": "email"},
    )
    @patch(
        "backend.app.utils.helpers.json_helper.GLINER_AVAILABLE_ENTITIES",
        ["PERSON", "ORGANIZATION"],
    )
    @patch(
        "backend.app.utils.helpers.json_helper.HIDEME_AVAILABLE_ENTITIES",
        ["PERSON", "PHONE_NUMBER"],
    )
    # should expand ALL_HIDEME to all Hideme entities
    def test_check_all_option_with_all_hideme(self, *mocks):
        result = check_all_option(["ALL_HIDEME"])

        self.assertEqual(result, ["PERSON", "PHONE_NUMBER"])

    @patch(
        "backend.app.utils.helpers.json_helper.PRESIDIO_AVAILABLE_ENTITIES",
        ["PERSON", "EMAIL_ADDRESS"],
    )
    @patch(
        "backend.app.utils.helpers.json_helper.GEMINI_AVAILABLE_ENTITIES",
        {"PERSON": "person", "EMAIL": "email"},
    )
    @patch(
        "backend.app.utils.helpers.json_helper.GLINER_AVAILABLE_ENTITIES",
        ["PERSON", "ORGANIZATION"],
    )
    @patch(
        "backend.app.utils.helpers.json_helper.HIDEME_AVAILABLE_ENTITIES",
        ["PERSON", "PHONE_NUMBER"],
    )
    # should combine ALL_ options and specific entities correctly
    def test_check_all_option_with_mixed_options(self, *mocks):
        result = check_all_option(["ALL_PRESIDIO", "CREDIT_CARD", "ALL_GEMINI"])

        expected = ["PERSON", "EMAIL_ADDRESS", "CREDIT_CARD", "PERSON", "EMAIL"]

        self.assertEqual(result, expected)

    @patch(
        "backend.app.utils.helpers.json_helper.PRESIDIO_AVAILABLE_ENTITIES",
        ["PERSON", "EMAIL_ADDRESS"],
    )
    @patch(
        "backend.app.utils.helpers.json_helper.GEMINI_AVAILABLE_ENTITIES",
        {"PERSON": "person", "EMAIL": "email"},
    )
    @patch(
        "backend.app.utils.helpers.json_helper.GLINER_AVAILABLE_ENTITIES",
        ["PERSON", "ORGANIZATION"],
    )
    @patch(
        "backend.app.utils.helpers.json_helper.HIDEME_AVAILABLE_ENTITIES",
        ["PERSON", "PHONE_NUMBER"],
    )
    # should return specific entities unchanged when no ALL_ present
    def test_check_all_option_with_specific_entities(self, *mocks):
        result = check_all_option(["PERSON", "EMAIL_ADDRESS"])

        self.assertEqual(result, ["PERSON", "EMAIL_ADDRESS"])

    @patch(
        "backend.app.utils.helpers.json_helper.PRESIDIO_AVAILABLE_ENTITIES",
        ["PERSON", "EMAIL_ADDRESS"],
    )
    @patch(
        "backend.app.utils.helpers.json_helper.GEMINI_AVAILABLE_ENTITIES",
        {"PERSON": "person", "EMAIL": "email"},
    )
    @patch(
        "backend.app.utils.helpers.json_helper.GLINER_AVAILABLE_ENTITIES",
        ["PERSON", "ORGANIZATION"],
    )
    @patch(
        "backend.app.utils.helpers.json_helper.HIDEME_AVAILABLE_ENTITIES",
        ["PERSON", "PHONE_NUMBER"],
    )
    # should return empty list when input is empty
    def test_check_all_option_with_empty_list(self, *mocks):
        result = check_all_option([])

        self.assertEqual(result, [])

    @patch(
        "backend.app.utils.helpers.json_helper.PRESIDIO_AVAILABLE_ENTITIES",
        ["PERSON", "EMAIL_ADDRESS"],
    )
    @patch(
        "backend.app.utils.helpers.json_helper.GEMINI_AVAILABLE_ENTITIES",
        {"PERSON": "person", "EMAIL": "email"},
    )
    @patch(
        "backend.app.utils.helpers.json_helper.GLINER_AVAILABLE_ENTITIES",
        ["PERSON", "ORGANIZATION"],
    )
    @patch(
        "backend.app.utils.helpers.json_helper.HIDEME_AVAILABLE_ENTITIES",
        ["PERSON", "PHONE_NUMBER"],
    )
    # should combine all ALL_ options into full list
    def test_check_all_option_with_all_options(self, *mocks):
        result = check_all_option(
            ["ALL_PRESIDIO", "ALL_GEMINI", "ALL_GLINER", "ALL_HIDEME"]
        )

        expected = [
            "PERSON",
            "EMAIL_ADDRESS",  # PRESIDIO
            "PERSON",
            "EMAIL",  # GEMINI
            "PERSON",
            "ORGANIZATION",  # GLINER
            "PERSON",
            "PHONE_NUMBER",  # HIDEME
        ]

        self.assertEqual(result, expected)


# Tests for validate_all_engines_requested_entities


# Test class for validate_all_engines_requested_entities function
class TestValidateAllEnginesRequestedEntities(unittest.TestCase):

    @patch(
        "backend.app.utils.helpers.json_helper.PRESIDIO_AVAILABLE_ENTITIES",
        ["P1", "P2"],
    )
    @patch(
        "backend.app.utils.helpers.json_helper.GEMINI_AVAILABLE_ENTITIES",
        {"G1": "gemini1", "G2": "gemini2"},
    )
    @patch(
        "backend.app.utils.helpers.json_helper.GLINER_AVAILABLE_ENTITIES", ["L1", "L2"]
    )
    @patch(
        "backend.app.utils.helpers.json_helper.HIDEME_AVAILABLE_ENTITIES", ["H1", "H2"]
    )
    @patch("backend.app.utils.helpers.json_helper.log_warning")
    @patch("backend.app.utils.helpers.json_helper.log_info")
    # should return all entities and log warning when input is None
    def test_validate_all_engines_requested_entities_none(
        self, mock_log_info, mock_log_warning, *mocks
    ):
        result = validate_all_engines_requested_entities(None)

        expected = ["G1", "G2", "P1", "P2", "L1", "L2", "H1", "H2"]

        self.assertEqual(result, expected)

        mock_log_warning.assert_called_once()

        self.assertIn(
            "No specific entities requested", mock_log_warning.call_args[0][0]
        )

    @patch(
        "backend.app.utils.helpers.json_helper.PRESIDIO_AVAILABLE_ENTITIES",
        ["P1", "P2"],
    )
    @patch(
        "backend.app.utils.helpers.json_helper.GEMINI_AVAILABLE_ENTITIES",
        {"G1": "gemini1", "G2": "gemini2"},
    )
    @patch(
        "backend.app.utils.helpers.json_helper.GLINER_AVAILABLE_ENTITIES", ["L1", "L2"]
    )
    @patch(
        "backend.app.utils.helpers.json_helper.HIDEME_AVAILABLE_ENTITIES", ["H1", "H2"]
    )
    @patch("backend.app.utils.helpers.json_helper.log_info")
    # should validate and return only requested entities from JSON
    def test_validate_all_engines_requested_entities_valid_json(
        self, mock_log_info, *mocks
    ):
        result = validate_all_engines_requested_entities('["P1", "L2"]')

        self.assertEqual(result, ["P1", "L2"])

        mock_log_info.assert_called_once()

        self.assertIn("Validated entity list", mock_log_info.call_args[0][0])

    @patch(
        "backend.app.utils.helpers.json_helper.PRESIDIO_AVAILABLE_ENTITIES",
        ["P1", "P2"],
    )
    @patch(
        "backend.app.utils.helpers.json_helper.GEMINI_AVAILABLE_ENTITIES",
        {"G1": "gemini1", "G2": "gemini2"},
    )
    @patch(
        "backend.app.utils.helpers.json_helper.GLINER_AVAILABLE_ENTITIES", ["L1", "L2"]
    )
    @patch(
        "backend.app.utils.helpers.json_helper.HIDEME_AVAILABLE_ENTITIES", ["H1", "H2"]
    )
    # should raise HTTPException for invalid entity in JSON
    def test_validate_all_engines_requested_entities_invalid_entity(self, *mocks):
        with self.assertRaises(HTTPException) as context:
            validate_all_engines_requested_entities('["INVALID"]')

        self.assertEqual(context.exception.status_code, 400)

        self.assertIn("Invalid entity type: INVALID", context.exception.detail)


# Tests for validate_gemini_requested_entities


# Test class for validate_gemini_requested_entities function
class TestValidateGeminiRequestedEntities(unittest.TestCase):

    @patch("backend.app.utils.helpers.json_helper.log_warning")
    # should return empty list and log warning when input is None
    def test_validate_gemini_requested_entities_none(self, mock_log_warning):
        result = validate_gemini_requested_entities(None)

        self.assertEqual(result, [])

        mock_log_warning.assert_called_once()

        self.assertIn(
            "No specific entities requested", mock_log_warning.call_args[0][0]
        )

    @patch("backend.app.utils.helpers.json_helper.log_info")
    @patch("backend.app.utils.helpers.json_helper.log_warning")
    # should expand ALL_GEMINI to all available Gemini keys
    def test_validate_gemini_requested_entities_all_gemini(
        self, mock_log_warning, mock_log_info
    ):
        with patch(
            "backend.app.utils.helpers.json_helper.GEMINI_AVAILABLE_ENTITIES",
            {"G1": "gem1", "G2": "gem2"},
        ):
            result = validate_gemini_requested_entities('["ALL_GEMINI"]')

            self.assertEqual(result, ["G1", "G2"])

            mock_log_info.assert_called_once()

    @patch("backend.app.utils.helpers.json_helper.log_info")
    @patch("backend.app.utils.helpers.json_helper.log_warning")
    # should return valid single Gemini entity and log info
    def test_validate_gemini_requested_entities_valid(
        self, mock_log_warning, mock_log_info
    ):
        with patch(
            "backend.app.utils.helpers.json_helper.GEMINI_AVAILABLE_ENTITIES",
            {"G1": "gem1", "G2": "gem2"},
        ):
            result = validate_gemini_requested_entities('["G1"]')

            self.assertEqual(result, ["G1"])

            mock_log_info.assert_called_once()

    # should raise HTTPException for invalid JSON format
    def test_validate_gemini_requested_entities_invalid_json(self):
        with self.assertRaises(HTTPException) as context:
            validate_gemini_requested_entities('{"invalid": json}')

        self.assertEqual(context.exception.status_code, 400)

        self.assertEqual(
            context.exception.detail, "Invalid JSON format in gemini requested_entities"
        )


# Tests for validate_presidio_requested_entities


# Test class for validate_presidio_requested_entities function
class TestValidatePresidioRequestedEntities(unittest.TestCase):

    @patch("backend.app.utils.helpers.json_helper.log_warning")
    # should return empty list and log warning when input is None
    def test_validate_presidio_requested_entities_none(self, mock_log_warning):
        result = validate_presidio_requested_entities(None)

        self.assertEqual(result, [])

        mock_log_warning.assert_called_once()

    @patch("backend.app.utils.helpers.json_helper.log_info")
    @patch("backend.app.utils.helpers.json_helper.log_warning")
    # should expand ALL_PRESIDIO to all available Presidio entities
    def test_validate_presidio_requested_entities_all_presidio(
        self, mock_log_warning, mock_log_info
    ):
        with patch(
            "backend.app.utils.helpers.json_helper.PRESIDIO_AVAILABLE_ENTITIES",
            ["P1", "P2"],
        ):
            result = validate_presidio_requested_entities('["ALL_PRESIDIO"]')

            self.assertEqual(result, ["P1", "P2"])

            mock_log_info.assert_called_once()

    @patch("backend.app.utils.helpers.json_helper.log_info")
    @patch("backend.app.utils.helpers.json_helper.log_warning")
    # should return valid single Presidio entity and log info
    def test_validate_presidio_requested_entities_valid(
        self, mock_log_warning, mock_log_info
    ):
        with patch(
            "backend.app.utils.helpers.json_helper.PRESIDIO_AVAILABLE_ENTITIES",
            ["P1", "P2"],
        ):
            result = validate_presidio_requested_entities('["P1"]')

            self.assertEqual(result, ["P1"])

            mock_log_info.assert_called_once()

    # should raise HTTPException for invalid JSON format
    def test_validate_presidio_requested_entities_invalid_json(self):
        with self.assertRaises(HTTPException) as context:
            validate_presidio_requested_entities('{"invalid": json}')

        self.assertEqual(context.exception.status_code, 400)


# Tests for validate_gliner_requested_entities


# Test class for validate_gliner_requested_entities function
class TestValidateGlinerRequestedEntities(unittest.TestCase):

    @patch("backend.app.utils.helpers.json_helper.log_warning")
    # should return empty list and log warning when input is None
    def test_validate_gliner_requested_entities_none(self, mock_log_warning):
        result = validate_gliner_requested_entities(None)

        self.assertEqual(result, [])

        mock_log_warning.assert_called_once()

    @patch("backend.app.utils.helpers.json_helper.log_info")
    @patch("backend.app.utils.helpers.json_helper.log_warning")
    # should expand ALL_GLINER to all available Gliner entities
    def test_validate_gliner_requested_entities_all_gliner(
        self, mock_log_warning, mock_log_info
    ):
        with patch(
            "backend.app.utils.helpers.json_helper.GLINER_AVAILABLE_ENTITIES",
            ["L1", "L2"],
        ):
            result = validate_gliner_requested_entities('["ALL_GLINER"]')

            self.assertEqual(result, ["L1", "L2"])

            mock_log_info.assert_called_once()

    @patch("backend.app.utils.helpers.json_helper.log_info")
    @patch("backend.app.utils.helpers.json_helper.log_warning")
    # should return valid single Gliner entity and log info
    def test_validate_gliner_requested_entities_valid(
        self, mock_log_warning, mock_log_info
    ):
        with patch(
            "backend.app.utils.helpers.json_helper.GLINER_AVAILABLE_ENTITIES",
            ["L1", "L2"],
        ):
            result = validate_gliner_requested_entities('["L1"]')

            self.assertEqual(result, ["L1"])

            mock_log_info.assert_called_once()

    # should raise HTTPException for invalid JSON format
    def test_validate_gliner_requested_entities_invalid_json(self):
        with self.assertRaises(HTTPException) as context:
            validate_gliner_requested_entities('{"invalid": json}')

        self.assertEqual(context.exception.status_code, 400)


# Tests for validate_hideme_requested_entities


# Test class for validate_hideme_requested_entities function
class TestValidateHidemeRequestedEntities(unittest.TestCase):

    @patch("backend.app.utils.helpers.json_helper.log_warning")
    # should return empty list and log warning when input is None
    def test_validate_hideme_requested_entities_none(self, mock_log_warning):
        result = validate_hideme_requested_entities(None)

        self.assertEqual(result, [])

        mock_log_warning.assert_called_once()

    @patch("backend.app.utils.helpers.json_helper.log_info")
    @patch("backend.app.utils.helpers.json_helper.log_warning")
    # should expand ALL_HIDEME to all available Hideme entities
    def test_validate_hideme_requested_entities_all_hideme(
        self, mock_log_warning, mock_log_info
    ):
        with patch(
            "backend.app.utils.helpers.json_helper.HIDEME_AVAILABLE_ENTITIES",
            ["H1", "H2"],
        ):
            result = validate_hideme_requested_entities('["ALL_HIDEME"]')

            self.assertEqual(result, ["H1", "H2"])

            mock_log_info.assert_called_once()

    @patch("backend.app.utils.helpers.json_helper.log_info")
    @patch("backend.app.utils.helpers.json_helper.log_warning")
    # should return valid single Hideme entity and log info
    def test_validate_hideme_requested_entities_valid(
        self, mock_log_warning, mock_log_info
    ):
        with patch(
            "backend.app.utils.helpers.json_helper.HIDEME_AVAILABLE_ENTITIES",
            ["H1", "H2"],
        ):
            result = validate_hideme_requested_entities('["H1"]')

            self.assertEqual(result, ["H1"])

            mock_log_info.assert_called_once()

    # should raise HTTPException for invalid JSON format
    def test_validate_hideme_requested_entities_invalid_json(self):
        with self.assertRaises(HTTPException) as context:
            validate_hideme_requested_entities('{"invalid": json}')

        self.assertEqual(context.exception.status_code, 400)
