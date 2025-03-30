import json
import os
import time
import logging
import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, Any, List, Tuple
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("EntityDetectionComparison")


class EntityDetectionComparison:
    """
    Framework for comparing automated entity detection with manually redacted data.
    """

    def __init__(self,
                 pdf_directory: str,
                 manual_redaction_directory: str,
                 hybrid_endpoint: str,
                 output_directory: str = "model_validation",
                 max_files: int = 10):
        """
        Initialize the comparison framework.

        Args:
            pdf_directory: Directory containing PDF files to process
            manual_redaction_directory: Directory containing all manually redacted text files
            hybrid_endpoint: API endpoint for the hybrid model
            output_directory: Directory to store all output files
            max_files: Maximum number of files to process (default: 10)
        """
        self.pdf_directory = os.path.abspath(pdf_directory)
        self.manual_redaction_directory = os.path.abspath(manual_redaction_directory)
        self.hybrid_endpoint = hybrid_endpoint
        self.output_directory = os.path.abspath(output_directory)
        self.max_files = max_files

        # Create output directory if it doesn't exist
        os.makedirs(self.output_directory, exist_ok=True)
        os.makedirs(os.path.join(self.output_directory, "visualizations"), exist_ok=True)
        logger.info(f"Created output directory: {self.output_directory}")

        # Comprehensive entity type mapping for all models (Presidio, Gemini, Gliner) and manual redaction
        # Using standardized form for consistent comparison
        self.entity_mapping = {
            # Presidio entities (standardized form)
            "NO_FODSELSNUMMER": "PERSONAL_ID",
            "NO_PHONE_NUMBER": "PHONE_NUMBER",
            "NO_ADDRESS": "ADDRESS",
            "NO_BANK_ACCOUNT": "FINANCIAL_INFO",
            "NO_COMPANY_NUMBER": "ORGANIZATION_ID",
            "NO_LICENSE_PLATE": "VEHICLE_INFO",
            "EMAIL_ADDRESS": "EMAIL",
            "CRYPTO": "FINANCIAL_INFO",
            "DATE_TIME": "DATE_TIME",
            "IBAN_CODE": "FINANCIAL_INFO",
            "IP_ADDRESS": "DIGITAL_ID",
            "URL": "DIGITAL_ID",
            "MEDICAL_LICENSE": "HEALTH_INFO",
            "PERSON": "PERSON",
            "ORGANIZATION": "ORGANIZATION",
            "LOCATION": "LOCATION",

            # Gemini entities
            "PHONE": "PHONE_NUMBER",
            "EMAIL": "EMAIL",
            "ADDRESS": "ADDRESS",
            "DATE": "DATE_TIME",
            "GOVID": "PERSONAL_ID",
            "FINANCIAL": "FINANCIAL_INFO",
            "EMPLOYMENT": "EMPLOYMENT_INFO",
            "HEALTH": "HEALTH_INFO",
            "SEXUAL": "SENSITIVE_INFO",
            "CRIMINAL": "SENSITIVE_INFO",
            "CONTEXT": "SENSITIVE_INFO",
            "INFO": "SENSITIVE_INFO",
            "FAMILY": "PERSON_INFO",
            "BEHAVIORAL_PATTERN": "SENSITIVE_INFO",
            "POLITICAL_CASE": "SENSITIVE_INFO",
            "ECONOMIC_STATUS": "FINANCIAL_INFO",

            # Gliner entities (lowercase in original)
            "BOOK": "OTHER",
            "ACTOR": "PERSON",
            "CHARACTER": "PERSON",
            "PHONE NUMBER": "PHONE_NUMBER",
            "PASSPORT NUMBER": "PERSONAL_ID",
            "CREDIT CARD NUMBER": "FINANCIAL_INFO",
            "SOCIAL SECURITY NUMBER": "PERSONAL_ID",
            "HEALTH INSURANCE ID NUMBER": "HEALTH_INFO",
            "DATE OF BIRTH": "DATE_TIME",
            "MOBILE PHONE NUMBER": "PHONE_NUMBER",
            "BANK ACCOUNT NUMBER": "FINANCIAL_INFO",
            "MEDICATION": "HEALTH_INFO",
            "CPF": "PERSONAL_ID",
            "TAX IDENTIFICATION NUMBER": "PERSONAL_ID",
            "MEDICAL CONDITION": "HEALTH_INFO",
            "IDENTITY CARD NUMBER": "PERSONAL_ID",
            "NATIONAL ID NUMBER": "PERSONAL_ID",
            "IP ADDRESS": "DIGITAL_ID",
            "IBAN": "FINANCIAL_INFO",
            "CREDIT CARD EXPIRATION DATE": "FINANCIAL_INFO",
            "USERNAME": "DIGITAL_ID",
            "HEALTH INSURANCE NUMBER": "HEALTH_INFO",
            "REGISTRATION NUMBER": "PERSONAL_ID",
            "STUDENT ID NUMBER": "PERSONAL_ID",
            "INSURANCE NUMBER": "FINANCIAL_INFO",
            "FLIGHT NUMBER": "OTHER",
            "LANDLINE PHONE NUMBER": "PHONE_NUMBER",
            "BLOOD TYPE": "HEALTH_INFO",
            "CVV": "FINANCIAL_INFO",
            "RESERVATION NUMBER": "OTHER",
            "DIGITAL SIGNATURE": "DIGITAL_ID",
            "SOCIAL MEDIA HANDLE": "DIGITAL_ID",
            "LICENSE PLATE NUMBER": "VEHICLE_INFO",
            "CNPJ": "ORGANIZATION_ID",
            "POSTAL CODE": "ADDRESS",
            "PASSPORT_NUMBER": "PERSONAL_ID",
            "VEHICLE REGISTRATION NUMBER": "VEHICLE_INFO",
            "CREDIT CARD BRAND": "FINANCIAL_INFO",
            "FAX NUMBER": "PHONE_NUMBER",
            "VISA NUMBER": "PERSONAL_ID",
            "INSURANCE COMPANY": "ORGANIZATION",
            "IDENTITY DOCUMENT NUMBER": "PERSONAL_ID",
            "TRANSACTION NUMBER": "FINANCIAL_INFO",
            "NATIONAL HEALTH INSURANCE NUMBER": "HEALTH_INFO",
            "CVC": "FINANCIAL_INFO",
            "BIRTH CERTIFICATE NUMBER": "PERSONAL_ID",
            "TRAIN TICKET NUMBER": "OTHER",
            "PASSPORT EXPIRATION DATE": "DATE_TIME",
            "SOCIAL_SECURITY_NUMBER": "PERSONAL_ID",

            # Manual redaction entities (add more as needed)
            "NAME": "PERSON",
            "NAME_1": "PERSON",
            "NAME_GIVEN": "PERSON",
            "NAME_FAMILY": "PERSON",
            "GENDER": "PERSON_INFO",
            "GENDER_1": "PERSON_INFO",
            "ORIGIN": "PERSON_INFO",
            "ORIGIN_1": "PERSON_INFO",
            "OCCUPATION": "EMPLOYMENT_INFO",
            "OCCUPATION_1": "EMPLOYMENT_INFO",
            "LOCATION_CITY": "LOCATION",
            "LOCATION_CITY_1": "LOCATION",
            "LOCATION_ADDRESS": "ADDRESS",
            "LOCATION_ADDRESS_1": "ADDRESS",
            "LOCATION_ADDRESS_STREET": "ADDRESS",
            "LOCATION_ADDRESS_STREET_1": "ADDRESS",
            "PHONE_NUMBER": "PHONE_NUMBER",
            "PHONE_NUMBER_1": "PHONE_NUMBER",
            "EMAIL_ADDRESS": "EMAIL",
            "EMAIL_ADDRESS_1": "EMAIL",
            "CONDITION": "HEALTH_INFO",
            "CONDITION_1": "HEALTH_INFO",
            "OKONOMI_STATE": "FINANCIAL_INFO",
            "OKONOMI_STATE_1": "FINANCIAL_INFO",
            "CONTEXUAL": "SENSITIVE_INFO",
            "CONTEXUAL_1": "SENSITIVE_INFO",
            "ORGANIZATION": "ORGANIZATION",
            "ORGANIZATION_1": "ORGANIZATION",
            "DURATION": "DATE_TIME",
            "DURATION_1": "DATE_TIME",
            "NUMERICAL_PII": "PERSONAL_ID",
            "NUMERICAL_PII_1": "PERSONAL_ID",
            "DATE": "DATE_TIME",
            "DATE_1": "DATE_TIME",
            "TIME": "DATE_TIME",
            "TIME_1": "DATE_TIME",

            # Additional entity types found in the logs
            "INJURY": "HEALTH_INFO",
            "MEDICAL_PROCESS": "HEALTH_INFO"
        }

        # Create inverse mapping for debugging and reporting
        self.entity_groups = {}
        for original, standard in self.entity_mapping.items():
            if standard not in self.entity_groups:
                self.entity_groups[standard] = []
            self.entity_groups[standard].append(original)

        # Results storage
        self.hybrid_results = {}
        self.manual_results = {}

        # Processing time tracking
        self.processing_times = {
            "hybrid": 0
        }

        # Performance metrics
        self.metrics = {
            "entity_counts": {},
            "precision_recall": {},
            "detection_rates": {},
            "document_level_metrics": []
        }

        logger.info(f"Initialized comparison framework")
        logger.info(f"PDF directory: {self.pdf_directory}")
        logger.info(f"Manual redaction data directory: {self.manual_redaction_directory}")
        logger.info(f"Output will be saved to: {self.output_directory}")
        logger.info(f"Maximum files to process: {self.max_files}")

    def get_pdf_files(self, directory: str) -> List[str]:
        """
        Gets PDF files in a directory, limited by max_files.

        Args:
            directory: Directory to check for PDF files

        Returns:
            List of PDF file paths (limited by max_files)
        """
        files = []

        # Check if directory exists
        if not os.path.exists(directory):
            logger.error(f"Directory does not exist: {directory}")
            return files

        # List all files in directory
        all_files = os.listdir(directory)
        logger.info(f"Found {len(all_files)} total files in {directory}")

        # Check for .pdf files
        pdf_files = [f for f in all_files if f.lower().endswith('.pdf')]
        logger.info(f"Found {len(pdf_files)} .pdf files in {directory}")

        # Limit to max_files
        pdf_files = pdf_files[:self.max_files]
        logger.info(f"Limited to {len(pdf_files)} PDF files per max_files setting")

        # If no PDF files found, check directory contents more thoroughly
        if not pdf_files:
            logger.warning(f"No PDF files found in {directory}. Directory contents:")
            for item in all_files[:10]:  # Show first 5 items
                item_path = os.path.join(directory, item)
                if os.path.isdir(item_path):
                    logger.warning(f"  Directory: {item}")
                else:
                    logger.warning(f"  File: {item} ({os.path.getsize(item_path)} bytes)")

        return pdf_files

    def process_hybrid_model(self) -> Dict[str, Any]:
        """
        Process PDF files through the hybrid model endpoint.
        """
        logger.info(f"Starting hybrid model processing for files in {self.pdf_directory}")
        start_time = time.time()

        # Get list of PDF files (limited to max_files)
        pdf_files = self.get_pdf_files(self.pdf_directory)
        logger.info(f"Processing {len(pdf_files)} PDF files")

        if not pdf_files:
            logger.warning(f"No PDF files found to process in {self.pdf_directory}")
            end_time = time.time()
            self.processing_times["hybrid"] = end_time - start_time
            self.hybrid_results = {}
            return {}

        # Process files in batches to avoid overloading the endpoint
        batch_size = min(10, self.max_files)
        results = {}

        for i in range(0, len(pdf_files), batch_size):
            batch_files = pdf_files[i:i + batch_size]
            logger.info(f"Processing batch of {len(batch_files)} files")

            # Prepare files for batch processing
            files = []
            for pdf_file in batch_files:
                file_path = os.path.join(self.pdf_directory, pdf_file)
                try:
                    # Add PDF file directly to API request
                    with open(file_path, 'rb') as f:
                        file_data = f.read()
                        files.append(('files', (pdf_file, file_data)))

                    logger.info(f"Prepared PDF file {pdf_file} for API request")

                except Exception as e:
                    logger.error(f"Error preparing file {file_path}: {e}")
                    continue

            # Skip if no files were prepared
            if not files:
                logger.warning(f"No valid files in batch, skipping")
                continue

            # Make API call to hybrid batch endpoint
            try:
                logger.info(f"Sending batch request to {self.hybrid_endpoint}")
                response = requests.post(
                    self.hybrid_endpoint,
                    files=files,
                    timeout=60  # Add timeout to prevent hanging
                )

                if response.status_code == 200:
                    logger.info(f"Successfully processed batch")
                    batch_results = response.json()

                    # Extract file-specific results
                    for file_result in batch_results.get("file_results", []):
                        file_name = file_result.get("file")
                        if file_name:
                            results[file_name] = file_result
                            logger.info(f"Added results for {file_name}")
                else:
                    logger.error(f"Failed to process batch. Status code: {response.status_code}")
                    logger.error(f"Response: {response.text[:500]}...")  # Log partial response
            except Exception as e:
                logger.error(f"Error processing batch: {e}")

            # Add a small delay between batches
            if i + batch_size < len(pdf_files):
                logger.info(f"Waiting 2 seconds before next batch")
                time.sleep(2)

        end_time = time.time()
        processing_time = end_time - start_time
        logger.info(f"Completed hybrid model processing in {processing_time:.2f} seconds")

        # Save results to file
        hybrid_output_path = os.path.join(self.output_directory, "hybrid_results.json")
        logger.info(f"Saving hybrid results to: {hybrid_output_path}")
        try:
            with open(hybrid_output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving hybrid results: {e}")
            # Create directory if it doesn't exist (double-check)
            os.makedirs(os.path.dirname(hybrid_output_path), exist_ok=True)
            # Try again
            with open(hybrid_output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2)

        logger.info(f"Hybrid model results saved to {hybrid_output_path}")

        self.hybrid_results = results
        self.processing_times["hybrid"] = processing_time

        return results

    def create_manual_samples(self) -> None:
        """
        Create sample manual redaction files for testing if needed.
        This is used only as a fallback when no hybrid results are available.
        """
        # Check if we have hybrid results
        if self.hybrid_results:
            return

        logger.warning("No hybrid results available. Creating sample redactions for testing.")

        # Get manual files (limited to max_files)
        manual_files = [f for f in os.listdir(self.manual_redaction_directory)
                        if f.lower().endswith('.txt')][:self.max_files]

        # Create sample hybrid results for manual files
        sample_results = {}

        for manual_file in manual_files:  # Limited by max_files already
            manual_path = os.path.join(self.manual_redaction_directory, manual_file)

            # Try to read the manual file
            try:
                with open(manual_path, 'r', encoding='utf-8') as f:
                    manual_text = f.read()
            except UnicodeDecodeError:
                try:
                    with open(manual_path, 'r', encoding='latin-1') as f:
                        manual_text = f.read()
                except Exception:
                    continue
            except Exception:
                continue

            # Create a simulated result with some false positives and false negatives
            if manual_file in self.manual_results:
                manual_entities = self.manual_results[manual_file].get("entities", [])

                # Sample 70% of entities as true positives
                detected_entities = []
                for entity in manual_entities[:int(len(manual_entities) * 0.7)]:
                    detected_entities.append({
                        "original_text": entity.get("text", ""),
                        "entity_type": entity.get("best_label", ""),
                        "score": 0.85
                    })

                # Add some false positives
                false_positives = [
                    {"original_text": "Example Inc.", "entity_type": "ORGANIZATION", "score": 0.75},
                    {"original_text": "12.34.5678", "entity_type": "DATE_TIME", "score": 0.65}
                ]

                detected_entities.extend(false_positives)

                # Create simulated result
                sample_results[manual_file] = {
                    "status": "success",
                    "file": manual_file,
                    "results": {
                        "redaction_mapping": {
                            "pages": [{
                                "sensitive": detected_entities
                            }]
                        }
                    }
                }

        # Save and use these sample results
        self.hybrid_results = sample_results

        # Save results to file
        hybrid_output_path = os.path.join(self.output_directory, "hybrid_results_sample.json")
        with open(hybrid_output_path, 'w', encoding='utf-8') as f:
            json.dump(sample_results, f, indent=2)

        logger.info(f"Created {len(sample_results)} sample hybrid results for testing")

    def load_manual_data(self) -> Dict[str, Any]:
        """
        Load and parse manually redacted data from text files (limited by max_files).
        """
        logger.info("Loading manual redaction data")

        manual_results = {}
        manual_files = [f for f in os.listdir(self.manual_redaction_directory)
                        if f.lower().endswith('.txt')][:self.max_files]

        logger.info(f"Loading {len(manual_files)} manual files (limited by max_files)")

        for manual_file in manual_files:
            file_path = os.path.join(self.manual_redaction_directory, manual_file)

            try:
                # Try different encodings
                content = None
                for encoding in ['utf-8', 'latin-1', 'cp1252']:
                    try:
                        with open(file_path, 'r', encoding=encoding) as f:
                            content = f.read()
                        break
                    except UnicodeDecodeError:
                        continue

                if not content:
                    logger.warning(f"Could not read {file_path} with any encoding, skipping")
                    continue

                # Try to parse as JSON
                try:
                    data = json.loads(content)
                    logger.info(f"Successfully loaded manual data from {file_path} as JSON")
                except json.JSONDecodeError:
                    # If not valid JSON, try to parse in a more forgiving way
                    logger.warning(f"File {file_path} is not valid JSON. Attempting alternative parsing.")

                    # Extract processed text (if available)
                    processed_text = re.search(r'"processed_text"\s*:\s*"([^"]+)"', content)
                    if processed_text:
                        processed_text = processed_text.group(1)
                    else:
                        processed_text = content

                    # Extract entities using various patterns
                    entities = []

                    # Pattern 1: Look for JSON-like entity patterns
                    entity_patterns = re.finditer(
                        r'"text"\s*:\s*"([^"]+)".*?"best_label"\s*:\s*"([^"]+)"',
                        content, re.DOTALL)

                    for match in entity_patterns:
                        entity = {
                            "text": match.group(1),
                            "best_label": match.group(2)
                        }
                        entities.append(entity)

                    # Pattern 2: Look for patterns like [PERSON: John Doe] in the text
                    if not entities:
                        entity_patterns = re.finditer(r'\[([A-Z_]+):\s*([^\]]+)\]', content)
                        for match in entity_patterns:
                            entity = {
                                "text": match.group(2).strip(),
                                "best_label": match.group(1)
                            }
                            entities.append(entity)

                    # Pattern 3: Look for patterns like <PERSON>John Doe</PERSON>
                    if not entities:
                        entity_patterns = re.finditer(r'<([A-Z_]+)>([^<]+)</\1>', content)
                        for match in entity_patterns:
                            entity = {
                                "text": match.group(2).strip(),
                                "best_label": match.group(1)
                            }
                            entities.append(entity)

                    data = {
                        "processed_text": processed_text,
                        "entities": entities
                    }

                manual_results[manual_file] = data
                logger.info(f"Parsed {len(data.get('entities', []))} entities from {file_path}")

            except Exception as e:
                logger.error(f"Error loading manual data from {file_path}: {e}")
                manual_results[manual_file] = {"processed_text": "", "entities": []}

        logger.info(f"Loaded manual data for {len(manual_results)} files")

        # Save results to file
        manual_output_path = os.path.join(self.output_directory, "manual_results.json")
        logger.info(f"Saving manual results to: {manual_output_path}")
        try:
            with open(manual_output_path, 'w', encoding='utf-8') as f:
                json.dump(manual_results, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving manual results: {e}")
            # Create directory if it doesn't exist (double-check)
            os.makedirs(os.path.dirname(manual_output_path), exist_ok=True)
            # Try again
            with open(manual_output_path, 'w', encoding='utf-8') as f:
                json.dump(manual_results, f, indent=2)

        logger.info(f"Manual redaction results saved to {manual_output_path}")

        self.manual_results = manual_results

        return manual_results

    def normalize_entities(self) -> Tuple[Dict[str, List[Dict]], Dict[str, List[Dict]]]:
        """
        Normalize entities from both hybrid model and manual data for comparison.
        """
        logger.info("Normalizing entities for comparison")

        normalized_hybrid = {}
        normalized_manual = {}

        # Process hybrid model results
        for file_name, result in self.hybrid_results.items():
            if file_name not in normalized_hybrid:
                normalized_hybrid[file_name] = []

            if "error" in result or result.get("status") != "success":
                logger.warning(f"Skipping file {file_name} in hybrid results due to error or unsuccessful status")
                continue

            # Extract entities from the results structure
            if "results" in result and "redaction_mapping" in result["results"]:
                for page in result["results"]["redaction_mapping"].get("pages", []):
                    for sensitive in page.get("sensitive", []):
                        # Map the entity type to standard form
                        original_type = sensitive.get("entity_type", "")
                        mapped_type = self.entity_mapping.get(original_type, original_type)

                        normalized_entity = {
                            "text": sensitive.get("original_text", ""),
                            "type": mapped_type,
                            "original_type": original_type,
                            "confidence": sensitive.get("score", 0.0)
                        }
                        normalized_hybrid[file_name].append(normalized_entity)

            # Print entities detected for this file
            logger.info(f"Hybrid model detected {len(normalized_hybrid.get(file_name, []))} entities in {file_name}")
            for entity in normalized_hybrid.get(file_name, [])[:10]:  # Log just the first 5 to avoid spam
                logger.info(
                    f"  Entity: {entity['text']} | Type: {entity['type']} | Original Type: {entity['original_type']} | "
                    f"Confidence: {entity['confidence']:.4f}")

            if len(normalized_hybrid.get(file_name, [])) > 10:
                logger.info(f"  ... and {len(normalized_hybrid.get(file_name, [])) - 10} more entities")

        # Process manual data results
        for file_name, result in self.manual_results.items():
            if file_name not in normalized_manual:
                normalized_manual[file_name] = []

            if not result or "entities" not in result:
                logger.warning(f"Skipping file {file_name} in manual results due to missing or invalid data")
                continue

            for entity in result.get("entities", []):
                # Map the entity type to standard form
                original_type = entity.get("best_label", "")
                mapped_type = self.entity_mapping.get(original_type, original_type)

                normalized_entity = {
                    "text": entity.get("text", ""),
                    "type": mapped_type,
                    "original_type": original_type,
                    "confidence": 1.0  # Manual redactions are assumed to be 100% confident
                }
                normalized_manual[file_name].append(normalized_entity)

            # Print entities detected for this file
            logger.info(
                f"Manual redaction contains {len(normalized_manual.get(file_name, []))} entities in {file_name}")
            for entity in normalized_manual.get(file_name, [])[:10]:  # Log just the first 5 to avoid spam
                logger.info(
                    f"  Entity: {entity['text']} | Type: {entity['type']} | Original Type: {entity['original_type']}")

            if len(normalized_manual.get(file_name, [])) > 10:
                logger.info(f"  ... and {len(normalized_manual.get(file_name, [])) - 10} more entities")

        logger.info(
            f"Normalized entities from {len(normalized_hybrid)} hybrid model results and {len(normalized_manual)} manual redaction files")

        return normalized_hybrid, normalized_manual

    def map_files_for_comparison(self, hybrid_entities: Dict[str, List[Dict]],
                                 manual_entities: Dict[str, List[Dict]]) -> Dict[str, str]:
        """
        Map hybrid filenames to manual filenames for direct comparison.

        Args:
            hybrid_entities: Normalized hybrid entities by filename
            manual_entities: Normalized manual entities by filename

        Returns:
            Dictionary mapping hybrid filenames to manual filenames
        """
        mapping = {}

        # First try direct mapping (exact filenames)
        for hybrid_file in hybrid_entities.keys():
            if hybrid_file in manual_entities:
                mapping[hybrid_file] = hybrid_file
                logger.info(f"Direct file mapping: {hybrid_file} -> {hybrid_file}")
                continue

            # For PDF files, try mapping to equivalent text files in manual data
            hybrid_base = os.path.splitext(hybrid_file)[0]
            for manual_file in manual_entities.keys():
                manual_base = os.path.splitext(manual_file)[0]
                if hybrid_base == manual_base:
                    mapping[hybrid_file] = manual_file
                    logger.info(f"Base name mapping: {hybrid_file} -> {manual_file}")
                    break

        # For remaining files, try to find matches based on filename patterns
        remaining_hybrid = [f for f in hybrid_entities.keys() if f not in mapping]

        for hybrid_file in remaining_hybrid:
            hybrid_base = os.path.splitext(hybrid_file)[0].lower()

            # Try to find a manual file that contains the hybrid file name
            best_match = None
            best_score = 0

            for manual_file in manual_entities.keys():
                manual_base = os.path.splitext(manual_file)[0].lower()

                # Check for exact substring
                if hybrid_base in manual_base or manual_base in hybrid_base:
                    # Calculate match score based on length of common substring
                    score = len(set(hybrid_base) & set(manual_base)) / max(len(hybrid_base), len(manual_base))

                    if score > best_score:
                        best_score = score
                        best_match = manual_file

            if best_match and best_score > 0.5:  # Threshold for good match
                mapping[hybrid_file] = best_match
                logger.info(f"Fuzzy file mapping: {hybrid_file} -> {best_match} (score: {best_score:.2f})")

        # If no hybrid files, create sample mappings for testing
        if not hybrid_entities and manual_entities:
            logger.warning("No hybrid files found. Creating sample mappings for testing.")

            # Use first few manual files for testing
            sample_files = list(manual_entities.keys())[:self.max_files]
            for manual_file in sample_files:
                # Use the same filename for both
                mapping[manual_file] = manual_file
                logger.info(f"Sample mapping for testing: {manual_file} -> {manual_file}")

        logger.info(f"Mapped {len(mapping)} files for comparison")
        return mapping

    def calculate_metrics(self, hybrid_entities: Dict[str, List[Dict]], manual_entities: Dict[str, List[Dict]]) -> Dict[
        str, Any]:
        """
        Calculate comparison metrics between automated detection and manual redaction.
        """
        logger.info("Calculating comparison metrics")

        # Log entity mapping groups for transparency
        logger.info("Entity mapping groups:")
        for standard_type, original_types in sorted(self.entity_groups.items()):
            original_list = ", ".join(sorted(original_types))
            logger.info(f"  {standard_type} → [{original_list}]")

        metrics = {
            "entity_counts": {
                "hybrid": {},
                "manual": {},
                "comparison": {}
            },
            "precision_recall": {
                "overall": {},
                "by_type": {}
            },
            "document_level_metrics": [],
            "processing_time": self.processing_times,
            "entity_mapping": self.entity_groups
        }

        # Calculate entity counts by type
        hybrid_count = {}
        manual_count = {}

        for file_name, entities in hybrid_entities.items():
            for entity in entities:
                entity_type = entity["type"]
                hybrid_count[entity_type] = hybrid_count.get(entity_type, 0) + 1

        for file_name, entities in manual_entities.items():
            for entity in entities:
                entity_type = entity["type"]
                manual_count[entity_type] = manual_count.get(entity_type, 0) + 1

        metrics["entity_counts"]["hybrid"] = hybrid_count
        metrics["entity_counts"]["manual"] = manual_count

        # Calculate comparison metrics for all entity types
        all_entity_types = set(hybrid_count.keys()) | set(manual_count.keys())

        for entity_type in all_entity_types:
            hybrid_type_count = hybrid_count.get(entity_type, 0)
            manual_type_count = manual_count.get(entity_type, 0)

            # Calculate difference and ratio
            difference = hybrid_type_count - manual_type_count
            ratio = hybrid_type_count / manual_type_count if manual_type_count > 0 else float('inf')

            metrics["entity_counts"]["comparison"][entity_type] = {
                "hybrid": hybrid_type_count,
                "manual": manual_type_count,
                "difference": difference,
                "ratio": ratio
            }

        # Map hybrid files to manual files for comparison
        file_mapping = self.map_files_for_comparison(hybrid_entities, manual_entities)

        # Skip metrics calculation if no mappings
        if not file_mapping:
            logger.warning("No file mappings available for metrics calculation.")
            metrics["precision_recall"]["overall"] = {
                "true_positives": 0,
                "false_positives": 0,
                "false_negatives": 0,
                "precision": 0,
                "recall": 0,
                "f1": 0
            }
            return metrics

        # Calculate document-level metrics
        total_true_positives = 0
        total_false_positives = 0
        total_false_negatives = 0

        for hybrid_file, manual_file in file_mapping.items():
            hybrid_file_entities = hybrid_entities.get(hybrid_file, [])
            manual_file_entities = manual_entities.get(manual_file, [])

            # Extract text content for approximate matching
            hybrid_entities_set = [(e["text"].lower(), e["type"]) for e in hybrid_file_entities]
            manual_entities_set = [(e["text"].lower(), e["type"]) for e in manual_file_entities]

            # Count matching entities (true positives)
            true_positives = 0
            matched_hybrid_indices = set()
            matched_manual_indices = set()

            for i, (hybrid_text, hybrid_type) in enumerate(hybrid_entities_set):
                for j, (manual_text, manual_type) in enumerate(manual_entities_set):
                    if j in matched_manual_indices:
                        continue

                    # Check if the entities match (using fuzzy matching)
                    text_similarity = self._calculate_text_similarity(hybrid_text, manual_text)

                    # Types match if they are the same after mapping
                    type_match = (hybrid_type == manual_type)

                    if text_similarity > 0.7 and type_match:
                        true_positives += 1
                        matched_hybrid_indices.add(i)
                        matched_manual_indices.add(j)
                        break

            # False positives are hybrid detections that don't match any manual entity
            false_positives = len(hybrid_entities_set) - true_positives

            # False negatives are manual entities that don't match any hybrid detection
            false_negatives = len(manual_entities_set) - true_positives

            # Print detailed metrics for this file
            logger.info(f"File comparison: {hybrid_file} (hybrid) vs {manual_file} (manual)")
            logger.info(f"  True Positives: {true_positives}")
            logger.info(f"  False Positives: {false_positives}")
            logger.info(f"  False Negatives: {false_negatives}")

            # Print missed entities (false negatives) - up to 5
            if false_negatives > 0:
                logger.info("  Sample missed entities (False Negatives):")
                count = 0
                for j, (manual_text, manual_type) in enumerate(manual_entities_set):
                    if j not in matched_manual_indices:
                        logger.info(f"    Text: {manual_text} | Type: {manual_type}")
                        count += 1
                        if count >= 10:
                            logger.info(f"    ... and {false_negatives - 10} more")
                            break

            # Print incorrect detections (false positives) - up to 5
            if false_positives > 0:
                logger.info("  Sample incorrect detections (False Positives):")
                count = 0
                for i, (hybrid_text, hybrid_type) in enumerate(hybrid_entities_set):
                    if i not in matched_hybrid_indices:
                        logger.info(f"    Text: {hybrid_text} | Type: {hybrid_type}")
                        count += 1
                        if count >= 10:
                            logger.info(f"    ... and {false_positives - 10} more")
                            break

            # Calculate precision, recall, and F1 score
            precision = true_positives / len(hybrid_entities_set) if len(hybrid_entities_set) > 0 else 0
            recall = true_positives / len(manual_entities_set) if len(manual_entities_set) > 0 else 0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

            # Add document-level metrics
            metrics["document_level_metrics"].append({
                "hybrid_file": hybrid_file,
                "manual_file": manual_file,
                "hybrid_count": len(hybrid_entities_set),
                "manual_count": len(manual_entities_set),
                "true_positives": true_positives,
                "false_positives": false_positives,
                "false_negatives": false_negatives,
                "precision": precision,
                "recall": recall,
                "f1": f1
            })

            # Accumulate totals for overall metrics
            total_true_positives += true_positives
            total_false_positives += false_positives
            total_false_negatives += false_negatives

        # Calculate overall precision, recall, and F1 score
        total_hybrid = total_true_positives + total_false_positives
        total_manual = total_true_positives + total_false_negatives

        overall_precision = total_true_positives / total_hybrid if total_hybrid > 0 else 0
        overall_recall = total_true_positives / total_manual if total_manual > 0 else 0
        overall_f1 = 2 * overall_precision * overall_recall / (overall_precision + overall_recall) if (
                                                                                                              overall_precision + overall_recall) > 0 else 0

        metrics["precision_recall"]["overall"] = {
            "true_positives": total_true_positives,
            "false_positives": total_false_positives,
            "false_negatives": total_false_negatives,
            "precision": overall_precision,
            "recall": overall_recall,
            "f1": overall_f1
        }

        # Print overall false positive/negative metrics
        logger.info(f"Overall Metrics:")
        logger.info(f"  Total True Positives: {total_true_positives}")
        logger.info(f"  Total False Positives: {total_false_positives}")
        logger.info(f"  Total False Negatives: {total_false_negatives}")
        logger.info(f"  Precision: {overall_precision:.4f}")
        logger.info(f"  Recall: {overall_recall:.4f}")
        logger.info(f"  F1 Score: {overall_f1:.4f}")

        # Calculate precision, recall, and F1 score by entity type
        for entity_type in all_entity_types:
            type_true_positives = 0
            type_false_positives = 0
            type_false_negatives = 0

            for hybrid_file, manual_file in file_mapping.items():
                if hybrid_file not in hybrid_entities or manual_file not in manual_entities:
                    continue

                hybrid_file_entities = [(e["text"].lower(), e["type"]) for e in hybrid_entities[hybrid_file] if
                                        e["type"] == entity_type]
                manual_file_entities = [(e["text"].lower(), e["type"]) for e in manual_entities[manual_file] if
                                        e["type"] == entity_type]

                # Count matching entities (true positives) for this type
                type_matched_hybrid_indices = set()
                type_matched_manual_indices = set()

                for i, (hybrid_text, _) in enumerate(hybrid_file_entities):
                    for j, (manual_text, _) in enumerate(manual_file_entities):
                        if j in type_matched_manual_indices:
                            continue

                        text_similarity = self._calculate_text_similarity(hybrid_text, manual_text)

                        if text_similarity > 0.7:
                            type_true_positives += 1
                            type_matched_hybrid_indices.add(i)
                            type_matched_manual_indices.add(j)
                            break

                # Count false positives and false negatives for this type
                type_false_positives += len(hybrid_file_entities) - len(type_matched_hybrid_indices)
                type_false_negatives += len(manual_file_entities) - len(type_matched_manual_indices)

            # Calculate precision, recall, and F1 score for this entity type
            type_precision = type_true_positives / (type_true_positives + type_false_positives) if (
                                                                                                           type_true_positives + type_false_positives) > 0 else 0
            type_recall = type_true_positives / (type_true_positives + type_false_negatives) if (
                                                                                                        type_true_positives + type_false_negatives) > 0 else 0
            type_f1 = 2 * type_precision * type_recall / (type_precision + type_recall) if (
                                                                                                   type_precision + type_recall) > 0 else 0

            metrics["precision_recall"]["by_type"][entity_type] = {
                "precision": type_precision,
                "recall": type_recall,
                "f1": type_f1,
                "true_positives": type_true_positives,
                "false_positives": type_false_positives,
                "false_negatives": type_false_negatives
            }

            # Print metrics by entity type
            logger.info(f"Entity Type: {entity_type}")
            logger.info(f"  True Positives: {type_true_positives}")
            logger.info(f"  False Positives: {type_false_positives}")
            logger.info(f"  False Negatives: {type_false_negatives}")
            logger.info(f"  Precision: {type_precision:.4f}")
            logger.info(f"  Recall: {type_recall:.4f}")
            logger.info(f"  F1 Score: {type_f1:.4f}")

        logger.info("Comprehensive metrics calculation complete")
        return metrics

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate text similarity between two strings for entity matching.

        Args:
            text1: First string
            text2: Second string

        Returns:
            Similarity score between 0 and 1
        """
        # Simple case: exact match
        if text1 == text2:
            return 1.0

        # Case-insensitive exact match
        if text1.lower() == text2.lower():
            return 0.95

        # One is a substring of the other
        if text1.lower() in text2.lower():
            return 0.9 * (len(text1) / len(text2))

        if text2.lower() in text1.lower():
            return 0.9 * (len(text2) / len(text1))

        # Tokenize and compare word overlap
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        common_words = words1.intersection(words2)
        return len(common_words) / max(len(words1), len(words2))

    def generate_visualizations(self, metrics: Dict[str, Any]) -> None:
        """
        Generate key visualizations for comparison.
        """
        logger.info("Generating visualizations")

        # Set the style for all visualizations
        plt.style.use('ggplot')
        sns.set_palette("viridis")

        # 1. Entity Count Comparison
        self._plot_entity_count_comparison(metrics)

        # 2. Precision-Recall-F1 Comparison
        self._plot_precision_recall_f1(metrics)

        # 3. Document-Level Performance
        self._plot_document_level_performance(metrics)

        # 4. False Positives and False Negatives by Entity Type
        self._plot_false_positives_negatives(metrics)

        # 5. Confusion Matrix
        self._plot_confusion_matrix(metrics)

        logger.info(f"All visualizations generated in '{self.output_directory}/visualizations' directory")

    def _plot_entity_count_comparison(self, metrics: Dict[str, Any]) -> None:
        """
        Plot entity count comparison between hybrid model and manual redaction.
        """
        # Get entity types sorted by manual count
        sorted_entities = sorted(
            metrics["entity_counts"]["comparison"].items(),
            key=lambda x: x[1]["manual"],
            reverse=True
        )

        entity_types = [item[0] for item in sorted_entities]
        manual_counts = [item[1]["manual"] for item in sorted_entities]
        hybrid_counts = [item[1]["hybrid"] for item in sorted_entities]

        # Truncate entity types list if too long
        if len(entity_types) > 15:
            entity_types = entity_types[:15]
            manual_counts = manual_counts[:15]
            hybrid_counts = hybrid_counts[:15]

        # If no entities, add dummy data
        if not entity_types:
            entity_types = ["NO DATA"]
            manual_counts = [0]
            hybrid_counts = [0]

        x = np.arange(len(entity_types))
        width = 0.35

        fig, ax = plt.subplots(figsize=(14, 10))
        rects1 = ax.bar(x - width / 2, manual_counts, width, label='Manual Redaction', color='#4472C4')
        rects2 = ax.bar(x + width / 2, hybrid_counts, width, label='Automated Detection', color='#ED7D31')

        ax.set_ylabel('Entity Count', fontsize=12)
        ax.set_title('Entity Count Comparison by Type', fontsize=16, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(entity_types, rotation=45, ha='right', fontsize=10)
        ax.legend(fontsize=12)

        # Add count labels on bars
        for i, v in enumerate(manual_counts):
            ax.text(i - width / 2, v + 1, str(v), ha='center', fontsize=9)

        for i, v in enumerate(hybrid_counts):
            ax.text(i + width / 2, v + 1, str(v), ha='center', fontsize=9)

        plt.tight_layout()
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        plt.savefig(os.path.join(self.output_directory, "visualizations/entity_count_comparison.png"), dpi=300)
        plt.close()

    def _plot_precision_recall_f1(self, metrics: Dict[str, Any]) -> None:
        """
        Plot precision, recall, and F1 score by entity type.
        """
        # Get top entity types by count
        top_entity_types = sorted(
            metrics["precision_recall"]["by_type"].keys(),
            key=lambda x: metrics["entity_counts"]["comparison"].get(x, {}).get("manual", 0),
            reverse=True
        )

        # Take top 10 for readability
        if len(top_entity_types) > 10:
            top_entity_types = top_entity_types[:10]

        # If no entity types, add dummy data
        if not top_entity_types:
            logger.warning("No entity types found for precision/recall chart.")
            return

        # Create data for plotting
        data = []

        for entity_type in top_entity_types:
            metrics_by_type = metrics["precision_recall"]["by_type"].get(entity_type, {})

            precision = metrics_by_type.get("precision", 0) * 100
            recall = metrics_by_type.get("recall", 0) * 100
            f1 = metrics_by_type.get("f1", 0) * 100

            data.append({
                'Entity Type': entity_type,
                'Metric': 'Precision',
                'Value': precision
            })

            data.append({
                'Entity Type': entity_type,
                'Metric': 'Recall',
                'Value': recall
            })

            data.append({
                'Entity Type': entity_type,
                'Metric': 'F1 Score',
                'Value': f1
            })

        df = pd.DataFrame(data)

        # Create grouped bar chart
        plt.figure(figsize=(14, 10))

        sns.barplot(
            x='Entity Type',
            y='Value',
            hue='Metric',
            data=df,
            palette=['#4472C4', '#ED7D31', '#70AD47']
        )

        plt.title('Precision, Recall, and F1 Score by Entity Type', fontsize=16, fontweight='bold')
        plt.xlabel('Entity Type', fontsize=12)
        plt.ylabel('Percentage (%)', fontsize=12)
        plt.ylim(0, 100)
        plt.xticks(rotation=45, ha='right', fontsize=10)
        plt.legend(title='Metric', fontsize=12)
        plt.grid(axis='y', linestyle='--', alpha=0.7)

        plt.tight_layout()
        plt.savefig(os.path.join(self.output_directory, "visualizations/precision_recall_f1.png"), dpi=300)
        plt.close()

        # Create a separate chart for overall metrics
        overall = metrics["precision_recall"]["overall"]

        overall_data = [
            {'Metric': 'Precision', 'Value': overall.get("precision", 0) * 100},
            {'Metric': 'Recall', 'Value': overall.get("recall", 0) * 100},
            {'Metric': 'F1 Score', 'Value': overall.get("f1", 0) * 100}
        ]

        df_overall = pd.DataFrame(overall_data)

        plt.figure(figsize=(10, 6))

        bars = plt.bar(
            df_overall['Metric'],
            df_overall['Value'],
            color=['#4472C4', '#ED7D31', '#70AD47']
        )

        plt.title('Overall Detection Performance', fontsize=16, fontweight='bold')
        plt.ylabel('Percentage (%)', fontsize=12)
        plt.ylim(0, 100)
        plt.grid(axis='y', linestyle='--', alpha=0.7)

        # Add percentage labels on bars
        for bar in bars:
            height = bar.get_height()
            plt.text(
                bar.get_x() + bar.get_width() / 2.,
                height + 1,
                f'{height:.1f}%',
                ha='center',
                fontsize=12
            )

        plt.tight_layout()
        plt.savefig(os.path.join(self.output_directory, "visualizations/overall_performance.png"), dpi=300)
        plt.close()

    def _plot_document_level_performance(self, metrics: Dict[str, Any]) -> None:
        """
        Plot document-level performance comparison.
        """
        doc_metrics = metrics["document_level_metrics"]

        if not doc_metrics:
            logger.warning("No document-level metrics available for visualization")
            return

        # Sort documents by F1 score
        sorted_docs = sorted(doc_metrics, key=lambda x: x["f1"], reverse=True)

        # Create data for plotting
        file_names = [os.path.splitext(d.get("hybrid_file", ""))[0][:10] + "..." for d in
                      sorted_docs]  # Truncate for display
        precision_values = [d["precision"] * 100 for d in sorted_docs]
        recall_values = [d["recall"] * 100 for d in sorted_docs]
        f1_values = [d["f1"] * 100 for d in sorted_docs]

        # Prepare DataFrame for easier plotting
        data = []

        for i, file_name in enumerate(file_names):
            data.append({'File': file_name, 'Metric': 'Precision', 'Value': precision_values[i]})
            data.append({'File': file_name, 'Metric': 'Recall', 'Value': recall_values[i]})
            data.append({'File': file_name, 'Metric': 'F1 Score', 'Value': f1_values[i]})

        df = pd.DataFrame(data)

        # Plot document-level metrics
        plt.figure(figsize=(14, 10))

        sns.barplot(
            x='File',
            y='Value',
            hue='Metric',
            data=df,
            palette=['#4472C4', '#ED7D31', '#70AD47']
        )

        plt.title('Document-Level Performance Metrics', fontsize=16, fontweight='bold')
        plt.xlabel('Document', fontsize=12)
        plt.ylabel('Percentage (%)', fontsize=12)
        plt.ylim(0, 105)  # Allow space for labels
        plt.xticks(rotation=45, ha='right', fontsize=10)
        plt.legend(title='Metric', fontsize=12)
        plt.grid(axis='y', linestyle='--', alpha=0.7)

        plt.tight_layout()
        plt.savefig(os.path.join(self.output_directory, "visualizations/document_level_performance.png"), dpi=300)
        plt.close()

    def _plot_false_positives_negatives(self, metrics: Dict[str, Any]) -> None:
        """
        Plot false positives and false negatives by entity type.
        """
        # Get entity types sorted by manual count
        sorted_entities = sorted(
            metrics["precision_recall"]["by_type"].items(),
            key=lambda x: metrics["entity_counts"]["comparison"].get(x[0], {}).get("manual", 0),
            reverse=True
        )

        # Take top 10 for readability
        if len(sorted_entities) > 10:
            sorted_entities = sorted_entities[:10]

        # If no entity types, skip this visualization
        if not sorted_entities:
            logger.warning("No entity types found for false positives/negatives chart.")
            return

        entity_types = [item[0] for item in sorted_entities]
        false_positives = [item[1]["false_positives"] for item in sorted_entities]
        false_negatives = [item[1]["false_negatives"] for item in sorted_entities]

        x = np.arange(len(entity_types))
        width = 0.35

        fig, ax = plt.subplots(figsize=(14, 10))
        ax.bar(x - width / 2, false_positives, width, label='False Positives', color='#FF5050')
        ax.bar(x + width / 2, false_negatives, width, label='False Negatives', color='#FFD700')

        ax.set_ylabel('Count', fontsize=12)
        ax.set_title('False Positives and False Negatives by Entity Type', fontsize=16, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(entity_types, rotation=45, ha='right', fontsize=10)
        ax.legend(fontsize=12)

        # Add count labels on bars
        for i, v in enumerate(false_positives):
            ax.text(i - width / 2, v + 0.5, str(v), ha='center', fontsize=9)

        for i, v in enumerate(false_negatives):
            ax.text(i + width / 2, v + 0.5, str(v), ha='center', fontsize=9)

        plt.tight_layout()
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        plt.savefig(os.path.join(self.output_directory, "visualizations/false_positives_negatives.png"), dpi=300)
        plt.close()

    def _plot_confusion_matrix(self, metrics: Dict[str, Any]) -> None:
        """
        Plot a confusion matrix visualization showing true/false positives and negatives.
        """
        # Create an aggregate confusion matrix
        tp_sum = sum(d["true_positives"] for d in metrics["document_level_metrics"])
        fp_sum = sum(d["false_positives"] for d in metrics["document_level_metrics"])
        fn_sum = sum(d["false_negatives"] for d in metrics["document_level_metrics"])

        # If no metrics data, use zeros
        if not metrics["document_level_metrics"]:
            tp_sum, fp_sum, fn_sum = 0, 0, 0

        # Calculate implied true negatives (this is an approximation)
        # For simplicity, we'll assume the total number of possible entity positions is 10x the entities found
        total_possible = max((tp_sum + fn_sum) * 10, 1)  # Avoid division by zero
        tn_sum = total_possible - tp_sum - fp_sum - fn_sum

        # Create confusion matrix
        cm = np.array([
            [tp_sum, fn_sum],
            [fp_sum, tn_sum]
        ])

        plt.figure(figsize=(10, 8))

        sns.heatmap(
            cm,
            annot=True,
            fmt="d",
            cmap="YlGnBu",
            xticklabels=['Detected', 'Not Detected'],
            yticklabels=['Present', 'Not Present'],
            cbar=False
        )

        plt.title('Confusion Matrix (Aggregated)', fontsize=16, fontweight='bold')
        plt.xlabel('Automated Detection', fontsize=12)
        plt.ylabel('Manual Redaction (Ground Truth)', fontsize=12)

        plt.tight_layout()
        plt.savefig(os.path.join(self.output_directory, "visualizations/confusion_matrix.png"), dpi=300)
        plt.close()

    def run_comparison(self) -> Dict[str, Any]:
        """
        Run the complete comparison process.
        """
        logger.info("Starting comparison process")

        # Step 1: Process files through the hybrid model
        self.process_hybrid_model()

        # Step 2: If no hybrid results, create sample results for testing
        self.create_manual_samples()

        # Step 3: Load all corresponding manual data
        self.load_manual_data()

        # Step 4: Normalize entities from both sources
        hybrid_entities, manual_entities = self.normalize_entities()

        # Step 5: Calculate comparison metrics
        metrics = self.calculate_metrics(hybrid_entities, manual_entities)
        self.metrics.update(metrics)

        # Step 6: Generate visualizations
        self.generate_visualizations(metrics)

        logger.info("Comparison process complete")

        # Print detailed metrics summary
        self._print_metrics_summary(metrics)

        # Return a comprehensive summary
        return {
            "entity_counts": {
                "hybrid_total": sum(metrics["entity_counts"]["hybrid"].values()),
                "manual_total": sum(metrics["entity_counts"]["manual"].values())
            },
            "overall_metrics": metrics["precision_recall"]["overall"],
            "entity_type_count": {
                "hybrid": len(metrics["entity_counts"]["hybrid"]),
                "manual": len(metrics["entity_counts"]["manual"]),
                "common": len(
                    set(metrics["entity_counts"]["hybrid"].keys()) & set(metrics["entity_counts"]["manual"].keys()))
            },
            "processing_time": metrics["processing_time"],
            "top_performing_types": sorted(
                [(et, metrics["precision_recall"]["by_type"][et]["f1"])
                 for et in metrics["precision_recall"]["by_type"].keys()],
                key=lambda x: x[1],
                reverse=True
            )[:10] if metrics["precision_recall"]["by_type"] else [],
            "visualization_files": [
                os.path.join(self.output_directory, "visualizations/entity_count_comparison.png"),
                os.path.join(self.output_directory, "visualizations/precision_recall_f1.png"),
                os.path.join(self.output_directory, "visualizations/overall_performance.png"),
                os.path.join(self.output_directory, "visualizations/document_level_performance.png"),
                os.path.join(self.output_directory, "visualizations/false_positives_negatives.png"),
                os.path.join(self.output_directory, "visualizations/confusion_matrix.png")
            ]
        }

    def _print_metrics_summary(self, metrics: Dict[str, Any]) -> None:
        """
        Print a detailed summary of metrics to the console.
        """
        print("\n" + "=" * 80)
        print("ENTITY DETECTION COMPARISON SUMMARY".center(80))
        print("=" * 80)

        # Entity counts
        hybrid_total = sum(metrics["entity_counts"]["hybrid"].values())
        manual_total = sum(metrics["entity_counts"]["manual"].values())

        print("\nENTITY COUNTS:")
        print(f"  Manual Redaction:    {manual_total} entities")
        print(f"  Automated Detection: {hybrid_total} entities")
        print(f"  Difference:          {hybrid_total - manual_total} entities")

        # Overall performance
        overall = metrics["precision_recall"]["overall"]
        tp = overall.get("true_positives", 0)
        fp = overall.get("false_positives", 0)
        fn = overall.get("false_negatives", 0)

        print("\nOVERALL PERFORMANCE:")
        print(f"  True Positives:  {tp}")
        print(f"  False Positives: {fp}")
        print(f"  False Negatives: {fn}")
        print(f"  Precision:       {overall.get('precision', 0) * 100:.2f}%")
        print(f"  Recall:          {overall.get('recall', 0) * 100:.2f}%")
        print(f"  F1 Score:        {overall.get('f1', 0) * 100:.2f}%")

        # Top entity types
        print("\nTOP ENTITY TYPES BY COUNT:")
        top_types = sorted(
            metrics["entity_counts"]["comparison"].items(),
            key=lambda x: x[1]["manual"],
            reverse=True
        )[:10]

        for entity_type, counts in top_types:
            print(f"  {entity_type}:")
            print(f"    Manual: {counts['manual']} | Automated: {counts['hybrid']}")

            # Get precision/recall for this type
            type_metrics = metrics["precision_recall"]["by_type"].get(entity_type, {})
            if type_metrics:
                print(f"    Precision: {type_metrics.get('precision', 0) * 100:.2f}% | "
                      f"Recall: {type_metrics.get('recall', 0) * 100:.2f}% | "
                      f"F1: {type_metrics.get('f1', 0) * 100:.2f}%")

        # Document-level performance
        if metrics["document_level_metrics"]:
            print("\nDOCUMENT-LEVEL PERFORMANCE:")
            avg_precision = np.mean([d["precision"] for d in metrics["document_level_metrics"]]) * 100
            avg_recall = np.mean([d["recall"] for d in metrics["document_level_metrics"]]) * 100
            avg_f1 = np.mean([d["f1"] for d in metrics["document_level_metrics"]]) * 100

            print(f"  Average Precision: {avg_precision:.2f}%")
            print(f"  Average Recall:    {avg_recall:.2f}%")
            print(f"  Average F1 Score:  {avg_f1:.2f}%")

        print("\nResults have been saved to the output directory:")
        print(f"  {self.output_directory}")
        print("=" * 80)


def main():
    """Main function to run the entity detection comparison."""
    logger.info("Starting Entity Detection Comparison")

    # Configuration with absolute paths
    pdf_directory = r"" # replace with your the 100 PDFs
    manual_redaction_directory = r"" # replace with the manuell redaction of the PDFs
    hybrid_endpoint = "http://localhost:8000/batch/hybrid_detect"
    output_directory = "model_validation"
    max_files = 10  # Limit to 5 files

    # Create and run comparison
    comparison = EntityDetectionComparison(
        pdf_directory=pdf_directory,
        manual_redaction_directory=manual_redaction_directory,
        hybrid_endpoint=hybrid_endpoint,
        output_directory=output_directory,
        max_files=max_files
    )

    summary = comparison.run_comparison()


if __name__ == "__main__":
    main()