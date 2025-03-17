import os
import re
import time
import json
import random
import signal
import sys
import threading
from datetime import datetime

from dotenv import load_dotenv
import google.generativeai as genai

"""
Combined script for generating and labeling Norwegian inspection reports.
This script handles both generation of reports and their subsequent labeling with sensitive data extraction.
"""

# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backend', '.env'))

# Configuration
API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=API_KEY)

# Define data folders
MAIN_FOLDER = os.path.join(os.path.dirname(__file__), 'inspeksjonsrapport')
DATA_FOLDER = os.path.join(MAIN_FOLDER, 'inspeksjonsrapport_text')
TRAINING_FOLDER = os.path.join(MAIN_FOLDER, 'labeling_inspeksjonsrapport')
PROCESSED_FOLDER = os.path.join(DATA_FOLDER, 'processed')

# Create necessary directories
for folder in [MAIN_FOLDER, DATA_FOLDER, TRAINING_FOLDER, PROCESSED_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)
        print(f"Created directory: {folder}")

# Flag to control threads
running = True

# Define scenarios for inspection reports
report_scenarios = [
    "A man repeatedly violating animal welfare laws through neglect and cruelty.",
    "A woman owning a restaurant repeatedly failing hygiene and health standards.",
    "A financially unstable farmer falsifying veterinary documents for livestock transport.",
    "A cosmetics shop owner illegally importing banned chemical substances. ",
    "A religious community center repeatedly failing food safety and documentation requirements. ",
    "A nursery responsible for outbreaks of severe plant diseases due to ignoring quarantine rules. ",
    "A dairy producer falsifying financial statements and economic records. ",
    "A butcher arrested previously for weapon-related crimes with repeated hygiene violations.",
    "A seafood exporter providing fraudulent product origin documentation linked to economic fraud.",
    "An employee in a slaughterhouse arrested previously for animal cruelty, presenting political extremist views.",
    "A catering business owner involved in sexual scandals and unsanitary food preparation conditions. ",
    "A religious community center involved in illegal political activities and repeated health documentation violations. ",
    "A plant nursery intentionally violating quarantine guidelines causing severe plant disease outbreaks.",
    "A dairy producer with chronic animal diseases (e.g., Johne's disease, Mastitis) and falsified health records.",
    "A bakery owner repeatedly concealing criminal history involving financial fraud and violence. ",
    "A cosmetic store illegally importing banned substances, owner actively involved in political propaganda. ",
    "A farmer actively involved in political campaigns accused of animal abuse and falsified financial statements. ",
    "An owner of a catering service involved in multiple scandals including poor hygiene practices and illegal weapon possession. ",
    "An agricultural business with a family history of illegal financial practices, currently neglecting plant quarantine rules. ",
    "A religious organization accused of severe food safety violations and illegal political activities. ",
    "A woman managing a facility with repeated violations in documentation, health standards, and known for political activism. ",
    "A fisherman falsifying economic records and financial statements, arrested previously for illegal weapon possession. ",
    "A restaurant owner involved in personal scandals, known political extremist, repeatedly failing food inspections. ",
    "A farmer repeatedly neglecting animal health (e.g., Foot-and-mouth disease), with family members previously arrested for animal cruelty and violence. ",
    "A dairy producer accused of financial fraud, animal neglect (e.g., Lameness, Bovine tuberculosis), and manipulation of health inspection results. ",
    "A plant nursery owner politically active, responsible for intentional neglect causing widespread plant diseases (e.g., Ash dieback). ",
    "A dog breeder neglecting animal health standards (e.g., Parvovirus, Canine distemper), resulting in severe health issues and financial fraud.",
    "A pet shop owner illegally importing animals and neglecting proper veterinary documentation and animal care guidelines. ",
    "A poultry farm owner repeatedly violating animal welfare, hygiene standards, and falsifying documentation (e.g., Salmonella outbreaks). ",
    "A zoo facility failing animal welfare standards and falsifying health records, involving weapon-related crimes. ",
    "An animal shelter owner arrested previously for animal abuse and falsification of financial documents. ",
    "A veterinarian repeatedly falsifying animal health certifications and involved in illegal financial activities. ",
    "A riding stable owner accused of neglecting horse welfare (e.g., Equine influenza, Colic), with known financial difficulties and criminal records. ",
    "A wildlife park manager with political extremist views repeatedly failing animal welfare inspections. ",
    "A pet shop owner repeatedly importing animals illegally and hiding serious health issues (e.g., Giardia, Rabies) from customers. ",
    "An agricultural company repeatedly accused of using banned pesticides (e.g., DDT), falsifying documents, and economic fraud. ",
    "A seafood processing plant owner hiding weapon-related incidents and financial irregularities, compromising hygiene. ",
    "A livestock transport company falsifying veterinary documents, causing outbreaks of serious animal diseases (e.g., Bluetongue). ",
    "A farmer concealing family members' violent criminal past, repeatedly violating animal health and welfare standards. ",
    "A food processing facility manager arrested previously for financial fraud, involved in repeated hygiene failures. ",
    "A religious food establishment repeatedly violating hygiene rules, run by individuals with political extremist views. ",
    "An organic farm owner repeatedly neglecting health documentation, politically active and involved in scandals.",
    "A bakery owner accused of multiple sexual scandals, financial irregularities, and food safety violations. ",
    "A plant nursery spreading serious diseases (e.g., Sudden oak death) due to politically motivated neglect of quarantine guidelines."
]

# Signal handler for graceful shutdown
def signal_handler(sig, frame):
    """Handle termination signals to shut down properly"""
    global running
    print("\nShutting down processes gracefully...")
    running = False

    # Give threads time to complete current operations
    time.sleep(2)
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Generator functions
def generate_text(prompt, system_instruction):
    """Generate text using Gemini model with given prompt and system instruction"""
    model = genai.GenerativeModel("gemini-2.0-pro-exp-02-05", system_instruction=system_instruction)
    response = model.generate_content(prompt)
    return response.text

def save_to_txt(text, filename):
    """Save the generated text to a file after cleaning"""
    cleaned_text = clean_response(text)
    filepath = os.path.join(DATA_FOLDER, filename)
    with open(filepath, 'w', encoding='utf-8') as file:
        file.write(cleaned_text)
    return filepath

def clean_response(text):
    """Clean the response text from unwanted formatting"""
    # Remove [text] at the beginning and end
    text = re.sub(r'^\[\s*|\s*\]$', '', text.strip())
    # Remove all occurrences of '**'
    text = re.sub(r'\*\*', '', text)
    return text.strip()

# Labeling functions
def get_all_txt_files():
    """Retrieve all .txt files from DATA_FOLDER, sorted by creation time (oldest first)"""
    txt_files = [f for f in os.listdir(DATA_FOLDER) if f.endswith('.txt')]
    txt_files.sort(key=lambda f: os.path.getctime(os.path.join(DATA_FOLDER, f)))
    return txt_files

def clean_json_response(response_text):
    """Clean and parse the API response JSON"""
    cleaned_text = re.sub(r"```json\s*|\s*```", "", response_text).strip()

    try:
        data = json.loads(cleaned_text)
        if "text_input" in data and data["text_input"].endswith("["):
            data["text_input"] = data["text_input"].rstrip("[")
        return data
    except json.JSONDecodeError as e:
        print("JSON Decode Error:", e)
        print("Raw text that failed to parse:", cleaned_text[:200])  # Limited preview
        return {"error": "Invalid response from Gemini"}

def extract_sensitive_data(text):
    """Send text to Gemini API to extract and label sensitive data in structured format"""
    prompt = (
        "Analyze the following text and extract all sensitive entities according to the categories below. "
        "Ensure the output is a valid JSON format.\n\n"
        "**Sensitive Data Categories:**\n"
        "- **NO_PHONE_NUMBER** → Norwegian Phone Numbers\n"
        "- **PERSON** → Norwegian Names\n"
        "- **EMAIL_ADDRESS** → Email Addresses\n"
        "- **NO_ADDRESS** → Norwegian Home/Street Addresses\n"
        "- **DATE_TIME** → Dates and Timestamps\n"
        "- **GOV_ID** → Government-Issued Identifiers (any identification number)\n"
        "- **FINANCIAL_INFO** → Financial Data (contextually financial information, not just words about money)\n"
        "- **EMPLOYMENT_INFO** → Employment and Professional Details\n"
        "- **HEALTH_INFO** → Health-Related Information\n"
        "- **SEXUAL_ORIENTATION** → Sexual Relationships and Orientation\n"
        "- **CRIMINAL_RECORD** → Crime-Related Information\n"
        "- **CONTEXT_SENSITIVE** → Context-Sensitive Information\n"
        "- **IDENTIFIABLE_IMAGE** → Any Identifiable Image Reference\n"
        "- **FAMILY_RELATION** → Family and Relationship Data\n"
        "- **BEHAVIORAL_PATTERN** → Behavioral Pattern Data\n"
        "- **POLITICAL_CASE** → Political-Related Cases\n"
        "- **ECONOMIC_STATUS** → Economic Information\n"
        "- **POSTAL_CODE** → Norwegian Postal Codes\n\n"
        "### **Expected JSON Output Format:**\n"
        "{\n"
        '  "text_input": "Original text...",\n'
        '  "output": {\n'
        '    "PERSON": ["John Doe"],\n'
        '    "NO_ADDRESS": ["123 Main St"],\n'
        '    "POSTAL_CODE": ["12345"],\n'
        '    "NO_PHONE_NUMBER": ["123-456-7890"],\n'
        '    "EMAIL_ADDRESS": ["john.doe@email.com"],\n'
        '    "GOV_ID": ["12345678901"],\n'
        '    "EMPLOYMENT_INFO": ["Works as a teacher"]\n'
        "  }\n"
        "}\n"
        "**Ensure that the response is valid JSON without any Markdown syntax.**\n"
        f"Text: {text}"
    )

    model = genai.GenerativeModel("gemini-1.5-pro")
    response = model.generate_content(prompt)
    return response.text

# Main worker functions
def generator_worker():
    """Thread function to generate inspection reports"""
    print("Starting generator worker...")
    while running:
        try:
            scenario = random.choice(report_scenarios)

            prompt = (
                f"Generate an expanded Norwegian inspection report example based explicitly on this scenario: {scenario}. "
                "The report should mirror the structure, tone, and formatting typically used by Mattilsynet. "
                "Include realistic, detailed, but entirely fictional sensitive personal data clearly covering: "
                "Name, full address, Norwegian postal code; realistic Norwegian phone number; email address; government-issued ID numbers; "
                "specific health conditions (e.g., diabetes type 2, chronic depression); religious beliefs; detailed economic figures (e.g., debts exceeding 500,000 NOK, falsified tax documents); "
                "criminal history including specific crimes; political affiliations; sexual orientation or personal scandals; family and relationship details; and any weapon-related incidents. "
                "Clearly specify the inspected facility or type."
                "Title: 'Inspeksjonsrapport med skriftlig veiledning'"
                "Sections: Name, address, postal code, 'Deres ref:', 'Vår ref:', date, org.nr.; Inspeksjonen omfattet; "
                "Oppsummering (detailed summary of observations); Vår rett til å føre tilsyn og fatte nødvendige vedtak; "
                "Skriftlig veiledning ved regelverksbrudd (with subsections clearly stated as: "
                "'Vi har observert:', 'Kravene som gjelder:', 'Mattilsynet vurderer det slik:', 'Regelverket som veiledningen bygger på:'). "
                "Important: Start and end your generated text with [ text ]. Every generation must be unique, realistic, and avoid common placeholder names like 'Ola Nordmann'."
            )

            system_instruction = (
                "You generate fictional yet realistic Norwegian inspection reports following precise Mattilsynet templates. "
                "Always include rich, detailed, fictional sensitive personal information within context."
            )

            generated_text = generate_text(prompt, system_instruction)

            timestamp = int(time.time())
            txt_filename = f"inspeksjonsrapport_{timestamp}.txt"
            filepath = save_to_txt(generated_text, txt_filename)

            print(f"Generated inspection report saved to {filepath}")

            # Wait to not overwhelm the API
            time.sleep(5)

        except Exception as e:
            print(f"Error in generator: {e}")
            time.sleep(5)

def labeler_worker():
    """Thread function to label inspection reports"""
    print("Starting labeler worker...")

    # Give the generator a head start
    time.sleep(10)

    while running:
        try:
            txt_files = get_all_txt_files()

            if not txt_files:
                print("No files to process. Waiting...")
                time.sleep(10)
                continue

            # Process the oldest file
            txt_file = txt_files[0]
            file_path = os.path.join(DATA_FOLDER, txt_file)

            with open(file_path, 'r', encoding='utf-8') as file:
                report_text = file.read().strip()

            print(f"Labeling: {file_path}")
            raw_labeled_data = extract_sensitive_data(report_text)
            labeled_data = clean_json_response(raw_labeled_data)

            if "error" in labeled_data:
                print("Error in response:", labeled_data["error"])
                # Move to next file
                continue

            # Convert to JSONL format with proper Unicode encoding
            jsonl_entry = json.dumps({
                "text_input": labeled_data.get("text_input", "").encode("utf-8").decode("utf-8"),
                "output": labeled_data.get("output", {})
            }, ensure_ascii=False)  # Ensure readable characters (å, ø, æ, etc.)

            training_file = os.path.join(TRAINING_FOLDER, "inspeksjonsrapport.jsonl")

            # Append to training file
            with open(training_file, 'a', encoding='utf-8') as file:
                file.write(jsonl_entry + '\n')

            print(f"Labeled training data saved to {training_file}")

            # Move processed file to processed folder
            os.rename(file_path, os.path.join(PROCESSED_FOLDER, txt_file))
            print(f"Moved processed file to {PROCESSED_FOLDER}")

            # Wait between API calls to avoid rate limiting
            time.sleep(5)

        except Exception as e:
            print(f"Error in labeler: {e}")
            time.sleep(5)


if __name__ == "__main__":
    print("Starting inspection report generation and labeling system...")
    print(f"Data will be stored in: {DATA_FOLDER}")
    print(f"Labeled data will be stored in: {TRAINING_FOLDER}")

    # Start threads
    generator_thread = threading.Thread(target=generator_worker)
    labeler_thread = threading.Thread(target=labeler_worker)

    generator_thread.daemon = True
    labeler_thread.daemon = True

    generator_thread.start()
    labeler_thread.start()

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)