import spacy
from spacy.cli import download as spacy_download
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline
from backend.app.utils.logger import default_logger as logging


def get_spacy_model(model_name):
    """
    Load a spaCy model. If the model is not found, download it automatically.

    :param model_name: Name of the spaCy model (e.g. "nb_core_news_lg")
    :return: Loaded spaCy model.
    """
    try:
        model = spacy.load(model_name)
        logging.info(f"Loaded spaCy model '{model_name}' successfully.")
    except OSError:
        logging.info(f"spaCy model '{model_name}' not found. Downloading...")
        spacy_download(model_name)
        model = spacy.load(model_name)
        logging.info(f"Downloaded and loaded spaCy model '{model_name}'.")
    return model


def get_hf_ner_pipeline(model_name, cache_dir=None, trust_remote_code=True, aggregation_strategy="first"):
    """
    Load a Hugging Face NER pipeline using the specified model.
    If the model isn't cached, it will be downloaded.

    :param model_name: Hugging Face model identifier (e.g., "kushtrim/norbert3-large-ner")
    :param cache_dir: Optional directory to cache the model.
    :param trust_remote_code: Whether to trust remote code (default True).
    :param aggregation_strategy: Aggregation strategy for the pipeline (default "first").
    :return: A Hugging Face NER pipeline.
    """
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir=cache_dir)
        tokenizer.model_max_length = 512  # Avoid issues with long text
        model = AutoModelForTokenClassification.from_pretrained(
            model_name, cache_dir=cache_dir, trust_remote_code=trust_remote_code
        )

        ner_pipe = pipeline("ner", model=model, tokenizer=tokenizer, aggregation_strategy=aggregation_strategy)
        logging.info(f"Loaded Hugging Face model '{model_name}' successfully!")
    except Exception as e:
        logging.error(f"Failed to load Hugging Face model '{model_name}': {e}")
        ner_pipe = None
    return ner_pipe
