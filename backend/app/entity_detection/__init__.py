"""
Entity detection package.

This package contains implementations for detecting sensitive entities
in text using various detection engines.
"""
from backend.app.entity_detection.base import BaseEntityDetector
from backend.app.entity_detection.presidio import PresidioEntityDetector
from backend.app.entity_detection.gemini import GeminiEntityDetector
from backend.app.entity_detection.gliner import GlinerEntityDetector

# Export classes
__all__ = [
    "BaseEntityDetector",
    "PresidioEntityDetector",
    "GeminiEntityDetector",
    "GlinerEntityDetector"
]