"""
Unit tests for ml_models_helper.py module.

This test file covers the ML model helper functions with both positive
and negative test cases to ensure proper functionality and error handling.
"""

import unittest
from unittest.mock import patch, MagicMock

from transformers import Pipeline

# Import the module to be tested
from backend.app.utils.helpers.ml_models_helper import (
    get_spacy_model,
    get_hf_ner_pipeline
)


class TestGetSpacyModel(unittest.TestCase):
    """Test cases for get_spacy_model function."""

    @patch('backend.app.utils.helpers.ml_models_helper.spacy.load')
    @patch('backend.app.utils.helpers.ml_models_helper.log_info')
    def test_get_spacy_model_already_installed(self, mock_log_info, mock_spacy_load):
        """Test get_spacy_model when the model is already installed."""
        # Set up mock
        mock_model = MagicMock()
        mock_spacy_load.return_value = mock_model
        
        # Call the function
        result = get_spacy_model("en_core_web_sm")
        
        # Verify spacy.load was called with the correct model name
        mock_spacy_load.assert_called_once_with("en_core_web_sm")
        
        # Verify log_info was called with success message
        mock_log_info.assert_called_once_with("[OK] Loaded spaCy model 'en_core_web_sm' successfully")
        
        # Verify the function returns the loaded model
        self.assertEqual(result, mock_model)

    @patch('backend.app.utils.helpers.ml_models_helper.spacy.load')
    @patch('backend.app.utils.helpers.ml_models_helper.spacy_download')
    @patch('backend.app.utils.helpers.ml_models_helper.log_warning')
    @patch('backend.app.utils.helpers.ml_models_helper.log_info')
    def test_get_spacy_model_not_installed(self, mock_log_info, mock_log_warning, 
                                          mock_spacy_download, mock_spacy_load):
        """Test get_spacy_model when the model is not installed and needs to be downloaded."""
        # Set up mocks
        mock_model = MagicMock()
        # First call raises OSError, second call returns the model
        mock_spacy_load.side_effect = [OSError(), mock_model]
        
        # Call the function
        result = get_spacy_model("en_core_web_sm")
        
        # Verify spacy.load was called twice
        self.assertEqual(mock_spacy_load.call_count, 2)
        
        # Verify spacy_download was called with the correct model name
        mock_spacy_download.assert_called_once_with("en_core_web_sm")
        
        # Verify log_warning was called with download message
        mock_log_warning.assert_called_once_with("[OK] spaCy model 'en_core_web_sm' not found. Downloading...")
        
        # Verify log_info was called with success message after download
        mock_log_info.assert_called_once_with("[OK] Downloaded and loaded spaCy model 'en_core_web_sm'")
        
        # Verify the function returns the loaded model
        self.assertEqual(result, mock_model)

    @patch('backend.app.utils.helpers.ml_models_helper.spacy.load')
    @patch('backend.app.utils.helpers.ml_models_helper.spacy_download')
    @patch('backend.app.utils.helpers.ml_models_helper.log_warning')
    @patch('backend.app.utils.helpers.ml_models_helper.log_error')
    def test_get_spacy_model_download_fails(self, mock_log_error, mock_log_warning, 
                                           mock_spacy_download, mock_spacy_load):
        """Test get_spacy_model when the model download fails."""
        # Set up mocks
        mock_spacy_load.side_effect = OSError("Model not found")
        mock_spacy_download.side_effect = Exception("Download failed")
        
        # Call the function and expect exception to be raised
        with self.assertRaises(Exception):
            get_spacy_model("en_core_web_sm")
        
        # Verify spacy.load was called once
        mock_spacy_load.assert_called_once_with("en_core_web_sm")
        
        # Verify spacy_download was called with the correct model name
        mock_spacy_download.assert_called_once_with("en_core_web_sm")
        
        # Verify log_warning was called with download message
        mock_log_warning.assert_called_once_with("[OK] spaCy model 'en_core_web_sm' not found. Downloading...")
        
        # Verify log_error was not called (exception is propagated)
        mock_log_error.assert_not_called()

    @patch('backend.app.utils.helpers.ml_models_helper.spacy.load')
    @patch('backend.app.utils.helpers.ml_models_helper.log_info')
    def test_get_spacy_model_with_different_model(self, mock_log_info, mock_spacy_load):
        """Test get_spacy_model with a different model name."""
        # Set up mock
        mock_model = MagicMock()
        mock_spacy_load.return_value = mock_model
        
        # Call the function with a different model name
        result = get_spacy_model("en_core_web_lg")
        
        # Verify spacy.load was called with the correct model name
        mock_spacy_load.assert_called_once_with("en_core_web_lg")
        
        # Verify log_info was called with success message
        mock_log_info.assert_called_once_with("[OK] Loaded spaCy model 'en_core_web_lg' successfully")
        
        # Verify the function returns the loaded model
        self.assertEqual(result, mock_model)


class TestGetHfNerPipeline(unittest.TestCase):
    """Test cases for get_hf_ner_pipeline function."""

    @patch('backend.app.utils.helpers.ml_models_helper.AutoTokenizer.from_pretrained')
    @patch('backend.app.utils.helpers.ml_models_helper.AutoModelForTokenClassification.from_pretrained')
    @patch('backend.app.utils.helpers.ml_models_helper.pipeline')
    @patch('backend.app.utils.helpers.ml_models_helper.log_info')
    def test_get_hf_ner_pipeline_success(self, mock_log_info, mock_pipeline, 
                                        mock_model_from_pretrained, mock_tokenizer_from_pretrained):
        """Test get_hf_ner_pipeline with successful model loading."""
        # Set up mocks
        mock_tokenizer = MagicMock()
        mock_model = MagicMock()
        mock_ner_pipe = MagicMock(spec=Pipeline)
        
        mock_tokenizer_from_pretrained.return_value = mock_tokenizer
        mock_model_from_pretrained.return_value = mock_model
        mock_pipeline.return_value = mock_ner_pipe
        
        # Call the function
        result = get_hf_ner_pipeline("dslim/bert-base-NER")
        
        # Verify AutoTokenizer.from_pretrained was called with correct arguments
        mock_tokenizer_from_pretrained.assert_called_once_with("dslim/bert-base-NER", trust_remote_code=True)
        
        # Verify AutoModelForTokenClassification.from_pretrained was called with correct arguments
        mock_model_from_pretrained.assert_called_once_with("dslim/bert-base-NER", trust_remote_code=True)
        
        # Verify pipeline was called with correct arguments
        mock_pipeline.assert_called_once_with(
            "ner",
            model=mock_model,
            tokenizer=mock_tokenizer,
            aggregation_strategy="simple"
        )
        
        # Verify log_info was called with success message
        mock_log_info.assert_called_once_with("[OK] Successfully loaded Hugging Face model from 'dslim/bert-base-NER'")
        
        # Verify the function returns the NER pipeline
        self.assertEqual(result, mock_ner_pipe)

    @patch('backend.app.utils.helpers.ml_models_helper.AutoTokenizer.from_pretrained')
    @patch('backend.app.utils.helpers.ml_models_helper.AutoModelForTokenClassification.from_pretrained')
    @patch('backend.app.utils.helpers.ml_models_helper.pipeline')
    @patch('backend.app.utils.helpers.ml_models_helper.log_info')
    def test_get_hf_ner_pipeline_with_custom_aggregation(self, mock_log_info, mock_pipeline, 
                                                       mock_model_from_pretrained, mock_tokenizer_from_pretrained):
        """Test get_hf_ner_pipeline with custom aggregation strategy."""
        # Set up mocks
        mock_tokenizer = MagicMock()
        mock_model = MagicMock()
        mock_ner_pipe = MagicMock(spec=Pipeline)
        
        mock_tokenizer_from_pretrained.return_value = mock_tokenizer
        mock_model_from_pretrained.return_value = mock_model
        mock_pipeline.return_value = mock_ner_pipe
        
        # Call the function with custom aggregation strategy
        result = get_hf_ner_pipeline("dslim/bert-base-NER", aggregation_strategy="first")
        
        # Verify pipeline was called with custom aggregation strategy
        mock_pipeline.assert_called_once_with(
            "ner",
            model=mock_model,
            tokenizer=mock_tokenizer,
            aggregation_strategy="first"
        )
        
        # Verify the function returns the NER pipeline
        self.assertEqual(result, mock_ner_pipe)

    @patch('backend.app.utils.helpers.ml_models_helper.AutoTokenizer.from_pretrained')
    @patch('backend.app.utils.helpers.ml_models_helper.log_error')
    def test_get_hf_ner_pipeline_tokenizer_error(self, mock_log_error, mock_tokenizer_from_pretrained):
        """Test get_hf_ner_pipeline when tokenizer loading fails."""
        # Set up mock to raise an exception
        mock_tokenizer_from_pretrained.side_effect = Exception("Tokenizer loading failed")
        
        # Call the function
        result = get_hf_ner_pipeline("invalid/model")
        
        # Verify AutoTokenizer.from_pretrained was called with correct arguments
        mock_tokenizer_from_pretrained.assert_called_once_with("invalid/model", trust_remote_code=True)
        
        # Verify log_error was called with error message
        mock_log_error.assert_called_once()
        self.assertIn("Failed to load Hugging Face model", mock_log_error.call_args[0][0])
        self.assertIn("invalid/model", mock_log_error.call_args[0][0])
        self.assertIn("Tokenizer loading failed", mock_log_error.call_args[0][0])
        
        # Verify the function returns None
        self.assertIsNone(result)

    @patch('backend.app.utils.helpers.ml_models_helper.AutoTokenizer.from_pretrained')
    @patch('backend.app.utils.helpers.ml_models_helper.AutoModelForTokenClassification.from_pretrained')
    @patch('backend.app.utils.helpers.ml_models_helper.log_error')
    def test_get_hf_ner_pipeline_model_error(self, mock_log_error, mock_model_from_pretrained, 
                                           mock_tokenizer_from_pretrained):
        """Test get_hf_ner_pipeline when model loading fails."""
        # Set up mocks
        mock_tokenizer = MagicMock()
        mock_tokenizer_from_pretrained.return_value = mock_tokenizer
        
        # Set up model loading to fail
        mock_model_from_pretrained.side_effect = Exception("Model loading failed")
        
        # Call the function
        result = get_hf_ner_pipeline("dslim/bert-base-NER")
        
        # Verify AutoTokenizer.from_pretrained was called with correct arguments
        mock_tokenizer_from_pretrained.assert_called_once_with("dslim/bert-base-NER", trust_remote_code=True)
        
        # Verify AutoModelForTokenClassification.from_pretrained was called with correct arguments
        mock_model_from_pretrained.assert_called_once_with("dslim/bert-base-NER", trust_remote_code=True)
        
        # Verify log_error was called with error message
        mock_log_error.assert_called_once()
        self.assertIn("Failed to load Hugging Face model", mock_log_error.call_args[0][0])
        self.assertIn("dslim/bert-base-NER", mock_log_error.call_args[0][0])
        self.assertIn("Model loading failed", mock_log_error.call_args[0][0])
        
        # Verify the function returns None
        self.assertIsNone(result)

    @patch('backend.app.utils.helpers.ml_models_helper.AutoTokenizer.from_pretrained')
    @patch('backend.app.utils.helpers.ml_models_helper.AutoModelForTokenClassification.from_pretrained')
    @patch('backend.app.utils.helpers.ml_models_helper.pipeline')
    @patch('backend.app.utils.helpers.ml_models_helper.log_error')
    def test_get_hf_ner_pipeline_pipeline_error(self, mock_log_error, mock_pipeline, 
                                              mock_model_from_pretrained, mock_tokenizer_from_pretrained):
        """Test get_hf_ner_pipeline when pipeline creation fails."""
        # Set up mocks
        mock_tokenizer = MagicMock()
        mock_model = MagicMock()
        
        mock_tokenizer_from_pretrained.return_value = mock_tokenizer
        mock_model_from_pretrained.return_value = mock_model
        
        # Set up pipeline creation to fail
        mock_pipeline.side_effect = Exception("Pipeline creation failed")
        
        # Call the function
        result = get_hf_ner_pipeline("dslim/bert-base-NER")
        
        # Verify pipeline was called with correct arguments
        mock_pipeline.assert_called_once_with(
            "ner",
            model=mock_model,
            tokenizer=mock_tokenizer,
            aggregation_strategy="simple"
        )
        
        # Verify log_error was called with error message
        mock_log_error.assert_called_once()
        self.assertIn("Failed to load Hugging Face model", mock_log_error.call_args[0][0])
        self.assertIn("dslim/bert-base-NER", mock_log_error.call_args[0][0])
        self.assertIn("Pipeline creation failed", mock_log_error.call_args[0][0])
        
        # Verify the function returns None
        self.assertIsNone(result)

    @patch('backend.app.utils.helpers.ml_models_helper.AutoTokenizer.from_pretrained')
    @patch('backend.app.utils.helpers.ml_models_helper.AutoModelForTokenClassification.from_pretrained')
    @patch('backend.app.utils.helpers.ml_models_helper.pipeline')
    @patch('backend.app.utils.helpers.ml_models_helper.log_info')
    def test_get_hf_ner_pipeline_local_path(self, mock_log_info, mock_pipeline, 
                                          mock_model_from_pretrained, mock_tokenizer_from_pretrained):
        """Test get_hf_ner_pipeline with a local model path."""
        # Set up mocks
        mock_tokenizer = MagicMock()
        mock_model = MagicMock()
        mock_ner_pipe = MagicMock(spec=Pipeline)
        
        mock_tokenizer_from_pretrained.return_value = mock_tokenizer
        mock_model_from_pretrained.return_value = mock_model
        mock_pipeline.return_value = mock_ner_pipe
        
        # Call the function with a local path
        local_path = "/path/to/local/model"
        result = get_hf_ner_pipeline(local_path)
        
        # Verify AutoTokenizer.from_pretrained was called with the local path
        mock_tokenizer_from_pretrained.assert_called_once_with(local_path, trust_remote_code=True)
        
        # Verify AutoModelForTokenClassification.from_pretrained was called with the local path
        mock_model_from_pretrained.assert_called_once_with(local_path, trust_remote_code=True)
        
        # Verify log_info was called with success message
        mock_log_info.assert_called_once_with(f"[OK] Successfully loaded Hugging Face model from '{local_path}'")
        
        # Verify the function returns the NER pipeline
        self.assertEqual(result, mock_ner_pipe)
