from unittest.mock import patch
import pytest

from backend.app.document_processing.pdf_searcher import PDFSearcher
from backend.app.utils.helpers import TextUtils


@pytest.fixture
def extracted_pdf_data():
    # Return mock extracted PDF data for testing

    return {

        "pages": [

            {"page": 1, "words": [{"text": "hello", "bbox": {"x0": 0, "y0": 0, "x1": 50, "y1": 10}},

                                  {"text": "world", "bbox": {"x0": 60, "y0": 0, "x1": 100, "y1": 10}}]},

            {"page": 2, "words": [{"text": "test", "bbox": {"x0": 0, "y0": 0, "x1": 50, "y1": 10}}]}

        ]

    }


@pytest.fixture
def simple_page():
    # a page with two words and their boxes
    return {
        "page": 1,
        "words": [
            {"text": "foo", "bbox": {"x0": 0, "y0": 0, "x1": 10, "y1": 5}},
            {"text": "bar", "bbox": {"x0": 20, "y0": 0, "x1": 30, "y1": 5}},
        ]
    }


class TestPDFSearcher:

    # Build search set for case sensitivity

    def test_build_search_set(self):
        search_terms = ["hello", "world"]

        pdf_searcher = PDFSearcher(extracted_data={})

        case_sensitive_set = pdf_searcher._build_search_set(search_terms, case_sensitive=True)

        insensitive_set = pdf_searcher._build_search_set(search_terms, case_sensitive=False)

        assert "hello" in case_sensitive_set

        assert "WORLD" not in case_sensitive_set

        assert "hello" in insensitive_set

        assert "world" in insensitive_set

    # Word matching logic respects case and AI flag

    def test_word_matches(self):
        search_terms = ["hello"]

        pdf_searcher = PDFSearcher(extracted_data={})

        assert pdf_searcher._word_matches("hello", set(search_terms), case_sensitive=True, ai_search=False)

        assert not pdf_searcher._word_matches("Hello", set(search_terms), case_sensitive=True, ai_search=False)

        assert pdf_searcher._word_matches("hello", set(search_terms), case_sensitive=False, ai_search=False)

    # Build page text and mapping correctly joins words

    def test_build_page_text_and_mapping(self, extracted_pdf_data):
        pdf_searcher = PDFSearcher(extracted_data=extracted_pdf_data)

        mapping, full_text = pdf_searcher.build_page_text_and_mapping(extracted_pdf_data["pages"][0]["words"])

        assert len(mapping) == 2

        assert full_text == "hello world"

    # Fallback page processing counts matches

    def test_process_fallback_page(self, extracted_pdf_data):
        search_set = {"hello", "world"}

        pdf_searcher = PDFSearcher(extracted_data=extracted_pdf_data)

        result, match_count = pdf_searcher._process_fallback_page(

            extracted_pdf_data["pages"][0],

            search_set,

            case_sensitive=False

        )

        assert match_count == 2

        assert len(result["matches"]) == 2

    # Find target phrase occurrences logs debug

    @patch("backend.app.document_processing.pdf_searcher.log_debug")
    def test_find_target_phrase_occurrences(self, mock_log_debug, extracted_pdf_data):
        target_bbox = {"x0": 0, "y0": 2, "x1": 50, "y1": 8}

        pdf_searcher = PDFSearcher(extracted_data=extracted_pdf_data)

        result, total_occurrences = pdf_searcher.find_target_phrase_occurrences(target_bbox)

        assert total_occurrences == 1

        assert "page" in result["pages"][0]

        mock_log_debug.assert_called()

    # Split and remap entity based on mapping

    def test_split_and_remap_entity(self):
        entity = {"original_text": "hello", "entity_type": "greeting", "score": 1.0}

        mapping = [{"start": 0, "end": 5, "bbox": {"x0": 0, "y0": 0, "x1": 50, "y1": 10}, "text": "hello"}]

        pdf_searcher = PDFSearcher(extracted_data={})

        remapped_entities = pdf_searcher._split_and_remap_entity(entity, mapping, case_sensitive=False)

        assert len(remapped_entities) == 1

        assert remapped_entities[0]["entity_type"] == "greeting"

        assert remapped_entities[0]["original_text"] == "hello"

    # AI search integrates with Gemini helper

    @pytest.mark.asyncio
    @patch("backend.app.document_processing.pdf_searcher.gemini_helper.send_request")
    @patch("backend.app.document_processing.pdf_searcher.gemini_helper.parse_response")
    @patch("backend.app.document_processing.pdf_searcher.PDFSearcher._process_fallback_page")
    async def test_search_terms_with_ai_search(self, mock_fallback, mock_parse_response, mock_send_request):
        page_data = {

            "page": 1,

            "words": [

                {"text": "hello", "x0": 0, "y0": 0, "x1": 50, "y1": 10},

                {"text": "world", "x0": 60, "y0": 0, "x1": 100, "y1": 10},

            ],

        }

        mock_send_request.return_value = {

            "pages": [

                {

                    "page": 1,

                    "text": [

                        {

                            "entities": [

                                {

                                    "original_text": "hello",

                                    "entity_type": "word",

                                    "start": 0,

                                    "end": 5,

                                    "score": 0.8,

                                    "bbox": {"x0": 0, "y0": 0, "x1": 50, "y1": 10}

                                },

                                {

                                    "original_text": "world",

                                    "entity_type": "word",

                                    "start": 6,

                                    "end": 10,

                                    "score": 0.85,

                                    "bbox": {"x0": 60, "y0": 0, "x1": 100, "y1": 10}

                                }

                            ]

                        }

                    ]

                }

            ]

        }

        mock_parse_response.return_value = mock_send_request.return_value

        mock_fallback.return_value = ({"page": 1, "matches": []}, 0)

        extracted_pdf_data = {"pages": [page_data]}

        pdf_searcher = PDFSearcher(extracted_data=extracted_pdf_data)

        search_terms = ["hello", "world"]

        result = await pdf_searcher.search_terms(search_terms, case_sensitive=False, ai_search=True)

        assert result["match_count"] == 2

        assert len(result["pages"]) == 1

        assert "bbox" in result["pages"][0]["matches"][0]

        assert "bbox" in result["pages"][0]["matches"][1]

        mock_send_request.assert_called_once()

        mock_parse_response.assert_called_once()

    # Fallback search is used when AI search disabled

    @pytest.mark.asyncio
    @patch("backend.app.document_processing.pdf_searcher.PDFSearcher._process_ai_page")
    @patch("backend.app.document_processing.pdf_searcher.PDFSearcher._process_fallback_page")
    async def test_search_terms_with_fallback(self, mock_fallback, mock_ai_page):
        page_data = {

            "page": 1,

            "words": [

                {"text": "hello", "x0": 0, "y0": 0, "x1": 50, "y1": 10},

                {"text": "world", "x0": 60, "y0": 0, "x1": 100, "y1": 10},

            ],

        }

        mock_fallback.return_value = ({"page": 1, "matches": [

            {"bbox": {"x0": 0, "y0": 0, "x1": 50, "y1": 10}},

            {"bbox": {"x0": 60, "y0": 0, "x1": 100, "y1": 10}}

        ]}, 2)

        mock_ai_page.return_value = ({"page": 1, "matches": []}, 0)

        extracted_pdf_data = {"pages": [page_data]}

        pdf_searcher = PDFSearcher(extracted_data=extracted_pdf_data)

        search_terms = ["hello", "world"]

        result = await pdf_searcher.search_terms(search_terms, case_sensitive=False, ai_search=False)

        assert result["match_count"] == 2

        assert len(result["pages"]) == 1

        assert "bbox" in result["pages"][0]["matches"][0]

        assert "bbox" in result["pages"][0]["matches"][1]

        mock_fallback.assert_called_once()

        mock_ai_page.assert_not_called()

    # Group consecutive indices into ranges

    @pytest.mark.parametrize("input_indices, expected_output", [

        ([], []),

        ([1, 2, 3, 4], [[1, 2, 3, 4]]),

        ([1, 2, 5, 6, 7, 10, 11], [[1, 2], [5, 6, 7], [10, 11]]),

        ([1, 3, 5, 7], [[1], [3], [5], [7]]),

        ([1, 2, 4, 5, 7, 8, 10], [[1, 2], [4, 5], [7, 8], [10]])

    ])
    def test_group_consecutive_indices(self, input_indices, expected_output):
        result = PDFSearcher._group_consecutive_indices(input_indices)

        assert result == expected_output

    # Process multiword occurrences merges bboxes and logs debug

    @pytest.mark.asyncio
    @patch("backend.app.document_processing.pdf_searcher.TextUtils.reconstruct_text_and_mapping")
    @patch("backend.app.document_processing.pdf_searcher.TextUtils.recompute_offsets")
    @patch("backend.app.document_processing.pdf_searcher.TextUtils.map_offsets_to_bboxes")
    @patch("backend.app.document_processing.pdf_searcher.TextUtils.merge_bounding_boxes")
    @patch("backend.app.document_processing.pdf_searcher.log_debug")
    async def test_process_multiword_occurrences(

            self, mock_log_debug, mock_merge_bboxes, mock_map_offsets_to_bboxes, mock_recompute_offsets,

            mock_reconstruct_text_and_mapping

    ):
        page_data = {

            "page": 1,

            "words": [

                {"text": "hello", "x0": 0, "y0": 0, "x1": 50, "y1": 10},

                {"text": "world", "x0": 60, "y0": 0, "x1": 100, "y1": 10},

            ],

        }

        candidate_phrase = "hello world"

        mock_reconstruct_text_and_mapping.return_value = ("hello world", [

            {"text": "hello", "bbox": {"x0": 0, "y0": 0, "x1": 50, "y1": 10}},

            {"text": "world", "bbox": {"x0": 60, "y0": 0, "x1": 100, "y1": 10}}

        ])

        mock_recompute_offsets.return_value = [(0, 5), (6, 11)]

        mock_map_offsets_to_bboxes.return_value = [

            {"x0": 0, "y0": 0, "x1": 50, "y1": 10},

            {"x0": 60, "y0": 0, "x1": 100, "y1": 10}

        ]

        mock_merge_bboxes.return_value = {"composite": {"x0": 0, "y0": 0, "x1": 100, "y1": 10}}

        extracted_pdf_data = {"pages": [page_data]}

        pdf_searcher = PDFSearcher(extracted_data=extracted_pdf_data)

        result, match_count = pdf_searcher._process_multiword_occurrences(page_data, candidate_phrase)

        assert match_count == 2

        assert len(result["matches"]) == 2

        assert "bbox" in result["matches"][0]

        assert result["matches"][0]["bbox"] == {"x0": 0, "y0": 0, "x1": 100, "y1": 10}

        mock_reconstruct_text_and_mapping.assert_called_once_with(page_data["words"])

        mock_recompute_offsets.assert_called_once_with("hello world", candidate_phrase)

        assert mock_map_offsets_to_bboxes.call_count == 2

        mock_map_offsets_to_bboxes.assert_any_call("hello world", [

            {"text": "hello", "bbox": {"x0": 0, "y0": 0, "x1": 50, "y1": 10}},

            {"text": "world", "bbox": {"x0": 60, "y0": 0, "x1": 100, "y1": 10}}

        ], (0, 5))

        mock_map_offsets_to_bboxes.assert_any_call("hello world", [

            {"text": "hello", "bbox": {"x0": 0, "y0": 0, "x1": 50, "y1": 10}},

            {"text": "world", "bbox": {"x0": 60, "y0": 0, "x1": 100, "y1": 10}}

        ], (6, 11))


    def test_single_word_returns_its_bbox(self, simple_page):
        mapping, _ = PDFSearcher(extracted_data={}).build_page_text_and_mapping(simple_page["words"])

        bbox = PDFSearcher._get_phrase_bbox(simple_page, mapping, [1], "bar")

        # Here we should also include the padding y0=+2 and y1=-2 (y0 = 0 + 2 = 2) (y1 = 5 - 2 = 3)
        assert bbox == {"x0": 20, "y0": 2, "x1": 30, "y1": 3}

    @patch.object(TextUtils, "reconstruct_text_and_mapping")
    @patch.object(TextUtils, "recompute_offsets")
    @patch.object(TextUtils, "map_offsets_to_bboxes")
    @patch.object(TextUtils, "merge_bounding_boxes")
    def test_multiword_merges_correctly(
            self,
            mock_merge,
            mock_map,
            mock_recompute,
            mock_reconstruct,
            simple_page
    ):
        mock_reconstruct.return_value = (
            "foo bar",
            simple_page["words"]
        )

        mock_recompute.return_value = [(0, 6)]

        mock_map.return_value = [
            {"x0": 0, "y0": 2, "x1": 10, "y1": 3},
            {"x0": 20, "y0": 2, "x1": 30, "y1": 3},
        ]

        mock_merge.return_value = {"composite": {"x0": 0, "y0": 2, "x1": 30, "y1": 3}}

        mapping, _ = PDFSearcher(extracted_data={}).build_page_text_and_mapping(simple_page["words"])

        bbox = PDFSearcher._get_phrase_bbox(simple_page, mapping, [0, 1], "foo bar")

        mock_reconstruct.assert_called_once_with(simple_page["words"])

        mock_recompute.assert_called_once_with("foo bar", "foo bar")

        mock_map.assert_called_once_with(
            "foo bar", simple_page["words"], (0, 6)
        )

        mock_merge.assert_called_once_with(mock_map.return_value)

        assert bbox == {"x0": 0, "y0": 2, "x1": 30, "y1": 3}
