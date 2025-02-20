import spacy
import logging
import os

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
