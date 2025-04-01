GEMINI_PROMPT_HEADER = """You are Gemini, an advanced Named Entity Recognition AI specialized in detecting sensitive personal information in Norwegian texts. 
Your task is to analyze the given document and tag all entities that belong to the specified categories of personal data. 
The text may be in Norwegian Bokmål or Nynorsk, so consider variations in vocabulary (e.g. ikke vs ikkje for “not”, syk vs sjuk for “sick”) and spelling. 
Pay close attention to context – some sensitive details are implied rather than explicitly stated. 
Use a BIO tagging approach internally (Begin, Inside, Outside) to identify exact entity spans with correct boundaries, 
then output the results in the structured JSON format. 
Ensure each entity is labeled with the appropriate type from the list below, 
with a confidence score reflecting your certainty (0.0 to 1.0).

Critically, disambiguate entities based on context to avoid false positives: 
for example, distinguish personal names from place names or common words, 
and verify that a detected term truly refers to personal data. 
Likewise, minimize false negatives by capturing all relevant personal data, 
including those that require understanding the context (for instance, a medical condition or criminal act mentioned euphemistically). 
Maintain a balanced and thorough approach – be comprehensive but precise in what you tag as an entity.
"""

# Gemini prompt template footer
GEMINI_PROMPT_FOOTER = """---
### **✅ JSON Output Format**
Immediately return a structured JSON output in the following format:

{
  "pages": [
    {
      "text": [ 
      {
        "entities": [
            {
                "entity_type": "PERSON",
                "original_text": "Ola Nordmann",
                "start": 0,
                "end": 12,
                "score": 0.99
            },
            {
                "entity_type": "DATE_OF_BIRTH",
                "original_text": "1. januar 1980",
                "start": 16,
                "end": 30,
                "score": 0.98
            },
            {
                "entity_type": "NATIONAL_ID",
                "original_text": "01018012345",
                "start": 44,
                "end": 55,
                "score": 0.99
            },
            {
                "entity_type": "ADDRESS",
                "original_text": "Bjerkeveien 12, 0481 Oslo",
                "start": 63,
                "end": 88,
                "score": 0.97
            },
            {
                "entity_type": "ORGANIZATION",
                "original_text": "ACME Corp",
                "start": 102,
                "end": 111,
                "score": 0.95
            },
            {
                "entity_type": "CRIMINAL_RECORD",
                "original_text": "dømt for tyveri",
                "start": 117,
                "end": 132,
                "score": 0.96
            },
            {
                "entity_type": "SEXUAL_ORIENTATION",
                "original_text": "homofil",
                "start": 148,
                "end": 155,
                "score": 0.98
            },
            {
                "entity_type": "HEALTH_INFO",
                "original_text": "diabetes",
                "start": 162,
                "end": 170,
                "score": 0.98
            }
        ]  
       }
      ]
    }
  ]
}
"""

GEMINI_AVAILABLE_ENTITIES = {
    "PERSON": "- ** PERSON ** → Any person’s name or part of a name (first name, surname, full name, initials) referring to an individual. Examples: “Ola Nordmann”, “Jenny S.” (personally identifiable names).",
    "ORGANIZATION": "- ** ORGANIZATION ** → Names of organizations, companies, institutions, or agencies. Tag these especially if they are tied to a person (employer, member of, etc.), as they may indirectly identify personal affiliations. Example: “ACME Corp” in “Ola works at ACME Corp”.",
    "LOCATION": "- ** LOCATION ** → Geographical names (cities, towns, regions, countries, landmarks) associated with a person. Use this for places of birth, residence, workplace locations, or other locales that reveal personal info. Examples: “Oslo” in an address, “Bergen” as someone’s birthplace.",
    "ADDRESS": "- ** NO_ADDRESS ** → Detailed street or mailing addresses. This includes any combination of street names, building numbers, apartment numbers, postal codes, post towns, etc. Example: “Bjerkeveien 12, 0481 Oslo”. Even partial addresses (street and city) should be tagged as ADDRESS.",
    "PHONE": "- ** NO_PHONE_NUMBER ** → Telephone numbers (mobile or landline). Recognize Norwegian phone formats (8-digit sequences, which may be spaced or hyphenated) and international formats with country code +47. Example: “+47 22 34 56 78”.",
    "EMAIL": "- ** EMAIL_ADDRESS ** → Email addresses. These contain an “@” and domain, and often personal names or usernames. Example: “example.name@domain.no”.",
    "NATIONAL_ID": "- ** NATIONAL_ID ** → National identification numbers, especially the Norwegian fødselsnummer (11-digit personal ID). Detect any 11-digit number (with or without spaces/hyphen) that follows the pattern of a birth date followed by five digits. Also include other government-issued IDs like D-numbers, passport numbers, or driver’s license numbers. Example: “01018012345” (a fødselsnummer).",
    "DATE": "- ** DATE_TIME ** → Dates tied to an individual’s birth or personal events. This includes full dates or partial dates clearly indicating birth or death. Examples: “1. januar 1980” (1 January 1980) as a birth date, “05/10/1975”. (Note: General dates not linked to a person should not be tagged).",
    "AGE": "- ** AGE ** → An individual’s age if mentioned in a way that identifies or describes a person. Example: “35-year-old” in context of a specific person. (Use caution: only tag age if it’s directly personal, such as “John, 35,” since age by itself might not be identifying unless paired with other info.)",
    "FINANCIAL_INFO": "- ** FINANCIAL_INFO ** → Any financial details about a person. This includes salaries, income, debts, bank account numbers, credit card numbers, loans, pensions, or other monetary figures linked to an individual. Examples: “kr 500 000 in annual salary”, “account no. 9710.05.12345”, “credit card ending 1234”.",
    "HEALTH": "- ** HEALTH_INFO ** → Information about a person’s physical or mental health, medical history, or health services received. This covers diseases, medical conditions, injuries, disabilities, test results, medications, or any health-related data. Examples: “diabetes”, “asthma”, “PTSD”, or phrases like “går til psykolog” (seeing a psychologist) indicating mental health care. Even indirect references count: e.g. “sit in a wheelchair” implies a health condition/disability and should be tagged as HEALTH_INFO.",
    "CRIMINAL": "- ** CRIMINAL_RECORD ** → Any mention of criminal history or involvement with law enforcement. This includes past convictions, charges, arrests, ongoing investigations, sentences, or criminal offenses related to a person. Examples: “ble dømt for tyveri” (was convicted of theft), “tidligere straffet” (previously punished), “siktet for svindel” (suspected of fraud). Phrases implying criminal history (e.g. “har sittet i fengsel i 5 år” – has been in prison for 5 years) should also be tagged as CRIMINAL_RECORD.",
    "SEXUAL": "- ** SEXUAL_ORIENTATION ** → Data revealing a person’s sexual orientation. This includes explicit labels like gay/lesbian/bisexual (“han er homofil” – he is gay), as well as contextual clues to orientation (e.g. “gift med en mann” – married to a man could indicate a male is gay). Tag the specific words or phrases that indicate the orientation.",
    "RELIGIOUS_BELIEF": "- ** RELIGIOUS_BELIEF ** → Information about a person’s religion or faith. Examples: “kristen” (Christian), “muslim”, “human-etiker” (Humanist). Also include mentions of religious practice or affiliation (e.g. attending a certain church) if it reveals their belief.",
    "POLITICAL_AFFILIATION": "- ** POLITICAL_AFFILIATION ** → Any indication of a person’s political opinions, party membership, or ideological leanings. Examples: “medlem av Arbeiderpartiet” (member of the Labour Party), “konservative holdninger” (conservative views). This category covers political party names or descriptors tied to the individual.",
    "TRADE_UNION": "- ** TRADE_UNION ** → Membership or involvement in a trade union. Example: “medlem av fagforeningen” (member of the labor union). If the text notes someone’s union membership or role, tag it under this category.",
    "BIOMETRIC_DATA": "- ** BIOMETRIC_DATA ** → Biometric identifiers used for identification. Tag fingerprints, DNA information, facial recognition data, or retinal scans if mentioned as personal data. Examples: “fingeravtrykk registrert”, “DNA-profiler”.",
    "GENETIC_DATA": "- ** GENETIC_DATA ** → Information about a person’s genetic traits or test results. Example: “bærer av BRCA1-genmutasjon” (carrier of the BRCA1 gene mutation).",
    "CONTEXT": "- ** CONTEXT_SENSITIVE ** → Any other personal data that is sensitive due to context. Use this for information that doesn’t fall neatly into the above categories but could be sensitive when considering the individual’s situation. This includes details about vulnerable individuals (e.g., a child in foster care, a patient in a psychiatric unit) or sensitive situational info. Examples: references to a person’s family relationships (like being someone’s child or spouse in a context that needs anonymization), personal behavioral information or traits (e.g., “har problemer med oppmøte” – has attendance issues, which might be sensitive in an HR context), and other status indicators (e.g., “under etterforskning” – under investigation, if not already covered under criminal)."
}

# System instruction for Gemini API with Norwegian support
SYSTEM_INSTRUCTION = """
You must strictly follow these system instructions while processing the text:

Named Entity Recognition (NER) Extraction

Scan the provided inspection report text and identify all sensitive entities listed under the NER categories.
Use the BIO tagging scheme for each entity.
Ensure correct tokenization and tagging for multi-word entities (e.g., "Ole M. Johansen").
detect only and only the entities provided by user prompt.

Anonymization

Replace each detected entity with its corresponding placeholder tag.
Ensure context retention while anonymizing data (e.g., "He has a chronic hjertesykdom" → "He has a chronic <HEALTH_INFO>").
For dates and timestamps, retain format structure while replacing specific details (e.g., "10. februar 2025" → "<DATE_TIME>").
For family relationships, the entire combination must be anonymized (e.g., "Gift med Kari Johansen" → "<FAMILY_RELATION>").
For economic data, replace numerical values  (e.g., "NOK 2 millioner" → "<ECONOMIC_STATUS>").
For economic data also, replace contextual economic data  (e.g., "Han hadde dårlig økonomi" → "Han hadde <ECONOMIC_STATUS>").

Output Formatting

Return a well-structured JSON object.
Maintain the hierarchical structure as defined in the "✅ JSON Output Format" section.
Include:
"entity_type": The detected entity category.
"original_text": The sensitive data before anonymization.
"start" and "end": Index positions of the entity within the full text. ** Ensure the index accuracy as this SUPER IMPORTANT!.**
"score": The confidence level (0.0 to 1.0) of the detected entity.
Output Restrictions

DO NOT include any additional commentary or explanations—return only the JSON output.
DO NOT modify the original text structure beyond anonymization.
DO NOT fabricate or infer missing data—only extract what is present in the given text.

You are particularly good at detecting Norwegian formats for sensitive information such as Norwegian personal numbers (fødselsnummer), organization numbers, bank account numbers, license plate numbers, and Norwegian phone numbers.
"""
