import logging

import google.generativeai as genai


class GeminiAPI:
    """
    Handles sending a request to the Google Gemini API and receiving the response.
    """

    def __init__(self, api_key):
        """
        Initializes the Gemini API client.
        :param api_key: The Google Gemini API key.
        """
        self.api_key = api_key
        genai.configure(api_key=self.api_key)

    @staticmethod
    def send_request(document_text):
        """
        Sends a request to the Gemini API with the extracted PDF text.
        :param document_text: The extracted text from the PDF file.
        :return: The JSON response from the API.
        """
        prompt = f"""
        ### **Task: Extract and Anonymize Sensitive Data in JSON Format**
        Analyze the following **inspection report text** and extract all **sensitive information** (as defined by GDPR and other privacy laws).

        ### **Task Requirements:**
        - **Identify, tokenize, and assign NER tags** for each detected sensitive item.
        - **Anonymize the sensitive data** using placeholder tags.
        - **Use the BIO scheme** for Named Entity Recognition (NER) tags.
        - **Ensure JSON output matches the required format** (see below).

        ## **🛑 Named Entity Categories (NER Tags)**
        Assign the correct **BIO-based entity tags** to each detected item:

        ### **🔹 General Identifiable Data**
        - **ORG** → Organizations  
        - **PER** → Persons  
        - **NO_PHONE_NUMBER** → Norwegian phone numbers  
        - **EMAIL_ADDRESS** → Email addresses  
        - **NO_ADDRESS** → Norwegian addresses  
        - **DATE_TIME** → Dates and timestamps  
        - **GOV_ID** → Government-issued identifiers (e.g., passport numbers, national IDs)  
        - **FINANCIAL_INFO** → Financial data (e.g., bank account numbers, credit card details)  
        - **EMPLOYMENT_INFO** → Employment and professional details  

        ### **🔹 Highly Sensitive Data**
        - **HEALTH_INFO** → Health-related information (e.g., "TSE-prøver")  
        - **SEXUAL_ORIENTATION** → Sexual relationships and orientation  
        - **CRIMINAL_RECORD** → Crime-related information  
        - **CONTEXT_SENSITIVE** → Context-sensitive information (e.g., IP addresses, internal discussions)  
        - **IDENTIFIABLE_IMAGE** → Any identifiable image reference  
        - **FAMILY_RELATION** → Family and relationship data (e.g., "kona Vera" should be entirely tagged)  
        - **BEHAVIORAL_PATTERN** → Behavioral pattern data  
        - **EXTRA_SENSITIVE** → Any extra sensitive data  
        - **POLITICAL_CASE** → Political-related cases  
        - **ECONOMIC_STATUS** → Economic information (e.g., "dårlig økonomi" should be tagged)  

        ---
        **Inspection Report Text:**
        {document_text}

        ---
        ### **✅ JSON Output Format**
        Immediately return a structured JSON output in the following format:
        json
        {{
          "pages": [
            {{
              "text": [
                {{
                  "original_text": "Mattilsynet",
                  "anonymized_text": "<ORG>",
                  "entities": [
                    {{
                      "entity_type": "ORG",
                      "start": 0,
                      "end": 11,
                      "score": 0.996
                    }}
                  ]
                }},
                {{
                  "original_text": "Diagnose: Diabetes Type 1",
                  "anonymized_text": "Diagnose: <HEALTH_INFO>",
                  "entities": [
                    {{
                      "entity_type": "HEALTH_INFO",
                      "start": 9,
                      "end": 25,
                      "score": 0.98
                    }}
                  ]
                }},
                {{
                  "original_text": "Han har en dom for ran i 2012.",
                  "anonymized_text": "Han har en dom for <CRIMINAL_RECORD>.",
                  "entities": [
                    {{
                      "entity_type": "CRIMINAL_RECORD",
                      "start": 16,
                      "end": 19,
                      "score": 0.99
                    }}
                  ]
                }},
                {{
                  "original_text": "Postadresse: 2381 Brumunddal",
                  "anonymized_text": "Postadresse: <NO_ADDRESS>",
                  "entities": [
                    {{
                      "entity_type": "NO_ADDRESS",
                      "start": 12,
                      "end": 28,
                      "score": 0.95
                    }}
                  ]
                }},
                {{
                  "original_text": "Bankkontonummer: 1234 5678 9012 3456",
                  "anonymized_text": "Bankkontonummer: <FINANCIAL_INFO>",
                  "entities": [
                    {{
                      "entity_type": "FINANCIAL_INFO",
                      "start": 19,
                      "end": 39,
                      "score": 0.999
                    }}
                  ]
                }},
                {{
                  "original_text": "E-post: postmottak@mattilsynet.no",
                  "anonymized_text": "E-post: <EMAIL_ADDRESS>",
                  "entities": [
                    {{
                      "entity_type": "EMAIL_ADDRESS",
                      "start": 8,
                      "end": 33,
                      "score": 1.0
                    }}
                  ]
                }},
                {{
                  "original_text": "Gift med Kari Olsen",
                  "anonymized_text": "Gift med <FAMILY_RELATION>",
                  "entities": [
                    {{
                      "entity_type": "FAMILY_RELATION",
                      "start": 9,
                      "end": 19,
                      "score": 0.88
                    }}
                  ]
                }},
                {{
                  "original_text": "IP-adresse: 192.168.1.1",
                  "anonymized_text": "IP-adresse: <CONTEXT_SENSITIVE>",
                  "entities": [
                    {{
                      "entity_type": "CONTEXT_SENSITIVE",
                      "start": 11,
                      "end": 23,
                      "score": 0.93
                    }}
                  ]
                }}
              ]
            }}
          ]
        }}

        **IMPORTANT:** Return only JSON output without additional text.
        """

        try:
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content(prompt)

            if not response or not response.text.strip():
                logging.error("❌ Empty response from API.")
                return None

            # Clean and validate the response
            response_text = response.text.strip("`").strip()

            logging.info("✅ Successfully received response from Gemini API.")
            return response_text

        except Exception as e:
            logging.error(f"❌ Error communicating with Gemini API: {e}")
            return None
