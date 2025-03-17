"""
Domain package for core domain entities and interfaces.

This package defines the core domain model and interfaces for the
document processing system.
"""
from backend.app.domain.interfaces import (
    DocumentExtractor,
    EntityDetector,
    DocumentRedactor,
    PDFEntityMapping
)
from backend.app.domain.models import (
    EntityInfo,
    BoundingBox,
    SensitiveEntity,
    PageInfo,
    RedactionMapping,
    Word,
    Page,
    ExtractedData,
    EntityDetectionResult
)

# Export classes
__all__ = [
    "DocumentExtractor",
    "EntityDetector",
    "DocumentRedactor",
    "PDFEntityMapping",
    "EntityInfo",
    "BoundingBox",
    "SensitiveEntity",
    "PageInfo",
    "RedactionMapping",
    "Word",
    "Page",
    "ExtractedData",
    "EntityDetectionResult"
]