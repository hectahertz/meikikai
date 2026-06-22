# meikikai/ocr/interface.py
import abc
from dataclasses import dataclass
from typing import List, Optional

from PIL import Image


@dataclass(frozen=True)
class BoundingBox:
    """A normalized bounding box. All coordinates are floats between 0.0 and 1.0."""
    center_x: float
    center_y: float
    width: float
    height: float


@dataclass(frozen=True)
class Word:
    """Represents a single word recognized by the OCR."""
    text: str  # this can be either a word or a single character
    separator: str  # The separator that follows the word (e.g., a space) - optional
    box: BoundingBox


@dataclass(frozen=True)
class Paragraph:
    """Represents a block of text, composed of words."""
    full_text: str
    words: List[Word]
    box: BoundingBox
    is_vertical: bool  # True if text is top-to-bottom - optional


@dataclass(frozen=True)
class LookupContext:
    """OCR context for the character under the cursor."""
    lookup_text: str
    full_text: str
    hit_index: int
    is_vertical: bool


class OcrProvider(abc.ABC):
    """Abstract base class for MeikiKai's OCR backend."""

    @property
    @abc.abstractmethod
    def NAME(self) -> str:
        """A user-friendly name for this provider."""
        raise NotImplementedError

    @abc.abstractmethod
    def scan(self, image: Image.Image) -> Optional[List[Paragraph]]:
        """
        Performs OCR on the given image.

        Args:
            image: A PIL Image object to perform OCR on.

        Returns:
            A list of Paragraph objects found in the image, or None if an
            error occurred. Returns an empty list if no text is found.
        """
        raise NotImplementedError
