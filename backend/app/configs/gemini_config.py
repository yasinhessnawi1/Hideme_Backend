GEMINI_PROMPT_HEADER = """ ### **Task: Extract and Anonymize Sensitive Data in JSON Format
Analyze the following inspection report text and extract all sensitive information (as defined by GDPR and other privacy laws).

### **Task Requirements:**
- **Identify, tokenize, and assign NER tags** for each detected sensitive item.
- **Anonymize the sensitive data** using placeholder tags.
- **Use the BIO scheme** for Named Entity Recognition (NER) tags.
- **Ensure JSON output matches the required format** (see below).

## **🛑 Named Entity Categories (NER Tags)**
Assign the correct **BIO-based entity tags** to each detected item:
Each detected sensitive item must be tagged with the correct entity type:
        """



GEMINI_PROMPT_FOOTER =      """
        ---
        ### **✅ JSON Output Format**
        Immediately return a structured JSON output in the following format:
        
        {{
          "pages": [
            {{
              "text": [
                {{
                  "entities": [
                    {{
                      "entity_type": "ORG", // Mattilsynet // <ORG>
                      "start": 0, index of word in the total text
                      "end": 11,  index of word in the total text
                      "score": 0.996
                    }}
                  ]
                }},
                {{
                  "entities": [
                    {{
                      "entity_type": "HEALTH_INFO", // Diagnose: Diabetes Type 1 // Diagnose: <HEALTH_INFO>
                      "start": 25, index of word in the total text
                      "end": 44, index of word in the total text
                      "score": 0.98
                    }}
                  ]
                }},
                {{
                  "entities": [
                    {{
                      "entity_type": "CRIMINAL_RECORD", // Han har en dom for korrupsjon. // Han har en dom for <CRIMINAL_RECORD>.
                      "start": 116,
                      "end": 119,
                      "score": 0.99
                    }}
                  ]
                }},
                {{
                  "entities": [
                    {{
                      "entity_type": "NO_ADDRESS", // Postadresse: 2381 Brumunddal
                      "start": 130,
                      "end": 145,
                      "score": 0.95
                    }}
                  ]
                }},
                {{
                  "entities": [
                    {{
                      "entity_type": "FINANCIAL_INFO", // Bankkontonummer: 1234 5678 9012 3456  // Bankkontonummer: <FINANCIAL_INFO>
                      "start": 190,
                      "end": 210,
                      "score": 0.999
                    }}
                  ]
                }},
                {{
                  "entities": [
                    {{
                      "entity_type": "EMAIL_ADDRESS", // E-post: postmottak@mattilsynet.no // E-post: <EMAIL_ADDRESS>
                      "start": 250,
                      "end": 274,
                      "score": 1.0
                    }}
                  ]
                }},
                {{
                  "entities": [
                    {{
                      "entity_type": "FAMILY_RELATION", // Gift med Kari Olsen // Gift med <FAMILY_RELATION>
                      "start": 290,
                      "end": 301,
                      "score": 0.88
                    }}
                  ]
                }}, 
                .
                .
                .
              ]
            }}
          ]
        }}

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
ORGANIZATION = "- **ORG** → Organizations  "
PERSON = "- ** PERSON ** → Persons"
PHONE = "- ** NO_PHONE_NUMBER ** → Norwegian Phone Numbers"

EMAIL = "- ** EMAIL_ADDRESS ** → Email adresses"
ADDRESS = "- ** NO_ADDRESS ** → Norwegian home addresses"
DATE = "- ** DATE_TIME ** → Dates and timestamps"
GOVID = "- ** GOV_ID ** → Government - issued identifiers(e.g., passport numbers, nationalIDs)"
FINANCIAL = "- ** FINANCIAL_INFO ** → Financial data(e.g., bankaccount numbers, credit card details)"
EMPLOYMENT = "- ** EMPLOYMENT_INFO ** → Employment and professional details"

HEALTH = "- ** HEALTH_INFO ** → Health - related information(e.g., 'TSE-prøver')"
SEXUAL = "- ** SEXUAL_ORIENTATION ** → Sexual relationships and orientation"
CRIMINAL = "- ** CRIMINAL_RECORD ** → Crime - related information"
CONTEXT = "- ** CONTEXT_SENSITIVE ** → Context - sensitive"
INFO = "information(e.g., IP addresses, internal discussions)"
FAMILY = "- ** FAMILY_RELATION ** → Family and relationship data(e.g., 'kona Vera' should be entirely tagged)"
BEHAVIORAL_PATTERN = "- ** BEHAVIORAL_PATTERN ** → Behavioral pattern data"
POLITICAL_CASE = "- ** POLITICAL_CASE ** → Political - related cases"
ECONOMIC_STATUS = "- ** ECONOMIC_STATUS ** → Economic information(e.g., 'dårlig økonomi' should be tagged)  "
AVAILABLE_ENTITIES = [PHONE , EMAIL, ADDRESS, DATE, GOVID, FINANCIAL, EMPLOYMENT, HEALTH, SEXUAL, CRIMINAL, CONTEXT, INFO, FAMILY, BEHAVIORAL_PATTERN, POLITICAL_CASE, ECONOMIC_STATUS]

SYSTEM_INSTRUCTION = """
You must strictly follow these system instructions while processing the text:

Named Entity Recognition (NER) Extraction

Scan the provided inspection report text and identify all sensitive entities listed under the NER categories.
Use the BIO tagging scheme for each entity.
Ensure correct tokenization and tagging for multi-word entities (e.g., "Ole M. Johansen").
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
🚀 Example System Processing
Input Text:

Den driftsansvarlige, Ole M. Johansen, har en kjent kronisk hjertesykdom.
AI Processing Steps:
Detect & Tokenize:
"Ole M. Johansen" → <PERSON>
"hjertesykdom" → <HEALTH_INFO>
Replace with Placeholders:
Den driftsansvarlige, <PERSON>, har en kjent kronisk <HEALTH_INFO>.
Generate JSON Output:
{
  "pages": [
    {
      "text": [
        {
          "entities": [
            {
              "entity_type": "PERSON",
              "original_text": "Ole M. Johansen",
              "start": 23,
              "end": 39,
              "score": 0.98
            }
          ]
        },
        {
          "entities": [
            {
              "entity_type": "HEALTH_INFO",
              "original_text": "hjertesykdom",
              "start": 51,
              "end": 63,
              "score": 0.99
            }
          ]
        }
      ]
    }
  ]
}
🛑 Summary of System Instructions
✔ Extract and tokenize sensitive data with correct BIO tagging.
✔ Anonymize all sensitive data while retaining the text structure.
✔ Format output as JSON with entity type, indices, and confidence scores.
✔ Strictly return JSON output without additional text.
✔ DO NOT fabricate data—only extract what exists in the input.
✔ Follow the provided JSON structure for the output.
"""