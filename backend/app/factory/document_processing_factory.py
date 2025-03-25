"""
Enhanced factory for creating document processing components with batch support.

This module provides factory methods for creating document extractors, entity detectors,
and document redactors with comprehensive support for both single document and batch
processing operations with optimized parallel execution.
"""
import io
import zipfile
import os
from enum import Enum, auto
from typing import Dict, Any, Optional, Union, List, Tuple, BinaryIO

import pymupdf

from backend.app.configs.gliner_config import GLINER_MODEL_NAME, GLINER_MODEL_PATH, GLINER_ENTITIES
from backend.app.domain.interfaces import DocumentExtractor, EntityDetector, DocumentRedactor
from backend.app.document_processing.pdf import PDFTextExtractor, PDFRedactionService
from backend.app.entity_detection.presidio import PresidioEntityDetector
from backend.app.entity_detection.gemini import GeminiEntityDetector
from backend.app.entity_detection.gliner import GlinerEntityDetector
from backend.app.utils.security.retention_management import retention_manager
from backend.app.utils.secure_file_utils import SecureTempFileManager
from backend.app.utils.logging.logger import log_info, log_warning, log_error


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
    Enhanced factory for creating document processing components based on format and configuration.
    Supports both single document and batch operations with parallel processing.

    Key features:
    - Unified creation of extractors and redactors for single and batch operations
    - Memory-optimized processing for large documents
    - Support for in-memory document processing to avoid file I/O
    - Automatic format detection from file content
    - Enhanced error handling and resource management
    """

    @staticmethod
    def create_document_extractor(
            document_input: Union[str, io.BytesIO, bytes, BinaryIO],
            document_format: Optional[DocumentFormat] = None,
            detect_images: bool = False,
            remove_images: bool = False
    ) -> DocumentExtractor:
        """
        Create a document extractor for the specified format with improved handling of input types.

        Args:
            document_input: A file path, BytesIO buffer, bytes, or file-like object
            document_format: Format of the document (detected automatically if None)
            detect_images: Whether to detect and include image information
            remove_images: Whether to remove images during extraction (PDF only)

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
            return PDFTextExtractor(document_input, page_batch_size=20)
        elif document_format == DocumentFormat.DOCX:
            # Future implementation
            raise ValueError("DOCX extraction not implemented yet")
        elif document_format == DocumentFormat.TXT:
            # Future implementation
            raise ValueError("TXT extraction not implemented yet")
        else:
            raise ValueError(f"Unsupported document format: {document_format}")

    @staticmethod
    async def extract_batch_documents(
            documents: List[Union[str, bytes, io.BytesIO, BinaryIO]],
            document_formats: Optional[List[DocumentFormat]] = None,
            max_workers: Optional[int] = None,
            detect_images: bool = False,
            remove_images: bool = False
    ) -> List[Tuple[int, Dict[str, Any]]]:
        """
        Extract text from multiple documents in parallel with optimized resource utilization.

        Args:
            documents: List of document inputs (paths, bytes, or file-like objects)
            document_formats: Optional formats corresponding to each document
            max_workers: Maximum number of parallel workers (None for auto-configuration)
            detect_images: Whether to detect and include image information (PDF only)
            remove_images: Whether to remove images during extraction (PDF only)

        Returns:
            List of tuples (index, extraction_result)

        Raises:
            ValueError: If input parameters are invalid
        """
        # Validate inputs
        if not documents:
            return []

        # Detect PDF files to use the optimized batch processor
        pdf_indices = []
        pdf_documents = []
        non_pdf_indices = []
        non_pdf_documents = []
        non_pdf_formats = []

        # Separate PDFs from other document types
        for i, doc in enumerate(documents):
            doc_format = None
            if document_formats and i < len(document_formats):
                doc_format = document_formats[i]

            # Detect format if not provided
            if doc_format is None:
                if isinstance(doc, str):
                    doc_format = DocumentProcessingFactory._detect_format(doc)
                else:
                    # Default to PDF for in-memory content
                    doc_format = DocumentFormat.PDF

            # Separate PDFs from other document types
            if doc_format == DocumentFormat.PDF:
                pdf_indices.append(i)
                pdf_documents.append(doc)
            else:
                non_pdf_indices.append(i)
                non_pdf_documents.append(doc)
                non_pdf_formats.append(doc_format)

        # Process PDFs with the optimized batch processor
        pdf_results = []
        if pdf_documents:
            log_info(f"Processing {len(pdf_documents)} PDF documents with optimized batch processor")
            try:
                pdf_batch_results = await PDFTextExtractor.extract_batch_text(
                    pdf_documents,
                    max_workers=max_workers,
                    detect_images=detect_images,
                    remove_images=remove_images
                )

                # Map results back to original indices
                for i, (_, result) in enumerate(pdf_batch_results):
                    pdf_results.append((pdf_indices[i], result))
            except Exception as e:
                log_error(f"Error in batch PDF processing: {str(e)}")
                # Fall back to individual processing for PDFs
                for i, doc in zip(pdf_indices, pdf_documents):
                    try:
                        extractor = PDFTextExtractor(doc)
                        result = extractor.extract_text(detect_images=detect_images, remove_images=remove_images)
                        extractor.close()
                        pdf_results.append((i, result))
                    except Exception as doc_e:
                        log_error(f"Error processing PDF at index {i}: {str(doc_e)}")
                        pdf_results.append((i, {"error": str(doc_e), "pages": []}))

        # Process non-PDF documents individually (to be enhanced in future versions)
        non_pdf_results = []
        if non_pdf_documents:
            log_info(f"Processing {len(non_pdf_documents)} non-PDF documents individually")
            for i, (idx, doc, fmt) in enumerate(zip(non_pdf_indices, non_pdf_documents, non_pdf_formats)):
                try:
                    extractor = DocumentProcessingFactory.create_document_extractor(doc, fmt)
                    result = extractor.extract_text()
                    extractor.close()
                    non_pdf_results.append((idx, result))
                except Exception as e:
                    log_error(f"Error processing non-PDF document at index {idx}: {str(e)}")
                    non_pdf_results.append((idx, {"error": str(e), "pages": []}))

        # Combine and sort results by original index
        all_results = pdf_results + non_pdf_results
        return sorted(all_results, key=lambda x: x[0])

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
            document_input: Union[str, pymupdf.Document, bytes, BinaryIO],
            document_format: Optional[DocumentFormat] = None,
            page_batch_size: int = 5
    ) -> DocumentRedactor:
        """
        Create a document redactor for the specified format with enhanced flexibility.

        Args:
            document_input: A file path, PyMuPDF Document, bytes, or file-like object
            document_format: Format of the document (detected automatically if None)
            page_batch_size: Number of pages to process in a batch for large documents

        Returns:
            DocumentRedactor instance.

        Raises:
            ValueError: If document format is not supported.
        """
        if document_format is None and isinstance(document_input, str):
            document_format = DocumentProcessingFactory._detect_format(document_input)
        elif document_format is None:
            # Default to PDF for in-memory content
            document_format = DocumentFormat.PDF

        if document_format == DocumentFormat.PDF:
            return PDFRedactionService(document_input, page_batch_size=page_batch_size)
        elif document_format == DocumentFormat.DOCX:
            raise ValueError("DOCX redaction not implemented yet")
        elif document_format == DocumentFormat.TXT:
            raise ValueError("TXT redaction not implemented yet")
        else:
            raise ValueError(f"Unsupported document format: {document_format}")

    @staticmethod
    async def redact_batch_documents(
            documents: List[Union[str, bytes, BinaryIO]],
            redaction_mappings: List[Dict[str, Any]],
            output_paths: List[str],
            document_formats: Optional[List[DocumentFormat]] = None,
            max_workers: Optional[int] = None
    ) -> List[Tuple[int, Dict[str, Any]]]:
        """
        Apply redactions to multiple documents in parallel with optimized resource utilization.

        Args:
            documents: List of document inputs (paths, bytes, or file-like objects)
            redaction_mappings: List of redaction mappings corresponding to each document
            output_paths: List of output paths for redacted documents
            document_formats: Optional formats corresponding to each document
            max_workers: Maximum number of parallel workers (None for auto-configuration)

        Returns:
            List of tuples (index, redaction_result)

        Raises:
            ValueError: If input parameters are invalid
        """
        # Validate inputs
        if len(documents) != len(redaction_mappings) or len(documents) != len(output_paths):
            raise ValueError("The lengths of documents, redaction_mappings, and output_paths must be the same")

        if not documents:
            return []

        # Detect PDF files to use the optimized batch processor
        pdf_indices = []
        pdf_documents = []
        pdf_mappings = []
        pdf_outputs = []
        non_pdf_indices = []
        non_pdf_documents = []
        non_pdf_mappings = []
        non_pdf_outputs = []
        non_pdf_formats = []

        # Separate PDFs from other document types
        for i, (doc, mapping, output) in enumerate(zip(documents, redaction_mappings, output_paths)):
            doc_format = None
            if document_formats and i < len(document_formats):
                doc_format = document_formats[i]

            # Detect format if not provided
            if doc_format is None:
                if isinstance(doc, str):
                    doc_format = DocumentProcessingFactory._detect_format(doc)
                else:
                    # Default to PDF for in-memory content
                    doc_format = DocumentFormat.PDF

            # Separate PDFs from other document types
            if doc_format == DocumentFormat.PDF:
                pdf_indices.append(i)
                pdf_documents.append(doc)
                pdf_mappings.append(mapping)
                pdf_outputs.append(output)
            else:
                non_pdf_indices.append(i)
                non_pdf_documents.append(doc)
                non_pdf_mappings.append(mapping)
                non_pdf_outputs.append(output)
                non_pdf_formats.append(doc_format)

        # Process PDFs with the optimized batch processor
        pdf_results = []
        if pdf_documents:
            log_info(f"Redacting {len(pdf_documents)} PDF documents with optimized batch processor")
            try:
                pdf_batch_results = await PDFRedactionService.redact_batch(
                    pdf_documents,
                    pdf_mappings,
                    pdf_outputs,
                    max_workers=max_workers
                )

                # Map results back to original indices
                for i, (_, result) in enumerate(pdf_batch_results):
                    pdf_results.append((pdf_indices[i], result))
            except Exception as e:
                log_error(f"Error in batch PDF redaction: {str(e)}")
                # Fall back to individual processing for PDFs
                for i, (doc, mapping, output) in enumerate(zip(pdf_documents, pdf_mappings, pdf_outputs)):
                    try:
                        redactor = PDFRedactionService(doc)
                        result_path = redactor.apply_redactions(mapping, output)
                        redactor.close()
                        pdf_results.append((pdf_indices[i], {
                            "status": "success",
                            "output_path": result_path
                        }))
                    except Exception as doc_e:
                        log_error(f"Error redacting PDF at index {pdf_indices[i]}: {str(doc_e)}")
                        pdf_results.append((pdf_indices[i], {
                            "status": "error",
                            "error": str(doc_e)
                        }))

        # Process non-PDF documents individually (to be enhanced in future versions)
        non_pdf_results = []
        if non_pdf_documents:
            log_info(f"Redacting {len(non_pdf_documents)} non-PDF documents individually")
            for i, (idx, doc, fmt, mapping, output) in enumerate(zip(
                non_pdf_indices, non_pdf_documents, non_pdf_formats, non_pdf_mappings, non_pdf_outputs
            )):
                try:
                    redactor = DocumentProcessingFactory.create_document_redactor(doc, fmt)
                    result_path = redactor.apply_redactions(mapping, output)
                    redactor.close()
                    non_pdf_results.append((idx, {
                        "status": "success",
                        "output_path": result_path
                    }))
                except Exception as e:
                    log_error(f"Error redacting non-PDF document at index {idx}: {str(e)}")
                    non_pdf_results.append((idx, {
                        "status": "error",
                        "error": str(e)
                    }))

        # Combine and sort results by original index
        all_results = pdf_results + non_pdf_results
        return sorted(all_results, key=lambda x: x[0])

    @staticmethod
    def _detect_format(document_path: str) -> DocumentFormat:
        """
        Detect document format based on file signature and extension.

        This method uses a combination of file extension and content inspection to
        determine the document format more reliably than using either approach alone.

        Args:
            document_path: Path to the document.

        Returns:
            DocumentFormat enum value.

        Raises:
            ValueError: If the format cannot be determined.
        """
        # First check by extension for efficiency
        _, ext = os.path.splitext(document_path.lower())

        # Quick check by extension first
        if ext == '.pdf':
            return DocumentFormat.PDF
        elif ext in ['.docx', '.doc']:
            return DocumentFormat.DOCX
        elif ext in ['.txt', '.text', '.md', '.csv', '.json']:
            return DocumentFormat.TXT

        # Fall back to content inspection for more reliable detection
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

    @staticmethod
    def open_pdf_from_buffer(buffer: io.BytesIO) -> Any:
        """
        Open a PDF document from an in-memory buffer using PyMuPDF.

        This utility method is provided for backward compatibility.

        Args:
            buffer: BytesIO buffer containing PDF data.

        Returns:
            A PyMuPDF Document instance.
        """
        import pymupdf
        return pymupdf.open(stream=buffer, filetype="pdf")