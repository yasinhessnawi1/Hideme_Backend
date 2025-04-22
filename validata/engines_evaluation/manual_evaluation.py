import json


def count_entities(file_paths):
    """
    Count entities from manually redacted JSON files based on the 'entity' field.

    Args:
        file_paths (list): List of paths to manually redacted JSON files

    Returns:
        dict: Dictionary with entity types as keys and counts as values
    """
    entity_counts = {}
    files_processed = 0
    files_with_entities = 0

    for file_path in file_paths:
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                files_processed += 1
                data = json.load(file)

                if data:
                    files_with_entities += 1

                    # Process each entity entry in the JSON array
                    for entry in data:
                        if 'entity' in entry:
                            entity_type = entry['entity']

                            # Update count
                            if entity_type in entity_counts:
                                entity_counts[entity_type] += 1
                            else:
                                entity_counts[entity_type] = 1

        except Exception as e:
            print(f"Error processing file {file_path}: {str(e)}")

    print(f"Processed {files_processed} files, found entities in {files_with_entities} files.")
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
    print(f"{'Entity manuell redacted':<{entity_width}} Count")
    print("-" * (entity_width + 10))

    # Print rows
    for entity, count in data:
        print(f"{entity:<{entity_width}} {count}")


def main():
    # Files to process
    file_paths = [
        r"C:\Users\anwar\final_backend_2\traning\evaluation\manuell_redacted.json",
        r"C:\Users\anwar\final_backend_2\traning\evaluation\manuell_redacted_2.json",
        r"C:\Users\anwar\final_backend_2\traning\evaluation\manuell_redacted_3.json"
    ]

    # Count entities
    entity_counts = count_entities(file_paths)

    # Sort by count (descending)
    sorted_counts = sorted(entity_counts.items(), key=lambda x: x[1], reverse=True)

    # Display results in a table
    display_table(sorted_counts)


if __name__ == "__main__":
    main()
