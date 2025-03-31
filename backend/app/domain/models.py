"""
Domain models for document processing.

This module contains data classes and models that represent the core domain entities.
"""
from typing import List, Optional
from pydantic import BaseModel


class EntityInfo(BaseModel):
    """Information about a detected entity."""
    entity_type: str
    start: int
    end: int
    score: float
    original_text: Optional[str] = None


class BoundingBox(BaseModel):
    """Bounding box information for a word or entity."""
    x0: float
    y0: float
    x1: float
    y1: float


class SensitiveEntity(BaseModel):
    """Information about a sensitive entity with its bounding box."""
    original_text: str
    entity_type: str
    start: int
    end: int
    score: float
    bbox: BoundingBox


class PageInfo(BaseModel):
    """Information about a page with its sensitive entities."""
    page: int
    sensitive: List[SensitiveEntity]


class RedactionMapping(BaseModel):
    """Mapping of sensitive entities for redaction."""
    pages: List[PageInfo]


class Word(BaseModel):
    """Information about a word with its position."""
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


class Page(BaseModel):
    """Information about a page with its words."""
    page: int
    words: List[Word]


class ExtractedData(BaseModel):
    """Extracted text data from a document."""
    pages: List[Page]


class EntityDetectionResult(BaseModel):
    """Result of entity detection."""
    entities: List[EntityInfo]
    redaction_mapping: RedactionMapping