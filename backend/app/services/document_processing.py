"""
Optimized document processing services leveraging centralized PDF processing.

This module provides high-level services for orchestrating document processing workflows
with improved memory efficiency by utilizing the centralized PDF processing functionality
and eliminating unnecessary file operations.
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
from backend.app.document_processing.pdf import PDFTextExtractor, PDFRedactionService
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.validation.data_minimization import minimize_extracted_data
from backend.app.utils.error_handling import SecurityAwareErrorHandler
from backend.app.utils.helpers.json_helper import validate_requested_entities
from backend.app.utils.logging.logger import log_info, log_warning, log_error
from backend.app.utils.security.processing_records import record_keeper
from backend.app.utils.security.retention_management import retention_manager
from backend.app.utils.secure_file_utils import SecureTempFileManager
from backend.app.utils.logging.secure_logging import log_sensitive_operation
from backend.app.utils.memory_management import memory_monitor


class DocumentProcessingService:
    """
    Optimized service for orchestrating document processing workflows that
    leverages centralized PDF processing functionality.

    Features:
    - Uses centralized PDFTextExtractor and PDFRedactionService for consistent processing
    - Processes documents in memory where possible
    - Eliminates unnecessary temporary file creation
    - Utilizes batch processing when appropriate
    - Comprehensive GDPR compliance
    - Enhanced error handling and recovery
    """

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
        entity_list = []

        try:
            # Validate requested entities
            if isinstance(requested_entities, str):
                entity_list = validate_requested_entities(requested_entities)
            else:
                entity_list = requested_entities or []

            # Determine document format if not provided
            if document_format is None:
                document_format = DocumentProcessingFactory._detect_format(input_path)

            # Step 1: Extract text data using the centralized PDFTextExtractor
            extract_start = time.time()
            log_info(f"[OK] Extracting text from document: {input_path}")

            if document_format == DocumentFormat.PDF:
                # Use centralized PDF text extractor
                extractor = PDFTextExtractor(input_path)
                extracted_data = extractor.extract_text(detect_images=True)
                extractor.close()
            else:
                # Use factory for other document types
                extractor = DocumentProcessingFactory.create_document_extractor(input_path, document_format)
                extracted_data = extractor.extract_text()
                extractor.close()

            extract_time = time.time() - extract_start
            performance_metrics["extraction_time"] = extract_time
            log_info(f"[PERF] Text extraction completed in {extract_time:.2f}s")

            # Apply data minimization for GDPR compliance
            minimized_data = minimize_extracted_data(extracted_data)

            # Step 2: Get entity detector from initialization service
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
            detector = initialization_service.get_detector(detection_engine, config=config)
            detector_time = time.time() - detector_start
            performance_metrics["detector_init_time"] = detector_time

            # Step 3: Detect sensitive data
            detection_start = time.time()
            log_info(f"[OK] Detecting sensitive information using {detection_engine.name}")

            # Use shorter timeout for detection
            detection_timeout = 60  # 60 seconds for detection
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

            # Step 4: Apply redactions using the centralized PDFRedactionService
            redact_start = time.time()

            if document_format == DocumentFormat.PDF:
                # Use centralized PDF redaction service
                redactor = PDFRedactionService(input_path)
                redacted_path = redactor.apply_redactions(redaction_mapping, output_path)
                redactor.close()
            else:
                # Use factory for other document types
                redactor = DocumentProcessingFactory.create_document_redactor(input_path, document_format)
                redacted_path = redactor.apply_redactions(redaction_mapping, output_path)
                redactor.close()

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
                entity_types_processed=entity_list,
                processing_time=total_time,
                file_count=1,
                entity_count=stats.get("total_entities", 0) if success else 0,
                success=success
            )

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

        This method is optimized to work directly with document bytes using the centralized
        PDF processing functionality.

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
            # Validate requested entities
            if isinstance(requested_entities, str):
                entity_list = validate_requested_entities(requested_entities)
            else:
                entity_list = requested_entities or []

            # Step 1: Extract text data using the centralized PDF processing
            extract_start = time.time()
            log_info(f"[OK] Extracting text from memory stream")

            if document_format == DocumentFormat.PDF:
                # Use centralized PDF text extractor for direct memory processing
                extractor = PDFTextExtractor(document_stream)
                extracted_data = extractor.extract_text(detect_images=True)
                extractor.close()
            else:
                # For non-PDF formats, use a temporary file approach
                with SecureTempFileManager.create_temp_file(
                    suffix=f".{document_format.name.lower()}",
                    content=document_stream
                ) as temp_path:
                    extractor = DocumentProcessingFactory.create_document_extractor(temp_path, document_format)
                    extracted_data = extractor.extract_text()
                    extractor.close()

            extract_time = time.time() - extract_start
            performance_metrics["extraction_time"] = extract_time
            log_info(f"[PERF] Stream extraction completed in {extract_time:.2f}s")

            # Apply data minimization for GDPR compliance
            minimized_data = minimize_extracted_data(extracted_data)

            # Step 2: Get entity detector from initialization service
            detector_start = time.time()
            detector = initialization_service.get_detector(detection_engine)
            detector_time = time.time() - detector_start
            performance_metrics["detector_init_time"] = detector_time

            # Step 3: Detect sensitive data
            detection_start = time.time()
            log_info(f"[OK] Detecting sensitive information using {detection_engine.name}")

            # Detection with timeout
            detection_timeout = 60  # 60 seconds timeout for detection

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

            detection_time = time.time() - detection_start
            performance_metrics["detection_time"] = detection_time
            log_info(f"[PERF] Stream detection completed in {detection_time:.2f}s")

            # Step 4: Apply redactions
            redact_start = time.time()

            if document_format == DocumentFormat.PDF:
                # Use centralized PDFRedactionService for memory-based processing
                redactor = PDFRedactionService(document_stream)
                redacted_path = redactor.apply_redactions(redaction_mapping, output_path)
                redactor.close()
            else:
                # For non-PDF formats, use a temporary file approach
                with SecureTempFileManager.create_temp_file(
                    suffix=f".{document_format.name.lower()}",
                    content=document_stream
                ) as temp_path:
                    redactor = DocumentProcessingFactory.create_document_redactor(temp_path, document_format)
                    redacted_path = redactor.apply_redactions(redaction_mapping, output_path)
                    redactor.close()

            redact_time = time.time() - redact_start
            performance_metrics["redaction_time"] = redact_time
            log_info(f"[PERF] Stream redaction completed in {redact_time:.2f}s")

            # Collect statistics
            stats = await self._collect_processing_stats(minimized_data, entities, redaction_mapping)
            stats["performance"] = performance_metrics
            stats["total_time"] = time.time() - start_time

            total_time = time.time() - start_time
            log_info(f"[PERF] Total stream processing time: {total_time:.2f}s")
            log_sensitive_operation(
                "Stream Document Processing",
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
            return {
                "status": "success",
                "output_path": output_path,
                "entities_detected": len(entities),
                "stats": stats
            }
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

    async def process_batch_documents(
            self,
            input_paths: List[str],
            output_paths: List[str],
            requested_entities: Optional[Union[str, List[str]]] = None,
            detection_engine: EntityDetectionEngine = EntityDetectionEngine.PRESIDIO,
            document_formats: Optional[List[DocumentFormat]] = None,
            max_workers: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Process multiple documents in parallel using the centralized batch processing functionality.

        Args:
            input_paths: List of paths to input documents
            output_paths: List of paths to save redacted documents
            requested_entities: JSON string or list of entity types to detect
            detection_engine: Entity detection engine to use
            document_formats: Optional list of document formats
            max_workers: Maximum number of parallel workers (None for auto)

        Returns:
            Dictionary with processing results and statistics
        """
        if len(input_paths) != len(output_paths):
            return {
                "status": "error",
                "error": "Input and output path lists must have the same length"
            }

        start_time = time.time()
        batch_id = f"batch_{uuid.uuid4().hex[:8]}"
        entity_list = []

        # Validate requested entities
        try:
            if isinstance(requested_entities, str):
                entity_list = validate_requested_entities(requested_entities)
            else:
                entity_list = requested_entities or []
        except Exception as e:
            return {
                "status": "error",
                "error": f"Invalid requested entities: {str(e)}"
            }

        # Step 1: Extract text from all documents in parallel
        extract_start = time.time()
        log_info(f"[BATCH] Extracting text from {len(input_paths)} documents")

        try:
            extraction_results = await DocumentProcessingFactory.extract_batch_documents(
                input_paths,
                document_formats=document_formats,
                max_workers=max_workers,
                detect_images=True
            )

            extract_time = time.time() - extract_start
            log_info(f"[PERF] Batch extraction completed in {extract_time:.2f}s")
        except Exception as e:
            log_error(f"[ERROR] Batch extraction failed: {str(e)}")
            return {
                "status": "error",
                "error": f"Batch extraction failed: {str(e)}",
                "processing_time": time.time() - start_time
            }

        # Step 2: Apply data minimization to all extracted data
        minimized_data_list = []
        for idx, result in extraction_results:
            if "error" in result:
                minimized_data_list.append((idx, result))
            else:
                minimized_data = minimize_extracted_data(result)
                minimized_data_list.append((idx, minimized_data))

        # Step 3: Get entity detector
        detector_start = time.time()
        log_info(f"[BATCH] Getting {detection_engine.name} detector")

        config = None
        if detection_engine == EntityDetectionEngine.HYBRID:
            config = {
                "use_presidio": True,
                "use_gemini": True,
                "use_gliner": False
            }

        detector = initialization_service.get_detector(detection_engine, config=config)
        detector_time = time.time() - detector_start

        # Step 4: Detect sensitive data in all documents
        detection_start = time.time()
        log_info(f"[BATCH] Detecting entities in {len(minimized_data_list)} documents")

        detection_results = []

        # Process each document for entity detection
        async def detect_document(idx, data):
            if "error" in data:
                return idx, {"error": data["error"]}

            try:
                if hasattr(detector, 'detect_sensitive_data_async'):
                    anonymized_text, entities, redaction_mapping = await detector.detect_sensitive_data_async(
                        data, entity_list
                    )
                else:
                    anonymized_text, entities, redaction_mapping = await asyncio.to_thread(
                        detector.detect_sensitive_data, data, entity_list
                    )

                return idx, {
                    "anonymized_text": anonymized_text,
                    "entities": entities,
                    "redaction_mapping": redaction_mapping
                }
            except Exception as e:
                log_error(f"[ERROR] Detection failed for document {idx}: {str(e)}")
                return idx, {"error": str(e)}

        # Determine optimal batch size for detection
        batch_size = max_workers or 4

        # Create tasks for parallel detection
        detection_tasks = []
        for idx, data in minimized_data_list:
            detection_tasks.append(detect_document(idx, data))

        # Run detection in parallel
        detection_results = await asyncio.gather(*detection_tasks)
        detection_time = time.time() - detection_start
        log_info(f"[PERF] Batch detection completed in {detection_time:.2f}s")

        # Step 5: Apply redactions to all documents
        redact_start = time.time()
        log_info(f"[BATCH] Applying redactions to {len(detection_results)} documents")

        # Prepare redaction mappings and filter out documents with errors
        valid_redactions = []
        documents_to_redact = []
        output_paths_to_use = []
        document_formats_to_use = []

        for idx, result in detection_results:
            if "error" not in result:
                valid_redactions.append((idx, result["redaction_mapping"]))
                documents_to_redact.append(input_paths[idx])
                output_paths_to_use.append(output_paths[idx])
                doc_format = None
                if document_formats and idx < len(document_formats):
                    doc_format = document_formats[idx]
                document_formats_to_use.append(doc_format)

        # Redact documents in parallel
        if valid_redactions:
            try:
                redaction_results = await DocumentProcessingFactory.redact_batch_documents(
                    [input_paths[idx] for idx, _ in valid_redactions],
                    [mapping for _, mapping in valid_redactions],
                    [output_paths[idx] for idx, _ in valid_redactions],
                    document_formats=[document_formats[idx] if document_formats and idx < len(document_formats) else None
                                     for idx, _ in valid_redactions],
                    max_workers=max_workers
                )
            except Exception as e:
                log_error(f"[ERROR] Batch redaction failed: {str(e)}")
                redaction_results = []
        else:
            redaction_results = []

        redact_time = time.time() - redact_start
        log_info(f"[PERF] Batch redaction completed in {redact_time:.2f}s")

        # Step 6: Combine all results
        total_time = time.time() - start_time

        # Calculate statistics
        successful = 0
        failed = 0
        total_entities = 0
        file_results = []

        # Process all detection results
        for idx, result in detection_results:
            if "error" in result:
                file_results.append({
                    "file": input_paths[idx],
                    "status": "error",
                    "error": result["error"]
                })
                failed += 1
            else:
                # Look for corresponding redaction result
                redacted = False
                for redact_idx, redact_result in redaction_results:
                    if redact_idx == idx and redact_result.get("status") == "success":
                        file_results.append({
                            "file": input_paths[idx],
                            "status": "success",
                            "output_path": redact_result.get("output_path", output_paths[idx]),
                            "entities_detected": len(result.get("entities", []))
                        })
                        redacted = True
                        successful += 1
                        total_entities += len(result.get("entities", []))
                        break

                if not redacted:
                    file_results.append({
                        "file": input_paths[idx],
                        "status": "error",
                        "error": "Redaction failed"
                    })
                    failed += 1

        # Record processing for GDPR compliance
        record_keeper.record_processing(
            operation_type="batch_document_processing",
            document_type="multiple",
            entity_types_processed=entity_list,
            processing_time=total_time,
            file_count=len(input_paths),
            entity_count=total_entities,
            success=(successful > 0)
        )

        log_sensitive_operation(
            "Batch Document Processing",
            total_entities,
            total_time,
            files=len(input_paths),
            successful=successful,
            engine=detection_engine.name,
            extraction_time=extract_time,
            detection_time=detection_time,
            redaction_time=redact_time
        )

        return {
            "status": "success",
            "batch_summary": {
                "batch_id": batch_id,
                "total_files": len(input_paths),
                "successful": successful,
                "failed": failed,
                "total_entities": total_entities,
                "total_time": total_time,
                "extraction_time": extract_time,
                "detection_time": detection_time,
                "redaction_time": redact_time
            },
            "file_results": file_results
        }

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