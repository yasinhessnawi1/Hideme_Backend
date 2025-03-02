import os
import base64
import json
import time

import requests

from data_generation.generate_text import PRIVATE_AI_API_KEY

# Replace with your actual API key and directory path
API_URL = "https://api.private-ai.com/community/v4/process/files/base64"
API_KEY = PRIVATE_AI_API_KEY
DIRECTORY = "data"

# Prepare the headers (include the API key if required)
headers = {
    "Content-Type": "application/json",
    "x-api-key": API_KEY
}
count = 0
# Loop over each file in the directory
for filename in os.listdir(DIRECTORY):
    if count == 70:
        break
    if filename.lower().endswith('.pdf'):
        file_path = os.path.join(DIRECTORY, filename)

        # Read and encode the PDF file in base64
        with open(file_path, "rb") as f:
            file_bytes = f.read()
        encoded_data = base64.b64encode(file_bytes).decode("utf-8")

        # Prepare the payload based on the documentation and example
        payload = {
            "file": {
                "fisk_data": encoded_data,
                "content_type": "application/pdf"
            },
            "entity_detection": {
                "return_entity": True,
                "accuracy": "high_multilingual"
            },
            "pdf_options": {
                "density": 150,
                "max_resolution": 2000,
                "enable_pdf_text_layer": True
            },
            "audio_options": {
                "bleep_start_padding": 0,
                "bleep_end_padding": 0
            },

        }

        # Make the API request
        response = requests.post(API_URL, json=payload, headers=headers)
        count += 1
        try:
            response_json = response.json()
        except json.JSONDecodeError:
            print(f"Error decoding JSON response for {filename}")
            continue
        if "processed_file" in response_json:
            del response_json["processed_file"]
        # Define the output JSON file path using the same base name as the PDF
        json_filename = os.path.splitext(filename)[0] + ".txt"
        json_path = os.path.join(DIRECTORY, json_filename)

        # Save the JSON response with pretty printing
        with open(json_path, "w", encoding="utf-8") as json_file:
            json.dump(response_json, json_file, indent=4, ensure_ascii=False)

        print(f"Processed {filename} and saved response as {json_filename}")
        time.sleep(12)
        print(f"Waiting for 12 seconds before the next request...")