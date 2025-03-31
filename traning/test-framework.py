#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Improved Simple GLiNER Model Test Script
---------------------------------------
This script provides a simple way to test a GLiNER model and get clean JSON results
with properly handled entity boundaries.
"""

import json
import os
import re
from gliner import GLiNER

# Configuration
CONFIG = {
    "model_dir": "models/trained_gliner/checkpoint-23952",
    "entity_labels_file": "models/trained_gliner/entity_labels.json",
    "max_length": 512,
    "threshold": 0.5
}


def load_entity_labels():
    """Load entity labels from file or use default labels."""
    try:
        if os.path.exists(CONFIG["entity_labels_file"]):
            with open(CONFIG["entity_labels_file"], 'r', encoding='utf-8') as f:
                labels = json.load(f)
            print(f"Loaded {len(labels)} entity labels from {CONFIG['entity_labels_file']}")
            return labels
        else:
            print(f"Entity labels file not found: {CONFIG['entity_labels_file']}")
            # Fallback to default labels
            return ['PERSON', 'NO_ADDRESS', 'POSTAL_CODE', 'DATE_TIME', 'NO_PHONE_NUMBER',
                    'EMAIL_ADDRESS', 'GOV_ID', 'AGE', 'AGE_INFO']
    except Exception as e:
        print(f"Error loading entity labels: {e}")
        return []


def fix_entity_spans(text, entities):
    """
    Fix entity spans by correcting for line breaks and ensuring the entities
    match actual text sections.
    """
    fixed_entities = []

    for entity in entities:
        # Get the original entity text and create a version without line breaks
        original_text = entity['text']
        clean_text = re.sub(r'\s*\n\s*', ' ', original_text).strip()

        # Try to find where this text really appears in the source
        found = False

        # First try the exact text as-is
        start_idx = text.find(original_text)
        if start_idx >= 0:
            fixed_entities.append({
                "text": original_text,
                "label": entity['label'],
                "score": entity['score'],
                "start_idx": start_idx,
                "end_idx": start_idx + len(original_text)
            })
            found = True
            continue

        # Next try the clean text (without line breaks)
        start_idx = text.find(clean_text)
        if start_idx >= 0:
            fixed_entities.append({
                "text": clean_text,
                "label": entity['label'],
                "score": entity['score'],
                "start_idx": start_idx,
                "end_idx": start_idx + len(clean_text)
            })
            found = True
            continue

        # If still not found, try each line of the original text
        if not found:
            # Split on newlines and check each segment
            segments = re.split(r'\n', original_text)
            for segment in segments:
                segment = segment.strip()
                if len(segment) >= 3:  # Only consider substantial segments
                    segment_idx = text.find(segment)
                    if segment_idx >= 0:
                        fixed_entities.append({
                            "text": segment,
                            "label": entity['label'],
                            "score": entity['score'],
                            "start_idx": segment_idx,
                            "end_idx": segment_idx + len(segment)
                        })
                        found = True
                        break

        # If we still haven't found it, log a warning
        if not found:
            print(f"Warning: Could not locate entity in text: '{original_text}'")

    return fixed_entities


def run_entity_recognition(text):
    """Run entity recognition on the provided text and return clean results."""
    try:
        # Load the model
        model = GLiNER.from_pretrained(
            CONFIG["model_dir"],
            load_tokenizer=True,
            local_files_only=True,
            max_length=CONFIG["max_length"]
        )
        print(f"Model loaded successfully from {CONFIG['model_dir']}")

        # Load entity labels
        entity_labels = load_entity_labels()

        # Run prediction
        raw_entities = model.predict_entities(
            text,
            entity_labels,
            threshold=CONFIG["threshold"]
        )
        for entity in raw_entities:
            print(entity["text"], "=>", entity["label"])

        # Fix entity spans
        fixed_entities = fix_entity_spans(text, raw_entities)

        # Sort entities by their start position in the text
        fixed_entities.sort(key=lambda x: x['start_idx'])

        return fixed_entities

    except Exception as e:
        print(f"Error during entity recognition: {e}")
        return []


def main():
    # Sample text, feel free to replace with your own
    sample_text = """
    Inspeksjonsrapport med skriftlig veiledning
    Navn:  Lars Kristian Olsen
    Adresse:  Lillehammervegen 27B, leil. 304
    Postnummer: 2620 Lillehammer
    Deres ref:  -
    Vår ref:  20231027-0047-LILLE
    Dato: 27. oktober 2023
    Org.nr.: 987654321
    Bekymringsmelding for dyrevelferd

    Vi har mottatt bekymringsmelding om dyrene ved Hansens gård. 
    Eier: Johan Hansen, født 12.03.1965
    Adresse: Fjellveien 45, 3050 Mjøndalen
    Telefon: +47 922 33 444
    """

    # Run entity recognition
    results = run_entity_recognition(sample_text)

    # Print the results as nicely formatted JSON
    print("\nEntity Recognition Results:")
    print(json.dumps(results, indent=2, ensure_ascii=False))

    # Print a summary
    if results:
        print(f"\nFound {len(results)} entities")

        # Count entities by type
        entity_counts = {}
        for entity in results:
            label = entity['label']
            entity_counts[label] = entity_counts.get(label, 0) + 1

        print("\nEntity count by type:")
        for label, count in sorted(entity_counts.items()):
            print(f"  {label}: {count}")


if __name__ == "__main__":
    main()