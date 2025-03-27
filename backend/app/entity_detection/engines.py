from enum import Enum, auto


class EntityDetectionEngine(Enum):
    """Supported entity detection engines."""
    PRESIDIO = auto()
    GEMINI = auto()
    GLINER = auto()
    HYBRID = auto()  # Uses multiple engines and combines results