"""
Services package for orchestrating document processing.

This package contains high-level services that coordinate the various
components of the document processing system.
"""
from backend.app.services.configuration import config_service
from backend.app.services.document_processing import (
    DocumentProcessingService,

)
from backend.app.services.batch_processing_service import BatchProcessingService

# Export classes and instances
__all__ = [
    "config_service",
    "DocumentProcessingService",
    "BatchProcessingService"
]