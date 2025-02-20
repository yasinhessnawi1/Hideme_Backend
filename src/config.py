import spacy
import logging
import os

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