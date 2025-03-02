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
# Ensure the fisk_data folder exists
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

def countfiles():
    count = 0
    for filename in os.listdir(DATA_FOLDER):
        if filename.lower().endswith('.pdf'):
            count += 1
    return count

prompt = (
            "Generate an expanded Norwegian inspection report example. The report should mirror the structure, "
            "tone, and formatting of a typical inspection report. It must include sensitive information such as "
            "fake health situation, fake personal fisk_data, fake religious beliefs, fake private life details, fake family and membership fisk_data, "
            "fake financial information. The report should be adaptable to "
            "various exapmle templates Mattilsynet inspections, including Food Safety, Animal Welfare, Plant Health, Food Processing, "
            "Cosmetics, and Medicines Regulation, choose very randomly. Ensure all missing fields are filled appropriately with fake fisk_data. "
            "Include the following sections with fake fisk_data: Name, address, postal code, 'Deres ref:', 'Vår ref:', date, and org.nr. "
            "Title: 'Inspeksjonsrapport med skriftlig veiledning.' Inspeksjonen omfattet: Clearly state the inspected "
            "facility/type. Oppsummering: A detailed, expanded, and connected text description covering observations "
            "on animal health, hygiene, documentation, facility conditions, and interactions with the owner/staff. "
            "Include a list of control. Vår rett til å føre tilsyn og fatte nødvendige vedtak. Skriftlig veiledning ved "
            "regelverksbrudd: 'Vi har observert:' Provide an in-depth, expanded explanation of observed violations "
            "(e.g., inadequate animal welfare in farming, violations related to food safety, hygiene failures, and "
            "'Kravene som gjelder:' Describe the requirements that apply for "
            "the observed violation. 'Mattilsynet vurderer det slik:' Explain how Mattilsynet assesses the observed "
            "violation. 'Regelverket som veiledningen bygger på:' List the regulations on which the guidance is based "
            "for the observed violation. All the information should be generated and formatted to fit well in a PDF file."
            " **Important:** This is a purely fictional example. The fisk_data should be fabricated, It is for demonstration purposes only."
            "** Important Only generate and output the text, no additional processing, clarification is required.**"
            "** Important the text related to the report should start and end with [[ text ]] and the text in middle as shown**"
            "** Important use fictional fisk_data but make them not very basic, dont use ola Nordmann as name, you can come up with much batter fake fisk_data**"
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
        system_instruction = """Named Entity Recognition (NER) generation. You are a fictive fisk_data generator that helps users generate fisk_data based on their requirements specified in the prompt. this is an example of a pdf file of Mattilsynet's inspection report to follow, but the stories and the data should be changed and varied, be creative each time with the story.**ØSTDAHL SIMEN VIEN 
Lyngheivegen 15 
2618 LILLEHAMMER 
Inspeksjonsrapport med skriftlig veiledning 
Vi viser til inspeksjon hos deg den 27. oktober 2024.  
Deres ref: 
Vår ref: 
Dato: 
Org.nr: 
TESTDOKUMENT 
2025/12345678 
01.01.2025 
985399077 
Førsteinspektør Synnøve Goli Ellingstad og seniorinspektør Jeanett Lofthagen gjennomførte 
inspeksjonen. Simen Vien Østdahl var til stede. 
Inspeksjonen omfattet 
• Geitehold, Produsentnummer 1234567890 
Oppsummering 
Skrapesjuketilsyn er en obligatorisk offentlig kontroll. Alle småfebesetninger skal inspiseres 
minst hvert tiende år. Hovedinnholdet i dette tilsynet er informasjon om skrapesjuke, kontroll 
av journaler og helseopplysninger, TSE-prøver og eventuelle forflytninger av livdyr. Ingen av 
dyra dine viste tegn til skrapesjuke. Du fikk utdelt faktaark om skrapesjuke under tilsynet. 
Merketilsyn skal gjennomføres på 3 % av alle småfebesetninger hvert år. Noen av dyra dine 
var ikke merket i henhold til regelverket, men du rettet opp dette umiddelbart etter tilsynet. 
Du hadde merker liggende og bestilte hvite merker til geitene som manglet det. Du har ikke 
sendt oss dokumentasjon på at du har egenerklæring og veterinærattest på dyrene dine. Vi 
veileder deg derfor om regelverkskravene når det gjelder dette. 
• Oppbevaring av veterinærattester 
og egenerklæring av flytting av 
dyr 
• Merking av sau og geit 
• Krav til transportdokument sau og 
geit 
• Skrapsjuketilsyn 
Skriftlig veiledning
 Ingen oppfølging
 Ingen oppfølging
 Ingen oppfølging
 Mattilsynet 
Dette er en test-rapport, og 
inneholder ingen ekte 
informasjon. 
Postadresse:  
Saksbehandler: Jeanett Lofthagen 
Tlf: 22 40 00 00 
E-post: postmottak@mattilsynet.no 
(Husk mottakers navn) 
Felles postmottak, Postboks 383 
2381 Brumunddal 
Deres ref. TESTDOKUMENT — Vår ref. 2025/12345678— Dato: 01.01.2025 
Vi viser også til skjema «Bekreftelse på gjennomført tilsyn» datert 12. desember 2024. Der 
har vi gjengitt observasjonene vi gjorde under inspeksjonen. 
Vår rett til å føre tilsyn og fatte nødvendige vedtak 
Mattilsynets adgang til å føre tilsyn og fatte nødvendige vedtak følger av matloven § 23 og 
dyrevelferdsloven § 30.  
Se også vedlegg om rettigheter og regelverk. 
Skriftlig veiledning ved regelverksbrudd 
Vi veileder om veterinærattest og egenerklæring ved flytting av geit. 
Vi har observert: 
Du fant ikke egenerklæringer og veterinærattestene til dyrene dine da vi var på tilsyn. Du 
skulle ettersende det når du hadde funnet det frem, eller få tak i papirene fra 
opprinnelsesbesetning. Vi har ikke mottatt dokumentasjon per i dag. Da vi ringte i etterkant 
av tilsynet kom vi kun i kontakt med din kone Vera, som heller ikke kunne bistå. 
Kravene som gjelder for egenerklæring og veterinærattest 
Den driftsansvarlige skal sikre at veterinærattester og egenerklæringer, som kreves ved 
flytting av storfe, sauer, geiter, svin eller dyr av kamelfamilien i Norge, oppbevares i journalen 
på mottakeranlegget. 
Mattilsynet vurderer det slik 
Du har ikke ettersendt dokumentasjon på egenerklæring på dyrene dine enda. 
Når du ikke har fremvist egenerklæring og veterinærattest på dyrene du har i besetningen, 
mener vi at det utgjør et regelbrudd. Dette er dessverre også et gjentagende brudd. Vi har 
ved gjentatte tidligere tilsyn ikke dokumentert veterinærattester. Du har tidligere skyldt på 
dårlig økonomi og at utgiftene ved veterinær til for eksempel dokumentasjon ved forflytning 
ikke har vært prioritert. 
Du har selv ansvaret for å følge det regelverket som gjelder for virksomheten deres. Når 
Mattilsynet finner brudd på regelverket, skal vi bruke de reaksjonene som er nødvendige for 
å sikre at regelverket følges. I dette tilfellet mener vi det er tilstrekkelig å veilede skriftlig om 
regelverksbrudd fordi du seier du ønsker å følge regelverket som gjelder og har forsøkt å 
framskaffe dokumentasjon. 
Regelverket som veiledningen bygger på 
Vi mener at vi har funnet brudd på landdyrsporbarhetsforskriften § 14 Journalføring av visse 
dokumenter for storfe, sauer, geiter, svin, dyr av kamelfamilien, rein og hestedyr 
Med hilsen 
Karl Ove Stadheim Jensen 
avdelingssjef 
Dette dokumentet er elektronisk godkjent og sendes uten signatur.  
Dokumenter som må ha signatur blir i tillegg sendt i papirversjon.  """
        response_text = generate_text(prompt, system_instruction)
        save_to_pdf(response_text, f"inspection_report{time.time()}.pdf")
        print(f"Generated inspection_report{time.time()}.pdf")
        manageFiles()
        print(countfiles())

if __name__ == "__main__":
    main()

