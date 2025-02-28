import os
import shutil
import time

from fpdf import FPDF
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backend', '.env'))

# Configuration
API_KEY = os.getenv("GOOGLE_GENAI_API_KEY")
PRIVATE_AI_API_KEY = os.getenv("PRIVATE_AI_API_KEY")
DATA_FOLDER = os.path.join(os.path.dirname(__file__), 'data')
genai.configure(api_key=API_KEY)
# Ensure the data folder exists
if not os.path.exists(DATA_FOLDER):
    os.makedirs(DATA_FOLDER)


def generate_text(prompt, system_instruction):
    model = genai.GenerativeModel("gemini-1.5-pro", system_instruction=system_instruction)
    response = model.generate_content(prompt)
    text = response.text
    # Extract content starting from "```" to the end
    return text


def save_to_pdf(text, filename):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    # Extract the provided text and write it to the PDF using multi_cell to ensure line wrappin
    text = text.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 10, text)
    pdf.output(os.path.join(DATA_FOLDER, filename))

prompt = (
            "Generate an expanded Norwegian inspection report example. The report should mirror the structure, "
            "tone, and formatting of a typical inspection report. It must include sensitive information such as "
            "fake health situation, fake personal data, fake religious beliefs, fake private life details, fake family and membership data, "
            "fake financial information. The report should be adaptable to "
            "various exapmle templates Mattilsynet inspections, including Food Safety, Animal Welfare, Plant Health, Food Processing, "
            "Cosmetics, and Medicines Regulation. Ensure all missing fields are filled appropriately with fake data. "
            "Include the following sections with fake data: Name, address, postal code, 'Deres ref:', 'Vår ref:', date, and org.nr. "
            "Title: 'Inspeksjonsrapport med skriftlig veiledning.' Inspeksjonen omfattet: Clearly state the inspected "
            "facility/type. Oppsummering: A detailed, expanded, and connected text description covering observations "
            "on animal health, hygiene, documentation, facility conditions, and interactions with the owner/staff. "
            "Include a list of control. Vår rett til å føre tilsyn og fatte nødvendige vedtak. Skriftlig veiledning ved "
            "regelverksbrudd: 'Vi har observert:' Provide an in-depth, expanded explanation of observed violations "
            "(e.g., inadequate animal welfare in farming, violations related to food safety, hygiene failures, and "
            "insufficient fish welfare in aquaculture). 'Kravene som gjelder:' Describe the requirements that apply for "
            "the observed violation. 'Mattilsynet vurderer det slik:' Explain how Mattilsynet assesses the observed "
            "violation. 'Regelverket som veiledningen bygger på:' List the regulations on which the guidance is based "
            "for the observed violation. All the information should be generated and formatted to fit well in a PDF file."
            " **Important:** This is a purely fictional example. The data should be fabricated, It is for demonstration purposes only."
            "** Important Only generate and output the text, no additional processing, clarification is required.**"
            "** Important the text related to the report should start and end with [[ text ]] and the text in middle as shown**"
            "** Important use fictional data but make them not very basic, dont use ola Nordmann as name, you can come up with much batter fake data**"
        )
def manageFiles():
    # Define folders
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    ready_data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ready_data')

    # Create ready_data directory if it doesn’t exist
    if not os.path.exists(ready_data_dir):
        os.makedirs(ready_data_dir)

    # Check for matching .pdf and .txt files
    pdf_files = {os.path.splitext(f)[0] for f in os.listdir(data_dir) if f.endswith('.pdf')}
    txt_files = {os.path.splitext(f)[0] for f in os.listdir(data_dir) if f.endswith('.txt')}
    matching_files = pdf_files & txt_files

    # Move matching files to ready_data directory
    for match in matching_files:
        pdf_path = os.path.join(data_dir, f"{match}.pdf")
        txt_path = os.path.join(data_dir, f"{match}.txt")
        shutil.move(pdf_path, os.path.join(ready_data_dir, f"{match}.pdf"))
        shutil.move(txt_path, os.path.join(ready_data_dir, f"{match}.txt"))
        print(f"Moved {match}.pdf and {match}.txt to ready_data directory.")


def main():
    while True:
        system_instruction = "Named Entity Recognition (NER) generation. You are a fictive data generator that helps users generate data based on their requirements specified in the prompt."
        response_text = generate_text(prompt, system_instruction)
        save_to_pdf(response_text, f"inspection_report{time.time()}.pdf")
        print(f"Generated inspection_report{time.time()}.pdf")
        manageFiles()

if __name__ == "__main__":
    main()

