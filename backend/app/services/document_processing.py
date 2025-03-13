"""
 document processing orchestration services.

This module provides high-level services for orchestrating the entire
document processing workflow with improved parallel processing.
"""
import os
import time
import asyncio
from typing import Dict, Any, List, Optional, Union, Tuple

from backend.app.utils.logger import log_info, log_warning, log_error
from backend.app.utils.helpers.json_helper import validate_requested_entities
from backend.app.utils.helpers.parallel_helper import ParallelProcessingHelper
from backend.app.factory.document_processing import (
    DocumentProcessingFactory,
    DocumentFormat,
    EntityDetectionEngine
)
from backend.app.services.initialization_service import initialization_service


class DocumentProcessingService:
    """
    High-level service for orchestrating document processing workflows with  performance.

    Features:
    - Uses cached detector instances from initialization service
    - Parallel processing of documents and pages
    - Performance monitoring and statistics
    - Adaptive resource allocation
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
        Process a document for sensitive information and apply redactions asynchronously.

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

        try:
            # Validate requested entities
            if isinstance(requested_entities, str):
                entity_list = validate_requested_entities(requested_entities)
            else:
                entity_list = requested_entities

            # Step 1: Create document extractor
            extractor = DocumentProcessingFactory.create_document_extractor(
                input_path, document_format
            )

            # Step 2: Extract text with positions
            extract_start = time.time()
            log_info(f"[OK] Extracting text from document: {input_path}")
            extracted_data = extractor.extract_text_with_positions()
            extractor.close()

            extract_time = time.time() - extract_start
            performance_metrics["extraction_time"] = extract_time
            log_info(f"[PERF] Text extraction completed in {extract_time:.2f}s")

            # Step 3: Get entity detector from initialization service
            detector_start = time.time()
            log_info(f"[OK] Getting cached {detection_engine.name} detector")

            if detection_engine == EntityDetectionEngine.PRESIDIO:
                detector = initialization_service.get_presidio_detector()
            elif detection_engine == EntityDetectionEngine.GEMINI:
                detector = initialization_service.get_gemini_detector()
            elif detection_engine == EntityDetectionEngine.GLINER:
                detector = initialization_service.get_gliner_detector(entity_list)
            else:
                # For any other engine, create a new instance
                detector = DocumentProcessingFactory.create_entity_detector(detection_engine)

            detector_time = time.time() - detector_start
            performance_metrics["detector_init_time"] = detector_time

            # Step 4: Detect sensitive data
            detection_start = time.time()
            log_info(f"[OK] Detecting sensitive information using {detection_engine.name}")

            if hasattr(detector, 'detect_sensitive_data_async'):
                # Use async version if available
                anonymized_text, entities, redaction_mapping = await detector.detect_sensitive_data_async(
                    extracted_data, entity_list
                )
            else:
                # Fall back to sync version if needed
                anonymized_text, entities, redaction_mapping = await asyncio.to_thread(
                    detector.detect_sensitive_data,
                    extracted_data, entity_list
                )

            detection_time = time.time() - detection_start
            performance_metrics["detection_time"] = detection_time
            log_info(f"[PERF] Entity detection completed in {detection_time:.2f}s")

            # Step 5: Create document redactor
            redact_start = time.time()
            redactor = DocumentProcessingFactory.create_document_redactor(
                input_path, document_format
            )

            # Step 6: Apply redactions
            log_info(f"[OK] Applying redactions and saving to: {output_path}")
            redacted_path = await asyncio.to_thread(
                redactor.apply_redactions,
                redaction_mapping, output_path
            )

            redact_time = time.time() - redact_start
            performance_metrics["redaction_time"] = redact_time
            log_info(f"[PERF] Redaction completed in {redact_time:.2f}s")

            # Collect statistics
            stats = await self._collect_processing_stats(extracted_data, entities, redaction_mapping)

            # Add performance metrics
            stats["performance"] = performance_metrics
            stats["total_time"] = time.time() - start_time

            # Log final timing
            total_time = time.time() - start_time
            log_info(f"[PERF] Total document processing time: {total_time:.2f}s")
            log_info(f"[PERF] Extraction: {extract_time:.2f}s ({extract_time/total_time*100:.1f}%) | "
                    f"Detection: {detection_time:.2f}s ({detection_time/total_time*100:.1f}%) | "
                    f"Redaction: {redact_time:.2f}s ({redact_time/total_time*100:.1f}%)")

            return {
                "status": "success",
                "input_path": input_path,
                "output_path": redacted_path,
                "entities_detected": len(entities),
                "stats": stats
            }

        except Exception as e:
            total_time = time.time() - start_time
            log_error(f"[ERROR] Error processing document ({total_time:.2f}s): {e}")
            return {
                "status": "error",
                "input_path": input_path,
                "error": str(e),
                "processing_time": total_time
            }

    def process_document(
            self,
            input_path: str,
            output_path: str,
            requested_entities: Optional[Union[str, List[str]]] = None,
            detection_engine: EntityDetectionEngine = EntityDetectionEngine.PRESIDIO,
            document_format: Optional[DocumentFormat] = None
    ) -> Dict[str, Any]:
        """
        Process a document for sensitive information and apply redactions.
        Synchronous wrapper around the async version.

        Args:
            input_path: Path to the input document
            output_path: Path to save the redacted document
            requested_entities: JSON string or list of entity types to detect
            detection_engine: Entity detection engine to use
            document_format: Format of the document (optional, will be detected if not provided)

        Returns:
            Dictionary with processing results and statistics
        """
        try:
            # Try to use an existing event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're already in an event loop, create a new one
                new_loop = asyncio.new_event_loop()
                try:
                    return new_loop.run_until_complete(
                        self.process_document_async(
                            input_path, output_path, requested_entities,
                            detection_engine, document_format
                        )
                    )
                finally:
                    new_loop.close()
            else:
                # Use the existing loop
                return loop.run_until_complete(
                    self.process_document_async(
                        input_path, output_path, requested_entities,
                        detection_engine, document_format
                    )
                )
        except RuntimeError:
            # No event loop available, create one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    self.process_document_async(
                        input_path, output_path, requested_entities,
                        detection_engine, document_format
                    )
                )
            finally:
                loop.close()

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
        # Count words across all pages
        total_words = sum(
            len(page.get("words", []))
            for page in extracted_data.get("pages", [])
        )

        # Count entities by type
        entities_by_type = {}
        for entity in entities:
            entity_type = entity.get("entity_type", "UNKNOWN")
            entities_by_type[entity_type] = entities_by_type.get(entity_type, 0) + 1

        # Count sensitive items per page
        sensitive_by_page = {}
        for page_info in redaction_mapping.get("pages", []):
            page_num = page_info.get("page")
            sensitive_items = page_info.get("sensitive", [])
            sensitive_by_page[f"page_{page_num}"] = len(sensitive_items)

        # Calculate entity density
        entity_density = (len(entities) / total_words) * 1000 if total_words > 0 else 0

        return {
            "total_pages": len(extracted_data.get("pages", [])),
            "total_words": total_words,
            "total_entities": len(entities),
            "entity_density": entity_density,  # Entities per 1000 words
            "entities_by_type": entities_by_type,
            "sensitive_by_page": sensitive_by_page
        }


class BatchDocumentProcessingService:
    """
    Service for processing multiple documents in batch with parallel processing.
    """

    def __init__(self):
        """Initialize the service."""
        self.document_service = DocumentProcessingService()

    async def process_documents_async(
            self,
            input_files: List[str],
            output_dir: str,
            requested_entities: Optional[Union[str, List[str]]] = None,
            detection_engine: EntityDetectionEngine = EntityDetectionEngine.PRESIDIO,
            max_parallel_docs: int = 4
    ) -> List[Dict[str, Any]]:
        """
        Process multiple documents for sensitive information and apply redactions asynchronously.

        Args:
            input_files: List of paths to input documents
            output_dir: Directory to save redacted documents
            requested_entities: JSON string or list of entity types to detect
            detection_engine: Entity detection engine to use
            max_parallel_docs: Maximum number of documents to process in parallel

        Returns:
            List of dictionaries with processing results
        """
        start_time = time.time()

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        # Prepare document processing tasks
        async def process_doc(input_file):
            # Generate output path
            filename = os.path.basename(input_file)
            base_name, ext = os.path.splitext(filename)
            output_path = os.path.join(output_dir, f"{base_name}_redacted{ext}")

            # Process document
            return await self.document_service.process_document_async(
                input_file,
                output_path,
                requested_entities,
                detection_engine
            )

        # Process documents in parallel
        log_info(f"[OK] Starting batch processing of {len(input_files)} documents")

        # Use adaptive concurrency based on number of documents
        optimal_workers = ParallelProcessingHelper.get_optimal_workers(
            len(input_files),
            min_workers=1,
            max_workers=max_parallel_docs
        )

        results, stats = await ParallelProcessingHelper.process_items_in_parallel(
            input_files,
            process_doc,
            max_workers=optimal_workers
        )

        # Collect batch statistics
        success_count = sum(1 for r in results if r.get("status") == "success")
        error_count = len(results) - success_count

        batch_time = time.time() - start_time
        log_info(f"[PERF] Batch processing completed in {batch_time:.2f}s. "
                f"Successful: {success_count}, Failed: {error_count}")

        # Add batch statistics
        batch_stats = {
            "total_documents": len(input_files),
            "successful": success_count,
            "failed": error_count,
            "total_time": batch_time,
            "avg_time_per_doc": batch_time / len(input_files) if input_files else 0,
            "parallel_workers": optimal_workers,
            **stats
        }

        # Add batch statistics to each result
        for result in results:
            result["batch_stats"] = batch_stats

        return results

    def process_documents(
            self,
            input_files: List[str],
            output_dir: str,
            requested_entities: Optional[Union[str, List[str]]] = None,
            detection_engine: EntityDetectionEngine = EntityDetectionEngine.PRESIDIO,
            max_parallel_docs: int = 4
    ) -> List[Dict[str, Any]]:
        """
        Process multiple documents for sensitive information and apply redactions.
        Synchronous wrapper around the async version.

        Args:
            input_files: List of paths to input documents
            output_dir: Directory to save redacted documents
            requested_entities: JSON string or list of entity types to detect
            detection_engine: Entity detection engine to use
            max_parallel_docs: Maximum number of documents to process in parallel

        Returns:
            List of dictionaries with processing results
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self.process_documents_async(
                    input_files, output_dir, requested_entities,
                    detection_engine, max_parallel_docs
                )
            )
        finally:
            loop.close()