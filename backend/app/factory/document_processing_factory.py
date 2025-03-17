"""
Factory for creating document processing components.
"""
import io
import zipfile
from enum import Enum, auto
from typing import Dict, Any, Optional, Union

from backend.app.configs.gliner_config import GLINER_MODEL_NAME, GLINER_MODEL_PATH, GLINER_ENTITIES
from backend.app.domain.interfaces import DocumentExtractor, EntityDetector, DocumentRedactor
from backend.app.document_processing.pdf import PDFTextExtractor, PDFRedactionService
from backend.app.entity_detection.presidio import PresidioEntityDetector
from backend.app.entity_detection.gemini import GeminiEntityDetector
from backend.app.entity_detection.gliner import GlinerEntityDetector
from backend.app.utils.retention_management import retention_manager
from backend.app.utils.secure_file_utils import SecureTempFileManager


class DocumentFormat(Enum):
    """Supported document formats."""
    PDF = auto()
    DOCX = auto()
    TXT = auto()
    # Add more formats later


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
            document_input: Union[str, io.BytesIO],
            document_format: Optional[DocumentFormat] = None
    ) -> DocumentExtractor:
        """
        Create a document extractor for the specified format with improved handling of input types.

        Args:
            document_input: A file path to the document, an in-memory BytesIO buffer,
                           or bytes containing document data.
            document_format: Format of the document. If not provided and document_input is a string,
                             the format is detected based on the file signature.
                             If document_input is not a string, PDF is assumed.

        Returns:
            DocumentExtractor instance.

        Raises:
            ValueError: If document format is not supported.
        """
        # Handle bytes input by converting to BytesIO
        if isinstance(document_input, bytes):
            # Use SecureTempFileManager's buffer pooling
            buffer = SecureTempFileManager.buffer_or_file_based_on_size(document_input)

            # If we got a file path back instead of a buffer, register it for cleanup
            if isinstance(buffer, str):
                retention_manager.register_processed_file(buffer)
                document_input = buffer
            else:
                document_input = buffer

        if not isinstance(document_input, str):
            # When an in-memory buffer is provided, default to PDF if not explicitly set
            if document_format is None:
                document_format = DocumentFormat.PDF
        else:
            # Input is a file path string; auto-detect format if not provided
            if document_format is None:
                document_format = DocumentProcessingFactory._detect_format(document_input)

        if document_format == DocumentFormat.PDF:
            return PDFTextExtractor(document_input)
        elif document_format == DocumentFormat.DOCX:
            # Future implementation
            raise ValueError("DOCX extraction not implemented yet")
        elif document_format == DocumentFormat.TXT:
            # Future implementation
            raise ValueError("TXT extraction not implemented yet")
        else:
            raise ValueError(f"Unsupported document format: {document_format}")

    @staticmethod
    def open_pdf_from_buffer(buffer: io.BytesIO) -> Any:
        """
        Open a PDF document from an in-memory buffer using PyMuPDF.

        Args:
            buffer: BytesIO buffer containing PDF data.

        Returns:
            A PyMuPDF Document instance.
        """
        import pymupdf
        return pymupdf.open(stream=buffer, filetype="pdf")

    @staticmethod
    def create_entity_detector(
            engine: EntityDetectionEngine = EntityDetectionEngine.PRESIDIO,
            config: Optional[Dict[str, Any]] = None
    ) -> EntityDetector:
        """
        Create an entity detector using the specified engine.

        Args:
            engine: Entity detection engine to use.
            config: Configuration for the detector (optional).

        Returns:
            EntityDetector instance.

        Raises:
            ValueError: If the engine is not supported.
        """
        if engine == EntityDetectionEngine.PRESIDIO:
            return PresidioEntityDetector()
        elif engine == EntityDetectionEngine.GEMINI:
            return GeminiEntityDetector()
        elif engine == EntityDetectionEngine.GLINER:
            config = config or {}
            model_name = config.get("model_name", GLINER_MODEL_NAME)
            entities = config.get("entities", GLINER_ENTITIES)
            local_model_path = config.get("local_model_path", GLINER_MODEL_PATH)
            local_files_only = config.get("local_files_only", False)
            return GlinerEntityDetector(
                model_name=model_name,
                entities=entities,
                local_model_path=local_model_path,
                local_files_only=local_files_only
            )
        elif engine == EntityDetectionEngine.HYBRID:
            from backend.app.entity_detection.hybrid import HybridEntityDetector
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
            document_path: Path to the document.
            document_format: Format of the document (optional; will be detected if not provided).

        Returns:
            DocumentRedactor instance.

        Raises:
            ValueError: If document format is not supported.
        """
        if document_format is None:
            document_format = DocumentProcessingFactory._detect_format(document_path)

        if document_format == DocumentFormat.PDF:
            return PDFRedactionService(document_path)
        elif document_format == DocumentFormat.DOCX:
            raise ValueError("DOCX redaction not implemented yet")
        elif document_format == DocumentFormat.TXT:
            raise ValueError("TXT redaction not implemented yet")
        else:
            raise ValueError(f"Unsupported document format: {document_format}")

    @staticmethod
    def _detect_format(document_path: str) -> DocumentFormat:
        """
        Detect document format based on file signature.

        This method reads the first few bytes of the file to determine its format,
        offering a more reliable detection than using file extensions alone.

        Args:
            document_path: Path to the document.

        Returns:
            DocumentFormat enum value.

        Raises:
            ValueError: If the format cannot be determined.
        """
        try:
            with open(document_path, 'rb') as f:
                header = f.read(16)
        except Exception as e:
            raise ValueError(f"Cannot read document: {document_path}") from e

        if header.startswith(b'%PDF'):
            return DocumentFormat.PDF
        elif header.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
            # Likely an older DOC file (OLE Compound File)
            return DocumentFormat.DOCX
        elif header.startswith(b'PK'):
            # Likely a ZIP-based file; check for DOCX-specific structure
            try:
                with zipfile.ZipFile(document_path) as zf:
                    if '[Content_Types].xml' in zf.namelist():
                        return DocumentFormat.DOCX
            except Exception:
                pass
            # Fallback: if not DOCX structure, treat as TXT
            return DocumentFormat.TXT
        else:
            # Default to TXT if no known signature is found
            return DocumentFormat.TXT
