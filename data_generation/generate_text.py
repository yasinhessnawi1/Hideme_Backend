import os
import re
import time
import random

from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backend', '.env'))

# Configuration
API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=API_KEY)

DATA_FOLDER = os.path.join(os.path.dirname(__file__), 'data')

if not os.path.exists(DATA_FOLDER):
    os.makedirs(DATA_FOLDER)


def generate_text(prompt, system_instruction):
    model = genai.GenerativeModel("gemini-1.5-pro", system_instruction=system_instruction)
    response = model.generate_content(prompt)
    return response.text


def save_to_txt(text, filename):
    cleaned_text = clean_response(text)
    with open(os.path.join(DATA_FOLDER, filename), 'w', encoding='utf-8') as file:
        file.write(cleaned_text)


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


def clean_response(text):
    # Remove [text] at the beginning and end
    text = re.sub(r'^\[\s*|\s*\]$', '', text.strip())
    # Remove all occurrences of '**'
    text = re.sub(r'\*\*', '', text)
    return text.strip()


def main():
    while True:  # Run indefinitely
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
            cleaned_text = clean_response(generated_text)

            timestamp = int(time.time())
            txt_filename = f"inspection_report_{timestamp}.txt"
            save_to_txt(cleaned_text, txt_filename)

            print(f"Report saved to {txt_filename}")

        except Exception as e:
            print(f"Error: {e}")

        # Wait for 5 seconds before the next request
        time.sleep(5)

if __name__ == "__main__":
    main()




#todo: copy this script and make it generate bekjymringsmeldinger