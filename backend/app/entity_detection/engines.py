"""
Enum representing the supported entity detection engines.
"""

from enum import Enum, auto


class EntityDetectionEngine(Enum):
    """
    Enum representing the supported entity detection engines.

    Attributes:
        PRESIDIO: Engine using Presidio for entity detection.
        GEMINI: Engine using Gemini for entity detection.
        GLINER: Engine using Gliner for entity detection.
        HIDEME: Engine using HIDEME for entity detection.
        HYBRID: Engine that utilizes multiple engines (combination of results)
                to enhance entity detection accuracy.
    """

    PRESIDIO = auto()
    GEMINI = auto()
    GLINER = auto()
    HIDEME = auto()
    HYBRID = auto()
