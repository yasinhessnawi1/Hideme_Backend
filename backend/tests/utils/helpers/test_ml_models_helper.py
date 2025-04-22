import unittest
from unittest.mock import patch, MagicMock
from transformers import Pipeline

from backend.app.utils.helpers.ml_models_helper import (
    get_spacy_model,
    get_hf_ner_pipeline
)


# Tests for get_spacy_model function
class TestGetSpacyModel(unittest.TestCase):

    # should return loaded model if already installed
    @patch('backend.app.utils.helpers.ml_models_helper.spacy.load')
    @patch('backend.app.utils.helpers.ml_models_helper.log_info')
    def test_get_spacy_model_already_installed(self, mock_log_info, mock_spacy_load):
        mock_model = MagicMock()

        mock_spacy_load.return_value = mock_model

        result = get_spacy_model("en_core_web_sm")

        mock_spacy_load.assert_called_once_with("en_core_web_sm")

        mock_log_info.assert_called_once_with("[OK] Loaded spaCy model 'en_core_web_sm' successfully")

        self.assertEqual(result, mock_model)

    # should download and load model if not installed
    @patch('backend.app.utils.helpers.ml_models_helper.spacy.load')
    @patch('backend.app.utils.helpers.ml_models_helper.spacy_download')
    @patch('backend.app.utils.helpers.ml_models_helper.log_warning')
    @patch('backend.app.utils.helpers.ml_models_helper.log_info')
    def test_get_spacy_model_not_installed(self, mock_log_info, mock_log_warning, mock_spacy_download, mock_spacy_load):
        mock_model = MagicMock()

        mock_spacy_load.side_effect = [OSError(), mock_model]

        result = get_spacy_model("en_core_web_sm")

        self.assertEqual(mock_spacy_load.call_count, 2)

        mock_spacy_download.assert_called_once_with("en_core_web_sm")

        mock_log_warning.assert_called_once_with("[OK] spaCy model 'en_core_web_sm' not found. Downloading...")

        mock_log_info.assert_called_once_with("[OK] Downloaded and loaded spaCy model 'en_core_web_sm'")

        self.assertEqual(result, mock_model)

    # should propagate exception if download fails
    @patch('backend.app.utils.helpers.ml_models_helper.spacy.load')
    @patch('backend.app.utils.helpers.ml_models_helper.spacy_download')
    @patch('backend.app.utils.helpers.ml_models_helper.log_warning')
    @patch('backend.app.utils.helpers.ml_models_helper.log_error')
    def test_get_spacy_model_download_fails(self, mock_log_error, mock_log_warning, mock_spacy_download,
                                            mock_spacy_load):
        mock_spacy_load.side_effect = OSError("Model not found")

        mock_spacy_download.side_effect = Exception("Download failed")

        with self.assertRaises(Exception):
            get_spacy_model("en_core_web_sm")

        mock_spacy_load.assert_called_once_with("en_core_web_sm")

        mock_spacy_download.assert_called_once_with("en_core_web_sm")

        mock_log_warning.assert_called_once_with("[OK] spaCy model 'en_core_web_sm' not found. Downloading...")

        mock_log_error.assert_not_called()

    # should load different model names correctly
    @patch('backend.app.utils.helpers.ml_models_helper.spacy.load')
    @patch('backend.app.utils.helpers.ml_models_helper.log_info')
    def test_get_spacy_model_with_different_model(self, mock_log_info, mock_spacy_load):
        mock_model = MagicMock()

        mock_spacy_load.return_value = mock_model

        result = get_spacy_model("en_core_web_lg")

        mock_spacy_load.assert_called_once_with("en_core_web_lg")

        mock_log_info.assert_called_once_with("[OK] Loaded spaCy model 'en_core_web_lg' successfully")

        self.assertEqual(result, mock_model)


# Tests for get_hf_ner_pipeline function
class TestGetHfNerPipeline(unittest.TestCase):

    # should return NER pipeline on successful load
    @patch('backend.app.utils.helpers.ml_models_helper.AutoTokenizer.from_pretrained')
    @patch('backend.app.utils.helpers.ml_models_helper.AutoModelForTokenClassification.from_pretrained')
    @patch('backend.app.utils.helpers.ml_models_helper.pipeline')
    @patch('backend.app.utils.helpers.ml_models_helper.log_info')
    def test_get_hf_ner_pipeline_success(self, mock_log_info, mock_pipeline, mock_model_from_pretrained,
                                         mock_tokenizer_from_pretrained):
        mock_tokenizer = MagicMock()

        mock_model = MagicMock()

        mock_ner_pipe = MagicMock(spec=Pipeline)

        mock_tokenizer_from_pretrained.return_value = mock_tokenizer

        mock_model_from_pretrained.return_value = mock_model

        mock_pipeline.return_value = mock_ner_pipe

        result = get_hf_ner_pipeline("dslim/bert-base-NER")

        mock_tokenizer_from_pretrained.assert_called_once_with("dslim/bert-base-NER", trust_remote_code=True)

        mock_model_from_pretrained.assert_called_once_with("dslim/bert-base-NER", trust_remote_code=True)

        mock_pipeline.assert_called_once_with(
            "ner",
            model=mock_model,
            tokenizer=mock_tokenizer,
            aggregation_strategy="simple"
        )

        mock_log_info.assert_called_once_with("[OK] Successfully loaded Hugging Face model from 'dslim/bert-base-NER'")

        self.assertEqual(result, mock_ner_pipe)

    # should accept custom aggregation strategy
    @patch('backend.app.utils.helpers.ml_models_helper.AutoTokenizer.from_pretrained')
    @patch('backend.app.utils.helpers.ml_models_helper.AutoModelForTokenClassification.from_pretrained')
    @patch('backend.app.utils.helpers.ml_models_helper.pipeline')
    @patch('backend.app.utils.helpers.ml_models_helper.log_info')
    def test_get_hf_ner_pipeline_with_custom_aggregation(self, mock_log_info, mock_pipeline, mock_model_from_pretrained,
                                                         mock_tokenizer_from_pretrained):
        mock_tokenizer = MagicMock()

        mock_model = MagicMock()

        mock_ner_pipe = MagicMock(spec=Pipeline)

        mock_tokenizer_from_pretrained.return_value = mock_tokenizer

        mock_model_from_pretrained.return_value = mock_model

        mock_pipeline.return_value = mock_ner_pipe

        result = get_hf_ner_pipeline("dslim/bert-base-NER", aggregation_strategy="first")

        mock_pipeline.assert_called_once_with(
            "ner",
            model=mock_model,
            tokenizer=mock_tokenizer,
            aggregation_strategy="first"
        )

        self.assertEqual(result, mock_ner_pipe)

    # should return None and log error if tokenizer fails
    @patch('backend.app.utils.helpers.ml_models_helper.AutoTokenizer.from_pretrained')
    @patch('backend.app.utils.helpers.ml_models_helper.log_error')
    def test_get_hf_ner_pipeline_tokenizer_error(self, mock_log_error, mock_tokenizer_from_pretrained):
        mock_tokenizer_from_pretrained.side_effect = Exception("Tokenizer loading failed")

        result = get_hf_ner_pipeline("invalid/model")

        mock_tokenizer_from_pretrained.assert_called_once_with("invalid/model", trust_remote_code=True)

        mock_log_error.assert_called_once()
        self.assertIn("Failed to load Hugging Face model", mock_log_error.call_args[0][0])
        self.assertIn("invalid/model", mock_log_error.call_args[0][0])
        self.assertIn("Tokenizer loading failed", mock_log_error.call_args[0][0])

        self.assertIsNone(result)

    # should return None and log error if model fails
    @patch('backend.app.utils.helpers.ml_models_helper.AutoTokenizer.from_pretrained')
    @patch('backend.app.utils.helpers.ml_models_helper.AutoModelForTokenClassification.from_pretrained')
    @patch('backend.app.utils.helpers.ml_models_helper.log_error')
    def test_get_hf_ner_pipeline_model_error(self, mock_log_error, mock_model_from_pretrained,
                                             mock_tokenizer_from_pretrained):
        mock_tokenizer = MagicMock()

        mock_tokenizer_from_pretrained.return_value = mock_tokenizer

        mock_model_from_pretrained.side_effect = Exception("Model loading failed")

        result = get_hf_ner_pipeline("dslim/bert-base-NER")

        mock_tokenizer_from_pretrained.assert_called_once_with("dslim/bert-base-NER", trust_remote_code=True)

        mock_model_from_pretrained.assert_called_once_with("dslim/bert-base-NER", trust_remote_code=True)

        mock_log_error.assert_called_once()
        self.assertIn("Failed to load Hugging Face model", mock_log_error.call_args[0][0])
        self.assertIn("dslim/bert-base-NER", mock_log_error.call_args[0][0])
        self.assertIn("Model loading failed", mock_log_error.call_args[0][0])

        self.assertIsNone(result)

    # should return None and log error if pipeline creation fails
    @patch('backend.app.utils.helpers.ml_models_helper.AutoTokenizer.from_pretrained')
    @patch('backend.app.utils.helpers.ml_models_helper.AutoModelForTokenClassification.from_pretrained')
    @patch('backend.app.utils.helpers.ml_models_helper.pipeline')
    @patch('backend.app.utils.helpers.ml_models_helper.log_error')
    def test_get_hf_ner_pipeline_pipeline_error(self, mock_log_error, mock_pipeline, mock_model_from_pretrained,
                                                mock_tokenizer_from_pretrained):
        mock_tokenizer = MagicMock()

        mock_model = MagicMock()

        mock_tokenizer_from_pretrained.return_value = mock_tokenizer

        mock_model_from_pretrained.return_value = mock_model

        mock_pipeline.side_effect = Exception("Pipeline creation failed")

        result = get_hf_ner_pipeline("dslim/bert-base-NER")

        mock_pipeline.assert_called_once_with(
            "ner",
            model=mock_model,
            tokenizer=mock_tokenizer,
            aggregation_strategy="simple"
        )

        mock_log_error.assert_called_once()
        self.assertIn("Failed to load Hugging Face model", mock_log_error.call_args[0][0])
        self.assertIn("dslim/bert-base-NER", mock_log_error.call_args[0][0])
        self.assertIn("Pipeline creation failed", mock_log_error.call_args[0][0])

        self.assertIsNone(result)

    # should load local model paths successfully
    @patch('backend.app.utils.helpers.ml_models_helper.AutoTokenizer.from_pretrained')
    @patch('backend.app.utils.helpers.ml_models_helper.AutoModelForTokenClassification.from_pretrained')
    @patch('backend.app.utils.helpers.ml_models_helper.pipeline')
    @patch('backend.app.utils.helpers.ml_models_helper.log_info')
    def test_get_hf_ner_pipeline_local_path(self, mock_log_info, mock_pipeline, mock_model_from_pretrained,
                                            mock_tokenizer_from_pretrained):
        mock_tokenizer = MagicMock()

        mock_model = MagicMock()

        mock_ner_pipe = MagicMock(spec=Pipeline)

        mock_tokenizer_from_pretrained.return_value = mock_tokenizer

        mock_model_from_pretrained.return_value = mock_model

        mock_pipeline.return_value = mock_ner_pipe

        local_path = "/path/to/local/model"

        result = get_hf_ner_pipeline(local_path)

        mock_tokenizer_from_pretrained.assert_called_once_with(local_path, trust_remote_code=True)

        mock_model_from_pretrained.assert_called_once_with(local_path, trust_remote_code=True)

        mock_log_info.assert_called_once_with(f"[OK] Successfully loaded Hugging Face model from '{local_path}'")

        self.assertEqual(result, mock_ner_pipe)
