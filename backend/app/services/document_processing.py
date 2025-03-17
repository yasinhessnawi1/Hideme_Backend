"""
Optimized document processing orchestration services that eliminate unnecessary file operations.

This module provides high-level services for orchestrating document processing workflows
with improved memory efficiency by minimizing temporary file creation and maximizing
in-memory processing where possible.
"""
import asyncio
import hashlib
import io
import os
import time
import uuid
from typing import Dict, Any, List, Optional, Union

from backend.app.document_processing.pdf import PDFTextExtractor
from backend.app.factory.document_processing_factory import (
    DocumentProcessingFactory,
    DocumentFormat,
    EntityDetectionEngine
)
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.data_minimization import minimize_extracted_data
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.helpers.json_helper import validate_requested_entities
from backend.app.utils.logger import log_info
from backend.app.utils.processing_records import record_keeper
from backend.app.utils.retention_management import retention_manager
from backend.app.utils.secure_file_utils import SecureTempFileManager
from backend.app.utils.secure_logging import log_sensitive_operation


class DocumentProcessingService:
    """
    Optimized service for orchestrating document processing workflows that minimizes
    unnecessary file operations.

    Features:
    - Uses cached detector instances from initialization service
    - Processes documents in memory where possible
    - Eliminates unnecessary temporary file creation
    - Parallel processing of documents and pages
    - Performance monitoring and statistics
    - Adaptive resource allocation
    - Comprehensive GDPR compliance
    - Enhanced error handling
    - Data minimization throughout the pipeline
    """
    _pdf_cache = {}  # Cache for PDF extraction results, keyed by content hash
    _pdf_cache_size = 10  # Maximum number of cached results
    _pdf_cache_lock = asyncio.Lock()  # Lock for thread-safety

    async def process_document_async(
            self,
            input_path: str,
            output_path: str,
            requested_entities: Optional[Union[str, List[str]]] = None,
            detection_engine: EntityDetectionEngine = EntityDetectionEngine.PRESIDIO,
            document_format: Optional[DocumentFormat] = None
    ) -> Dict[str, Any]:
        """
        Process a document for sensitive information and apply redactions asynchronously
        with optimized memory usage and reduced file operations.

        Args:
            input_path: Path to the input document
            output_path: Path to save the redacted document
            requested_entities: JSON string or list of entity types to detect
            detection_engine: Entity detection engine to use
            document_format: Format of the document (optional, will be detected if not provided)

        Returns:
            Dictionary with processing results and statistics
        """
        start_time = time.time()
        performance_metrics = {}
        operation_id = f"{os.path.basename(input_path)}_{uuid.uuid4().hex[:8]}"
        success = False
        stats = {"total_entities": 0}

        try:
            # Validate requested entities
            if isinstance(requested_entities, str):
                entity_list = validate_requested_entities(requested_entities)
            else:
                entity_list = requested_entities

            # Step 1: Read document content once to avoid multiple file operations
            with open(input_path, "rb") as f:
                document_content = f.read()

            # Determine document format if not provided
            if document_format is None:
                document_format = DocumentProcessingFactory._detect_format(input_path)

            # Step 2: Process based on document format using memory-based approach
            if document_format == DocumentFormat.PDF:
                extract_start = time.time()
                log_info(f"[OK] Extracting text from document using memory-based processing")

                # Calculate content hash for caching
                content_hash = hashlib.sha256(document_content).hexdigest()

                # Try to get from cache first
                async with self._pdf_cache_lock:
                    if content_hash in self._pdf_cache:
                        extracted_data = self._pdf_cache[content_hash]
                        log_info(f"[CACHE] Using cached PDF extraction result")
                    else:
                        # Use in-memory extraction for PDFs
                        buffer = io.BytesIO(document_content)
                        extracted_data = await self._extract_pdf_from_buffer(buffer)

                        # Update cache with LRU policy
                        if len(self._pdf_cache) >= self._pdf_cache_size:
                            # Remove oldest item (first item in the dict)
                            self._pdf_cache.pop(next(iter(self._pdf_cache)))
                        self._pdf_cache[content_hash] = extracted_data

                extract_time = time.time() - extract_start
                performance_metrics["extraction_time"] = extract_time
                log_info(f"[PERF] Text extraction completed in {extract_time:.2f}s")
            else:
                extract_start = time.time()
                log_info(f"[OK] Extracting text from document: {input_path}")
                extractor = DocumentProcessingFactory.create_document_extractor(
                    document_content, document_format
                )
                extracted_data = extractor.extract_text()
                extractor.close()

                extract_time = time.time() - extract_start
                performance_metrics["extraction_time"] = extract_time
                log_info(f"[PERF] Text extraction completed in {extract_time:.2f}s")

            # Apply data minimization for GDPR compliance
            minimized_data = minimize_extracted_data(extracted_data)

            # Step 3: Get entity detector from initialization service
            detector_start = time.time()
            log_info(f"[OK] Getting cached {detection_engine.name} detector")

            config = None
            if detection_engine == EntityDetectionEngine.HYBRID:
                config = {
                    "use_presidio": True,
                    "use_gemini": True,
                    "use_gliner": False
                }

            detector = initialization_service.get_detector(detection_engine, config=config)
            detector_time = time.time() - detector_start
            performance_metrics["detector_init_time"] = detector_time

            # Step 4: Detect sensitive data
            detection_start = time.time()
            log_info(f"[OK] Detecting sensitive information using {detection_engine.name}")

            if hasattr(detector, 'detect_sensitive_data_async'):
                anonymized_text, entities, redaction_mapping = await detector.detect_sensitive_data_async(
                    minimized_data, entity_list
                )
            else:
                anonymized_text, entities, redaction_mapping = await asyncio.to_thread(
                    detector.detect_sensitive_data, minimized_data, entity_list
                )
            detection_time = time.time() - detection_start
            performance_metrics["detection_time"] = detection_time
            log_info(f"[PERF] Entity detection completed in {detection_time:.2f}s")

            # Step 5: Apply redactions using memory-based approach for all document types
            redact_start = time.time()
            try:
                # Process PDFs entirely in memory
                if document_format == DocumentFormat.PDF:
                    # Use the PDFRedactionService to apply redactions in memory
                    from backend.app.document_processing.pdf import PDFRedactionService
                    redaction_service = PDFRedactionService(document_content)
                    redacted_content = await asyncio.to_thread(
                        redaction_service.apply_redactions_to_memory, redaction_mapping
                    )
                    with open(output_path, "wb") as f:
                        f.write(redacted_content)
                    redacted_path = output_path
                else:
                    # For other formats, use the memory-optimized approach when possible
                    redactor = DocumentProcessingFactory.create_document_redactor(
                        document_content if len(
                            document_content) < SecureTempFileManager.IN_MEMORY_THRESHOLD else input_path,
                        document_format
                    )
                    redacted_path = await asyncio.to_thread(
                        redactor.apply_redactions, redaction_mapping, output_path
                    )
            except Exception as e:
                SecurityAwareErrorHandler.log_processing_error(e, "document_redaction", input_path)
                raise

            redact_time = time.time() - redact_start
            performance_metrics["redaction_time"] = redact_time
            log_info(f"[PERF] Redaction completed in {redact_time:.2f}s")

            # Collect statistics
            stats = await self._collect_processing_stats(minimized_data, entities, redaction_mapping)
            stats["performance"] = performance_metrics
            stats["total_time"] = time.time() - start_time

            total_time = time.time() - start_time
            log_info(f"[PERF] Total document processing time: {total_time:.2f}s")
            log_sensitive_operation(
                "Document Processing",
                len(entities),
                total_time,
                engine=detection_engine.name,
                pages_count=len(minimized_data.get("pages", [])),
                extraction_time=extract_time,
                detection_time=detection_time,
                redaction_time=redact_time,
                operation_id=operation_id
            )

            success = True

            if output_path != input_path:
                retention_manager.register_processed_file(redacted_path)

            return {
                "status": "success",
                "input_path": input_path,
                "output_path": redacted_path,
                "entities_detected": len(entities),
                "stats": stats
            }
        except Exception as e:
            SecurityAwareErrorHandler.log_processing_error(
                e, "document_processing", input_path
            )
            return {
                "status": "error",
                "input_path": input_path,
                "error": str(e),
                "processing_time": time.time() - start_time
            }
        finally:
            total_time = time.time() - start_time
            record_keeper.record_processing(
                operation_type="document_processing",
                document_type=str(document_format) if document_format else "unknown",
                entity_types_processed=entity_list if entity_list else [],
                processing_time=total_time,
                file_count=1,
                entity_count=stats.get("total_entities", 0) if success else 0,
                success=success
            )

    async def _extract_pdf_from_buffer(self, buffer: io.BytesIO) -> Dict[str, Any]:
        """
        Extract text and positions from a PDF buffer without creating temporary files.

        Args:
            buffer: BytesIO buffer containing PDF data

        Returns:
            Dictionary with extracted text and position data
        """
        import pymupdf
        extracted_data = {"pages": []}
        try:
            pdf_document = pymupdf.open(stream=buffer, filetype="pdf")
            for page_num in range(len(pdf_document)):
                page = pdf_document[page_num]
                words = page.get_text("words")
                page_words = []
                for word in words:
                    x0, y0, x1, y1, text, *_ = word
                    if text.strip():
                        page_words.append({
                            "text": text.strip(),
                            "x0": x0,
                            "y0": y0,
                            "x1": x1,
                            "y1": y1
                        })
                if page_words:
                    extracted_data["pages"].append({
                        "page": page_num + 1,
                        "words": page_words
                    })
            metadata = pdf_document.metadata
            if metadata:
                from backend.app.utils.data_minimization import sanitize_document_metadata
                extracted_data["metadata"] = sanitize_document_metadata(metadata)
            pdf_document.close()
        except Exception as e:
            SecurityAwareErrorHandler.log_processing_error(
                e, "pdf_buffer_extraction", "memory_buffer"
            )
        return extracted_data

    async def process_document_stream(
            self,
            document_stream: bytes,
            output_path: str,
            document_format: DocumentFormat,
            requested_entities: Optional[Union[str, List[str]]] = None,
            detection_engine: EntityDetectionEngine = EntityDetectionEngine.PRESIDIO
    ) -> Dict[str, Any]:
        """
        Process a document stream directly in memory without creating unnecessary temporary files.

        This method is optimized to work directly with document bytes when possible.

        Args:
            document_stream: Bytes of the document content
            output_path: Path to save the redacted document
            document_format: Format of the document
            requested_entities: List of entity types to detect
            detection_engine: Entity detection engine to use

        Returns:
            Dictionary with processing results and statistics
        """
        start_time = time.time()
        performance_metrics = {}
        operation_id = f"stream_{uuid.uuid4().hex[:8]}"
        success = False
        stats = {"total_entities": 0}
        entity_list = []

        try:
            if isinstance(requested_entities, str):
                entity_list = validate_requested_entities(requested_entities)
            else:
                entity_list = requested_entities or []

            if document_format == DocumentFormat.PDF:
                import pymupdf
                extract_start = time.time()
                log_info(f"[OK] Extracting text from memory stream")
                buffer = io.BytesIO(document_stream)
                pdf_document = pymupdf.open(stream=buffer, filetype="pdf")
                extracted_data = {"pages": []}
                for page_num in range(len(pdf_document)):
                    page = pdf_document[page_num]
                    words = page.get_text("words")
                    page_words = []
                    for word in words:
                        x0, y0, x1, y1, text, *_ = word
                        if text.strip():
                            page_words.append({
                                "text": text.strip(),
                                "x0": x0,
                                "y0": y0,
                                "x1": x1,
                                "y1": y1
                            })
                    if page_words:
                        extracted_data["pages"].append({
                            "page": page_num + 1,
                            "words": page_words
                        })
                pdf_document.close()
                extract_time = time.time() - extract_start
                performance_metrics["extraction_time"] = extract_time

                minimized_data = minimize_extracted_data(extracted_data)
                detector_start = time.time()
                detector = initialization_service.get_detector(detection_engine)
                detector_time = time.time() - detector_start
                performance_metrics["detector_init_time"] = detector_time

                detection_start = time.time()
                if hasattr(detector, 'detect_sensitive_data_async'):
                    anonymized_text, entities, redaction_mapping = await detector.detect_sensitive_data_async(
                        minimized_data, entity_list
                    )
                else:
                    anonymized_text, entities, redaction_mapping = await asyncio.to_thread(
                        detector.detect_sensitive_data,
                        minimized_data, entity_list
                    )
                detection_time = time.time() - detection_start
                performance_metrics["detection_time"] = detection_time

                redact_start = time.time()
                from backend.app.document_processing.pdf import PDFRedactionService
                redaction_service = PDFRedactionService(document_stream)
                redacted_content = await asyncio.to_thread(
                    redaction_service.apply_redactions_to_memory, redaction_mapping
                )
                with open(output_path, "wb") as f:
                    f.write(redacted_content)
                output_pdf = output_path
                redact_time = time.time() - redact_start
                performance_metrics["redaction_time"] = redact_time

                stats = await self._collect_processing_stats(minimized_data, entities, redaction_mapping)
                stats["performance"] = performance_metrics
                stats["total_time"] = time.time() - start_time
                success = True
                total_time = time.time() - start_time
                log_sensitive_operation(
                    "Memory Stream Processing",
                    len(entities),
                    total_time,
                    engine=detection_engine.name,
                    pages_count=len(minimized_data.get("pages", [])),
                    extract_time=extract_time,
                    detection_time=detection_time,
                    redaction_time=redact_time,
                    operation_id=operation_id
                )

                return {
                    "status": "success",
                    "output_path": output_path,
                    "entities_detected": len(entities),
                    "stats": stats
                }
            else:
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=f".{document_format.name.lower()}") as temp_file:
                    temp_input_path = temp_file.name
                    temp_file.write(document_stream)
                try:
                    retention_manager.register_processed_file(temp_input_path)
                    result = await self.process_document_async(
                        temp_input_path,
                        output_path,
                        requested_entities,
                        detection_engine,
                        document_format
                    )
                    success = result.get("status") == "success"
                    if success:
                        stats = result.get("stats", {"total_entities": 0})
                    return result
                finally:
                    retention_manager.immediate_cleanup(temp_input_path)
        except Exception as e:
            SecurityAwareErrorHandler.log_processing_error(
                e, "document_stream_processing", operation_id
            )
            return {
                "status": "error",
                "error": str(e),
                "processing_time": time.time() - start_time
            }
        finally:
            total_time = time.time() - start_time
            record_keeper.record_processing(
                operation_type="document_stream_processing",
                document_type=str(document_format),
                entity_types_processed=entity_list,
                processing_time=total_time,
                file_count=1,
                entity_count=stats.get("total_entities", 0) if success else 0,
                success=success
            )

    async def _collect_processing_stats(
            self,
            extracted_data: Dict[str, Any],
            entities: List[Dict[str, Any]],
            redaction_mapping: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Collect statistics about the document processing.

        Args:
            extracted_data: Extracted text data
            entities: Detected entities
            redaction_mapping: Redaction mapping

        Returns:
            Dictionary with statistics
        """
        total_words = sum(
            len(page.get("words", []))
            for page in extracted_data.get("pages", [])
        )
        entities_by_type = {}
        for entity in entities:
            entity_type = entity.get("entity_type", "UNKNOWN")
            entities_by_type[entity_type] = entities_by_type.get(entity_type, 0) + 1
        sensitive_by_page = {}
        for page_info in redaction_mapping.get("pages", []):
            page_num = page_info.get("page")
            sensitive_items = page_info.get("sensitive", [])
            sensitive_by_page[f"page_{page_num}"] = len(sensitive_items)
        entity_density = (len(entities) / total_words) * 1000 if total_words > 0 else 0
        return {
            "total_pages": len(extracted_data.get("pages", [])),
            "total_words": total_words,
            "total_entities": len(entities),
            "entity_density": entity_density,
            "entities_by_type": entities_by_type,
            "sensitive_by_page": sensitive_by_page
        }


async def extraction_processor(content):
    # Check if content is a file-like object or bytes
    if hasattr(content, 'read'):
        # It's a file-like object, use it directly
        extractor = PDFTextExtractor(content)
        extracted_data = extractor.extract_text()
        extractor.close()
    else:
        # It's bytes, create a buffer
        buffer = io.BytesIO(content)
        extractor = PDFTextExtractor(buffer)
        extracted_data = extractor.extract_text()
        extractor.close()
    return extracted_data
