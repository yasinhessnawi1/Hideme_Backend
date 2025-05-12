"""
Domain package for core domain  interfaces.

This package defines the core domain interfaces for the
document processing system.
"""

from backend.app.domain.interfaces import (
    DocumentExtractor,
    EntityDetector,
    DocumentRedactor,
    PDFEntityMapping,
)

# Export classes
__all__ = [
    "DocumentExtractor",
    "EntityDetector",
    "DocumentRedactor",
    "PDFEntityMapping",
]
