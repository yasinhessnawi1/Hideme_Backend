"""
Services package for orchestrating document processing.

This package contains high-level services that coordinate the various
components of the document processing system.
"""
from backend.app.services.batch_detect_service import BatchDetectService
from backend.app.services.batch_extract_service import BatchExtractService
from backend.app.services.batch_redact_service import BatchRedactService

# Export classes and instances
__all__ = [
    "BatchDetectService",
    "BatchExtractService",
    "BatchRedactService"
]
