import os
import json
import re
import time
import google.generativeai as genai
from dotenv import load_dotenv

# Load API Key
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backend', '.env'))
API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=API_KEY)

# Directory setup
DATA_FOLDER = os.path.join(os.path.dirname(__file__), 'data')
TRAINING_FOLDER = os.path.join(os.path.dirname(__file__), 'training_data')

if not os.path.exists(TRAINING_FOLDER):
    os.makedirs(TRAINING_FOLDER)

# Track processed files to avoid reprocessing
processed_files = set()


def get_next_unprocessed_file():
    """Get the next unprocessed .txt file from the data folder, sorted by creation time."""
    txt_files = [f for f in os.listdir(DATA_FOLDER) if f.endswith('.txt') and f not in processed_files]
    if not txt_files:
        return None

    # Sort by creation time (oldest first)
    txt_files.sort(key=lambda f: os.path.getctime(os.path.join(DATA_FOLDER, f)))
    return txt_files[0]


def clean_json_response(response_text):
    """Clean and parse the API response JSON."""
    cleaned_text = re.sub(r"```json\s*|\s*```", "", response_text).strip()

    try:
        data = json.loads(cleaned_text)
        if "text_input" in data and data["text_input"].endswith("["):
            data["text_input"] = data["text_input"].rstrip("[")
        return data
    except json.JSONDecodeError as e:
        print("JSON Decode Error:", e)
        return {"error": "Invalid response from Gemini"}


def extract_sensitive_data(text):
    """Send text to Gemini API to extract and label sensitive data in structured format."""
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
        "- **FINANCIAL_INFO** → Financial Data (contextually financial fisk_data, not just words about money)\n"
        "- **EMPLOYMENT_INFO** → Employment and Professional Details\n"
        "- **HEALTH_INFO** → Health-Related Information\n"
        "- **SEXUAL_ORIENTATION** → Sexual Relationships and Orientation\n"
        "- **CRIMINAL_RECORD** → Crime-Related Information\n"
        "- **CONTEXT_SENSITIVE** → Context-Sensitive Information\n"
        "- **IDENTIFIABLE_IMAGE** → Any Identifiable Image Reference\n"
        "- **FAMILY_RELATION** → Family and Relationship Data\n"
        "- **BEHAVIORAL_PATTERN** → Behavioral Pattern Data\n"
        "- **POLITICAL_CASE** → Political-Related Cases\n"
        "- **ECONOMIC_STATUS** → Economic Information\n\n"
        "### **Expected JSON Output Format:**\n"
        "{\n"
        '  "text_input": "Original text...",\n'
        '  "output": {\n'
        '    "PERSON": ["John Doe"],\n'
        '    "NO_ADDRESS": ["123 Main St"],\n'
        '    "POSTAL_CODE": "12345",\n'
        '    "NO_PHONE_NUMBER": "123-456-7890",\n'
        '    "EMAIL_ADDRESS": "john.doe@email.com",\n'
        '    "GOV_ID": "12345678901",\n'
        '    "FINANCIAL_INFO": ["500,000 NOK"],\n'
        '    "CRIMINAL_RECORD": ["Fraud Conviction"],\n'
        '    "HEALTH_INFO": ["Diabetes Type 2"],\n'
        '    "POLITICAL_CASE": "Member of Party X",\n'
        '    "FAMILY_RELATION": ["Spouse: Jane Doe"],\n'
        '    "ECONOMIC_STATUS": "Debt of 500,000 NOK"\n'
        "  }\n"
        "}\n"
        "**Ensure that the response is valid JSON without any Markdown syntax.**\n"
        f"Text: {text}"
    )

    model = genai.GenerativeModel("gemini-1.5-pro")

    try:
        response = model.generate_content(prompt)
        raw_response = response.text
        print("Raw API Response:", raw_response)

        # Attempt to clean up gRPC resources to prevent timeout error
        if hasattr(model, "_client") and hasattr(model._client, "close"):
            try:
                model._client.close()
            except Exception as e:
                print(f"Error closing gRPC client: {e}")

        return clean_json_response(raw_response)
    except Exception as e:
        print(f"API Error: {e}")
        return {"error": f"API Error: {str(e)}"}


def process_file(filename):
    """Process a single file and save the labeled data to training_data.jsonl."""
    file_path = os.path.join(DATA_FOLDER, filename)

    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            report_text = file.read().strip()

        print(f"Processing: {file_path}")
        labeled_data = extract_sensitive_data(report_text)

        if "error" in labeled_data:
            print(f"Error in response for {filename}: {labeled_data['error']}")
            return False

        # Convert to JSONL format with proper Unicode encoding
        jsonl_entry = json.dumps({
            "text_input": labeled_data.get("text_input", "").encode("utf-8").decode("utf-8"),
            "output": labeled_data.get("output", {})
        }, ensure_ascii=False)  # Ensure readable characters (å, ø, æ, etc.)

        training_file = os.path.join(TRAINING_FOLDER, "training_data.jsonl")

        # Append to training file
        with open(training_file, 'a', encoding='utf-8') as file:
            file.write(jsonl_entry + '\n')

        print(f"Labeled training data saved to {training_file}")

        # Mark file as processed
        processed_files.add(filename)
        return True

    except Exception as e:
        print(f"Error processing file {filename}: {str(e)}")
        return False


def continuous_processing(wait_time=30):
    """Continuously process files from the data folder."""
    print(f"Starting continuous processing. Checking for new files every {wait_time} seconds.")
    print(f"Monitoring folder: {DATA_FOLDER}")
    print(f"Saving labeled data to: {TRAINING_FOLDER}")

    while True:
        try:
            filename = get_next_unprocessed_file()

            if not filename:
                print(f"No new files to process. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
                continue

            success = process_file(filename)

            # Small pause between files to avoid rate limiting
            time.sleep(2)

        except KeyboardInterrupt:
            print("Process interrupted by user. Exiting.")
            break
        except Exception as e:
            print(f"Unexpected error in processing loop: {str(e)}")
            # Continue despite errors to maintain continuous operation
            time.sleep(5)


if __name__ == "__main__":
    continuous_processing()