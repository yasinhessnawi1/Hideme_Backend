"""
Helper functions for loading and using ML models.

This module provides utility functions for:
- Loading spaCy models, downloading them if they are not already available locally.
- Creating a Hugging Face Named Entity Recognition (NER) pipeline from a specified model path,
  which may be a local path or a remote model identifier.

The functions include logging to help trace successes, warnings, and errors during model loading.
"""

import spacy
from spacy.cli import download as spacy_download
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline
from typing import Optional, Any

from backend.app.utils.logging.logger import log_info, log_error, log_warning


def get_spacy_model(model_name: str) -> Any:
    """
    Load a spaCy model, downloading it if it is not already available locally.

    Args:
        model_name (str): Name of the spaCy model to load.

    Returns:
        Any: The loaded spaCy model.
    """
    try:
        # Attempt to load the specified spaCy model.
        model = spacy.load(model_name)
        # Log successful model loading.
        log_info(f"[OK] Loaded spaCy model '{model_name}' successfully")
    except OSError:
        # Log warning that the model was not found locally.
        log_warning(f"[OK] spaCy model '{model_name}' not found. Downloading...")
        # Download the spaCy model.
        spacy_download(model_name)
        # Load the downloaded spaCy model.
        model = spacy.load(model_name)
        # Log that the model has been downloaded and loaded.
        log_info(f"[OK] Downloaded and loaded spaCy model '{model_name}'")
    # Return the loaded model.
    return model


def get_hf_ner_pipeline(
    model_path: str, aggregation_strategy: str = "simple"
) -> Optional[Any]:
    """
    Load a Hugging Face Named Entity Recognition (NER) pipeline from a local or remote model.

    Args:
        model_path (str): Path or name of the Hugging Face model.
        aggregation_strategy (str, optional): Token aggregation strategy (default is "simple").

    Returns:
        Optional[Any]: The NER pipeline if loading is successful, or None if loading fails.
    """
    try:
        # Load the tokenizer for the specified model with trust for remote code.
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        # Load the model for token classification with trust for remote code.
        model = AutoModelForTokenClassification.from_pretrained(
            model_path, trust_remote_code=True
        )
        # Initialize the NER pipeline with the model, tokenizer, and aggregation strategy.
        ner_pipe = pipeline(
            "ner",
            model=model,
            tokenizer=tokenizer,
            aggregation_strategy=aggregation_strategy,
        )
        # Log that the Hugging Face model was successfully loaded.
        log_info(f"[OK] Successfully loaded Hugging Face model from '{model_path}'")
        # Return the initialized NER pipeline.
        return ner_pipe
    except Exception as e:
        # Log an error message if model loading fails.
        log_error(f"[ERROR] Failed to load Hugging Face model from '{model_path}': {e}")
        # Return None to signal that the NER pipeline could not be created.
        return None
