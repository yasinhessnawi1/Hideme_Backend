GEMINI_PROMPT_HEADER = """### **Task: Extract and Anonymize Sensitive Data in JSON Format
Analyze the following inspection report text and extract all sensitive information (as defined by GDPR and other privacy laws).

### **Task Requirements:**
- **Identify, tokenize, and assign NER tags** for each detected sensitive item.
- **Anonymize the sensitive data** using placeholder tags.
- **Use the BIO scheme** for Named Entity Recognition (NER) tags.
- **Ensure JSON output matches the required format** (see below).

## **🛑 Named Entity Categories (NER Tags)**
Assign the correct **BIO-based entity tags** to each detected item:
Each detected sensitive item must be tagged with the correct entity type:
detect only and only the entities listed below:

"""

# Gemini prompt template footer
GEMINI_PROMPT_FOOTER = """
---
### **✅ JSON Output Format**
Immediately return a structured JSON output in the following format:

{
  "pages": [
    {
      "text": [
        {
          "entities": [
            {
              "entity_type": "ORG", // Mattilsynet // <ORG>
              "start": 0,  // index of word in the total text
              "end": 11,   // index of word in the total text
              "score": 0.996
            }
          ]
        },
        {
          "entities": [
            {
              "entity_type": "HEALTH_INFO", // Diagnose: Diabetes Type 1 // Diagnose: <HEALTH_INFO>
              "start": 25, // index of word in the total text
              "end": 44, // index of word in the total text
              "score": 0.98
            }
          ]
        }
      ]
    }
  ]
}

**IMPORTANT:** 
🔹 Additional Requirements
Output JSON only: Do not include any additional text, explanations, or formatting.
Ensure correct entity tagging: Each detected entity must be anonymized with a placeholder.
Preserve structure and accuracy: Maintain the correct JSON format while anonymizing detected information.
Confidence scores: Assign a confidence score (between 0 and 1) for each extracted entity.
🔹 Example Output
json
Copy
{
  "pages": [
    {
      "text": [
        {
          "entities": [
            {
              "entity_type": "HEALTH_INFO",
              "original_text": "hjertesykdom",
              "start": 456,
              "end": 469,
              "score": 0.98
            }
          ]
        }
      ]
    }
  ]
}

"""
GEMINI_AVAILABLE_ENTITIES = {"PHONE": "- ** NO_PHONE_NUMBER ** → Norwegian Phone Numbers",
                        "PERSON": "- ** PERSON ** → Norwegian Names",
                        "EMAIL": "- ** EMAIL_ADDRESS ** → Email Addresses",
                        "ADDRESS": "- ** NO_ADDRESS ** → Norwegian Home/street Addresses",
                        "DATE": "- ** DATE_TIME ** → Dates and Timestamps",
                        "GOVID": "- ** GOV_ID ** → Government - Issued Identifiers any identification number",
                        "FINANCIAL": "- ** FINANCIAL_INFO ** → Financial Data (contextually financial fisk_data not just words about money)",
                        "EMPLOYMENT": "- ** EMPLOYMENT_INFO ** → Employment and Professional Details",  #todo: fix this entity and add organization
                        "HEALTH": "- ** HEALTH_INFO ** → Health - Related Information",
                        "SEXUAL": "- ** SEXUAL_ORIENTATION ** → Sexual Relationships and Orientation",
                        "CRIMINAL": "- ** CRIMINAL_RECORD ** → Crime - Related Information",
                             "CONTEXT": "- ** CONTEXT_SENSITIVE ** → Context - Sensitive Information",
                             "FAMILY": "- ** FAMILY_RELATION ** → Family and Relationship Data",
                             "BEHAVIORAL_PATTERN": "- ** BEHAVIORAL_PATTERN ** → Behavioral Pattern Data",
                             "POLITICAL_CASE": "- ** POLITICAL_CASE ** → Political - Related Cases",
                             "ECONOMIC_STATUS": "- ** ECONOMIC_STATUS ** → Economic Information",

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
