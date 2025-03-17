"""
Core domain interfaces for document processing system.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple


class DocumentExtractor(ABC):
    """Interface for extracting text from various document formats."""

    @abstractmethod
    def extract_text(self) -> Dict[str, Any]:
        """
        Extract text with positional information from a document.

        Returns:
            Dict with structure:
            {
                "pages": [
                    {
                        "page": int,
                        "words": [
                            {"text": str, "x0": float, "y0": float, "x1": float, "y1": float},
                            ...
                        ]
                    },
                    ...
                ]
            }
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the document and free resources."""
        pass


class EntityDetector(ABC):
    """Interface for detecting sensitive entities in text."""

    @abstractmethod
    def detect_sensitive_data(
        self,
        extracted_data: Dict[str, Any],
        requested_entities: Optional[List[str]] = None
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        """
        Detect sensitive entities in extracted text.

        Args:
            extracted_data: Dictionary with text and position information
            requested_entities: List of entity types to detect (optional)

        Returns:
            Tuple of (anonymized_text, results_json, redaction_mapping)
        """
        pass


class DocumentRedactor(ABC):
    """Interface for redacting sensitive information in documents."""

    @abstractmethod
    def apply_redactions(
        self,
        redaction_mapping: Dict[str, Any],
        output_path: str
    ) -> str:
        """
        Apply redactions to the document based on provided mapping.

        Args:
            redaction_mapping: Dictionary with redaction information
            output_path: Path to save the redacted document

        Returns:
            Path to the redacted document
        """
        pass

    def close(self):
        """Close the document and free resources."""
        pass



class PDFEntityMapping(ABC):
    """Interface for mapping entity offsets to document positions."""

    @abstractmethod
    def map_entities_to_positions(
        self,
        full_text: str,
        text_to_position_mapping: List[Tuple[Any, int, int]],
        entity_offsets: Tuple[int, int]
    ) -> List[Dict[str, float]]:
        """
        Map entity character offsets to document positions.

        Args:
            full_text: Complete text where entity was found
            text_to_position_mapping: Mapping from text offsets to document positions
            entity_offsets: Character start/end offsets for the entity

        Returns:
            List of bounding boxes as dictionaries
        """
        pass