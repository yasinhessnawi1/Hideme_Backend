"""
Factory for creating document processing components.
"""
from enum import Enum, auto
from typing import Dict, Any, Optional, List, Tuple

from backend.app.configs.gliner_config import GLINER_MODEL_NAME, GLINER_MODEL_PATH, GLINER_ENTITIES
from backend.app.domain.interfaces import DocumentExtractor, EntityDetector, DocumentRedactor
from backend.app.document_processing.pdf import PDFTextExtractor, PDFRedactionService
from backend.app.entity_detection.presidio import PresidioEntityDetector
from backend.app.entity_detection.gemini import GeminiEntityDetector
from backend.app.entity_detection.gliner import GlinerEntityDetector
from backend.app.utils.logger import log_info


class DocumentFormat(Enum):
    """Supported document formats."""
    PDF = auto()
    DOCX = auto()
    TXT = auto()
    # Add more formats as needed


class EntityDetectionEngine(Enum):
    """Supported entity detection engines."""
    PRESIDIO = auto()
    GEMINI = auto()
    GLINER = auto()
    HYBRID = auto()  # Uses multiple engines and combines results


class DocumentProcessingFactory:
    """
    Factory for creating document processing components based on format and configuration.
    """

    @staticmethod
    def create_document_extractor(
            document_path: str,
            document_format: Optional[DocumentFormat] = None
    ) -> DocumentExtractor:
        """
        Create a document extractor for the specified format.

        Args:
            document_path: Path to the document
            document_format: Format of the document (optional, will be detected if not provided)

        Returns:
            DocumentExtractor instance

        Raises:
            ValueError: If document format is not supported
        """
        # Auto-detect format if not provided
        if document_format is None:
            document_format = DocumentProcessingFactory._detect_format(document_path)

        # Create extractor based on format
        if document_format == DocumentFormat.PDF:
            return PDFTextExtractor(document_path)
        elif document_format == DocumentFormat.DOCX:
            # Not implemented yet
            raise ValueError("DOCX extraction not implemented yet")
        elif document_format == DocumentFormat.TXT:
            # Not implemented yet
            raise ValueError("TXT extraction not implemented yet")
        else:
            raise ValueError(f"Unsupported document format: {document_format}")

    """
    Update to the DocumentProcessingFactory to support pre-downloaded GLiNER models.
    """

    # Update the create_entity_detector method in DocumentProcessingFactory class
    @staticmethod
    def create_entity_detector(
            engine: EntityDetectionEngine = EntityDetectionEngine.PRESIDIO,
            config: Optional[Dict[str, Any]] = None
    ) -> EntityDetector:
        """
        Create an entity detector using the specified engine.

        Args:
            engine: Entity detection engine to use
            config: Configuration for the detector (optional)

        Returns:
            EntityDetector instance

        Raises:
            ValueError: If the engine is not supported
        """
        if engine == EntityDetectionEngine.PRESIDIO:
            return PresidioEntityDetector()
        elif engine == EntityDetectionEngine.GEMINI:
            return GeminiEntityDetector()
        elif engine == EntityDetectionEngine.GLINER:
            # Handle GLiNER with support for pre-downloaded models
            config = config or {}
            model_name = config.get("model_name", GLINER_MODEL_NAME)
            entities = config.get("entities", GLINER_ENTITIES)

            # Configure local model support
            local_model_path = config.get("local_model_path", GLINER_MODEL_PATH)
            local_files_only = config.get("local_files_only", False)

            # Create detector with local model support
            return GlinerEntityDetector(
                model_name=model_name,
                entities=entities,
                local_model_path=local_model_path,
                local_files_only=local_files_only
            )
        elif engine == EntityDetectionEngine.HYBRID:
            return HybridEntityDetector(config or {})
        else:
            raise ValueError(f"Unsupported entity detection engine: {engine}")

    @staticmethod
    def create_document_redactor(
            document_path: str,
            document_format: Optional[DocumentFormat] = None
    ) -> DocumentRedactor:
        """
        Create a document redactor for the specified format.

        Args:
            document_path: Path to the document
            document_format: Format of the document (optional, will be detected if not provided)

        Returns:
            DocumentRedactor instance

        Raises:
            ValueError: If document format is not supported
        """
        # Auto-detect format if not provided
        if document_format is None:
            document_format = DocumentProcessingFactory._detect_format(document_path)

        # Create redactor based on format
        if document_format == DocumentFormat.PDF:
            return PDFRedactionService(document_path)
        elif document_format == DocumentFormat.DOCX:
            # Not implemented yet
            raise ValueError("DOCX redaction not implemented yet")
        elif document_format == DocumentFormat.TXT:
            # Not implemented yet
            raise ValueError("TXT redaction not implemented yet")
        else:
            raise ValueError(f"Unsupported document format: {document_format}")

    @staticmethod
    def _detect_format(document_path: str) -> DocumentFormat:
        """
        Detect document format based on file extension.

        Args:
            document_path: Path to the document

        Returns:
            DocumentFormat enum value

        Raises:
            ValueError: If format cannot be determined
        """
        if document_path.lower().endswith('.pdf'):
            return DocumentFormat.PDF
        elif document_path.lower().endswith(('.docx', '.doc')):
            return DocumentFormat.DOCX
        elif document_path.lower().endswith('.txt'):
            return DocumentFormat.TXT
        else:
            raise ValueError(f"Cannot determine document format for: {document_path}")


class HybridEntityDetector(EntityDetector):
    """
    A hybrid entity detector that combines results from multiple engines.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the hybrid detector with configuration.

        Args:
            config: Configuration dictionary with settings for each detector
        """
        self.detectors = []

        # Create detectors based on configuration
        if config.get("use_presidio", True):
            self.detectors.append(PresidioEntityDetector())

        if config.get("use_gemini", False):
            self.detectors.append(GeminiEntityDetector())

        if config.get("use_gliner", False):
            model_name = config.get("gliner_model_name")
            if model_name:
                self.detectors.append(GlinerEntityDetector(model_name=model_name))
            else:
                self.detectors.append(GlinerEntityDetector())

        if not self.detectors:
            # Default to Presidio if no detectors specified
            self.detectors.append(PresidioEntityDetector())

        log_info(f"[OK]Created hybrid entity detector with {len(self.detectors)} detection engines")

    def detect_sensitive_data(
            self,
            extracted_data: Dict[str, Any],
            requested_entities: Optional[List[str]] = None
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        """
        Detect sensitive entities using multiple detection engines.

        Args:
            extracted_data: Dictionary containing text and bounding box information
            requested_entities: List of entity types to detect

        Returns:
            Tuple of (anonymized_text, results_json, redaction_mapping)
        """
        all_entities = []
        all_redaction_mappings = []
        anonymized_text = None

        # Run detection with each engine
        for detector in self.detectors:
            anon_text, entities, redaction_mapping = detector.detect_sensitive_data(
                extracted_data, requested_entities
            )

            # Use the first anonymized text (we'll merge entities, not text)
            if anonymized_text is None:
                anonymized_text = anon_text

            all_entities.extend(entities)
            all_redaction_mappings.append(redaction_mapping)

        # Merge redaction mappings
        merged_mapping = self._merge_redaction_mappings(all_redaction_mappings)

        return anonymized_text, all_entities, merged_mapping

    def _merge_redaction_mappings(
            self,
            redaction_mappings: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Merge multiple redaction mappings into one.

        Args:
            redaction_mappings: List of redaction mappings to merge

        Returns:
            Merged redaction mapping
        """
        if not redaction_mappings:
            return {"pages": []}

        merged = {"pages": []}
        page_mappings = {}

        # Group mappings by page
        for mapping in redaction_mappings:
            for page_info in mapping.get("pages", []):
                page_num = page_info.get("page")
                sensitive_items = page_info.get("sensitive", [])

                if page_num not in page_mappings:
                    page_mappings[page_num] = []

                page_mappings[page_num].extend(sensitive_items)

        # Create merged mapping
        for page_num, sensitive_items in sorted(page_mappings.items()):
            merged["pages"].append({
                "page": page_num,
                "sensitive": sensitive_items
            })

        return merged