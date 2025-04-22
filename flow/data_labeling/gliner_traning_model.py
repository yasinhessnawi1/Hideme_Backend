#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Import necessary libraries
import os
import json
import random
import torch
import glob
import traceback
import time
import datetime
import gc
import numpy as np
import argparse  # Added for command line arguments
from gliner import GLiNER
from gliner.training import Trainer, TrainingArguments
from gliner.data_processing.collator import DataCollator
import jsonlines
from tqdm import tqdm
import logging
import sys
import re

# Configure logging for better visibility
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"gliner_training_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Enable tokenizer parallelism for better performance
os.environ["TOKENIZERS_PARALLELISM"] = "true"

# Define paths to data files
#data_path = r"C:\Users\yasin\Hideme_Backend\flow\Data-jsonl"
data_path = r"C:/workspace"

# Path for combined JSONL file
combined_data_path = os.path.join(os.path.dirname(data_path), "combined_data.jsonl")

# Maximum sequence length supported by the model
MAX_SEQ_LENGTH = 384  # Using the model's hard-coded limit


def sanitize_and_combine_jsonl_files(directory_path, output_path):
    """
    Process all JSONL files in a directory:
    1. Read all JSONL files
    2. Sanitize text by removing escape characters
    3. Combine into a single JSONL file

    Args:
        directory_path: Path to directory containing JSONL files
        output_path: Path to save the combined JSONL file

    Returns:
        Path to the combined file
    """
    logger.info(f"Sanitizing and combining JSONL files from {directory_path}")

    # Find all JSONL files in the directory
    jsonl_files = glob.glob(os.path.join(directory_path, "*.jsonl"))
    if not jsonl_files:
        raise ValueError(f"No JSONL files found in {directory_path}")

    logger.info(f"Found {len(jsonl_files)} JSONL files to process")

    # Process and combine all files
    combined_data = []
    total_items = 0
    error_count = 0

    for file_path in tqdm(jsonl_files, desc="Processing JSONL files"):
        try:
            with jsonlines.open(file_path) as reader:
                for item in reader:
                    try:
                        # Sanitize the text input
                        if "text_input" in item:
                            # Replace escape sequences with their actual characters
                            text = item["text_input"]

                            # Keep actual newlines but normalize them
                            text = text.replace('\\n', '\n')

                            # Remove other common escape characters
                            text = re.sub(r'\\[rft]', ' ', text)

                            # Normalize multiple spaces and newlines
                            text = re.sub(r'\s+', ' ', text)
                            text = text.strip()

                            # Update the item with sanitized text
                            item["text_input"] = text

                            # Sanitize output values
                            if "output" in item:
                                for entity_type, values in item["output"].items():
                                    # Handle None values by converting to empty list
                                    if values is None:
                                        item["output"][entity_type] = []
                                    # Handle string values by converting to list
                                    elif isinstance(values, str):
                                        item["output"][entity_type] = [values]
                                    # Ensure all values in list are strings
                                    elif isinstance(values, list):
                                        sanitized_values = []
                                        for value in values:
                                            if value is not None:
                                                if isinstance(value, str):
                                                    sanitized_values.append(value)
                                                else:
                                                    try:
                                                        sanitized_values.append(str(value))
                                                    except:
                                                        pass  # Skip values that can't be converted to string
                                        item["output"][entity_type] = sanitized_values

                            # Add to combined data
                            combined_data.append(item)
                            total_items += 1
                    except Exception as e:
                        error_count += 1
                        if error_count <= 5:
                            logger.error(f"Error processing item in file {os.path.basename(file_path)}: {e}")
                            if error_count == 5:
                                logger.error("Too many errors, suppressing further error messages")
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")

    # Write combined data to output file
    logger.info(f"Writing {total_items} combined items to {output_path}")
    with jsonlines.open(output_path, mode='w') as writer:
        for item in combined_data:
            writer.write(item)

    if error_count > 0:
        logger.warning(f"Encountered {error_count} errors during data sanitization")

    logger.info(f"Successfully combined data into {output_path}")
    return output_path


class CustomGLiNERDataset(torch.utils.data.Dataset):
    """
    Custom dataset class for GLiNER that fixes the classes_to_id issue.
    """

    def __init__(self, data, entity_types):
        self.data = data
        self.entity_types = entity_types
        # Create global mapping
        self.entity_to_id = {entity_type: idx for idx, entity_type in enumerate(entity_types)}

        # Process data to ensure it has proper format
        for item in self.data:
            # Ensure each item has its own copy of entity_to_id
            item["classes_to_id"] = self.entity_to_id

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        return self.data[idx]


def load_jsonl_data(file_path):
    """
    Load data from JSONL file and prepare it for NER.
    """
    data = []
    error_count = 0
    with jsonlines.open(file_path) as reader:
        for item in tqdm(reader, desc=f"Processing {os.path.basename(file_path)}"):
            try:
                text_input = item.get('text_input', '')
                outputs = item.get('output', {})

                # Create a dictionary with the proper format
                transformed_item = {
                    "text": text_input,
                    "ner": []
                }

                # Process each entity type and its values
                for entity_type, entity_values in outputs.items():
                    # Skip if entity_values is None or not iterable
                    if entity_values is None:
                        logger.warning(f"Found None value for entity type {entity_type}, skipping")
                        continue

                    # Handle case where entity_values might be a string instead of a list
                    if isinstance(entity_values, str):
                        entity_values = [entity_values]

                    # Ensure entity_values is iterable
                    if not hasattr(entity_values, '__iter__'):
                        logger.warning(
                            f"Entity values for {entity_type} is not iterable: {type(entity_values)}, skipping")
                        continue

                    for entity_value in entity_values:
                        # Skip if entity_value is None or empty
                        if entity_value is None or entity_value == '':
                            continue

                        # Ensure entity_value is a string
                        if not isinstance(entity_value, str):
                            try:
                                entity_value = str(entity_value)
                            except:
                                logger.warning(f"Could not convert entity_value to string: {entity_value}, skipping")
                                continue

                        # Find all occurrences of this entity in the text
                        start_pos = 0
                        while True:
                            # Find the entity starting from start_pos
                            start_idx = text_input.find(entity_value, start_pos)
                            if start_idx == -1:  # No more occurrences
                                break

                            end_idx = start_idx + len(entity_value)
                            # Add entity with character positions
                            transformed_item["ner"].append((start_idx, end_idx, entity_type))

                            # Move past this occurrence
                            start_pos = start_idx + 1

                # Only add items that have at least one entity
                if transformed_item["ner"]:
                    data.append(transformed_item)
            except Exception as e:
                error_count += 1
                if error_count <= 10:  # Limit the number of error logs to avoid flooding
                    logger.error(f"Error processing item: {e}")
                    if error_count == 10:
                        logger.error("Too many errors, suppressing further error messages")

    logger.info(f"Loaded {len(data)} valid data items with entities")
    if error_count > 0:
        logger.warning(f"Encountered {error_count} errors during data loading")

    return data


def segment_long_texts(data_items, tokenizer, max_length=MAX_SEQ_LENGTH):
    """
    Split long texts into smaller segments that can be processed by the model.
    Only segments containing entities will be kept.
    """
    logger.info(f"Segmenting long texts into chunks of max {max_length} tokens...")
    segmented_items = []
    skipped_count = 0

    for item in tqdm(data_items, desc="Segmenting texts"):
        text = item["text"]
        char_spans = item["ner"]

        # Tokenize the full text
        encoded = tokenizer(
            text,
            add_special_tokens=False,
            return_offsets_mapping=True
        )
        tokens = tokenizer.convert_ids_to_tokens(encoded.input_ids)
        offset_mapping = encoded.offset_mapping

        # If text is within the length limit, process it normally
        if len(tokens) <= max_length:
            # Convert character spans to token spans
            token_spans = []
            for char_start, char_end, entity_type in char_spans:
                # Find corresponding token indices
                token_start = None
                token_end = None

                for i, (offset_start, offset_end) in enumerate(offset_mapping):
                    # Find the starting token
                    if token_start is None and offset_end > char_start:
                        token_start = i

                    # Find the ending token (inclusive)
                    if offset_start < char_end and offset_end >= char_end:
                        token_end = i
                        break

                # Only add valid spans
                if token_start is not None and token_end is not None:
                    token_spans.append((token_start, token_end + 1, entity_type))

            if token_spans:
                segmented_items.append({
                    "text": text,
                    "tokenized_text": tokens,
                    "ner": token_spans
                })
            else:
                skipped_count += 1
        else:
            # For longer texts, segment into overlapping chunks
            segment_size = max_length - 50  # Allow overlap between segments

            for start_idx in range(0, len(tokens), segment_size):
                end_idx = min(start_idx + max_length, len(tokens))

                # Get the character range for this segment
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

                        # Find the starting token
                        if token_start is None and offset_end > char_start:
                            token_start = i - start_idx  # Adjust to segment

                        # Find the ending token (inclusive)
                        if offset_start < char_end and offset_end >= char_end:
                            token_end = i - start_idx  # Adjust to segment
                            break

                    # Only add valid spans that are fully contained in the segment
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

    logger.info(f"Created {len(segmented_items)} segments from {len(data_items)} original items")
    logger.info(f"Skipped {skipped_count} items with no valid entities")

    return segmented_items


def find_latest_checkpoint(output_dir):
    """
    Find the latest checkpoint in the output directory.
    Returns the path to the latest checkpoint or None if not found.
    """
    checkpoints = glob.glob(os.path.join(output_dir, "checkpoint-*"))

    if not checkpoints:
        logger.info("No checkpoints found.")
        return None

    # Sort by creation time (newest first)
    latest_checkpoint = max(checkpoints, key=os.path.getctime)
    logger.info(f"Found latest checkpoint: {latest_checkpoint}")
    return latest_checkpoint


def main(resume_training=False, checkpoint_path=None, output_dir="models/trained_gliner"):
    # Start timer
    start_time = time.time()
    logger.info("Starting GLiNER training process")

    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Check CUDA availability first
    if torch.cuda.is_available():
        logger.info("CUDA is available!")
        logger.info(f"CUDA Version: {torch.version.cuda}")
        logger.info(f"Device count: {torch.cuda.device_count()}")
        for i in range(torch.cuda.device_count()):
            logger.info(f"Device {i}: {torch.cuda.get_device_name(i)}")
    else:
        logger.warning("CUDA is not available. Training will run on CPU which will be much slower.")
        logger.warning("To enable CUDA, ensure PyTorch is installed with CUDA support.")
        logger.warning("Please install the CUDA-enabled version of PyTorch using:")
        logger.warning("pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121")

    # Process and combine all JSONL files from the data_path
    combined_data_file = sanitize_and_combine_jsonl_files(data_path, combined_data_path)

    # Find the latest checkpoint if resuming and no specific checkpoint is provided
    if resume_training and checkpoint_path is None:
        checkpoint_path = find_latest_checkpoint(output_dir)
        if checkpoint_path is None:
            logger.warning("Resume training requested but no checkpoint found. Starting from scratch.")
            resume_training = False

    # Load the model (either from checkpoint or pre-trained)
    if resume_training and checkpoint_path:
        logger.info(f"Resuming training from checkpoint: {checkpoint_path}")
        try:
            model = GLiNER.from_pretrained(checkpoint_path)
            logger.info("Successfully loaded model from checkpoint")
        except Exception as e:
            logger.error(f"Error loading model from checkpoint: {e}")
            logger.info("Falling back to pre-trained model")
            model_name = "urchade/gliner_multi_pii-v1"
            logger.info(f"Loading model from {model_name}...")
            model = GLiNER.from_pretrained(model_name)
    else:
        model_name = "urchade/gliner_multi_pii-v1"
        logger.info(f"Loading model from {model_name}...")
        model = GLiNER.from_pretrained(model_name)

    # Get tokenizer from model
    tokenizer = model.data_processor.transformer_tokenizer

    # Load datasets from the combined file
    logger.info(f"Loading data from combined file: {combined_data_file}...")
    all_data = load_jsonl_data(combined_data_file)

    # Shuffle the combined dataset
    random.shuffle(all_data)
    logger.info('Dataset is shuffled...')

    # Get a list of all unique entity labels from the data
    entity_labels = set()
    for item in all_data:
        for _, _, entity_type in item["ner"]:
            entity_labels.add(entity_type)

    entity_labels = sorted(list(entity_labels))
    logger.info(f"Found {len(entity_labels)} unique entity types: {entity_labels}")

    # Set up device (GPU or CPU)
    device = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')
    logger.info(f"Using device: {device}")

    # Split into train and test datasets
    logger.info("Preparing datasets...")
    train_data = all_data[:int(len(all_data) * 0.9)]
    test_data = all_data[int(len(all_data) * 0.9):]
    logger.info(f'Dataset is split... Train: {len(train_data)}, Test: {len(test_data)}')

    # Convert to segments to handle long texts
    train_data_processed = segment_long_texts(train_data, tokenizer)
    test_data_processed = segment_long_texts(test_data, tokenizer)

    # Use full dataset for training (no subsampling)
    logger.info(f"Using full training dataset with {len(train_data_processed)} examples")

    # Limit test set size if it's extremely large to save memory during engines_evaluation
    MAX_TEST_SAMPLES = 2000 if torch.cuda.is_available() else 500
    if len(test_data_processed) > MAX_TEST_SAMPLES:
        logger.info(f"Limiting test set to {MAX_TEST_SAMPLES} samples to conserve memory during evaluation")
        test_data_processed = random.sample(test_data_processed, MAX_TEST_SAMPLES)
    else:
        logger.info(f"Using all {len(test_data_processed)} examples for testing")

    # Create custom datasets with proper classes_to_id mapping
    train_dataset = CustomGLiNERDataset(train_data_processed, entity_labels)
    test_dataset = CustomGLiNERDataset(test_data_processed, entity_labels)

    logger.info(
        f"Datasets prepared successfully with {len(train_dataset)} train and {len(test_dataset)} test examples.")

    # Check the distribution of sequence lengths
    train_lengths = [len(item["tokenized_text"]) for item in train_dataset.data]
    logger.info(
        f"Train sequence length stats - Min: {min(train_lengths)}, Max: {max(train_lengths)}, Avg: {sum(train_lengths) / len(train_lengths):.2f}")

    # Set up the data collator
    data_collator = DataCollator(
        model.config,
        data_processor=model.data_processor,
        prepare_labels=True,
    )

    # Set random seeds for reproducibility
    seed = 42
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    # Clear GPU cache if using CUDA
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        gc.collect()

    # Move model to device
    model.to(device)
    logger.info("Model moved to device...")

    # Determine optimal batch size based on available VRAM
    if torch.cuda.is_available():
        try:
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)  # Convert to GB
            logger.info(f"Total GPU memory: {gpu_memory:.2f} GB")

            # Conservative batch size estimation based on available VRAM
            if gpu_memory > 10:  # High-end GPU (>10GB VRAM)
                batch_size = 16
            elif gpu_memory > 6:  # Mid-range GPU (6-10GB VRAM)
                batch_size = 8
            else:  # Lower-end GPU (<6GB VRAM)
                batch_size = 4
        except:
            # Default batch size if we can't determine GPU memory
            batch_size = 8
    else:
        # CPU batch size
        batch_size = 4

    logger.info(f"Using batch size of {batch_size} for training")

    # Setup training arguments
    training_args = TrainingArguments(
        output_dir=output_dir,
        learning_rate=2e-5,
        weight_decay=0.01,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        gradient_accumulation_steps=2,  # Accumulate gradients to simulate larger batch size
        num_train_epochs=3,
        save_steps=100,
        eval_steps=100,
        save_total_limit=2,  # Keep only 2 checkpoints to save space
        logging_steps=10,
        logging_dir=f"{output_dir}/logs",
        dataloader_num_workers=4 if torch.cuda.is_available() else 0,  # Use multiprocessing with GPU
        use_cpu=device.type == 'cpu',
        fp16=torch.cuda.is_available(),  # Enable mixed precision training with GPU
        fp16_opt_level="O1" if torch.cuda.is_available() else None,  # Mixed precision optimization level
        max_grad_norm=1.0,  # Gradient clipping
    )

    # Create the trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=test_dataset,
        data_collator=data_collator,
        processing_class=model.data_processor,
    )

    # Train the model
    logger.info("Starting training...")
    try:
        # Print training confirmation
        logger.info(f"First item has classes_to_id: {train_dataset[0].get('classes_to_id') is not None}")
        logger.info(f"Train dataset size: {len(train_dataset)}")

        # Sample data point inspection
        sample_idx = 0
        sample_item = train_dataset[sample_idx]
        logger.info(f"Sample data point (idx={sample_idx}):")
        logger.info(f"  - Text length: {len(sample_item['text'])}")
        logger.info(f"  - Tokenized length: {len(sample_item['tokenized_text'])}")
        logger.info(f"  - Number of entities: {len(sample_item['ner'])}")

        # Run training with progress tracking
        logger.info(f"Training model with {len(train_dataset)} examples...")
        start_train_time = time.time()

        # Resume from checkpoint if applicable
        if resume_training and checkpoint_path:
            trainer.train(resume_from_checkpoint=checkpoint_path)
            logger.info(f"Resumed training from checkpoint: {checkpoint_path}")
        else:
            trainer.train()
            logger.info("Started training from scratch")

        train_duration = time.time() - start_train_time
        logger.info(f"Training completed successfully in {train_duration:.2f} seconds!")
    except KeyboardInterrupt:
        logger.warning("Training interrupted by user. Saving current model state...")
    except Exception as e:
        logger.error(f"An error occurred during training: {e}")
        traceback.print_exc()

    # Save the list of entity labels
    labels_file = os.path.join(output_dir, "entity_labels.json")
    with open(labels_file, "w", encoding="utf-8") as f:
        json.dump(entity_labels, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved entity labels to {labels_file}")

    # Save the final model
    final_model_path = os.path.join(output_dir, "final_model")
    os.makedirs(final_model_path, exist_ok=True)
    logger.info(f"Saving final model to {final_model_path}")
    model.save_pretrained(final_model_path)

    # Load the best model from checkpoint
    checkpoints = glob.glob(f"{output_dir}/checkpoint-*")

    if checkpoints:
        latest_checkpoint = max(checkpoints, key=os.path.getctime)
        logger.info(f"Loading model from checkpoint: {latest_checkpoint}")
        try:
            trained_model = GLiNER.from_pretrained(latest_checkpoint, load_tokenizer=True)
            logger.info(f"Successfully loaded model from {latest_checkpoint}")
        except Exception as e:
            logger.error(f"Error loading trained model: {e}")
            logger.info("Falling back to the original model")
            trained_model = model
    else:
        logger.info("No checkpoints found. Using the original model.")
        trained_model = model

    # Test the model on a sample text
    logger.info("\nTesting the model on a sample text:")

    sample_text = """
    Inspeksjonsrapport med skriftlig veiledning

    Navn:  Lars Kristian Olsen
    Adresse:  Lillehammervegen 27B, leil. 304
    Postnummer: 2620 Lillehammer
    Deres ref:  -
    Vår ref:  20231027-0047-LILLE
    Dato: 27. oktober 2023
    Org.nr.: 987654321
    """

    # Predict entities
    entities = trained_model.predict_entities(sample_text, entity_labels, threshold=0.5)

    logger.info("\nPredicted entities:")
    for entity in entities:
        logger.info(f"{entity['text']} => {entity['label']}")

    # Calculate and log total execution time
    total_duration = time.time() - start_time
    logger.info(f"\nTotal execution time: {total_duration:.2f} seconds ({total_duration / 60:.2f} minutes)")
    logger.info("Model training and testing complete.")

    # Return the model for use in other scripts
    return trained_model, entity_labels


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Train the GLiNER model with resumable training')
    parser.add_argument('--resume', action='store_true', help='Resume training from the latest checkpoint')
    parser.add_argument('--checkpoint', type=str, help='Specific checkpoint to resume from', default=None)
    parser.add_argument('--output_dir', type=str, default="models/trained_gliner",
                        help='Directory to save model and checkpoints')

    args = parser.parse_args()

    # Run training with parsed arguments
    main(resume_training=args.resume, checkpoint_path=args.checkpoint, output_dir=args.output_dir)