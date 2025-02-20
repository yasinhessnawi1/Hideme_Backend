import json
import logging
import re


class ResponseHandler:
    """
    Handles processing and sending of extracted text per page to Gemini API.
    """

    def __init__(self, gemini_api):
        """
        Initializes the ResponseHandler with an API client.
        """
        self.gemini_api = gemini_api

    def save_responses_per_page(self, extracted_pages):
        """
        Processes and sends extracted text per page to Gemini API.
        """
        logging.info("📤 Starting Gemini API processing...")

        final_output = {"pages": []}
        for page_index, page in enumerate(extracted_pages):
            processed_page = self.process_page(page, page_index)
            final_output["pages"].append(processed_page)

        # Now returning JSON directly instead of saving.
        return final_output

    def process_page(self, page, page_index):
        """Processes an individual page, sending its text to Gemini API."""
        if not page or not self.get_page_text(page):
            return self.get_empty_page_placeholder(page_index)

        logging.info(f"📤 Sending Page {page_index + 1} to Gemini API...")
        response = self.gemini_api.send_request(self.get_page_text(page))

        return self.get_processed_page(response, page_index)

    @staticmethod
    def get_page_text(page):
        """Extracts all text from a page."""
        return "\n".join(
            [item["original_text"] for item in page.get("text", []) if "original_text" in item]
        ).strip()

    def get_processed_page(self, response, page_index):
        """Cleans and formats Gemini API response."""
        if not response:
            return self.get_error_page_placeholder(page_index)

        try:
            return self.parse_response(response)
        except Exception as e:
            logging.error(f"❌ Error processing Page {page_index + 1}: {e}")
            return self.get_error_page_placeholder(page_index)

    @staticmethod
    def parse_response(response):
        """
        Parses JSON response from Gemini API.
        """
        try:
            json_data = json.loads(response)
        except json.JSONDecodeError:
            cleaned_response = re.search(r"\{.*}", response.strip("`").strip(), re.DOTALL)
            json_data = json.loads(cleaned_response.group(0)) if cleaned_response else {}

        return {"text": json_data["pages"][0]["text"]} if "pages" in json_data else {}

    @staticmethod
    def get_empty_page_placeholder(page_index):
        """Returns a placeholder for empty pages."""
        logging.warning(f"⚠️ Empty Page {page_index + 1}, inserting placeholder.")
        return {"text": [
            {"original_text": "This page was empty", "anonymized_text": "This page was empty", "entities": []}]}

    @staticmethod
    def get_error_page_placeholder(page_index):
        """Returns a placeholder for pages with processing errors."""
        return {"text": [
            {"original_text": "Error processing this page", "anonymized_text": "Error processing this page",
             "entities": []}]}
