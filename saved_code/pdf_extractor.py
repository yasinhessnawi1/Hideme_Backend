import logging
import pymupdf
from presidio_analyzer import RecognizerResult

from backend.app import configs


class PDFExtractor:
    def __init__(self, pdf_input):
        """
        Initialize PDFExtractor.
        ✅ Accepts EITHER a file path OR a PyMuPDF document.
        """
        # If file path is given
        if isinstance(pdf_input, str):
            self.pdf_document = pymupdf.open(pdf_input)

        # If PyMuPDF document is given
        elif isinstance(pdf_input, pymupdf.Document):
            self.pdf_document = pdf_input

        else:
            raise ValueError("Invalid input! Expected file path or PyMuPDF Document.")

        # Use Presidio Analyzer and NLP engine from configs
        self.analyzer = configs.analyzer
        # spaCy NLP model
        self.nlp = configs.nlp
        # Custom NER pipeline
        self.ner_pipeline = configs.ner_pipeline
        self.anonymizer = configs.anonymizer

    def detect_sensitive_data(self, text):
        """
        Detect and anonymize sensitive entities in text.
        """

        # Fetch available recognizers
        available_recognizers = self.analyzer.registry.get_supported_entities()

        # Select only available recognizers (Ensures no mismatch)
        requested_entities = [
            entity
            for entity in [
                "US_SSN", "NO_FODSELSNUMMER", "NO_ADDRESS", "SG_NRIC_FIN",
                "AU_MEDICARE", "US_ITIN", "CREDIT_CARD", "PHONE_NUMBER",
                "IN_PASSPORT", "LOCATION", "UK_NHS", "UK_NINO", "IN_VOTER",
                "US_DRIVER_LICENSE", "IN_AADHAAR", "AU_ABN", "MEDICAL_LICENSE",
                "AU_ACN", "ID", "NO_PHONE_NUMBER", "IN_VEHICLE_REGISTRATION",
                "AU_TFN", "US_PASSPORT", "PERSON", "AGE", "EMAIL_ADDRESS",
                "IP_ADDRESS", "EMAIL", "CRYPTO", "NRP", "URL", "DATE_TIME",
                "US_BANK_NUMBER", "ORGANIZATION", "IBAN_CODE", "IN_PAN"
            ]
            if entity in available_recognizers
        ]

        if not requested_entities:
            logging.warning("⚠️ No valid recognizers found for the requested entities. Skipping analysis.")
            presidio_results = []
        else:
            presidio_results = self.analyzer.analyze(
                text=text, language="nb", entities=requested_entities
            )

        # Run Custom NER Pipeline
        try:
            ner_results = self.ner_pipeline(text)
        except Exception as e:
            logging.error(f"❌ Kushtrim's NER model failed: {e}")
            ner_results = []

        # Convert NER results into Presidio format
        custom_ner_results = [
            RecognizerResult(
                entity_type=entity["entity_group"],
                start=entity["start"],
                end=entity["end"],
                score=entity["score"]
            )
            for entity in ner_results
            if entity["entity_group"] in ["PER", "LOC", "DATE", "MISC", "GPE", "PROD", "EVT", "DRV"]
        ]

        # Combine both detection results
        combined_results = presidio_results + custom_ner_results

        # Anonymize sensitive text
        anonymized_text = self.anonymizer.anonymize(text, combined_results).text

        return anonymized_text, combined_results

    def extract_data(self):
        """
        Extracts text line by line from a PDF, detects sensitive entities, and returns JSON.
        """
        extracted_data = {"pages": []}

        try:
            for page_num, page in enumerate(self.pdf_document):
                logging.info(f"📄 Processing page {page_num + 1}")
                page_data = {"text": []}

                # Extract text block-by-block
                blocks = page.get_text("dict")["blocks"]
                for block in blocks:
                    for line in block.get("lines", []):
                        # Join text spans within a line
                        line_text = " ".join(span["text"].strip() for span in line["spans"] if span["text"].strip())

                        if not line_text:
                            continue  # Skip empty lines

                        # Detect sensitive data for each line
                        anonymized_text, detected_entities = self.detect_sensitive_data(line_text)

                        # Format entity data
                        entity_dicts = [
                            {
                                "entity_type": e.entity_type,
                                "start": e.start,
                                "end": e.end,
                                "score": float(e.score)
                            }
                            for e in detected_entities if e.score > 0.5
                        ]

                        # Store the processed line
                        text_data = {
                            "original_text": line_text,
                            "anonymized_text": anonymized_text,
                            "entities": entity_dicts
                        }
                        page_data["text"].append(text_data)

                extracted_data["pages"].append(page_data)

        except Exception as e:
            logging.error(f"❌ Failed to process PDF: {e}")
            return {}

        logging.info("✅ Successfully extracted data from PDF.")
        # Now directly returning data, NOT saving a JSON file.
        return extracted_data
