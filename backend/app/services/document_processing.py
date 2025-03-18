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

from backend.app.factory.document_processing_factory import (
    DocumentProcessingFactory,
    DocumentFormat,
    EntityDetectionEngine
)
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.data_minimization import minimize_extracted_data
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.helpers.json_helper import validate_requested_entities
from backend.app.utils.logger import log_info, log_warning, log_error
from backend.app.utils.processing_records import record_keeper
from backend.app.utils.retention_management import retention_manager
from backend.app.utils.secure_file_utils import SecureTempFileManager
from backend.app.utils.secure_logging import log_sensitive_operation
from backend.app.utils.synchronization_utils import AsyncTimeoutLock, LockPriority


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
    _pdf_cache_lock = AsyncTimeoutLock("pdf_cache_lock", priority=LockPriority.MEDIUM, timeout=3.0)

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

                # Try to get from cache with exponential backoff
                max_attempts = 3
                base_timeout = 1.0
                extracted_data = None

                # First check cache without lock for better performance
                if content_hash in self._pdf_cache:
                    extracted_data = self._pdf_cache[content_hash]
                    log_info(f"[CACHE] Using cached PDF extraction result (no lock required)")

                # If not in cache, try with lock
                if extracted_data is None:
                    for attempt in range(max_attempts):
                        # Exponential backoff for timeout
                        timeout = base_timeout * (2 ** attempt)

                        try:
                            # Use lock with timeout
                            async with self._pdf_cache_lock.acquire_timeout(timeout=timeout) as acquired:
                                if not acquired:
                                    # If lock acquisition failed but this is the last attempt,
                                    # proceed without caching
                                    if attempt == max_attempts - 1:
                                        log_warning(f"[CACHE] Final lock acquisition attempt failed, processing without caching")
                                        buffer = io.BytesIO(document_content)
                                        extracted_data = await self._extract_pdf_from_buffer(buffer, use_cache=False)
                                        break
                                    else:
                                        log_warning(f"[CACHE] Lock acquisition attempt {attempt+1}/{max_attempts} failed, retrying...")
                                        if attempt < max_attempts - 1:
                                            await asyncio.sleep(0.1 * (2 ** attempt))  # Increasing delay before retry
                                        continue

                                # Double-check if another thread added it to cache while we were waiting
                                if content_hash in self._pdf_cache:
                                    extracted_data = self._pdf_cache[content_hash]
                                    log_info(f"[CACHE] Using cached PDF extraction result (double-checked)")
                                    break

                                # Not in cache, extract it
                                buffer = io.BytesIO(document_content)
                                extracted_data = await self._extract_pdf_from_buffer(buffer, use_cache=True)

                                # Update cache with LRU policy
                                if len(self._pdf_cache) >= self._pdf_cache_size:
                                    # Remove oldest item (first item in the dict)
                                    self._pdf_cache.pop(next(iter(self._pdf_cache)))
                                self._pdf_cache[content_hash] = extracted_data
                                log_info(f"[CACHE] Added PDF extraction result to cache")
                                break

                        except Exception as e:
                            log_warning(f"[CACHE] Error during attempt {attempt+1}/{max_attempts} to acquire PDF cache lock: {str(e)}")
                            if attempt == max_attempts - 1:
                                # Final fallback: process without caching
                                buffer = io.BytesIO(document_content)
                                extracted_data = await self._extract_pdf_from_buffer(buffer, use_cache=False)
                                log_warning(f"[CACHE] Processed without caching after lock error")
                            elif attempt < max_attempts - 1:
                                await asyncio.sleep(0.1 * (2 ** attempt))  # Increasing delay before retry

                # If all attempts failed, make sure we have extraction data
                if extracted_data is None:
                    log_warning(f"[CACHE] All cache attempts failed, processing without caching as last resort")
                    buffer = io.BytesIO(document_content)
                    extracted_data = await self._extract_pdf_from_buffer(buffer, use_cache=False)

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

            # Use detector with timeout
            max_detector_attempts = 3
            base_detector_timeout = 2.0
            detector = None

            for attempt in range(max_detector_attempts):
                try:
                    detector = initialization_service.get_detector(detection_engine, config=config)
                    if detector:
                        break
                except Exception as e:
                    log_warning(f"[DETECTOR] Error getting detector on attempt {attempt+1}/{max_detector_attempts}: {str(e)}")
                    if attempt < max_detector_attempts - 1:
                        # Wait before retry with increasing backoff
                        await asyncio.sleep(0.2 * (2 ** attempt))

            # If all attempts fail, raise exception
            if detector is None:
                raise ValueError(f"Failed to initialize {detection_engine.name} detector after {max_detector_attempts} attempts")

            detector_time = time.time() - detector_start
            performance_metrics["detector_init_time"] = detector_time

            # Step 4: Detect sensitive data
            detection_start = time.time()
            log_info(f"[OK] Detecting sensitive information using {detection_engine.name}")

            # Use shorter timeout for detection
            detection_timeout = 40
            try:
                if hasattr(detector, 'detect_sensitive_data_async'):
                    detection_task = detector.detect_sensitive_data_async(minimized_data, entity_list)
                    anonymized_text, entities, redaction_mapping = await asyncio.wait_for(
                        detection_task,
                        timeout=detection_timeout
                    )
                else:
                    detection_future = asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: detector.detect_sensitive_data(minimized_data, entity_list)
                    )
                    anonymized_text, entities, redaction_mapping = await asyncio.wait_for(
                        detection_future,
                        timeout=detection_timeout
                    )
            except asyncio.TimeoutError:
                log_error(f"[DETECTION] Timed out after {detection_timeout}s")
                raise TimeoutError(f"Detection operation timed out after {detection_timeout} seconds")

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

                    # Use timeout for redaction
                    redaction_timeout = 60  # Redaction can take longer than detection
                    redaction_service = PDFRedactionService(document_content)

                    # Process with timeout
                    redaction_future = asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: redaction_service.apply_redactions_to_memory(redaction_mapping)
                    )
                    try:
                        redacted_content = await asyncio.wait_for(redaction_future, timeout=redaction_timeout)
                    except asyncio.TimeoutError:
                        log_error(f"[REDACTION] Timed out after {redaction_timeout}s")
                        raise TimeoutError(f"Redaction operation timed out after {redaction_timeout} seconds")

                    with open(output_path, "wb") as f:
                        f.write(redacted_content)
                    redacted_path = output_path
                else:
                    # For other formats, use the memory-optimized approach when possible
                    redaction_timeout = 60  # Redaction can take longer than detection

                    redactor = DocumentProcessingFactory.create_document_redactor(
                        document_content if len(
                            document_content) < SecureTempFileManager.IN_MEMORY_THRESHOLD else input_path,
                        document_format
                    )

                    # Process with timeout
                    redaction_future = asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: redactor.apply_redactions(redaction_mapping, output_path)
                    )
                    try:
                        redacted_path = await asyncio.wait_for(redaction_future, timeout=redaction_timeout)
                    except asyncio.TimeoutError:
                        log_error(f"[REDACTION] Timed out after {redaction_timeout}s")
                        raise TimeoutError(f"Redaction operation timed out after {redaction_timeout} seconds")

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

    async def _extract_pdf_from_buffer(self, buffer: io.BytesIO, use_cache: bool = True) -> Dict[str, Any]:
        """
        Extract text and positions from a PDF buffer without creating temporary files.

        Args:
            buffer: BytesIO buffer containing PDF data
            use_cache: Whether to use caching for results

        Returns:
            Dictionary with extracted text and position data
        """
        import pymupdf
        extracted_data = {"pages": []}
        try:
            # Set a timeout for PDF processing to prevent hanging
            extraction_timeout = 30  # 30 seconds for PDF extraction

            # Define extraction function for timeout
            def extract_pdf():
                pdf_document = pymupdf.open(stream=buffer, filetype="pdf")
                result = {"pages": []}

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
                        result["pages"].append({
                            "page": page_num + 1,
                            "words": page_words
                        })

                # Add metadata if available
                try:
                    metadata = pdf_document.metadata
                    if metadata:
                        from backend.app.utils.data_minimization import sanitize_document_metadata
                        result["metadata"] = sanitize_document_metadata(metadata)
                except Exception as meta_error:
                    log_warning(f"[PDF] Error extracting metadata: {str(meta_error)}")

                pdf_document.close()
                return result

            # Run extraction with timeout
            try:
                # Convert to async task with timeout
                extraction_future = asyncio.get_event_loop().run_in_executor(None, extract_pdf)
                extracted_data = await asyncio.wait_for(extraction_future, timeout=extraction_timeout)
            except asyncio.TimeoutError:
                log_error(f"[PDF] Extraction timed out after {extraction_timeout}s")
                raise TimeoutError(f"PDF extraction timed out after {extraction_timeout} seconds")

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

                # Process PDF with timeout
                extraction_timeout = 30  # 30 seconds for PDF extraction

                try:
                    buffer = io.BytesIO(document_stream)
                    extracted_data = await self._extract_pdf_from_buffer(buffer, use_cache=False)
                except TimeoutError:
                    log_error(f"[STREAM] PDF extraction timed out after {extraction_timeout}s")
                    raise

                extract_time = time.time() - extract_start
                performance_metrics["extraction_time"] = extract_time

                minimized_data = minimize_extracted_data(extracted_data)

                # Get detector with backoff strategy
                detector_start = time.time()
                max_detector_attempts = 3
                base_detector_timeout = 2.0
                detector = None

                for attempt in range(max_detector_attempts):
                    try:
                        detector = initialization_service.get_detector(detection_engine)
                        if detector:
                            break
                    except Exception as e:
                        log_warning(f"[DETECTOR] Error getting detector on attempt {attempt+1}/{max_detector_attempts}: {str(e)}")
                        if attempt < max_detector_attempts - 1:
                            # Wait before retry with increasing backoff
                            await asyncio.sleep(0.2 * (2 ** attempt))

                # If all attempts fail, raise exception
                if detector is None:
                    raise ValueError(f"Failed to initialize {detection_engine.name} detector after {max_detector_attempts} attempts")

                detector_time = time.time() - detector_start
                performance_metrics["detector_init_time"] = detector_time

                # Detection with timeout
                detection_start = time.time()
                detection_timeout = 40  # 40 seconds timeout for detection

                try:
                    if hasattr(detector, 'detect_sensitive_data_async'):
                        detection_task = detector.detect_sensitive_data_async(minimized_data, entity_list)
                        anonymized_text, entities, redaction_mapping = await asyncio.wait_for(
                            detection_task,
                            timeout=detection_timeout
                        )
                    else:
                        detection_future = asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda: detector.detect_sensitive_data(minimized_data, entity_list)
                        )
                        anonymized_text, entities, redaction_mapping = await asyncio.wait_for(
                            detection_future,
                            timeout=detection_timeout
                        )
                except asyncio.TimeoutError:
                    log_error(f"[STREAM] Detection timed out after {detection_timeout}s")
                    raise TimeoutError(f"Detection operation timed out after {detection_timeout} seconds")

                detection_time = time.time() - detection_start
                performance_metrics["detection_time"] = detection_time

                # Redaction with timeout
                redact_start = time.time()
                redaction_timeout = 60  # 60 seconds for redaction

                try:
                    from backend.app.document_processing.pdf import PDFRedactionService
                    redaction_service = PDFRedactionService(document_stream)

                    redaction_future = asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: redaction_service.apply_redactions_to_memory(redaction_mapping)
                    )
                    redacted_content = await asyncio.wait_for(redaction_future, timeout=redaction_timeout)

                    with open(output_path, "wb") as f:
                        f.write(redacted_content)
                except asyncio.TimeoutError:
                    log_error(f"[STREAM] Redaction timed out after {redaction_timeout}s")
                    raise TimeoutError(f"Redaction operation timed out after {redaction_timeout} seconds")

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
                # Use temp files with shorter retention for non-PDF formats
                with tempfile.NamedTemporaryFile(delete=False, suffix=f".{document_format.name.lower()}") as temp_file:
                    temp_input_path = temp_file.name
                    temp_file.write(document_stream)
                try:
                    # Register for cleanup with shorter retention time
                    retention_manager.register_processed_file(temp_input_path, retention_seconds=300)  # 5 minutes max

                    # Process using the async method with standard timeouts
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
                    # Force immediate cleanup instead of waiting for retention manager
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