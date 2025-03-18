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
from gliner import GLiNER
from gliner.training import Trainer, TrainingArguments
from gliner.data_processing.collator import DataCollator
import jsonlines
from tqdm import tqdm
import logging
import sys

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
inspeksjonsrapport_path = r"C:\Users\anwar\PycharmProjects\Hideme_Backend\data_generation\inspeksjonsrapport\labeling_inspeksjonsrapport\inspeksjonsrapport.jsonl"
bekymringsmelding_path = r"C:\Users\anwar\PycharmProjects\Hideme_Backend\data_generation\bekymringsmelding\labeling_bekymringsmelding\bekymringsmelding.jsonl"

# Maximum sequence length supported by the model
MAX_SEQ_LENGTH = 384  # Using the model's hard-coded limit


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
    with jsonlines.open(file_path) as reader:
        for item in tqdm(reader, desc=f"Processing {os.path.basename(file_path)}"):
            text_input = item.get('text_input', '')
            outputs = item.get('output', {})

            # Create a dictionary with the proper format
            transformed_item = {
                "text": text_input,
                "ner": []
            }

            # Process each entity type and its values
            for entity_type, entity_values in outputs.items():
                for entity_value in entity_values:
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


def main():
    # Start timer
    start_time = time.time()
    logger.info("Starting GLiNER training process")

    # Load the pre-trained model
    model_name = "urchade/gliner_multi_pii-v1"
    logger.info(f"Loading model from {model_name}...")
    model = GLiNER.from_pretrained(model_name)

    # Get tokenizer from model
    tokenizer = model.data_processor.transformer_tokenizer

    # Load datasets
    logger.info("Loading inspeksjonsrapport data...")
    inspeksjonsrapport_data = load_jsonl_data(inspeksjonsrapport_path)
    logger.info(f"Loaded {len(inspeksjonsrapport_data)} inspeksjonsrapport records")

    logger.info("Loading bekymringsmelding data...")
    bekymringsmelding_data = load_jsonl_data(bekymringsmelding_path)
    logger.info(f"Loaded {len(bekymringsmelding_data)} bekymringsmelding records")

    # Combine datasets
    all_data = inspeksjonsrapport_data + bekymringsmelding_data
    logger.info(f"Total dataset size: {len(all_data)}")

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
    device = torch.device('cuda:0') if torch.cuda.is_available() else torch.device('cpu')
    logger.info(f"Using device: {device}")

    # Split into train and test datasets
    logger.info("Preparing datasets...")
    train_data = all_data[:int(len(all_data) * 0.9)]
    test_data = all_data[int(len(all_data) * 0.9):]
    logger.info(f'Dataset is split... Train: {len(train_data)}, Test: {len(test_data)}')

    # Convert to segments to handle long texts
    train_data_processed = segment_long_texts(train_data, tokenizer)
    test_data_processed = segment_long_texts(test_data, tokenizer)

    # Sample a subset for faster training
    MAX_TRAIN_SAMPLES = 2000
    if len(train_data_processed) > MAX_TRAIN_SAMPLES:
        logger.info(f"Sampling {MAX_TRAIN_SAMPLES} examples from {len(train_data_processed)} for faster training")
        train_data_processed = random.sample(train_data_processed, MAX_TRAIN_SAMPLES)

    MAX_TEST_SAMPLES = 200
    if len(test_data_processed) > MAX_TEST_SAMPLES:
        test_data_processed = random.sample(test_data_processed, MAX_TEST_SAMPLES)

    # Create custom datasets with proper classes_to_id mapping
    train_dataset = CustomGLiNERDataset(train_data_processed, entity_labels)
    test_dataset = CustomGLiNERDataset(test_data_processed, entity_labels)

    logger.info(
        f"Datasets prepared successfully with {len(train_dataset)} train and {len(test_dataset)} test examples.")

    # Check the distribution of sequence lengths
    train_lengths = [len(item["tokenized_text"]) for item in train_dataset.data]
    logger.info(
        f"Train sequence length stats - Min: {min(train_lengths)}, Max: {max(train_lengths)}, Avg: {sum(train_lengths) / len(train_lengths):.2f}")

    # Output directory
    output_dir = "models/trained_gliner"
    os.makedirs(output_dir, exist_ok=True)

    # Set up the data collator
    data_collator = DataCollator(
        model.config,
        data_processor=model.data_processor,
        prepare_labels=True,
    )

    # Move model to device
    model.to(device)
    logger.info("Model moved to device...")

    # Setup training arguments with low resource requirements
    training_args = TrainingArguments(
        output_dir=output_dir,
        learning_rate=2e-5,
        weight_decay=0.01,
        per_device_train_batch_size=4,  # Increased batch size for smaller segments
        per_device_eval_batch_size=4,
        gradient_accumulation_steps=2,  # Reduced accumulation for faster steps
        num_train_epochs=3,  # Train for more epochs on reduced dataset
        save_steps=100,
        eval_steps=100,
        save_total_limit=2,  # Keep only 2 checkpoints to save space
        logging_steps=10,
        logging_dir=f"{output_dir}/logs",
        dataloader_num_workers=0,
        use_cpu=device.type == 'cpu',
        report_to="none",
        fp16=False,
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
        trainer.train()
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
    main()