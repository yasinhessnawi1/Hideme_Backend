"""
Domain package for core domain entities and interfaces.

This package defines the core domain model and interfaces for the
document processing system.
"""
from backend.app.domain.interfaces import (
    DocumentExtractor,
    EntityDetector,
    DocumentRedactor,
    EntityMappingService
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
    "EntityMappingService",
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