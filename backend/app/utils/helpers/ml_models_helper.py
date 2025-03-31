"""
Helper functions for loading and using ML models.
"""
import spacy
from spacy.cli import download as spacy_download
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline
from typing import Optional, Any

from backend.app.utils.logging.logger import log_info, log_error, log_warning


def get_spacy_model(model_name: str) -> Any:
    """
    Load a spaCy model, downloading it if not available.

    Args:
        model_name: Name of the spaCy model to load

    Returns:
        Loaded spaCy model
    """
    try:
        model = spacy.load(model_name)
        log_info(f"[OK] Loaded spaCy model '{model_name}' successfully")
    except OSError:
        log_warning(f"[OK] spaCy model '{model_name}' not found. Downloading...")
        spacy_download(model_name)
        model = spacy.load(model_name)
        log_info(f"[OK] Downloaded and loaded spaCy model '{model_name}'")
    return model


def get_hf_ner_pipeline(model_path: str, aggregation_strategy: str = "simple") -> Optional[Any]:
    """
    Load a Hugging Face NER pipeline from a local or remote model.

    Args:
        model_path: Path or name of the Hugging Face model
        aggregation_strategy: Token aggregation strategy (default: "simple")

    Returns:
        NER pipeline or None if loading fails
    """
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = AutoModelForTokenClassification.from_pretrained(model_path, trust_remote_code=True)

        ner_pipe = pipeline(
            "ner",
            model=model,
            tokenizer=tokenizer,
            aggregation_strategy=aggregation_strategy
        )

        log_info(f"[OK] Successfully loaded Hugging Face model from '{model_path}'")
        return ner_pipe # Return the pipeline
    except Exception as e:
        log_error(f"[ERROR] Failed to load Hugging Face model from '{model_path}': {e}")
        return None