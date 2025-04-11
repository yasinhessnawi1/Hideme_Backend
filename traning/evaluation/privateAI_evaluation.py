import json
import os


def count_entities(file_paths):
    """
    Count entities from PrivateAI JSON files based on the 'best_label' field.

    Args:
        file_paths (list): List of paths to PrivateAI JSON files

    Returns:
        dict: Dictionary with entity types as keys and counts as values
    """
    entity_counts = {}

    for file_path in file_paths:
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                data = json.load(file)

                # Process each document/item in the JSON file
                for item in data:
                    if 'ai_results' in item:
                        for ai_result in item['ai_results']:
                            if 'entities' in ai_result:
                                for entity in ai_result['entities']:
                                    if 'best_label' in entity:
                                        entity_type = entity['best_label']

                                        # Update count
                                        if entity_type in entity_counts:
                                            entity_counts[entity_type] += 1
                                        else:
                                            entity_counts[entity_type] = 1

        except Exception as e:
            print(f"Error processing file {file_path}: {str(e)}")

    return entity_counts


def display_table(data):
    """
    Display data in a simple table format.

    Args:
        data (list): List of tuples (entity, count)
    """
    # Find the maximum width for the entity column
    max_entity_len = max(len(entity) for entity, _ in data)
    entity_width = max(max_entity_len + 5, 35)  # Add padding

    # Print header
    print(f"{'Entity PrivateAI':<{entity_width}} Count")
    print("-" * (entity_width + 10))

    # Print rows
    for entity, count in data:
        print(f"{entity:<{entity_width}} {count}")


def main():
    # Files to process
    file_paths = [
        r"C:\Users\anwar\final_backend_2\traning\private_AI_labeling.json",
        r"C:\Users\anwar\final_backend_2\traning\private_AI_labeling_2.json"
    ]

    # Count entities
    entity_counts = count_entities(file_paths)

    # Sort by count (descending)
    sorted_counts = sorted(entity_counts.items(), key=lambda x: x[1], reverse=True)

    # Display results in a table
    display_table(sorted_counts)


if __name__ == "__main__":
    main()