#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GLiNER Text Segmentation Utility

This script preprocesses JSONL data files by applying text segmentation for GLiNER training.
It handles long texts that exceed the model's token limit (384 tokens) by:
1. Splitting them into overlapping segments
2. Preserving entity annotations
3. Converting character positions to token positions

The output is a new JSONL file with properly segmented texts ready for GLiNER training.
"""

import os
import json
import argparse
import logging
import torch
import traceback
from pathlib import Path

from gliner import GLiNER
from tqdm import tqdm
import jsonlines
from transformers import AutoTokenizer
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"gliner_segmentation.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants
MAX_SEQ_LENGTH = 384  # Maximum sequence length for GLiNER model
DEFAULT_MODEL = "urchade/gliner_multi_pii-v1"  # Default model for tokenizer


def repair_jsonl_file(file_path, output_path):
    """
    Repair a potentially corrupted JSONL file.

    Args:
        file_path: Path to the input JSONL file
        output_path: Path to save the repaired file

    Returns:
        bool: True if repair was successful, False otherwise
    """
    try:
        logger.info(f"Attempting to repair JSONL file: {file_path}")

        valid_count = 0
        invalid_count = 0

        with open(output_path, 'w', encoding='utf-8') as out_file:
            with open(file_path, 'r', encoding='utf-8') as in_file:
                for line_num, line in enumerate(in_file, 1):
                    line = line.strip()
                    if not line:
                        continue  # Skip empty lines

                    try:
                        # Try to parse as valid JSON
                        obj = json.loads(line)
                        # Rewrite to ensure proper formatting
                        json.dump(obj, out_file, ensure_ascii=False)
                        out_file.write('\n')
                        valid_count += 1
                    except json.JSONDecodeError:
                        # Try to repair the line
                        try:
                            # Fix common issues like trailing commas
                            fixed_line = re.sub(r',\s*}', '}', line)
                            fixed_line = re.sub(r',\s*\]', ']', fixed_line)

                            # Look for complete JSON object endings
                            matches = list(re.finditer(r'\}', fixed_line))
                            if matches:
                                for match in reversed(matches):
                                    try:
                                        potential_obj = fixed_line[:match.end()]
                                        obj = json.loads(potential_obj)
                                        json.dump(obj, out_file, ensure_ascii=False)
                                        out_file.write('\n')
                                        valid_count += 1
                                        break
                                    except:
                                        continue
                            else:
                                invalid_count += 1
                                logger.warning(f"Could not repair line {line_num}")
                        except Exception as e:
                            invalid_count += 1
                            logger.warning(f"Failed to repair line {line_num}: {str(e)}")

        logger.info(f"Repair complete: {valid_count} valid lines, {invalid_count} invalid lines")
        return valid_count > 0

    except Exception as e:
        logger.error(f"Repair failed: {str(e)}")
        return False


def load_jsonl_data(file_path):
    """
    Load and validate data from a JSONL file.

    Args:
        file_path: Path to the JSONL file

    Returns:
        list: List of dictionaries containing the data
    """
    data = []
    error_count = 0

    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return []

    try:
        with jsonlines.open(file_path) as reader:
            for i, item in enumerate(tqdm(reader, desc=f"Loading data")):
                try:
                    # Make sure we have required fields
                    if 'text_input' not in item or 'output' not in item:
                        error_count += 1
                        if error_count <= 5:
                            logger.warning(f"Item {i} missing required fields")
                        continue

                    # Extract text and entity annotations
                    text = item['text_input']
                    output = item['output']

                    # Create initial format for processing
                    processed_item = {
                        "text": text,
                        "ner": []  # Will contain (start, end, entity_type) tuples
                    }

                    # Process each entity type and its occurrences
                    for entity_type, entity_values in output.items():
                        # Handle different formats (string vs list)
                        if entity_values is None:
                            continue
                        elif isinstance(entity_values, str):
                            entity_values = [entity_values]
                        elif not hasattr(entity_values, '__iter__'):
                            continue

                        # Find each entity's positions in the text
                        for entity_value in entity_values:
                            if not entity_value or not isinstance(entity_value, str):
                                continue

                            # Find all occurrences of this entity in the text
                            start_pos = 0
                            while True:
                                start_idx = text.find(entity_value, start_pos)
                                if start_idx == -1:  # No more occurrences
                                    break

                                end_idx = start_idx + len(entity_value)
                                processed_item["ner"].append((start_idx, end_idx, entity_type))
                                start_pos = start_idx + 1

                    # Only add items that have at least one entity
                    if processed_item["ner"]:
                        data.append(processed_item)

                except Exception as e:
                    error_count += 1
                    if error_count <= 5:  # Limit the number of error logs
                        logger.error(f"Error processing item {i}: {str(e)}")
                        if error_count == 5:
                            logger.error("Too many errors, suppressing further error messages")

        logger.info(f"Loaded {len(data)} items with valid entities")
        if error_count > 0:
            logger.warning(f"Encountered {error_count} errors during data loading")

        return data

    except Exception as e:
        logger.error(f"Failed to load data: {str(e)}")
        logger.error(traceback.format_exc())
        return []


def segment_long_texts(data_items, tokenizer, max_length=MAX_SEQ_LENGTH):
    """
    Split long texts into smaller segments that can be processed by the model.

    Args:
        data_items: List of data items with text and entity annotations
        tokenizer: Tokenizer to use for tokenization
        max_length: Maximum sequence length

    Returns:
        list: List of segmented items
    """
    logger.info(f"Segmenting texts exceeding {max_length} tokens...")
    segmented_items = []
    skipped_count = 0
    error_count = 0

    for item_idx, item in enumerate(tqdm(data_items, desc="Segmenting texts")):
        text = item["text"]
        char_spans = item["ner"]

        try:
            # Tokenize the full text
            encoded = tokenizer(
                text,
                add_special_tokens=False,
                return_offsets_mapping=True,
                truncation=False
            )
            tokens = tokenizer.convert_ids_to_tokens(encoded.input_ids)
            offset_mapping = encoded.offset_mapping

            # If text is within length limit, process it normally
            if len(tokens) <= max_length:
                # Convert character spans to token spans
                token_spans = []
                for char_start, char_end, entity_type in char_spans:
                    # Find corresponding token indices
                    token_start = None
                    token_end = None

                    for i, (offset_start, offset_end) in enumerate(offset_mapping):
                        # Find starting token
                        if token_start is None and offset_end > char_start:
                            token_start = i

                        # Find ending token (inclusive)
                        if offset_start < char_end and offset_end >= char_end:
                            token_end = i
                            break

                    # Only add valid spans
                    if token_start is not None and token_end is not None:
                        token_spans.append((token_start, token_end + 1, entity_type))

                # Add to results if it has valid spans
                if token_spans:
                    segmented_items.append({
                        "text": text,
                        "tokenized_text": tokens,
                        "ner": token_spans
                    })
                else:
                    skipped_count += 1

            # For longer texts, segment into overlapping chunks
            else:
                # Calculate segment size with overlap
                segment_size = max_length - 50  # Allow overlap between segments

                # Process each segment
                for start_idx in range(0, len(tokens), segment_size):
                    end_idx = min(start_idx + max_length, len(tokens))

                    # Get character range for this segment
                    if len(offset_mapping) <= start_idx or len(offset_mapping) <= end_idx - 1:
                        continue  # Skip if index out of range

                    segment_char_start = offset_mapping[start_idx][0]
                    segment_char_end = offset_mapping[min(end_idx - 1, len(offset_mapping) - 1)][1]

                    # Find entities that fall within this segment
                    segment_token_spans = []
                    for char_start, char_end, entity_type in char_spans:
                        # Skip entities outside this segment
                        if char_end <= segment_char_start or char_start >= segment_char_end:
                            continue

                        # Find corresponding token indices within the segment
                        token_start = None
                        token_end = None

                        for i in range(start_idx, end_idx):
                            if i >= len(offset_mapping):
                                break

                            offset_start, offset_end = offset_mapping[i]

                            # Find starting token
                            if token_start is None and offset_end > char_start:
                                token_start = i - start_idx  # Adjust to segment

                            # Find ending token (inclusive)
                            if offset_start < char_end and offset_end >= char_end:
                                token_end = i - start_idx  # Adjust to segment
                                break

                        # Only add valid spans that are fully contained
                        if token_start is not None and token_end is not None:
                            segment_token_spans.append((token_start, token_end + 1, entity_type))

                    # Only add segments that contain entities
                    if segment_token_spans:
                        segment_tokens = tokens[start_idx:end_idx]
                        segment_text = tokenizer.convert_tokens_to_string(segment_tokens).strip()

                        segmented_items.append({
                            "text": segment_text,
                            "tokenized_text": segment_tokens,
                            "ner": segment_token_spans
                        })

        except Exception as e:
            error_count += 1
            if error_count <= 5:
                logger.error(f"Error processing item {item_idx}: {str(e)}")
                if error_count == 5:
                    logger.error("Too many errors, suppressing further messages")

    logger.info(f"Created {len(segmented_items)} segments from {len(data_items)} original items")
    logger.info(f"Skipped {skipped_count} items with no valid entities")
    if error_count > 0:
        logger.warning(f"Encountered {error_count} errors during segmentation")

    return segmented_items


def save_segmented_data(segmented_items, output_path):
    """
    Save segmented data to a JSONL file in the format expected by GLiNER.

    Args:
        segmented_items: List of segmented items
        output_path: Path to save the output JSONL file

    Returns:
        bool: True if save was successful, False otherwise
    """
    try:
        logger.info(f"Saving {len(segmented_items)} segmented items to {output_path}")

        # Get all unique entity types
        entity_types = set()
        for item in segmented_items:
            for _, _, entity_type in item["ner"]:
                entity_types.add(entity_type)

        entity_types = sorted(list(entity_types))
        logger.info(f"Found {len(entity_types)} unique entity types")

        # Create entity type to ID mapping
        entity_to_id = {entity_type: idx for idx, entity_type in enumerate(entity_types)}

        # Save the data
        with jsonlines.open(output_path, mode='w') as writer:
            for item in segmented_items:
                # Create the output format expected by GLiNER
                output_item = {
                    "text": item["text"],
                    "tokenized_text": item["tokenized_text"],
                    "ner": item["ner"],
                    "classes_to_id": entity_to_id
                }
                writer.write(output_item)

        # Also save entity types to a separate file for reference
        entity_file = os.path.splitext(output_path)[0] + "_entity_types.json"
        with open(entity_file, 'w', encoding='utf-8') as f:
            json.dump(entity_types, f, indent=2, ensure_ascii=False)

        logger.info(f"Successfully saved segmented data to {output_path}")
        logger.info(f"Entity types saved to {entity_file}")
        return True

    except Exception as e:
        logger.error(f"Failed to save segmented data: {str(e)}")
        logger.error(traceback.format_exc())
        return False


def main():
    """Main function to run the segmentation process."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="GLiNER Text Segmentation Utility")
    parser.add_argument("--input", type=str, required=True, help="Input JSONL file")
    parser.add_argument("--output", type=str, help="Output JSONL file")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help="Model name for tokenizer")
    parser.add_argument("--max-length", type=int, default=MAX_SEQ_LENGTH, help="Maximum sequence length")
    parser.add_argument("--repair", action="store_true", help="Attempt to repair corrupt JSONL")
    args = parser.parse_args()

    # Set output path if not provided
    if not args.output:
        input_path = Path(args.input)
        args.output = str(input_path.parent / f"{input_path.stem}_segmented{input_path.suffix}")

    logger.info(f"Starting GLiNER text segmentation")
    logger.info(f"Input file: {args.input}")
    logger.info(f"Output file: {args.output}")
    logger.info(f"Model for tokenizer: {args.model}")
    logger.info(f"Maximum sequence length: {args.max_length}")

    # Repair file if requested
    if args.repair:
        logger.info("Repair mode enabled")
        repair_output = args.input + ".repaired"
        if repair_jsonl_file(args.input, repair_output):
            logger.info(f"Using repaired file for processing: {repair_output}")
            args.input = repair_output
        else:
            logger.error("Repair failed, will attempt to use original file")

    # Load data from JSONL file
    data = load_jsonl_data(args.input)
    if not data:
        logger.error("No valid data found. Exiting.")
        return

    # Load tokenizer
    logger.info(f"Loading tokenizer from {args.model}")
    try:
        gliner_model = GLiNER.from_pretrained(args.model)
        tokenizer = gliner_model.data_processor.transformer_tokenizer
    except Exception as e:
        logger.error(f"Failed to load tokenizer: {str(e)}")
        return

    # Segment texts
    segmented_data = segment_long_texts(data, tokenizer, args.max_length)
    if not segmented_data:
        logger.error("No valid segments created. Exiting.")
        return

    # Save segmented data
    if save_segmented_data(segmented_data, args.output):
        logger.info("Segmentation process completed successfully")
    else:
        logger.error("Failed to save segmented data")

    # Print summary
    original_count = len(data)
    segmented_count = len(segmented_data)
    logger.info(f"Summary:")
    logger.info(f"  - Original items: {original_count}")
    logger.info(f"  - Segmented items: {segmented_count}")
    if segmented_count > original_count:
        logger.info(f"  - Expansion ratio: {segmented_count / original_count:.2f}x")

    # Calculate average entities per segment
    total_entities = sum(len(item["ner"]) for item in segmented_data)
    logger.info(f"  - Total entities preserved: {total_entities}")
    logger.info(f"  - Average entities per segment: {total_entities / segmented_count:.2f}")


if __name__ == "__main__":
    main()