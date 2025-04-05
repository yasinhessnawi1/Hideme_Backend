import json
import os


def normalize_entity_type(entity_type):
    """
    Normalize entity types across different engines.

    Args:
        entity_type (str): The original entity type

    Returns:
        str: Normalized entity type
    """
    # Remove engine-specific suffixes and prefixes
    if entity_type.endswith('-G'):
        # Gemini format: ENTITY-G
        return entity_type[:-2]
    elif entity_type.startswith('NO_'):
        # Presidio format for some entities: NO_ENTITY
        return entity_type[3:]
    else:
        return entity_type


def count_entities(file_paths):
    """
    Count entities from combined model JSON files by entity type and engine.

    Args:
        file_paths (list): List of paths to combined model JSON files

    Returns:
        dict: Dictionary with (entity_type, engine) as keys and counts as values
        dict: Dictionary with normalized entity types as keys and total counts as values
    """
    entity_counts_by_engine = {}
    entity_counts_total = {}

    for file_path in file_paths:
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                data = json.load(file)

                # Process each document in the JSON file
                for item in data:
                    if 'response' in item and 'file_results' in item['response']:
                        file_results = item['response']['file_results']

                        # Process each file result
                        for file_result in file_results:
                            if 'results' in file_result and 'redaction_mapping' in file_result['results']:
                                redaction_mapping = file_result['results']['redaction_mapping']

                                # Iterate through pages
                                if 'pages' in redaction_mapping:
                                    for page in redaction_mapping['pages']:
                                        if 'sensitive' in page:
                                            for entity in page['sensitive']:
                                                if 'entity_type' in entity and 'engine' in entity:
                                                    entity_type = entity['entity_type']
                                                    engine = entity['engine']

                                                    # Update count by engine
                                                    key = (entity_type, engine)
                                                    if key in entity_counts_by_engine:
                                                        entity_counts_by_engine[key] += 1
                                                    else:
                                                        entity_counts_by_engine[key] = 1

                                                    # Update total count with normalized entity type
                                                    normalized_type = normalize_entity_type(entity_type)
                                                    if normalized_type in entity_counts_total:
                                                        entity_counts_total[normalized_type] += 1
                                                    else:
                                                        entity_counts_total[normalized_type] = 1

        except Exception as e:
            print(f"Error processing file {file_path}: {str(e)}")

    return entity_counts_by_engine, entity_counts_total


def display_entity_by_engine_table(data):
    """
    Display entity counts by engine in a table format.

    Args:
        data (dict): Dictionary with (entity_type, engine) as keys and counts as values
    """
    # Convert dictionary to sorted list of tuples
    rows = [(entity_type, engine, count) for (entity_type, engine), count in data.items()]

    # Sort by entity type and then by count (descending)
    rows.sort(key=lambda x: (x[0], -x[2]))

    # Find the maximum width for the entity column
    max_entity_len = max(len(entity_type) for entity_type, _, _ in rows)
    entity_width = max(max_entity_len + 5, 35)  # Add padding

    # Print header
    print("\nEntity Counts by Engine:")
    print(f"{'Entity Type':<{entity_width}} {'Engine':<15} Count")
    print("-" * (entity_width + 25))

    # Print rows
    for entity_type, engine, count in rows:
        print(f"{entity_type:<{entity_width}} {engine:<15} {count}")


def display_entity_total_table(data):
    """
    Display total entity counts in a table format.

    Args:
        data (dict): Dictionary with normalized entity types as keys and total counts as values
    """
    # Convert dictionary to sorted list of tuples
    rows = [(entity_type, count) for entity_type, count in data.items()]

    # Sort by count (descending)
    rows.sort(key=lambda x: -x[1])

    # Find the maximum width for the entity column
    max_entity_len = max(len(entity_type) for entity_type, _ in rows)
    entity_width = max(max_entity_len + 5, 35)  # Add padding

    # Print header
    print("\nTotal Entity Counts Across All Engines:")
    print(f"{'Entity Type':<{entity_width}} {'Engine':<15} Count")
    print("-" * (entity_width + 25))

    # Print rows
    for entity_type, count in rows:
        print(f"{entity_type:<{entity_width}} {'ALL':<15} {count}")


def main():
    # Files to process
    file_paths = [
        r"C:\Users\anwar\final_backend_2\traning\hideme-models-labeling\gemini_gliner_presidio.json",
        r"C:\Users\anwar\final_backend_2\traning\hideme-models-labeling\gemini_gliner_presidio_2.json"
    ]

    # Count entities
    entity_counts_by_engine, entity_counts_total = count_entities(file_paths)

    # Display results in tables
    display_entity_by_engine_table(entity_counts_by_engine)
    display_entity_total_table(entity_counts_total)


if __name__ == "__main__":
    main()