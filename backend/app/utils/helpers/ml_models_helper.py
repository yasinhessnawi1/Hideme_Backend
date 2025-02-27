import spacy
from spacy.cli import download as spacy_download
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline

from backend.app.configs.presidio_config import LOCAL_HF_MODEL_PATH
from backend.app.utils.logger import default_logger as logging


def get_spacy_model(model_name):
    """
    Load a spaCy model. If the model is not found, download it automatically.

    :param model_name: Name of the spaCy model (e.g. "nb_core_news_lg")
    :return: Loaded spaCy model.
    """
    try:
        model = spacy.load(model_name)
        logging.info(f"✅ Loaded spaCy model '{model_name}' successfully.")
    except OSError:
        logging.info(f"❌ spaCy model '{model_name}' not found. Downloading...")
        spacy_download(model_name)
        model = spacy.load(model_name)
        logging.info(f"❌ Downloaded and loaded spaCy model '{model_name}'.")
    return model


def get_hf_ner_pipeline(model_path=LOCAL_HF_MODEL_PATH, aggregation_strategy="simple"):
    """
    Load a Hugging Face NER pipeline using the local model with custom code execution enabled.

    :param model_path: Path to the local Hugging Face model (from presidio_config.py)
    :param aggregation_strategy: Aggregation strategy for the pipeline (default "simple").
    :return: A Hugging Face NER pipeline.
    """
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = AutoModelForTokenClassification.from_pretrained(model_path, trust_remote_code=True)

        ner_pipe = pipeline("ner", model=model, tokenizer=tokenizer, aggregation_strategy=aggregation_strategy)

        logging.info(f"✅ Successfully loaded Hugging Face model from '{model_path}'!")
    except Exception as e:
        logging.error(f"❌ Failed to load Hugging Face model from '{model_path}': {e}")
        ner_pipe = None
    return ner_pipe
