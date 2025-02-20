import spacy
import logging
import os

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import NlpEngineProvider, NerModelConfiguration
from presidio_anonymizer import AnonymizerEngine
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline

# Ensure logs directory exists
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Define log file path
LOG_FILE = os.path.join(LOG_DIR, "app.log")

# Configure logging to use UTF-8 encoding
logging.basicConfig(
    # Log all levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        # Use UTF-8 for log file
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        # Print logs to console
        logging.StreamHandler()
    ]
)

# Load the Norwegian spaCy Model
try:
    nlp = spacy.load("nb_core_news_lg")
    logging.info("Loaded Norwegian spaCy model successfully!")
except OSError:
    logging.error("Norwegian spaCy model is missing! Run: python -m spacy download nb_core_news_lg")
    raise

# Define the Local NER Model Path
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../models/local_kushtrim_norbert3_large_ner")

if not os.path.exists(MODEL_DIR):
    logging.error(f"❌ Model directory not found: {MODEL_DIR}")
    raise FileNotFoundError(f"Model directory not found: {MODEL_DIR}")

# Load Tokenizer and Model
try:
    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR, local_files_only=True)
    model = AutoModelForTokenClassification.from_pretrained(
        MODEL_DIR,
        local_files_only=True,
        trust_remote_code=True
    )
    logging.info("✅ Local NER model loaded successfully!")
except Exception as e:
    logging.error(f"❌ Failed to load local NER model: {e}")
    raise

# Create NER Pipeline
ner_pipeline = pipeline("ner", model=model, tokenizer=tokenizer, aggregation_strategy="first")

# Configure Presidio to use Norwegian (`nb`)
nlp_configuration = {
    "nlp_engine_name": "spacy",
    # Norwegian language support
    "models": [{"lang_code": "nb", "model_name": "nb_core_news_lg"}]
}

# Initialize NLP Engine
provider = NlpEngineProvider()
provider.nlp_configuration = nlp_configuration
spacy_nlp_engine = provider.create_engine()

# Map `GPE_LOC` to `LOCATION`
ner_model_config = NerModelConfiguration()
ner_model_config.model_to_presidio_entity_mapping["GPE_LOC"] = "LOCATION"

# Create Presidio Analyzer and Anonymizer
analyzer = AnalyzerEngine(nlp_engine=spacy_nlp_engine, supported_languages=["nb"])
anonymizer = AnonymizerEngine()

# Norwegian Fødselsnummer (National ID)
fodselsnummer_pattern = Pattern(
    name="Fodselsnummer Pattern",
    # Matches 11-digit Norwegian National ID
    regex=r"\b\d{6}\s?\d{5}\b",
    score=0.9
)
fodselsnummer_recognizer = PatternRecognizer(
    supported_entity="NO_FODSELSNUMMER",
    patterns=[fodselsnummer_pattern],
    supported_language="nb"
)

phone_number_pattern = Pattern(
    name="Norwegian Phone Number Pattern",
    regex=r"\b(?:\+47\s?)?(\d{2}\s?\d{2}\s?\d{2}\s?\d{2})\b",
    score=0.95
)
phone_number_recognizer = PatternRecognizer(
    supported_entity="NO_PHONE_NUMBER",
    patterns=[phone_number_pattern],
    supported_language="nb"
)

# Norwegian Address
address_pattern = Pattern(
    name="Norwegian Address Pattern",
    regex=r"(\b(?:[A-Za-zÆØÅæøå]+\s){1,4}\d{1,4}(?:,\s)?\d{4}\s[A-Za-zÆØÅæøå]+)|"
          r"(\bPostboks\s?\d{1,5}(?:,\s)?\d{4}\s[A-Za-zÆØÅæøå]+)|"
          r"(\b\d{4}\s[A-Za-zÆØÅæøå]+\b)|"
          r"(\b[A-Za-zÆØÅæøå]+\s\d{1,4},?\s?\d{4}\s[A-Za-zÆØÅæøå]+\b)",
    score=0.98
)
address_recognizer = PatternRecognizer(
    supported_entity="NO_ADDRESS",
    patterns=[address_pattern],
    supported_language="nb"
)

# Register Custom Recognizers in Presidio
analyzer.registry.add_recognizer(fodselsnummer_recognizer)
analyzer.registry.add_recognizer(phone_number_recognizer)
analyzer.registry.add_recognizer(address_recognizer)

logging.info("✅ Added Norwegian custom recognizers to Presidio!")

print("✅ Presidio now supports Norwegian!")
